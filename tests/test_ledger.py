import unittest
from dataclasses import replace
from tempfile import TemporaryDirectory

from contracts import (Clearance, EventLedger, IdempotencyConflict,
                       ProvenanceRejected, ReplayRejected, SQLiteLedgerStore,
                       StorageFailure, TransitionRejected, build_event)


class LedgerTests(unittest.TestCase):
    def make(self, ledger, event_type, payload, key):
        return build_event(
            event_type=event_type, task_id="task.ledger-001", actor_id="orchestrator.001",
            actor_type="service", payload_contract="TestPayload", payload_version="1.0",
            payload=payload, clearance=Clearance.restricted, idempotency=key,
            sequence=len(ledger.events), previous_event_hash=ledger.head_hash,
        )

    def test_append_chain_and_replay(self):
        ledger = EventLedger()
        ledger.append(self.make(ledger, "task.created", {"state": "created"}, "task-create"))
        ledger.append(self.make(ledger, "team.created", {"team_id": "team.1"}, "team-create"))
        ledger.append(self.make(ledger, "verification.completed", {"status": "needs_review"}, "verify"))
        ledger.verify_chain()
        state = ledger.replay("task.ledger-001")
        self.assertEqual(state.state, "needs_review")
        self.assertEqual(state.sequence, 2)
        self.assertEqual(len(state.event_ids), 3)

    def test_same_idempotency_key_is_replay_safe_but_conflicts_fail(self):
        ledger = EventLedger()
        event = self.make(ledger, "task.created", {"state": "created"}, "same-key")
        self.assertIs(ledger.append(event), ledger.append(event))
        conflict = self.make(ledger, "task.created", {"state": "different"}, "same-key")
        with self.assertRaises(IdempotencyConflict):
            ledger.append(conflict)

    def test_invalid_sequence_or_hash_fails_closed(self):
        ledger = EventLedger()
        event = self.make(ledger, "task.created", {"state": "created"}, "create")
        tampered = replace(event, event_hash="f" * 64)
        with self.assertRaises(ReplayRejected):
            ledger.append(tampered)

    def test_preconditions_and_failure_states(self):
        ledger = EventLedger()
        with self.assertRaises(TransitionRejected):
            ledger.append(self.make(ledger, "team.created", {"team_id": "team.1"}, "team-before-task"))
        ledger.append(self.make(ledger, "task.created", {}, "task"))
        with self.assertRaises(TransitionRejected):
            ledger.append(self.make(ledger, "completion.recorded", {}, "complete-too-early"))
        ledger.append(self.make(ledger, "verification.completed", {"status": "failed"}, "verify-failed"))
        self.assertEqual(ledger.replay("task.ledger-001").failure_state, "blocked")

    def test_sqlite_store_persists_chain_seals_batches_and_replays(self):
        with TemporaryDirectory() as directory:
            path = f"{directory}/ledger.sqlite3"
            store = SQLiteLedgerStore(path, b"test-signing-key")
            first = build_event(event_type="task.created", task_id="task.persisted-001", actor_id="orchestrator.001", actor_type="service", payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"}, clearance=Clearance.internal, idempotency="persist-task", sequence=0)
            second = build_event(event_type="evidence.created", task_id="task.persisted-001", actor_id="intake.001", actor_type="service", payload_contract="UntrustedEvidence", payload_version="1.0", payload={"provenance": {"source_ref": "upload:1", "confidence": 0.9, "clearance": "internal", "taint": "untrusted"}}, clearance=Clearance.internal, idempotency="persist-evidence", sequence=1, previous_event_hash=first.event_hash)
            committed = store.append_batch([first, second], "transaction.persisted-001")
            self.assertEqual(committed.last_sequence, 1)
            self.assertTrue(committed.signature)
            checkpoint = store.checkpoint(checkpoint_id="checkpoint.1", task_id="task.persisted-001", state="running", transaction_id=committed.transaction_id)
            store.close()
            reopened = SQLiteLedgerStore(path, b"test-signing-key")
            self.assertEqual(reopened.replay("task.persisted-001").sequence, 1)
            self.assertEqual(reopened.latest_checkpoint("task.persisted-001"), checkpoint)
            exported = reopened.signed_export(Clearance.internal)
            self.assertEqual(len(exported["events"]), 2)
            self.assertTrue(exported["signature"])
            reopened.close()

    def test_sqlite_store_clearance_projection_filters_events(self):
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"key")
            public = build_event(event_type="task.created", task_id="task.clearance-001", actor_id="o", actor_type="service", payload_contract="TaskEnvelope", payload_version="1.0", payload={}, clearance=Clearance.public, idempotency="public", sequence=0)
            secret = build_event(event_type="team.created", task_id="task.clearance-001", actor_id="o", actor_type="service", payload_contract="TeamPlan", payload_version="1.0", payload={}, clearance=Clearance.secret, idempotency="secret", sequence=1, previous_event_hash=public.event_hash)
            store.append(public)
            store.append(secret)
            self.assertEqual(len(store.projection(Clearance.public)), 1)
            self.assertEqual(len(store.projection(Clearance.secret)), 2)
            store.close()

    def test_sqlite_store_rejects_missing_provenance_atomically(self):
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"key")
            first = build_event(event_type="task.created", task_id="task.provenance-001", actor_id="o", actor_type="service", payload_contract="TaskEnvelope", payload_version="1.0", payload={}, clearance=Clearance.restricted, idempotency="p1", sequence=0)
            invalid = build_event(event_type="fact.committed", task_id="task.provenance-001", actor_id="o", actor_type="service", payload_contract="FactEnvelope", payload_version="1.0", payload={}, clearance=Clearance.restricted, idempotency="p2", sequence=1, previous_event_hash=first.event_hash)
            with self.assertRaises(StorageFailure) as caught:
                store.append_batch([first, invalid], "transaction.invalid")
            self.assertIsInstance(caught.exception.__cause__, ProvenanceRejected)
            self.assertEqual(store.events, ())
            store.close()

    def test_sqlite_duplicate_write_is_idempotent(self):
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"key")
            event = build_event(event_type="task.created", task_id="task.duplicate-001", actor_id="o", actor_type="service", payload_contract="TaskEnvelope", payload_version="1.0", payload={}, clearance=Clearance.internal, idempotency="duplicate", sequence=0)
            first = store.append(event)
            second = store.append(event)
            self.assertEqual(first.transaction_id, second.transaction_id)
            self.assertEqual(len(store.events), 1)
            store.close()


if __name__ == "__main__":
    unittest.main()
