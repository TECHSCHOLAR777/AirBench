from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from airbench.model_store import (
    ModelStoreError,
    ModelStoreTarget,
    audit_model_store,
    prune_verified_cache,
)


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _target() -> ModelStoreTarget:
    return ModelStoreTarget(
        target_id="target-a",
        repository="example/model-a",
        runtime_path="target-a",
        required_files=("weights.bin", "tokenizer.json"),
    )


def _cache_blob(cache_root: Path, content: bytes, name: str = "blob-record") -> Path:
    path = cache_root / "models--example--model-a" / "blobs" / name
    _write(path, content)
    return path


def test_audit_proves_duplicate_by_content_and_size_not_blob_name(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    cache = tmp_path / "cache"
    _write(runtime / "target-a" / "weights.bin", b"weights")
    _write(runtime / "target-a" / "tokenizer.json", b"tokenizer")
    duplicate = _cache_blob(cache, b"weights", name="git-style-blob-id")
    _cache_blob(cache, b"metadata", name="unique-metadata")

    report = audit_model_store(runtime, cache, (_target(),))

    repository = report.repositories[0]
    assert repository.safe_to_prune is True
    assert repository.duplicate_bytes == duplicate.stat().st_size
    assert repository.unmatched_blob_paths
    assert report.prunable_bytes == duplicate.stat().st_size


def test_prune_requires_explicit_apply_and_keeps_unmatched_blob(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    cache = tmp_path / "cache"
    _write(runtime / "target-a" / "weights.bin", b"weights")
    _write(runtime / "target-a" / "tokenizer.json", b"tokenizer")
    duplicate = _cache_blob(cache, b"weights")
    unique = _cache_blob(cache, b"metadata", name="unique")
    report = audit_model_store(runtime, cache, (_target(),))

    assert prune_verified_cache(report, apply=False) == 0
    assert duplicate.exists()
    removed = prune_verified_cache(report, apply=True)

    assert removed == len(b"weights")
    assert not duplicate.exists()
    assert unique.exists()


def test_incomplete_download_blocks_pruning(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    cache = tmp_path / "cache"
    _write(runtime / "target-a" / "weights.bin", b"weights")
    _write(runtime / "target-a" / "tokenizer.json", b"tokenizer")
    _cache_blob(cache, b"weights")
    _cache_blob(cache, b"partial", name="partial.incomplete")
    report = audit_model_store(runtime, cache, (_target(),))

    assert report.safe_to_prune is False
    with pytest.raises(ModelStoreError, match="not safe"):
        prune_verified_cache(report, apply=True)


def test_stale_incomplete_download_can_be_explicitly_purged(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    cache = tmp_path / "cache"
    _write(runtime / "target-a" / "weights.bin", b"weights")
    _write(runtime / "target-a" / "tokenizer.json", b"tokenizer")
    _cache_blob(cache, b"weights")
    partial = _cache_blob(cache, b"partial", name="partial.incomplete")
    import os
    import time

    old = time.time() - 2 * 24 * 60 * 60
    os.utime(partial, (old, old))
    report = audit_model_store(runtime, cache, (_target(),), allow_stale_incomplete=True)

    assert report.safe_to_prune is True
    assert prune_verified_cache(report, apply=True, prune_stale_incomplete=True) == len(b"weights") + len(b"partial")
    assert not partial.exists()


def test_missing_required_runtime_file_blocks_pruning(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    cache = tmp_path / "cache"
    _write(runtime / "target-a" / "weights.bin", b"weights")
    _cache_blob(cache, b"weights")

    report = audit_model_store(runtime, cache, (_target(),))

    assert report.repositories[0].required_runtime_files_present is False
    assert report.safe_to_prune is False
