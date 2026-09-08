"""Offline acceptance-package audit for the AirBench release gate."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from contracts.models import LEDGER_EVENT_TYPES

PLACEHOLDER_MARKERS = ("REPLACE_WITH_MEASURED", "PENDING", "TODO", "FIXME")
RELEASE_EVIDENCE_DIRS = ("acceptance", "benchmarks", "models/roster", "profiles/hardware", "qualifications")
REQUIRED_PACK_FILES = (
    "manifest.yaml", "document_profiles.yaml", "world_schema.yaml", "field_rules.yaml",
    "decision_types.yaml", "risk_mappings.yaml", "clearance_roles.yaml",
    "deliverable_templates.yaml", "worker_requirements.yaml",
)


@dataclass(frozen=True, slots=True)
class AuditFinding:
    code: str
    path: str
    message: str
    blocking: bool = True


@dataclass(frozen=True, slots=True)
class AuditReport:
    findings: tuple[AuditFinding, ...]

    @property
    def passed(self) -> bool:
        return not any(f.blocking for f in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "findings": [
            {"code": f.code, "path": f.path, "message": f.message, "blocking": f.blocking}
            for f in self.findings
        ]}


def _walk_strings(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(child, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{prefix}[{index}]")
    elif isinstance(value, str):
        yield prefix, value


def _load_yaml(path: Path) -> tuple[Any | None, list[AuditFinding]]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")), []
    except (OSError, yaml.YAMLError) as exc:
        return None, [AuditFinding("invalid_yaml", str(path), str(exc))]


def _yaml_findings(path: Path) -> list[AuditFinding]:
    payload, findings = _load_yaml(path)
    for field, value in _walk_strings(payload):
        if any(marker in value for marker in PLACEHOLDER_MARKERS):
            findings.append(AuditFinding("unresolved_evidence", f"{path}:{field}", "release evidence still contains a placeholder"))
    return findings


def audit_repository(root: Path) -> AuditReport:
    findings: list[AuditFinding] = []
    pack_dir = root / "packs" / "refinery_psu_v0"
    manifest_path = pack_dir / "manifest.yaml"
    manifest: Any | None = None
    if not manifest_path.exists():
        findings.append(AuditFinding("missing_domain_pack", str(manifest_path), "domain-pack manifest is missing"))
    else:
        manifest, errors = _load_yaml(manifest_path)
        findings.extend(errors)
        if isinstance(manifest, dict) and manifest.get("signing_status") != "signed":
            findings.append(AuditFinding("unsigned_domain_pack", str(manifest_path), "pack requires an external signature"))
        if isinstance(manifest, dict):
            for key in REQUIRED_PACK_FILES[1:]:
                if not (pack_dir / key).exists():
                    findings.append(AuditFinding("missing_pack_component", str(pack_dir / key), "required declaration is missing"))

    for relative_dir in RELEASE_EVIDENCE_DIRS:
        directory = root / relative_dir
        if directory.exists():
            for path in directory.rglob("*.yaml"):
                findings.extend(_yaml_findings(path))

    catalog_path = root / "src" / "contracts" / "schemas" / "ledger_event_catalog.yaml"
    catalog, errors = _load_yaml(catalog_path)
    findings.extend(errors)
    catalog_events = set(catalog.get("events", ())) if isinstance(catalog, dict) else set()
    expected_events = set(LEDGER_EVENT_TYPES)
    if expected_events - catalog_events:
        findings.append(AuditFinding("ledger_catalog_incomplete", str(catalog_path), f"missing event types: {', '.join(sorted(expected_events - catalog_events))}"))
    if catalog_events - expected_events:
        findings.append(AuditFinding("ledger_catalog_stale", str(catalog_path), f"unknown event types: {', '.join(sorted(catalog_events - expected_events))}"))

    run_manifest_path = root / "acceptance" / "acceptance_run_manifest.yaml"
    run_manifest, errors = _load_yaml(run_manifest_path)
    findings.extend(errors)
    if isinstance(run_manifest, dict):
        for requirement in run_manifest.get("external_evidence_required", ()):
            if not isinstance(requirement, dict) or requirement.get("status") != "complete":
                findings.append(AuditFinding(
                    "external_gate",
                    str(run_manifest_path),
                    f"{requirement.get('id', 'unknown')} is not complete" if isinstance(requirement, dict) else "malformed external evidence requirement",
                ))
    else:
        findings.append(AuditFinding("external_gate", str(run_manifest_path), "acceptance run manifest is missing"))
    return AuditReport(tuple(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args(argv)
    report = audit_repository(args.root.resolve())
    if args.as_json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(f"AirBench acceptance audit: {'PASS' if report.passed else 'BLOCKED'}")
        for finding in report.findings:
            print(f"- {finding.code}: {finding.path}: {finding.message}")
    return 0 if args.allow_incomplete or report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
