from __future__ import annotations

from hashlib import sha256

import pytest

from airbench.knowledge.retrieval import IndexChunk, LocalVectorIndex
from airbench.knowledge.vector_store import ChromaVectorStore, build_vector_store_from_env
from contracts import Clearance, Taint

pytest.importorskip("chromadb", reason="chromadb is an optional vector-store engine")


def _chunk(chunk_id: str, *, source_ref: str = "local:manual.pdf", revision_id: str = "revision-1",
           text: str = "seal leakage requires isolation", embedding: tuple[float, ...] = (1.0, 0.0, 0.0),
           clearance: Clearance = Clearance.internal) -> IndexChunk:
    return IndexChunk(
        chunk_id=chunk_id, intake_id="intake-1", revision_id=revision_id, source_ref=source_ref,
        page_id="page-1", source_span="page:1", text=text, content_hash=sha256(text.encode()).hexdigest(),
        confidence=0.9, clearance=clearance, taint=Taint.untrusted, embedding=embedding,
        embedding_model="fixture.embedding", qualification_reference="qualification.fixture",
    )


class TestChromaVectorStore:
    def test_upsert_search_and_clearance_filter(self, tmp_path) -> None:
        store = ChromaVectorStore(tmp_path / "chroma")
        store.upsert((
            _chunk("chunk-public", embedding=(1.0, 0.0, 0.0), clearance=Clearance.public),
            _chunk("chunk-restricted", source_ref="local:secret.pdf", embedding=(1.0, 0.0, 0.0), clearance=Clearance.restricted),
        ))
        assert {chunk.chunk_id for chunk in store.search((1.0, 0.0, 0.0), Clearance.internal, 10)} == {"chunk-public"}
        assert {chunk.chunk_id for chunk in store.search((1.0, 0.0, 0.0), Clearance.restricted, 10)} == {"chunk-public", "chunk-restricted"}

    def test_restart_preserves_chunks(self, tmp_path) -> None:
        path = tmp_path / "chroma"
        ChromaVectorStore(path).upsert((_chunk("chunk-1"),))
        reopened = ChromaVectorStore(path)
        assert {chunk.chunk_id for chunk in reopened.chunks} == {"chunk-1"}
        result = reopened.search((1.0, 0.0, 0.0), Clearance.internal, 5)
        assert result[0].chunk_id == "chunk-1"
        assert result[0].embedding == (1.0, 0.0, 0.0)

    def test_mixed_source_revision_batch_supersedes_each_source(self, tmp_path) -> None:
        store = ChromaVectorStore(tmp_path / "chroma")
        store.upsert((
            _chunk("manual-v1", source_ref="local:manual.pdf", revision_id="revision-1"),
            _chunk("sop-v1", source_ref="local:sop.pdf", revision_id="revision-1"),
        ))
        store.upsert((
            _chunk("manual-v2", source_ref="local:manual.pdf", revision_id="revision-2"),
            _chunk("sop-v2", source_ref="local:sop.pdf", revision_id="revision-2"),
        ))

        current = {chunk.chunk_id for chunk in store.search((1.0, 0.0, 0.0), Clearance.internal, 10)}
        assert current == {"manual-v2", "sop-v2"}

    def test_local_vector_index_delegates_to_chroma(self, tmp_path) -> None:
        store = ChromaVectorStore(tmp_path / "chroma")
        index = LocalVectorIndex(store=store)
        index.upsert((_chunk("chunk-1"),))
        assert index.store is store
        assert index.search((1.0, 0.0, 0.0), Clearance.internal, 5)[0].chunk_id == "chunk-1"

    def test_env_selection_builds_chroma(self, tmp_path) -> None:
        store = build_vector_store_from_env({"AIRBENCH_VECTOR_STORE": "chroma", "AIRBENCH_VECTOR_STORE_PATH": str(tmp_path / "chroma")})
        assert isinstance(store, ChromaVectorStore)
