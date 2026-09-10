from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from contracts import Clearance, EventLedger, Taint, build_event
from airbench.delivery import (
    DeliverableEngine,
    DeliverableError,
    DeliverableRequest,
    DeterministicValue,
    LocalArtifactStore,
)


TEMPLATE = """
templates:
  - id: generic_memo_v1
    version: "1.0"
    format: docx
    required_sections: [summary, deterministic_calculations]
    numeric_values: verified_fact_or_deterministic_calculation_only
    structural_check: required
    visual_check: false
"""


def _task_event(ledger: EventLedger, task_id: str = "task.deliverable-001") -> None:
    event = build_event(
        event_type="task.created",
        task_id=task_id,
        actor_id="fixture.operator",
        actor_type="human",
        payload_contract="TaskEnvelope",
        payload_version="1.0",
        payload={"task": {"task_id": task_id}},
        clearance=Clearance.internal,
        idempotency="fixture.task.created",
        sequence=0,
        previous_event_hash=None,
    )
    ledger.append(event)


def _request(*, task_id: str = "task.deliverable-001", value: DeterministicValue | None = None) -> DeliverableRequest:
    return DeliverableRequest(
        task_id=task_id,
        template_id="generic_memo_v1",
        title="Local review memo",
        prose_sections={
            "summary": "The verified total is {{total}}.",
            "deterministic_calculations": "Values in this section are inserted by the engine.",
        },
        values=(value,) if value is not None else (),
        source_refs=("intake:report-001",),
        evidence_refs=("evidence:report-001",),
        verification_refs=("verification:report-001",),
        clearance=Clearance.internal,
        taint=Taint.clean,
        confidence=0.96,
        idempotency_key="render.memo.001",
    )


def _value(*, verified: bool = True) -> DeterministicValue:
    return DeterministicValue(
        name="total",
        value_text="42",
        unit="items",
        value_origin="deterministic_calculation",
        source_refs=("intake:report-001",),
        evidence_refs=("evidence:report-001",),
        verification_refs=("verification:report-001",),
        confidence=0.96,
        clearance=Clearance.internal,
        taint=Taint.clean,
        derivation={"operation": "count", "input_refs": ["fact:items"]},
        verified=verified,
    )


def _engine(tmp_path: Path, ledger: EventLedger, *, visual_check_required: bool = False) -> DeliverableEngine:
    template_path = tmp_path / "templates.yaml"
    template_path.write_text(TEMPLATE.replace("visual_check: false", f"visual_check: {'required' if visual_check_required else 'false'}"), encoding="utf-8")
    return DeliverableEngine(
        template_path=template_path,
        artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        ledger=ledger,
    )


@pytest.fixture()
def ledger() -> EventLedger:
    value = EventLedger()
    _task_event(value)
    return value


def test_render_writes_a_real_docx_and_appends_provenance_events(tmp_path: Path, ledger: EventLedger):
    engine = _engine(tmp_path, ledger)

    artifact = engine.render(_request(value=_value()))

    assert artifact.path.suffix == ".docx"
    assert artifact.path.is_file()
    assert artifact.content_hash
    assert artifact.status == "verified_draft"
    assert artifact.structural_check == "passed"
    assert artifact.visual_check == "not_required"
    assert artifact.deterministic_value_refs == ("total",)
    assert artifact.source_refs == ("intake:report-001",)
    assert [event.event_type for event in ledger.events] == [
        "task.created",
        "artifact.staged",
        "artifact.checked",
    ]

    with zipfile.ZipFile(artifact.path) as package:
        assert "word/document.xml" in package.namelist()
        document_xml = package.read("word/document.xml")
    assert b"42" in document_xml
    assert b"{{total}}" not in document_xml


def test_render_accepts_orchestrator_uuid_task_identity(tmp_path: Path):
    ledger = EventLedger()
    task_id = "12345678-1234-5678-1234-567812345678"
    _task_event(ledger, task_id)

    artifact = _engine(tmp_path, ledger).render(_request(task_id=task_id, value=_value()))

    assert artifact.task_id == task_id
    assert artifact.path.is_file()


def test_same_idempotency_key_replays_without_duplicate_artifact_events(tmp_path: Path, ledger: EventLedger):
    engine = _engine(tmp_path, ledger)
    request = _request(value=_value())

    first = engine.render(request)
    second = engine.render(request)

    assert second.artifact_id == first.artifact_id
    assert second.content_hash == first.content_hash
    assert len(ledger.events) == 3


def test_missing_named_value_is_rejected_before_file_or_ledger_mutation(tmp_path: Path, ledger: EventLedger):
    engine = _engine(tmp_path, ledger)

    with pytest.raises(DeliverableError, match="unbound named value"):
        engine.render(_request())

    assert len(ledger.events) == 1
    assert not list((tmp_path / "artifacts").glob("*"))


def test_unverified_deterministic_value_is_rejected(tmp_path: Path, ledger: EventLedger):
    engine = _engine(tmp_path, ledger)

    with pytest.raises(DeliverableError, match="not verified"):
        engine.render(_request(value=_value(verified=False)))

    assert len(ledger.events) == 1


def test_contaminated_request_is_rejected_before_render_or_mutation(tmp_path: Path, ledger: EventLedger):
    engine = _engine(tmp_path, ledger)

    with pytest.raises(DeliverableError, match="contaminated"):
        engine.render(replace(_request(value=_value()), taint=Taint.contaminated))

    assert len(ledger.events) == 1
    assert not list((tmp_path / "artifacts").glob("*"))


def test_oversized_prose_is_rejected_before_render_or_mutation(tmp_path: Path, ledger: EventLedger):
    engine = _engine(tmp_path, ledger)
    oversized = replace(
        _request(value=_value()),
        prose_sections={
            "summary": "x" * 200_001,
            "deterministic_calculations": "Values in this section are inserted by the engine.",
        },
    )

    with pytest.raises(DeliverableError, match="section summary"):
        engine.render(oversized)

    assert len(ledger.events) == 1
    assert not list((tmp_path / "artifacts").glob("*"))


def test_required_visual_check_without_local_renderer_is_needs_review(tmp_path: Path, ledger: EventLedger):
    engine = _engine(tmp_path, ledger, visual_check_required=True)

    artifact = engine.render(_request(value=_value()))

    assert artifact.path.is_file()
    assert artifact.status == "needs_review"
    assert artifact.visual_check == "unavailable"
    checked = ledger.events[-1]
    assert checked.event_type == "artifact.checked"
    assert checked.payload["status"] == "needs_review"
    assert checked.payload["checks"]["visual"] == "unavailable"
