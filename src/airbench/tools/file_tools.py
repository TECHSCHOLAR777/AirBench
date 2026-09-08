"""Safe local file, typed spreadsheet, and artifact operations.

This module deliberately does not parse uploaded files. File interpretation is
owned by ``FileIntakeLayer``. Spreadsheet operations accept a typed table that
the intake boundary or another approved producer has already created.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import mimetypes
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from contracts import (Clearance, LedgerEventEnvelope, Taint, build_event,
                       idempotency_key, stable_id)


class FileToolError(RuntimeError):
    """A file or typed-table operation was rejected safely."""


class FileToolLedger(Protocol):
    @property
    def events(self) -> tuple[LedgerEventEnvelope, ...]: ...

    @property
    def head_hash(self) -> str | None: ...

    def append(self, event: LedgerEventEnvelope) -> Any: ...


@dataclass(frozen=True, slots=True)
class WorkspacePolicy:
    workspace_root: Path
    source_mounts: tuple[Path, ...] = ()
    max_read_bytes: int = 50_000_000
    max_write_bytes: int = 50_000_000

    def validate(self) -> None:
        if self.max_read_bytes <= 0 or self.max_read_bytes > 500_000_000:
            raise FileToolError("read size limit is invalid")
        if self.max_write_bytes <= 0 or self.max_write_bytes > 500_000_000:
            raise FileToolError("write size limit is invalid")
        if not self.workspace_root:
            raise FileToolError("workspace root is required")


@dataclass(frozen=True, slots=True)
class FileProvenance:
    source_ref: str
    confidence: float
    clearance: Clearance
    taint: Taint

    def validate(self) -> None:
        if not self.source_ref or not 0 <= self.confidence <= 1:
            raise FileToolError("file provenance is incomplete")


@dataclass(frozen=True, slots=True)
class FileReadResult:
    path: str
    content: bytes
    content_hash: str
    byte_size: int
    provenance: FileProvenance
    ledger_event_ref: str


@dataclass(frozen=True, slots=True)
class FileWriteResult:
    path: str
    content_hash: str
    byte_size: int
    provenance: FileProvenance
    ledger_event_ref: str


@dataclass(frozen=True, slots=True)
class ArtifactInspection:
    path: str
    content_hash: str
    byte_size: int
    media_type: str
    provenance: FileProvenance
    ledger_event_ref: str


@dataclass(frozen=True, slots=True)
class SpreadsheetTable:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    provenance: FileProvenance
    revision_id: str

    def validate(self) -> None:
        self.provenance.validate()
        if not self.columns or len(set(self.columns)) != len(self.columns):
            raise FileToolError("spreadsheet columns must be non-empty and unique")
        if not self.revision_id:
            raise FileToolError("spreadsheet revision is required")
        if any(len(row) != len(self.columns) for row in self.rows):
            raise FileToolError("spreadsheet row width does not match columns")
        if len(self.rows) > 100_000:
            raise FileToolError("spreadsheet row limit exceeded")


@dataclass(frozen=True, slots=True)
class ComputedValue:
    name: str
    value_text: str
    provenance: FileProvenance
    ledger_event_ref: str


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _rank(clearance: Clearance) -> int:
    return {Clearance.public: 0, Clearance.internal: 1, Clearance.restricted: 2, Clearance.secret: 3}[clearance]


def _highest_clearance(*provenance: FileProvenance) -> Clearance:
    return max((item.clearance for item in provenance), key=_rank)


def _combined_taint(*provenance: FileProvenance) -> Taint:
    if any(item.taint == Taint.contaminated for item in provenance):
        return Taint.contaminated
    if any(item.taint == Taint.untrusted for item in provenance):
        return Taint.untrusted
    return Taint.clean


class FileToolRunner:
    """Perform bounded opaque file operations within a workspace policy."""

    def __init__(self, ledger: FileToolLedger, policy: WorkspacePolicy) -> None:
        policy.validate()
        self._ledger = ledger
        self._policy = policy

    def read(self, *, task_id: str, operation_id: str, path: str, clearance: Clearance) -> FileReadResult:
        resolved = self._resolve_read(path)
        try:
            size = resolved.stat().st_size
            if size > self._policy.max_read_bytes:
                raise FileToolError("file exceeds the read size limit")
            content = resolved.read_bytes()
        except FileToolError:
            raise
        except OSError as exc:
            raise FileToolError("file could not be read") from exc
        content_hash = _hash_bytes(content)
        provenance = FileProvenance(f"file:{content_hash}", 1.0, clearance, Taint.untrusted)
        event_ref = self._append(
            event_type="artifact.checked", task_id=task_id, operation_id=operation_id,
            clearance=clearance,
            payload={"operation": "read", "path": self._display_path(resolved), "content_hash": content_hash,
                     "byte_size": len(content), "provenance": self._provenance_dict(provenance)},
        )
        return FileReadResult(self._display_path(resolved), content, content_hash, len(content), provenance, event_ref)

    def write(self, *, task_id: str, operation_id: str, path: str, content: bytes,
              provenance: FileProvenance) -> FileWriteResult:
        self._validate_content(content, self._policy.max_write_bytes)
        provenance.validate()
        resolved = self._resolve_write(path)
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_bytes(content)
        except OSError as exc:
            raise FileToolError("file could not be written") from exc
        content_hash = _hash_bytes(content)
        event_ref = self._append(
            event_type="artifact.staged", task_id=task_id, operation_id=operation_id,
            clearance=provenance.clearance,
            payload={"operation": "write", "path": self._display_path(resolved), "content_hash": content_hash,
                     "byte_size": len(content), "provenance": self._provenance_dict(provenance)},
        )
        return FileWriteResult(self._display_path(resolved), content_hash, len(content), provenance, event_ref)

    def inspect(self, *, task_id: str, operation_id: str, path: str, clearance: Clearance) -> ArtifactInspection:
        result = self.read(task_id=task_id, operation_id=f"{operation_id}.read", path=path, clearance=clearance)
        media_type = mimetypes.guess_type(result.path)[0] or "application/octet-stream"
        event_ref = self._append(
            event_type="artifact.checked", task_id=task_id, operation_id=operation_id,
            clearance=clearance,
            payload={"operation": "inspect", "path": result.path, "content_hash": result.content_hash,
                     "byte_size": result.byte_size, "media_type": media_type,
                     "provenance": self._provenance_dict(result.provenance)},
        )
        return ArtifactInspection(result.path, result.content_hash, result.byte_size, media_type, result.provenance, event_ref)

    def write_csv(self, *, task_id: str, operation_id: str, path: str, table: SpreadsheetTable) -> FileWriteResult:
        table.validate()
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(table.columns)
        writer.writerows(table.rows)
        return self.write(
            task_id=task_id,
            operation_id=operation_id,
            path=path,
            content=buffer.getvalue().encode("utf-8"),
            provenance=table.provenance,
        )

    def _resolve_read(self, path: str) -> Path:
        resolved = self._resolve(path)
        roots = (self._policy.workspace_root, *self._policy.source_mounts)
        if not self._inside(resolved, roots):
            raise FileToolError("read path is outside the workspace and source mounts")
        if not resolved.is_file():
            raise FileToolError("read path is not a regular file")
        return resolved

    def _resolve_write(self, path: str) -> Path:
        resolved = self._resolve(path)
        if not self._inside(resolved, (self._policy.workspace_root,)):
            raise FileToolError("write path is outside the workspace")
        return resolved

    @staticmethod
    def _resolve(path: str) -> Path:
        if not isinstance(path, str) or not path or "\x00" in path:
            raise FileToolError("file path is invalid")
        try:
            return Path(path).resolve(strict=False)
        except (OSError, RuntimeError, ValueError) as exc:
            raise FileToolError("file path could not be resolved") from exc

    @staticmethod
    def _inside(path: Path, roots: tuple[Path, ...]) -> bool:
        return any(path == root.resolve() or root.resolve() in path.parents for root in roots)

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._policy.workspace_root.resolve()))
        except ValueError:
            return str(path)

    @staticmethod
    def _validate_content(content: bytes, limit: int) -> None:
        if not isinstance(content, bytes):
            raise FileToolError("file content must be bytes")
        if len(content) > limit:
            raise FileToolError("file content exceeds the size limit")

    def _append(self, *, event_type: str, task_id: str, operation_id: str,
                clearance: Clearance, payload: dict[str, Any]) -> str:
        key = idempotency_key("file-tool", task_id, operation_id, event_type)
        existing = next((event for event in self._ledger.events if event.idempotency_key == key), None)
        if existing is not None:
            return existing.event_id
        event = build_event(
            event_type=event_type, task_id=task_id, actor_id="file-tools.local",
            actor_type="service", payload_contract="FileToolResult", payload_version="1.0",
            payload=payload, clearance=clearance, idempotency=key,
            sequence=len(self._ledger.events), previous_event_hash=self._ledger.head_hash,
        )
        try:
            self._ledger.append(event)
        except Exception as exc:
            raise FileToolError("file tool ledger append failed") from exc
        return event.event_id

    @staticmethod
    def _provenance_dict(provenance: FileProvenance) -> dict[str, Any]:
        return {
            "source_ref": provenance.source_ref,
            "confidence": provenance.confidence,
            "clearance": provenance.clearance.value,
            "taint": provenance.taint.value,
        }


class SpreadsheetTool:
    """Operate on already typed tables without adding a parser."""

    def __init__(self, ledger: FileToolLedger) -> None:
        self._ledger = ledger

    def select_columns(self, *, task_id: str, operation_id: str, table: SpreadsheetTable,
                       columns: tuple[str, ...]) -> SpreadsheetTable:
        table.validate()
        if not columns or any(column not in table.columns for column in columns):
            raise FileToolError("requested spreadsheet column is unavailable")
        indexes = tuple(table.columns.index(column) for column in columns)
        result = SpreadsheetTable(
            columns=columns,
            rows=tuple(tuple(row[index] for index in indexes) for row in table.rows),
            provenance=self._derived_provenance(table.provenance, f"select:{columns}"),
            revision_id=stable_id("table", table.revision_id, operation_id),
        )
        return self._record_table(task_id, operation_id, result, "select_columns")

    def filter_equals(self, *, task_id: str, operation_id: str, table: SpreadsheetTable,
                      column: str, value: Any) -> SpreadsheetTable:
        table.validate()
        if column not in table.columns:
            raise FileToolError("filter column is unavailable")
        index = table.columns.index(column)
        result = SpreadsheetTable(
            columns=table.columns,
            rows=tuple(row for row in table.rows if row[index] == value),
            provenance=self._derived_provenance(table.provenance, f"filter:{column}"),
            revision_id=stable_id("table", table.revision_id, operation_id),
        )
        return self._record_table(task_id, operation_id, result, "filter_equals")

    def sum_column(self, *, task_id: str, operation_id: str, table: SpreadsheetTable,
                   column: str, name: str) -> ComputedValue:
        table.validate()
        if column not in table.columns or not name:
            raise FileToolError("sum column or result name is invalid")
        index = table.columns.index(column)
        total = Decimal("0")
        try:
            for row in table.rows:
                value = row[index]
                if isinstance(value, bool):
                    raise InvalidOperation
                number = Decimal(str(value))
                if not number.is_finite():
                    raise InvalidOperation
                total += number
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise FileToolError("spreadsheet sum requires finite numeric values") from exc
        provenance = self._derived_provenance(table.provenance, f"sum:{column}")
        event_ref = self._append(
            task_id=task_id, operation_id=operation_id, clearance=provenance.clearance,
            payload={"operation": "sum_column", "name": name, "value_text": format(total, "f"),
                     "provenance": FileToolRunner._provenance_dict(provenance)},
        )
        return ComputedValue(name, format(total, "f"), provenance, event_ref)

    def _record_table(self, task_id: str, operation_id: str, table: SpreadsheetTable, operation: str) -> SpreadsheetTable:
        self._append(
            task_id=task_id, operation_id=operation_id, clearance=table.provenance.clearance,
            payload={"operation": operation, "revision_id": table.revision_id,
                     "columns": list(table.columns), "row_count": len(table.rows),
                     "provenance": FileToolRunner._provenance_dict(table.provenance)},
        )
        return table

    def _derived_provenance(self, source: FileProvenance, operation: str) -> FileProvenance:
        return FileProvenance(
            source_ref=f"derived:{stable_id('table-source', source.source_ref, operation)}",
            confidence=source.confidence,
            clearance=source.clearance,
            taint=source.taint,
        )

    def _append(self, *, task_id: str, operation_id: str, clearance: Clearance, payload: dict[str, Any]) -> str:
        key = idempotency_key("spreadsheet-tool", task_id, operation_id)
        existing = next((event for event in self._ledger.events if event.idempotency_key == key), None)
        if existing is not None:
            return existing.event_id
        event = build_event(
            event_type="artifact.checked", task_id=task_id, actor_id="spreadsheet-tools.local",
            actor_type="service", payload_contract="SpreadsheetResult", payload_version="1.0",
            payload=payload, clearance=clearance, idempotency=key,
            sequence=len(self._ledger.events), previous_event_hash=self._ledger.head_hash,
        )
        try:
            self._ledger.append(event)
        except Exception as exc:
            raise FileToolError("spreadsheet tool ledger append failed") from exc
        return event.event_id


__all__ = [
    "FileToolError", "WorkspacePolicy", "FileProvenance", "FileReadResult",
    "FileWriteResult", "ArtifactInspection", "SpreadsheetTable", "ComputedValue",
    "FileToolRunner", "SpreadsheetTool",
]
