from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
import yaml

from airbench.delivery import DeliverableEngine, DeliverableRequest, DeterministicValue, LocalArtifactStore
from contracts import Clearance, EventLedger, Taint, build_event

SECTIONS = ["subject", "findings", "source_register", "deterministic_calculations", "review_status"]

TEMPLATES = {
    "templates": [
        {"id": "fmt_docx", "version": "1.0", "format": "docx", "required_sections": SECTIONS,
         "value_bindings": [{"name": "page_count", "required": True}],
         "values_section": "deterministic_calculations", "structural_check": "required", "visual_check": "not_required"},
        {"id": "fmt_xlsx", "version": "1.0", "format": "xlsx", "required_sections": SECTIONS,
         "value_bindings": [{"name": "page_count", "required": True}],
         "values_section": "deterministic_calculations", "structural_check": "required", "visual_check": "not_required"},
        {"id": "fmt_pptx", "version": "1.0", "format": "pptx", "required_sections": SECTIONS,
         "value_bindings": [{"name": "page_count", "required": True}],
         "values_section": "deterministic_calculations", "structural_check": "required", "visual_check": "not_required"},
    ]
}


def _seed(ledger: EventLedger, task_id: str) -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
        clearance=Clearance.internal, idempotency=f"created-{task_id}", sequence=0,
    ))


def _value() -> DeterministicValue:
    return DeterministicValue(
        name="page_count", value_text="3", unit="pages", value_origin="verified_fact",
        source_refs=("intake:report.pdf",), evidence_refs=("evidence:1",), verification_refs=("verification:1",),
        confidence=0.9, clearance=Clearance.internal, taint=Taint.untrusted, derivation=None, verified=True,
    )


def _request(template_id: str) -> DeliverableRequest:
    return DeliverableRequest(
        task_id="task.fmt", template_id=template_id, title="Inspection review",
        prose_sections={
            "subject": "Review of the inspection report",
            "findings": "The pump showed seal leakage.",
            "source_register": "Source: intake:report.pdf",
            "deterministic_calculations": "The report contains {{page_count}} pages.",
            "review_status": "Verified draft for operator review.",
        },
        values=(_value(),), source_refs=("intake:report.pdf",), evidence_refs=("evidence:1",),
        verification_refs=("verification:1",), clearance=Clearance.internal, taint=Taint.untrusted,
        confidence=0.9, idempotency_key=f"fmt-{template_id}",
    )


@pytest.fixture
def engine(tmp_path) -> DeliverableEngine:
    template_path = tmp_path / "templates.yaml"
    template_path.write_text(yaml.safe_dump(TEMPLATES), encoding="utf-8")
    ledger = EventLedger()
    _seed(ledger, "task.fmt")
    return DeliverableEngine(
        template_path=template_path,
        artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        ledger=ledger,
    )


@pytest.mark.parametrize("template_id,fmt,required_parts", [
    ("fmt_docx", "docx", {"word/document.xml"}),
    ("fmt_xlsx", "xlsx", {"xl/workbook.xml", "xl/worksheets/sheet1.xml"}),
    ("fmt_pptx", "pptx", {"ppt/presentation.xml", "ppt/slides/slide1.xml"}),
])
def test_render_each_format_end_to_end(engine, template_id, fmt, required_parts):
    artifact = engine.render(_request(template_id))
    assert artifact.file_format == fmt
    assert artifact.structural_check == "passed"
    assert artifact.status == "verified_draft"
    assert artifact.content_hash and artifact.byte_size > 0
    content = engine.artifact_store.read(artifact.artifact_id, fmt)
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        assert required_parts.issubset(set(package.namelist()))
        assert not any(name.endswith("vbaProject.bin") for name in package.namelist())


def test_xlsx_carries_the_deterministic_value(engine):
    artifact = engine.render(_request("fmt_xlsx"))
    text = _archive_text(engine, artifact, "xlsx", "xl/")
    assert "page_count" in text and "3" in text


def test_unsupported_format_is_rejected(tmp_path):
    template_path = tmp_path / "templates.yaml"
    template_path.write_text(
        yaml.safe_dump({"templates": [{"id": "bad", "version": "1.0", "format": "pdf", "required_sections": SECTIONS}]}),
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        DeliverableEngine(
            template_path=template_path,
            artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
            ledger=EventLedger(),
        )


def _archive_text(engine, artifact, fmt, prefix) -> str:
    from xml.etree import ElementTree

    content = engine.artifact_store.read(artifact.artifact_id, fmt)
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        return "".join(
            "".join(ElementTree.fromstring(package.read(name)).itertext())
            for name in package.namelist()
            if name.endswith(".xml") and name.startswith(prefix)
        )
