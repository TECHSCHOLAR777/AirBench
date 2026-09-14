from __future__ import annotations

from dataclasses import replace

import pytest

from airbench.knowledge.graph_store import SqliteGraphStore, build_graph_store_from_env
from airbench.knowledge.world_model import (
    CandidateFact,
    CandidateFactWriter,
    WorldModelError,
    WorldModelQuery,
    WorldModelRelation,
    WorldModelStore,
    candidate_id,
)
from contracts import Clearance, EventLedger, FactEnvelope, Taint, build_event


def _seed(ledger: EventLedger, task_id: str) -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
        clearance=Clearance.restricted, idempotency=f"created-{task_id}", sequence=0,
    ))


def _fact(*, fact_id: str = "fact.pump.1", confidence: float = 0.9, supersedes: str | None = None) -> FactEnvelope:
    return FactEnvelope(
        fact_id=fact_id, value={"entity_id": fact_id, "object_type": "equipment", "attributes": {"tag": "P-101"}},
        source_ref="upload:report.pdf#page-1", confidence=confidence, clearance=Clearance.internal,
        taint=Taint.untrusted, extraction_method="entity_extractor:fixture",
        observed_at="2026-01-01T00:00:00Z", ingested_at="2026-01-01T00:00:01Z", supersedes_fact_id=supersedes,
    )


def _candidate(fact: FactEnvelope, relations: tuple[WorldModelRelation, ...] = ()) -> CandidateFact:
    identity = candidate_id("task.m79", fact)
    return CandidateFact(identity, "task.m79", fact, ("evidence.1",), "consistency.1", "verification.1", relations)


class TestSqliteGraphStore:
    def test_restart_preserves_facts_and_relations(self, tmp_path) -> None:
        path = tmp_path / "world.sqlite"
        first = WorldModelStore(backend=SqliteGraphStore(path))
        writer = CandidateFactWriter(first, consistency_gate=lambda _: True, verification_gate=lambda _: True)
        target = _fact(fact_id="fact.valve.1")
        relation = WorldModelRelation(
            relation_id="relation.pump-valve", source_fact_id="fact.pump.1", relation="downstream",
            target_fact_id="fact.valve.1", source_ref=target.source_ref, confidence=0.8,
            clearance=Clearance.internal, taint=Taint.untrusted,
        )
        source = _candidate(_fact())
        writer.stage(source)
        writer.commit(source.candidate_id)
        linked = _candidate(target, (relation,))
        writer.stage(linked)
        writer.commit(linked.candidate_id)

        reopened = SqliteGraphStore(path)
        restored = WorldModelStore(backend=reopened)
        assert {fact.fact_id for fact in restored.facts} == {"fact.pump.1", "fact.valve.1"}
        assert len(restored.relations) == 1
        result = restored.query(WorldModelQuery("task.m79", clearance=Clearance.internal, entity_id="fact.pump.1", relation="downstream"))
        assert [fact.fact_id for fact in result] == ["fact.valve.1"]
        history = reopened.history()
        assert {row["fact_id"] for row in history} == {"fact.pump.1", "fact.valve.1"}

    def test_unchanged_fact_is_not_recorded_twice(self, tmp_path) -> None:
        store = SqliteGraphStore(tmp_path / "world.sqlite")
        world = WorldModelStore(backend=store)
        writer = CandidateFactWriter(world, consistency_gate=lambda _: True, verification_gate=lambda _: True)
        item = _fact()
        candidate = _candidate(item)
        writer.stage(candidate)
        writer.commit(candidate.candidate_id)
        first_history = len(store.history())
        world._persist()
        assert len(store.history()) == first_history
        assert store.node_count == 1

    def test_env_selection(self, tmp_path) -> None:
        assert build_graph_store_from_env({}) is None
        store = build_graph_store_from_env({"AIRBENCH_WORLD_MODEL_BACKEND": "sqlite", "AIRBENCH_WORLD_MODEL_PATH": str(tmp_path / "w.sqlite")})
        assert isinstance(store, SqliteGraphStore)
        with pytest.raises(WorldModelError):
            build_graph_store_from_env({"AIRBENCH_WORLD_MODEL_BACKEND": "sqlite"})
        with pytest.raises(WorldModelError):
            build_graph_store_from_env({"AIRBENCH_WORLD_MODEL_BACKEND": "mystery"})


class TestReconciliation:
    def test_low_confidence_candidate_is_queued_not_committed(self) -> None:
        ledger = EventLedger()
        _seed(ledger, "task.m79")
        store = WorldModelStore(ledger=ledger)
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True, ledger=ledger)
        candidate = _candidate(_fact(confidence=0.4))
        writer.stage(candidate)
        with pytest.raises(WorldModelError) as caught:
            writer.reconcile(candidate.candidate_id, review_floor=0.6)
        assert caught.value.code == "review_required"
        assert store.facts == ()
        assert [item.candidate.candidate_id for item in store.review_queue] == [candidate.candidate_id]
        assert ledger.events[-1].event_type == "world_model.review_required"

    def test_review_accept_commits_and_reject_tombstones(self) -> None:
        ledger = EventLedger()
        _seed(ledger, "task.m79")
        store = WorldModelStore(ledger=ledger)
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True, ledger=ledger)
        accepted = _candidate(_fact(fact_id="fact.a", confidence=0.4))
        rejected = _candidate(_fact(fact_id="fact.b", confidence=0.4))
        writer.stage(accepted)
        writer.stage(rejected)
        with pytest.raises(WorldModelError):
            writer.reconcile(accepted.candidate_id, review_floor=0.6)
        with pytest.raises(WorldModelError):
            writer.reconcile(rejected.candidate_id, review_floor=0.6)

        assert store.resolve_review(accepted.candidate_id, accept=True).fact_id == "fact.a"
        assert store.resolve_review(rejected.candidate_id, accept=False) is None
        assert {fact.fact_id for fact in store.facts} == {"fact.a"}
        assert [event.event_type for event in ledger.events].count("world_model.review_resolved") == 2
        with pytest.raises(WorldModelError):
            store.resolve_review("candidate.missing", accept=True)

    def test_supersession_emits_conflict_and_hides_old_fact(self) -> None:
        ledger = EventLedger()
        _seed(ledger, "task.m79")
        store = WorldModelStore(ledger=ledger)
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True, ledger=ledger)
        original = _candidate(_fact(fact_id="fact.pump.1"))
        writer.stage(original)
        writer.reconcile(original.candidate_id, review_floor=0.0)
        newer = _candidate(_fact(fact_id="fact.pump.2", supersedes="fact.pump.1"))
        writer.stage(newer)
        writer.reconcile(newer.candidate_id, review_floor=0.0)

        assert "world_model.conflict" in [event.event_type for event in ledger.events]
        assert len(store.facts) == 2
        assert [fact.fact_id for fact in store.query(WorldModelQuery("task.m79"))] == ["fact.pump.2"]


class TestAsOfQuery:
    def _store(self) -> WorldModelStore:
        store = WorldModelStore()
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True)
        older = replace(_fact(fact_id="fact.pump.1"), ingested_at="2026-01-01T00:00:00Z")
        newer = replace(_fact(fact_id="fact.pump.2", supersedes="fact.pump.1"), ingested_at="2026-03-01T00:00:00Z")
        for item in (older, newer):
            candidate = _candidate(item)
            writer.stage(candidate)
            writer.commit(candidate.candidate_id)
        return store

    def test_as_of_returns_the_then_current_fact(self) -> None:
        store = self._store()
        before = store.query(WorldModelQuery("task.m79", as_of="2026-02-01T00:00:00Z"))
        after = store.query(WorldModelQuery("task.m79", as_of="2026-04-01T00:00:00Z"))
        assert [fact.fact_id for fact in before] == ["fact.pump.1"]
        assert [fact.fact_id for fact in after] == ["fact.pump.2"]

    def test_missing_as_of_returns_current_graph(self) -> None:
        store = self._store()
        assert [fact.fact_id for fact in store.query(WorldModelQuery("task.m79"))] == ["fact.pump.2"]

    def test_valid_window_excludes_not_yet_valid_and_expired_facts(self) -> None:
        store = WorldModelStore()
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True)
        fact = replace(
            _fact(fact_id="fact.pump.window"),
            ingested_at="2026-01-01T00:00:00Z",
            valid_from="2026-02-01T00:00:00Z",
            valid_to="2026-03-01T00:00:00Z",
        )
        candidate = _candidate(fact)
        writer.stage(candidate)
        writer.commit(candidate.candidate_id)
        assert store.query(WorldModelQuery("task.m79", as_of="2026-01-15T00:00:00Z")) == ()
        assert [f.fact_id for f in store.query(WorldModelQuery("task.m79", as_of="2026-02-15T00:00:00Z"))] == ["fact.pump.window"]
        assert store.query(WorldModelQuery("task.m79", as_of="2026-04-01T00:00:00Z")) == ()

    def test_invalid_as_of_is_rejected(self) -> None:
        with pytest.raises(WorldModelError):
            WorldModelQuery("task.m79", as_of="not-a-time")
