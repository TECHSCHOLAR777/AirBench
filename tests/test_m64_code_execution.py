import json
import tempfile
import unittest
from pathlib import Path

from airbench.code_execution import (CodeExecutionError, CodeExecutionRequest,
                                      CodeExecutionRunner)
from airbench.sandbox import SandboxPolicy, SandboxRunner
from contracts import Clearance, EventLedger, ToolAction, build_event


TASK_ID = "task.code-001"


def task_created(ledger):
    ledger.append(build_event(
        event_type="task.created", task_id=TASK_ID, actor_id="test.user", actor_type="principal",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"request": "test"},
        clearance=Clearance.restricted, idempotency="task-created", sequence=0,
    ))


def action(code, root, *, action_id="action.main", idempotency="main-action"):
    return ToolAction.from_dict({
        "action_id": action_id, "task_id": TASK_ID, "worker_id": "worker.code",
        "tool_name": "python.execute", "arguments": {"code": code},
        "path_scope": [str(root)], "clearance": "restricted", "taint": "clean",
        "risk_class": "low", "timeout_ms": 2000, "idempotency_key": idempotency,
        "status": "proposed",
    })


class CodeExecutionTests(unittest.TestCase):
    def test_successful_code_tests_artifact_and_calculation_are_manifested(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "calculation.txt"
            main_code = (
                f"from pathlib import Path\n"
                f"import json\n"
                f"Path({str(output)!r}).write_text('computed')\n"
                f"print('AIRBENCH_CALCULATION:' + json.dumps({{'net_total': 12.50}}))"
            )
            test_code = "assert 2 + 2 == 4\nprint('test passed')"
            request = CodeExecutionRequest(
                action=action(main_code, root),
                policy=SandboxPolicy(Path(root), allowed_write_paths=(Path(root),)),
                declared_tests=(action(test_code, root, action_id="action.test", idempotency="test-action"),),
                output_paths=(str(output),),
                calculation_names=("net_total",),
            )
            manifest = CodeExecutionRunner(SandboxRunner(ledger), ledger).run(request)

        self.assertEqual(manifest.status, "succeeded")
        self.assertEqual(manifest.test_results[0].status, "passed")
        self.assertEqual(manifest.calculations[0].value_text, "12.5")
        self.assertEqual(manifest.artifacts[0].byte_size, len(b"computed"))
        self.assertEqual(ledger.events[-1].event_type, "artifact.checked")
        self.assertEqual(ledger.events[-1].payload["provenance"]["taint"], "untrusted")

    def test_failed_declared_test_blocks_success(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root:
            request = CodeExecutionRequest(
                action=action("print('main')", root),
                policy=SandboxPolicy(Path(root)),
                declared_tests=(action("raise RuntimeError('no')", root, action_id="action.test", idempotency="test-action"),),
            )
            manifest = CodeExecutionRunner(SandboxRunner(ledger), ledger).run(request)
        self.assertEqual(manifest.status, "failed")
        self.assertEqual(manifest.failure_code, "declared_test_failed")

    def test_plain_prose_numbers_do_not_count_as_calculation_evidence(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root:
            request = CodeExecutionRequest(
                action=action("print('The calculated number is 123')", root),
                policy=SandboxPolicy(Path(root)),
                calculation_names=("total",),
            )
            manifest = CodeExecutionRunner(SandboxRunner(ledger), ledger).run(request)
        self.assertEqual(manifest.status, "needs_review")
        self.assertEqual(manifest.failure_code, "calculation_evidence_missing")
        self.assertEqual(manifest.calculations, ())

    def test_missing_or_out_of_scope_artifacts_fail_before_execution(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            request = CodeExecutionRequest(
                action=action("print('should not run')", root),
                policy=SandboxPolicy(Path(root), allowed_write_paths=(Path(root),)),
                output_paths=(str(Path(outside) / "forbidden.txt"),),
            )
            with self.assertRaises(CodeExecutionError):
                CodeExecutionRunner(SandboxRunner(ledger), ledger).run(request)
        self.assertEqual(len(ledger.events), 1)


if __name__ == "__main__":
    unittest.main()
