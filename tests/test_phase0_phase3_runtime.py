"""Phase 0 runtime-lifecycle and Phase 3 typed-terminal-state tests.

GPU-free by design: everything runs against loopback fake servers or the
in-process Node app, so the live remote lanes are not required.

Covers:
- ``scripts/node_preflight.py`` port/Node/foreign-listener classification;
- the machine-readable startup summary in the ``node.started`` evidence sidecar
  and the ``NODE_STARTUP_SUMMARY`` log line (Phase 0);
- typed terminal task states for unexpected post-approval execution failures
  and typed ``failure_code`` propagation (Phase 3 item 3).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import httpx

from contracts import Clearance, EventLedger, HardwareProfile, Orchestrator
from contracts.models import NODE_PROTOCOL_VERSION

from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.server import NodeServerConfig, build_node_app
from airbench.node.task_execution import NodeTaskExecutionError
from airbench.node.task_planning import NodeTaskPlanner, PlannerConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = REPO_ROOT / "profiles" / "hardware" / "workstation_04.json"
STRUCTURAL_TEMPLATE = REPO_ROOT / "tests" / "fixtures" / "deliverable_templates_structural_only.yaml"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _ReadinessHandler(BaseHTTPRequestHandler):
    """Fake Node: readiness + model-serving routes with configurable states."""

    readiness_payload: dict = {"status": "ok"}
    readiness_status: int = 200
    serving_payload: dict = {"configured": True, "status": "ready", "endpoints": [
        {"target_id": "t", "health": "healthy", "readiness": "ready", "reason": "ready"}]}

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/v1/node/readiness":
            body = json.dumps(type(self).readiness_payload).encode()
            self.send_response(type(self).readiness_status)
        elif self.path == "/api/v1/node/model-serving":
            body = json.dumps(type(self).serving_payload).encode()
            self.send_response(200)
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


class _FakeServer:
    def __init__(self, handler_cls) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.port = self._server.server_port

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class _ForeignHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


class NodePreflightScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_script("node_preflight")
        self.json_argv = ["--json"]
        # Class-level handler state is shared across tests; reset it so one
        # degraded-lane test cannot pollute the next healthy-node test.
        _ReadinessHandler.readiness_status = 200
        _ReadinessHandler.readiness_payload = {"status": "ok"}
        _ReadinessHandler.serving_payload = {"configured": True, "status": "ready", "endpoints": [
            {"target_id": "t", "health": "healthy", "readiness": "ready", "reason": "ready"}]}

    def test_free_port_reports_ready_to_start(self) -> None:
        with patch("sys.stdout"):
            code = self.module.main(self.json_argv + ["--port", str(_free_port())])
        self.assertEqual(code, 0)

    def test_foreign_listener_is_refused(self) -> None:
        server = _FakeServer(_ForeignHandler)
        try:
            with patch("sys.stdout"):
                code = self.module.main(self.json_argv + ["--port", str(server.port)])
        finally:
            server.close()
        self.assertEqual(code, 1)

    def test_healthy_node_reports_ready(self) -> None:
        _ReadinessHandler.readiness_status = 200
        _ReadinessHandler.readiness_payload = {"status": "ok"}
        server = _FakeServer(_ReadinessHandler)
        try:
            with patch("sys.stdout"):
                code = self.module.main(self.json_argv + ["--port", str(server.port)])
        finally:
            server.close()
        self.assertEqual(code, 0)

    def test_degraded_node_lanes_report_degraded(self) -> None:
        _ReadinessHandler.serving_payload = {"configured": True, "status": "degraded", "endpoints": [
            {"target_id": "t", "health": "unhealthy", "readiness": "not_ready", "reason": "unhealthy"}]}
        server = _FakeServer(_ReadinessHandler)
        try:
            with patch("sys.stdout"):
                code = self.module.main(self.json_argv + ["--port", str(server.port)])
        finally:
            server.close()
        self.assertEqual(code, 1)

    def test_node_answering_503_readiness_is_still_recognized_as_a_node(self) -> None:
        _ReadinessHandler.readiness_status = 503
        _ReadinessHandler.readiness_payload = {"status": "degraded", "reason": "ledger replay in progress"}
        _ReadinessHandler.serving_payload = {"configured": True, "status": "ready", "endpoints": [
            {"target_id": "t", "health": "healthy", "readiness": "ready", "reason": "ready"}]}
        server = _FakeServer(_ReadinessHandler)
        try:
            with patch("sys.stdout"):
                code = self.module.main(self.json_argv + ["--port", str(server.port)])
        finally:
            server.close()
        self.assertEqual(code, 0)


class StartupSummaryTests(unittest.TestCase):
    def test_build_node_app_records_the_machine_readable_startup_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict("os.environ", {
                "AIRBENCH_INTAKE_ROOT": str(root / "intake"),
                "AIRBENCH_ARTIFACT_ROOT": str(root / "artifacts"),
                "AIRBENCH_DELIVERABLE_TEMPLATE_PATH": str(STRUCTURAL_TEMPLATE),
                "AIRBENCH_TASK_EXECUTION_ENABLED": "1",
            }, clear=False):
                config = NodeServerConfig(
                    node_identity="node.summary.test", bearer_token="t",
                    domain_pack_ref="refinery-psu-v0", clearance=Clearance.internal,
                    subject="demo.operator",
                )
                with self.assertLogs("airbench.node.server", level="INFO") as logs:
                    build_node_app(config, skip_startup_check=True, evidence_dir=root)
                summary_lines = [line for line in logs.output if "NODE_STARTUP_SUMMARY" in line]
            self.assertTrue(summary_lines, "the startup summary log line is missing")
            summary = json.loads(summary_lines[0].split("NODE_STARTUP_SUMMARY", 1)[1])
            self.assertTrue(summary["execution_enabled"])
            self.assertFalse(summary["model_serving_configured"])
            self.assertEqual(summary["intake_root"], str(root / "intake"))
            self.assertEqual(summary["ledger_head"], "ledger.empty")

            evidence = json.loads((root / "node_started_node_summary_test.json").read_text(encoding="utf-8"))
            self.assertEqual(evidence["startup_summary"], summary)
            self.assertEqual(evidence["protocol_version"], NODE_PROTOCOL_VERSION)


class _FailingExecution:
    """Duck-typed execution coordinator that raises like the real one."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.executed = False

    def preflight(self, task_id: str) -> None:
        return None

    def authorize(self, operator_id: str, task_id: str, operator_roles: tuple[str, ...] = ()) -> None:
        return None

    def execute(self, task_id: str) -> None:
        self.executed = True
        raise self.error


class TypedTerminalStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = EventLedger()
        self.orchestrator = Orchestrator(self.ledger)
        planner = NodeTaskPlanner(self.orchestrator, PlannerConfig(
            policy_version_hash="policy.typed",
            hardware_profile=HardwareProfile.from_dict(json.loads(PROFILE_PATH.read_text(encoding="utf-8"))),
        ))
        service = NodeApiService(
            self.orchestrator,
            NodeApiConfig(
                node_identity="node.typed", protocol_version="0.1",
                clearance_context=Clearance.internal, authenticated_subject="principal.typed",
                domain_pack_ref="pack.fake", bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.typed",
                sovereignty_evidence_ref="evidence.typed",
                require_orchestrator_authorization=False,
            ),
            task_planner=planner,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(service)), base_url="http://node.typed",
        )
        self.service = service
        task = self.orchestrator.create_task(
            principal_id="principal.typed", clearance=Clearance.internal,
            request="typed terminal failures", domain_pack_ref="pack.fake",
            risk_class="inspection_review", autonomy_ceiling="review_required",
            permitted_worker_capabilities=("reasoning",), verification_criteria=("source_check",),
            resource_budget={"max_concurrency": 1}, task_id="task.typed",
        )
        self.orchestrator.authorize(task.task_id, authorization_ref="auth.typed")
        planner.plan_and_admit(task)

    def tearDown(self) -> None:
        asyncio.run(self.client.aclose())

    def _approve(self, execution) -> httpx.Response:
        # Rebind the service's execution coordinator for this approval.
        self.service.execution = execution
        command = {
            "command_id": "command.typed.approve", "task_id": "task.typed", "actor": "principal.typed",
            "expected_sequence": len(self.ledger.events), "idempotency_key": "idem.typed.approve",
            "client_version": "0.1", "command_type": "task.approve_plan",
            "arguments": {"approval_ref": "approval.typed"},
        }

        async def run() -> httpx.Response:
            return await self.client.post("/api/v1/tasks/task.typed/approve",
                                          headers={"Authorization": "Bearer test-token"}, json=command)
        return asyncio.run(run())

    def test_typed_execution_error_records_its_failure_code(self) -> None:
        self.service.execution = _FailingExecution(
            NodeTaskExecutionError("the deterministic source verification did not pass",
                                   failure_code="verification_failed"))
        response = self._approve(self.service.execution)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "task_execution_failed")
        self.assertEqual(self.orchestrator.state("task.typed"), "failed")
        failed = next(event for event in self.ledger.events if event.event_type == "task.failed")
        self.assertEqual(failed.payload.get("failure_code"), "verification_failed")

    def test_unexpected_exception_becomes_a_typed_terminal_state(self) -> None:
        self.service.execution = _FailingExecution(RuntimeError("unexpected boom"))
        response = self._approve(self.service.execution)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "task_execution_internal_error")
        self.assertEqual(self.orchestrator.state("task.typed"), "failed")
        failed = next(event for event in self.ledger.events if event.event_type == "task.failed")
        self.assertEqual(failed.payload.get("failure_code"), "task_execution_internal_error")


if __name__ == "__main__":
    unittest.main()
