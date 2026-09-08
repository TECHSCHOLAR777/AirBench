"""M5.3 router and orchestrator integration tests."""

from __future__ import annotations

import unittest

from contracts import (
    BackendContent,
    BackendHealth,
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


def target(
    target_id: str = "target.fake",
    routing_tier: str = "capable",
    adapter_id: str = "airbench.fake-backend",
) -> ModelTarget:
    return ModelTarget.from_dict({
        "target_id": target_id,
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
        "adapter_id": adapter_id,
        "adapter_version": "1.0",
        "streaming": True,
        "cancellation": True,
        "routing_tier": routing_tier,
    })


def request(task_id: str = "task.m53.integration", **routing: object) -> ModelCallRequest:
    payload = {
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
    }
    payload.update(routing)
    return ModelCallRequest.from_dict(payload)


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

    def test_settled_stage_signal_prefers_efficient_role_qualified_target(self) -> None:
        efficient = target("target.efficient", "efficient")
        capable = target("target.capable", "capable")
        registry = ModelRegistry("registry.stage", "1.0", (efficient, capable), "e" * 64, "2030-01-01T00:00:00Z")
        router_instance = ModelRouter(
            registry,
            {
                "airbench.fake-backend": FakeBackend(),
            },
            policy_version_hash="policy.stage",
            resource_admission=lambda _target, _request: "admitted",
        )
        result = router_instance.route(
            request(
                stage="mechanical_edit",
                stage_signals={"recent_production": True, "test_result": "passed"},
            ),
            pack_ref="pack.fake",
            hardware_profile_ref="hw.fake",
        )
        self.assertEqual(result.decision.selected_target, "target.efficient")
        self.assertEqual(result.decision.routing_mode, "efficient")

    def test_failed_check_sticks_to_capable_target_for_same_stage(self) -> None:
        efficient = target("target.efficient", "efficient")
        capable = target("target.capable", "capable")
        registry = ModelRegistry("registry.sticky", "1.0", (efficient, capable), "e" * 64, "2030-01-01T00:00:00Z")
        router_instance = ModelRouter(
            registry,
            {"airbench.fake-backend": FakeBackend()},
            policy_version_hash="policy.sticky",
            resource_admission=lambda _target, _request: "admitted",
        )
        failed = router_instance.route(
            request(
                stage="draft",
                previous_verification_status="failed",
                stage_signals={"test_result": "failed", "error_severity": "critical"},
            ),
            pack_ref="pack.fake",
            hardware_profile_ref="hw.fake",
        )
        self.assertEqual(failed.decision.selected_target, "target.capable")
        self.assertTrue(failed.decision.escalation_sticky)

        later = router_instance.route(
            request(task_id="task.m53.integration", stage="draft"),
            pack_ref="pack.fake",
            hardware_profile_ref="hw.fake",
        )
        self.assertEqual(later.decision.selected_target, "target.capable")
        self.assertEqual(later.decision.routing_mode, "escalated_sticky")

    def test_escalation_refuses_efficient_only_fallback(self) -> None:
        registry = ModelRegistry(
            "registry.no-downgrade", "1.0", (target("target.efficient", "efficient"),),
            "e" * 64, "2030-01-01T00:00:00Z",
        )
        router_instance = ModelRouter(
            registry,
            {"airbench.fake-backend": FakeBackend()},
            policy_version_hash="policy.no-downgrade",
            resource_admission=lambda _target, _request: "admitted",
        )
        result = router_instance.route(
            request(previous_verification_status="failed", stage_signals={"error_severity": "critical"}),
            pack_ref="pack.fake",
            hardware_profile_ref="hw.fake",
        )
        self.assertEqual(result.decision.status, ContractStatus.rejected)
        self.assertIsNone(result.target)
        self.assertIn("refusing silent downgrade", result.decision.reason)

    def test_fallback_selection_preserves_attempt_and_writes_ledger_event(self) -> None:
        primary = target("target.primary", "capable", "airbench.primary-backend")
        fallback = target("target.fallback", "capable", "airbench.fallback-backend")
        primary_backend = FakeBackend()
        primary_backend.set_state(health=BackendHealth.unhealthy)
        fallback_backend = FakeBackend()
        registry = ModelRegistry("registry.fallback", "1.0", (primary, fallback), "e" * 64, "2030-01-01T00:00:00Z")
        router_instance = ModelRouter(
            registry,
            {
                "airbench.primary-backend": primary_backend,
                "airbench.fallback-backend": fallback_backend,
            },
            policy_version_hash="policy.fallback",
            resource_admission=lambda _target, _request: "admitted",
        )
        result = router_instance.route(
            request(attempt=2), pack_ref="pack.fake", hardware_profile_ref="hw.fake"
        )
        self.assertEqual(result.decision.attempt, 2)
        self.assertEqual(result.decision.selected_target, "target.fallback")
        self.assertEqual(result.decision.fallback_target, "target.fallback")

        ledger = EventLedger()
        orchestrator = Orchestrator(ledger)
        task = orchestrator.create_task(
            principal_id="principal.m53.fallback", clearance=Clearance.internal,
            request="run fallback model call", domain_pack_ref="pack.fake",
            risk_class="inspection_review", autonomy_ceiling="review_required",
            permitted_worker_capabilities=("reasoning",), verification_criteria=("source_check",),
            resource_budget={"max_concurrency": 1}, task_id="task.m53.integration",
        )
        orchestrator.authorize(task.task_id, authorization_ref="auth.m53.fallback")
        orchestrator.commit_plan(TeamPlan(
            team_id="team.m53.integration", task_id=task.task_id,
            assignments=("assignment.m53",), dependency_graph={}, concurrency_ceiling=1,
            required_verification=True, completion_criteria=("source_check",),
            plan_version_hash="plan.m53", policy_version_hash="policy.fallback", status=ContractStatus.proposed,
        ))
        orchestrator.execute_model_call(
            request(attempt=2), router=router_instance, pack_ref="pack.fake",
            hardware_profile_ref="hw.fake",
            messages=(BackendMessage("user", (BackendContent(kind="text", text="hello"),)),),
        )
        self.assertIn("routing.fallback.selected", [event.event_type for event in ledger.events])


if __name__ == "__main__":
    unittest.main()
