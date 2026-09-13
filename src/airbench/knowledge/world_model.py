"""Clearance-filtered World Model queries and gated candidate writes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from contracts import Clearance, EventLedger, FactEnvelope, Taint, build_event, stable_id


def _rank(clearance: Clearance) -> int:
    return {
        Clearance.public: 0,
        Clearance.internal: 1,
        Clearance.restricted: 2,
        Clearance.secret: 3,
    }[clearance]


class WorldModelError(RuntimeError):
    """A stable candidate or query failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class WorldModelRelation:
    """A provenance-bearing edge between committed fact identities."""

    relation_id: str
    source_fact_id: str
    relation: str
    target_fact_id: str
    source_ref: str
    confidence: float
    clearance: Clearance
    taint: Taint
    valid_from: str | None = None
    valid_to: str | None = None

    def __post_init__(self) -> None:
        if not self.relation_id or not self.source_fact_id or not self.target_fact_id or not self.relation or not self.source_ref:
            raise WorldModelError("invalid_relation", "relation identity and provenance are required")
        if not 0 <= self.confidence <= 1:
            raise WorldModelError("invalid_confidence", "relation confidence must be between zero and one")
        if self.taint == Taint.clean:
            raise WorldModelError("clean_relation", "world model relations must remain untrusted")


@dataclass(frozen=True, slots=True)
class WorldModelQuery:
    task_id: str
    key: str = ""
    clearance: Clearance = Clearance.internal
    limit: int = 50
    entity_id: str = ""
    relation: str = ""
    max_depth: int = 1

    def __post_init__(self) -> None:
        if not self.task_id or self.limit < 1 or self.limit > 1_000 or len(self.key) > 256:
            raise WorldModelError("invalid_query", "world model query identity or limit is invalid")
        if len(self.relation) > 128 or self.max_depth < 0 or self.max_depth > 5:
            raise WorldModelError("invalid_query", "world model relation query is outside the allowed bounds")


@dataclass(frozen=True, slots=True)
class CandidateFact:
    candidate_id: str
    task_id: str
    fact: FactEnvelope
    provenance_refs: tuple[str, ...]
    consistency_reference: str
    verification_reference: str
    relations: tuple[WorldModelRelation, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.task_id or self.fact.taint == Taint.clean:
            raise WorldModelError("invalid_candidate", "candidate identity and untrusted provenance are required")
        if not self.provenance_refs or not self.consistency_reference or not self.verification_reference:
            raise WorldModelError("missing_gates", "candidate provenance and gate references are required")
        if any(relation.taint == Taint.clean for relation in self.relations):
            raise WorldModelError("clean_relation", "candidate relations must remain untrusted")


Gate = Callable[[CandidateFact], bool]


@dataclass(frozen=True, slots=True)
class ReviewItem:
    """A low-confidence or ambiguous candidate awaiting a human decision."""

    candidate: CandidateFact
    reason: str
    enqueued_at: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise WorldModelError("invalid_review", "a review item requires a reason")


class GraphStore(Protocol):
    """Pluggable durable persistence behind :class:`WorldModelStore`.

    A backend only stores and returns serialised committed facts and relations;
    reconciliation, visibility, clearance filtering, and traversal stay in the
    core.  ``SqliteGraphStore`` provides an append-only local implementation.
    """

    def load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]: ...

    def save(self, facts: Sequence[FactEnvelope], relations: Sequence["WorldModelRelation"]) -> None: ...


class WorldModelStore:
    """Committed-fact store with optional bounded JSON persistence."""

    def __init__(self, *, ledger: EventLedger | None = None, path: str | Path | None = None,
                 max_file_bytes: int = 50_000_000, backend: GraphStore | None = None) -> None:
        if max_file_bytes < 1:
            raise WorldModelError("invalid_storage_limit", "world model storage limit must be positive")
        self._facts: dict[str, FactEnvelope] = {}
        self._relations: dict[str, WorldModelRelation] = {}
        self._ledger = ledger
        self._backend = backend
        self._path = Path(path) if (path is not None and backend is None) else None
        self._max_file_bytes = max_file_bytes
        self._review: dict[str, ReviewItem] = {}
        self._load()

    @property
    def facts(self) -> tuple[FactEnvelope, ...]:
        return tuple(self._facts.values())

    @property
    def relations(self) -> tuple[WorldModelRelation, ...]:
        return tuple(self._relations.values())

    @property
    def review_queue(self) -> tuple[ReviewItem, ...]:
        return tuple(self._review.values())

    def enqueue_review(self, candidate: CandidateFact, reason: str) -> ReviewItem:
        """Stage a candidate for human review instead of committing it."""
        item = ReviewItem(candidate, reason, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        self._review[candidate.candidate_id] = item
        self._emit("world_model.review_required", candidate.task_id, candidate.fact.clearance, {
            "candidate_id": candidate.candidate_id, "fact_id": candidate.fact.fact_id, "reason": reason,
        })
        return item

    def resolve_review(self, candidate_id: str, *, accept: bool) -> FactEnvelope | None:
        """Accept a queued candidate into the graph, or tombstone it by rejection."""
        item = self._review.pop(candidate_id, None)
        if item is None:
            raise WorldModelError("review_missing", "review item is not queued")
        self._emit("world_model.review_resolved", item.candidate.task_id, item.candidate.fact.clearance, {
            "candidate_id": candidate_id, "decision": "accept" if accept else "reject",
        })
        if not accept:
            return None
        self._commit(item.candidate.fact, item.candidate.relations)
        return item.candidate.fact

    def _emit(self, event_type: str, task_id: str, clearance: Clearance, payload: dict[str, str]) -> None:
        if self._ledger is None:
            return
        sequence = len(self._ledger.events)
        self._ledger.append(build_event(
            event_type=event_type,
            task_id=task_id,
            actor_id="world-model",
            actor_type="world_model",
            payload_contract="WorldModelOperation",
            payload_version="1.0",
            payload={"task_id": task_id, "clearance": clearance.value, **payload},
            clearance=clearance,
            idempotency=stable_id("world-model", event_type, task_id, sequence),
            sequence=sequence,
            previous_event_hash=self._ledger.head_hash,
            occurred_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        ))

    def query(self, request: WorldModelQuery) -> tuple[FactEnvelope, ...]:
        self._event("world_model.requested", request, {
            "key_hash": hashlib.sha256(request.key.encode("utf-8")).hexdigest(),
            "limit": str(request.limit),
        })
        visible = self._visible_facts()
        matches = [
            fact for fact in visible.values()
            if _rank(fact.clearance) <= _rank(request.clearance) and self._matches_key(fact, request.key)
        ]
        if request.entity_id:
            matches = self._traverse(request, visible)
        matches.sort(key=lambda fact: fact.fact_id)
        return tuple(matches[:request.limit])

    def _commit(self, fact: FactEnvelope, relations: tuple[WorldModelRelation, ...] = ()) -> None:
        self._validate_commit(fact, relations)
        existing = self._facts.get(fact.fact_id)
        if existing is not None and existing != fact:
            raise WorldModelError("fact_conflict", "fact identity was reused for different content")
        for relation in relations:
            previous = self._relations.get(relation.relation_id)
            if previous is not None and previous != relation:
                raise WorldModelError("relation_conflict", "relation identity was reused for different content")
        self._facts[fact.fact_id] = fact
        for relation in relations:
            self._relations[relation.relation_id] = relation
        self._persist()

    def _validate_commit(self, fact: FactEnvelope, relations: tuple[WorldModelRelation, ...] = ()) -> None:
        """Reject a bounded-storage commit before its ledger event is written."""
        if self._path is None:
            return
        encoded = json.dumps(
            {
                "facts": [*([item.to_dict() for item in self._facts.values()]), fact.to_dict()],
                "relations": [
                    *[
                        {"relation_id": item.relation_id, "source_fact_id": item.source_fact_id,
                         "relation": item.relation, "target_fact_id": item.target_fact_id,
                         "source_ref": item.source_ref, "confidence": item.confidence,
                         "clearance": item.clearance.value, "taint": item.taint.value,
                         "valid_from": item.valid_from, "valid_to": item.valid_to}
                        for item in self._relations.values()
                    ],
                    *[
                        {"relation_id": item.relation_id, "source_fact_id": item.source_fact_id,
                         "relation": item.relation, "target_fact_id": item.target_fact_id,
                         "source_ref": item.source_ref, "confidence": item.confidence,
                         "clearance": item.clearance.value, "taint": item.taint.value,
                         "valid_from": item.valid_from, "valid_to": item.valid_to}
                        for item in relations
                    ],
                ],
            },
            sort_keys=True, separators=(",", ":"), default=str,
        ).encode("utf-8")
        if len(encoded) > self._max_file_bytes:
            raise WorldModelError("storage_limit", "world model file exceeds the configured limit")

    def _visible_facts(self) -> dict[str, FactEnvelope]:
        superseded = {
            fact.supersedes_fact_id for fact in self._facts.values()
            if fact.supersedes_fact_id
        }
        return {
            fact_id: fact for fact_id, fact in self._facts.items()
            if fact_id not in superseded
        }

    def _traverse(self, request: WorldModelQuery, visible: dict[str, FactEnvelope]) -> list[FactEnvelope]:
        frontier = {request.entity_id}
        visited = set(frontier)
        matches: list[FactEnvelope] = []
        for _ in range(request.max_depth):
            next_frontier: set[str] = set()
            for relation in self._relations.values():
                if relation.source_fact_id not in frontier or relation.source_fact_id not in visible:
                    continue
                if request.relation and relation.relation != request.relation:
                    continue
                if _rank(relation.clearance) > _rank(request.clearance):
                    continue
                if relation.target_fact_id in visited:
                    continue
                visited.add(relation.target_fact_id)
                next_frontier.add(relation.target_fact_id)
                target = visible.get(relation.target_fact_id)
                if target is not None and _rank(target.clearance) <= _rank(request.clearance):
                    matches.append(target)
            frontier = next_frontier
            if not frontier:
                break
        return matches

    def _load(self) -> None:
        if self._backend is not None:
            try:
                fact_payload, relation_payload = self._backend.load()
                self._facts = {item["fact_id"]: FactEnvelope.from_dict(item) for item in fact_payload}
                self._relations = {
                    item["relation_id"]: WorldModelRelation(
                        relation_id=item["relation_id"], source_fact_id=item["source_fact_id"],
                        relation=item["relation"], target_fact_id=item["target_fact_id"],
                        source_ref=item["source_ref"], confidence=item["confidence"],
                        clearance=Clearance(item["clearance"]), taint=Taint(item["taint"]),
                        valid_from=item.get("valid_from"), valid_to=item.get("valid_to"),
                    ) for item in relation_payload
                }
            except (ValueError, KeyError, TypeError, WorldModelError) as exc:
                raise WorldModelError("invalid_storage", "world model backend returned invalid data") from exc
            return
        if self._path is None or not self._path.exists():
            return
        if self._path.stat().st_size > self._max_file_bytes:
            raise WorldModelError("storage_limit", "world model file exceeds the configured limit")
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                fact_payload = payload
                relation_payload = ()
            elif isinstance(payload, dict):
                fact_payload = payload.get("facts", ())
                relation_payload = payload.get("relations", ())
            else:
                raise ValueError("world model storage must be an object or legacy fact list")
            self._facts = {
                item["fact_id"]: FactEnvelope.from_dict(item)
                for item in fact_payload
            }
            self._relations = {
                item["relation_id"]: WorldModelRelation(
                    relation_id=item["relation_id"], source_fact_id=item["source_fact_id"],
                    relation=item["relation"], target_fact_id=item["target_fact_id"],
                    source_ref=item["source_ref"], confidence=item["confidence"],
                    clearance=Clearance(item["clearance"]), taint=Taint(item["taint"]),
                    valid_from=item.get("valid_from"), valid_to=item.get("valid_to"),
                ) for item in relation_payload
            }
        except (OSError, ValueError, KeyError, TypeError, WorldModelError) as exc:
            raise WorldModelError("invalid_storage", "world model file is invalid") from exc

    def _persist(self) -> None:
        if self._backend is not None:
            self._backend.save(tuple(self._facts.values()), tuple(self._relations.values()))
            return
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            {
                "facts": [fact.to_dict() for fact in self._facts.values()],
                "relations": [
                    {"relation_id": relation.relation_id, "source_fact_id": relation.source_fact_id,
                     "relation": relation.relation, "target_fact_id": relation.target_fact_id,
                     "source_ref": relation.source_ref, "confidence": relation.confidence,
                     "clearance": relation.clearance.value, "taint": relation.taint.value,
                     "valid_from": relation.valid_from, "valid_to": relation.valid_to}
                    for relation in self._relations.values()
                ],
            },
            sort_keys=True, separators=(",", ":"), default=str,
        ).encode("utf-8")
        if len(encoded) > self._max_file_bytes:
            raise WorldModelError("storage_limit", "world model file exceeds the configured limit")
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            temporary.write_bytes(encoded)
            temporary.replace(self._path)
        except OSError as exc:
            raise WorldModelError("storage_failed", "world model file could not be written") from exc

    @staticmethod
    def _matches_key(fact: FactEnvelope, key: str) -> bool:
        if not key:
            return True
        return isinstance(fact.value, dict) and key in fact.value

    def _event(self, event_type: str, request: WorldModelQuery, payload: dict[str, str]) -> None:
        if self._ledger is None:
            return
        sequence = len(self._ledger.events)
        self._ledger.append(build_event(
            event_type=event_type,
            task_id=request.task_id,
            actor_id="world-model",
            actor_type="world_model",
            payload_contract="WorldModelQuery",
            payload_version="1.0",
            payload={"task_id": request.task_id, "clearance": request.clearance.value, **payload},
            clearance=request.clearance,
            idempotency=stable_id("world-model", event_type, request.task_id, sequence),
            sequence=sequence,
            previous_event_hash=self._ledger.head_hash,
            occurred_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        ))


class CandidateFactWriter:
    """Stage facts and commit only after both external gates approve them."""

    def __init__(self, store: WorldModelStore, *, consistency_gate: Gate, verification_gate: Gate, ledger: EventLedger | None = None) -> None:
        self._store = store
        self._consistency_gate = consistency_gate
        self._verification_gate = verification_gate
        self._ledger = ledger
        self._candidates: dict[str, CandidateFact] = {}

    @property
    def candidates(self) -> tuple[CandidateFact, ...]:
        return tuple(self._candidates.values())

    def stage(self, candidate: CandidateFact) -> CandidateFact:
        if candidate.candidate_id in self._candidates:
            existing = self._candidates[candidate.candidate_id]
            if existing != candidate:
                raise WorldModelError("candidate_conflict", "candidate identity was reused for different content")
            return existing
        self._event("fact.candidate", candidate, {"candidate_id": candidate.candidate_id, "state": "candidate"})
        self._candidates[candidate.candidate_id] = candidate
        return candidate

    def commit(self, candidate_id: str) -> FactEnvelope:
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise WorldModelError("candidate_missing", "candidate fact is not staged")
        if not self._consistency_gate(candidate):
            raise WorldModelError("consistency_failed", "candidate failed the consistency gate")
        if not self._verification_gate(candidate):
            raise WorldModelError("verification_failed", "candidate failed the verification gate")
        self._store._validate_commit(candidate.fact, candidate.relations)
        self._event("fact.committed", candidate, {
            "candidate_id": candidate.candidate_id,
            "fact_id": candidate.fact.fact_id,
            "state": "committed",
        })
        self._store._commit(candidate.fact, candidate.relations)
        del self._candidates[candidate.candidate_id]
        return candidate.fact

    def reconcile(self, candidate_id: str, *, review_floor: float = 0.0, emit_conflict: bool = True) -> FactEnvelope:
        """Gate, reconcile, and commit a staged candidate.

        A candidate below ``review_floor`` is queued for human review instead
        of being committed.  A candidate that supersedes an existing fact emits
        a ``world_model.conflict`` event and commits both facts, keeping the
        older one auditable but no longer query-visible.
        """
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise WorldModelError("candidate_missing", "candidate fact is not staged")
        if not self._consistency_gate(candidate):
            raise WorldModelError("consistency_failed", "candidate failed the consistency gate")
        if not self._verification_gate(candidate):
            raise WorldModelError("verification_failed", "candidate failed the verification gate")
        if candidate.fact.confidence < review_floor:
            self._store.enqueue_review(candidate, "fact confidence is below the reconciliation floor")
            raise WorldModelError("review_required", "candidate was queued for human review")
        if emit_conflict and candidate.fact.supersedes_fact_id:
            self._event("world_model.conflict", candidate, {
                "candidate_id": candidate.candidate_id,
                "fact_id": candidate.fact.fact_id,
                "supersedes_fact_id": candidate.fact.supersedes_fact_id,
                "resolution": "supersession",
            })
        return self.commit(candidate_id)

    def _event(self, event_type: str, candidate: CandidateFact, payload: dict[str, str]) -> None:
        if self._ledger is None:
            return
        provenance = candidate.fact
        sequence = len(self._ledger.events)
        body = {
            **payload,
            "task_id": candidate.task_id,
            "provenance": {
                "source_ref": provenance.source_ref,
                "confidence": provenance.confidence,
                "clearance": provenance.clearance.value,
                "taint": provenance.taint.value,
                "content_hash": hashlib.sha256(json.dumps(provenance.value, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
                "provenance_refs": list(candidate.provenance_refs),
                "consistency_reference": candidate.consistency_reference,
                "verification_reference": candidate.verification_reference,
                "relations": [
                    {"relation_id": relation.relation_id, "source_fact_id": relation.source_fact_id,
                     "relation": relation.relation, "target_fact_id": relation.target_fact_id,
                     "source_ref": relation.source_ref, "confidence": relation.confidence,
                     "clearance": relation.clearance.value, "taint": relation.taint.value}
                    for relation in candidate.relations
                ],
            },
        }
        self._ledger.append(build_event(
            event_type=event_type,
            task_id=candidate.task_id,
            actor_id="world-model-writer",
            actor_type="world_model",
            payload_contract="CandidateFact",
            payload_version="1.0",
            payload=body,
            clearance=provenance.clearance,
            idempotency=stable_id("fact", event_type, candidate.task_id, candidate.candidate_id, sequence),
            sequence=sequence,
            previous_event_hash=self._ledger.head_hash,
            occurred_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        ))


def candidate_id(task_id: str, fact: FactEnvelope) -> str:
    return stable_id("candidate", task_id, fact.fact_id, fact.source_ref, fact.ingested_at)


__all__ = ["CandidateFact", "CandidateFactWriter", "GraphStore", "ReviewItem", "WorldModelError", "WorldModelQuery", "WorldModelRelation", "WorldModelStore", "candidate_id"]
