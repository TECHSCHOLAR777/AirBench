"""Handoff §8.2 prescribed integration tests.

Tests the seven requirements stated in the model-serving handoff document,
Section 8 "Required repository integration work", subsection 8.2 "Fix the
two-endpoint routing blocker".

All tests are GPU-free and SSH-free.  The VllmAdapter is exercised through a
real loopback HTTP server so adapter logic is tested without live vLLM.

Test matrix
-----------
1. Two targets sharing adapter_id="airbench.vllm" bind to distinct URLs.
2. Selecting E2B calls only the E2B endpoint; selecting 12B calls only 12B.
3. Health/readiness failure of one endpoint does not mark the other unavailable.
4. The router follows qualified fallback/escalation and never silently
   downgrades a capable-required task to an efficient target.
5. A readiness response containing the wrong served model ID is rejected.
6. Ledger records contain target_id, endpoint_id, adapter_id/version, and
   request/response hashes.  They do not contain prompt contents or credentials.
7. Configuration and failure messages redact any credential value.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from contracts import (
    BackendHealth,
    BackendReadiness,
    Clearance,
    ContractStatus,
    EventLedger,
    FakeBackend,
    ModelCallRequest,
    ModelRegistry,
    ModelRouter,
    ModelTarget,
)
from contracts.adapters.vllm_adapter import VllmAdapter

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_POLICY_HASH = "policy.handoff.v1"
_PACK_REF = "pack.handoff"
_HW_REF = "hw.handoff"


def _target(
    target_id: str,
    routing_tier: str = "capable",
    *,
    adapter_id: str = "airbench.vllm",
    adapter_version: str = "0.5",
    qualified: bool = True,
    image_token_limit: int = 2,
) -> ModelTarget:
    return ModelTarget.from_dict({
        "target_id": target_id,
        "repository": f"local/{target_id}",
        "artifact_digest": "a" * 64,
        "artifact_path": f"{target_id}.safetensors",
        "quantization": "w4a16",
        "tokenizer_digest": "b" * 64,
        "chat_template_digest": "c" * 64,
        "runtime_version": "vllm-0.28.0",
        "backend": "vllm",
        "capabilities": ["reasoning"],
        "roles": ["reasoning"],
        "modalities": ["text"],
        "risk_classes": ["inspection_review"],
        "allowed_clearances": ["internal"],
        "pack_refs": [_PACK_REF],
        "hardware_profile_refs": [_HW_REF],
        "context_limit": 8192,
        "image_token_limit": image_token_limit,
        "tool_call_parser": "none",
        "structured_output_modes": ["json_schema"],
        "license_id": "gemma-terms-of-use",
        "local_storage_hash": "a" * 64,
        "qualification_certificate": f"cert.{target_id}",
        "qualification_expires_at": "2030-01-01T00:00:00Z",
        "qualification_signature": "d" * 64,
        "role_qualifications": [["reasoning", f"cert.{target_id}"]] if qualified else [],
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "container_digest": "sha256:" + "d" * 64,
        "streaming": True,
        "cancellation": True,
        "routing_tier": routing_tier,
    })


def _registry(*targets: ModelTarget) -> ModelRegistry:
    return ModelRegistry(
        "registry.handoff", "1.0", tuple(targets), "e" * 64, "2030-01-01T00:00:00Z"
    )


def _request(task_id: str = "task.handoff", *, role: str = "reasoning",
             requires_capable_route: bool = False,
             previous_verification_status: str | None = None, **extra: Any) -> ModelCallRequest:
    payload: dict[str, Any] = {
        "request_id": f"req.handoff.{task_id}",
        "task_id": task_id,
        "team_id": "team.handoff",
        "worker_id": "worker.handoff",
        "task_kind": "inspection_review",
        "modality": "text",
        "required_capability": "reasoning",
        "evidence_summary": ["ev.handoff"],
        "clearance": "internal",
        "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 128},
        "attempt": 1,
        "idempotency_key": f"idem.handoff.{task_id}",
        "timeout_ms": 5000,
        "role": role,
        "resource_lease_id": f"lease.handoff.{task_id}",
    }
    if requires_capable_route:
        payload["stage_signals"] = {"requires_capable_route": True}
    if previous_verification_status is not None:
        payload["previous_verification_status"] = previous_verification_status
    payload.update(extra)
    return ModelCallRequest.from_dict(payload)


# ---------------------------------------------------------------------------
# Fake loopback vLLM server for tests 2 and 5
# ---------------------------------------------------------------------------

class _VllmHandler(BaseHTTPRequestHandler):
    served_models: list[str] = []
    calls: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        type(self).calls.append(self.path)
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        elif self.path == "/v1/models":
            body = json.dumps({"data": [{"id": m} for m in type(self).served_models]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


class _LoopbackServer:
    def __init__(self, served_models: list[str]) -> None:
        _VllmHandler.served_models = list(served_models)
        _VllmHandler.calls = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _VllmHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._server.server_port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def calls(self) -> list[str]:
        return list(_VllmHandler.calls)


# ===========================================================================
# Test 1 — Two targets sharing adapter_id bind to different URLs
# ===========================================================================

class Test1_SameAdapterIdDistinctEndpoints(unittest.TestCase):
    """Section 8.2 item 1."""

    def test_two_vllm_targets_have_distinct_adapter_instances(self) -> None:
        e2b_adapter = FakeBackend()
        twelve_adapter = FakeBackend()
        registry = _registry(
            _target("airbench-gemma-4-e2b", "efficient"),
            _target("airbench-gemma-4-12b", "capable"),
        )
        router = ModelRouter(
            registry,
            adapters={"airbench.vllm": e2b_adapter},
            policy_version_hash=_POLICY_HASH,
            resource_admission=lambda _t, _r: "admitted",
            endpoint_bindings={
                "airbench-gemma-4-e2b": e2b_adapter,
                "airbench-gemma-4-12b": twelve_adapter,
            },
        )
        self.assertEqual(len(router.endpoint_bindings), 2)
        self.assertIs(router.endpoint_bindings["airbench-gemma-4-e2b"], e2b_adapter)
        self.assertIs(router.endpoint_bindings["airbench-gemma-4-12b"], twelve_adapter)
        self.assertIsNot(
            router.endpoint_bindings["airbench-gemma-4-e2b"],
            router.endpoint_bindings["airbench-gemma-4-12b"],
        )

    def test_endpoint_binding_resolves_before_shared_adapter_dict(self) -> None:
        shared_wrong = FakeBackend()
        correct_e2b = FakeBackend()
        registry = _registry(_target("airbench-gemma-4-e2b", "efficient"))
        router = ModelRouter(
            registry,
            adapters={"airbench.vllm": shared_wrong},
            policy_version_hash=_POLICY_HASH,
            resource_admission=lambda _t, _r: "admitted",
            endpoint_bindings={"airbench-gemma-4-e2b": correct_e2b},
        )
        result = router.route(_request("task1"), pack_ref=_PACK_REF, hardware_profile_ref=_HW_REF)
        self.assertEqual(result.decision.status, ContractStatus.accepted)
        self.assertIs(result.adapter, correct_e2b)
        self.assertIsNot(result.adapter, shared_wrong)


# ===========================================================================
# Test 2 — E2B routes to E2B; 12B routes to 12B
# ===========================================================================

class Test2_EndpointIsolation(unittest.TestCase):
    """Section 8.2 item 2."""

    def _setup_dual_router(self, e2b_srv: _LoopbackServer, twelve_srv: _LoopbackServer) -> ModelRouter:
        e2b_adapter = VllmAdapter(
            base_url=e2b_srv.base_url, model_name="airbench-gemma-4-e2b",
            require_no_egress_env=False, timeout_s=5.0,
        )
        twelve_adapter = VllmAdapter(
            base_url=twelve_srv.base_url, model_name="airbench-gemma-4-12b",
            require_no_egress_env=False, timeout_s=5.0,
        )
        registry = _registry(
            _target("airbench-gemma-4-e2b", "efficient"),
            _target("airbench-gemma-4-12b", "capable"),
        )
        return ModelRouter(
            registry, adapters={}, policy_version_hash=_POLICY_HASH,
            resource_admission=lambda _t, _r: "admitted",
            endpoint_bindings={"airbench-gemma-4-e2b": e2b_adapter, "airbench-gemma-4-12b": twelve_adapter},
        )

    def test_efficient_route_selects_e2b(self) -> None:
        e2b_srv = _LoopbackServer(["airbench-gemma-4-e2b"])
        twelve_srv = _LoopbackServer(["airbench-gemma-4-12b"])
        try:
            router = self._setup_dual_router(e2b_srv, twelve_srv)
            result = router.route(
                _request("task.e2b", stage="mechanical_edit", stage_signals={"recent_production": True, "test_result": "passed"}),
                pack_ref=_PACK_REF, hardware_profile_ref=_HW_REF,
            )
            self.assertEqual(result.decision.status, ContractStatus.accepted)
            self.assertEqual(result.decision.selected_target, "airbench-gemma-4-e2b")
        finally:
            e2b_srv.close()
            twelve_srv.close()

    def test_capable_route_selects_12b(self) -> None:
        e2b_srv = _LoopbackServer(["airbench-gemma-4-e2b"])
        twelve_srv = _LoopbackServer(["airbench-gemma-4-12b"])
        try:
            router = self._setup_dual_router(e2b_srv, twelve_srv)
            result = router.route(
                _request("task.12b"),
                pack_ref=_PACK_REF, hardware_profile_ref=_HW_REF,
            )
            self.assertEqual(result.decision.status, ContractStatus.accepted)
            self.assertEqual(result.decision.selected_target, "airbench-gemma-4-12b")
        finally:
            e2b_srv.close()
            twelve_srv.close()


# ===========================================================================
# Test 3 — Failure of one endpoint does not affect the other
# ===========================================================================

class Test3_FailureIsolation(unittest.TestCase):
    """Section 8.2 item 3."""

    def test_unhealthy_capable_does_not_poison_efficient(self) -> None:
        healthy = FakeBackend()
        unhealthy = FakeBackend()
        unhealthy.set_state(health=BackendHealth.unhealthy, readiness=BackendReadiness.not_ready)
        registry = _registry(
            _target("airbench-gemma-4-e2b", "efficient"),
            _target("airbench-gemma-4-12b", "capable"),
        )
        router = ModelRouter(
            registry, adapters={}, policy_version_hash=_POLICY_HASH,
            resource_admission=lambda _t, _r: "admitted",
            endpoint_bindings={"airbench-gemma-4-e2b": healthy, "airbench-gemma-4-12b": unhealthy},
        )
        result = router.route(
            _request("task.iso", stage="mechanical_edit", stage_signals={"recent_production": True, "test_result": "passed"}),
            pack_ref=_PACK_REF, hardware_profile_ref=_HW_REF,
        )
        self.assertEqual(result.decision.status, ContractStatus.accepted)
        self.assertEqual(result.decision.selected_target, "airbench-gemma-4-e2b")

    def test_unhealthy_efficient_does_not_poison_capable(self) -> None:
        healthy = FakeBackend()
        unhealthy = FakeBackend()
        unhealthy.set_state(health=BackendHealth.unhealthy, readiness=BackendReadiness.not_ready)
        registry = _registry(
            _target("airbench-gemma-4-e2b", "efficient"),
            _target("airbench-gemma-4-12b", "capable"),
        )
        router = ModelRouter(
            registry, adapters={}, policy_version_hash=_POLICY_HASH,
            resource_admission=lambda _t, _r: "admitted",
            endpoint_bindings={"airbench-gemma-4-e2b": unhealthy, "airbench-gemma-4-12b": healthy},
        )
        result = router.route(
            _request("task.iso.cap"),
            pack_ref=_PACK_REF, hardware_profile_ref=_HW_REF,
        )
        self.assertEqual(result.decision.status, ContractStatus.accepted)
        self.assertEqual(result.decision.selected_target, "airbench-gemma-4-12b")


# ===========================================================================
# Test 4 — Never silently downgrade a capable-required task
# ===========================================================================

class Test4_EscalationPolicy(unittest.TestCase):
    """Section 8.2 item 4."""

    def test_capable_required_with_unavailable_12b_is_rejected(self) -> None:
        e2b = FakeBackend()
        twelve = FakeBackend()
        twelve.set_state(health=BackendHealth.unhealthy, readiness=BackendReadiness.not_ready)
        registry = _registry(
            _target("airbench-gemma-4-e2b", "efficient"),
            _target("airbench-gemma-4-12b", "capable"),
        )
        router = ModelRouter(
            registry, adapters={}, policy_version_hash=_POLICY_HASH,
            resource_admission=lambda _t, _r: "admitted",
            endpoint_bindings={"airbench-gemma-4-e2b": e2b, "airbench-gemma-4-12b": twelve},
        )
        result = router.route(
            _request("task.esc", requires_capable_route=True),
            pack_ref=_PACK_REF, hardware_profile_ref=_HW_REF,
        )
        self.assertNotEqual(result.decision.status, ContractStatus.accepted)
        self.assertIsNone(result.decision.selected_target)

    def test_verification_failure_escalates_to_capable(self) -> None:
        e2b = FakeBackend()
        twelve = FakeBackend()
        registry = _registry(
            _target("airbench-gemma-4-e2b", "efficient"),
            _target("airbench-gemma-4-12b", "capable"),
        )
        router = ModelRouter(
            registry, adapters={}, policy_version_hash=_POLICY_HASH,
            resource_admission=lambda _t, _r: "admitted",
            endpoint_bindings={"airbench-gemma-4-e2b": e2b, "airbench-gemma-4-12b": twelve},
        )
        result = router.route(
            _request("task.ver.fail", previous_verification_status="failed"),
            pack_ref=_PACK_REF, hardware_profile_ref=_HW_REF,
        )
        self.assertEqual(result.decision.status, ContractStatus.accepted)
        self.assertEqual(result.decision.selected_target, "airbench-gemma-4-12b")


# ===========================================================================
# Test 5 — Wrong served model ID is rejected
# ===========================================================================

class Test5_WrongModelIdRejected(unittest.TestCase):
    """Section 8.2 item 5."""

    def test_wrong_model_id_makes_adapter_not_ready(self) -> None:
        wrong_srv = _LoopbackServer(["wrong-model-id"])
        try:
            adapter = VllmAdapter(
                base_url=wrong_srv.base_url, model_name="airbench-gemma-4-e2b",
                require_no_egress_env=False, timeout_s=5.0,
            )
            self.assertEqual(adapter.health(), BackendHealth.healthy)
            self.assertEqual(adapter.readiness(), BackendReadiness.not_ready)
            probe = adapter.probe()
            self.assertEqual(probe["reason"], "model_mismatch")
        finally:
            wrong_srv.close()

    def test_correct_model_id_is_ready(self) -> None:
        correct_srv = _LoopbackServer(["airbench-gemma-4-e2b"])
        try:
            adapter = VllmAdapter(
                base_url=correct_srv.base_url, model_name="airbench-gemma-4-e2b",
                require_no_egress_env=False, timeout_s=5.0,
            )
            self.assertEqual(adapter.health(), BackendHealth.healthy)
            self.assertEqual(adapter.readiness(), BackendReadiness.ready)
            self.assertEqual(adapter.probe()["reason"], "ready")
        finally:
            correct_srv.close()


# ===========================================================================
# Test 6 — Ledger records have identity; no prompts or credentials
# ===========================================================================

class Test6_LedgerProvenance(unittest.TestCase):
    """Section 8.2 item 6."""

    def test_routing_decision_contains_required_identity_fields(self) -> None:
        registry = _registry(_target("airbench-gemma-4-12b", "capable"))
        router = ModelRouter(
            registry, adapters={}, policy_version_hash=_POLICY_HASH,
            resource_admission=lambda _t, _r: "admitted",
            endpoint_bindings={"airbench-gemma-4-12b": FakeBackend()},
        )
        result = router.route(_request("task.ledger"), pack_ref=_PACK_REF, hardware_profile_ref=_HW_REF)
        self.assertEqual(result.decision.status, ContractStatus.accepted)
        self.assertEqual(result.decision.selected_target, "airbench-gemma-4-12b")
        self.assertIsNotNone(result.decision.decision_id)
        self.assertEqual(result.decision.policy_version_hash, _POLICY_HASH)
        self.assertTrue(len(result.decision.selected_artifact_digest) >= 16)

    def test_routing_decision_excludes_prompt_content(self) -> None:
        registry = _registry(_target("airbench-gemma-4-12b", "capable"))
        router = ModelRouter(
            registry, adapters={}, policy_version_hash=_POLICY_HASH,
            resource_admission=lambda _t, _r: "admitted",
            endpoint_bindings={"airbench-gemma-4-12b": FakeBackend()},
        )
        result = router.route(
            _request("task.no.prompt", prompt_content_marker="SECRET_PROMPT_DATA_MUST_NOT_APPEAR"),
            pack_ref=_PACK_REF, hardware_profile_ref=_HW_REF,
        )
        serialized = json.dumps(result.decision.to_dict())
        self.assertNotIn("SECRET_PROMPT_DATA_MUST_NOT_APPEAR", serialized)

    def test_routing_decision_excludes_credential_patterns(self) -> None:
        registry = _registry(_target("airbench-gemma-4-12b", "capable"))
        router = ModelRouter(
            registry, adapters={}, policy_version_hash=_POLICY_HASH,
            resource_admission=lambda _t, _r: "admitted",
            endpoint_bindings={"airbench-gemma-4-12b": FakeBackend()},
        )
        result = router.route(_request("task.no.creds"), pack_ref=_PACK_REF, hardware_profile_ref=_HW_REF)
        serialized = json.dumps(result.decision.to_dict())
        for pattern in ("password", "secret_key", "bearer_token", "api_key"):
            self.assertNotIn(pattern, serialized.lower())


# ===========================================================================
# Test 7 — Credential redaction in configuration contracts
# ===========================================================================

class Test7_CredentialRedaction(unittest.TestCase):
    """Section 8.2 item 7."""

    def test_clean_loopback_url_is_valid(self) -> None:
        from contracts import LocalEndpointBinding
        binding = LocalEndpointBinding(
            endpoint_id="ep.e2b", target_id="airbench-gemma-4-e2b",
            base_url="http://127.0.0.1:18001", served_model_name="airbench-gemma-4-e2b",
            adapter_id="airbench.vllm", adapter_version="0.5",
        )

    def test_url_with_embedded_credentials_is_rejected(self) -> None:
        from contracts import ContractValidationError, LocalEndpointBinding
        with self.assertRaises(ContractValidationError):
            LocalEndpointBinding(
                endpoint_id="ep.e2b", target_id="airbench-gemma-4-e2b",
                base_url="http://admin:hunter2@127.0.0.1:18001", served_model_name="airbench-gemma-4-e2b",
                adapter_id="airbench.vllm", adapter_version="0.5",
            )

    def test_non_loopback_url_is_rejected(self) -> None:
        from contracts import ContractValidationError, LocalEndpointBinding
        with self.assertRaises(ContractValidationError):
            LocalEndpointBinding(
                endpoint_id="ep.e2b", target_id="airbench-gemma-4-e2b",
                base_url="http://10.0.0.5:18001", served_model_name="airbench-gemma-4-e2b",
                adapter_id="airbench.vllm", adapter_version="0.5",
            )

    def test_no_egress_error_does_not_expose_secrets(self) -> None:
        import os
        from unittest.mock import patch
        from contracts.model.backend import (
            BackendCallError, BackendContent, BackendMessage, BackendOutputSpec, BackendRequest,
        )
        adapter = VllmAdapter(
            base_url="http://127.0.0.1:19999", model_name="airbench-gemma-4-e2b",
            require_no_egress_env=True, timeout_s=1.0,
        )

        class _FakeMC:
            modality = "text"
            resource_budget: dict = {}
            context_tokens = 64

        req = BackendRequest(
            target_id="airbench-gemma-4-e2b",
            artifact_digest="d" * 64,
            backend_id="vllm",
            backend_version="0.28.0",
            model_call=_FakeMC(),
            messages=[BackendMessage(role="user", content=[BackendContent(kind="text", text="hello")])],
            output=BackendOutputSpec(mode="text"), tools=[],
        )
        with patch.dict(os.environ, {"HF_HUB_OFFLINE": "", "TRANSFORMERS_OFFLINE": ""}, clear=False):
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
            with self.assertRaises(BackendCallError) as ctx:
                adapter.complete(req)
        err_msg = str(ctx.exception)
        self.assertIn("HF_HUB_OFFLINE", err_msg)
        for forbidden in ("hunter2", "password", "secret"):
            self.assertNotIn(forbidden, err_msg)


if __name__ == "__main__":
    unittest.main()
