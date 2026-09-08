import tempfile
import unittest
from pathlib import Path

from airbench.sandbox import SandboxError, SandboxPolicy, SandboxRunner
from contracts import Clearance, EventLedger, ToolAction, build_event


def task_created(ledger: EventLedger, task_id: str) -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test.user", actor_type="principal",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"request": "test"},
        clearance=Clearance.restricted, idempotency="task-created", sequence=0,
    ))


def action(code: str, task_id: str = "task.sandbox") -> ToolAction:
    return ToolAction.from_dict({
        "action_id": "action.execute", "task_id": task_id, "worker_id": "worker.code",
        "tool_name": "python.execute", "arguments": {"code": code}, "path_scope": ["sandbox"],
        "clearance": "restricted", "taint": "clean", "risk_class": "low", "timeout_ms": 2000,
        "idempotency_key": "sandbox-action", "status": "proposed",
    })


class SandboxTests(unittest.TestCase):
    def test_code_runs_with_bounded_output_and_ledger_trace(self):
        ledger = EventLedger()
        task_created(ledger, "task.sandbox")
        with tempfile.TemporaryDirectory() as root:
            policy = SandboxPolicy(Path(root))
            result = SandboxRunner(ledger).execute(action("print('computed evidence')"), policy)
            self.assertEqual(list(Path(root).iterdir()), [])
        self.assertEqual(result.status, "succeeded")
        self.assertIn("computed evidence", result.stdout)
        self.assertFalse(result.hard_network_isolation)
        self.assertEqual([event.event_type for event in ledger.events], ["task.created", "tool.requested", "tool.authorized", "tool.result"])
        self.assertEqual(len(result.ledger_event_refs), 3)

    def test_network_dns_subprocess_and_package_paths_are_denied(self):
        ledger = EventLedger()
        task_created(ledger, "task.sandbox")
        code = """
try:
    import socket
    socket.getaddrinfo('example.invalid', 443)
except Exception as exc:
    print(type(exc).__name__)
try:
    import subprocess
    subprocess.run(['echo', 'blocked'])
except Exception as exc:
    print(type(exc).__name__)
try:
    import pip
except Exception as exc:
    print(type(exc).__name__)
"""
        with tempfile.TemporaryDirectory() as root:
            result = SandboxRunner(ledger).execute(action(code), SandboxPolicy(Path(root)))
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.stdout.count("ImportError"), 3)
        self.assertIn("ImportError", result.stdout)

    def test_timeout_and_hard_isolation_requirement_fail_safely(self):
        ledger = EventLedger()
        task_created(ledger, "task.sandbox")
        with tempfile.TemporaryDirectory() as root:
            timeout_result = SandboxRunner(ledger).execute(action("while True: pass"), SandboxPolicy(Path(root), max_wall_seconds=0.01))
            self.assertEqual(timeout_result.status, "timed_out")
            with self.assertRaises(SandboxError) as caught:
                SandboxRunner(ledger).execute(action("print('not started')"), SandboxPolicy(Path(root), require_hard_network_isolation=True))
        self.assertEqual(caught.exception.code, "network_isolation_unavailable")
        self.assertEqual(ledger.events[-1].event_type, "tool.result")

    def test_invalid_worker_output_still_writes_a_result_and_cleans_scratch(self):
        ledger = EventLedger()
        task_created(ledger, "task.sandbox")
        with tempfile.TemporaryDirectory() as root:
            result = SandboxRunner(ledger).execute(
                action("import sys; sys.__stdout__.write('not-json')"),
                SandboxPolicy(Path(root)),
            )
            self.assertEqual(list(Path(root).iterdir()), [])
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.stderr, "sandbox worker failed or returned invalid output")
        self.assertEqual(ledger.events[-1].event_type, "tool.result")

    def test_write_scope_is_limited_to_sandbox_root(self):
        ledger = EventLedger()
        task_created(ledger, "task.sandbox")
        with tempfile.TemporaryDirectory() as root:
            result = SandboxRunner(ledger).execute(action("open('/outside.txt', 'w').write('no')"), SandboxPolicy(Path(root)))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.output_hash.__len__(), 64)
        self.assertEqual(ledger.events[-1].event_type, "tool.result")


if __name__ == "__main__":
    unittest.main()
