"""Deterministic, pack-driven autonomy and authority decisions."""
from __future__ import annotations
from dataclasses import dataclass
from contracts import Clearance, EventLedger, Taint, build_event, idempotency_key

@dataclass(frozen=True, slots=True)
class RiskRule:
    action_kind: str; harm: str; reversible: bool; required_authority: str; required_checks: tuple[str, ...] = (); confidence_floor: float = 0.5
    def __post_init__(self) -> None:
        if not self.action_kind or not self.required_authority or not 0 <= self.confidence_floor <= 1: raise ValueError("risk rule is incomplete or has an invalid confidence floor")
@dataclass(frozen=True, slots=True)
class ActionProposal:
    task_id: str; action_id: str; action_kind: str; worker_id: str; source_ref: str; confidence: float; clearance: Clearance; taint: Taint; claimed_risk: str | None = None
@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    task_id: str; action_id: str; outcome: str; required_authority: str; required_checks: tuple[str, ...]; reason: str; ledger_event_id: str

class AutonomyGovernor:
    def __init__(self, ledger: EventLedger, risk_rules: tuple[RiskRule, ...] = ()) -> None: self.ledger = ledger; self.rules = {rule.action_kind: rule for rule in risk_rules}
    def decide(self, proposal: ActionProposal) -> AuthorityDecision:
        rule = self.rules.get(proposal.action_kind)
        if rule is None: authority, checks, outcome, reason = "human", ("risk_rule",), "escalate", "no pack risk rule exists; unknown risk fails closed"
        elif proposal.worker_id.startswith("verification") and proposal.claimed_risk: authority, checks, outcome, reason = rule.required_authority, rule.required_checks, "escalate", "worker self-certification cannot determine authority"
        elif proposal.taint != Taint.clean or proposal.confidence < rule.confidence_floor: authority, checks, outcome, reason = rule.required_authority, rule.required_checks, "escalate", "tainted or low-confidence input requires authority review"
        elif rule.harm == "high" or not rule.reversible: authority, checks, outcome, reason = rule.required_authority, rule.required_checks, "escalate", "high-harm or irreversible action requires named authority"
        else: authority, checks, outcome, reason = "none", rule.required_checks, "allow", "pack rule permits a reversible, low-harm, sufficiently confident action"
        payload = {"action_id": proposal.action_id, "action_kind": proposal.action_kind, "outcome": outcome, "required_authority": authority, "required_checks": list(checks), "reason": reason, "worker_agreement_ignored": True, "provenance": {"source_ref": proposal.source_ref, "confidence": proposal.confidence, "clearance": proposal.clearance.value, "taint": proposal.taint.value}}
        event_type = "authority.decided" if outcome == "allow" else "escalation.required"
        self.ledger.append(build_event(event_type=event_type, task_id=proposal.task_id, actor_id="autonomy-governor", actor_type="policy", payload_contract="AuthorityDecision", payload_version="1.0", payload=payload, clearance=proposal.clearance, idempotency=idempotency_key(event_type, proposal.task_id, proposal.action_id), sequence=len(self.ledger.events), previous_event_hash=self.ledger.head_hash))
        event = self.ledger.events[-1]
        return AuthorityDecision(proposal.task_id, proposal.action_id, outcome, authority, checks, reason, event.event_id)

__all__ = ["ActionProposal", "AuthorityDecision", "AutonomyGovernor", "RiskRule"]
