"""Provider-neutral OCR and vision page extraction.

This module is the engine seam behind ``LocalVisionAdapter``.  A provider
receives already-framed page bytes from the File Intake Layer and returns
typed, confidence-bearing lines with bounding boxes.  It never opens a source
path, parses a document container, or reaches the network.

The default providers are:

- ``DeterministicOcrProvider`` for offline fixtures and contract tests;
- ``TesseractOcrProvider`` wrapping the local ``pytesseract`` binary when the
  optional dependency is installed; and
- ``VllmVisionOcrProvider`` delegating to a qualified M5 backend adapter.

Real engines are optional imports.  Importing this module never imports a
heavy dependency or performs I/O.
"""

from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence

from contracts import BoundingBox, PageRegion, StructuredTable, stable_id


class OcrProviderError(RuntimeError):
    """A stable, non-content-bearing OCR provider failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class OcrPageInput:
    """One bounded page image handed to a provider, still untrusted data."""

    page_number: int
    content: bytes
    content_hash: str
    media_type: str
    dpi: int = 300

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise OcrProviderError("invalid_page", "OCR page number must be positive")
        if not self.content:
            raise OcrProviderError("empty_page", "OCR page content is empty")
        if not self.media_type or "/" not in self.media_type:
            raise OcrProviderError("invalid_media", "OCR page media type is invalid")
        if hashlib.sha256(self.content).hexdigest() != self.content_hash:
            raise OcrProviderError("content_hash_mismatch", "OCR page content hash does not match")
        if self.dpi < 72 or self.dpi > 1_200:
            raise OcrProviderError("invalid_dpi", "OCR dpi is outside the allowed range")


@dataclass(frozen=True, slots=True)
class OcrLine:
    """One recognized text line with its page-local bounding box."""

    text: str
    bounding_box: BoundingBox
    confidence: float
    page_number: int

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise OcrProviderError("empty_line", "OCR line text is empty")
        if not 0 <= self.confidence <= 1:
            raise OcrProviderError("invalid_confidence", "OCR line confidence must be between zero and one")
        if self.bounding_box.page_number != self.page_number:
            raise OcrProviderError("page_mismatch", "OCR line box page does not match its line page")


@dataclass(frozen=True, slots=True)
class OcrPageResult:
    """A typed page extraction; untrusted and confidence-bearing."""

    page_number: int
    lines: tuple[OcrLine, ...]
    provider_name: str
    provider_version: str
    confidence: float
    media_type: str
    tables: tuple[StructuredTable, ...] = ()

    def __post_init__(self) -> None:
        if self.page_number < 1 or not self.provider_name or not self.provider_version:
            raise OcrProviderError("invalid_result", "OCR page result identity is required")
        if not 0 <= self.confidence <= 1:
            raise OcrProviderError("invalid_confidence", "OCR page confidence must be between zero and one")
        if any(line.page_number != self.page_number for line in self.lines):
            raise OcrProviderError("page_mismatch", "OCR line does not belong to the result page")
        for table in self.tables:
            if table.page_number != self.page_number:
                raise OcrProviderError("page_mismatch", "OCR table does not belong to the result page")

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text.strip())

    def regions(self, *, source_ref: str = "") -> tuple[PageRegion, ...]:
        """Project lines into typed, bbox-bearing ``PageRegion`` values."""
        return tuple(
            PageRegion(
                region_id=stable_id("region", self.provider_name, self.page_number, index, line.text, line.bounding_box.to_dict()),
                page_number=self.page_number,
                text=line.text,
                bounding_box=line.bounding_box,
                confidence=line.confidence,
                extraction_method=f"ocr_{self.provider_name}",
            )
            for index, line in enumerate(self.lines)
        )


class OcrProvider(Protocol):
    """Extract one page image into typed lines without touching the network."""

    name: str
    version: str

    def extract(self, page: OcrPageInput) -> OcrPageResult: ...


def _weighted_confidence(lines: Sequence[OcrLine]) -> float:
    if not lines:
        return 0.0
    weights = [max(1, len(line.text)) for line in lines]
    total = sum(weights)
    return sum(line.confidence * weight for line, weight in zip(lines, weights)) / total


class DeterministicOcrProvider:
    """Offline fixture provider keyed by page content hash.

    ``lines_by_hash`` maps a page's sha256 to a sequence of
    ``(text, x, y, width, height, confidence)`` tuples.  It exists so contract
    tests and demos can exercise the full OCR seam without a real engine and
    without claiming production OCR quality.
    """

    def __init__(
        self,
        lines_by_hash: Mapping[str, Sequence[tuple[str, int, int, int, int, float]]] | None = None,
        *,
        name: str = "deterministic",
        version: str = "1.0",
    ) -> None:
        if not name or not version:
            raise OcrProviderError("invalid_provider", "deterministic OCR provider identity is required")
        self.name = name
        self.version = version
        self._lines_by_hash = {key: tuple(value) for key, value in (lines_by_hash or {}).items()}

    def extract(self, page: OcrPageInput) -> OcrPageResult:
        raw = self._lines_by_hash.get(page.content_hash, ())
        lines = tuple(
            OcrLine(
                text=text,
                bounding_box=BoundingBox(x=x, y=y, width=width, height=height, page_number=page.page_number),
                confidence=confidence,
                page_number=page.page_number,
            )
            for text, x, y, width, height, confidence in raw
            if text.strip()
        )
        return OcrPageResult(
            page_number=page.page_number,
            lines=lines,
            provider_name=self.name,
            provider_version=self.version,
            confidence=_weighted_confidence(lines),
            media_type=page.media_type,
        )


class TesseractOcrProvider:
    """Wrap a local ``pytesseract`` install; never fetches from a network.

    ``pytesseract`` is an optional dependency.  When it or the ``tesseract``
    binary is missing the provider raises a typed ``OcrProviderError`` instead
    of silently returning empty text, so callers can report honest status.
    """

    def __init__(self, *, name: str = "tesseract", version: str = "1.0", lang: str = "eng") -> None:
        if not name or not version or not lang:
            raise OcrProviderError("invalid_provider", "tesseract provider identity is required")
        self.name = name
        self.version = version
        self.lang = lang

    def extract(self, page: OcrPageInput) -> OcrPageResult:
        pytesseract, Image = self._dependencies()
        try:
            with Image.open(io.BytesIO(page.content)) as image:
                image.load()
                data = pytesseract.image_to_data(
                    image.convert("RGB"),
                    lang=self.lang,
                    config=f"--dpi {page.dpi}",
                    output_type=pytesseract.Output.DICT,
                )
        except OcrProviderError:
            raise
        except Exception as exc:
            raise OcrProviderError("ocr_failed", "tesseract could not process the page") from exc
        lines = _group_tesseract_lines(data, page.page_number)
        return OcrPageResult(
            page_number=page.page_number,
            lines=lines,
            provider_name=self.name,
            provider_version=self.version,
            confidence=_weighted_confidence(lines),
            media_type=page.media_type,
        )

    @staticmethod
    def _dependencies():
        try:
            import pytesseract  # type: ignore[import-not-found]
            from PIL import Image  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise OcrProviderError(
                "provider_unavailable",
                "pytesseract and Pillow are required for the tesseract OCR provider",
            ) from exc
        command = os.environ.get("TESSERACT_CMD", "").strip()
        if command:
            pytesseract.pytesseract.tesseract_cmd = command
        return pytesseract, Image


def _group_tesseract_lines(data: Mapping[str, Sequence[object]], page_number: int) -> tuple[OcrLine, ...]:
    groups: dict[tuple[int, int, int], list[tuple[str, int, int, int, int, float]]] = {}
    texts = data.get("text", [])
    for index, raw_text in enumerate(texts):
        text = str(raw_text).strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index])  # type: ignore[index]
            left = int(data["left"][index])  # type: ignore[index]
            top = int(data["top"][index])  # type: ignore[index]
            width = int(data["width"][index])  # type: ignore[index]
            height = int(data["height"][index])  # type: ignore[index]
            key = (int(data["block_num"][index]), int(data["par_num"][index]), int(data["line_num"][index]))  # type: ignore[index]
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if confidence < 0:  # tesseract marks non-word entries with -1
            continue
        groups.setdefault(key, []).append((text, left, top, width, height, max(0.0, min(1.0, confidence / 100.0))))

    lines: list[OcrLine] = []
    for key in sorted(groups):
        words = groups[key]
        left = min(word[1] for word in words)
        top = min(word[2] for word in words)
        right = max(word[1] + word[3] for word in words)
        bottom = max(word[2] + word[4] for word in words)
        text = " ".join(word[0] for word in words)
        confidence = sum(word[5] for word in words) / len(words)
        lines.append(OcrLine(
            text=text,
            bounding_box=BoundingBox(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top), page_number=page_number),
            confidence=confidence,
            page_number=page_number,
        ))
    return tuple(lines)


class VllmVisionOcrProvider:
    """Delegate page extraction to a qualified M5 multimodal backend.

    The request builder owns the model-specific prompt and multimodal
    ``BackendRequest``; this provider only enforces the typed result contract.
    Without a ``response_parser`` the whole response is treated as one
    full-page line at the backend's reported confidence.
    """

    def __init__(
        self,
        backend: object,
        request_builder: Callable[[OcrPageInput], object],
        *,
        name: str = "vllm_vision",
        version: str = "1.0",
        response_parser: Callable[[str, int, float], Sequence[OcrLine]] | None = None,
    ) -> None:
        if not name or not version or not callable(request_builder):
            raise OcrProviderError("invalid_provider", "vllm vision provider requires a request builder")
        self.name = name
        self.version = version
        self._backend = backend
        self._request_builder = request_builder
        self._response_parser = response_parser

    def extract(self, page: OcrPageInput) -> OcrPageResult:
        from contracts.model.backend import BackendRequest  # local import keeps the seam light

        request = self._request_builder(page)
        if not isinstance(request, BackendRequest):
            raise OcrProviderError("invalid_backend_request", "vision request builder returned an invalid backend request")
        response = self._backend.complete(request)
        confidence = float(getattr(getattr(response, "provenance", None), "confidence", 0.0) or 0.0)
        output = getattr(response, "output", "")
        text = output if isinstance(output, str) else str(output)
        confidence = max(0.0, min(1.0, confidence))
        if self._response_parser is not None:
            lines = tuple(self._response_parser(text, page.page_number, confidence))
        else:
            lines = (
                OcrLine(
                    text=text.strip(),
                    bounding_box=BoundingBox(x=0, y=0, width=1, height=1, page_number=page.page_number),
                    confidence=confidence,
                    page_number=page.page_number,
                ),
            ) if text.strip() else ()
        return OcrPageResult(
            page_number=page.page_number,
            lines=lines,
            provider_name=self.name,
            provider_version=self.version,
            confidence=_weighted_confidence(lines),
            media_type=page.media_type,
        )


def build_ocr_provider_from_env(
    env: Mapping[str, str] | None = None,
    *,
    backend: object | None = None,
    request_builder: Callable[[OcrPageInput], object] | None = None,
    response_parser: Callable[[str, int, float], Sequence[OcrLine]] | None = None,
) -> OcrProvider | None:
    """Select the configured OCR provider, or ``None`` when disabled.

    ``OCR_PROVIDER`` accepts ``none``, ``tesseract``, or ``vllm_vision``.  The
    vLLM lane requires an injected qualified backend, because the core must not
    construct a model endpoint itself.
    """

    values = os.environ if env is None else env
    selected = values.get("OCR_PROVIDER", "").strip().lower()
    if not selected or selected in {"none", "disabled", "off"}:
        return None
    if selected == "tesseract":
        return TesseractOcrProvider(lang=values.get("OCR_LANG", "eng").strip() or "eng")
    if selected in {"vllm_vision", "vllm"}:
        if backend is None or request_builder is None:
            raise OcrProviderError("provider_unavailable", "vllm_vision OCR requires a qualified backend and request builder")
        return VllmVisionOcrProvider(backend, request_builder, response_parser=response_parser)
    raise OcrProviderError("unknown_provider", "OCR_PROVIDER must be none, tesseract, or vllm_vision")


__all__ = [
    "DeterministicOcrProvider",
    "OcrLine",
    "OcrPageInput",
    "OcrPageResult",
    "OcrProvider",
    "OcrProviderError",
    "TesseractOcrProvider",
    "VllmVisionOcrProvider",
    "build_ocr_provider_from_env",
]
