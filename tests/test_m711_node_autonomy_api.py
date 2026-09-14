from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import dataclass

import httpx

from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.autonomy_gateway import LocalNodeAutonomyService
from airbench.verification.autonomy import AutonomyGovernor, risk_rules_from_mappings
from contracts import Clearance, EventLedger, Orchestrator


@dataclass(frozen=True)
class _Mapping:
    action_kind: str
    reversibility: str
    required_human_authority: str


class NodeAutonomyApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.ledger = EventLedger()
        self.orchestrator = Orchestrator(self.ledger)
        self.task = self.orchestrator.create_task(
            principal_id="principal.api", clearance=Clearance.internal, request="Draft the approval note",
            domain_pack_ref="pack.refinery.v0", risk_class="low", autonomy_ceiling="draft_for_review",
            verification_criteria=("source_check",), task_id="task.m711.api",
        )
        rules = risk_rules_from_mappings([
            _Mapping("prepare_approval_note", "reversible", "human_reviewer"),
            _Mapping("release_approval_note", "non_reversible", "authorized_approver"),
        ])
        self.autonomy = LocalNodeAutonomyService(
            governor=AutonomyGovernor(self.ledger, rules), ledger=self.ledger,
            clearance_context=Clearance.internal,
        )
        self.service = NodeApiService(
            self.orchestrator,
            NodeApiConfig(
                node_identity="node.autonomy.test", protocol_version="0.1", clearance_context=Clearance.internal,
                authenticated_subject="principal.api", domain_pack_ref="pack.refinery.v0", bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.test", sovereignty_evidence_ref="evidence.sovereignty.test",
                authenticated_roles=("authorized_approver",), require_orchestrator_authorization=False,
            ),
            autonomy=self.autonomy,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.service)), base_url="http://node.autonomy.test",
        )

    def tearDown(self):
        asyncio.run(self.client.aclose())
        self.directory.cleanup()

    def _request(self, method, path, **kwargs):
        async def run():
            return await self.client.request(method, path, headers={"Authorization": "Bearer test-token"}, **kwargs)

        return asyncio.run(run())

    def _score(self, action_id: str, action_kind: str, confidence: float = 0.95) -> dict:
        return {
            "action_id": action_id, "action_kind": action_kind, "source_ref": "proposal.1",
            "confidence": confidence, "taint": "clean",
        }

    def test_low_risk_action_is_allowed_with_system_authority(self):
        response = self._request("POST", f"/api/v1/tasks/{self.task.task_id}/autonomy/score", json=self._score("action.1", "prepare_approval_note"))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["outcome"], "allow")
        self.assertEqual(body["required_authority"], "system")
        self.assertTrue(body["reason"].strip())

    def test_irreversible_action_escalates_and_can_be_authorized(self):
        escalated = self._request("POST", f"/api/v1/tasks/{self.task.task_id}/autonomy/score", json=self._score("action.2", "release_approval_note"))
        self.assertEqual(escalated.status_code, 200, escalated.text)
        self.assertEqual(escalated.json()["outcome"], "escalate")
        self.assertEqual(escalated.json()["required_authority"], "authorized_approver")
        self.assertTrue(self.autonomy.is_blocked(self.task.task_id))

        records = self._request("GET", f"/api/v1/tasks/{self.task.task_id}/autonomy")
        self.assertEqual(records.status_code, 200, records.text)
        self.assertTrue(records.json()["is_blocked"])
        self.assertEqual(len(records.json()["decisions"]), 1)

        authorize = self._request("POST", f"/api/v1/tasks/{self.task.task_id}/autonomy/authorize", json={"action_id": "action.2"})
        self.assertEqual(authorize.status_code, 200, authorize.text)
        self.assertTrue(authorize.json()["authorized"])
        self.assertFalse(self.autonomy.is_blocked(self.task.task_id))
        self.assertEqual(self.ledger.events[-1].event_type, "authority.authorized")
        self.assertEqual(self.ledger.events[-1].payload["operator_id"], "principal.api")

    def test_authorize_without_escalation_is_rejected(self):
        response = self._request("POST", f"/api/v1/tasks/{self.task.task_id}/autonomy/authorize", json={})
        self.assertEqual(response.status_code, 409, response.text)

    def test_missing_task_and_auth(self):
        missing = self._request("GET", "/api/v1/tasks/task.missing/autonomy")
        self.assertEqual(missing.status_code, 404)

        async def run():
            return await self.client.get(f"/api/v1/tasks/{self.task.task_id}/autonomy")

        self.assertEqual(asyncio.run(run()).status_code, 401)

    def test_score_rejects_clearance_widening(self):
        payload = {**self._score("action.9", "prepare_approval_note"), "clearance": "restricted"}
        response = self._request("POST", f"/api/v1/tasks/{self.task.task_id}/autonomy/score", json=payload)
        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
