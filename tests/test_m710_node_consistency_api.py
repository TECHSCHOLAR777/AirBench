from __future__ import annotations

import asyncio
import tempfile
import unittest

import httpx

from airbench.knowledge.consistency import ConsistencyEngine
from airbench.knowledge.decision_store import SqliteDecisionStore
from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.consistency_gateway import LocalNodeConsistencyService
from contracts import Clearance, EventLedger, Orchestrator


class NodeConsistencyApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.ledger = EventLedger()
        self.orchestrator = Orchestrator(self.ledger)
        self.task = self.orchestrator.create_task(
            principal_id="principal.api", clearance=Clearance.internal, request="Approve the inspection note",
            domain_pack_ref="pack.refinery.v0", risk_class="low", autonomy_ceiling="human_only",
            verification_criteria=("source_check",), task_id="task.m710.api",
        )
        self.store = SqliteDecisionStore(f"{self.directory.name}/decisions.sqlite")
        self.consistency = LocalNodeConsistencyService(
            engine=ConsistencyEngine(self.ledger), store=self.store, ledger=self.ledger,
            clearance_context=Clearance.internal,
        )
        self.service = NodeApiService(
            self.orchestrator,
            NodeApiConfig(
                node_identity="node.consistency.test", protocol_version="0.1", clearance_context=Clearance.internal,
                authenticated_subject="principal.api", domain_pack_ref="pack.refinery.v0", bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.test", sovereignty_evidence_ref="evidence.sovereignty.test",
                require_orchestrator_authorization=False,
            ),
            consistency=self.consistency,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.service)), base_url="http://node.consistency.test",
        )

    def tearDown(self):
        asyncio.run(self.client.aclose())
        self.store.close()
        self.directory.cleanup()

    def _request(self, method, path, **kwargs):
        async def run():
            return await self.client.request(method, path, headers={"Authorization": "Bearer test-token"}, **kwargs)

        return asyncio.run(run())

    def _decision(self, decision_id: str, severity: str) -> dict:
        return {
            "decision_id": decision_id, "decision_type": "approval_note_review_status",
            "object_id": "equipment.P-101", "features": {"severity": severity, "tag": "P-101"},
            "decision": "approved", "rule_ref": "pack.rule.1", "authority": "human_reviewer",
            "material_features": ["severity"],
        }

    def test_not_evaluated_then_evaluate_consistent(self):
        initial = self._request("GET", f"/api/v1/tasks/{self.task.task_id}/consistency")
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertEqual(initial.json()["status"], "not_evaluated")

        first = self._request("POST", f"/api/v1/tasks/{self.task.task_id}/consistency/evaluate", json=self._decision("decision.api.1", "low"))
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["deviation"])
        self.assertEqual(first.json()["comparable_ids"], [])

    def test_material_deviation_blocks_until_justified(self):
        self._request("POST", f"/api/v1/tasks/{self.task.task_id}/consistency/evaluate", json=self._decision("decision.api.1", "low"))
        second = self._request("POST", f"/api/v1/tasks/{self.task.task_id}/consistency/evaluate", json=self._decision("decision.api.2", "high"))
        self.assertEqual(second.status_code, 200, second.text)
        body = second.json()
        self.assertTrue(body["deviation"])
        self.assertEqual(body["comparable_ids"], ["decision.api.1"])
        self.assertIn(["severity", "low", "high"], body["material_differences"])
        self.assertTrue(self.consistency.is_blocked(self.task.task_id))

        report = self._request("GET", f"/api/v1/tasks/{self.task.task_id}/consistency")
        self.assertTrue(report.json()["deviation"])
        self.assertFalse(report.json()["justified"])

        justify = self._request(
            "POST", f"/api/v1/tasks/{self.task.task_id}/consistency/justify",
            json={"justification": "Higher severity was confirmed by a follow-up inspection."},
        )
        self.assertEqual(justify.status_code, 200, justify.text)
        self.assertTrue(justify.json()["justified"])
        self.assertFalse(self.consistency.is_blocked(self.task.task_id))
        self.assertEqual(self.ledger.events[-1].event_type, "consistency.justified")
        self.assertEqual(self.ledger.events[-1].payload["operator_id"], "principal.api")

    def test_justify_requires_a_flagged_deviation(self):
        self._request("POST", f"/api/v1/tasks/{self.task.task_id}/consistency/evaluate", json=self._decision("decision.api.1", "low"))
        response = self._request(
            "POST", f"/api/v1/tasks/{self.task.task_id}/consistency/justify", json={"justification": "not needed"},
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_missing_task_and_auth(self):
        missing = self._request("GET", "/api/v1/tasks/task.missing/consistency")
        self.assertEqual(missing.status_code, 404)

        async def run():
            return await self.client.get(f"/api/v1/tasks/{self.task.task_id}/consistency")

        self.assertEqual(asyncio.run(run()).status_code, 401)

    def test_evaluate_rejects_clearance_widening(self):
        payload = {**self._decision("decision.api.9", "low"), "clearance": "restricted"}
        response = self._request("POST", f"/api/v1/tasks/{self.task.task_id}/consistency/evaluate", json=payload)
        self.assertEqual(response.status_code, 403, response.text)

    def test_policy_restricts_which_deviations_block(self):
        from airbench.knowledge.consistency import ConsistencyEngine
        from airbench.knowledge.decision_store import SqliteDecisionStore

        def drive(required, name):
            store = SqliteDecisionStore(f"{self.directory.name}/{name}.sqlite")
            service = LocalNodeConsistencyService(
                engine=ConsistencyEngine(self.ledger), store=store, ledger=self.ledger,
                clearance_context=Clearance.internal, required_review_types=required,
            )
            base = dict(
                task_id=self.task.task_id, decision_type="approval_note_review_status",
                object_id=f"equipment.{name}", decision="approved", rule_ref="r.1", authority="human_reviewer",
            )
            service.evaluate(decision_id=f"decision.{name}.1", features={"severity": "low"}, **base)
            service.evaluate(decision_id=f"decision.{name}.2", features={"severity": "high"}, **base)
            blocked = service.is_blocked(self.task.task_id)
            store.close()
            return blocked

        self.assertFalse(drive(frozenset({"some_other_type"}), "policyA"))
        self.assertTrue(drive(frozenset({"approval_note_review_status"}), "policyB"))


if __name__ == "__main__":
    unittest.main()
