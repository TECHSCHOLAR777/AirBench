from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from airbench.qualify import (
    QualificationError,
    QualificationHarness,
    build_certificate,
    load_cases,
    sign_certificate,
    verify_certificate,
    verify_model,
)
from airbench.qualify.__main__ import main


def _write_fixtures(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "seal.qualify.json").write_text(json.dumps({
        "fixture_id": "fixture.seal", "task_kind": "inspection_review",
        "prompt": "Summarize the seal leak finding.", "expected_keywords": ["seal", "isolate"],
    }), encoding="utf-8")
    (directory / "pressure.qualify.json").write_text(json.dumps({
        "fixture_id": "fixture.pressure", "task_kind": "inspection_review",
        "prompt": "State the operating pressure.", "expected_keywords": ["pressure"],
    }), encoding="utf-8")
    return directory


class TestHarness:
    def test_load_and_run_scores_pass_rate(self, tmp_path) -> None:
        cases = load_cases(_write_fixtures(tmp_path))
        assert [case.fixture_id for case in cases] == ["fixture.pressure", "fixture.seal"]

        def complete(prompt: str) -> str:
            return "seal leak requires isolation; isolate the line" if "seal" in prompt else "operating pressure is 12 bar"

        run = QualificationHarness(complete, model_id="target.fixture").run(target_id="target.fixture", role="reasoning", cases=cases)
        assert run.pass_rates["fixture_pass_rate"] == 1.0
        assert run.benchmark_scores["mean_confidence"] == 1.0
        assert len(run.fixture_set_hash) == 64

    def test_missing_fixture_prompt_fails_closed(self, tmp_path) -> None:
        (tmp_path / "bad.qualify.json").write_text(json.dumps({"task_kind": "x"}), encoding="utf-8")
        with pytest.raises(QualificationError):
            load_cases(tmp_path)

    def test_empty_fixture_directory_is_rejected(self, tmp_path) -> None:
        with pytest.raises(QualificationError):
            QualificationHarness(lambda prompt: "", model_id="m").run(target_id="t", role="r", cases=())


class TestCertificate:
    def test_build_sign_and_verify(self, tmp_path) -> None:
        cases = load_cases(_write_fixtures(tmp_path))
        run = QualificationHarness(lambda prompt: "seal isolate pressure", model_id="m").run(target_id="t", role="r", cases=cases)
        certificate = build_certificate(run, hardware_profile_id="workstation_demo", runtime_version="vllm-0.8.5")
        assert certificate["status"] == "ready_for_review"
        assert certificate["expires_at"] > certificate["qualified_at"]
        assert certificate["signature"] is None
        signed = sign_certificate(certificate, b"k" * 32)
        assert verify_certificate(signed, b"k" * 32)
        assert not verify_certificate(signed, b"x" * 32)


class TestCli:
    def test_reference_run_writes_a_labelled_certificate(self, tmp_path) -> None:
        fixtures = _write_fixtures(tmp_path / "fixtures")
        output = tmp_path / "cert.yaml"
        code = main(["--target", "target.e2b", "--role", "reasoning", "--fixtures", str(fixtures), "--output", str(output)])
        assert code == 0
        certificate = yaml.safe_load(output.read_text(encoding="utf-8"))
        assert certificate["qualification_source"] == "reference_self_test"
        assert certificate["target_id"] == "target.e2b"
        assert certificate["pass_rates"]["fixture_pass_rate"] >= 0.0
        assert certificate["status"] == "unqualified"

    def test_response_run_is_signed(self, tmp_path) -> None:
        fixtures = _write_fixtures(tmp_path / "fixtures")
        responses = tmp_path / "responses.json"
        responses.write_text(json.dumps({"fixture.seal": "seal isolate", "fixture.pressure": "pressure"}), encoding="utf-8")
        key = tmp_path / "key.bin"
        key.write_bytes(b"s" * 32)
        output = tmp_path / "cert.yaml"
        code = main([
            "--target", "target.12b", "--role", "reasoning", "--fixtures", str(fixtures),
            "--responses", str(responses), "--signing-key-path", str(key), "--output", str(output),
        ])
        assert code == 0
        certificate = yaml.safe_load(output.read_text(encoding="utf-8"))
        assert certificate["qualification_source"] == "operator_measured"
        assert certificate["status"] == "ready_for_review"
        assert verify_certificate(certificate, b"s" * 32)


class TestModelIntegrity:
    def _artifact(self, tmp_path) -> tuple:
        import hashlib

        path = tmp_path / "model.safetensors"
        path.write_bytes(b"weights")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_full_integrity_pass(self, tmp_path) -> None:
        path, digest = self._artifact(tmp_path)
        result = verify_model(
            artifact_path=path, expected_hash=digest, license_id="apache-2.0",
            license_accepted=True, sandbox_probe=lambda: True,
        )
        assert result.passed
        assert {check.name: check.passed for check in result.checks} == {
            "artifact_present": True, "artifact_hash": True, "safe_format": True,
            "license": True, "sandbox_load": True,
        }

    def test_hash_format_license_and_sandbox_failures(self, tmp_path) -> None:
        path, digest = self._artifact(tmp_path)
        wrong = verify_model(artifact_path=path, expected_hash="0" * 64, license_id="apache-2.0", license_accepted=True, sandbox_probe=lambda: True)
        assert not wrong.passed
        assert {c.name: c.passed for c in wrong.checks}["artifact_hash"] is False

        unsafe = tmp_path / "model.bin"
        unsafe.write_bytes(b"pickle")
        assert not verify_model(artifact_path=unsafe, license_id="x", license_accepted=True, sandbox_probe=lambda: True).passed

        no_license = verify_model(artifact_path=path, expected_hash=digest, sandbox_probe=lambda: True)
        assert {c.name: c.passed for c in no_license.checks}["license"] is False

        no_probe = verify_model(artifact_path=path, expected_hash=digest, license_id="apache-2.0", license_accepted=True)
        assert {c.name: c.passed for c in no_probe.checks}["sandbox_load"] is False

    def test_certificate_records_integrity(self, tmp_path) -> None:
        path, digest = self._artifact(tmp_path)
        integrity = verify_model(artifact_path=path, expected_hash=digest, license_id="apache-2.0", license_accepted=True, sandbox_probe=lambda: True)
        cases = load_cases(_write_fixtures(tmp_path / "fixtures"))
        run = QualificationHarness(lambda prompt: "seal isolate", model_id="m").run(target_id="t", role="r", cases=cases)
        certificate = build_certificate(run, hardware_profile_id="workstation-04", runtime_version="vllm", integrity=integrity)
        assert certificate["model_integrity"]["passed"] is True
        assert len(certificate["model_integrity"]["checks"]) == 5
