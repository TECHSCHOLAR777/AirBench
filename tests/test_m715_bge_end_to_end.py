"""End-to-end retrieval with the real local BGE models and a Chroma store.

These tests load multi-GB local models, so they are opt-in:

    AIRBENCH_RUN_MODEL_TESTS=1 pytest tests/test_m715_bge_end_to_end.py

The models are read from the local ``airbench-models`` directory only; the
runtime rejects Hugging Face repo ids, so no network call can occur.
"""

from __future__ import annotations

import asyncio
import os
from hashlib import sha256
from pathlib import Path

import pytest

RUN_MODEL_TESTS = os.environ.get("AIRBENCH_RUN_MODEL_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}
pytestmark = pytest.mark.skipif(not RUN_MODEL_TESTS, reason="set AIRBENCH_RUN_MODEL_TESTS=1 to run real model tests")

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_STORE = REPO_ROOT / "airbench-models"
EMBEDDING_DIR = MODEL_STORE / "bge-m3"
RERANKER_DIR = MODEL_STORE / "bge-reranker-v2-m3"

TEXTS = {
    "seal": "Seal leakage requires immediate isolation of the pump and a confined-space work permit.",
    "pressure": "Operating pressure must remain below the relief valve set point at all times.",
    "lubrication": "Lubrication of the drive bearing is scheduled every 500 operating hours.",
}


@pytest.fixture(scope="module")
def stack():
    import importlib.util

    if importlib.util.find_spec("sentence_transformers") is None:
        pytest.skip("sentence-transformers is not installed")
    assert EMBEDDING_DIR.is_dir(), f"missing local embedding model at {EMBEDDING_DIR}"
    assert RERANKER_DIR.is_dir(), f"missing local reranker model at {RERANKER_DIR}"
    from airbench.knowledge.embedding_runtime import local_embedding_provider, local_reranker

    embeddings = local_embedding_provider(
        EMBEDDING_DIR, model_id="bge-m3", qualification_reference="cert.bge-m3-embedding-v0",
    )
    # The cross-encoder needs several GB of commit space; on a memory-constrained
    # host it may fail to load.  The embedding + Chroma + Node path still runs.
    try:
        reranker = local_reranker(
            RERANKER_DIR, model_id="bge-reranker-v2-m3", qualification_reference="cert.bge-reranker-v2-m3-reranking-v0",
        )
    except Exception:  # noqa: BLE001 - resource-dependent optional engine
        reranker = None
    return embeddings, reranker


def _chunks(embeddings):
    from airbench.knowledge.retrieval import IndexChunk
    from contracts import Clearance, Taint

    return tuple(
        IndexChunk(
            chunk_id=f"chunk-{key}", intake_id="intake-1", revision_id="revision-1",
            source_ref=f"local:{key}.pdf", page_id="page-1", source_span="page:1", text=text,
            content_hash=sha256(text.encode()).hexdigest(), confidence=0.9,
            clearance=Clearance.internal, taint=Taint.untrusted, embedding=embeddings.embed(text),
            embedding_model=embeddings.model_id, qualification_reference=embeddings.qualification_reference,
        )
        for key, text in TEXTS.items()
    )


def _index(tmp_path, embeddings):
    from airbench.knowledge.retrieval import LocalVectorIndex
    from airbench.knowledge.vector_store import ChromaVectorStore

    store = ChromaVectorStore(tmp_path / "chroma")
    index = LocalVectorIndex(store=store)
    index.upsert(_chunks(embeddings))
    return index


class TestRealRetrieval:
    def test_bge_embeddings_are_dense_and_normalised(self, stack):
        embeddings, _ = stack
        vector = embeddings.embed("seal leakage")
        assert len(vector) == 1024
        norm = sum(value * value for value in vector) ** 0.5
        assert norm == pytest.approx(1.0, abs=1e-3)

    def test_end_to_end_search_ranks_the_relevant_chunk_first(self, stack, tmp_path):
        from airbench.knowledge.retrieval import RetrievalRequest, RetrievalService
        from contracts import Clearance, Taint

        embeddings, reranker = stack
        index = _index(tmp_path, embeddings)
        service = RetrievalService(index, embeddings, reranker=reranker)
        results = service.search(RetrievalRequest("task.e2e", "seal leakage isolation procedure", Clearance.internal, top_k=3))
        assert results[0].chunk_id == "chunk-seal"
        assert results[0].source_span and results[0].clearance == Clearance.internal and results[0].taint == Taint.untrusted
        assert results[0].embedding_model == "bge-m3"

    def test_iterative_retrieval_merges_follow_up_rounds(self, stack, tmp_path):
        from airbench.knowledge.retrieval import RetrievalService
        from airbench.knowledge.retrieval_loop import RetrievalLoopRequest, run_iterative_retrieval
        from contracts import Clearance

        embeddings, reranker = stack
        service = RetrievalService(_index(tmp_path, embeddings), embeddings, reranker=reranker)
        merged = run_iterative_retrieval(
            service,
            RetrievalLoopRequest("task.e2e", "seal leakage", Clearance.internal, top_k=2, max_rounds=2),
            gap_analyzer=lambda query, citations: ("relief valve pressure",),
        )
        assert {citation.chunk_id for citation in merged} >= {"chunk-seal", "chunk-pressure"}

    def test_node_knowledge_search_end_to_end(self, stack, tmp_path):
        import httpx

        from airbench.knowledge.embedding_runtime import build_retrieval_runtime
        from airbench.knowledge.vector_store import ChromaVectorStore
        from airbench.node.api import NodeApiConfig, NodeApiService, create_app
        from contracts import Clearance, EventLedger, Orchestrator

        embeddings, reranker = stack
        if reranker is None:
            pytest.skip("the cross-encoder reranker could not be loaded in this environment")
        runtime = build_retrieval_runtime(
            model_store=MODEL_STORE, embedding_provider=embeddings, reranker=reranker,
            vector_store=ChromaVectorStore(tmp_path / "chroma"),
        )
        runtime.index.upsert(_chunks(embeddings))
        service = NodeApiService(
            Orchestrator(EventLedger()),
            NodeApiConfig(
                node_identity="node.e2e", protocol_version="0.1", clearance_context=Clearance.internal,
                authenticated_subject="principal.api", domain_pack_ref="pack.refinery.v0", bearer_token="token",
                handshake_ledger_event_ref="ledger.handshake", sovereignty_evidence_ref="evidence.sovereignty",
                require_orchestrator_authorization=False,
            ),
            retrieval=runtime,
        )
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(service)), base_url="http://node.e2e")

        async def run():
            try:
                return await client.post(
                    "/api/v1/knowledge/search",
                    headers={"Authorization": "Bearer token"},
                    json={"query": "seal leakage isolation", "top_k": 3},
                )
            finally:
                await client.aclose()

        response = asyncio.run(run())
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["result_count"] >= 1
        assert body["results"][0]["chunk_id"] == "chunk-seal"
        assert body["results"][0]["clearance"] == "internal"
