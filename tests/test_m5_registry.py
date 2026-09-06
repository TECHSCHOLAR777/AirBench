"""M5.1 — Expanded model registry tests covering all failure paths from the issue spec.

Added tests beyond the existing 3:
  - Mutable tag ('latest') in artifact_path is rejected
  - Missing tokenizer_digest is rejected
  - Missing chat_template_digest is rejected
  - Artifact path escapes artifact_root — rejected
  - Local storage hash mismatch — rejected
  - Stale qualification signature — rejected
  - Role-scope isolation: reasoning cert is not eligible for code role
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import unittest

from contracts import ModelCallRequest, ModelRegistry, ModelTarget, RegistryError
from contracts.model_registry import _target_from_roster, _sha256_descriptor


KEY = b"m5-test-signing-key"


def _target(
    path: str,
    digest: str,
    expiry: str = "2030-01-01T00:00:00Z",
    roles: list | None = None,
    tokenizer_digest: str | None = None,
    chat_template_digest: str | None = None,
    local_storage_hash: str | None = None,
) -> dict:
    """Build a minimal valid target dict for use in tests.

    local_storage_hash defaults to the same value as digest so that
    the on-disk tamper check passes for normal test cases.
    """
    return {
        "target_id": "gemma-26b-q4",
        "repository": "local/google/gemma-4-26b-a4b-it",
        "artifact_digest": digest,
        "artifact_path": path,
        "quantization": "int4_awq",
        "tokenizer_digest": tokenizer_digest if tokenizer_digest is not None else "a" * 64,
        "chat_template_digest": chat_template_digest if chat_template_digest is not None else "b" * 64,
        "runtime_version": "vllm-0.8.5",
        "backend": "vllm",
        "capabilities": ["reasoning"],
        "roles": roles if roles is not None else ["lead", "reasoning"],
        "modalities": ["text"],
        "risk_classes": ["inspection_review"],
        "allowed_clearances": ["restricted"],
        "pack_refs": ["refinery-psu-v0"],
        "hardware_profile_refs": ["gpu-96gb-01"],
        "context_limit": 32768,
        "image_token_limit": 0,
        "tool_call_parser": "json",
        "structured_output_modes": ["json_schema"],
        "license_id": "gemma-license",
        # Default: local_storage_hash == digest so the tamper-check passes for normal tests.
        # Override with a different value to test tamper detection.
        "local_storage_hash": local_storage_hash if local_storage_hash is not None else digest,
        "qualification_certificate": "cert-1",
        "qualification_expires_at": expiry,
        "qualification_signature": "",
        "model_family": "gemma4",
        "display_name": "Test target",
        "revision": "a" * 40,
        "container_digest": "sha256:" + "c" * 64,
        "adapter_id": "airbench-vllm-adapter",
        "adapter_version": "0.1.0",
    }



def _manifest(targets: list, valid_until: str = "2030-01-01T00:00:00Z") -> dict:
    """Sign targets and assemble a valid manifest dict."""
    for target in targets:
        unsigned_target = {k: v for k, v in target.items() if k != "qualification_signature"}
        unsigned_target["qualification_signature"] = "0" * 64
        try:
            payload = ModelTarget.from_dict(unsigned_target).qualification_payload()
        except RegistryError:
            payload = {k: v for k, v in target.items() if k != "qualification_signature"}
        target["qualification_signature"] = hmac.new(
            KEY,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
    unsigned = {
        "registry_id": "registry-1",
        "manifest_version": "1.0",
        "targets": targets,
        "valid_until": valid_until,
    }
    unsigned["signature"] = hmac.new(
        KEY,
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    return unsigned


def _request(role: str = "reasoning", capability: str = "reasoning") -> ModelCallRequest:
    return ModelCallRequest.from_dict({
        "request_id": "request-1",
        "task_id": "task-1",
        "team_id": "team-1",
        "worker_id": "worker-1",
        "task_kind": "inspection_review",
        "modality": "text",
        "required_capability": capability,
        "evidence_summary": ["evidence-1"],
        "clearance": "restricted",
        "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 12000},
        "attempt": 1,
        "idempotency_key": "idem-1",
        "timeout_ms": 1000,
        "role": role,
        "resource_lease_id": "lease-1",
    })


class ModelRegistryTests(unittest.TestCase):
    """M5.1 registry tests — normal path, failure paths, and role-scope isolation."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path
        self._temporary = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    # ── Existing passing tests (must remain green) ────────────────────────────

    def test_signed_registry_verifies_local_artifact_and_exact_scope(self) -> None:
        """Signed registry loads and returns the target for a matching request."""
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"pre-staged model")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        registry = ModelRegistry.load(
            _manifest([_target("gemma.bin", digest)]),
            signing_key=KEY,
            artifact_root=self.tmp_path,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(
            [t.target_id for t in registry.eligible_targets(
                _request(), pack_ref="refinery-psu-v0", hardware_profile_ref="gpu-96gb-01",
                now=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )],
            ["gemma-26b-q4"],
        )

    def test_unsigned_or_tampered_registry_is_rejected(self) -> None:
        """Tampered manifest signature or artifact digest raises RegistryError."""
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"pre-staged model")
        payload = _manifest([_target("gemma.bin", hashlib.sha256(artifact.read_bytes()).hexdigest())])
        for mutator in (
            lambda p: p.update(signature="bad"),
            lambda p: p["targets"][0].update(artifact_digest="d" * 64),
        ):
            with self.assertRaises(RegistryError):
                candidate = json.loads(json.dumps(payload))
                mutator(candidate)
                ModelRegistry.load(candidate, signing_key=KEY, artifact_root=self.tmp_path)

    def test_stale_target_is_not_eligible(self) -> None:
        """An expired qualification certificate makes the target ineligible."""
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"pre-staged model")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        registry = ModelRegistry.load(
            _manifest([_target("gemma.bin", digest, "2025-01-01T00:00:00Z")]),
            signing_key=KEY,
            artifact_root=self.tmp_path,
            now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(
            registry.eligible_targets(
                _request(), pack_ref="refinery-psu-v0", hardware_profile_ref="gpu-96gb-01",
                now=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            (),
        )

    # ── New failure-path tests ────────────────────────────────────────────────

    def test_mutable_tag_in_artifact_path_is_rejected(self) -> None:
        """An artifact path containing ':latest' must be rejected at load time."""
        # A path like 'gemma:latest' indicates a mutable container tag rather than
        # a pinned artifact — the registry must reject this.
        artifact = self.tmp_path / "gemma_latest"
        artifact.write_bytes(b"mutable model")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest = _manifest([_target("gemma:latest", digest)])
        with self.assertRaises(RegistryError, msg="Expected RegistryError for mutable tag ':latest'"):
            ModelRegistry.load(manifest, signing_key=KEY, artifact_root=self.tmp_path)

    def test_missing_tokenizer_digest_is_rejected(self) -> None:
        """A target with an empty tokenizer_digest must be rejected."""
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"model data")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest = _manifest([_target("gemma.bin", digest, tokenizer_digest="")])
        with self.assertRaises(RegistryError, msg="Expected RegistryError for empty tokenizer_digest"):
            ModelRegistry.load(manifest, signing_key=KEY, artifact_root=self.tmp_path)

    def test_missing_chat_template_digest_is_rejected(self) -> None:
        """A target with an empty chat_template_digest must be rejected."""
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"model data")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest = _manifest([_target("gemma.bin", digest, chat_template_digest="")])
        with self.assertRaises(RegistryError, msg="Expected RegistryError for empty chat_template_digest"):
            ModelRegistry.load(manifest, signing_key=KEY, artifact_root=self.tmp_path)

    def test_artifact_path_outside_root_is_rejected(self) -> None:
        """A target whose artifact_path escapes the artifact_root must be rejected.

        This prevents path traversal attacks where a malicious manifest could
        reference files outside the designated model bundle directory.
        """
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"model data")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        # Use a path traversal string
        manifest = _manifest([_target("../outside_root/gemma.bin", digest)])
        with self.assertRaises(RegistryError, msg="Expected RegistryError for path outside artifact_root"):
            ModelRegistry.load(manifest, signing_key=KEY, artifact_root=self.tmp_path)

    def test_windows_absolute_artifact_file_is_rejected(self) -> None:
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"model")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        target = _target("gemma.bin", digest)
        target["artifact_files"] = ["C:\\outside\\gemma.bin"]
        with self.assertRaisesRegex(RegistryError, "artifact_files must contain relative paths"):
            ModelRegistry.load(_manifest([target]), signing_key=KEY, artifact_root=self.tmp_path)

    def test_local_storage_hash_mismatch_is_rejected(self) -> None:
        """A local storage hash that does not match the on-disk artifact must be rejected.

        The registry checks local_storage_hash against the actual artifact file contents.
        A mismatch indicates the locally stored artifact has been tampered.
        """
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"original model")
        real_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

        # Pass a deliberately wrong local_storage_hash to simulate on-disk tampering
        manifest = _manifest([_target("gemma.bin", real_digest, local_storage_hash="f" * 64)])

        with self.assertRaises(RegistryError, msg="Expected RegistryError for local_storage_hash mismatch"):
            ModelRegistry.load(manifest, signing_key=KEY, artifact_root=self.tmp_path)


    def test_stale_qualification_signature_is_rejected(self) -> None:
        """A target whose qualification signature was generated from a different payload is rejected.

        This catches the case where the target fields have been edited after signing.
        """
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"pre-staged model")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        target = _target("gemma.bin", digest)
        # Resign with a different key so the stored signature doesn't match
        wrong_key = b"wrong-key"
        payload = {k: v for k, v in target.items() if k != "qualification_signature"}
        target["qualification_signature"] = hmac.new(
            wrong_key,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        # Re-sign the manifest with the correct key so only the per-target sig is wrong
        unsigned = {
            "registry_id": "registry-1",
            "manifest_version": "1.0",
            "targets": [target],
            "valid_until": "2030-01-01T00:00:00Z",
        }
        unsigned["signature"] = hmac.new(
            KEY,
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()

        with self.assertRaises(RegistryError, msg="Expected RegistryError for wrong qualification signature"):
            ModelRegistry.load(unsigned, signing_key=KEY, artifact_root=self.tmp_path)

    def test_role_scope_isolation_reasoning_not_eligible_for_code_role(self) -> None:
        """A target qualified only for 'reasoning' is not eligible for the 'code' role.

        This enforces the invariant: qualified(target, role_A) ≠ qualified(target, role_B).
        The code_worker role requires a separate qualification certificate.
        """
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"pre-staged model")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        # Target is qualified only for reasoning role
        registry = ModelRegistry.load(
            _manifest([_target("gemma.bin", digest, roles=["reasoning"])]),
            signing_key=KEY,
            artifact_root=self.tmp_path,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        # Request is for the code role — should return empty
        code_request = _request(role="code", capability="code_generation")
        eligible = registry.eligible_targets(
            code_request,
            pack_ref="refinery-psu-v0",
            hardware_profile_ref="gpu-96gb-01",
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(
            eligible,
            (),
            "A target qualified only for 'reasoning' must not be eligible for the 'code' role",
        )

    def test_eligible_target_returned_for_matching_role(self) -> None:
        """Positive control: a target whose role matches is returned as eligible."""
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"pre-staged model")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        registry = ModelRegistry.load(
            _manifest([_target("gemma.bin", digest, roles=["reasoning"])]),
            signing_key=KEY,
            artifact_root=self.tmp_path,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        eligible = registry.eligible_targets(
            _request(role="reasoning", capability="reasoning"),
            pack_ref="refinery-psu-v0",
            hardware_profile_ref="gpu-96gb-01",
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0].target_id, "gemma-26b-q4")

    def test_quantization_alias_is_normalized(self) -> None:
        artifact = self.tmp_path / "gemma.bin"
        artifact.write_bytes(b"model data")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        target = _target("gemma.bin", digest)
        target["quantization"] = "Q4_0"
        registry = ModelRegistry.load(
            _manifest([target]), signing_key=KEY, artifact_root=self.tmp_path,
        )
        self.assertEqual(registry.targets[0].quantization, "int4")

    def test_explicit_directory_file_set_is_hashed_deterministically(self) -> None:
        artifact_dir = self.tmp_path / "bundle"
        artifact_dir.mkdir()
        first = artifact_dir / "weights-a.bin"
        second = artifact_dir / "weights-b.bin"
        first.write_bytes(b"a")
        second.write_bytes(b"b")
        digest = hashlib.sha256(b"a" + b"b").hexdigest()
        target = _target("bundle", digest)
        target["artifact_files"] = ["weights-a.bin", "weights-b.bin"]
        target["role_qualifications"] = [["lead", "cert-1"], ["reasoning", "cert-2"]]
        target["roles"] = ["lead", "reasoning"]
        registry = ModelRegistry.load(
            _manifest([target]), signing_key=KEY, artifact_root=self.tmp_path,
        )
        self.assertEqual(registry.targets[0].artifact_files, ("weights-a.bin", "weights-b.bin"))
        self.assertEqual(registry.targets[0].role_qualifications[1], ("reasoning", "cert-2"))
        self.assertEqual(registry.targets[0].qualification_certificate_for("reasoning"), "cert-2")
        (artifact_dir / "unlisted.txt").write_bytes(b"ignored by the signed artifact set")
        registry.verify_artifacts(self.tmp_path)

    def test_roster_normalization_binds_embedded_components_and_roles(self) -> None:
        artifact_hash = "a" * 64
        target = _target_from_roster({
            "target_id": "embedded",
            "repository": "local/embedded",
            "revision": "sha256:" + artifact_hash,
            "artifact_hash": artifact_hash,
            "artifact_path": "embedded.bin",
            "artifact_files": ["embedded.bin"],
            "local_storage_hash": artifact_hash,
            "tokenizer": {"hash": "bundled"},
            "chat_template": {"template_id": "embedded-template", "hash": "bundled"},
            "quantization": {"format": "Q4_0"},
            "serving": {"runtime": "vllm", "runtime_version": "0.8.5", "adapter_id": "adapter", "adapter_version": "1", "container_digest": "sha256:" + "c" * 64},
            "limits": {"context_tokens": 1, "image_tokens": 0},
            "qualified_roles": [{"role": "lead", "certificate_id": "cert-lead", "qualification_hash": "e" * 64}, {"role": "reasoning", "certificate_id": "cert-reasoning", "qualification_hash": "f" * 64}],
            "capabilities": ["reasoning"], "modalities": ["text"], "risk_classes": ["inspection_review"],
            "allowed_clearances": ["restricted"], "pack_refs": ["pack"], "hardware_profile_refs": ["hw"],
            "tool_call_parser": "json", "structured_output_modes": ["json_schema"], "license": "license",
            "qualification_expires_at": "2030-01-01T00:00:00Z", "qualification_signature": "d" * 64,
        })
        self.assertEqual(target.quantization, "int4")
        self.assertEqual(target.tokenizer_digest, _sha256_descriptor("tokenizer", "bundled", artifact_hash))
        self.assertEqual(target.chat_template_digest, _sha256_descriptor("chat_template", "embedded-template", artifact_hash))
        self.assertEqual(dict(target.role_qualifications)["reasoning"], "cert-reasoning")

    def test_nested_roster_root_and_target_signatures_verify(self) -> None:
        import yaml

        artifact = self.tmp_path / "model.bin"
        artifact.write_bytes(b"nested roster artifact")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        nested_target = {
            "target_id": "nested-target", "repository": "local/nested", "revision": "sha256:" + digest,
            "artifact_hash": digest, "artifact_path": "model.bin", "artifact_files": ["model.bin"],
            "local_storage_hash": digest, "tokenizer": {"hash": "bundled"},
            "chat_template": {"template_id": "nested-template", "hash": "bundled"},
            "quantization": {"format": "Q4_0"}, "serving": {"runtime": "custom", "runtime_version": "1", "adapter_id": "adapter", "adapter_version": "1"},
            "limits": {"context_tokens": 128, "image_tokens": 0},
            "qualified_roles": [{"role": "lead", "certificate_id": "cert-nested", "qualification_hash": "e" * 64}],
            "tool_call_parser": "none", "structured_output_modes": ["json_schema"], "capabilities": ["reasoning"],
            "modalities": ["text"], "risk_classes": ["inspection_review"], "allowed_clearances": ["restricted"],
            "pack_refs": ["pack"], "hardware_profile_refs": ["hw"], "license": "license",
            "qualification_expires_at": "2030-01-01T00:00:00Z", "qualification_signature": "0" * 64,
        }
        normalized = _target_from_roster(nested_target)
        nested_target["qualification_signature"] = hmac.new(
            KEY, json.dumps(normalized.qualification_payload(), sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256,
        ).hexdigest()
        document = {
            "roster": {"roster_id": "nested-roster", "schema_version": "1.0", "network_policy": "air_gapped_no_egress", "targets": [nested_target]},
            "registry_id": "nested-roster", "manifest_version": "1.0", "valid_until": "2030-01-01T00:00:00Z",
        }
        document["signature"] = hmac.new(
            KEY, json.dumps(document, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256,
        ).hexdigest()
        roster_path = self.tmp_path / "roster.yaml"
        roster_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        registry = ModelRegistry.load_roster_file(
            roster_path, signing_key=KEY, artifact_root=self.tmp_path, now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(registry.targets[0].target_id, "nested-target")
