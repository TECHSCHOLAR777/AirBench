from __future__ import annotations

from hashlib import sha256

import pytest

from airbench.knowledge.retrieval import CitedExcerpt
from airbench.knowledge.retrieval_loop import RetrievalLoopRequest, run_iterative_retrieval
from airbench.knowledge.reranker import (
    FunctionRerankerAdapter,
    RerankerAdapterError,
    RetrievalReranker,
    build_reranker_from_env,
)
from contracts import Clearance, Taint


def _citation(chunk_id: str, score: float, text: str = "excerpt") -> CitedExcerpt:
    return CitedExcerpt(
        citation_id=f"citation-{chunk_id}", chunk_id=chunk_id, source_ref="local:manual.pdf",
        revision_id="revision-1", page_id="page-1", source_span="page:1", excerpt=text, score=score,
        confidence=0.9, clearance=Clearance.internal, taint=Taint.untrusted,
        content_hash=sha256(text.encode()).hexdigest(), embedding_model="fixture.embedding",
        reranker_model=None, revision_state="current",
    )


class _FakeService:
    def __init__(self, by_query: dict[str, tuple[CitedExcerpt, ...]]) -> None:
        self._by_query = by_query
        self.calls: list[str] = []

    def search(self, request):
        self.calls.append(request.query)
        return self._by_query.get(request.query, ())


class TestRetrievalLoop:
    def test_single_round_without_gap_analyzer(self) -> None:
        service = _FakeService({"q": (_citation("chunk-1", 0.5),)})
        result = run_iterative_retrieval(service, RetrievalLoopRequest("task.loop", "q", Clearance.internal))
        assert service.calls == ["q"]
        assert [citation.chunk_id for citation in result] == ["chunk-1"]

    def test_gap_analysis_expands_and_deduplicates(self) -> None:
        service = _FakeService({
            "q": (_citation("chunk-1", 0.4), _citation("chunk-2", 0.9)),
            "q2": (_citation("chunk-1", 0.7), _citation("chunk-3", 0.6)),
        })

        def analyzer(query, citations):
            assert query == "q"
            return ["q2", "  "]

        result = run_iterative_retrieval(
            service, RetrievalLoopRequest("task.loop", "q", Clearance.internal, max_rounds=2), gap_analyzer=analyzer,
        )
        assert service.calls == ["q", "q2"]
        assert [citation.chunk_id for citation in result] == ["chunk-2", "chunk-1", "chunk-3"]
        assert result[1].score == 0.7

    def test_round_cap_is_enforced(self) -> None:
        service = _FakeService({})

        def analyzer(query, citations):
            return [f"{query}-next"]

        run_iterative_retrieval(
            service, RetrievalLoopRequest("task.loop", "q", Clearance.internal, max_rounds=2), gap_analyzer=analyzer,
        )
        assert service.calls == ["q", "q-next"]

    def test_empty_gap_analysis_stops_early(self) -> None:
        service = _FakeService({"q": ()})
        run_iterative_retrieval(
            service, RetrievalLoopRequest("task.loop", "q", Clearance.internal, max_rounds=3),
            gap_analyzer=lambda query, citations: (),
        )
        assert service.calls == ["q"]


class TestRerankerAdapters:
    def test_function_adapter_and_retrieval_bridge(self) -> None:
        adapter = FunctionRerankerAdapter(
            model_id="fixture.reranker", qualification_reference="qualification.fixture",
            scorer=lambda query, passages: [len(passage) for passage in passages],
        )
        assert adapter.rerank("q", ["a", "bb"]) == (1.0, 2.0)

        class _Chunk:
            def __init__(self, text: str) -> None:
                self.text = text

        bridge = RetrievalReranker(adapter)
        assert bridge.score("q", (_Chunk("a"), _Chunk("bb"))) == (1.0, 2.0)

    def test_adapter_rejects_wrong_score_count(self) -> None:
        adapter = FunctionRerankerAdapter(
            model_id="fixture.reranker", qualification_reference="qualification.fixture",
            scorer=lambda query, passages: [1.0],
        )
        with pytest.raises(RerankerAdapterError):
            adapter.rerank("q", ["a", "b"])

    def test_env_selection(self) -> None:
        assert build_reranker_from_env({}) is None
        with pytest.raises(RerankerAdapterError):
            build_reranker_from_env({"AIRBENCH_RERANKER_ADAPTER": "vllm"})
        with pytest.raises(RerankerAdapterError):
            build_reranker_from_env({"AIRBENCH_RERANKER_ADAPTER": "mystery"})
