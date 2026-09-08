from __future__ import annotations

import ast
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from airbench.orchestration.worker_context import (
    AssignmentValidationError,
    ScopedEvidence,
    ScopeViolation,
    WorkerDeadlineExceeded,
    create_worker_assignment,
    create_worker_context,
)
from contracts import (
    BackendContent,
    BackendMessage,
    BackendRequest,
    Clearance,
    ContractStatus,
    EventLedger,
    FakeBackend,
    ModelCallRequest,
    Orchestrator,
    SQLiteLedgerStore,
    StorageFailure,
    Taint,
    TaskEnvelope,
    TeamPlan,
    TransitionRejected,
    build_event,
)
from contracts.errors import ContractValidationError


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent / "fixtures"


class FixtureEvidenceProvider:
    def __init__(self, records: list[ScopedEvidence]) -> None:
        self.records = {record.evidence_ref: record for record in records}

    def get(self, evidence_ref: str) -> ScopedEvidence | None:
        return self.records.get(evidence_ref)


def make_task(*, task_id: str = "task.m41-001", allowed_evidence_scope: tuple[str, ...] = ("evidence.one", "evidence.two")) -> TaskEnvelope:
    return TaskEnvelope.from_dict({
        "task_id": task_id,
        "principal_id": "principal.m41-operator",
        "clearance": "restricted",
        "request": "Review the supplied evidence",
        "domain_pack_ref": "pack.refinery:1.0",
        "risk_class": "review_required",
        "autonomy_ceiling": "review_required",
        "allowed_evidence_scope": list(allowed_evidence_scope),
        "permitted_worker_capabilities": ["vision", "reasoning"],
        "permitted_tools": ["local.read", "local.write"],
        "output_contract": "approval-note",
        "verification_criteria": ["sources_attached"],
        "resource_budget": {"max_model_calls": 4, "max_tool_calls": 2},
        "deadline": "2026-09-09T12:00:00Z",
    })


def make_assignment(task: TaskEnvelope, *, worker_id: str = "worker.m41-one", evidence_refs: tuple[str, ...] = ("evidence.one",)):
    return create_worker_assignment(
        task=task,
        team_id="team.m41-001",
        worker_id=worker_id,
        role="research_worker",
        stage="evidence_extraction",
        input_schema="UntrustedEvidence.v1",
        output_schema="WorkPacket.v1",
        evidence_refs=evidence_refs,
        allowed_tools=("local.read",),
        capability_requirement="reasoning",
        deadline="2026-09-09T11:00:00Z",
        clearance=Clearance.internal,
        taint=Taint.untrusted,
        assignment_id=f"assignment.{worker_id}",
        call_idempotency_key=f"idempotency.{worker_id}",
    )


def make_provider() -> FixtureEvidenceProvider:
    payload = json.loads((FIXTURES / "m41_worker_evidence.json").read_text(encoding="utf-8"))
    return FixtureEvidenceProvider([
        ScopedEvidence(
            evidence_ref=item["evidence_ref"],
            source_ref=item["source_ref"],
            confidence=item["confidence"],
            clearance=Clearance(item["clearance"]),
            taint=Taint(item["taint"]),
            content_hash=item["content_hash"],
        )
        for item in payload
    ])


class FailingAssignmentLedger(EventLedger):
    def append(self, event):
        if event.event_type == "worker.assigned":
            raise StorageFailure("synthetic assignment ledger failure")
        return super().append(event)


class M41WorkerContextTests(unittest.TestCase):
    def test_assignment_creation_is_deterministic_and_narrowed(self) -> None:
        task = make_task()
        first = make_assignment(task)
        second = make_assignment(task)
        self.assertEqual(first, second)
        self.assertEqual(first.assignment_id, "assignment.worker.m41-one")
        self.assertEqual(first.clearance, Clearance.internal)
        self.assertEqual(first.taint, Taint.untrusted)

    def test_assignment_rejects_malformed_and_expanded_scope(self) -> None:
        task = make_task()
        with self.assertRaises(ContractValidationError):
            create_worker_assignment(
                task=task, team_id="team.m41-001", worker_id="worker.m41-one",
                role="research_worker", stage="evidence_extraction",
                input_schema="UntrustedEvidence.v1", output_schema="WorkPacket.v1",
                evidence_refs=("evidence.one",), allowed_tools=("local.read",),
                capability_requirement="reasoning", deadline="not-a-timestamp",
            )
        with self.assertRaises(AssignmentValidationError):
            create_worker_assignment(
                task=task, team_id="team.m41-001", worker_id="worker.m41-one",
                role="research_worker", stage="evidence_extraction",
                input_schema="UntrustedEvidence.v1", output_schema="WorkPacket.v1",
                evidence_refs=("evidence.peer",), allowed_tools=("local.read",),
                capability_requirement="reasoning", deadline="2026-09-09T11:00:00Z",
            )
        with self.assertRaises(AssignmentValidationError):
            create_worker_assignment(
                task=task, team_id="team.m41-001", worker_id="worker.m41-one",
                role="research_worker", stage="evidence_extraction",
                input_schema="UntrustedEvidence.v1", output_schema="WorkPacket.v1",
                evidence_refs=("evidence.one",), allowed_tools=("host.shell",),
                capability_requirement="reasoning", deadline="2026-09-09T11:00:00Z",
            )
        with self.assertRaises(AssignmentValidationError):
            create_worker_assignment(
                task=task, team_id="team.m41-001", worker_id="worker.m41-one",
                role="research_worker", stage="evidence_extraction",
                input_schema="UntrustedEvidence.v1", output_schema="WorkPacket.v1",
                evidence_refs=("evidence.one",), allowed_tools=("local.read",),
                capability_requirement="unapproved", deadline="2026-09-09T11:00:00Z",
            )
        with self.assertRaises(AssignmentValidationError):
            create_worker_assignment(
                task=task, team_id="team.m41-001", worker_id="worker.m41-one",
                role="research_worker", stage="evidence_extraction",
                input_schema="UntrustedEvidence.v1", output_schema="WorkPacket.v1",
                evidence_refs=("evidence.one",), allowed_tools=("local.read",),
                capability_requirement="reasoning", deadline="2026-09-09T11:00:00Z",
                clearance=Clearance.secret,
            )
        with self.assertRaises(AssignmentValidationError):
            create_worker_assignment(
                task=task, team_id="team.m41-001", worker_id="worker.m41-one",
                role="research_worker", stage="evidence_extraction",
                input_schema="UntrustedEvidence.v1", output_schema="WorkPacket.v1",
                evidence_refs=("evidence.one",), allowed_tools=("local.read",),
                capability_requirement="reasoning", deadline="2026-09-09T11:00:00Z",
                taint=Taint.clean,
            )

    def test_contexts_have_distinct_scratch_roots_and_block_peer_access(self) -> None:
        task = make_task()
        first = make_assignment(task, worker_id="worker.m41-one")
        second = make_assignment(task, worker_id="worker.m41-two", evidence_refs=("evidence.two",))
        with TemporaryDirectory() as directory:
            first_context = create_worker_context(
                task=task, assignment=first, workspace_root=directory,
                evidence_provider=make_provider(), signing_key=b"m41-key",
                policy_version_hash="policy.m41", now=NOW,
            )
            second_context = create_worker_context(
                task=task, assignment=second, workspace_root=directory,
                evidence_provider=make_provider(), signing_key=b"m41-key",
                policy_version_hash="policy.m41", now=NOW,
            )
            self.assertNotEqual(first_context.scope.scratch_root, second_context.scope.scratch_root)
            first_context.write_scratch("own.txt", "worker one", now=NOW)
            self.assertEqual(first_context.read_scratch("own.txt", now=NOW), b"worker one")
            with self.assertRaises(ScopeViolation):
                second_context.read_scratch(first_context.scope.scratch_root / "own.txt", now=NOW)
            with self.assertRaises(ScopeViolation):
                second_context.write_scratch(Path("..") / "shared.txt", "no", now=NOW)
            self.assertNotIn("request", first_context.view().to_dict())
            self.assertNotIn("worker.m41-two", first_context.view().to_dict()["identity"].values())

    def test_evidence_scope_preserves_provenance_and_taint(self) -> None:
        task = make_task()
        assignment = make_assignment(task)
        with TemporaryDirectory() as directory:
            context = create_worker_context(
                task=task, assignment=assignment, workspace_root=directory,
                evidence_provider=make_provider(), signing_key=b"m41-key",
                policy_version_hash="policy.m41", now=NOW,
            )
            evidence = context.evidence("evidence.one", now=NOW)
            self.assertEqual(evidence.provenance()["source_ref"], "intake:inspection-report-001#page=1")
            self.assertEqual(evidence.provenance()["confidence"], 0.91)
            self.assertEqual(evidence.clearance, Clearance.internal)
            self.assertEqual(evidence.taint, Taint.untrusted)
            with self.assertRaises(ScopeViolation):
                context.evidence("evidence.two", now=NOW)

        secret_task = make_task(allowed_evidence_scope=("evidence.secret",))
        secret_assignment = make_assignment(secret_task, evidence_refs=("evidence.secret",))
        secret_provider = FixtureEvidenceProvider([
            ScopedEvidence("evidence.secret", "secret:document#1", 0.99, Clearance.secret, Taint.untrusted, "3" * 64)
        ])
        with TemporaryDirectory() as directory:
            context = create_worker_context(
                task=secret_task, assignment=secret_assignment, workspace_root=directory,
                evidence_provider=secret_provider, signing_key=b"m41-key",
                policy_version_hash="policy.m41", now=NOW,
            )
            with self.assertRaises(ScopeViolation):
                context.evidence("evidence.secret", now=NOW)

    def test_tool_scope_and_model_call_identity_are_bound_to_assignment(self) -> None:
        task = make_task()
        assignment = make_assignment(task)
        with TemporaryDirectory() as directory:
            context = create_worker_context(
                task=task, assignment=assignment, workspace_root=directory,
                evidence_provider=make_provider(), signing_key=b"m41-key",
                policy_version_hash="policy.m41", now=NOW,
            )
            self.assertTrue(context.can_use_tool("local.read"))
            self.assertFalse(context.can_use_tool("local.write"))
            self.assertIsNotNone(context.scope.capability_scope)
            context.scope.capability_scope.validate()
            self.assertEqual(context.scope.capability_scope.worker_id, assignment.worker_id)
            request = context.build_model_call_request(
                request_id="request.m41-one", task_kind="evidence_review", modality="text",
                evidence_summary=("evidence.one",), resource_budget={"context_tokens": 1024},
                attempt=1, call_idempotency_key="call.m41-one", timeout_ms=1000,
                resource_lease_id="lease.m41-one", now=NOW,
            )
            self.assertEqual(request.task_id, task.task_id)
            self.assertEqual(request.team_id, assignment.team_id)
            self.assertEqual(request.worker_id, assignment.worker_id)
            self.assertEqual(request.role, assignment.role)
            self.assertEqual(request.required_capability, assignment.capability_requirement)
            self.assertEqual(request.clearance, assignment.clearance)
            with self.assertRaises(ScopeViolation):
                context.build_model_call_request(
                    request_id="request.m41-two", task_kind="evidence_review", modality="text",
                    evidence_summary=("evidence.one",), resource_budget={}, attempt=1,
                    call_idempotency_key="call.m41-two", timeout_ms=1000,
                    resource_lease_id="", now=NOW,
                )

            ledger = EventLedger()
            ledger.append(build_event(
                event_type="task.created", task_id=task.task_id, actor_id="test", actor_type="test",
                payload_contract="TaskEnvelope", payload_version="1.0", payload={},
                clearance=task.clearance, idempotency="task.m41-created", sequence=0,
            ))
            response = FakeBackend(ledger=ledger).complete(BackendRequest(
                model_call=request, target_id="target.m41-fake", artifact_digest="a" * 64,
                backend_id="fake.m41", backend_version="1.0",
                messages=(BackendMessage(role="user", content=(BackendContent(kind="text", text="review"),)),),
            ))
            self.assertEqual(response.request_id, request.request_id)
            self.assertEqual(ledger.events[-1].event_type, "model.call.completed")

    def test_deadline_is_hard_and_model_timeout_cannot_overrun_it(self) -> None:
        task = make_task()
        assignment = make_assignment(task)
        with TemporaryDirectory() as directory:
            context = create_worker_context(
                task=task, assignment=assignment, workspace_root=directory,
                evidence_provider=make_provider(), signing_key=b"m41-key",
                policy_version_hash="policy.m41", now=NOW,
            )
            self.assertGreater(context.scope.remaining_ms(NOW), 0)
            with self.assertRaises(WorkerDeadlineExceeded):
                context.build_model_call_request(
                    request_id="request.m41-late", task_kind="review", modality="text",
                    evidence_summary=(), resource_budget={}, attempt=1,
                    call_idempotency_key="call.m41-late", timeout_ms=3_600_001_000,
                    resource_lease_id="lease.m41-late", now=NOW,
                )
            with self.assertRaises(WorkerDeadlineExceeded):
                context.read_scratch("late.txt", now=NOW + timedelta(hours=24))
        with TemporaryDirectory() as directory:
            with self.assertRaises(WorkerDeadlineExceeded):
                create_worker_context(
                    task=task, assignment=assignment, workspace_root=directory,
                    evidence_provider=make_provider(), signing_key=b"m41-key",
                    policy_version_hash="policy.m41", now=datetime(2026, 9, 9, 11, 0, tzinfo=timezone.utc),
                )

    def test_orchestrator_commits_assignment_once_and_rejects_conflict(self) -> None:
        ledger = EventLedger()
        orchestrator = Orchestrator(ledger)
        task = orchestrator.create_task(
            principal_id="principal.m41-operator", clearance=Clearance.restricted,
            request="Review evidence", domain_pack_ref="pack.refinery:1.0",
            risk_class="review_required", autonomy_ceiling="review_required",
            allowed_evidence_scope=("evidence.one",),
            permitted_worker_capabilities=("reasoning",), permitted_tools=("local.read",),
            verification_criteria=("sources_attached",), task_id="task.m41-orchestrator",
        )
        orchestrator.authorize(task.task_id, authorization_ref="auth.m41")
        assignment = make_assignment(make_task(task_id=task.task_id), evidence_refs=("evidence.one",))
        plan = TeamPlan(
            team_id=assignment.team_id, task_id=task.task_id,
            assignments=(assignment.assignment_id,), dependency_graph={}, concurrency_ceiling=1,
            required_verification=True, completion_criteria=("sources_attached",),
            plan_version_hash="plan.m41", policy_version_hash="policy.m41",
        )
        orchestrator.commit_plan(plan)
        first = orchestrator.assign_worker(assignment)
        second = orchestrator.assign_worker(assignment)
        self.assertEqual(first.event_id, second.event_id)
        self.assertEqual([event.event_type for event in ledger.events].count("worker.assigned"), 1)
        self.assertEqual(orchestrator.state(task.task_id), "planned")
        conflicting = replace(assignment, stage="different_stage")
        with self.assertRaises(TransitionRejected):
            orchestrator.assign_worker(conflicting)

    def test_assignment_ledger_failure_does_not_mutate_state(self) -> None:
        ledger = FailingAssignmentLedger()
        orchestrator = Orchestrator(ledger)
        task = orchestrator.create_task(
            principal_id="principal.m41-operator", clearance=Clearance.restricted,
            request="Review evidence", domain_pack_ref="pack.refinery:1.0",
            risk_class="review_required", autonomy_ceiling="review_required",
            allowed_evidence_scope=("evidence.one",),
            permitted_worker_capabilities=("reasoning",), permitted_tools=("local.read",),
            verification_criteria=("sources_attached",), task_id="task.m41-failing-ledger",
        )
        orchestrator.authorize(task.task_id, authorization_ref="auth.m41")
        assignment = make_assignment(make_task(task_id=task.task_id), evidence_refs=("evidence.one",))
        orchestrator.commit_plan(TeamPlan(
            team_id=assignment.team_id, task_id=task.task_id,
            assignments=(assignment.assignment_id,), dependency_graph={}, concurrency_ceiling=1,
            required_verification=True, completion_criteria=("sources_attached",),
            plan_version_hash="plan.m41", policy_version_hash="policy.m41",
        ))
        with self.assertRaises(StorageFailure):
            orchestrator.assign_worker(assignment)
        self.assertEqual(orchestrator.state(task.task_id), "planned")
        self.assertNotIn("worker.assigned", [event.event_type for event in ledger.events])

    def test_assignment_and_context_are_replayable_after_restart(self) -> None:
        with TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            store = SQLiteLedgerStore(ledger_path, b"m41-signing-key")
            orchestrator = Orchestrator(store)
            task = orchestrator.create_task(
                principal_id="principal.m41-operator", clearance=Clearance.restricted,
                request="Review evidence", domain_pack_ref="pack.refinery:1.0",
                risk_class="review_required", autonomy_ceiling="review_required",
                allowed_evidence_scope=("evidence.one",),
                permitted_worker_capabilities=("reasoning",), permitted_tools=("local.read",),
                verification_criteria=("sources_attached",), task_id="task.m41-replay",
            )
            orchestrator.authorize(task.task_id, authorization_ref="auth.m41")
            assignment = make_assignment(make_task(task_id=task.task_id), evidence_refs=("evidence.one",))
            orchestrator.commit_plan(TeamPlan(
                team_id=assignment.team_id, task_id=task.task_id,
                assignments=(assignment.assignment_id,), dependency_graph={}, concurrency_ceiling=1,
                required_verification=True, completion_criteria=("sources_attached",),
                plan_version_hash="plan.m41", policy_version_hash="policy.m41",
            ))
            orchestrator.assign_worker(assignment)
            store.close()

            reopened = SQLiteLedgerStore(ledger_path, b"m41-signing-key")
            self.assertEqual(reopened.replay(task.task_id).state, "planned")
            self.assertIn("worker.assigned", [event.event_type for event in reopened.events])
            self.assertEqual(Orchestrator(reopened).state(task.task_id), "planned")
            reopened.close()

    def test_worker_context_module_has_no_network_imports(self) -> None:
        source = Path(__file__).parents[1] / "src" / "airbench" / "orchestration" / "worker_context.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update({
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        })
        self.assertTrue(imported.isdisjoint({"socket", "requests", "urllib", "httpx", "subprocess"}))


if __name__ == "__main__":
    unittest.main()
