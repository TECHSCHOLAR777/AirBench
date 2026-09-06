import unittest
from dataclasses import replace

from contracts import (Clearance, EventLedger, IdempotencyConflict,
                       ReplayRejected, TransitionRejected, build_event)


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


if __name__ == "__main__":
    unittest.main()
