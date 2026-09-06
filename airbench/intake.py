"""The single governed file intake boundary.

This module accepts bytes and metadata, identifies the source, produces a
stable manifest, and records an evidence event. It deliberately does not
interpret document text as instructions. Production OCR, vision, and rich
document parsers plug in behind ``DocumentParser`` without changing the
bulk-ingestion or query-upload boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from contracts import Clearance, EventLedger, Taint, build_event, idempotency_key, stable_id


MAX_FILE_BYTES = 50_000_000
_PDF_MAGIC = b"%PDF-"
_PDF_PAGE = re.compile(rb"/Type\s*/Page\b")
_TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log"}
_IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
    (b"BM", "image/bmp"),
)


class IntakeMode(str, Enum):
    bulk_ingest = "bulk_ingest"
    query_upload = "query_upload"


class IntakeError(ValueError):
    """A safe, stable intake failure that does not echo source content."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        return {"error": "intake_failed", "code": self.code, "message": str(self)}


@dataclass(frozen=True, slots=True)
class IntakeRequest:
    task_id: str
    source_ref: str
    file_name: str
    content: bytes
    mode: IntakeMode
    clearance: Clearance
    parser_version: str = "builtin-intake-1"
    destination: str = ""
    trust_profile: str = ""
    latency_profile: str = ""

    def __post_init__(self) -> None:
        defaults = {
            IntakeMode.bulk_ingest: ("permanent_knowledge", "bulk_candidate", "offline_enrichment"),
            IntakeMode.query_upload: ("task_scratch", "query_untrusted", "interactive"),
        }
        try:
            destination, trust_profile, latency_profile = defaults[self.mode]
        except (KeyError, TypeError) as exc:
            raise IntakeError("invalid_mode", "intake mode is invalid") from exc
        if not self.destination:
            object.__setattr__(self, "destination", destination)
        if not self.trust_profile:
            object.__setattr__(self, "trust_profile", trust_profile)
        if not self.latency_profile:
            object.__setattr__(self, "latency_profile", latency_profile)


@dataclass(frozen=True, slots=True)
class PageRecord:
    page_id: str
    page_number: int
    source_region: str
    content_hash: str
    media_type: str
    text: str
    extraction_method: str
    confidence: float
    clearance: Clearance
    taint: Taint
    evidence_ref: str
    rendered_page_ref: str | None = None
    render_status: str = "deferred"
    rendered_media_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "page_number": self.page_number,
            "source_region": self.source_region,
            "content_hash": self.content_hash,
            "media_type": self.media_type,
            "text": self.text,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
            "clearance": self.clearance.value,
            "taint": self.taint.value,
            "evidence_ref": self.evidence_ref,
            "rendered_page_ref": self.rendered_page_ref,
            "render_status": self.render_status,
            "rendered_media_type": self.rendered_media_type,
        }


@dataclass(frozen=True, slots=True)
class RenderedPage:
    """A renderer result that is still untrusted document data."""

    page_number: int
    content: bytes
    media_type: str

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise IntakeError("invalid_rendered_page", "rendered page number must be positive")
        if not self.content:
            raise IntakeError("empty_rendered_page", "rendered page content is empty")
        if not self.media_type or "/" not in self.media_type:
            raise IntakeError("invalid_rendered_media", "rendered page media type is invalid")


class PageRenderer(Protocol):
    name: str
    version: str

    def render(self, request: IntakeRequest, page: PageRecord) -> RenderedPage | None: ...


@dataclass(frozen=True, slots=True)
class IntakeManifest:
    intake_id: str
    task_id: str
    source_ref: str
    revision_id: str
    source_hash: str
    file_name: str
    media_type: str
    byte_size: int
    page_count: int
    parser_name: str
    parser_version: str
    extraction_settings: dict[str, str]
    pages: tuple[PageRecord, ...]
    mode: IntakeMode
    clearance: Clearance
    taint: Taint
    confidence: float
    ledger_event_ref: str
    ingested_at: str
    destination: str
    trust_profile: str
    latency_profile: str
    source_artifact_ref: str | None = None
    manifest_artifact_ref: str | None = None

    def to_dict(self, *, include_page_text: bool = True) -> dict[str, Any]:
        pages = []
        for page in self.pages:
            item = page.to_dict()
            if not include_page_text:
                item.pop("text", None)
            pages.append(item)
        return {
            "intake_id": self.intake_id,
            "task_id": self.task_id,
            "source_ref": self.source_ref,
            "revision_id": self.revision_id,
            "source_hash": self.source_hash,
            "file_name": self.file_name,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
            "page_count": self.page_count,
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "extraction_settings": dict(sorted(self.extraction_settings.items())),
            "pages": pages,
            "mode": self.mode.value,
            "clearance": self.clearance.value,
            "taint": self.taint.value,
            "confidence": self.confidence,
            "ledger_event_ref": self.ledger_event_ref,
            "ingested_at": self.ingested_at,
            "destination": self.destination,
            "trust_profile": self.trust_profile,
            "latency_profile": self.latency_profile,
            "source_artifact_ref": self.source_artifact_ref,
            "manifest_artifact_ref": self.manifest_artifact_ref,
        }

    def digest(self) -> str:
        payload = dict(self.to_dict(include_page_text=False))
        payload["ledger_event_ref"] = ""
        payload.pop("ingested_at", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DocumentParser(Protocol):
    name: str
    version: str

    def parse(self, request: IntakeRequest, source_hash: str) -> tuple[str, tuple[PageRecord, ...]]: ...


class IntakeStage(Protocol):
    """Prepared local storage that becomes visible only after ledger success."""

    def commit(self, manifest: IntakeManifest) -> None: ...

    def abort(self) -> None: ...


class IntakeStore(Protocol):
    def load(self, intake_id: str) -> IntakeManifest | None: ...

    def source_artifact_ref(self, intake_id: str) -> str: ...

    def manifest_artifact_ref(self, intake_id: str) -> str: ...

    def stage(
        self,
        manifest: IntakeManifest,
        source_content: bytes,
        rendered_pages: dict[str, bytes],
    ) -> IntakeStage: ...


class _LocalIntakeStage:
    def __init__(self, staging_path: Path, final_path: Path) -> None:
        self._staging_path = staging_path
        self._final_path = final_path
        self._closed = False

    def commit(self, manifest: IntakeManifest) -> None:
        if self._closed:
            raise IntakeError("storage_stage_closed", "intake storage stage is already closed")
        try:
            _atomic_write_json(self._staging_path / "manifest.json", manifest.to_dict())
            self._final_path.parent.mkdir(parents=True, exist_ok=True)
            if self._final_path.exists():
                raise IntakeError("storage_conflict", "intake identity already exists")
            os.replace(self._staging_path, self._final_path)
            self._closed = True
        except IntakeError:
            self.abort()
            raise
        except (OSError, TypeError, ValueError) as exc:
            self.abort()
            raise IntakeError("storage_commit_failed", "intake artifacts could not be committed") from exc

    def abort(self) -> None:
        if self._closed:
            return
        shutil.rmtree(self._staging_path, ignore_errors=True)
        self._closed = True


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    _atomic_write_bytes(path, encoded)


class LocalIntakeStore:
    """A local, network-free, transactional store for intake artifacts."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._staging_root = self._root / "staging"
        self._intakes_root = self._root / "intakes"
        self._staging_root.mkdir(parents=True, exist_ok=True)
        self._intakes_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_intake_id(intake_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", intake_id):
            raise IntakeError("invalid_intake_id", "intake identity is invalid")

    @classmethod
    def _ref(cls, intake_id: str, name: str) -> str:
        cls._validate_intake_id(intake_id)
        return f"intake://{intake_id}/{name}"

    def source_artifact_ref(self, intake_id: str) -> str:
        return self._ref(intake_id, "source")

    def manifest_artifact_ref(self, intake_id: str) -> str:
        return self._ref(intake_id, "manifest")

    def load(self, intake_id: str) -> IntakeManifest | None:
        self._validate_intake_id(intake_id)
        manifest_path = self._intakes_root / intake_id / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            pages = tuple(
                PageRecord(
                    page_id=item["page_id"],
                    page_number=item["page_number"],
                    source_region=item["source_region"],
                    content_hash=item["content_hash"],
                    media_type=item["media_type"],
                    text=item.get("text", ""),
                    extraction_method=item["extraction_method"],
                    confidence=item["confidence"],
                    clearance=Clearance(item["clearance"]),
                    taint=Taint(item["taint"]),
                    evidence_ref=item["evidence_ref"],
                    rendered_page_ref=item.get("rendered_page_ref"),
                    render_status=item.get("render_status", "deferred"),
                    rendered_media_type=item.get("rendered_media_type"),
                )
                for item in payload["pages"]
            )
            manifest = IntakeManifest(
                intake_id=payload["intake_id"],
                task_id=payload["task_id"],
                source_ref=payload["source_ref"],
                revision_id=payload["revision_id"],
                source_hash=payload["source_hash"],
                file_name=payload["file_name"],
                media_type=payload["media_type"],
                byte_size=payload["byte_size"],
                page_count=payload["page_count"],
                parser_name=payload["parser_name"],
                parser_version=payload["parser_version"],
                extraction_settings=dict(payload["extraction_settings"]),
                pages=pages,
                mode=IntakeMode(payload["mode"]),
                clearance=Clearance(payload["clearance"]),
                taint=Taint(payload["taint"]),
                confidence=payload["confidence"],
                ledger_event_ref=payload["ledger_event_ref"],
                ingested_at=payload["ingested_at"],
                destination=payload["destination"],
                trust_profile=payload["trust_profile"],
                latency_profile=payload["latency_profile"],
                source_artifact_ref=payload.get("source_artifact_ref"),
                manifest_artifact_ref=payload.get("manifest_artifact_ref"),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise IntakeError("storage_corrupt", "stored intake manifest is invalid") from exc
        if manifest.intake_id != intake_id:
            raise IntakeError("storage_corrupt", "stored intake identity does not match its path")
        source_path = self._intakes_root / intake_id / "source.bin"
        try:
            if not source_path.is_file() or source_path.stat().st_size != manifest.byte_size:
                raise IntakeError("storage_corrupt", "stored intake source is missing or incomplete")
            if _sha256(source_path.read_bytes()) != manifest.source_hash:
                raise IntakeError("storage_corrupt", "stored intake source hash does not match")
            for page in manifest.pages:
                if page.render_status == "ready":
                    page_path = self._intakes_root / intake_id / "pages" / f"{page.page_id}.bin"
                    if not page_path.is_file() or page_path.stat().st_size == 0:
                        raise IntakeError("storage_corrupt", "stored rendered page is missing")
        except IntakeError:
            raise
        except OSError as exc:
            raise IntakeError("storage_corrupt", "stored intake artifacts cannot be verified") from exc
        return manifest

    def stage(
        self,
        manifest: IntakeManifest,
        source_content: bytes,
        rendered_pages: dict[str, bytes],
    ) -> IntakeStage:
        if manifest.source_artifact_ref != self.source_artifact_ref(manifest.intake_id):
            raise IntakeError("storage_reference_mismatch", "source artifact reference is invalid")
        if manifest.manifest_artifact_ref != self.manifest_artifact_ref(manifest.intake_id):
            raise IntakeError("storage_reference_mismatch", "manifest artifact reference is invalid")
        if _sha256(source_content) != manifest.source_hash:
            raise IntakeError("storage_source_mismatch", "source content does not match the manifest")
        expected_pages = {
            page.page_id for page in manifest.pages if page.render_status == "ready"
        }
        if set(rendered_pages) != expected_pages:
            raise IntakeError("storage_page_mismatch", "rendered page artifacts do not match the manifest")

        self._validate_intake_id(manifest.intake_id)
        final_path = self._intakes_root / manifest.intake_id
        if final_path.exists():
            raise IntakeError("storage_conflict", "intake identity already exists")
        staging_path = Path(tempfile.mkdtemp(prefix=f"{manifest.intake_id}-", dir=self._staging_root))
        try:
            (staging_path / "pages").mkdir(parents=True, exist_ok=False)
            _atomic_write_bytes(staging_path / "source.bin", source_content)
            for page_id, content in rendered_pages.items():
                _atomic_write_bytes(staging_path / "pages" / f"{page_id}.bin", content)
        except (OSError, ValueError) as exc:
            shutil.rmtree(staging_path, ignore_errors=True)
            raise IntakeError("storage_prepare_failed", "intake artifacts could not be staged") from exc
        return _LocalIntakeStage(staging_path, final_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _media_type(file_name: str, content: bytes) -> str:
    suffix = Path(file_name).suffix.lower()
    if content.startswith(_PDF_MAGIC) and suffix == ".pdf":
        return "application/pdf"
    for signature, media_type in _IMAGE_SIGNATURES:
        if content.startswith(signature):
            return media_type
    if suffix in _TEXT_SUFFIXES:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IntakeError("malformed_text", "the text document is not valid UTF-8") from exc
        return {
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".json": "application/json",
            ".log": "text/plain",
        }[suffix]
    raise IntakeError("unsupported_media", "the File Intake Layer does not support this file type")


def _validate_request(request: IntakeRequest) -> None:
    if not request.task_id or not request.source_ref:
        raise IntakeError("missing_identity", "task and source identities are required")
    if not request.file_name or len(request.file_name) > 255:
        raise IntakeError("invalid_file_name", "file name is missing or too long")
    if any(char in request.file_name for char in ("/", "\\", "\x00")) or request.file_name in {".", ".."}:
        raise IntakeError("invalid_file_name", "file name must not contain path syntax")
    if len(request.content) == 0:
        raise IntakeError("empty_file", "empty files are rejected")
    if len(request.content) > MAX_FILE_BYTES:
        raise IntakeError("file_too_large", "file exceeds the intake size limit")
    if not request.parser_version.strip():
        raise IntakeError("invalid_parser_version", "parser version is required")
    if not isinstance(request.clearance, Clearance):
        raise IntakeError("invalid_clearance", "clearance must be a typed contract value")
    expected = {
        IntakeMode.bulk_ingest: ("permanent_knowledge", "bulk_candidate", "offline_enrichment"),
        IntakeMode.query_upload: ("task_scratch", "query_untrusted", "interactive"),
    }.get(request.mode)
    if expected is None or (request.destination, request.trust_profile, request.latency_profile) != expected:
        raise IntakeError("invalid_switches", "destination, trust, and latency switches do not match the intake mode")


class BuiltinDocumentParser:
    name = "builtin-safe-metadata-parser"
    version = "builtin-intake-1"

    def parse(self, request: IntakeRequest, source_hash: str) -> tuple[str, tuple[PageRecord, ...]]:
        media_type = _media_type(request.file_name, request.content)
        suffix = Path(request.file_name).suffix.lower()
        if media_type == "application/pdf":
            page_count = max(1, len(_PDF_PAGE.findall(request.content)))
            extraction_method = "pdf_metadata_only"
            texts = [""] * page_count
        elif media_type.startswith("image/"):
            page_count = 1
            extraction_method = "image_metadata_only"
            texts = [""]
        else:
            page_count = 1
            extraction_method = "utf8_text_decode"
            texts = [request.content.decode("utf-8")]

        pages = tuple(
            PageRecord(
                page_id=stable_id("page", request.source_ref, source_hash, page_number),
                page_number=page_number,
                source_region=f"page:{page_number}",
                content_hash=hashlib.sha256(f"{source_hash}:page:{page_number}".encode()).hexdigest(),
                media_type=media_type,
                text=text,
                extraction_method=extraction_method,
                confidence=1.0 if extraction_method == "utf8_text_decode" else 0.0,
                clearance=request.clearance,
                taint=Taint.untrusted,
                evidence_ref=stable_id("evidence", request.source_ref, source_hash, page_number),
                rendered_page_ref=None,
                render_status="deferred",
            )
            for page_number, text in enumerate(texts, start=1)
        )
        return media_type, pages


class LedgerSink(Protocol):
    @property
    def events(self) -> tuple[Any, ...]: ...

    @property
    def head_hash(self) -> str | None: ...

    def append(self, event: Any) -> Any: ...


def _append_evidence_event(ledger: LedgerSink, manifest: IntakeManifest) -> str:
    key = idempotency_key("intake.evidence.created", manifest.task_id, manifest.intake_id)
    existing = next((event for event in ledger.events if event.idempotency_key == key), None)
    if existing is not None:
        return existing.event_id
    event = build_event(
        event_type="evidence.created",
        task_id=manifest.task_id,
        actor_id="intake.layer",
        actor_type="service",
        payload_contract="IntakeManifest",
        payload_version="1.0",
        payload={
            "intake_id": manifest.intake_id,
            "revision_id": manifest.revision_id,
            "manifest_hash": manifest.digest(),
            "source_hash": manifest.source_hash,
            "page_ids": [page.page_id for page in manifest.pages],
            "source_artifact_ref": manifest.source_artifact_ref,
            "manifest_artifact_ref": manifest.manifest_artifact_ref,
            "rendered_page_refs": [
                page.rendered_page_ref for page in manifest.pages if page.rendered_page_ref
            ],
            "destination": manifest.destination,
            "trust_profile": manifest.trust_profile,
            "latency_profile": manifest.latency_profile,
            "provenance": {
                "source_ref": manifest.source_ref,
                "confidence": manifest.confidence,
                "clearance": manifest.clearance.value,
                "taint": manifest.taint.value,
            },
        },
        clearance=manifest.clearance,
            idempotency=key,
        sequence=len(ledger.events),
        previous_event_hash=ledger.head_hash,
        occurred_at=manifest.ingested_at,
    )
    try:
        ledger.append(event)
    except Exception as exc:  # the caller must see that the evidence was not committed
        raise IntakeError("ledger_write_failed", "intake evidence could not be committed") from exc
    return event.event_id


class FileIntakeLayer:
    """One parser boundary shared by bulk ingestion and query uploads."""

    def __init__(
        self,
        ledger: LedgerSink,
        parser: DocumentParser | None = None,
        *,
        renderer: PageRenderer | None = None,
        store: IntakeStore | None = None,
    ) -> None:
        self._ledger = ledger
        self._parser = parser or BuiltinDocumentParser()
        self._renderer = renderer
        self._store = store

    def intake(self, request: IntakeRequest) -> IntakeManifest:
        _validate_request(request)
        source_hash = _sha256(request.content)
        renderer_name = self._renderer.name if self._renderer is not None else "none"
        renderer_version = self._renderer.version if self._renderer is not None else "none"
        intake_id = stable_id(
            "intake", request.task_id, request.source_ref, source_hash, request.mode.value,
            self._parser.name, self._parser.version, renderer_name, renderer_version,
        )
        if self._store is not None:
            existing = self._store.load(intake_id)
            if existing is not None:
                if not any(event.event_id == existing.ledger_event_ref for event in self._ledger.events):
                    raise IntakeError("storage_ledger_mismatch", "stored intake is missing its ledger evidence")
                return existing
        media_type, pages = self._parser.parse(request, source_hash)
        if self._renderer is not None and self._store is None:
            raise IntakeError("renderer_requires_store", "rendered pages require an intake store")
        rendered_pages: dict[str, bytes] = {}
        rendered_records: list[PageRecord] = []
        for page in pages:
            if self._renderer is None:
                rendered_records.append(page)
                continue
            try:
                rendered = self._renderer.render(request, page)
            except IntakeError:
                raise
            except Exception as exc:
                raise IntakeError("render_failed", "page rendering failed") from exc
            if rendered is None:
                rendered_records.append(page)
                continue
            if rendered.page_number != page.page_number:
                raise IntakeError("rendered_page_mismatch", "renderer returned the wrong page")
            rendered_pages[page.page_id] = rendered.content
            rendered_records.append(replace(
                page,
                rendered_page_ref=f"intake://{intake_id}/pages/{page.page_id}",
                render_status="ready",
                rendered_media_type=rendered.media_type,
            ))
        pages = tuple(rendered_records)
        ingested_at = _now()
        manifest = IntakeManifest(
            intake_id=intake_id,
            task_id=request.task_id,
            source_ref=request.source_ref,
            revision_id=stable_id("revision", request.source_ref, source_hash, self._parser.version, renderer_version),
            source_hash=source_hash,
            file_name=request.file_name,
            media_type=media_type,
            byte_size=len(request.content),
            page_count=len(pages),
            parser_name=self._parser.name,
            parser_version=self._parser.version,
            extraction_settings={
                "mode": request.mode.value,
                "parser_version": self._parser.version,
                "renderer_name": renderer_name,
                "renderer_version": renderer_version,
            },
            pages=pages,
            mode=request.mode,
            clearance=request.clearance,
            taint=Taint.untrusted,
            confidence=min((page.confidence for page in pages), default=0.0),
            ledger_event_ref="",
            ingested_at=ingested_at,
            destination=request.destination,
            trust_profile=request.trust_profile,
            latency_profile=request.latency_profile,
            source_artifact_ref=(self._store.source_artifact_ref(intake_id) if self._store else None),
            manifest_artifact_ref=(self._store.manifest_artifact_ref(intake_id) if self._store else None),
        )
        staged: IntakeStage | None = None
        if self._store is not None:
            try:
                staged = self._store.stage(manifest, request.content, rendered_pages)
            except IntakeError:
                raise
            except Exception as exc:
                raise IntakeError("storage_prepare_failed", "intake artifacts could not be staged") from exc
        try:
            ledger_event_ref = _append_evidence_event(self._ledger, manifest)
        except IntakeError:
            if staged is not None:
                staged.abort()
            raise
        committed = replace(manifest, ledger_event_ref=ledger_event_ref)
        if staged is not None:
            try:
                staged.commit(committed)
            except IntakeError:
                raise
            except Exception as exc:
                staged.abort()
                raise IntakeError("storage_commit_failed", "intake artifacts could not be committed") from exc
        return committed

    def bulk_ingest(self, *, task_id: str, source_ref: str, file_name: str, content: bytes, clearance: Clearance) -> IntakeManifest:
        return self.intake(IntakeRequest(task_id, source_ref, file_name, content, IntakeMode.bulk_ingest, clearance))

    def query_upload(self, *, task_id: str, source_ref: str, file_name: str, content: bytes, clearance: Clearance) -> IntakeManifest:
        return self.intake(IntakeRequest(task_id, source_ref, file_name, content, IntakeMode.query_upload, clearance))
