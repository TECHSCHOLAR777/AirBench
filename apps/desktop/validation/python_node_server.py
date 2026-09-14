"""Run a minimal real AirBench Python Node for cross-language validation.

This process is intentionally local-only and exists for validation. It uses
the real NodeApiService and Orchestrator, not the synthetic HTTP fixture.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ``python_node_server.py`` lives at apps/desktop/validation.  Keep the
# validation process rooted at the repository so its imports and pack-owned
# template path do not accidentally resolve to apps/apps/....
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import uvicorn  # noqa: E402

from airbench.delivery import LocalArtifactStore  # noqa: E402
from airbench.intake import FileIntakeLayer, LocalIntakeStore  # noqa: E402
from airbench.node.api import NodeApiConfig, NodeApiService, NodeApiError, create_app  # noqa: E402
from airbench.node.deliverable_gateway import LocalDeliverableGateway  # noqa: E402
from airbench.node.intake_gateway import LocalNodeIntakeGateway  # noqa: E402
from contracts import Clearance, EventLedger, Orchestrator  # noqa: E402
from local_task_run import LocalTaskExecutionCoordinator, LocalTaskRunError  # noqa: E402


class ValidationNodeService(NodeApiService):
    """Real Node API with an explicit local validation execution composition."""

    def __init__(self, *args, execution: LocalTaskExecutionCoordinator, **kwargs):
        super().__init__(*args, **kwargs)
        self._execution = execution
        self._replay_evidence_path = os.environ.get("AIRBENCH_WDIO_REPLAY_EVIDENCE_PATH")

    def authorize(self, subject: str, task_id: str, payload: dict[str, object]) -> dict[str, object]:
        result = super().authorize(subject, task_id, payload)
        try:
            self._execution.prepare(task_id)
        except LocalTaskRunError as exc:
            if self.orchestrator.state(task_id) not in {"failed", "cancelled"}:
                self.orchestrator.transition(task_id, "task.failed", {"failure_code": "local_validation_prepare_failed"})
            raise NodeApiError(409, "validation_prepare_failed", "The local validation Node could not prepare an admitted plan from the committed intake.") from exc
        return result

    def approve_plan(self, subject: str, task_id: str, payload: dict[str, object]) -> dict[str, object]:
        result = super().approve_plan(subject, task_id, payload)
        try:
            self._execution.execute(task_id)
        except LocalTaskRunError as exc:
            if self.orchestrator.state(task_id) not in {"failed", "cancelled"}:
                self.orchestrator.transition(task_id, "task.failed", {"failure_code": "local_validation_execution_failed"})
            raise NodeApiError(503, "validation_execution_failed", "The approved local validation plan did not produce a verified draft.") from exc
        self._write_replay_evidence(task_id)
        return result

    def _write_replay_evidence(self, task_id: str) -> None:
        if not self._replay_evidence_path:
            return
        events = [event for event in self.orchestrator.store.events if event.task_id == task_id]
        sequence_numbers = [event.sequence for event in events]
        has_gap = len(sequence_numbers) > 1 and any(
            sequence_numbers[i] != sequence_numbers[i - 1] + 1
            for i in range(1, len(sequence_numbers))
        )
        has_duplicate = len(sequence_numbers) != len(set(sequence_numbers))
        evidence = {
            "task_id": task_id,
            "has_gap": has_gap,
            "has_duplicate": has_duplicate,
            # Keep the evidence field names aligned with the WDIO contract.
            # This file is consumed by the replay smoke test, not by the
            # frontend projection, so the names must remain stable here.
            "sequences": sequence_numbers,
            "event_count": len(events),
        }
        path = Path(self._replay_evidence_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(evidence, indent=2))
        tmp.replace(path)


def build_app(args: argparse.Namespace):
    ledger = EventLedger()
    orchestrator = Orchestrator(ledger)
    intake_store = LocalIntakeStore(args.intake_root)
    artifact_store = LocalArtifactStore(Path(args.intake_root).parent / "artifacts")
    intake_layer = FileIntakeLayer(ledger, store=intake_store)
    intake_gateway = LocalNodeIntakeGateway(
        layer=intake_layer,
        store=intake_store,
        ledger=ledger,
        clearance_context=Clearance.restricted,
    )
    execution = LocalTaskExecutionCoordinator(
        orchestrator=orchestrator,
        ledger=ledger,
        intake_store=intake_store,
        artifact_root=artifact_store.root,
        workspace_root=Path(args.intake_root).parent / "workspaces",
        template_path=ROOT / "apps" / "desktop" / "validation" / "deliverable_templates.yaml",
        hardware_profile_path=Path(args.hardware_profile) if args.hardware_profile else None,
    )
    service = ValidationNodeService(
        orchestrator,
        NodeApiConfig(
            node_identity=args.node_identity,
            protocol_version="0.1",
            clearance_context=Clearance.restricted,
            authenticated_subject=args.subject,
            domain_pack_ref="validation-pack.v0",
            bearer_token=args.token,
            handshake_ledger_event_ref="ledger-validation-handshake",
            sovereignty_evidence_ref="evidence-validation-sovereignty",
            require_orchestrator_authorization=False,
        ),
        intake_gateway=intake_gateway,
        deliverable_gateway=LocalDeliverableGateway(
            ledger=ledger,
            artifact_store=artifact_store,
            node_identity=args.node_identity,
            protocol_version="0.1",
            clearance_context=Clearance.restricted,
        ),
        execution=execution,
    )
    return create_app(service)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--node-identity", default="python-node-validation")
    parser.add_argument("--subject", default="validation-user")
    parser.add_argument("--intake-root", required=True)
    parser.add_argument("--hardware-profile", type=str, default=None, help="Optional path to a HardwareProfile JSON fixture")
    args = parser.parse_args()
    uvicorn.run(build_app(args), host="127.0.0.1", port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
