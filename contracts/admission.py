"""Deterministic hardware measurement and safe team admission for M5.2.

This module is deliberately network-free.  All admission decisions are
deterministic functions of the supplied HardwareProfile and HardwareMeasurement.
No method performs I/O; callers are responsible for writing ledger events.

Priority classes (ordered highest → lowest):
    interactive_high_consequence
    interactive_normal
    scheduled_domain_work
    background_ingestion
    maintenance

Legacy values ``interactive`` and ``background`` are accepted as aliases for
``interactive_normal`` and ``background_ingestion`` respectively so that
existing callers and tests are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .ids import idempotency_key, stable_id
from .models import PRIORITY_CLASSES, HardwareProfile, TeamResourcePlan

# ── Priority ordering (lower number = higher priority) ────────────────────────
_PRIORITY_ORDER: dict[str, int] = {
    "interactive_high_consequence": 0,
    "interactive_normal": 1,
    "scheduled_domain_work": 2,
    "background_ingestion": 3,
    "maintenance": 4,
}
# Legacy aliases accepted for backward compatibility
_PRIORITY_ALIASES: dict[str, str] = {
    "interactive": "interactive_normal",
    "background": "background_ingestion",
}
_BACKGROUND_PRIORITIES = {"background_ingestion", "maintenance"}
_VALID_PRIORITIES = PRIORITY_CLASSES | set(_PRIORITY_ALIASES)


def _normalize_priority(raw: str) -> str:
    """Resolve a legacy alias or validate a canonical priority class."""
    if raw in _PRIORITY_ALIASES:
        return _PRIORITY_ALIASES[raw]
    return raw


class AdmissionError(RuntimeError):
    """Admission cannot proceed without changing authority or safety."""


@dataclass(frozen=True, slots=True)
class HardwareMeasurement:
    """Live hardware capacity snapshot produced by the local probe script.

    All byte values reflect *currently available* capacity after reserved OS
    and runtime overhead has been subtracted.  ``egress_verified`` must be
    True: a measurement from a node that has not passed the no-egress check
    is not trusted for consequential work.
    """

    measurement_id: str
    profile_id: str
    measured_at: str
    available_vram_bytes: int
    available_ram_bytes: int
    kv_cache_bytes: int
    # Residency map: (target_id, resident_vram_bytes)
    model_residency_bytes: tuple[tuple[str, int], ...]
    # Per-target measured latency: (target_id, first_token_ms)
    latency_ms: tuple[tuple[str, float], ...]
    # Per-target measured throughput: (target_id, tokens_per_second)
    throughput_tokens_per_second: tuple[tuple[str, float], ...]
    # Per-sandbox limit: (limit_name, value)
    sandbox_limits: tuple[tuple[str, int], ...]
    max_concurrency: int
    egress_verified: bool

    def __post_init__(self) -> None:
        for name in ("available_vram_bytes", "available_ram_bytes", "kv_cache_bytes", "max_concurrency"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise AdmissionError(f"{name} must be a non-negative integer")
        if self.max_concurrency < 1:
            raise AdmissionError("hardware must have at least one concurrency slot")
        if not self.egress_verified:
            raise AdmissionError(
                "hardware must have a verified no-egress status before consequential admission"
            )


@dataclass(frozen=True, slots=True)
class AdmissionRequest:
    """A request to reserve resources for a worker team.

    ``verifier_worker_id`` must name one of the workers in ``reservations``.
    If the verifier reservation is absent, admission returns ``stopped``
    (never ``queued`` or ``admitted``).

    ``degraded_allowed`` controls whether the controller may return
    ``degraded_needs_review`` instead of ``queued`` when only a lower-VRAM
    target path is available.  The caller (orchestrator) sets this only when
    an explicitly qualified lower-capability target exists for the same role.
    """

    task_id: str
    team_id: str
    worker_capabilities: tuple[tuple[str, str], ...]
    reservations: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    verifier_worker_id: str
    priority: str = "interactive_normal"
    background: bool = False           # True ↔ task is a background ingestion job
    degraded_allowed: bool = False     # True ↔ caller has a qualified lower-VRAM fallback

    def __post_init__(self) -> None:
        normalized = _normalize_priority(self.priority)
        if normalized not in PRIORITY_CLASSES:
            raise AdmissionError(
                f"priority must be one of {sorted(PRIORITY_CLASSES)} "
                f"(or legacy aliases 'interactive' / 'background'); got {self.priority!r}"
            )
        # Normalize in-place using object.__setattr__ because the dataclass is frozen
        object.__setattr__(self, "priority", normalized)
        if not self.verifier_worker_id.strip():
            raise AdmissionError("verifier_worker_id is required")
        if not self.reservations:
            raise AdmissionError("reservations cannot be empty")

    def reservation_map(self) -> dict[str, dict[str, int]]:
        """Return reservations as a plain mutable dict for arithmetic."""
        return {worker: dict(values) for worker, values in self.reservations}

    @property
    def priority_rank(self) -> int:
        """Numeric rank for queue ordering (0 = highest priority)."""
        return _PRIORITY_ORDER.get(self.priority, 99)

    @property
    def is_background(self) -> bool:
        return self.priority in _BACKGROUND_PRIORITIES or self.background


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """Immutable result of an admission attempt."""

    plan: TeamResourcePlan
    decision_id: str
    reason: str
    # Structured audit payload suitable for a ledger event.
    audit_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReleaseRecord:
    """Audit record returned by AdmissionController.release()."""

    team_id: str
    released_vram_bytes: int
    remaining_active_vram_bytes: int
    audit_payload: dict[str, Any]


class AdmissionController:
    """Deterministic admission controller with parallel/serial/queue/degraded outcomes.

    State transitions:
        admitted (parallel)         — all reservations fit concurrently
        admitted (serial_virtual_team) — only the largest single reservation fits
        degraded_needs_review       — caller has a qualified lower-VRAM fallback
        queued                      — capacity temporarily unavailable; verifier preserved
        stopped                     — no safe outcome is possible (oversized or no verifier)

    The controller never silently removes the verifier or lowers thresholds.
    A missing verifier reservation always produces ``stopped``, not ``queued``.

    Active VRAM allocations are tracked across multiple ``admit()`` calls so that
    the available headroom used in each decision reflects already-committed work.
    """

    def __init__(self, profile: HardwareProfile, measurement: HardwareMeasurement) -> None:
        if profile.profile_id != measurement.profile_id:
            raise AdmissionError(
                f"measurement profile_id {measurement.profile_id!r} does not match "
                f"hardware profile {profile.profile_id!r}"
            )
        self.profile = profile
        self.measurement = measurement
        self._active_vram: int = 0
        self._active_allocations: dict[str, int] = {}  # team_id → committed vram_bytes
        # Queue entries: (priority_rank, sequence, request)
        self._queue: list[tuple[int, int, AdmissionRequest]] = []
        self._sequence: int = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def admit(self, request: AdmissionRequest) -> AdmissionDecision:
        """Evaluate a team resource request and return a deterministic decision.

        Checks (in order):
        1. Verifier reservation present — else stopped.
        2. Parallel fit — if all reservations fit in available VRAM and concurrency
           ceiling, admit as parallel.
        3. Serial fit — if the largest single reservation fits, admit as
           serial_virtual_team.
        4. Degraded fit — if caller permits degraded mode and the verifier fits alone
           (indicating a lower-VRAM qualified fallback exists), return degraded_needs_review.
        5. Background or already-active work — queue the request.
        6. Otherwise — stop.
        """
        reservations = request.reservation_map()
        total_vram = sum(v.get("vram_bytes", 0) for v in reservations.values())
        verifier = reservations.get(request.verifier_worker_id)

        # Gate 1: verifier must be present — safety invariant, cannot be waived
        if verifier is None:
            return self._decision(request, "stopped",
                                  "independent verifier reservation is missing — cannot proceed safely",
                                  "serial_virtual_team")

        available_vram = self.measurement.available_vram_bytes - self._active_vram

        # Gate 2: parallel admission
        concurrency_ceiling = min(self.profile.safe_parallel_slots, self.measurement.max_concurrency)
        if total_vram <= available_vram and len(reservations) <= concurrency_ceiling:
            return self._decision(request, "admitted",
                                  "all worker reservations fit concurrently within VRAM and concurrency ceiling",
                                  "parallel")

        # Gate 3: serial virtual-team admission
        serial_vram = max(v.get("vram_bytes", 0) for v in reservations.values())
        if serial_vram <= available_vram:
            return self._decision(request, "admitted",
                                  "reservations fit only as a serial virtual team (sequential worker execution)",
                                  "serial_virtual_team")

        # Gate 4: degraded mode — caller has a qualified lower-VRAM fallback target
        verifier_vram = verifier.get("vram_bytes", 0)
        if request.degraded_allowed and verifier_vram <= available_vram:
            return self._decision(request, "degraded_needs_review",
                                  "primary targets exceed available VRAM; lower-capability qualified fallback "
                                  "admitted with mandatory human review",
                                  "serial_virtual_team")

        # Gate 5: queue
        if request.is_background or self._active_vram > 0:
            self._queue.append((request.priority_rank, self._sequence, request))
            self._sequence += 1
            return self._decision(request, "queued",
                                  "resource capacity temporarily unavailable; verifier reservation preserved in queue",
                                  "serial_virtual_team")

        # Gate 6: stop — no safe path
        return self._decision(request, "stopped",
                              "no reservation fits the available hardware profile; cannot proceed without "
                              "removing the verifier or lowering safety thresholds",
                              "serial_virtual_team")

    def release(self, request: AdmissionRequest) -> ReleaseRecord:
        """Release the VRAM allocation for a completed or cancelled team.

        Returns a ReleaseRecord suitable for emitting a ``resource.lease.released``
        ledger event.  Releasing a team that was never admitted (queued or stopped)
        is a no-op and returns a zero-bytes release record.
        """
        freed = self._active_allocations.pop(request.team_id, 0)
        self._active_vram = max(0, self._active_vram - freed)
        # Remove from queue if it was queued
        self._queue = [
            entry for entry in self._queue if entry[2].team_id != request.team_id
        ]
        payload = {
            "team_id": request.team_id,
            "task_id": request.task_id,
            "released_vram_bytes": freed,
            "remaining_active_vram_bytes": self._active_vram,
        }
        return ReleaseRecord(
            team_id=request.team_id,
            released_vram_bytes=freed,
            remaining_active_vram_bytes=self._active_vram,
            audit_payload=payload,
        )

    def queued_requests(self) -> tuple[AdmissionRequest, ...]:
        """Return queued requests in priority order (highest priority first)."""
        return tuple(entry[2] for entry in sorted(self._queue))

    def active_vram_bytes(self) -> int:
        """Return the total VRAM bytes currently committed to active teams."""
        return self._active_vram

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _decision(
        self,
        request: AdmissionRequest,
        admission: str,
        reason: str,
        mode: str,
    ) -> AdmissionDecision:
        reservations = request.reservation_map()
        parallel = mode == "parallel"
        admitted_or_degraded = admission in {"admitted", "degraded_needs_review"}

        if admitted_or_degraded:
            allocation = (
                sum(v.get("vram_bytes", 0) for v in reservations.values())
                if parallel
                else max(v.get("vram_bytes", 0) for v in reservations.values())
            )
            self._active_vram += allocation
            self._active_allocations[request.team_id] = allocation
        else:
            allocation = 0

        plan = TeamResourcePlan(
            task_id=request.task_id,
            team_id=request.team_id,
            hardware_profile_ref=self.profile.profile_id,
            worker_capabilities=dict(request.worker_capabilities),
            reservations=reservations,
            concurrency_ceiling=len(reservations) if parallel else 1,
            execution_mode=mode if mode != "stop" else "serial_virtual_team",
            priority=request.priority,
            verifier_capacity=1,
            admission=admission,
            reason=reason,
        )
        decision_id = stable_id(
            "resource-decision",
            request.task_id,
            request.team_id,
            idempotency_key("admission", request.task_id, reservations),
        )
        audit_payload: dict[str, Any] = {
            "decision_id": decision_id,
            "task_id": request.task_id,
            "team_id": request.team_id,
            "admission": admission,
            "execution_mode": plan.execution_mode,
            "verifier_worker_id": request.verifier_worker_id,
            "priority": request.priority,
            "is_background": request.is_background,
            "degraded_allowed": request.degraded_allowed,
            "committed_vram_bytes": allocation,
            "active_vram_bytes_after": self._active_vram,
            "available_vram_bytes": self.measurement.available_vram_bytes,
            "reason": reason,
            # Ledger event types for the caller to emit
            "ledger_event_type": (
                "team.resource_plan.admitted" if admitted_or_degraded and admission != "degraded_needs_review"
                else "team.resource_plan.degraded_needs_review" if admission == "degraded_needs_review"
                else "team.resource_plan.queued" if admission == "queued"
                else "team.resource_plan.rejected"
            ),
        }
        return AdmissionDecision(plan=plan, decision_id=decision_id, reason=reason, audit_payload=audit_payload)
