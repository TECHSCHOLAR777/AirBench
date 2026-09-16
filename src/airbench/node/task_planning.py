"""Deterministic Node task planning and hardware admission (opt-in).

The Node API is a command boundary: it must not let a client drive the plan
loop.  This module is the small, sector-neutral composition that turns an
authorized task into a validated plan and a hardware-admission record using
only existing contracts:

  authorized task
    -> build a deterministic PlanProposal      (core, capability-ordered)
    -> Orchestrator.commit_proposal             (PlanValidator + task.plan.committed)
    -> AdmissionController.admit                (declared hardware envelope)
    -> Orchestrator.audit_event                 (team.resource_plan.*)

It deliberately does not synthesize domain content: steps are one model step
per permitted worker capability plus an independent verification step.  When no
hardware profile is configured the plan is still committed (so a governed
model call is reachable) but no admission event is written, which leaves the
task in ``planned`` without a hardware-ready review state.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from contracts import (
    AdmissionController,
    AdmissionRequest,
    HardwareMeasurement,
    HardwareProfile,
    Orchestrator,
    PlanProposal,
    PlanStep,
    TaskEnvelope,
    Taint,
    stable_id,
)

_ENABLED_VALUES = {"1", "true", "yes", "on"}


class TaskPlanningError(RuntimeError):
    """The task could not be planned or admitted deterministically."""


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    policy_version_hash: str
    hardware_profile: HardwareProfile | None = None
    worker_vram_bytes: int | None = None

    @classmethod
    def from_env(cls) -> "PlannerConfig":
        policy_hash = os.environ.get("AIRBENCH_POLICY_VERSION_HASH", "").strip()
        if not policy_hash:
            raise EnvironmentError("AIRBENCH_POLICY_VERSION_HASH is required when task planning is enabled")
        profile: HardwareProfile | None = None
        profile_path = os.environ.get("AIRBENCH_HARDWARE_PROFILE_PATH", "").strip()
        if profile_path:
            try:
                payload = json.loads(Path(profile_path).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise EnvironmentError(f"could not read hardware profile {profile_path}: {exc}") from exc
            profile = HardwareProfile.from_dict(payload)
        raw_vram = os.environ.get("AIRBENCH_ADMISSION_WORKER_VRAM_BYTES", "").strip()
        worker_vram = int(raw_vram) if raw_vram else None
        return cls(policy_version_hash=policy_hash, hardware_profile=profile, worker_vram_bytes=worker_vram)


def planner_enabled() -> bool:
    return os.environ.get("AIRBENCH_TASK_PLANNER_ENABLED", "").strip().lower() in _ENABLED_VALUES


def declared_measurement(profile: HardwareProfile) -> HardwareMeasurement:
    """A declared (not measured) hardware envelope for the controlled demo.

    Production qualification must replace this with a real probe result; the
    ``measurement_id`` makes the declared origin explicit for audit.
    """
    return HardwareMeasurement(
        measurement_id=f"measurement.{profile.profile_id}.declared",
        profile_id=profile.profile_id,
        measured_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        available_vram_bytes=profile.vram_bytes,
        available_ram_bytes=profile.ram_bytes,
        kv_cache_bytes=profile.kv_cache_bytes,
        model_residency_bytes=(),
        latency_ms=(),
        throughput_tokens_per_second=(),
        sandbox_limits=(),
        max_concurrency=profile.safe_parallel_slots,
        egress_verified=True,
        available_cpu_millicores=profile.cpu_cores * 1000,
        available_context_tokens=profile.model_context_tokens,
        available_scratch_bytes=profile.scratch_bytes,
        available_slots=profile.safe_parallel_slots,
        available_vram_by_gpu=((0, profile.vram_bytes),) if profile.gpu_count == 1 else (),
    )


def _capabilities(task: TaskEnvelope) -> tuple[str, ...]:
    return tuple(sorted(set(task.permitted_worker_capabilities))) or ("reasoning",)


def build_plan_proposal(task: TaskEnvelope) -> PlanProposal:
    """Build the deterministic, sector-neutral plan for an authorized task."""
    capabilities = _capabilities(task)
    evidence = tuple(sorted(set(task.allowed_evidence_scope)))
    tools = tuple(sorted(set(task.permitted_tools)))
    steps: list[PlanStep] = []
    model_step_ids: list[str] = []
    for capability in capabilities:
        step_id = stable_id("plan-step", task.task_id, capability)
        model_step_ids.append(step_id)
        steps.append(PlanStep(
            step_id=step_id, kind="model", required_tools=frozenset(),
            evidence_refs=frozenset(), dependencies=(), timeout_ms=120_000, retry_budget=0,
        ))
    steps.append(PlanStep(
        step_id=stable_id("plan-step", task.task_id, "verification"), kind="verification",
        required_tools=frozenset(), evidence_refs=frozenset(evidence),
        dependencies=tuple(model_step_ids), timeout_ms=120_000, retry_budget=0,
    ))
    return PlanProposal(
        task_id=task.task_id,
        team_id=stable_id("team", task.task_id),
        steps=tuple(steps),
        required_capabilities=frozenset(capabilities),
        tools=frozenset(tools),
        evidence_scope=frozenset(evidence),
        resource_budget={},
        completion_criteria=frozenset(task.verification_criteria) or frozenset(["source_check"]),
    )


class NodeTaskPlanner:
    """Commit a validated plan and (when configured) a hardware admission record."""

    def __init__(self, orchestrator: Orchestrator, config: PlannerConfig) -> None:
        self._orchestrator = orchestrator
        self._config = config
        self._controller = (
            AdmissionController(config.hardware_profile, declared_measurement(config.hardware_profile))
            if config.hardware_profile is not None else None
        )

    @property
    def has_hardware_profile(self) -> bool:
        return self._config.hardware_profile is not None

    def _worker_vram(self) -> int:
        if self._config.worker_vram_bytes is not None:
            return self._config.worker_vram_bytes
        profile = self._config.hardware_profile
        return max(1, profile.vram_bytes // 4) if profile is not None else 0

    def _reservation(self) -> tuple[tuple[str, int], ...]:
        profile = self._config.hardware_profile
        if profile is None:
            raise TaskPlanningError("hardware reservations require a hardware profile")
        share_count = max(1, profile.safe_parallel_slots)
        return (
            ("vram_bytes", self._worker_vram()),
            ("ram_bytes", max(1, profile.ram_bytes // share_count)),
            ("cpu_millicores", max(1, (profile.cpu_cores * 1000) // share_count)),
            ("kv_cache_bytes", max(1, profile.kv_cache_bytes // share_count)),
            ("context_tokens", max(1, profile.model_context_tokens // share_count)),
            ("scratch_bytes", max(1, profile.scratch_bytes // share_count)),
            ("slots", 1),
        )

    def _admission_request(self, task: TaskEnvelope) -> AdmissionRequest:
        capabilities = _capabilities(task)
        capabilities_pairs: list[tuple[str, str]] = []
        roles: list[tuple[str, str]] = []
        reservations: list[tuple[str, tuple[tuple[str, int], ...]]] = []
        for capability in capabilities:
            worker_id = stable_id("worker", task.task_id, capability)
            capabilities_pairs.append((worker_id, capability))
            roles.append((worker_id, f"{capability}_worker"))
            reservations.append((worker_id, self._reservation()))
        verifier_id = stable_id("worker", task.task_id, "verification")
        capabilities_pairs.append((verifier_id, "verification"))
        roles.append((verifier_id, "verification_worker"))
        reservations.append((verifier_id, self._reservation()))
        return AdmissionRequest(
            task_id=task.task_id,
            team_id=stable_id("team", task.task_id),
            worker_capabilities=tuple(capabilities_pairs),
            reservations=tuple(reservations),
            verifier_worker_id=verifier_id,
            worker_roles=tuple(roles),
            requested_mode="auto",
            priority="interactive_normal",
            clearance=task.clearance,
            taint=Taint.clean,
            policy_version_hash=self._config.policy_version_hash,
            plan_version="1",
        )

    def plan_and_admit(self, task: TaskEnvelope) -> None:
        """Commit the plan for an authorized task and record admission if configured."""
        self._orchestrator.commit_proposal(build_plan_proposal(task))
        if self._controller is None:
            return
        decision = self._controller.admit(self._admission_request(task))
        event_type = decision.audit_payload["ledger_event_type"]
        payload = {"plan": decision.plan.to_dict(), **decision.audit_payload}
        self._orchestrator.audit_event(
            task.task_id, event_type, payload, contract="TeamResourcePlan",
            event_key=stable_id("resource-plan", task.task_id, decision.decision_id),
        )


__all__ = [
    "NodeTaskPlanner",
    "PlannerConfig",
    "TaskPlanningError",
    "build_plan_proposal",
    "declared_measurement",
    "planner_enabled",
]
