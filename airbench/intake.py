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
import re
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
        }


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
        }

    def digest(self) -> str:
        payload = dict(self.to_dict(include_page_text=False))
        payload["ledger_event_ref"] = ""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DocumentParser(Protocol):
    name: str
    version: str

    def parse(self, request: IntakeRequest, source_hash: str) -> tuple[str, tuple[PageRecord, ...]]: ...


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
        idempotency=idempotency_key("intake.evidence.created", manifest.task_id, manifest.intake_id),
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

    def __init__(self, ledger: LedgerSink, parser: DocumentParser | None = None) -> None:
        self._ledger = ledger
        self._parser = parser or BuiltinDocumentParser()

    def intake(self, request: IntakeRequest) -> IntakeManifest:
        _validate_request(request)
        source_hash = _sha256(request.content)
        media_type, pages = self._parser.parse(request, source_hash)
        ingested_at = _now()
        manifest = IntakeManifest(
            intake_id=stable_id("intake", request.task_id, request.source_ref, source_hash, request.mode.value),
            task_id=request.task_id,
            source_ref=request.source_ref,
            revision_id=stable_id("revision", request.source_ref, source_hash, self._parser.version),
            source_hash=source_hash,
            file_name=request.file_name,
            media_type=media_type,
            byte_size=len(request.content),
            page_count=len(pages),
            parser_name=self._parser.name,
            parser_version=self._parser.version,
            extraction_settings={"mode": request.mode.value, "parser_version": self._parser.version},
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
        )
        ledger_event_ref = _append_evidence_event(self._ledger, manifest)
        return replace(manifest, ledger_event_ref=ledger_event_ref)

    def bulk_ingest(self, *, task_id: str, source_ref: str, file_name: str, content: bytes, clearance: Clearance) -> IntakeManifest:
        return self.intake(IntakeRequest(task_id, source_ref, file_name, content, IntakeMode.bulk_ingest, clearance))

    def query_upload(self, *, task_id: str, source_ref: str, file_name: str, content: bytes, clearance: Clearance) -> IntakeManifest:
        return self.intake(IntakeRequest(task_id, source_ref, file_name, content, IntakeMode.query_upload, clearance))
