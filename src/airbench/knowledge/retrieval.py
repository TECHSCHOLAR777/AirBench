"""Local indexing, embedding, reranking, and cited retrieval.

The index stores intake-derived chunks only. Providers are injected through
small typed interfaces so the core does not contain BGE or vendor logic.
"""

from __future__ import annotations

import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Protocol

from contracts import Clearance, EventLedger, Taint, build_event, stable_id

from airbench.intake.layer import IntakeManifest, PageRecord
from airbench.intake.vision import VisionResult


def _rank(clearance: Clearance) -> int:
    return {
        Clearance.public: 0,
        Clearance.internal: 1,
        Clearance.restricted: 2,
        Clearance.secret: 3,
    }[clearance]


class RetrievalError(RuntimeError):
    """A stable retrieval or indexing failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class IndexChunk:
    chunk_id: str
    intake_id: str
    revision_id: str
    source_ref: str
    page_id: str
    source_span: str
    text: str
    content_hash: str
    confidence: float
    clearance: Clearance
    taint: Taint
    embedding: tuple[float, ...]
    embedding_model: str
    qualification_reference: str
    revision_state: str = "current"

    def __post_init__(self) -> None:
        if not self.chunk_id or not self.source_ref or not self.page_id or not self.source_span:
            raise RetrievalError("invalid_chunk", "index chunk identity is required")
        if not self.text.strip() or not self.embedding or not self.embedding_model:
            raise RetrievalError("invalid_chunk", "index chunk text and embedding are required")
        if not 0 <= self.confidence <= 1:
            raise RetrievalError("invalid_confidence", "index confidence must be between zero and one")
        if self.taint == Taint.clean:
            raise RetrievalError("clean_input", "indexed intake content must remain untrusted")
        if self.revision_state not in {"current", "superseded", "deleted"}:
            raise RetrievalError("invalid_revision_state", "index revision state is invalid")


@dataclass(frozen=True, slots=True)
class IndexRequest:
    task_id: str
    manifest: IntakeManifest
    max_chunk_chars: int = 1_200
    revision_state: str = "current"

    def __post_init__(self) -> None:
        if not self.task_id or self.max_chunk_chars < 64 or self.revision_state not in {"current", "superseded", "deleted"}:
            raise RetrievalError("invalid_index_request", "index task and chunk limit are required")


class EmbeddingProvider(Protocol):
    model_id: str
    qualification_reference: str

    def embed(self, text: str) -> tuple[float, ...]: ...


class Reranker(Protocol):
    model_id: str
    qualification_reference: str

    def score(self, query: str, chunks: tuple[IndexChunk, ...]) -> tuple[float, ...]: ...


@dataclass(frozen=True, slots=True)
class QualifiedEmbeddingProvider:
    """Provider-neutral wrapper for a qualified local embedding runtime."""

    model_id: str
    qualification_reference: str
    dimension: int
    embedder: Callable[[str], Iterable[float]]
    timeout_s: float = 30.0
    max_input_chars: int = 100_000

    def __post_init__(self) -> None:
        if not self.model_id or not self.qualification_reference or self.dimension < 1 or self.timeout_s <= 0 or self.max_input_chars < 1:
            raise RetrievalError("invalid_embedding_provider", "embedding identity and dimension are required")

    def embed(self, text: str) -> tuple[float, ...]:
        if not text.strip() or len(text) > self.max_input_chars:
            raise RetrievalError("resource_exhausted", "embedding input exceeds the configured limit")
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            values = tuple(float(value) for value in executor.submit(self.embedder, text).result(timeout=self.timeout_s))
        except FutureTimeout as exc:
            raise RetrievalError("embedding_timeout", "embedding provider timed out") from exc
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError("embedding_failed", "embedding provider failed") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if len(values) != self.dimension or not all(math.isfinite(value) for value in values):
            raise RetrievalError("invalid_embedding", "embedding dimension or values are invalid")
        return values


@dataclass(frozen=True, slots=True)
class QualifiedReranker:
    """Provider-neutral wrapper for a qualified local reranker runtime."""

    model_id: str
    qualification_reference: str
    scorer: Callable[[str, tuple[IndexChunk, ...]], Iterable[float]]
    timeout_s: float = 30.0
    max_chunks: int = 100

    def __post_init__(self) -> None:
        if not self.model_id or not self.qualification_reference or self.timeout_s <= 0 or self.max_chunks < 1:
            raise RetrievalError("invalid_reranker", "reranker identity and qualification are required")

    def score(self, query: str, chunks: tuple[IndexChunk, ...]) -> tuple[float, ...]:
        if not query.strip() or len(chunks) > self.max_chunks:
            raise RetrievalError("resource_exhausted", "reranker input exceeds the configured limit")
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            values = tuple(float(value) for value in executor.submit(self.scorer, query, chunks).result(timeout=self.timeout_s))
        except FutureTimeout as exc:
            raise RetrievalError("reranker_timeout", "reranker timed out") from exc
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError("reranker_failed", "reranker failed") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if len(values) != len(chunks) or not all(math.isfinite(value) for value in values):
            raise RetrievalError("invalid_rerank", "reranker returned an invalid score set")
        return values


class VectorStore(Protocol):
    """Provider-neutral durable index storage behind ``LocalVectorIndex``.

    A store owns persistence and clearance-filtered similarity search.  It is
    injected so the core can use an offline SQLite store, an optional Chroma
    collection, or an in-memory test double without changing callers.
    """

    @property
    def chunks(self) -> tuple[IndexChunk, ...]: ...

    def upsert(self, chunks: Iterable[IndexChunk]) -> None: ...

    def search(self, embedding: tuple[float, ...], clearance: Clearance, limit: int) -> tuple[IndexChunk, ...]: ...


class LocalVectorIndex:
    """Local index facade with optional bounded JSON persistence.

    When a ``VectorStore`` is injected, ``upsert``, ``search``, and ``chunks``
    delegate to it and the JSON file seam is unused.  Without a store the
    built-in JSON-backed behavior is preserved.

    The file is a simple deployment seam, not a claim that JSON is the
    production-scale vector database.  Providers and durable storage remain
    replaceable at the boundary.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_file_bytes: int = 50_000_000,
        store: VectorStore | None = None,
    ) -> None:
        if max_file_bytes < 1:
            raise RetrievalError("invalid_storage_limit", "index storage limit must be positive")
        self._store = store
        self._path = Path(path) if (path is not None and store is None) else None
        self._max_file_bytes = max_file_bytes
        self._chunks: dict[str, IndexChunk] = {}
        if store is None:
            self._load()

    @property
    def store(self) -> VectorStore | None:
        return self._store

    @property
    def chunks(self) -> tuple[IndexChunk, ...]:
        if self._store is not None:
            return self._store.chunks
        return tuple(self._chunks.values())

    def upsert(self, chunks: Iterable[IndexChunk]) -> None:
        if self._store is not None:
            self._store.upsert(chunks)
            return
        updated = dict(self._chunks)
        incoming = tuple(chunks)
        for chunk in incoming:
            for chunk_id, existing in tuple(updated.items()):
                if (
                    existing.source_ref == chunk.source_ref
                    and existing.revision_id != chunk.revision_id
                    and existing.revision_state == "current"
                ):
                    updated[chunk_id] = replace(existing, revision_state="superseded")
            updated[chunk.chunk_id] = chunk
        self._persist(updated)
        self._chunks = updated

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        if self._path.stat().st_size > self._max_file_bytes:
            raise RetrievalError("storage_limit", "index file exceeds the configured limit")
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            self._chunks = {
                item["chunk_id"]: IndexChunk(
                    chunk_id=item["chunk_id"], intake_id=item["intake_id"], revision_id=item["revision_id"],
                    source_ref=item["source_ref"], page_id=item["page_id"], source_span=item["source_span"],
                    text=item["text"], content_hash=item["content_hash"], confidence=item["confidence"],
                    clearance=Clearance(item["clearance"]), taint=Taint(item["taint"]),
                    embedding=tuple(item["embedding"]), embedding_model=item["embedding_model"],
                    qualification_reference=item["qualification_reference"],
                    revision_state=item.get("revision_state", "current"),
                ) for item in payload
            }
        except (OSError, ValueError, KeyError, TypeError, RetrievalError) as exc:
            raise RetrievalError("invalid_storage", "index file is invalid") from exc

    def _persist(self, chunks: dict[str, IndexChunk] | None = None) -> None:
        if self._path is None:
            return
        records = self._chunks if chunks is None else chunks
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "chunk_id": chunk.chunk_id, "intake_id": chunk.intake_id, "revision_id": chunk.revision_id,
                "source_ref": chunk.source_ref, "page_id": chunk.page_id, "source_span": chunk.source_span,
                "text": chunk.text, "content_hash": chunk.content_hash, "confidence": chunk.confidence,
                "clearance": chunk.clearance.value, "taint": chunk.taint.value,
                "embedding": list(chunk.embedding), "embedding_model": chunk.embedding_model,
                "qualification_reference": chunk.qualification_reference,
                "revision_state": chunk.revision_state,
            } for chunk in records.values()
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > self._max_file_bytes:
            raise RetrievalError("storage_limit", "index file exceeds the configured limit")
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            temporary.write_bytes(encoded)
            temporary.replace(self._path)
        except OSError as exc:
            raise RetrievalError("storage_failed", "index file could not be written") from exc

    def search(self, embedding: tuple[float, ...], clearance: Clearance, limit: int) -> tuple[IndexChunk, ...]:
        if limit < 1:
            raise RetrievalError("invalid_limit", "search limit must be positive")
        if self._store is not None:
            return self._store.search(embedding, clearance, limit)
        candidates = [
            (self._cosine(embedding, chunk.embedding), chunk)
            for chunk in self._chunks.values()
            if _rank(chunk.clearance) <= _rank(clearance)
            and chunk.revision_state == "current"
        ]
        candidates.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return tuple(chunk for _, chunk in candidates[:limit])

    @staticmethod
    def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if len(left) != len(right):
            return -1.0
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


class LocalIndexer:
    """Convert intake pages or OCR results into bounded local vector chunks."""

    def __init__(self, index: LocalVectorIndex, embeddings: EmbeddingProvider, *, ledger: EventLedger | None = None) -> None:
        self.index = index
        self.embeddings = embeddings
        self._ledger = ledger

    def index_manifest(self, request: IndexRequest) -> tuple[IndexChunk, ...]:
        self._event("index.requested", request.task_id, request.manifest.clearance, {"intake_id": request.manifest.intake_id})
        try:
            chunks = self._index_pages(request, request.manifest.pages)
            self.index.upsert(chunks)
            self._event("index.completed", request.task_id, request.manifest.clearance, {
                "intake_id": request.manifest.intake_id,
                "chunk_count": str(len(chunks)),
            })
            return chunks
        except RetrievalError as exc:
            self._event("index.failed", request.task_id, request.manifest.clearance, {"code": exc.code})
            raise
        except Exception as exc:
            self._event("index.failed", request.task_id, request.manifest.clearance, {"code": "index_failed"})
            raise RetrievalError("index_failed", "local indexing failed") from exc

    def index_vision_results(self, request: IndexRequest, results: Iterable[VisionResult]) -> tuple[IndexChunk, ...]:
        pages = tuple(
            PageRecord(
                page_id=result.page_id,
                page_number=1,
                source_region=result.page_id,
                content_hash=result.content_hash,
                media_type="text/plain",
                text=result.text,
                extraction_method=result.extraction_method,
                confidence=result.confidence,
                clearance=result.clearance,
                taint=result.taint,
                evidence_ref=result.source_ref,
            )
            for result in results
        )
        return self.index_manifest(IndexRequest(
            request.task_id,
            replace_manifest_pages(request.manifest, pages),
            request.max_chunk_chars,
            request.revision_state,
        ))

    def _index_pages(self, request: IndexRequest, pages: Iterable[PageRecord]) -> tuple[IndexChunk, ...]:
        chunks: list[IndexChunk] = []
        for page in pages:
            text = page.text.strip()
            for offset in range(0, len(text), request.max_chunk_chars):
                excerpt = text[offset:offset + request.max_chunk_chars].strip()
                if not excerpt:
                    continue
                source_span = f"{page.source_region}:chars-{offset}-{offset + len(excerpt)}"
                chunks.append(IndexChunk(
                    chunk_id=stable_id("chunk", request.manifest.revision_id, page.page_id, offset, excerpt),
                    intake_id=request.manifest.intake_id,
                    revision_id=request.manifest.revision_id,
                    source_ref=request.manifest.source_ref,
                    page_id=page.page_id,
                    source_span=source_span,
                    text=excerpt,
                    content_hash=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                    confidence=page.confidence,
                    clearance=page.clearance,
                    taint=page.taint,
                    embedding=self.embeddings.embed(excerpt),
                    embedding_model=self.embeddings.model_id,
                    qualification_reference=self.embeddings.qualification_reference,
                    revision_state=request.revision_state,
                ))
        return tuple(chunks)

    def _event(self, event_type: str, task_id: str, clearance: Clearance, payload: dict[str, str]) -> None:
        if self._ledger is None:
            return
        sequence = len(self._ledger.events)
        self._ledger.append(build_event(
            event_type=event_type,
            task_id=task_id,
            actor_id="local-indexer",
            actor_type="indexer",
            payload_contract="IndexOperation",
            payload_version="1.0",
            payload={"task_id": task_id, **payload},
            clearance=clearance,
            idempotency=stable_id("index", event_type, task_id, sequence),
            sequence=sequence,
            previous_event_hash=self._ledger.head_hash,
            occurred_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        ))


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    task_id: str
    query: str
    clearance: Clearance
    top_k: int = 5
    max_excerpt_chars: int = 800

    def __post_init__(self) -> None:
        if not self.task_id or not self.query.strip():
            raise RetrievalError("invalid_query", "retrieval task and query are required")
        if not 1 <= self.top_k <= 100 or not 1 <= self.max_excerpt_chars <= 10_000:
            raise RetrievalError("invalid_limit", "retrieval limits are outside the allowed range")


@dataclass(frozen=True, slots=True)
class CitedExcerpt:
    citation_id: str
    chunk_id: str
    source_ref: str
    revision_id: str
    page_id: str
    source_span: str
    excerpt: str
    score: float
    confidence: float
    clearance: Clearance
    taint: Taint
    content_hash: str
    embedding_model: str
    reranker_model: str | None
    revision_state: str


class RetrievalService:
    def __init__(self, index: LocalVectorIndex, embeddings: EmbeddingProvider, *, reranker: Reranker | None = None, ledger: EventLedger | None = None) -> None:
        self._index = index
        self._embeddings = embeddings
        self._reranker = reranker
        self._ledger = ledger

    def search(self, request: RetrievalRequest) -> tuple[CitedExcerpt, ...]:
        self._event("retrieval.requested", request, {"query_hash": hashlib.sha256(request.query.encode("utf-8")).hexdigest()})
        try:
            query_embedding = self._embeddings.embed(request.query)
            candidates = self._index.search(query_embedding, request.clearance, min(request.top_k * 3, 100))
            scores = self._reranker.score(request.query, candidates) if self._reranker else tuple(0.0 for _ in candidates)
            ranked = sorted(zip(candidates, scores), key=lambda pair: (-pair[1], pair[0].chunk_id))[:request.top_k]
            result = tuple(CitedExcerpt(
                citation_id=stable_id("citation", request.task_id, chunk.chunk_id),
                chunk_id=chunk.chunk_id,
                source_ref=chunk.source_ref,
                revision_id=chunk.revision_id,
                page_id=chunk.page_id,
                source_span=chunk.source_span,
                excerpt=chunk.text[:request.max_excerpt_chars],
                score=float(score),
                confidence=chunk.confidence,
                clearance=chunk.clearance,
                taint=chunk.taint,
                content_hash=chunk.content_hash,
                embedding_model=chunk.embedding_model,
                reranker_model=self._reranker.model_id if self._reranker else None,
                revision_state=chunk.revision_state,
            ) for chunk, score in ranked)
            self._event("retrieval.completed", request, {"citation_count": str(len(result))})
            return result
        except RetrievalError as exc:
            self._event("retrieval.failed", request, {"code": exc.code})
            raise
        except Exception as exc:
            self._event("retrieval.failed", request, {"code": "retrieval_failed"})
            raise RetrievalError("retrieval_failed", "local retrieval failed") from exc

    def _event(self, event_type: str, request: RetrievalRequest, payload: dict[str, str]) -> None:
        if self._ledger is None:
            return
        sequence = len(self._ledger.events)
        self._ledger.append(build_event(
            event_type=event_type,
            task_id=request.task_id,
            actor_id="local-retrieval",
            actor_type="retrieval",
            payload_contract="RetrievalOperation",
            payload_version="1.0",
            payload={
                "task_id": request.task_id,
                "clearance": request.clearance.value,
                **payload,
            },
            clearance=request.clearance,
            idempotency=stable_id("retrieval", event_type, request.task_id, sequence),
            sequence=sequence,
            previous_event_hash=self._ledger.head_hash,
            occurred_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        ))


def replace_manifest_pages(manifest: IntakeManifest, pages: tuple[PageRecord, ...]) -> IntakeManifest:
    """Return a manifest view with OCR text while retaining intake identity."""
    return replace(manifest, pages=pages)


class DeterministicEmbeddingProvider:
    """Offline fixture provider; not a claim of BGE model quality."""

    model_id = "fixture.embedding"
    qualification_reference = "fixture.embedding.qualified"

    def __init__(self, dimension: int = 16) -> None:
        self.dimension = dimension

    def embed(self, text: str) -> tuple[float, ...]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return tuple((digest[index % len(digest)] / 127.5) - 1.0 for index in range(self.dimension))


class LexicalReranker:
    """Offline fixture reranker for deterministic contract tests."""

    model_id = "fixture.reranker"
    qualification_reference = "fixture.reranker.qualified"

    def score(self, query: str, chunks: tuple[IndexChunk, ...]) -> tuple[float, ...]:
        terms = set(query.lower().split())
        return tuple(sum(term in chunk.text.lower().split() for term in terms) for chunk in chunks)


__all__ = [
    "CitedExcerpt", "DeterministicEmbeddingProvider", "EmbeddingProvider", "IndexChunk", "IndexRequest",
    "LexicalReranker", "LocalIndexer", "LocalVectorIndex", "QualifiedEmbeddingProvider", "QualifiedReranker",
    "RetrievalError", "RetrievalRequest", "RetrievalService", "Reranker", "VectorStore",
]
