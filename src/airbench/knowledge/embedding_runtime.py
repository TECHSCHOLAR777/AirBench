"""Real local BGE embedding and reranking runtimes.

These adapters sit behind the provider-neutral interfaces in ``retrieval.py``
so the core never imports ``sentence_transformers`` or ``torch`` directly and
so tests can inject deterministic fakes.  Only a local directory inside the
canonical model store is accepted: a Hugging Face repository id would fetch
from the network and is rejected, preserving the no-egress invariant.

BGE-M3 is a dense-embedding model (1024-dim, normalised).  The reranker is a
cross-encoder that scores (query, passage) pairs.  Both run on CPU by default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Never let transformers import TensorFlow for these local BGE models.  The TF
# import is unnecessary here and can crash natively on Windows when combined
# with the installed torch build, so it is disabled before the lazy import.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

from .retrieval import (
    LocalIndexer,
    LocalVectorIndex,
    QualifiedEmbeddingProvider,
    QualifiedReranker,
    RetrievalService,
)


class EmbeddingRuntimeError(RuntimeError):
    """A local BGE runtime could not be loaded or used."""


def _require_local_dir(model_dir: str | Path) -> Path:
    path = Path(model_dir)
    if not path.is_dir():
        raise EmbeddingRuntimeError(f"a local model directory is required (got {model_dir!r}); repo ids are rejected")
    return path


_DEPENDENCY_HINT = (
    "sentence-transformers/transformers could not be imported. Install a compatible "
    "stack, e.g. python -m pip install -U \"huggingface-hub>=0.34.0,<1.0\" "
    "sentence-transformers transformers torch"
)


def _load_sentence_transformer(model_dir: Path, device: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise EmbeddingRuntimeError(f"{_DEPENDENCY_HINT} (import error: {exc})") from exc
    try:
        return SentenceTransformer(str(model_dir), device=device)
    except Exception as exc:  # pragma: no cover - model/environment dependent
        raise EmbeddingRuntimeError(f"the local embedding model could not be loaded: {exc}") from exc


def local_embedding_provider(
    model_dir: str | Path, *, model_id: str, qualification_reference: str,
    device: str = "cpu", dimension: int | None = None,
) -> QualifiedEmbeddingProvider:
    """Build a qualified dense-embedding provider from a local BGE-M3 directory."""
    path = _require_local_dir(model_dir)
    model = _load_sentence_transformer(path, device)
    getter = getattr(model, "get_embedding_dimension", None) or getattr(model, "get_sentence_embedding_dimension", None)
    try:
        detected = int(getter()) if callable(getter) else (dimension or 1024)
    except Exception:  # pragma: no cover - backend dependent
        detected = dimension or 1024

    def embed(text: str) -> list[float]:
        vector = model.encode(text, normalize_embeddings=True)
        return [float(value) for value in vector]

    return QualifiedEmbeddingProvider(
        model_id=model_id,
        qualification_reference=qualification_reference,
        dimension=dimension or detected,
        embedder=embed,
    )


def local_reranker(
    model_dir: str | Path, *, model_id: str, qualification_reference: str, device: str = "cpu",
) -> QualifiedReranker:
    """Build a qualified cross-encoder reranker from a local bge-reranker directory."""
    path = _require_local_dir(model_dir)
    try:
        from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise EmbeddingRuntimeError(f"{_DEPENDENCY_HINT} (import error: {exc})") from exc
    try:
        model = CrossEncoder(str(path), device=device)
    except Exception as exc:  # pragma: no cover - model/environment dependent
        raise EmbeddingRuntimeError(f"the local reranker model could not be loaded: {exc}") from exc

    def score(query: str, chunks: tuple[Any, ...]) -> list[float]:
        if not chunks:
            return []
        pairs = [[query, chunk.text] for chunk in chunks]
        return [float(value) for value in model.predict(pairs)]

    return QualifiedReranker(model_id=model_id, qualification_reference=qualification_reference, scorer=score)


@dataclass(frozen=True, slots=True)
class RetrievalRuntime:
    """A composed local retrieval stack: index, indexer, and retrieval service."""

    service: RetrievalService
    indexer: LocalIndexer
    index: LocalVectorIndex
    embedding_model_id: str
    embedding_qualification_reference: str
    reranker_model_id: str | None = None
    reranker_qualification_reference: str | None = None


def build_retrieval_runtime(
    *, model_store: str | Path,
    embedding_dir: str = "bge-m3",
    reranker_dir: str = "bge-reranker-v2-m3",
    embedding_model_id: str = "bge-m3",
    embedding_qualification_reference: str = "cert-bge-m3-embedding-v0",
    reranker_model_id: str = "bge-reranker-v2-m3",
    reranker_qualification_reference: str = "cert-bge-reranker-v2-m3-reranking-v0",
    index_path: str | Path | None = None,
    device: str = "cpu",
    ledger: Any = None,
    embedding_provider: Any = None,
    reranker: Any = None,
    vector_store: Any = None,
) -> RetrievalRuntime:
    """Compose the retrieval stack from the canonical model store.

    ``embedding_provider``/``reranker`` may be injected (for tests or a
    different qualified runtime); otherwise the real local BGE adapters load
    from ``model_store``.
    """
    root = Path(model_store)
    embeddings = embedding_provider or local_embedding_provider(
        root / embedding_dir, model_id=embedding_model_id,
        qualification_reference=embedding_qualification_reference, device=device,
    )
    reranker_impl = reranker or local_reranker(
        root / reranker_dir, model_id=reranker_model_id,
        qualification_reference=reranker_qualification_reference, device=device,
    )
    index = LocalVectorIndex(index_path, store=vector_store)
    indexer = LocalIndexer(index, embeddings, ledger=ledger)
    service = RetrievalService(index, embeddings, reranker=reranker_impl, ledger=ledger)
    return RetrievalRuntime(
        service=service, indexer=indexer, index=index,
        embedding_model_id=embeddings.model_id,
        embedding_qualification_reference=embeddings.qualification_reference,
        reranker_model_id=getattr(reranker_impl, "model_id", None),
        reranker_qualification_reference=getattr(reranker_impl, "qualification_reference", None),
    )


def retrieval_runtime_from_env(*, ledger: Any = None,
                               embedding_provider: Any = None, reranker: Any = None,
                               vector_store: Any = None) -> RetrievalRuntime:
    """Build the retrieval stack from environment configuration.

    ``AIRBENCH_RETRIEVAL_MODEL_STORE`` takes precedence so the BGE models may
    live in a different store than the routed chat models; it falls back to
    ``AIRBENCH_MODEL_STORE``.
    """
    model_store = (
        os.environ.get("AIRBENCH_RETRIEVAL_MODEL_STORE", "").strip()
        or os.environ.get("AIRBENCH_MODEL_STORE", "").strip()
    )
    if not model_store:
        raise EnvironmentError("AIRBENCH_RETRIEVAL_MODEL_STORE or AIRBENCH_MODEL_STORE is required when retrieval is enabled")
    index_path = os.environ.get("AIRBENCH_RETRIEVAL_INDEX_PATH", "").strip() or None
    if vector_store is None:
        from .vector_store import build_vector_store_from_env

        vector_store = build_vector_store_from_env()
    return build_retrieval_runtime(
        model_store=model_store, index_path=index_path, ledger=ledger,
        embedding_provider=embedding_provider, reranker=reranker, vector_store=vector_store,
        embedding_dir=os.environ.get("AIRBENCH_EMBEDDING_DIR", "bge-m3").strip() or "bge-m3",
        reranker_dir=os.environ.get("AIRBENCH_RERANKER_DIR", "bge-reranker-v2-m3").strip() or "bge-reranker-v2-m3",
    )


def retrieval_enabled() -> bool:
    return os.environ.get("AIRBENCH_RETRIEVAL_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


__all__ = [
    "EmbeddingRuntimeError",
    "RetrievalRuntime",
    "build_retrieval_runtime",
    "local_embedding_provider",
    "local_reranker",
    "retrieval_enabled",
    "retrieval_runtime_from_env",
]
