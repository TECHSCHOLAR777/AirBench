"""Structural types shared by the qualification scorer and harness."""

from __future__ import annotations

from typing import Protocol


class CaseOutcomeView(Protocol):
    """A scored fixture outcome (implemented by ``harness.CaseOutcome``)."""

    fixture_id: str
    task_kind: str
    passed: bool
    confidence: float
    response_hash: str


__all__ = ["CaseOutcomeView"]
