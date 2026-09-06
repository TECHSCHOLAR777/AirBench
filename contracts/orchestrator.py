"""Deterministic, ledger-backed task orchestration for the first backend slice."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .errors import ContractValidationError
from .ids import idempotency_key, stable_id
from .authorization import AuthorizationService
from .ledger import (CommittedTransaction, EventLedger, LedgerError, SQLiteLedgerStore,
                     StorageFailure, TransitionRejected, build_event)
from .models import Clearance, ContractStatus, TaskEnvelope, TeamPlan
from .planning import PlanProposal, PlanValidator


class OrchestrationError(RuntimeError):
    """Base error for deterministic orchestration rejection."""


class AuthorizationRejected(OrchestrationError):
    pass


class PlanRejected(OrchestrationError):
    pass


class StepTimeout(OrchestrationError):
    pass


class RetryExhausted(OrchestrationError):
    pass


class CircuitOpen(OrchestrationError):
    pass


class CancellationRequested(OrchestrationError):
    pass


@dataclass(frozen=True, slots=True)
class TransitionResult:
    task_id: str
    event_id: str
    event_type: str
    state: str
    sequence: int
    idempotency_key: str
    transaction_id: str | None


@dataclass(frozen=True, slots=True)
class StepResult:
    task_id: str
    step_id: str
    attempt: int
    result: Any
    transition: TransitionResult


_TARGETS = {
    "task.created": "created",
    "task.authorized": "authorized",
    "task.plan.committed": "planned",
    "resource.plan.admitted": "executing",
    "model.requested": "executing",
    "retrieval.requested": "executing",
    "world_model.requested": "executing",
    "verification.requested": "executing",
    "tool.requested": "executing",
    "barrier.waiting": "awaiting_check",
    "verification.completed": {"passed": "deliverable_verified", "needs_review": "needs_review", "failed": "blocked"},
    "human.review.required": "awaiting_review",
    "artifact.staged": "rendering",
    "artifact.checked": "deliverable_verified",
    "completion.recorded": "complete",
    "task.failed": "failed",
    "task.cancelled": "cancelled",
}

_ALLOWED = {
    "task.authorized": {"created"},
    "task.plan.committed": {"authorized"},
    "resource.plan.admitted": {"planned"},
    "model.requested": {"planned", "executing"},
    "retrieval.requested": {"planned", "executing"},
    "world_model.requested": {"planned", "executing"},
    "tool.requested": {"planned", "executing"},
    "barrier.waiting": {"executing"},
    "verification.requested": {"executing", "awaiting_check"},
    "verification.completed": {"awaiting_check"},
    "human.review.required": {"deliverable_verified", "needs_review", "awaiting_review"},
    "artifact.staged": {"deliverable_verified", "awaiting_review"},
    "artifact.checked": {"rendering"},
    "completion.recorded": {"deliverable_verified"},
    "task.failed": {"created", "authorized", "planned", "executing", "awaiting_check", "awaiting_review", "rendering"},
    "task.cancelled": {"created", "authorized", "planned", "executing", "awaiting_check", "awaiting_review", "rendering", "needs_review"},
}


class Orchestrator:
    """The sole state-mutating API exposed to workers and integrations."""

    def __init__(self, store: SQLiteLedgerStore | EventLedger, *, actor_id: str = "orchestrator.local",
                 authorization: AuthorizationService | None = None,
                 plan_validator: PlanValidator | None = None) -> None:
        self.store = store
        self.actor_id = actor_id
        self.authorization = authorization
        self.plan_validator = plan_validator or PlanValidator()
        self._circuit_failures: dict[str, int] = {}
        self._circuit_open: set[str] = set()

    def create_task(self, *, principal_id: str, clearance: Clearance | str, request: str,
                    domain_pack_ref: str, risk_class: str, autonomy_ceiling: str,
                    allowed_evidence_scope: tuple[str, ...] = (),
                    permitted_worker_capabilities: tuple[str, ...] = (),
                    permitted_tools: tuple[str, ...] = (), output_contract: str = "text",
                    verification_criteria: tuple[str, ...] = (),
                    resource_budget: dict[str, int] | None = None,
                    task_id: str | None = None) -> TaskEnvelope:
        task = TaskEnvelope(
            task_id=task_id or stable_id("task", principal_id, request, domain_pack_ref),
            principal_id=principal_id, clearance=clearance if isinstance(clearance, Clearance) else Clearance(clearance),
            request=request, domain_pack_ref=domain_pack_ref, risk_class=risk_class,
            autonomy_ceiling=autonomy_ceiling, allowed_evidence_scope=allowed_evidence_scope,
            permitted_worker_capabilities=permitted_worker_capabilities, permitted_tools=permitted_tools,
            output_contract=output_contract, verification_criteria=verification_criteria,
            resource_budget=resource_budget or {},
        )
        try:
            if self.authorization is not None:
                decision = self.authorization.authorize(
                    principal_id=principal_id, requested_clearance=task.clearance,
                    evidence_scope=allowed_evidence_scope, tools=permitted_tools,
                    risk_class=risk_class, resource_budget=task.resource_budget)
            else:
                decision = None
            task = TaskEnvelope.from_dict(task.to_dict())
            payload = {"task": task.to_dict(), "state": "created"}
            if decision is not None:
                payload["authorization"] = {"principal_id": decision.principal_id, "pack_ref": decision.pack.reference, "pack_digest": decision.pack.digest, "policy_ref": decision.policy.reference, "policy_digest": decision.policy.digest}
            self._append("task.created", task.task_id, payload, "TaskEnvelope", idempotency_key("orchestrator.task.create", task.task_id))
        except (ContractValidationError, LedgerError) as exc:
            raise StorageFailure("task creation was not committed") from exc
        return task

    def authorize(self, task_id: str, *, authorization_ref: str) -> TransitionResult:
        if not authorization_ref.strip():
            raise AuthorizationRejected("authorization reference is required")
        return self.transition(task_id, "task.authorized", {"authorization_ref": authorization_ref})

    def commit_plan(self, plan: TeamPlan) -> TransitionResult:
        task = self._task(plan.task_id)
        self.validate_plan(task, plan)
        if plan.status != ContractStatus.proposed:
            raise PlanRejected("only proposed plans may be committed")
        return self.transition(plan.task_id, "task.plan.committed", {"team_id": plan.team_id, "plan_hash": plan.plan_version_hash})

    def commit_proposal(self, proposal: PlanProposal) -> TransitionResult:
        task = self._task(proposal.task_id)
        plan = self.plan_validator.validate(task, proposal)
        return self.commit_plan(plan)

    def validate_plan(self, task: TaskEnvelope, plan: TeamPlan) -> None:
        if plan.task_id != task.task_id:
            raise PlanRejected("plan task does not match envelope")
        if plan.concurrency_ceiling > task.resource_budget.get("max_concurrency", plan.concurrency_ceiling):
            raise PlanRejected("plan exceeds concurrency budget")
        if not set(plan.completion_criteria).issuperset(task.verification_criteria):
            raise PlanRejected("plan cannot remove task verification criteria")

    def validate_replan(self, original: TaskEnvelope, candidate: TaskEnvelope) -> None:
        if candidate.task_id != original.task_id or candidate.domain_pack_ref != original.domain_pack_ref:
            raise PlanRejected("replan cannot change task identity or domain pack")
        if _rank(candidate.clearance) > _rank(original.clearance):
            raise PlanRejected("replan cannot increase clearance")
        for field_name in ("allowed_evidence_scope", "permitted_worker_capabilities", "permitted_tools"):
            if not set(getattr(candidate, field_name)).issubset(getattr(original, field_name)):
                raise PlanRejected(f"replan cannot expand {field_name}")
        if not set(candidate.verification_criteria).issuperset(original.verification_criteria):
            raise PlanRejected("replan cannot remove verification criteria")
        for name, value in candidate.resource_budget.items():
            if value > original.resource_budget.get(name, 0):
                raise PlanRejected(f"replan cannot increase budget {name}")

    def transition(self, task_id: str, event_type: str, payload: dict[str, Any], *, timeout_ms: int = 60_000) -> TransitionResult:
        if timeout_ms <= 0 or timeout_ms > 86_400_000:
            raise StepTimeout("transition timeout must be 1..86400000 ms")
        state = self.state(task_id)
        allowed = _ALLOWED.get(event_type)
        if allowed is None:
            raise TransitionRejected(f"event {event_type} is not an orchestrator transition")
        if state not in allowed:
            raise TransitionRejected(f"{event_type} requires one of {sorted(allowed)}, got {state}")
        if event_type == "completion.recorded":
            criteria = payload.get("criteria")
            if not isinstance(criteria, dict) or not criteria or any(value is not True for value in criteria.values()):
                raise TransitionRejected("completion requires all criteria to be explicitly true")
        key = idempotency_key("orchestrator.transition", task_id, event_type, payload)
        existing = next((event for event in self.store.events if event.idempotency_key == key), None)
        if existing is not None:
            return TransitionResult(task_id, existing.event_id, event_type, self.state(task_id), existing.sequence, key, self._transaction_id(existing.event_id))
        result = self._append(event_type, task_id, payload, "OrchestratorTransition", key)
        if event_type not in {"task.failed", "task.cancelled"}:
            self._checkpoint(task_id, result)
        return result

    def execute_step(self, task_id: str, *, step_id: str, action: Callable[[], Any],
                     timeout_ms: int, max_attempts: int = 1, kind: str = "model",
                     result_payload: Callable[[Any, int], dict[str, Any]] | None = None,
                     dependency: str | None = None) -> StepResult:
        if timeout_ms <= 0 or max_attempts < 1 or kind not in {"model", "retrieval", "world_model", "verification", "tool"}:
            raise StepTimeout("step timeout and attempts must be positive")
        if dependency and dependency in self._circuit_open:
            raise CircuitOpen(f"circuit is open for {dependency}")
        request_event = "tool.requested" if kind == "tool" else f"{kind}.requested" if kind in {"retrieval", "world_model", "verification"} else "model.requested"
        self.transition(task_id, request_event, {"step_id": step_id, "timeout_ms": timeout_ms})
        for attempt in range(1, max_attempts + 1):
            started = time.monotonic()
            try:
                result = action()
                elapsed_ms = int((time.monotonic() - started) * 1000)
                if elapsed_ms > timeout_ms:
                    raise TimeoutError("step exceeded timeout")
                event_type = {"tool": "tool.result", "retrieval": "evidence.created",
                              "world_model": "fact.candidate", "verification": "verification.completed"}.get(kind, "model.responded")
                payload = result_payload(result, attempt) if result_payload else {"step_id": step_id, "attempt": attempt, "proposal": result}
                transition = self._append(event_type, task_id, payload, "ToolResult" if kind == "tool" else "ModelResult", idempotency_key("orchestrator.step.result", task_id, step_id, attempt))
                self._checkpoint(task_id, transition)
                return StepResult(task_id, step_id, attempt, result, transition)
            except TimeoutError as exc:
                if dependency:
                    self._record_dependency_failure(dependency)
                self._append("retry.started", task_id, {"step_id": step_id, "attempt": attempt, "reason": "timeout"}, "RetryRecord", idempotency_key("orchestrator.step.retry", task_id, step_id, attempt))
                if attempt == max_attempts:
                    self.transition(task_id, "task.failed", {"failure_code": "step_timeout", "step_id": step_id})
                    raise RetryExhausted(f"step {step_id} exhausted its retry budget") from exc
            except StorageFailure:
                raise
            except Exception as exc:
                if dependency:
                    self._record_dependency_failure(dependency)
                self._append("retry.started", task_id, {"step_id": step_id, "attempt": attempt, "reason": "step_failure"}, "RetryRecord", idempotency_key("orchestrator.step.retry", task_id, step_id, attempt))
                if attempt == max_attempts:
                    self.transition(task_id, "task.failed", {"failure_code": "step_failed", "step_id": step_id})
                    raise RetryExhausted(f"step {step_id} exhausted its retry budget") from exc
        raise RetryExhausted(f"step {step_id} exhausted its retry budget")

    def cancel(self, task_id: str, *, reason: str) -> TransitionResult:
        if not reason.strip():
            raise CancellationRequested("cancellation reason is required")
        return self.transition(task_id, "task.cancelled", {"reason": reason})

    def request_review(self, task_id: str, *, reason: str) -> TransitionResult:
        if not reason.strip():
            raise TransitionRejected("review reason is required")
        return self.transition(task_id, "human.review.required", {"reason": reason})

    def _record_dependency_failure(self, dependency: str) -> None:
        failures = self._circuit_failures.get(dependency, 0) + 1
        self._circuit_failures[dependency] = failures
        if failures >= 3:
            self._circuit_open.add(dependency)

    def state(self, task_id: str) -> str:
        state = "absent"
        for event in self.store.events:
            if event.task_id != task_id:
                continue
            target = _TARGETS.get(event.event_type)
            if isinstance(target, dict):
                target = target.get(event.payload.get("status"), "needs_review")
            if target is not None:
                state = target
        return state

    def _task(self, task_id: str) -> TaskEnvelope:
        for event in self.store.events:
            if event.task_id == task_id and event.event_type == "task.created":
                return TaskEnvelope.from_dict(event.payload["task"])
        raise TransitionRejected("task does not exist")

    def _append(self, event_type: str, task_id: str, payload: dict[str, Any], contract: str, key: str) -> TransitionResult:
        sequence = len(self.store.events)
        event = build_event(event_type=event_type, task_id=task_id, actor_id=self.actor_id,
                            actor_type="orchestrator", payload_contract=contract, payload_version="1.0",
                            payload=payload, clearance=self._task(task_id).clearance if event_type != "task.created" else Clearance.internal,
                            idempotency=key, sequence=sequence, previous_event_hash=self.store.head_hash)
        try:
            committed = self.store.append(event)
        except Exception as exc:
            raise StorageFailure("orchestrator transition was not committed") from exc
        transaction_id = committed.transaction_id if isinstance(committed, CommittedTransaction) else None
        return TransitionResult(task_id, event.event_id, event_type, self.state(task_id), event.sequence, key, transaction_id)

    def _checkpoint(self, task_id: str, result: TransitionResult) -> None:
        if isinstance(self.store, SQLiteLedgerStore) and result.transaction_id:
            try:
                self.store.checkpoint(checkpoint_id=stable_id("checkpoint", task_id, result.event_id), task_id=task_id, state=result.state, transaction_id=result.transaction_id)
            except Exception as exc:
                raise StorageFailure("transition committed but checkpoint failed; task must stop") from exc

    def _transaction_id(self, event_id: str) -> str | None:
        if not isinstance(self.store, SQLiteLedgerStore):
            return None
        row = self.store._db.execute("SELECT transaction_id FROM ledger_events WHERE event_id = ?", (event_id,)).fetchone()
        return row["transaction_id"] if row else None


def _rank(clearance: Clearance) -> int:
    return {Clearance.public: 0, Clearance.internal: 1, Clearance.restricted: 2, Clearance.secret: 3}[clearance]
