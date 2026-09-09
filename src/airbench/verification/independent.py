"""Fresh-context evaluator and fail-closed completion gates."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Protocol
from contracts import Clearance, EventLedger, Taint, idempotency_key, build_event

class EvaluatorUnavailable(RuntimeError):
    """The independent evaluator could not safely run."""

@dataclass(frozen=True, slots=True)
class EvaluatorInput:
    task_id: str; evaluation_id: str; generator_worker_id: str; evaluator_worker_id: str
    proposal_ref: str; work_packet_refs: tuple[str, ...]; evidence_refs: tuple[str, ...]
    completion_criteria: tuple[str, ...]; clearance: Clearance; confidence: float; taint: Taint
    def __post_init__(self) -> None:
        if not self.task_id or not self.evaluation_id or not self.proposal_ref: raise ValueError("evaluator identity and proposal reference are required")
        if self.generator_worker_id == self.evaluator_worker_id: raise ValueError("generator and evaluator must be independent workers")
        if not self.completion_criteria: raise ValueError("completion criteria are required")
        if not 0 <= self.confidence <= 1: raise ValueError("confidence must be between zero and one")

@dataclass(frozen=True, slots=True)
class EvaluatorResult:
    evaluation_id: str; task_id: str; outcome: str; criteria: tuple[tuple[str, bool], ...]
    reason: str; confidence: float; clearance: Clearance; taint: Taint; evaluator_worker_id: str
    ledger_event_ids: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        if self.outcome not in {"passed", "failed", "needs_review"}: raise ValueError("invalid evaluator outcome")
        if not 0 <= self.confidence <= 1: raise ValueError("confidence must be between zero and one")

class Evaluator(Protocol):
    def __call__(self, request: EvaluatorInput) -> EvaluatorResult: ...

def _append(ledger: EventLedger, event_type: str, request: EvaluatorInput, payload: dict) -> object:
    provenance = {"source_ref": request.proposal_ref, "confidence": request.confidence, "clearance": request.clearance.value, "taint": request.taint.value}
    ledger.append(build_event(event_type=event_type, task_id=request.task_id, actor_id=request.evaluator_worker_id, actor_type="verification_worker", payload_contract="EvaluatorResult", payload_version="1.0", payload={**payload, "provenance": provenance}, clearance=request.clearance, idempotency=idempotency_key(event_type, request.task_id, request.evaluation_id), sequence=len(ledger.events), previous_event_hash=ledger.head_hash))
    return ledger.events[-1]

class IndependentEvaluator:
    """Evaluate a proposal from a fresh, separately identified worker context."""
    def __init__(self, ledger: EventLedger, evaluator: Evaluator | None = None, *, evaluator_worker_id: str = "verification-worker") -> None:
        self.ledger = ledger; self.evaluator = evaluator; self.evaluator_worker_id = evaluator_worker_id
    def evaluate(self, request: EvaluatorInput) -> EvaluatorResult:
        if request.evaluator_worker_id != self.evaluator_worker_id: raise EvaluatorUnavailable("request evaluator does not match qualified evaluator")
        requested = _append(self.ledger, "verification.evaluator.requested", request, {"evaluation_id": request.evaluation_id, "proposal_ref": request.proposal_ref, "criteria": list(request.completion_criteria), "fresh_context": True})
        if self.evaluator is None:
            result = EvaluatorResult(request.evaluation_id, request.task_id, "needs_review", tuple((criterion, False) for criterion in request.completion_criteria), "independent evaluator is unavailable", 0.0, request.clearance, request.taint, request.evaluator_worker_id)
        else:
            try: result = self.evaluator(request)
            except Exception as exc: result = EvaluatorResult(request.evaluation_id, request.task_id, "needs_review", tuple((criterion, False) for criterion in request.completion_criteria), f"independent evaluator failed: {type(exc).__name__}", 0.0, request.clearance, request.taint, request.evaluator_worker_id)
            if result.evaluator_worker_id == request.generator_worker_id: raise EvaluatorUnavailable("evaluator result was produced by the generator")
        completed = _append(self.ledger, "verification.evaluator.completed", request, {"evaluation_id": result.evaluation_id, "outcome": result.outcome, "criteria": dict(result.criteria), "reason": result.reason})
        return EvaluatorResult(result.evaluation_id, result.task_id, result.outcome, result.criteria, result.reason, result.confidence, result.clearance, result.taint, result.evaluator_worker_id, (requested.event_id, completed.event_id))

@dataclass(frozen=True, slots=True)
class CompletionDecision:
    task_id: str; outcome: str; reason: str; criteria: tuple[tuple[str, bool], ...]; ledger_event_id: str

class CompletionGate:
    """Default-fail completion gate; worker agreement is never an input."""
    def __init__(self, ledger: EventLedger) -> None: self.ledger = ledger
    def decide(self, request: EvaluatorInput, result: EvaluatorResult, *, deterministic_checks: dict[str, str], evidence_refs: tuple[str, ...]) -> CompletionDecision:
        criteria = dict(result.criteria); reasons: list[str] = []
        if not evidence_refs: reasons.append("required evidence is missing")
        if result.outcome != "passed": reasons.append(f"independent evaluator outcome is {result.outcome}")
        if result.confidence < request.confidence: reasons.append("evaluator confidence is below the input confidence floor")
        if any(value != "passed" for value in deterministic_checks.values()): reasons.append("a deterministic check did not pass")
        if not criteria or not all(criteria.values()): reasons.append("not all completion criteria passed")
        outcome = "complete" if not reasons else "needs_review"; reason = "all independent and deterministic gates passed" if not reasons else "; ".join(reasons)
        event_type = "completion.ready" if outcome == "complete" else "completion.blocked"
        event = _append(self.ledger, event_type, request, {"evaluation_id": result.evaluation_id, "outcome": outcome, "reason": reason, "criteria": criteria, "deterministic_checks": deterministic_checks, "evidence_refs": list(evidence_refs), "worker_agreement_ignored": True})
        return CompletionDecision(request.task_id, outcome, reason, tuple(sorted(criteria.items())), event.event_id)

__all__ = ["CompletionDecision", "CompletionGate", "EvaluatorInput", "EvaluatorResult", "EvaluatorUnavailable", "IndependentEvaluator"]
