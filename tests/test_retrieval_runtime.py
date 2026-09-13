"""Real local BGE retrieval runtime integration tests.

The provider-neutral interfaces are exercised with deterministic fakes so the
suite stays offline and fast.  A real BGE-M3 / reranker load is gated behind
``AIRBENCH_TEST_REAL_BGE=1`` because it loads multi-gigabyte models.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

# Native import order: the torch stack must precede pypdf (File Intake) or the
# process can crash on Windows.  Only needed for the real-model test.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
if os.environ.get("AIRBENCH_TEST_REAL_BGE") == "1":
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        pass

import httpx
from fastapi import FastAPI

from airbench.knowledge.embedding_runtime import (
    EmbeddingRuntimeError,
    build_retrieval_runtime,
)
from airbench.knowledge.retrieval import DeterministicEmbeddingProvider, LexicalReranker
from airbench.node.server import add_retrieval_route

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_STORE = REPO_ROOT / "airbench-models"


def _fake_runtime():
    return build_retrieval_runtime(
        model_store=str(REPO_ROOT),
        embedding_provider=DeterministicEmbeddingProvider(dimension=8),
        reranker=LexicalReranker(),
    )


class RetrievalRuntimeTests(unittest.TestCase):
    def test_builds_with_injected_providers(self) -> None:
        runtime = _fake_runtime()
        self.assertEqual(runtime.embedding_model_id, "fixture.embedding")
        self.assertEqual(runtime.reranker_model_id, "fixture.reranker")
        self.assertEqual(len(runtime.index.chunks), 0)
        self.assertTrue(callable(runtime.service.search))
        self.assertTrue(callable(runtime.indexer.index_manifest))

    def test_repo_id_is_rejected(self) -> None:
        with self.assertRaises(EmbeddingRuntimeError):
            build_retrieval_runtime(model_store=str(REPO_ROOT), embedding_dir="BAAI/bge-m3")

    @unittest.skipUnless(
        os.environ.get("AIRBENCH_TEST_REAL_BGE") == "1" and (MODEL_STORE / "bge-m3").is_dir(),
        "set AIRBENCH_TEST_REAL_BGE=1 with the BGE models staged to run the real load",
    )
    def test_real_bge_m3_runtime_loads_and_embeds(self) -> None:  # pragma: no cover - heavy
        runtime = build_retrieval_runtime(model_store=str(MODEL_STORE))
        vector = runtime.service._embeddings.embed("pump discharge pressure")
        self.assertGreater(len(vector), 0)
        self.assertEqual(len(vector), 1024)


class _Index:
    chunks: tuple = ()


class _Runtime:
    embedding_model_id = "bge-m3"
    embedding_qualification_reference = "cert-bge-m3-embedding-v0"
    reranker_model_id = "bge-reranker-v2-m3"
    reranker_qualification_reference = "cert-bge-reranker-v2-m3-reranking-v0"
    index = _Index()


class _Service:
    def __init__(self, runtime) -> None:
        self.retrieval = runtime


class RetrievalRouteTests(unittest.TestCase):
    def _get(self, app, path: str) -> httpx.Response:
        async def run() -> httpx.Response:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://node.retrieval") as client:
                return await client.get(path)
        return asyncio.run(run())

    def test_route_reports_disabled_without_runtime(self) -> None:
        app = FastAPI()
        add_retrieval_route(app, _Service(None))
        resp = self._get(app, "/api/v1/node/retrieval")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["configured"])

    def test_route_reports_configured_runtime(self) -> None:
        app = FastAPI()
        add_retrieval_route(app, _Service(_Runtime()))
        resp = self._get(app, "/api/v1/node/retrieval")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["configured"])
        self.assertEqual(body["embedding_model"], "bge-m3")
        self.assertEqual(body["reranker_model"], "bge-reranker-v2-m3")


if __name__ == "__main__":
    unittest.main()
