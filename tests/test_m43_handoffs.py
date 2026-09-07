import ast
import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from contracts import (
    BarrierStatus,
    Clearance,
    EventLedger,
    FactEnvelope,
    HandoffCoordinator,
    HandoffRejected,
    HandoffSubmission,
    InMemoryRecordResolver,
    JoinBarrier,
    LeaseStatus,
    Orchestrator,
    ResourceLease,
    Taint,
    TaskEnvelope,
    TeamPlan,
    UntrustedEvidence,
    WorkerAssignment,
    WorkPacket,
    build_event,
    work_packet_hash,
)
from contracts.ledger import LedgerError


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
NOW = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)
DEADLINE = "2026-09-08T02:00:00Z"


class FailingBatchLedger(EventLedger):
    def append_batch(self, events):
        raise LedgerError("synthetic append failure")


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.task, self.team, self.assignments, self.resolver = self._records()
        self.plan_version = self.team.plan_version_hash
        self.policy_version = self.team.policy_version_hash

    def _records(self, *, two_predecessors=False):
        task = TaskEnvelope.from_dict(json.loads((FIXTURES / "task_valid.json").read_text()))
        team_payload = json.loads((FIXTURES / "team_valid.json").read_text())
        if two_predecessors:
            team_payload["dependency_graph"]["assignment.reasoning-001"] = [
                "assignment.vision-001", "assignment.verify-001"
            ]
        team = TeamPlan.from_dict(team_payload)

        vision_payload = json.loads((FIXTURES / "worker_assignment_valid.json").read_text())
        reasoning_payload = copy.deepcopy(vision_payload)
        reasoning_payload.update({
            "assignment_id": "assignment.reasoning-001",
            "worker_id": "worker.reasoning-001",
            "role": "lead_worker",
            "stage": "reasoning",
            "input_schema": "WorkPacket.v1",
            "output_schema": "WorkPacket.v1",
            "capability_requirement": "local_reasoning",
            "evidence_refs": [],
        })
        verify_payload = copy.deepcopy(vision_payload)
        verify_payload.update({
            "assignment_id": "assignment.verify-001",
            "worker_id": "worker.verify-001",
            "role": "verification_worker",
            "stage": "verification",
            "input_schema": "WorkPacket.v1",
            "output_schema": "WorkPacket.v1",
            "capability_requirement": "local_verification",
            "evidence_refs": [],
        })
        assignments = {
            item.assignment_id: item
            for item in (
                WorkerAssignment.from_dict(vision_payload),
                WorkerAssignment.from_dict(reasoning_payload),
                WorkerAssignment.from_dict(verify_payload),
            )
        }
        leases = {
            assignment.worker_id: self._lease(assignment)
            for assignment in assignments.values()
        }
        fact = FactEnvelope.from_dict({
            "fact_id": "fact.finding-001",
            "value": "seal damage",
            "source_ref": "evidence.report-001#finding-1",
            "confidence": 0.91,
            "clearance": "restricted",
            "taint": "untrusted",
            "extraction_method": "ocr",
            "observed_at": "2026-09-08T00:10:00Z",
            "ingested_at": "2026-09-08T00:11:00Z",
        })
        evidence = UntrustedEvidence.from_dict({
            "evidence_id": "evidence.report-001",
            "source_ref": "intake.manifest-001",
            "content_hash": "a" * 64,
            "media_type": "application/pdf",
            "clearance": "restricted",
            "taint": "untrusted",
            "captured_at": "2026-09-08T00:00:00Z",
        })
        resolver = InMemoryRecordResolver(
            assignments=assignments,
            leases={lease.lease_id: lease for lease in leases.values()},
            facts={fact.fact_id: fact},
            evidence_records={evidence.evidence_id: evidence},
            artifacts={},
        )
        return task, team, assignments, resolver

    def _lease(self, assignment):
        return ResourceLease.from_dict({
            "lease_id": f"lease.{assignment.worker_id}",
            "task_id": "task.inspection-001",
            "team_id": "team.inspection-001",
            "plan_id": "plan.inspection-001",
            "worker_id": assignment.worker_id,
            "role": assignment.role,
            "capability": assignment.capability_requirement,
            "hardware_profile_ref": "hardware.synthetic-001",
            "measurement_id": "measurement.synthetic-001",
            "reservation": [["cpu_millicores", 100]],
            "residency": "load_on_demand",
            "clearance": "restricted",
            "taint": "clean",
            "policy_version_hash": "b" * 64,
            "idempotency_key": f"lease-key.{assignment.worker_id}",
            "issued_at": "2026-09-08T00:00:00Z",
            "expires_at": "2026-09-08T12:00:00Z",
            "status": "active",
            "model_target_id": "target.local-001",
            "qualification_id": "qualification.local-001",
        })

    def _packet(self, *, packet_id="packet.vision-001", proposed="synthesize sourced findings", source_worker="worker.vision-001"):
        payload = {
            "packet_id": packet_id,
            "task_id": self.task.task_id,
            "team_id": self.team.team_id,
            "source_worker_id": source_worker,
            "destination_stage": "reasoning",
            "fact_refs": ["fact.finding-001"],
            "evidence_refs": ["evidence.report-001"],
            "artifact_refs": [],
            "checks": {"source_present": True, "confidence_present": True},
            "unresolved_questions": [],
            "proposed_next_result": proposed,
            "clearance": "restricted",
            "taint": "untrusted",
        }
        payload["packet_hash"] = work_packet_hash(payload)
        return WorkPacket.from_dict(payload)

    def _barrier(self, *, ledger=None, deadline=DEADLINE, required=None, barrier_id="barrier.reasoning-001"):
        required = required or ("assignment.vision-001",)
        coordinator = HandoffCoordinator(
            self.task, self.team, self.assignments,
            plan_version=self.plan_version,
            policy_version_hash=self.policy_version,
            ledger=ledger,
            record_resolver=self.resolver,
        )
        barrier = JoinBarrier.from_dict({
            "barrier_id": barrier_id,
            "task_id": self.task.task_id,
            "team_id": self.team.team_id,
            "destination_assignment_id": "assignment.reasoning-001",
            "destination_stage": "reasoning",
            "plan_version": self.plan_version,
            "barrier_version": 1,
            "required_predecessor_assignment_ids": list(required),
            "accepted_handoff_ids": [],
            "accepted_packet_hashes": [],
            "missing_assignment_ids": list(required),
            "conflict_packet_refs": [],
            "deadline": deadline,
            "join_policy": "join_all",
            "status": "waiting",
            "clearance": "restricted",
            "taint": "untrusted",
            "policy_version_hash": self.policy_version,
            "idempotency_key": f"barrier-key.{barrier_id}",
            "created_at": "2026-09-08T00:00:00Z",
        })
        coordinator.open_barrier(barrier)
        return coordinator, barrier

    def _handoff(self, *, handoff_id="handoff.vision-001", packet=None, deadline=DEADLINE, submitted_at="2026-09-08T00:30:00Z", source_assignment="assignment.vision-001", barrier_id="barrier.reasoning-001"):
        packet = packet or self._packet()
        source = self.assignments[source_assignment]
        return HandoffSubmission.from_dict({
            "handoff_id": handoff_id,
            "task_id": self.task.task_id,
            "team_id": self.team.team_id,
            "source_assignment_id": source_assignment,
            "source_worker_id": source.worker_id,
            "destination_assignment_id": "assignment.reasoning-001",
            "destination_stage": "reasoning",
            "packet": packet.to_dict(),
            "packet_hash": packet.packet_hash,
            "barrier_id": barrier_id,
            "barrier_version": 1,
            "source_lease_id": f"lease.{source.worker_id}",
            "plan_version": self.plan_version,
            "policy_version_hash": self.policy_version,
            "clearance": "restricted",
            "taint": "untrusted",
            "submitted_at": submitted_at,
            "deadline": deadline,
            "idempotency_key": f"handoff-key.{handoff_id}",
        })

    def _ledger(self, task=None):
        task = task or self.task
        ledger = EventLedger()
        event = build_event(
            event_type="task.created",
            task_id=task.task_id,
            actor_id="test.orchestrator",
            actor_type="orchestrator",
            payload_contract="TaskEnvelope",
            payload_version="1.0",
            payload={"task": task.to_dict()},
            clearance=Clearance.internal,
            idempotency="seed.task.created",
            sequence=0,
            occurred_at="2026-09-08T00:00:00Z",
        )
        ledger.append(event)
        return ledger

    def test_packet_hash_is_canonical_and_round_trip_safe(self):
        packet = WorkPacket.from_dict(json.loads((FIXTURES / "work_packet_valid.json").read_text()))
        self.assertEqual(packet.packet_hash, work_packet_hash(packet))
        changed = packet.to_dict()
        changed["proposed_next_result"] = "tampered"
        with self.assertRaises(Exception):
            WorkPacket.from_dict(changed)

    def test_open_barrier_requires_committed_topology_and_projects_state(self):
        ledger = self._ledger()
        coordinator, barrier = self._barrier(ledger=ledger)
        self.assertEqual(coordinator.barrier(barrier.barrier_id).status, BarrierStatus.waiting)
        self.assertEqual(Orchestrator(ledger).state(self.task.task_id), "awaiting_check")
        self.assertEqual(ledger.events[-1].event_type, "join_barrier.waiting")

    def test_accept_completes_barrier_and_is_idempotent_after_restart(self):
        ledger = self._ledger()
        coordinator, barrier = self._barrier(ledger=ledger)
        handoff = self._handoff()
        accepted = coordinator.submit_handoff(handoff, now=NOW)
        self.assertEqual(accepted.outcome, "accepted")
        self.assertEqual(accepted.barrier.status, BarrierStatus.completed)
        event_count = len(ledger.events)
        duplicate = coordinator.submit_handoff(handoff, now=NOW)
        self.assertEqual(duplicate.outcome, "duplicate")
        self.assertEqual(len(ledger.events), event_count)

        restarted = HandoffCoordinator(
            self.task, self.team, self.assignments,
            plan_version=self.plan_version,
            policy_version_hash=self.policy_version,
            ledger=ledger,
            record_resolver=self.resolver,
        )
        self.assertEqual(restarted.barrier(barrier.barrier_id).status, BarrierStatus.completed)
        self.assertEqual(restarted.submit_handoff(handoff, now=NOW).outcome, "duplicate")
        self.assertEqual(ledger.replay(self.task.task_id).state, "executing")

    def test_conflicting_packet_resolves_barrier_without_accepting_second_packet(self):
        self.task, self.team, self.assignments, self.resolver = self._records(two_predecessors=True)
        ledger = self._ledger()
        coordinator, _ = self._barrier(
            ledger=ledger,
            required=("assignment.vision-001", "assignment.verify-001"),
        )
        first = coordinator.submit_handoff(self._handoff(), now=NOW)
        self.assertEqual(first.outcome, "accepted")
        self.assertEqual(first.barrier.status, BarrierStatus.waiting)
        second_packet = self._packet(packet_id="packet.vision-002", proposed="different result")
        conflict = coordinator.submit_handoff(
            self._handoff(handoff_id="handoff.vision-002", packet=second_packet), now=NOW
        )
        self.assertEqual(conflict.outcome, "conflicting")
        self.assertEqual(conflict.barrier.status, BarrierStatus.conflicting)
        self.assertEqual(len(coordinator.barrier("barrier.reasoning-001").accepted_handoff_ids), 1)

    def test_rejects_missing_provenance_wrong_identity_and_inactive_lease(self):
        coordinator, _ = self._barrier()
        missing = self._handoff(packet=self._packet())
        resolver = copy.copy(self.resolver)
        coordinator.record_resolver = InMemoryRecordResolver(
            assignments=resolver.assignments,
            leases={},
            facts=resolver.facts,
            evidence_records=resolver.evidence_records,
            artifacts={},
        )
        decision = coordinator.submit_handoff(missing, now=NOW)
        self.assertEqual(decision.outcome, "rejected")
        self.assertIn("lease", decision.reason)

        coordinator, _ = self._barrier()
        wrong = self._handoff()
        wrong_payload = wrong.to_dict()
        wrong_payload["destination_assignment_id"] = "assignment.verify-001"
        wrong_payload["idempotency_key"] = "handoff-key.wrong-destination"
        decision = coordinator.submit_handoff(wrong_payload, now=NOW)
        self.assertEqual(decision.outcome, "rejected")
        self.assertIn("destination", decision.reason)

    def test_late_handoff_does_not_satisfy_barrier_and_timeout_is_explicit(self):
        ledger = self._ledger()
        coordinator, barrier = self._barrier(ledger=ledger, deadline="2026-09-08T00:30:00Z")
        late = coordinator.submit_handoff(
            self._handoff(
                deadline="2026-09-08T00:30:00Z",
                submitted_at="2026-09-08T00:40:00Z",
            ),
            now=NOW,
        )
        self.assertEqual(late.outcome, "late")
        self.assertEqual(coordinator.barrier(barrier.barrier_id).status, BarrierStatus.waiting)
        self.assertEqual(coordinator.resolve_barrier(barrier.barrier_id, outcome="timed_out", now=NOW).outcome, BarrierStatus.timed_out)
        with self.assertRaises(HandoffRejected):
            coordinator.resolve_barrier(barrier.barrier_id, outcome="completed", now=NOW)

    def test_failed_ledger_batch_leaves_coordinator_projection_unchanged(self):
        ledger = self._ledger()
        coordinator = HandoffCoordinator(
            self.task, self.team, self.assignments,
            plan_version=self.plan_version,
            policy_version_hash=self.policy_version,
            ledger=ledger,
            record_resolver=self.resolver,
        )
        ledger.append_batch = FailingBatchLedger().append_batch
        with self.assertRaises(HandoffRejected):
            coordinator.open_barrier(self._barrier(ledger=None)[1])
        self.assertEqual(len(ledger.events), 1)
        self.assertEqual(coordinator.barriers, ())

    def test_in_memory_ledger_batch_rejects_without_partial_events(self):
        ledger = self._ledger()
        first = build_event(
            event_type="task.authorized",
            task_id=self.task.task_id,
            actor_id="test.orchestrator",
            actor_type="orchestrator",
            payload_contract="AuthorizationRecord",
            payload_version="1.0",
            payload={"authorized": True},
            clearance=Clearance.restricted,
            idempotency="authorize.batch-001",
            sequence=1,
            previous_event_hash=ledger.head_hash,
            occurred_at="2026-09-08T00:01:00Z",
        )
        invalid_second = build_event(
            event_type="task.plan.committed",
            task_id=self.task.task_id,
            actor_id="test.orchestrator",
            actor_type="orchestrator",
            payload_contract="PlanRecord",
            payload_version="1.0",
            payload={"plan": "invalid-sequence"},
            clearance=Clearance.restricted,
            idempotency="plan.batch-001",
            sequence=99,
            previous_event_hash=first.event_hash,
            occurred_at="2026-09-08T00:02:00Z",
        )
        with self.assertRaises(Exception):
            ledger.append_batch([first, invalid_second])
        self.assertEqual(len(ledger.events), 1)

    def test_state_replay_maps_resolution_to_needs_review(self):
        ledger = self._ledger()
        coordinator, barrier = self._barrier(ledger=ledger, deadline="2026-09-08T00:30:00Z")
        coordinator.resolve_barrier(barrier.barrier_id, outcome="timed_out", now=NOW)
        self.assertEqual(Orchestrator(ledger).state(self.task.task_id), "needs_review")
        self.assertEqual(ledger.replay(self.task.task_id).state, "needs_review")

    def test_contract_rejects_inconsistent_barrier_coverage(self):
        payload = {
            "barrier_id": "barrier.invalid-001",
            "task_id": self.task.task_id,
            "team_id": self.team.team_id,
            "destination_assignment_id": "assignment.reasoning-001",
            "destination_stage": "reasoning",
            "plan_version": self.plan_version,
            "barrier_version": 1,
            "required_predecessor_assignment_ids": ["assignment.vision-001"],
            "accepted_handoff_ids": ["handoff.vision-001"],
            "accepted_packet_hashes": [],
            "missing_assignment_ids": [],
            "conflict_packet_refs": [],
            "deadline": DEADLINE,
            "join_policy": "join_all",
            "status": "waiting",
            "clearance": "restricted",
            "taint": "untrusted",
            "policy_version_hash": self.policy_version,
            "idempotency_key": "barrier-key.invalid-001",
            "created_at": "2026-09-08T00:00:00Z",
        }
        with self.assertRaises(Exception):
            JoinBarrier.from_dict(payload)

    def test_handoff_module_has_no_network_or_process_imports(self):
        tree = ast.parse((ROOT / "contracts" / "handoffs.py").read_text())
        forbidden = {"socket", "ssl", "subprocess", "requests", "http", "urllib"}
        imports = {
            node.names[0].name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
        }
        imports.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(forbidden.isdisjoint(imports))


if __name__ == "__main__":
    unittest.main()
