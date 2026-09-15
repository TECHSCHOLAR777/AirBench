"""Phase 1 model-lane preflight tests.

Covers the remote-GPU readiness seam from the end-to-end roadmap:
- ``VllmAdapter.probe()`` typed reasons over real loopback HTTP;
- ``NodeTaskExecutionCoordinator.preflight()`` refusing admission when no
  ready, qualified lane can serve the worker step;
- the ``task.approve_plan`` admission gate (503 ``model_lane_not_ready``,
  approval not committed, retryable);
- ``scripts/model_endpoint_preflight.py`` against a signed roster.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import httpx

from contracts import (
    Clearance,
    EventLedger,
    FakeBackend,
    ModelRegistry,
    ModelRouter,
    ModelTarget,
    Orchestrator,
    build_event,
)
from contracts.adapters.vllm_adapter import VllmAdapter

from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.task_execution import (
    ModelLaneNotReady,
    NodeExecutionConfig,
    NodeTaskExecutionCoordinator,
)
from airbench.node.task_planning import NodeTaskPlanner, PlannerConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = REPO_ROOT / "profiles" / "hardware" / "workstation_04.json"
SIGNING_KEY = b"p" * 32
HW_REF = "workstation-04"


class _FakeVllmHandler(BaseHTTPRequestHandler):
    """Serves /health and /v1/models with a configurable served model list."""

    served_models: list[str] = []
    models_ok: bool = True

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        elif self.path == "/v1/models":
            if not type(self).models_ok:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"data": [{"id": name} for name in type(self).served_models]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


class _ModelServer:
    def __init__(self, served_models: list[str], *, models_ok: bool = True) -> None:
        _FakeVllmHandler.served_models = served_models
        _FakeVllmHandler.models_ok = models_ok
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeVllmHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._server.server_port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _adapter(base_url: str, model_name: str = "airbench-gemma-4-12b") -> VllmAdapter:
    return VllmAdapter(
        base_url=base_url, model_name=model_name,
        require_no_egress_env=False, timeout_s=5.0,
    )


class VllmAdapterProbeTests(unittest.TestCase):
    def test_ready_lane(self) -> None:
        server = _ModelServer(["airbench-gemma-4-12b"])
        try:
            probe = _adapter(server.base_url).probe()
        finally:
            server.close()
        self.assertEqual(probe["health"], "healthy")
        self.assertEqual(probe["readiness"], "ready")
        self.assertEqual(probe["reason"], "ready")
        self.assertEqual(probe["served_models"], ["airbench-gemma-4-12b"])

    def test_model_mismatch_reports_served_ids(self) -> None:
        server = _ModelServer(["some-other-model"])
        try:
            probe = _adapter(server.base_url).probe()
        finally:
            server.close()
        self.assertEqual(probe["reason"], "model_mismatch")
        self.assertEqual(probe["readiness"], "not_ready")
        self.assertEqual(probe["served_models"], ["some-other-model"])

    def test_health_ok_but_models_unavailable_is_not_ready(self) -> None:
        server = _ModelServer(["airbench-gemma-4-12b"], models_ok=False)
        try:
            probe = _adapter(server.base_url).probe()
        finally:
            server.close()
        self.assertEqual(probe["health"], "healthy")
        self.assertEqual(probe["reason"], "not_ready")

    def test_dead_port_is_unhealthy(self) -> None:
        probe = _adapter("http://127.0.0.1:1").probe()
        self.assertEqual(probe["reason"], "unhealthy")
        self.assertEqual(probe["health"], "unhealthy")


# ---------------------------------------------------------------------------
# Coordinator preflight
# ---------------------------------------------------------------------------

def _target(target_id: str = "airbench-gemma-4-12b", adapter_id: str = "airbench.fake-backend") -> ModelTarget:
    return ModelTarget.from_dict({
        "target_id": target_id, "repository": "local/gemma", "artifact_digest": "a" * 64,
        "artifact_path": f"{target_id}.bin", "quantization": "int4", "tokenizer_digest": "b" * 64,
        "chat_template_digest": "c" * 64, "runtime_version": "vllm-0.28", "backend": "custom",
        "capabilities": ["reasoning"], "roles": ["reasoning"], "modalities": ["text"],
        "risk_classes": ["inspection_review"], "allowed_clearances": ["internal"],
        "pack_refs": ["pack.fake"], "hardware_profile_refs": ["node-execution-local"],
        "context_limit": 8192, "image_token_limit": 0, "tool_call_parser": "none",
        "structured_output_modes": ["json_schema"], "license_id": "license.gemma",
        "local_storage_hash": "a" * 64, "qualification_certificate": f"cert.{target_id}",
        "qualification_expires_at": "2030-01-01T00:00:00Z", "qualification_signature": "d" * 64,
        "role_qualifications": [["reasoning", f"cert.{target_id}"]],
        "adapter_id": adapter_id, "adapter_version": "1.0",
        "streaming": True, "cancellation": True, "routing_tier": "capable",
    })


def _coordinator(orchestrator: Orchestrator, ledger: EventLedger, router: ModelRouter) -> NodeTaskExecutionCoordinator:
    return NodeTaskExecutionCoordinator(
        orchestrator=orchestrator, ledger=ledger, intake_store=object(),
        config=NodeExecutionConfig(
            artifact_root="artifacts", workspace_root="workspaces", template_path="templates.yaml",
        ),
        model_router=router,
    )


class CoordinatorPreflightTests(unittest.TestCase):
    def _task(self, orchestrator: Orchestrator):
        return orchestrator.create_task(
            principal_id="principal.preflight", clearance=Clearance.internal,
            request="preflight the model lane", domain_pack_ref="pack.fake",
            risk_class="inspection_review", autonomy_ceiling="review_required",
            permitted_worker_capabilities=("reasoning",), verification_criteria=("source_check",),
            resource_budget={"max_concurrency": 1}, task_id="task.preflight.lane",
        )

    def test_preflight_raises_when_the_lane_is_down(self) -> None:
        ledger = EventLedger()
        orchestrator = Orchestrator(ledger)
        self._task(orchestrator)
        dead_adapter = VllmAdapter(
            base_url="http://127.0.0.1:1", model_name="airbench-gemma-4-12b",
            require_no_egress_env=False, timeout_s=1.0,
        )
        router = ModelRouter(
            ModelRegistry("registry.preflight", "1.0", (_target(),), "e" * 64, "2030-01-01T00:00:00Z"),
            {}, policy_version_hash="policy.preflight",
            resource_admission=lambda _target, _request: "admitted",
            endpoint_bindings={"airbench-gemma-4-12b": dead_adapter},
        )
        with self.assertRaises(ModelLaneNotReady) as caught:
            _coordinator(orchestrator, ledger, router).preflight("task.preflight.lane")
        self.assertIn("unhealthy", caught.exception.reason)

    def test_preflight_passes_with_a_ready_qualified_lane(self) -> None:
        ledger = EventLedger()
        orchestrator = Orchestrator(ledger)
        self._task(orchestrator)
        router = ModelRouter(
            ModelRegistry("registry.preflight", "1.0", (_target(),), "e" * 64, "2030-01-01T00:00:00Z"),
            {}, policy_version_hash="policy.preflight",
            resource_admission=lambda _target, _request: "admitted",
            endpoint_bindings={"airbench-gemma-4-12b": FakeBackend()},
        )
        _coordinator(orchestrator, ledger, router).preflight("task.preflight.lane")  # must not raise

    def test_preflight_is_a_noop_without_a_model_router(self) -> None:
        ledger = EventLedger()
        orchestrator = Orchestrator(ledger)
        self._task(orchestrator)
        coordinator = NodeTaskExecutionCoordinator(
            orchestrator=orchestrator, ledger=ledger, intake_store=object(),
            config=NodeExecutionConfig(
                artifact_root="artifacts", workspace_root="workspaces", template_path="templates.yaml",
            ),
            model_router=None,
        )
        coordinator.preflight("task.preflight.lane")  # must not raise

    def test_manifest_recovers_from_committed_evidence_after_store_restart(self) -> None:
        ledger = EventLedger()
        orchestrator = Orchestrator(ledger)
        task = self._task(orchestrator)
        source_hash = "a" * 64
        ledger.append(build_event(
            event_type="evidence.created", task_id=task.task_id, actor_id="node.intake",
            actor_type="service", payload_contract="EvidenceManifest", payload_version="1.0",
            payload={
                "intake_id": "intake.recovered", "revision_id": "revision.recovered",
                "source_hash": source_hash, "page_ids": ["page.recovered"],
                "provenance": {
                    "source_ref": "upload:query.txt", "confidence": 0.91,
                    "clearance": "internal", "taint": "untrusted",
                }, "destination": "task_scratch", "trust_profile": "query_untrusted",
                "latency_profile": "interactive",
            }, clearance=Clearance.internal, idempotency="evidence.recovered", sequence=len(ledger),
            previous_event_hash=ledger.head_hash,
        ))

        class MissingManifestStore:
            def load(self, _intake_id: str):
                return None

        coordinator = _coordinator(orchestrator, ledger, ModelRouter(
            ModelRegistry("registry.preflight", "1.0", (_target(),), "e" * 64, "2030-01-01T00:00:00Z"),
            {}, policy_version_hash="policy.preflight", resource_admission=lambda _target, _request: "admitted",
            endpoint_bindings={"airbench-gemma-4-12b": FakeBackend()},
        ))
        coordinator._intake_store = MissingManifestStore()
        recovered = coordinator._manifest(task.task_id)
        self.assertEqual(recovered.intake_id, "intake.recovered")
        self.assertEqual(recovered.source_ref, "upload:query.txt")
        self.assertEqual(recovered.pages[0].extraction_method, "ledger_recovery")
        self.assertEqual(recovered.pages[0].text, "")


# ---------------------------------------------------------------------------
# approve_plan admission gate
# ---------------------------------------------------------------------------

class _StubExecution:
    """Duck-typed execution coordinator used to test the API seam."""

    def __init__(self) -> None:
        self.preflight_reason: str | None = "both endpoints unhealthy"
        self.executed = False

    def preflight(self, task_id: str) -> None:
        if self.preflight_reason is not None:
            raise ModelLaneNotReady(self.preflight_reason)

    def authorize(self, operator_id: str, task_id: str, operator_roles: tuple[str, ...] = ()) -> None:
        return None

    def execute(self, task_id: str) -> None:
        self.executed = True


class ApprovePlanGateTests(unittest.TestCase):
    def setUp(self) -> None:
        from contracts import HardwareProfile

        self.ledger = EventLedger()
        self.orchestrator = Orchestrator(self.ledger)
        self.execution = _StubExecution()
        planner = NodeTaskPlanner(self.orchestrator, PlannerConfig(
            policy_version_hash="policy.gate",
            hardware_profile=HardwareProfile.from_dict(json.loads(PROFILE_PATH.read_text(encoding="utf-8"))),
        ))
        service = NodeApiService(
            self.orchestrator,
            NodeApiConfig(
                node_identity="node.gate", protocol_version="0.1",
                clearance_context=Clearance.internal, authenticated_subject="principal.gate",
                domain_pack_ref="pack.fake", bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.gate",
                sovereignty_evidence_ref="evidence.gate",
                require_orchestrator_authorization=False,
            ),
            task_planner=planner, execution=self.execution,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(service)), base_url="http://node.gate",
        )
        task = self.orchestrator.create_task(
            principal_id="principal.gate", clearance=Clearance.internal,
            request="gate the approval on lane readiness", domain_pack_ref="pack.fake",
            risk_class="inspection_review", autonomy_ceiling="review_required",
            permitted_worker_capabilities=("reasoning",), verification_criteria=("source_check",),
            resource_budget={"max_concurrency": 1}, task_id="task.gate",
        )
        self.orchestrator.authorize(task.task_id, authorization_ref="auth.gate")
        planner.plan_and_admit(task)

    def tearDown(self) -> None:
        asyncio.run(self.client.aclose())

    def _command(self, command_type: str, arguments: dict, *, command_id: str, idem: str) -> dict:
        return {
            "command_id": command_id, "task_id": "task.gate", "actor": "principal.gate",
            "expected_sequence": len(self.ledger.events), "idempotency_key": idem,
            "client_version": "0.1", "command_type": command_type, "arguments": arguments,
        }

    def _post(self, path: str, body: dict) -> httpx.Response:
        async def run() -> httpx.Response:
            return await self.client.post(path, headers={"Authorization": "Bearer test-token"}, json=body)
        return asyncio.run(run())

    def _get(self, path: str) -> httpx.Response:
        async def run() -> httpx.Response:
            return await self.client.get(path, headers={"Authorization": "Bearer test-token"})
        return asyncio.run(run())

    def test_approval_refused_while_the_lane_is_down_and_retry_succeeds(self) -> None:
        review = self._get("/api/v1/tasks/task.gate/plan")
        self.assertEqual(review.json()["plan_state"], "ready", review.text)

        refused = self._post("/api/v1/tasks/task.gate/approve", self._command(
            "task.approve_plan", {"approval_ref": "approval.gate"},
            command_id="command.gate.approve", idem="idem.gate.approve",
        ))
        self.assertEqual(refused.status_code, 503, refused.text)
        self.assertEqual(refused.json()["code"], "model_lane_not_ready")
        self.assertIn("unhealthy", refused.json()["message"])
        # The approval was not committed: the task remains plan-ready and the
        # stub execution never ran.
        self.assertEqual(self.orchestrator.state("task.gate"), "planned")
        self.assertFalse(self.execution.executed)

        self.execution.preflight_reason = None
        approved = self._post("/api/v1/tasks/task.gate/approve", self._command(
            "task.approve_plan", {"approval_ref": "approval.gate"},
            command_id="command.gate.approve2", idem="idem.gate.approve2",
        ))
        self.assertEqual(approved.status_code, 202, approved.text)
        self.assertTrue(self.execution.executed)


# ---------------------------------------------------------------------------
# scripts/model_endpoint_preflight.py
# ---------------------------------------------------------------------------

def _nested_target(target_id: str, served_name: str, endpoint_url: str) -> dict:
    return {
        'target_id': target_id, 'repository': f'local/{target_id}', 'revision': 'a' * 40,
        'artifact_hash': 'a' * 64, 'artifact_path': f'{target_id}.bin',
        'artifact_files': [f'{target_id}.bin'], 'local_storage_hash': 'a' * 64,
        'tokenizer': {'hash': 'bundled'}, 'chat_template': {'template_id': 'tpl', 'hash': 'bundled'},
        'quantization': {'format': 'w4a16'},
        'serving': {'runtime': 'vllm', 'runtime_version': '0.28.0', 'adapter_id': 'airbench.vllm',
                    'adapter_version': '0.5', 'container_digest': 'sha256:' + 'c' * 64,
                    'demo_endpoint_url': endpoint_url, 'demo_served_model_name': served_name},
        'limits': {'context_tokens': 8192, 'image_tokens': 0, 'max_concurrency': 1, 'max_batch_size': 1},
        'qualified_roles': [{'role': 'reasoning', 'certificate_id': f'cert.{target_id}',
                             'qualification_hash': 'e' * 64}],
        'tool_call_parser': 'none', 'structured_output_modes': ['json_schema'],
        'capabilities': ['reasoning'], 'modalities': ['text'], 'risk_classes': ['inspection_review'],
        'allowed_clearances': ['internal'], 'pack_refs': ['pack.fake'],
        'hardware_profile_refs': ['hw.fake'], 'license': 'license.gemma', 'routing_tier': 'capable',
        'qualification_expires_at': '2030-01-01T00:00:00Z', 'qualification_signature': '0' * 64,
    }


def _write_signed_roster(root: Path, targets: list[dict]) -> Path:
    import yaml

    from contracts.model.model_registry import _target_from_roster

    signed = []
    for raw in targets:
        item = json.loads(json.dumps(raw))
        normalized = _target_from_roster(item)
        item['qualification_signature'] = hmac.new(
            SIGNING_KEY,
            json.dumps(normalized.qualification_payload(), sort_keys=True, separators=(',', ':')).encode(),
            hashlib.sha256,
        ).hexdigest()
        signed.append(item)
    document = {
        'roster': {'roster_id': 'roster.preflight', 'schema_version': '1.0', 'targets': signed},
        'registry_id': 'roster.preflight', 'manifest_version': '1.0',
        'valid_until': '2030-01-01T00:00:00Z',
    }
    document['signature'] = hmac.new(
        SIGNING_KEY, json.dumps(document, sort_keys=True, separators=(',', ':')).encode(), hashlib.sha256,
    ).hexdigest()
    path = root / 'roster.yaml'
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding='utf-8')
    return path


class ModelEndpointPreflightScriptTests(unittest.TestCase):
    def _run(self, roster: Path) -> int:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "model_endpoint_preflight", REPO_ROOT / "scripts" / "model_endpoint_preflight.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        key = roster.parent / "key.bin"
        key.write_bytes(SIGNING_KEY)
        with patch.dict("os.environ", {}, clear=False):
            return module.main(["--roster", str(roster), "--signing-key", str(key), "--json"])

    def test_ready_lane_exits_zero(self) -> None:
        server = _ModelServer(["airbench-gemma-4-12b"])
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                roster = _write_signed_roster(Path(tmp), [
                    _nested_target("airbench-gemma-4-12b", "airbench-gemma-4-12b", server.base_url)])
                self.assertEqual(self._run(roster), 0)
        finally:
            server.close()

    def test_model_mismatch_exits_one(self) -> None:
        server = _ModelServer(["not-the-expected-model"])
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                roster = _write_signed_roster(Path(tmp), [
                    _nested_target("airbench-gemma-4-12b", "airbench-gemma-4-12b", server.base_url)])
                self.assertEqual(self._run(roster), 1)
        finally:
            server.close()

    def test_tampered_roster_exits_two(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            roster = _write_signed_roster(Path(tmp), [
                _nested_target("airbench-gemma-4-12b", "airbench-gemma-4-12b", "http://127.0.0.1:1")])
            text = roster.read_text(encoding="utf-8").replace("roster.preflight", "roster.tampered")
            roster.write_text(text, encoding="utf-8")
            self.assertEqual(self._run(roster), 2)


if __name__ == "__main__":
    unittest.main()
