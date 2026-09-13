"""Offline model qualification harness.

Runs a model callable over a fixture set and produces a candidate certificate.
The harness never claims production quality by itself: a reference self-test is
labelled as such, and only an operator-signed certificate with real scores is
treated as qualification evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from .scorer import score_outcomes


class QualificationError(RuntimeError):
    """A qualification run could not be completed safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class FixtureCase:
    fixture_id: str
    task_kind: str
    prompt: str
    expected_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.fixture_id or not self.prompt.strip():
            raise QualificationError("invalid_fixture", "a fixture requires an id and a prompt")


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    fixture_id: str
    task_kind: str
    passed: bool
    confidence: float
    response_hash: str


@dataclass(frozen=True, slots=True)
class QualificationRun:
    target_id: str
    role: str
    outcomes: tuple[CaseOutcome, ...]
    benchmark_scores: dict[str, float]
    pass_rates: dict[str, float]
    fixture_set_hash: str
    qualification_source: str


def load_cases(fixtures_dir: str | Path) -> tuple[FixtureCase, ...]:
    root = Path(fixtures_dir)
    if not root.is_dir():
        raise QualificationError("fixtures_missing", "the fixture directory does not exist")
    cases: list[FixtureCase] = []
    for path in sorted(root.glob("*.qualify.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise QualificationError("invalid_fixture", f"fixture {path.name} is not valid JSON") from exc
        if not isinstance(payload, Mapping) or not payload.get("prompt"):
            raise QualificationError("invalid_fixture", f"fixture {path.name} is missing a prompt")
        cases.append(FixtureCase(
            fixture_id=str(payload.get("fixture_id") or path.stem),
            task_kind=str(payload.get("task_kind", "general")),
            prompt=str(payload["prompt"]),
            expected_keywords=tuple(str(item) for item in payload.get("expected_keywords", [])),
        ))
    return tuple(cases)


class QualificationHarness:
    """Run one model callable over a fixture set and score the outcomes."""

    def __init__(self, complete: Callable[[str], str], *, model_id: str) -> None:
        if not model_id or not callable(complete):
            raise QualificationError("invalid_harness", "a model id and callable are required")
        self.model_id = model_id
        self._complete = complete

    def run(self, *, target_id: str, role: str, cases: Sequence[FixtureCase], qualification_source: str = "operator_measured") -> QualificationRun:
        if not target_id or not role:
            raise QualificationError("invalid_run", "target and role are required")
        if not cases:
            raise QualificationError("empty_fixture_set", "at least one fixture case is required")
        outcomes: list[CaseOutcome] = []
        for case in cases:
            response = self._complete(case.prompt)
            if not isinstance(response, str):
                raise QualificationError("invalid_response", "the model callable must return text")
            lowered = response.lower()
            passed = all(keyword.lower() in lowered for keyword in case.expected_keywords)
            confidence = self._confidence(response, case)
            outcomes.append(CaseOutcome(
                fixture_id=case.fixture_id, task_kind=case.task_kind, passed=passed,
                confidence=confidence, response_hash=hashlib.sha256(response.encode("utf-8")).hexdigest(),
            ))
        benchmark_scores, pass_rates = score_outcomes(outcomes)
        return QualificationRun(
            target_id=target_id, role=role, outcomes=tuple(outcomes), benchmark_scores=benchmark_scores,
            pass_rates=pass_rates, fixture_set_hash=_fixture_hash(cases), qualification_source=qualification_source,
        )

    @staticmethod
    def _confidence(response: str, case: FixtureCase) -> float:
        if not case.expected_keywords:
            return 1.0 if response.strip() else 0.0
        hits = sum(1 for keyword in case.expected_keywords if keyword.lower() in response.lower())
        return hits / len(case.expected_keywords)


def _fixture_hash(cases: Iterable[FixtureCase]) -> str:
    payload = [
        {"fixture_id": case.fixture_id, "task_kind": case.task_kind, "prompt": case.prompt,
         "expected_keywords": list(case.expected_keywords)}
        for case in sorted(cases, key=lambda item: item.fixture_id)
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["CaseOutcome", "FixtureCase", "QualificationError", "QualificationHarness", "QualificationRun", "load_cases"]
