"""Node-owned autonomy scoring and human authorization.

The Autonomy Governor owns the deterministic decision.  This service scopes it
per task, keeps the escalation hold, exposes the decision records, and records
an operator authorization on the ledger when a human unblocks an escalation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from contracts import Clearance, EventLedger, Taint, build_event, idempotency_key

from ..verification.autonomy import ActionProposal, AuthorityDecision, AutonomyGovernor


class AutonomyServiceError(RuntimeError):
    """A task-scoped autonomy operation was rejected safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _rank(clearance: Clearance) -> int:
    return {Clearance.public: 0, Clearance.internal: 1, Clearance.restricted: 2, Clearance.secret: 3}[clearance]


def select_execution_action_kind(risk_mappings: Any, override: str = "") -> str:
    """Pick the pack-declared action kind that gates task execution.

    The core must not hardcode a sector action name.  When the operator does not
    pin one, the most consequential declared action (the first non-reversible
    mapping) is used; if no mappings exist, a neutral default is returned so the
    governor still fails closed on an unmapped action.
    """
    if override and override.strip():
        return override.strip()
    mappings = tuple(risk_mappings or ())
    if not mappings:
        return "task_execution"
    non_reversible = [
        mapping for mapping in mappings
        if str(getattr(mapping, "reversibility", "")).strip().lower() not in {"reversible", "yes", "true"}
    ]
    chosen = (non_reversible or list(mappings))[0]
    return str(getattr(chosen, "action_kind", "") or "task_execution")


def _decision_wire(decision: AuthorityDecision) -> dict[str, Any]:
    return {
        "task_id": decision.task_id,
        "action_id": decision.action_id,
        "outcome": decision.outcome,
        "required_authority": decision.required_authority,
        "required_checks": list(decision.required_checks),
        "reason": decision.reason,
        "ledger_event_id": decision.ledger_event_id,
    }


class LocalNodeAutonomyService:
    """Task-scoped autonomy decisions with an escalation hold and authorization."""

    def __init__(
        self,
        *,
        governor: AutonomyGovernor,
        ledger: EventLedger,
        clearance_context: Clearance,
        world_model: Any = None,
    ) -> None:
        self._governor = governor
        self._ledger = ledger
        self._clearance = clearance_context
        self._world_model = world_model
        self._holds: dict[str, dict[str, Any]] = {}

    def score(
        self,
        *,
        task_id: str,
        action_id: str,
        action_kind: str,
        source_ref: str,
        confidence: float,
        clearance: Clearance | None = None,
        taint: Taint = Taint.untrusted,
        worker_id: str = "node.execution",
        claimed_risk: str | None = None,
        target_object_id: str = "",
    ) -> dict[str, Any]:
        if not task_id or not action_id or not action_kind or not source_ref:
            raise AutonomyServiceError("invalid_action", "autonomy scoring requires an action identity and source")
        level = clearance or self._clearance
        if _rank(level) > _rank(self._clearance):
            raise AutonomyServiceError("clearance_exceeded", "the action clearance exceeds this Node context")
        decision = self._governor.score(
            ActionProposal(
                task_id=task_id, action_id=action_id, action_kind=action_kind, worker_id=worker_id,
                source_ref=source_ref, confidence=confidence, clearance=level, taint=taint,
                claimed_risk=claimed_risk, target_object_id=target_object_id,
            ),
            world_model=self._world_model,
        )
        wire = _decision_wire(decision)
        if decision.outcome == "allow":
            self._holds.pop(task_id, None)
        else:
            self._holds[task_id] = wire
        return wire

    def decisions(self, task_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "action_id": event.payload.get("action_id"),
                "action_kind": event.payload.get("action_kind"),
                "outcome": event.payload.get("outcome"),
                "required_authority": event.payload.get("required_authority"),
                "required_checks": list(event.payload.get("required_checks", [])),
                "reason": event.payload.get("reason"),
                "ledger_event_ref": event.event_id,
            }
            for event in self._ledger.events
            if event.task_id == task_id and event.event_type in {"authority.decided", "escalation.required"}
        )

    def is_blocked(self, task_id: str) -> bool:
        return task_id in self._holds

    def is_authorized(self, task_id: str, action_id: str = "") -> bool:
        """Whether an operator has authorized this task's escalated action.

        The operator's plan approval records an ``authority.authorized`` event
        for the gated execution action. Execution may proceed only when that
        authorization exists; the governor still records the escalation.
        """
        target = action_id or (self._holds.get(task_id) or {}).get("action_id") or ""
        if not target:
            return False
        return any(
            event.task_id == task_id
            and event.event_type == "authority.authorized"
            and isinstance(event.payload, dict)
            and event.payload.get("action_id") == target
            for event in self._ledger.events
        )

    def clear(self, task_id: str) -> None:
        """Drop a resolved escalation hold without recording a new decision."""
        self._holds.pop(task_id, None)

    def authorize(self, *, task_id: str, operator_id: str, action_id: str = "", operator_roles: tuple[str, ...] = ()) -> dict[str, Any]:
        hold = self._holds.get(task_id)
        if hold is None:
            raise AutonomyServiceError("no_escalation", "there is no autonomy escalation to authorize")
        if not operator_id.strip():
            raise AutonomyServiceError("invalid_operator", "an operator identity is required to authorize")
        if hold.get("required_authority") and hold["required_authority"] not in operator_roles:
            raise AutonomyServiceError("insufficient_authority", f"the operator lacks the required role {hold['required_authority']}")
        self._ledger.append(build_event(
            event_type="authority.authorized", task_id=task_id, actor_id=operator_id, actor_type="operator",
            payload_contract="AuthorityAuthorization", payload_version="1.0",
            payload={
                "task_id": task_id,
                "action_id": action_id or hold.get("action_id"),
                "operator_id": operator_id,
                "escalation_event_ref": hold.get("ledger_event_id"),
                "reason": hold.get("reason"),
                "provenance": {
                    "source_ref": f"autonomy:{action_id or hold.get('action_id')}", "confidence": 1.0,
                    "clearance": self._clearance.value, "taint": Taint.clean.value,
                },
            },
            clearance=self._clearance,
            idempotency=idempotency_key("authority.authorized", task_id, operator_id, action_id or str(hold.get("action_id"))),
            sequence=len(self._ledger.events), previous_event_hash=self._ledger.head_hash,
        ))
        self._holds.pop(task_id, None)
        return {"task_id": task_id, "authorized": True, "action_id": action_id or hold.get("action_id")}


__all__ = ["AutonomyServiceError", "LocalNodeAutonomyService", "select_execution_action_kind"]
