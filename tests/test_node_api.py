import asyncio
import unittest

import httpx

from contracts import Clearance, ContractStatus, EventLedger, Orchestrator, TeamPlan, build_event
from airbench.node_api import NodeApiConfig, NodeApiService, create_app


class NodeApiTests(unittest.TestCase):
    def setUp(self):
        self.ledger = EventLedger()
        self.orchestrator = Orchestrator(self.ledger)
        self.service = NodeApiService(
            self.orchestrator,
            NodeApiConfig(
                node_identity="node.test.local",
                protocol_version="0.1",
                clearance_context=Clearance.restricted,
                authenticated_subject="principal.api",
                domain_pack_ref="pack.refinery.v0",
                bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.test",
                sovereignty_evidence_ref="evidence.sovereignty.test",
                require_orchestrator_authorization=False,
            ),
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.service)),
            base_url="http://node.test",
        )

    def tearDown(self):
        asyncio.run(self.client.aclose())

    def request(self, method, path, **kwargs):
        async def run():
            return await self.client.request(method, path, **kwargs)

        return asyncio.run(run())

    def headers(self, token="test-token"):
        return {"Authorization": f"Bearer {token}"}

    def task_body(self, **overrides):
        arguments = {
            "principal_id": "principal.api",
            "clearance": "internal",
            "request": "Review the local inspection report",
            "domain_pack_ref": "pack.refinery.v0",
            "risk_class": "high",
            "autonomy_ceiling": "review_required",
            "allowed_evidence_scope": ["inspection-report"],
            "permitted_worker_capabilities": ["reasoning"],
            "permitted_tools": ["calculator"],
            "output_contract": "approval-note",
            "verification_criteria": ["source_check"],
            "resource_budget": {"max_concurrency": 1, "max_steps": 8},
        }
        arguments.update(overrides)
        return self.command(
            command_id="command.create.1",
            task_id=None,
            expected_sequence=None,
            idempotency_key="idempotency.create.1",
            command_type="task.create",
            arguments=arguments,
        )

    def command(self, *, command_id, task_id, expected_sequence, idempotency_key, command_type, arguments):
        return {
            "command_id": command_id,
            "task_id": task_id,
            "actor": "principal.api",
            "expected_sequence": expected_sequence,
            "idempotency_key": idempotency_key,
            "client_version": "0.1",
            "command_type": command_type,
            "arguments": arguments,
        }

    def create_task(self):
        response = self.request("POST", "/api/v1/tasks", headers=self.headers(), json=self.task_body())
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["task"], response.json()["snapshot"]

    def append_event(self, event_type, task_id, payload, clearance=Clearance.internal):
        event = build_event(
            event_type=event_type,
            task_id=task_id,
            actor_id="fixture.service",
            actor_type="service",
            payload_contract="FixturePayload",
            payload_version="1.0",
            payload=payload,
            clearance=clearance,
            idempotency=f"fixture.{event_type}.{len(self.ledger.events)}",
            sequence=len(self.ledger.events),
            previous_event_hash=self.ledger.head_hash,
        )
        return self.ledger.append(event)

    def test_handshake_is_authenticated_and_does_not_expose_docs(self):
        response = self.request("GET", "/api/v1/node/handshake", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "node_identity": "node.test.local",
                "protocol_version": "0.1",
                "clearance_context": "restricted",
                "authenticated_subject": "principal.api",
                "domain_pack_ref": "pack.refinery.v0",
                "ledger_event_ref": "ledger.handshake.test",
            },
        )
        self.assertEqual(self.request("GET", "/api/v1/node/handshake").status_code, 401)
        self.assertEqual(self.request("GET", "/docs").status_code, 404)

    def test_create_authorize_and_cancel_are_orchestrator_mutations(self):
        task, snapshot = self.create_task()
        task_id = task["task_id"]
        self.assertEqual(snapshot["asOfSequence"], 1)

        authorize = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/authorize",
            headers=self.headers(),
            json=self.command(
                command_id="command.authorize.1",
                task_id=task_id,
                expected_sequence=1,
                idempotency_key="idempotency.authorize.1",
                command_type="task.authorize",
                arguments={"authorization_ref": "authorization.local"},
            ),
        )
        self.assertEqual(authorize.status_code, 202, authorize.text)
        self.assertEqual(authorize.json()["event_type"], "task.authorized")
        self.assertEqual(authorize.json()["outcome"], "accepted")
        self.assertEqual(authorize.json()["node_identity"], "node.test.local")
        self.assertEqual(authorize.json()["protocol_version"], "0.1")
        self.assertEqual(authorize.json()["clearance_context"], "restricted")

        cancelled = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/cancel",
            headers=self.headers(),
            json=self.command(
                command_id="command.cancel.1",
                task_id=task_id,
                expected_sequence=2,
                idempotency_key="idempotency.cancel.1",
                command_type="task.cancel",
                arguments={"reason": "operator stopped the task"},
            ),
        )
        self.assertEqual(cancelled.status_code, 202, cancelled.text)
        self.assertEqual(cancelled.json()["state"], "cancelled")
        self.assertEqual([event.event_type for event in self.ledger.events], [
            "task.created", "task.authorized", "task.cancelled",
        ])

    def test_create_preserves_bounded_user_manifest_fields(self):
        response = self.request(
            "POST",
            "/api/v1/tasks",
            headers=self.headers(),
            json=self.task_body(
                title="Inspection approval note",
                project_ref="project.unit-4",
                priority="high",
                deadline="2026-10-01T12:00:00Z",
                input_manifest_refs=["intake.report-001"],
            ),
        )
        self.assertEqual(response.status_code, 201, response.text)
        task = response.json()["task"]
        self.assertEqual(task["title"], "Inspection approval note")
        self.assertEqual(task["project_ref"], "project.unit-4")
        self.assertEqual(task["priority"], "high")
        self.assertEqual(task["deadline"], "2026-10-01T12:00:00Z")
        self.assertEqual(task["input_manifest_refs"], ["intake.report-001"])

    def test_plan_projection_is_explicitly_not_ready_until_node_commits_plan_and_hardware(self):
        task, _ = self.create_task()
        response = self.request("GET", f"/api/v1/tasks/{task['task_id']}/plan", headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["plan_state"], "not_ready")
        self.assertEqual(response.json()["execution_mode"], "not_selected")
        self.assertEqual(response.json()["failure_code"], "plan_not_ready")

    def test_plan_projection_and_approval_are_server_authoritative_and_idempotent(self):
        task, _ = self.create_task()
        task_id = task["task_id"]
        self.orchestrator.authorize(task_id, authorization_ref="authorization.plan")
        plan = TeamPlan(
            team_id="team.plan-001",
            task_id=task_id,
            assignments=("assignment.intake-001", "assignment.verify-001"),
            dependency_graph={"intake": (), "verify": ("intake",)},
            concurrency_ceiling=1,
            required_verification=True,
            completion_criteria=("source_check",),
            plan_version_hash="plan-hash-001",
            policy_version_hash="policy-hash-001",
            status=ContractStatus.proposed,
        )
        self.orchestrator.commit_plan(plan)
        self.append_event(
            "team.resource_plan.admitted",
            task_id,
            {
                "team_id": plan.team_id,
                "task_id": task_id,
                "admission": "admitted",
                "execution_mode": "serial_virtual_team",
                "concurrency_ceiling": 1,
                "hardware_profile_ref": "hardware.test.local",
                "worker_capabilities": {"worker-intake": "vision", "worker-verify": "verification"},
                "reason": "Only one safe concurrent slot is available on the measured workstation.",
            },
        )
        review = self.request("GET", f"/api/v1/tasks/{task_id}/plan", headers=self.headers())
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["plan_state"], "ready")
        self.assertEqual(review.json()["execution_mode"], "serial_virtual_team")
        self.assertEqual(review.json()["dependency_graph"]["verify"], ["intake"])
        self.assertEqual(review.json()["hardware_profile_ref"], "hardware.test.local")
        self.assertEqual(review.json()["task_sequence"], 4)

        approval_command = self.command(
            command_id="command.approve-plan.1",
            task_id=task_id,
            expected_sequence=4,
            idempotency_key="idempotency.approve-plan.1",
            command_type="task.approve_plan",
            arguments={"approval_ref": "operator.plan-review"},
        )
        approval = self.request("POST", f"/api/v1/tasks/{task_id}/approve", headers=self.headers(), json=approval_command)
        self.assertEqual(approval.status_code, 202, approval.text)
        self.assertEqual(approval.json()["event_type"], "task.plan.approved")
        retry = self.request("POST", f"/api/v1/tasks/{task_id}/approve", headers=self.headers(), json=approval_command)
        self.assertEqual(retry.status_code, 202, retry.text)
        self.assertEqual(retry.json()["ledger_event_ref"], approval.json()["ledger_event_ref"])
        self.assertEqual([event.event_type for event in self.ledger.events].count("task.plan.approved"), 1)

        stale = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/approve",
            headers=self.headers(),
            json={**approval_command, "command_id": "command.approve-plan-stale", "idempotency_key": "idempotency.approve-plan-stale", "expected_sequence": 4},
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["code"], "stale_command")

    def test_event_batch_uses_task_local_cursor_and_preserves_ledger_reference(self):
        task, _ = self.create_task()
        task_id = task["task_id"]
        self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/authorize",
            headers=self.headers(),
            json=self.command(
                command_id="command.authorize.1",
                task_id=task_id,
                expected_sequence=1,
                idempotency_key="idempotency.authorize.1",
                command_type="task.authorize",
                arguments={"authorization_ref": "authorization.local"},
            ),
        )
        batch = self.request(
            "GET",
            f"/api/v1/tasks/{task_id}/events?after_sequence=0",
            headers=self.headers(),
        )
        self.assertEqual(batch.status_code, 200, batch.text)
        body = batch.json()
        self.assertEqual([event["sequence"] for event in body["events"]], [1, 2])
        self.assertEqual(body["next_sequence"], 2)
        self.assertEqual(body["ledger_event_refs"], [event["ledgerEventRef"] for event in body["events"]])
        self.assertEqual(body["events"][0]["eventType"], "task.accepted")
        self.assertEqual(body["events"][1]["eventType"], "task.accepted")
        self.assertEqual(body["events"][0]["schemaVersion"], "0.1")
        self.assertEqual(body["events"][0]["taskId"], task_id)

        ahead = self.request(
            "GET",
            f"/api/v1/tasks/{task_id}/events?after_sequence=3",
            headers=self.headers(),
        )
        self.assertEqual(ahead.status_code, 409)
        self.assertEqual(ahead.json()["code"], "cursor_ahead")

    def test_evidence_and_route_trace_are_clearance_filtered(self):
        task, _ = self.create_task()
        task_id = task["task_id"]
        provenance = {
            "source_ref": "upload:inspection-1",
            "confidence": 0.91,
            "clearance": "internal",
            "taint": "untrusted",
        }
        self.append_event(
            "evidence.created",
            task_id,
            {"evidence_id": "evidence.one", "content_hash": "a" * 64, "provenance": provenance},
        )
        self.append_event(
            "evidence.created",
            task_id,
            {"evidence_id": "evidence.secret", "content_hash": "b" * 64, "provenance": {**provenance, "clearance": "secret"}},
            Clearance.secret,
        )
        self.append_event(
            "routing.decision",
            task_id,
            {"selected_target": "model.local.reasoner", "decision_source": "fixture", "qualification_certificate": "cert.1"},
        )

        evidence = self.request("GET", f"/api/v1/tasks/{task_id}/evidence", headers=self.headers())
        self.assertEqual(evidence.status_code, 200, evidence.text)
        self.assertEqual([item["evidenceId"] for item in evidence.json()["evidence"]], ["evidence.one"])
        self.assertEqual(evidence.json()["evidence"][0]["confidence"], 0.91)
        self.assertEqual(evidence.json()["evidence"][0]["taint"], "untrusted")

        route = self.request("GET", f"/api/v1/tasks/{task_id}/route-trace", headers=self.headers())
        self.assertEqual(route.status_code, 200, route.text)
        self.assertEqual(route.json()["entries"][0]["selected_target"], "model.local.reasoner")
        self.assertNotIn("evidence.secret", evidence.text)

    def test_invalid_clearance_and_oversized_json_fail_closed(self):
        response = self.request(
            "POST",
            "/api/v1/tasks",
            headers=self.headers(),
            json=self.task_body(clearance="secret"),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "clearance_exceeded")

        oversized = "x" * (2 * 1024 * 1024)
        response = self.request(
            "POST",
            "/api/v1/tasks",
            headers={**self.headers(), "Content-Type": "application/json"},
            content=(f'{{"request":"{oversized}"}}').encode(),
        )
        self.assertEqual(response.status_code, 413)

    def test_create_command_retry_replays_and_conflict_is_rejected(self):
        first = self.request("POST", "/api/v1/tasks", headers=self.headers(), json=self.task_body())
        self.assertEqual(first.status_code, 201, first.text)
        second = self.request("POST", "/api/v1/tasks", headers=self.headers(), json=self.task_body())
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()["task"]["task_id"], first.json()["task"]["task_id"])
        self.assertEqual(second.json()["ledger_event_ref"], first.json()["ledger_event_ref"])
        self.assertEqual(self.ledger.events[0].payload["_command"]["actor"], "principal.api")
        self.assertNotIn("request", self.ledger.events[0].payload["_command"])
        self.assertEqual(len(self.ledger.events), 1)

        conflict = self.request(
            "POST",
            "/api/v1/tasks",
            headers=self.headers(),
            json=self.task_body(request="A different request"),
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["code"], "idempotency_conflict")
        self.assertEqual(len(self.ledger.events), 1)

    def test_transition_retry_replays_but_stale_new_command_is_rejected(self):
        task, _ = self.create_task()
        task_id = task["task_id"]
        command = self.command(
            command_id="command.authorize.1",
            task_id=task_id,
            expected_sequence=1,
            idempotency_key="idempotency.authorize.1",
            command_type="task.authorize",
            arguments={"authorization_ref": "authorization.local"},
        )
        first = self.request("POST", f"/api/v1/tasks/{task_id}/authorize", headers=self.headers(), json=command)
        retry = self.request("POST", f"/api/v1/tasks/{task_id}/authorize", headers=self.headers(), json=command)
        self.assertEqual(first.status_code, 202, first.text)
        self.assertEqual(retry.status_code, 202, retry.text)
        self.assertEqual(retry.json(), first.json())
        self.assertEqual(self.ledger.events[1].payload["_command"]["actor"], "principal.api")
        self.assertEqual(len(self.ledger.events), 2)

        stale = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/cancel",
            headers=self.headers(),
            json=self.command(
                command_id="command.cancel.stale",
                task_id=task_id,
                expected_sequence=1,
                idempotency_key="idempotency.cancel.stale",
                command_type="task.cancel",
                arguments={"reason": "operator stopped the task"},
            ),
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["code"], "stale_command")
        self.assertEqual(len(self.ledger.events), 2)

    def test_command_actor_and_protocol_mismatch_fail_before_mutation(self):
        actor_mismatch = self.request(
            "POST",
            "/api/v1/tasks",
            headers=self.headers(),
            json={**self.task_body(), "actor": "other.subject"},
        )
        self.assertEqual(actor_mismatch.status_code, 403, actor_mismatch.text)
        self.assertEqual(actor_mismatch.json()["code"], "command_actor_mismatch")

        protocol_mismatch = self.request(
            "POST",
            "/api/v1/tasks",
            headers=self.headers(),
            json={**self.task_body(), "client_version": "9.9"},
        )
        self.assertEqual(protocol_mismatch.status_code, 409, protocol_mismatch.text)
        self.assertEqual(protocol_mismatch.json()["code"], "protocol_mismatch")
        self.assertEqual(len(self.ledger.events), 0)


if __name__ == "__main__":
    unittest.main()
