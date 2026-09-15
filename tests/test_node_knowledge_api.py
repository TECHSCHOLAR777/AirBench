from __future__ import annotations

import asyncio
import tempfile
import unittest
from hashlib import sha256

import httpx

from airbench.knowledge.embedding_runtime import build_retrieval_runtime
from airbench.knowledge.retrieval import DeterministicEmbeddingProvider, IndexChunk, LexicalReranker
from airbench.knowledge.vector_store import SqliteVectorStore
from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from contracts import Clearance, EventLedger, Orchestrator, Taint


class NodeKnowledgeApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.ledger = EventLedger()
        self.embeddings = DeterministicEmbeddingProvider()
        self.store = SqliteVectorStore(f"{self.directory.name}/index.sqlite")
        self.runtime = build_retrieval_runtime(
            model_store=self.directory.name,
            embedding_provider=self.embeddings,
            reranker=LexicalReranker(),
            vector_store=self.store,
            ledger=self.ledger,
        )
        self.runtime.index.upsert((self._chunk("chunk-1", "seal leakage requires isolation"),))
        self.service = NodeApiService(
            Orchestrator(self.ledger),
            NodeApiConfig(
                node_identity="node.knowledge.test", protocol_version="0.1",
                clearance_context=Clearance.internal, authenticated_subject="principal.api",
                domain_pack_ref="pack.refinery.v0", bearer_token="test-token",
                handshake_ledger_event_ref="ledger.handshake.test",
                sovereignty_evidence_ref="evidence.sovereignty.test",
                require_orchestrator_authorization=False,
            ),
            retrieval=self.runtime,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.service)), base_url="http://node.knowledge.test",
        )

    def tearDown(self):
        asyncio.run(self.client.aclose())
        self.store.close()
        self.directory.cleanup()

    def _chunk(self, chunk_id, text):
        return IndexChunk(
            chunk_id=chunk_id, intake_id="intake-1", revision_id="revision-1",
            source_ref="local:manual.pdf", page_id="page-1", source_span="page:1", text=text,
            content_hash=sha256(text.encode()).hexdigest(), confidence=0.9,
            clearance=Clearance.internal, taint=Taint.untrusted, embedding=self.embeddings.embed(text),
            embedding_model="fixture.embedding", qualification_reference="qualification.fixture",
        )

    def _request(self, method, path, **kwargs):
        async def run():
            return await self.client.request(method, path, headers={"Authorization": "Bearer test-token"}, **kwargs)

        return asyncio.run(run())

    def test_status_reports_store_and_counts(self):
        status = self._request("GET", "/api/v1/knowledge/status")
        self.assertEqual(status.status_code, 200, status.text)
        body = status.json()
        self.assertTrue(body["configured"])
        self.assertEqual(body["indexed_chunks"], 1)
        self.assertEqual(body["vector_store"], "SqliteVectorStore")
        self.assertEqual(body["store_chunk_count"], 1)

    def test_search_returns_cited_results(self):
        response = self._request("POST", "/api/v1/knowledge/search", json={"query": "seal leakage", "top_k": 3})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["result_count"], 1)
        result = body["results"][0]
        self.assertEqual(result["chunk_id"], "chunk-1")
        self.assertEqual(result["taint"], "untrusted")
        self.assertEqual(result["clearance"], "internal")
        self.assertTrue(result["source_span"])
        event_types = [event.event_type for event in self.ledger.events]
        self.assertIn("task.created", event_types)
        self.assertIn("retrieval.requested", event_types)
        self.assertIn("retrieval.completed", event_types)
        repeated = self._request("POST", "/api/v1/knowledge/search", json={"query": "seal leakage", "top_k": 3})
        self.assertEqual(repeated.status_code, 200, repeated.text)

    def test_search_rejects_clearance_widening(self):
        response = self._request(
            "POST", "/api/v1/knowledge/search",
            json={"query": "seal leakage", "clearance": "restricted"},
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_search_requires_authentication(self):
        async def run():
            return await self.client.post("/api/v1/knowledge/search", json={"query": "x"})

        self.assertEqual(asyncio.run(run()).status_code, 401)

    def test_guarded_directory_ingest_indexes_files(self):
        from pathlib import Path

        from airbench.intake.layer import FileIntakeLayer
        from airbench.node.knowledge_gateway import LocalNodeKnowledgeService

        root = Path(self.directory.name) / "corpus"
        root.mkdir()
        (root / "sop.txt").write_text("seal leakage requires isolation and a work permit", encoding="utf-8")
        task_id = "task.knowledge.ingest"
        self.service.orchestrator.create_task(
            principal_id="principal.api", clearance=Clearance.internal,
            request="Bulk knowledge ingestion", domain_pack_ref="pack.refinery.v0",
            risk_class="low", autonomy_ceiling="system", task_id=task_id,
        )
        self.service.knowledge = LocalNodeKnowledgeService(
            layer=FileIntakeLayer(self.ledger),
            indexer=self.runtime.indexer,
            ingest_root=root,
            task_id=task_id,
            clearance_context=Clearance.internal,
        )
        response = self._request("POST", "/api/v1/knowledge/ingest", json={"path": "."})
        self.assertEqual(response.status_code, 202, response.text)
        body = response.json()
        self.assertEqual(body["file_count"], 1)
        self.assertGreaterEqual(body["chunk_count"], 1)
        status = self._request("GET", "/api/v1/knowledge/status")
        self.assertGreaterEqual(status.json()["store_chunk_count"], 1)

    def test_ingest_rejects_path_outside_root(self):
        from pathlib import Path

        from airbench.intake.layer import FileIntakeLayer
        from airbench.node.knowledge_gateway import LocalNodeKnowledgeService

        root = Path(self.directory.name) / "corpus"
        root.mkdir()
        self.service.knowledge = LocalNodeKnowledgeService(
            layer=FileIntakeLayer(self.ledger), indexer=self.runtime.indexer,
            ingest_root=root, task_id="task.knowledge.ingest", clearance_context=Clearance.internal,
        )
        response = self._request("POST", "/api/v1/knowledge/ingest", json={"path": "../"})
        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
