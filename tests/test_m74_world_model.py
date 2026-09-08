from __future__ import annotations

import unittest
from dataclasses import replace
from tempfile import TemporaryDirectory

from airbench.world_model import CandidateFact, CandidateFactWriter, WorldModelQuery, WorldModelRelation, WorldModelStore, WorldModelError, candidate_id
from contracts import Clearance, EventLedger, FactEnvelope, ProjectionBuilder, Taint, build_event, verify_projection_export


def seed_task(ledger: EventLedger, task_id: str) -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
        clearance=Clearance.restricted, idempotency=f"created-{task_id}", sequence=0,
    ))


def fact(*, clearance: Clearance = Clearance.internal) -> FactEnvelope:
    return FactEnvelope(
        fact_id="fact.pump.1", value={"pressure": 12}, source_ref="upload:report.pdf#page-1",
        confidence=.91, clearance=clearance, taint=Taint.untrusted, extraction_method="retrieval",
        observed_at="2026-01-01T00:00:00Z", ingested_at="2026-01-01T00:00:01Z",
    )


def named_fact(fact_id: str) -> FactEnvelope:
    return FactEnvelope(
        fact_id=fact_id, value={"entity": fact_id}, source_ref="upload:graph.pdf#page-1",
        confidence=.9, clearance=Clearance.internal, taint=Taint.untrusted, extraction_method="retrieval",
        observed_at="2026-01-01T00:00:00Z", ingested_at="2026-01-01T00:00:01Z",
    )


class WorldModelTests(unittest.TestCase):
    def test_candidate_requires_both_gates_before_query_visibility(self) -> None:
        ledger = EventLedger()
        seed_task(ledger, "task.m74")
        store = WorldModelStore(ledger=ledger)
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True, ledger=ledger)
        candidate = CandidateFact(candidate_id("task.m74", fact()), "task.m74", fact(), ("citation.1",), "consistency.1", "verification.1")
        writer.stage(candidate)
        self.assertEqual(store.query(WorldModelQuery("task.m74")), ())
        committed = writer.commit(candidate.candidate_id)
        self.assertEqual(committed.fact_id, "fact.pump.1")
        self.assertEqual(store.query(WorldModelQuery("task.m74", key="pressure"))[0].value["pressure"], 12)
        self.assertEqual(
            [event.event_type for event in ledger.events],
            ["task.created", "fact.candidate", "world_model.requested", "fact.committed", "world_model.requested"],
        )
        export = ProjectionBuilder(ledger, b"m74-projection-key").signed_export("evidence", Clearance.restricted)
        self.assertTrue(verify_projection_export(export, b"m74-projection-key"))
        self.assertTrue(any(record["event_type"] == "fact.committed" for record in export["records"]))

    def test_failed_gate_keeps_candidate_uncommitted(self) -> None:
        store = WorldModelStore()
        writer = CandidateFactWriter(store, consistency_gate=lambda _: False, verification_gate=lambda _: True)
        candidate = CandidateFact(candidate_id("task.m74", fact()), "task.m74", fact(), ("citation.1",), "consistency.1", "verification.1")
        writer.stage(candidate)
        with self.assertRaises(WorldModelError) as caught:
            writer.commit(candidate.candidate_id)
        self.assertEqual(caught.exception.code, "consistency_failed")
        self.assertEqual(len(writer.candidates), 1)
        self.assertEqual(store.facts, ())

    def test_clearance_filter_hides_secret_facts(self) -> None:
        store = WorldModelStore()
        candidate = CandidateFact(candidate_id("task.m74", fact(clearance=Clearance.secret)), "task.m74", fact(clearance=Clearance.secret), ("citation.1",), "consistency.1", "verification.1")
        CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True).stage(candidate)
        self.assertEqual(store.query(WorldModelQuery("task.m74", clearance=Clearance.restricted)), ())

    def test_committed_facts_survive_restart(self) -> None:
        with TemporaryDirectory() as directory:
            path = f"{directory}/world-model.json"
            first = WorldModelStore(path=path)
            item = fact()
            candidate = CandidateFact(candidate_id("task.m74", item), "task.m74", item, ("citation.1",), "consistency.1", "verification.1")
            writer = CandidateFactWriter(first, consistency_gate=lambda _: True, verification_gate=lambda _: True)
            writer.stage(candidate)
            writer.commit(candidate.candidate_id)
            second = WorldModelStore(path=path)
            self.assertEqual(second.query(WorldModelQuery("task.m74", key="pressure"))[0].fact_id, item.fact_id)

    def test_gated_graph_relation_supports_clearance_filtered_traversal(self) -> None:
        store = WorldModelStore()
        source = named_fact("fact.pump")
        target = named_fact("fact.valve")
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True)
        writer.stage(CandidateFact(candidate_id("task.m74", source), "task.m74", source, ("citation.source",), "consistency.source", "verification.source"))
        writer.commit(candidate_id("task.m74", source))
        relation = WorldModelRelation(
            relation_id="relation.pump-downstream-valve", source_fact_id=source.fact_id,
            relation="downstream", target_fact_id=target.fact_id, source_ref=target.source_ref,
            confidence=.88, clearance=Clearance.internal, taint=Taint.untrusted,
        )
        target_candidate = CandidateFact(candidate_id("task.m74", target), "task.m74", target, ("citation.target",), "consistency.target", "verification.target", (relation,))
        writer.stage(target_candidate)
        writer.commit(target_candidate.candidate_id)
        result = store.query(WorldModelQuery("task.m74", clearance=Clearance.internal, entity_id=source.fact_id, relation="downstream"))
        self.assertEqual([item.fact_id for item in result], [target.fact_id])
        self.assertEqual(store.query(WorldModelQuery("task.m74", clearance=Clearance.public, entity_id=source.fact_id, relation="downstream")), ())

    def test_world_model_storage_limit_rejects_before_commit_event(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = EventLedger()
            seed_task(ledger, "task.m74")
            store = WorldModelStore(path=f"{directory}/world-model.json", max_file_bytes=1)
            writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True, ledger=ledger)
            item = fact()
            candidate = CandidateFact(candidate_id("task.m74", item), "task.m74", item, ("citation.1",), "consistency.1", "verification.1")
            writer.stage(candidate)
            with self.assertRaisesRegex(WorldModelError, "configured limit"):
                writer.commit(candidate.candidate_id)
            self.assertEqual(ledger.events[-1].event_type, "fact.candidate")
            self.assertEqual(store.facts, ())

    def test_superseded_fact_remains_auditable_but_is_not_query_visible(self) -> None:
        store = WorldModelStore()
        original = fact()
        newer = replace(original, fact_id="fact.pump.2", value={"pressure": 14}, supersedes_fact_id=original.fact_id)
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True)
        for item in (original, newer):
            candidate = CandidateFact(candidate_id("task.m74", item), "task.m74", item, ("citation.1",), "consistency.1", "verification.1")
            writer.stage(candidate)
            writer.commit(candidate.candidate_id)
        self.assertEqual(len(store.facts), 2)
        result = store.query(WorldModelQuery("task.m74", key="pressure"))
        self.assertEqual([item.fact_id for item in result], ["fact.pump.2"])


if __name__ == "__main__":
    unittest.main()
