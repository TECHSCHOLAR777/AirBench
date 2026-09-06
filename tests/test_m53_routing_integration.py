"""M5.3 router and orchestrator integration tests."""

from __future__ import annotations

import unittest

from contracts import (
    BackendContent,
    BackendMessage,
    Clearance,
    ContractStatus,
    EventLedger,
    FakeBackend,
    ModelCallRequest,
    ModelRegistry,
    ModelRouter,
    ModelTarget,
    Orchestrator,
    TeamPlan,
)


def target() -> ModelTarget:
    return ModelTarget.from_dict({
        "target_id": "target.fake",
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
        "pack_refs": ["pack.fake"],
        "hardware_profile_refs": ["hw.fake"],
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
    })


def request(task_id: str = "task.m53.integration") -> ModelCallRequest:
    return ModelCallRequest.from_dict({
        "request_id": "request.m53.integration",
        "task_id": task_id,
        "team_id": "team.m53.integration",
        "worker_id": "worker.m53.integration",
        "task_kind": "inspection_review",
        "modality": "text",
        "required_capability": "reasoning",
        "evidence_summary": ["evidence.m53.integration"],
        "clearance": "internal",
        "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 100},
        "attempt": 1,
        "idempotency_key": "idempotency.m53.integration",
        "timeout_ms": 1000,
        "role": "reasoning",
        "resource_lease_id": "lease.m53.integration",
    })


def router(*, admission: str | None = "admitted", ledger: EventLedger | None = None) -> tuple[ModelRouter, FakeBackend]:
    backend = FakeBackend(ledger=ledger)
    registry = ModelRegistry("registry.fake", "1.0", (target(),), "e" * 64, "2030-01-01T00:00:00Z")
    callback = None if admission is None else lambda _target, _request: admission
    return ModelRouter(
        registry, {"airbench.fake-backend": backend}, policy_version_hash="policy.m53", resource_admission=callback,
    ), backend


class M53RoutingIntegrationTests(unittest.TestCase):
    def test_router_requires_registry_eligibility_and_admission(self) -> None:
        model_router, _backend = router()
        result = model_router.route(request(), pack_ref="pack.fake", hardware_profile_ref="hw.fake")
        self.assertEqual(result.decision.status, ContractStatus.accepted)
        self.assertEqual(result.decision.selected_target, "target.fake")
        self.assertEqual(result.decision.qualification_certificate, "cert.fake")

        review_router, _backend = router(admission=None)
        review = review_router.route(request(), pack_ref="pack.fake", hardware_profile_ref="hw.fake")
        self.assertEqual(review.decision.status, ContractStatus.needs_review)
        self.assertIsNone(review.adapter)

    def test_router_queues_without_calling_backend(self) -> None:
        model_router, backend = router(admission="queued")
        result = model_router.route(request(), pack_ref="pack.fake", hardware_profile_ref="hw.fake")
        self.assertEqual(result.decision.status, ContractStatus.queued)
        self.assertIsNone(result.adapter)
        self.assertEqual(backend.health().value, "healthy")

    def test_orchestrator_records_route_then_executes_adapter(self) -> None:
        ledger = EventLedger()
        orchestrator = Orchestrator(ledger)
        task = orchestrator.create_task(
            principal_id="principal.m53", clearance=Clearance.internal,
            request="run integration model call", domain_pack_ref="pack.fake",
            risk_class="inspection_review", autonomy_ceiling="review_required",
            permitted_worker_capabilities=("reasoning",), verification_criteria=("source_check",),
            resource_budget={"max_concurrency": 1}, task_id="task.m53.integration",
        )
        orchestrator.authorize(task.task_id, authorization_ref="auth.m53")
        orchestrator.commit_plan(TeamPlan(
            team_id="team.m53.integration", task_id=task.task_id,
            assignments=("assignment.m53",), dependency_graph={}, concurrency_ceiling=1,
            required_verification=True, completion_criteria=("source_check",),
            plan_version_hash="plan.m53", policy_version_hash="policy.m53", status=ContractStatus.proposed,
        ))
        model_router, _backend = router(ledger=ledger)
        execution = orchestrator.execute_model_call(
            request(), router=model_router, pack_ref="pack.fake", hardware_profile_ref="hw.fake",
            messages=(BackendMessage("user", (BackendContent(kind="text", text="hello"),)),),
        )
        self.assertIsNotNone(execution.response)
        self.assertEqual(execution.route.decision.status, ContractStatus.accepted)
        event_types = [event.event_type for event in ledger.events]
        self.assertIn("routing.decision", event_types)
        self.assertIn("model.call.started", event_types)
        self.assertIn("model.call.completed", event_types)
        self.assertIn("model.responded", event_types)


if __name__ == "__main__":
    unittest.main()
