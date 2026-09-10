from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml
from PIL import Image
from io import BytesIO

from airbench.m9 import RefineryPack, RefineryVerticalSlice, SignedPackError
import airbench.m9.vertical_slice as vertical_slice
from airbench.intake.vision import LocalVisionAdapter, VisionResult, static_text_extractor
from airbench.intake.layer import RenderedPage
from contracts import Clearance, EventLedger, HardwareProfile, HandoffSubmission
from pypdf import PdfWriter


ROOT = Path(__file__).parents[1]
PACK = ROOT / "packs" / "refinery_psu_v0"


def signed_pack(tmp_path: Path) -> RefineryPack:
    target = tmp_path / "pack"
    shutil.copytree(PACK, target)
    key = b"test-only-m9-key"
    signature = RefineryPack.sign(target, key)
    manifest_path = target / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["signature"] = signature
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return RefineryPack.load(target, key)


def test_signed_pack_rejects_tampering(tmp_path: Path) -> None:
    key = b"test-only-m9-key"
    target = tmp_path / "pack"
    shutil.copytree(PACK, target)
    manifest = yaml.safe_load((target / "manifest.yaml").read_text(encoding="utf-8"))
    manifest["signature"] = RefineryPack.sign(target, key)
    (target / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    (target / "field_rules.yaml").write_text("rules: []\n", encoding="utf-8")
    with pytest.raises(SignedPackError):
        RefineryPack.load(target, key)


def test_signed_pack_rejects_manifest_tampering(tmp_path: Path) -> None:
    key = b"test-only-m9-key"
    target = tmp_path / "pack"
    shutil.copytree(PACK, target)
    manifest_path = target / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["signature"] = RefineryPack.sign(target, key)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    manifest["pack_version"] = "9.9"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    with pytest.raises(SignedPackError):
        RefineryPack.load(target, key)


def test_serial_run_extracts_provenance_computes_values_and_checks_docx(tmp_path: Path) -> None:
    ledger = EventLedger()
    run = RefineryVerticalSlice(signed_pack(tmp_path), ledger, artifact_dir=tmp_path / "artifacts").run(
        task_id="task.m9.demo",
        report_pages={"page-1": "F-01: P-101: high: seal leakage observed\nF-02: P-102: critical: vibration above limit"},
        manuals={"manual://pump-sop": "seal leakage requires isolation and inspection", "manual://vibration-sop": "vibration above limit requires review"},
        safe_parallel_slots=1,
    )
    assert run.execution_mode == "serial_virtual_team"
    assert run.computed_values == {"finding_count": 2, "critical_finding_count": 1, "manual_match_count": 2}
    assert set(run.manual_refs) == {"manual://pump-sop", "manual://vibration-sop"}
    assert {route.role for route in run.routes} == {
        "lead_worker", "evidence_vision_worker", "reasoning_worker",
        "independent_verification_worker", "render_review_worker",
    }
    assert all(f.fact.source_ref.startswith("intake:inspection-report") for f in run.findings)
    assert run.artifact and run.artifact.structural == "passed"
    assert run.artifact.content_hash
    assert Path(run.artifact.path).is_file()
    assert Path(tmp_path / "artifacts" / "task.m9.demo-approval-note.docx").is_file()
    with zipfile.ZipFile(tmp_path / "artifacts" / "task.m9.demo-approval-note.docx") as document:
        document_text = document.read("word/document.xml").decode("utf-8")
    assert "Manual/SOP: manual://pump-sop" in document_text
    assert "Manual/SOP: manual://vibration-sop" in document_text
    # The completion event is environment-dependent: hosts with a visual converter
    # emit completion.ready while hosts without one emit completion.blocked.
    # Both carry evidence_refs and both are valid; we accept either.
    completion = next(
        event for event in ledger.events
        if event.event_type in {"completion.blocked", "completion.ready"}
    )
    assert set(completion.payload["evidence_refs"]) >= {"manual://pump-sop", "manual://vibration-sop"}
    artifact_event = next(event for event in ledger.events if event.event_type == "artifact.checked")
    assert artifact_event.payload["visual_backend"] in {"microsoft_word", "libreoffice", "none"}
    assert artifact_event.payload["check_reason"]
    assert artifact_event.payload["path"] == run.artifact.path
    handoffs = [event for event in ledger.events if event.event_type == "worker.handoff"]
    assert len(handoffs) == len(run.routes) - 1
    assert all(HandoffSubmission.from_dict(event.payload["handoff"]).packet_hash for event in handoffs)
    assert "artifact.checked" in [event.event_type for event in ledger.events]
    assert "verification.evaluator.completed" in [event.event_type for event in ledger.events]
    assert any(
        event.event_type in {"completion.blocked", "completion.ready"}
        for event in ledger.events
    ), "expected a completion gate event (blocked or ready)"
    # The ledger task state is always needs_review because human.review.required
    # is unconditionally emitted after the completion gate.
    assert ledger.replay("task.m9.demo").state == "needs_review"


def test_parallel_mode_is_hardware_selected(tmp_path: Path) -> None:
    run = RefineryVerticalSlice(signed_pack(tmp_path), EventLedger(), artifact_dir=tmp_path / "artifacts").run(
        task_id="task.m9.parallel",
        report_pages={"page-1": "F-01: P-101: low: label damaged"},
        manuals={"manual://labels": "replace damaged label"},
        safe_parallel_slots=2,
        supported_modes=("parallel", "serial_virtual_team"),
    )
    assert run.execution_mode == "parallel"
    assert {route.execution_mode for route in run.routes} == {"parallel"}


def test_missing_findings_fails_closed(tmp_path: Path) -> None:
    ledger = EventLedger()
    with pytest.raises(ValueError, match="no sourced findings"):
        RefineryVerticalSlice(signed_pack(tmp_path), ledger, artifact_dir=tmp_path / "artifacts").run(
            task_id="task.m9.empty", report_pages={"page-1": "not a finding"}, manuals={}
        )
    assert sum(event.event_type == "worker.failed" for event in ledger.events) == 5
    assert any(event.event_type == "team.execution.failed" for event in ledger.events)
    assert next(event for event in ledger.events if event.event_type == "team.execution.failed").payload["failure_code"] == "no_sourced_findings"


def test_missing_input_and_resource_pressure_fail_closed_or_degrade_to_serial(tmp_path: Path) -> None:
    pack = signed_pack(tmp_path)
    slice_ = RefineryVerticalSlice(pack, EventLedger(), artifact_dir=tmp_path / "artifacts")
    with pytest.raises(FileNotFoundError, match="inspection report"):
        slice_.run_from_file(task_id="task.m9.missing", report_path=tmp_path / "missing.pdf")
    result = slice_.run(
        task_id="task.m9.resource", report_pages={"page-1": "F-01: P-101: low: label damaged"},
        manuals={}, safe_parallel_slots=0, supported_modes=("parallel", "serial_virtual_team"),
    )
    assert result.execution_mode == "serial_virtual_team"


def test_unsupported_hardware_modes_and_nonlocal_routes_fail_closed(tmp_path: Path) -> None:
    pack = signed_pack(tmp_path)
    slice_ = RefineryVerticalSlice(pack, EventLedger(), artifact_dir=tmp_path / "artifacts")
    with pytest.raises(ValueError, match="cannot admit"):
        slice_.run(
            task_id="task.m9.no-mode", report_pages={"page-1": "F-01: P-101: low: label damaged"},
            manuals={}, safe_parallel_slots=1, supported_modes=("parallel",),
        )
    profile = HardwareProfile.from_dict(json.loads((ROOT / "tests" / "fixtures" / "hardware_profile_96gb_valid.json").read_text()))
    with pytest.raises(ValueError, match="no-egress"):
        slice_.run(
            task_id="task.m9.egress", report_pages={"page-1": "F-01: P-101: low: label damaged"},
            manuals={}, hardware_profile=profile, model_routes={"reasoning": "remote.reasoning"},
        )


def test_low_confidence_finding_remains_review_required(tmp_path: Path) -> None:
    ledger = EventLedger()
    result = RefineryVerticalSlice(signed_pack(tmp_path), ledger, artifact_dir=tmp_path / "artifacts").run(
        task_id="task.m9.low-confidence", report_pages={"page-1": "F-01: P-101: high: seal leakage observed"},
        manuals={}, page_confidences={"page-1": 0.2},
    )
    assert result.outcome == "needs_review"
    verification = next(event for event in ledger.events if event.event_type == "verification.completed")
    assert verification.payload["status"] == "needs_review"


def test_visual_converter_timeout_is_a_blocking_artifact_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vertical_slice.shutil, "which", lambda _name: "soffice")

    def timed_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("soffice", 30)

    monkeypatch.setattr(vertical_slice.subprocess, "run", timed_out)
    result = RefineryVerticalSlice(signed_pack(tmp_path), EventLedger(), artifact_dir=tmp_path / "artifacts").run(
        task_id="task.m9.visual-timeout", report_pages={"page-1": "F-01: P-101: low: label damaged"},
        manuals={},
    )
    assert result.artifact and result.artifact.structural == "passed" and result.artifact.visual == "failed"
    assert result.outcome == "needs_review"


def test_renderer_backed_scanned_pdf_reaches_local_vision(tmp_path: Path) -> None:
    report = tmp_path / "scanned.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with report.open("wb") as handle:
        writer.write(handle)
    manual = tmp_path / "sop.txt"
    manual.write_text("seal leakage requires isolation", encoding="utf-8")
    ledger = EventLedger()

    class Renderer:
        name = "fixture.pdf-renderer"
        version = "1.0"

        def render(self, _request, page):
            return RenderedPage(page.page_number, b"rendered-scan-bytes", "image/png")

    def extract(request):
        return VisionResult(
            extraction_id=f"extraction-{request.page_id}", task_id=request.task_id,
            intake_id=request.intake_id, revision_id=request.revision_id, page_id=request.page_id,
            source_ref=request.source_ref, text="F-01: P-101: high: seal leakage observed",
            confidence=0.9, extraction_method="fixture.pdf-vision", adapter_id="fixture.vision",
            adapter_version="1.0", model_target_id="target.fixture",
            qualification_reference="qualification.fixture", clearance=request.clearance,
            taint=request.taint, content_hash=request.content_hash,
        )

    vision = LocalVisionAdapter(
        adapter_id="fixture.vision", adapter_version="1.0", model_target_id="target.fixture",
        qualification_reference="qualification.fixture", extractor=extract, ledger=ledger,
    )
    result = RefineryVerticalSlice(signed_pack(tmp_path), ledger, artifact_dir=tmp_path / "artifacts").run_from_file(
        task_id="task.m9.scanned-pdf", report_path=report, manual_paths={"local:sop": manual},
        renderer=Renderer(), vision_adapter=vision,
    )
    assert result.findings[0].fact.confidence == 0.9
    assert any(
        event.event_type == "vision.requested"
        and event.payload.get("content_hash") == hashlib.sha256(b"rendered-scan-bytes").hexdigest()
        for event in ledger.events
    )


def test_run_from_local_image_uses_file_intake_and_typed_vision(tmp_path: Path) -> None:
    pack = signed_pack(tmp_path)
    report = tmp_path / "inspection.png"
    image = Image.new("RGB", (8, 8), "white")
    image.save(report, format="PNG")
    manual = tmp_path / "sop.txt"
    manual.write_text("seal leakage requires isolation", encoding="utf-8")
    ledger = EventLedger()
    vision = LocalVisionAdapter(
        adapter_id="airbench.vision.fixture", adapter_version="1.0",
        model_target_id="target.fixture.vision", qualification_reference="qualification.fixture.vision",
        extractor=static_text_extractor(
            {}, adapter_id="airbench.vision.fixture", adapter_version="1.0",
            model_target_id="target.fixture.vision", qualification_reference="qualification.fixture.vision",
        ),
        ledger=ledger,
    )
    # The fixture extractor is keyed after intake creates the stable page ID.
    def extract(request):
        return VisionResult(
            extraction_id=f"extraction-{request.page_id}", task_id=request.task_id,
            intake_id=request.intake_id, revision_id=request.revision_id, page_id=request.page_id,
            source_ref=request.source_ref, text="F-01: P-101: high: seal leakage observed",
            confidence=0.91, extraction_method="fixture", adapter_id="airbench.vision.fixture",
            adapter_version="1.0", model_target_id="target.fixture.vision",
            qualification_reference="qualification.fixture.vision", clearance=request.clearance,
            taint=request.taint, content_hash=request.content_hash,
        )
    vision._extractor = extract
    result = RefineryVerticalSlice(pack, ledger, artifact_dir=tmp_path / "artifacts").run_from_file(
        task_id="task.m9.file", report_path=report, manual_paths={"local:sop": manual},
        vision_adapter=vision,
    )
    assert result.findings[0].fact.source_ref.startswith("local:")
    assert result.findings[0].fact.confidence == 0.91
    event_types = [event.event_type for event in ledger.events]
    assert "evidence.created" in event_types
    assert "vision.requested" in event_types and "vision.completed" in event_types
    assert "index.completed" in event_types and "retrieval.completed" in event_types
    assert "verification.completed" in event_types and "verification.evaluator.completed" in event_types
    assert "routing.decided" in event_types
    assert "fact.committed" in event_types and "tool.authorized" in event_types


def test_file_intake_failure_appends_task_failed_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a FileIntakeLayer.intake IntakeError must append a task.failed
    event before re-raising so the ledger has a full failure trace."""
    from airbench.intake.layer import IntakeError, FileIntakeLayer

    # setattr replaces the unbound method, so the replacement receives self too.
    def raise_intake_error(_self, _request):
        raise IntakeError("test_invalid_content", "synthetic intake failure for test")

    monkeypatch.setattr(FileIntakeLayer, "intake", raise_intake_error)

    pack = signed_pack(tmp_path)
    report = tmp_path / "report.txt"
    report.write_bytes(b"dummy")
    ledger = EventLedger()
    with pytest.raises(IntakeError, match="synthetic intake failure"):
        RefineryVerticalSlice(pack, ledger, artifact_dir=tmp_path / "artifacts").run_from_file(
            task_id="task.m9.intake-fail", report_path=report
        )

    failed_events = [e for e in ledger.events if e.event_type == "task.failed"]
    assert len(failed_events) == 1, "expected exactly one task.failed event"
    payload = failed_events[0].payload
    assert payload["failure_code"] == "test_invalid_content"
    assert payload["stage"] == "file_intake"
    assert payload["retryable"] is False
    assert "synthetic intake failure" in payload["failure_message"]
