import json
import tempfile
import unittest
from pathlib import Path

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

    def test_pdf_manifest_has_stable_page_identity_and_no_instruction_authority(self):
        ledger = EventLedger()
        task_created(ledger, "task.pdf")
        pdf = b"%PDF-1.7\n/Type /Page\n/Type /Page\n"
        manifest = FileIntakeLayer(ledger).intake(IntakeRequest("task.pdf", "bulk:pdf", "scan.pdf", pdf, IntakeMode.bulk_ingest, Clearance.internal))
        self.assertEqual(manifest.media_type, "application/pdf")
        self.assertEqual(manifest.page_count, 2)
        self.assertEqual(manifest.pages[0].extraction_method, "pdf_metadata_only")
        self.assertEqual(manifest.pages[0].render_status, "deferred")
        self.assertEqual(manifest.pages[0].text, "")
        self.assertEqual(manifest.taint.value, "untrusted")
        self.assertTrue(manifest.ledger_event_ref)

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
