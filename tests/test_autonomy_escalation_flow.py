"""Autonomy escalation flow over the Node API (demo composition, GPU-free).

Reproduces the live demo defect where a task that escalated to human authority
and was then authorized by the operator's plan approval remained "blocked" in
the autonomy panel, and clicking Authorize returned HTTP 503.

Root causes proven here:
1. ``score`` re-added the escalation hold after ``execute()`` re-scored the
   already-authorized action, so ``is_blocked`` stayed true forever.
2. ``authorize`` always appended a new ``authority.authorized`` event; because
   the operator's plan approval had already recorded one, the re-append hit an
   idempotency conflict surfaced as 503 ``transition_not_committed``.
3. When the pack-selected execution action required a role the operator did
   not hold, the approve request surfaced an internal-error 503 after the
   approval had already been committed, instead of a typed authorization
   failure before commit.

The Node is composed exactly like the offline demo: signed domain pack (loaded
unsigned in tests), durable SQLite ledger, autonomy governor from pack risk
rules, Node-owned execution, and no model router.
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
PACK_DIR = REPO_ROOT / "packs" / "refinery_psu_v0"
PACK_SIGNING_KEY = REPO_ROOT / ".airbench_signing_key"
STRUCTURAL_TEMPLATE = REPO_ROOT / "tests" / "fixtures" / "deliverable_templates_structural_only.yaml"


class AutonomyEscalationFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.signing_key_path = self.root / "signing.key"
        self.signing_key_path.write_bytes(b"autonomy-flow-test-signing-key-32b")
        self._apps: list = []
        self._env = None

    def tearDown(self) -> None:
        if self._env is not None:
            self._env.stop()
        for app in self._apps:
            store = app.state.service.orchestrator.store
            if hasattr(store, "close"):
                store.close()
        self._tmp.cleanup()

    def _start_node(self, *, action_kind: str | None) -> httpx.AsyncClient:
        env = {
            "AIRBENCH_INTAKE_ROOT": str(self.root / "intake"),
            "AIRBENCH_ARTIFACT_ROOT": str(self.root / "artifacts"),
            "AIRBENCH_WORKSPACE_ROOT": str(self.root / "workspaces"),
            "AIRBENCH_DELIVERABLE_TEMPLATE_PATH": str(STRUCTURAL_TEMPLATE),
            "AIRBENCH_TASK_EXECUTION_ENABLED": "1",
            "AIRBENCH_PACK_DIR": str(PACK_DIR),
            "AIRBENCH_PACK_ALLOW_UNSIGNED": "1",
            "AIRBENCH_PACK_SIGNING_KEY_PATH": str(PACK_SIGNING_KEY),
            "AIRBENCH_LEDGER_PATH": str(self.root / "ledger.sqlite"),
            "AIRBENCH_SIGNING_KEY_PATH": str(self.signing_key_path),
        }
        if action_kind is not None:
            env["AIRBENCH_EXECUTION_ACTION_KIND"] = action_kind
        self._env = patch.dict(os.environ, env, clear=False)
        self._env.start()
        config = NodeServerConfig(
            node_identity="node.autonomy.test", bearer_token="test-token",
            domain_pack_ref="refinery-psu-v0", clearance=Clearance.internal,
            subject="demo.operator", ledger_path=str(self.root / "ledger.sqlite"),
            signing_key_path=str(self.signing_key_path),
        )
        app = build_node_app(config, skip_startup_check=True, evidence_dir=self.root)
        self._apps.append(app)
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://node.autonomy.test",
        )

    # -- helpers -----------------------------------------------------------

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

    def _create_task(self, client: httpx.AsyncClient, key: str) -> str:
        create = self._request(client, "POST", "/api/v1/tasks", json=self._command(
            "task.create",
            {
                "principal_id": "demo.operator", "clearance": "internal",
                "request": "Draft the inspection approval note.",
                "risk_class": "inspection_review", "autonomy_ceiling": "review_required",
                "allowed_evidence_scope": ["task-input"],
                "permitted_worker_capabilities": ["reasoning"], "permitted_tools": [],
                "output_contract": "text", "verification_criteria": ["source_check"],
                "resource_budget": {"max_concurrency": 1},
            },
            command_id=f"command.autonomy.create.{key}", idem=f"idem.autonomy.create.{key}",
            expected_sequence=None,
        ))
        self.assertEqual(create.status_code, 201, create.text)
        return create.json()["task"]["task_id"]

    def _upload(self, client: httpx.AsyncClient, task_id: str, key: str) -> None:
        content = b"Inspection finding remains untrusted source data."
        upload = self._request(
            client, "POST", "/api/v1/intake/query-upload",
            data={"intake_mode": "query_upload", "task_id": task_id, "source_file_size": str(len(content))},
            files={"document": ("inspection-report.txt", content, "text/plain")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)

    def _authorize_task(self, client: httpx.AsyncClient, task_id: str, key: str) -> None:
        authorize = self._request(client, "POST", f"/api/v1/tasks/{task_id}/authorize", json=self._command(
            "task.authorize", {"authorization_ref": f"auth.autonomy.{key}"},
            command_id=f"command.autonomy.authorize.{key}", idem=f"idem.autonomy.authorize.{key}",
            expected_sequence=self._sequence(client, task_id), task_id=task_id,
        ))
        self.assertEqual(authorize.status_code, 202, authorize.text)

    def _approve(self, client: httpx.AsyncClient, task_id: str, key: str) -> httpx.Response:
        return self._request(client, "POST", f"/api/v1/tasks/{task_id}/approve", json=self._command(
            "task.approve_plan", {"approval_ref": f"approval.autonomy.{key}"},
            command_id=f"command.autonomy.approve.{key}", idem=f"idem.autonomy.approve.{key}",
            expected_sequence=self._sequence(client, task_id), task_id=task_id,
        ))

    # -- tests -------------------------------------------------------------

    def test_authorized_escalation_unblocks_and_authorize_is_idempotent(self) -> None:
        client = self._start_node(action_kind="prepare_approval_note")
        task_id = self._create_task(client, "ok")
        self._upload(client, task_id, "ok")
        self._authorize_task(client, task_id, "ok")

        approve = self._approve(client, task_id, "ok")
        self.assertEqual(approve.status_code, 202, approve.text)
        snapshot = self._request(client, "GET", f"/api/v1/tasks/{task_id}")
        self.assertEqual(snapshot.json()["status"], "needs_review", snapshot.text)

        # The escalation happened (1 decision) but the operator's plan
        # approval already recorded the required human authorization, so the
        # task must not remain blocked.
        autonomy = self._request(client, "GET", f"/api/v1/tasks/{task_id}/autonomy")
        self.assertEqual(autonomy.status_code, 200, autonomy.text)
        body = autonomy.json()
        self.assertGreaterEqual(len(body["decisions"]), 1)
        self.assertEqual(body["decisions"][0]["outcome"], "escalate")
        self.assertFalse(body["is_blocked"], body)

        # Clicking Authorize for the already-authorized action must replay the
        # recorded authorization, not raise an idempotency conflict (503).
        decision = body["decisions"][0]
        authorize = self._request(
            client, "POST", f"/api/v1/tasks/{task_id}/autonomy/authorize",
            json={"operator_id": "demo.operator", "action_id": decision["action_id"]},
        )
        self.assertEqual(authorize.status_code, 200, authorize.text)
        self.assertTrue(authorize.json()["authorized"], authorize.text)

        after = self._request(client, "GET", f"/api/v1/tasks/{task_id}/autonomy").json()
        self.assertFalse(after["is_blocked"], after)
        asyncio.run(client.aclose())

    def test_role_gap_fails_typed_before_approval_commit(self) -> None:
        # Without the action-kind pin the pack's most consequential action
        # (release_approval_note, requires authorized_approver) gates execution;
        # the demo operator only holds human_reviewer.
        client = self._start_node(action_kind=None)
        task_id = self._create_task(client, "role")
        self._upload(client, task_id, "role")
        self._authorize_task(client, task_id, "role")

        approve = self._approve(client, task_id, "role")
        self.assertEqual(approve.status_code, 403, approve.text)
        self.assertEqual(approve.json()["code"], "autonomy_authority_insufficient", approve.text)
        self.assertIn("authorized_approver", approve.json()["message"], approve.text)

        # The approval must not have been committed and the task must remain
        # approvable once the operator holds the required role, not failed.
        snapshot = self._request(client, "GET", f"/api/v1/tasks/{task_id}")
        self.assertNotEqual(snapshot.json()["status"], "failed", snapshot.text)
        plan = self._request(client, "GET", f"/api/v1/tasks/{task_id}/plan")
        self.assertEqual(plan.json()["plan_state"], "ready", plan.text)
        asyncio.run(client.aclose())


if __name__ == "__main__":
    unittest.main()
