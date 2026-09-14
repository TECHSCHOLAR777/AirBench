"""Node-owned bulk knowledge ingestion.

Bulk ingestion uses the same single File Intake Layer as query uploads, then
hands the committed manifest to the local indexer.  A directory may only be
ingested from an operator-configured root, so a client cannot ask the Node to
walk an arbitrary host path.  Files remain untrusted data throughout.
"""

from __future__ import annotations

from pathlib import Path

from airbench.intake.layer import FileIntakeLayer, IntakeError
from airbench.knowledge.retrieval import IndexRequest, LocalIndexer

from .intake_gateway import NodeIntakeError


MAX_INGEST_FILES = 500
MAX_INGEST_BYTES = 500_000_000


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
    ) -> None:
        self._layer = layer
        self._indexer = indexer
        self._root = Path(ingest_root).resolve()
        self._task_id = task_id
        self._clearance = clearance_context
        self._max_files = max_files
        self._max_total_bytes = max_total_bytes

    def ingest_directory(self, *, path: str) -> dict:
        if not self._root.is_dir():
            raise NodeIntakeError(503, "ingest_root_unavailable", "The configured ingestion root does not exist.")
        target = Path(path)
        resolved = (target if target.is_absolute() else self._root / target).resolve()
        if resolved != self._root and self._root not in resolved.parents:
            raise NodeIntakeError(403, "ingest_root_denied", "The requested path is outside the configured ingestion root.")
        if not resolved.is_dir():
            raise NodeIntakeError(404, "ingest_path_not_found", "The requested ingestion directory does not exist.")

        files = sorted(candidate for candidate in resolved.rglob("*") if candidate.is_file())
        if len(files) > self._max_files:
            raise NodeIntakeError(413, "ingest_too_many_files", "The directory contains more files than the ingestion limit.")

        total_bytes = 0
        ingested: list[dict] = []
        failures: list[dict] = []
        chunk_total = 0
        for candidate in files:
            try:
                content = candidate.read_bytes()
            except OSError as exc:
                failures.append({"file_name": candidate.name, "code": "ingest_read_failed", "message": "The file could not be read."})
                continue
            total_bytes += len(content)
            if total_bytes > self._max_total_bytes:
                failures.append({"file_name": candidate.name, "code": "ingest_too_large", "message": "The directory exceeds the ingestion byte limit."})
                break
            source_ref = f"ingest:{resolved.relative_to(self._root).as_posix()}/{candidate.name}"
            try:
                manifest = self._layer.bulk_ingest(
                    task_id=self._task_id,
                    source_ref=source_ref,
                    file_name=candidate.name,
                    content=content,
                    clearance=self._clearance,
                )
            except IntakeError as exc:
                failures.append({"file_name": candidate.name, "code": f"ingest_{exc.code}", "message": str(exc)})
                continue
            try:
                chunks = self._indexer.index_manifest(IndexRequest(self._task_id, manifest))
            except Exception as exc:  # noqa: BLE001 - report a bounded per-file failure
                failures.append({"file_name": candidate.name, "code": "ingest_index_failed", "message": "The file was accepted but could not be indexed."})
                continue
            chunk_total += len(chunks)
            ingested.append({
                "file_name": candidate.name,
                "intake_id": manifest.intake_id,
                "revision_id": manifest.revision_id,
                "page_count": manifest.page_count,
                "chunk_count": len(chunks),
            })
        status = "completed" if not failures else ("partial" if ingested else "failed")
        return {
            "status": status,
            "root": str(self._root),
            "file_count": len(ingested),
            "chunk_count": chunk_total,
            "files": ingested,
            "failure_count": len(failures),
            "failures": failures,
        }


__all__ = ["LocalNodeKnowledgeService"]
