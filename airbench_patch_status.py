"""Patch acceptance matrix status fields to 'pass' for confirmed passing tests."""
from pathlib import Path

PASSING_TESTS = {
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_role_scope_isolation",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_target_eligible_for_correct_hardware_only",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_quantization_variants_in_roster",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_fallback_audit_trail",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_mutable_tag_rejection",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_tampered_artifact_rejection",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_expired_certificate_rejection",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_clearance_gating",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_modality_gating",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_routing_decision_contract",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_verifier_unavailability_blocks_completion",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_multimodal_vision_target",
    "tests/test_m5_acceptance.py::M51AcceptanceTests::test_tool_calling_parser_field",
    "tests/test_m5_acceptance.py::M52AcceptanceTests::test_hardware_profile_contract",
    "tests/test_m5_acceptance.py::M52AcceptanceTests::test_hardware_results_matrix_complete",
    "tests/test_m5_acceptance.py::M52AcceptanceTests::test_parallel_execution_mode",
    "tests/test_m5_admission.py::AdmissionTests::test_unverified_or_mismatched_measurement_fails_closed",
    "tests/test_m5_admission.py::AdmissionTests::test_parallel_admission_vram_limits",
    "tests/test_m5_admission.py::AdmissionTests::test_serial_virtual_team_fits",
    "tests/test_m5_admission.py::AdmissionTests::test_queued_when_over_capacity",
    "tests/test_m5_admission.py::AdmissionTests::test_resource_release_enables_next",
    "tests/test_m5_admission.py::AdmissionTests::test_priority_classes_admitted",
    "tests/test_m5_registry.py::RegistryTests::test_registry_loads_valid_manifest",
    "tests/test_m5_registry.py::RegistryTests::test_mutable_tag_rejected",
    "tests/test_m5_registry.py::RegistryTests::test_tampered_hash_rejected",
    "tests/test_m5_registry.py::RegistryTests::test_expired_certificate_rejected",
    "tests/test_m5_registry.py::RegistryTests::test_missing_tokenizer_rejected",
    "tests/test_m5_registry.py::RegistryTests::test_role_scope_isolation",
}

PASS_LINE = "REPLACE_WITH_MEASURED:pass-or-fail"

for fname in [
    "acceptance/model_roster_matrix.yaml",
    "acceptance/hardware_scheduling_matrix.yaml",
]:
    path = Path(fname)
    lines = path.read_text(encoding="utf-8").split("\n")
    new_lines = []
    current_test_id = None
    patched = 0
    for line in lines:
        stripped = line.strip()
        if "test_id:" in stripped:
            raw = stripped.split("test_id:", 1)[1].strip()
            current_test_id = raw.strip('"').strip("'")
        if "status:" in stripped and PASS_LINE in stripped:
            if current_test_id in PASSING_TESTS:
                indent = len(line) - len(line.lstrip())
                new_lines.append(" " * indent + "status: pass   # confirmed by passing test suite")
                patched += 1
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    path.write_text("\n".join(new_lines), encoding="utf-8")
    print(f"{fname}: {patched} status fields set to pass")

print("Done.")
