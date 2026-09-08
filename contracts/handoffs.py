"""Orchestrator-owned handoffs and join barriers.

This module coordinates already validated worker assignments, packets, and
resource leases. It never runs a model, parses a file, opens a network
connection, or decides substantive domain correctness. Its only authority is
whether a declared synchronization precondition has been satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Mapping, Protocol

from .errors import ContractValidationError
from .ids import idempotency_key, stable_id
from .ledger import EventLedger, LedgerError, SQLiteLedgerStore, build_event
from .models import (
    BarrierStatus,
    Clearance,
    FactEnvelope,
    HandoffSubmission,
    JoinBarrier,
    LeaseStatus,
    ResourceLease,
    Taint,
    TaskEnvelope,
    TeamPlan,
    UntrustedEvidence,
    WorkerAssignment,
)


class HandoffRejected(RuntimeError):
    """A handoff failed a typed identity, scope, provenance, or lease gate."""

    def __init__(self, reason: str, *, code: str = "handoff_rejected") -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class HandoffReplayError(RuntimeError):
    """Committed handoff/barrier history cannot be reconstructed safely."""


class RecordResolver(Protocol):
    """Read-only resolver for governed records already produced elsewhere."""

    def assignment(self, assignment_id: str) -> WorkerAssignment | None: ...
    def lease(self, lease_id: str) -> ResourceLease | None: ...
    def fact(self, fact_id: str) -> FactEnvelope | None: ...
    def evidence(self, evidence_id: str) -> UntrustedEvidence | None: ...
    def artifact(self, artifact_id: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class InMemoryRecordResolver:
    """Small read-only resolver useful for tests and local projections."""

    assignments: Mapping[str, WorkerAssignment]
    leases: Mapping[str, ResourceLease]
    facts: Mapping[str, FactEnvelope]
    evidence_records: Mapping[str, UntrustedEvidence]
    artifacts: Mapping[str, Mapping[str, Any]]

    def assignment(self, assignment_id: str) -> WorkerAssignment | None:
        return self.assignments.get(assignment_id)

    def lease(self, lease_id: str) -> ResourceLease | None:
        return self.leases.get(lease_id)

    def fact(self, fact_id: str) -> FactEnvelope | None:
        return self.facts.get(fact_id)

    def evidence(self, evidence_id: str) -> UntrustedEvidence | None:
        return self.evidence_records.get(evidence_id)

    def artifact(self, artifact_id: str) -> Mapping[str, Any] | None:
        return self.artifacts.get(artifact_id)


@dataclass(frozen=True, slots=True)
class HandoffDecision:
    outcome: Literal["accepted", "duplicate", "rejected", "late", "conflicting"]
    handoff: HandoffSubmission | None
    barrier: JoinBarrier | None
    reason: str
    ledger_event_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BarrierDecision:
    outcome: BarrierStatus
    barrier: JoinBarrier
    reason: str
    ledger_event_refs: tuple[str, ...] = ()


class HandoffCoordinator:
    """Validate and commit typed handoffs while owning barrier projections."""

    def __init__(
        self,
        task: TaskEnvelope,
        team_plan: TeamPlan,
        assignments: Mapping[str, WorkerAssignment],
        *,
        plan_version: str,
        policy_version_hash: str,
        ledger: EventLedger | SQLiteLedgerStore | None = None,
        record_resolver: RecordResolver | None = None,
        actor_id: str = "orchestrator.handoff",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if team_plan.task_id != task.task_id:
            raise HandoffRejected("team plan task does not match task envelope", code="task_mismatch")
        if not plan_version.strip() or not policy_version_hash.strip():
            raise HandoffRejected("plan and policy identities are required", code="identity_missing")
        if not actor_id.strip():
            raise HandoffRejected("handoff actor identity is required", code="identity_missing")
        self.task = task
        self.team_plan = team_plan
        self.assignments = dict(assignments)
        self.plan_version = plan_version
        self.policy_version_hash = policy_version_hash
        self.ledger = ledger
        self.record_resolver = record_resolver
        self.actor_id = actor_id
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._barriers: dict[tuple[str, int], JoinBarrier] = {}
        self._handoffs: dict[str, HandoffSubmission] = {}
        self._handoffs_by_idempotency: dict[str, str] = {}
        self._accepted_by_source: dict[tuple[str, int, str], str] = {}
        self.reconcile()

    @property
    def barriers(self) -> tuple[JoinBarrier, ...]:
        return tuple(sorted(self._barriers.values(), key=lambda barrier: (barrier.barrier_id, barrier.barrier_version)))

    @property
    def handoffs(self) -> tuple[HandoffSubmission, ...]:
        return tuple(sorted(self._handoffs.values(), key=lambda handoff: handoff.handoff_id))

    def barrier(self, barrier_id: str, version: int = 1) -> JoinBarrier:
        try:
            return self._barriers[(barrier_id, version)]
        except KeyError as exc:
            raise HandoffRejected("join barrier does not exist", code="barrier_missing") from exc

    def open_barrier(self, barrier: JoinBarrier) -> JoinBarrier:
        """Open one immutable barrier version after validating its topology."""

        barrier = _round_trip(JoinBarrier, barrier)
        key = (barrier.barrier_id, barrier.barrier_version)
        existing = self._barriers.get(key)
        if existing is not None:
            if existing.digest() != barrier.digest():
                raise HandoffRejected("barrier identity was reused with different content", code="idempotency_conflict")
            return existing
        self._validate_barrier_open(barrier)
        refs = self._append_events(
            task_id=barrier.task_id,
            clearance=barrier.clearance,
            occurred_at=barrier.created_at,
            specs=[(
                "join_barrier.waiting",
                "JoinBarrier",
                {"barrier": barrier.to_dict(), "reason": "barrier_opened"},
                barrier.idempotency_key,
            )],
        )
        self._barriers[key] = barrier
        return barrier

    def submit_handoff(
        self,
        handoff: HandoffSubmission,
        *,
        now: datetime | None = None,
    ) -> HandoffDecision:
        """Validate one handoff and update at most one barrier version."""

        now_value = _aware(now or self._now_provider())
        try:
            handoff = _round_trip(HandoffSubmission, handoff)
            self._validate_handoff(handoff, now_value)
        except (ContractValidationError, HandoffRejected) as exc:
            reason = str(exc)
            code = getattr(exc, "code", "contract_invalid")
            refs = self._append_events(
                task_id=getattr(handoff, "task_id", self.task.task_id),
                clearance=getattr(handoff, "clearance", self.task.clearance),
                occurred_at=_rfc3339(now_value),
                specs=[(
                    "worker.handoff.rejected",
                    "HandoffSubmission",
                    {"failure_code": code, "reason": reason, "handoff_id": getattr(handoff, "handoff_id", "")},
                    idempotency_key("handoff.rejected", getattr(handoff, "idempotency_key", ""), code, reason),
                )],
            )
            return HandoffDecision("rejected", handoff if isinstance(handoff, HandoffSubmission) else None, None, reason, refs)

        idem_existing = self._handoffs_by_idempotency.get(handoff.idempotency_key)
        if idem_existing is not None:
            existing = self._handoffs[idem_existing]
            if existing.digest() != handoff.digest():
                reason = "handoff idempotency key was reused with different packet or destination"
                refs = self._append_events(
                    task_id=handoff.task_id,
                    clearance=handoff.clearance,
                    occurred_at=_rfc3339(now_value),
                    specs=[(
                        "worker.handoff.rejected",
                        "HandoffSubmission",
                        {"failure_code": "idempotency_conflict", "reason": reason, "handoff_id": handoff.handoff_id},
                        idempotency_key("handoff.rejected", handoff.idempotency_key, handoff.digest()),
                    )],
                )
                return HandoffDecision("rejected", handoff, self._barriers.get((handoff.barrier_id, handoff.barrier_version)), reason, refs)
            return HandoffDecision(
                "duplicate",
                existing,
                self._barriers.get((existing.barrier_id, existing.barrier_version)),
                "identical handoff already committed",
                self._refs_for_handoff(existing.handoff_id),
            )

        barrier = self.barrier(handoff.barrier_id, handoff.barrier_version)
        if _parse_time(barrier.deadline) <= now_value:
            refs = self._append_events(
                task_id=handoff.task_id,
                clearance=handoff.clearance,
                occurred_at=_rfc3339(now_value),
                specs=[(
                    "worker.handoff.late",
                    "HandoffSubmission",
                    {"handoff": handoff.to_dict(), "barrier_id": barrier.barrier_id, "reason": "barrier_deadline_elapsed"},
                    idempotency_key("handoff.late", handoff.idempotency_key),
                )],
            )
            self._handoffs[handoff.handoff_id] = handoff
            self._handoffs_by_idempotency[handoff.idempotency_key] = handoff.handoff_id
            return HandoffDecision("late", handoff, barrier, "handoff arrived after the immutable barrier deadline", refs)

        if barrier.status != BarrierStatus.waiting:
            reason = f"barrier is already {barrier.status.value}"
            refs = self._append_events(
                task_id=handoff.task_id,
                clearance=handoff.clearance,
                occurred_at=_rfc3339(now_value),
                specs=[(
                    "worker.handoff.rejected",
                    "HandoffSubmission",
                    {"failure_code": "barrier_terminal", "reason": reason, "handoff_id": handoff.handoff_id},
                    idempotency_key("handoff.rejected", handoff.idempotency_key, "barrier_terminal"),
                )],
            )
            return HandoffDecision("rejected", handoff, barrier, reason, refs)

        source_key = (barrier.barrier_id, barrier.barrier_version, handoff.source_assignment_id)
        existing_source_id = self._accepted_by_source.get(source_key)
        if existing_source_id is not None:
            existing_source = self._handoffs[existing_source_id]
            if existing_source.packet_hash == handoff.packet_hash:
                return HandoffDecision("duplicate", existing_source, barrier, "identical packet already satisfied this predecessor", self._refs_for_handoff(existing_source.handoff_id))
            conflict = self._barrier_with_conflict(barrier, existing_source, handoff)
            refs = self._append_events(
                task_id=handoff.task_id,
                clearance=handoff.clearance,
                occurred_at=_rfc3339(now_value),
                specs=[
                    (
                        "worker.handoff.rejected",
                        "HandoffSubmission",
                        {"failure_code": "conflicting_packet", "reason": "different packets claim the same predecessor", "handoff": handoff.to_dict()},
                        idempotency_key("handoff.conflict", handoff.idempotency_key),
                    ),
                    (
                        "join_barrier.resolved",
                        "JoinBarrier",
                        {"barrier": conflict.to_dict(), "outcome": BarrierStatus.conflicting.value},
                        idempotency_key("barrier.conflict", conflict.barrier_id, conflict.barrier_version, handoff.packet_hash),
                    ),
                ],
            )
            self._handoffs[handoff.handoff_id] = handoff
            self._handoffs_by_idempotency[handoff.idempotency_key] = handoff.handoff_id
            self._barriers[(barrier.barrier_id, barrier.barrier_version)] = conflict
            return HandoffDecision("conflicting", handoff, conflict, "different packet for an already satisfied predecessor", refs)

        updated = self._barrier_after_accept(barrier, handoff)
        refs = self._append_events(
            task_id=handoff.task_id,
            clearance=handoff.clearance,
            occurred_at=_rfc3339(now_value),
            specs=self._accepted_event_specs(handoff, updated),
        )
        self._handoffs[handoff.handoff_id] = handoff
        self._handoffs_by_idempotency[handoff.idempotency_key] = handoff.handoff_id
        self._accepted_by_source[source_key] = handoff.handoff_id
        self._barriers[(barrier.barrier_id, barrier.barrier_version)] = updated
        return HandoffDecision("accepted", handoff, updated, "handoff accepted and barrier projection committed", refs)

    def resolve_barrier(
        self,
        barrier_id: str,
        *,
        outcome: BarrierStatus | str,
        now: datetime | None = None,
        reason: str = "",
    ) -> BarrierDecision:
        """Resolve a waiting barrier without treating missing work as success."""

        now_value = _aware(now or self._now_provider())
        target = outcome if isinstance(outcome, BarrierStatus) else BarrierStatus(outcome)
        barrier = self.barrier(barrier_id)
        if barrier.status != BarrierStatus.waiting:
            raise HandoffRejected("only a waiting barrier can be resolved", code="barrier_terminal")
        if target == BarrierStatus.completed:
            raise HandoffRejected("completion is derived only from accepted packets", code="completion_not_manual")
        if target in {BarrierStatus.timed_out, BarrierStatus.missing} and _parse_time(barrier.deadline) > now_value:
            raise HandoffRejected("barrier deadline has not elapsed", code="deadline_not_reached")
        if target not in {BarrierStatus.missing, BarrierStatus.conflicting, BarrierStatus.timed_out, BarrierStatus.cancelled, BarrierStatus.needs_review}:
            raise HandoffRejected("invalid non-completed barrier resolution", code="invalid_resolution")
        updated = JoinBarrier.from_dict({
            **barrier.to_dict(),
            "status": target.value,
            "unresolved_questions": list(barrier.unresolved_questions) + ([reason] if reason else []),
        })
        refs = self._append_events(
            task_id=barrier.task_id,
            clearance=barrier.clearance,
            occurred_at=_rfc3339(now_value),
            specs=[(
                "join_barrier.resolved",
                "JoinBarrier",
                {"barrier": updated.to_dict(), "outcome": target.value, "reason": reason or target.value},
                idempotency_key("barrier.resolve", barrier.barrier_id, barrier.barrier_version, target.value),
            )],
        )
        self._barriers[(barrier.barrier_id, barrier.barrier_version)] = updated
        return BarrierDecision(target, updated, reason or target.value, refs)

    def reconcile(self) -> None:
        """Rebuild accepted handoffs and barrier versions from ledger history."""

        self._barriers.clear()
        self._handoffs.clear()
        self._handoffs_by_idempotency.clear()
        self._accepted_by_source.clear()
        if self.ledger is None:
            return
        for event in self.ledger.events:
            payload = event.payload
            if event.event_type in {"join_barrier.waiting", "join_barrier.completed", "join_barrier.resolved"}:
                raw = payload.get("barrier")
                if not isinstance(raw, dict):
                    continue
                try:
                    barrier = JoinBarrier.from_dict(raw)
                except ContractValidationError as exc:
                    raise HandoffReplayError("ledger contains an invalid join barrier") from exc
                self._barriers[(barrier.barrier_id, barrier.barrier_version)] = barrier
            if event.event_type in {"worker.handoff", "worker.handoff.rejected", "worker.handoff.late"}:
                raw = payload.get("handoff")
                if not isinstance(raw, dict):
                    continue
                try:
                    handoff = HandoffSubmission.from_dict(raw)
                except ContractValidationError as exc:
                    raise HandoffReplayError("ledger contains an invalid handoff") from exc
                self._handoffs[handoff.handoff_id] = handoff
                self._handoffs_by_idempotency[handoff.idempotency_key] = handoff.handoff_id
                if event.event_type == "worker.handoff":
                    self._accepted_by_source[(handoff.barrier_id, handoff.barrier_version, handoff.source_assignment_id)] = handoff.handoff_id

    def _validate_barrier_open(self, barrier: JoinBarrier) -> None:
        if barrier.task_id != self.task.task_id or barrier.team_id != self.team_plan.team_id:
            raise HandoffRejected("barrier task or team does not match the committed plan", code="identity_mismatch")
        if barrier.plan_version != self.plan_version or barrier.policy_version_hash != self.policy_version_hash:
            raise HandoffRejected("barrier uses a stale plan or policy version", code="stale_plan")
        if barrier.status != BarrierStatus.waiting or barrier.join_policy != "join_all":
            raise HandoffRejected("barrier must open as a waiting join_all barrier", code="barrier_shape")
        destination = self._assignment(barrier.destination_assignment_id)
        if destination.stage != barrier.destination_stage:
            raise HandoffRejected("barrier destination stage does not match assignment", code="destination_mismatch")
        required = set(self.team_plan.dependency_graph.get(barrier.destination_assignment_id, ()))
        if required != set(barrier.required_predecessor_assignment_ids):
            raise HandoffRejected("barrier predecessor set does not match the committed dependency graph", code="topology_mismatch")
        if set(barrier.missing_assignment_ids) != required:
            raise HandoffRejected("new barrier must begin with every predecessor missing", code="barrier_shape")
        if barrier.accepted_handoff_ids or barrier.accepted_packet_hashes or barrier.conflict_packet_refs:
            raise HandoffRejected("new barrier cannot contain prior handoff state", code="barrier_shape")
        if _rank(barrier.clearance) > _rank(self.task.clearance):
            raise HandoffRejected("barrier clearance exceeds task clearance", code="clearance_exceeded")
        if _rank(barrier.clearance) > _rank(destination.clearance):
            raise HandoffRejected("barrier clearance exceeds destination assignment", code="clearance_exceeded")

    def _validate_handoff(self, handoff: HandoffSubmission, now: datetime) -> None:
        if handoff.task_id != self.task.task_id or handoff.team_id != self.team_plan.team_id:
            raise HandoffRejected("handoff task or team does not match the committed plan", code="identity_mismatch")
        if handoff.plan_version != self.plan_version or handoff.policy_version_hash != self.policy_version_hash:
            raise HandoffRejected("handoff uses a stale plan or policy version", code="stale_plan")
        barrier = self.barrier(handoff.barrier_id, handoff.barrier_version)
        if _parse_time(handoff.deadline) != _parse_time(barrier.deadline):
            raise HandoffRejected("handoff deadline does not match the immutable barrier deadline", code="deadline_mismatch")
        if _parse_time(handoff.submitted_at) > now:
            raise HandoffRejected("handoff timestamp is in the future", code="timestamp_future")
        source = self._assignment(handoff.source_assignment_id)
        destination = self._assignment(handoff.destination_assignment_id)
        if source.worker_id != handoff.source_worker_id:
            raise HandoffRejected("source worker does not match source assignment", code="source_mismatch")
        if destination.stage != handoff.destination_stage:
            raise HandoffRejected("destination stage does not match destination assignment", code="destination_mismatch")
        if handoff.destination_assignment_id != barrier.destination_assignment_id:
            raise HandoffRejected("handoff destination is not the barrier destination", code="destination_mismatch")
        if handoff.source_assignment_id not in barrier.required_predecessor_assignment_ids:
            raise HandoffRejected("source assignment is not a declared predecessor", code="topology_mismatch")
        if handoff.source_assignment_id == handoff.destination_assignment_id:
            raise HandoffRejected("self-handoff is not allowed", code="self_handoff")
        if handoff.clearance not in _CLEARANCE_RANK or _rank(handoff.clearance) > min(_rank(self.task.clearance), _rank(source.clearance), _rank(destination.clearance)):
            raise HandoffRejected("handoff clearance exceeds an authoritative boundary", code="clearance_exceeded")
        if _rank(handoff.packet.clearance) > _rank(handoff.clearance):
            raise HandoffRejected("packet clearance exceeds handoff clearance", code="clearance_exceeded")
        if _taint_rank(handoff.taint) < _taint_rank(handoff.packet.taint):
            raise HandoffRejected("handoff taint is cleaner than its packet", code="taint_downgrade")
        self._validate_lease(handoff, source, now)
        self._validate_references(handoff, destination)

    def _validate_lease(self, handoff: HandoffSubmission, source: WorkerAssignment, now: datetime) -> None:
        lease = self.record_resolver.lease(handoff.source_lease_id) if self.record_resolver else None
        if lease is None:
            raise HandoffRejected("source resource lease cannot be resolved", code="lease_missing")
        if lease.status != LeaseStatus.active:
            raise HandoffRejected("source resource lease is not active", code="lease_inactive")
        if lease.task_id != handoff.task_id or lease.team_id != handoff.team_id or lease.worker_id != source.worker_id:
            raise HandoffRejected("source resource lease identity does not match handoff", code="lease_mismatch")
        if _parse_time(lease.expires_at) <= now:
            raise HandoffRejected("source resource lease has expired", code="lease_expired")
        if _rank(lease.clearance) > _rank(source.clearance):
            raise HandoffRejected("lease clearance exceeds source assignment", code="lease_scope")
        if _taint_rank(lease.taint) > _taint_rank(handoff.taint):
            raise HandoffRejected("handoff taint is cleaner than the source lease", code="taint_downgrade")

    def _validate_references(self, handoff: HandoffSubmission, destination: WorkerAssignment) -> None:
        if self.record_resolver is None:
            raise HandoffRejected("governed packet references require a record resolver", code="provenance_unresolved")
        for fact_id in handoff.packet.fact_refs:
            fact = self.record_resolver.fact(fact_id)
            if fact is None:
                raise HandoffRejected(f"fact reference {fact_id!r} cannot be resolved", code="provenance_unresolved")
            if _rank(fact.clearance) > _rank(destination.clearance):
                raise HandoffRejected("fact clearance exceeds destination assignment", code="clearance_exceeded")
            if _taint_rank(handoff.packet.taint) < _taint_rank(fact.taint):
                raise HandoffRejected("packet taint downgraded a referenced fact", code="taint_downgrade")
        for evidence_id in handoff.packet.evidence_refs:
            evidence = self.record_resolver.evidence(evidence_id)
            if evidence is None:
                raise HandoffRejected(f"evidence reference {evidence_id!r} cannot be resolved", code="provenance_unresolved")
            if _rank(evidence.clearance) > _rank(destination.clearance):
                raise HandoffRejected("evidence clearance exceeds destination assignment", code="clearance_exceeded")
            if _taint_rank(handoff.packet.taint) < _taint_rank(evidence.taint):
                raise HandoffRejected("packet taint downgraded untrusted evidence", code="taint_downgrade")
        artifact_hashes = dict(handoff.artifact_hashes)
        if len(artifact_hashes) != len(handoff.artifact_hashes):
            raise HandoffRejected("artifact hash references cannot be duplicated", code="artifact_integrity")
        for artifact_id in handoff.packet.artifact_refs:
            expected_hash = artifact_hashes.get(artifact_id)
            artifact = self.record_resolver.artifact(artifact_id)
            if not expected_hash or artifact is None or artifact.get("content_hash") != expected_hash:
                raise HandoffRejected("artifact manifest hash does not match the handoff", code="artifact_integrity")
            if "clearance" in artifact and _rank(Clearance(str(artifact["clearance"]))) > _rank(destination.clearance):
                raise HandoffRejected("artifact clearance exceeds destination assignment", code="clearance_exceeded")

    def _assignment(self, assignment_id: str) -> WorkerAssignment:
        if assignment_id not in self.team_plan.assignments:
            raise HandoffRejected("assignment is not in the committed team plan", code="assignment_missing")
        assignment = self.assignments.get(assignment_id)
        if assignment is None and self.record_resolver is not None:
            assignment = self.record_resolver.assignment(assignment_id)
        if assignment is None:
            raise HandoffRejected("assignment cannot be resolved", code="assignment_missing")
        if assignment.task_id != self.task.task_id or assignment.team_id != self.team_plan.team_id:
            raise HandoffRejected("assignment identity does not match task and team", code="assignment_mismatch")
        return assignment

    def _barrier_after_accept(self, barrier: JoinBarrier, handoff: HandoffSubmission) -> JoinBarrier:
        accepted_ids = tuple(sorted(set(barrier.accepted_handoff_ids) | {handoff.handoff_id}))
        accepted_hashes = dict(barrier.accepted_packet_hashes)
        accepted_hashes[handoff.source_assignment_id] = handoff.packet_hash
        missing = tuple(sorted(set(barrier.required_predecessor_assignment_ids) - set(accepted_hashes)))
        unresolved = set(barrier.unresolved_questions)
        unresolved.update(f"check:{name}" for name, passed in handoff.packet.checks.items() if not passed)
        unresolved.update(handoff.packet.unresolved_questions)
        status = BarrierStatus.completed if not missing and not unresolved else BarrierStatus.waiting
        taint = max((barrier.taint, handoff.taint), key=_taint_rank)
        return JoinBarrier.from_dict({
            **barrier.to_dict(),
            "accepted_handoff_ids": list(accepted_ids),
            "accepted_packet_hashes": [[source, packet_hash] for source, packet_hash in sorted(accepted_hashes.items())],
            "missing_assignment_ids": list(missing),
            "status": status.value,
            "taint": taint.value,
            "unresolved_questions": sorted(unresolved),
            "lease_refs": sorted(set(barrier.lease_refs) | {handoff.source_lease_id}),
        })

    def _barrier_with_conflict(self, barrier: JoinBarrier, first: HandoffSubmission, second: HandoffSubmission) -> JoinBarrier:
        conflicts = set(barrier.conflict_packet_refs)
        conflicts.add((first.handoff_id, first.packet_hash))
        conflicts.add((second.handoff_id, second.packet_hash))
        taint = max((barrier.taint, first.taint, second.taint), key=_taint_rank)
        return JoinBarrier.from_dict({
            **barrier.to_dict(),
            "status": BarrierStatus.conflicting.value,
            "taint": taint.value,
            "conflict_packet_refs": [[handoff_id, packet_hash] for handoff_id, packet_hash in sorted(conflicts)],
        })

    def _accepted_event_specs(self, handoff: HandoffSubmission, barrier: JoinBarrier) -> list[tuple[str, str, dict[str, Any], str]]:
        payload = {
            "handoff": handoff.to_dict(),
            "barrier": barrier.to_dict(),
            "packet_hash": handoff.packet_hash,
            "source_assignment_id": handoff.source_assignment_id,
            "destination_assignment_id": handoff.destination_assignment_id,
            "source_lease_id": handoff.source_lease_id,
            "plan_version": handoff.plan_version,
            "policy_version_hash": handoff.policy_version_hash,
            "provenance": {
                "source_ref": "work-packet:" + handoff.packet.packet_id,
                "confidence": 1.0,
                "clearance": handoff.clearance.value,
                "taint": handoff.taint.value,
            },
        }
        specs = [(
            "worker.handoff",
            "HandoffSubmission",
            payload,
            handoff.idempotency_key,
        )]
        if barrier.status == BarrierStatus.completed:
            specs.append((
                "join_barrier.completed",
                "JoinBarrier",
                {"barrier": barrier.to_dict(), "outcome": BarrierStatus.completed.value},
                idempotency_key("barrier.completed", barrier.barrier_id, barrier.barrier_version, *barrier.accepted_handoff_ids),
            ))
        else:
            specs.append((
                "join_barrier.waiting",
                "JoinBarrier",
                {"barrier": barrier.to_dict(), "outcome": BarrierStatus.waiting.value},
                idempotency_key("barrier.waiting", barrier.barrier_id, barrier.barrier_version, *barrier.accepted_handoff_ids),
            ))
        return specs

    def _refs_for_handoff(self, handoff_id: str) -> tuple[str, ...]:
        if self.ledger is None:
            return ()
        refs: list[str] = []
        for event in self.ledger.events:
            raw_handoff = event.payload.get("handoff")
            if isinstance(raw_handoff, dict) and raw_handoff.get("handoff_id") == handoff_id:
                refs.append(event.event_id)
        return tuple(refs)

    def _append_events(
        self,
        *,
        task_id: str,
        clearance: Clearance,
        occurred_at: str,
        specs: list[tuple[str, str, dict[str, Any], str]],
    ) -> tuple[str, ...]:
        if self.ledger is None or not specs:
            return ()
        existing = tuple(self.ledger.events)
        previous = existing[-1].event_hash if existing else None
        events = []
        for offset, (event_type, contract, payload, key) in enumerate(specs):
            event = build_event(
                event_type=event_type,
                task_id=task_id,
                actor_id=self.actor_id,
                actor_type="orchestrator",
                payload_contract=contract,
                payload_version="1.0",
                payload=payload,
                clearance=clearance,
                idempotency=key,
                sequence=len(existing) + offset,
                previous_event_hash=previous,
                occurred_at=occurred_at,
            )
            events.append(event)
            previous = event.event_hash
        try:
            if isinstance(self.ledger, EventLedger):
                committed = self.ledger.append_batch(events)
            else:
                self.ledger.append_batch(events, stable_id("handoff-transaction", *(event.event_id for event in events)))
                committed = tuple(events)
        except (ContractValidationError, LedgerError) as exc:
            raise HandoffRejected("handoff or barrier ledger append failed", code="ledger_failure") from exc
        return tuple(event.event_id for event in committed)


def _round_trip(contract: type[Any], value: Any) -> Any:
    if isinstance(value, contract):
        return contract.from_dict(value.to_dict())
    return contract.from_dict(value)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise HandoffRejected("timestamps must include timezone", code="timestamp_invalid")
    return value.astimezone(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return _aware(value).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (AttributeError, TypeError, ValueError) as exc:
        raise HandoffRejected("timestamp is not RFC3339", code="timestamp_invalid") from exc


_CLEARANCE_RANK = {
    Clearance.public: 0,
    Clearance.internal: 1,
    Clearance.restricted: 2,
    Clearance.secret: 3,
}
_TAINT_RANK = {Taint.clean: 0, Taint.untrusted: 1, Taint.contaminated: 2}


def _rank(value: Clearance) -> int:
    return _CLEARANCE_RANK[value]


def _taint_rank(value: Taint) -> int:
    return _TAINT_RANK[value]


__all__ = [
    "BarrierDecision",
    "HandoffCoordinator",
    "HandoffDecision",
    "HandoffRejected",
    "HandoffReplayError",
    "InMemoryRecordResolver",
    "RecordResolver",
]
