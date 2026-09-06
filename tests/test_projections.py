import unittest
from tempfile import TemporaryDirectory

from contracts import Clearance, ProjectionBuilder, SQLiteLedgerStore, build_event


class ProjectionTests(unittest.TestCase):
    def test_rebuilds_clearance_filtered_read_models_without_mutating_ledger(self):
        with TemporaryDirectory() as directory:
            store = SQLiteLedgerStore(f"{directory}/ledger.sqlite3", b"projection-key")
            task = build_event(event_type="task.created", task_id="task.projection-001", actor_id="orchestrator.1", actor_type="service", payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"}, clearance=Clearance.public, idempotency="projection-task", sequence=0)
            evidence = build_event(event_type="evidence.created", task_id=task.task_id, actor_id="intake.1", actor_type="service", payload_contract="UntrustedEvidence", payload_version="1.0", payload={"provenance": {"source_ref": "upload:1", "confidence": 0.91, "clearance": "internal", "taint": "untrusted"}, "text": "inspection finding"}, clearance=Clearance.internal, idempotency="projection-evidence", sequence=1, previous_event_hash=task.event_hash)
            artifact = build_event(event_type="artifact.staged", task_id=task.task_id, actor_id="deliverable.1", actor_type="service", payload_contract="Artifact", payload_version="1.0", payload={"artifact_id": "artifact.1"}, clearance=Clearance.restricted, idempotency="projection-artifact", sequence=2, previous_event_hash=evidence.event_hash)
            store.append_batch([task, evidence, artifact], "projection-transaction")
            before = (store.head_hash, store.events)
            builder = ProjectionBuilder(store, b"projection-key")
            public = builder.rebuild("evidence", Clearance.public)
            internal = builder.rebuild("evidence", Clearance.internal)
            self.assertEqual(len(public.records), 0)
            self.assertEqual(len(internal.records), 1)
            self.assertEqual(internal.records[0]["payload"]["provenance"]["source_ref"], "upload:1")
            self.assertEqual(builder.rebuild("task", Clearance.secret).records[0]["task_id"], task.task_id)
            self.assertEqual(len(builder.rebuild("artifact", Clearance.restricted).records), 1)
            self.assertEqual(len(builder.rebuild("search", Clearance.internal).records), 1)
            with self.assertRaises(TypeError):
                internal.records[0]["event_type"] = "tampered"
            exported = builder.signed_export("audit", Clearance.internal)
            self.assertTrue(exported["signature"])
            self.assertEqual((store.head_hash, store.events), before)
            store.close()


if __name__ == "__main__":
    unittest.main()
