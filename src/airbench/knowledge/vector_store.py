"""Durable vector stores for the local knowledge index.

The core declares ``VectorStore`` in ``retrieval.py``; this module provides
real implementations.  ``SqliteVectorStore`` is stdlib-only, file-backed, and
offline, so the index survives a Node restart without re-embedding.
``ChromaVectorStore`` is an optional adapter around a local Chroma collection
and is imported lazily so ``chromadb`` never becomes a hard dependency.

Both stores preserve the full ``IndexChunk`` provenance: source, revision,
page, span, clearance, taint, content hash, embedding model, and qualification
reference.  Search filters by the caller's clearance before returning results.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from threading import RLock
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Sequence

from contracts import Clearance, Taint

from .retrieval import IndexChunk, RetrievalError


class VectorStoreError(RuntimeError):
    """A durable vector store could not be opened or used."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _rank(clearance: Clearance) -> int:
    return {
        Clearance.public: 0,
        Clearance.internal: 1,
        Clearance.restricted: 2,
        Clearance.secret: 3,
    }[clearance]


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        return -1.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _encode(chunk: IndexChunk) -> str:
    return json.dumps({
        "chunk_id": chunk.chunk_id, "intake_id": chunk.intake_id, "revision_id": chunk.revision_id,
        "source_ref": chunk.source_ref, "page_id": chunk.page_id, "source_span": chunk.source_span,
        "text": chunk.text, "content_hash": chunk.content_hash, "confidence": chunk.confidence,
        "clearance": chunk.clearance.value, "taint": chunk.taint.value,
        "embedding": list(chunk.embedding), "embedding_model": chunk.embedding_model,
        "qualification_reference": chunk.qualification_reference, "revision_state": chunk.revision_state,
    }, sort_keys=True, separators=(",", ":"))


def _decode(payload: str) -> IndexChunk:
    item = json.loads(payload)
    return IndexChunk(
        chunk_id=item["chunk_id"], intake_id=item["intake_id"], revision_id=item["revision_id"],
        source_ref=item["source_ref"], page_id=item["page_id"], source_span=item["source_span"],
        text=item["text"], content_hash=item["content_hash"], confidence=item["confidence"],
        clearance=Clearance(item["clearance"]), taint=Taint(item["taint"]),
        embedding=tuple(item["embedding"]), embedding_model=item["embedding_model"],
        qualification_reference=item["qualification_reference"],
        revision_state=item.get("revision_state", "current"),
    )


class SqliteVectorStore:
    """File-backed, offline vector store using only the standard library.

    The store applies intake-consistent supersession: a new revision of the
    same ``source_ref`` marks the prior current revision superseded instead of
    overwriting it.  Search is a bounded cosine scan over current rows after a
    clearance filter, which is appropriate for a single-node local index.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        try:
            self._connection = sqlite3.connect(str(self._path), check_same_thread=False, timeout=30.0)
        except sqlite3.Error as exc:
            raise VectorStoreError("store_open_failed", "the vector store could not be opened") from exc
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS chunks ("
            "chunk_id TEXT PRIMARY KEY, source_ref TEXT NOT NULL, revision_id TEXT NOT NULL, "
            "revision_state TEXT NOT NULL, clearance_rank INTEGER NOT NULL, embedding TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._connection.close()
            except sqlite3.Error:
                pass

    @property
    def chunks(self) -> tuple[IndexChunk, ...]:
        with self._lock:
            return tuple(_decode(row[0]) for row in self._connection.execute("SELECT payload FROM chunks"))

    @property
    def chunk_count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) FROM chunks").fetchone()
            return int(row[0]) if row else 0

    def upsert(self, chunks: Iterable[IndexChunk]) -> None:
        incoming = tuple(chunks)
        with self._lock:
            try:
                cursor = self._connection.cursor()
                for chunk in incoming:
                    rows = cursor.execute(
                        "SELECT chunk_id, payload FROM chunks WHERE source_ref = ? AND revision_state = 'current' AND revision_id != ?",
                        (chunk.source_ref, chunk.revision_id),
                    ).fetchall()
                    for chunk_id, payload in rows:
                        superseded = _decode(payload)
                        cursor.execute(
                            "UPDATE chunks SET revision_state = 'superseded', payload = ? WHERE chunk_id = ?",
                            (_encode(replace(superseded, revision_state="superseded")), chunk_id),
                        )
                    cursor.execute(
                        "INSERT OR REPLACE INTO chunks (chunk_id, source_ref, revision_id, revision_state, clearance_rank, embedding, payload) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            chunk.chunk_id, chunk.source_ref, chunk.revision_id, chunk.revision_state,
                            _rank(chunk.clearance), json.dumps(list(chunk.embedding)), _encode(chunk),
                        ),
                    )
                self._connection.commit()
            except sqlite3.Error as exc:
                self._connection.rollback()
                raise VectorStoreError("store_write_failed", "the vector store could not be written") from exc

    def search(self, embedding: tuple[float, ...], clearance: Clearance, limit: int) -> tuple[IndexChunk, ...]:
        if limit < 1:
            raise RetrievalError("invalid_limit", "search limit must be positive")
        max_rank = _rank(clearance)
        with self._lock:
            candidates: list[tuple[float, IndexChunk]] = []
            for weight, payload in self._connection.execute(
                "SELECT clearance_rank, payload FROM chunks WHERE revision_state = 'current' AND clearance_rank <= ?",
                (max_rank,),
            ):
                del weight  # already filtered by the query
                chunk = _decode(payload)
                candidates.append((_cosine(embedding, chunk.embedding), chunk))
            candidates.sort(key=lambda item: (-item[0], item[1].chunk_id))
            return tuple(chunk for _, chunk in candidates[:limit])


class ChromaVectorStore:
    """Optional adapter around a local, file-backed Chroma collection.

    ``chromadb`` is imported lazily and must be a local persistent client.  A
    missing dependency raises a typed error instead of silently degrading.
    """

    def __init__(self, path: str | Path, *, collection: str = "airbench") -> None:
        # Chroma's anonymised telemetry phones home by default; disable it before
        # the import so the local store can never make an external call.
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "False")
        try:
            import chromadb  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise VectorStoreError("store_unavailable", "chromadb is required for the Chroma vector store") from exc
        # Defensive no-egress: even if a Chroma build ignores the telemetry
        # setting, neutralise its capture call entirely.
        try:
            import chromadb.telemetry.product.posthog as _chroma_posthog  # type: ignore[import-not-found]

            _chroma_posthog.Posthog.capture = lambda self, *args, **kwargs: None
            _chroma_posthog.Posthog.capture_batch = lambda self, *args, **kwargs: None
        except Exception:  # pragma: no cover - hardening must never fail the store
            pass
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)
        try:
            from chromadb.config import Settings  # type: ignore[import-not-found]

            self._client = chromadb.PersistentClient(
                path=str(self._path), settings=Settings(anonymized_telemetry=False)
            )
            self._collection = self._client.get_or_create_collection(name=collection, metadata={"hnsw:space": "cosine"})
        except Exception as exc:  # pragma: no cover - optional dependency
            raise VectorStoreError("store_open_failed", "the Chroma collection could not be opened") from exc

    @property
    def chunks(self) -> tuple[IndexChunk, ...]:
        result = self._collection.get(include=["embeddings", "metadatas", "documents"])
        return _chroma_to_chunks(result)

    @property
    def chunk_count(self) -> int:
        """Return the durable collection count without loading embeddings."""
        return int(self._collection.count())

    def upsert(self, chunks: Iterable[IndexChunk]) -> None:
        incoming = tuple(chunks)
        if not incoming:
            return
        revisions = {(chunk.source_ref, chunk.revision_id) for chunk in incoming}
        for source_ref, revision_id in revisions:
            stale = self._collection.get(where={"source_ref": source_ref}, include=["metadatas"])
            for metadata in stale.get("metadatas") or ():
                if metadata and metadata.get("revision_state") == "current" and metadata.get("revision_id") != revision_id:
                    self._collection.update(ids=[metadata["chunk_id"]], metadatas=[{**metadata, "revision_state": "superseded"}])
        self._collection.upsert(
            ids=[chunk.chunk_id for chunk in incoming],
            embeddings=[list(chunk.embedding) for chunk in incoming],
            documents=[chunk.text for chunk in incoming],
            metadatas=[_chunk_metadata(chunk) for chunk in incoming],
        )

    def search(self, embedding: tuple[float, ...], clearance: Clearance, limit: int) -> tuple[IndexChunk, ...]:
        if limit < 1:
            raise RetrievalError("invalid_limit", "search limit must be positive")
        result = self._collection.query(
            query_embeddings=[list(embedding)],
            n_results=limit,
            where={"$and": [{"revision_state": "current"}, {"clearance_rank": {"$lte": _rank(clearance)}}]},
            include=["embeddings", "metadatas", "documents"],
        )
        return _chroma_to_chunks(result)


def _chunk_metadata(chunk: IndexChunk) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id, "intake_id": chunk.intake_id, "revision_id": chunk.revision_id,
        "source_ref": chunk.source_ref, "page_id": chunk.page_id, "source_span": chunk.source_span,
        "content_hash": chunk.content_hash, "confidence": chunk.confidence,
        "clearance": chunk.clearance.value, "clearance_rank": _rank(chunk.clearance), "taint": chunk.taint.value,
        "embedding_model": chunk.embedding_model, "qualification_reference": chunk.qualification_reference,
        "revision_state": chunk.revision_state,
    }


def _to_pylist(value: Any) -> list:
    """Normalise a Chroma value (possibly a numpy array) to a Python list."""
    if value is None:
        return []
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _chroma_to_chunks(result: dict) -> tuple[IndexChunk, ...]:
    metadatas = _to_pylist(result.get("metadatas"))
    documents = _to_pylist(result.get("documents"))
    embeddings = _to_pylist(result.get("embeddings"))
    # ``query`` returns one extra level of nesting (per query) than ``get``.
    nested = bool(metadatas) and isinstance(metadatas[0], list)
    if nested:
        metadatas = metadatas[0]
        documents = _to_pylist(documents[0]) if documents else []
        embeddings = _to_pylist(embeddings[0]) if embeddings else []
    chunks: list[IndexChunk] = []
    for index, metadata in enumerate(metadatas or ()):
        if not metadata:
            continue
        embedding = embeddings[index] if index < len(embeddings) else ()
        text = documents[index] if index < len(documents) else ""
        chunks.append(IndexChunk(
            chunk_id=metadata["chunk_id"], intake_id=metadata["intake_id"], revision_id=metadata["revision_id"],
            source_ref=metadata["source_ref"], page_id=metadata["page_id"], source_span=metadata["source_span"],
            text=text, content_hash=metadata["content_hash"], confidence=metadata["confidence"],
            clearance=Clearance(metadata["clearance"]), taint=Taint(metadata["taint"]),
            embedding=tuple(float(value) for value in embedding), embedding_model=metadata["embedding_model"],
            qualification_reference=metadata["qualification_reference"],
            revision_state=metadata.get("revision_state", "current"),
        ))
    return tuple(chunks)


def build_vector_store_from_env(
    env: dict[str, str] | None = None,
) -> object | None:
    """Build the configured durable store, or ``None`` for the built-in JSON seam.

    ``AIRBENCH_VECTOR_STORE`` accepts ``json`` (default), ``sqlite``, or
    ``chroma``.  ``AIRBENCH_VECTOR_STORE_PATH`` sets the on-disk location.
    """

    values = os.environ if env is None else env
    selected = values.get("AIRBENCH_VECTOR_STORE", "json").strip().lower() or "json"
    if selected in {"json", "none", "memory"}:
        return None
    path = values.get("AIRBENCH_VECTOR_STORE_PATH", "").strip()
    if not path:
        raise VectorStoreError("store_path_required", "AIRBENCH_VECTOR_STORE_PATH is required for a durable vector store")
    if selected == "sqlite":
        return SqliteVectorStore(path)
    if selected == "chroma":
        return ChromaVectorStore(path)
    raise VectorStoreError("unknown_store", "AIRBENCH_VECTOR_STORE must be json, sqlite, or chroma")


__all__ = [
    "ChromaVectorStore",
    "SqliteVectorStore",
    "VectorStoreError",
    "build_vector_store_from_env",
]
