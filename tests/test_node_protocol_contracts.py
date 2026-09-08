import unittest

from contracts import (
    Clearance,
    NodeEvidenceRef,
    NodeFactRef,
    NodeHandshake,
    NodeProvenanceRef,
    NodeTaskEvent,
    NodeTaskEventBatch,
    NodeTaskSnapshot,
    Taint,
)


class NodeProtocolContractTests(unittest.TestCase):
    def provenance(self) -> NodeProvenanceRef:
        return NodeProvenanceRef(
            source_document_id="upload:inspection-1",
            source_version="revision-1",
            location={"page": 2, "region": "table:1"},
            extraction_method="ocr",
            observed_at=None,
            ingested_at="2026-09-09T00:00:00Z",
            ledger_event_ref="ledger-source-1",
        )

    def evidence(self) -> NodeEvidenceRef:
        return NodeEvidenceRef(
            evidence_id="evidence-1",
            content_hash="a" * 64,
            source=self.provenance(),
            confidence=0.94,
            clearance=Clearance.restricted,
            taint=Taint.untrusted,
        )

    def test_snapshot_round_trip_preserves_node_envelope_and_provenance(self):
        snapshot = NodeTaskSnapshot(
            task_id="task-1",
            snapshot_id="snapshot-1",
            as_of_sequence=4,
            title="Inspection approval note",
            request_summary="Review a scanned inspection report.",
            status="running",
            phase="evidence",
            clearance_context=Clearance.restricted,
            input_manifest_ref="manifest-1",
            evidence=(self.evidence(),),
            facts=(NodeFactRef(
                fact_id="fact-1",
                value=42,
                source=self.provenance(),
                confidence=0.91,
                clearance=Clearance.restricted,
                taint=Taint.untrusted,
                parent_fact_ids=(),
                unit="bar",
                derivation={"method": "deterministic-calculation", "input_fact_ids": []},
                superseded_by=None,
            ),),
            artifact_refs=("artifact-1",),
            unresolved_questions=("Confirm the inspection date.",),
            node_connection_ref="node-1",
            ledger_head_ref="ledger-4",
        )

        wire = snapshot.to_wire_dict()
        self.assertEqual(wire["schemaVersion"], "0.1")
        self.assertEqual(wire["compatibilityId"], "airbench-node-protocol")
        self.assertEqual(wire["evidence"][0]["source"]["sourceDocumentId"], "upload:inspection-1")
        self.assertEqual(wire["facts"][0]["parentFactIds"], [])
        restored = NodeTaskSnapshot.from_wire_dict(wire)
        self.assertEqual(restored, snapshot)

    def test_event_batch_keeps_core_batch_envelope_and_node_event_envelope_distinct(self):
        wire = {
            "schema_version": "1.0",
            "compatibility_id": "airbench-core-contracts",
            "stream_id": "task-1",
            "node_identity": "node-1",
            "protocol_version": "0.1",
            "clearance_context": "restricted",
            "events": [{
                "eventId": "event-1",
                "taskId": "task-1",
                "sequence": 1,
                "schemaVersion": "0.1",
                "compatibilityId": "airbench-node-protocol",
                "eventType": "task.accepted",
                "occurredAt": "2026-09-09T00:00:00Z",
                "actor": "node-1",
                "clearanceContext": "restricted",
                "payloadHash": "b" * 64,
                "ledgerEventRef": "ledger-1",
                "payload": {"phase": "accepted", "status": "accepted"},
            }],
            "next_sequence": 1,
            "has_more": False,
            "ledger_event_refs": ["ledger-1"],
        }
        batch = NodeTaskEventBatch.from_wire_dict(wire)
        output = batch.to_dict()
        self.assertEqual(output["schema_version"], "1.0")
        self.assertEqual(output["compatibility_id"], "airbench-core-contracts")
        self.assertEqual(output["events"][0]["compatibilityId"], "airbench-node-protocol")
        self.assertEqual(output["events"][0]["payload"]["phase"], "accepted")

    def test_handshake_requires_selected_version_to_be_advertised(self):
        handshake = NodeHandshake(
            node_identity="node-1",
            protocol_version="0.1",
            protocol_compatibility_id="airbench-node-protocol",
            supported_protocol_versions=("0.1",),
            clearance_context=Clearance.restricted,
            authenticated_subject="operator-1",
            domain_pack_ref="pack.refinery.v0",
            ledger_event_ref="ledger-handshake-1",
        )
        self.assertEqual(handshake.to_dict()["supported_protocol_versions"], ["0.1"])
        with self.assertRaises(Exception):
            NodeHandshake.from_dict({**handshake.to_dict(), "protocol_version": "9.9"})


if __name__ == "__main__":
    unittest.main()
