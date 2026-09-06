"""Append-only event ledger, transition guards, and deterministic replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .errors import ContractValidationError, ValidationIssue
from .ids import idempotency_key, stable_id
from .models import Clearance, LEDGER_EVENT_TYPES, LedgerEventEnvelope


EVENT_TYPES = LEDGER_EVENT_TYPES

TERMINAL_STATES = {"completed", "failed", "cancelled"}
FAILURE_STATES = {"failed", "needs_review", "blocked", "cancelled"}


class LedgerError(RuntimeError):
    """Base error for append, transition, and replay failures."""


class IdempotencyConflict(LedgerError):
    """The same idempotency key was reused for different content."""


class TransitionRejected(LedgerError):
    """An event violates the task state machine preconditions."""


class ReplayRejected(LedgerError):
    """The event chain cannot be safely replayed."""


@dataclass(frozen=True, slots=True)
class ReplayState:
    task_id: str
    state: str
    sequence: int
    event_ids: tuple[str, ...]
    failure_state: str | None = None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _event_hash(event: LedgerEventEnvelope) -> str:
    body = {
        "event_id": event.event_id, "event_type": event.event_type, "task_id": event.task_id,
        "parent_event_id": event.parent_event_id, "sequence": event.sequence,
        "occurred_at": event.occurred_at, "actor_id": event.actor_id, "actor_type": event.actor_type,
        "clearance": event.clearance.value, "payload_contract": event.payload_contract,
        "payload_version": event.payload_version, "payload_hash": event.payload_hash,
        "idempotency_key": event.idempotency_key, "previous_event_hash": event.previous_event_hash,
        "payload": event.payload,
    }
    return _sha256(_canonical(body))


def build_event(*, event_type: str, task_id: str, actor_id: str, actor_type: str,
                payload_contract: str, payload_version: str, payload: dict[str, Any],
                clearance: Clearance | str, idempotency: str, sequence: int = 0,
                previous_event_hash: str | None = None, parent_event_id: str | None = None,
                occurred_at: str = "2026-01-01T00:00:00Z") -> LedgerEventEnvelope:
    """Build one immutable event. ``Ledger.append`` remains the authority to commit it."""
    if event_type not in EVENT_TYPES:
        raise ContractValidationError("LedgerEventEnvelope", [ValidationIssue("event_type", "event", "unknown ledger event type")])
    level = clearance if isinstance(clearance, Clearance) else Clearance(clearance)
    payload_hash = _sha256(_canonical(payload))
    draft = LedgerEventEnvelope(
        event_id=stable_id("event", task_id, sequence, event_type, idempotency),
        event_type=event_type, task_id=task_id, parent_event_id=parent_event_id,
        sequence=sequence, occurred_at=occurred_at, actor_id=actor_id, actor_type=actor_type,
        clearance=level, payload_contract=payload_contract, payload_version=payload_version,
        payload_hash=payload_hash, idempotency_key=idempotency, previous_event_hash=previous_event_hash,
        event_hash="0" * 64, immutable=True, payload=payload,
    )
    return LedgerEventEnvelope.from_dict({**draft.to_dict(), "event_hash": _event_hash(draft)})


class EventLedger:
    """In-memory reference ledger with production-compatible append/replay semantics."""

    def __init__(self) -> None:
        self._events: list[LedgerEventEnvelope] = []
        self._by_idempotency: dict[str, LedgerEventEnvelope] = {}

    @property
    def events(self) -> tuple[LedgerEventEnvelope, ...]:
        return tuple(self._events)

    @property
    def head_hash(self) -> str | None:
        return self._events[-1].event_hash if self._events else None

    def append(self, event: LedgerEventEnvelope) -> LedgerEventEnvelope:
        """Validate and append once; reject chain, transition, and idempotency violations."""
        validated = LedgerEventEnvelope.from_dict(event.to_dict())
        existing = self._by_idempotency.get(validated.idempotency_key)
        if existing is not None:
            if existing.event_hash != validated.event_hash:
                raise IdempotencyConflict(validated.idempotency_key)
            return existing
        expected_sequence = len(self._events)
        if validated.sequence != expected_sequence:
            raise ReplayRejected(f"expected sequence {expected_sequence}, got {validated.sequence}")
        if validated.previous_event_hash != self.head_hash:
            raise ReplayRejected("previous event hash does not match ledger head")
        if validated.event_hash != _event_hash(validated):
            raise ReplayRejected("event hash does not match canonical event content")
        self._check_transition(validated)
        self._events.append(validated)
        self._by_idempotency[validated.idempotency_key] = validated
        return validated

    def _check_transition(self, event: LedgerEventEnvelope) -> None:
        state = self.replay(event.task_id).state if self._events else "absent"
        if event.event_type == "task.created" and state != "absent":
            raise TransitionRejected("task.created requires an absent task")
        if event.event_type != "task.created" and state == "absent":
            raise TransitionRejected(f"{event.event_type} requires task.created")
        if state in TERMINAL_STATES and event.event_type not in {"human.review.required"}:
            raise TransitionRejected("terminal task cannot accept another consequential event")
        if event.event_type == "completion.recorded" and state not in {"verified", "needs_review"}:
            raise TransitionRejected("completion requires verified or review state")
        if event.event_type == "verification.completed" and event.payload.get("status") not in {"passed", "needs_review", "failed"}:
            raise TransitionRejected("verification must declare passed, needs_review, or failed")

    def replay(self, task_id: str) -> ReplayState:
        state = "absent"
        failure: str | None = None
        ids: list[str] = []
        for event in self._events:
            if event.task_id != task_id:
                continue
            ids.append(event.event_id)
            state, failure = _apply_event(state, failure, event)
        return ReplayState(task_id, state, len(ids) - 1, tuple(ids), failure)

    def verify_chain(self) -> None:
        previous: str | None = None
        for sequence, event in enumerate(self._events):
            if event.sequence != sequence or event.previous_event_hash != previous:
                raise ReplayRejected("ledger ordering or parent hash is invalid")
            if event.event_hash != _event_hash(event):
                raise ReplayRejected("ledger event hash is invalid")
            previous = event.event_hash


def _apply_event(state: str, failure: str | None, event: LedgerEventEnvelope) -> tuple[str, str | None]:
    transitions = {
        "task.created": "created", "task.authorized": "authorized", "task.plan.committed": "planned",
        "resource.plan.admitted": "executing", "resource.plan.queued": "queued",
        "worker.started": "executing", "model.requested": "executing", "tool.requested": "executing",
        "verification.completed": {"passed": "verified", "needs_review": "needs_review", "failed": "blocked"},
        "human.review.required": "needs_review", "human.signoff": "verified",
        "completion.recorded": "completed", "task.cancelled": "cancelled", "task.failed": "failed",
        "escalation.required": "needs_review",
    }
    target = transitions.get(event.event_type)
    if isinstance(target, dict):
        target = target.get(event.payload.get("status"), "needs_review")
    if target is not None:
        state = target
    if state in FAILURE_STATES:
        failure = state
    return state, failure
