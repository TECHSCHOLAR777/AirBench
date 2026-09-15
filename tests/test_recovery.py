import unittest
from tempfile import TemporaryDirectory

from airbench.node.recovery import reconcile_stale_tasks
from contracts import Clearance, RecoveryManager, SQLiteLedgerStore, SideEffectUncertain, build_event
from contracts import EventLedger, Orchestrator


class RecoveryTests(unittest.TestCase):
    def test_knowledge_search_projection_is_not_reconciled_as_a_crashed_task(self):
        ledger = EventLedger()
        orchestrator = Orchestrator(ledger)
        orchestrator.create_task(
            principal_id="shared.operator", clearance=Clearance.internal,
            request="Node-owned knowledge search", domain_pack_ref="pack.refinery.v0",
            risk_class="low", autonomy_ceiling="system", task_id="task.knowledge.search",
        )
        ledger.append(build_event(
            event_type="retrieval.requested", task_id="task.knowledge.search",
            actor_id="local-retrieval", actor_type="retrieval",
            payload_contract="RetrievalOperation", payload_version="1.0",
            payload={"task_id": "task.knowledge.search", "query_hash": "hash"},
            clearance=Clearance.internal, idempotency="knowledge-search-request",
            sequence=len(ledger), previous_event_hash=ledger.head_hash,
        ))

        result = reconcile_stale_tasks(orchestrator, ledger)

        self.assertEqual(result["interrupted"], [])
        self.assertEqual(orchestrator.state("task.knowledge.search"), "executing")

    def test_retry_records_and_recovery_survive_reopen(self):
        with TemporaryDirectory() as directory:
            path = f"{directory}/ledger.sqlite3"
            store = SQLiteLedgerStore(path, b"recovery-key")
            event = build_event(event_type="task.created", task_id="task.recovery-001", actor_id="orchestrator.1", actor_type="service", payload_contract="TaskEnvelope", payload_version="1.0", payload={}, clearance=Clearance.internal, idempotency="recovery-task", sequence=0)
            tx = store.append(event)
            store.checkpoint(checkpoint_id="checkpoint.recovery-1", task_id=event.task_id, state="created", transaction_id=tx.transaction_id)
            recovery = RecoveryManager(store)
            retry = recovery.record_retry(retry_id="retry.1", task_id=event.task_id, action_id="action.1", attempt=1, status="failed", error_code="timeout")
            self.assertEqual(retry.status, "failed")
            store.close()
            reopened = SQLiteLedgerStore(path, b"recovery-key")
            reopened_recovery = RecoveryManager(reopened)
            point = reopened_recovery.recover(event.task_id)
            self.assertEqual(point.resumed_from_sequence, 1)
            self.assertEqual(reopened_recovery.retries(event.task_id)[0].error_code, "timeout")
            reopened.close()

    def test_completed_side_effect_is_not_run_twice(self):
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"recovery-key")
            recovery = RecoveryManager(store)
            calls = []
            effect = lambda: calls.append("executed") or {"artifact_id": "artifact.1"}
            self.assertEqual(recovery.run_once(idempotency_key="effect.1", task_id="task.1", action_id="action.1", effect=effect), {"artifact_id": "artifact.1"})
            self.assertEqual(recovery.run_once(idempotency_key="effect.1", task_id="task.1", action_id="action.1", effect=effect), {"artifact_id": "artifact.1"})
            self.assertEqual(calls, ["executed"])
            store.close()

    def test_ambiguous_crash_blocks_retry(self):
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"recovery-key")
            recovery = RecoveryManager(store)
            calls = []
            recovery.reserve_side_effect(idempotency_key="effect.uncertain", task_id="task.1", action_id="action.1")
            calls.append("side effect happened before crash")
            recovery.mark_uncertain("effect.uncertain")
            with self.assertRaises(SideEffectUncertain):
                recovery.run_once(idempotency_key="effect.uncertain", task_id="task.1", action_id="action.1", effect=lambda: calls.append("duplicated"))
            self.assertEqual(calls, ["side effect happened before crash"])
            store.close()


if __name__ == "__main__":
    unittest.main()
