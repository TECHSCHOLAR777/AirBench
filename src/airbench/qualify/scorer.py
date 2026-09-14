"""Benchmark and pass-rate scoring for a qualification run."""

from __future__ import annotations

from typing import Sequence

from .types import CaseOutcomeView


def score_outcomes(outcomes: Sequence[CaseOutcomeView]) -> tuple[dict[str, float], dict[str, float]]:
    """Return ``(benchmark_scores, pass_rates)`` for a set of case outcomes.

    ``benchmark_scores`` summarises quality; ``pass_rates`` summarises the
    fraction of fixtures that met their acceptance keywords.
    """
    if not outcomes:
        return {}, {}
    total = len(outcomes)
    passed = sum(1 for outcome in outcomes if outcome.passed)
    confidence = sum(outcome.confidence for outcome in outcomes) / total
    by_task: dict[str, list] = {}
    for outcome in outcomes:
        by_task.setdefault(outcome.task_kind, []).append(outcome)
    task_pass_rates = {
        task_kind: sum(1 for outcome in items if outcome.passed) / len(items)
        for task_kind, items in sorted(by_task.items())
    }
    benchmark_scores = {
        "fixture_accuracy": passed / total,
        "mean_confidence": confidence,
    }
    pass_rates = {"fixture_pass_rate": passed / total, **{f"{kind}_pass_rate": rate for kind, rate in task_pass_rates.items()}}
    return benchmark_scores, pass_rates


__all__ = ["score_outcomes"]
