import tempfile
import unittest
from pathlib import Path

from airbench.acceptance_audit import audit_repository


class AcceptanceAuditTests(unittest.TestCase):
    def test_repository_audit_is_fail_closed_and_reports_external_gates(self) -> None:
        report = audit_repository(Path(__file__).resolve().parents[1])
        codes = {finding.code for finding in report.findings}
        self.assertFalse(report.passed)
        self.assertIn("external_gate", codes)
        self.assertIn("unresolved_evidence", codes)
        self.assertIn("unsigned_domain_pack", codes)

    def test_placeholder_scan_reports_nested_yaml_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "acceptance").mkdir()
            (root / "acceptance" / "acceptance_run_manifest.yaml").write_text("status: PENDING\n", encoding="utf-8")
            schema_dir = root / "src" / "contracts" / "schemas"
            schema_dir.mkdir(parents=True)
            (schema_dir / "ledger_event_catalog.yaml").write_text("events: []\n", encoding="utf-8")
            report = audit_repository(root)
            self.assertTrue(any(f.code == "unresolved_evidence" for f in report.findings))
            self.assertTrue(any(f.code == "missing_domain_pack" for f in report.findings))

    def test_completed_external_requirements_are_not_reported_as_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "acceptance").mkdir()
            (root / "acceptance" / "acceptance_run_manifest.yaml").write_text(
                "external_evidence_required:\n  - id: example\n    status: complete\n",
                encoding="utf-8",
            )
            schema_dir = root / "src" / "contracts" / "schemas"
            schema_dir.mkdir(parents=True)
            (schema_dir / "ledger_event_catalog.yaml").write_text(
                "events: []\n", encoding="utf-8"
            )
            report = audit_repository(root)
            self.assertFalse(any(f.code == "external_gate" for f in report.findings))


if __name__ == "__main__":
    unittest.main()
