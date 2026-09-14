"""Provider-neutral reranker adapters.

``RetrievalService`` consumes a ``Reranker`` that scores ``(query, chunk)``
pairs.  This module adds a higher-level ``RerankerAdapter`` that scores raw
passages, plus an adapter that delegates to a qualified local backend through
a single-shot rerank prompt.  A thin bridge lets an adapter plug into the
existing retrieval service without changing the core.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from .retrieval import IndexChunk, RetrievalError


class RerankerAdapterError(RuntimeError):
    """A reranker adapter could not score the supplied passages."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class RerankerAdapter(Protocol):
    """Score passages against a query, highest score first is not required."""

    model_id: str
    qualification_reference: str

    def rerank(self, query: str, passages: Sequence[str]) -> tuple[float, ...]: ...


@dataclass(frozen=True, slots=True)
class FunctionRerankerAdapter:
    """Wrap a deterministic or injected scoring function."""

    model_id: str
    qualification_reference: str
    scorer: Callable[[str, Sequence[str]], Sequence[float]]

    def __post_init__(self) -> None:
        if not self.model_id or not self.qualification_reference:
            raise RerankerAdapterError("invalid_adapter", "reranker identity and qualification are required")

    def rerank(self, query: str, passages: Sequence[str]) -> tuple[float, ...]:
        if not query.strip():
            raise RerankerAdapterError("invalid_query", "reranker query is required")
        values = tuple(float(value) for value in self.scorer(query, tuple(passages)))
        if len(values) != len(passages):
            raise RerankerAdapterError("invalid_score_count", "reranker returned the wrong number of scores")
        return values


class RetrievalReranker:
    """Bridge a ``RerankerAdapter`` to the retrieval ``Reranker`` interface."""

    def __init__(self, adapter: RerankerAdapter) -> None:
        self._adapter = adapter
        self.model_id = adapter.model_id
        self.qualification_reference = adapter.qualification_reference

    def score(self, query: str, chunks: tuple[IndexChunk, ...]) -> tuple[float, ...]:
        return self._adapter.rerank(query, tuple(chunk.text for chunk in chunks))


class VllmRerankerAdapter:
    """Score passages with a qualified local backend via one rerank prompt.

    The request builder supplies the model-specific prompt.  The default
    parser expects the response to be a JSON array of numbers, one per
    passage; a custom parser may be injected.
    """

    def __init__(
        self,
        backend: object,
        request_builder: Callable[[str, Sequence[str]], object],
        *,
        model_id: str = "vllm_reranker",
        qualification_reference: str,
        parser: Callable[[str, int], Sequence[float]] | None = None,
    ) -> None:
        if not model_id or not qualification_reference or not callable(request_builder):
            raise RerankerAdapterError("invalid_adapter", "vllm reranker requires identity and a request builder")
        self.model_id = model_id
        self.qualification_reference = qualification_reference
        self._backend = backend
        self._request_builder = request_builder
        self._parser = parser or _parse_score_list

    def rerank(self, query: str, passages: Sequence[str]) -> tuple[float, ...]:
        from contracts.model.backend import BackendRequest

        request = self._request_builder(query, tuple(passages))
        if not isinstance(request, BackendRequest):
            raise RerankerAdapterError("invalid_backend_request", "reranker request builder returned an invalid request")
        # The backend protocol has no timeout parameter; a hung local model
        # server must not hang knowledge_search indefinitely.
        from airbench.concurrency import run_with_timeout

        timeout_ms = int(getattr(request, "timeout_ms", 0) or 0)
        timeout_s = (timeout_ms / 1000.0) if timeout_ms > 0 else 120.0
        try:
            response = run_with_timeout(lambda: self._backend.complete(request), timeout_s)
        except FutureTimeout as exc:
            raise RerankerAdapterError("reranker_timeout", "the reranker backend timed out") from exc
        output = getattr(response, "output", "")
        text = output if isinstance(output, str) else json.dumps(output, sort_keys=True, separators=(",", ":"), default=str)
        values = tuple(float(value) for value in self._parser(text, len(passages)))
        if len(values) != len(passages):
            raise RerankerAdapterError("invalid_score_count", "reranker returned the wrong number of scores")
        return values


def _parse_score_list(text: str, expected: int) -> Sequence[float]:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise RerankerAdapterError("invalid_response", "reranker response was not a JSON score list") from exc
    if not isinstance(payload, list) or len(payload) != expected:
        raise RerankerAdapterError("invalid_response", "reranker response length does not match the passages")
    try:
        return tuple(float(value) for value in payload)
    except (TypeError, ValueError) as exc:
        raise RerankerAdapterError("invalid_response", "reranker scores were not numeric") from exc


def build_reranker_from_env(
    env: dict[str, str] | None = None,
    *,
    backend: object | None = None,
    request_builder: Callable[[str, Sequence[str]], object] | None = None,
) -> RerankerAdapter | None:
    """Select the configured model reranker, or ``None`` for passthrough."""

    values = os.environ if env is None else env
    selected = values.get("AIRBENCH_RERANKER_ADAPTER", "").strip().lower()
    if not selected or selected in {"none", "disabled", "off"}:
        return None
    if selected in {"vllm", "vllm_reranker", "model"}:
        if backend is None or request_builder is None:
            raise RerankerAdapterError("adapter_unavailable", "vllm reranker requires a qualified backend and request builder")
        return VllmRerankerAdapter(
            backend, request_builder, qualification_reference=values.get("AIRBENCH_RERANKER_QUALIFICATION", "qualification.reranker.local"),
        )
    raise RerankerAdapterError("unknown_adapter", "AIRBENCH_RERANKER_ADAPTER must be none or vllm")


__all__ = [
    "FunctionRerankerAdapter",
    "RerankerAdapter",
    "RerankerAdapterError",
    "RetrievalReranker",
    "VllmRerankerAdapter",
    "build_reranker_from_env",
]
