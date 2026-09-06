"""Durable idempotency and restart recovery services for consequential actions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .ledger import Checkpoint, ReplayRejected, SQLiteLedgerStore, StorageFailure


class SideEffectUncertain(StorageFailure):
    """The previous attempt may have executed; retrying is prohibited."""


@dataclass(frozen=True, slots=True)
class RetryRecord:
    retry_id: str
    task_id: str
    action_id: str
    attempt: int
    status: str
    error_code: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class RecoveryPoint:
    checkpoint: Checkpoint | None
    replay_sequence: int
    replay_state: str
    resumed_from_sequence: int


class RecoveryManager:
    """Uses the same local DB as the ledger and fails closed on ambiguity."""

    def __init__(self, store: SQLiteLedgerStore) -> None:
        self.store = store
        self._db = store._db
        self._db.execute("""CREATE TABLE IF NOT EXISTS ledger_retries (
            retry_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, action_id TEXT NOT NULL,
            attempt INTEGER NOT NULL, status TEXT NOT NULL, error_code TEXT,
            created_at TEXT NOT NULL)""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS ledger_side_effects (
            idempotency_key TEXT PRIMARY KEY, task_id TEXT NOT NULL, action_id TEXT NOT NULL,
            status TEXT NOT NULL, result_json TEXT, result_hash TEXT)""")
        self._db.commit()

    def record_retry(self, *, retry_id: str, task_id: str, action_id: str,
                     attempt: int, status: str, error_code: str | None = None) -> RetryRecord:
        if attempt < 1 or status not in {"started", "completed", "failed", "cancelled"}:
            raise ValueError("invalid retry record")
        record = RetryRecord(retry_id, task_id, action_id, attempt, status, error_code,
                             datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        try:
            self._db.execute("INSERT INTO ledger_retries VALUES (?, ?, ?, ?, ?, ?, ?)", tuple(record.__dict__.values()) if hasattr(record, "__dict__") else (record.retry_id, record.task_id, record.action_id, record.attempt, record.status, record.error_code, record.created_at))
            self._db.commit()
        except sqlite3.IntegrityError as exc:
            raise StorageFailure("retry record already exists") from exc
        return record

    def retries(self, task_id: str) -> tuple[RetryRecord, ...]:
        rows = self._db.execute("SELECT * FROM ledger_retries WHERE task_id = ? ORDER BY created_at", (task_id,)).fetchall()
        return tuple(RetryRecord(row["retry_id"], row["task_id"], row["action_id"], row["attempt"], row["status"], row["error_code"], row["created_at"]) for row in rows)

    def recover(self, task_id: str) -> RecoveryPoint:
        checkpoint = self.store.latest_checkpoint(task_id)
        events = self.store.events
        if checkpoint is not None:
            if checkpoint.sequence >= len(events) or events[checkpoint.sequence].event_hash != checkpoint.head_hash:
                raise ReplayRejected("checkpoint does not match committed event chain")
        replay = self.store.replay(task_id)
        return RecoveryPoint(checkpoint, replay.sequence, replay.state,
                             checkpoint.sequence + 1 if checkpoint else 0)

    def reserve_side_effect(self, *, idempotency_key: str, task_id: str, action_id: str) -> None:
        try:
            self._db.execute("INSERT INTO ledger_side_effects VALUES (?, ?, ?, 'started', NULL, NULL)", (idempotency_key, task_id, action_id))
            self._db.commit()
        except sqlite3.IntegrityError:
            row = self._db.execute("SELECT task_id, action_id, status FROM ledger_side_effects WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if row and (row["task_id"], row["action_id"]) != (task_id, action_id):
                raise StorageFailure("idempotency key is bound to a different action")
            if row and row["status"] == "completed":
                return
            raise SideEffectUncertain("side effect has an unfinished prior reservation")

    def complete_side_effect(self, idempotency_key: str, result: Any) -> Any:
        result_json = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        result_hash = hashlib.sha256(result_json.encode()).hexdigest()
        cursor = self._db.execute("UPDATE ledger_side_effects SET status='completed', result_json=?, result_hash=? WHERE idempotency_key=? AND status='started'", (result_json, result_hash, idempotency_key))
        if cursor.rowcount != 1:
            raise SideEffectUncertain("side effect was not reserved by this attempt")
        self._db.commit()
        return result

    def run_once(self, *, idempotency_key: str, task_id: str, action_id: str,
                 effect: Callable[[], Any]) -> Any:
        row = self._db.execute("SELECT status, result_json FROM ledger_side_effects WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        if row and row["status"] == "completed":
            return json.loads(row["result_json"])
        self.reserve_side_effect(idempotency_key=idempotency_key, task_id=task_id, action_id=action_id)
        try:
            result = effect()
        except Exception as exc:
            raise StorageFailure("side effect failed; reservation retained for explicit recovery") from exc
        return self.complete_side_effect(idempotency_key, result)

    def mark_uncertain(self, idempotency_key: str) -> None:
        cursor = self._db.execute("UPDATE ledger_side_effects SET status='uncertain' WHERE idempotency_key=? AND status='started'", (idempotency_key,))
        if cursor.rowcount != 1:
            raise SideEffectUncertain("no active side-effect reservation")
        self._db.commit()
