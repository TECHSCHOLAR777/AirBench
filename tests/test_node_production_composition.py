"""Production Node composition test.

Proves the normal ``build_node_app`` composes File Intake, the Node-owned task
execution coordinator, the Deliverable Engine, and artifact review/approval,
then runs the documented first-slice chain end to end over the HTTP API with no
external model or network dependency.
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
PACK_TEMPLATE = REPO_ROOT / "packs" / "refinery_psu_v0" / "deliverable_templates.yaml"
STRUCTURAL_TEMPLATE = REPO_ROOT / "tests" / "fixtures" / "deliverable_templates_structural_only.yaml"
TASK_ID = "task.production.composition"


class ProductionNodeCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.env = patch.dict(os.environ, {
            "AIRBENCH_INTAKE_ROOT": str(root / "intake"),
            "AIRBENCH_ARTIFACT_ROOT": str(root / "artifacts"),
            "AIRBENCH_WORKSPACE_ROOT": str(root / "workspaces"),
            "AIRBENCH_DELIVERABLE_TEMPLATE_PATH": str(STRUCTURAL_TEMPLATE),
            "AIRBENCH_TASK_EXECUTION_ENABLED": "1",
        }, clear=False)
        self.env.start()
        config = NodeServerConfig(
            node_identity="node.production.test", bearer_token="test-token",
            domain_pack_ref="refinery-psu-v0", clearance=Clearance.internal,
            subject="demo.operator",
        )
        app = build_node_app(config, skip_startup_check=True, evidence_dir=root)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://node.production.test",
        )

    def tearDown(self) -> None:
        asyncio.run(self.client.aclose())
        self.env.stop()
        self._tmp.cleanup()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer test-token"}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async def run() -> httpx.Response:
            return await self.client.request(method, path, headers=self._headers(), **kwargs)
        return asyncio.run(run())

    def _command(self, command_type: str, arguments: dict, *, command_id: str, idem: str,
                 expected_sequence: int | None, task_id: str | None = None) -> dict:
        return {
            "command_id": command_id, "task_id": task_id, "actor": "demo.operator",
            "expected_sequence": expected_sequence, "idempotency_key": idem,
            "client_version": "0.1", "command_type": command_type, "arguments": arguments,
        }

    def _sequence(self, task_id: str) -> int:
        return int(self._request("GET", f"/api/v1/tasks/{task_id}/events").json()["next_sequence"])

    def test_upload_execute_review_and_approve(self) -> None:
        create = self._request("POST", "/api/v1/tasks", json=self._command(
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
            command_id="command.production.create", idem="idem.production.create",
            expected_sequence=None,
        ))
        self.assertEqual(create.status_code, 201, create.text)
        task_id = create.json()["task"]["task_id"]

        content = b"Inspection finding remains untrusted source data."
        upload = self._request(
            "POST", "/api/v1/intake/query-upload",
            data={"intake_mode": "query_upload", "task_id": task_id, "source_file_size": str(len(content))},
            files={"document": ("inspection-report.txt", content, "text/plain")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(upload.json()["taint"], "untrusted")

        authorize = self._request("POST", f"/api/v1/tasks/{task_id}/authorize", json=self._command(
            "task.authorize", {"authorization_ref": "auth.production"},
            command_id="command.production.authorize", idem="idem.production.authorize",
            expected_sequence=self._sequence(task_id), task_id=task_id,
        ))
        self.assertEqual(authorize.status_code, 202, authorize.text)

        plan = self._request("GET", f"/api/v1/tasks/{task_id}/plan")
        self.assertEqual(plan.status_code, 200, plan.text)
        self.assertEqual(plan.json()["plan_state"], "ready", plan.text)

        approve = self._request("POST", f"/api/v1/tasks/{task_id}/approve", json=self._command(
            "task.approve_plan", {"approval_ref": "approval.production"},
            command_id="command.production.approve", idem="idem.production.approve",
            expected_sequence=self._sequence(task_id), task_id=task_id,
        ))
        self.assertEqual(approve.status_code, 202, approve.text)

        review = self._request("GET", f"/api/v1/tasks/{task_id}/artifact-review")
        self.assertEqual(review.status_code, 200, review.text)
        body = review.json()
        artifact_id = body["artifactId"]
        self.assertEqual(body["approvalState"], "pending")
        self.assertEqual(body["structuralCheck"], "passed")
        self.assertEqual(body["verificationStatus"], "passed")
        self.assertEqual(body["approvalBlockingReasons"], [])

        signoff = self._request("POST", f"/api/v1/tasks/{task_id}/approve-artifact", json=self._command(
            "task.approve_artifact", {"artifact_id": artifact_id, "reason": "Operator approved."},
            command_id="command.production.signoff", idem="idem.production.signoff",
            expected_sequence=self._sequence(task_id), task_id=task_id,
        ))
        self.assertEqual(signoff.status_code, 202, signoff.text)

    def test_artifact_approval_rejects_foreign_artifact(self) -> None:
        create = self._request("POST", "/api/v1/tasks", json=self._command(
            "task.create",
            {
                "principal_id": "demo.operator", "clearance": "internal",
                "request": "Second task for artifact binding.",
                "risk_class": "inspection_review", "autonomy_ceiling": "review_required",
                "allowed_evidence_scope": ["task-input"],
                "permitted_worker_capabilities": ["reasoning"], "permitted_tools": [],
                "output_contract": "text", "verification_criteria": ["source_check"],
                "resource_budget": {"max_concurrency": 1},
            },
            command_id="command.production.create2", idem="idem.production.create2", expected_sequence=None,
        ))
        task_id = create.json()["task"]["task_id"]
        content = b"Second source."
        self._request(
            "POST", "/api/v1/intake/query-upload",
            data={"intake_mode": "query_upload", "task_id": task_id, "source_file_size": str(len(content))},
            files={"document": ("second.txt", content, "text/plain")},
        )
        self._request("POST", f"/api/v1/tasks/{task_id}/authorize", json=self._command(
            "task.authorize", {"authorization_ref": "auth.production.2"},
            command_id="command.production.authorize2", idem="idem.production.authorize2",
            expected_sequence=self._sequence(task_id), task_id=task_id,
        ))
        self._request("POST", f"/api/v1/tasks/{task_id}/approve", json=self._command(
            "task.approve_plan", {"approval_ref": "approval.production.2"},
            command_id="command.production.approve2", idem="idem.production.approve2",
            expected_sequence=self._sequence(task_id), task_id=task_id,
        ))
        mismatch = self._request("POST", f"/api/v1/tasks/{task_id}/approve-artifact", json=self._command(
            "task.approve_artifact", {"artifact_id": "artifact.not-this-task", "reason": "attempt"},
            command_id="command.production.signoff2", idem="idem.production.signoff2",
            expected_sequence=self._sequence(task_id), task_id=task_id,
        ))
        self.assertEqual(mismatch.status_code, 409, mismatch.text)
        self.assertEqual(mismatch.json()["code"], "artifact_mismatch")


if __name__ == "__main__":
    unittest.main()
