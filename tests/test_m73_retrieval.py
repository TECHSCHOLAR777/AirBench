from __future__ import annotations

import unittest
import time
from dataclasses import replace
from tempfile import TemporaryDirectory

from airbench.intake import IntakeManifest, IntakeMode, PageRecord
from airbench.knowledge.retrieval import (
    DeterministicEmbeddingProvider,
    IndexRequest,
    LexicalReranker,
    LocalIndexer,
    LocalVectorIndex,
    QualifiedEmbeddingProvider,
    QualifiedReranker,
    RetrievalError,
    RetrievalRequest,
    RetrievalService,
)
from contracts import Clearance, EventLedger, Taint, build_event


def seed_task(ledger: EventLedger, task_id: str) -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
        clearance=Clearance.restricted, idempotency=f"created-{task_id}", sequence=0,
    ))


def manifest() -> IntakeManifest:
    return IntakeManifest(
        intake_id="intake.m73", task_id="task.m73", source_ref="upload:report.pdf", revision_id="revision.m73",
        source_hash="a" * 64, file_name="report.pdf", media_type="application/pdf", byte_size=10,
        page_count=2, parser_name="test", parser_version="1", extraction_settings={},
        pages=(
            PageRecord("page.public", 1, "page-1", "b" * 64, "text/plain", "pump pressure normal", "pdf.text", .9, Clearance.internal, Taint.untrusted, "evidence.1"),
            PageRecord("page.secret", 2, "page-2", "c" * 64, "text/plain", "secret maintenance bypass", "pdf.text", .9, Clearance.secret, Taint.untrusted, "evidence.2"),
        ),
        mode=IntakeMode.bulk_ingest, clearance=Clearance.secret, taint=Taint.untrusted, confidence=.9,
        ledger_event_ref="event.evidence", ingested_at="2026-01-01T00:00:00Z",
        destination="permanent_knowledge", trust_profile="bulk_candidate", latency_profile="offline_enrichment",
    )


class RetrievalTests(unittest.TestCase):
    def test_index_and_retrieval_preserve_citations_and_clearance(self) -> None:
        ledger = EventLedger()
        seed_task(ledger, "task.m73")
        index = LocalVectorIndex()
        embeddings = DeterministicEmbeddingProvider()
        LocalIndexer(index, embeddings, ledger=ledger).index_manifest(IndexRequest("task.m73", manifest()))
        result = RetrievalService(index, embeddings, reranker=LexicalReranker(), ledger=ledger).search(
            RetrievalRequest("task.m73", "pump pressure", Clearance.internal, top_k=5, max_excerpt_chars=10)
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_ref, "upload:report.pdf")
        self.assertEqual(result[0].page_id, "page.public")
        self.assertLessEqual(len(result[0].excerpt), 10)
        self.assertEqual(result[0].taint, Taint.untrusted)
        self.assertEqual(result[0].confidence, .9)
        self.assertEqual(ledger.events[-1].event_type, "retrieval.completed")

    def test_secret_chunks_are_not_exposed_to_lower_clearance(self) -> None:
        index = LocalVectorIndex()
        embeddings = DeterministicEmbeddingProvider()
        LocalIndexer(index, embeddings).index_manifest(IndexRequest("task.m73", manifest()))
        internal = RetrievalService(index, embeddings).search(RetrievalRequest("task.m73", "secret", Clearance.internal))
        restricted = RetrievalService(index, embeddings).search(RetrievalRequest("task.m73", "secret", Clearance.secret))
        self.assertTrue(all(item.page_id != "page.secret" for item in internal))
        self.assertTrue(any(item.page_id == "page.secret" for item in restricted))

    def test_invalid_limits_fail_before_search(self) -> None:
        with self.assertRaisesRegex(Exception, "retrieval limits"):
            RetrievalRequest("task.m73", "query", Clearance.internal, top_k=0)

    def test_superseded_revisions_remain_auditable_but_are_not_returned(self) -> None:
        index = LocalVectorIndex()
        embeddings = DeterministicEmbeddingProvider()
        old = IndexRequest("task.m73", manifest(), revision_state="superseded")
        chunks = LocalIndexer(index, embeddings).index_manifest(old)
        self.assertEqual(chunks[0].revision_state, "superseded")
        self.assertEqual(RetrievalService(index, embeddings).search(RetrievalRequest("task.m73", "pump", Clearance.secret)), ())

    def test_new_revision_supersedes_previous_current_chunks(self) -> None:
        index = LocalVectorIndex()
        embeddings = DeterministicEmbeddingProvider()
        LocalIndexer(index, embeddings).index_manifest(IndexRequest("task.m73", manifest()))
        newer = replace(manifest(), revision_id="revision.m73.new", source_hash="d" * 64)
        LocalIndexer(index, embeddings).index_manifest(IndexRequest("task.m73", newer))
        self.assertTrue(any(chunk.revision_state == "superseded" and chunk.revision_id == "revision.m73" for chunk in index.chunks))
        results = RetrievalService(index, embeddings).search(RetrievalRequest("task.m73", "pump", Clearance.internal))
        self.assertTrue(results)
        self.assertTrue(all(result.revision_id == "revision.m73.new" for result in results))

    def test_persistent_index_survives_restart(self) -> None:
        with TemporaryDirectory() as directory:
            path = f"{directory}/index.json"
            first = LocalVectorIndex(path)
            LocalIndexer(first, DeterministicEmbeddingProvider()).index_manifest(IndexRequest("task.m73", manifest()))
            second = LocalVectorIndex(path)
            self.assertEqual(len(second.chunks), len(first.chunks))
            self.assertEqual(second.chunks[0].source_ref, first.chunks[0].source_ref)

    def test_qualified_providers_enforce_input_and_timeout_limits(self) -> None:
        embedding = QualifiedEmbeddingProvider(
            "embedding.test", "qualification.test", 2, lambda _: (0.1, 0.2), max_input_chars=4,
        )
        with self.assertRaisesRegex(RetrievalError, "exceeds"):
            embedding.embed("too long")
        slow_embedding = QualifiedEmbeddingProvider(
            "embedding.test", "qualification.test", 2, lambda _: (time.sleep(.05) or (0.1, 0.2)), timeout_s=.001,
        )
        with self.assertRaisesRegex(RetrievalError, "timed out"):
            slow_embedding.embed("ok")
        with self.assertRaises(RetrievalError):
            QualifiedReranker("reranker.test", "qualification.test", lambda _, chunks: (1.0 for _ in chunks), max_chunks=0)

    def test_index_storage_limit_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            index = LocalVectorIndex(f"{directory}/index.json", max_file_bytes=1)
            with self.assertRaisesRegex(RetrievalError, "configured limit"):
                LocalIndexer(index, DeterministicEmbeddingProvider()).index_manifest(IndexRequest("task.m73", manifest()))


if __name__ == "__main__":
    unittest.main()
