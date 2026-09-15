from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from airbench.intake.pid.adapter import PidAdapterError, PidIntakeAdapter
from contracts import Clearance, Taint

PAGE = b"rendered-pid-page-bytes"
HASH = sha256(PAGE).hexdigest()

TOPOLOGY = {
    "symbols": [
        {"id": "gate_valve1", "label": "gate_valve", "tag": "V-101", "bbox": [1, 2, 3, 4], "confidence": 0.9},
    ],
    "connectors": [],
    "crossings": [],
    "edges": [{"id": "line_1", "source": "gate_valve1", "target": "connector1", "edge_label": "solid"}],
    "texts": [{"text": "V-101", "bbox": [1, 2, 3, 4]}],
}


class _StubAdapter(PidIntakeAdapter):
    def availability(self):
        return True, ""

    def _run_pipeline(self, source, output_dir):
        return TOPOLOGY


def _process(adapter: PidIntakeAdapter, tmp_path: Path, **overrides):
    args = dict(
        page_bytes=PAGE, media_type="image/png", task_id="task.pid", intake_id="intake.pid",
        revision_id="revision.pid", source_ref="upload:pid.png", content_hash=HASH,
        clearance=Clearance.internal, taint=Taint.untrusted, workspace=tmp_path,
    )
    args.update(overrides)
    return adapter.process(**args)


def test_adapter_maps_topology_to_a_typed_record(tmp_path) -> None:
    record = _process(_StubAdapter(), tmp_path)
    assert record.source_ref == "upload:pid.png"
    assert record.taint == Taint.untrusted
    assert record.clearance == Clearance.internal
    assert [component.label for component in record.components] == ["gate_valve"]
    assert record.components[0].tag == "V-101"
    assert record.relations == ()
    assert record.texts[0]["text"] == "V-101"
    payload = record.to_dict()
    assert payload["summary"] == {"components": 1, "relations": 0, "texts": 1}


def test_adapter_resolves_connector_paths_to_symbol_relations(tmp_path) -> None:
    topology = {
        "symbols": [
            {"id": "pump1", "label": "pump", "bbox": [1, 2, 3, 4], "confidence": 0.9},
            {"id": "valve1", "label": "valve", "bbox": [5, 6, 7, 8], "confidence": 0.9},
        ],
        "connectors": [
            {"id": "connector1", "parent_sym": "pump1"},
            {"id": "connector2", "parent_sym": "valve1"},
        ],
        "crossings": [{"id": "crossing1"}],
        "edges": [
            {"id": "line_1", "source": "connector1", "target": "crossing1", "edge_label": "solid"},
            {"id": "line_2", "source": "crossing1", "target": "connector2", "edge_label": "solid"},
        ],
        "texts": [],
    }

    class _PathAdapter(PidIntakeAdapter):
        def availability(self):
            return True, ""

        def _run_pipeline(self, source, output_dir):
            return topology

    record = _process(_PathAdapter(), tmp_path)
    assert [(item.source, item.target) for item in record.relations] == [("pump1", "valve1")]


def test_adapter_rejects_clean_taint_hash_and_media(tmp_path) -> None:
    with pytest.raises(PidAdapterError) as clean:
        _process(_StubAdapter(), tmp_path, taint=Taint.clean)
    assert clean.value.code == "clean_input"

    with pytest.raises(PidAdapterError) as mismatch:
        _process(_StubAdapter(), tmp_path, content_hash="0" * 64)
    assert mismatch.value.code == "content_hash_mismatch"

    with pytest.raises(PidAdapterError) as media:
        _process(_StubAdapter(), tmp_path, media_type="application/pdf")
    assert media.value.code == "unsupported_media"


def test_adapter_reports_unavailable_without_local_dependencies(tmp_path) -> None:
    # The real adapter has no local vision deps/weights in this environment.
    adapter = PidIntakeAdapter()
    available, reason = adapter.availability()
    if available:  # pragma: no cover - depends on the environment
        pytest.skip("local vision dependencies are installed")
    assert "missing" in reason
    with pytest.raises(PidAdapterError) as caught:
        _process(adapter, tmp_path)
    assert caught.value.code == "adapter_unavailable"
