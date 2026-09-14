"""Durable decision history for the Consistency Engine.

The engine compares a forming decision against past decisions about the same
object: plain text similarity is not enough, so decisions are stored as typed
feature vectors keyed by object identity and decision type.  This store is
stdlib-only, local, and offline, and it supersedes a prior decision about the
same object and type when a newer one is recorded.
"""

from __future__ import annotations

import json
import os
import sqlite3
from threading import RLock
from pathlib import Path
from typing import Sequence

from .consistency import DecisionRecord


class DecisionStoreError(RuntimeError):
    """The decision store could not be opened or used."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _encode_features(features: Sequence[tuple[str, str]]) -> str:
    return json.dumps({key: value for key, value in features}, sort_keys=True, separators=(",", ":"))


def _decode_features(payload: str) -> tuple[tuple[str, str], ...]:
    data = json.loads(payload)
    return tuple(sorted((str(key), str(value)) for key, value in data.items()))


class SqliteDecisionStore:
    """Local SQLite decision history with object/type comparability lookups."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        try:
            self._connection = sqlite3.connect(str(self._path), check_same_thread=False, timeout=30.0)
        except sqlite3.Error as exc:
            raise DecisionStoreError("store_open_failed", "the decision store could not be opened") from exc
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS decisions ("
            "decision_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, decision_type TEXT NOT NULL, "
            "object_id TEXT NOT NULL, features TEXT NOT NULL, decision TEXT NOT NULL, rule_ref TEXT NOT NULL, "
            "authority TEXT NOT NULL, current INTEGER NOT NULL, outcome TEXT, "
            "rule_current INTEGER NOT NULL, authority_current INTEGER NOT NULL)"
        )
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._connection.close()
            except sqlite3.Error:
                pass

    def record(self, record: DecisionRecord, *, supersede_existing: bool = True) -> str:
        """Persist one decision, optionally superseding prior ones for the object."""
        with self._lock:
            try:
                cursor = self._connection.cursor()
                if supersede_existing:
                    cursor.execute(
                        "UPDATE decisions SET current = 0 WHERE decision_type = ? AND object_id = ? AND current = 1",
                        (record.decision_type, record.object_id),
                    )
                cursor.execute(
                    "INSERT OR REPLACE INTO decisions "
                    "(decision_id, task_id, decision_type, object_id, features, decision, rule_ref, authority, "
                    " current, outcome, rule_current, authority_current) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.decision_id, record.task_id, record.decision_type, record.object_id,
                        _encode_features(record.features), record.decision, record.rule_ref, record.authority,
                        1 if record.current else 0, record.outcome,
                        1 if record.rule_current else 0, 1 if record.authority_current else 0,
                    ),
                )
                self._connection.commit()
            except sqlite3.Error as exc:
                self._connection.rollback()
                raise DecisionStoreError("store_write_failed", "the decision could not be recorded") from exc
        return record.decision_id

    def find_comparable(self, decision_type: str, object_id: str, *, limit: int = 100) -> tuple[DecisionRecord, ...]:
        if not decision_type or not object_id or limit < 1:
            raise DecisionStoreError("invalid_query", "a comparable lookup requires a type, object, and limit")
        with self._lock:
            rows = self._connection.execute(
                "SELECT decision_id, task_id, decision_type, object_id, features, decision, rule_ref, authority, "
                "current, outcome, rule_current, authority_current FROM decisions "
                "WHERE decision_type = ? AND object_id = ? ORDER BY current DESC, decision_id LIMIT ?",
                (decision_type, object_id, limit),
            ).fetchall()
            return tuple(self._row_to_record(row) for row in rows)

    def list_records(self) -> tuple[DecisionRecord, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT decision_id, task_id, decision_type, object_id, features, decision, rule_ref, authority, "
                "current, outcome, rule_current, authority_current FROM decisions ORDER BY decision_id"
            ).fetchall()
            return tuple(self._row_to_record(row) for row in rows)

    @property
    def count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) FROM decisions").fetchone()
            return int(row[0]) if row else 0

    @staticmethod
    def _row_to_record(row: Sequence[object]) -> DecisionRecord:
        return DecisionRecord(
            decision_id=str(row[0]), task_id=str(row[1]), decision_type=str(row[2]), object_id=str(row[3]),
            features=_decode_features(str(row[4])), decision=str(row[5]), rule_ref=str(row[6]),
            authority=str(row[7]), current=bool(row[8]), outcome=str(row[9]) if row[9] is not None else None,
            rule_current=bool(row[10]), authority_current=bool(row[11]),
        )


def build_decision_store_from_env(env: dict[str, str] | None = None) -> SqliteDecisionStore | None:
    """Build the decision store when ``AIRBENCH_DECISION_STORE_PATH`` is set."""

    values = os.environ if env is None else env
    path = values.get("AIRBENCH_DECISION_STORE_PATH", "").strip()
    if not path:
        return None
    return SqliteDecisionStore(path)


__all__ = ["DecisionStoreError", "SqliteDecisionStore", "build_decision_store_from_env"]
