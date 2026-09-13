"""Node task planning + hardware admission + full command-chain tests.

Proves the documented flow works through the HTTP command boundary:
create -> authorize (Node plans + admits) -> plan ready -> approve -> model call.
No live model server is used (FakeBackend), and no GPU is required.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path

import httpx

from contracts import (
    Clearance,
    ContractStatus,
    EventLedger,
    FakeBackend,
    HardwareProfile,
    ModelRegistry,
    ModelRouter,
    ModelTarget,
    Orchestrator,
    TeamPlan,
)
from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.task_planning import NodeTaskPlanner, PlannerConfig, build_plan_proposal

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = REPO_ROOT / "profiles" / "hardware" / "workstation_04.json"
TASK_ID = "task.planning"
PACK_REF = "pack.fake"
HW_REF = "workstation-04"
TARGET_ID = "target.fake"


def _profile() -> HardwareProfile:
    return HardwareProfile.from_dict(json.loads(PROFILE_PATH.read_text(encoding="utf-8")))


def _target() -> ModelTarget:
    return ModelTarget.from_dict({
        "target_id": TARGET_ID, "repository": "local/fake", "artifact_digest": "a" * 64,
        "artifact_path": "fake.bin", "quantization": "int4", "tokenizer_digest": "b" * 64,
        "chat_template_digest": "c" * 64, "runtime_version": "fake-1", "backend": "custom",
        "capabilities": ["reasoning"], "roles": ["reasoning"], "modalities": ["text"],
        "risk_classes": ["inspection_review"], "allowed_clearances": ["internal"],
        "pack_refs": [PACK_REF], "hardware_profile_refs": [HW_REF], "context_limit": 8192,
        "image_token_limit": 0, "tool_call_parser": "none", "structured_output_modes": ["json_schema"],
        "license_id": "license.fake", "local_storage_hash": "a" * 64,
        "qualification_certificate": "cert.fake", "qualification_expires_at": "2030-01-01T00:00:00Z",
        "qualification_signature": "d" * 64, "role_qualifications": [["reasoning", "cert.fake"]],
        "adapter_id": "airbench.fake-backend", "adapter_version": "1.0",
        "streaming": True, "cancellation": True, "routing_tier": "capable",
    })


def _request_payload(task_id: str = TASK_ID) -> dict:
    return {
        "request_id": "request.placeholder", "task_id": task_id, "team_id": "team.planning",
        "worker_id": "worker.planning", "task_kind": "inspection_review", "modality": "text",
        "required_capability": "reasoning", "evidence_summary": ["evidence.planning"],
        "clearance": "internal", "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 100}, "attempt": 1,
        "idempotency_key": "idempotency.planning.request", "timeout_ms": 5000,
        "role": "reasoning", "resource_lease_id": "lease.planning",
    }


class PlanProposalTests(unittest.TestCase):
    def _task(self, orchestrator: Orchestrator):
        return orchestrator.create_task(
            principal_id="principal.plan", clearance=Clearance.internal, request="plan me",
            domain_pack_ref=PACK_REF, risk_class="inspection_review", autonomy_ceiling="review_required",
            permitted_worker_capabilities=("reasoning",), verification_criteria=("source_check",),
            resource_budget={"max_concurrency": 1}, task_id=TASK_ID,
        )

    def test_proposal_has_model_and_verification_steps(self) -> None:
        proposal = build_plan_proposal(self._task(Orchestrator(EventLedger())))
        kinds = [step.kind for step in proposal.steps]
        self.assertIn("model", kinds)
        self.assertIn("verification", kinds)

    def test_planner_commits_plan_and_admission(self) -> None:
        ledger = EventLedger()
        orchestrator = Orchestrator(ledger)
        task = self._task(orchestrator)
        orchestrator.authorize(task.task_id, authorization_ref="auth.plan")
        planner = NodeTaskPlanner(orchestrator, PlannerConfig(
            policy_version_hash="policy.plan", hardware_profile=_profile(),
        ))
        planner.plan_and_admit(task)
        self.assertEqual(orchestrator.state(task.task_id), "planned")
        events = [event.event_type for event in ledger.events]
        self.assertIn("task.plan.committed", events)
        self.assertIn("team.resource_plan.admitted", events)

    def test_planner_without_profile_still_commits_plan(self) -> None:
        ledger = EventLedger()
        orchestrator = Orchestrator(ledger)
        task = self._task(orchestrator)
        orchestrator.authorize(task.task_id, authorization_ref="auth.plan")
        planner = NodeTaskPlanner(orchestrator, PlannerConfig(policy_version_hash="policy.plan"))
        self.assertFalse(planner.has_hardware_profile)
        planner.plan_and_admit(task)
        self.assertEqual(orchestrator.state(task.task_id), "planned")
        self.assertNotIn("team.resource_plan.admitted", [event.event_type for event in ledger.events])


class FullCommandChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = EventLedger()
        self.orchestrator = Orchestrator(self.ledger)
        registry = ModelRegistry("registry.planning", "1.0", (_target(),), "e" * 64, "2030-01-01T00:00:00Z")
        router = ModelRouter(
            registry, {}, policy_version_hash="policy.planning",
            resource_admission=lambda _target, _request: "admitted",
            endpoint_bindings={TARGET_ID: FakeBackend(ledger=self.ledger)},
        )
        planner = NodeTaskPlanner(self.orchestrator, PlannerConfig(
            policy_version_hash="policy.planning", hardware_profile=_profile(),
        ))
        service = NodeApiService(
            self.orchestrator,
            NodeApiConfig(
                node_identity="node.planning", protocol_version="0.1",
                clearance_context=Clearance.internal, authenticated_subject="principal.api",
                domain_pack_ref=PACK_REF, bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.planning",
                sovereignty_evidence_ref="evidence.planning",
                require_orchestrator_authorization=False,
            ),
            model_router=router, task_planner=planner,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(service)), base_url="http://node.planning",
        )

    def tearDown(self) -> None:
        asyncio.run(self.client.aclose())

    def _command(self, command_type: str, arguments: dict, *, command_id: str, idem: str,
                 expected_sequence: int | None, task_id: str | None = None) -> dict:
        return {
            "command_id": command_id,
            "task_id": None if expected_sequence is None else (task_id or TASK_ID),
            "actor": "principal.api", "expected_sequence": expected_sequence,
            "idempotency_key": idem, "client_version": "0.1",
            "command_type": command_type, "arguments": arguments,
        }

    def _post(self, path: str, body: dict) -> httpx.Response:
        async def run() -> httpx.Response:
            return await self.client.post(path, headers={"Authorization": "Bearer test-token"}, json=body)
        return asyncio.run(run())

    def _get(self, path: str) -> httpx.Response:
        async def run() -> httpx.Response:
            return await self.client.get(path, headers={"Authorization": "Bearer test-token"})
        return asyncio.run(run())

    def test_create_authorize_plan_approve_model_call(self) -> None:
        create = self._post("/api/v1/tasks", self._command(
            "task.create", {
                "principal_id": "principal.api", "clearance": "internal",
                "request": "run the two-lane demo", "risk_class": "inspection_review",
                "autonomy_ceiling": "review_required", "allowed_evidence_scope": ["evidence.scope"],
                "permitted_worker_capabilities": ["reasoning"], "permitted_tools": [],
                "output_contract": "text", "verification_criteria": ["source_check"],
                "resource_budget": {"max_concurrency": 1},
            }, command_id="command.planning.create", idem="idempotency.planning.create", expected_sequence=None,
        ))
        self.assertEqual(create.status_code, 201, create.text)
        created_id = create.json()["task"]["task_id"]

        authorize = self._post("/api/v1/tasks/{}/authorize".format(created_id), self._command(
            "task.authorize", {"authorization_ref": "auth.planning"},
            command_id="command.planning.authorize", idem="idempotency.planning.authorize",
            expected_sequence=len(self.ledger.events), task_id=created_id,
        ))
        self.assertEqual(authorize.status_code, 202, authorize.text)

        review = self._get("/api/v1/tasks/{}/plan".format(created_id))
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["plan_state"], "ready", review.text)

        approve = self._post("/api/v1/tasks/{}/approve".format(created_id), self._command(
            "task.approve_plan", {"approval_ref": "approval.planning"},
            command_id="command.planning.approve", idem="idempotency.planning.approve",
            expected_sequence=len(self.ledger.events), task_id=created_id,
        ))
        self.assertEqual(approve.status_code, 202, approve.text)

        call = self._post("/api/v1/tasks/{}/model-call".format(created_id), self._command(
            "model.call", {
                "hardware_profile_ref": HW_REF, "request": _request_payload(created_id),
                "messages": [{"role": "user", "content": [{"kind": "text", "text": "hello"}]}],
                "output": {"mode": "text"},
            }, command_id="command.planning.call", idem="idempotency.planning.call",
            expected_sequence=len(self.ledger.events), task_id=created_id,
        ))
        self.assertEqual(call.status_code, 202, call.text)
        self.assertEqual(call.json()["model"]["selected_target"], TARGET_ID)
        event_types = [event.event_type for event in self.ledger.events]
        self.assertIn("routing.decision", event_types)
        self.assertIn("team.resource_plan.admitted", event_types)


if __name__ == "__main__":
    unittest.main()
