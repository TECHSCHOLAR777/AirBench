"""Deterministic execution of one declared AirBench worker team.

This module is the M4.4 execution seam.  It coordinates stateless worker
callbacks, but it does not become a second orchestrator: task state and audit
events go through :class:`contracts.Orchestrator`, physical admission and
leases go through :class:`contracts.ResourceScheduler`, and dependency
packets go through :class:`contracts.HandoffCoordinator`.

The callback supplied for a worker is one bounded invocation.  It receives an
isolated ``WorkerContext`` and immutable input handoffs.  It cannot create a
worker, alter the plan, mark a result verified, or decide task completion.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import Future, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol

from contracts import (
    BarrierStatus,
    CancellationToken,
    Clearance,
    ContractStatus,
    HandoffCoordinator,
    HandoffDecision,
    HandoffSubmission,
    JoinBarrier,
    LeaseStatus,
    Orchestrator,
    ResourceLease,
    ResourceScheduler,
    ScheduleDecision,
    Taint,
    TaskEnvelope,
    TeamPlan,
    WorkerAssignment,
    WorkerResult,
)
from contracts.errors import ContractValidationError
from contracts.ids import idempotency_key, stable_id
from airbench.orchestration.worker_context import EvidenceProvider, WorkerContext, create_worker_context


ExecutionMode = Literal["parallel", "pipelined", "serial_virtual_team"]
LifecycleAction = Literal["before", "after"]
LifecyclePhase = Literal[
    "before_task",
    "after_task",
    "before_team_plan",
    "after_team_plan",
    "before_worker_start",
    "after_worker_result",
    "before_model_call",
    "after_model_call",
    "before_tool_call",
    "after_tool_call",
    "before_join_barrier",
    "after_join_barrier",
    "before_context_compaction",
    "after_context_compaction",
    "before_team_complete",
    "after_team_complete",
]


class TeamRuntimeError(RuntimeError):
    """Base error for a rejected or failed team execution."""


class TeamPlanRejected(TeamRuntimeError):
    """The declared team cannot be executed under its immutable envelope."""


class LifecycleVeto(TeamRuntimeError):
    """A lifecycle interceptor blocked a boundary; execution fails closed."""


class TeamExecutionFailure(TeamRuntimeError):
    """A worker, dependency, resource, or ledger failure stopped the team."""


class TeamExecutionCancelled(TeamRuntimeError):
    """The host requested cancellation and the runtime is unwinding."""


class LifecycleInterceptor(Protocol):
    """A deterministic observer/veto point owned by the core runtime."""

    def before(self, event: "LifecycleEvent") -> None: ...

    def after(self, event: "LifecycleEvent") -> None: ...


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    """Metadata-only lifecycle event; it never carries document content."""

    phase: str
    action: LifecycleAction
    task_id: str
    team_id: str
    assignment_id: str | None = None
    payload: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.phase.strip() or not self.task_id.strip() or not self.team_id.strip():
            raise ValueError("lifecycle identity and phase are required")
        if self.action not in {"before", "after"}:
            raise ValueError("lifecycle action must be before or after")
        if len(set(key for key, _ in self.payload)) != len(self.payload):
            raise ValueError("lifecycle payload keys must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "action": self.action,
            "task_id": self.task_id,
            "team_id": self.team_id,
            "assignment_id": self.assignment_id,
            "payload": {key: value for key, value in self.payload},
        }

    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class WorkerInvocation:
    """The only input a stateless worker callback receives from the runtime."""

    context: WorkerContext
    lease: ResourceLease
    input_handoffs: tuple[HandoffSubmission, ...]
    output_barrier_ids: tuple[tuple[str, str], ...]

    def barrier_id_for(self, destination_assignment_id: str) -> str:
        for assignment_id, barrier_id in self.output_barrier_ids:
            if assignment_id == destination_assignment_id:
                return barrier_id
        raise TeamRuntimeError("destination assignment has no declared output barrier")


@dataclass(frozen=True, slots=True)
class WorkerExecution:
    """A worker proposal and its typed dependency handoffs."""

    result: WorkerResult
    handoffs: tuple[HandoffSubmission, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.result, WorkerResult):
            raise TypeError("worker execution requires a WorkerResult")
        if any(not isinstance(item, HandoffSubmission) for item in self.handoffs):
            raise TypeError("worker handoffs must be HandoffSubmission contracts")

    def digest(self) -> str:
        return _digest({
            "result": self.result.to_dict(),
            "handoffs": [handoff.to_dict() for handoff in self.handoffs],
        })


WorkerRunner = Callable[[WorkerInvocation, CancellationToken], WorkerExecution | WorkerResult]


@dataclass(frozen=True, slots=True)
class WorkerRunRecord:
    assignment_id: str
    worker_id: str
    status: str
    result: WorkerResult | None
    lease: ResourceLease
    handoff_decisions: tuple[HandoffDecision, ...] = ()
    failure_code: str | None = None
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "worker_id": self.worker_id,
            "status": self.status,
            "result": self.result.to_dict() if self.result else None,
            "lease": self.lease.to_dict(),
            "handoff_decisions": [
                {"outcome": decision.outcome, "reason": decision.reason,
                 "ledger_event_refs": list(decision.ledger_event_refs)}
                for decision in self.handoff_decisions
            ],
            "failure_code": self.failure_code,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(frozen=True, slots=True)
class TeamExecutionReport:
    task_id: str
    team_id: str
    execution_mode: ExecutionMode
    status: Literal["completed", "cancelled", "failed"]
    workers: tuple[WorkerRunRecord, ...]
    failure_code: str | None = None
    ledger_event_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "team_id": self.team_id,
            "execution_mode": self.execution_mode,
            "status": self.status,
            "workers": [worker.to_dict() for worker in self.workers],
            "failure_code": self.failure_code,
            "ledger_event_refs": list(self.ledger_event_refs),
        }


@dataclass(frozen=True, slots=True)
class ContextCompaction:
    """A resumable context manifest rebuilt from committed ledger evidence."""

    task_id: str
    team_id: str
    assignment_id: str
    source_event_ids: tuple[str, ...]
    source_event_hashes: tuple[str, ...]
    accepted_handoff_ids: tuple[str, ...]
    worker_result_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    clearance: Clearance
    taint: Taint
    last_source_sequence: int
    context_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "team_id": self.team_id,
            "assignment_id": self.assignment_id,
            "source_event_ids": list(self.source_event_ids),
            "source_event_hashes": list(self.source_event_hashes),
            "accepted_handoff_ids": list(self.accepted_handoff_ids),
            "worker_result_ids": list(self.worker_result_ids),
            "evidence_refs": list(self.evidence_refs),
            "clearance": self.clearance.value,
            "taint": self.taint.value,
            "last_source_sequence": self.last_source_sequence,
            "context_digest": self.context_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextCompaction":
        return cls(
            task_id=str(payload["task_id"]),
            team_id=str(payload["team_id"]),
            assignment_id=str(payload["assignment_id"]),
            source_event_ids=tuple(str(value) for value in payload.get("source_event_ids", ())),
            source_event_hashes=tuple(str(value) for value in payload.get("source_event_hashes", ())),
            accepted_handoff_ids=tuple(str(value) for value in payload.get("accepted_handoff_ids", ())),
            worker_result_ids=tuple(str(value) for value in payload.get("worker_result_ids", ())),
            evidence_refs=tuple(str(value) for value in payload.get("evidence_refs", ())),
            clearance=Clearance(str(payload["clearance"])),
            taint=Taint(str(payload["taint"])),
            last_source_sequence=int(payload["last_source_sequence"]),
            context_digest=str(payload["context_digest"]),
        )


@dataclass(frozen=True, slots=True)
class _WorkerOutcome:
    assignment_id: str
    lease: ResourceLease
    execution: WorkerExecution | None
    failure_code: str | None
    failure_hash: str | None
    elapsed_ms: int
    cancelled: bool = False


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _now_utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("runtime timestamps must include a timezone")
    return current.astimezone(timezone.utc)


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise TeamPlanRejected("assignment deadline is not RFC3339") from exc
    if parsed.tzinfo is None:
        raise TeamPlanRejected("assignment deadline must include a timezone")
    return parsed.astimezone(timezone.utc)


class TeamRuntime:
    """Execute one already-admitted ``TeamPlan`` with deterministic commits."""

    _AUDIT_ONLY_EVENTS = {
        "team.created", "team.execution.started", "team.execution.completed",
        "team.execution.failed", "team.execution.cancelled", "lifecycle.intercepted",
        "lifecycle.blocked", "worker.context.compacted",
    }

    def __init__(
        self,
        *,
        task: TaskEnvelope,
        team_plan: TeamPlan,
        assignments: Mapping[str, WorkerAssignment],
        schedule: ScheduleDecision,
        scheduler: ResourceScheduler,
        orchestrator: Orchestrator,
        workspace_root: str | Path,
        evidence_provider: EvidenceProvider,
        signing_key: bytes,
        worker_runners: Mapping[str, WorkerRunner],
        handoff_coordinator: HandoffCoordinator | None = None,
        interceptors: tuple[LifecycleInterceptor, ...] = (),
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.task = task
        self.team_plan = team_plan
        self.assignments = dict(assignments)
        self.schedule = schedule
        self.scheduler = scheduler
        self.orchestrator = orchestrator
        self.workspace_root = Path(workspace_root).resolve(strict=False)
        self.evidence_provider = evidence_provider
        self.signing_key = bytes(signing_key)
        self.worker_runners = dict(worker_runners)
        self.handoff_coordinator = handoff_coordinator
        self.interceptors = tuple(interceptors)
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._cancellation = CancellationToken()
        self._cancel_lock = threading.RLock()
        self._cancel_reason: str | None = None
        self._running = False
        self._barrier_ids: dict[str, str] = {}
        self._validate_constructor_inputs()

    def _validate_constructor_inputs(self) -> None:
        plan = self.schedule.plan
        if self.task.task_id != self.team_plan.task_id or self.task.task_id != plan.task_id:
            raise TeamPlanRejected("task identity does not match the team and resource plans")
        if self.team_plan.team_id != plan.team_id:
            raise TeamPlanRejected("team identity does not match the resource plan")
        if plan.admission not in {"admitted", "degraded_needs_review"}:
            raise TeamPlanRejected("team resource plan is not admitted")
        if plan.execution_mode not in {"parallel", "pipelined", "serial_virtual_team"}:
            raise TeamPlanRejected("resource plan has no executable mode")
        declared = set(self.team_plan.assignments)
        if declared != set(self.assignments):
            raise TeamPlanRejected("assignment mapping must exactly match the team plan")
        if declared != set(self.worker_runners):
            raise TeamPlanRejected("every declared assignment needs one stateless worker callback")
        if any(assignment_id not in self.team_plan.dependency_graph for assignment_id in declared):
            raise TeamPlanRejected("dependency graph must declare every assignment")
        for assignment_id, predecessors in self.team_plan.dependency_graph.items():
            if assignment_id not in declared or any(predecessor not in declared for predecessor in predecessors):
                raise TeamPlanRejected("dependency graph references an undeclared assignment")
        self._topological_order()
        if any(self.team_plan.dependency_graph.get(assignment_id) for assignment_id in declared) and self.handoff_coordinator is None:
            raise TeamPlanRejected("dependent teams require a HandoffCoordinator")
        if self.handoff_coordinator is not None:
            if self.handoff_coordinator.task.task_id != self.task.task_id:
                raise TeamPlanRejected("handoff coordinator task does not match the runtime")
            if self.handoff_coordinator.team_plan.team_id != self.team_plan.team_id:
                raise TeamPlanRejected("handoff coordinator team does not match the runtime")
        if not self.signing_key:
            raise TeamPlanRejected("worker context signing key is required")
        if not self.workspace_root.is_absolute() or self.workspace_root == Path(self.workspace_root.anchor):
            raise TeamPlanRejected("worker workspace root must be a non-root absolute path")

    def _topological_order(self) -> tuple[str, ...]:
        graph = {assignment_id: set(self.team_plan.dependency_graph.get(assignment_id, ())) for assignment_id in self.team_plan.assignments}
        order: list[str] = []
        ready = sorted(assignment_id for assignment_id, predecessors in graph.items() if not predecessors)
        while ready:
            current = ready.pop(0)
            order.append(current)
            for assignment_id in sorted(graph):
                if current in graph[assignment_id]:
                    graph[assignment_id].remove(current)
                    if not graph[assignment_id]:
                        ready.append(assignment_id)
            ready.sort()
        if len(order) != len(graph):
            raise TeamPlanRejected("team dependency graph contains a cycle")
        return tuple(order)

    @property
    def cancellation(self) -> CancellationToken:
        return self._cancellation

    def request_cancel(self, reason: str) -> None:
        """Request cooperative cancellation; the executing runtime commits it."""

        if not reason.strip():
            raise ValueError("cancellation reason is required")
        with self._cancel_lock:
            if self._cancel_reason is None:
                self._cancel_reason = reason.strip()
            self._cancellation.cancel()

    def notify(self, phase: LifecyclePhase, *, assignment_id: str | None = None,
               payload: Mapping[str, str] | None = None) -> None:
        """Expose the same audited hook seam to model/tool adapters."""

        self._notify(phase, assignment_id=assignment_id, payload=payload)

    def execute(self) -> TeamExecutionReport:
        with self._cancel_lock:
            if self._running:
                raise TeamRuntimeError("team runtime is already executing")
            self._running = True
        completed: set[str] = set()
        terminal: set[str] = set()
        records: list[WorkerRunRecord] = []
        task_started = False
        team_executing = False
        try:
            self._notify("before_task")
            task_started = True
            self._notify("before_team_plan")
            self._ensure_assignments()
            self._audit_team_start()
            self._notify("after_team_plan")
            team_executing = True
            completed, terminal = self._replay_worker_outcomes()
            pending = set(self.team_plan.assignments) - terminal

            while pending:
                if self._cancel_requested():
                    self._cancel_pending(pending)
                    return self._finish_cancelled(records)
                ready = self._ready_assignments(pending, completed)
                if not ready:
                    self._fail_team("dependency_barrier_unsatisfied", pending=pending)
                    return self._finish_failed(records, "dependency_barrier_unsatisfied")
                capacity = 1 if self.schedule.plan.execution_mode == "serial_virtual_team" else self.schedule.plan.concurrency_ceiling
                batch = tuple(ready[:max(1, capacity)])
                outcomes = self._run_batch(batch)
                # Commit EVERY outcome in the batch before aborting: returning
                # on the first failure dropped already-finished siblings' results
                # (no worker.completed events, lost handoffs, duplicated work on replay).
                abort_failure: str | None = None
                abort_cancelled = False
                for outcome in outcomes:
                    pending.discard(outcome.assignment_id)
                    record = self._commit_outcome(outcome)
                    records.append(record)
                    if record.status == "completed":
                        completed.add(outcome.assignment_id)
                    elif record.status == "cancelled":
                        abort_cancelled = True
                    elif abort_failure is None:
                        abort_failure = record.failure_code or "worker_failed"
                if abort_cancelled:
                    return self._finish_cancelled(records)
                if abort_failure is not None:
                    self._fail_team(abort_failure, pending=pending)
                    return self._finish_failed(records, abort_failure)

            if self._cancel_requested():
                return self._finish_cancelled(records)
            self._notify("before_team_complete")
            result = self.orchestrator.audit_event(
                self.task.task_id,
                "team.execution.completed",
                self._team_payload(status="completed"),
                contract="TeamExecutionReport",
                event_key=idempotency_key("team-runtime.completed", self.task.task_id, self.team_plan.team_id, self.team_plan.plan_version_hash),
            )
            self._notify("after_team_complete")
            report = TeamExecutionReport(
                task_id=self.task.task_id,
                team_id=self.team_plan.team_id,
                execution_mode=self.schedule.plan.execution_mode,
                status="completed",
                workers=tuple(sorted(records, key=lambda record: record.assignment_id)),
                ledger_event_refs=(result.event_id,),
            )
            self._notify("after_task")
            return report
        except (TeamRuntimeError, ContractValidationError):
            self._cleanup_active_leases()
            # A lifecycle veto raised after workers started must still record a
            # terminal state; previously the task stayed in `executing` forever.
            if team_executing and self.orchestrator.state(self.task.task_id) not in {"failed", "cancelled"}:
                try:
                    self._fail_team("runtime_failure", pending=set())
                except Exception:  # noqa: BLE001 - the original error is authoritative
                    pass
            raise
        except Exception as exc:
            self._cleanup_active_leases()
            if task_started and self.orchestrator.state(self.task.task_id) not in {"failed", "cancelled"}:
                self._fail_team("runtime_failure", pending=set())
            raise TeamExecutionFailure("team runtime failed closed") from exc
        finally:
            self._running = False
            self._cleanup_workspace()

    def _cleanup_workspace(self) -> None:
        """Best-effort removal of this team's worker scratch tree.

        Scratch directories are deterministic but were never deleted, so every
        task/team/worker execution leaked a directory until the disk filled
        and all sandbox executions started failing.  Contexts are recreated
        on demand by ``create_worker_context`` so removal is always safe.
        """
        import shutil

        team_dir = (
            self.workspace_root
            / f"task-{stable_id('worker-task', self.task.task_id)}"
            / f"team-{stable_id('worker-team', self.team_plan.team_id)}"
        )
        try:
            if team_dir.is_relative_to(self.workspace_root):
                shutil.rmtree(team_dir, ignore_errors=True)
        except OSError:
            pass

    def rebuild_context(self, assignment_id: str) -> ContextCompaction:
        """Rebuild a metadata-only context manifest from the append-only ledger."""

        assignment = self.assignments.get(assignment_id)
        if assignment is None:
            raise TeamPlanRejected("cannot compact an undeclared assignment")
        relevant = []
        handoff_ids: set[str] = set()
        result_ids: set[str] = set()
        evidence_refs = set(assignment.evidence_refs)
        taint = assignment.taint
        clearance = assignment.clearance
        for event in self.orchestrator.store.events:
            if event.task_id != self.task.task_id:
                continue
            if event.event_type in {"lifecycle.intercepted", "lifecycle.blocked", "worker.context.compacted"}:
                continue
            payload = event.payload
            event_assignment = payload.get("assignment_id")
            handoff_payload = payload.get("handoff")
            is_relevant = event_assignment == assignment_id
            if isinstance(handoff_payload, dict) and handoff_payload.get("destination_assignment_id") == assignment_id:
                is_relevant = True
                handoff_id = str(handoff_payload.get("handoff_id", ""))
                if handoff_id:
                    handoff_ids.add(handoff_id)
                packet = handoff_payload.get("packet")
                if isinstance(packet, dict):
                    evidence_refs.update(str(value) for value in packet.get("evidence_refs", ()))
                    if str(packet.get("taint", taint.value)) == Taint.contaminated.value:
                        taint = Taint.contaminated
            if is_relevant:
                relevant.append(event)
            if event.event_type == "worker.completed" and event_assignment == assignment_id:
                result_id = str(payload.get("result_id", ""))
                if result_id:
                    result_ids.add(result_id)
        source_ids = tuple(event.event_id for event in relevant)
        source_hashes = tuple(event.event_hash for event in relevant)
        last_sequence = relevant[-1].sequence if relevant else -1
        identity = {
            "task_id": self.task.task_id,
            "team_id": self.team_plan.team_id,
            "assignment_id": assignment_id,
            "source_event_ids": list(source_ids),
            "source_event_hashes": list(source_hashes),
            "accepted_handoff_ids": sorted(handoff_ids),
            "worker_result_ids": sorted(result_ids),
            "evidence_refs": sorted(evidence_refs),
            "clearance": clearance.value,
            "taint": taint.value,
            "last_source_sequence": last_sequence,
        }
        return ContextCompaction(
            task_id=self.task.task_id,
            team_id=self.team_plan.team_id,
            assignment_id=assignment_id,
            source_event_ids=source_ids,
            source_event_hashes=source_hashes,
            accepted_handoff_ids=tuple(sorted(handoff_ids)),
            worker_result_ids=tuple(sorted(result_ids)),
            evidence_refs=tuple(sorted(evidence_refs)),
            clearance=clearance,
            taint=taint,
            last_source_sequence=last_sequence,
            context_digest=_digest(identity),
        )

    def compact_worker_context(self, assignment_id: str) -> ContextCompaction:
        self._notify("before_context_compaction", assignment_id=assignment_id)
        compaction = self.rebuild_context(assignment_id)
        key = idempotency_key("team-runtime.compaction", self.task.task_id, assignment_id, compaction.context_digest)
        existing = self.orchestrator.store.find_by_idempotency(key)
        if existing is not None:
            compacted = ContextCompaction.from_dict(existing.payload["compaction"])
        else:
            self.orchestrator.audit_event(
                self.task.task_id,
                "worker.context.compacted",
                {
                    "team_id": self.team_plan.team_id,
                    "assignment_id": assignment_id,
                    "compaction": compaction.to_dict(),
                    "source_head_hash": self.orchestrator.store.head_hash,
                },
                contract="ContextCompaction",
                event_key=key,
            )
            compacted = compaction
        self._notify("after_context_compaction", assignment_id=assignment_id,
                     payload={"context_digest": compacted.context_digest})
        return compacted

    def _ensure_assignments(self) -> None:
        state = self.orchestrator.state(self.task.task_id)
        if state not in {"planned", "executing", "awaiting_check"}:
            raise TeamPlanRejected(f"team execution requires a planned or active task, got {state}")
        existing = {
            event.payload.get("assignment", {}).get("assignment_id")
            for event in self.orchestrator.store.events
            if event.task_id == self.task.task_id and event.event_type == "worker.assigned"
        }
        if state != "planned" and any(assignment_id not in existing for assignment_id in self.team_plan.assignments):
            raise TeamPlanRejected("active team is missing a committed worker assignment")
        if state == "planned":
            for assignment_id in sorted(set(self.team_plan.assignments) - existing):
                self.orchestrator.assign_worker(self.assignments[assignment_id])

    def _audit_team_start(self) -> None:
        self.orchestrator.audit_event(
            self.task.task_id,
            "team.created",
            {"team_id": self.team_plan.team_id, "plan_hash": self.team_plan.plan_version_hash},
            contract="TeamPlan",
            event_key=idempotency_key("team-runtime.created", self.task.task_id, self.team_plan.team_id, self.team_plan.plan_version_hash),
        )
        self.orchestrator.audit_event(
            self.task.task_id,
            "team.execution.started",
            self._team_payload(status="started"),
            contract="TeamExecutionReport",
            event_key=idempotency_key("team-runtime.started", self.task.task_id, self.team_plan.team_id, self.team_plan.plan_version_hash),
        )

    def _team_payload(self, *, status: str) -> dict[str, Any]:
        return {
            "team_id": self.team_plan.team_id,
            "plan_hash": self.team_plan.plan_version_hash,
            "execution_mode": self.schedule.plan.execution_mode,
            "status": status,
            "assignment_ids": list(self.team_plan.assignments),
        }

    def _topological_ready(self, pending: set[str], completed: set[str]) -> list[str]:
        ready = []
        for assignment_id in self._topological_order():
            if assignment_id not in pending:
                continue
            predecessors = set(self.team_plan.dependency_graph.get(assignment_id, ()))
            if not predecessors.issubset(completed):
                continue
            if predecessors:
                barrier = self._barrier_for(assignment_id, create=False)
                if barrier is None or barrier.status != BarrierStatus.completed:
                    continue
            ready.append(assignment_id)
        return ready

    def _ready_assignments(self, pending: set[str], completed: set[str]) -> list[str]:
        return self._topological_ready(pending, completed)

    def _barrier_for(self, assignment_id: str, *, create: bool) -> JoinBarrier | None:
        if self.handoff_coordinator is None:
            return None
        predecessors = tuple(sorted(self.team_plan.dependency_graph.get(assignment_id, ())))
        if not predecessors:
            return None
        barrier_id = self._barrier_ids.get(assignment_id)
        if barrier_id is None:
            barrier_id = f"barrier.{stable_id('team-runtime.join', self.task.task_id, self.team_plan.team_id, assignment_id, self.team_plan.plan_version_hash)}"
            self._barrier_ids[assignment_id] = barrier_id
        try:
            return self.handoff_coordinator.barrier(barrier_id)
        except Exception:
            if not create:
                return None
        assignment = self.assignments[assignment_id]
        barrier = JoinBarrier.from_dict({
            "barrier_id": barrier_id,
            "task_id": self.task.task_id,
            "team_id": self.team_plan.team_id,
            "destination_assignment_id": assignment_id,
            "destination_stage": assignment.stage,
            "plan_version": self.team_plan.plan_version_hash,
            "barrier_version": 1,
            "required_predecessor_assignment_ids": list(predecessors),
            "accepted_handoff_ids": [],
            "accepted_packet_hashes": [],
            "missing_assignment_ids": list(predecessors),
            "conflict_packet_refs": [],
            "deadline": assignment.deadline,
            "join_policy": "join_all",
            "status": "waiting",
            "clearance": assignment.clearance.value,
            "taint": assignment.taint.value,
            "policy_version_hash": self.team_plan.policy_version_hash,
            "idempotency_key": idempotency_key("team-runtime.barrier", self.task.task_id, self.team_plan.team_id, assignment_id, self.team_plan.plan_version_hash),
            "created_at": _now_utc(self._now_provider()).isoformat().replace("+00:00", "Z"),
        })
        self._notify("before_join_barrier", assignment_id=assignment_id,
                     payload={"barrier_id": barrier_id})
        opened = self.handoff_coordinator.open_barrier(barrier)
        self._notify("after_join_barrier", assignment_id=assignment_id,
                     payload={"barrier_id": barrier_id, "status": opened.status.value})
        return opened

    def _lease_for(self, assignment_id: str) -> ResourceLease:
        assignment = self.assignments[assignment_id]
        existing = next((lease for lease in self.scheduler.active_leases if lease.worker_id == assignment.worker_id), None)
        if existing is not None:
            return existing
        for lease in self.schedule.leases:
            if lease.worker_id == assignment.worker_id:
                return lease
        return self.scheduler.grant_worker_lease(self.team_plan.team_id, assignment.worker_id, now=_now_utc(self._now_provider()))

    def _prepare_invocation(self, assignment_id: str) -> tuple[WorkerInvocation, ResourceLease]:
        assignment = self.assignments[assignment_id]
        lease = self._lease_for(assignment_id)
        active = self.scheduler.activate_lease(lease.lease_id, now=_now_utc(self._now_provider()))
        self._notify("before_worker_start", assignment_id=assignment_id,
                     payload={"worker_id": assignment.worker_id, "lease_id": active.lease_id})
        self.orchestrator.transition(
            self.task.task_id,
            "worker.started",
            {"team_id": self.team_plan.team_id, "assignment_id": assignment_id,
             "worker_id": assignment.worker_id, "lease_id": active.lease_id},
        )
        context = create_worker_context(
            task=self.task,
            assignment=assignment,
            workspace_root=self.workspace_root,
            evidence_provider=self.evidence_provider,
            signing_key=self.signing_key,
            policy_version_hash=self.team_plan.policy_version_hash,
            now=_now_utc(self._now_provider()),
        )
        inputs: tuple[HandoffSubmission, ...] = ()
        barrier = self._barrier_for(assignment_id, create=False)
        if barrier is not None and self.handoff_coordinator is not None:
            by_id = {handoff.handoff_id: handoff for handoff in self.handoff_coordinator.handoffs}
            inputs = tuple(by_id[handoff_id] for handoff_id in barrier.accepted_handoff_ids if handoff_id in by_id)
        output_barriers = tuple(
            (destination, self._barrier_id_for(destination))
            for destination, predecessors in sorted(self.team_plan.dependency_graph.items())
            if assignment_id in predecessors
        )
        self._notify("before_model_call", assignment_id=assignment_id,
                     payload={"lease_id": active.lease_id})
        return WorkerInvocation(context, active, inputs, output_barriers), active

    def _barrier_id_for(self, assignment_id: str) -> str:
        barrier = self._barrier_for(assignment_id, create=True)
        if barrier is None:
            raise TeamRuntimeError("dependent assignment has no join barrier")
        return barrier.barrier_id

    def _run_batch(self, assignment_ids: tuple[str, ...]) -> tuple[_WorkerOutcome, ...]:
        prepared: dict[str, tuple[WorkerInvocation, ResourceLease]] = {}
        try:
            for assignment_id in assignment_ids:
                prepared[assignment_id] = self._prepare_invocation(assignment_id)
        except Exception:
            for _, lease in prepared.values():
                self._release(lease, LeaseStatus.failed)
            raise

        started_at = {assignment_id: time.monotonic() for assignment_id in assignment_ids}
        # Daemon worker threads: a timed-out (abandoned) worker must never
        # block interpreter exit. ThreadPoolExecutor threads are non-daemon
        # and are joined at process shutdown, which hung the whole Node.
        futures: dict[str, Future[WorkerExecution | WorkerResult]] = {}
        for assignment_id in assignment_ids:
            future: Future[WorkerExecution | WorkerResult] = Future()

            def _run(aid: str = assignment_id, fut: Future = future) -> None:
                if not fut.set_running_or_notify_cancel():
                    return
                try:
                    fut.set_result(self._call_worker(aid, prepared[aid][0]))
                except BaseException as exc:  # noqa: BLE001 - forwarded to the future
                    fut.set_exception(exc)

            thread = threading.Thread(target=_run, daemon=True, name=f"airbench-worker-{assignment_id[:12]}")
            thread.start()
            futures[assignment_id] = future
        deadlines = {assignment_id: _parse_time(self.assignments[assignment_id].deadline) for assignment_id in assignment_ids}
        # Wait per assignment deadline: using the batch MINIMUM deadline
        # timed out every sibling as soon as the shortest deadline expired.
        # Deadlines are converted to monotonic-relative timeouts once so an
        # injected fixed ``now_provider`` (tests, replay) still converges.
        batch_started = time.monotonic()
        relative_deadlines = {
            futures[assignment_id]: max(0.0, (deadline - _now_utc(self._now_provider())).total_seconds())
            for assignment_id, deadline in deadlines.items()
        }
        pending_futures: set[Future] = set(futures.values())
        while pending_futures:
            now_monotonic = time.monotonic()
            expired = {future for future in pending_futures if batch_started + relative_deadlines[future] <= now_monotonic}
            if expired:
                pending_futures -= expired
                continue
            next_deadline = min(batch_started + relative_deadlines[future] for future in pending_futures)
            remaining = max(0.0, next_deadline - now_monotonic)
            done_now, _ = wait(pending_futures, timeout=remaining)
            pending_futures -= done_now
        outcomes: list[_WorkerOutcome] = []
        for assignment_id in sorted(assignment_ids):
            future = futures[assignment_id]
            elapsed = int((time.monotonic() - started_at[assignment_id]) * 1000)
            lease = prepared[assignment_id][1]
            if not future.done():
                future.cancel()
                outcomes.append(_WorkerOutcome(assignment_id, lease, None, "worker_timeout", None, elapsed))
                continue
            try:
                execution = _coerce_execution(future.result())
                outcomes.append(_WorkerOutcome(assignment_id, lease, execution, None, None, elapsed))
            except Exception as exc:
                outcomes.append(_WorkerOutcome(
                    assignment_id, lease, None, "worker_failure", _digest({"type": type(exc).__name__, "message": str(exc)}), elapsed,
                    cancelled=self._cancel_requested(),
                ))
        return tuple(sorted(outcomes, key=lambda outcome: outcome.assignment_id))

    def _call_worker(self, assignment_id: str, invocation: WorkerInvocation) -> WorkerExecution | WorkerResult:
        if self._cancel_requested():
            raise TeamExecutionCancelled(self._cancel_reason or "team cancellation requested")
        result = self.worker_runners[assignment_id](invocation, self._cancellation)
        if self._cancel_requested():
            raise TeamExecutionCancelled(self._cancel_reason or "team cancellation requested")
        return result

    def _commit_outcome(self, outcome: _WorkerOutcome) -> WorkerRunRecord:
        assignment = self.assignments[outcome.assignment_id]
        if outcome.cancelled or (outcome.failure_code == "worker_failure" and self._cancel_requested()):
            self.orchestrator.transition(
                self.task.task_id,
                "worker.cancelled",
                {"team_id": self.team_plan.team_id, "assignment_id": outcome.assignment_id,
                 "worker_id": assignment.worker_id, "reason": self._cancel_reason or "cancelled"},
            )
            lease = self._release(outcome.lease, LeaseStatus.cancelled)
            return WorkerRunRecord(outcome.assignment_id, assignment.worker_id, "cancelled", None, lease,
                                   failure_code="cancelled", elapsed_ms=outcome.elapsed_ms)
        if outcome.execution is None:
            self.orchestrator.transition(
                self.task.task_id,
                "worker.failed",
                {"team_id": self.team_plan.team_id, "assignment_id": outcome.assignment_id,
                 "worker_id": assignment.worker_id, "failure_code": outcome.failure_code or "worker_failure",
                 "failure_hash": outcome.failure_hash, "elapsed_ms": outcome.elapsed_ms},
            )
            lease = self._release(outcome.lease, LeaseStatus.failed)
            return WorkerRunRecord(outcome.assignment_id, assignment.worker_id, "failed", None, lease,
                                   failure_code=outcome.failure_code or "worker_failure", elapsed_ms=outcome.elapsed_ms)

        execution = outcome.execution
        result = execution.result
        if result.task_id != self.task.task_id or result.assignment_id != outcome.assignment_id:
            self.orchestrator.transition(
                self.task.task_id,
                "worker.failed",
                {"team_id": self.team_plan.team_id, "assignment_id": outcome.assignment_id,
                 "worker_id": assignment.worker_id, "failure_code": "result_identity_mismatch"},
            )
            lease = self._release(outcome.lease, LeaseStatus.failed)
            return WorkerRunRecord(outcome.assignment_id, assignment.worker_id, "failed", None, lease,
                                   failure_code="result_identity_mismatch", elapsed_ms=outcome.elapsed_ms)
        if result.status not in {ContractStatus.proposed, ContractStatus.accepted, ContractStatus.needs_review}:
            self.orchestrator.transition(
                self.task.task_id,
                "worker.failed",
                {"team_id": self.team_plan.team_id, "assignment_id": outcome.assignment_id,
                 "worker_id": assignment.worker_id, "failure_code": "invalid_worker_status"},
            )
            lease = self._release(outcome.lease, LeaseStatus.failed)
            return WorkerRunRecord(outcome.assignment_id, assignment.worker_id, "failed", result, lease,
                                   failure_code="invalid_worker_status", elapsed_ms=outcome.elapsed_ms)
        try:
            self._notify("after_model_call", assignment_id=outcome.assignment_id,
                         payload={"result_hash": result.digest()})
            decisions = self._submit_handoffs(outcome.assignment_id, outcome.lease, execution.handoffs)
            if any(decision.outcome not in {"accepted", "duplicate"} for decision in decisions):
                raise TeamExecutionFailure("worker handoff was not accepted")
            self._notify("after_worker_result", assignment_id=outcome.assignment_id,
                         payload={"result_hash": result.digest()})
        except Exception:
            self.orchestrator.transition(
                self.task.task_id,
                "worker.failed",
                {"team_id": self.team_plan.team_id, "assignment_id": outcome.assignment_id,
                 "worker_id": assignment.worker_id, "failure_code": "handoff_or_lifecycle_failure"},
            )
            lease = self._release(outcome.lease, LeaseStatus.failed)
            return WorkerRunRecord(outcome.assignment_id, assignment.worker_id, "failed", None, lease,
                                   failure_code="handoff_or_lifecycle_failure", elapsed_ms=outcome.elapsed_ms)

        self.orchestrator.transition(
            self.task.task_id,
            "worker.completed",
            {
                "team_id": self.team_plan.team_id,
                "assignment_id": outcome.assignment_id,
                "worker_id": assignment.worker_id,
                "result_id": result.result_id,
                "result_hash": result.digest(),
                "status": result.status.value,
                "handoff_ids": [handoff.handoff_id for handoff in execution.handoffs],
                "provenance": {
                    "source_refs": list(assignment.evidence_refs),
                    "clearance": assignment.clearance.value,
                    "taint": assignment.taint.value,
                    "derivation": f"worker:{assignment.role}:{assignment.stage}",
                },
            },
        )
        lease = self._release(outcome.lease, LeaseStatus.released)
        return WorkerRunRecord(outcome.assignment_id, assignment.worker_id, "completed", result, lease,
                               elapsed_ms=outcome.elapsed_ms)

    def _submit_handoffs(self, source_assignment_id: str, lease: ResourceLease,
                         handoffs: tuple[HandoffSubmission, ...]) -> tuple[HandoffDecision, ...]:
        if not handoffs:
            return ()
        if self.handoff_coordinator is None:
            raise TeamExecutionFailure("worker returned a handoff without a coordinator")
        expected_destinations = {
            destination for destination, predecessors in self.team_plan.dependency_graph.items()
            if source_assignment_id in predecessors
        }
        decisions = []
        for handoff in sorted(handoffs, key=lambda item: item.handoff_id):
            if handoff.source_assignment_id != source_assignment_id or handoff.source_lease_id != lease.lease_id:
                raise TeamExecutionFailure("handoff source or lease is not the active worker identity")
            if handoff.destination_assignment_id not in expected_destinations:
                raise TeamExecutionFailure("handoff destination is not a declared dependency")
            expected_barrier = self._barrier_id_for(handoff.destination_assignment_id)
            if handoff.barrier_id != expected_barrier:
                raise TeamExecutionFailure("handoff does not target the runtime-owned barrier")
            self._barrier_for(handoff.destination_assignment_id, create=True)
            decisions.append(self.handoff_coordinator.submit_handoff(handoff, now=_now_utc(self._now_provider())))
        return tuple(decisions)

    def _release(self, lease: ResourceLease, status: LeaseStatus) -> ResourceLease:
        if lease.status in {LeaseStatus.granted, LeaseStatus.active}:
            return self.scheduler.release_lease(lease.lease_id, status=status, now=_now_utc(self._now_provider()))
        return lease

    def _cleanup_active_leases(self) -> None:
        for lease in tuple(self.scheduler.active_leases):
            if lease.team_id == self.team_plan.team_id:
                try:
                    self.scheduler.release_lease(lease.lease_id, status=LeaseStatus.failed, now=_now_utc(self._now_provider()))
                except Exception:
                    pass

    def _replay_worker_outcomes(self) -> tuple[set[str], set[str]]:
        completed: set[str] = set()
        terminal: set[str] = set()
        for event in self.orchestrator.store.events:
            if event.task_id != self.task.task_id:
                continue
            assignment_id = event.payload.get("assignment_id")
            if assignment_id not in self.team_plan.assignments:
                continue
            if event.event_type in {"worker.completed", "worker.failed", "worker.cancelled"}:
                terminal.add(assignment_id)
                if event.event_type == "worker.completed":
                    completed.add(assignment_id)
        return completed, terminal

    def _cancel_requested(self) -> bool:
        return self._cancellation.cancelled

    def _cancel_pending(self, pending: set[str]) -> None:
        for assignment_id in sorted(pending):
            assignment = self.assignments[assignment_id]
            self.orchestrator.transition(
                self.task.task_id,
                "worker.cancelled",
                {"team_id": self.team_plan.team_id, "assignment_id": assignment_id,
                 "worker_id": assignment.worker_id, "reason": self._cancel_reason or "cancelled"},
            )

    def _fail_team(self, failure_code: str, *, pending: set[str]) -> None:
        self._cleanup_active_leases()
        self.orchestrator.audit_event(
            self.task.task_id,
            "team.execution.failed",
            {**self._team_payload(status="failed"), "failure_code": failure_code,
             "pending_assignment_ids": sorted(pending)},
            contract="TeamExecutionReport",
            event_key=idempotency_key("team-runtime.failed", self.task.task_id, self.team_plan.team_id, failure_code),
        )
        if self.orchestrator.state(self.task.task_id) not in {"failed", "cancelled"}:
            self.orchestrator.transition(self.task.task_id, "task.failed", {"failure_code": failure_code, "team_id": self.team_plan.team_id})

    def _finish_cancelled(self, records: list[WorkerRunRecord]) -> TeamExecutionReport:
        self._cleanup_active_leases()
        self.orchestrator.audit_event(
            self.task.task_id,
            "team.execution.cancelled",
            {**self._team_payload(status="cancelled"), "reason": self._cancel_reason or "cancelled"},
            contract="TeamExecutionReport",
            event_key=idempotency_key("team-runtime.cancelled", self.task.task_id, self.team_plan.team_id, self._cancel_reason or "cancelled"),
        )
        self._notify("after_task")
        if self.orchestrator.state(self.task.task_id) not in {"failed", "cancelled"}:
            self.orchestrator.cancel(self.task.task_id, reason=self._cancel_reason or "cancelled")
        return TeamExecutionReport(self.task.task_id, self.team_plan.team_id, self.schedule.plan.execution_mode,
                                   "cancelled", tuple(sorted(records, key=lambda record: record.assignment_id)),
                                   failure_code="cancelled")

    def _finish_failed(self, records: list[WorkerRunRecord], failure_code: str) -> TeamExecutionReport:
        return TeamExecutionReport(self.task.task_id, self.team_plan.team_id, self.schedule.plan.execution_mode,
                                   "failed", tuple(sorted(records, key=lambda record: record.assignment_id)),
                                   failure_code=failure_code)

    def _notify(self, phase: LifecyclePhase, *, assignment_id: str | None = None,
                payload: Mapping[str, str] | None = None) -> None:
        values = tuple(sorted((str(key), str(value)) for key, value in (payload or {}).items()))
        action: LifecycleAction = "before" if phase.startswith("before_") else "after"
        current = LifecycleEvent(phase, action, self.task.task_id, self.team_plan.team_id, assignment_id, values)
        self.orchestrator.audit_event(
            self.task.task_id,
            "lifecycle.intercepted",
            {"team_id": self.team_plan.team_id, "phase": phase, "action": action,
             "assignment_id": assignment_id, "payload_hash": current.digest()},
            contract="LifecycleEvent",
            event_key=idempotency_key("team-runtime.lifecycle", phase, action, self.task.task_id,
                                     self.team_plan.team_id, assignment_id, current.digest()),
        )
        try:
            for interceptor in self.interceptors:
                getattr(interceptor, action)(current)
        except Exception as exc:
            self.orchestrator.audit_event(
                self.task.task_id,
                "lifecycle.blocked",
                {"team_id": self.team_plan.team_id, "phase": phase, "action": action,
                 "assignment_id": assignment_id, "failure_class": type(exc).__name__,
                 "failure_hash": _digest({"type": type(exc).__name__, "message": str(exc)})},
                contract="LifecycleEvent",
                event_key=idempotency_key("team-runtime.lifecycle.blocked", phase, action, self.task.task_id,
                                         self.team_plan.team_id, assignment_id, current.digest()),
            )
            raise LifecycleVeto(f"lifecycle interceptor blocked {action}:{phase}") from exc


def _coerce_execution(value: WorkerExecution | WorkerResult) -> WorkerExecution:
    if isinstance(value, WorkerExecution):
        return value
    if isinstance(value, WorkerResult):
        return WorkerExecution(value)
    raise TeamRuntimeError("worker callback returned an unsupported result type")


def _completed_future(value: WorkerExecution | WorkerResult) -> Future[WorkerExecution | WorkerResult]:
    future: Future[WorkerExecution | WorkerResult] = Future()
    future.set_result(value)
    return future


def _failed_future(error: Exception) -> Future[WorkerExecution | WorkerResult]:
    future: Future[WorkerExecution | WorkerResult] = Future()
    future.set_exception(error)
    return future


__all__ = [
    "ContextCompaction", "ExecutionMode", "LifecycleEvent", "LifecycleInterceptor",
    "LifecycleVeto", "TeamExecutionFailure", "TeamExecutionReport", "TeamPlanRejected",
    "TeamRuntime", "TeamRuntimeError", "WorkerExecution", "WorkerInvocation", "WorkerRunRecord",
    "WorkerRunner",
]
