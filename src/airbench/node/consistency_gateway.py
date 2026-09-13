"""Node-owned consistency checks for approval decisions.

The Consistency Engine owns comparison; this service owns task scoping, the
latest report per task, operator justification, and the approval hold.  A
flagged deviation blocks artifact approval until an operator records a
justification, which is written to the ledger.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from contracts import Clearance, EventLedger, Taint, build_event, idempotency_key

from ..knowledge.consistency import ConsistencyEngine, ConsistencyResult, DecisionRecord


class ConsistencyServiceError(RuntimeError):
    """A task-scoped consistency operation was rejected safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _rank(clearance: Clearance) -> int:
    return {
        Clearance.public: 0, Clearance.internal: 1, Clearance.restricted: 2, Clearance.secret: 3,
    }[clearance]


class LocalNodeConsistencyService:
    """Task-scoped consistency evaluation, justification, and approval hold."""

    def __init__(
        self,
        *,
        engine: ConsistencyEngine,
        store: Any | None,
        ledger: EventLedger,
        clearance_context: Clearance,
        max_justification_chars: int = 4_000,
    ) -> None:
        self._engine = engine
        self._store = store
        self._ledger = ledger
        self._clearance = clearance_context
        self._max_justification_chars = max_justification_chars
        self._reports: dict[str, dict[str, Any]] = {}
        self._justified: dict[str, str] = {}

    def evaluate(
        self,
        *,
        task_id: str,
        decision_id: str,
        decision_type: str,
        object_id: str,
        features: Mapping[str, str],
        decision: str,
        rule_ref: str,
        authority: str,
        clearance: Clearance | None = None,
        material_features: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        if not task_id or not decision_id or not decision_type or not object_id:
            raise ConsistencyServiceError("invalid_decision", "the decision identity and object are required")
        level = clearance or self._clearance
        if _rank(level) > _rank(self._clearance):
            raise ConsistencyServiceError("clearance_exceeded", "the decision clearance exceeds this Node context")
        record = DecisionRecord(
            decision_id=decision_id, task_id=task_id, decision_type=decision_type, object_id=object_id,
            features=tuple(sorted((str(key), str(value)) for key, value in features.items())),
            decision=decision, rule_ref=rule_ref, authority=authority,
        )
        # Evaluate against history first; only then record the forming decision so
        # it cannot supersede the very decisions it is being compared with.
        result = self._engine.evaluate(
            record, store=self._store, material_features=material_features, clearance=level, taint=Taint.clean,
        )
        self._engine.record(record, store=self._store)
        report = self._report_wire(result, decision_type=decision_type, object_id=object_id)
        self._reports[task_id] = report
        self._justified.pop(task_id, None)
        return report

    def latest(self, task_id: str) -> dict[str, Any]:
        report = self._reports.get(task_id)
        if report is None:
            return {"task_id": task_id, "status": "not_evaluated", "deviation": False}
        merged = dict(report)
        merged["justified"] = task_id in self._justified
        merged["justification"] = self._justified.get(task_id)
        return merged

    def justify(self, *, task_id: str, operator_id: str, justification: str) -> dict[str, Any]:
        report = self._reports.get(task_id)
        if report is None:
            raise ConsistencyServiceError("report_missing", "there is no consistency report to justify")
        text = justification.strip()
        if not text:
            raise ConsistencyServiceError("invalid_justification", "a justification is required")
        if len(text) > self._max_justification_chars:
            raise ConsistencyServiceError("invalid_justification", "the justification is too long")
        if not report.get("deviation"):
            raise ConsistencyServiceError("no_deviation", "the decision is consistent; no justification is needed")
        self._justified[task_id] = text
        self._ledger.append(build_event(
            event_type="consistency.justified", task_id=task_id, actor_id=operator_id, actor_type="operator",
            payload_contract="ConsistencyJustification", payload_version="1.0",
            payload={
                "task_id": task_id, "decision_id": report.get("decision_id"),
                "operator_id": operator_id, "justification": text,
                "ledger_event_ref": report.get("ledger_event_id"),
                "provenance": {
                    "source_ref": f"decision:{report.get('decision_id')}", "confidence": 1.0,
                    "clearance": self._clearance.value, "taint": Taint.clean.value,
                },
            },
            clearance=self._clearance,
            idempotency=idempotency_key("consistency.justified", task_id, operator_id, report.get("decision_id", "")),
            sequence=len(self._ledger.events), previous_event_hash=self._ledger.head_hash,
            occurred_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        ))
        return self.latest(task_id)

    def is_blocked(self, task_id: str) -> bool:
        report = self._reports.get(task_id)
        return bool(report and report.get("deviation")) and task_id not in self._justified

    @staticmethod
    def _report_wire(result: ConsistencyResult, *, decision_type: str, object_id: str) -> dict[str, Any]:
        return {
            "task_id": result.task_id,
            "status": "evaluated",
            "decision_id": result.decision_id,
            "decision_type": decision_type,
            "object_id": object_id,
            "comparable_ids": list(result.comparable_ids),
            "superseded_ids": list(result.superseded_ids),
            "material_differences": [list(difference) for difference in result.material_differences],
            "deviation": result.deviation,
            "reason": result.reason,
            "ledger_event_id": result.ledger_event_id,
        }


__all__ = ["ConsistencyServiceError", "LocalNodeConsistencyService"]
