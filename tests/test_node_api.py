import asyncio
import unittest

import httpx

from contracts import Clearance, EventLedger, Orchestrator, build_event
from airbench.node_api import NodeApiConfig, NodeApiService, create_app


class NodeApiTests(unittest.TestCase):
    def setUp(self):
        self.ledger = EventLedger()
        self.orchestrator = Orchestrator(self.ledger)
        self.service = NodeApiService(
            self.orchestrator,
            NodeApiConfig(
                node_identity="node.test.local",
                protocol_version="0.1",
                clearance_context=Clearance.restricted,
                authenticated_subject="principal.api",
                bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.test",
                sovereignty_evidence_ref="evidence.sovereignty.test",
                require_orchestrator_authorization=False,
            ),
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.service)),
            base_url="http://node.test",
        )

    def tearDown(self):
        asyncio.run(self.client.aclose())

    def request(self, method, path, **kwargs):
        async def run():
            return await self.client.request(method, path, **kwargs)

        return asyncio.run(run())

    def headers(self, token="test-token"):
        return {"Authorization": f"Bearer {token}"}

    def task_body(self, **overrides):
        body = {
            "principal_id": "principal.api",
            "clearance": "internal",
            "request": "Review the local inspection report",
            "domain_pack_ref": "pack.refinery.v0",
            "risk_class": "high",
            "autonomy_ceiling": "review_required",
            "allowed_evidence_scope": ["inspection-report"],
            "permitted_worker_capabilities": ["reasoning"],
            "permitted_tools": ["calculator"],
            "output_contract": "approval-note",
            "verification_criteria": ["source_check"],
            "resource_budget": {"max_concurrency": 1, "max_steps": 8},
        }
        body.update(overrides)
        return body

    def create_task(self):
        response = self.request("POST", "/api/v1/tasks", headers=self.headers(), json=self.task_body())
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["task"], response.json()["snapshot"]

    def append_event(self, event_type, task_id, payload, clearance=Clearance.internal):
        event = build_event(
            event_type=event_type,
            task_id=task_id,
            actor_id="fixture.service",
            actor_type="service",
            payload_contract="FixturePayload",
            payload_version="1.0",
            payload=payload,
            clearance=clearance,
            idempotency=f"fixture.{event_type}.{len(self.ledger.events)}",
            sequence=len(self.ledger.events),
            previous_event_hash=self.ledger.head_hash,
        )
        return self.ledger.append(event)

    def test_handshake_is_authenticated_and_does_not_expose_docs(self):
        response = self.request("GET", "/api/v1/node/handshake", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "node_identity": "node.test.local",
                "protocol_version": "0.1",
                "clearance_context": "restricted",
                "authenticated_subject": "principal.api",
                "ledger_event_ref": "ledger.handshake.test",
            },
        )
        self.assertEqual(self.request("GET", "/api/v1/node/handshake").status_code, 401)
        self.assertEqual(self.request("GET", "/docs").status_code, 404)

    def test_create_authorize_and_cancel_are_orchestrator_mutations(self):
        task, snapshot = self.create_task()
        task_id = task["task_id"]
        self.assertEqual(snapshot["asOfSequence"], 1)

        authorize = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/authorize",
            headers=self.headers(),
            json={"authorization_ref": "authorization.local"},
        )
        self.assertEqual(authorize.status_code, 202, authorize.text)
        self.assertEqual(authorize.json()["event_type"], "task.authorized")

        cancelled = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/cancel",
            headers=self.headers(),
            json={"reason": "operator stopped the task"},
        )
        self.assertEqual(cancelled.status_code, 202, cancelled.text)
        self.assertEqual(cancelled.json()["state"], "cancelled")
        self.assertEqual([event.event_type for event in self.ledger.events], [
            "task.created", "task.authorized", "task.cancelled",
        ])

    def test_event_batch_uses_task_local_cursor_and_preserves_ledger_reference(self):
        task, _ = self.create_task()
        task_id = task["task_id"]
        self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/authorize",
            headers=self.headers(),
            json={"authorization_ref": "authorization.local"},
        )
        batch = self.request(
            "GET",
            f"/api/v1/tasks/{task_id}/events?after_sequence=0",
            headers=self.headers(),
        )
        self.assertEqual(batch.status_code, 200, batch.text)
        body = batch.json()
        self.assertEqual([event["sequence"] for event in body["events"]], [1, 2])
        self.assertEqual(body["next_sequence"], 2)
        self.assertEqual(body["ledger_event_refs"], [event["ledgerEventRef"] for event in body["events"]])
        self.assertEqual(body["events"][0]["eventType"], "task.accepted")
        self.assertEqual(body["events"][1]["eventType"], "task.accepted")
        self.assertEqual(body["events"][0]["schemaVersion"], "0.1")
        self.assertEqual(body["events"][0]["taskId"], task_id)

        ahead = self.request(
            "GET",
            f"/api/v1/tasks/{task_id}/events?after_sequence=3",
            headers=self.headers(),
        )
        self.assertEqual(ahead.status_code, 409)
        self.assertEqual(ahead.json()["code"], "cursor_ahead")

    def test_evidence_and_route_trace_are_clearance_filtered(self):
        task, _ = self.create_task()
        task_id = task["task_id"]
        provenance = {
            "source_ref": "upload:inspection-1",
            "confidence": 0.91,
            "clearance": "internal",
            "taint": "untrusted",
        }
        self.append_event(
            "evidence.created",
            task_id,
            {"evidence_id": "evidence.one", "content_hash": "a" * 64, "provenance": provenance},
        )
        self.append_event(
            "evidence.created",
            task_id,
            {"evidence_id": "evidence.secret", "content_hash": "b" * 64, "provenance": {**provenance, "clearance": "secret"}},
            Clearance.secret,
        )
        self.append_event(
            "routing.decision",
            task_id,
            {"selected_target": "model.local.reasoner", "decision_source": "fixture", "qualification_certificate": "cert.1"},
        )

        evidence = self.request("GET", f"/api/v1/tasks/{task_id}/evidence", headers=self.headers())
        self.assertEqual(evidence.status_code, 200, evidence.text)
        self.assertEqual([item["evidenceId"] for item in evidence.json()["evidence"]], ["evidence.one"])
        self.assertEqual(evidence.json()["evidence"][0]["confidence"], 0.91)
        self.assertEqual(evidence.json()["evidence"][0]["taint"], "untrusted")

        route = self.request("GET", f"/api/v1/tasks/{task_id}/route-trace", headers=self.headers())
        self.assertEqual(route.status_code, 200, route.text)
        self.assertEqual(route.json()["entries"][0]["selected_target"], "model.local.reasoner")
        self.assertNotIn("evidence.secret", evidence.text)

    def test_invalid_clearance_and_oversized_json_fail_closed(self):
        response = self.request(
            "POST",
            "/api/v1/tasks",
            headers=self.headers(),
            json=self.task_body(clearance="secret"),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "clearance_exceeded")

        oversized = "x" * (2 * 1024 * 1024)
        response = self.request(
            "POST",
            "/api/v1/tasks",
            headers={**self.headers(), "Content-Type": "application/json"},
            content=(f'{{"request":"{oversized}"}}').encode(),
        )
        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
