import tempfile
import unittest
from pathlib import Path

from airbench.tools.sandbox import (
    LocalSubprocessProvider,
    SandboxCapabilities,
    SandboxError,
    SandboxExecutionRequest,
    SandboxExecutionResponse,
    SandboxPolicy,
    SandboxRunner,
)
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


class RecordingProvider:
    def __init__(self) -> None:
        self.delegate = LocalSubprocessProvider()
        self.requests: list[SandboxExecutionRequest] = []

    @property
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities(
            provider_id="test.subprocess-provider",
            provider_version="test-1",
            hard_network_isolation=False,
            hard_filesystem_isolation=False,
            non_root_execution=False,
            restricted_syscalls=False,
            resource_limits=("code_bytes", "output_bytes", "wall_time"),
        )

    def verify(self) -> None:
        return None

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResponse:
        self.requests.append(request)
        return self.delegate.execute(request)


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
try:
    import socket
    socket.create_connection(('198.51.100.1', 443))
except Exception as exc:
    print('ipv4:' + type(exc).__name__)
try:
    import socket
    socket.create_connection(('2001:db8::1', 443))
except Exception as exc:
    print('ipv6:' + type(exc).__name__)
try:
    import socket
    socket.getaddrinfo('example.invalid', 443)
except Exception as exc:
    print('dns:' + type(exc).__name__)
try:
    import urllib.request
    urllib.request.urlopen('https://example.invalid')
except Exception as exc:
    print('proxy_or_http:' + type(exc).__name__)
try:
    import ensurepip
except Exception as exc:
    print('package_install:' + type(exc).__name__)
print('proxy_env:' + str(not any(key in __import__('os').environ for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'))))
"""
        with tempfile.TemporaryDirectory() as root:
            result = SandboxRunner(ledger).execute(action(code), SandboxPolicy(Path(root)))
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.stdout.count("ImportError"), 8)
        self.assertIn("ipv4:ImportError", result.stdout)
        self.assertIn("ipv6:ImportError", result.stdout)
        self.assertIn("dns:ImportError", result.stdout)
        self.assertIn("proxy_or_http:ImportError", result.stdout)
        self.assertIn("package_install:ImportError", result.stdout)
        self.assertIn("proxy_env:True", result.stdout)
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

    def test_provider_identity_capabilities_and_manifest_are_recorded(self):
        ledger = EventLedger()
        task_created(ledger, "task.sandbox")
        provider = RecordingProvider()
        with tempfile.TemporaryDirectory() as root:
            result = SandboxRunner(ledger, provider=provider).execute(
                action("print('provider boundary')"),
                SandboxPolicy(Path(root)),
            )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.provider_id, "test.subprocess-provider")
        self.assertEqual(result.provider_version, "test-1")
        self.assertEqual(result.manifest_hash, result.manifest.digest())
        self.assertEqual(result.manifest.resource_limits["max_processes"], None)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(provider.requests[0].command[1:3], ("-I", "-c"))
        self.assertEqual(provider.requests[0].root_dir, Path(root).resolve())
        self.assertEqual(provider.requests[0].resource_limits["max_wall_seconds"], 10.0)
        event = ledger.events[-1]
        self.assertEqual(event.event_type, "tool.result")
        self.assertEqual(event.payload["provider_id"], "test.subprocess-provider")
        self.assertEqual(event.payload["manifest_hash"], result.manifest_hash)
        self.assertNotIn(root, str(event.payload["manifest"]))

    def test_worker_output_is_capped_before_result_is_returned(self):
        ledger = EventLedger()
        task_created(ledger, "task.sandbox")
        with tempfile.TemporaryDirectory() as root:
            result = SandboxRunner(ledger).execute(
                action("print('x' * 1000)"),
                SandboxPolicy(Path(root), max_output_bytes=64),
            )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.stderr, "sandbox output limit exceeded")
        self.assertLessEqual(len(result.stdout.encode("utf-8")), 64)
        self.assertEqual(result.manifest.cleanup_status, "completed")

    def test_hard_isolation_requires_provider_capabilities_not_a_caller_flag(self):
        ledger = EventLedger()
        task_created(ledger, "task.sandbox")
        provider = RecordingProvider()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(SandboxError) as caught:
                SandboxRunner(ledger, provider=provider).execute(
                    action("print('must not run')"),
                    SandboxPolicy(Path(root), require_hard_network_isolation=True),
                )
        self.assertEqual(caught.exception.code, "network_isolation_unavailable")
        self.assertEqual(provider.requests, [])

    def test_unenforced_resource_limit_fails_closed(self):
        ledger = EventLedger()
        task_created(ledger, "task.sandbox")
        provider = RecordingProvider()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(SandboxError) as caught:
                SandboxRunner(ledger, provider=provider).execute(
                    action("print('must not run')"),
                    SandboxPolicy(Path(root), max_memory_bytes=1024 * 1024),
                )
        self.assertEqual(caught.exception.code, "resource_isolation_unavailable")
        self.assertEqual(provider.requests, [])


if __name__ == "__main__":
    unittest.main()
