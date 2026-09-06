from __future__ import annotations

import hashlib
import json
import re
import types
from dataclasses import MISSING, dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Union, get_args, get_origin, get_type_hints

from .errors import ContractValidationError, ValidationIssue

SCHEMA_VERSION = "1.0"
COMPATIBILITY_ID = "airbench-core-contracts"
_ID = re.compile(r"^[a-z][a-z0-9._:-]{0,127}$")


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
class TaskEnvelope(Contract):
    task_id: str; principal_id: str; clearance: Clearance; request: str; domain_pack_ref: str; risk_class: str; autonomy_ceiling: str; allowed_evidence_scope: tuple[str, ...]; permitted_worker_capabilities: tuple[str, ...]; permitted_tools: tuple[str, ...]; output_contract: str; verification_criteria: tuple[str, ...]; resource_budget: dict[str, int]; state: str = "created"; parent_task_id: str | None = None; created_at: str = field(default_factory=_now)
    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.state not in {"created", "authorized", "planned", "executing", "awaiting_check", "awaiting_review", "rendering", "deliverable_verified", "complete", "needs_review", "blocked", "failed", "cancelled"}:
            issues.append(ValidationIssue("state", "enum", "invalid task state"))
        if not self.request.strip():
            issues.append(ValidationIssue("request", "required", "request must not be empty"))
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
        if not self.completion_criteria:
            issues.append(ValidationIssue("completion_criteria", "required", "completion criteria are required"))
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
        return issues


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
class ModelCallRequest(Contract):
    request_id: str; task_id: str; team_id: str | None; worker_id: str | None; task_kind: str; modality: str; required_capability: str; evidence_summary: tuple[str, ...]; clearance: Clearance; action_risk: str; resource_budget: dict[str, int]; attempt: int; idempotency_key: str; timeout_ms: int
    role: str = ""
    resource_lease_id: str = ""
    def _validate(self, hints):
        issues = super()._validate(hints)
        if type(self.timeout_ms) is not int or self.timeout_ms <= 0 or self.timeout_ms > 86_400_000: issues.append(ValidationIssue("timeout_ms", "range", "must be 1..86400000"))
        if type(self.attempt) is not int or self.attempt < 1: issues.append(ValidationIssue("attempt", "range", "must be >= 1"))
        if not self.role.strip(): issues.append(ValidationIssue("role", "required", "worker role is required"))
        if not self.resource_lease_id.strip(): issues.append(ValidationIssue("resource_lease_id", "required", "resource lease is required"))
        if not self.required_capability.strip(): issues.append(ValidationIssue("required_capability", "required", "model capability is required"))
        if isinstance(self.resource_budget, dict) and any(type(value) is not int or value < 0 for value in self.resource_budget.values()): issues.append(ValidationIssue("resource_budget", "resource", "budget values must be non-negative integers"))
        return issues


@dataclass(frozen=True)
class RoutingDecision(Contract):
    decision_id: str; request_id: str; eligible_targets: tuple[str, ...]; selected_target: str | None; policy_version_hash: str; decision_source: str; rule_or_threshold: str; qualification_certificate: str; session_affinity: str; fallback_target: str | None; resource_admission: str; status: ContractStatus; reason: str
    def _validate(self, hints):
        issues = super()._validate(hints)
        if not self.eligible_targets:
            issues.append(ValidationIssue("eligible_targets", "required", "routing requires an eligible target set"))
        if self.status == ContractStatus.accepted and (not self.selected_target or not self.qualification_certificate or self.resource_admission != "admitted"):
            issues.append(ValidationIssue("selected_target", "admission", "accepted routing requires target, qualification, and admitted resources"))
        if self.resource_admission not in {"admitted", "queued", "rejected", "needs_review"}:
            issues.append(ValidationIssue("resource_admission", "enum", "invalid resource admission"))
        return issues


@dataclass(frozen=True)
class TeamResourcePlan(Contract):
    team_id: str; hardware_profile_ref: str; worker_capabilities: dict[str, str]; reservations: dict[str, dict[str, int]]; concurrency_ceiling: int; execution_mode: str; priority: str; verifier_capacity: int; admission: str; reason: str
    task_id: str = ""
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
        return issues


@dataclass(frozen=True)
class HardwareProfile(Contract):
    profile_id: str; gpu_model: str; gpu_count: int; vram_bytes: int; driver_version: str; accelerator_runtime: str; cpu_model: str; cpu_cores: int; ram_bytes: int; storage_bytes: int; scratch_bytes: int; model_context_tokens: int; kv_cache_bytes: int; safe_parallel_slots: int; egress_policy: str; measurement_hash: str
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
    event_id: str; event_type: str; task_id: str; parent_event_id: str | None; sequence: int; occurred_at: str; actor_id: str; actor_type: str; clearance: Clearance; payload_contract: str; payload_version: str; payload_hash: str; idempotency_key: str; previous_event_hash: str | None; event_hash: str; immutable: bool = True
    def _validate(self, hints):
        issues = super()._validate(hints)
        if self.sequence < 0: issues.append(ValidationIssue("sequence", "range", "must be non-negative"))
        if not self.immutable: issues.append(ValidationIssue("immutable", "ledger", "ledger events are immutable"))
        if not re.fullmatch(r"[0-9a-f]{64}", self.event_hash): issues.append(ValidationIssue("event_hash", "hash", "must be a SHA-256 hex digest"))
        return issues
