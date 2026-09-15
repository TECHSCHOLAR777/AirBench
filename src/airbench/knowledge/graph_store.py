"""Durable, append-only storage for the World Model graph.

The core owns graph reconciliation and query semantics; this module owns
durability.  ``SqliteGraphStore`` persists committed facts and relations in a
local SQLite file and records an append-only ``fact_history`` row whenever a
fact is first seen or changes, so the graph's own history is reconstructable.

It is stdlib-only and offline.  The JSON seam remains the default; a deployment
opts into SQLite with ``AIRBENCH_WORLD_MODEL_BACKEND=sqlite``.
"""

from __future__ import annotations

import json
import os
import sqlite3
from threading import RLock
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from .world_model import FactEnvelope, WorldModelError, WorldModelRelation

_WORLD_MODEL_BACKEND_ENV = "AIRBENCH_WORLD_MODEL_BACKEND"
_WORLD_MODEL_PATH_ENV = "AIRBENCH_WORLD_MODEL_PATH"


def _rank(clearance) -> int:
    from contracts import Clearance

    return {
        Clearance.public: 0, Clearance.internal: 1, Clearance.restricted: 2, Clearance.secret: 3,
    }[clearance]


def _relation_dict(relation: WorldModelRelation) -> dict[str, Any]:
    return {
        "relation_id": relation.relation_id, "source_fact_id": relation.source_fact_id,
        "relation": relation.relation, "target_fact_id": relation.target_fact_id,
        "source_ref": relation.source_ref, "confidence": relation.confidence,
        "clearance": relation.clearance.value, "taint": relation.taint.value,
        "valid_from": relation.valid_from, "valid_to": relation.valid_to,
    }


class SqliteGraphStore:
    """Local SQLite persistence for committed world-model facts and relations."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        try:
            self._connection = sqlite3.connect(str(self._path), check_same_thread=False, timeout=30.0)
        except sqlite3.Error as exc:
            raise WorldModelError("storage_failed", "the world model store could not be opened") from exc
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS nodes ("
            "fact_id TEXT PRIMARY KEY, clearance_rank INTEGER NOT NULL, supersedes_fact_id TEXT, "
            "payload_hash TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS edges ("
            "relation_id TEXT PRIMARY KEY, source_fact_id TEXT NOT NULL, target_fact_id TEXT NOT NULL, "
            "relation TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS fact_history ("
            "sequence INTEGER PRIMARY KEY AUTOINCREMENT, fact_id TEXT NOT NULL, "
            "payload_hash TEXT NOT NULL, payload TEXT NOT NULL, recorded_at TEXT NOT NULL)"
        )
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._connection.close()
            except sqlite3.Error:
                pass

    def load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with self._lock:
            facts = [json.loads(row[0]) for row in self._connection.execute("SELECT payload FROM nodes")]
            relations = [json.loads(row[0]) for row in self._connection.execute("SELECT payload FROM edges")]
            return facts, relations

    def save(self, facts: Sequence[FactEnvelope], relations: Sequence[WorldModelRelation]) -> None:
        recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        fact_payloads = [fact.to_dict() for fact in facts]
        relation_payloads = [_relation_dict(relation) for relation in relations]
        with self._lock:
            try:
                cursor = self._connection.cursor()
                for fact, payload in zip(facts, fact_payloads):
                    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
                    previous = cursor.execute("SELECT payload_hash FROM nodes WHERE fact_id = ?", (fact.fact_id,)).fetchone()
                    payload_hash = sha256(encoded.encode("utf-8")).hexdigest()
                    if previous is not None and previous[0] == payload_hash:
                        continue
                    cursor.execute(
                        "INSERT OR REPLACE INTO nodes (fact_id, clearance_rank, supersedes_fact_id, payload_hash, payload) VALUES (?, ?, ?, ?, ?)",
                        (fact.fact_id, _rank(fact.clearance), fact.supersedes_fact_id, payload_hash, encoded),
                    )
                    cursor.execute(
                        "INSERT INTO fact_history (fact_id, payload_hash, payload, recorded_at) VALUES (?, ?, ?, ?)",
                        (fact.fact_id, payload_hash, encoded, recorded_at),
                    )
                for relation, payload in zip(relations, relation_payloads):
                    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
                    cursor.execute(
                        "INSERT OR REPLACE INTO edges (relation_id, source_fact_id, target_fact_id, relation, payload) VALUES (?, ?, ?, ?, ?)",
                        (relation.relation_id, relation.source_fact_id, relation.target_fact_id, relation.relation, encoded),
                    )
                self._connection.commit()
            except sqlite3.Error as exc:
                self._connection.rollback()
                raise WorldModelError("storage_failed", "the world model store could not be written") from exc

    def history(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT sequence, fact_id, payload_hash, recorded_at FROM fact_history ORDER BY sequence"
            ).fetchall()
            return tuple({
                "sequence": row[0], "fact_id": row[1], "payload_hash": row[2], "recorded_at": row[3],
            } for row in rows)

    @property
    def node_count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) FROM nodes").fetchone()
            return int(row[0]) if row else 0

    @property
    def edge_count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) FROM edges").fetchone()
            return int(row[0]) if row else 0


def build_graph_store_from_env(
    env: dict[str, str] | None = None,
    *,
    default_path: str | Path | None = None,
) -> SqliteGraphStore | None:
    """Build the configured durable graph store, or ``None`` for the JSON seam."""

    values = os.environ if env is None else env
    selected = values.get(_WORLD_MODEL_BACKEND_ENV, "json").strip().lower() or "json"
    if selected in {"json", "none", "memory"}:
        return None
    if selected != "sqlite":
        raise WorldModelError("unknown_store", "AIRBENCH_WORLD_MODEL_BACKEND must be json or sqlite")
    path = values.get(_WORLD_MODEL_PATH_ENV, "").strip() or (str(default_path) if default_path else "")
    if not path:
        raise WorldModelError("store_path_required", "AIRBENCH_WORLD_MODEL_PATH is required for the SQLite graph store")
    return SqliteGraphStore(path)


__all__ = ["SqliteGraphStore", "build_graph_store_from_env"]
