from __future__ import annotations

from pathlib import Path

import pytest

from airbench.knowledge.consistency import ConsistencyEngine, DecisionRecord
from airbench.knowledge.decision_store import DecisionStoreError, SqliteDecisionStore, build_decision_store_from_env
from contracts import Clearance, EventLedger, build_event

TASK = "task.m710"
OBJECT = "equipment.P-101"
TYPE = "approval_note_review_status"


def _seed(ledger: EventLedger, task_id: str = TASK) -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
        clearance=Clearance.restricted, idempotency=f"created-{task_id}", sequence=0,
    ))


def _record(decision_id: str, features: dict[str, str], *, decision: str = "approved", current: bool = True,
            rule_current: bool = True, authority_current: bool = True, decision_type: str = TYPE) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id, task_id=TASK, decision_type=decision_type, object_id=OBJECT,
        features=tuple(sorted(features.items())), decision=decision, rule_ref="pack.rule.1",
        authority="human_reviewer", current=current, rule_current=rule_current, authority_current=authority_current,
    )


class TestDecisionStore:
    def test_record_and_find_comparable(self, tmp_path) -> None:
        store = SqliteDecisionStore(tmp_path / "decisions.sqlite")
        store.record(_record("decision.1", {"severity": "low", "tag": "P-101"}))
        comparable = store.find_comparable(TYPE, OBJECT)
        assert [item.decision_id for item in comparable] == ["decision.1"]
        assert dict(comparable[0].features) == {"severity": "low", "tag": "P-101"}
        assert store.find_comparable(TYPE, "equipment.other") == ()

    def test_new_decision_supersedes_prior_for_the_same_object(self, tmp_path) -> None:
        store = SqliteDecisionStore(tmp_path / "decisions.sqlite")
        store.record(_record("decision.1", {"severity": "low"}))
        store.record(_record("decision.2", {"severity": "high"}))
        records = {item.decision_id: item for item in store.find_comparable(TYPE, OBJECT)}
        assert records["decision.1"].current is False
        assert records["decision.2"].current is True
        assert store.count == 2

    def test_env_selection(self, tmp_path) -> None:
        assert build_decision_store_from_env({}) is None
        store = build_decision_store_from_env({"AIRBENCH_DECISION_STORE_PATH": str(tmp_path / "d.sqlite")})
        assert isinstance(store, SqliteDecisionStore)
        with pytest.raises(DecisionStoreError):
            store.find_comparable("", OBJECT)


class TestConsistencyEvaluate:
    def _engine(self) -> ConsistencyEngine:
        ledger = EventLedger()
        _seed(ledger)
        return ConsistencyEngine(ledger)

    def test_identical_decision_is_consistent(self, tmp_path) -> None:
        store = SqliteDecisionStore(tmp_path / "d.sqlite")
        store.record(_record("decision.1", {"severity": "low", "tag": "P-101"}))
        result = self._engine().evaluate(
            _record("decision.2", {"severity": "low", "tag": "P-101"}),
            store=store, material_features=("severity",),
        )
        assert result.deviation is False
        assert result.comparable_ids == ("decision.1",)
        assert "consistent" in result.reason

    def test_material_difference_triggers_deviation(self, tmp_path) -> None:
        store = SqliteDecisionStore(tmp_path / "d.sqlite")
        store.record(_record("decision.1", {"severity": "low", "tag": "P-101"}))
        result = self._engine().evaluate(
            _record("decision.3", {"severity": "high", "tag": "P-101"}),
            store=store, material_features=("severity",),
        )
        assert result.deviation is True
        assert ("severity", "low", "high") in result.material_differences

    def test_non_material_difference_is_not_a_deviation(self, tmp_path) -> None:
        store = SqliteDecisionStore(tmp_path / "d.sqlite")
        store.record(_record("decision.1", {"severity": "low", "note": "first"}))
        result = self._engine().evaluate(
            _record("decision.4", {"severity": "low", "note": "second"}),
            store=store, material_features=("severity",),
        )
        assert result.deviation is False

    def test_no_comparable_decisions_is_not_a_deviation(self, tmp_path) -> None:
        store = SqliteDecisionStore(tmp_path / "d.sqlite")
        result = self._engine().evaluate(_record("decision.5", {"severity": "low"}), store=store, material_features=("severity",))
        assert result.deviation is False
        assert result.comparable_ids == ()
        assert "no comparable" in result.reason

    def test_stale_rule_or_authority_is_superseded_not_comparable(self) -> None:
        ledger = EventLedger()
        _seed(ledger)
        active = _record("decision.active", {"severity": "low"})
        stale = _record("decision.stale", {"severity": "low"}, rule_current=False)
        engine = ConsistencyEngine(ledger, history=(active, stale))
        result = engine.evaluate(_record("decision.new", {"severity": "low"}), material_features=("severity",))
        assert result.comparable_ids == ("decision.active",)
        assert result.superseded_ids == ("decision.stale",)
        assert result.deviation is False

    def test_recording_uses_injected_store(self, tmp_path) -> None:
        store = SqliteDecisionStore(tmp_path / "d.sqlite")
        engine = self._engine()
        assert engine.record(_record("decision.6", {"severity": "low"}), store=store) == "decision.6"
        assert store.count == 1
