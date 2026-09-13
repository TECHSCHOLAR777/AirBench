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


__all__ = ["PIDRecord", "PidComponent", "PidRelation"]
