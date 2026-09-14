from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

import httpx

from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.hardware_gateway import hardware_status, load_hardware_profile
from airbench.node.qualification_gateway import load_qualification_matrix, qualification_roster, qualification_status
from airbench.node.server import add_node_asset_routes
from contracts import Clearance, EventLedger, Orchestrator

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_PROFILE = REPO_ROOT / "profiles" / "hardware" / "workstation_demo.yaml"
QUAL_MATRIX = REPO_ROOT / "qualifications" / "model_qualification_matrix.yaml"


class HardwareProfileTests(unittest.TestCase):
    def test_demo_profile_loads_and_projects(self):
        profile = load_hardware_profile(DEMO_PROFILE)
        self.assertEqual(profile.profile_id, "workstation-demo")
        self.assertEqual(profile.gpu_count, 1)
        self.assertEqual(profile.safe_parallel_slots, 4)
        status = hardware_status(profile)
        self.assertGreater(status["vram_gb"], 90)
        self.assertEqual(status["egress_policy"], "deny-all")
        self.assertIn("serial_virtual_team", status["supported_execution_modes"])

    def test_missing_profile_fails_closed(self):
        with self.assertRaises(Exception):
            load_hardware_profile(REPO_ROOT / "profiles" / "hardware" / "nope.yaml")


class QualificationStatusTests(unittest.TestCase):
    def test_placeholder_certificates_are_pending_not_qualified(self):
        matrix = load_qualification_matrix(QUAL_MATRIX)
        status = qualification_status(matrix, "gemma4-31b-it-q4")
        self.assertEqual(status["status"], "pending")
        self.assertTrue(status["certificates"])

    def test_unknown_target_is_not_listed(self):
        matrix = load_qualification_matrix(QUAL_MATRIX)
        status = qualification_status(matrix, "target.unknown")
        self.assertEqual(status["status"], "not_listed")

    def test_roster_lists_every_declared_target(self):
        matrix = load_qualification_matrix(QUAL_MATRIX)
        roster = qualification_roster(matrix)
        self.assertGreaterEqual(roster["count"], 1)
        self.assertEqual(roster["count"], len(roster["targets"]))
        self.assertTrue(all(target["status"] in {"qualified", "unqualified", "pending"} for target in roster["targets"]))


class NodeAssetApiTests(unittest.TestCase):
    def _app(self):
        service = NodeApiService(
            Orchestrator(EventLedger()),
            NodeApiConfig(
                node_identity="node.assets.test", protocol_version="0.1", clearance_context=Clearance.internal,
                authenticated_subject="principal.api", domain_pack_ref="pack.refinery.v0", bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.test", sovereignty_evidence_ref="evidence.sovereignty.test",
                require_orchestrator_authorization=False,
            ),
            hardware_profile=load_hardware_profile(DEMO_PROFILE),
            qualification_matrix=load_qualification_matrix(QUAL_MATRIX),
        )
        app = create_app(service)
        add_node_asset_routes(app, service)
        return app

    def _get(self, path: str):
        async def run():
            client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self._app()), base_url="http://node.assets.test")
            try:
                return await client.get(path)
            finally:
                await client.aclose()

        return asyncio.run(run())

    def test_hardware_endpoint(self):
        response = self._get("/api/v1/node/hardware")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["configured"])
        self.assertEqual(body["profile_id"], "workstation-demo")
        self.assertEqual(body["safe_parallel_slots"], 4)

    def test_qualification_endpoint(self):
        response = self._get("/api/v1/node/qualification/gemma4-31b-it-q4")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "pending")
        unknown = self._get("/api/v1/node/qualification/target.unknown")
        self.assertEqual(unknown.json()["status"], "not_listed")

    def test_qualification_roster_endpoint(self):
        response = self._get("/api/v1/node/qualification")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["configured"])
        self.assertGreaterEqual(body["count"], 1)
        self.assertEqual(body["count"], len(body["targets"]))


if __name__ == "__main__":
    unittest.main()
