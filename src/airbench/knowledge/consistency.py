"""Bounded structured comparison of current decisions with past decisions.

A decision is compared against past decisions about the *same object* and the
*same pack decision type*, using typed features rather than text similarity.
Only pack-declared material features can trigger a deviation, and a decision
whose cited rule or authority is no longer current is treated as superseded
rather than comparable.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from contracts import Clearance, EventLedger, Taint, build_event, idempotency_key


class DecisionStore(Protocol):
    """Structural view of a durable decision history (no core store dependency)."""

    def find_comparable(self, decision_type: str, object_id: str, *, limit: int = 100) -> tuple["DecisionRecord", ...]: ...

    def record(self, record: "DecisionRecord", *, supersede_existing: bool = True) -> str: ...


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    decision_id: str; task_id: str; decision_type: str; object_id: str; features: tuple[tuple[str, str], ...]; decision: str; rule_ref: str; authority: str; current: bool = True; outcome: str | None = None; rule_current: bool = True; authority_current: bool = True


@dataclass(frozen=True, slots=True)
class ConsistencyResult:
    task_id: str; decision_id: str; comparable_ids: tuple[str, ...]; superseded_ids: tuple[str, ...]; material_differences: tuple[tuple[str, str, str], ...]; deviation: bool; reason: str; ledger_event_id: str


class ConsistencyEngine:
    def __init__(self, ledger: EventLedger, history: tuple[DecisionRecord, ...] = ()) -> None:
        self.ledger = ledger
        self.history = history

    def record(self, record: DecisionRecord, *, store: DecisionStore | None = None) -> str:
        """Persist a decision so later comparisons can find it."""
        if store is not None:
            return store.record(record)
        self.history = (*self.history, record)
        return record.decision_id

    def evaluate(
        self,
        current: DecisionRecord,
        *,
        store: DecisionStore | None = None,
        material_features: Sequence[str] | None = None,
        clearance: Clearance = Clearance.internal,
        taint: Taint = Taint.clean,
    ) -> ConsistencyResult:
        """Compare a forming decision against comparable history.

        A differing material feature, or a different decision with the same
        features, is a deviation that requires justification.  Compared
        decisions whose rule or authority is no longer current are recorded as
        superseded, never used to justify the forming decision.
        """
        history = tuple(store.find_comparable(current.decision_type, current.object_id)) if store is not None else self.history
        comparable = [item for item in history if item.decision_type == current.decision_type and item.object_id == current.object_id]
        superseded = [item for item in comparable if not (item.current and item.rule_current and item.authority_current)]
        active = [item for item in comparable if item.current and item.rule_current and item.authority_current]
        material = set(material_features) if material_features is not None else None

        current_features = dict(current.features)
        differences: list[tuple[str, str, str]] = []
        for item in active:
            old = dict(item.features)
            for key in sorted(set(old) | set(current_features)):
                old_value, new_value = old.get(key, ""), current_features.get(key, "")
                if old_value != new_value:
                    differences.append((key, old_value, new_value))
        material_differences = [
            difference for difference in differences
            if material is None or difference[0] in material
        ]
        decision_differs = any(item.decision != current.decision for item in active)
        deviation = bool(active) and (bool(material_differences) or decision_differs)
        if not active:
            reason = "no comparable decisions to compare"
        elif deviation:
            reason = "material difference from comparable decisions requires justification"
        else:
            reason = "consistent with comparable decisions"
        return self._emit(current, active, superseded, differences, deviation, reason, clearance, taint)

    def compare(self, current: DecisionRecord, *, clearance: Clearance = Clearance.internal, taint: Taint = Taint.clean) -> ConsistencyResult:
        """Legacy in-memory comparison: a deviation is an unexplained decision change."""
        comparable = [item for item in self.history if item.decision_type == current.decision_type and item.object_id == current.object_id]
        superseded = [item for item in comparable if not (item.current and item.rule_current and item.authority_current)]
        active = [item for item in comparable if item.current and item.rule_current and item.authority_current]
        current_features = dict(current.features)
        differences: list[tuple[str, str, str]] = []
        for item in active:
            old = dict(item.features); keys = set(old) | set(current_features)
            differences.extend((key, old.get(key, ""), current_features.get(key, "")) for key in sorted(keys) if old.get(key, "") != current_features.get(key, ""))
        deviation = bool(active) and not differences and any(item.decision != current.decision for item in active)
        reason = "material differences explain the comparable decisions" if differences else ("deviation requires human justification" if deviation else "no unexplained deviation detected")
        return self._emit(current, active, superseded, differences, deviation, reason, clearance, taint)

    def _emit(
        self,
        current: DecisionRecord,
        active: list[DecisionRecord],
        superseded: list[DecisionRecord],
        differences: list[tuple[str, str, str]],
        deviation: bool,
        reason: str,
        clearance: Clearance,
        taint: Taint,
    ) -> ConsistencyResult:
        payload: dict[str, Any] = {
            "decision_id": current.decision_id,
            "decision_type": current.decision_type,
            "object_id": current.object_id,
            "comparable_ids": [item.decision_id for item in active],
            "superseded_ids": [item.decision_id for item in superseded],
            "material_differences": differences,
            "deviation": deviation,
            "reason": reason,
            "provenance": {
                "source_ref": f"decision:{current.decision_id}",
                "confidence": 1.0,
                "clearance": clearance.value,
                "taint": taint.value,
            },
        }
        self.ledger.append(build_event(
            event_type="consistency.checked", task_id=current.task_id, actor_id="consistency-engine", actor_type="policy",
            payload_contract="ConsistencyResult", payload_version="1.0", payload=payload, clearance=clearance,
            idempotency=idempotency_key("consistency.checked", current.task_id, current.decision_id),
            sequence=len(self.ledger.events), previous_event_hash=self.ledger.head_hash,
        ))
        event = self.ledger.events[-1]
        return ConsistencyResult(
            current.task_id, current.decision_id, tuple(item.decision_id for item in active),
            tuple(item.decision_id for item in superseded), tuple(differences), deviation, reason, event.event_id,
        )


__all__ = ["ConsistencyEngine", "ConsistencyResult", "DecisionRecord", "DecisionStore"]
