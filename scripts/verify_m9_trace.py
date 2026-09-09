"""Verify and replay an offline M9 demo trace."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contracts import EventLedger, LedgerEventEnvelope


REQUIRED_EVENT_TYPES = {
    "task.created",
    "execution.mode.selected",
    "retrieval.completed",
    "artifact.checked",
    "verification.completed",
    "verification.evaluator.completed",
    "completion.blocked",
    "human.review.required",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_trace(trace_dir: Path) -> dict[str, object]:
    ledger_path = trace_dir / "ledger.jsonl"
    summary_path = trace_dir / "run-summary.json"
    if not ledger_path.is_file() or not summary_path.is_file():
        raise ValueError("trace must contain ledger.jsonl and run-summary.json")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ledger = EventLedger()
    for line_number, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = LedgerEventEnvelope.from_dict(json.loads(line))
            ledger.append(event)
        except Exception as exc:  # pragma: no cover - exercised by CLI failure paths
            raise ValueError(f"invalid ledger event at line {line_number}: {exc}") from exc
    ledger.verify_chain()
    if summary.get("ledger_event_count") != len(ledger.events):
        raise ValueError("summary ledger_event_count does not match ledger")
    if summary.get("ledger_head_hash") != ledger.head_hash:
        raise ValueError("summary ledger_head_hash does not match ledger")

    event_types = {event.event_type for event in ledger.events}
    missing = sorted(REQUIRED_EVENT_TYPES - event_types)
    if missing:
        raise ValueError(f"trace is missing required event types: {', '.join(missing)}")

    runs = summary.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("summary must contain at least one run")
    modes = {run.get("execution_mode") for run in runs if isinstance(run, dict)}
    if not {"serial_virtual_team", "parallel"}.issubset(modes):
        raise ValueError("summary must demonstrate serial and parallel execution")
    if any(not run.get("manual_refs") for run in runs if isinstance(run, dict)):
        raise ValueError("every run must retain at least one local manual/SOP reference")

    checked_artifacts = [
        event.payload for event in ledger.events if event.event_type == "artifact.checked"
    ]
    for event in ledger.events:
        if event.event_type != "artifact.checked":
            continue
        artifact = event.payload
        artifact_path = trace_dir / f"{event.task_id}-approval-note.docx"
        expected_hash = artifact.get("content_hash")
        if not artifact_path.is_file():
            raise ValueError(f"checked artifact is missing: {artifact_path}")
        if expected_hash != _sha256(artifact_path):
            raise ValueError(f"checked artifact hash mismatch: {artifact_path}")

    return {
        "event_count": len(ledger.events),
        "ledger_head_hash": ledger.head_hash,
        "execution_modes": sorted(modes),
        "manual_ref_count": sum(len(run.get("manual_refs", ())) for run in runs if isinstance(run, dict)),
        "checked_artifact_count": len(checked_artifacts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_dir", type=Path)
    args = parser.parse_args()
    try:
        result = verify_trace(args.trace_dir)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"M9 trace verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
