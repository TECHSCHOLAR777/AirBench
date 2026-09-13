from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from airbench.node.autonomy_gateway import select_execution_action_kind
from airbench.node.pack_loader import PackLoader
from airbench.verification.autonomy import ActionProposal, AutonomyGovernor, risk_rules_from_mappings
from contracts import Clearance, EventLedger, Taint, build_event

REPO_ROOT = Path(__file__).resolve().parents[1]
REFINERY_PACK = REPO_ROOT / "packs" / "refinery_psu_v0"


@dataclass(frozen=True)
class _Mapping:
    action_kind: str
    reversibility: str


def _seed(ledger: EventLedger, task_id: str = "task.gate") -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
        clearance=Clearance.internal, idempotency=f"created-{task_id}", sequence=0,
    ))


class TestSelectExecutionActionKind:
    def test_override_wins(self) -> None:
        assert select_execution_action_kind([], "custom_action") == "custom_action"

    def test_non_reversible_mapping_is_selected_first(self) -> None:
        mappings = (
            _Mapping("prepare_approval_note", "reversible"),
            _Mapping("release_approval_note", "non_reversible"),
        )
        assert select_execution_action_kind(mappings) == "release_approval_note"

    def test_reversible_only_falls_back_to_first(self) -> None:
        assert select_execution_action_kind((_Mapping("prepare_approval_note", "reversible"),)) == "prepare_approval_note"

    def test_empty_mappings_use_neutral_default(self) -> None:
        assert select_execution_action_kind(()) == "task_execution"

    def test_real_pack_selects_the_release_action(self) -> None:
        pack = PackLoader(allow_unsigned=True).load(REFINERY_PACK)
        assert select_execution_action_kind(pack.risk_mappings) == "release_approval_note"


class TestExecutionGateGovernor:
    """The selected pack action must be governed, and the old neutral name must not be."""

    def test_selected_release_action_is_governed(self) -> None:
        ledger = EventLedger()
        _seed(ledger)
        pack = PackLoader(allow_unsigned=True).load(REFINERY_PACK)
        governor = AutonomyGovernor(ledger, risk_rules_from_mappings(pack.risk_mappings))
        action_kind = select_execution_action_kind(pack.risk_mappings)
        decision = governor.decide(ActionProposal(
            "task.gate", "action.gate", action_kind, "node.execution", "intake:report.pdf",
            0.95, Clearance.internal, Taint.clean,
        ))
        assert decision.outcome == "escalate"
        assert decision.required_authority == "authorized_approver"

    def test_old_neutral_name_would_have_failed_closed(self) -> None:
        ledger = EventLedger()
        _seed(ledger)
        decision = AutonomyGovernor(ledger, ()).decide(ActionProposal(
            "task.gate", "action.gate", "task_execution", "node.execution", "intake:report.pdf",
            0.95, Clearance.internal, Taint.clean,
        ))
        assert decision.outcome == "escalate"
        assert "fails closed" in decision.reason
