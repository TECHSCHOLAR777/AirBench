"""Cross-framework M8 gate used before an orchestrated completion transition."""
from __future__ import annotations
from dataclasses import dataclass
from contracts import EventLedger, Clearance, Taint, build_event, idempotency_key
from .autonomy import AuthorityDecision
from .independent import CompletionDecision
from ..knowledge.consistency import ConsistencyResult
from .runner import VerificationResult

@dataclass(frozen=True, slots=True)
class CrossFrameworkResult:
    task_id: str; outcome: str; reasons: tuple[str, ...]; ledger_event_id: str

class CrossFrameworkGate:
    def __init__(self, ledger: EventLedger) -> None: self.ledger = ledger
    def evaluate(self, task_id: str, verification: VerificationResult, evaluator: CompletionDecision, authority: AuthorityDecision, consistency: ConsistencyResult, *, clearance: Clearance = Clearance.internal, taint: Taint = Taint.clean) -> CrossFrameworkResult:
        reasons: list[str] = []
        if verification.outcome != "passed": reasons.append(f"verification is {verification.outcome}")
        if evaluator.outcome != "complete": reasons.append(f"completion gate is {evaluator.outcome}")
        if authority.outcome != "allow": reasons.append("authority escalation is unresolved")
        if consistency.deviation: reasons.append("consistency deviation requires review")
        outcome = "passed" if not reasons else "needs_review"; event_type = "completion.ready" if outcome == "passed" else "completion.blocked"
        payload = {"outcome": outcome, "reasons": reasons or ["all M8 gates passed"], "verification_ref": verification.verification_id, "evaluator_ref": evaluator.ledger_event_id, "authority_ref": authority.ledger_event_id, "consistency_ref": consistency.ledger_event_id, "team_agreement_cannot_override": True, "provenance": {"source_ref": f"task:{task_id}", "confidence": min(verification.confidence, 1.0), "clearance": clearance.value, "taint": taint.value}}
        self.ledger.append(build_event(event_type=event_type, task_id=task_id, actor_id="m8-gate", actor_type="orchestrator", payload_contract="CrossFrameworkResult", payload_version="1.0", payload=payload, clearance=clearance, idempotency=idempotency_key(event_type, task_id, verification.verification_id), sequence=len(self.ledger.events), previous_event_hash=self.ledger.head_hash))
        event = self.ledger.events[-1]
        return CrossFrameworkResult(task_id, outcome, tuple(payload["reasons"]), event.event_id)

__all__ = ["CrossFrameworkGate", "CrossFrameworkResult"]
