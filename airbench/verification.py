"""Deterministic, domain-neutral verification execution.

The core owns the check lifecycle and outcome semantics. A domain pack supplies
the rules and their values; this module does not contain sector assumptions.
Values are never copied into ledger reasons. Only typed references and safe
metadata are persisted there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from math import isfinite
from typing import Any, Callable, Protocol
import time

from contracts import (Clearance, Contract, ContractValidationError, EventLedger,
                       FactEnvelope, LedgerEventEnvelope, SQLiteLedgerStore,
                       Taint, build_event, idempotency_key)


class VerificationError(RuntimeError):
    """A verification request or ledger operation was rejected safely."""


class VerificationOutcome(str, Enum):
    passed = "passed"
    failed = "failed"
    needs_review = "needs_review"


_RULE_KINDS = {"source", "confidence", "unit", "bounds", "cross_fact", "calculation"}
_CROSS_OPERATORS = {"equals", "not_equals", "lt", "lte", "gt", "gte", "delta_lte"}
_CALC_OPERATORS = {"add", "subtract", "multiply", "divide"}
_CLEARANCE_RANK = {
    Clearance.public: 0,
    Clearance.internal: 1,
    Clearance.restricted: 2,
    Clearance.secret: 3,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class VerificationRule(Contract):
    """A serializable rule supplied by a domain pack.

    The rule language is deliberately finite. It does not evaluate Python,
    expressions, regular expressions, or model-written code.
    """

    rule_id: str
    kind: str
    fact_ids: tuple[str, ...] = ()
    confidence_floor: float | None = None
    source_prefixes: tuple[str, ...] = ()
    expected_unit: str | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    operator: str | None = None
    expected_value: Any = None
    expected_fact_id: str | None = None
    tolerance: float = 0.0

    def _validate(self, hints: dict[str, Any]) -> list[Any]:
        issues = super()._validate(hints)
        if self.kind not in _RULE_KINDS:
            issues.append(_issue("kind", "enum", "unsupported verification rule kind"))
        if not self.fact_ids:
            issues.append(_issue("fact_ids", "required", "a rule must name at least one fact"))
        if len(set(self.fact_ids)) != len(self.fact_ids):
            issues.append(_issue("fact_ids", "duplicate", "fact IDs must be unique within a rule"))
        if self.confidence_floor is not None and not 0 <= self.confidence_floor <= 1:
            issues.append(_issue("confidence_floor", "range", "must be between 0 and 1"))
        if self.tolerance < 0 or not isfinite(self.tolerance):
            issues.append(_issue("tolerance", "range", "must be finite and non-negative"))
        if self.kind == "confidence" and self.confidence_floor is None:
            issues.append(_issue("confidence_floor", "required", "confidence rules require a floor"))
        if self.kind == "unit" and not self.expected_unit:
            issues.append(_issue("expected_unit", "required", "unit rules require an expected unit"))
        if self.kind == "bounds":
            if self.lower_bound is None and self.upper_bound is None:
                issues.append(_issue("bounds", "required", "bounds require a lower or upper limit"))
            if self.lower_bound is not None and self.upper_bound is not None and self.lower_bound > self.upper_bound:
                issues.append(_issue("bounds", "range", "lower bound cannot exceed upper bound"))
        if self.kind == "cross_fact":
            if len(self.fact_ids) != 2:
                issues.append(_issue("fact_ids", "length", "cross-fact rules require exactly two facts"))
            if self.operator not in _CROSS_OPERATORS:
                issues.append(_issue("operator", "enum", "unsupported cross-fact operator"))
        if self.kind == "calculation":
            if self.operator not in _CALC_OPERATORS:
                issues.append(_issue("operator", "enum", "unsupported calculation operator"))
            if self.operator in {"subtract", "divide"} and len(self.fact_ids) != 2:
                issues.append(_issue("fact_ids", "length", "subtract and divide require exactly two facts"))
            if self.expected_fact_id is None and self.expected_value is None:
                issues.append(_issue("expected_value", "required", "calculation requires a target value or fact"))
            if self.expected_fact_id is not None and self.expected_fact_id in self.fact_ids:
                issues.append(_issue("expected_fact_id", "cycle", "calculation target cannot be an operand"))
        return issues


@dataclass(frozen=True)
class VerificationRequest(Contract):
    verification_id: str
    task_id: str
    rules: tuple[VerificationRule, ...]
    facts: tuple[FactEnvelope, ...]
    clearance: Clearance
    evidence_refs: tuple[str, ...] = ()
    rule_set_version: str = "core"
    timeout_ms: int = 30_000
    idempotency_key: str = ""

    def _validate(self, hints: dict[str, Any]) -> list[Any]:
        issues = super()._validate(hints)
        if not self.rules:
            issues.append(_issue("rules", "required", "verification requires at least one rule"))
        if len(self.rules) > 1_000:
            issues.append(_issue("rules", "resource_limit", "verification rule count exceeds 1000"))
        if len(self.facts) > 10_000:
            issues.append(_issue("facts", "resource_limit", "verification fact count exceeds 10000"))
        if len({rule.rule_id for rule in self.rules}) != len(self.rules):
            issues.append(_issue("rules", "duplicate", "rule IDs must be unique"))
        if len({fact.fact_id for fact in self.facts}) != len(self.facts):
            issues.append(_issue("facts", "duplicate", "fact IDs must be unique"))
        if type(self.timeout_ms) is not int or self.timeout_ms <= 0 or self.timeout_ms > 86_400_000:
            issues.append(_issue("timeout_ms", "range", "must be 1..86400000"))
        if not self.idempotency_key.strip():
            issues.append(_issue("idempotency_key", "required", "idempotency key is required"))
        return issues


@dataclass(frozen=True)
class VerificationCheck(Contract):
    rule_id: str
    kind: str
    outcome: VerificationOutcome
    reason: str
    fact_ids: tuple[str, ...]
    source_refs: tuple[str, ...]
    confidence: float
    clearance: Clearance
    taint: Taint


@dataclass(frozen=True)
class VerificationResult(Contract):
    verification_id: str
    task_id: str
    outcome: VerificationOutcome
    checks: tuple[VerificationCheck, ...]
    confidence: float
    clearance: Clearance
    taint: Taint
    reason: str
    ledger_event_ids: tuple[str, ...] = ()
    completed_at: str = field(default_factory=_now)


class VerificationLedger(Protocol):
    @property
    def events(self) -> tuple[LedgerEventEnvelope, ...]: ...

    @property
    def head_hash(self) -> str | None: ...

    def append(self, event: LedgerEventEnvelope) -> Any: ...


def _issue(path: str, category: str, message: str) -> Any:
    from contracts import ValidationIssue

    return ValidationIssue(path, category, message)


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _comparison(left: Any, right: Any, operator: str, tolerance: float) -> bool:
    left_decimal = _decimal(left)
    right_decimal = _decimal(right)
    if left_decimal is not None and right_decimal is not None:
        if operator == "equals":
            return abs(left_decimal - right_decimal) <= Decimal(str(tolerance))
        if operator == "not_equals":
            return abs(left_decimal - right_decimal) > Decimal(str(tolerance))
        if operator == "lt":
            return left_decimal < right_decimal
        if operator == "lte":
            return left_decimal <= right_decimal
        if operator == "gt":
            return left_decimal > right_decimal
        if operator == "gte":
            return left_decimal >= right_decimal
        if operator == "delta_lte":
            return abs(left_decimal - right_decimal) <= Decimal(str(tolerance))
    if operator == "equals":
        return left == right
    if operator == "not_equals":
        return left != right
    raise ValueError("non-numeric comparison is not supported for this operator")


def _combined_taint(facts: list[FactEnvelope]) -> Taint:
    if any(fact.taint == Taint.contaminated for fact in facts):
        return Taint.contaminated
    if any(fact.taint == Taint.untrusted for fact in facts):
        return Taint.untrusted
    return Taint.clean


def _highest_clearance(facts: list[FactEnvelope], fallback: Clearance) -> Clearance:
    if not facts:
        return fallback
    return max((fact.clearance for fact in facts), key=lambda value: _CLEARANCE_RANK[value])


class VerificationRunner:
    """Run finite rules outside the model and append a sealed result."""

    def __init__(self, ledger: VerificationLedger, *, actor_id: str = "verification.local",
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.ledger = ledger
        self.actor_id = actor_id
        self._clock = clock

    def run(self, request: VerificationRequest) -> VerificationResult:
        self._validate_request(request)
        requested_key = idempotency_key("verification.requested", request.verification_id)
        completed_key = idempotency_key("verification.completed", request.verification_id)
        existing_requested = self._event_by_key(requested_key)
        existing_completed = self._event_by_key(completed_key)
        request_payload = self._request_payload(request)

        if existing_completed is not None:
            return self._result_from_event(existing_completed, existing_requested)
        if existing_requested is not None and existing_requested.payload != request_payload:
            raise VerificationError("verification idempotency key was reused for different inputs")
        if existing_requested is None:
            requested = self._append(
                event_type="verification.requested",
                task_id=request.task_id,
                payload=request_payload,
                contract="VerificationRequest",
                key=requested_key,
                clearance=request.clearance,
            )
        else:
            requested = existing_requested

        result = self._evaluate(request, self._clock() + request.timeout_ms / 1000)
        completed_payload = result.to_dict()
        # The ledger state machine uses ``status`` as its transition field.
        # Keep ``outcome`` in the typed result as the public contract name.
        completed_payload["status"] = result.outcome.value
        completed_payload["provenance"] = {
            "source_ref": f"verification:{request.verification_id}",
            "confidence": result.confidence,
            "clearance": result.clearance.value,
            "taint": result.taint.value,
        }
        completed = self._append(
            event_type="verification.completed",
            task_id=request.task_id,
            payload=completed_payload,
            contract="VerificationResult",
            key=completed_key,
            clearance=result.clearance,
        )
        return VerificationResult(
            verification_id=result.verification_id,
            task_id=result.task_id,
            outcome=result.outcome,
            checks=result.checks,
            confidence=result.confidence,
            clearance=result.clearance,
            taint=result.taint,
            reason=result.reason,
            ledger_event_ids=(requested.event_id, completed.event_id),
            completed_at=result.completed_at,
        )

    def _validate_request(self, request: VerificationRequest) -> None:
        try:
            if not isinstance(request, VerificationRequest):
                raise TypeError("request must be a VerificationRequest")
            request_issues = request._validate({})
            if request_issues:
                raise ContractValidationError("VerificationRequest", request_issues)
            for rule in request.rules:
                if not isinstance(rule, VerificationRule):
                    raise TypeError("request rules must be VerificationRule values")
                rule_issues = rule._validate({})
                if rule_issues:
                    raise ContractValidationError("VerificationRule", rule_issues)
            for fact in request.facts:
                if not isinstance(fact, FactEnvelope):
                    raise TypeError("request facts must be FactEnvelope values")
                fact_issues = fact._validate({})
                if fact_issues:
                    raise ContractValidationError("FactEnvelope", fact_issues)
        except ContractValidationError as exc:
            raise VerificationError("verification request failed contract validation") from exc

    def _request_payload(self, request: VerificationRequest) -> dict[str, Any]:
        return {
            "verification_id": request.verification_id,
            "rule_set_version": request.rule_set_version,
            "rule_ids": [rule.rule_id for rule in request.rules],
            "fact_ids": [fact.fact_id for fact in request.facts],
            "evidence_refs": list(request.evidence_refs),
            "clearance": request.clearance.value,
        }

    def _evaluate(self, request: VerificationRequest, deadline: float) -> VerificationResult:
        facts = {fact.fact_id: fact for fact in request.facts}
        checks: list[VerificationCheck] = []
        used_facts: list[FactEnvelope] = []
        timed_out = False
        for rule in request.rules:
            if self._clock() > deadline:
                timed_out = True
                timeout_facts = [facts[fact_id] for fact_id in rule.fact_ids if fact_id in facts]
                checks.append(self._timeout_check(rule, timeout_facts, request.clearance))
                used_facts.extend(timeout_facts)
                break
            check, rule_facts = self._evaluate_rule(rule, facts, request.clearance)
            checks.append(check)
            used_facts.extend(rule_facts)

        unique_facts = list({fact.fact_id: fact for fact in used_facts}.values())
        confidence = min((fact.confidence for fact in unique_facts), default=0.0)
        taint = _combined_taint(unique_facts)
        clearance = _highest_clearance(unique_facts, request.clearance)
        if timed_out:
            outcome = VerificationOutcome.needs_review
            reason = "verification exceeded its time budget"
        elif _CLEARANCE_RANK[clearance] > _CLEARANCE_RANK[request.clearance]:
            outcome = VerificationOutcome.needs_review
            reason = "a fact exceeds the request clearance"
        elif any(check.outcome == VerificationOutcome.failed for check in checks):
            outcome = VerificationOutcome.failed
            reason = "one or more deterministic checks failed"
        elif any(check.outcome == VerificationOutcome.needs_review for check in checks):
            outcome = VerificationOutcome.needs_review
            reason = "one or more checks lacked sufficient evidence"
        else:
            outcome = VerificationOutcome.passed
            reason = "all deterministic checks passed"
        return VerificationResult(
            verification_id=request.verification_id,
            task_id=request.task_id,
            outcome=outcome,
            checks=tuple(checks),
            confidence=confidence,
            clearance=clearance,
            taint=taint,
            reason=reason,
        )

    def _timeout_check(
        self,
        rule: VerificationRule,
        facts: list[FactEnvelope],
        request_clearance: Clearance,
    ) -> VerificationCheck:
        return VerificationCheck(
            rule_id=rule.rule_id,
            kind=rule.kind,
            outcome=VerificationOutcome.needs_review,
            reason="verification exceeded its time budget",
            fact_ids=rule.fact_ids,
            source_refs=tuple(fact.source_ref for fact in facts),
            confidence=min((fact.confidence for fact in facts), default=0.0),
            clearance=_highest_clearance(facts, request_clearance),
            taint=_combined_taint(facts),
        )

    def _evaluate_rule(
        self,
        rule: VerificationRule,
        facts: dict[str, FactEnvelope],
        request_clearance: Clearance,
    ) -> tuple[VerificationCheck, list[FactEnvelope]]:
        required_fact_ids = list(rule.fact_ids)
        if rule.kind == "calculation" and rule.expected_fact_id and rule.expected_fact_id not in required_fact_ids:
            required_fact_ids.append(rule.expected_fact_id)
        available = [facts[fact_id] for fact_id in required_fact_ids if fact_id in facts]
        source_refs = tuple(fact.source_ref for fact in available)
        base = dict(
            rule_id=rule.rule_id,
            kind=rule.kind,
            fact_ids=tuple(required_fact_ids),
            source_refs=source_refs,
            confidence=min((fact.confidence for fact in available), default=0.0),
            clearance=_highest_clearance(available, request_clearance),
            taint=_combined_taint(available),
        )
        if len(available) != len(required_fact_ids):
            return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="required fact is unavailable", **base), available
        if any(_CLEARANCE_RANK[fact.clearance] > _CLEARANCE_RANK[request_clearance] for fact in available):
            return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="fact clearance exceeds request clearance", **base), available
        if rule.confidence_floor is not None and any(fact.confidence < rule.confidence_floor for fact in available):
            return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="fact confidence is below the rule floor", **base), available

        try:
            if rule.kind == "source":
                if any(not fact.source_ref for fact in available):
                    return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="source reference is unavailable", **base), available
                if rule.source_prefixes and any(not any(fact.source_ref.startswith(prefix) for prefix in rule.source_prefixes) for fact in available):
                    return VerificationCheck(outcome=VerificationOutcome.failed, reason="fact source is outside the allowed source set", **base), available
            elif rule.kind == "confidence":
                if any(fact.confidence < (rule.confidence_floor or 0.0) for fact in available):
                    return VerificationCheck(outcome=VerificationOutcome.failed, reason="fact confidence is below the required floor", **base), available
            elif rule.kind == "unit":
                if any(fact.unit is None for fact in available):
                    return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="required unit is unavailable", **base), available
                if any(fact.unit != rule.expected_unit for fact in available):
                    return VerificationCheck(outcome=VerificationOutcome.failed, reason="fact unit does not match the required unit", **base), available
            elif rule.kind == "bounds":
                values = [_decimal(fact.value) for fact in available]
                if any(value is None for value in values):
                    return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="fact value is not a finite number", **base), available
                if rule.lower_bound is not None and any(value < Decimal(str(rule.lower_bound)) for value in values if value is not None):
                    return VerificationCheck(outcome=VerificationOutcome.failed, reason="fact is below the allowed lower bound", **base), available
                if rule.upper_bound is not None and any(value > Decimal(str(rule.upper_bound)) for value in values if value is not None):
                    return VerificationCheck(outcome=VerificationOutcome.failed, reason="fact exceeds the allowed upper bound", **base), available
            elif rule.kind == "cross_fact":
                if not _comparison(available[0].value, available[1].value, rule.operator or "equals", rule.tolerance):
                    return VerificationCheck(outcome=VerificationOutcome.failed, reason="cross-fact relation failed", **base), available
            elif rule.kind == "calculation":
                operand_facts = [facts[fact_id] for fact_id in rule.fact_ids]
                operands = [_decimal(fact.value) for fact in operand_facts]
                if any(value is None for value in operands):
                    return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="calculation input is not a finite number", **base), available
                result = operands[0]
                for operand in operands[1:]:
                    if rule.operator == "add":
                        result += operand
                    elif rule.operator == "multiply":
                        result *= operand
                    elif rule.operator == "subtract":
                        result -= operand
                    elif rule.operator == "divide":
                        if operand == 0:
                            return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="calculation divisor is zero", **base), available
                        result /= operand
                if rule.expected_fact_id and rule.expected_fact_id not in facts:
                    return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="calculation target fact is unavailable", **base), available
                target = facts[rule.expected_fact_id].value if rule.expected_fact_id else rule.expected_value
                target_decimal = _decimal(target)
                if target_decimal is None:
                    return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="calculation target is not a finite number", **base), available
                if abs(result - target_decimal) > Decimal(str(rule.tolerance)):
                    return VerificationCheck(outcome=VerificationOutcome.failed, reason="calculation result did not match the target", **base), available
        except (ArithmeticError, TypeError, ValueError):
            return VerificationCheck(outcome=VerificationOutcome.needs_review, reason="check could not be evaluated safely", **base), available
        return VerificationCheck(outcome=VerificationOutcome.passed, reason="check passed", **base), available

    def _event_by_key(self, key: str) -> LedgerEventEnvelope | None:
        return next((event for event in self.ledger.events if event.idempotency_key == key), None)

    def _append(self, *, event_type: str, task_id: str, payload: dict[str, Any], contract: str, key: str, clearance: Clearance) -> LedgerEventEnvelope:
        event = build_event(
            event_type=event_type,
            task_id=task_id,
            actor_id=self.actor_id,
            actor_type="verification",
            payload_contract=contract,
            payload_version="1.0",
            payload=payload,
            clearance=clearance,
            idempotency=key,
            sequence=len(self.ledger.events),
            previous_event_hash=self.ledger.head_hash,
        )
        try:
            committed = self.ledger.append(event)
        except Exception as exc:
            raise VerificationError("verification ledger append failed; result was not accepted") from exc
        if isinstance(committed, LedgerEventEnvelope):
            return committed
        return event

    def _result_from_event(self, event: LedgerEventEnvelope, requested: LedgerEventEnvelope | None) -> VerificationResult:
        payload = event.payload
        try:
            checks = tuple(VerificationCheck.from_dict(value) for value in payload["checks"])
            outcome = VerificationOutcome(payload["outcome"])
            clearance = Clearance(payload["clearance"])
            taint = Taint(payload["taint"])
        except (KeyError, TypeError, ValueError, ContractValidationError) as exc:
            raise VerificationError("sealed verification result could not be replayed") from exc
        return VerificationResult(
            verification_id=payload["verification_id"],
            task_id=payload["task_id"],
            outcome=outcome,
            checks=checks,
            confidence=payload["confidence"],
            clearance=clearance,
            taint=taint,
            reason=payload["reason"],
            ledger_event_ids=((requested.event_id,) if requested else ()) + (event.event_id,),
            completed_at=payload["completed_at"],
        )


__all__ = [
    "VerificationError",
    "VerificationOutcome",
    "VerificationRule",
    "VerificationRequest",
    "VerificationCheck",
    "VerificationResult",
    "VerificationRunner",
]
