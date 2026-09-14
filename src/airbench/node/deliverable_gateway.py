"""Node boundary for generated deliverables.

Source-intake artifacts and generated deliverables have different meanings.
This gateway exposes only a committed Deliverable Engine record as an output
artifact, and it projects stored preview blocks instead of parsing DOCX bytes
in a second place.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Protocol

from contracts import (
    Clearance,
    ContractValidationError,
    EventLedger,
    NodeArtifactReview,
    Taint,
    build_event,
    idempotency_key,
)

from .intake_gateway import NodeArtifactDownload, NodeIntakeError


_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CLEARANCE_RANK = {
    Clearance.public: 0,
    Clearance.internal: 1,
    Clearance.restricted: 2,
    Clearance.secret: 3,
}
_MAX_BLOCKS = 1_024
_MAX_BLOCK_TEXT = 256 * 1024


class NodeDeliverableGateway(Protocol):
    def artifact_review(self, *, task_id: str) -> dict[str, Any]: ...

    def artifact_preview(self, *, artifact_id: str) -> dict[str, Any]: ...

    def download(self, *, artifact_id: str) -> NodeArtifactDownload: ...


class LocalDeliverableGateway:
    """Project locally committed deliverables through the authenticated Node."""

    def __init__(
        self,
        *,
        ledger: EventLedger,
        artifact_store: Any,
        node_identity: str,
        protocol_version: str,
        clearance_context: Clearance,
    ) -> None:
        self._ledger = ledger
        self._artifact_store = artifact_store
        self._node_identity = node_identity
        self._protocol_version = protocol_version
        self._clearance_context = clearance_context

    def artifact_review(self, *, task_id: str) -> dict[str, Any]:
        self._require_reference(task_id, "task")
        self._visible_task(task_id)
        event = next(
            (
                event
                for event in reversed(self._ledger.events)
                if event.task_id == task_id and self._is_deliverable_check(event)
            ),
            None,
        )
        if event is None:
            raise NodeIntakeError(404, "deliverable_not_found", "The task has no committed output deliverable.")
        review = self._review_wire(event)
        # The committed human sign-off is the authoritative approval state; the
        # deliverable event itself is immutable and stays "pending".
        signoff = next(
            (
                item for item in reversed(self._ledger.events)
                if item.task_id == task_id and item.event_type == "human.signoff"
                and item.payload.get("artifact_id") == review.get("artifactId")
            ),
            None,
        )
        if signoff is not None and signoff.payload.get("decision") == "approved":
            review["approvalState"] = "approved"
        return review

    def artifact_preview(self, *, artifact_id: str) -> dict[str, Any]:
        event = self._visible_record(artifact_id)
        payload = event.payload
        blocks = self._preview_blocks(payload.get("preview_blocks"))
        access_ref = self._record_access(event, "artifact.previewed")
        return {
            "artifact_id": artifact_id,
            "preview_kind": "structured_document",
            "title": self._required_text(payload.get("title"), "artifact title", 255),
            "blocks": blocks,
            "clearance": event.clearance.value,
            "taint": self._taint(payload),
            "ledger_event_ref": access_ref,
        }

    def download(self, *, artifact_id: str) -> NodeArtifactDownload:
        event = self._visible_record(artifact_id)
        payload = event.payload
        file_format = self._required_text(payload.get("format"), "artifact format", 16)
        if file_format not in {"docx", "xlsx", "pptx"}:
            raise NodeIntakeError(503, "deliverable_format_unsupported", "The local output format is not supported by this Node.")
        try:
            content = self._artifact_store.read(artifact_id, file_format)
        except Exception as exc:
            raise NodeIntakeError(503, "deliverable_unavailable", "The committed output bytes are not available locally.") from exc
        content_hash = hashlib.sha256(content).hexdigest()
        expected_hash = self._required_hash(payload.get("content_hash"))
        expected_size = payload.get("byte_size")
        if content_hash != expected_hash or type(expected_size) is not int or len(content) != expected_size:
            raise NodeIntakeError(503, "deliverable_integrity_failed", "The local output bytes do not match the committed artifact.")
        access_ref = self._record_access(event, "artifact.downloaded")
        return NodeArtifactDownload(
            artifact_id=artifact_id,
            content=content,
            media_type=self._required_text(payload.get("media_type"), "artifact media type", 256),
            content_hash=f"sha256:{content_hash}",
            ledger_event_ref=access_ref,
            file_name=f"{artifact_id}.{file_format}",
        )

    def _visible_record(self, artifact_id: str):
        self._require_reference(artifact_id, "artifact")
        event = next(
            (
                event
                for event in reversed(self._ledger.events)
                if event.payload.get("artifact_id") == artifact_id and self._is_deliverable_check(event)
            ),
            None,
        )
        if event is None or not self._can_read(event.clearance):
            raise NodeIntakeError(404, "deliverable_not_found", "The requested output deliverable does not exist.")
        if self._taint(event.payload) == Taint.contaminated.value:
            raise NodeIntakeError(404, "deliverable_not_found", "The requested output deliverable does not exist.")
        self._visible_task(event.task_id)
        return event

    def _review_wire(self, event) -> dict[str, Any]:
        payload = event.payload
        provenance = payload.get("provenance")
        if not isinstance(provenance, dict):
            raise NodeIntakeError(503, "deliverable_contract_corrupt", "The output provenance record is incomplete.")
        checks = payload.get("checks")
        if not isinstance(checks, dict):
            raise NodeIntakeError(503, "deliverable_contract_corrupt", "The output verification record is incomplete.")
        verification_status = self._required_text(payload.get("verification_status"), "verification status", 64)
        structural_check = self._required_text(checks.get("structural"), "structural check", 64)
        visual_check = self._required_text(checks.get("visual"), "visual check", 64)
        status = self._required_text(payload.get("status"), "artifact status", 64)
        reasons = payload.get("approval_blocking_reasons", [])
        if not isinstance(reasons, list) or any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
            raise NodeIntakeError(503, "deliverable_contract_corrupt", "The output approval blockers are invalid.")
        try:
            review = NodeArtifactReview.from_dict(
                {
                    "task_id": event.task_id,
                    "artifact_id": self._required_reference(payload.get("artifact_id"), "artifact"),
                    "node_identity": self._node_identity,
                    "protocol_version": self._protocol_version,
                    "clearance_context": self._clearance_context,
                    "title": self._required_text(payload.get("title"), "artifact title", 255),
                    "media_type": self._required_text(payload.get("media_type"), "artifact media type", 256),
                    "file_format": self._required_text(payload.get("format"), "artifact format", 16),
                    "template_id": self._required_text(payload.get("template_id"), "template identity", 128),
                    "template_version": self._required_text(payload.get("template_version"), "template version", 64),
                    "content_hash": self._required_hash(payload.get("content_hash")),
                    "byte_size": payload.get("byte_size"),
                    "status": status,
                    "verification_status": verification_status,
                    "structural_check": structural_check,
                    "visual_check": visual_check,
                    "approval_state": self._required_text(payload.get("approval_state", "pending"), "approval state", 64),
                    "approval_blocking_reasons": tuple(reasons),
                    "source_refs": self._references(payload.get("source_refs", provenance.get("source_refs")), "source"),
                    "evidence_refs": self._references(payload.get("evidence_refs", provenance.get("evidence_refs")), "evidence"),
                    "verification_refs": self._references(payload.get("verification_refs", provenance.get("verification_refs")), "verification"),
                    "deterministic_value_refs": self._references(payload.get("deterministic_value_refs", provenance.get("deterministic_value_refs", [])), "deterministic value"),
                    "confidence": payload.get("confidence", provenance.get("confidence")),
                    "clearance": event.clearance,
                    "taint": self._taint_enum(payload),
                    "derivation": payload.get("derivation", provenance.get("derivation", {})),
                    "preview_ref": self._required_reference(payload.get("artifact_id"), "preview"),
                    "download_ref": self._required_reference(payload.get("artifact_id"), "download"),
                    "ledger_event_ref": event.event_id,
                    "artifact_sequence": event.sequence,
                    "created_at": event.occurred_at,
                }
            )
        except (ContractValidationError, TypeError, ValueError) as exc:
            raise NodeIntakeError(503, "deliverable_contract_corrupt", "The output deliverable contract could not be verified.") from exc
        return review.to_wire_dict()

    def _visible_task(self, task_id: str):
        event = next(
            (event for event in self._ledger.events if event.task_id == task_id and event.event_type == "task.created"),
            None,
        )
        if event is None or not self._can_read(event.clearance):
            raise NodeIntakeError(404, "task_not_found", "The requested task does not exist.")
        return event

    def _record_access(self, event, event_type: str) -> str:
        key = idempotency_key("node-deliverable-access", event_type, event.payload["artifact_id"])
        existing = self._ledger.find_by_idempotency(key)
        if existing is not None:
            return existing.event_id
        access = build_event(
            event_type=event_type,
            task_id=event.task_id,
            actor_id="node.deliverable",
            actor_type="service",
            payload_contract="NodeDeliverableAccess",
            payload_version="1.0",
            payload={
                "artifact_id": event.payload["artifact_id"],
                "content_hash": event.payload.get("content_hash"),
                "operation": event_type,
            },
            clearance=event.clearance,
            idempotency=key,
            sequence=len(self._ledger),
            previous_event_hash=self._ledger.head_hash,
        )
        try:
            self._ledger.append(access)
        except Exception as exc:
            raise NodeIntakeError(503, "ledger_unavailable", "The deliverable access could not be recorded.") from exc
        return access.event_id

    @staticmethod
    def _is_deliverable_check(event) -> bool:
        return event.event_type == "artifact.checked" and event.payload_contract == "DeliverableArtifactCheck"

    def _can_read(self, clearance: Clearance) -> bool:
        return _CLEARANCE_RANK[clearance] <= _CLEARANCE_RANK[self._clearance_context]

    @staticmethod
    def _require_reference(value: Any, label: str) -> str:
        if not isinstance(value, str) or not _REFERENCE_RE.fullmatch(value):
            raise NodeIntakeError(400, "invalid_reference", f"The {label} reference is invalid.")
        return value

    @classmethod
    def _required_reference(cls, value: Any, label: str) -> str:
        return cls._require_reference(value, label)

    @staticmethod
    def _required_text(value: Any, label: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or "\x00" in value or len(value) > maximum:
            raise NodeIntakeError(503, "deliverable_contract_corrupt", f"The {label} is invalid.")
        return value

    @staticmethod
    def _required_hash(value: Any) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise NodeIntakeError(503, "deliverable_contract_corrupt", "The deliverable hash is invalid.")
        return value.lower()

    @classmethod
    def _references(cls, value: Any, label: str) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise NodeIntakeError(503, "deliverable_contract_corrupt", f"The deliverable {label} references are incomplete.")
        return tuple(cls._required_text(item, f"{label} reference", 512) for item in value)

    @staticmethod
    def _taint(payload: dict[str, Any]) -> str:
        value = payload.get("taint")
        if value is None and isinstance(payload.get("provenance"), dict):
            value = payload["provenance"].get("taint")
        if value not in {item.value for item in Taint}:
            raise NodeIntakeError(503, "deliverable_contract_corrupt", "The deliverable taint is invalid.")
        return value

    @classmethod
    def _taint_enum(cls, payload: dict[str, Any]) -> Taint:
        return Taint(cls._taint(payload))

    @classmethod
    def _preview_blocks(cls, value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list) or not value or len(value) > _MAX_BLOCKS:
            raise NodeIntakeError(503, "deliverable_contract_corrupt", "The deliverable preview is incomplete.")
        blocks: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                raise NodeIntakeError(503, "deliverable_contract_corrupt", "The deliverable preview block is invalid.")
            kind = cls._required_text(item.get("kind"), "preview block kind", 64)
            text = cls._required_text(item.get("text"), "preview block text", _MAX_BLOCK_TEXT)
            blocks.append({"kind": kind, "text": text})
        return blocks


__all__ = ["LocalDeliverableGateway", "NodeDeliverableGateway"]
