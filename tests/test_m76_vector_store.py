from __future__ import annotations

from hashlib import sha256

import pytest

from airbench.knowledge.retrieval import IndexChunk, LocalVectorIndex
from airbench.knowledge.vector_store import (
    ChromaVectorStore,
    SqliteVectorStore,
    VectorStoreError,
    build_vector_store_from_env,
)
from contracts import Clearance, Taint


def _chunk(
    chunk_id: str,
    *,
    source_ref: str = "local:report.pdf",
    revision_id: str = "revision-1",
    text: str = "seal leakage requires isolation",
    embedding: tuple[float, ...] = (1.0, 0.0),
    clearance: Clearance = Clearance.internal,
    revision_state: str = "current",
) -> IndexChunk:
    return IndexChunk(
        chunk_id=chunk_id,
        intake_id="intake-1",
        revision_id=revision_id,
        source_ref=source_ref,
        page_id="page-1",
        source_span="page:1",
        text=text,
        content_hash=sha256(text.encode()).hexdigest(),
        confidence=0.9,
        clearance=clearance,
        taint=Taint.untrusted,
        embedding=embedding,
        embedding_model="fixture.embedding",
        qualification_reference="qualification.fixture",
        revision_state=revision_state,
    )


class TestSqliteVectorStore:
    def test_upsert_search_and_clearance_filter(self, tmp_path) -> None:
        store = SqliteVectorStore(tmp_path / "index.sqlite")
        store.upsert((
            _chunk("chunk-public", embedding=(1.0, 0.0), clearance=Clearance.public),
            _chunk("chunk-restricted", source_ref="local:secret.pdf", embedding=(1.0, 0.0), clearance=Clearance.restricted),
        ))
        assert {chunk.chunk_id for chunk in store.search((1.0, 0.0), Clearance.internal, 10)} == {"chunk-public"}
        assert {chunk.chunk_id for chunk in store.search((1.0, 0.0), Clearance.restricted, 10)} == {"chunk-public", "chunk-restricted"}

    def test_restart_preserves_chunks_without_reembedding(self, tmp_path) -> None:
        path = tmp_path / "index.sqlite"
        first = SqliteVectorStore(path)
        first.upsert((_chunk("chunk-1"),))
        first.close()
        second = SqliteVectorStore(path)
        assert second.chunk_count == 1
        assert second.chunks[0].chunk_id == "chunk-1"
        assert second.chunks[0].embedding == (1.0, 0.0)
        assert second.search((1.0, 0.0), Clearance.internal, 5)[0].chunk_id == "chunk-1"

    def test_new_revision_supersedes_old(self, tmp_path) -> None:
        store = SqliteVectorStore(tmp_path / "index.sqlite")
        store.upsert((_chunk("chunk-old", revision_id="revision-1", text="old text"),))
        store.upsert((_chunk("chunk-new", revision_id="revision-2", text="new text"),))
        states = {chunk.chunk_id: chunk.revision_state for chunk in store.chunks}
        assert states == {"chunk-old": "superseded", "chunk-new": "current"}
        assert [chunk.chunk_id for chunk in store.search((1.0, 0.0), Clearance.internal, 5)] == ["chunk-new"]


class TestLocalVectorIndexStoreInjection:
    def test_facade_delegates_to_injected_store(self, tmp_path) -> None:
        store = SqliteVectorStore(tmp_path / "index.sqlite")
        index = LocalVectorIndex(store=store)
        index.upsert((_chunk("chunk-1"),))
        assert index.store is store
        assert [chunk.chunk_id for chunk in index.chunks] == ["chunk-1"]
        assert index.search((1.0, 0.0), Clearance.internal, 5)[0].chunk_id == "chunk-1"


class TestVectorStoreSelection:
    def test_env_selection(self, tmp_path) -> None:
        assert build_vector_store_from_env({}) is None
        assert build_vector_store_from_env({"AIRBENCH_VECTOR_STORE": "json"}) is None
        store = build_vector_store_from_env({
            "AIRBENCH_VECTOR_STORE": "sqlite",
            "AIRBENCH_VECTOR_STORE_PATH": str(tmp_path / "index.sqlite"),
        })
        assert isinstance(store, SqliteVectorStore)

    def test_env_missing_path_and_unknown(self) -> None:
        with pytest.raises(VectorStoreError):
            build_vector_store_from_env({"AIRBENCH_VECTOR_STORE": "sqlite"})
        with pytest.raises(VectorStoreError):
            build_vector_store_from_env({"AIRBENCH_VECTOR_STORE": "mystery", "AIRBENCH_VECTOR_STORE_PATH": "x"})

    def test_chroma_requires_optional_dependency(self) -> None:
        import importlib.util

        if importlib.util.find_spec("chromadb") is not None:
            pytest.skip("chromadb is installed; the unavailable-dependency path does not apply")
        with pytest.raises(VectorStoreError):
            ChromaVectorStore("unused-path")
