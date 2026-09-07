"""Deterministic, lease-based scheduling for virtual worker teams.

The scheduler owns physical admission and lease state.  It does not inspect
models, documents, or domain-pack content.  A model target is an identity and
qualification reference supplied by the caller; qualification itself remains
the responsibility of the model registry and router.

This module deliberately performs no hardware probing and no network I/O.
Production probes create :class:`HardwareMeasurement` records before this
module is called.  That separation makes software-only tests truthful while
leaving real GPU validation to the hardware qualification stage.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping

from .admission import AdmissionRequest, HardwareMeasurement
from .errors import ContractValidationError
from .ids import idempotency_key, stable_id
from .ledger import EventLedger, LedgerError, SQLiteLedgerStore, build_event
from .models import (
    Clearance,
    ContractStatus,
    HardwareProfile,
    LeaseStatus,
    ResourceLease,
    ResourceReservation,
    Taint,
    TeamResourcePlan,
)


RESOURCE_DIMENSIONS = (
    "vram_bytes",
    "ram_bytes",
    "cpu_millicores",
    "kv_cache_bytes",
    "context_tokens",
    "scratch_bytes",
    "slots",
)
_ACTIVE_LEASE_STATUSES = {LeaseStatus.granted, LeaseStatus.active}
_TERMINAL_LEASE_STATUSES = {
    LeaseStatus.released,
    LeaseStatus.expired,
    LeaseStatus.cancelled,
    LeaseStatus.revoked,
    LeaseStatus.failed,
}
_LEDGER_EVENT_FOR_STATUS = {
    "admitted": "team.resource_plan.admitted",
    "queued": "team.resource_plan.queued",
    "stopped": "team.resource_plan.rejected",
}
_LEASE_EVENT_FOR_STATUS = {
    LeaseStatus.released: "resource.lease.released",
    LeaseStatus.expired: "resource.lease.expired",
    LeaseStatus.cancelled: "resource.lease.cancelled",
    LeaseStatus.revoked: "resource.lease.failed",
    LeaseStatus.failed: "resource.lease.failed",
}


class SchedulerError(RuntimeError):
    """Base error for invalid scheduling state or an uncommitted ledger write."""


class SchedulingRejected(SchedulerError):
    """The request cannot be admitted without weakening a safety invariant."""


class LeaseUnavailable(SchedulerError):
    """A valid worker lease cannot be granted with the current capacity."""


@dataclass(frozen=True, slots=True)
class ScheduleDecision:
    """Immutable scheduler result returned to the orchestrator."""

    plan: TeamResourcePlan
    decision_id: str
    reason: str
    leases: tuple[ResourceLease, ...] = ()
    queue_position: int | None = None
    ledger_event_refs: tuple[str, ...] = ()
    audit_payload: Mapping[str, Any] | None = None


class ResourceScheduler:
    """Admit teams and issue identity-bound per-worker resource leases.

    Admission is a pure calculation over the supplied profile, measurement,
    request, and currently active leases.  The only mutable state is owned by
    this scheduler.  Models and workers receive leases but cannot alter the
    plan, queue, or execution mode.
    """

    def __init__(
        self,
        profile: HardwareProfile,
        measurement: HardwareMeasurement,
        *,
        ledger: EventLedger | SQLiteLedgerStore | None = None,
        actor_id: str = "scheduler.local",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if profile.profile_id != measurement.profile_id:
            raise SchedulerError("hardware profile and measurement identities must match")
        if not actor_id.strip():
            raise SchedulerError("scheduler actor identity is required")
        self.profile = profile
        self.measurement = measurement
        self.ledger = ledger
        self.actor_id = actor_id
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._plans: dict[str, TeamResourcePlan] = {}
        self._plans_by_team: dict[str, str] = {}
        self._requests_by_plan: dict[str, AdmissionRequest] = {}
        self._decisions_by_request: dict[str, ScheduleDecision] = {}
        self._requests_by_key: dict[str, AdmissionRequest] = {}
        self._leases: dict[str, ResourceLease] = {}
        self._lease_key_index: dict[str, str] = {}
        self._used: dict[str, int] = {dimension: 0 for dimension in RESOURCE_DIMENSIONS}
        self._used_gpu: dict[int, int] = {}
        self._queue: list[tuple[int, int, str]] = []
        self._queue_sequence = 0
        self.reconcile()

    @property
    def active_leases(self) -> tuple[ResourceLease, ...]:
        return tuple(
            sorted(
                (lease for lease in self._leases.values() if lease.status in _ACTIVE_LEASE_STATUSES),
                key=lambda lease: lease.lease_id,
            )
        )

    @property
    def plans(self) -> tuple[TeamResourcePlan, ...]:
        return tuple(sorted(self._plans.values(), key=lambda plan: plan.plan_id))

    def queued_requests(self) -> tuple[AdmissionRequest, ...]:
        return tuple(
            self._requests_by_key[key]
            for _, _, key in sorted(self._queue)
            if key in self._requests_by_key
        )

    def resource_usage(self) -> dict[str, dict[str, int]]:
        capacities = self._capacities()
        return {
            "capacity": capacities,
            "used": dict(self._used),
            "available": {
                dimension: max(0, capacities[dimension] - self._used[dimension])
                for dimension in RESOURCE_DIMENSIONS
            },
        }

    def admit(self, request: AdmissionRequest, *, now: datetime | None = None) -> ScheduleDecision:
        """Create a plan, queue it, or stop it, then commit the decision.

        A queued request is a valid request whose minimum safe serial execution
        fits the node when existing work is released.  A stopped request cannot
        fit even as one worker at a time, or fails a structural safety gate.
        """

        now_value = _aware(now or self._now_provider())
        request_key = self._request_key(request)
        existing = self._decisions_by_request.get(request_key)
        if existing is not None:
            return existing
        recovered = next(
            (
                plan for plan in self._plans.values()
                if plan.task_id == request.task_id
                and plan.team_id == request.team_id
                and plan.plan_version == request.plan_version
            ),
            None,
        )
        if recovered is not None:
            recovered_decision_id = stable_id(
                "resource-decision", recovered.plan_id, recovered.admission, recovered.execution_mode
            )
            leases = tuple(
                sorted(
                    (lease for lease in self._leases.values() if lease.plan_id == recovered.plan_id),
                    key=lambda lease: lease.lease_id,
                )
            )
            decision = ScheduleDecision(
                plan=recovered,
                decision_id=recovered_decision_id,
                reason=recovered.reason,
                leases=leases,
                queue_position=None,
                ledger_event_refs=self._ledger_refs_for_plan(recovered.plan_id),
                audit_payload={
                    "decision_id": recovered_decision_id,
                    "plan_id": recovered.plan_id,
                    "task_id": recovered.task_id,
                    "team_id": recovered.team_id,
                    "admission": recovered.admission,
                    "admitted_mode": recovered.admitted_mode,
                    "recovered_from_ledger": True,
                },
            )
            self._requests_by_plan[recovered.plan_id] = request
            self._requests_by_key[request_key] = request
            self._decisions_by_request[request_key] = decision
            return decision

        structural_errors = self._validate_request_shape(request)
        records: tuple[ResourceReservation, ...] = ()
        if not structural_errors:
            try:
                records = self._build_reservations(request)
            except (ContractValidationError, SchedulerError) as exc:
                structural_errors.append(str(exc))

        if structural_errors:
            admission, mode, reason = "stopped", "serial_virtual_team", "; ".join(structural_errors)
        else:
            admission, mode, reason = self._select_mode(request, records)

        queue_position: int | None = None
        if admission == "queued":
            queue_position = self._prospective_queue_position(request, request_key)

        plan_id = stable_id(
            "resource-plan",
            request.task_id,
            request.team_id,
            request.plan_version,
            request_key,
        )
        plan = self._make_plan(
            request,
            records,
            plan_id=plan_id,
            admission=admission,
            mode=mode,
            reason=reason,
        )
        decision_id = stable_id("resource-decision", plan.plan_id, admission, mode)

        leases: tuple[ResourceLease, ...] = ()
        if admission == "admitted" and mode in {"parallel", "pipelined"}:
            leases = tuple(
                self._new_lease(plan, request, record, now_value)
                for record in records
            )

        specs = self._decision_event_specs(
            request,
            plan,
            decision_id=decision_id,
            queue_position=queue_position,
            leases=leases,
        )
        event_refs = self._append_events(
            task_id=request.task_id,
            clearance=request.clearance,
            occurred_at=_rfc3339(now_value),
            specs=specs,
        )

        self._plans[plan.plan_id] = plan
        self._plans_by_team[request.team_id] = plan.plan_id
        self._requests_by_plan[plan.plan_id] = request
        self._requests_by_key[request_key] = request
        if admission == "queued":
            self._queue.append((request.priority_rank, self._queue_sequence, request_key))
            self._queue_sequence += 1
        for lease in leases:
            self._store_active_lease(lease)

        audit = {
            "decision_id": decision_id,
            "plan_id": plan.plan_id,
            "task_id": request.task_id,
            "team_id": request.team_id,
            "admission": admission,
            "requested_mode": request.requested_mode,
            "admitted_mode": plan.admitted_mode,
            "reason": reason,
            "queue_position": queue_position,
            "hardware_profile_id": self.profile.profile_id,
            "measurement_id": self.measurement.measurement_id,
            "policy_version_hash": request.policy_version_hash,
            "clearance": request.clearance.value,
            "taint": request.taint.value,
            "ledger_event_refs": list(event_refs),
        }
        decision = ScheduleDecision(
            plan=plan,
            decision_id=decision_id,
            reason=reason,
            leases=leases,
            queue_position=queue_position,
            ledger_event_refs=event_refs,
            audit_payload=audit,
        )
        self._decisions_by_request[request_key] = decision
        return decision

    def grant_worker_lease(
        self,
        team_id: str,
        worker_id: str,
        *,
        now: datetime | None = None,
    ) -> ResourceLease:
        """Grant a lease for one worker after admission.

        Serial teams receive one lease at a time.  Parallel and pipelined teams
        normally receive all leases during admission, but this method also
        supports replay recovery where a lease grant must be reconstructed.
        """

        now_value = _aware(now or self._now_provider())
        self.expire_leases(now=now_value)
        plan_id = self._plans_by_team.get(team_id)
        if plan_id is None:
            raise LeaseUnavailable("team has no committed resource plan")
        plan = self._plans[plan_id]
        if plan.admission != "admitted":
            raise LeaseUnavailable(f"team plan is {plan.admission}, not admitted")
        request = self._requests_by_plan.get(plan_id)
        if request is None:
            request = self._request_from_plan(plan)
            self._requests_by_plan[plan_id] = request
        record = next((item for item in plan.reservation_records if item.worker_id == worker_id), None)
        if record is None:
            raise LeaseUnavailable("worker is not present in the committed resource plan")

        lease_key = self._lease_key(plan, worker_id)
        existing_id = self._lease_key_index.get(lease_key)
        if existing_id is not None:
            existing = self._leases[existing_id]
            if existing.status in _ACTIVE_LEASE_STATUSES:
                return existing
            raise LeaseUnavailable("worker lease identity was already terminally used")

        if plan.execution_mode == "serial_virtual_team":
            if any(
                lease.team_id == team_id and lease.status in _ACTIVE_LEASE_STATUSES
                for lease in self._leases.values()
            ):
                raise LeaseUnavailable("serial virtual team already has an active worker lease")
        if not self._fits_records((record,), include_current=True):
            raise LeaseUnavailable("worker reservation does not fit current available capacity")

        lease = self._new_lease(plan, request, record, now_value)
        event_refs = self._append_events(
            task_id=plan.task_id,
            clearance=request.clearance,
            occurred_at=_rfc3339(now_value),
            specs=[(
                "resource.lease.granted",
                "ResourceLease",
                {"lease": lease.to_dict(), "plan_id": plan.plan_id, "decision": "worker_lease_granted"},
                lease.idempotency_key,
            )],
        )
        self._store_active_lease(lease)
        return lease

    def activate_lease(self, lease_id: str, *, now: datetime | None = None) -> ResourceLease:
        """Mark a granted lease active when the orchestrator starts its worker."""

        now_value = _aware(now or self._now_provider())
        lease = self._leases.get(lease_id)
        if lease is None:
            raise LeaseUnavailable("unknown resource lease")
        if lease.status == LeaseStatus.active:
            return lease
        if lease.status != LeaseStatus.granted:
            raise LeaseUnavailable(f"cannot activate lease in {lease.status.value} state")
        active = ResourceLease.from_dict({**lease.to_dict(), "status": LeaseStatus.active.value})
        request = self._requests_by_plan.get(lease.plan_id) or self._request_from_lease(lease)
        self._append_events(
            task_id=lease.task_id,
            clearance=request.clearance,
            occurred_at=_rfc3339(now_value),
            specs=[(
                "resource.lease.activated",
                "ResourceLease",
                {"lease": active.to_dict(), "plan_id": lease.plan_id},
                idempotency_key("scheduler.lease.activate", lease.lease_id),
            )],
        )
        self._leases[lease_id] = active
        return active

    def release_lease(
        self,
        lease_id: str,
        *,
        status: LeaseStatus | str = LeaseStatus.released,
        now: datetime | None = None,
    ) -> ResourceLease:
        """Release or terminally transition one lease and return its snapshot."""

        now_value = _aware(now or self._now_provider())
        target = status if isinstance(status, LeaseStatus) else LeaseStatus(status)
        if target not in _TERMINAL_LEASE_STATUSES:
            raise SchedulerError("lease release status must be terminal")
        lease = self._leases.get(lease_id)
        if lease is None:
            raise LeaseUnavailable("unknown resource lease")
        if lease.status == target:
            return lease
        if lease.status in _TERMINAL_LEASE_STATUSES:
            raise LeaseUnavailable("terminal resource lease cannot transition again")
        updated = ResourceLease.from_dict({**lease.to_dict(), "status": target.value})
        request = self._requests_by_plan.get(lease.plan_id) or self._request_from_lease(lease)
        self._append_events(
            task_id=lease.task_id,
            clearance=request.clearance,
            occurred_at=_rfc3339(now_value),
            specs=[(
                _LEASE_EVENT_FOR_STATUS[target],
                "ResourceLease",
                {
                    "lease": updated.to_dict(),
                    "plan_id": lease.plan_id,
                    "previous_status": lease.status.value,
                },
                idempotency_key("scheduler.lease.transition", lease.lease_id, target.value),
            )],
        )
        if lease.status in _ACTIVE_LEASE_STATUSES:
            self._remove_active_lease(lease)
        self._leases[lease_id] = updated
        return updated

    def expire_leases(self, *, now: datetime | None = None) -> tuple[ResourceLease, ...]:
        """Expire all active leases whose fixed deadline has passed."""

        now_value = _aware(now or self._now_provider())
        expired: list[ResourceLease] = []
        for lease in tuple(self.active_leases):
            if _parse_time(lease.expires_at) <= now_value:
                expired.append(self.release_lease(lease.lease_id, status=LeaseStatus.expired, now=now_value))
        return tuple(expired)

    def cancel_team(self, team_id: str, *, now: datetime | None = None) -> None:
        """Cancel queued work and all active leases for a team."""

        now_value = _aware(now or self._now_provider())
        plan_id = self._plans_by_team.get(team_id)
        if plan_id is None:
            raise SchedulerError("team has no committed resource plan")
        plan = self._plans[plan_id]
        for lease in tuple(self.active_leases):
            if lease.team_id == team_id:
                self.release_lease(lease.lease_id, status=LeaseStatus.cancelled, now=now_value)
        self._queue = [entry for entry in self._queue if entry[2] not in self._keys_for_team(team_id)]
        request = self._requests_by_plan.get(plan_id) or self._request_from_plan(plan)
        self._append_events(
            task_id=plan.task_id,
            clearance=request.clearance,
            occurred_at=_rfc3339(now_value),
            specs=[(
                "team.resource_plan.cancelled",
                "TeamResourcePlan",
                {"plan": plan.to_dict(), "reason": "team_cancelled"},
                idempotency_key("scheduler.plan.cancel", plan.plan_id),
            )],
        )

    def drain_queue(self, *, now: datetime | None = None) -> tuple[ScheduleDecision, ...]:
        """Retry queued work in deterministic priority/FIFO order.

        A retry receives a higher immutable plan version.  The queued plan is
        retained in the ledger as historical evidence; it is never mutated.
        """

        now_value = _aware(now or self._now_provider())
        results: list[ScheduleDecision] = []
        for _, _, request_key in tuple(sorted(self._queue)):
            request = self._requests_by_key.get(request_key)
            if request is None:
                continue
            self._queue = [entry for entry in self._queue if entry[2] != request_key]
            next_request = replace(request, plan_version=_next_version(request.plan_version))
            result = self.admit(next_request, now=now_value)
            results.append(result)
            if result.plan.admission == "queued":
                break
        return tuple(results)

    def reconcile(self) -> None:
        """Rebuild plan and lease state from committed ledger events only."""

        self._plans.clear()
        self._plans_by_team.clear()
        self._requests_by_plan.clear()
        self._requests_by_key.clear()
        self._decisions_by_request.clear()
        self._leases.clear()
        self._lease_key_index.clear()
        self._used = {dimension: 0 for dimension in RESOURCE_DIMENSIONS}
        self._used_gpu.clear()
        self._queue.clear()
        cancelled_plans: set[str] = set()
        if self.ledger is None:
            return
        for event in self.ledger.events:
            payload = event.payload
            if event.event_type in {
                "team.resource_plan.created",
                "team.resource_plan.admitted",
                "team.resource_plan.queued",
                "team.resource_plan.rejected",
                "team.resource_plan.degraded_needs_review",
            }:
                plan_payload = payload.get("plan")
                if isinstance(plan_payload, dict):
                    try:
                        plan = TeamResourcePlan.from_dict(plan_payload)
                    except ContractValidationError as exc:
                        raise SchedulerError("ledger contains an invalid resource plan") from exc
                    self._plans[plan.plan_id] = plan
                    self._plans_by_team[plan.team_id] = plan.plan_id
            elif event.event_type == "team.resource_plan.cancelled":
                plan_payload = payload.get("plan")
                if isinstance(plan_payload, dict) and isinstance(plan_payload.get("plan_id"), str):
                    cancelled_plans.add(plan_payload["plan_id"])
            elif event.event_type in {
                "resource.lease.granted",
                "resource.lease.activated",
                "resource.lease.released",
                "resource.lease.expired",
                "resource.lease.cancelled",
                "resource.lease.failed",
            }:
                lease_payload = payload.get("lease")
                if not isinstance(lease_payload, dict):
                    continue
                try:
                    lease = ResourceLease.from_dict(lease_payload)
                except ContractValidationError as exc:
                    raise SchedulerError("ledger contains an invalid resource lease") from exc
                self._leases[lease.lease_id] = lease
                self._lease_key_index[self._lease_key_from_lease(lease)] = lease.lease_id
        for lease in self._leases.values():
            if lease.status in _ACTIVE_LEASE_STATUSES:
                self._add_active_lease(lease)
        for plan in sorted(self._plans.values(), key=lambda item: item.plan_id):
            if plan.admission != "queued" or plan.plan_id in cancelled_plans or not plan.reservation_records:
                continue
            request = self._request_from_plan(plan)
            request_key = self._request_key(request)
            self._requests_by_plan[plan.plan_id] = request
            self._requests_by_key[request_key] = request
            self._queue.append((request.priority_rank, self._queue_sequence, request_key))
            self._queue_sequence += 1

    # Internal contract and arithmetic helpers

    def _validate_request_shape(self, request: AdmissionRequest) -> list[str]:
        errors: list[str] = []
        if not request.task_id.strip() or not request.team_id.strip():
            errors.append("task and team identities are required")
        workers = set(request.reservation_map())
        if request.verifier_worker_id not in workers:
            errors.append("independent verifier reservation is missing")
        if not workers:
            errors.append("at least one worker reservation is required")
        graph = request.dependency_map()
        if set(graph) - workers:
            errors.append("dependency graph contains an unknown worker")
        if any(dependency not in workers for deps in graph.values() for dependency in deps):
            errors.append("dependency graph references an unknown worker")
        if self._has_cycle(graph, workers):
            errors.append("dependency graph must be acyclic")
        roles = request.pair_map("worker_roles")
        if set(roles) != workers:
            errors.append("every worker must have an explicit role")
        if request.requested_mode == "pipelined":
            stages = request.pair_map("worker_stages")
            if not request.pipeline_stages or set(stages) != workers:
                errors.append("pipelined admission requires one stage for every worker")
        return errors

    def _build_reservations(self, request: AdmissionRequest) -> tuple[ResourceReservation, ...]:
        resources_by_worker = request.reservation_map()
        roles = request.pair_map("worker_roles")
        targets = request.pair_map("model_targets")
        qualifications = request.pair_map("qualification_refs")
        residency = request.pair_map("residency_requests")
        gpu_indices = request.pair_map("gpu_indices")
        missing = [
            worker for worker in sorted(resources_by_worker)
            if not targets.get(worker) or not qualifications.get(worker)
        ]
        if missing:
            raise SchedulingRejected("every worker requires a qualified model target and qualification reference")

        records: list[ResourceReservation] = []
        for worker in sorted(resources_by_worker):
            raw = resources_by_worker[worker]
            unknown = set(raw) - set(RESOURCE_DIMENSIONS)
            if unknown:
                raise SchedulingRejected(f"unknown resource dimensions for {worker}: {sorted(unknown)}")
            values = {dimension: raw.get(dimension, 0) for dimension in RESOURCE_DIMENSIONS}
            values["slots"] = raw.get("slots", 1)
            if any(type(value) is not int or value < 0 for value in values.values()):
                raise SchedulingRejected(f"resource values for {worker} must be non-negative integers")
            indices = tuple(gpu_indices.get(worker, ()))
            if any(type(index) is not int or index < 0 or index >= self.profile.gpu_count for index in indices):
                raise SchedulingRejected(f"GPU indices for {worker} are outside the hardware profile")
            if values["vram_bytes"] > 0 and not indices:
                raise SchedulingRejected(f"GPU-backed worker {worker} must declare its GPU placement")
            record_payload = {
                "worker_id": worker,
                "role": roles[worker],
                "capability": request.worker_capability_map().get(worker, ""),
                "model_target_id": targets[worker],
                "qualification_id": qualifications[worker],
                "gpu_indices": list(indices),
                "vram_reserved_bytes": values["vram_bytes"],
                "cpu_reserved_millicores": values["cpu_millicores"],
                "ram_reserved_bytes": values["ram_bytes"],
                "scratch_reserved_bytes": values["scratch_bytes"],
                "context_tokens_reserved": values["context_tokens"],
                "kv_cache_reserved_bytes": values["kv_cache_bytes"],
                "residency": residency.get(worker, "load_on_demand"),
                "slots_reserved": values["slots"],
                "start_deadline": request.start_deadline,
                "execution_deadline": request.execution_deadline,
            }
            records.append(ResourceReservation.from_dict(record_payload))
        if not records:
            raise SchedulingRejected("at least one typed reservation is required")
        return tuple(records)

    def _select_mode(
        self,
        request: AdmissionRequest,
        records: tuple[ResourceReservation, ...],
    ) -> tuple[str, str, str]:
        parallel_fit = self._fits_records(records, include_current=True)
        serial_fit = all(self._fits_records((record,), include_current=True) for record in records)
        serial_fit_empty = all(self._fits_records((record,), include_current=False) for record in records)
        pipeline_valid = bool(request.pipeline_stages) and set(request.pair_map("worker_stages")) == {
            record.worker_id for record in records
        }

        if parallel_fit and request.requested_mode == "pipelined" and pipeline_valid:
            return "admitted", "pipelined", "all pipeline reservations fit concurrently"
        if parallel_fit and request.requested_mode == "auto" and pipeline_valid:
            return "admitted", "pipelined", "pipeline topology is present and all reservations fit concurrently"
        if parallel_fit and request.requested_mode != "serial_virtual_team":
            return "admitted", "parallel", "all worker reservations fit across every measured resource dimension"
        if serial_fit:
            reason = "workers fit one at a time with isolated leases"
            if request.requested_mode in {"parallel", "pipelined"}:
                reason += "; requested concurrency was reduced without removing the verifier"
            return "admitted", "serial_virtual_team", reason
        if serial_fit_empty:
            return "queued", "serial_virtual_team", "minimum safe worker reservation fits after current work releases capacity"
        return "stopped", "serial_virtual_team", "at least one worker cannot fit even alone; no safe scheduling mode exists"

    def _make_plan(
        self,
        request: AdmissionRequest,
        records: tuple[ResourceReservation, ...],
        *,
        plan_id: str,
        admission: str,
        mode: str,
        reason: str,
    ) -> TeamResourcePlan:
        reservation_map = {
            record.worker_id: {
                "vram_bytes": record.vram_reserved_bytes,
                "ram_bytes": record.ram_reserved_bytes,
                "cpu_millicores": record.cpu_reserved_millicores,
                "kv_cache_bytes": record.kv_cache_reserved_bytes,
                "context_tokens": record.context_tokens_reserved,
                "scratch_bytes": record.scratch_reserved_bytes,
                "slots": record.slots_reserved,
            }
            for record in records
        }
        if not reservation_map:
            reservation_map = request.reservation_map()
        if mode == "parallel":
            ceiling = request.concurrency_ceiling or min(len(reservation_map), self._capacities()["slots"])
        elif mode == "pipelined":
            ceiling = request.concurrency_ceiling or min(len(reservation_map), self._capacities()["slots"])
        else:
            ceiling = 1
        admitted_mode = mode if admission == "admitted" else ("queued" if admission == "queued" else "stopped")
        graph = {worker: tuple(deps) for worker, deps in sorted(request.dependency_map().items())}
        provenance = {
            "hardware_profile_hash": request.policy_version_hash and self.profile.measurement_hash,
            "measurement_id": self.measurement.measurement_id,
            "policy_hash": request.policy_version_hash,
            "clearance": request.clearance.value,
            "taint": request.taint.value,
        }
        scheduling = {
            "queue_class": request.priority,
            "preemption_policy": "cooperative" if request.is_background else "none",
            "cancellation_policy": "release_all_leases_and_record_cancel",
            "retry_policy": "orchestrator_owned",
            "unload_policy": "respect_residency_request",
            "verifier_worker_id": request.verifier_worker_id,
            "pipeline_stages": ",".join(request.pipeline_stages),
        }
        safety = {
            "verifier_required": True,
            "review_required": True,
            "qualified_targets_only": True,
            "provenance_required": True,
            "verifier_worker_id": request.verifier_worker_id,
        }
        payload = {
            "task_id": request.task_id,
            "plan_id": plan_id,
            "team_id": request.team_id,
            "hardware_profile_ref": self.profile.profile_id,
            "hardware_profile_id": self.profile.profile_id,
            "worker_capabilities": request.worker_capability_map(),
            "reservations": reservation_map,
            "concurrency_ceiling": ceiling,
            "execution_mode": mode,
            "priority": request.priority,
            "verifier_capacity": 1,
            "admission": admission,
            "reason": reason,
            "plan_version": request.plan_version,
            "requested_mode": request.requested_mode,
            "admitted_mode": admitted_mode,
            "admission_reason": reason,
            "dependency_graph": graph,
            "scheduling": scheduling,
            "safety_invariants": safety,
            "provenance": provenance,
            "residency_requests": request.pair_map("residency_requests"),
            "reservation_records": [record.to_dict() for record in records],
        }
        return TeamResourcePlan.from_dict(payload)

    def _new_lease(
        self,
        plan: TeamResourcePlan,
        request: AdmissionRequest,
        record: ResourceReservation,
        now: datetime,
    ) -> ResourceLease:
        expires_at = record.execution_deadline or request.execution_deadline
        if expires_at is None:
            expires_at = _rfc3339(now + timedelta(hours=1))
        lease_key = self._lease_key(plan, record.worker_id)
        payload = {
            "lease_id": stable_id("resource-lease", plan.plan_id, record.worker_id),
            "task_id": plan.task_id,
            "team_id": plan.team_id,
            "plan_id": plan.plan_id,
            "worker_id": record.worker_id,
            "role": record.role,
            "capability": record.capability,
            "hardware_profile_ref": self.profile.profile_id,
            "measurement_id": self.measurement.measurement_id,
            "reservation": [
                ["vram_bytes", record.vram_reserved_bytes],
                ["ram_bytes", record.ram_reserved_bytes],
                ["cpu_millicores", record.cpu_reserved_millicores],
                ["kv_cache_bytes", record.kv_cache_reserved_bytes],
                ["context_tokens", record.context_tokens_reserved],
                ["scratch_bytes", record.scratch_reserved_bytes],
                ["slots", record.slots_reserved],
            ],
            "residency": record.residency,
            "clearance": request.clearance.value,
            "taint": request.taint.value,
            "policy_version_hash": request.policy_version_hash,
            "idempotency_key": lease_key,
            "issued_at": _rfc3339(now),
            "expires_at": expires_at,
            "status": LeaseStatus.granted.value,
            "model_target_id": record.model_target_id,
            "qualification_id": record.qualification_id,
            "version": 1,
            "provenance_refs": [self.profile.measurement_hash, self.measurement.measurement_id],
            "gpu_indices": list(record.gpu_indices),
        }
        return ResourceLease.from_dict(payload)

    def _decision_event_specs(
        self,
        request: AdmissionRequest,
        plan: TeamResourcePlan,
        *,
        decision_id: str,
        queue_position: int | None,
        leases: tuple[ResourceLease, ...],
    ) -> list[tuple[str, str, dict[str, Any], str]]:
        base = {
            "plan": plan.to_dict(),
            "decision_id": decision_id,
            "hardware_profile_id": self.profile.profile_id,
            "measurement_id": self.measurement.measurement_id,
            "provenance": {
                "source_ref": f"hardware-measurement:{self.measurement.measurement_id}",
                "confidence": 1.0,
                "clearance": request.clearance.value,
                "taint": request.taint.value,
            },
        }
        specs: list[tuple[str, str, dict[str, Any], str]] = [
            (
                "team.resource_plan.created",
                "TeamResourcePlan",
                base,
                idempotency_key("scheduler.plan.created", plan.plan_id),
            ),
            (
                _LEDGER_EVENT_FOR_STATUS[plan.admission],
                "TeamResourcePlan",
                {**base, "reason": plan.reason, "admitted_mode": plan.admitted_mode},
                idempotency_key("scheduler.plan.decision", plan.plan_id, plan.admission),
            ),
        ]
        if plan.admission == "admitted":
            specs.append((
                "execution.mode.selected",
                "TeamResourcePlan",
                {"plan_id": plan.plan_id, "mode": plan.execution_mode, "decision_id": decision_id},
                idempotency_key("scheduler.mode.selected", plan.plan_id, plan.execution_mode),
            ))
            for record in plan.reservation_records:
                specs.append((
                    "worker.resource_reserved",
                    "ResourceReservation",
                    {"plan_id": plan.plan_id, "reservation": record.to_dict()},
                    idempotency_key("scheduler.worker.reserved", plan.plan_id, record.worker_id),
                ))
            for lease in leases:
                specs.append((
                    "resource.lease.granted",
                    "ResourceLease",
                    {"lease": lease.to_dict(), "plan_id": plan.plan_id},
                    lease.idempotency_key,
                ))
        elif plan.admission == "queued":
            specs.append((
                "resource.queue.updated",
                "TeamResourcePlan",
                {"plan_id": plan.plan_id, "queue_position": queue_position, "priority": request.priority},
                idempotency_key("scheduler.queue.updated", plan.plan_id, queue_position),
            ))
        return specs

    def _append_events(
        self,
        *,
        task_id: str,
        clearance: Clearance,
        occurred_at: str,
        specs: Iterable[tuple[str, str, dict[str, Any], str]],
    ) -> tuple[str, ...]:
        if self.ledger is None:
            return ()
        specs_list = list(specs)
        if not specs_list:
            return ()
        existing = tuple(self.ledger.events)
        previous_hash = existing[-1].event_hash if existing else None
        events = []
        for offset, (event_type, payload_contract, payload, idem) in enumerate(specs_list):
            events.append(build_event(
                event_type=event_type,
                task_id=task_id,
                actor_id=self.actor_id,
                actor_type="scheduler",
                payload_contract=payload_contract,
                payload_version="1.0",
                payload=payload,
                clearance=clearance,
                idempotency=idem,
                sequence=len(existing) + offset,
                previous_event_hash=previous_hash,
                occurred_at=occurred_at,
            ))
            previous_hash = events[-1].event_hash
        try:
            if isinstance(self.ledger, EventLedger):
                committed = tuple(self.ledger.append(event) for event in events)
            else:
                self.ledger.append_batch(events, stable_id("resource-transaction", *(event.event_id for event in events)))
                committed = tuple(events)
        except (ContractValidationError, LedgerError) as exc:
            raise SchedulerError("resource decision was not committed to the ledger") from exc
        return tuple(event.event_id for event in committed)

    def _ledger_refs_for_plan(self, plan_id: str) -> tuple[str, ...]:
        if self.ledger is None:
            return ()
        refs: list[str] = []
        for event in self.ledger.events:
            plan_payload = event.payload.get("plan")
            lease_payload = event.payload.get("lease")
            if (
                event.payload.get("plan_id") == plan_id
                or (isinstance(plan_payload, dict) and plan_payload.get("plan_id") == plan_id)
                or (isinstance(lease_payload, dict) and lease_payload.get("plan_id") == plan_id)
            ):
                refs.append(event.event_id)
        return tuple(refs)

    def _capacities(self) -> dict[str, int]:
        return {
            "vram_bytes": self.measurement.available_vram_bytes,
            "ram_bytes": self.measurement.available_ram_bytes,
            "cpu_millicores": self.measurement.available_cpu_millicores
            if self.measurement.available_cpu_millicores is not None else self.profile.cpu_cores * 1000,
            "kv_cache_bytes": self.measurement.kv_cache_bytes,
            "context_tokens": self.measurement.available_context_tokens
            if self.measurement.available_context_tokens is not None else self.profile.model_context_tokens,
            "scratch_bytes": self.measurement.available_scratch_bytes
            if self.measurement.available_scratch_bytes is not None else self.profile.scratch_bytes,
            "slots": min(
                self.profile.safe_parallel_slots,
                self.measurement.max_concurrency,
                self.measurement.available_slots if self.measurement.available_slots is not None else self.measurement.max_concurrency,
            ),
        }

    def _gpu_capacities(self) -> dict[int, int] | None:
        measured = dict(self.measurement.available_vram_by_gpu)
        if measured:
            return measured
        if self.profile.gpu_count == 1:
            return {0: self.measurement.available_vram_bytes}
        return None

    def _fits_records(self, records: tuple[ResourceReservation, ...], *, include_current: bool) -> bool:
        capacities = self._capacities()
        used = self._used if include_current else {dimension: 0 for dimension in RESOURCE_DIMENSIONS}
        totals = {dimension: 0 for dimension in RESOURCE_DIMENSIONS}
        for record in records:
            values = {
                "vram_bytes": record.vram_reserved_bytes,
                "ram_bytes": record.ram_reserved_bytes,
                "cpu_millicores": record.cpu_reserved_millicores,
                "kv_cache_bytes": record.kv_cache_reserved_bytes,
                "context_tokens": record.context_tokens_reserved,
                "scratch_bytes": record.scratch_reserved_bytes,
                "slots": record.slots_reserved,
            }
            for dimension, value in values.items():
                totals[dimension] += value
        if any(totals[d] + used[d] > capacities[d] for d in RESOURCE_DIMENSIONS):
            return False
        gpu_capacities = self._gpu_capacities()
        if gpu_capacities is None and any(record.vram_reserved_bytes > 0 for record in records):
            return False
        gpu_totals: dict[int, int] = {}
        for record in records:
            if record.vram_reserved_bytes <= 0:
                continue
            if not record.gpu_indices:
                return False
            share = (record.vram_reserved_bytes + len(record.gpu_indices) - 1) // len(record.gpu_indices)
            for gpu_index in record.gpu_indices:
                gpu_totals[gpu_index] = gpu_totals.get(gpu_index, 0) + share
        for gpu_index, demand in gpu_totals.items():
            if gpu_index not in (gpu_capacities or {}):
                return False
            current = self._used_gpu.get(gpu_index, 0) if include_current else 0
            if current + demand > (gpu_capacities or {})[gpu_index]:
                return False
        return True

    def _store_active_lease(self, lease: ResourceLease) -> None:
        self._leases[lease.lease_id] = lease
        self._lease_key_index[self._lease_key_from_lease(lease)] = lease.lease_id
        self._add_active_lease(lease)

    def _add_active_lease(self, lease: ResourceLease) -> None:
        if lease.status not in _ACTIVE_LEASE_STATUSES:
            return
        values = dict(lease.reservation)
        for dimension in RESOURCE_DIMENSIONS:
            self._used[dimension] += values.get(dimension, 0)
        self._add_gpu_usage(lease, 1)

    def _remove_active_lease(self, lease: ResourceLease) -> None:
        values = dict(lease.reservation)
        for dimension in RESOURCE_DIMENSIONS:
            self._used[dimension] = max(0, self._used[dimension] - values.get(dimension, 0))
        self._add_gpu_usage(lease, -1)

    def _add_gpu_usage(self, lease: ResourceLease, sign: int) -> None:
        vram = dict(lease.reservation).get("vram_bytes", 0)
        if vram <= 0 or not lease.gpu_indices:
            return
        share = (vram + len(lease.gpu_indices) - 1) // len(lease.gpu_indices)
        for gpu_index in lease.gpu_indices:
            self._used_gpu[gpu_index] = max(0, self._used_gpu.get(gpu_index, 0) + sign * share)

    def _request_key(self, request: AdmissionRequest) -> str:
        return idempotency_key(
            "scheduler.admission",
            request.task_id,
            request.team_id,
            request.worker_capabilities,
            request.worker_roles,
            request.reservations,
            request.gpu_indices,
            request.verifier_worker_id,
            request.priority,
            request.requested_mode,
            request.dependency_graph,
            request.worker_stages,
            request.pipeline_stages,
            request.residency_requests,
            request.model_targets,
            request.qualification_refs,
            request.clearance.value,
            request.taint.value,
            request.policy_version_hash,
            request.plan_version,
        )

    def _lease_key(self, plan: TeamResourcePlan, worker_id: str) -> str:
        return idempotency_key("scheduler.lease.grant", plan.plan_id, worker_id)

    def _lease_key_from_lease(self, lease: ResourceLease) -> str:
        return lease.idempotency_key

    def _prospective_queue_position(self, request: AdmissionRequest, request_key: str) -> int:
        entries = list(self._queue) + [(request.priority_rank, self._queue_sequence, request_key)]
        return sorted(entries).index((request.priority_rank, self._queue_sequence, request_key)) + 1

    def _keys_for_team(self, team_id: str) -> set[str]:
        return {
            key for key, request in self._requests_by_key.items()
            if request.team_id == team_id
        }

    def _request_from_plan(self, plan: TeamResourcePlan) -> AdmissionRequest:
        records = plan.reservation_records
        return AdmissionRequest(
            task_id=plan.task_id,
            team_id=plan.team_id,
            worker_capabilities=tuple(sorted(plan.worker_capabilities.items())),
            reservations=tuple(
                (
                    record.worker_id,
                    tuple((name, value) for name, value in {
                        "vram_bytes": record.vram_reserved_bytes,
                        "ram_bytes": record.ram_reserved_bytes,
                        "cpu_millicores": record.cpu_reserved_millicores,
                        "kv_cache_bytes": record.kv_cache_reserved_bytes,
                        "context_tokens": record.context_tokens_reserved,
                        "scratch_bytes": record.scratch_reserved_bytes,
                        "slots": record.slots_reserved,
                    }.items()),
                )
                for record in records
            ),
            verifier_worker_id=str(plan.scheduling.get("verifier_worker_id", "")),
            priority=plan.priority,
            requested_mode=plan.requested_mode,
            worker_roles=tuple((record.worker_id, record.role) for record in records),
            gpu_indices=tuple((record.worker_id, record.gpu_indices) for record in records),
            dependency_graph=tuple(sorted(plan.dependency_graph.items())),
            residency_requests=tuple(sorted(plan.residency_requests.items())),
            model_targets=tuple((record.worker_id, record.model_target_id) for record in records),
            qualification_refs=tuple((record.worker_id, record.qualification_id) for record in records),
            clearance=Clearance(str(plan.provenance.get("clearance", Clearance.internal.value))),
            taint=Taint(str(plan.provenance.get("taint", Taint.clean.value))),
            policy_version_hash=str(plan.provenance.get("policy_hash", "policy.m4.2")),
            plan_version=plan.plan_version,
        )

    def _request_from_lease(self, lease: ResourceLease) -> AdmissionRequest:
        plan = self._plans.get(lease.plan_id)
        if plan is not None:
            return self._request_from_plan(plan)
        return AdmissionRequest(
            task_id=lease.task_id,
            team_id=lease.team_id,
            worker_capabilities=((lease.worker_id, lease.capability),),
            reservations=((lease.worker_id, lease.reservation),),
            verifier_worker_id=lease.worker_id,
            worker_roles=((lease.worker_id, lease.role),),
            gpu_indices=((lease.worker_id, lease.gpu_indices),),
            model_targets=((lease.worker_id, lease.model_target_id or "model.unknown"),),
            qualification_refs=((lease.worker_id, lease.qualification_id or "qualification.unknown"),),
            clearance=lease.clearance,
            taint=lease.taint,
            policy_version_hash=lease.policy_version_hash,
        )

    @staticmethod
    def _has_cycle(graph: Mapping[str, Iterable[str]], workers: set[str]) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(worker: str) -> bool:
            if worker in visiting:
                return True
            if worker in visited:
                return False
            visiting.add(worker)
            if any(visit(dependency) for dependency in graph.get(worker, ())):
                return True
            visiting.remove(worker)
            visited.add(worker)
            return False

        return any(visit(worker) for worker in workers)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise SchedulerError("scheduler timestamps must include timezone")
    return value.astimezone(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return _aware(value).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (AttributeError, ValueError) as exc:
        raise SchedulerError("invalid RFC3339 scheduler timestamp") from exc


def _next_version(version: str) -> str:
    try:
        return str(int(version) + 1)
    except ValueError:
        return f"{version}.1"


__all__ = [
    "LeaseUnavailable",
    "RESOURCE_DIMENSIONS",
    "ResourceScheduler",
    "ScheduleDecision",
    "SchedulerError",
    "SchedulingRejected",
]
