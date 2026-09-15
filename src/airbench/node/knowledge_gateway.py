"""Node-owned bulk knowledge ingestion.

Bulk ingestion uses the same single File Intake Layer as query uploads, then
hands the committed manifest to the local indexer.  A directory may only be
ingested from an operator-configured root, so a client cannot ask the Node to
walk an arbitrary host path.  Files remain untrusted data throughout.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

import yaml

from contracts import Clearance, EventLedger, build_event, idempotency_key, stable_id

from airbench.intake.layer import FileIntakeLayer, IntakeError
from airbench.knowledge.retrieval import IndexRequest, LocalIndexer

from .intake_gateway import NodeIntakeError


MAX_INGEST_FILES = 500
MAX_INGEST_BYTES = 500_000_000
CATALOG_PREFIX = PurePosixPath("01_knowledge_base_ingestion")


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    relative_path: PurePosixPath
    document_profile: str
    source_hash: str
    revision: str


def _catalog_relative_path(raw_path: str) -> PurePosixPath:
    candidate = PurePosixPath(raw_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("catalog path escapes the ingestion root")
    if candidate.parts[: len(CATALOG_PREFIX.parts)] == CATALOG_PREFIX.parts:
        candidate = PurePosixPath(*candidate.parts[len(CATALOG_PREFIX.parts):])
    if not candidate.parts:
        raise ValueError("catalog path is empty")
    return candidate


def _load_catalog(path: Path) -> dict[PurePosixPath, CatalogEntry]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("the knowledge catalog could not be read") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("the knowledge catalog must contain a records list")
    entries: dict[PurePosixPath, CatalogEntry] = {}
    for raw in payload["records"]:
        if not isinstance(raw, dict):
            raise ValueError("a knowledge catalog record must be an object")
        try:
            relative_path = _catalog_relative_path(str(raw["path"]))
            source_hash = str(raw["sha256"]).lower()
            document_profile = str(raw["document_profile"])
            revision = str(raw["revision"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("a knowledge catalog record is incomplete") from exc
        if len(source_hash) != 64 or any(char not in "0123456789abcdef" for char in source_hash):
            raise ValueError(f"catalog hash is invalid for {relative_path.as_posix()}")
        if not document_profile or not revision or relative_path in entries:
            raise ValueError(f"catalog record is invalid for {relative_path.as_posix()}")
        entries[relative_path] = CatalogEntry(relative_path, document_profile, source_hash, revision)
    if not entries:
        raise ValueError("the knowledge catalog contains no records")
    return entries


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class LocalNodeKnowledgeService:
    """Compose the intake layer and local indexer into a guarded bulk ingest."""

    def __init__(
        self,
        *,
        layer: FileIntakeLayer,
        indexer: LocalIndexer,
        ingest_root: str | Path,
        task_id: str,
        clearance_context,
        max_files: int = MAX_INGEST_FILES,
        max_total_bytes: int = MAX_INGEST_BYTES,
        catalog_path: str | Path | None = None,
        ledger: EventLedger | None = None,
    ) -> None:
        self._layer = layer
        self._indexer = indexer
        self._root = Path(ingest_root).resolve()
        self._task_id = task_id
        self._clearance = clearance_context
        self._max_files = max_files
        self._max_total_bytes = max_total_bytes
        self._catalog_path = Path(catalog_path).resolve() if catalog_path is not None else None
        self._ledger = ledger

    def _event(self, event_type: str, *, job_id: str, payload: dict[str, Any], key: str) -> str | None:
        if self._ledger is None:
            return None
        existing = self._ledger.find_by_idempotency(key)
        if existing is not None:
            return existing.event_id
        event = build_event(
            event_type=event_type,
            task_id=self._task_id,
            actor_id="knowledge.ingest",
            actor_type="service",
            payload_contract="KnowledgeIngestOperation",
            payload_version="1.0",
            payload={"job_id": job_id, "clearance": self._clearance.value, **payload},
            clearance=self._clearance,
            idempotency=key,
            sequence=len(self._ledger),
            previous_event_hash=self._ledger.head_hash,
        )
        try:
            self._ledger.append(event)
        except Exception as exc:  # the operation must not succeed without its audit record
            raise NodeIntakeError(503, "knowledge_ledger_unavailable", "The knowledge ingestion ledger could not be updated.") from exc
        return event.event_id

    def ingest_directory(self, *, path: str) -> dict:
        if not self._root.is_dir():
            raise NodeIntakeError(503, "ingest_root_unavailable", "The configured ingestion root does not exist.")
        target = Path(path)
        resolved = (target if target.is_absolute() else self._root / target).resolve()
        if resolved != self._root and self._root not in resolved.parents:
            raise NodeIntakeError(403, "ingest_root_denied", "The requested path is outside the configured ingestion root.")
        if not resolved.is_dir():
            raise NodeIntakeError(404, "ingest_path_not_found", "The requested ingestion directory does not exist.")

        try:
            catalog = _load_catalog(self._catalog_path) if self._catalog_path is not None else None
        except ValueError as exc:
            raise NodeIntakeError(422, "ingest_catalog_invalid", str(exc)) from exc

        candidates = sorted(candidate for candidate in resolved.rglob("*") if candidate.is_file())
        if catalog is not None:
            candidate_paths = {PurePosixPath(candidate.relative_to(self._root).as_posix()) for candidate in candidates}
            unlisted = sorted(candidate_paths - set(catalog))
            candidates = [candidate for candidate in candidates if PurePosixPath(candidate.relative_to(self._root).as_posix()) in catalog]
            missing = sorted(set(catalog) - {PurePosixPath(candidate.relative_to(self._root).as_posix()) for candidate in candidates})
        else:
            unlisted = []
            missing = []
        files = candidates
        if len(files) > self._max_files:
            raise NodeIntakeError(413, "ingest_too_many_files", "The directory contains more files than the ingestion limit.")

        job_id = stable_id("knowledge-ingest-job", str(self._root), str(resolved))
        self._event(
            "knowledge.ingest.started", job_id=job_id,
            payload={"root": str(self._root), "path": str(resolved), "catalog_path": str(self._catalog_path) if self._catalog_path else None},
            key=idempotency_key("knowledge.ingest.started", job_id),
        )
        total_bytes = 0
        ingested: list[dict] = []
        failures: list[dict] = []
        chunk_total = 0
        for relative in unlisted:
            failure = {"file_name": relative.name, "relative_path": relative.as_posix(), "code": "ingest_not_catalogued", "message": "The file is present but is not listed in the approved knowledge catalog."}
            failures.append(failure)
            self._event(
                "knowledge.ingest.file_failed", job_id=job_id, payload=failure,
                key=idempotency_key("knowledge.ingest.file_failed", job_id, relative.as_posix(), "unlisted"),
            )
        for relative in missing:
            failure = {"file_name": relative.name, "relative_path": relative.as_posix(), "code": "ingest_catalog_missing_file", "message": "The catalogued file is missing from the ingestion root."}
            failures.append(failure)
            self._event(
                "knowledge.ingest.file_failed", job_id=job_id, payload=failure,
                key=idempotency_key("knowledge.ingest.file_failed", job_id, relative.as_posix(), "missing"),
            )
        for candidate in files:
            relative = PurePosixPath(candidate.relative_to(self._root).as_posix())
            entry = catalog.get(relative) if catalog is not None else None
            try:
                content = candidate.read_bytes()
            except OSError as exc:
                failure = {"file_name": candidate.name, "relative_path": relative.as_posix(), "code": "ingest_read_failed", "message": "The file could not be read."}
                failures.append(failure)
                self._event("knowledge.ingest.file_failed", job_id=job_id, payload=failure, key=idempotency_key("knowledge.ingest.file_failed", job_id, relative.as_posix(), "read"))
                continue
            total_bytes += len(content)
            if total_bytes > self._max_total_bytes:
                failure = {"file_name": candidate.name, "relative_path": relative.as_posix(), "code": "ingest_too_large", "message": "The directory exceeds the ingestion byte limit."}
                failures.append(failure)
                self._event("knowledge.ingest.file_failed", job_id=job_id, payload=failure, key=idempotency_key("knowledge.ingest.file_failed", job_id, relative.as_posix(), "size"))
                break
            content_hash = _sha256(content)
            transaction_id = stable_id("knowledge-ingest-file", job_id, relative.as_posix(), content_hash)
            if entry is not None and content_hash != entry.source_hash:
                failure = {"file_name": candidate.name, "relative_path": relative.as_posix(), "code": "ingest_catalog_hash_mismatch", "message": "The file hash does not match the approved knowledge catalog."}
                failures.append(failure)
                self._event("knowledge.ingest.file_failed", job_id=job_id, payload={**failure, "transaction_id": transaction_id}, key=idempotency_key("knowledge.ingest.file_failed", transaction_id))
                continue
            source_ref = f"ingest:{relative.as_posix()}"
            try:
                manifest = self._layer.bulk_ingest(
                    task_id=self._task_id,
                    source_ref=source_ref,
                    file_name=candidate.name,
                    content=content,
                    clearance=self._clearance,
                )
            except IntakeError as exc:
                failure = {"file_name": candidate.name, "relative_path": relative.as_posix(), "code": f"ingest_{exc.code}", "message": str(exc), "transaction_id": transaction_id}
                failures.append(failure)
                self._event("knowledge.ingest.file_failed", job_id=job_id, payload=failure, key=idempotency_key("knowledge.ingest.file_failed", transaction_id))
                continue
            existing_chunks = tuple(
                chunk for chunk in self._indexer.index.chunks
                if chunk.source_ref == manifest.source_ref
                and chunk.revision_id == manifest.revision_id
                and chunk.revision_state == "current"
            )
            if existing_chunks:
                chunks = existing_chunks
            else:
                try:
                    chunks = self._indexer.index_manifest(IndexRequest(self._task_id, manifest))
                except Exception as exc:  # noqa: BLE001 - report a bounded per-file failure
                    failure = {"file_name": candidate.name, "relative_path": relative.as_posix(), "code": "ingest_index_failed", "message": "The file was accepted but could not be indexed.", "transaction_id": transaction_id}
                    failures.append(failure)
                    self._event("knowledge.ingest.file_failed", job_id=job_id, payload=failure, key=idempotency_key("knowledge.ingest.file_failed", transaction_id))
                    continue
            chunk_total += len(chunks)
            completed = {
                "file_name": candidate.name,
                "relative_path": relative.as_posix(),
                "source_ref": manifest.source_ref,
                "document_profile": entry.document_profile if entry is not None else None,
                "catalog_revision": entry.revision if entry is not None else None,
                "intake_id": manifest.intake_id,
                "revision_id": manifest.revision_id,
                "page_count": manifest.page_count,
                "chunk_count": len(chunks),
                "transaction_id": transaction_id,
                "ledger_event_ref": manifest.ledger_event_ref,
            }
            ingested.append(completed)
            self._event("knowledge.ingest.file_completed", job_id=job_id, payload=completed, key=idempotency_key("knowledge.ingest.file_completed", transaction_id))
        status = "completed" if not failures else ("partial" if ingested else "failed")
        result = {
            "job_id": job_id,
            "status": status,
            "root": str(self._root),
            "file_count": len(ingested),
            "chunk_count": chunk_total,
            "files": ingested,
            "failure_count": len(failures),
            "failures": failures,
        }
        self._event(
            "knowledge.ingest.completed", job_id=job_id,
            payload={"status": status, "file_count": len(ingested), "chunk_count": chunk_total, "failure_count": len(failures)},
            key=idempotency_key("knowledge.ingest.completed", job_id, status, len(ingested), chunk_total, len(failures)),
        )
        return result


__all__ = ["LocalNodeKnowledgeService"]
