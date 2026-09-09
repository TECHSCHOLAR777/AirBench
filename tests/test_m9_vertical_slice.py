from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from airbench.m9 import RefineryPack, RefineryVerticalSlice, SignedPackError
from contracts import Clearance, EventLedger


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
    assert all(f.fact.source_ref.startswith("intake:inspection-report") for f in run.findings)
    assert run.artifact and run.artifact.structural == "passed"
    assert run.artifact.content_hash
    assert Path(tmp_path / "artifacts" / "task.m9.demo-approval-note.docx").is_file()
    assert "artifact.checked" in [event.event_type for event in ledger.events]
    assert "verification.evaluator.completed" in [event.event_type for event in ledger.events]
    assert "completion.blocked" in [event.event_type for event in ledger.events]
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
    with pytest.raises(ValueError, match="no sourced findings"):
        RefineryVerticalSlice(signed_pack(tmp_path), EventLedger(), artifact_dir=tmp_path / "artifacts").run(
            task_id="task.m9.empty", report_pages={"page-1": "not a finding"}, manuals={}
        )
