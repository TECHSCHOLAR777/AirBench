"""Bounded structured comparison of current decisions with past decisions."""
from __future__ import annotations
from dataclasses import dataclass
from contracts import Clearance, EventLedger, Taint, build_event, idempotency_key

@dataclass(frozen=True, slots=True)
class DecisionRecord:
    decision_id: str; task_id: str; decision_type: str; object_id: str; features: tuple[tuple[str, str], ...]; decision: str; rule_ref: str; authority: str; current: bool = True; outcome: str | None = None; rule_current: bool = True; authority_current: bool = True
@dataclass(frozen=True, slots=True)
class ConsistencyResult:
    task_id: str; decision_id: str; comparable_ids: tuple[str, ...]; superseded_ids: tuple[str, ...]; material_differences: tuple[tuple[str, str, str], ...]; deviation: bool; reason: str; ledger_event_id: str

class ConsistencyEngine:
    def __init__(self, ledger: EventLedger, history: tuple[DecisionRecord, ...] = ()) -> None: self.ledger = ledger; self.history = history
    def compare(self, current: DecisionRecord, *, clearance: Clearance = Clearance.internal, taint: Taint = Taint.clean) -> ConsistencyResult:
        comparable = [item for item in self.history if item.decision_type == current.decision_type and item.object_id == current.object_id]; superseded = [item for item in comparable if not (item.current and item.rule_current and item.authority_current)]; active = [item for item in comparable if item.current and item.rule_current and item.authority_current]
        current_features = dict(current.features); differences: list[tuple[str, str, str]] = []
        for item in active:
            old = dict(item.features); keys = set(old) | set(current_features)
            differences.extend((key, old.get(key, ""), current_features.get(key, "")) for key in sorted(keys) if old.get(key, "") != current_features.get(key, ""))
        deviation = bool(active) and not differences and any(item.decision != current.decision for item in active)
        reason = "material differences explain the comparable decisions" if differences else ("deviation requires human justification" if deviation else "no unexplained deviation detected")
        payload = {"decision_id": current.decision_id, "comparable_ids": [x.decision_id for x in active], "superseded_ids": [x.decision_id for x in superseded], "material_differences": differences, "deviation": deviation, "reason": reason, "provenance": {"source_ref": f"decision:{current.decision_id}", "confidence": 1.0, "clearance": clearance.value, "taint": taint.value}}
        self.ledger.append(build_event(event_type="consistency.checked", task_id=current.task_id, actor_id="consistency-engine", actor_type="policy", payload_contract="ConsistencyResult", payload_version="1.0", payload=payload, clearance=clearance, idempotency=idempotency_key("consistency.checked", current.task_id, current.decision_id), sequence=len(self.ledger.events), previous_event_hash=self.ledger.head_hash))
        event = self.ledger.events[-1]
        return ConsistencyResult(current.task_id, current.decision_id, tuple(x.decision_id for x in active), tuple(x.decision_id for x in superseded), tuple(differences), deviation, reason, event.event_id)

__all__ = ["ConsistencyEngine", "ConsistencyResult", "DecisionRecord"]
