"""Typed P&ID extraction record.

The adapter produces a `PIDRecord`: a bounded, provenance-bearing structured
view of the drawing.  It is untrusted evidence, not a trusted World Model
update; downstream candidate-fact and verification gates decide what may be
committed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from contracts import Clearance, Taint
from contracts import FactEnvelope, stable_id
from airbench.knowledge.world_model import CandidateFact, WorldModelRelation


@dataclass(frozen=True, slots=True)
class PidComponent:
    component_id: str
    label: str
    tag: str | None
    bbox: tuple[float, float, float, float]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id, "label": self.label, "tag": self.tag,
            "bbox": [round(value, 2) for value in self.bbox], "confidence": round(self.confidence, 4),
        }


@dataclass(frozen=True, slots=True)
class PidRelation:
    relation_id: str
    source: str
    target: str
    relation: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id, "source": self.source, "target": self.target,
            "relation": self.relation, "confidence": round(self.confidence, 4),
        }


@dataclass(frozen=True, slots=True)
class PIDRecord:
    task_id: str
    intake_id: str
    revision_id: str
    source_ref: str
    content_hash: str
    media_type: str
    clearance: Clearance
    taint: Taint
    components: tuple[PidComponent, ...] = ()
    relations: tuple[PidRelation, ...] = ()
    texts: tuple[dict[str, Any], ...] = ()
    legend_id: str = "default"
    adapter_version: str = "1.0"
    graphml_ref: str | None = None
    json_ref: str | None = None
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "intake_id": self.intake_id,
            "revision_id": self.revision_id,
            "source_ref": self.source_ref,
            "content_hash": self.content_hash,
            "media_type": self.media_type,
            "clearance": self.clearance.value,
            "taint": self.taint.value,
            "legend_id": self.legend_id,
            "adapter_version": self.adapter_version,
            "graphml_ref": self.graphml_ref,
            "json_ref": self.json_ref,
            "extracted_at": self.extracted_at,
            "summary": {
                "components": len(self.components),
                "relations": len(self.relations),
                "texts": len(self.texts),
            },
            "components": [component.to_dict() for component in self.components],
            "relations": [relation.to_dict() for relation in self.relations],
            "texts": list(self.texts),
        }


def candidate_facts_from_pid(record: PIDRecord, *, task_id: str | None = None) -> tuple[CandidateFact, ...]:
    """Convert an extracted P&ID into gated World Model candidates.

    The returned values are deliberately still untrusted. This function only
    creates typed candidates; callers must pass them through
    ``CandidateFactWriter`` before they become graph facts.
    """
    candidate_task_id = task_id or record.task_id
    fact_ids = {
        component.component_id: stable_id("pid-fact", record.revision_id, component.component_id)
        for component in record.components
        if component.component_id
    }
    relations_by_source: dict[str, list[WorldModelRelation]] = {}
    for relation in record.relations:
        source_fact_id = fact_ids.get(relation.source)
        target_fact_id = fact_ids.get(relation.target)
        if not source_fact_id or not target_fact_id:
            continue
        relations_by_source.setdefault(relation.source, []).append(WorldModelRelation(
            relation_id=stable_id("pid-relation", record.revision_id, relation.relation_id),
            source_fact_id=source_fact_id,
            relation=relation.relation,
            target_fact_id=target_fact_id,
            source_ref=f"{record.source_ref}#relation:{relation.relation_id}",
            confidence=relation.confidence,
            clearance=record.clearance,
            taint=record.taint,
        ))

    candidates: list[CandidateFact] = []
    for component in record.components:
        if not component.component_id or component.component_id not in fact_ids:
            continue
        source_ref = f"{record.source_ref}#component:{component.component_id}"
        fact = FactEnvelope(
            fact_id=fact_ids[component.component_id],
            value={
                "entity_id": component.component_id,
                "object_type": "engineering_component",
                "attributes": {
                    "label": component.label,
                    "tag": component.tag,
                    "bbox": list(component.bbox),
                    "revision_id": record.revision_id,
                },
            },
            source_ref=source_ref,
            confidence=component.confidence,
            clearance=record.clearance,
            taint=record.taint,
            extraction_method=f"pid_adapter:{record.adapter_version}",
            observed_at=record.extracted_at,
            ingested_at=record.extracted_at,
        )
        evidence_ref = stable_id("pid-evidence", record.intake_id, component.component_id)
        candidate_identity = stable_id("pid-candidate", candidate_task_id, fact.fact_id, record.revision_id)
        candidates.append(CandidateFact(
            candidate_id=candidate_identity,
            task_id=candidate_task_id,
            fact=fact,
            provenance_refs=(evidence_ref, record.intake_id),
            consistency_reference=f"pid-consistency:{candidate_identity}",
            verification_reference=f"pid-verification:{candidate_identity}",
            relations=tuple(relations_by_source.get(component.component_id, ())),
        ))
    return tuple(candidates)


__all__ = ["PIDRecord", "PidComponent", "PidRelation", "candidate_facts_from_pid"]
