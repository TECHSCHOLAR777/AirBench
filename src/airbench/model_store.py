"""Local model-store inventory and one-copy Hugging Face cache cleanup.

The runtime has one canonical copy of each model under ``AIRBENCH_MODEL_STORE``.
Hugging Face is an acquisition mechanism only.  Its cache is never a runtime
dependency and this module performs no network I/O.

Cache pruning is deliberately conservative: it removes only cache blobs whose
content and size are already present in the canonical store.  The caller must
explicitly opt into deletion through the provisioning CLI.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Mapping


class ModelStoreError(ValueError):
    """The model store cannot be audited or safely changed."""


def _safe_relative(value: str) -> bool:
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")):
        return False
    return not (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or ".." in PurePosixPath(value).parts
        or ".." in PureWindowsPath(value).parts
    )


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ModelStoreTarget:
    """Storage identity derived from a signed roster target."""

    target_id: str
    repository: str
    runtime_path: str
    required_files: tuple[str, ...]
    cache_repository: str = ""

    def validate(self) -> None:
        if not self.target_id or not self.repository or not _safe_relative(self.runtime_path):
            raise ModelStoreError(f"invalid storage target: {self.target_id or '<unknown>'}")
        if self.cache_repository and self.cache_repository.count("/") != 1:
            raise ModelStoreError(f"invalid cache repository override: {self.target_id}")
        if not self.required_files or any(not _safe_relative(item) for item in self.required_files):
            raise ModelStoreError(f"required runtime files are invalid: {self.target_id}")


@dataclass(frozen=True, slots=True)
class CacheRepositoryAudit:
    target_id: str
    repository: str
    cache_path: str
    required_runtime_files_present: bool
    incomplete_blob_paths: tuple[str, ...]
    stale_incomplete_blob_paths: tuple[str, ...]
    duplicate_blob_paths: tuple[str, ...]
    unmatched_blob_paths: tuple[str, ...]
    duplicate_bytes: int
    safe_to_prune: bool
    reason: str

    @property
    def duplicate_gib(self) -> float:
        return self.duplicate_bytes / (1024**3)


@dataclass(frozen=True, slots=True)
class ModelStoreAudit:
    runtime_root: str
    cache_root: str
    repositories: tuple[CacheRepositoryAudit, ...]

    @property
    def safe_to_prune(self) -> bool:
        return bool(self.repositories) and all(item.safe_to_prune for item in self.repositories)

    @property
    def prunable_bytes(self) -> int:
        return sum(item.duplicate_bytes for item in self.repositories if item.safe_to_prune)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_root": self.runtime_root,
            "cache_root": self.cache_root,
            "safe_to_prune": self.safe_to_prune,
            "prunable_bytes": self.prunable_bytes,
            "repositories": [
                {
                    "target_id": item.target_id,
                    "repository": item.repository,
                    "cache_path": item.cache_path,
                    "required_runtime_files_present": item.required_runtime_files_present,
                    "incomplete_blob_paths": list(item.incomplete_blob_paths),
                    "stale_incomplete_blob_paths": list(item.stale_incomplete_blob_paths),
                    "duplicate_blob_paths": list(item.duplicate_blob_paths),
                    "unmatched_blob_paths": list(item.unmatched_blob_paths),
                    "duplicate_bytes": item.duplicate_bytes,
                    "safe_to_prune": item.safe_to_prune,
                    "reason": item.reason,
                }
                for item in self.repositories
            ],
        }


def targets_from_roster(
    path: Path,
    target_ids: Iterable[str] | None = None,
    cache_repositories: Mapping[str, str] | None = None,
) -> tuple[ModelStoreTarget, ...]:
    """Read storage fields from the human-maintained roster.

    This function does not qualify a model or replace the signed registry
    loader.  The runtime must still load the signed roster through
    ``ModelRegistry``.  It only prevents a separate storage mapping from
    drifting from the roster's ``artifact_path`` and declared components.
    """

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ModelStoreError("PyYAML is required to read the model roster") from exc
    with path.open("r", encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    if not isinstance(document, Mapping) or not isinstance(document.get("roster"), Mapping):
        raise ModelStoreError("model roster must contain a roster object")
    raw_targets = document["roster"].get("targets")
    if not isinstance(raw_targets, list):
        raise ModelStoreError("model roster targets must be an array")
    requested = set(target_ids or ())
    result: list[ModelStoreTarget] = []
    for raw in raw_targets:
        if not isinstance(raw, Mapping):
            raise ModelStoreError("model roster target must be an object")
        target_id = str(raw.get("target_id", ""))
        if requested and target_id not in requested:
            continue
        required = list(raw.get("artifact_files") or [])
        for component_name in ("tokenizer", "chat_template", "image_processor", "mmproj"):
            component = raw.get(component_name)
            if isinstance(component, Mapping) and component.get("path"):
                required.append(str(component["path"]))
        target = ModelStoreTarget(
            target_id=target_id,
            repository=str(raw.get("repository", "")),
            runtime_path=str(raw.get("artifact_path", "")),
            required_files=tuple(dict.fromkeys(str(item) for item in required)),
            cache_repository=(cache_repositories or {}).get(target_id, ""),
        )
        target.validate()
        result.append(target)
    if requested and {item.target_id for item in result} != requested:
        missing = sorted(requested - {item.target_id for item in result})
        raise ModelStoreError(f"unknown roster target IDs: {missing}")
    if not result:
        raise ModelStoreError("no model-store targets selected")
    return tuple(result)


def _cache_repo_name(repository: str) -> str:
    if repository.count("/") != 1 or any(part in {"", ".", ".."} for part in repository.split("/")):
        raise ModelStoreError(f"invalid Hugging Face repository: {repository}")
    return "models--" + repository.replace("/", "--")


def _runtime_inventory(root: Path, targets: tuple[ModelStoreTarget, ...]) -> dict[tuple[str, int], tuple[Path, ...]]:
    inventory: dict[tuple[str, int], list[Path]] = {}
    for target in targets:
        target_root = root / target.runtime_path
        if not target_root.is_dir() or target_root.is_symlink():
            continue
        for current, directories, files in os.walk(target_root, followlinks=False):
            directories[:] = [name for name in directories if name != ".cache"]
            for name in files:
                candidate = Path(current) / name
                if candidate.is_symlink() or candidate.suffix.lower() == ".log":
                    continue
                key = (_sha256(candidate), candidate.stat().st_size)
                inventory.setdefault(key, []).append(candidate)
    return {key: tuple(value) for key, value in inventory.items()}


def _required_files_present(root: Path, target: ModelStoreTarget) -> bool:
    target_root = root / target.runtime_path
    if not target_root.is_dir() or target_root.is_symlink():
        return False
    for relative in target.required_files:
        raw_candidate = target_root / relative
        candidate = raw_candidate.resolve()
        if raw_candidate.is_symlink() or not _within(target_root.resolve(), candidate) or not candidate.is_file():
            return False
    return True


def audit_model_store(
    runtime_root: Path,
    cache_root: Path,
    targets: tuple[ModelStoreTarget, ...],
    *,
    allow_stale_incomplete: bool = False,
) -> ModelStoreAudit:
    """Audit one canonical runtime store against selected HF cache repos."""

    runtime = runtime_root.resolve()
    cache = cache_root.resolve()
    if not runtime.is_dir():
        raise ModelStoreError("canonical runtime model store must be an existing directory")
    if not cache.is_dir():
        raise ModelStoreError("Hugging Face cache root must be an existing directory")
    for target in targets:
        target.validate()

    inventory = _runtime_inventory(runtime, targets)
    audits: list[CacheRepositoryAudit] = []
    for target in targets:
        repository = target.cache_repository or target.repository
        repository_path = cache / _cache_repo_name(repository)
        blobs_root = repository_path / "blobs"
        required_present = _required_files_present(runtime, target)
        incomplete: list[str] = []
        stale_incomplete: list[str] = []
        duplicate: list[str] = []
        unmatched: list[str] = []
        duplicate_bytes = 0
        if not repository_path.is_dir() or repository_path.is_symlink() or not blobs_root.is_dir():
            audits.append(CacheRepositoryAudit(
                target.target_id, repository, str(repository_path), required_present,
                (), (), (), (), 0, required_present, "cache repository is absent; canonical runtime store is the only copy",
            ))
            continue
        for blob in sorted(blobs_root.iterdir(), key=lambda item: item.name):
            if not blob.is_file() or blob.is_symlink():
                continue
            if blob.name.endswith(".incomplete"):
                blob_path = str(blob)
                incomplete.append(blob_path)
                modified = datetime.fromtimestamp(blob.stat().st_mtime, tz=timezone.utc)
                if datetime.now(timezone.utc) - modified >= timedelta(hours=24):
                    stale_incomplete.append(blob_path)
                continue
            key = (_sha256(blob), blob.stat().st_size)
            if key in inventory:
                duplicate.append(str(blob))
                duplicate_bytes += blob.stat().st_size
            else:
                unmatched.append(str(blob))
        safe = required_present and (
            not incomplete or (allow_stale_incomplete and len(stale_incomplete) == len(incomplete))
        )
        if not required_present:
            reason = "canonical runtime target is missing one or more declared files"
        elif incomplete and not (allow_stale_incomplete and len(stale_incomplete) == len(incomplete)):
            reason = "fresh or unclassified incomplete cache download exists; nothing is deleted"
        elif incomplete:
            reason = "verified duplicates are prunable; stale incomplete downloads are retained unless explicitly purged"
        elif not duplicate:
            reason = "no duplicate cache blob remains; canonical runtime store is the only copy"
        elif unmatched:
            reason = "verified duplicates are prunable; unmatched cache metadata/blobs are retained"
        else:
            reason = "all cache blobs are proven duplicates of the canonical runtime files"
        audits.append(CacheRepositoryAudit(
            target.target_id, repository, str(repository_path), required_present,
            tuple(incomplete), tuple(stale_incomplete), tuple(duplicate), tuple(unmatched), duplicate_bytes, safe, reason,
        ))
    return ModelStoreAudit(str(runtime), str(cache), tuple(audits))


def prune_verified_cache(
    audit: ModelStoreAudit,
    *,
    apply: bool = False,
    prune_stale_incomplete: bool = False,
) -> int:
    """Remove only blobs proven duplicate by a completed audit.

    ``apply=False`` is intentionally a no-op.  The CLI requires ``--apply``
    before calling this mutating path.
    """

    if not apply:
        return 0
    if not audit.repositories or any(not item.safe_to_prune for item in audit.repositories):
        raise ModelStoreError("refusing to prune: at least one selected repository is not safe")
    removed = 0
    removed_paths: set[Path] = set()
    for repository in audit.repositories:
        for raw_path in repository.duplicate_blob_paths:
            blob = Path(raw_path)
            if not blob.is_file() or blob.is_symlink():
                raise ModelStoreError(f"verified cache blob changed before deletion: {blob}")
            removed += blob.stat().st_size
            removed_paths.add(blob.resolve())
        if prune_stale_incomplete:
            if set(repository.stale_incomplete_blob_paths) != set(repository.incomplete_blob_paths):
                raise ModelStoreError(
                    "refusing to remove incomplete downloads unless every incomplete file is older than 24 hours"
                )
            for raw_path in repository.stale_incomplete_blob_paths:
                partial = Path(raw_path)
                if not partial.is_file() or partial.is_symlink():
                    raise ModelStoreError(f"stale incomplete cache file changed before deletion: {partial}")
                removed += partial.stat().st_size
    for repository in audit.repositories:
        for raw_path in repository.duplicate_blob_paths:
            Path(raw_path).unlink()
        if prune_stale_incomplete:
            for raw_path in repository.stale_incomplete_blob_paths:
                Path(raw_path).unlink()
        repo = Path(repository.cache_path)
        snapshots = repo / "snapshots"
        if snapshots.is_dir():
            for entry in snapshots.rglob("*"):
                if entry.is_symlink() and entry.resolve(strict=False) in removed_paths:
                    entry.unlink()
    return removed
