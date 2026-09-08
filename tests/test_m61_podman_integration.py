import os
import tempfile
import unittest
from pathlib import Path

from airbench.tools.podman_provider import PodmanProvider
from airbench.tools.sandbox import SandboxPolicy, SandboxRunner
from contracts import Clearance, EventLedger, ToolAction, build_event


@unittest.skipUnless(
    os.name != "nt" and os.environ.get("AIRBENCH_PODMAN_INTEGRATION") == "1",
    "requires a Linux/POSIX host, a running rootless Podman runtime, and an explicit integration opt-in",
)
class PodmanIntegrationTests(unittest.TestCase):
    def test_airbench_runner_executes_through_pinned_provider(self):
        image = os.environ["AIRBENCH_PODMAN_IMAGE"]
        ledger = EventLedger()
        task_id = "task.podman.integration"
        ledger.append(build_event(
            event_type="task.created", task_id=task_id, actor_id="test.user", actor_type="principal",
            payload_contract="TaskEnvelope", payload_version="1.0", payload={"request": "provider"},
            clearance=Clearance.restricted, idempotency="podman-task-created", sequence=0,
        ))
        action = ToolAction.from_dict({
            "action_id": "action.podman", "task_id": task_id, "worker_id": "worker.code",
            "tool_name": "python.execute", "arguments": {"code": "print('integrated-provider')"},
            "path_scope": ["/tmp/airbench"], "clearance": "restricted", "taint": "clean",
            "risk_class": "low", "timeout_ms": 5000, "idempotency_key": "podman-action",
            "status": "proposed",
        })
        with tempfile.TemporaryDirectory(prefix="airbench-podman-") as root:
            root_path = Path(root)
            provider = PodmanProvider(image, expected_runtime_version=os.environ.get("AIRBENCH_PODMAN_VERSION"))
            result = SandboxRunner(ledger, provider=provider).execute(
                action,
                SandboxPolicy(
                    root_path,
                    max_wall_seconds=5,
                    max_cpu_seconds=2,
                    max_memory_bytes=128 * 1024 * 1024,
                    max_disk_bytes=64 * 1024 * 1024,
                    max_processes=32,
                    require_hard_network_isolation=True,
                ),
            )
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.hard_network_isolation)
        self.assertEqual(result.provider_id, "podman.rootless")
        self.assertEqual(result.manifest.cleanup_status, "completed")
        self.assertTrue(any(ref.startswith("podman:verification:") for ref in result.isolation_evidence_refs))
        self.assertEqual(ledger.events[-1].event_type, "tool.result")


if __name__ == "__main__":
    unittest.main()
