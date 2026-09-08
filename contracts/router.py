"""Deterministic, qualification-first model routing for M5."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping

from .backend import BackendAdapter, BackendHealth, BackendReadiness
from .ids import stable_id
from .model_registry import ModelRegistry, ModelTarget
from .models import ContractStatus, ModelCallRequest, RoutingDecision


class RoutingError(RuntimeError):
    """Base error for an invalid routing configuration or decision."""


class RoutingRejected(RoutingError):
    """No verified, admitted target can serve the request."""


ResourceAdmission = Callable[[ModelTarget, ModelCallRequest], str]


@dataclass(frozen=True, slots=True)
class RouteResult:
    decision: RoutingDecision
    target: ModelTarget | None
    adapter: BackendAdapter | None


class ModelRouter:
    """Select one qualified target and its provider-neutral adapter.

    Registry eligibility is always evaluated before backend health or policy
    priority.  The router never invents qualification and never treats a
    healthy backend as admitted.  Production callers must provide an
    ``resource_admission`` callback backed by the M5.2 resource plan; without
    one, routes remain ``needs_review``.
    """

    def __init__(self, registry: ModelRegistry, adapters: Mapping[str, BackendAdapter], *,
                 policy_version_hash: str, resource_admission: ResourceAdmission | None = None) -> None:
        if not policy_version_hash.strip():
            raise ValueError("policy_version_hash is required")
        self.registry = registry
        self.adapters = dict(adapters)
        self.policy_version_hash = policy_version_hash
        self.resource_admission = resource_admission
        # Sticky escalation is scoped to a task stage.  A new explicit stage
        # gets a fresh route; later turns in the same stage retain the capable
        # target after a failed check.
        self._sticky_routes: dict[tuple[str, str], str] = {}

    def route(self, request: ModelCallRequest, *, pack_ref: str, hardware_profile_ref: str,
              now: datetime | None = None) -> RouteResult:
        candidates = self.registry.eligible_targets(
            request, pack_ref=pack_ref, hardware_profile_ref=hardware_profile_ref, now=now,
        )
        eligible_ids = tuple(target.target_id for target in candidates)
        if not candidates:
            return self._result(
                request, (), None, None, None, "rejected", ContractStatus.rejected,
                "no signed, current target passed the role, capability, modality, risk, clearance, pack, and hardware gates",
                hardware_profile_ref=hardware_profile_ref,
            )

        signals = request.stage_signals
        sticky_key = (request.task_id, request.stage)
        sticky_target_id = self._sticky_routes.get(sticky_key)
        escalation_requested = request.previous_verification_status in {"failed", "needs_review"} or signals.requires_capable_route
        routing_mode = "standard"
        if escalation_requested:
            candidates = tuple(target for target in candidates if target.routing_tier == "capable")
            routing_mode = "capable"
            if not candidates:
                return self._result(
                    request, eligible_ids, None, None, None, "rejected", ContractStatus.rejected,
                    "sticky escalation requires an eligible capable target; refusing silent downgrade to an efficient target",
                    routing_mode=routing_mode, hardware_profile_ref=hardware_profile_ref,
                )
        elif sticky_target_id:
            sticky = next((target for target in candidates if target.target_id == sticky_target_id), None)
            if sticky is not None:
                candidates = (sticky,) + tuple(target for target in candidates if target.target_id != sticky_target_id)
                routing_mode = "escalated_sticky"
        elif signals.is_settled_mechanical:
            candidates = tuple(sorted(candidates, key=lambda target: target.routing_tier != "efficient"))
            routing_mode = "efficient" if candidates and candidates[0].routing_tier == "efficient" else "standard"
        else:
            candidates = tuple(sorted(candidates, key=lambda target: target.routing_tier != "capable"))
            routing_mode = "capable"

        fallback = next((target.target_id for target in candidates[1:] if target.adapter_id in self.adapters), None)
        queued = False
        needs_review = False
        reasons: list[str] = []
        for target in candidates:
            adapter = self.adapters.get(target.adapter_id)
            if adapter is None:
                reasons.append(f"{target.target_id}: adapter {target.adapter_id} is not registered")
                continue
            validate_target = getattr(adapter, "validate_target", None)
            if validate_target is not None:
                try:
                    validate_target(target, request)
                except Exception as exc:
                    reasons.append(f"{target.target_id}: endpoint admission rejected ({exc})")
                    continue
            if adapter.health() != BackendHealth.healthy:
                reasons.append(f"{target.target_id}: backend unhealthy")
                continue
            if adapter.readiness() != BackendReadiness.ready:
                reasons.append(f"{target.target_id}: backend not ready")
                continue
            admission = self.resource_admission(target, request) if self.resource_admission else "needs_review"
            if admission == "admitted":
                sticky = escalation_requested or routing_mode == "escalated_sticky"
                if sticky:
                    self._sticky_routes[sticky_key] = target.target_id
                return self._result(
                    request, eligible_ids, target, adapter, fallback, "admitted", ContractStatus.accepted,
                    "selected first deterministic target passing qualification, backend readiness, and resource admission",
                    routing_mode=routing_mode, escalation_sticky=sticky,
                    hardware_profile_ref=hardware_profile_ref,
                )
            if admission == "queued":
                queued = True
            elif admission == "needs_review":
                needs_review = True
            elif admission != "rejected":
                raise RoutingError(f"resource admission returned invalid state: {admission!r}")
            reasons.append(f"{target.target_id}: resource admission={admission}")

        if queued:
            state, status = "queued", ContractStatus.queued
        elif needs_review:
            state, status = "needs_review", ContractStatus.needs_review
        else:
            state, status = "rejected", ContractStatus.rejected
        return self._result(
            request, eligible_ids, None, None, fallback, state, status,
            "; ".join(reasons) or "no eligible backend adapter is available",
            routing_mode=routing_mode, hardware_profile_ref=hardware_profile_ref,
        )

    def _result(self, request: ModelCallRequest, eligible_ids: tuple[str, ...], target: ModelTarget | None,
                adapter: BackendAdapter | None, fallback: str | None, admission: str,
                status: ContractStatus, reason: str, *, routing_mode: str = "standard",
                escalation_sticky: bool = False, hardware_profile_ref: str = "") -> RouteResult:
        decision = RoutingDecision.from_dict({
            "decision_id": stable_id(
                "routing-decision", request.request_id, self.policy_version_hash,
                status.value, target.target_id if target else "", admission,
            ),
            "request_id": request.request_id,
            "eligible_targets": list(eligible_ids),
            "selected_target": target.target_id if target else None,
            "policy_version_hash": self.policy_version_hash,
            "decision_source": "deterministic_registry_and_backend_router",
            "rule_or_threshold": "qualification_then_health_readiness_then_resource_admission",
            "qualification_certificate": target.qualification_certificate_for(request.role) if target else "",
            "session_affinity": request.task_id,
            "fallback_target": fallback,
            "resource_admission": admission,
            "status": status.value,
            "reason": reason,
            "stage": request.stage,
            "stage_signals": request.stage_signals.to_dict(),
            "routing_mode": routing_mode,
            "escalation_sticky": escalation_sticky,
            "attempt": request.attempt,
            "task_id": request.task_id,
            "team_id": request.team_id or "",
            "worker_id": request.worker_id or "",
            "resource_lease_id": request.resource_lease_id,
            "hardware_profile_ref": hardware_profile_ref,
            "selected_artifact_digest": target.artifact_digest if target else "",
        })
        return RouteResult(decision, target, adapter)


__all__ = ["ModelRouter", "ResourceAdmission", "RouteResult", "RoutingError", "RoutingRejected"]
