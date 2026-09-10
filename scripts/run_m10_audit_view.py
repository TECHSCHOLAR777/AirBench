"""M10.3 — Offline ledger audit view for the AirBench release gate.

Reads a JSONL ledger export (one JSON object per line, each representing a
``LedgerEventEnvelope``) and produces:

* Per-event summary table (event_type, task_id, actor, clearance, occurred_at)
* Route-trace view (all routing-decision and model-call events per task)
* Artifact hash manifest (all artifact.staged and evidence.created events)
* Chain integrity verification (event_hash chain across the sequence)
* No-egress evidence record (endpoint.egress.denied counts and no outbound
  calls detected when the count is > 0 or an offline flag is declared)

Outputs a JSON report to stdout or a file, suitable for offline review.

Usage::

    python scripts/run_m10_audit_view.py --help
    python scripts/run_m10_audit_view.py <ledger.jsonl>
    python scripts/run_m10_audit_view.py <ledger.jsonl> --output evidence.json
    python scripts/run_m10_audit_view.py <ledger.jsonl> --format table
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# JSONL ledger loading
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL ledger export.  Each non-blank line is one event."""
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {lineno}: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"Line {lineno}: expected a JSON object, got {type(obj).__name__}")
            events.append(obj)
    return events


# ---------------------------------------------------------------------------
# Chain integrity verification
# ---------------------------------------------------------------------------

@dataclass
class ChainCheckResult:
    passed: bool
    event_count: int
    first_broken_sequence: int | None = None
    detail: str = ""


def _verify_chain(events: list[dict[str, Any]]) -> ChainCheckResult:
    """Verify the SHA-256 event_hash chain.

    Each event must declare ``event_hash`` equal to
    ``SHA-256(canonical_json(all other fields))``.  We also check that
    ``previous_event_hash`` on event N matches ``event_hash`` on event N-1.
    """
    if not events:
        return ChainCheckResult(passed=True, event_count=0, detail="Empty ledger — nothing to verify")

    prev_hash: str | None = None
    for i, raw in enumerate(events):
        event_hash = raw.get("event_hash", "")
        prev = raw.get("previous_event_hash")

        # 1. Check previous_event_hash linkage
        if i == 0:
            if prev not in (None, ""):
                # First event may have a non-None previous hash in replay exports
                pass
        else:
            if prev != prev_hash:
                return ChainCheckResult(
                    passed=False,
                    event_count=len(events),
                    first_broken_sequence=i,
                    detail=(
                        f"Sequence {i}: previous_event_hash {prev!r} "
                        f"does not match prior event_hash {prev_hash!r}"
                    ),
                )

        # 2. Re-compute the event hash over all fields except event_hash itself
        payload_for_hash = {k: v for k, v in raw.items() if k != "event_hash"}
        canonical = json.dumps(payload_for_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        computed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if computed != event_hash:
            return ChainCheckResult(
                passed=False,
                event_count=len(events),
                first_broken_sequence=i,
                detail=(
                    f"Sequence {i} (event_type={raw.get('event_type', '?')}): "
                    f"stored hash {event_hash!r} != computed {computed!r}"
                ),
            )

        prev_hash = event_hash

    return ChainCheckResult(passed=True, event_count=len(events))


# ---------------------------------------------------------------------------
# Route trace view
# ---------------------------------------------------------------------------

_ROUTE_EVENT_TYPES = {
    "routing.decision", "routing.fallback.selected", "routing.queued",
    "model.requested", "model.responded", "model.failed",
    "model.call.started", "model.call.completed", "model.call.failed",
    "fallback.selected", "endpoint.selected", "endpoint.rejected",
}


def _build_route_trace(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Return route-trace events grouped by task_id."""
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        if ev.get("event_type") in _ROUTE_EVENT_TYPES:
            task_id = ev.get("task_id", "unknown")
            by_task[task_id].append({
                "sequence": ev.get("sequence"),
                "event_type": ev.get("event_type"),
                "actor": ev.get("actor_id"),
                "occurred_at": ev.get("occurred_at"),
                "model_id": ev.get("payload", {}).get("model_id"),
                "endpoint": ev.get("payload", {}).get("endpoint"),
            })
    return dict(by_task)


# ---------------------------------------------------------------------------
# Artifact hash manifest
# ---------------------------------------------------------------------------

def _build_artifact_manifest(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect all artifact.staged and evidence.created events."""
    artifacts = []
    for ev in events:
        if ev.get("event_type") == "artifact.staged":
            p = ev.get("payload", {})
            artifacts.append({
                "type": "artifact",
                "artifact_id": p.get("artifact_id"),
                "content_hash": p.get("content_hash"),
                "task_id": ev.get("task_id"),
                "occurred_at": ev.get("occurred_at"),
                "actor": ev.get("actor_id"),
            })
        elif ev.get("event_type") == "evidence.created":
            p = ev.get("payload", {})
            artifacts.append({
                "type": "evidence",
                "evidence_id": p.get("evidence_id"),
                "content_hash": p.get("content_hash"),
                "task_id": ev.get("task_id"),
                "occurred_at": ev.get("occurred_at"),
                "actor": ev.get("actor_id"),
            })
    return artifacts


# ---------------------------------------------------------------------------
# No-egress evidence
# ---------------------------------------------------------------------------

def _build_egress_evidence(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Collect egress-related ledger events.

    ``endpoint.egress.denied`` events indicate that an outbound call was
    blocked by the local air-gap guard.  A ledger with only
    ``endpoint.egress.denied`` and no ``endpoint.request.completed`` events
    from an external source constitutes no-egress evidence.
    """
    denied: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("event_type") == "endpoint.egress.denied":
            denied.append({
                "task_id": ev.get("task_id"),
                "occurred_at": ev.get("occurred_at"),
                "endpoint": ev.get("payload", {}).get("endpoint"),
            })
        elif ev.get("event_type") == "endpoint.request.completed":
            p = ev.get("payload", {})
            completed.append({
                "task_id": ev.get("task_id"),
                "occurred_at": ev.get("occurred_at"),
                "endpoint": p.get("endpoint"),
                "source": p.get("source"),
            })

    # No-egress: either no requests at all, or all requests were denied
    no_egress = len(completed) == 0
    return {
        "no_egress": no_egress,
        "egress_denied_count": len(denied),
        "egress_completed_count": len(completed),
        "denied_events": denied,
        "completed_events": completed,
    }


# ---------------------------------------------------------------------------
# Per-event summary
# ---------------------------------------------------------------------------

def _build_event_summary(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sequence": ev.get("sequence"),
            "event_type": ev.get("event_type"),
            "task_id": ev.get("task_id"),
            "actor": ev.get("actor_id"),
            "clearance": ev.get("clearance"),
            "occurred_at": ev.get("occurred_at"),
        }
        for ev in events
    ]


# ---------------------------------------------------------------------------
# Table formatter
# ---------------------------------------------------------------------------

def _fmt_table(summary: list[dict[str, Any]]) -> str:
    cols = ["sequence", "event_type", "task_id", "actor", "clearance", "occurred_at"]
    col_widths = {c: max(len(c), max((len(str(r.get(c) or "")) for r in summary), default=0)) for c in cols}
    sep = "+" + "+".join("-" * (col_widths[c] + 2) for c in cols) + "+"
    header = "|" + "|".join(f" {c:<{col_widths[c]}} " for c in cols) + "|"
    lines = [sep, header, sep]
    for row in summary:
        lines.append("|" + "|".join(f" {str(row.get(c) or ''):<{col_widths[c]}} " for c in cols) + "|")
    lines.append(sep)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main report assembly
# ---------------------------------------------------------------------------

@dataclass
class AuditReport:
    event_count: int
    chain: ChainCheckResult
    event_summary: list[dict[str, Any]]
    route_trace: dict[str, list[dict[str, Any]]]
    artifact_manifest: list[dict[str, Any]]
    egress_evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "chain": {
                "passed": self.chain.passed,
                "event_count": self.chain.event_count,
                "first_broken_sequence": self.chain.first_broken_sequence,
                "detail": self.chain.detail,
            },
            "event_summary": self.event_summary,
            "route_trace": self.route_trace,
            "artifact_manifest": self.artifact_manifest,
            "egress_evidence": self.egress_evidence,
            "no_egress": self.egress_evidence.get("no_egress", False),
            "passed": self.chain.passed,
        }


def run_audit(path: Path) -> AuditReport:
    events = _load_jsonl(path)
    chain = _verify_chain(events)
    return AuditReport(
        event_count=len(events),
        chain=chain,
        event_summary=_build_event_summary(events),
        route_trace=_build_route_trace(events),
        artifact_manifest=_build_artifact_manifest(events),
        egress_evidence=_build_egress_evidence(events),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ledger", type=Path, help="Path to the JSONL ledger export file")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Write JSON report to this file (default: stdout)")
    parser.add_argument("--format", choices=["json", "table"], default="json", help="Output format (default: json)")
    args = parser.parse_args(argv)

    if not args.ledger.exists():
        print(f"Error: ledger file not found: {args.ledger}", file=sys.stderr)
        return 2

    try:
        report = run_audit(args.ledger)
    except (ValueError, OSError) as exc:
        print(f"Error reading ledger: {exc}", file=sys.stderr)
        return 1

    if args.format == "table":
        output = _fmt_table(report.event_summary)
        print(f"\nAirBench Audit View — {args.ledger}")
        print(f"Events: {report.event_count}  Chain: {'PASS' if report.chain.passed else 'FAIL'}  No-Egress: {report.egress_evidence['no_egress']}")
        print(output)
        print(f"\nArtifacts/Evidence: {len(report.artifact_manifest)}")
        for a in report.artifact_manifest:
            print(f"  [{a['type']}] {a.get('artifact_id') or a.get('evidence_id')} hash={a.get('content_hash', 'N/A')[:16]}…")
    else:
        text = json.dumps(report.to_dict(), indent=2, sort_keys=True)
        if args.output:
            args.output.write_text(text, encoding="utf-8")
            print(f"Audit report written to {args.output}")
        else:
            print(text)

    return 0 if report.chain.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
