from __future__ import annotations

from dataclasses import dataclass

from airbench.knowledge.world_model import CandidateFact, CandidateFactWriter, WorldModelStore, candidate_id
from airbench.verification.autonomy import (
    ActionProposal,
    AutonomyGovernor,
    RiskRule,
    risk_rules_from_mappings,
)
from contracts import Clearance, EventLedger, FactEnvelope, Taint, build_event


@dataclass(frozen=True)
class _Mapping:
    action_kind: str
    risk_class: str
    reversibility: str
    required_human_authority: str


def _ledger(task_id: str = "task.m711") -> EventLedger:
    ledger = EventLedger()
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
        clearance=Clearance.internal, idempotency=f"created-{task_id}", sequence=0,
    ))
    return ledger


def _proposal(**overrides) -> ActionProposal:
    base = dict(
        task_id="task.m711", action_id="action.1", action_kind="prepare_approval_note",
        worker_id="worker.reasoning", source_ref="proposal.1", confidence=0.9,
        clearance=Clearance.internal, taint=Taint.clean,
    )
    base.update(overrides)
    return ActionProposal(**base)


def _low_risk_rule() -> RiskRule:
    return RiskRule(action_kind="prepare_approval_note", harm="medium", reversible=True, required_authority="human_reviewer")


class TestRiskRuleCompilation:
    def test_reversible_action_defaults_to_medium_harm(self) -> None:
        rules = risk_rules_from_mappings([_Mapping("prepare_approval_note", "regulated_document_draft", "reversible", "human_reviewer")])
        assert rules[0].reversible is True
        assert rules[0].harm == "medium"
        assert rules[0].required_authority == "human_reviewer"

    def test_irreversible_action_defaults_to_high_harm_and_escalates(self) -> None:
        rules = risk_rules_from_mappings([_Mapping("release_approval_note", "organizational_decision", "non_reversible", "authorized_approver")])
        assert rules[0].reversible is False
        assert rules[0].harm == "high"
        decision = AutonomyGovernor(_ledger(), rules).decide(_proposal(action_kind="release_approval_note"))
        assert decision.outcome == "escalate"
        assert decision.required_authority == "authorized_approver"


class TestAutonomyDecision:
    def test_low_risk_action_is_allowed_with_system_authority(self) -> None:
        ledger = _ledger()
        decision = AutonomyGovernor(ledger, (_low_risk_rule(),)).decide(_proposal())
        assert decision.outcome == "allow"
        assert decision.required_authority == "system"
        assert decision.reason.strip() and decision.reason != "unknown"
        assert ledger.events[-1].event_type == "authority.decided"
        assert ledger.events[-1].payload["required_authority"] == "system"

    def test_unknown_risk_rule_escalates(self) -> None:
        ledger = _ledger()
        decision = AutonomyGovernor(ledger).decide(_proposal(action_kind="mystery"))
        assert decision.outcome == "escalate"
        assert "fails closed" in decision.reason
        assert ledger.events[-1].event_type == "escalation.required"

    def test_tainted_or_low_confidence_input_escalates(self) -> None:
        governor = AutonomyGovernor(_ledger(), (_low_risk_rule(),))
        assert governor.decide(_proposal(action_id="action.tainted", taint=Taint.untrusted)).outcome == "escalate"
        assert governor.decide(_proposal(action_id="action.lowconf", confidence=0.1)).outcome == "escalate"

    def test_verification_worker_self_certification_escalates(self) -> None:
        governor = AutonomyGovernor(_ledger(), (_low_risk_rule(),))
        decision = governor.decide(_proposal(worker_id="verification.worker", claimed_risk="low"))
        assert decision.outcome == "escalate"
        assert "self-certification" in decision.reason


class TestWorldModelSafetyOverride:
    def _world_model(self) -> WorldModelStore:
        store = WorldModelStore()
        fact = FactEnvelope(
            fact_id="fact.pump.safety", value={"entity_id": "equipment.P-101", "object_type": "equipment", "attributes": {"tag": "P-101", "safety_critical": "true"}},
            source_ref="upload:report.pdf#page-1", confidence=0.9, clearance=Clearance.internal,
            taint=Taint.untrusted, extraction_method="entity_extractor:fixture",
            observed_at="2026-01-01T00:00:00Z", ingested_at="2026-01-01T00:00:01Z",
        )
        candidate = CandidateFact(candidate_id("task.m711", fact), "task.m711", fact, ("evidence.1",), "consistency.1", "verification.1")
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True)
        writer.stage(candidate)
        writer.commit(candidate.candidate_id)
        return store

    def test_safety_critical_object_forces_escalation(self) -> None:
        governor = AutonomyGovernor(_ledger(), (_low_risk_rule(),))
        decision = governor.score(_proposal(target_object_id="equipment.P-101"), world_model=self._world_model())
        assert decision.outcome == "escalate"
        assert "safety-critical" in decision.reason

    def test_low_risk_object_without_attribute_is_allowed(self) -> None:
        store = WorldModelStore()
        fact = FactEnvelope(
            fact_id="fact.valve.1", value={"entity_id": "equipment.V-1", "object_type": "equipment", "attributes": {"tag": "V-1"}},
            source_ref="upload:report.pdf#page-1", confidence=0.9, clearance=Clearance.internal,
            taint=Taint.untrusted, extraction_method="entity_extractor:fixture",
            observed_at="2026-01-01T00:00:00Z", ingested_at="2026-01-01T00:00:01Z",
        )
        candidate = CandidateFact(candidate_id("task.m711", fact), "task.m711", fact, ("evidence.1",), "consistency.1", "verification.1")
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True)
        writer.stage(candidate)
        writer.commit(candidate.candidate_id)
        governor = AutonomyGovernor(_ledger(), (_low_risk_rule(),))
        decision = governor.score(_proposal(target_object_id="equipment.V-1"), world_model=store)
        assert decision.outcome == "allow"
