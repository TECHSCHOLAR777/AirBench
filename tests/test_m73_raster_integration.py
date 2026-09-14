from __future__ import annotations

import io
from hashlib import sha256

import pytest

from airbench.intake.layer import IntakeMode, IntakeRequest, PageRecord
from airbench.intake.raster_renderer import PdfRasterPageRenderer
from contracts import Clearance, Taint

pytest.importorskip("pypdfium2", reason="pypdfium2 is an optional OCR rasterisation engine")


def _scanned_pdf() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _request(content: bytes) -> IntakeRequest:
    return IntakeRequest("task.raster", "local:scan.pdf", "scan.pdf", content, IntakeMode.query_upload, Clearance.restricted)


def _textless_page(content: bytes) -> PageRecord:
    return PageRecord(
        page_id="page-1", page_number=1, source_region="page:1", content_hash=sha256(content).hexdigest(),
        media_type="application/pdf", text="", extraction_method="pdf_text", confidence=0.0,
        clearance=Clearance.restricted, taint=Taint.untrusted, evidence_ref="evidence-1",
    )


def test_raster_renderer_produces_png_for_a_textless_pdf_page() -> None:
    content = _scanned_pdf()
    renderer = PdfRasterPageRenderer(dpi=72)
    assert PdfRasterPageRenderer.available()
    rendered = renderer.render(_request(content), _textless_page(content))
    assert rendered is not None
    assert rendered.page_number == 1
    assert rendered.media_type == "image/png"
    assert rendered.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_raster_renderer_skips_pages_that_already_have_text() -> None:
    content = _scanned_pdf()
    renderer = PdfRasterPageRenderer(dpi=72)
    page = _textless_page(content)
    from dataclasses import replace

    assert renderer.render(_request(content), replace(page, text="digital text")) is None
