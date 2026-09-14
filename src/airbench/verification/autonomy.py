"""Deterministic, pack-driven autonomy and authority decisions.

The governor turns a pack's action risk mappings and a proposed action into an
authority decision.  A model never grants itself authority: the decision is a
plain function of the pack rule, the input confidence and taint, and whether
the target object is declared safety-critical in the world model.

Every decision is written to the ledger as ``authority.decided`` (allow) or
``escalation.required`` (escalate).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from contracts import Clearance, EventLedger, Taint, build_event, idempotency_key

_SAFETY_TRUE = {"true", "1", "yes", "safety_critical", "high"}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _SAFETY_TRUE
    if isinstance(value, (int, float)):
        return value != 0
    return False


@dataclass(frozen=True, slots=True)
class RiskRule:
    action_kind: str; harm: str; reversible: bool; required_authority: str; required_checks: tuple[str, ...] = (); confidence_floor: float = 0.5

    def __post_init__(self) -> None:
        if not self.action_kind or not self.required_authority or not 0 <= self.confidence_floor <= 1:
            raise ValueError("risk rule is incomplete or has an invalid confidence floor")


@dataclass(frozen=True, slots=True)
class ActionProposal:
    task_id: str; action_id: str; action_kind: str; worker_id: str; source_ref: str; confidence: float; clearance: Clearance; taint: Taint; claimed_risk: str | None = None; target_object_id: str = ""


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    task_id: str; action_id: str; outcome: str; required_authority: str; required_checks: tuple[str, ...]; reason: str; ledger_event_id: str


def risk_rules_from_mappings(
    mappings: Sequence[Any],
    *,
    default_confidence_floor: float = 0.5,
) -> tuple[RiskRule, ...]:
    """Compile pack ``RiskMapping`` values into executable ``RiskRule`` values.

    A mapping is any object with ``action_kind``, ``reversibility`` and
    ``required_human_authority``.  Irreversible actions default to high harm,
    so they escalate even before the world-model check.
    """
    rules: list[RiskRule] = []
    for mapping in mappings:
        action_kind = str(getattr(mapping, "action_kind", "") or "").strip()
        if not action_kind:
            continue
        reversibility = str(getattr(mapping, "reversibility", "") or "").strip().lower()
        reversible = reversibility in {"reversible", "yes", "true"}
        harm = str(getattr(mapping, "harm", "") or "").strip().lower() or ("medium" if reversible else "high")
        authority = str(getattr(mapping, "required_human_authority", "") or "human").strip() or "human"
        raw_floor = getattr(mapping, "confidence_floor", None)
        floor = float(raw_floor) if raw_floor is not None else default_confidence_floor
        rules.append(RiskRule(
            action_kind=action_kind, harm=harm, reversible=reversible, required_authority=authority,
            required_checks=("risk_rule",), confidence_floor=floor,
        ))
    return tuple(rules)


class AutonomyGovernor:
    def __init__(self, ledger: EventLedger, risk_rules: tuple[RiskRule, ...] = ()) -> None:
        self.ledger = ledger
        self.rules = {rule.action_kind: rule for rule in risk_rules}

    def score(
        self,
        proposal: ActionProposal,
        *,
        world_model: Any = None,
        safety_attribute: str = "safety_critical",
    ) -> AuthorityDecision:
        """Score an action, escalating if its target object is safety-critical."""
        forced: str | None = None
        if world_model is not None and proposal.target_object_id:
            if self._is_safety_critical(world_model, proposal.target_object_id, safety_attribute):
                forced = "target object is declared safety-critical in the world model"
        return self.decide(proposal, force_escalation_reason=forced)

    @staticmethod
    def _is_safety_critical(world_model: Any, target_object_id: str, attribute: str) -> bool:
        for fact in getattr(world_model, "facts", ()) or ():
            value = fact.value if isinstance(fact.value, dict) else {}
            identities = {fact.fact_id, str(value.get("entity_id", ""))}
            if target_object_id not in identities:
                continue
            attributes = value.get("attributes")
            if isinstance(attributes, dict) and _truthy(attributes.get(attribute)):
                return True
            if _truthy(value.get(attribute)):
                return True
        return False

    def decide(self, proposal: ActionProposal, *, force_escalation_reason: str | None = None) -> AuthorityDecision:
        rule = self.rules.get(proposal.action_kind)
        if force_escalation_reason is not None:
            authority = rule.required_authority if rule is not None else "human"
            checks = rule.required_checks if rule is not None else ("risk_rule",)
            outcome, reason = "escalate", force_escalation_reason
        elif rule is None:
            authority, checks, outcome, reason = "human", ("risk_rule",), "escalate", "no pack risk rule exists; unknown risk fails closed"
        elif proposal.worker_id.startswith("verification") and proposal.claimed_risk:
            authority, checks, outcome, reason = rule.required_authority, rule.required_checks, "escalate", "worker self-certification cannot determine authority"
        elif proposal.taint != Taint.clean or proposal.confidence < rule.confidence_floor:
            authority, checks, outcome, reason = rule.required_authority, rule.required_checks, "escalate", "tainted or low-confidence input requires authority review"
        elif rule.harm == "high" or not rule.reversible:
            authority, checks, outcome, reason = rule.required_authority, rule.required_checks, "escalate", "high-harm or irreversible action requires named authority"
        else:
            authority, checks, outcome, reason = "system", rule.required_checks, "allow", "pack rule permits a reversible, low-harm, sufficiently confident action"
        payload = {"action_id": proposal.action_id, "action_kind": proposal.action_kind, "outcome": outcome, "required_authority": authority, "required_checks": list(checks), "reason": reason, "worker_agreement_ignored": True, "target_object_id": proposal.target_object_id, "provenance": {"source_ref": proposal.source_ref, "confidence": proposal.confidence, "clearance": proposal.clearance.value, "taint": proposal.taint.value}}
        event_type = "authority.decided" if outcome == "allow" else "escalation.required"
        event_key = idempotency_key(event_type, proposal.task_id, proposal.action_id)
        for existing in reversed(self.ledger.events):
            if existing.event_type == event_type and existing.task_id == proposal.task_id and existing.payload.get("action_id") == proposal.action_id:
                existing_payload = existing.payload
                return AuthorityDecision(
                    proposal.task_id,
                    proposal.action_id,
                    str(existing_payload.get("outcome", outcome)),
                    str(existing_payload.get("required_authority", authority)),
                    tuple(str(item) for item in existing_payload.get("required_checks", checks)),
                    str(existing_payload.get("reason", reason)),
                    existing.event_id,
                )
        committed = self.ledger.append(build_event(event_type=event_type, task_id=proposal.task_id, actor_id="autonomy-governor", actor_type="policy", payload_contract="AuthorityDecision", payload_version="1.0", payload=payload, clearance=proposal.clearance, idempotency=event_key, sequence=len(self.ledger), previous_event_hash=self.ledger.head_hash))
        # In-memory ledgers return the committed event; sealed SQLite ledgers
        # return a transaction envelope.  Preserve the same event reference
        # across both implementations.
        event_ref = getattr(committed, "event_id", None)
        if not isinstance(event_ref, str):
            event_ids = getattr(committed, "event_ids", ())
            event_ref = event_ids[-1] if event_ids else ""
        return AuthorityDecision(proposal.task_id, proposal.action_id, outcome, authority, checks, reason, event_ref)


__all__ = ["ActionProposal", "AuthorityDecision", "AutonomyGovernor", "RiskRule", "risk_rules_from_mappings"]
