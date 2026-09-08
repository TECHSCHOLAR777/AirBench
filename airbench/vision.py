"""Typed local OCR and vision adapters for intake-produced pages.

Adapters receive page bytes from the File Intake Layer. They never open source
paths or parse document containers, so bulk ingestion and query uploads keep
the same boundary and provenance rules.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol

from contracts import Clearance, EventLedger, Taint, build_event, stable_id
from contracts.backend import BackendAdapter, BackendRequest, CancellationToken


class VisionError(RuntimeError):
    """A stable, non-content-bearing OCR or vision failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class VisionRequest:
    task_id: str
    intake_id: str
    revision_id: str
    page_id: str
    page_number: int
    source_ref: str
    media_type: str
    content: bytes
    content_hash: str
    clearance: Clearance
    taint: Taint

    def __post_init__(self) -> None:
        if not self.task_id or not self.intake_id or not self.page_id or not self.source_ref:
            raise VisionError("invalid_identity", "vision identity fields are required")
        if self.page_number < 1 or not self.content:
            raise VisionError("invalid_page", "vision page number and content are required")
        if hashlib.sha256(self.content).hexdigest() != self.content_hash:
            raise VisionError("content_hash_mismatch", "vision page content hash does not match")
        if self.taint == Taint.clean:
            raise VisionError("clean_input", "intake page content must remain untrusted")


@dataclass(frozen=True, slots=True)
class VisionRegion:
    region_id: str
    text: str
    confidence: float
    source_span: str

    def __post_init__(self) -> None:
        if not self.region_id or not self.source_span or not 0 <= self.confidence <= 1:
            raise VisionError("invalid_region", "vision region identity and confidence are required")


@dataclass(frozen=True, slots=True)
class VisionResult:
    extraction_id: str
    task_id: str
    intake_id: str
    revision_id: str
    page_id: str
    source_ref: str
    text: str
    confidence: float
    extraction_method: str
    adapter_id: str
    adapter_version: str
    model_target_id: str
    qualification_reference: str
    clearance: Clearance
    taint: Taint
    content_hash: str
    regions: tuple[VisionRegion, ...] = ()
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))

    def __post_init__(self) -> None:
        if not self.extraction_id or not self.extraction_method or not self.qualification_reference:
            raise VisionError("invalid_result", "vision result identity and qualification are required")
        if not 0 <= self.confidence <= 1:
            raise VisionError("invalid_confidence", "vision confidence must be between zero and one")
        if self.taint == Taint.clean:
            raise VisionError("clean_result", "OCR and vision output remains untrusted")


class VisionExtractor(Protocol):
    def __call__(self, request: VisionRequest) -> VisionResult: ...


class LocalVisionAdapter:
    """Run one qualified local OCR or vision callable behind a typed seam."""

    def __init__(
        self,
        *,
        adapter_id: str,
        adapter_version: str,
        model_target_id: str,
        qualification_reference: str,
        extractor: VisionExtractor,
        ledger: EventLedger | None = None,
        timeout_s: float = 30.0,
        max_input_bytes: int = 25_000_000,
        kind: str = "vision",
    ) -> None:
        if not adapter_id or not adapter_version or not model_target_id or not qualification_reference:
            raise VisionError("invalid_adapter", "qualified adapter identity is required")
        if kind not in {"ocr", "vision"}:
            raise VisionError("invalid_adapter_kind", "adapter kind must be ocr or vision")
        if timeout_s <= 0 or max_input_bytes <= 0:
            raise VisionError("invalid_limits", "vision timeout and input limit must be positive")
        self.adapter_id = adapter_id
        self.adapter_version = adapter_version
        self.model_target_id = model_target_id
        self.qualification_reference = qualification_reference
        self._extractor = extractor
        self._ledger = ledger
        self._timeout_s = timeout_s
        self._max_input_bytes = max_input_bytes
        self.kind = kind

    def extract(self, request: VisionRequest, cancellation: CancellationToken | None = None) -> VisionResult:
        if cancellation and cancellation.cancelled:
            raise VisionError("cancelled", "vision extraction was cancelled")
        if len(request.content) > self._max_input_bytes:
            raise VisionError("resource_exhausted", "vision page exceeds the configured input limit")
        self._event("vision.requested", request, {"adapter_id": self.adapter_id, "kind": self.kind})
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._extractor, request)
        try:
            result = future.result(timeout=self._timeout_s)
            if cancellation and cancellation.cancelled:
                raise VisionError("cancelled", "vision extraction was cancelled")
            self._validate_result(request, result)
            self._event("vision.completed", request, {
                "extraction_id": result.extraction_id,
                "content_hash": result.content_hash,
            })
            return result
        except FutureTimeout as exc:
            future.cancel()
            self._event("vision.failed", request, {"code": "timeout"})
            raise VisionError("timeout", "vision extraction timed out") from exc
        except VisionError as exc:
            self._event("vision.failed", request, {"code": exc.code})
            raise
        except Exception as exc:
            self._event("vision.failed", request, {"code": "adapter_failed"})
            raise VisionError("adapter_failed", "qualified vision adapter failed") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _validate_result(self, request: VisionRequest, result: VisionResult) -> None:
        if result.task_id != request.task_id or result.intake_id != request.intake_id:
            raise VisionError("identity_mismatch", "vision result does not belong to the request")
        if result.revision_id != request.revision_id or result.page_id != request.page_id:
            raise VisionError("page_mismatch", "vision result page identity does not match")
        if result.source_ref != request.source_ref or result.content_hash != request.content_hash:
            raise VisionError("provenance_mismatch", "vision result provenance does not match")
        if result.adapter_id != self.adapter_id or result.adapter_version != self.adapter_version:
            raise VisionError("adapter_mismatch", "vision result adapter identity does not match")
        if result.model_target_id != self.model_target_id or result.qualification_reference != self.qualification_reference:
            raise VisionError("qualification_mismatch", "vision result qualification does not match")
        if result.clearance != request.clearance or result.taint != request.taint:
            raise VisionError("provenance_mismatch", "vision result clearance or taint changed")

    def _event(self, event_type: str, request: VisionRequest, payload: dict[str, str]) -> None:
        if self._ledger is None:
            return
        sequence = len(self._ledger.events)
        self._ledger.append(build_event(
            event_type=event_type,
            task_id=request.task_id,
            actor_id=self.adapter_id,
            actor_type="vision_adapter",
            payload_contract="VisionOperation",
            payload_version="1.0",
            payload={
                **payload,
                "task_id": request.task_id,
                "intake_id": request.intake_id,
                "page_id": request.page_id,
                "source_ref": request.source_ref,
                "content_hash": request.content_hash,
                "clearance": request.clearance.value,
                "taint": request.taint.value,
                "qualification_reference": self.qualification_reference,
            },
            clearance=request.clearance,
            idempotency=stable_id("vision", event_type, request.task_id, request.page_id, sequence),
            sequence=sequence,
            previous_event_hash=self._ledger.head_hash,
            occurred_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        ))


def static_text_extractor(
    text_by_page: dict[str, str],
    *,
    adapter_id: str,
    adapter_version: str,
    model_target_id: str,
    qualification_reference: str,
) -> VisionExtractor:
    """Create a deterministic fixture extractor without pretending to be OCR."""

    def extract(request: VisionRequest) -> VisionResult:
        text = text_by_page.get(request.page_id, "")
        return VisionResult(
            extraction_id=stable_id("extraction", request.intake_id, request.page_id, request.content_hash),
            task_id=request.task_id,
            intake_id=request.intake_id,
            revision_id=request.revision_id,
            page_id=request.page_id,
            source_ref=request.source_ref,
            text=text,
            confidence=0.95 if text else 0.0,
            extraction_method="fixture",
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            model_target_id=model_target_id,
            qualification_reference=qualification_reference,
            clearance=request.clearance,
            taint=request.taint,
            content_hash=request.content_hash,
        )

    return extract


def backend_text_extractor(
    backend: BackendAdapter,
    request_builder: Callable[[VisionRequest], BackendRequest],
    *,
    adapter_id: str,
    adapter_version: str,
    model_target_id: str,
    qualification_reference: str,
) -> VisionExtractor:
    """Bridge a qualified M5 backend to the M7 page-extraction contract.

    The request builder owns the model-specific prompt and multimodal
    `BackendRequest`; the M7 core only validates the returned provenance.
    """

    def extract(request: VisionRequest) -> VisionResult:
        backend_request = request_builder(request)
        if not isinstance(backend_request, BackendRequest):
            raise VisionError("invalid_backend_request", "vision request builder returned an invalid backend request")
        response = backend.complete(backend_request)
        if isinstance(response.output, str):
            text = response.output
        else:
            text = json.dumps(response.output, sort_keys=True, separators=(",", ":"), default=str)
        return VisionResult(
            extraction_id=stable_id("extraction", request.intake_id, request.page_id, response.digest()),
            task_id=request.task_id,
            intake_id=request.intake_id,
            revision_id=request.revision_id,
            page_id=request.page_id,
            source_ref=request.source_ref,
            text=text,
            confidence=response.provenance.confidence,
            extraction_method=f"{adapter_id}.backend",
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            model_target_id=model_target_id,
            qualification_reference=qualification_reference,
            clearance=request.clearance,
            taint=request.taint,
            content_hash=request.content_hash,
        )

    return extract


__all__ = [
    "LocalVisionAdapter", "VisionError", "VisionExtractor", "VisionRegion", "VisionRequest", "VisionResult",
    "backend_text_extractor", "static_text_extractor",
]
