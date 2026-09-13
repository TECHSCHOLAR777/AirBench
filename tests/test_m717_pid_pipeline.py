"""Real, offline P&ID pipeline run (opt-in).

    AIRBENCH_RUN_MODEL_TESTS=1 pytest tests/test_m717_pid_pipeline.py

Loads the local YOLO detector (committed weights) and, when present, local
EasyOCR models. Never downloads anything.
"""

from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path

import pytest

RUN_MODEL_TESTS = os.environ.get("AIRBENCH_RUN_MODEL_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}
pytestmark = pytest.mark.skipif(not RUN_MODEL_TESTS, reason="set AIRBENCH_RUN_MODEL_TESTS=1 to run the real P&ID pipeline")

pytest.importorskip("cv2", reason="opencv is an optional vision dependency")
pytest.importorskip("ultralytics", reason="ultralytics is an optional vision dependency")

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_real_pid_pipeline_runs_offline(tmp_path) -> None:
    import cv2
    import numpy as np

    from airbench.intake.pid.adapter import PidIntakeAdapter
    from contracts import Clearance, Taint

    image = np.full((640, 640, 3), 255, dtype=np.uint8)
    cv2.line(image, (60, 60), (580, 60), (0, 0, 0), 2)
    cv2.line(image, (60, 60), (60, 580), (0, 0, 0), 2)
    cv2.circle(image, (320, 320), 34, (0, 0, 0), 2)
    cv2.putText(image, "V-101", (380, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    path = tmp_path / "pid.png"
    cv2.imwrite(str(path), image)
    content = path.read_bytes()

    adapter = PidIntakeAdapter(legend_path=REPO_ROOT / "packs" / "refinery_psu_v0" / "pid_legend.yaml")
    available, reason = adapter.availability()
    assert available, reason

    record = adapter.process(
        page_bytes=content, media_type="image/png", task_id="task.pid.real", intake_id="intake.pid.real",
        revision_id="revision.pid.real", source_ref="local:pid.png", content_hash=sha256(content).hexdigest(),
        clearance=Clearance.internal, taint=Taint.untrusted, workspace=tmp_path,
    )
    assert record.source_ref == "local:pid.png"
    assert record.taint == Taint.untrusted
    assert record.clearance == Clearance.internal
    assert isinstance(record.components, tuple)
    assert record.adapter_version
