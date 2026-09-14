"""Optional PDF page rasterisation for OCR.

A scanned PDF has no extractable text, so OCR needs rendered page images.  The
rasteriser is an optional engine: ``pypdfium2`` is imported lazily and never
becomes a hard dependency.  When it is missing the renderer is simply not
constructed, and scanned pages remain honestly marked as unread instead of
being silently dropped.

Rendered pages are still untrusted document data.  They are produced inside the
File Intake Layer, stored in the intake store, and never opened from a host
path by a worker.
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

from .layer import IntakeError, IntakeRequest, PageRecord, RenderedPage

_PDF_MAGIC = b"%PDF-"


class PdfRasterPageRenderer:
    """Render textless PDF pages to PNG bytes with ``pypdfium2``."""

    name = "pypdfium2-pdf-raster"
    version = "1.0"

    def __init__(self, *, dpi: int = 200, max_dimension: int = 32_768) -> None:
        if dpi < 72 or dpi > 600 or max_dimension < 512:
            raise IntakeError("invalid_renderer", "PDF rasteriser configuration is invalid")
        self._dpi = dpi
        self._max_dimension = max_dimension

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("pypdfium2") is not None

    def render(self, request: IntakeRequest, page: PageRecord) -> RenderedPage | None:
        if page.text.strip():
            return None
        if not (request.content.startswith(_PDF_MAGIC) or Path(request.file_name).suffix.lower() == ".pdf"):
            return None
        try:
            import pypdfium2  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise IntakeError("renderer_unavailable", "pypdfium2 is required to rasterise PDF pages") from exc
        try:
            document = pypdfium2.PdfDocument(io.BytesIO(request.content))
        except Exception as exc:
            raise IntakeError("render_failed", "the PDF could not be opened for rasterisation") from exc
        try:
            pdf_page = document[page.page_number - 1]
            bitmap = pdf_page.render(scale=self._dpi / 72)
            image = bitmap.to_pil()
            width, height = image.size
            if width < 1 or height < 1 or width > self._max_dimension or height > self._max_dimension:
                raise IntakeError("rendered_page_too_large", "a rendered PDF page exceeds the dimension limit")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
        except IntakeError:
            raise
        except Exception as exc:
            raise IntakeError("render_failed", "the PDF page could not be rasterised") from exc
        finally:
            document.close()
        return RenderedPage(page.page_number, buffer.getvalue(), "image/png")


__all__ = ["PdfRasterPageRenderer"]
