"""Offline end-to-end prototype proof (roadmap Phases 3/6/9, GPU-free).

Drives the full governed chain over the Node HTTP API with **no model router**
(the deterministic local worker is used, so no remote GPU or tunnel is
required) against a durable ledger, then restarts the Node and proves:

- committed task, artifact, and event projections survive the restart;
- an authorized task can still be approved and executed after the restart
  (the in-memory preparation is rebuilt from the committed ledger);
- mid-flight execution state left by a crashed Node is reconciled at startup
  to a typed terminal state instead of staying silently stuck;
- a verified-but-unreviewed task is recovered to operator review;
- command replay after restart is idempotent (no duplicate tasks).

No external model, network, or GPU is used at any point.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from airbench.node.server import NodeServerConfig, build_node_app
from contracts import Clearance

REPO_ROOT = Path(__file__).resolve().parents[1]
STRUCTURAL_TEMPLATE = REPO_ROOT / "tests" / "fixtures" / "deliverable_templates_structural_only.yaml"


class OfflineEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ledger_path = self.root / "ledger.sqlite"
        self.signing_key_path = self.root / "signing.key"
        self.signing_key_path.write_bytes(b"offline-e2e-test-signing-key-32bytes!!")
        self._env = patch.dict(os.environ, {
            "AIRBENCH_INTAKE_ROOT": str(self.root / "intake"),
            "AIRBENCH_ARTIFACT_ROOT": str(self.root / "artifacts"),
            "AIRBENCH_WORKSPACE_ROOT": str(self.root / "workspaces"),
            "AIRBENCH_DELIVERABLE_TEMPLATE_PATH": str(STRUCTURAL_TEMPLATE),
            "AIRBENCH_TASK_EXECUTION_ENABLED": "1",
            # No AIRBENCH_MODEL_SERVING_ENABLED: the offline prototype runs the
            # deterministic local worker instead of the remote vLLM lanes.
        }, clear=False)
        self._env.start()
        self.config = NodeServerConfig(
            node_identity="node.offline.test", bearer_token="test-token",
            domain_pack_ref="refinery-psu-v0", clearance=Clearance.internal,
            subject="demo.operator", ledger_path=str(self.ledger_path),
            signing_key_path=str(self.signing_key_path),
        )

    def tearDown(self) -> None:
        for app in getattr(self, "_apps", ()):
            store = app.state.service.orchestrator.store
            if hasattr(store, "close"):
                store.close()
        self._env.stop()
        self._tmp.cleanup()

    # -- helpers -----------------------------------------------------------

    def _node(self) -> httpx.AsyncClient:
        app = build_node_app(self.config, skip_startup_check=True, evidence_dir=self.root)
        if not hasattr(self, "_apps"):
            self._apps = []
        self._apps.append(app)
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://node.offline.test",
        )

    def _request(self, client: httpx.AsyncClient, method: str, path: str, **kwargs) -> httpx.Response:
        async def run() -> httpx.Response:
            return await client.request(method, path, headers={"Authorization": "Bearer test-token"}, **kwargs)
        return asyncio.run(run())

    def _command(self, command_type: str, arguments: dict, *, command_id: str, idem: str,
                 expected_sequence: int | None, task_id: str | None = None) -> dict:
        return {
            "command_id": command_id, "task_id": task_id, "actor": "demo.operator",
            "expected_sequence": expected_sequence, "idempotency_key": idem,
            "client_version": "0.1", "command_type": command_type, "arguments": arguments,
        }

    def _sequence(self, client: httpx.AsyncClient, task_id: str) -> int:
        return int(self._request(client, "GET", f"/api/v1/tasks/{task_id}/events").json()["next_sequence"])

    def _create_task(self, client: httpx.AsyncClient, *, request: str, key: str) -> str:
        create = self._request(client, "POST", "/api/v1/tasks", json=self._command(
            "task.create",
            {
                "principal_id": "demo.operator", "clearance": "internal",
                "request": request,
                "risk_class": "inspection_review", "autonomy_ceiling": "review_required",
                "allowed_evidence_scope": ["task-input"],
                "permitted_worker_capabilities": ["reasoning"], "permitted_tools": [],
                "output_contract": "text", "verification_criteria": ["source_check"],
                "resource_budget": {"max_concurrency": 1},
            },
            command_id=f"command.offline.create.{key}", idem=f"idem.offline.create.{key}",
            expected_sequence=None,
        ))
        self.assertEqual(create.status_code, 201, create.text)
        return create.json()["task"]["task_id"]

    def _upload(self, client: httpx.AsyncClient, task_id: str, content: bytes, name: str = "inspection-report.txt") -> None:
        upload = self._request(
            client, "POST", "/api/v1/intake/query-upload",
            data={"intake_mode": "query_upload", "task_id": task_id, "source_file_size": str(len(content))},
            files={"document": (name, content, "text/plain")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)

    def _authorize(self, client: httpx.AsyncClient, task_id: str, key: str) -> None:
        authorize = self._request(client, "POST", f"/api/v1/tasks/{task_id}/authorize", json=self._command(
            "task.authorize", {"authorization_ref": f"auth.offline.{key}"},
            command_id=f"command.offline.authorize.{key}", idem=f"idem.offline.authorize.{key}",
            expected_sequence=self._sequence(client, task_id), task_id=task_id,
        ))
        self.assertEqual(authorize.status_code, 202, authorize.text)

    def _approve(self, client: httpx.AsyncClient, task_id: str, key: str) -> httpx.Response:
        return self._request(client, "POST", f"/api/v1/tasks/{task_id}/approve", json=self._command(
            "task.approve_plan", {"approval_ref": f"approval.offline.{key}"},
            command_id=f"command.offline.approve.{key}", idem=f"idem.offline.approve.{key}",
            expected_sequence=self._sequence(client, task_id), task_id=task_id,
        ))

    def _run_to_review(self, client: httpx.AsyncClient, task_id: str, key: str) -> str:
        """Upload, authorize, approve, and return the reviewable artifact id."""
        self._upload(client, task_id, b"Inspection finding remains untrusted source data.")
        self._authorize(client, task_id, key)
        plan = self._request(client, "GET", f"/api/v1/tasks/{task_id}/plan")
        self.assertEqual(plan.json()["plan_state"], "ready", plan.text)
        approve = self._approve(client, task_id, key)
        self.assertEqual(approve.status_code, 202, approve.text)
        snapshot = self._request(client, "GET", f"/api/v1/tasks/{task_id}")
        self.assertEqual(snapshot.json()["status"], "needs_review", snapshot.text)
        review = self._request(client, "GET", f"/api/v1/tasks/{task_id}/artifact-review")
        self.assertEqual(review.status_code, 200, review.text)
        return review.json()["artifactId"]

    # -- tests -------------------------------------------------------------

    def test_offline_chain_completes_and_survives_restart(self) -> None:
        client = self._node()
        task_id = self._create_task(client, request="Review the uploaded inspection source.", key="chain")
        artifact_id = self._run_to_review(client, task_id, "chain")

        signoff = self._request(client, "POST", f"/api/v1/tasks/{task_id}/approve-artifact", json=self._command(
            "task.approve_artifact", {"artifact_id": artifact_id, "reason": "Operator approved."},
            command_id="command.offline.signoff.chain", idem="idem.offline.signoff.chain",
            expected_sequence=self._sequence(client, task_id), task_id=task_id,
        ))
        self.assertEqual(signoff.status_code, 202, signoff.text)
        # The wire status stays in the review family; the recorded artifact
        # approval is the authoritative sign-off evidence.
        self.assertEqual(
            self._request(client, "GET", f"/api/v1/tasks/{task_id}/artifact-review").json()["approvalState"],
            "approved",
        )
        events_before = self._request(client, "GET", f"/api/v1/tasks/{task_id}/events").json()
        asyncio.run(client.aclose())

        # Restart the Node against the same durable ledger and stores.  The
        # signed-off task must survive unchanged (a signed-off task is a valid
        # resting state and must NOT be resurrected into review).
        client = self._node()
        snapshot = self._request(client, "GET", f"/api/v1/tasks/{task_id}")
        self.assertEqual(snapshot.status_code, 200, snapshot.text)
        review = self._request(client, "GET", f"/api/v1/tasks/{task_id}/artifact-review")
        self.assertEqual(review.json()["artifactId"], artifact_id, review.text)
        self.assertEqual(review.json()["approvalState"], "approved", review.text)
        events_after = self._request(client, "GET", f"/api/v1/tasks/{task_id}/events").json()
        self.assertEqual(events_after["next_sequence"], events_before["next_sequence"])

        # Replay of the create command is idempotent after the restart.
        replay = self._request(client, "POST", "/api/v1/tasks", json=self._command(
            "task.create",
            {
                "principal_id": "demo.operator", "clearance": "internal",
                "request": "Review the uploaded inspection source.",
                "risk_class": "inspection_review", "autonomy_ceiling": "review_required",
                "allowed_evidence_scope": ["task-input"],
                "permitted_worker_capabilities": ["reasoning"], "permitted_tools": [],
                "output_contract": "text", "verification_criteria": ["source_check"],
                "resource_budget": {"max_concurrency": 1},
            },
            command_id="command.offline.create.chain", idem="idem.offline.create.chain",
            expected_sequence=None,
        ))
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertEqual(replay.json()["task"]["task_id"], task_id)
        asyncio.run(client.aclose())

    def test_authorized_task_resumes_after_restart(self) -> None:
        client = self._node()
        task_id = self._create_task(client, request="Task authorized before the restart.", key="resume")
        self._upload(client, task_id, b"Resumed task source content is still untrusted data.")
        self._authorize(client, task_id, "resume")
        asyncio.run(client.aclose())

        # The Node restarts; the authorized task must still be approvable.
        client = self._node()
        approve = self._approve(client, task_id, "resume")
        self.assertEqual(approve.status_code, 202, approve.text)
        snapshot = self._request(client, "GET", f"/api/v1/tasks/{task_id}")
        self.assertEqual(snapshot.json()["status"], "needs_review", snapshot.text)
        review = self._request(client, "GET", f"/api/v1/tasks/{task_id}/artifact-review")
        self.assertEqual(review.json()["structuralCheck"], "passed", review.text)
        asyncio.run(client.aclose())

    def test_midflight_task_is_reconciled_at_startup(self) -> None:
        client = self._node()
        task_id = self._create_task(client, request="Task interrupted mid-execution.", key="interrupted")
        self._upload(client, task_id, b"Interrupted task source.")
        self._authorize(client, task_id, "interrupted")
        # Simulate a crash mid-execution: the worker started but the process
        # died before any further committed transition.
        app = client._transport.app  # noqa: SLF001 - test reaches the composed service
        app.state.service.orchestrator.transition(task_id, "worker.started", {"worker_id": "node-worker"})
        asyncio.run(client.aclose())

        client = self._node()
        snapshot = self._request(client, "GET", f"/api/v1/tasks/{task_id}")
        self.assertEqual(snapshot.json()["status"], "failed", snapshot.text)
        events = self._request(client, "GET", f"/api/v1/tasks/{task_id}/events").json()
        self.assertTrue([e for e in events["events"] if e.get("eventType") == "task.failed"], events)
        store = client._transport.app.state.service.orchestrator.store  # noqa: SLF001 - test inspects the committed ledger
        failed = [
            event for event in store.events
            if event.task_id == task_id and event.event_type == "task.failed"
        ]
        self.assertTrue(failed)
        self.assertEqual(failed[-1].payload["failure_code"], "node_restart_interrupted")
        asyncio.run(client.aclose())

    def test_verified_task_is_recovered_to_review_at_startup(self) -> None:
        client = self._node()
        task_id = self._create_task(client, request="Task verified but never moved to review.", key="verified")
        self._upload(client, task_id, b"Verified task source.")
        self._authorize(client, task_id, "verified")
        # Simulate a crash after verification passed but before the review
        # request was committed: verification.completed is a governed event and
        # carries full provenance, exactly as the real VerificationRunner does.
        app = client._transport.app  # noqa: SLF001 - test reaches the composed service
        orchestrator = app.state.service.orchestrator
        orchestrator.transition(task_id, "worker.started", {"worker_id": "node-worker"})
        orchestrator.transition(task_id, "join_barrier.waiting", {"barrier_id": "barrier"})
        orchestrator.transition(task_id, "verification.completed", {
            "status": "passed",
            "rule_set_version": "node.execution.v1",
            "provenance": {
                "source_ref": "query-upload:simulated",
                "confidence": 0.9,
                "clearance": "internal",
                "taint": "untrusted",
            },
        })
        asyncio.run(client.aclose())

        client = self._node()
        snapshot = self._request(client, "GET", f"/api/v1/tasks/{task_id}")
        self.assertEqual(snapshot.json()["status"], "needs_review", snapshot.text)
        store = client._transport.app.state.service.orchestrator.store  # noqa: SLF001 - test inspects the committed ledger
        recovered = [
            event for event in store.events
            if event.task_id == task_id and event.event_type == "human.review.required"
        ]
        self.assertTrue(recovered)
        self.assertIn("recovered", recovered[-1].payload["reason"])
        asyncio.run(client.aclose())


if __name__ == "__main__":
    unittest.main()
