"""The single governed file intake boundary.

This module accepts bytes and metadata, identifies the source, produces a
stable manifest, and records an evidence event. It deliberately does not
interpret document text as instructions. Production OCR, vision, and rich
document parsers plug in behind ``DocumentParser`` without changing the
bulk-ingestion or query-upload boundary.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Protocol
from xml.etree import ElementTree

from contracts import Clearance, EventLedger, Taint, build_event, idempotency_key, stable_id
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError


MAX_FILE_BYTES = 50_000_000
MAX_OFFICE_ZIP_MEMBERS = 1_024
MAX_OFFICE_UNCOMPRESSED_BYTES = 100_000_000
MAX_CSV_ROWS = 1_000_000
MAX_CSV_COLUMNS = 4_096
MAX_PDF_PAGES = 10_000
MAX_PDF_PAGE_TEXT_BYTES = 2_000_000
MAX_PDF_TEXT_BYTES = 20_000_000
MAX_IMAGE_PIXELS = 100_000_000
MAX_IMAGE_DIMENSION = 32_768
_PDF_MAGIC = b"%PDF-"
_TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log"}
_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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


def _semantic_revision_hash(
    media_type: str,
    page_data: list[tuple[str, str]] | tuple[tuple[str, str], ...],
    source_hash: str,
) -> str:
    """Fingerprint parsed content while retaining raw identity for opaque pages.

    Office archives commonly carry changing ZIP metadata such as timestamps.
    Those bytes are retained as ``source_hash`` for provenance, but they must
    not make bulk and query parsing of the same document appear to be different
    revisions. Images and text-free scans remain bound to their raw bytes so
    two opaque documents cannot collapse to one revision.
    """

    normalized = [(str(region), str(text)) for region, text in page_data]
    material: dict[str, Any] = {"media_type": media_type, "pages": normalized}
    if media_type.startswith("image/") or not any(text for _, text in normalized):
        material["source_hash"] = source_hash
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _media_type(file_name: str, content: bytes) -> str:
    suffix = Path(file_name).suffix.lower()
    if content.startswith(_PDF_MAGIC) and suffix == ".pdf":
        return "application/pdf"
    if suffix == ".docx":
        if not content.startswith(b"PK"):
            raise IntakeError("malformed_office", "the DOCX archive is malformed")
        return _DOCX_MEDIA_TYPE
    if suffix == ".xlsx":
        if not content.startswith(b"PK"):
            raise IntakeError("malformed_office", "the XLSX archive is malformed")
        return _XLSX_MEDIA_TYPE
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


def _pdf_pages(content: bytes) -> list[tuple[str, str]]:
    """Extract bounded digital PDF text without executing document content."""

    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
    except (OSError, ValueError, TypeError, PdfReadError) as exc:
        raise IntakeError("malformed_pdf", "the PDF document is malformed") from exc
    if reader.is_encrypted:
        raise IntakeError("encrypted_pdf", "encrypted PDF documents require an approved decryption adapter")
    try:
        page_count = len(reader.pages)
    except (OSError, ValueError, TypeError, PdfReadError) as exc:
        raise IntakeError("malformed_pdf", "the PDF page tree is malformed") from exc
    if page_count < 1:
        raise IntakeError("pdf_no_pages", "the PDF document has no pages")
    if page_count > MAX_PDF_PAGES:
        raise IntakeError("pdf_too_many_pages", "the PDF document has too many pages")

    pages: list[tuple[str, str]] = []
    total_text_bytes = 0
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except (OSError, ValueError, TypeError, PdfReadError) as exc:
            raise IntakeError("pdf_text_extraction_failed", "the PDF text could not be extracted") from exc
        page_text_bytes = len(text.encode("utf-8"))
        if page_text_bytes > MAX_PDF_PAGE_TEXT_BYTES:
            raise IntakeError("pdf_page_text_too_large", "a PDF page contains too much extracted text")
        total_text_bytes += page_text_bytes
        if total_text_bytes > MAX_PDF_TEXT_BYTES:
            raise IntakeError("pdf_text_too_large", "the PDF contains too much extracted text")
        pages.append((f"page:{page_number}", text))
    return pages


def _validate_image(content: bytes) -> None:
    """Validate image structure and dimensions without decoding pixels for OCR."""

    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            if (
                width < 1
                or height < 1
                or width > MAX_IMAGE_DIMENSION
                or height > MAX_IMAGE_DIMENSION
                or width * height > MAX_IMAGE_PIXELS
            ):
                raise IntakeError("image_dimensions_too_large", "the image dimensions exceed the intake limit")
            image.verify()
    except IntakeError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise IntakeError("malformed_image", "the image document is malformed") from exc


def _csv_table(content: bytes) -> str:
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntakeError("malformed_text", "the CSV document is not valid UTF-8") from exc
    reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
    rows: list[str] = []
    try:
        for row_number, row in enumerate(reader, start=1):
            if row_number > MAX_CSV_ROWS:
                raise IntakeError("csv_too_many_rows", "the CSV document has too many rows")
            if len(row) > MAX_CSV_COLUMNS:
                raise IntakeError("csv_too_many_columns", "the CSV document has too many columns")
            rows.append("\t".join(row))
    except csv.Error as exc:
        raise IntakeError("malformed_csv", "the CSV document is malformed") from exc
    return "\n".join(rows)


def _safe_office_members(content: bytes) -> dict[str, bytes]:
    """Read only bounded ZIP members and never extract archive paths."""

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise IntakeError("malformed_office", "the office archive is malformed") from exc

    try:
        infos = archive.infolist()
        if len(infos) > MAX_OFFICE_ZIP_MEMBERS:
            raise IntakeError("office_archive_too_many_members", "the office archive has too many members")
        total_size = 0
        names: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            if not name or "\\" in name or path.is_absolute() or ".." in path.parts:
                raise IntakeError("office_archive_path", "the office archive contains an unsafe path")
            if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
                raise IntakeError("office_archive_symlink", "the office archive contains a symlink")
            if info.file_size < 0 or info.file_size > MAX_OFFICE_UNCOMPRESSED_BYTES:
                raise IntakeError("office_member_too_large", "an office archive member is too large")
            total_size += info.file_size
            if total_size > MAX_OFFICE_UNCOMPRESSED_BYTES:
                raise IntakeError("office_archive_too_large", "the office archive is too large")
            if not info.is_dir():
                if name in names:
                    raise IntakeError("office_archive_duplicate", "the office archive contains duplicate members")
                names[name] = info
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            raise IntakeError("office_macros_not_allowed", "macro content is not accepted by the intake parser")

        members: dict[str, bytes] = {}
        for name, info in names.items():
            try:
                members[name] = archive.read(info)
            except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
                raise IntakeError("malformed_office", "the office archive could not be read") from exc
        return members
    finally:
        archive.close()


_DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _xml_root(members: dict[str, bytes], name: str) -> ElementTree.Element:
    content = members.get(name)
    if content is None:
        raise IntakeError("malformed_office", "the office document is missing a required part")
    upper_content = content.upper()
    if b"<!DOCTYPE" in upper_content or b"<!ENTITY" in upper_content:
        raise IntakeError("office_xml_entities", "XML entity declarations are not accepted by the intake parser")
    try:
        return ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise IntakeError("malformed_office", "the office XML part is malformed") from exc


def _docx_pages(content: bytes) -> list[str]:
    members = _safe_office_members(content)
    if "[Content_Types].xml" not in members or "word/document.xml" not in members:
        raise IntakeError("malformed_office", "the DOCX document is missing required parts")
    root = _xml_root(members, "word/document.xml")
    body = root.find(f"{{{_DOCX_NS}}}body")
    if body is None:
        raise IntakeError("malformed_office", "the DOCX document has no body")

    pages: list[list[str]] = [[]]
    for block in body:
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            parts: list[str] = []
            page_break = False
            for node in block.iter():
                node_tag = node.tag.rsplit("}", 1)[-1]
                if node_tag == "t":
                    parts.append(node.text or "")
                elif node_tag == "tab":
                    parts.append("\t")
                elif node_tag == "br":
                    if node.attrib.get(f"{{{_DOCX_NS}}}type") == "page":
                        page_break = True
                    else:
                        parts.append("\n")
                elif node_tag == "lastRenderedPageBreak":
                    page_break = True
            text = "".join(parts).strip()
            if text:
                pages[-1].append(text)
            if page_break:
                pages.append([])
        elif tag == "tbl":
            rows: list[str] = []
            for row in block.findall(f".//{{{_DOCX_NS}}}tr"):
                cells = []
                for cell in row.findall(f"{{{_DOCX_NS}}}tc"):
                    cells.append("".join(node.text or "" for node in cell.iter(f"{{{_DOCX_NS}}}t")).strip())
                rows.append("\t".join(cells))
            if rows:
                pages[-1].append("\n".join(rows))
    return ["\n".join(blocks) for blocks in pages] or [""]


def _column_number(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha()).upper()
    if not letters:
        return 1
    value = 0
    for char in letters:
        value = value * 26 + ord(char) - ord("A") + 1
    return value


def _xlsx_shared_strings(root: ElementTree.Element | None) -> list[str]:
    if root is None:
        return []
    return ["".join(node.text or "" for node in item.iter(f"{{{_SPREADSHEET_NS}}}t")) for item in root.findall(f"{{{_SPREADSHEET_NS}}}si")]


def _xlsx_cell_text(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    formula = cell.find(f"{{{_SPREADSHEET_NS}}}f")
    if formula is not None:
        return f"={formula.text or ''}"
    value = cell.find(f"{{{_SPREADSHEET_NS}}}v")
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{_SPREADSHEET_NS}}}t"))
    raw = "" if value is None else value.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError) as exc:
            raise IntakeError("malformed_office", "the XLSX shared-string reference is invalid") from exc
    if cell_type == "b":
        return "TRUE" if raw == "1" else "FALSE"
    return raw


def _xlsx_pages(content: bytes) -> list[tuple[str, str]]:
    members = _safe_office_members(content)
    if "[Content_Types].xml" not in members or "xl/workbook.xml" not in members:
        raise IntakeError("malformed_office", "the XLSX workbook is missing required parts")
    workbook = _xml_root(members, "xl/workbook.xml")
    shared_strings = _xlsx_shared_strings(
        _xml_root(members, "xl/sharedStrings.xml") if "xl/sharedStrings.xml" in members else None
    )
    relationships: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in members:
        rels = _xml_root(members, "xl/_rels/workbook.xml.rels")
        for rel in rels.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
            target = rel.attrib.get("Target", "")
            if target.startswith("/"):
                target = target[1:]
            else:
                target = str(PurePosixPath("xl") / target)
            normalized = str(PurePosixPath(target))
            if normalized.startswith("xl/") and ".." not in PurePosixPath(normalized).parts:
                relationships[rel.attrib.get("Id", "")] = normalized

    sheets = workbook.find(f"{{{_SPREADSHEET_NS}}}sheets")
    if sheets is None:
        raise IntakeError("malformed_office", "the XLSX workbook has no worksheets")
    pages: list[tuple[str, str]] = []
    for index, sheet in enumerate(sheets.findall(f"{{{_SPREADSHEET_NS}}}sheet"), start=1):
        relationship_id = sheet.attrib.get(f"{{{_REL_NS}}}id", "")
        target = relationships.get(relationship_id, f"xl/worksheets/sheet{index}.xml")
        if target not in members:
            raise IntakeError("malformed_office", "the XLSX worksheet part is missing")
        root = _xml_root(members, target)
        rows: list[str] = []
        sheet_data = root.find(f"{{{_SPREADSHEET_NS}}}sheetData")
        if sheet_data is not None:
            for row in sheet_data.findall(f"{{{_SPREADSHEET_NS}}}row"):
                cells: dict[int, str] = {}
                for cell in row.findall(f"{{{_SPREADSHEET_NS}}}c"):
                    column = _column_number(cell.attrib.get("r", "A1"))
                    cells[column] = _xlsx_cell_text(cell, shared_strings)
                if cells:
                    rows.append("\t".join(cells.get(column, "") for column in range(1, max(cells) + 1)))
        sheet_name = sheet.attrib.get("name", f"Sheet{index}")
        pages.append((f"sheet:{sheet_name}", "\n".join(rows)))
    return pages or [("sheet:Sheet1", "")]


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
    version = "builtin-intake-2"

    def parse(self, request: IntakeRequest, source_hash: str) -> tuple[str, tuple[PageRecord, ...]]:
        media_type = _media_type(request.file_name, request.content)
        if media_type == "application/pdf":
            extraction_method = "pdf_text"
            page_data = _pdf_pages(request.content)
        elif media_type.startswith("image/"):
            _validate_image(request.content)
            extraction_method = "image_metadata_only"
            page_data = [("page:1", "")]
        elif media_type == _DOCX_MEDIA_TYPE:
            extraction_method = "docx_xml_text"
            page_data = [(f"page:{page_number}", text) for page_number, text in enumerate(_docx_pages(request.content), start=1)]
        elif media_type == _XLSX_MEDIA_TYPE:
            extraction_method = "xlsx_xml_table"
            page_data = _xlsx_pages(request.content)
        elif media_type == "text/csv":
            extraction_method = "csv_table"
            page_data = [("page:1", _csv_table(request.content))]
        else:
            extraction_method = "utf8_text_decode"
            page_data = [("page:1", request.content.decode("utf-8"))]

        semantic_source_hash = _semantic_revision_hash(media_type, page_data, source_hash)
        pages = tuple(
            PageRecord(
                page_id=stable_id("page", request.source_ref, semantic_source_hash, page_number),
                page_number=page_number,
                source_region=source_region,
                content_hash=hashlib.sha256(f"{semantic_source_hash}:page:{page_number}".encode()).hexdigest(),
                media_type=media_type,
                text=text,
                extraction_method=extraction_method,
                confidence=1.0
                if extraction_method in {"utf8_text_decode", "csv_table", "docx_xml_text", "xlsx_xml_table"}
                or (extraction_method == "pdf_text" and bool(text))
                else 0.0,
                clearance=request.clearance,
                taint=Taint.untrusted,
                evidence_ref=stable_id("evidence", request.source_ref, semantic_source_hash, page_number),
                rendered_page_ref=None,
                render_status="deferred",
            )
            for page_number, (source_region, text) in enumerate(page_data, start=1)
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
        revision_hash = _semantic_revision_hash(
            media_type,
            tuple((page.source_region, page.text) for page in pages),
            source_hash,
        )
        manifest = IntakeManifest(
            intake_id=intake_id,
            task_id=request.task_id,
            source_ref=request.source_ref,
            revision_id=stable_id("revision", request.source_ref, revision_hash, self._parser.version, renderer_version),
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
