"""Scoped worker assignments and isolated worker execution contexts.

This module is deliberately a runtime boundary around the shared contracts.
It does not create model targets, run a worker loop, parse files, or mutate
orchestrator state.  The orchestrator creates and commits assignments; this
module gives one stateless worker call a bounded view of that assignment.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from contracts import (
    Clearance,
    ContractStatus,
    ModelCallRequest,
    TaskEnvelope,
    Taint,
    WorkerAssignment,
)
from contracts.errors import ContractValidationError, ValidationIssue
from contracts.ids import idempotency_key as make_idempotency_key
from contracts.ids import stable_id
from airbench.tool_gateway import CapabilityScope, issue_capability_scope


WORKER_CONTEXT_SCHEMA_VERSION = "1.0"


class WorkerContextError(RuntimeError):
    """Base error for fail-closed worker context operations."""


class AssignmentValidationError(WorkerContextError):
    """The assignment is structurally valid but outside the task envelope."""


class ScopeViolation(WorkerContextError):
    """The worker attempted to access data, tools, or paths outside its scope."""


class WorkerDeadlineExceeded(ScopeViolation):
    """The worker attempted an operation after its immutable deadline."""


class EvidenceNotFound(ScopeViolation):
    """A permitted evidence reference was not available from the provider."""


def _parse_deadline(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise AssignmentValidationError("worker deadline is not RFC3339") from exc
    if parsed.tzinfo is None:
        raise AssignmentValidationError("worker deadline must include a timezone")
    return parsed.astimezone(timezone.utc)


def _now_utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must include a timezone")
    return current.astimezone(timezone.utc)


_CLEARANCE_RANK = {
    Clearance.public: 0,
    Clearance.internal: 1,
    Clearance.restricted: 2,
    Clearance.secret: 3,
}
_TAINT_RANK = {
    Taint.clean: 0,
    Taint.untrusted: 1,
    Taint.contaminated: 2,
}


def _as_clearance(value: Clearance | str) -> Clearance:
    try:
        return value if isinstance(value, Clearance) else Clearance(value)
    except ValueError as exc:
        raise AssignmentValidationError("invalid worker clearance") from exc


def _as_taint(value: Taint | str) -> Taint:
    try:
        return value if isinstance(value, Taint) else Taint(value)
    except ValueError as exc:
        raise AssignmentValidationError("invalid worker taint") from exc


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssignmentValidationError(f"{field_name} is required")
    return value


def _validate_task_scope(task: TaskEnvelope, assignment: WorkerAssignment) -> None:
    """Validate authority narrowing before a context or assignment is used."""

    issues: list[ValidationIssue] = []
    if assignment.task_id != task.task_id:
        issues.append(ValidationIssue("task_id", "identity", "assignment task does not match task envelope"))
    if not assignment.team_id.strip() or not assignment.worker_id.strip():
        issues.append(ValidationIssue("identity", "required", "team and worker identities are required"))
    if not assignment.role.strip() or not assignment.stage.strip():
        issues.append(ValidationIssue("role", "required", "worker role and stage are required"))
    if assignment.clearance not in _CLEARANCE_RANK or _CLEARANCE_RANK[assignment.clearance] > _CLEARANCE_RANK[task.clearance]:
        issues.append(ValidationIssue("clearance", "authority", "worker clearance cannot exceed task clearance"))
    if not set(assignment.evidence_refs).issubset(set(task.allowed_evidence_scope)):
        issues.append(ValidationIssue("evidence_refs", "authority", "worker evidence scope exceeds task evidence scope"))
    if not set(assignment.allowed_tools).issubset(set(task.permitted_tools)):
        issues.append(ValidationIssue("allowed_tools", "authority", "worker tools exceed task tools"))
    if assignment.capability_requirement not in task.permitted_worker_capabilities:
        issues.append(ValidationIssue("capability_requirement", "authority", "worker capability is not permitted by task"))
    if assignment.evidence_refs and assignment.taint == Taint.clean:
        issues.append(ValidationIssue("taint", "provenance", "evidence-bearing assignments cannot become clean"))
    if not task.risk_class.strip():
        issues.append(ValidationIssue("risk_class", "required", "task risk class is required for capability scoping"))
    if task.deadline is not None:
        task_deadline = _parse_deadline(task.deadline)
        if _parse_deadline(assignment.deadline) > task_deadline:
            issues.append(ValidationIssue("deadline", "authority", "worker deadline cannot exceed task deadline"))
    if issues:
        raise AssignmentValidationError(
            "worker assignment exceeds the task envelope: "
            + ", ".join(issue.path for issue in issues)
        )


@dataclass(frozen=True, slots=True)
class ScopedEvidence:
    """Metadata-only evidence view exposed to one worker.

    The payload is intentionally absent.  The File Intake and retrieval
    layers remain responsible for parsing and serving governed content.  This
    view preserves the provenance labels needed at the worker boundary.
    """

    evidence_ref: str
    source_ref: str
    confidence: float | None
    clearance: Clearance
    taint: Taint
    content_hash: str

    def __post_init__(self) -> None:
        if not self.evidence_ref.strip() or not self.source_ref.strip():
            raise ValueError("evidence and source references are required")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("evidence confidence must be between 0 and 1")
        if not self.content_hash.strip():
            raise ValueError("evidence content hash is required")

    def provenance(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source_ref": self.source_ref,
            "clearance": self.clearance.value,
            "taint": self.taint.value,
            "content_hash": self.content_hash,
        }
        if self.confidence is not None:
            result["confidence"] = self.confidence
        return result


class EvidenceProvider(Protocol):
    """Read-only local provider for already-intaken evidence metadata."""

    def get(self, evidence_ref: str) -> ScopedEvidence | None:
        """Return a governed evidence view, never an executable instruction."""


@dataclass(frozen=True, slots=True)
class WorkerIdentity:
    task_id: str
    team_id: str
    worker_id: str
    assignment_id: str
    role: str
    stage: str

    def to_dict(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "team_id": self.team_id,
            "worker_id": self.worker_id,
            "assignment_id": self.assignment_id,
            "role": self.role,
            "stage": self.stage,
        }


@dataclass(frozen=True, slots=True)
class WorkerContextView:
    """Safe context manifest without raw task text or peer state."""

    schema_version: str
    identity: WorkerIdentity
    evidence_refs: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    clearance: Clearance
    taint: Taint
    deadline: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "identity": self.identity.to_dict(),
            "evidence_refs": list(self.evidence_refs),
            "allowed_tools": list(self.allowed_tools),
            "allowed_paths": list(self.allowed_paths),
            "clearance": self.clearance.value,
            "taint": self.taint.value,
            "deadline": self.deadline,
        }


@dataclass(frozen=True, slots=True)
class WorkerScope:
    """Immutable authority scope for one worker assignment."""

    task_id: str
    team_id: str
    worker_id: str
    assignment_id: str
    evidence_refs: tuple[str, ...]
    clearance: Clearance
    taint: Taint
    scratch_root: Path
    deadline: datetime
    capability_scope: CapabilityScope | None

    def __post_init__(self) -> None:
        if self.deadline.tzinfo is None:
            raise ValueError("worker scope deadline must include a timezone")
        root = self.scratch_root.resolve(strict=False)
        if not root.is_absolute() or root == Path(root.anchor):
            raise ValueError("worker scratch root must be a non-root absolute path")
        object.__setattr__(self, "scratch_root", root)

    @property
    def allowed_paths(self) -> tuple[str, ...]:
        if self.capability_scope is None:
            return (str(self.scratch_root),)
        return self.capability_scope.allowed_paths

    def assert_active(self, now: datetime | None = None) -> datetime:
        current = _now_utc(now)
        if current >= self.deadline.astimezone(timezone.utc):
            raise WorkerDeadlineExceeded("worker deadline has elapsed")
        return current

    def remaining_ms(self, now: datetime | None = None) -> int:
        current = self.assert_active(now)
        return max(1, int((self.deadline.astimezone(timezone.utc) - current).total_seconds() * 1000))

    def allows_evidence(self, evidence_ref: str) -> bool:
        return evidence_ref in self.evidence_refs

    def resolve_scratch_path(self, relative_path: str | Path) -> Path:
        """Resolve a relative path and reject traversal or peer roots."""

        candidate = Path(relative_path)
        if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
            raise ScopeViolation("scratch paths must be relative to the worker root")
        resolved = (self.scratch_root / candidate).resolve(strict=False)
        try:
            resolved.relative_to(self.scratch_root)
        except ValueError as exc:
            raise ScopeViolation("scratch path escapes the worker root") from exc
        if resolved == self.scratch_root:
            raise ScopeViolation("worker root is not a file")
        return resolved

    def digest(self) -> str:
        payload = {
            "task_id": self.task_id,
            "team_id": self.team_id,
            "worker_id": self.worker_id,
            "assignment_id": self.assignment_id,
            "evidence_refs": list(self.evidence_refs),
            "clearance": self.clearance.value,
            "taint": self.taint.value,
            "scratch_root": str(self.scratch_root),
            "deadline": self.deadline.isoformat(),
            "capability": self.capability_scope.digest() if self.capability_scope else None,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class WorkerContext:
    """One worker's bounded, non-shared runtime view."""

    task: TaskEnvelope
    assignment: WorkerAssignment
    scope: WorkerScope
    evidence_provider: EvidenceProvider

    def __post_init__(self) -> None:
        if self.assignment.task_id != self.scope.task_id or self.assignment.worker_id != self.scope.worker_id:
            raise ValueError("assignment and scope identity do not match")

    @property
    def identity(self) -> WorkerIdentity:
        return WorkerIdentity(
            task_id=self.assignment.task_id,
            team_id=self.assignment.team_id,
            worker_id=self.assignment.worker_id,
            assignment_id=self.assignment.assignment_id,
            role=self.assignment.role,
            stage=self.assignment.stage,
        )

    def view(self) -> WorkerContextView:
        return WorkerContextView(
            schema_version=WORKER_CONTEXT_SCHEMA_VERSION,
            identity=self.identity,
            evidence_refs=self.assignment.evidence_refs,
            allowed_tools=self.assignment.allowed_tools,
            allowed_paths=self.scope.allowed_paths,
            clearance=self.assignment.clearance,
            taint=self.assignment.taint,
            deadline=self.assignment.deadline,
        )

    def can_use_tool(self, tool_name: str) -> bool:
        return tool_name in self.assignment.allowed_tools

    def evidence(self, evidence_ref: str, *, now: datetime | None = None) -> ScopedEvidence:
        self.scope.assert_active(now)
        if not self.scope.allows_evidence(evidence_ref):
            raise ScopeViolation("evidence reference is outside the worker scope")
        evidence = self.evidence_provider.get(evidence_ref)
        if evidence is None:
            raise EvidenceNotFound("permitted evidence is unavailable")
        if evidence.evidence_ref != evidence_ref:
            raise ScopeViolation("evidence provider returned an unexpected reference")
        if _CLEARANCE_RANK[evidence.clearance] > _CLEARANCE_RANK[self.assignment.clearance]:
            raise ScopeViolation("evidence clearance exceeds worker clearance")
        if _TAINT_RANK[evidence.taint] < _TAINT_RANK[self.assignment.taint]:
            raise ScopeViolation("evidence taint was downgraded at the worker boundary")
        return evidence

    def write_scratch(self, relative_path: str | Path, data: bytes | str, *, now: datetime | None = None) -> Path:
        self.scope.assert_active(now)
        if type(data) not in (bytes, str):
            raise ScopeViolation("scratch data must be bytes or text")
        target = self.scope.resolve_scratch_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = data.encode("utf-8") if isinstance(data, str) else data
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".airbench-", delete=False) as temporary:
                temporary_name = temporary.name
                temporary.write(raw)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, target)
            temporary_name = None
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
        return target

    def read_scratch(self, relative_path: str | Path, *, now: datetime | None = None) -> bytes:
        self.scope.assert_active(now)
        target = self.scope.resolve_scratch_path(relative_path)
        try:
            return target.read_bytes()
        except (FileNotFoundError, IsADirectoryError) as exc:
            raise ScopeViolation("worker scratch file is unavailable") from exc

    def build_model_call_request(
        self,
        *,
        request_id: str,
        task_kind: str,
        modality: str,
        evidence_summary: tuple[str, ...],
        resource_budget: dict[str, int] | None,
        attempt: int,
        call_idempotency_key: str,
        timeout_ms: int,
        resource_lease_id: str,
        now: datetime | None = None,
    ) -> ModelCallRequest:
        """Build one identity-bound request; this method never selects a model."""

        remaining_ms = self.scope.remaining_ms(now)
        if timeout_ms <= 0 or timeout_ms > remaining_ms:
            raise WorkerDeadlineExceeded("model timeout exceeds the worker deadline")
        if not resource_lease_id.strip():
            raise ScopeViolation("model call requires an orchestrator-issued resource lease")
        if not set(evidence_summary).issubset(set(self.assignment.evidence_refs)):
            raise ScopeViolation("model evidence summary exceeds the worker scope")
        payload = {
            "request_id": _require_text(request_id, "request_id"),
            "task_id": self.assignment.task_id,
            "team_id": self.assignment.team_id,
            "worker_id": self.assignment.worker_id,
            "task_kind": _require_text(task_kind, "task_kind"),
            "modality": _require_text(modality, "modality"),
            "required_capability": self.assignment.capability_requirement,
            "evidence_summary": list(evidence_summary),
            "clearance": self.assignment.clearance.value,
            "action_risk": self.task.risk_class,
            "resource_budget": dict(resource_budget if resource_budget is not None else self.task.resource_budget),
            "attempt": attempt,
            "idempotency_key": _require_text(call_idempotency_key, "call_idempotency_key"),
            "timeout_ms": timeout_ms,
            "role": self.assignment.role,
            "resource_lease_id": resource_lease_id,
        }
        return ModelCallRequest.from_dict(payload)


def create_worker_assignment(
    *,
    task: TaskEnvelope,
    team_id: str,
    worker_id: str,
    role: str,
    stage: str,
    input_schema: str,
    output_schema: str,
    evidence_refs: tuple[str, ...],
    allowed_tools: tuple[str, ...],
    capability_requirement: str,
    deadline: str,
    clearance: Clearance | str | None = None,
    taint: Taint | str = Taint.untrusted,
    assignment_id: str | None = None,
    call_idempotency_key: str | None = None,
    status: ContractStatus = ContractStatus.queued,
) -> WorkerAssignment:
    """Create a deterministic assignment narrowed from a TaskEnvelope."""

    worker_clearance = task.clearance if clearance is None else _as_clearance(clearance)
    worker_taint = _as_taint(taint)
    identity = assignment_id or f"assignment.{stable_id('worker-assignment', task.task_id, team_id, worker_id, stage)}"
    idem = call_idempotency_key or make_idempotency_key(
        "worker.assignment.create", task.task_id, team_id, worker_id, stage, identity
    )
    payload = {
        "assignment_id": identity,
        "team_id": team_id,
        "task_id": task.task_id,
        "worker_id": worker_id,
        "role": role,
        "stage": stage,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "evidence_refs": list(evidence_refs),
        "allowed_tools": list(allowed_tools),
        "clearance": worker_clearance.value,
        "taint": worker_taint.value,
        "capability_requirement": capability_requirement,
        "deadline": deadline,
        "idempotency_key": idem,
        "status": status.value,
    }
    try:
        assignment = WorkerAssignment.from_dict(payload)
    except ContractValidationError:
        raise
    _validate_task_scope(task, assignment)
    return assignment


def create_worker_context(
    *,
    task: TaskEnvelope,
    assignment: WorkerAssignment,
    workspace_root: str | Path,
    evidence_provider: EvidenceProvider,
    signing_key: bytes,
    policy_version_hash: str,
    now: datetime | None = None,
) -> WorkerContext:
    """Build one isolated context and, when needed, a signed tool capability."""

    _validate_task_scope(task, assignment)
    deadline = _parse_deadline(assignment.deadline)
    current = _now_utc(now)
    if current >= deadline:
        raise WorkerDeadlineExceeded("worker deadline has already elapsed")
    base = Path(workspace_root).resolve(strict=False)
    if not base.is_absolute() or base == Path(base.anchor):
        raise ScopeViolation("workspace root must be a non-root absolute path")
    scratch_root = (
        base
        / f"task-{stable_id('worker-task', task.task_id)}"
        / f"team-{stable_id('worker-team', assignment.team_id)}"
        / f"worker-{stable_id('worker-context', assignment.worker_id, assignment.assignment_id)}"
    ).resolve(strict=False)
    try:
        scratch_root.relative_to(base)
    except ValueError as exc:
        raise ScopeViolation("worker scratch root escaped the workspace root") from exc
    scratch_root.mkdir(parents=True, exist_ok=True)

    capability_scope: CapabilityScope | None = None
    if assignment.allowed_tools:
        capability_scope = issue_capability_scope(
            token_id=f"capability.{stable_id('worker-capability', assignment.assignment_id)}",
            task_id=assignment.task_id,
            team_id=assignment.team_id,
            worker_id=assignment.worker_id,
            allowed_tools=assignment.allowed_tools,
            allowed_paths=(str(scratch_root),),
            allowed_risk_classes=(task.risk_class,),
            max_clearance=assignment.clearance,
            max_timeout_ms=max(1, int((deadline - current).total_seconds() * 1000)),
            expires_at=assignment.deadline,
            policy_version_hash=_require_text(policy_version_hash, "policy_version_hash"),
            signing_key=signing_key,
        )
    scope = WorkerScope(
        task_id=assignment.task_id,
        team_id=assignment.team_id,
        worker_id=assignment.worker_id,
        assignment_id=assignment.assignment_id,
        evidence_refs=assignment.evidence_refs,
        clearance=assignment.clearance,
        taint=assignment.taint,
        scratch_root=scratch_root,
        deadline=deadline,
        capability_scope=capability_scope,
    )
    return WorkerContext(task=task, assignment=assignment, scope=scope, evidence_provider=evidence_provider)


__all__ = [
    "WORKER_CONTEXT_SCHEMA_VERSION",
    "AssignmentValidationError",
    "EvidenceNotFound",
    "EvidenceProvider",
    "ScopedEvidence",
    "ScopeViolation",
    "WorkerContext",
    "WorkerContextError",
    "WorkerContextView",
    "WorkerDeadlineExceeded",
    "WorkerIdentity",
    "WorkerScope",
    "create_worker_assignment",
    "create_worker_context",
]
