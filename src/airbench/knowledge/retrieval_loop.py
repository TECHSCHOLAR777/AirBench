"""Iterative retrieval-in-the-loop.

The orchestrator owns the retrieval loop.  Single-shot retrieval is the
default; when a gap analyser is supplied, the loop asks it which sub-topics
are still missing after a round and issues bounded follow-up retrievals.  Every
round is a normal ``RetrievalService.search`` call, so each round is a separate
ledger event and results keep their full provenance.

The gap analyser is an injected, bounded micro-call.  A model never controls
the loop: it returns candidate sub-queries, and this module decides how many
rounds run and when to stop.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from contracts import Clearance

from .retrieval import CitedExcerpt, RetrievalRequest, RetrievalService


class GapAnalyzer(Protocol):
    """Return missing sub-queries for the next retrieval round."""

    def __call__(self, query: str, citations: tuple[CitedExcerpt, ...]) -> Sequence[str]: ...


@dataclass(frozen=True, slots=True)
class RetrievalLoopRequest:
    task_id: str
    query: str
    clearance: Clearance
    top_k: int = 5
    max_excerpt_chars: int = 800
    max_rounds: int = 1
    max_followups_per_round: int = 3

    def __post_init__(self) -> None:
        if not self.task_id or not self.query.strip():
            raise ValueError("retrieval loop task and query are required")
        if not 1 <= self.max_rounds <= 10:
            raise ValueError("max_rounds must be between 1 and 10")
        if not 0 <= self.max_followups_per_round <= 10:
            raise ValueError("max_followups_per_round must be between 0 and 10")


def run_iterative_retrieval(
    service: RetrievalService,
    request: RetrievalLoopRequest,
    *,
    gap_analyzer: GapAnalyzer | None = None,
) -> tuple[CitedExcerpt, ...]:
    """Run bounded retrieval rounds and return a merged, deduplicated set.

    Results are deduplicated by ``chunk_id`` and keep the highest score seen.
    Round count is capped by ``max_rounds``; when no gap analyser is supplied
    the behavior is exactly one round (single-shot retrieval).
    """

    pending: deque[str] = deque([request.query])
    visited: set[str] = set()
    merged: dict[str, CitedExcerpt] = {}
    rounds = 0
    while pending and rounds < request.max_rounds:
        query = pending.popleft()
        if query in visited:
            continue
        visited.add(query)
        rounds += 1
        citations = service.search(RetrievalRequest(
            task_id=request.task_id,
            query=query,
            clearance=request.clearance,
            top_k=request.top_k,
            max_excerpt_chars=request.max_excerpt_chars,
        ))
        for citation in citations:
            existing = merged.get(citation.chunk_id)
            if existing is None or citation.score > existing.score:
                merged[citation.chunk_id] = citation
        if gap_analyzer is None or rounds >= request.max_rounds:
            break
        follow_ups = gap_analyzer(query, citations)[: request.max_followups_per_round]
        for follow_up in follow_ups:
            if follow_up.strip() and follow_up not in visited:
                pending.append(follow_up)
    return tuple(sorted(merged.values(), key=lambda citation: (-citation.score, citation.chunk_id)))


__all__ = ["GapAnalyzer", "RetrievalLoopRequest", "run_iterative_retrieval"]
