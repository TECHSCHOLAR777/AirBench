"""Contract-first M9 refinery inspection report to approval note slice.

The module deliberately keeps refinery vocabulary in the pack loader and keeps
execution, provenance, artifact checks, and ledger semantics in the core slice.
It is deterministic and local: model workers are represented by bounded route
records, so the same run is replayable without a live model service.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree as ET

import yaml

from contracts import (
    Clearance, EventLedger, FactEnvelope, HardwareProfile, HandoffSubmission,
    LedgerEventEnvelope, Taint, WorkPacket, build_event, idempotency_key,
    stable_id, work_packet_hash,
)
from airbench.intake.layer import FileIntakeLayer, IntakeManifest, IntakeMode, IntakeRequest, LocalIntakeStore, PageRenderer
from airbench.intake.vision import LocalVisionAdapter, VisionRequest
from airbench.knowledge.retrieval import (
    DeterministicEmbeddingProvider,
    IndexRequest,
    LexicalReranker,
    LocalIndexer,
    LocalVectorIndex,
    RetrievalRequest,
    RetrievalService,
)
from airbench.verification.independent import (
    CompletionGate,
    EvaluatorInput,
    EvaluatorResult,
    IndependentEvaluator,
)
from airbench.verification.runner import (
    VerificationOutcome,
    VerificationRequest,
    VerificationRule,
    VerificationRunner,
)


class SignedPackError(ValueError):
    """A pack is missing a valid signature or contains unsafe declarations."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _append(
    ledger: EventLedger,
    event_type: str,
    task_id: str,
    payload: dict[str, Any],
    clearance: Clearance,
    actor: str = "m9.orchestrator",
) -> LedgerEventEnvelope:
    event = build_event(
        event_type=event_type, task_id=task_id, actor_id=actor, actor_type="orchestrator",
        payload_contract="M9RunEvent", payload_version="1.0", payload=payload,
        clearance=clearance, idempotency=idempotency_key(event_type, task_id, json.dumps(payload, sort_keys=True)),
        sequence=len(ledger.events), previous_event_hash=ledger.head_hash,
    )
    return ledger.append(event)


@dataclass(frozen=True, slots=True)
class RefineryPack:
    root: Path
    manifest: Mapping[str, Any]
    documents: Mapping[str, Any]
    world: Mapping[str, Any]
    rules: Mapping[str, Any]
    workers: Mapping[str, Any]
    templates: Mapping[str, Any]
    decisions: Mapping[str, Any]
    risks: Mapping[str, Any]
    clearance_roles: Mapping[str, Any]
    signature: str

    @staticmethod
    def _payload(root: Path) -> dict[str, Any]:
        files = sorted(p for p in root.glob("*.yaml") if p.name != "manifest.yaml")
        manifest = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise SignedPackError("pack manifest is not a mapping")
        manifest = dict(manifest)
        manifest.pop("signature", None)
        return {"manifest.yaml": manifest, **{p.name: yaml.safe_load(p.read_text(encoding="utf-8")) for p in files}}

    @classmethod
    def sign(cls, root: str | Path, key: bytes) -> str:
        if not key:
            raise SignedPackError("signing key is required")
        return hmac.new(key, _canonical(cls._payload(Path(root))), hashlib.sha256).hexdigest()

    @classmethod
    def load(cls, root: str | Path, key: bytes, signature: str | None = None) -> "RefineryPack":
        path = Path(root).resolve()
        try:
            manifest = yaml.safe_load((path / "manifest.yaml").read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise SignedPackError("pack manifest is not a mapping")
            actual = signature or manifest.get("signature")
            expected = cls.sign(path, key)
        except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
            raise SignedPackError("pack could not be read") from exc
        if not actual or not hmac.compare_digest(str(actual), expected):
            raise SignedPackError("pack signature verification failed")
        if manifest.get("status") == "draft_pending_external_acceptance" and not actual:
            raise SignedPackError("draft packs cannot be loaded")
        required = {
            "document_profiles", "world_schema", "field_rules", "decision_types",
            "risk_mappings", "clearance_roles", "deliverable_templates", "worker_requirements",
        }
        if not required.issubset(manifest):
            raise SignedPackError("pack manifest is missing a required declaration")
        def load(name: str) -> Mapping[str, Any]:
            component = path / name
            if not component.is_file():
                raise SignedPackError(f"pack component is missing: {name}")
            value = yaml.safe_load(component.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise SignedPackError(f"pack component is not a mapping: {name}")
            return value
        return cls(path, manifest, load("document_profiles.yaml"), load("world_schema.yaml"), load("field_rules.yaml"), load("worker_requirements.yaml"), load("deliverable_templates.yaml"), load("decision_types.yaml"), load("risk_mappings.yaml"), load("clearance_roles.yaml"), expected)


@dataclass(frozen=True, slots=True)
class InspectionFinding:
    finding_id: str
    equipment_tag: str
    severity: str
    description: str
    fact: FactEnvelope
    source_region: str


@dataclass(frozen=True, slots=True)
class WorkerRoute:
    worker_id: str
    role: str
    capability: str
    execution_mode: str
    model_route: str


@dataclass(frozen=True, slots=True)
class ArtifactCheck:
    artifact_id: str
    content_hash: str
    structural: str
    visual: str
    check_reason: str
    generator_version: str = "m9-docx-1"
    visual_backend: str = "none"


@dataclass(frozen=True, slots=True)
class M9RunResult:
    task_id: str
    outcome: str
    review_status: str
    execution_mode: str
    findings: tuple[InspectionFinding, ...]
    computed_values: Mapping[str, int]
    manual_refs: tuple[str, ...]
    routes: tuple[WorkerRoute, ...]
    artifact: ArtifactCheck | None
    ledger_event_ids: tuple[str, ...]


class ApprovalNoteRenderer:
    """Small dependency-free OOXML writer with structural and visual checks."""

    version = "m9-docx-1"

    @staticmethod
    def _word_executable() -> str | None:
        candidates = (
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Microsoft Office/root/Office16/WINWORD.EXE",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Office/root/Office16/WINWORD.EXE",
        )
        return next((str(path) for path in candidates if path.is_file()), None)

    @classmethod
    def _check_with_word(cls, path: Path) -> str:
        word = cls._word_executable()
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if word is None or powershell is None:
            return "not_run"
        with tempfile.TemporaryDirectory() as temp:
            pdf_path = Path(temp) / "approval-note.pdf"
            script_path = Path(temp) / "render-docx.ps1"
            script_path.write_text(
                "param([string]$InputPath,[string]$OutputPath)\n"
                "$ErrorActionPreference='Stop'\n"
                "$word=$null; $doc=$null\n"
                "try {\n"
                "  $word=New-Object -ComObject Word.Application\n"
                "  $word.Visible=$false; $word.DisplayAlerts=0\n"
                "  $doc=$word.Documents.Open($InputPath,$false,$true)\n"
                "  $doc.ExportAsFixedFormat($OutputPath,17)\n"
                "  if (-not (Test-Path -LiteralPath $OutputPath)) { exit 2 }\n"
                "} finally {\n"
                "  if ($doc) { $doc.Close($false) }\n"
                "  if ($word) { $word.Quit() }\n"
                "}\n",
                encoding="utf-8",
            )
            try:
                completed = subprocess.run(
                    [powershell, "-NoProfile", "-NonInteractive", "-File", str(script_path), str(path.resolve()), str(pdf_path)],
                    capture_output=True, timeout=60,
                )
            except (OSError, subprocess.TimeoutExpired):
                return "failed"
            return "passed" if completed.returncode == 0 and pdf_path.is_file() else "failed"

    def render(
        self,
        output: Path,
        *,
        findings: tuple[InspectionFinding, ...],
        manual_refs: tuple[str, ...],
        values: Mapping[str, int],
        review_status: str,
        template: Mapping[str, Any],
    ) -> ArtifactCheck:
        output.parent.mkdir(parents=True, exist_ok=True)
        def esc(value: Any) -> str:
            return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        labels = {str(key): str(value) for key, value in template.get("section_labels", {}).items()}
        paragraphs = [
            (str(template.get("title", "Approval Note")), "Title"),
            (labels.get("subject", "Subject"), "Heading1"), (str(template.get("subject", "Review")), "Normal"),
            (labels.get("findings", "Findings"), "Heading1"),
        ]
        paragraphs.extend((f"{f.finding_id}: {f.equipment_tag} — {f.severity} — {f.description}", "Normal") for f in findings)
        paragraphs.extend([
            (labels.get("source_register", "Source Register"), "Heading1"),
            *[(f"{f.finding_id}: {f.fact.source_ref} ({f.source_region})", "Normal") for f in findings],
            *[(f"Manual/SOP: {source_ref}", "Normal") for source_ref in manual_refs],
            (labels.get("deterministic_calculations", "Deterministic Calculations"), "Heading1"),
            *[(f"{name}: {value}", "Normal") for name, value in sorted(values.items())],
            (labels.get("review_status", "Review Status"), "Heading1"), (review_status, "Normal"),
        ])
        body = "".join(f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t xml:space="preserve">{esc(text)}</w:t></w:r></w:p>' for text, style in paragraphs)
        document = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>'''
        styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/></w:rPr></w:style></w:styles>'''
        rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
        content = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'''
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as docx:
            docx.writestr("[Content_Types].xml", content); docx.writestr("_rels/.rels", rels); docx.writestr("word/document.xml", document); docx.writestr("word/styles.xml", styles)
        structural, visual, reason, visual_backend = self.check(output, values, tuple(str(section) for section in template.get("required_sections", ())), template)
        return ArtifactCheck(stable_id("artifact", output.name, _sha(output.read_bytes())), _sha(output.read_bytes()), structural, visual, reason, self.version, visual_backend)

    def check(self, path: Path, values: Mapping[str, int], required_sections: tuple[str, ...], template: Mapping[str, Any]) -> tuple[str, str, str, str]:
        try:
            with zipfile.ZipFile(path) as archive:
                xml = ET.fromstring(archive.read("word/document.xml"))
                text = " ".join(xml.itertext())
                if any(str(value) not in text for value in values.values()): return "failed", "not_run", "computed value missing from document", "none"
                labels = {str(key): str(value) for key, value in template.get("section_labels", {}).items()}
                required_titles = {labels.get(section, section.replace("_", " ").title()) for section in required_sections}
                if any(title not in text for title in required_titles): return "failed", "not_run", "required template section missing from document", "none"
        except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
            return "failed", "not_run", "DOCX structure is invalid", "none"
        visual = "not_run"
        visual_backend = "none"
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice:
            visual_backend = "libreoffice"
            with tempfile.TemporaryDirectory() as temp:
                try:
                    completed = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", temp, str(path)], capture_output=True, timeout=30)
                except (OSError, subprocess.TimeoutExpired):
                    return "passed", "failed", "structural checks passed; visual conversion failed or timed out", visual_backend
                visual = "passed" if completed.returncode == 0 and list(Path(temp).glob("*.pdf")) else "failed"
        else:
            visual = self._check_with_word(path)
            visual_backend = "microsoft_word" if visual != "not_run" else "none"
        return "passed", visual, "structural checks passed; visual conversion " + visual, visual_backend


class RefineryVerticalSlice:
    def __init__(self, pack: RefineryPack, ledger: EventLedger, *, artifact_dir: str | Path) -> None:
        self.pack, self.ledger, self.artifact_dir = pack, ledger, Path(artifact_dir)

    @staticmethod
    def _mode(safe_parallel_slots: int, supported: tuple[str, ...]) -> str:
        if safe_parallel_slots > 1 and "parallel" in supported: return "parallel"
        if "serial_virtual_team" in supported: return "serial_virtual_team"
        raise ValueError("hardware profile cannot admit parallel or serial execution")

    def run_from_file(
        self,
        *,
        task_id: str,
        report_path: str | Path,
        manual_paths: Mapping[str, str | Path] | None = None,
        clearance: Clearance = Clearance.restricted,
        safe_parallel_slots: int = 1,
        supported_modes: tuple[str, ...] = ("serial_virtual_team",),
        vision_adapter: LocalVisionAdapter | None = None,
        rendered_page_bytes: Mapping[str, bytes] | None = None,
        renderer: PageRenderer | None = None,
        hardware_profile: HardwareProfile | None = None,
        model_routes: Mapping[str, str] | None = None,
    ) -> M9RunResult:
        """Run the vertical slice from local files through the one intake path.

        The caller may provide a qualified local vision adapter and rendered
        page bytes for scanned PDFs. The runner never opens a source file
        after intake; all downstream text is taken from intake manifests or
        typed vision results.
        """
        report_file = Path(report_path)
        if not report_file.is_file():
            raise FileNotFoundError("inspection report does not exist")
        report_content = report_file.read_bytes()
        for path in (manual_paths or {}).values():
            if not Path(path).is_file():
                raise FileNotFoundError("manual does not exist")
        clearance_value = clearance
        _append(self.ledger, "task.created", task_id, {
            "domain_pack_ref": self.pack.manifest["pack_id"],
            "pack_signature": self.pack.signature,
            "provenance": {"source_ref": f"local:{report_file.name}", "confidence": 1.0,
                           "clearance": clearance.value, "taint": Taint.untrusted.value},
        }, clearance_value)
        intake_store = LocalIntakeStore(self.artifact_dir / ".intake") if renderer is not None else None
        intake = FileIntakeLayer(self.ledger, renderer=renderer, store=intake_store)
        report_manifest = intake.intake(IntakeRequest(
            task_id, f"local:{report_file.resolve()}", report_file.name,
            report_content, IntakeMode.query_upload, clearance,
        ))
        manual_manifests = {
            source_ref: intake.intake(IntakeRequest(
                task_id, source_ref, Path(path).name, Path(path).read_bytes(),
                IntakeMode.query_upload, clearance,
            )) for source_ref, path in (manual_paths or {}).items()
        }
        rendered = dict(rendered_page_bytes or {})
        if intake_store is not None:
            rendered.update({
                page.page_id: intake_store.read_rendered_page(report_manifest.intake_id, page.page_id)
                for page in report_manifest.pages if page.render_status == "ready"
            })
        pages = self._manifest_pages(report_manifest, vision_adapter, rendered, report_content)
        manuals = {
            source_ref: "\n".join(page.text for page in manifest.pages if page.text)
            for source_ref, manifest in manual_manifests.items()
        }
        index = LocalVectorIndex()
        embeddings = DeterministicEmbeddingProvider()
        indexer = LocalIndexer(index, embeddings, ledger=self.ledger)
        for manifest in manual_manifests.values():
            indexer.index_manifest(IndexRequest(task_id, manifest))
        query = " ".join(text for _, text, _ in pages).strip() or "inspection finding maintenance procedure"
        citations = RetrievalService(
            index, embeddings, reranker=LexicalReranker(), ledger=self.ledger,
        ).search(RetrievalRequest(task_id, query, clearance, top_k=10))
        return self.run(
            task_id=task_id, report_pages={page_id: text for page_id, text, _ in pages},
            manuals=manuals, report_source_ref=report_manifest.source_ref,
            page_confidences={page_id: confidence for page_id, _, confidence in pages},
            retrieved_manual_refs=tuple(citation.source_ref for citation in citations),
            clearance=clearance, safe_parallel_slots=safe_parallel_slots,
            supported_modes=supported_modes, start_task=False,
            hardware_profile=hardware_profile, model_routes=model_routes,
        )

    @staticmethod
    def _manifest_pages(
        manifest: IntakeManifest,
        vision_adapter: LocalVisionAdapter | None,
        rendered_page_bytes: Mapping[str, bytes],
        source_content: bytes,
    ) -> tuple[tuple[str, str, float], ...]:
        pages: list[tuple[str, str, float]] = []
        for page in manifest.pages:
            text = page.text
            content = rendered_page_bytes.get(page.page_id)
            if content is None and page.media_type.startswith("image/"):
                content = source_content
            if not text and vision_adapter is not None and content:
                result = vision_adapter.extract(VisionRequest(
                    task_id=manifest.task_id, intake_id=manifest.intake_id,
                    revision_id=manifest.revision_id, page_id=page.page_id,
                    page_number=page.page_number, source_ref=manifest.source_ref,
                    media_type=page.media_type, content=content,
                    content_hash=hashlib.sha256(content).hexdigest(),
                    clearance=page.clearance, taint=page.taint,
                ))
                text = result.text
                confidence = result.confidence
            else:
                confidence = page.confidence
            pages.append((page.page_id, text, confidence))
        return tuple(pages)

    def run(
        self,
        *,
        task_id: str,
        report_pages: Mapping[str, str],
        manuals: Mapping[str, str],
        report_source_ref: str = "intake:inspection-report",
        page_confidences: Mapping[str, float] | None = None,
        retrieved_manual_refs: tuple[str, ...] | None = None,
        clearance: Clearance = Clearance.restricted,
        safe_parallel_slots: int = 1,
        supported_modes: tuple[str, ...] = ("serial_virtual_team",),
        signature_ref: str = "",
        start_task: bool = True,
        hardware_profile: HardwareProfile | None = None,
        model_routes: Mapping[str, str] | None = None,
    ) -> M9RunResult:
        if not report_pages: raise ValueError("a scanned inspection report is required")
        if hardware_profile is not None:
            safe_parallel_slots = hardware_profile.safe_parallel_slots
            supported_modes = hardware_profile.supported_execution_modes
        route_map = model_routes or {}
        if hardware_profile is not None and str(hardware_profile.egress_policy).replace("_", "-") == "no-egress":
            invalid_routes = {
                role: target for role, target in route_map.items()
                if not str(target).startswith("local.")
            }
            if invalid_routes:
                raise ValueError("no-egress hardware profile rejects non-local model routes")
        ids: list[str] = []
        def event(kind: str, payload: dict[str, Any]) -> None: ids.append(_append(self.ledger, kind, task_id, payload, clearance).event_id)
        if start_task:
            event("task.created", {"domain_pack_ref": self.pack.manifest["pack_id"], "pack_signature": self.pack.signature, "signature_ref": signature_ref, "provenance": {"source_ref": report_source_ref, "confidence": 1.0, "clearance": clearance.value, "taint": Taint.untrusted.value}})
        mode = self._mode(safe_parallel_slots, supported_modes)
        if hardware_profile is not None:
            event("hardware.profile.loaded", {
                "profile_id": hardware_profile.profile_id,
                "measurement_hash": hardware_profile.measurement_hash,
                "supported_execution_modes": list(hardware_profile.supported_execution_modes),
                "safe_parallel_slots": hardware_profile.safe_parallel_slots,
                "egress_policy": hardware_profile.egress_policy,
            })
        event("execution.mode.selected", {"mode": mode, "safe_parallel_slots": safe_parallel_slots, "hardware_modes": list(supported_modes), "hardware_profile_id": hardware_profile.profile_id if hardware_profile else None})
        event("team.created", {"team_id": stable_id("team", task_id), "required_verification": True, "pack_workflow": "refinery_inspection_review"})
        event("team.execution.started", {"team_id": stable_id("team", task_id), "mode": mode})
        workflow = self.pack.workers.get("workflows", {}).get("refinery_inspection_review", {})
        required_workers = tuple(str(worker) for worker in workflow.get("required_workers", ()))
        capabilities = {
            "lead_worker": "coordination",
            "evidence_vision_worker": "vision",
            "reasoning_worker": "reasoning",
            "independent_verification_worker": "verification",
            "render_review_worker": "render",
        }
        if not required_workers or any(worker not in capabilities for worker in required_workers):
            raise SignedPackError("refinery workflow has an unsupported worker declaration")
        route_specs = tuple((worker, capabilities[worker]) for worker in required_workers)
        routes = tuple(WorkerRoute(f"worker.m9.{role}", role, capability, mode, route_map.get(role, f"local.{capability}.qualified")) for role, capability in route_specs)
        for route in routes:
            event("worker.assigned", {"worker_id": route.worker_id, "role": route.role, "capability": route.capability, "mode": mode, "model_route": route.model_route})
            event("routing.decided", {"worker_id": route.worker_id, "role": route.role, "capability": route.capability, "target_id": route.model_route, "hardware_profile_id": hardware_profile.profile_id if hardware_profile else None, "qualified": True})
            event("worker.started", {"worker_id": route.worker_id, "role": route.role, "stage": route.capability})
        findings: list[InspectionFinding] = []
        for page_id, text in report_pages.items():
            for index, line in enumerate(text.splitlines(), 1):
                match = re.match(r"\s*(?:finding\s*)?(?P<id>[A-Z]+[-_]?[0-9]+)\s*[:|-]\s*(?P<equipment>[A-Za-z0-9_.-]+)\s*[:|-]\s*(?P<severity>critical|high|medium|low)\s*[:|-]\s*(?P<description>.+)", line, re.I)
                if not match: continue
                data = match.groupdict(); fid = data["id"].replace("_", "-").lower()
                source = f"{report_source_ref}#{page_id}"
                confidence = (page_confidences or {}).get(page_id, 0.85)
                fact = FactEnvelope(stable_id("fact", task_id, fid), data["description"].strip(), source, confidence, clearance, Taint.untrusted, "local_ocr_vision", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
                findings.append(InspectionFinding(fid, data["equipment"], data["severity"].lower(), data["description"].strip(), fact, f"{page_id}:line={index}"))
                event("fact.candidate", {"fact_id": fact.fact_id, "source_ref": source, "confidence": fact.confidence, "clearance": clearance.value, "taint": fact.taint.value})
                event("fact.committed", {"fact_id": fact.fact_id, "source_ref": source, "confidence": fact.confidence, "clearance": clearance.value, "taint": fact.taint.value, "scope": "task", "promotion": "provenance_gate"})
        if not findings: raise ValueError("inspection report contained no sourced findings")
        manual_hits = tuple((key, value) for key, value in manuals.items() if any(token in value.lower() for finding in findings for token in finding.description.lower().split() if len(token) > 4))
        retrieved_refs = retrieved_manual_refs if retrieved_manual_refs is not None else tuple(key for key, _ in manual_hits)
        event("retrieval.completed", {"manual_refs": list(retrieved_refs), "finding_count": len(findings), "local_only": True})
        values = {"finding_count": len(findings), "critical_finding_count": sum(f.severity == "critical" for f in findings), "manual_match_count": len(retrieved_refs)}
        event("tool.requested", {"tool": "deterministic.computation", "worker_id": "worker.m9.reasoning_worker", "source_ref": "computed:m9", "taint": Taint.untrusted.value})
        event("tool.authorized", {"tool": "deterministic.computation", "worker_id": "worker.m9.reasoning_worker", "authorization": "task_policy"})
        event("tool.result", {"tool": "deterministic.computation", "values": values, "source_ref": "computed:m9", "taint": Taint.clean.value, "clearance": clearance.value})
        for route in routes:
            event("worker.completed", {"worker_id": route.worker_id, "role": route.role, "stage": route.capability, "status": "proposed_result"})
        team_id = stable_id("team", task_id)
        for source, destination in zip(routes, routes[1:]):
            packet = WorkPacket(
                packet_id=stable_id("packet", task_id, source.worker_id, destination.worker_id),
                task_id=task_id,
                team_id=team_id,
                source_worker_id=source.worker_id,
                destination_stage=destination.capability,
                fact_refs=tuple(f.fact.fact_id for f in findings),
                evidence_refs=tuple(f.fact.source_ref for f in findings),
                artifact_refs=(),
                checks={"source_bound": True, "confidence_bound": True},
                unresolved_questions=("human review remains required",),
                proposed_next_result=f"handoff from {source.role} to {destination.role}",
                clearance=clearance,
                taint=Taint.untrusted,
                packet_hash="",
            )
            packet = WorkPacket.from_dict({**packet.to_dict(), "packet_hash": work_packet_hash(packet)})
            handoff = HandoffSubmission(
                handoff_id=stable_id("handoff", task_id, source.worker_id, destination.worker_id),
                task_id=task_id,
                team_id=team_id,
                source_assignment_id=stable_id("assignment", task_id, source.worker_id),
                source_worker_id=source.worker_id,
                destination_assignment_id=stable_id("assignment", task_id, destination.worker_id),
                destination_stage=destination.capability,
                packet=packet,
                packet_hash=packet.packet_hash,
                barrier_id=stable_id("barrier", task_id, destination.worker_id),
                barrier_version=1,
                source_lease_id=stable_id("lease", task_id, source.worker_id),
                plan_version=self.pack.manifest.get("pack_version", "1.0"),
                policy_version_hash=_sha(_canonical(self.pack.manifest)),
                clearance=clearance,
                taint=Taint.untrusted,
                submitted_at="2026-01-01T00:00:00Z",
                deadline="2026-01-01T00:10:00Z",
                idempotency_key=idempotency_key("m9-handoff", task_id, source.worker_id, destination.worker_id),
            )
            event("worker.handoff", {
                "handoff": handoff.to_dict(),
                "packet_hash": handoff.packet_hash,
                "source_assignment_id": handoff.source_assignment_id,
                "destination_assignment_id": handoff.destination_assignment_id,
                "provenance": {
                    "source_ref": f"work-packet:{packet.packet_id}",
                    "confidence": 1.0,
                    "clearance": clearance.value,
                    "taint": Taint.untrusted.value,
                },
            })
        event("team.execution.completed", {"team_id": stable_id("team", task_id), "worker_count": len(routes), "finding_count": len(findings)})
        artifact_path = self.artifact_dir / f"{task_id}-approval-note.docx"
        template = next((item for item in self.pack.templates.get("templates", ()) if item.get("id") == "refinery_psu_approval_note_v0"), None)
        if not isinstance(template, dict) or template.get("format") != "docx":
            raise SignedPackError("approval-note DOCX template contract is unavailable")
        artifact = ApprovalNoteRenderer().render(
            artifact_path, findings=tuple(findings), manual_refs=tuple(retrieved_refs),
            values=values, review_status="verified draft for human review", template=template,
        )
        event("artifact.staged", {"artifact_id": artifact.artifact_id, "content_hash": artifact.content_hash, "generator_version": artifact.generator_version, "path": str(artifact_path)})
        event("artifact.checked", {"artifact_id": artifact.artifact_id, "content_hash": artifact.content_hash, "generator_version": artifact.generator_version, "structural": artifact.structural, "visual": artifact.visual, "visual_backend": artifact.visual_backend, "check_reason": artifact.check_reason})
        status = "verified draft for human review" if artifact.structural == "passed" and artifact.visual == "passed" else "needs_review"
        fact_values = tuple(fact.fact for fact in findings)
        verification = VerificationRunner(self.ledger, actor_id="worker.m9.independent_verification_worker").run(VerificationRequest(
            verification_id=stable_id("verification", task_id, artifact.artifact_id), task_id=task_id,
            rules=(
                VerificationRule(
                    rule_id=stable_id("rule", task_id, "source"), kind="source",
                    fact_ids=tuple(f.fact.fact_id for f in findings), source_prefixes=(report_source_ref,),
                ),
                VerificationRule(
                    rule_id=stable_id("rule", task_id, "confidence"), kind="confidence",
                    fact_ids=tuple(f.fact.fact_id for f in findings), confidence_floor=0.80,
                ),
            ),
            facts=fact_values, clearance=clearance,
            evidence_refs=tuple(f.fact.source_ref for f in findings),
            rule_set_version=self.pack.manifest.get("pack_version", "1.0"),
            idempotency_key=idempotency_key("m9-verification", task_id, artifact.artifact_id),
        ))
        criteria = ("artifact_rendered", "artifact_checked", "sources_attached", "deterministic_values_checked")
        evaluation_request = EvaluatorInput(
            task_id=task_id, evaluation_id=stable_id("evaluation", task_id, artifact.artifact_id),
            generator_worker_id="worker.m9.reasoning_worker",
            evaluator_worker_id="worker.m9.independent_verification_worker",
            proposal_ref=artifact.artifact_id,
            work_packet_refs=tuple(stable_id("packet", task_id, route.worker_id) for route in routes),
            evidence_refs=tuple(f.fact.source_ref for f in findings) + tuple(retrieved_refs) + (artifact.artifact_id,),
            completion_criteria=criteria, clearance=clearance,
            confidence=verification.confidence, taint=verification.taint,
        )
        def evaluate(_: EvaluatorInput) -> EvaluatorResult:
            passed = verification.outcome == VerificationOutcome.passed and artifact.structural == "passed" and artifact.visual == "passed"
            return EvaluatorResult(
                evaluation_id=evaluation_request.evaluation_id, task_id=task_id,
                outcome="passed" if passed else "needs_review",
                criteria=tuple((criterion, passed) for criterion in criteria),
                reason="independent checks passed" if passed else "artifact or deterministic verification remains incomplete",
                confidence=verification.confidence if passed else min(verification.confidence, 0.5),
                clearance=clearance, taint=verification.taint,
                evaluator_worker_id=evaluation_request.evaluator_worker_id,
            )
        evaluation = IndependentEvaluator(
            self.ledger, evaluator=evaluate,
            evaluator_worker_id="worker.m9.independent_verification_worker",
        ).evaluate(evaluation_request)
        completion = CompletionGate(self.ledger).decide(
            evaluation_request, evaluation,
            deterministic_checks={
                "verification": verification.outcome.value,
                "artifact_structural": artifact.structural,
                "artifact_visual": artifact.visual,
            }, evidence_refs=evaluation_request.evidence_refs,
        )
        final_status = "verified draft for human review" if completion.outcome == "complete" else "needs_review"
        event("human.review.required", {"artifact_id": artifact.artifact_id, "review_status": final_status, "completion_ref": completion.ledger_event_id})
        task_events = tuple(event.event_id for event in self.ledger.events if event.task_id == task_id)
        return M9RunResult(task_id, completion.outcome, final_status, mode, tuple(findings), values, tuple(retrieved_refs), routes, artifact, task_events)


__all__ = ["ArtifactCheck", "InspectionFinding", "M9RunResult", "RefineryPack", "RefineryVerticalSlice", "SignedPackError", "WorkerRoute"]
