"""Node-owned transport projections for the governed File Intake Layer.

The gateway is deliberately narrower than a document service. It accepts an
already framed upload, hands the bytes to ``FileIntakeLayer.query_upload``,
and exposes only typed, clearance-filtered projections of the committed
manifest. It never treats document content as instructions and never creates
an output deliverable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol
from contracts import Clearance, EventLedger, TaskEnvelope, build_event, idempotency_key, stable_id

from ..intake.layer import FileIntakeLayer, IntakeError, IntakeManifest, LocalIntakeStore, PageRecord


MAX_PREVIEW_TEXT_BYTES = 10 * 1024 * 1024
MAX_PREVIEW_BLOCKS = 1_024
MAX_BLOCK_TEXT_BYTES = 256 * 1024


class NodeIntakeError(RuntimeError):
    """Bounded error suitable for conversion to a Node API error."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class NodeArtifactDownload:
    artifact_id: str
    content: bytes
    media_type: str
    content_hash: str
    ledger_event_ref: str
    file_name: str


class NodeIntakeGateway(Protocol):
    def query_upload(self, *, subject: str, task_id: str, file_name: str, content: bytes) -> dict[str, Any]: ...

    def preview(self, *, preview_ref: str) -> dict[str, Any]: ...

    def artifact_preview(self, *, artifact_id: str) -> dict[str, Any]: ...

    def download(self, *, artifact_id: str) -> NodeArtifactDownload: ...


def _rank(clearance: Clearance) -> int:
    return {Clearance.public: 0, Clearance.internal: 1, Clearance.restricted: 2, Clearance.secret: 3}[clearance]


def _bounded(value: str, maximum: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum:
        return value
    return encoded[:maximum].decode("utf-8", errors="ignore")


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


class LocalNodeIntakeGateway:
    """Expose local intake records through the Node boundary.

    This implementation is intentionally useful for the local desktop path:
    it is a real File Intake Layer and transactional store, not an HTTP test
    fixture. OCR and vision remain unavailable unless qualified adapters are
    supplied elsewhere; the gateway never upgrades an image or scan to
    ``completed`` merely to make the UI proceed.
    """

    def __init__(self, *, layer: FileIntakeLayer, store: LocalIntakeStore, ledger: EventLedger, clearance_context: Clearance) -> None:
        self._layer = layer
        self._store = store
        self._ledger = ledger
        self._clearance_context = clearance_context

    def query_upload(self, *, subject: str, task_id: str, file_name: str, content: bytes) -> dict[str, Any]:
        task = self._task_for_upload(subject, task_id)
        self._check_clearance(task.clearance)
        try:
            manifest = self._layer.query_upload(
                task_id=task.task_id,
                # A retry of the same task-bound upload must resolve to the
                # same committed intake record.  This keeps retries from
                # creating duplicate evidence events or ambiguous previews.
                source_ref=f"query-upload:{task.task_id}:{file_name}:{_sha256(content)}",
                file_name=file_name,
                content=content,
                clearance=task.clearance,
            )
        except IntakeError as exc:
            raise _map_intake_error(exc) from exc
        return self._manifest_wire(manifest)

    def _task_for_upload(self, subject: str, task_id: str) -> TaskEnvelope:
        event = next(
            (event for event in self._ledger.events if event.task_id == task_id and event.event_type == "task.created"),
            None,
        )
        if event is None:
            raise NodeIntakeError(409, "task_required", "Create the task through the Node before sending query-upload material.")
        try:
            task = TaskEnvelope.from_dict(event.payload["task"])
        except (KeyError, TypeError, ValueError) as exc:
            raise NodeIntakeError(503, "task_contract_corrupt", "The task contract could not be verified for intake.") from exc
        if task.principal_id != subject:
            raise NodeIntakeError(403, "principal_mismatch", "The upload principal does not match the task principal.")
        return task

    def preview(self, *, preview_ref: str) -> dict[str, Any]:
        manifest = self._visible_manifest(preview_ref)
        page = manifest.pages[0]
        event_ref = self._record_access(manifest, "source_preview", preview_ref, page)
        return {
            "preview_ref": preview_ref,
            "preview_kind": _preview_kind(manifest.media_type),
            "text": _bounded(page.text, MAX_PREVIEW_TEXT_BYTES),
            "source_hash": _sha256_from_hex(manifest.source_hash),
            "source_region": page.source_region,
            "confidence": page.confidence,
            "clearance": manifest.clearance.value,
            "taint": manifest.taint.value,
            "ledger_event_ref": event_ref,
        }

    def artifact_preview(self, *, artifact_id: str) -> dict[str, Any]:
        manifest = self._visible_manifest(artifact_id)
        blocks = [
            {"kind": "page", "text": _bounded(page.text, MAX_BLOCK_TEXT_BYTES)}
            for page in manifest.pages
            if page.text
        ][:MAX_PREVIEW_BLOCKS]
        if not blocks:
            blocks = [{"kind": "status", "text": "No text was extracted by the configured File Intake parser."}]
        event_ref = self._record_access(manifest, "source_artifact_preview", artifact_id, manifest.pages[0])
        return {
            "artifact_id": artifact_id,
            "preview_kind": "pdf" if manifest.media_type == "application/pdf" else "text",
            "title": _bounded(manifest.file_name, 255),
            "blocks": blocks,
            "clearance": manifest.clearance.value,
            "taint": manifest.taint.value,
            "ledger_event_ref": event_ref,
        }

    def download(self, *, artifact_id: str) -> NodeArtifactDownload:
        manifest = self._visible_manifest(artifact_id)
        try:
            content = self._store.read_source(manifest.intake_id)
        except IntakeError as exc:
            raise _map_intake_error(exc) from exc
        page = manifest.pages[0]
        event_ref = self._record_access(manifest, "source_artifact_download", artifact_id, page)
        return NodeArtifactDownload(
            artifact_id=artifact_id,
            content=content,
            media_type=manifest.media_type,
            content_hash=_sha256(content),
            ledger_event_ref=event_ref,
            file_name=manifest.file_name,
        )

    def _visible_manifest(self, reference: str) -> IntakeManifest:
        try:
            manifest = self._store.load(reference)
        except IntakeError as exc:
            raise _map_intake_error(exc) from exc
        if manifest is None:
            raise NodeIntakeError(404, "intake_not_found", "The requested intake record does not exist.")
        if _rank(manifest.clearance) > _rank(self._clearance_context):
            raise NodeIntakeError(404, "intake_not_found", "The requested intake record does not exist.")
        return manifest

    def _check_clearance(self, clearance: Clearance) -> None:
        if _rank(clearance) > _rank(self._clearance_context):
            raise NodeIntakeError(403, "clearance_exceeded", "The requested intake clearance exceeds this Node context.")

    def _manifest_wire(self, manifest: IntakeManifest) -> dict[str, Any]:
        # The wire artifact is the committed source artifact. It is not an
        # output deliverable and is never presented as one by this gateway.
        statuses = _processing_status(manifest)
        return {
            "intake_id": manifest.intake_id,
            "file_name": manifest.file_name,
            "byte_size": manifest.byte_size,
            "source_hash": _sha256_from_hex(manifest.source_hash),
            "revision_id": manifest.revision_id,
            "media_type": manifest.media_type,
            "page_count": manifest.page_count,
            "ocr_status": statuses[0],
            "vision_status": statuses[1],
            "clearance": manifest.clearance.value,
            "taint": manifest.taint.value,
            "preview_ref": manifest.intake_id,
            "artifact_ref": manifest.intake_id,
            "ledger_event_ref": manifest.ledger_event_ref,
        }

    def _record_access(self, manifest: IntakeManifest, operation: str, reference: str, page: PageRecord) -> str:
        key = idempotency_key("node-intake-access", operation, manifest.intake_id)
        existing = next((event for event in self._ledger.events if event.idempotency_key == key), None)
        if existing is not None:
            return existing.event_id
        event = build_event(
            event_type="artifact.checked",
            task_id=manifest.task_id,
            actor_id="node.intake",
            actor_type="service",
            payload_contract="NodeIntakeAccess",
            payload_version="1.0",
            payload={
                "operation": operation,
                "reference": reference,
                "intake_id": manifest.intake_id,
                "source_hash": manifest.source_hash,
                "source_region": page.source_region,
                "provenance": {
                    "source_ref": manifest.source_ref,
                    "confidence": page.confidence,
                    "clearance": manifest.clearance.value,
                    "taint": manifest.taint.value,
                    "extraction_method": page.extraction_method,
                    "ingested_at": manifest.ingested_at,
                    "location": {"page": page.page_number, "region": page.source_region},
                },
            },
            clearance=manifest.clearance,
            idempotency=key,
            sequence=len(self._ledger.events),
            previous_event_hash=self._ledger.head_hash,
        )
        try:
            self._ledger.append(event)
        except Exception as exc:
            raise NodeIntakeError(503, "intake_access_not_committed", "The intake access record could not be committed.") from exc
        return event.event_id


def _sha256_from_hex(value: str) -> str:
    return value if value.startswith("sha256:") else f"sha256:{value}"


def _preview_kind(media_type: str) -> str:
    if media_type == "application/pdf":
        return "pdf_page"
    if media_type.startswith("image/"):
        return "image"
    if media_type == "text/csv":
        return "table"
    return "text"


def _processing_status(manifest: IntakeManifest) -> tuple[str, str]:
    if all(page.text and page.confidence > 0 for page in manifest.pages):
        return "not_applicable", "not_applicable"
    return "unavailable", "unavailable"


def _map_intake_error(error: IntakeError) -> NodeIntakeError:
    if error.code in {"file_too_large", "pdf_too_many_pages", "pdf_text_too_large", "pdf_page_text_too_large"}:
        status = 413
    elif error.code in {"unsupported_media"}:
        status = 415
    elif error.code in {"storage_not_found"}:
        status = 404
    elif error.code in {"ledger_write_failed", "storage_commit_failed", "storage_prepare_failed", "storage_corrupt", "storage_ledger_mismatch"}:
        status = 503
    else:
        status = 422
    return NodeIntakeError(status, f"intake_{error.code}", str(error))


__all__ = ["LocalNodeIntakeGateway", "NodeArtifactDownload", "NodeIntakeError", "NodeIntakeGateway"]
