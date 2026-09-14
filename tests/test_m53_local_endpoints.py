"""Local two-endpoint routing tests for the endpoint-binding contract.

These tests reproduce the production collision directly: two deployments are
served by the same adapter implementation (``adapter_id="airbench.vllm"``) but
must resolve to distinct adapter instances by ``target_id``.  No GPU, model
server, or network is required.
"""

from __future__ import annotations

import unittest

from contracts import (
    BackendHealth,
    ContractValidationError,
    ContractStatus,
    FakeBackend,
    LocalEndpointBinding,
    ModelCallRequest,
    ModelRegistry,
    ModelRouter,
    ModelTarget,
)


class _SharedImplementationBackend(FakeBackend):
    """Two deployments of one adapter class, exactly as two vLLM servers."""

    adapter_id = "airbench.vllm"
    adapter_version = "0.5"


def target(target_id: str, routing_tier: str = "capable") -> ModelTarget:
    return ModelTarget.from_dict({
        "target_id": target_id,
        "repository": "local/gemma",
        "artifact_digest": "a" * 64,
        "artifact_path": f"{target_id}.bin",
        "quantization": "int4",
        "tokenizer_digest": "b" * 64,
        "chat_template_digest": "c" * 64,
        "runtime_version": "vllm-0.28",
        "backend": "custom",
        "capabilities": ["reasoning"],
        "roles": ["reasoning"],
        "modalities": ["text"],
        "risk_classes": ["inspection_review"],
        "allowed_clearances": ["internal"],
        "pack_refs": ["pack.fake"],
        "hardware_profile_refs": ["hw.fake"],
        "context_limit": 8192,
        "image_token_limit": 0,
        "tool_call_parser": "none",
        "structured_output_modes": ["json_schema"],
        "license_id": "license.gemma",
        "local_storage_hash": "a" * 64,
        "qualification_certificate": f"cert.{target_id}",
        "qualification_expires_at": "2030-01-01T00:00:00Z",
        "qualification_signature": "d" * 64,
        "role_qualifications": [["reasoning", f"cert.{target_id}"]],
        "adapter_id": "airbench.vllm",
        "adapter_version": "0.5",
        "streaming": True,
        "cancellation": True,
        "routing_tier": routing_tier,
    })


def request(task_id: str = "task.m53.local", **routing: object) -> ModelCallRequest:
    payload = {
        "request_id": "request.m53.local",
        "task_id": task_id,
        "team_id": "team.m53.local",
        "worker_id": "worker.m53.local",
        "task_kind": "inspection_review",
        "modality": "text",
        "required_capability": "reasoning",
        "evidence_summary": ["evidence.m53.local"],
        "clearance": "internal",
        "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 128},
        "attempt": 1,
        "idempotency_key": "idempotency.m53.local",
        "timeout_ms": 1000,
        "role": "reasoning",
        "resource_lease_id": "lease.m53.local",
    }
    payload.update(routing)
    return ModelCallRequest.from_dict(payload)


def binding(endpoint_id: str, target_id: str, port: int, served_name: str) -> LocalEndpointBinding:
    return LocalEndpointBinding.from_dict({
        "endpoint_id": endpoint_id,
        "target_id": target_id,
        "base_url": f"http://127.0.0.1:{port}",
        "served_model_name": served_name,
        "adapter_id": "airbench.vllm",
        "adapter_version": "0.5",
    })


def registry(*targets: ModelTarget) -> ModelRegistry:
    return ModelRegistry("registry.local", "1.0", tuple(targets), "e" * 64, "2030-01-01T00:00:00Z")


class LocalEndpointBindingTests(unittest.TestCase):
    def test_loopback_binding_is_valid(self) -> None:
        value = binding("endpoint.e2b", "target.e2b", 18001, "airbench-gemma-4-e2b")
        self.assertEqual(value.execution_location, "local")
        self.assertEqual(value.base_url, "http://127.0.0.1:18001")

    def test_https_binding_is_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            LocalEndpointBinding.from_dict({
                "endpoint_id": "endpoint.remote",
                "target_id": "target.e2b",
                "base_url": "https://models.example.invalid",
                "served_model_name": "airbench-gemma-4-e2b",
                "adapter_id": "airbench.vllm",
                "adapter_version": "0.5",
            })

    def test_non_loopback_host_is_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            LocalEndpointBinding.from_dict({
                "endpoint_id": "endpoint.lan",
                "target_id": "target.e2b",
                "base_url": "http://10.0.0.5:18001",
                "served_model_name": "airbench-gemma-4-e2b",
                "adapter_id": "airbench.vllm",
                "adapter_version": "0.5",
            })

    def test_credentials_in_url_are_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            LocalEndpointBinding.from_dict({
                "endpoint_id": "endpoint.secret",
                "target_id": "target.e2b",
                "base_url": "http://user:pass@127.0.0.1:18001",
                "served_model_name": "airbench-gemma-4-e2b",
                "adapter_id": "airbench.vllm",
                "adapter_version": "0.5",
            })

    def test_remote_execution_location_is_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            LocalEndpointBinding.from_dict({
                "endpoint_id": "endpoint.e2b",
                "target_id": "target.e2b",
                "base_url": "http://127.0.0.1:18001",
                "served_model_name": "airbench-gemma-4-e2b",
                "adapter_id": "airbench.vllm",
                "adapter_version": "0.5",
                "execution_location": "remote",
            })


class TwoEndpointRoutingTests(unittest.TestCase):
    def _routers(self):
        e2b = _SharedImplementationBackend()
        twelve = _SharedImplementationBackend()
        bindings = {
            "target.gemma-e2b": e2b,
            "target.gemma-12b": twelve,
        }
        router = ModelRouter(
            registry(
                target("target.gemma-e2b", "efficient"),
                target("target.gemma-12b", "capable"),
            ),
            {"airbench.vllm": _SharedImplementationBackend()},
            policy_version_hash="policy.local",
            resource_admission=lambda _target, _request: "admitted",
            endpoint_bindings=bindings,
        )
        return router, e2b, twelve

    def test_capable_default_resolves_twelve_b_instance(self) -> None:
        router, _e2b, twelve = self._routers()
        result = router.route(request(), pack_ref="pack.fake", hardware_profile_ref="hw.fake")
        self.assertEqual(result.decision.status, ContractStatus.accepted)
        self.assertEqual(result.decision.selected_target, "target.gemma-12b")
        self.assertIs(result.adapter, twelve)

    def test_settled_stage_resolves_e2b_instance(self) -> None:
        router, e2b, _twelve = self._routers()
        result = router.route(
            request(stage="mechanical_edit", stage_signals={"recent_production": True, "test_result": "passed"}),
            pack_ref="pack.fake", hardware_profile_ref="hw.fake",
        )
        self.assertEqual(result.decision.selected_target, "target.gemma-e2b")
        self.assertEqual(result.decision.routing_mode, "efficient")
        self.assertIs(result.adapter, e2b)

    def test_same_adapter_id_does_not_collide(self) -> None:
        router, e2b, twelve = self._routers()
        self.assertIsNot(e2b, twelve)
        self.assertEqual(e2b.adapter_id, twelve.adapter_id)
        capable = router.route(request(), pack_ref="pack.fake", hardware_profile_ref="hw.fake")
        settled = router.route(
            request(stage="mechanical_edit", stage_signals={"recent_production": True, "test_result": "passed"}),
            pack_ref="pack.fake", hardware_profile_ref="hw.fake",
        )
        self.assertIsNot(capable.adapter, settled.adapter)

    def test_legacy_adapter_map_still_resolves_without_bindings(self) -> None:
        backend = _SharedImplementationBackend()
        router = ModelRouter(
            registry(target("target.gemma-12b", "capable")),
            {"airbench.vllm": backend},
            policy_version_hash="policy.legacy",
            resource_admission=lambda _target, _request: "admitted",
        )
        result = router.route(request(), pack_ref="pack.fake", hardware_profile_ref="hw.fake")
        self.assertEqual(result.decision.status, ContractStatus.accepted)
        self.assertIs(result.adapter, backend)

    def test_fallback_resolves_by_target_identity(self) -> None:
        primary = _SharedImplementationBackend()
        primary.set_state(health=BackendHealth.unhealthy)
        fallback = _SharedImplementationBackend()
        router = ModelRouter(
            registry(
                target("target.gemma-primary", "capable"),
                target("target.gemma-fallback", "capable"),
            ),
            {},
            policy_version_hash="policy.fallback",
            resource_admission=lambda _target, _request: "admitted",
            endpoint_bindings={
                "target.gemma-primary": primary,
                "target.gemma-fallback": fallback,
            },
        )
        result = router.route(request(), pack_ref="pack.fake", hardware_profile_ref="hw.fake")
        self.assertEqual(result.decision.selected_target, "target.gemma-fallback")
        self.assertIs(result.adapter, fallback)
        self.assertEqual(result.decision.fallback_target, "target.gemma-fallback")

    def test_escalation_refuses_efficient_only_downgrade(self) -> None:
        e2b = _SharedImplementationBackend()
        router = ModelRouter(
            registry(target("target.gemma-e2b", "efficient")),
            {},
            policy_version_hash="policy.no-downgrade",
            resource_admission=lambda _target, _request: "admitted",
            endpoint_bindings={"target.gemma-e2b": e2b},
        )
        result = router.route(
            request(previous_verification_status="failed"),
            pack_ref="pack.fake", hardware_profile_ref="hw.fake",
        )
        self.assertEqual(result.decision.status, ContractStatus.rejected)
        self.assertIsNone(result.adapter)
        self.assertIn("refusing silent downgrade", result.decision.reason)


if __name__ == "__main__":
    unittest.main()
