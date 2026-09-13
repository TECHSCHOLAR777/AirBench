from __future__ import annotations

import asyncio
import tempfile
import unittest

import httpx

from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from contracts import Clearance, EventLedger, Orchestrator, Taint

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-pid-image-bytes"


class _StubPidAdapter:
    def process(self, **kwargs):
        from airbench.intake.pid.records import PIDRecord, PidComponent

        return PIDRecord(
            task_id=kwargs["task_id"], intake_id=kwargs["intake_id"], revision_id=kwargs["revision_id"],
            source_ref=kwargs["source_ref"], content_hash=kwargs["content_hash"], media_type=kwargs["media_type"],
            clearance=kwargs["clearance"], taint=kwargs["taint"],
            components=(PidComponent("gate_valve1", "gate_valve", "V-101", (1.0, 2.0, 3.0, 4.0), 0.9),),
        )


class NodePidApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.ledger = EventLedger()
        self.orchestrator = Orchestrator(self.ledger)
        self.task = self.orchestrator.create_task(
            principal_id="principal.api", clearance=Clearance.internal, request="Digitize the P&ID",
            domain_pack_ref="pack.refinery.v0", risk_class="low", autonomy_ceiling="review_required",
            verification_criteria=("source_check",), task_id="task.pid.api",
        )
        self.service = NodeApiService(
            self.orchestrator,
            NodeApiConfig(
                node_identity="node.pid.test", protocol_version="0.1", clearance_context=Clearance.internal,
                authenticated_subject="principal.api", domain_pack_ref="pack.refinery.v0", bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.test", sovereignty_evidence_ref="evidence.sovereignty.test",
                require_orchestrator_authorization=False,
            ),
            pid_adapter=_StubPidAdapter(), pid_workspace=self.directory.name,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.service)), base_url="http://node.pid.test",
        )

    def tearDown(self):
        asyncio.run(self.client.aclose())
        self.directory.cleanup()

    def _post(self, content: bytes, name: str = "pid.png"):
        async def run():
            return await self.client.post(
                "/api/v1/intake/pid",
                headers={"Authorization": "Bearer test-token"},
                data={"intake_mode": "query_upload", "task_id": self.task.task_id, "source_file_size": str(len(content))},
                files={"document": (name, content, "image/png")},
            )

        return asyncio.run(run())

    def test_pid_extraction_returns_a_typed_record_and_ledger_event(self):
        response = self._post(PNG)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["summary"]["components"], 1)
        self.assertEqual(body["components"][0]["tag"], "V-101")
        self.assertEqual(body["taint"], "untrusted")
        self.assertTrue(body["ledger_event_ref"])
        self.assertEqual([event.event_type for event in self.ledger.events], ["task.created", "pid.extracted"])

    def test_pid_rejects_non_image_and_unconfigured_adapter(self):
        bad = self._post(b"not an image", name="notes.pdf")
        self.assertEqual(bad.status_code, 415, bad.text)

        service = NodeApiService(self.orchestrator, self.service.config, pid_adapter=None)
        app = create_app(service)

        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://n") as client:
                return await client.post(
                    "/api/v1/intake/pid",
                    headers={"Authorization": "Bearer test-token"},
                    data={"intake_mode": "query_upload", "task_id": self.task.task_id, "source_file_size": str(len(PNG))},
                    files={"document": ("pid.png", PNG, "image/png")},
                )

        self.assertEqual(asyncio.run(run()).status_code, 503)


if __name__ == "__main__":
    unittest.main()
