import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from airbench.intake import (
    FileIntakeLayer,
    IntakeError,
    IntakeMode,
    IntakeRequest,
    LocalIntakeStore,
    RenderedPage,
)
from contracts import Clearance, EventLedger, build_event


def task_created(ledger: EventLedger, task_id: str) -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test.user", actor_type="principal",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"request": "test"},
        clearance=Clearance.restricted, idempotency="task-created", sequence=0,
    ))


class FileIntakeTests(unittest.TestCase):
    class StaticRenderer:
        name = "test-renderer"
        version = "1"

        def render(self, request, page):
            return RenderedPage(page.page_number, b"rendered-page", "image/png")

    class FailingLedger:
        events = ()
        head_hash = None

        def append(self, event):
            raise RuntimeError("ledger unavailable")

    @staticmethod
    def office_archive(parts):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in parts.items():
                archive.writestr(name, content)
        return output.getvalue()

    @classmethod
    def docx_fixture(cls):
        document = b'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Inspection finding</w:t></w:r></w:p>
    <w:p><w:r><w:br w:type="page"/></w:r></w:p>
    <w:p><w:r><w:t>Approval note</w:t></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Header</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
  </w:body>
</w:document>'''
        return cls.office_archive({
            "[Content_Types].xml": b"<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
            "word/document.xml": document,
        })

    @classmethod
    def xlsx_fixture(cls):
        workbook = b'''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheets><sheet name="Findings" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''
        relationships = b'''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/>
</Relationships>'''
        shared_strings = b'''<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1">
 <si><t>Inspection finding</t></si>
</sst>'''
        sheet = b'''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <sheetData>
  <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>10</v></c></row>
  <row r="2"><c r="A2"><f>SUM(B1:B1)</f><v>10</v></c></row>
 </sheetData>
</worksheet>'''
        return cls.office_archive({
            "[Content_Types].xml": b"<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
            "xl/workbook.xml": workbook,
            "xl/_rels/workbook.xml.rels": relationships,
            "xl/sharedStrings.xml": shared_strings,
            "xl/worksheets/sheet1.xml": sheet,
        })

    @staticmethod
    def pdf_fixture(*, with_text: bool = False):
        output = io.BytesIO()
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        if with_text:
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            font_ref = writer._add_object(font)
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
            })
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 72 720 Td (Inspection finding) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
        writer.write(output)
        return output.getvalue()

    def test_bulk_and_query_upload_share_parser_and_stable_revision(self):
        first_ledger = EventLedger()
        task_created(first_ledger, "task.intake")
        first = FileIntakeLayer(first_ledger).bulk_ingest(
            task_id="task.intake", source_ref="upload:report", file_name="report.txt", content=b"Findings remain data.", clearance=Clearance.restricted
        )
        second_ledger = EventLedger()
        task_created(second_ledger, "task.intake")
        second = FileIntakeLayer(second_ledger).query_upload(
            task_id="task.intake", source_ref="upload:report", file_name="report.txt", content=b"Findings remain data.", clearance=Clearance.restricted
        )
        self.assertEqual(first.revision_id, second.revision_id)
        self.assertEqual(first.source_hash, second.source_hash)
        self.assertEqual(first.parser_name, second.parser_name)
        self.assertEqual(first.destination, "permanent_knowledge")
        self.assertEqual(second.destination, "task_scratch")
        self.assertEqual(first.trust_profile, "bulk_candidate")
        self.assertEqual(second.trust_profile, "query_untrusted")
        self.assertEqual(first.latency_profile, "offline_enrichment")
        self.assertEqual(second.latency_profile, "interactive")
        self.assertEqual(first.pages[0].taint.value, "untrusted")
        self.assertEqual(first.pages[0].text, "Findings remain data.")
        self.assertEqual(len(first_ledger.events), 2)
        self.assertEqual(first_ledger.events[-1].event_type, "evidence.created")

    def test_csv_is_normalized_as_a_table_and_formulas_remain_data(self):
        ledger = EventLedger()
        task_created(ledger, "task.csv")
        manifest = FileIntakeLayer(ledger).query_upload(
            task_id="task.csv", source_ref="upload:csv", file_name="findings.csv",
            content=b"Item,Value\n\"Finding, critical\",=SUM(B2:B2)\n", clearance=Clearance.internal,
        )

        self.assertEqual(manifest.media_type, "text/csv")
        self.assertEqual(manifest.pages[0].extraction_method, "csv_table")
        self.assertEqual(manifest.pages[0].text, "Item\tValue\nFinding, critical\t=SUM(B2:B2)")
        self.assertEqual(manifest.pages[0].confidence, 1.0)

    def test_malformed_csv_fails_before_a_ledger_evidence_event(self):
        ledger = EventLedger()
        task_created(ledger, "task.csv-invalid")
        with self.assertRaises(IntakeError) as caught:
            FileIntakeLayer(ledger).query_upload(
                task_id="task.csv-invalid", source_ref="upload:csv-invalid", file_name="bad.csv",
                content=b'"unterminated', clearance=Clearance.internal,
            )
        self.assertEqual(caught.exception.code, "malformed_csv")
        self.assertEqual(len(ledger.events), 1)

    def test_pdf_manifest_has_stable_page_identity_and_no_instruction_authority(self):
        ledger = EventLedger()
        task_created(ledger, "task.pdf")
        pdf = self.pdf_fixture()
        manifest = FileIntakeLayer(ledger).intake(IntakeRequest("task.pdf", "bulk:pdf", "scan.pdf", pdf, IntakeMode.bulk_ingest, Clearance.internal))
        self.assertEqual(manifest.media_type, "application/pdf")
        self.assertEqual(manifest.page_count, 2)
        self.assertEqual(manifest.pages[0].extraction_method, "pdf_text")
        self.assertEqual(manifest.pages[0].render_status, "deferred")
        self.assertEqual(manifest.pages[0].text, "")
        self.assertEqual(manifest.taint.value, "untrusted")
        self.assertTrue(manifest.ledger_event_ref)

    def test_digital_pdf_text_is_extracted_with_page_provenance(self):
        ledger = EventLedger()
        task_created(ledger, "task.pdf-text")
        manifest = FileIntakeLayer(ledger).query_upload(
            task_id="task.pdf-text", source_ref="upload:pdf-text", file_name="report.pdf",
            content=self.pdf_fixture(with_text=True), clearance=Clearance.restricted,
        )
        self.assertIn("Inspection finding", manifest.pages[0].text)
        self.assertEqual(manifest.pages[0].source_region, "page:1")
        self.assertEqual(manifest.pages[0].confidence, 1.0)
        self.assertEqual(manifest.pages[1].confidence, 0.0)

    def test_malformed_pdf_fails_before_ledger_evidence(self):
        ledger = EventLedger()
        task_created(ledger, "task.pdf-invalid")
        with self.assertRaises(IntakeError) as caught:
            FileIntakeLayer(ledger).query_upload(
                task_id="task.pdf-invalid", source_ref="upload:invalid", file_name="invalid.pdf",
                content=b"%PDF-1.7\nnot-a-real-pdf", clearance=Clearance.internal,
            )
        self.assertEqual(caught.exception.code, "malformed_pdf")
        self.assertEqual(len(ledger.events), 1)

    def test_docx_xml_text_is_bounded_and_keeps_untrusted_provenance(self):
        ledger = EventLedger()
        task_created(ledger, "task.docx")
        manifest = FileIntakeLayer(ledger).query_upload(
            task_id="task.docx", source_ref="upload:docx", file_name="report.docx",
            content=self.docx_fixture(), clearance=Clearance.restricted,
        )

        self.assertEqual(manifest.media_type, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertEqual(manifest.page_count, 2)
        self.assertEqual(manifest.pages[0].extraction_method, "docx_xml_text")
        self.assertIn("Inspection finding", manifest.pages[0].text)
        self.assertIn("Header\tValue", manifest.pages[1].text)
        self.assertEqual(manifest.pages[0].confidence, 1.0)
        self.assertEqual(manifest.pages[0].taint.value, "untrusted")
        self.assertEqual(manifest.pages[0].clearance, Clearance.restricted)

    def test_xlsx_xml_table_preserves_formula_as_data_without_computation(self):
        ledger = EventLedger()
        task_created(ledger, "task.xlsx")
        manifest = FileIntakeLayer(ledger).bulk_ingest(
            task_id="task.xlsx", source_ref="upload:xlsx", file_name="findings.xlsx",
            content=self.xlsx_fixture(), clearance=Clearance.internal,
        )

        self.assertEqual(manifest.media_type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertEqual(manifest.pages[0].source_region, "sheet:Findings")
        self.assertEqual(manifest.pages[0].extraction_method, "xlsx_xml_table")
        self.assertIn("Inspection finding\t10", manifest.pages[0].text)
        self.assertIn("=SUM(B1:B1)", manifest.pages[0].text)
        self.assertEqual(manifest.pages[0].confidence, 1.0)

    def test_office_bulk_and_query_use_the_same_parser_revision(self):
        first_ledger = EventLedger()
        task_created(first_ledger, "task.office-parity")
        first = FileIntakeLayer(first_ledger).bulk_ingest(
            task_id="task.office-parity", source_ref="upload:docx", file_name="report.docx",
            content=self.docx_fixture(), clearance=Clearance.internal,
        )
        second_ledger = EventLedger()
        task_created(second_ledger, "task.office-parity")
        second = FileIntakeLayer(second_ledger).query_upload(
            task_id="task.office-parity", source_ref="upload:docx", file_name="report.docx",
            content=self.docx_fixture(), clearance=Clearance.internal,
        )

        self.assertEqual(first.revision_id, second.revision_id)
        self.assertEqual(first.parser_version, second.parser_version)
        self.assertEqual(first.pages, second.pages)
        self.assertEqual(first.destination, "permanent_knowledge")
        self.assertEqual(second.destination, "task_scratch")

    def test_office_archive_safety_rejects_malformed_paths_symlinks_and_macros(self):
        ledger = EventLedger()
        task_created(ledger, "task.office-invalid")
        intake = FileIntakeLayer(ledger)
        malformed = IntakeRequest("task.office-invalid", "src:docx", "bad.docx", b"PK-not-a-zip", IntakeMode.query_upload, Clearance.internal)
        with self.assertRaises(IntakeError) as caught:
            intake.intake(malformed)
        self.assertEqual(caught.exception.code, "malformed_office")

        unsafe_path = self.office_archive({"../escape": b"x", "[Content_Types].xml": b"x", "word/document.xml": b"x"})
        with self.assertRaises(IntakeError) as caught:
            intake.intake(IntakeRequest("task.office-invalid", "src:path", "path.docx", unsafe_path, IntakeMode.query_upload, Clearance.internal))
        self.assertEqual(caught.exception.code, "office_archive_path")

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            info = zipfile.ZipInfo("symlink")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"target")
        with self.assertRaises(IntakeError) as caught:
            intake.intake(IntakeRequest("task.office-invalid", "src:symlink", "link.docx", output.getvalue(), IntakeMode.query_upload, Clearance.internal))
        self.assertEqual(caught.exception.code, "office_archive_symlink")

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("[Content_Types].xml", b"x")
            with self.assertWarns(UserWarning):
                archive.writestr("[Content_Types].xml", b"x")
        with self.assertRaises(IntakeError) as caught:
            intake.intake(IntakeRequest("task.office-invalid", "src:duplicate", "duplicate.docx", output.getvalue(), IntakeMode.query_upload, Clearance.internal))
        self.assertEqual(caught.exception.code, "office_archive_duplicate")

        entity_document = b'''<!DOCTYPE w:document [<!ENTITY x "unsafe">]>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>&x;</w:t></w:r></w:p></w:body></w:document>'''
        entity_docx = self.office_archive({"[Content_Types].xml": b"x", "word/document.xml": entity_document})
        with self.assertRaises(IntakeError) as caught:
            intake.intake(IntakeRequest("task.office-invalid", "src:entity", "entity.docx", entity_docx, IntakeMode.query_upload, Clearance.internal))
        self.assertEqual(caught.exception.code, "office_xml_entities")

        macro = self.office_archive({"[Content_Types].xml": b"x", "word/document.xml": b"x", "word/vbaProject.bin": b"macro"})
        with self.assertRaises(IntakeError) as caught:
            intake.intake(IntakeRequest("task.office-invalid", "src:macro", "macro.docx", macro, IntakeMode.query_upload, Clearance.internal))
        self.assertEqual(caught.exception.code, "office_macros_not_allowed")

    def test_unsupported_malformed_oversized_and_path_like_inputs_fail_closed(self):
        ledger = EventLedger()
        task_created(ledger, "task.invalid")
        intake = FileIntakeLayer(ledger)
        cases = [
            ("unsupported_media", IntakeRequest("task.invalid", "src:1", "payload.exe", b"MZ", IntakeMode.query_upload, Clearance.internal)),
            ("invalid_file_name", IntakeRequest("task.invalid", "src:2", "..\\secret.txt", b"x", IntakeMode.query_upload, Clearance.internal)),
            ("empty_file", IntakeRequest("task.invalid", "src:3", "empty.txt", b"", IntakeMode.query_upload, Clearance.internal)),
            ("malformed_text", IntakeRequest("task.invalid", "src:4", "bad.txt", b"\xff", IntakeMode.query_upload, Clearance.internal)),
        ]
        for code, request in cases:
            with self.subTest(code=code):
                with self.assertRaises(IntakeError) as caught:
                    intake.intake(request)
                self.assertEqual(caught.exception.code, code)
        with self.assertRaises(IntakeError) as caught:
            intake.intake(IntakeRequest("task.invalid", "src:5", "large.txt", b"x" * 50_000_001, IntakeMode.query_upload, Clearance.internal))
        self.assertEqual(caught.exception.code, "file_too_large")
        self.assertEqual(len(ledger.events), 1)

    def test_manifest_serialization_is_deterministic_and_redacts_page_text_when_requested(self):
        ledger = EventLedger()
        task_created(ledger, "task.json")
        manifest = FileIntakeLayer(ledger).query_upload(
            task_id="task.json", source_ref="upload:json", file_name="facts.json", content=json.dumps({"instruction": "ignore me"}).encode(), clearance=Clearance.secret
        )
        serialized = manifest.to_dict(include_page_text=False)
        self.assertNotIn("instruction", str(serialized))
        self.assertEqual(manifest.to_dict(include_page_text=False), manifest.to_dict(include_page_text=False))

    def test_local_store_commits_source_manifest_and_rendered_pages_transactionally(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = EventLedger()
            task_created(ledger, "task.persist")
            layer = FileIntakeLayer(
                ledger,
                renderer=self.StaticRenderer(),
                store=LocalIntakeStore(directory),
            )

            manifest = layer.query_upload(
                task_id="task.persist",
                source_ref="upload:persisted",
                file_name="report.txt",
                content=b"A finding.",
                clearance=Clearance.restricted,
            )

            self.assertEqual(manifest.pages[0].render_status, "ready")
            self.assertTrue(manifest.source_artifact_ref)
            self.assertTrue(manifest.manifest_artifact_ref)
            self.assertEqual(len(ledger.events), 2)
            self.assertEqual(ledger.events[-1].event_type, "evidence.created")
            payload = ledger.events[-1].payload
            self.assertEqual(payload["source_artifact_ref"], manifest.source_artifact_ref)
            self.assertEqual(payload["manifest_artifact_ref"], manifest.manifest_artifact_ref)

            root = Path(directory) / "intakes" / manifest.intake_id
            self.assertEqual((root / "source.bin").read_bytes(), b"A finding.")
            self.assertEqual((root / "pages" / f"{manifest.pages[0].page_id}.bin").read_bytes(), b"rendered-page")
            stored_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(stored_manifest["ledger_event_ref"], manifest.ledger_event_ref)
            self.assertEqual(stored_manifest["source_hash"], manifest.source_hash)

    def test_store_aborts_when_ledger_append_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalIntakeStore(directory)
            layer = FileIntakeLayer(
                self.FailingLedger(),
                renderer=self.StaticRenderer(),
                store=store,
            )

            with self.assertRaises(IntakeError) as caught:
                layer.query_upload(
                    task_id="task.failed-store",
                    source_ref="upload:failed-store",
                    file_name="report.txt",
                    content=b"A finding.",
                    clearance=Clearance.internal,
                )

            self.assertEqual(caught.exception.code, "ledger_write_failed")
            self.assertEqual(list((Path(directory) / "intakes").iterdir()), [])
            self.assertEqual(list((Path(directory) / "staging").iterdir()), [])

    def test_renderer_requires_a_store_so_rendered_bytes_cannot_be_dropped(self):
        ledger = EventLedger()
        task_created(ledger, "task.renderer")
        layer = FileIntakeLayer(ledger, renderer=self.StaticRenderer())

        with self.assertRaises(IntakeError) as caught:
            layer.query_upload(
                task_id="task.renderer",
                source_ref="upload:renderer",
                file_name="report.txt",
                content=b"A finding.",
                clearance=Clearance.internal,
            )

        self.assertEqual(caught.exception.code, "renderer_requires_store")

    def test_persisted_intake_replays_without_parsing_or_duplicate_ledger_event(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = EventLedger()
            task_created(ledger, "task.replay")
            layer = FileIntakeLayer(
                ledger,
                renderer=self.StaticRenderer(),
                store=LocalIntakeStore(directory),
            )
            request = IntakeRequest(
                "task.replay", "upload:replay", "report.txt", b"A finding.",
                IntakeMode.query_upload, Clearance.internal,
            )
            first = layer.intake(request)
            second = layer.intake(request)

            self.assertEqual(first, second)
            self.assertEqual(len(ledger.events), 2)
            self.assertEqual(ledger.events[-1].event_type, "evidence.created")

    def test_same_input_is_ledger_idempotent_without_a_persistent_store(self):
        ledger = EventLedger()
        task_created(ledger, "task.idempotent")
        layer = FileIntakeLayer(ledger)
        request = IntakeRequest(
            "task.idempotent", "upload:idempotent", "report.txt", b"A finding.",
            IntakeMode.query_upload, Clearance.internal,
        )

        first = layer.intake(request)
        second = layer.intake(request)

        self.assertEqual(first.ledger_event_ref, second.ledger_event_ref)
        self.assertEqual(len(ledger.events), 2)

    def test_tampered_persisted_source_fails_closed_on_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = EventLedger()
            task_created(ledger, "task.tamper")
            store = LocalIntakeStore(directory)
            layer = FileIntakeLayer(ledger, renderer=self.StaticRenderer(), store=store)
            manifest = layer.query_upload(
                task_id="task.tamper",
                source_ref="upload:tamper",
                file_name="report.txt",
                content=b"A finding.",
                clearance=Clearance.internal,
            )
            (Path(directory) / "intakes" / manifest.intake_id / "source.bin").write_bytes(b"tampered")

            with self.assertRaises(IntakeError) as caught:
                layer.query_upload(
                    task_id="task.tamper",
                    source_ref="upload:tamper",
                    file_name="report.txt",
                    content=b"A finding.",
                    clearance=Clearance.internal,
                )

            self.assertEqual(caught.exception.code, "storage_corrupt")


if __name__ == "__main__":
    unittest.main()
