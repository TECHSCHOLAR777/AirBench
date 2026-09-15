"""Append-only event ledger, transition guards, and deterministic replay."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..errors import ContractValidationError, ValidationIssue
from ..ids import idempotency_key, stable_id
from ..models import Clearance, LEDGER_EVENT_TYPES, LedgerEventEnvelope


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


class ProvenanceRejected(LedgerError):
    """An event carrying governed data has incomplete provenance."""


class StorageFailure(LedgerError):
    """A durable ledger transaction could not be committed."""


@dataclass(frozen=True, slots=True)
class ReplayState:
    task_id: str
    state: str
    sequence: int
    event_ids: tuple[str, ...]
    failure_state: str | None = None


@dataclass(frozen=True, slots=True)
class CommittedTransaction:
    transaction_id: str
    event_ids: tuple[str, ...]
    first_sequence: int
    last_sequence: int
    head_hash: str
    batch_hash: str
    signature: str
    sealed_at: str


@dataclass(frozen=True, slots=True)
class Checkpoint:
    checkpoint_id: str
    task_id: str
    sequence: int
    head_hash: str
    state: str
    transaction_id: str


class LedgerStore(Protocol):
    def append(self, event: LedgerEventEnvelope) -> CommittedTransaction: ...
    def append_batch(self, events: list[LedgerEventEnvelope], transaction_id: str) -> CommittedTransaction: ...
    def replay(self, task_id: str) -> ReplayState: ...


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


def _content_hash(event: LedgerEventEnvelope) -> str:
    """Hash of the logical event content, excluding chain-position fields.

    Two appends of the same logical event (same idempotency key and content)
    may differ in ``sequence``/``previous_event_hash`` when a retry rebuilds
    the envelope after the chain advanced.  Idempotency deduplication must
    compare logical content, not the position-dependent ``event_hash``.
    """
    body = {
        "event_type": event.event_type, "task_id": event.task_id,
        "occurred_at": event.occurred_at, "actor_id": event.actor_id, "actor_type": event.actor_type,
        "clearance": event.clearance.value, "payload_contract": event.payload_contract,
        "payload_version": event.payload_version, "payload_hash": event.payload_hash,
        "idempotency_key": event.idempotency_key, "payload": event.payload,
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
    """In-memory reference ledger with production-compatible append/replay semantics.

    All access is guarded by an internal lock: the runtime executes model
    calls on worker threads that share the process-owned ledger, so appends
    and reads must be serialized to keep the hash chain intact.
    """

    def __init__(self) -> None:
        self._events: list[LedgerEventEnvelope] = []
        self._by_idempotency: dict[str, LedgerEventEnvelope] = {}
        self._lock = threading.RLock()

    @property
    def events(self) -> tuple[LedgerEventEnvelope, ...]:
        with self._lock:
            return tuple(self._events)

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)

    @property
    def head_hash(self) -> str | None:
        with self._lock:
            return self._events[-1].event_hash if self._events else None

    def find_by_idempotency(self, key: str) -> LedgerEventEnvelope | None:
        """O(1) idempotency lookup instead of a full event scan."""
        with self._lock:
            return self._by_idempotency.get(key)

    def _shadow(self) -> EventLedger:
        """Copy-on-write snapshot for validating a batch without mutating."""
        with self._lock:
            shadow = EventLedger()
            shadow._events = list(self._events)
            shadow._by_idempotency = dict(self._by_idempotency)
            return shadow

    def _commit_validated(self, events: list[LedgerEventEnvelope]) -> None:
        with self._lock:
            self._events.extend(events)
            self._by_idempotency.update({event.idempotency_key: event for event in events})

    def append(self, event: LedgerEventEnvelope) -> LedgerEventEnvelope:
        """Validate and append once; reject chain, transition, and idempotency violations."""
        with self._lock:
            validated = LedgerEventEnvelope.from_dict(event.to_dict())
            existing = self._by_idempotency.get(validated.idempotency_key)
            if existing is not None:
                if _content_hash(existing) != _content_hash(validated):
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

    def append_batch(self, events: list[LedgerEventEnvelope]) -> tuple[LedgerEventEnvelope, ...]:
        """Validate a batch against a shadow ledger before mutating this one."""
        if not events:
            raise ValueError("events must not be empty")
        with self._lock:
            keys = [event.idempotency_key for event in events]
            if len(set(keys)) != len(keys):
                raise IdempotencyConflict("batch contains duplicate idempotency keys")
            existing = [self._by_idempotency.get(key) for key in keys]
            if any(item is not None for item in existing):
                if all(item is not None and _content_hash(item) == _content_hash(event) for item, event in zip(existing, events)):
                    return tuple(item for item in existing if item is not None)
                raise IdempotencyConflict("batch mixes already committed and new events")
            shadow = self._shadow()
            validated = list(shadow.append(event) for event in events)
            self._commit_validated(validated)
            return tuple(validated)

    def _check_transition(self, event: LedgerEventEnvelope) -> None:
        state = self.replay(event.task_id).state if self._events else "absent"
        if event.event_type == "task.created" and state != "absent":
            raise TransitionRejected("task.created requires an absent task")
        if event.event_type != "task.created" and state == "absent":
            raise TransitionRejected(f"{event.event_type} requires task.created")
        if state in TERMINAL_STATES and event.event_type not in {"human.review.required", "artifact.previewed", "artifact.downloaded"}:
            raise TransitionRejected("terminal task cannot accept another consequential event")
        if event.event_type == "completion.recorded" and state not in {"verified", "needs_review"}:
            raise TransitionRejected("completion requires verified or review state")
        if event.event_type == "verification.completed" and event.payload.get("status") not in {"passed", "needs_review", "failed"}:
            raise TransitionRejected("verification must declare passed, needs_review, or failed")

    def replay(self, task_id: str) -> ReplayState:
        state = "absent"
        failure: str | None = None
        ids: list[str] = []
        with self._lock:
            events = tuple(self._events)
        for event in events:
            if event.task_id != task_id:
                continue
            ids.append(event.event_id)
            state, failure = _apply_event(state, failure, event)
        return ReplayState(task_id, state, len(ids) - 1, tuple(ids), failure)

    def verify_chain(self) -> None:
        with self._lock:
            events = tuple(self._events)
        previous: str | None = None
        for sequence, event in enumerate(events):
            if event.sequence != sequence or event.previous_event_hash != previous:
                raise ReplayRejected("ledger ordering or parent hash is invalid")
            if event.event_hash != _event_hash(event):
                raise ReplayRejected("ledger event hash is invalid")
            previous = event.event_hash


class SQLiteLedgerStore:
    """Durable append-only ledger adapter.

    SQLite is used as the first local storage implementation; all writes are
    transactional and the public behavior is defined by ``LedgerStore`` rather
    than by SQLite. The signing key is supplied by the deployment key store and
    is never persisted in this database.
    """

    def __init__(self, path: str | Path, signing_key: bytes) -> None:
        if not signing_key:
            raise ValueError("signing_key is required for sealed ledger commits")
        self.path = str(path)
        self._signing_key = bytes(signing_key)
        # The Node's bounded worker runtime executes model calls on a worker
        # thread while sharing the process-owned ledger.  SQLite's default
        # thread affinity would reject those reads/writes even though the
        # Node serializes command mutations at its API boundary.
        self._db = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        # Cached in-memory projection of the durable ledger.  Without it every
        # ``.events`` access re-read, re-validated, and re-hashed the entire
        # table, making each request O(n^2) in ledger size.
        self._cache: EventLedger | None = None
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute("PRAGMA busy_timeout = 30000")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS ledger_events (
                sequence INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE,
                transaction_id TEXT NOT NULL,
                event_json TEXT NOT NULL,
                clearance TEXT NOT NULL
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS ledger_transactions (
                transaction_id TEXT PRIMARY KEY,
                first_sequence INTEGER NOT NULL,
                last_sequence INTEGER NOT NULL,
                head_hash TEXT NOT NULL,
                batch_hash TEXT NOT NULL,
                signature TEXT NOT NULL,
                sealed_at TEXT NOT NULL
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS ledger_checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                head_hash TEXT NOT NULL,
                state TEXT NOT NULL,
                transaction_id TEXT NOT NULL
            )
        """)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _load_ledger(self) -> EventLedger:
        ledger = EventLedger()
        rows = self._db.execute("SELECT event_json FROM ledger_events ORDER BY sequence").fetchall()
        try:
            for row in rows:
                event = LedgerEventEnvelope.from_dict(json.loads(row["event_json"]))
                ledger.append(event)
        except (ContractValidationError, LedgerError) as exc:
            raise ReplayRejected("durable ledger failed validation") from exc
        ledger.verify_chain()
        return ledger

    def _cached_ledger(self) -> EventLedger:
        """Return the cached projection, loading it from SQLite once."""
        with self._lock:
            if self._cache is None:
                self._cache = self._load_ledger()
            return self._cache

    @property
    def events(self) -> tuple[LedgerEventEnvelope, ...]:
        return self._cached_ledger().events

    def __len__(self) -> int:
        return len(self._cached_ledger())

    def find_by_idempotency(self, key: str) -> LedgerEventEnvelope | None:
        return self._cached_ledger().find_by_idempotency(key)

    @property
    def head_hash(self) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT head_hash FROM ledger_transactions ORDER BY last_sequence DESC LIMIT 1").fetchone()
        return row["head_hash"] if row else None

    def append(self, event: LedgerEventEnvelope) -> CommittedTransaction:
        return self.append_batch([event], stable_id("transaction", event.event_id))

    def append_batch(self, events: list[LedgerEventEnvelope], transaction_id: str) -> CommittedTransaction:
        if not events:
            raise ValueError("events must not be empty")
        if not transaction_id:
            raise ValueError("transaction_id is required")
        with self._lock:
            duplicate_transactions: set[str] = set()
            for event in events:
                row = self._db.execute("SELECT transaction_id, event_hash, event_json FROM ledger_events WHERE idempotency_key = ?", (event.idempotency_key,)).fetchone()
                if row is None:
                    continue
                if row["event_hash"] != event.event_hash:
                    # Same logical content under a new chain position is an
                    # idempotent replay, not a conflict.
                    stored = LedgerEventEnvelope.from_dict(json.loads(row["event_json"]))
                    if _content_hash(stored) != _content_hash(event):
                        raise IdempotencyConflict(event.idempotency_key)
                duplicate_transactions.add(row["transaction_id"])
            if duplicate_transactions:
                if len(duplicate_transactions) == 1 and len(duplicate_transactions) == len(events):
                    row = self._db.execute("SELECT * FROM ledger_transactions WHERE transaction_id = ?", (next(iter(duplicate_transactions)),)).fetchone()
                    if row is not None:
                        return CommittedTransaction(row["transaction_id"], tuple(json.loads(self._db.execute("SELECT json_group_array(event_id) FROM ledger_events WHERE transaction_id = ?", (row["transaction_id"],)).fetchone()[0])), row["first_sequence"], row["last_sequence"], row["head_hash"], row["batch_hash"], row["signature"], row["sealed_at"])
                raise IdempotencyConflict("batch mixes already committed and new events")
            current = self._cached_ledger()
            # Validate the batch on a shadow copy; the cached in-memory ledger
            # is only mutated after the durable SQLite commit succeeds so the
            # two can never diverge.
            shadow = current._shadow()
            validated: list[LedgerEventEnvelope] = []
            try:
                for event in events:
                    self._validate_provenance(event)
                    committed = shadow.append(event)
                    validated.append(committed)
            except (ContractValidationError, LedgerError) as exc:
                raise StorageFailure("batch rejected before durable commit") from exc
            payload = _canonical([event.event_hash for event in validated])
            batch_hash = _sha256(payload)
            signature = hmac.new(self._signing_key, batch_hash.encode(), hashlib.sha256).hexdigest()
            sealed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            first_sequence = validated[0].sequence
            last_sequence = validated[-1].sequence
            transaction = CommittedTransaction(transaction_id, tuple(e.event_id for e in validated), first_sequence, last_sequence, validated[-1].event_hash, batch_hash, signature, sealed_at)
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute("INSERT INTO ledger_transactions VALUES (?, ?, ?, ?, ?, ?, ?)", (transaction.transaction_id, transaction.first_sequence, transaction.last_sequence, transaction.head_hash, transaction.batch_hash, transaction.signature, transaction.sealed_at))
                for event in validated:
                    self._db.execute("INSERT INTO ledger_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (event.sequence, event.event_id, event.idempotency_key, event.task_id, event.event_hash, transaction_id, event.canonical_json(), event.clearance.value))
                self._db.commit()
            except sqlite3.Error as exc:
                self._db.rollback()
                raise StorageFailure("ledger transaction rolled back") from exc
            current._commit_validated(validated)
            return transaction

    def _validate_provenance(self, event: LedgerEventEnvelope) -> None:
        governed = {"evidence.created", "fact.candidate", "fact.committed", "tool.result", "verification.completed"}
        if event.event_type not in governed:
            return
        provenance = event.payload.get("provenance")
        if not isinstance(provenance, dict):
            raise ProvenanceRejected(f"{event.event_type} requires provenance")
        required = {"source_ref", "confidence", "clearance", "taint"}
        if not required.issubset(provenance):
            raise ProvenanceRejected(f"{event.event_type} has incomplete provenance")
        if type(provenance["confidence"]) not in (int, float) or not 0 <= provenance["confidence"] <= 1:
            raise ProvenanceRejected("provenance confidence must be between 0 and 1")
        if not provenance["source_ref"] or not provenance["taint"]:
            raise ProvenanceRejected("provenance source and taint are required")

    def checkpoint(self, *, checkpoint_id: str, task_id: str, state: str, transaction_id: str) -> Checkpoint:
        with self._lock:
            row = self._db.execute("SELECT last_sequence, head_hash FROM ledger_transactions WHERE transaction_id = ?", (transaction_id,)).fetchone()
            if row is None:
                raise StorageFailure("checkpoint requires a committed transaction")
            checkpoint = Checkpoint(checkpoint_id, task_id, row["last_sequence"], row["head_hash"], state, transaction_id)
            try:
                self._db.execute("INSERT INTO ledger_checkpoints VALUES (?, ?, ?, ?, ?, ?)", tuple(checkpoint.__dict__.values()) if hasattr(checkpoint, "__dict__") else (checkpoint.checkpoint_id, checkpoint.task_id, checkpoint.sequence, checkpoint.head_hash, checkpoint.state, checkpoint.transaction_id))
                self._db.commit()
            except sqlite3.Error as exc:
                self._db.rollback()
                raise StorageFailure("checkpoint commit failed") from exc
            return checkpoint

    def latest_checkpoint(self, task_id: str) -> Checkpoint | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM ledger_checkpoints WHERE task_id = ? ORDER BY sequence DESC LIMIT 1", (task_id,)).fetchone()
        if row is None:
            return None
        return Checkpoint(row["checkpoint_id"], row["task_id"], row["sequence"], row["head_hash"], row["state"], row["transaction_id"])

    def replay(self, task_id: str) -> ReplayState:
        return self._cached_ledger().replay(task_id)

    def projection(self, clearance: Clearance | str) -> tuple[LedgerEventEnvelope, ...]:
        requested = clearance if isinstance(clearance, Clearance) else Clearance(clearance)
        rank = {Clearance.public: 0, Clearance.internal: 1, Clearance.restricted: 2, Clearance.secret: 3}
        return tuple(event for event in self.events if rank[event.clearance] <= rank[requested])

    def signed_export(self, clearance: Clearance | str) -> dict[str, Any]:
        events = self.projection(clearance)
        export = {"clearance": (clearance.value if isinstance(clearance, Clearance) else clearance), "events": [event.to_dict() for event in events]}
        body_hash = _sha256(_canonical(export))
        export["content_hash"] = body_hash
        export["signature"] = hmac.new(self._signing_key, body_hash.encode(), hashlib.sha256).hexdigest()
        return export


def _apply_event(state: str, failure: str | None, event: LedgerEventEnvelope) -> tuple[str, str | None]:
    transitions = {
        "task.created": "created", "task.authorized": "authorized", "task.plan.committed": "planned",
        "resource.plan.admitted": "executing", "resource.plan.queued": "queued",
        "worker.started": "executing", "model.requested": "executing", "tool.requested": "executing",
        "worker.handoff": "executing", "join_barrier.waiting": "awaiting_check",
        "join_barrier.completed": "executing",
        "join_barrier.resolved": {
            "cancelled": "cancelled", "missing": "needs_review",
            "conflicting": "needs_review", "timed_out": "needs_review",
            "needs_review": "needs_review",
        },
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
