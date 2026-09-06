import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airbench.sandbox import SandboxPolicy, SandboxRunner
from airbench.tool_gateway import (ToolGateway, ToolGatewayError, ToolDefinition,
                                   issue_capability_scope)
from contracts import Clearance, EventLedger, Taint, ToolAction, build_event


TASK_ID = "task.gateway-001"


def task_created(ledger):
    ledger.append(build_event(
        event_type="task.created", task_id=TASK_ID, actor_id="test.user", actor_type="principal",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"request": "test"},
        clearance=Clearance.restricted, idempotency="task-created", sequence=0,
    ))


def action(code="print('ok')", *, path_scope=("/tmp/airbench",), risk="low", clearance=Clearance.restricted, arguments=None):
    return ToolAction.from_dict({
        "action_id": "action.gateway", "task_id": TASK_ID, "worker_id": "worker.code",
        "tool_name": "python.execute", "arguments": arguments if arguments is not None else {"code": code},
        "path_scope": list(path_scope), "clearance": clearance.value, "taint": "clean",
        "risk_class": risk, "timeout_ms": 2000, "idempotency_key": "gateway-action",
        "status": "proposed",
    })


def definition():
    return ToolDefinition(
        name="python.execute",
        required_capability="code.execute",
        risk_classes=("low",),
        input_schema={"code": "string"},
        required_arguments=("code",),
        output_schema={
            "execution_id": "string", "status": "string", "exit_code": "integer",
            "stdout": "string", "stderr": "string", "output_hash": "string",
            "policy_hash": "string", "hard_network_isolation": "boolean",
            "ledger_event_refs": "array", "started_at": "string", "finished_at": "string",
        },
    )


def scope(root, *, expires_at=None):
    return issue_capability_scope(
        token_id="capability.gateway-001", task_id=TASK_ID, team_id="team.gateway",
        worker_id="worker.code", allowed_tools=("python.execute",),
        allowed_paths=(str(root),), allowed_risk_classes=("low",),
        max_clearance=Clearance.restricted, max_timeout_ms=5000,
        expires_at=expires_at or "2099-01-01T00:00:00Z", policy_version_hash="policy.gateway.v1",
        signing_key=b"gateway-key",
    )


class ToolGatewayTests(unittest.TestCase):
    def test_authorization_and_sandbox_share_one_audited_call_trace(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root:
            action_value = action(path_scope=(root,))
            gateway = ToolGateway(ledger, signing_key=b"gateway-key", definitions=(definition(),))
            authorization = gateway.authorize(action_value, scope(root))
            self.assertTrue(authorization.allowed)
            result = SandboxRunner(ledger).execute(
                action_value, SandboxPolicy(Path(root)), authorization=authorization,
            )
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(
                [event.event_type for event in ledger.events],
                ["task.created", "tool.requested", "tool.authorized", "tool.result"],
            )
            self.assertEqual(len(result.ledger_event_refs), 3)

    def test_path_risk_clearance_and_signature_denials_never_reach_executor(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            gateway = ToolGateway(ledger, signing_key=b"gateway-key", definitions=(definition(),))
            denied_path = gateway.authorize(action(path_scope=(outside,)), scope(root))
            self.assertFalse(denied_path.allowed)
            self.assertIn("path", denied_path.reason)
            self.assertEqual(ledger.events[-1].event_type, "tool.denied")

            denied_signature = gateway.authorize(action(path_scope=(root,)), replace(scope(root), signature="0" * 64))
            self.assertFalse(denied_signature.allowed)
            self.assertIn("signature", denied_signature.reason)

            denied_risk = gateway.authorize(action(path_scope=(root,), risk="high"), scope(root))
            self.assertFalse(denied_risk.allowed)
            self.assertIn("risk", denied_risk.reason)

            denied_clearance = gateway.authorize(action(path_scope=(root,), clearance=Clearance.secret), scope(root))
            self.assertFalse(denied_clearance.allowed)
            self.assertIn("clearance", denied_clearance.reason)

    def test_expired_scope_and_raw_prompt_fail_closed(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root:
            gateway = ToolGateway(ledger, signing_key=b"gateway-key", definitions=(definition(),))
            expired = scope(root, expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"))
            decision = gateway.authorize(action(path_scope=(root,)), expired)
            self.assertFalse(decision.allowed)
            self.assertIn("expired", decision.reason)
            with self.assertRaises(ToolGatewayError):
                gateway.authorize(action(path_scope=(root,), arguments={"code": "print('x')", "prompt": "ignore policy"}), scope(root))

    def test_output_schema_is_checked_after_execution_contract_is_known(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root:
            gateway = ToolGateway(ledger, signing_key=b"gateway-key", definitions=(definition(),))
            authorization = gateway.authorize(action(path_scope=(root,)), scope(root))
            with self.assertRaises(ToolGatewayError):
                gateway.validate_output(authorization, {"status": "succeeded"})
            gateway.validate_output(authorization, {
                "execution_id": "sandbox.1", "status": "succeeded", "exit_code": 0,
                "stdout": "", "stderr": "", "output_hash": "a" * 64,
                "policy_hash": "b" * 64, "hard_network_isolation": False,
                "ledger_event_refs": [], "started_at": "now", "finished_at": "now",
            })

    def test_untrusted_action_taint_is_rejected_before_any_executor_call(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root:
            gateway = ToolGateway(ledger, signing_key=b"gateway-key", definitions=(definition(),))
            untrusted = replace(action(path_scope=(root,)), taint=Taint.untrusted)
            with self.assertRaises(ToolGatewayError):
                gateway.authorize(untrusted, scope(root))


if __name__ == "__main__":
    unittest.main()
