"""End-to-end Node ``model.call`` command tests.

Proves the desktop -> Node -> orchestrator -> ModelRouter -> adapter path is
reachable through the HTTP command boundary, that routing/ledger events are
written, that replay is idempotent, and that the route fails closed when model
serving is not configured.  No live model server or network is used.
"""

from __future__ import annotations

import asyncio
import unittest

import httpx

from contracts import (
    Clearance,
    ContractStatus,
    EventLedger,
    FakeBackend,
    ModelRegistry,
    ModelRouter,
    ModelTarget,
    NodeCommandEnvelope,
    Orchestrator,
    TeamPlan,
)
from airbench.node.api import NodeApiConfig, NodeApiService, create_app

TASK_ID = "task.model.call"
TARGET_ID = "target.fake"
PACK_REF = "pack.fake"
HARDWARE_REF = "hw.fake"


def _target() -> ModelTarget:
    return ModelTarget.from_dict({
        "target_id": TARGET_ID,
        "repository": "local/fake",
        "artifact_digest": "a" * 64,
        "artifact_path": "fake.bin",
        "quantization": "int4",
        "tokenizer_digest": "b" * 64,
        "chat_template_digest": "c" * 64,
        "runtime_version": "fake-1",
        "backend": "custom",
        "capabilities": ["reasoning"],
        "roles": ["reasoning"],
        "modalities": ["text"],
        "risk_classes": ["inspection_review"],
        "allowed_clearances": ["internal"],
        "pack_refs": [PACK_REF],
        "hardware_profile_refs": [HARDWARE_REF],
        "context_limit": 1000,
        "image_token_limit": 0,
        "tool_call_parser": "none",
        "structured_output_modes": ["json_schema"],
        "license_id": "license.fake",
        "local_storage_hash": "a" * 64,
        "qualification_certificate": "cert.fake",
        "qualification_expires_at": "2030-01-01T00:00:00Z",
        "qualification_signature": "d" * 64,
        "role_qualifications": [["reasoning", "cert.fake"]],
        "adapter_id": "airbench.fake-backend",
        "adapter_version": "1.0",
        "streaming": True,
        "cancellation": True,
        "routing_tier": "capable",
    })


def _model_request(task_id: str) -> dict:
    return {
        "request_id": "request.placeholder",
        "task_id": task_id,
        "team_id": "team.model.call",
        "worker_id": "worker.model.call",
        "task_kind": "inspection_review",
        "modality": "text",
        "required_capability": "reasoning",
        "evidence_summary": ["evidence.model.call"],
        "clearance": "internal",
        "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 100},
        "attempt": 1,
        "idempotency_key": "idempotency.model.call.request",
        "timeout_ms": 5000,
        "role": "reasoning",
        "resource_lease_id": "lease.model.call",
    }


class ModelCallRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = EventLedger()
        self.orchestrator = Orchestrator(self.ledger)
        self.orchestrator.create_task(
            principal_id="principal.api", clearance=Clearance.internal,
            request="run one model call", domain_pack_ref=PACK_REF,
            risk_class="inspection_review", autonomy_ceiling="review_required",
            permitted_worker_capabilities=("reasoning",), verification_criteria=("source_check",),
            resource_budget={"max_concurrency": 1}, task_id=TASK_ID,
        )
        self.orchestrator.authorize(TASK_ID, authorization_ref="auth.model.call")
        self.orchestrator.commit_plan(TeamPlan(
            team_id="team.model.call", task_id=TASK_ID, assignments=("assignment.model.call",),
            dependency_graph={}, concurrency_ceiling=1, required_verification=True,
            completion_criteria=("source_check",), plan_version_hash="plan.model.call",
            policy_version_hash="policy.model.call", status=ContractStatus.proposed,
        ))
        registry = ModelRegistry("registry.model.call", "1.0", (_target(),), "e" * 64, "2030-01-01T00:00:00Z")
        self.backend = FakeBackend(ledger=self.ledger)
        self.router = ModelRouter(
            registry, {},
            policy_version_hash="policy.model.call",
            resource_admission=lambda _target, _request: "admitted",
            endpoint_bindings={TARGET_ID: self.backend},
        )
        self.service = self._service(self.router)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.service)),
            base_url="http://node.model.call",
        )

    def tearDown(self) -> None:
        asyncio.run(self.client.aclose())

    def _service(self, router) -> NodeApiService:
        return NodeApiService(
            self.orchestrator,
            NodeApiConfig(
                node_identity="node.model.call", protocol_version="0.1",
                clearance_context=Clearance.internal, authenticated_subject="principal.api",
                domain_pack_ref=PACK_REF, bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.model.call",
                sovereignty_evidence_ref="evidence.model.call",
                require_orchestrator_authorization=False,
            ),
            model_router=router,
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer test-token"}

    def _command(self, **overrides) -> dict:
        body = {
            "command_id": "command.model.call.1",
            "task_id": TASK_ID,
            "actor": "principal.api",
            "expected_sequence": len(self.ledger.events),
            "idempotency_key": "idempotency.model.call.1",
            "client_version": "0.1",
            "command_type": "model.call",
            "arguments": {
                "hardware_profile_ref": HARDWARE_REF,
                "request": _model_request(TASK_ID),
                "messages": [{"role": "user", "content": [{"kind": "text", "text": "hello"}]}],
                "output": {"mode": "text"},
            },
        }
        body.update(overrides)
        return body

    def _post(self, body: dict, client: httpx.AsyncClient) -> httpx.Response:
        async def run() -> httpx.Response:
            return await client.post("/api/v1/tasks/{}/model-call".format(TASK_ID), headers=self._headers(), json=body)
        return asyncio.run(run())

    def test_model_call_executes_and_records_events(self) -> None:
        resp = self._post(self._command(), self.client)
        self.assertEqual(resp.status_code, 202, resp.text)
        body = resp.json()
        self.assertEqual(body["command"]["outcome"], "accepted")
        self.assertEqual(body["model"]["output"], "fake response")
        self.assertEqual(body["model"]["selected_target"], TARGET_ID)
        event_types = [event.event_type for event in self.ledger.events]
        for expected in ("routing.decision", "model.requested", "model.call.started", "model.call.completed", "model.responded"):
            self.assertIn(expected, event_types)

    def test_replayed_command_does_not_execute_twice(self) -> None:
        first = self._post(self._command(), self.client)
        self.assertEqual(first.status_code, 202, first.text)
        second = self._post(self._command(expected_sequence=len(self.ledger.events)), self.client)
        self.assertEqual(second.status_code, 202, second.text)
        self.assertTrue(second.json().get("replayed"))
        self.assertEqual(sum(1 for event in self.ledger.events if event.event_type == "model.responded"), 1)

    def test_route_fails_closed_without_router(self) -> None:
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self._service(None))),
            base_url="http://node.model.call",
        )
        try:
            resp = self._post(self._command(), client)
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["code"], "model_serving_unavailable")

    def test_request_mismatching_task_authority_is_rejected(self) -> None:
        body = self._command()
        body["arguments"]["request"] = dict(_model_request(TASK_ID), clearance="restricted")
        resp = self._post(body, self.client)
        self.assertEqual(resp.status_code, 409)
        self.assertIn(resp.json()["code"], {"model_request_rejected", "transition_rejected"})

    def test_command_catalog_accepts_dispatchable_types(self) -> None:
        for command_type in ("model.call", "task.approve_artifact", "task.return_artifact"):
            envelope = NodeCommandEnvelope.from_dict({
                "command_id": "command.catalog.1",
                "task_id": TASK_ID,
                "actor": "principal.api",
                "expected_sequence": 0,
                "idempotency_key": "idempotency.catalog.1",
                "client_version": "0.1",
                "command_type": command_type,
                "arguments": {},
            })
            self.assertEqual(envelope.command_type, command_type)


if __name__ == "__main__":
    unittest.main()
