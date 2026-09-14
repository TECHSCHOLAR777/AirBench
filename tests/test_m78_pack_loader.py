from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from airbench.node.pack_loader import PackError, PackLoader, compute_pack_signature
from airbench.verification.runner import VerificationOutcome, VerificationRunner, compile_pack_rule
from contracts import Clearance, EventLedger, FactEnvelope, Taint, build_event

REPO_ROOT = Path(__file__).resolve().parents[1]
REFINERY_PACK = REPO_ROOT / "packs" / "refinery_psu_v0"
KEY = b"p" * 32


def _copy_pack(tmp_path: Path) -> Path:
    from pack_support import materialize_pack

    return materialize_pack(tmp_path, signed=False)


def _sign_pack(pack_dir: Path, key: bytes = KEY) -> Path:
    signature = compute_pack_signature(pack_dir, key)
    manifest_path = pack_dir / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["signature"] = signature
    manifest["signing_status"] = "signed"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8")
    return pack_dir


def _seed_task(ledger: EventLedger, task_id: str) -> None:
    ledger.append(build_event(
        event_type="task.created", task_id=task_id, actor_id="test", actor_type="test",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"state": "created"},
        clearance=Clearance.internal, idempotency=f"created-{task_id}", sequence=0,
    ))


def _fact(
    value: object,
    *,
    method: str = "inspection_finding",
    source: str = "calc:pressure-reading",
    unit: str = "bar",
    confidence: float = 0.9,
    taint: Taint = Taint.clean,
) -> FactEnvelope:
    return FactEnvelope.from_dict({
        "fact_id": "fact.pressure", "value": value, "source_ref": source, "confidence": confidence,
        "clearance": "internal", "taint": taint.value, "extraction_method": method, "unit": unit,
        "observed_at": "2026-01-01T00:00:00Z", "ingested_at": "2026-01-01T00:00:00Z",
    })


class TestPackLoader:
    def test_loads_typed_sections_from_the_refinery_pack(self, tmp_path) -> None:
        pack = PackLoader(allow_unsigned=True).load(_copy_pack(tmp_path))
        assert pack.manifest.pack_id == "refinery_psu_inspection_review_v0"
        assert pack.signature_verified is False
        assert set(pack.active_sections()) == {
            "world_schema", "document_profiles", "field_rules", "decision_types", "risk_mappings",
            "clearance_roles", "deliverable_templates", "worker_requirements",
        }
        assert "equipment" in pack.world_schema.objects
        assert any(profile.profile_id == "scanned_inspection_report" for profile in pack.document_profiles)
        assert any(rule.rule_id == "pressure_within_operating_envelope" for rule in pack.field_rules)
        assert any(mapping.action_kind == "release_approval_note" for mapping in pack.risk_mappings)
        assert any(role.role_id == "authorized_approver" for role in pack.clearance_roles)
        assert len(pack.worker_requirements) == 1
        payload = pack.to_dict()
        assert payload["signature_status"] == "unsigned"
        assert payload["counts"]["field_rules"] == 4

    def test_unsigned_pack_is_rejected_by_default(self, tmp_path) -> None:
        with pytest.raises(PackError) as caught:
            PackLoader().load(_copy_pack(tmp_path))
        assert caught.value.code == "unsigned_pack"

    def test_signed_pack_verifies_and_tampering_is_rejected(self, tmp_path) -> None:
        pack_dir = _sign_pack(_copy_pack(tmp_path))
        pack = PackLoader(signing_key=KEY).load(pack_dir)
        assert pack.signature_verified is True

        section = pack_dir / "world_schema.yaml"
        content = yaml.safe_load(section.read_text(encoding="utf-8"))
        content["objects"] = list(content["objects"]) + ["tampered_object"]
        section.write_text(yaml.safe_dump(content, sort_keys=True), encoding="utf-8")
        with pytest.raises(PackError) as caught:
            PackLoader(signing_key=KEY).load(pack_dir)
        assert caught.value.code == "signature_mismatch"

    def test_signed_pack_requires_a_verification_key(self, tmp_path) -> None:
        pack_dir = _sign_pack(_copy_pack(tmp_path))
        with pytest.raises(PackError) as caught:
            PackLoader().load(pack_dir)
        assert caught.value.code == "signing_key_required"

    def test_missing_section_fails_closed(self, tmp_path) -> None:
        pack_dir = _copy_pack(tmp_path)
        (pack_dir / "worker_requirements.yaml").unlink()
        with pytest.raises(PackError) as caught:
            PackLoader(allow_unsigned=True).load(pack_dir)
        assert caught.value.code == "missing_section"

    def test_load_emits_pack_loaded_event(self, tmp_path) -> None:
        ledger = EventLedger()
        _seed_task(ledger, "task.pack.load")
        pack_dir = _sign_pack(_copy_pack(tmp_path))
        PackLoader(signing_key=KEY).load(pack_dir, ledger=ledger, task_id="task.pack.load")
        event = ledger.events[-1]
        assert event.event_type == "pack.loaded"
        assert event.payload["pack_id"] == "refinery_psu_inspection_review_v0"
        assert event.payload["signature_status"] == "signed"


class TestPackFieldRules:
    def setup_method(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.path = _copy_pack(Path(self._tmp.name))
        self.pack = PackLoader(allow_unsigned=True).load(self.path)
        self.runner = VerificationRunner(EventLedger())

    def teardown_method(self) -> None:
        self._tmp.cleanup()

    def test_range_check_rejects_out_of_envelope_fact(self) -> None:
        high = self.runner.run_pack_rules(_fact(250), self.pack.field_rules, fact_type="inspection_finding")
        outcome = {check.rule_id: check.outcome for check in high}
        assert outcome["pressure_within_operating_envelope"] == VerificationOutcome.failed

        nominal = self.runner.run_pack_rules(_fact(50), self.pack.field_rules, fact_type="inspection_finding")
        assert {check.rule_id: check.outcome for check in nominal}["pressure_within_operating_envelope"] == VerificationOutcome.passed

    def test_citation_rule_checks_source_prefixes(self) -> None:
        bad = self.runner.run_pack_rules(
            _fact(1, method="approval_note", source="upload:inspection.pdf"),
            self.pack.field_rules, fact_type="approval_note",
        )
        assert {check.rule_id: check.outcome for check in bad}["numeric_value_requires_deterministic_derivation"] == VerificationOutcome.failed

        good = self.runner.run_pack_rules(
            _fact(1, method="approval_note", source="calc:pressure"),
            self.pack.field_rules, fact_type="approval_note",
        )
        assert {check.rule_id: check.outcome for check in good}["numeric_value_requires_deterministic_derivation"] == VerificationOutcome.passed

    def test_cross_reference_without_a_second_fact_requires_review(self) -> None:
        checks = self.runner.run_pack_rules(
            _fact(1, method="approval_note"), self.pack.field_rules, fact_type="approval_note",
        )
        outcome = {check.rule_id: check.outcome for check in checks}
        assert outcome["approval_note_requires_independent_verification"] == VerificationOutcome.needs_review
        rule = next(rule for rule in self.pack.field_rules if rule.rule_id == "approval_note_requires_independent_verification")
        assert compile_pack_rule(rule, _fact(1)) is None

    def test_cross_reference_is_checked_against_the_world_model(self) -> None:
        from airbench.knowledge.world_model import CandidateFact, CandidateFactWriter, WorldModelStore, candidate_id
        from contracts import FactEnvelope, Taint as _Taint

        store = WorldModelStore()
        entity = FactEnvelope(
            fact_id="fact.pump", value={"entity_id": "equipment.P-101", "object_type": "equipment"},
            source_ref="upload:report.pdf#page-1", confidence=0.9, clearance=Clearance.internal,
            taint=_Taint.untrusted, extraction_method="entity_extractor:fixture",
            observed_at="2026-01-01T00:00:00Z", ingested_at="2026-01-01T00:00:01Z",
        )
        candidate = CandidateFact(candidate_id("task.cross", entity), "task.cross", entity, ("evidence.1",), "c.1", "v.1")
        writer = CandidateFactWriter(store, consistency_gate=lambda _: True, verification_gate=lambda _: True)
        writer.stage(candidate)
        writer.commit(candidate.candidate_id)

        referencing = _fact({"entity_id": "equipment.P-101", "object_type": "approval_note"}, method="approval_note")
        with_model = self.runner.run_pack_rules(referencing, self.pack.field_rules, fact_type="approval_note", world_model=store)
        assert {c.rule_id: c.outcome for c in with_model}["approval_note_requires_independent_verification"] == VerificationOutcome.passed

        unknown = _fact({"entity_id": "equipment.UNKNOWN", "object_type": "approval_note"}, method="approval_note")
        missing = self.runner.run_pack_rules(unknown, self.pack.field_rules, fact_type="approval_note", world_model=store)
        assert {c.rule_id: c.outcome for c in missing}["approval_note_requires_independent_verification"] == VerificationOutcome.failed

        without_model = self.runner.run_pack_rules(referencing, self.pack.field_rules, fact_type="approval_note")
        assert {c.rule_id: c.outcome for c in without_model}["approval_note_requires_independent_verification"] == VerificationOutcome.needs_review

    def test_rules_do_not_apply_to_other_fact_types(self) -> None:
        assert self.runner.run_pack_rules(_fact(250), self.pack.field_rules, fact_type="equipment") == ()
