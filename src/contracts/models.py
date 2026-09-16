from __future__ import annotations

import hashlib
import json
import re
import types
from dataclasses import MISSING, dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Literal, Union, get_args, get_origin, get_type_hints

from .errors import ContractValidationError, ValidationIssue

SCHEMA_VERSION = "1.0"
COMPATIBILITY_ID = "airbench-core-contracts"
NODE_PROTOCOL_VERSION = "0.1"
NODE_PROTOCOL_COMPATIBILITY_ID = "airbench-node-protocol"
_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
LEDGER_EVENT_TYPES = {
    # ── Core task lifecycle ────────────────────────────────────────────────────
    "task.created", "task.authorized", "task.plan.committed", "task.plan.approved", "task.checkpoint.committed", "task.cancelled", "task.failed",
    "team.execution.started", "team.execution.completed", "team.execution.failed", "team.execution.cancelled",
    "lifecycle.intercepted", "lifecycle.blocked", "worker.context.compacted",
    "team.created", "worker.assigned", "worker.started", "worker.completed", "worker.failed", "worker.handoff", "worker.handoff.rejected", "worker.handoff.late",
    "model.requested", "routing.decided", "model.responded", "model.failed", "tool.requested", "tool.authorized", "tool.denied", "tool.result",
    "evidence.created", "fact.candidate", "fact.committed", "verification.completed", "retry.started", "fallback.selected",
    "resource.plan.admitted", "resource.plan.queued", "barrier.waiting", "barrier.completed", "artifact.staged", "artifact.checked", "artifact.previewed", "artifact.downloaded",
    "human.review.required", "human.signoff", "completion.recorded", "escalation.required",
    "index.requested", "index.completed", "index.failed",
    "knowledge.ingest.started", "knowledge.ingest.file_completed", "knowledge.ingest.file_failed", "knowledge.ingest.completed",
    "retrieval.requested", "retrieval.completed", "retrieval.failed",
    "vision.requested", "vision.completed", "vision.failed",
    "pid.extracted",
    "world_model.requested", "verification.requested",
    "world_model.conflict", "world_model.review_required", "world_model.review_resolved",
    "projection.rebuilt", "projection.exported", "checkpoint.committed", "retry.completed",
    "retry.failed", "side_effect.reserved", "side_effect.committed", "side_effect.uncertain",
    "recovery.resumed", "crash.recovered",
    # M8 verification, authority, and consistency decisions
    "verification.evaluator.requested", "verification.evaluator.completed",
    "consistency.checked", "authority.decided", "completion.blocked", "completion.ready",
    "consistency.justified", "authority.authorized",
    # ── M5.1: Model registry, artifact integrity, qualification ───────────────
    "model.registry.loaded",          # registry manifest loaded and signature verified
    "model.registry.signature.verified",  # manifest HMAC confirmed
    "model.target.rejected",          # target failed eligibility or signature check
    "model.target.qualified",         # target passed all qualification gates
    "model.artifact.integrity.verified",  # local file hash matches registry digest
    "model.qualification.checked",    # certificate expiry and role scope verified
    "model.variant.qualified",        # quantization variant passed role/risk qualification
    "backend.compatibility.started",  # backend conformance test suite started
    "backend.compatibility.completed",# backend conformance test suite finished
    "backend.airgap_startup.checked", # no-egress startup confirmed
    "backend.nim.checked",            # NIM optional path tested
    "model.loaded",                   # model weights loaded into runtime
    "model.resident",                 # model is warm-resident in VRAM
    "model.evicted",                  # model evicted from VRAM (residency policy)
    "model.unloaded",                 # model fully unloaded
    "model.call.started",             # individual inference call started
    "model.call.completed",           # individual inference call finished
    "model.call.failed",              # individual inference call failed
    "model.tool_call.tested",         # tool-call schema validity tested
    "model.structured_output.tested", # structured output schema tested
    "model.multimodal.tested",        # multimodal/image input tested
    "model.lifecycle.tested",         # streaming and cancellation tested
    "routing.decision",               # RoutingDecision emitted for a worker assignment
    "routing.fallback.selected",      # qualified fallback target selected
    "routing.queued",                 # routing queued; no qualified target available now
    "endpoint.selected",               # signed, allowlisted remote endpoint selected
    "endpoint.rejected",               # endpoint failed security or qualification gates
    "endpoint.egress.denied",         # remote data-egress policy denied
    "endpoint.request.started",       # remote request started
    "endpoint.request.completed",     # remote request completed
    "endpoint.request.failed",        # remote request failed
    "verification.reservation.confirmed",  # verifier slot reserved before worker starts
    "completion.blocked",             # completion gate blocked (verifier unavailable etc.)
    "completion.ready",               # all completion gates passed
    "artifact.integrity.verified",    # supply-chain artifact hash confirmed
    # ── M5.2: Hardware measurement, scheduling, residency ─────────────────────
    "hardware.profile.measured",      # legacy alias kept for backward compatibility
    "hardware.measurement.started",   # probe script started collecting hardware data
    "hardware.measurement.completed", # signed HardwareProfile produced
    "hardware.profile.loaded",        # signed HardwareProfile validated and loaded
    "model.benchmark.started",        # per-target benchmark run started
    "model.benchmark.completed",      # per-target benchmark run finished
    "team.resource_plan.created",     # TeamResourcePlan constructed before admission
    "team.resource_plan.admitted",    # plan admitted (parallel or serial mode)
    "team.resource_plan.queued",      # plan queued; capacity temporarily unavailable
    "team.resource_plan.degraded_needs_review",  # admitted in lower-capability mode with review
    "team.resource_plan.rejected",    # plan rejected; unsafe or invalid
    "worker.resource_reserved",       # per-worker VRAM/RAM/KV reservation confirmed
    "worker.preempted",               # worker preempted by higher-priority task
    "worker.cancelled",               # worker cancelled; reservations released
    "execution.mode.selected",        # parallel/pipelined/serial mode selected
    "execution.mode.changed",         # mode changed during execution (e.g. capacity drop)
    "join_barrier.waiting",           # join barrier waiting for upstream workers
    "join_barrier.completed",         # all upstream workers satisfied the join barrier
    "background.work.yielded",        # background ingestion yielded to interactive task
    "resource.exhaustion.detected",   # VRAM/RAM/KV-cache exhaustion detected
    "resource.recovered",             # resource state confirmed clean after failure/reset
    "resource.lease.granted",         # resource lease issued to a worker
    "resource.lease.activated",       # worker started consuming a granted lease
    "resource.lease.released",        # resource lease returned after worker completes
    "resource.lease.expired",         # resource lease reached its deadline
    "resource.lease.cancelled",       # resource lease cancelled by task policy
    "resource.lease.failed",          # resource lease transition failed
    "team.resource_plan.released",    # the team's committed resource envelope returned
    "team.resource_plan.cancelled",   # the team's resource plan was cancelled
    "resource.admission.degraded",    # admission fell back to degraded mode
    "resource.queue.updated",         # admission queue position updated
    "join_barrier.resolved",          # non-completed barrier outcome
    # ── M-C: Domain pack loading ──────────────────────────────────────────────
    "pack.loaded",                    # signed domain pack loaded and registered
    "pack.load_rejected",             # domain pack failed signature or validation
}


class ContractStatus(str, Enum):
    proposed = "proposed"; accepted = "accepted"; rejected = "rejected"; failed = "failed"; needs_review = "needs_review"; queued = "queued"; cancelled = "cancelled"; verified = "verified"


class Clearance(str, Enum):
    public = "public"; internal = "internal"; restricted = "restricted"; secret = "secret"


class Taint(str, Enum):
    clean = "clean"; untrusted = "untrusted"; contaminated = "contaminated"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Contract:
    schema_version: ClassVar[str] = SCHEMA_VERSION
    compatibility_id: ClassVar[str] = COMPATIBILITY_ID

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Contract:
        if not isinstance(payload, dict):
            raise ContractValidationError(cls.__name__, [ValidationIssue("$", "type", "payload must be an object", type(payload).__name__)])
        hints = get_type_hints(cls)
        allowed = {f.name for f in fields(cls) if f.init} | {"schema_version", "compatibility_id"}
        issues: list[ValidationIssue] = []
        for key in payload:
            if key not in allowed:
                issues.append(ValidationIssue(key, "unknown_field", "field is not part of this contract"))
        for f in fields(cls):
            if f.init and f.name not in payload and f.default is MISSING and f.default_factory is MISSING:
                issues.append(ValidationIssue(f.name, "missing", "required field is missing"))
        if payload.get("schema_version", cls.schema_version) != cls.schema_version:
            issues.append(ValidationIssue("schema_version", "incompatible_version", f"expected {cls.schema_version}"))
        if payload.get("compatibility_id", cls.compatibility_id) != cls.compatibility_id:
            issues.append(ValidationIssue("compatibility_id", "incompatible_contract", f"expected {cls.compatibility_id}"))
        values = {k: _normalize(v, hints.get(k, Any)) for k, v in payload.items() if k in allowed and k not in {"schema_version", "compatibility_id"}}
        try:
            obj = cls(**values)
        except TypeError as exc:
            issues.append(ValidationIssue("$", "missing_or_invalid", str(exc)))
            obj = None
        if obj is not None:
            for f in fields(obj):
                if f.name in payload:
                    issues.extend(_type_issues(f.name, values[f.name], hints.get(f.name, Any)))
            issues.extend(obj._validate(hints))
        if issues:
            raise ContractValidationError(cls.__name__, issues)
        return obj

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            if f.name.endswith("_id") or f.name in {"task_id", "team_id", "worker_id", "event_id", "fact_id", "packet_id", "assignment_id", "completion_id", "request_id", "decision_id", "action_id", "evidence_id"}:
                if not isinstance(value, str) or not _ID.match(value):
                    issues.append(ValidationIssue(f.name, "invalid_id", "must be a lowercase stable identifier"))
            if isinstance(value, str) and len(value) > 65536:
                issues.append(ValidationIssue(f.name, "resource_limit", "string exceeds 65536 characters"))
            if isinstance(value, (list, dict)) and len(value) > 10000:
                issues.append(ValidationIssue(f.name, "resource_limit", "collection exceeds 10000 items"))
        return issues

    def to_dict(self) -> dict[str, Any]:
        def convert(v: Any) -> Any:
            if isinstance(v, Enum): return v.value
            if isinstance(v, Contract): return v.to_dict()
            if isinstance(v, tuple): return [convert(x) for x in v]
            if isinstance(v, list): return [convert(x) for x in v]
            if isinstance(v, dict): return {k: convert(v[k]) for k in sorted(v)}
            return v
        result = {"schema_version": self.schema_version, "compatibility_id": self.compatibility_id}
        result.update({f.name: convert(getattr(self, f.name)) for f in fields(self)})
        return result

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


def _camel_case(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _wire_value(value: Any) -> Any:
    if isinstance(value, NodeWireContract):
        return value.to_wire_dict()
    if isinstance(value, Contract):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_wire_value(item) for item in value]
    if isinstance(value, list):
        return [_wire_value(item) for item in value]
    if isinstance(value, dict):
        return {_camel_case(str(key)): _wire_value(item) for key, item in value.items()}
    return value


def _from_wire_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_from_wire_value(item) for item in value]
    if isinstance(value, dict):
        return {_snake_case(str(key)): _from_wire_value(item) for key, item in value.items()}
    return value


class NodeWireContract(Contract):
    """Camel-case response contract for the Rust-owned Node boundary."""

    schema_version: ClassVar[str] = NODE_PROTOCOL_VERSION
    compatibility_id: ClassVar[str] = NODE_PROTOCOL_COMPATIBILITY_ID

    @classmethod
    def from_wire_dict(cls, payload: dict[str, Any]) -> "NodeWireContract":
        return cls.from_dict(_from_wire_value(payload))

    def to_wire_dict(self) -> dict[str, Any]:
        return _wire_value(self.to_dict())


class NodeTaskStatus(str, Enum):
    accepted = "accepted"
    planning = "planning"
    running = "running"
    needs_review = "needs_review"
    completed = "completed"
    blocked = "blocked"
    failed = "failed"
    stopped = "stopped"


@dataclass(frozen=True)
class NodeLifecycleEventPayload:
    phase: str
    status: NodeTaskStatus
    summary: str | None = None


@dataclass(frozen=True)
class NodeWorkerEventPayload:
    role: str
    label: str
    status: str
    team_id: str | None = None
    assignment_id: str | None = None
    worker_id: str | None = None
    resource_lease_id: str | None = None


@dataclass(frozen=True)
class NodeExecutionEventPayload:
    """Clearance-filtered execution metadata for the desktop work trace.

    This is deliberately an allowlisted projection.  The Node exposes enough
    structure to explain deterministic team execution, admission, handoffs,
    and barriers, but never forwards the original ledger payload or worker
    content to the desktop.
    """

    status: str
    summary: str
    execution_mode: str | None = None
    team_id: str | None = None
    plan_id: str | None = None
    assignment_id: str | None = None
    worker_id: str | None = None
    role: str | None = None
    label: str | None = None
    barrier_id: str | None = None
    dependency_ids: tuple[str, ...] = ()
    resource_lease_id: str | None = None
    queue_position: int | None = None
    hardware_profile_ref: str | None = None
    model_target_id: str | None = None
    qualification_id: str | None = None


@dataclass(frozen=True)
class NodeEvidenceEventPayload:
    evidence: "NodeEvidenceRef"


@dataclass(frozen=True)
class NodeVerificationEventPayload:
    summary: str
    passed: bool


@dataclass(frozen=True)
class NodeApprovalEventPayload:
    reason: str


@dataclass(frozen=True)
class NodeArtifactEventPayload:
    artifact_id: str


@dataclass(frozen=True)
class NodeSummaryEventPayload:
    summary: str


@dataclass(frozen=True)
class NodeUnknownEventPayload:
    original_type: str
    raw: Any


@dataclass(frozen=True)
class NodeProvenanceRef(NodeWireContract):
    source_document_id: str
    source_version: str
    location: dict[str, Any] | None
    extraction_method: str
    observed_at: str | None
    ingested_at: str
    ledger_event_ref: str


@dataclass(frozen=True)
class NodeEvidenceRef(NodeWireContract):
    evidence_id: str
    content_hash: str
    source: NodeProvenanceRef
    confidence: float
    clearance: Clearance
    taint: Taint

    def _validate(self, hints):
        issues = super()._validate(hints)
        if not re.fullmatch(r"[0-9a-fA-F]{64}", self.content_hash):
            issues.append(ValidationIssue("content_hash", "hash", "must be a SHA-256 hex digest"))
        if not 0 <= self.confidence <= 1:
            issues.append(ValidationIssue("confidence", "range", "must be between 0 and 1"))
        return issues


@dataclass(frozen=True)
class NodeFactRef(NodeWireContract):
    fact_id: str
    value: Any
    source: NodeProvenanceRef
    confidence: float
    clearance: Clearance
    taint: Taint
    parent_fact_ids: tuple[str, ...]
    unit: str | None
    derivation: dict[str, Any] | None
    superseded_by: str | None

    def _validate(self, hints):
        issues = super()._validate(hints)
        if not 0 <= self.confidence <= 1:
            issues.append(ValidationIssue("confidence", "range", "must be between 0 and 1"))
        return issues


@dataclass(frozen=True)
class NodeRouteTraceEntry(NodeWireContract):
    sequence: int
    event_type: str
    occurred_at: str
    actor: str
    clearance_context: Clearance
    ledger_event_ref: str
    payload_hash: str
    request_id: str | None = None
    worker_id: str | None = None
    role: str | None = None
    task_kind: str | None = None
    required_capability: str | None = None
    selected_target: str | None = None
    selected_model_name: str | None = None
    decision_source: str | None = None
    rule_or_threshold: str | None = None
    qualification_certificate: str | None = None
    fallback_target: str | None = None
    reason: str | None = None
    status: str | None = None
    eligible_targets: tuple[str, ...] = ()

    def _validate(self, hints):
        issues = super()._validate(hints)
        if type(self.sequence) is not int or self.sequence < 1:
            issues.append(ValidationIssue("sequence", "range", "route sequence must be positive"))
        for name in ("event_type", "occurred_at", "actor", "ledger_event_ref", "payload_hash"):
            if not getattr(self, name).strip():
                issues.append(ValidationIssue(name, "required", "route entry identity is required"))
        return issues


@dataclass(frozen=True)
class NodeRouteTrace(NodeWireContract):
    task_id: str
    node_identity: str
    protocol_version: str
    clearance_context: Clearance
    entries: tuple[NodeRouteTraceEntry, ...]

    def _validate(self, hints):
        issues = super()._validate(hints)
        for name in ("task_id", "node_identity", "protocol_version"):
            if not getattr(self, name).strip():
                issues.append(ValidationIssue(name, "required", "route trace identity is required"))
        previous = 0
        for entry in self.entries:
            if entry.sequence <= previous:
                issues.append(ValidationIssue("entries", "order", "route entries must be ordered by sequence"))
            previous = entry.sequence
        return issues


@dataclass(frozen=True)
class NodeTaskSnapshot(NodeWireContract):
    task_id: str
    snapshot_id: str
    as_of_sequence: int
    title: str
    request_summary: str
    status: NodeTaskStatus
    phase: str
    clearance_context: Clearance
    input_manifest_ref: str
    evidence: tuple[NodeEvidenceRef, ...]
    facts: tuple[NodeFactRef, ...]
    artifact_refs: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    node_connection_ref: str
    ledger_head_ref: str

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.as_of_sequence < 0:
            issues.append(ValidationIssue("as_of_sequence", "range", "snapshot sequence must be non-negative"))
        for name in ("task_id", "snapshot_id", "node_connection_ref", "ledger_head_ref"):
            if not getattr(self, name).strip():
                issues.append(ValidationIssue(name, "required", "snapshot identity is required"))
        return issues


@dataclass(frozen=True)
class NodeArtifactReview(NodeWireContract):
    """Node-owned review projection for one generated deliverable.

    The desktop receives this projection only after the Deliverable Engine has
    committed the artifact and its checks to the ledger. The file bytes remain
    behind the Node preview/download boundary, while provenance and approval
    blockers stay visible.
    """

    task_id: str
    artifact_id: str
    node_identity: str
    protocol_version: str
    clearance_context: Clearance
    title: str
    media_type: str
    file_format: str
    template_id: str
    template_version: str
    content_hash: str
    byte_size: int
    status: str
    verification_status: str
    structural_check: str
    visual_check: str
    approval_state: str
    approval_blocking_reasons: tuple[str, ...]
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    verification_refs: tuple[str, ...]
    deterministic_value_refs: tuple[str, ...]
    confidence: float
    clearance: Clearance
    taint: Taint
    derivation: dict[str, Any]
    preview_ref: str
    download_ref: str
    ledger_event_ref: str
    artifact_sequence: int
    created_at: str

    def _validate(self, hints):
        issues = super()._validate(hints)
        if not re.fullmatch(r"[0-9a-fA-F]{64}", self.content_hash):
            issues.append(ValidationIssue("content_hash", "hash", "must be a SHA-256 hex digest"))
        if type(self.byte_size) is not int or self.byte_size < 0:
            issues.append(ValidationIssue("byte_size", "range", "artifact size must be non-negative"))
        if type(self.artifact_sequence) is not int or self.artifact_sequence < 0:
            issues.append(ValidationIssue("artifact_sequence", "range", "artifact sequence must be non-negative"))
        if type(self.confidence) not in (int, float) or not 0 <= self.confidence <= 1:
            issues.append(ValidationIssue("confidence", "range", "must be between 0 and 1"))
        if self.status not in {"staged", "verified_draft", "needs_review", "approved", "returned", "rejected", "superseded"}:
            issues.append(ValidationIssue("status", "enum", "invalid artifact status"))
        if self.verification_status not in {"not_run", "passed", "failed", "needs_review", "unavailable"}:
            issues.append(ValidationIssue("verification_status", "enum", "invalid artifact verification status"))
        if self.structural_check not in {"not_required", "passed", "failed"}:
            issues.append(ValidationIssue("structural_check", "enum", "invalid structural check status"))
        if self.visual_check not in {"not_required", "passed", "failed", "unavailable"}:
            issues.append(ValidationIssue("visual_check", "enum", "invalid visual check status"))
        if self.approval_state not in {"not_ready", "pending", "approved", "returned", "rejected", "unavailable"}:
            issues.append(ValidationIssue("approval_state", "enum", "invalid artifact approval state"))
        if not isinstance(self.derivation, dict):
            issues.append(ValidationIssue("derivation", "type", "artifact derivation must be an object"))
        for name in ("title", "media_type", "file_format", "template_id", "template_version", "preview_ref", "download_ref", "ledger_event_ref", "created_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                issues.append(ValidationIssue(name, "required", "artifact metadata is required"))
        for name, refs in (("source_refs", self.source_refs), ("evidence_refs", self.evidence_refs), ("verification_refs", self.verification_refs)):
            if not refs or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
                issues.append(ValidationIssue(name, "provenance", "artifact provenance references are required"))
        if self.taint == Taint.contaminated:
            issues.append(ValidationIssue("taint", "security", "contaminated artifacts cannot be exposed"))
        return issues


@dataclass(frozen=True)
class NodeTaskEvent(NodeWireContract):
    event_id: str
    task_id: str
    sequence: int
    event_type: str
    occurred_at: str
    actor: str
    clearance_context: Clearance
    payload_hash: str
    ledger_event_ref: str
    payload: dict[str, Any]

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.sequence < 1:
            issues.append(ValidationIssue("sequence", "range", "event sequence must be positive"))
        for name in ("event_id", "task_id", "event_type", "occurred_at", "actor", "payload_hash", "ledger_event_ref"):
            if not getattr(self, name).strip():
                issues.append(ValidationIssue(name, "required", "event identity is required"))
        if not isinstance(self.payload, dict):
            issues.append(ValidationIssue("payload", "type", "event payload must be an object"))
        return issues


@dataclass(frozen=True)
class NodeTaskEventBatch(Contract):
    stream_id: str
    node_identity: str
    protocol_version: str
    clearance_context: Clearance
    events: tuple[NodeTaskEvent, ...]
    next_sequence: int
    has_more: bool
    ledger_event_refs: tuple[str, ...]

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.next_sequence < 0:
            issues.append(ValidationIssue("next_sequence", "range", "event cursor must be non-negative"))
        if len(self.events) != len(self.ledger_event_refs):
            issues.append(ValidationIssue("ledger_event_refs", "alignment", "ledger references must align with events"))
        return issues

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["events"] = [event.to_wire_dict() for event in self.events]
        return result

    @classmethod
    def from_wire_dict(cls, payload: dict[str, Any]) -> "NodeTaskEventBatch":
        return cls.from_dict(_from_wire_value(payload))


NODE_COMMAND_TYPES = {
    "task.create",
    "task.authorize",
    "task.cancel",
    "task.request_review",
    "task.approve_plan",
    "task.approve_artifact",
    "task.return_artifact",
    "model.call",
    "node.recheck",
}


@dataclass(frozen=True)
class NodeHandshake(Contract):
    """Authenticated Node handshake and protocol negotiation result."""

    node_identity: str
    protocol_version: str
    protocol_compatibility_id: str
    supported_protocol_versions: tuple[str, ...]
    clearance_context: Clearance
    authenticated_subject: str
    domain_pack_ref: str
    ledger_event_ref: str

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.protocol_version not in self.supported_protocol_versions:
            issues.append(ValidationIssue("protocol_version", "compatibility", "selected protocol is not in the supported protocol list"))
        for name in ("node_identity", "protocol_version", "protocol_compatibility_id", "authenticated_subject", "domain_pack_ref", "ledger_event_ref"):
            if not getattr(self, name).strip():
                issues.append(ValidationIssue(name, "required", "handshake identity is required"))
        return issues


@dataclass(frozen=True)
class NodeCommandEnvelope(Contract):
    """Versioned, authenticated command envelope at the Node boundary.

    The command is transport-neutral. The Node validates it before handing
    the requested mutation to the orchestrator, and the ledger stores only a
    non-sensitive receipt derived from this envelope.
    """

    command_id: str
    task_id: str | None
    actor: str
    expected_sequence: int | None
    idempotency_key: str
    client_version: str
    command_type: str
    arguments: dict[str, Any]

    def _validate(self, hints):
        issues = super()._validate(hints)
        if not self.actor.strip():
            issues.append(ValidationIssue("actor", "required", "command actor is required"))
        if not self.idempotency_key.strip() or len(self.idempotency_key) > 256:
            issues.append(ValidationIssue("idempotency_key", "required", "idempotency key must be 1..256 characters"))
        if not self.client_version.strip() or len(self.client_version) > 64:
            issues.append(ValidationIssue("client_version", "required", "client version must be 1..64 characters"))
        if self.command_type not in NODE_COMMAND_TYPES:
            issues.append(ValidationIssue("command_type", "enum", "unsupported Node command"))
        if self.expected_sequence is not None and (type(self.expected_sequence) is not int or self.expected_sequence < 0):
            issues.append(ValidationIssue("expected_sequence", "range", "expected sequence must be a non-negative integer or null"))
        if not isinstance(self.arguments, dict):
            issues.append(ValidationIssue("arguments", "type", "command arguments must be an object"))
        return issues


@dataclass(frozen=True)
class NodeCommandResult(Contract):
    """Bounded result returned after a command is accepted or rejected."""

    outcome: Literal["accepted", "rejected", "needs_review"]
    command_id: str
    task_id: str | None
    idempotency_key: str
    ledger_event_ref: str | None
    sequence: int | None
    state: str | None
    node_identity: str
    protocol_version: str
    clearance_context: Clearance
    event_type: str | None = None
    code: str | None = None
    message: str | None = None
    reason: str | None = None

    def _validate(self, hints):
        issues = super()._validate(hints)
        if not self.idempotency_key.strip():
            issues.append(ValidationIssue("idempotency_key", "required", "result idempotency key is required"))
        if self.sequence is not None and (type(self.sequence) is not int or self.sequence < 0):
            issues.append(ValidationIssue("sequence", "range", "result sequence must be non-negative"))
        if self.outcome == "accepted" and (not self.task_id or not self.ledger_event_ref or not self.state or not self.event_type):
            issues.append(ValidationIssue("outcome", "result", "accepted results require task, ledger, and state"))
        if not self.node_identity.strip() or not self.protocol_version.strip():
            issues.append(ValidationIssue("node_identity", "result", "Node identity and protocol are required"))
        if self.outcome == "rejected" and not self.code:
            issues.append(ValidationIssue("code", "result", "rejected results require a code"))
        return issues


def _type_issues(path: str, value: Any, expected: Any) -> list[ValidationIssue]:
    if expected is Any:
        return []
    origin = get_origin(expected)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in get_args(expected): return []
        return [] if any(not _type_issues(path, value, t) for t in get_args(expected) if t is not type(None)) else [ValidationIssue(path, "type", "value does not match the declared type", type(value).__name__)]
    if origin in (tuple, list):
        if not isinstance(value, origin): return [ValidationIssue(path, "type", f"must be {origin.__name__}", type(value).__name__)]
        args = get_args(expected)
        if args and args[-1] is not Ellipsis:
            if len(value) != len(args): return [ValidationIssue(path, "length", "wrong number of items")]
            return [i for n, t in enumerate(args) for i in _type_issues(f"{path}[{n}]", value[n], t)]
        return [i for n, x in enumerate(value) for i in _type_issues(f"{path}[{n}]", x, args[0])] if args else []
    if origin is dict:
        if not isinstance(value, dict): return [ValidationIssue(path, "type", "must be an object", type(value).__name__)]
        args = get_args(expected)
        return [i for k, x in value.items() for i in _type_issues(f"{path}.{k}", x, args[1])] if len(args) == 2 else []
    if isinstance(expected, type) and issubclass(expected, Enum):
        return [] if isinstance(value, expected) or (isinstance(value, str) and value in [e.value for e in expected]) else [ValidationIssue(path, "enum", "invalid enum value", type(value).__name__)]
    if isinstance(expected, type) and issubclass(expected, Contract):
        return [] if isinstance(value, expected) else [ValidationIssue(path, "type", "must be a contract object", type(value).__name__)]
    if expected is None or expected is type(None): return [] if value is None else [ValidationIssue(path, "type", "must be null", type(value).__name__)]
    return [] if type(value) is expected else [ValidationIssue(path, "type", f"must be {getattr(expected, '__name__', expected)}", type(value).__name__)]


def _normalize(value: Any, expected: Any) -> Any:
    origin = get_origin(expected)
    if origin is tuple and isinstance(value, list):
        return tuple(_normalize(x, get_args(expected)[0]) for x in value)
    if origin is list and isinstance(value, list):
        return [_normalize(x, get_args(expected)[0]) for x in value]
    if origin is dict and isinstance(value, dict) and len(get_args(expected)) == 2:
        return {k: _normalize(v, get_args(expected)[1]) for k, v in value.items()}
    if isinstance(expected, type) and issubclass(expected, Contract) and isinstance(value, dict):
        return expected.from_dict(value)
    if isinstance(expected, type) and issubclass(expected, Enum) and isinstance(value, str):
        try:
            return expected(value)
        except ValueError:
            return value
    return value


@dataclass(frozen=True)
class FactEnvelope(Contract):
    fact_id: str; value: Any; source_ref: str; confidence: float; clearance: Clearance; taint: Taint
    extraction_method: str; observed_at: str; ingested_at: str; parent_fact_ids: tuple[str, ...] = (); unit: str | None = None; valid_from: str | None = None; valid_to: str | None = None; supersedes_fact_id: str | None = None
    def _validate(self, hints):
        issues = super()._validate(hints)
        if not 0 <= self.confidence <= 1: issues.append(ValidationIssue("confidence", "range", "must be between 0 and 1"))
        if not self.source_ref: issues.append(ValidationIssue("source_ref", "required", "source reference is required"))
        return issues


@dataclass(frozen=True)
class UntrustedEvidence(Contract):
    evidence_id: str; source_ref: str; content_hash: str; media_type: str; clearance: Clearance; taint: Taint = Taint.untrusted; captured_at: str = field(default_factory=_now); byte_size: int = 0; excerpt_ref: str | None = None
    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.byte_size < 0 or self.byte_size > 50_000_000: issues.append(ValidationIssue("byte_size", "resource_limit", "must be between 0 and 50,000,000"))
        if self.taint == Taint.clean: issues.append(ValidationIssue("taint", "security", "evidence cannot be clean by default"))
        return issues


@dataclass(frozen=True)
class BoundingBox(Contract):
    """Integer page-local pixel region produced by an OCR or vision extractor.

    Coordinates are page-local and never carry a host path.  The record stays
    untrusted evidence and does not imply any document authority.
    """

    x: int; y: int; width: int; height: int; page_number: int = 1; unit: str = "px"

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.x < 0 or self.y < 0: issues.append(ValidationIssue("x", "range", "coordinates must be non-negative"))
        if self.width <= 0 or self.height <= 0: issues.append(ValidationIssue("width", "range", "width and height must be positive"))
        if self.page_number < 1: issues.append(ValidationIssue("page_number", "range", "page number must be positive"))
        if self.unit not in {"px", "pt"}: issues.append(ValidationIssue("unit", "enum", "unit must be px or pt"))
        return issues


@dataclass(frozen=True)
class ConfidenceScore(Contract):
    """A calibrated-or-declared extraction confidence with its method label."""

    value: float; method: str; calibrated: bool = False

    def _validate(self, hints):
        issues = super()._validate(hints)
        if not 0 <= self.value <= 1: issues.append(ValidationIssue("value", "range", "confidence must be between 0 and 1"))
        if not self.method.strip(): issues.append(ValidationIssue("method", "required", "confidence method is required"))
        return issues


@dataclass(frozen=True)
class PageRegion(Contract):
    """One sourced text region with a bounding box and extraction confidence."""

    region_id: str; page_number: int; text: str; bounding_box: BoundingBox; confidence: float; extraction_method: str

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.page_number < 1: issues.append(ValidationIssue("page_number", "range", "page number must be positive"))
        if not 0 <= self.confidence <= 1: issues.append(ValidationIssue("confidence", "range", "confidence must be between 0 and 1"))
        if not self.text.strip(): issues.append(ValidationIssue("text", "required", "region text is required"))
        if not self.extraction_method.strip(): issues.append(ValidationIssue("extraction_method", "required", "extraction method is required"))
        return issues


@dataclass(frozen=True)
class StructuredTable(Contract):
    """A table recovered from an image or scanned page.

    Values remain strings because the unit context travels in ``units`` keyed
    by column header, not baked into a parsed number.  Deterministic conversion
    to typed values happens later, under verification, never inside extraction.
    """

    table_id: str; page_number: int; headers: tuple[str, ...]; rows: tuple[tuple[str, ...], ...]; confidence: float; extraction_method: str; units: dict[str, str] = field(default_factory=dict); source_ref: str = ""; source_span: str = ""

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.page_number < 1: issues.append(ValidationIssue("page_number", "range", "page number must be positive"))
        if not 0 <= self.confidence <= 1: issues.append(ValidationIssue("confidence", "range", "confidence must be between 0 and 1"))
        if not self.headers: issues.append(ValidationIssue("headers", "required", "table headers are required"))
        if not self.extraction_method.strip(): issues.append(ValidationIssue("extraction_method", "required", "extraction method is required"))
        width = len(self.headers)
        for index, row in enumerate(self.rows):
            if len(row) != width:
                issues.append(ValidationIssue(f"rows[{index}]", "shape", "row width must match header width"))
        if len(self.headers) != len(set(self.headers)):
            issues.append(ValidationIssue("headers", "duplicate", "table headers must be unique"))
        for column in self.units:
            if column not in self.headers:
                issues.append(ValidationIssue(f"units.{column}", "unknown_column", "unit column must match a header"))
        return issues


@dataclass(frozen=True)
class TaskEnvelope(Contract):
    task_id: str; principal_id: str; clearance: Clearance; request: str; domain_pack_ref: str; risk_class: str; autonomy_ceiling: str; allowed_evidence_scope: tuple[str, ...]; permitted_worker_capabilities: tuple[str, ...]; permitted_tools: tuple[str, ...]; output_contract: str; verification_criteria: tuple[str, ...]; resource_budget: dict[str, int]; title: str = ""; project_ref: str | None = None; priority: str = "normal"; deadline: str | None = None; input_manifest_refs: tuple[str, ...] = (); state: str = "created"; parent_task_id: str | None = None; created_at: str = field(default_factory=_now)
    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.state not in {"created", "authorized", "planned", "executing", "awaiting_check", "awaiting_review", "rendering", "deliverable_verified", "complete", "needs_review", "blocked", "failed", "cancelled"}:
            issues.append(ValidationIssue("state", "enum", "invalid task state"))
        if not self.request.strip():
            issues.append(ValidationIssue("request", "required", "request must not be empty"))
        if len(self.title) > 256:
            issues.append(ValidationIssue("title", "length", "title must not exceed 256 characters"))
        if self.project_ref is not None and len(self.project_ref) > 256:
            issues.append(ValidationIssue("project_ref", "length", "project reference must not exceed 256 characters"))
        if not self.priority.strip() or len(self.priority) > 64:
            issues.append(ValidationIssue("priority", "required", "priority must be 1..64 characters"))
        if self.deadline is not None and len(self.deadline) > 64:
            issues.append(ValidationIssue("deadline", "length", "deadline must not exceed 64 characters"))
        if isinstance(self.resource_budget, dict) and any(type(value) is not int or value < 0 for value in self.resource_budget.values()):
            issues.append(ValidationIssue("resource_budget", "resource", "budget values must be non-negative integers"))
        return issues


@dataclass(frozen=True)
class TeamPlan(Contract):
    team_id: str; task_id: str; assignments: tuple[str, ...]; dependency_graph: dict[str, tuple[str, ...]]; concurrency_ceiling: int; required_verification: bool; completion_criteria: tuple[str, ...]; plan_version_hash: str; policy_version_hash: str; status: ContractStatus = ContractStatus.proposed
    def _validate(self, hints):
        issues = super()._validate(hints)
        if type(self.concurrency_ceiling) is not int or self.concurrency_ceiling < 1:
            issues.append(ValidationIssue("concurrency_ceiling", "range", "must be at least 1"))
        if not self.required_verification:
            issues.append(ValidationIssue("required_verification", "safety", "independent verification is mandatory"))
        if not self.assignments:
            issues.append(ValidationIssue("assignments", "required", "team must contain at least one assignment"))
        return issues


@dataclass(frozen=True)
class TaskPlanReview(Contract):
    """Clearance-filtered plan projection for the desktop review surface.

    The Node creates this view from committed orchestrator and hardware
    admission events. The desktop cannot construct or revise it locally.
    """

    task_id: str
    node_identity: str
    protocol_version: str
    clearance_context: Clearance
    plan_state: str
    task_sequence: int
    team_id: str | None
    assignments: tuple[str, ...]
    dependency_graph: dict[str, tuple[str, ...]]
    concurrency_ceiling: int
    execution_mode: str
    worker_capabilities: dict[str, str]
    hardware_profile_ref: str | None
    hardware_reason: str
    required_verification: bool
    completion_criteria: tuple[str, ...]
    required_authority: str
    authority_reason: str
    plan_version_hash: str | None
    policy_version_hash: str | None
    ledger_event_ref: str | None
    failure_code: str | None = None
    failure_reason: str | None = None

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.plan_state not in {"not_ready", "ready", "queued", "needs_review", "blocked", "rejected"}:
            issues.append(ValidationIssue("plan_state", "enum", "invalid plan state"))
        if type(self.task_sequence) is not int or self.task_sequence < 0:
            issues.append(ValidationIssue("task_sequence", "range", "task sequence must be non-negative"))
        if type(self.concurrency_ceiling) is not int or self.concurrency_ceiling < 0:
            issues.append(ValidationIssue("concurrency_ceiling", "range", "concurrency ceiling must be non-negative"))
        if self.execution_mode not in {"parallel", "pipelined", "serial_virtual_team", "not_selected"}:
            issues.append(ValidationIssue("execution_mode", "enum", "invalid execution mode"))
        if not self.required_verification:
            issues.append(ValidationIssue("required_verification", "safety", "independent verification is mandatory"))
        if self.plan_state == "ready" and (not self.team_id or not self.plan_version_hash or self.execution_mode == "not_selected"):
            issues.append(ValidationIssue("plan_state", "authority", "ready plans require a committed team and hardware mode"))
        if self.plan_state in {"blocked", "rejected"} and not (self.failure_code and self.failure_reason):
            issues.append(ValidationIssue("failure_reason", "required", "blocked plans require a bounded failure reason"))
        return issues


@dataclass(frozen=True)
class WorkerAssignment(Contract):
    assignment_id: str; team_id: str; task_id: str; worker_id: str; role: str; stage: str; input_schema: str; output_schema: str; evidence_refs: tuple[str, ...]; allowed_tools: tuple[str, ...]; clearance: Clearance; taint: Taint; capability_requirement: str; deadline: str; idempotency_key: str; status: ContractStatus = ContractStatus.queued
    def _validate(self, hints):
        issues = super()._validate(hints)
        try:
            parsed = datetime.fromisoformat(self.deadline.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                issues.append(ValidationIssue("deadline", "timezone", "deadline must include timezone"))
        except (AttributeError, ValueError):
            issues.append(ValidationIssue("deadline", "timestamp", "deadline must be RFC3339"))
        if not self.idempotency_key.strip():
            issues.append(ValidationIssue("idempotency_key", "required", "idempotency key is required"))
        return issues


@dataclass(frozen=True)
class WorkPacket(Contract):
    packet_id: str; task_id: str; team_id: str; source_worker_id: str; destination_stage: str; fact_refs: tuple[str, ...]; evidence_refs: tuple[str, ...]; artifact_refs: tuple[str, ...]; checks: dict[str, bool]; unresolved_questions: tuple[str, ...]; proposed_next_result: str; clearance: Clearance; taint: Taint; packet_hash: str
    def _validate(self, hints):
        issues = super()._validate(hints)
        if not self.fact_refs and not self.evidence_refs:
            issues.append(ValidationIssue("evidence_refs", "provenance", "work packet must carry fact or evidence references"))
        if any(type(value) is not bool for value in self.checks.values()):
            issues.append(ValidationIssue("checks", "type", "check results must be boolean"))
        if self.taint == Taint.clean and (self.fact_refs or self.evidence_refs):
            issues.append(ValidationIssue("taint", "provenance", "packet carrying worker evidence cannot silently become clean"))
        if self.packet_hash != work_packet_hash(self):
            issues.append(ValidationIssue("packet_hash", "integrity", "packet hash does not match canonical packet content"))
        return issues


def work_packet_hash(packet: Any) -> str:
    """Return the canonical SHA-256 hash of a packet without its hash field."""

    payload = packet.to_dict() if isinstance(packet, Contract) else {
        "schema_version": SCHEMA_VERSION,
        "compatibility_id": COMPATIBILITY_ID,
        **dict(packet),
    }
    payload.pop("packet_hash", None)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class WorkerResult(Contract):
    result_id: str; assignment_id: str; task_id: str; status: ContractStatus; output: Any = None; packet_ref: str | None = None; failure_code: str | None = None; retryable: bool = False; completed_at: str = field(default_factory=_now)
    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.status == ContractStatus.verified:
            issues.append(ValidationIssue("status", "authority", "workers cannot mark results verified"))
        if self.status == ContractStatus.failed and not self.failure_code:
            issues.append(ValidationIssue("failure_code", "required", "failed results require a failure code"))
        if self.status in {ContractStatus.accepted, ContractStatus.proposed, ContractStatus.needs_review} and self.output is None and not self.packet_ref:
            issues.append(ValidationIssue("output", "required", "result requires output or packet reference"))
        if isinstance(self.output, dict) and any(key in self.output for key in ("complete", "completion", "authority_decision")):
            issues.append(ValidationIssue("output", "authority", "worker results cannot mark completion or grant authority"))
        return issues


@dataclass(frozen=True)
class ResourceReservation(Contract):
    """Immutable per-worker reservation recorded in an authoritative plan.

    The legacy ``TeamResourcePlan.reservations`` mapping remains available for
    compatibility with the M5.2 fixtures.  M4.2 plans additionally carry this
    typed record so scheduling metadata cannot be lost at the plan boundary.
    """

    worker_id: str
    role: str
    capability: str
    model_target_id: str
    qualification_id: str
    gpu_indices: tuple[int, ...]
    vram_reserved_bytes: int
    cpu_reserved_millicores: int
    ram_reserved_bytes: int
    scratch_reserved_bytes: int
    context_tokens_reserved: int
    kv_cache_reserved_bytes: int
    residency: str
    slots_reserved: int = 1
    start_deadline: str | None = None
    execution_deadline: str | None = None

    def _validate(self, hints):
        issues = super()._validate(hints)
        if not self.role.strip():
            issues.append(ValidationIssue("role", "required", "worker role is required"))
        if not self.capability.strip():
            issues.append(ValidationIssue("capability", "required", "worker capability is required"))
        if self.residency not in {"resident", "load_on_demand", "evictable"}:
            issues.append(ValidationIssue("residency", "enum", "invalid model residency request"))
        for name in (
            "vram_reserved_bytes", "cpu_reserved_millicores", "ram_reserved_bytes",
            "scratch_reserved_bytes", "context_tokens_reserved", "kv_cache_reserved_bytes",
            "slots_reserved",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                issues.append(ValidationIssue(name, "resource", "must be a non-negative integer"))
        if type(self.slots_reserved) is int and self.slots_reserved < 1:
            issues.append(ValidationIssue("slots_reserved", "resource", "at least one slot is required"))
        if any(type(index) is not int or index < 0 for index in self.gpu_indices):
            issues.append(ValidationIssue("gpu_indices", "resource", "GPU indices must be non-negative integers"))
        if not any(getattr(self, name) > 0 for name in (
            "vram_reserved_bytes", "cpu_reserved_millicores", "ram_reserved_bytes",
            "scratch_reserved_bytes", "context_tokens_reserved", "kv_cache_reserved_bytes",
        )):
            issues.append(ValidationIssue("reservation", "resource", "reservation must request at least one resource"))
        for name in ("start_deadline", "execution_deadline"):
            value = getattr(self, name)
            if value is None:
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    issues.append(ValidationIssue(name, "timezone", "deadline must include timezone"))
            except (AttributeError, ValueError):
                issues.append(ValidationIssue(name, "timestamp", "deadline must be RFC3339"))
        return issues


class LeaseStatus(str, Enum):
    requested = "requested"
    granted = "granted"
    active = "active"
    released = "released"
    expired = "expired"
    cancelled = "cancelled"
    revoked = "revoked"
    failed = "failed"


class BarrierStatus(str, Enum):
    waiting = "waiting"
    completed = "completed"
    missing = "missing"
    conflicting = "conflicting"
    timed_out = "timed_out"
    cancelled = "cancelled"
    needs_review = "needs_review"


@dataclass(frozen=True)
class ResourceLease(Contract):
    """Immutable, identity-bound permission to consume one worker reservation."""

    lease_id: str
    task_id: str
    team_id: str
    plan_id: str
    worker_id: str
    role: str
    capability: str
    hardware_profile_ref: str
    measurement_id: str
    reservation: tuple[tuple[str, int], ...]
    residency: str
    clearance: Clearance
    taint: Taint
    policy_version_hash: str
    idempotency_key: str
    issued_at: str
    expires_at: str
    status: LeaseStatus
    model_target_id: str | None = None
    qualification_id: str | None = None
    version: int = 1
    provenance_refs: tuple[str, ...] = ()
    gpu_indices: tuple[int, ...] = ()

    def _validate(self, hints):
        issues = super()._validate(hints)
        allowed_dimensions = {
            "vram_bytes", "ram_bytes", "cpu_millicores", "kv_cache_bytes",
            "context_tokens", "scratch_bytes", "slots",
        }
        seen: set[str] = set()
        total = 0
        for item in self.reservation:
            if not isinstance(item, tuple) or len(item) != 2:
                issues.append(ValidationIssue("reservation", "type", "reservation entries must be name/value pairs"))
                continue
            name, value = item
            if name not in allowed_dimensions:
                issues.append(ValidationIssue("reservation", "enum", f"unknown resource dimension: {name!r}"))
            if name in seen:
                issues.append(ValidationIssue("reservation", "duplicate", f"duplicate resource dimension: {name!r}"))
            seen.add(name)
            if type(value) is not int or value < 0:
                issues.append(ValidationIssue(f"reservation.{name}", "resource", "must be a non-negative integer"))
            elif value > 0:
                total += value
        if total == 0:
            issues.append(ValidationIssue("reservation", "resource", "lease must carry a non-zero reservation"))
        if self.residency not in {"resident", "load_on_demand", "evictable"}:
            issues.append(ValidationIssue("residency", "enum", "invalid model residency request"))
        if any(type(index) is not int or index < 0 for index in self.gpu_indices):
            issues.append(ValidationIssue("gpu_indices", "resource", "GPU indices must be non-negative integers"))
        if self.taint != Taint.clean:
            issues.append(ValidationIssue("taint", "security", "resource leases require policy-cleared task input"))
        if not self.policy_version_hash.strip():
            issues.append(ValidationIssue("policy_version_hash", "required", "lease policy identity is required"))
        if not self.idempotency_key.strip():
            issues.append(ValidationIssue("idempotency_key", "required", "lease idempotency key is required"))
        if type(self.version) is not int or self.version < 1:
            issues.append(ValidationIssue("version", "range", "lease version must be positive"))
        try:
            issued = datetime.fromisoformat(self.issued_at.replace("Z", "+00:00"))
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            if issued.tzinfo is None or expires.tzinfo is None:
                issues.append(ValidationIssue("issued_at", "timezone", "lease timestamps must include timezone"))
            elif expires <= issued:
                issues.append(ValidationIssue("expires_at", "range", "lease must expire after it is issued"))
        except (AttributeError, ValueError):
            issues.append(ValidationIssue("issued_at", "timestamp", "lease timestamps must be RFC3339"))
        return issues


@dataclass(frozen=True)
class HandoffSubmission(Contract):
    """Immutable request to transfer one worker packet to one assignment."""

    handoff_id: str
    task_id: str
    team_id: str
    source_assignment_id: str
    source_worker_id: str
    destination_assignment_id: str
    destination_stage: str
    packet: WorkPacket
    packet_hash: str
    barrier_id: str
    barrier_version: int
    source_lease_id: str
    plan_version: str
    policy_version_hash: str
    clearance: Clearance
    taint: Taint
    submitted_at: str
    deadline: str
    idempotency_key: str
    artifact_hashes: tuple[tuple[str, str], ...] = ()
    attempt: int = 1

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.packet.task_id != self.task_id or self.packet.team_id != self.team_id:
            issues.append(ValidationIssue("packet", "identity", "packet task and team must match handoff"))
        if self.packet.source_worker_id != self.source_worker_id:
            issues.append(ValidationIssue("source_worker_id", "identity", "handoff source does not match packet source"))
        if self.packet.destination_stage != self.destination_stage:
            issues.append(ValidationIssue("destination_stage", "identity", "handoff destination stage does not match packet"))
        if self.packet_hash != self.packet.packet_hash:
            issues.append(ValidationIssue("packet_hash", "integrity", "handoff packet hash does not match packet"))
        if self.barrier_version < 1:
            issues.append(ValidationIssue("barrier_version", "range", "barrier version must be positive"))
        if self.attempt < 1:
            issues.append(ValidationIssue("attempt", "range", "handoff attempt must be positive"))
        if not self.source_lease_id.strip() or not self.plan_version.strip() or not self.policy_version_hash.strip():
            issues.append(ValidationIssue("identity", "required", "lease, plan, and policy identities are required"))
        if not self.idempotency_key.strip():
            issues.append(ValidationIssue("idempotency_key", "required", "handoff idempotency key is required"))
        for name in ("submitted_at", "deadline"):
            try:
                parsed = datetime.fromisoformat(getattr(self, name).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    issues.append(ValidationIssue(name, "timezone", "timestamp must include timezone"))
            except (AttributeError, ValueError):
                issues.append(ValidationIssue(name, "timestamp", "timestamp must be RFC3339"))
        return issues


@dataclass(frozen=True)
class JoinBarrier(Contract):
    """Versioned orchestrator-owned synchronization state."""

    barrier_id: str
    task_id: str
    team_id: str
    destination_assignment_id: str
    destination_stage: str
    plan_version: str
    barrier_version: int
    required_predecessor_assignment_ids: tuple[str, ...]
    accepted_handoff_ids: tuple[str, ...]
    accepted_packet_hashes: tuple[tuple[str, str], ...]
    missing_assignment_ids: tuple[str, ...]
    conflict_packet_refs: tuple[tuple[str, str], ...]
    deadline: str
    join_policy: str
    status: BarrierStatus
    clearance: Clearance
    taint: Taint
    policy_version_hash: str
    idempotency_key: str
    created_at: str
    unresolved_questions: tuple[str, ...] = ()
    lease_refs: tuple[str, ...] = ()

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.barrier_version < 1:
            issues.append(ValidationIssue("barrier_version", "range", "barrier version must be positive"))
        if not self.required_predecessor_assignment_ids:
            issues.append(ValidationIssue("required_predecessor_assignment_ids", "required", "join barrier needs a predecessor set"))
        if self.join_policy not in {"join_all"}:
            issues.append(ValidationIssue("join_policy", "enum", "only join_all is supported by this slice"))
        if self.status not in set(BarrierStatus):
            issues.append(ValidationIssue("status", "enum", "invalid barrier status"))
        if not self.plan_version.strip() or not self.policy_version_hash.strip() or not self.idempotency_key.strip():
            issues.append(ValidationIssue("identity", "required", "barrier plan, policy, and idempotency identities are required"))
        for name in ("deadline", "created_at"):
            try:
                parsed = datetime.fromisoformat(getattr(self, name).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    issues.append(ValidationIssue(name, "timezone", "timestamp must include timezone"))
            except (AttributeError, ValueError):
                issues.append(ValidationIssue(name, "timestamp", "timestamp must be RFC3339"))
        required = set(self.required_predecessor_assignment_ids)
        accepted_sources = {source for source, _ in self.accepted_packet_hashes}
        if len(required) != len(self.required_predecessor_assignment_ids):
            issues.append(ValidationIssue("required_predecessor_assignment_ids", "duplicate", "predecessor IDs must be unique"))
        if len(set(self.accepted_handoff_ids)) != len(self.accepted_handoff_ids):
            issues.append(ValidationIssue("accepted_handoff_ids", "duplicate", "accepted handoff IDs must be unique"))
        if len(accepted_sources) != len(self.accepted_packet_hashes):
            issues.append(ValidationIssue("accepted_packet_hashes", "duplicate", "accepted packet sources must be unique"))
        if not set(self.missing_assignment_ids).issubset(required):
            issues.append(ValidationIssue("missing_assignment_ids", "consistency", "missing set must be a subset of required predecessors"))
        if set(accepted_sources) & set(self.missing_assignment_ids):
            issues.append(ValidationIssue("missing_assignment_ids", "consistency", "a predecessor cannot be both accepted and missing"))
        if accepted_sources | set(self.missing_assignment_ids) != required:
            issues.append(ValidationIssue("accepted_packet_hashes", "consistency", "accepted and missing predecessors must cover the required set"))
        if self.status == BarrierStatus.completed and (accepted_sources != required or self.missing_assignment_ids or self.unresolved_questions):
            issues.append(ValidationIssue("status", "consistency", "completed barrier cannot have missing or unresolved work"))
        if accepted_sources and not set(accepted_sources).issubset(required):
            issues.append(ValidationIssue("accepted_packet_hashes", "consistency", "accepted packet sources must be required predecessors"))
        return issues


@dataclass(frozen=True)
class CompletionRecord(Contract):
    completion_id: str; task_id: str; final_state: str; required_evidence_refs: tuple[str, ...]; verification_refs: tuple[str, ...]; artifact_hashes: tuple[str, ...]; human_review_ref: str | None; policy_version_hash: str; pack_version_hash: str; model_identities: tuple[str, ...]; hardware_identity: str; completed_at: str = field(default_factory=_now)
    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.final_state not in {"complete", "needs_review", "blocked", "failed", "cancelled"}:
            issues.append(ValidationIssue("final_state", "enum", "invalid completion state"))
        if self.final_state == "complete":
            if not self.required_evidence_refs:
                issues.append(ValidationIssue("required_evidence_refs", "completion_gate", "completion requires evidence"))
            if not self.verification_refs:
                issues.append(ValidationIssue("verification_refs", "completion_gate", "completion requires verification"))
            if not self.human_review_ref:
                issues.append(ValidationIssue("human_review_ref", "completion_gate", "completion requires human review reference"))
        return issues


@dataclass(frozen=True)
class StageSignals(Contract):
    """Deterministic progress signals supplied by the orchestrator."""

    exploration: bool = False
    error_severity: str = "none"
    spinning: bool = False
    recent_production: bool = False
    test_result: str = "not_run"
    context_pressure: str = "normal"
    capable_route_requested: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StageSignals":
        # Older orchestrator envelopes used the derived property name as an
        # explicit input signal.  Accept that representation at the boundary
        # and normalize it to a typed field; do not leave a raw compatibility
        # key in the contract or silently discard an escalation request.
        value = dict(payload)
        if "requires_capable_route" in value and "capable_route_requested" not in value:
            value["capable_route_requested"] = value.pop("requires_capable_route")
        return super().from_dict(value)  # type: ignore[return-value]

    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.error_severity not in {"none", "recoverable", "critical"}:
            issues.append(ValidationIssue("error_severity", "enum", "invalid error severity"))
        if self.test_result not in {"not_run", "passed", "failed"}:
            issues.append(ValidationIssue("test_result", "enum", "invalid test result"))
        if self.context_pressure not in {"normal", "elevated", "critical"}:
            issues.append(ValidationIssue("context_pressure", "enum", "invalid context pressure"))
        if type(self.capable_route_requested) is not bool:
            issues.append(ValidationIssue("capable_route_requested", "type", "must be a boolean"))
        return issues

    @property
    def requires_capable_route(self) -> bool:
        return (
            self.capable_route_requested
            or
            self.exploration
            or self.spinning
            or self.error_severity in {"recoverable", "critical"}
            or self.test_result == "failed"
            or self.context_pressure == "critical"
        )

    @property
    def is_settled_mechanical(self) -> bool:
        return (
            self.recent_production
            and self.test_result == "passed"
            and not self.exploration
            and not self.spinning
            and self.error_severity == "none"
            and self.context_pressure == "normal"
        )


@dataclass(frozen=True)
class ModelCallRequest(Contract):
    request_id: str; task_id: str; team_id: str | None; worker_id: str | None; task_kind: str; modality: str; required_capability: str; evidence_summary: tuple[str, ...]; clearance: Clearance; action_risk: str; resource_budget: dict[str, int]; attempt: int; idempotency_key: str; timeout_ms: int
    role: str = ""
    resource_lease_id: str = ""
    stage: str = "default"
    previous_verification_status: str = "not_run"
    stage_signals: StageSignals = field(default_factory=StageSignals)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ModelCallRequest":
        value = dict(payload)
        signals = value.get("stage_signals", StageSignals())
        value["stage_signals"] = signals if isinstance(signals, StageSignals) else StageSignals.from_dict(signals)
        return super().from_dict(value)  # type: ignore[return-value]

    def _validate(self, hints):
        issues = super()._validate(hints)
        if type(self.timeout_ms) is not int or self.timeout_ms <= 0 or self.timeout_ms > 86_400_000: issues.append(ValidationIssue("timeout_ms", "range", "must be 1..86400000"))
        if type(self.attempt) is not int or self.attempt < 1: issues.append(ValidationIssue("attempt", "range", "must be >= 1"))
        if not self.role.strip(): issues.append(ValidationIssue("role", "required", "worker role is required"))
        if not self.resource_lease_id.strip(): issues.append(ValidationIssue("resource_lease_id", "required", "resource lease is required"))
        if not self.required_capability.strip(): issues.append(ValidationIssue("required_capability", "required", "model capability is required"))
        if not self.stage.strip(): issues.append(ValidationIssue("stage", "required", "routing stage is required"))
        if self.previous_verification_status not in {"not_run", "passed", "failed", "needs_review"}:
            issues.append(ValidationIssue("previous_verification_status", "enum", "invalid previous verification status"))
        if isinstance(self.resource_budget, dict) and any(type(value) is not int or value < 0 for value in self.resource_budget.values()): issues.append(ValidationIssue("resource_budget", "resource", "budget values must be non-negative integers"))
        return issues


@dataclass(frozen=True)
class RoutingDecision(Contract):
    decision_id: str; request_id: str; eligible_targets: tuple[str, ...]; selected_target: str | None; policy_version_hash: str; decision_source: str; rule_or_threshold: str; qualification_certificate: str; session_affinity: str; fallback_target: str | None; resource_admission: str; status: ContractStatus; reason: str
    stage: str = "default"
    stage_signals: StageSignals = field(default_factory=StageSignals)
    routing_mode: str = "standard"
    escalation_sticky: bool = False
    attempt: int = 1
    task_id: str = "unknown"
    team_id: str = "unknown"
    worker_id: str = "unknown"
    resource_lease_id: str = "unknown"
    hardware_profile_ref: str = "unknown"
    selected_artifact_digest: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoutingDecision":
        value = dict(payload)
        signals = value.get("stage_signals", StageSignals())
        value["stage_signals"] = signals if isinstance(signals, StageSignals) else StageSignals.from_dict(signals)
        return super().from_dict(value)  # type: ignore[return-value]

    def _validate(self, hints):
        issues = super()._validate(hints)
        if not self.eligible_targets and self.status == ContractStatus.accepted:
            issues.append(ValidationIssue("eligible_targets", "required", "accepted routing requires an eligible target set"))
        if not self.reason.strip():
            issues.append(ValidationIssue("reason", "required", "routing must explain its outcome"))
        if self.status == ContractStatus.accepted and (not self.selected_target or not self.qualification_certificate or self.resource_admission != "admitted"):
            issues.append(ValidationIssue("selected_target", "admission", "accepted routing requires target, qualification, and admitted resources"))
        if self.resource_admission not in {"admitted", "queued", "rejected", "needs_review"}:
            issues.append(ValidationIssue("resource_admission", "enum", "invalid resource admission"))
        if not self.stage.strip():
            issues.append(ValidationIssue("stage", "required", "routing stage is required"))
        if self.routing_mode not in {"standard", "capable", "efficient", "escalated_sticky"}:
            issues.append(ValidationIssue("routing_mode", "enum", "invalid routing mode"))
        if type(self.attempt) is not int or self.attempt < 1:
            issues.append(ValidationIssue("attempt", "range", "routing attempt must be >= 1"))
        return issues


@dataclass(frozen=True)
class TeamResourcePlan(Contract):
    team_id: str; hardware_profile_ref: str; worker_capabilities: dict[str, str]; reservations: dict[str, dict[str, int]]; concurrency_ceiling: int; execution_mode: str; priority: str; verifier_capacity: int; admission: str; reason: str
    task_id: str = ""
    plan_id: str = ""
    hardware_profile_id: str = ""
    plan_version: str = "1"
    created_at: str = field(default_factory=_now)
    requested_mode: str = "auto"
    admitted_mode: str = ""
    admission_reason: str = ""
    dependency_graph: dict[str, tuple[str, ...]] = field(default_factory=dict)
    scheduling: dict[str, str] = field(default_factory=dict)
    safety_invariants: dict[str, bool | str] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    residency_requests: dict[str, str] = field(default_factory=dict)
    reservation_records: tuple[ResourceReservation, ...] = ()
    def _validate(self, hints):
        issues = super()._validate(hints)
        if not self.task_id.strip(): issues.append(ValidationIssue("task_id", "required", "resource plan must identify its task"))
        if self.concurrency_ceiling < 1: issues.append(ValidationIssue("concurrency_ceiling", "range", "must be at least 1"))
        if type(self.verifier_capacity) is not int or self.verifier_capacity < 1: issues.append(ValidationIssue("verifier_capacity", "safety", "at least one verifier reservation is required"))
        if self.execution_mode not in {"parallel", "pipelined", "serial_virtual_team"}: issues.append(ValidationIssue("execution_mode", "enum", "invalid execution mode"))
        if self.admission not in {"admitted", "queued", "degraded_needs_review", "rejected", "stopped"}: issues.append(ValidationIssue("admission", "enum", "invalid admission state"))
        if isinstance(self.reservations, dict):
            for worker, reservation in self.reservations.items():
                if not isinstance(reservation, dict) or any(type(value) is not int or value < 0 for value in reservation.values()):
                    issues.append(ValidationIssue(f"reservations.{worker}", "resource", "reservations must contain non-negative integer values"))
        if self.requested_mode not in {"auto", "parallel", "pipelined", "serial_virtual_team"}:
            issues.append(ValidationIssue("requested_mode", "enum", "invalid requested execution mode"))
        if self.plan_id:
            if not self.hardware_profile_id.strip() or self.hardware_profile_id != self.hardware_profile_ref:
                issues.append(ValidationIssue("hardware_profile_id", "identity", "authoritative plan profile IDs must match"))
            if not self.plan_version.strip():
                issues.append(ValidationIssue("plan_version", "required", "authoritative plan version is required"))
            if not self.admission_reason.strip():
                issues.append(ValidationIssue("admission_reason", "required", "authoritative plan reason is required"))
            valid_admitted_modes = {"parallel", "pipelined", "serial_virtual_team", "queued", "stopped"}
            if self.admitted_mode not in valid_admitted_modes:
                issues.append(ValidationIssue("admitted_mode", "enum", "invalid admitted execution mode"))
            if self.admission in {"admitted", "degraded_needs_review"} and self.admitted_mode != self.execution_mode:
                issues.append(ValidationIssue("admitted_mode", "consistency", "admitted mode must match execution mode"))
            if self.admission == "queued" and self.admitted_mode != "queued":
                issues.append(ValidationIssue("admitted_mode", "consistency", "queued plans must declare queued mode"))
            if self.admission in {"rejected", "stopped"} and self.admitted_mode != "stopped":
                issues.append(ValidationIssue("admitted_mode", "consistency", "stopped plans must declare stopped mode"))
            required_safety = {"verifier_required", "review_required", "qualified_targets_only", "provenance_required"}
            if not required_safety.issubset(self.safety_invariants):
                issues.append(ValidationIssue("safety_invariants", "safety", "authoritative plan must declare all safety invariants"))
            elif any(self.safety_invariants[name] is not True for name in required_safety):
                issues.append(ValidationIssue("safety_invariants", "safety", "authoritative plan safety invariants cannot be weakened"))
            record_workers = {record.worker_id for record in self.reservation_records}
            if record_workers and record_workers != set(self.reservations):
                issues.append(ValidationIssue("reservation_records", "consistency", "typed records must match reservation workers"))
        return issues


# Valid execution modes for HardwareProfile.supported_execution_modes
_EXECUTION_MODES = {"parallel", "pipelined", "serial_virtual_team"}

# Valid priority classes for AdmissionRequest and TeamResourcePlan
PRIORITY_CLASSES = {
    "interactive_high_consequence",  # highest — safety-critical inspection work
    "interactive_normal",            # normal interactive user tasks
    "scheduled_domain_work",         # scheduled batch domain processing
    "background_ingestion",          # document ingestion in the background
    "maintenance",                   # lowest — maintenance and housekeeping
}


@dataclass(frozen=True)
class HardwareProfile(Contract):
    """Signed, measured hardware capability record for a local deployment node.

    Required fields capture the minimal hardware identity needed for admission
    and routing decisions.  Extended fields (supported_execution_modes,
    network_check_id, sandbox_runtime, benchmark_result_ref) are optional but
    strongly recommended for production deployments.
    """
    profile_id: str
    gpu_model: str
    gpu_count: int
    vram_bytes: int
    driver_version: str
    accelerator_runtime: str
    cpu_model: str
    cpu_cores: int
    ram_bytes: int
    storage_bytes: int
    scratch_bytes: int
    model_context_tokens: int
    kv_cache_bytes: int
    safe_parallel_slots: int
    egress_policy: str
    measurement_hash: str
    # Extended M5.2 fields — default to safe/empty values so existing callers are unaffected
    supported_execution_modes: tuple[str, ...] = ("serial_virtual_team",)
    network_check_id: str = ""          # ledger event ID of the egress-denial evidence
    sandbox_runtime: str = ""           # e.g. "firejail-0.9.72" or "none"
    benchmark_result_ref: str = ""      # path to benchmarks/model_hardware_results.yaml entry

    def _validate(self, hints):
        issues = super()._validate(hints)
        for name in ("gpu_model", "driver_version", "accelerator_runtime", "cpu_model", "egress_policy", "measurement_hash"):
            if not getattr(self, name).strip(): issues.append(ValidationIssue(name, "required", f"{name} is required"))
        for name in ("gpu_count", "vram_bytes", "cpu_cores", "ram_bytes", "storage_bytes", "scratch_bytes", "model_context_tokens", "kv_cache_bytes", "safe_parallel_slots"):
            value = getattr(self, name)
            if type(value) is not int or value < 0: issues.append(ValidationIssue(name, "resource", "must be a non-negative integer"))
        if type(self.gpu_count) is int and self.gpu_count < 1: issues.append(ValidationIssue("gpu_count", "resource", "at least one GPU is required"))
        if type(self.vram_bytes) is int and self.vram_bytes == 0: issues.append(ValidationIssue("vram_bytes", "resource", "VRAM capacity is required"))
        if type(self.safe_parallel_slots) is int and self.safe_parallel_slots < 1: issues.append(ValidationIssue("safe_parallel_slots", "resource", "at least one execution slot is required"))
        for mode in self.supported_execution_modes:
            if mode not in _EXECUTION_MODES:
                issues.append(ValidationIssue("supported_execution_modes", "enum", f"unknown execution mode: {mode!r}"))
        if not self.supported_execution_modes:
            issues.append(ValidationIssue("supported_execution_modes", "required", "at least one execution mode is required"))
        return issues


@dataclass(frozen=True)
class ToolAction(Contract):
    action_id: str; task_id: str; worker_id: str; tool_name: str; arguments: dict[str, Any]; path_scope: tuple[str, ...]; clearance: Clearance; taint: Taint; risk_class: str; timeout_ms: int; idempotency_key: str; status: ContractStatus = ContractStatus.proposed
    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.taint != Taint.clean: issues.append(ValidationIssue("taint", "security", "tool actions require clean, policy-cleared inputs"))
        if type(self.timeout_ms) is not int or self.timeout_ms <= 0: issues.append(ValidationIssue("timeout_ms", "range", "must be positive"))
        if not self.path_scope: issues.append(ValidationIssue("path_scope", "security", "tool path scope is required"))
        return issues


@dataclass(frozen=True)
class LedgerEventEnvelope(Contract):
    event_id: str; event_type: str; task_id: str; parent_event_id: str | None; sequence: int; occurred_at: str; actor_id: str; actor_type: str; clearance: Clearance; payload_contract: str; payload_version: str; payload_hash: str; idempotency_key: str; previous_event_hash: str | None; event_hash: str; immutable: bool = True; payload: dict[str, Any] = field(default_factory=dict)
    def _validate(self, hints):
        issues = super()._validate(hints)
        if type(self.sequence) is not int or self.sequence < 0: issues.append(ValidationIssue("sequence", "range", "must be a non-negative integer"))
        if not self.immutable: issues.append(ValidationIssue("immutable", "ledger", "ledger events are immutable"))
        if not re.fullmatch(r"[0-9a-f]{64}", self.event_hash): issues.append(ValidationIssue("event_hash", "hash", "must be a SHA-256 hex digest"))
        if not re.fullmatch(r"[0-9a-f]{64}", self.payload_hash): issues.append(ValidationIssue("payload_hash", "hash", "must be a SHA-256 hex digest"))
        if self.event_type not in LEDGER_EVENT_TYPES: issues.append(ValidationIssue("event_type", "event", "unknown ledger event type"))
        return issues
