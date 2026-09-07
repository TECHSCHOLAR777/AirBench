"""M4.2 scheduler tests using explicit synthetic hardware measurements.

These tests prove scheduling arithmetic and lifecycle behavior.  They do not
claim that a real GPU probe, model load, or throughput benchmark has run.
Those checks belong to the hardware qualification workstream.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from contracts import (
    AdmissionRequest,
    EventLedger,
    HardwareMeasurement,
    HardwareProfile,
    LeaseUnavailable,
    ResourceScheduler,
    Taint,
    build_event,
)
from contracts.models import Clearance, LeaseStatus


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _profile(*, vram: int = 20_000, slots: int = 3, gpu_count: int = 1) -> HardwareProfile:
    return HardwareProfile.from_dict({
        "profile_id": "profile.synthetic",
        "gpu_model": "synthetic-gpu",
        "gpu_count": gpu_count,
        "vram_bytes": vram,
        "driver_version": "synthetic",
        "accelerator_runtime": "synthetic",
        "cpu_model": "synthetic-cpu",
        "cpu_cores": 4,
        "ram_bytes": 40_000,
        "storage_bytes": 100_000,
        "scratch_bytes": 4_000,
        "model_context_tokens": 1_000,
        "kv_cache_bytes": 4_000,
        "safe_parallel_slots": slots,
        "egress_policy": "deny-all",
        "measurement_hash": "a" * 64,
        "supported_execution_modes": ["parallel", "pipelined", "serial_virtual_team"],
        "network_check_id": "network-check.synthetic",
        "sandbox_runtime": "synthetic",
        "benchmark_result_ref": "benchmark.synthetic",
    })


def _measurement(profile: HardwareProfile, *, vram: int | None = None, cpu: int = 1_000, slots: int | None = None) -> HardwareMeasurement:
    return HardwareMeasurement(
        measurement_id="measurement.synthetic",
        profile_id=profile.profile_id,
        measured_at="2026-01-01T00:00:00Z",
        available_vram_bytes=profile.vram_bytes if vram is None else vram,
        available_ram_bytes=40_000,
        kv_cache_bytes=4_000,
        model_residency_bytes=(),
        latency_ms=(),
        throughput_tokens_per_second=(),
        sandbox_limits=(),
        max_concurrency=profile.safe_parallel_slots,
        egress_verified=True,
        available_cpu_millicores=cpu,
        available_context_tokens=1_000,
        available_scratch_bytes=4_000,
        available_slots=slots or profile.safe_parallel_slots,
        available_vram_by_gpu=((0, profile.vram_bytes if vram is None else vram),) if profile.gpu_count == 1 else (),
    )


def _request(
    *,
    task_id: str = "task.synthetic",
    team_id: str = "team.synthetic",
    vram: tuple[int, int, int] = (8_000, 8_000, 4_000),
    requested_mode: str = "auto",
    pipeline: bool = False,
    priority: str = "interactive_normal",
    plan_version: str = "1",
    cpu: tuple[int, int, int] = (100, 100, 100),
    gpu_count: int = 1,
) -> AdmissionRequest:
    workers = ("lead.worker", "vision.worker", "verify.worker")
    roles = ("lead.worker", "lead_worker"), ("vision.worker", "vision_worker"), ("verify.worker", "verification_worker")
    capabilities = ("lead.worker", "reasoning"), ("vision.worker", "vision"), ("verify.worker", "verification")
    reservations = tuple(
        (
            worker,
            (
                ("vram_bytes", worker_vram),
                ("ram_bytes", 5_000),
                ("cpu_millicores", worker_cpu),
                ("kv_cache_bytes", 500),
                ("context_tokens", 100),
                ("scratch_bytes", 500),
                ("slots", 1),
            ),
        )
        for worker, worker_vram, worker_cpu in zip(workers, vram, cpu)
    )
    stages = (
        ("lead.worker", "draft"),
        ("vision.worker", "extract"),
        ("verify.worker", "verify"),
    )
    return AdmissionRequest(
        task_id=task_id,
        team_id=team_id,
        worker_capabilities=capabilities,
        reservations=reservations,
        verifier_worker_id="verify.worker",
        worker_roles=roles,
        gpu_indices=tuple((worker, (0,)) if gpu_count == 1 else (worker, (0, 1)) for worker in workers),
        requested_mode=requested_mode,
        worker_stages=stages if pipeline else (),
        pipeline_stages=("extract", "draft", "verify") if pipeline else (),
        dependency_graph=(
            ("lead.worker", ()),
            ("vision.worker", ()),
            ("verify.worker", ("lead.worker", "vision.worker")),
        ),
        residency_requests=tuple((worker, "load_on_demand") for worker in workers),
        model_targets=tuple((worker, f"model.{worker.split('.')[0]}") for worker in workers),
        qualification_refs=tuple((worker, f"qual.{worker.split('.')[0]}") for worker in workers),
        priority=priority,
        clearance=Clearance.restricted,
        taint=Taint.clean,
        policy_version_hash="policy.synthetic",
        plan_version=plan_version,
    )


def _seed_task(ledger: EventLedger, task_id: str = "task.synthetic") -> None:
    event = build_event(
        event_type="task.created",
        task_id=task_id,
        actor_id="test.actor",
        actor_type="test",
        payload_contract="TaskEnvelope",
        payload_version="1.0",
        payload={"task_id": task_id},
        clearance="restricted",
        idempotency="seed.task.created." + task_id,
        sequence=len(ledger.events),
        previous_event_hash=ledger.head_hash,
        occurred_at="2026-01-01T00:00:00Z",
    )
    ledger.append(event)


def test_parallel_admission_grants_all_worker_leases() -> None:
    profile = _profile()
    scheduler = ResourceScheduler(profile, _measurement(profile), now_provider=lambda: NOW)

    decision = scheduler.admit(_request())

    assert decision.plan.admission == "admitted"
    assert decision.plan.execution_mode == "parallel"
    assert {lease.worker_id for lease in decision.leases} == {
        "lead.worker", "vision.worker", "verify.worker"
    }
    assert all(lease.status == LeaseStatus.granted for lease in decision.leases)
    assert scheduler.resource_usage()["used"]["vram_bytes"] == 20_000


def test_pipelined_mode_is_explicit_and_preserves_verifier() -> None:
    profile = _profile(vram=30_000)
    scheduler = ResourceScheduler(profile, _measurement(profile), now_provider=lambda: NOW)

    decision = scheduler.admit(_request(requested_mode="pipelined", pipeline=True))

    assert decision.plan.admission == "admitted"
    assert decision.plan.execution_mode == "pipelined"
    assert decision.plan.safety_invariants["verifier_required"] is True


def test_serial_mode_uses_one_lease_at_a_time() -> None:
    profile = _profile(vram=12_000, slots=3)
    scheduler = ResourceScheduler(profile, _measurement(profile, vram=12_000), now_provider=lambda: NOW)
    request = _request()

    decision = scheduler.admit(request)
    assert decision.plan.execution_mode == "serial_virtual_team"
    assert decision.leases == ()

    first = scheduler.grant_worker_lease(request.team_id, "lead.worker", now=NOW)
    with pytest.raises(LeaseUnavailable):
        scheduler.grant_worker_lease(request.team_id, "vision.worker", now=NOW)
    scheduler.release_lease(first.lease_id, now=NOW)
    second = scheduler.grant_worker_lease(request.team_id, "vision.worker", now=NOW)
    assert second.worker_id == "vision.worker"


def test_queue_is_used_for_temporary_capacity_and_drain_creates_new_plan_version() -> None:
    profile = _profile(vram=20_000)
    scheduler = ResourceScheduler(profile, _measurement(profile), now_provider=lambda: NOW)
    first = scheduler.admit(_request(team_id="team.first"))
    second_request = _request(task_id="task.second", team_id="team.second")

    second = scheduler.admit(second_request)
    assert first.plan.admission == "admitted"
    assert second.plan.admission == "queued"
    assert second.queue_position == 1
    for lease in first.leases:
        scheduler.release_lease(lease.lease_id, now=NOW)

    retried = scheduler.drain_queue(now=NOW)
    assert len(retried) == 1
    assert retried[0].plan.admission == "admitted"
    assert retried[0].plan.plan_version == "2"


def test_permanent_resource_shortfall_stops_instead_of_queueing() -> None:
    profile = _profile(vram=20_000)
    scheduler = ResourceScheduler(profile, _measurement(profile, vram=20_000), now_provider=lambda: NOW)

    decision = scheduler.admit(_request(vram=(30_000, 1, 1)))

    assert decision.plan.admission == "stopped"
    assert "cannot fit" in decision.reason


def test_cycle_and_missing_qualification_fail_closed() -> None:
    profile = _profile()
    scheduler = ResourceScheduler(profile, _measurement(profile), now_provider=lambda: NOW)
    request = _request()
    # AdmissionRequest uses slots, so construct the cycle without relying on
    # implementation internals or mutable request state.
    cyclic = AdmissionRequest(
        task_id=request.task_id,
        team_id="team.cycle",
        worker_capabilities=request.worker_capabilities,
        reservations=request.reservations,
        verifier_worker_id=request.verifier_worker_id,
        worker_roles=request.worker_roles,
        gpu_indices=request.gpu_indices,
        dependency_graph=(("lead.worker", ("verify.worker",)), ("verify.worker", ("lead.worker",))),
        residency_requests=request.residency_requests,
        model_targets=request.model_targets,
        qualification_refs=request.qualification_refs,
        clearance=request.clearance,
        taint=request.taint,
        policy_version_hash=request.policy_version_hash,
    )
    assert scheduler.admit(cyclic).plan.admission == "stopped"

    missing = AdmissionRequest(
        task_id="task.missing.qual",
        team_id="team.missing.qual",
        worker_capabilities=request.worker_capabilities,
        reservations=request.reservations,
        verifier_worker_id=request.verifier_worker_id,
        worker_roles=request.worker_roles,
        gpu_indices=request.gpu_indices,
        residency_requests=request.residency_requests,
        model_targets=(),
        qualification_refs=(),
        clearance=request.clearance,
        taint=request.taint,
        policy_version_hash=request.policy_version_hash,
    )
    assert scheduler.admit(missing).plan.admission == "stopped"


def test_lease_activation_release_and_expiry_are_monotonic() -> None:
    profile = _profile(vram=12_000)
    scheduler = ResourceScheduler(profile, _measurement(profile, vram=12_000), now_provider=lambda: NOW)
    request = _request()
    decision = scheduler.admit(request)
    lease = scheduler.grant_worker_lease(request.team_id, "lead.worker", now=NOW)
    active = scheduler.activate_lease(lease.lease_id, now=NOW)
    assert active.status == LeaseStatus.active
    expired = scheduler.release_lease(active.lease_id, status=LeaseStatus.expired, now=NOW)
    assert expired.status == LeaseStatus.expired
    assert scheduler.active_leases == ()
    with pytest.raises(LeaseUnavailable):
        scheduler.activate_lease(expired.lease_id, now=NOW)


def test_ledger_records_decision_and_reconcile_restores_active_leases() -> None:
    profile = _profile()
    ledger = EventLedger()
    _seed_task(ledger)
    scheduler = ResourceScheduler(profile, _measurement(profile), ledger=ledger, now_provider=lambda: NOW)

    decision = scheduler.admit(_request())

    event_types = [event.event_type for event in ledger.events]
    assert "team.resource_plan.created" in event_types
    assert "team.resource_plan.admitted" in event_types
    assert "execution.mode.selected" in event_types
    assert "resource.lease.granted" in event_types
    assert len(decision.ledger_event_refs) == len(event_types) - 1

    recovered = ResourceScheduler(profile, _measurement(profile), ledger=ledger, now_provider=lambda: NOW)
    assert {lease.lease_id for lease in recovered.active_leases} == {
        lease.lease_id for lease in decision.leases
    }
    assert recovered.resource_usage()["used"]["vram_bytes"] == 20_000
    replayed = recovered.admit(_request())
    assert replayed.plan.plan_id == decision.plan.plan_id
    assert len(ledger.events) == len(event_types)


def test_queued_plan_survives_scheduler_reconstruction() -> None:
    profile = _profile(vram=20_000)
    ledger = EventLedger()
    _seed_task(ledger, "task.first")
    _seed_task(ledger, "task.second")
    first_scheduler = ResourceScheduler(profile, _measurement(profile), ledger=ledger, now_provider=lambda: NOW)
    first_scheduler.admit(_request(task_id="task.first", team_id="team.first"))
    queued = first_scheduler.admit(_request(task_id="task.second", team_id="team.second"))
    assert queued.plan.admission == "queued"

    recovered = ResourceScheduler(profile, _measurement(profile), ledger=ledger, now_provider=lambda: NOW)

    assert [item.team_id for item in recovered.queued_requests()] == ["team.second"]


def test_multi_gpu_requires_per_device_measurement() -> None:
    profile = _profile(vram=20_000, gpu_count=2)
    measurement = _measurement(profile, vram=20_000)
    scheduler = ResourceScheduler(profile, measurement, now_provider=lambda: NOW)

    decision = scheduler.admit(_request(gpu_count=2))

    assert decision.plan.admission == "stopped"
    assert "cannot fit" in decision.reason or "measurement" in decision.reason
