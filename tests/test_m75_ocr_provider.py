from __future__ import annotations

import io
from hashlib import sha256

import pytest
from pypdf import PdfWriter

from airbench.intake.layer import FileIntakeLayer, IntakeMode, IntakeRequest, LocalIntakeStore, RenderedPage
from airbench.intake.ocr_provider import (
    DeterministicOcrProvider,
    OcrPageInput,
    OcrProviderError,
    build_ocr_provider_from_env,
)
from airbench.intake.table_extractor import GridLineTableExtractor, extract_tables
from airbench.intake.vision import LocalVisionAdapter, ocr_provider_extractor
from contracts import Clearance, EventLedger, Taint, build_event


def _hash(content: bytes) -> str:
    return sha256(content).hexdigest()


def _seed_task(ledger: EventLedger, task_id: str) -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
        clearance=Clearance.restricted, idempotency=f"created-{task_id}", sequence=0,
    ))


def _scanned_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _adapter(content_hash: str, ledger: EventLedger | None = None) -> LocalVisionAdapter:
    provider = DeterministicOcrProvider({
        content_hash: (
            ("Tag\tComponent\tPressure (bar)", 0, 0, 300, 10, 0.95),
            ("V-101\tGate valve\t12.5", 0, 12, 300, 10, 0.90),
            ("V-102\tGlobe valve\t9.0", 0, 24, 300, 10, 0.91),
        ),
    })
    return LocalVisionAdapter(
        adapter_id="airbench.ocr.deterministic", adapter_version="1.0",
        model_target_id="target.ocr.fixture", qualification_reference="qualification.ocr.fixture",
        extractor=ocr_provider_extractor(
            provider, adapter_id="airbench.ocr.deterministic", adapter_version="1.0",
            model_target_id="target.ocr.fixture", qualification_reference="qualification.ocr.fixture",
            table_extractor=GridLineTableExtractor(),
        ),
        ledger=ledger, kind="ocr",
    )


class TestOcrProvider:
    def test_page_input_rejects_hash_mismatch(self) -> None:
        with pytest.raises(OcrProviderError) as caught:
            OcrPageInput(page_number=1, content=b"abc", content_hash="0" * 64, media_type="image/png")
        assert caught.value.code == "content_hash_mismatch"

    def test_deterministic_provider_returns_bbox_and_confidence(self) -> None:
        content = b"page-bytes"
        provider = DeterministicOcrProvider({_hash(content): (("hello world", 5, 6, 40, 12, 0.8),)})
        result = provider.extract(OcrPageInput(page_number=2, content=content, content_hash=_hash(content), media_type="image/png"))
        assert result.text == "hello world"
        assert result.confidence == pytest.approx(0.8)
        line = result.lines[0]
        assert (line.bounding_box.x, line.bounding_box.y, line.bounding_box.width, line.bounding_box.height) == (5, 6, 40, 12)
        assert line.bounding_box.page_number == 2

    def test_env_selection(self) -> None:
        assert build_ocr_provider_from_env({}) is None
        assert build_ocr_provider_from_env({"OCR_PROVIDER": "none"}) is None
        provider = build_ocr_provider_from_env({"OCR_PROVIDER": "tesseract"})
        assert provider is not None and provider.name == "tesseract"
        with pytest.raises(OcrProviderError) as caught:
            build_ocr_provider_from_env({"OCR_PROVIDER": "mystery"})
        assert caught.value.code == "unknown_provider"
        with pytest.raises(OcrProviderError):
            build_ocr_provider_from_env({"OCR_PROVIDER": "vllm_vision"})


class TestTableExtractor:
    def test_extracts_three_column_table_with_units(self) -> None:
        provider = DeterministicOcrProvider({
            _hash(b"t"): (
                ("Tag\tComponent\tPressure (bar)", 0, 0, 300, 10, 0.95),
                ("V-101\tGate valve\t12.5", 0, 12, 300, 10, 0.90),
                ("V-102\tGlobe valve\t9.0", 0, 24, 300, 10, 0.91),
            ),
        })
        result = provider.extract(OcrPageInput(page_number=1, content=b"t", content_hash=_hash(b"t"), media_type="image/png"))
        tables = GridLineTableExtractor().extract(result, source_ref="local:scan.pdf")
        assert len(tables) == 1
        table = tables[0]
        assert table.headers == ("Tag", "Component", "Pressure (bar)")
        assert table.rows == (("V-101", "Gate valve", "12.5"), ("V-102", "Globe valve", "9.0"))
        assert table.units == {"Pressure (bar)": "bar"}
        assert table.source_ref == "local:scan.pdf"

    def test_extract_tables_is_identity_without_extractor(self) -> None:
        result = DeterministicOcrProvider().extract(OcrPageInput(page_number=1, content=b"x", content_hash=_hash(b"x"), media_type="image/png"))
        assert extract_tables(result, None) is result


class _Renderer:
    name = "fixture.pdf-renderer"
    version = "1.0"

    def render(self, _request, page):
        return RenderedPage(page.page_number, b"rendered-scan-bytes", "image/png")


class TestIntakeVisionWiring:
    def test_scanned_page_gets_ocr_text_regions_and_tables(self, tmp_path) -> None:
        ledger = EventLedger()
        _seed_task(ledger, "task.m75")
        adapter = _adapter(_hash(b"rendered-scan-bytes"), ledger)
        layer = FileIntakeLayer(ledger, renderer=_Renderer(), store=LocalIntakeStore(tmp_path / "intake"), vision_adapter=adapter)
        manifest = layer.intake(IntakeRequest(
            "task.m75", "local:scan.pdf", "scan.pdf", _scanned_pdf(), IntakeMode.query_upload, Clearance.restricted,
        ))
        page = manifest.pages[0]
        assert page.extraction_method == "ocr_deterministic"
        assert "V-101" in page.text
        assert 0.90 < page.confidence < 0.95
        assert len(page.regions) == 3
        assert all(region.bounding_box is not None for region in page.regions)
        assert len(page.tables) == 1
        assert page.taint == Taint.untrusted
        assert manifest.extraction_settings["ocr_provider"] == "airbench.ocr.deterministic"
        assert manifest.extraction_settings["ocr_failed_pages"] == "0"
        assert [event.event_type for event in ledger.events if event.event_type.startswith("vision.")] == [
            "vision.requested", "vision.completed",
        ]

    def test_ocr_failure_is_reported_not_hidden(self, tmp_path) -> None:
        ledger = EventLedger()
        _seed_task(ledger, "task.m75.fail")

        def failing(request):
            raise RuntimeError("engine down")

        adapter = LocalVisionAdapter(
            adapter_id="airbench.ocr.failing", adapter_version="1.0",
            model_target_id="target.ocr.fixture", qualification_reference="qualification.ocr.fixture",
            extractor=ocr_provider_extractor(
                DeterministicOcrProvider({}), adapter_id="airbench.ocr.failing", adapter_version="1.0",
                model_target_id="target.ocr.fixture", qualification_reference="qualification.ocr.fixture",
            ),
            kind="ocr",
        )
        adapter._extractor = failing
        layer = FileIntakeLayer(ledger, renderer=_Renderer(), store=LocalIntakeStore(tmp_path / "intake"), vision_adapter=adapter)
        manifest = layer.intake(IntakeRequest(
            "task.m75.fail", "local:scan.pdf", "scan.pdf", _scanned_pdf(), IntakeMode.query_upload, Clearance.restricted,
        ))
        assert manifest.pages[0].text == ""
        assert manifest.pages[0].confidence == 0.0
        assert manifest.extraction_settings["ocr_failed_pages"] == "1"
