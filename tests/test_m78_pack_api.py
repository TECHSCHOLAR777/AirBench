from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

import httpx

from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.pack_loader import PackLoader
from airbench.node.server import add_pack_route
from contracts import Clearance, EventLedger, Orchestrator

REPO_ROOT = Path(__file__).resolve().parents[1]
REFINERY_PACK = REPO_ROOT / "packs" / "refinery_psu_v0"


def _config() -> NodeApiConfig:
    return NodeApiConfig(
        node_identity="node.pack.test", protocol_version="0.1", clearance_context=Clearance.internal,
        authenticated_subject="principal.api", domain_pack_ref="pack.refinery.v0", bearer_token="test-token",
        handshake_ledger_event_ref="ledger.handshake.test", sovereignty_evidence_ref="evidence.sovereignty.test",
        require_orchestrator_authorization=False,
    )


class NodePackApiTests(unittest.TestCase):
    def _app(self, pack):
        service = NodeApiService(Orchestrator(EventLedger()), _config(), pack=pack)
        app = create_app(service)
        add_pack_route(app, service)
        return app

    def _get(self, app, path):
        async def run():
            client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://node.pack.test")
            try:
                return await client.get(path)
            finally:
                await client.aclose()

        return asyncio.run(run())

    def test_pack_status_is_served_without_a_token(self):
        pack = PackLoader(allow_unsigned=True).load(REFINERY_PACK)
        response = self._get(self._app(pack), "/api/v1/node/pack")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["configured"])
        self.assertEqual(body["pack_id"], "refinery_psu_inspection_review_v0")
        self.assertEqual(body["pack_version"], "1.0")
        self.assertEqual(body["signature_status"], "unsigned")
        self.assertEqual(len(body["active_sections"]), 8)
        self.assertEqual(body["counts"]["field_rules"], 4)

    def test_pack_status_reports_disabled_without_a_pack(self):
        response = self._get(self._app(None), "/api/v1/node/pack")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"configured": False, "status": "disabled"})


if __name__ == "__main__":
    unittest.main()
