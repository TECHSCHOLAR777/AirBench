from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from airbench.team_runtime import (
    ContextCompaction,
    LifecycleEvent,
    TeamRuntime,
    WorkerExecution,
)
from airbench.worker_context import ScopedEvidence
from contracts import (
    AdmissionRequest,
    Clearance,
    EventLedger,
    FactEnvelope,
    HardwareMeasurement,
    HardwareProfile,
    HandoffCoordinator,
    HandoffSubmission,
    Orchestrator,
    ResourceScheduler,
    Taint,
    TeamPlan,
    UntrustedEvidence,
    WorkPacket,
    WorkerAssignment,
    WorkerResult,
    work_packet_hash,
)


ROOT = Path(__file__).parents[1]
NOW = datetime.now(timezone.utc)


def _profile() -> HardwareProfile:
    return HardwareProfile.from_dict({
        "profile_id": "profile.m44",
        "gpu_model": "synthetic-gpu",
        "gpu_count": 1,
        "vram_bytes": 20_000,
        "driver_version": "synthetic",
        "accelerator_runtime": "synthetic",
        "cpu_model": "synthetic-cpu",
        "cpu_cores": 8,
        "ram_bytes": 80_000,
        "storage_bytes": 100_000,
        "scratch_bytes": 20_000,
        "model_context_tokens": 10_000,
        "kv_cache_bytes": 10_000,
        "safe_parallel_slots": 4,
        "egress_policy": "deny-all",
        "measurement_hash": "a" * 64,
        "supported_execution_modes": ["parallel", "pipelined", "serial_virtual_team"],
        "network_check_id": "network-check.m44",
        "sandbox_runtime": "synthetic",
        "benchmark_result_ref": "benchmark.m44",
    })


def _measurement(profile: HardwareProfile) -> HardwareMeasurement:
    return HardwareMeasurement(
        measurement_id="measurement.m44",
        profile_id=profile.profile_id,
        measured_at=NOW.isoformat().replace("+00:00", "Z"),
        available_vram_bytes=profile.vram_bytes,
        available_ram_bytes=profile.ram_bytes,
        kv_cache_bytes=profile.kv_cache_bytes,
        model_residency_bytes=(),
        latency_ms=(),
        throughput_tokens_per_second=(),
        sandbox_limits=(),
        max_concurrency=profile.safe_parallel_slots,
        egress_verified=True,
        available_vram_by_gpu=((0, profile.vram_bytes),),
        available_cpu_millicores=8_000,
        available_context_tokens=profile.model_context_tokens,
        available_scratch_bytes=profile.scratch_bytes,
        available_slots=profile.safe_parallel_slots,
    )


class _EvidenceProvider:
    def __init__(self, evidence: ScopedEvidence) -> None:
        self.evidence = evidence

    def get(self, evidence_ref: str) -> ScopedEvidence | None:
        return self.evidence if evidence_ref == self.evidence.evidence_ref else None


class _LiveResolver:
    def __init__(self, assignments, scheduler, evidence, fact=None):
        self.assignments = assignments
        self.scheduler = scheduler
        self.evidence_record = evidence
        self.fact_record = fact

    def assignment(self, assignment_id):
        return self.assignments.get(assignment_id)

    def lease(self, lease_id):
        return next((lease for lease in self.scheduler.active_leases if lease.lease_id == lease_id), None)

    def fact(self, fact_id):
        return self.fact_record if self.fact_record and self.fact_record.fact_id == fact_id else None

    def evidence(self, evidence_id):
        return self.evidence_record if self.evidence_record.evidence_id == evidence_id else None

    def artifact(self, artifact_id):
        return None


def _assignment(task_id: str, team_id: str, assignment_id: str, worker_id: str,
                capability: str, *, evidence_refs=(), deadline=None) -> WorkerAssignment:
    return WorkerAssignment.from_dict({
        "assignment_id": assignment_id,
        "team_id": team_id,
        "task_id": task_id,
        "worker_id": worker_id,
        "role": f"role.{worker_id}",
        "stage": f"stage.{worker_id}",
        "input_schema": "WorkerInput.v1",
        "output_schema": "WorkerOutput.v1",
        "evidence_refs": list(evidence_refs),
        "allowed_tools": [],
        "clearance": "restricted",
        "taint": "untrusted",
        "capability_requirement": capability,
        "deadline": (deadline or NOW + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
        "idempotency_key": f"key.{assignment_id}",
        "status": "queued",
    })


def _setup(*, dependent: bool, mode: str = "auto", deadline: datetime | None = None):
    ledger = EventLedger()
    orchestrator = Orchestrator(ledger)
    task_id = "task.m44"
    team_id = "team.m44"
    capabilities = ("cap.source", "cap.sink") if dependent else ("cap.alpha", "cap.beta")
    evidence_refs = ("evidence.report",) if dependent else ()
    task = orchestrator.create_task(
        principal_id="principal.m44",
        clearance=Clearance.restricted,
        request="Run a bounded worker team",
        domain_pack_ref="pack.example:1.0",
        risk_class="high",
        autonomy_ceiling="review_required",
        allowed_evidence_scope=evidence_refs,
        permitted_worker_capabilities=capabilities,
        permitted_tools=(),
        verification_criteria=("independent_verification",),
        resource_budget={"max_concurrency": 2},
        task_id=task_id,
    )
    orchestrator.authorize(task_id, authorization_ref="authorization.m44")
    assignment_ids = ("assignment.source", "assignment.sink") if dependent else ("assignment.alpha", "assignment.beta")
    worker_ids = ("worker.source", "worker.sink") if dependent else ("worker.alpha", "worker.beta")
    caps = ("cap.source", "cap.sink") if dependent else ("cap.alpha", "cap.beta")
    assignments = {
        assignment_id: _assignment(task_id, team_id, assignment_id, worker_id, capability=caps[index],
                                   evidence_refs=evidence_refs if index == 0 else (), deadline=deadline)
        for index, (assignment_id, worker_id) in enumerate(zip(assignment_ids, worker_ids))
    }
    graph = {
        assignment_ids[0]: (),
        assignment_ids[1]: (assignment_ids[0],) if dependent else (),
    }
    team_plan = TeamPlan.from_dict({
        "team_id": team_id,
        "task_id": task_id,
        "assignments": list(assignment_ids),
        "dependency_graph": {key: list(value) for key, value in graph.items()},
        "concurrency_ceiling": 2,
        "required_verification": True,
        "completion_criteria": ["independent_verification"],
        "plan_version_hash": "b" * 64,
        "policy_version_hash": "c" * 64,
    })
    orchestrator.commit_plan(team_plan)
    orchestrator.approve_plan(task_id, approval_ref="approval.m44")
    for assignment in assignments.values():
        orchestrator.assign_worker(assignment)

    profile = _profile()
    scheduler = ResourceScheduler(profile, _measurement(profile), ledger=ledger)
    reservations = tuple(
        (assignment.worker_id, (
            ("vram_bytes", 3_000), ("ram_bytes", 4_000), ("cpu_millicores", 100),
            ("kv_cache_bytes", 500), ("context_tokens", 100), ("scratch_bytes", 500), ("slots", 1),
        ))
        for assignment in assignments.values()
    )
    request = AdmissionRequest(
        task_id=task_id,
        team_id=team_id,
        worker_capabilities=tuple((assignment.worker_id, assignment.capability_requirement) for assignment in assignments.values()),
        reservations=reservations,
        verifier_worker_id=next(iter(assignments.values())).worker_id,
        worker_roles=tuple((assignment.worker_id, assignment.role) for assignment in assignments.values()),
        gpu_indices=tuple((assignment.worker_id, (0,)) for assignment in assignments.values()),
        requested_mode=mode,
        dependency_graph=tuple(
            (assignments[key].worker_id, tuple(assignments[predecessor].worker_id for predecessor in value))
            for key, value in graph.items()
        ),
        model_targets=tuple((assignment.worker_id, f"model.{assignment.worker_id}") for assignment in assignments.values()),
        qualification_refs=tuple((assignment.worker_id, f"qualification.{assignment.worker_id}") for assignment in assignments.values()),
        clearance=Clearance.restricted,
        taint=Taint.clean,
        policy_version_hash=team_plan.policy_version_hash,
        concurrency_ceiling=2,
        execution_deadline=(deadline.isoformat().replace("+00:00", "Z") if deadline else None),
    )
    schedule = scheduler.admit(request)
    evidence = UntrustedEvidence.from_dict({
        "evidence_id": "evidence.report",
        "source_ref": "intake.manifest.report",
        "content_hash": "d" * 64,
        "media_type": "text/plain",
        "clearance": "restricted",
        "taint": "untrusted",
        "captured_at": NOW.isoformat().replace("+00:00", "Z"),
    })
    scoped = ScopedEvidence("evidence.report", evidence.source_ref, 0.9, evidence.clearance, evidence.taint, evidence.content_hash)
    fact = FactEnvelope.from_dict({
        "fact_id": "fact.report",
        "value": "finding",
        "source_ref": "evidence.report#finding",
        "confidence": 0.9,
        "clearance": "restricted",
        "taint": "untrusted",
        "extraction_method": "worker",
        "observed_at": NOW.isoformat().replace("+00:00", "Z"),
        "ingested_at": NOW.isoformat().replace("+00:00", "Z"),
    })
    resolver = _LiveResolver(assignments, scheduler, evidence, fact)
    handoffs = HandoffCoordinator(
        task, team_plan, assignments,
        plan_version=team_plan.plan_version_hash,
        policy_version_hash=team_plan.policy_version_hash,
        ledger=ledger,
        record_resolver=resolver,
    ) if dependent else None
    runtime = TeamRuntime(
        task=task,
        team_plan=team_plan,
        assignments=assignments,
        schedule=schedule,
        scheduler=scheduler,
        orchestrator=orchestrator,
        workspace_root=ROOT / "tests" / ".m44-workspace",
        evidence_provider=_EvidenceProvider(scoped),
        signing_key=b"m44-test-signing-key",
        worker_runners={assignment_id: lambda invocation, token: WorkerResult.from_dict({
            "result_id": "result.placeholder",
            "assignment_id": assignment_id,
            "task_id": task_id,
            "status": "accepted",
            "output": {"proposal": "placeholder"},
        }) for assignment_id in assignments},
        handoff_coordinator=handoffs,
        now_provider=(lambda: deadline - timedelta(milliseconds=50)) if deadline else None,
    )
    return runtime, orchestrator, scheduler, assignments, team_plan


def _result(assignment_id: str, task_id: str, value: str) -> WorkerResult:
    return WorkerResult.from_dict({
        "result_id": f"result.{assignment_id.split('.')[-1]}",
        "assignment_id": assignment_id,
        "task_id": task_id,
        "status": "accepted",
        "output": {"proposal": value},
    })


def test_parallel_workers_overlap_but_commits_are_stable() -> None:
    runtime, orchestrator, scheduler, assignments, _ = _setup(dependent=False, mode="parallel")
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active = 0
    maximum = 0

    def runner(invocation, token):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        barrier.wait(timeout=2)
        with lock:
            active -= 1
        return _result(invocation.context.assignment.assignment_id, invocation.context.task.task_id, invocation.context.assignment.worker_id)

    runtime.worker_runners = {assignment_id: runner for assignment_id in assignments}
    report = runtime.execute()

    assert report.status == "completed"
    assert maximum == 2
    assert [worker.assignment_id for worker in report.workers] == sorted(assignments)
    assert not scheduler.active_leases
    completed = [event.payload["assignment_id"] for event in orchestrator.store.events if event.event_type == "worker.completed"]
    assert completed == sorted(assignments)
    assert orchestrator.state("task.m44") == "executing"


def test_serial_runtime_gates_sink_on_accepted_handoff() -> None:
    runtime, orchestrator, scheduler, assignments, team_plan = _setup(dependent=True, mode="serial_virtual_team")
    seen = []

    def source_runner(invocation, token):
        packet_payload = {
            "packet_id": "packet.source",
            "task_id": invocation.context.task.task_id,
            "team_id": invocation.context.assignment.team_id,
            "source_worker_id": invocation.context.assignment.worker_id,
            "destination_stage": assignments["assignment.sink"].stage,
            "fact_refs": ["fact.report"],
            "evidence_refs": ["evidence.report"],
            "artifact_refs": [],
            "checks": {"source_present": True},
            "unresolved_questions": [],
            "proposed_next_result": "synthesize finding",
            "clearance": "restricted",
            "taint": "untrusted",
        }
        packet_payload["packet_hash"] = work_packet_hash(packet_payload)
        packet = WorkPacket.from_dict(packet_payload)
        handoff = HandoffSubmission.from_dict({
            "handoff_id": "handoff.source",
            "task_id": invocation.context.task.task_id,
            "team_id": invocation.context.assignment.team_id,
            "source_assignment_id": "assignment.source",
            "source_worker_id": invocation.context.assignment.worker_id,
            "destination_assignment_id": "assignment.sink",
            "destination_stage": assignments["assignment.sink"].stage,
            "packet": packet.to_dict(),
            "packet_hash": packet.packet_hash,
            "barrier_id": invocation.barrier_id_for("assignment.sink"),
            "barrier_version": 1,
            "source_lease_id": invocation.lease.lease_id,
            "plan_version": team_plan.plan_version_hash,
            "policy_version_hash": team_plan.policy_version_hash,
            "clearance": "restricted",
            "taint": "untrusted",
            "submitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "deadline": assignments["assignment.sink"].deadline,
            "idempotency_key": "handoff-key.source",
        })
        return WorkerExecution(_result("assignment.source", invocation.context.task.task_id, "source"), (handoff,))

    def sink_runner(invocation, token):
        seen.append(tuple(handoff.handoff_id for handoff in invocation.input_handoffs))
        return _result("assignment.sink", invocation.context.task.task_id, "sink")

    runtime.worker_runners = {"assignment.source": source_runner, "assignment.sink": sink_runner}
    report = runtime.execute()

    assert report.status == "completed"
    assert seen == [("handoff.source",)]
    assert [worker.worker_id for worker in report.workers] == ["worker.sink", "worker.source"]
    assert not scheduler.active_leases
    assert any(event.event_type == "join_barrier.completed" for event in orchestrator.store.events)


def test_cancellation_is_cooperative_and_audited() -> None:
    runtime, orchestrator, scheduler, assignments, _ = _setup(dependent=False, mode="parallel")
    started = threading.Event()

    def runner(invocation, token):
        started.set()
        while not token.cancelled:
            time.sleep(0.005)
        raise RuntimeError("worker observed cancellation")

    runtime.worker_runners = {assignment_id: runner for assignment_id in assignments}
    holder = {}
    thread = threading.Thread(target=lambda: holder.setdefault("report", runtime.execute()))
    thread.start()
    assert started.wait(timeout=2)
    runtime.request_cancel("operator requested stop")
    thread.join(timeout=3)

    assert not thread.is_alive()
    assert holder["report"].status == "cancelled"
    assert orchestrator.state("task.m44") == "cancelled"
    assert not scheduler.active_leases
    assert any(event.event_type == "team.execution.cancelled" for event in orchestrator.store.events)


def test_timeout_fails_team_and_releases_lease() -> None:
    deadline = datetime.now(timezone.utc) + timedelta(milliseconds=100)
    runtime, orchestrator, scheduler, assignments, _ = _setup(dependent=False, mode="serial_virtual_team", deadline=deadline)

    def runner(invocation, token):
        time.sleep(0.2)
        return _result(invocation.context.assignment.assignment_id, invocation.context.task.task_id, "late")

    runtime.worker_runners = {assignment_id: runner for assignment_id in assignments}
    report = runtime.execute()

    assert report.status == "failed"
    assert report.failure_code == "worker_timeout"
    assert orchestrator.state("task.m44") == "failed"
    assert not scheduler.active_leases
    assert any(event.payload.get("failure_code") == "worker_timeout" for event in orchestrator.store.events if event.event_type == "worker.failed")


def test_compaction_rebuilds_from_ledger_and_is_idempotent() -> None:
    runtime, orchestrator, _, assignments, _ = _setup(dependent=False, mode="serial_virtual_team")
    runtime.worker_runners = {
        assignment_id: lambda invocation, token: _result(
            invocation.context.assignment.assignment_id, invocation.context.task.task_id, "value"
        )
        for assignment_id in assignments
    }
    runtime.execute()
    first = runtime.compact_worker_context("assignment.alpha")
    event_count = len(orchestrator.store.events)
    second = runtime.compact_worker_context("assignment.alpha")

    assert isinstance(first, ContextCompaction)
    assert first == second
    assert first.worker_result_ids == ("result.alpha",)
    assert len(orchestrator.store.events) == event_count
    assert any(event.event_type == "worker.context.compacted" for event in orchestrator.store.events)


def test_lifecycle_veto_is_fail_closed_before_worker_execution() -> None:
    runtime, orchestrator, _, assignments, _ = _setup(dependent=False, mode="serial_virtual_team")

    class Veto:
        def before(self, event: LifecycleEvent) -> None:
            if event.phase == "before_task":
                raise RuntimeError("policy veto")

        def after(self, event: LifecycleEvent) -> None:
            return None

    runtime.interceptors = (Veto(),)
    runtime.worker_runners = {
        assignment_id: lambda invocation, token: pytest.fail("worker must not run")
        for assignment_id in assignments
    }

    with pytest.raises(Exception, match="lifecycle interceptor blocked"):
        runtime.execute()
    assert orchestrator.state("task.m44") == "planned"
    assert any(event.event_type == "lifecycle.blocked" for event in orchestrator.store.events)
