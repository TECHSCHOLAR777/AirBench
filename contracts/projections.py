"""Read-only, rebuildable projections over the authoritative event stream."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol

from .models import Clearance, LedgerEventEnvelope


class EventSource(Protocol):
    @property
    def events(self) -> tuple[LedgerEventEnvelope, ...]: ...

    @property
    def head_hash(self) -> str | None: ...


_LEVEL = {Clearance.public: 0, Clearance.internal: 1, Clearance.restricted: 2, Clearance.secret: 3}
_EVIDENCE_EVENTS = {"evidence.created", "fact.candidate", "fact.committed"}
_ARTIFACT_EVENTS = {"artifact.staged", "artifact.checked"}
_SEARCH_EVENTS = {"evidence.created", "fact.candidate", "fact.committed", "artifact.staged"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value.value if isinstance(value, Clearance) else value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _canonical(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class ProjectionSnapshot:
    projection_id: str
    kind: str
    clearance: Clearance
    source_sequence: int
    source_head_hash: str | None
    event_ids: tuple[str, ...]
    records: tuple[Mapping[str, Any], ...]
    content_hash: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "projection_id": self.projection_id, "kind": self.kind,
            "clearance": self.clearance.value, "source_sequence": self.source_sequence,
            "source_head_hash": self.source_head_hash, "event_ids": list(self.event_ids),
            "records": [_jsonable(record) for record in self.records],
            "content_hash": self.content_hash, "signature": self.signature,
        }


class ProjectionBuilder:
    """Builds disposable read models; it has no write access to the ledger."""

    def __init__(self, source: EventSource, signing_key: bytes) -> None:
        if not signing_key:
            raise ValueError("signing_key is required for signed projection exports")
        self._source = source
        self._signing_key = bytes(signing_key)

    def rebuild(self, kind: str, clearance: Clearance | str) -> ProjectionSnapshot:
        if kind not in {"task", "evidence", "artifact", "search", "audit"}:
            raise ValueError("unknown projection kind")
        level = clearance if isinstance(clearance, Clearance) else Clearance(clearance)
        source_events = self._source.events
        source_head = self._source.head_hash
        events = tuple(event for event in source_events if _LEVEL[event.clearance] <= _LEVEL[level])
        selected = self._select(kind, events)
        records = tuple(_freeze(record) for record in selected)
        event_ids = tuple(event.event_id for event in events if self._selected_event(kind, event))
        body = {"kind": kind, "clearance": level.value, "source_sequence": len(source_events) - 1,
                "source_head_hash": source_head, "event_ids": event_ids,
                "records": records}
        content_hash = hashlib.sha256(_canonical(body).encode()).hexdigest()
        signature = hmac.new(self._signing_key, content_hash.encode(), hashlib.sha256).hexdigest()
        return ProjectionSnapshot(f"projection.{kind}.{content_hash[:16]}", kind, level,
                                  len(source_events) - 1, source_head,
                                  event_ids, records, content_hash, signature)

    def signed_export(self, kind: str, clearance: Clearance | str) -> dict[str, Any]:
        return self.rebuild(kind, clearance).to_dict()

    @staticmethod
    def _selected_event(kind: str, event: LedgerEventEnvelope) -> bool:
        selected: set[str] = set()
        if kind == "evidence":
            selected = _EVIDENCE_EVENTS
        elif kind == "artifact":
            selected = _ARTIFACT_EVENTS
        elif kind == "search":
            selected = _SEARCH_EVENTS
        return kind in {"audit", "task"} or event.event_type in selected

    def _select(self, kind: str, events: Iterable[LedgerEventEnvelope]) -> list[dict[str, Any]]:
        if kind == "task":
            latest: dict[str, dict[str, Any]] = {}
            for event in events:
                latest[event.task_id] = {"task_id": event.task_id, "state_event": event.event_type,
                                         "sequence": event.sequence, "event_id": event.event_id}
            return list(latest.values())
        return [{"event_id": event.event_id, "sequence": event.sequence, "task_id": event.task_id,
                 "event_type": event.event_type, "clearance": event.clearance.value,
                 "payload": event.payload} for event in events if self._selected_event(kind, event)]
