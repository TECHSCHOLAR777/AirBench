"""M10.2 — Offline bundle manifest and startup asset verification tests.

Covers:
- AssetRecord construction and validation.
- BundleManifest serialisation (to_dict / from_dict / to_json / from_json / from_file).
- BundleManifest.build() hashes real files.
- BundleManifest.sign() + verify_signature() round-trip.
- Wrong key fails verification.
- StartupVerifier: valid bundle passes.
- StartupVerifier: missing required asset fails.
- StartupVerifier: hash mismatch fails.
- StartupVerifier: optional missing asset does not fail.
- StartupVerifier: corrupt manifest signature fails.
- StartupVerifier: no key → signature_valid is None (caller decides).
- BundleVerificationResult serialisation.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from airbench.node.bundle import (
    AssetRecord,
    BundleManifest,
    BundleVerificationResult,
    StartupVerifier,
    BUNDLE_MANIFEST_VERSION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIGNING_KEY_32 = b"m10-bundle-test-signing-key-0000"  # exactly 32 bytes


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(tmpdir: str, name: str, content: bytes) -> Path:
    p = Path(tmpdir) / name
    p.write_bytes(content)
    return p


def _make_manifest(assets: list[AssetRecord]) -> BundleManifest:
    return BundleManifest(
        bundle_id="airbench.test.v0",
        bundle_version="0.1.0-test",
        built_at="2026-09-11T00:00:00Z",
        schema_version=BUNDLE_MANIFEST_VERSION,
        assets=tuple(assets),
        signature=None,
    )


# ---------------------------------------------------------------------------
# AssetRecord tests
# ---------------------------------------------------------------------------

class TestAssetRecord(unittest.TestCase):
    def test_valid_construction(self) -> None:
        content = b"hello world"
        digest = _sha(content)
        ar = AssetRecord(asset_id="test.asset", path="/some/file.py", expected_hash=digest)
        self.assertEqual(ar.asset_id, "test.asset")
        self.assertEqual(ar.expected_hash, digest)
        self.assertTrue(ar.required)

    def test_empty_asset_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            AssetRecord(asset_id="", path="/some/file.py", expected_hash="a" * 64)

    def test_empty_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            AssetRecord(asset_id="x.y", path="", expected_hash="a" * 64)

    def test_short_hash_raises(self) -> None:
        with self.assertRaises(ValueError):
            AssetRecord(asset_id="x.y", path="/f", expected_hash="abc")

    def test_non_hex_hash_raises(self) -> None:
        with self.assertRaises(ValueError):
            AssetRecord(asset_id="x.y", path="/f", expected_hash="g" * 64)

    def test_to_dict_from_dict_round_trip(self) -> None:
        ar = AssetRecord(
            asset_id="pack.refinery.v0",
            path="packs/refinery_psu_v0/manifest.yaml",
            expected_hash="a" * 64,
            asset_type="pack",
            required=False,
        )
        restored = AssetRecord.from_dict(ar.to_dict())
        self.assertEqual(restored.asset_id, ar.asset_id)
        self.assertEqual(restored.asset_type, "pack")
        self.assertFalse(restored.required)

    def test_from_dict_non_dict_raises(self) -> None:
        with self.assertRaises(TypeError):
            AssetRecord.from_dict([1, 2, 3])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# BundleManifest tests
# ---------------------------------------------------------------------------

class TestBundleManifest(unittest.TestCase):
    def _simple_manifest(self) -> BundleManifest:
        return _make_manifest([
            AssetRecord("src.airbench", "src/airbench/__init__.py", "a" * 64),
            AssetRecord("pack.refinery", "packs/manifest.yaml", "b" * 64, asset_type="pack"),
        ])

    def test_construction(self) -> None:
        m = self._simple_manifest()
        self.assertEqual(m.bundle_id, "airbench.test.v0")
        self.assertEqual(len(m.assets), 2)
        self.assertIsNone(m.signature)

    def test_to_dict_from_dict_round_trip(self) -> None:
        m = self._simple_manifest()
        restored = BundleManifest.from_dict(m.to_dict())
        self.assertEqual(restored.bundle_id, m.bundle_id)
        self.assertEqual(len(restored.assets), 2)
        self.assertIsNone(restored.signature)

    def test_to_json_from_json_round_trip(self) -> None:
        m = self._simple_manifest()
        text = m.to_json()
        restored = BundleManifest.from_json(text)
        self.assertEqual(restored.bundle_id, m.bundle_id)
        self.assertEqual(restored.bundle_version, m.bundle_version)

    def test_from_json_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            BundleManifest.from_json("not json{{{")

    def test_from_file_reads_correctly(self) -> None:
        m = self._simple_manifest()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            fh.write(m.to_json())
            path = Path(fh.name)
        try:
            loaded = BundleManifest.from_file(path)
            self.assertEqual(loaded.bundle_id, m.bundle_id)
        finally:
            path.unlink()

    def test_from_file_missing_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            BundleManifest.from_file(Path("/nonexistent_m10/bundle.json"))

    def test_wrong_schema_version_raises(self) -> None:
        data = self._simple_manifest().to_dict()
        data["schema_version"] = "99.0"
        with self.assertRaises(ValueError):
            BundleManifest.from_dict(data)

    def test_sign_and_verify_round_trip(self) -> None:
        m = self._simple_manifest()
        signed = m.sign(SIGNING_KEY_32)
        self.assertIsNotNone(signed.signature)
        self.assertTrue(signed.verify_signature(SIGNING_KEY_32))

    def test_wrong_key_fails_verification(self) -> None:
        signed = self._simple_manifest().sign(SIGNING_KEY_32)
        wrong_key = b"wrong-key-wrong-key-wrong-key-00"
        self.assertFalse(signed.verify_signature(wrong_key))

    def test_empty_key_fails_sign(self) -> None:
        with self.assertRaises(ValueError):
            self._simple_manifest().sign(b"")

    def test_unsigned_verify_returns_false(self) -> None:
        m = self._simple_manifest()
        self.assertFalse(m.verify_signature(SIGNING_KEY_32))

    def test_signed_manifest_serialises_with_signature(self) -> None:
        signed = self._simple_manifest().sign(SIGNING_KEY_32)
        d = signed.to_dict()
        self.assertIsNotNone(d["signature"])
        restored = BundleManifest.from_dict(d)
        self.assertTrue(restored.verify_signature(SIGNING_KEY_32))

    def test_build_hashes_real_files(self) -> None:
        content_a = b"file-a content"
        content_b = b"file-b content"
        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = _write(tmpdir, "file_a.txt", content_a)
            path_b = _write(tmpdir, "file_b.py", content_b)
            root = Path(tmpdir)
            m = BundleManifest.build(
                bundle_id="airbench.build.test",
                bundle_version="0.0.1",
                asset_paths=[
                    ("asset.a", "file", path_a),
                    ("asset.b", "file", path_b),
                ],
                bundle_root=root,
            )
            self.assertEqual(len(m.assets), 2)
            self.assertEqual(m.assets[0].expected_hash, _sha(content_a))
            self.assertEqual(m.assets[1].expected_hash, _sha(content_b))
            # Paths should be relative to bundle_root
            self.assertFalse(m.assets[0].path.startswith(tmpdir))

    def test_build_absolute_paths_without_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = _write(tmpdir, "file_a.txt", b"abc")
            m = BundleManifest.build(
                bundle_id="airbench.abs.test",
                bundle_version="0.0.1",
                asset_paths=[("asset.a", "file", path_a)],
            )
            self.assertTrue(Path(m.assets[0].path).is_absolute())


# ---------------------------------------------------------------------------
# StartupVerifier tests
# ---------------------------------------------------------------------------

class TestStartupVerifier(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_asset(self, name: str, content: bytes) -> tuple[Path, str]:
        p = _write(self.tmpdir, name, content)
        return p, _sha(content)

    def _make_and_verify(
        self,
        assets: list[AssetRecord],
        *,
        signing_key: bytes | None = None,
        sign: bool = False,
    ) -> BundleVerificationResult:
        m = _make_manifest(assets)
        if sign and signing_key:
            m = m.sign(signing_key)
        verifier = StartupVerifier(m, bundle_root=self.root, signing_key=signing_key)
        return verifier.verify()

    # ------ passing cases ------

    def test_valid_bundle_passes(self) -> None:
        content = b"valid asset"
        p, digest = self._write_asset("asset.py", content)
        result = self._make_and_verify([
            AssetRecord("src.airbench", p.name, digest),
        ])
        self.assertTrue(result.passed)
        self.assertEqual(len(result.asset_results), 1)
        self.assertEqual(result.asset_results[0].status, "ok")

    def test_valid_signed_bundle_passes(self) -> None:
        content = b"signed content"
        p, digest = self._write_asset("signed_asset.py", content)
        result = self._make_and_verify(
            [AssetRecord("src.test", p.name, digest)],
            signing_key=SIGNING_KEY_32,
            sign=True,
        )
        self.assertTrue(result.passed)
        self.assertTrue(result.signature_valid)

    def test_optional_missing_asset_does_not_fail(self) -> None:
        result = self._make_and_verify([
            AssetRecord("opt.asset", "nonexistent_file.py", "a" * 64, required=False),
        ])
        self.assertTrue(result.passed)
        self.assertEqual(result.asset_results[0].status, "not_required_ok")

    def test_asset_path_cannot_escape_bundle_root(self) -> None:
        result = self._make_and_verify([
            AssetRecord("escape", "../outside.txt", "a" * 64),
        ], signing_key=SIGNING_KEY_32, sign=True)
        self.assertFalse(result.passed)
        self.assertEqual(result.asset_results[0].status, "invalid_path")

    def test_no_signing_key_signature_valid_is_none(self) -> None:
        content = b"test"
        p, digest = self._write_asset("f.py", content)
        result = self._make_and_verify([AssetRecord("f", p.name, digest)])
        self.assertIsNone(result.signature_valid)

    # ------ failure cases ------

    def test_missing_required_asset_fails(self) -> None:
        result = self._make_and_verify([
            AssetRecord("src.missing", "does_not_exist.py", "a" * 64, required=True),
        ])
        self.assertFalse(result.passed)
        self.assertEqual(result.asset_results[0].status, "missing")

    def test_hash_mismatch_required_fails(self) -> None:
        content = b"original content"
        p, _ = self._write_asset("tampered.py", content)
        wrong_hash = _sha(b"different content")
        result = self._make_and_verify([
            AssetRecord("tampered", p.name, wrong_hash, required=True),
        ])
        self.assertFalse(result.passed)
        self.assertEqual(result.asset_results[0].status, "hash_mismatch")

    def test_hash_mismatch_optional_does_not_fail(self) -> None:
        content = b"original"
        p, _ = self._write_asset("opt_tampered.py", content)
        wrong_hash = _sha(b"different")
        result = self._make_and_verify([
            AssetRecord("opt", p.name, wrong_hash, required=False),
        ])
        # Hash mismatch on optional asset: still fails (data integrity must hold)
        self.assertFalse(result.passed)
        self.assertEqual(result.asset_results[0].status, "hash_mismatch")

    def test_corrupt_signature_fails(self) -> None:
        content = b"good content"
        p, digest = self._write_asset("good.py", content)
        m = _make_manifest([AssetRecord("good", p.name, digest)])
        signed = m.sign(SIGNING_KEY_32)
        # Tamper the signature
        corrupted_sig = "0" * len(signed.signature)
        tampered = BundleManifest(
            bundle_id=signed.bundle_id,
            bundle_version=signed.bundle_version,
            built_at=signed.built_at,
            schema_version=signed.schema_version,
            assets=signed.assets,
            signature=corrupted_sig,
        )
        verifier = StartupVerifier(tampered, bundle_root=self.root, signing_key=SIGNING_KEY_32)
        result = verifier.verify()
        self.assertFalse(result.passed)
        self.assertFalse(result.signature_valid)

    def test_multiple_assets_partial_failure(self) -> None:
        good_content = b"good"
        p_good, good_digest = self._write_asset("good.py", good_content)
        result = self._make_and_verify([
            AssetRecord("good", p_good.name, good_digest),
            AssetRecord("missing", "no_such_file.py", "c" * 64, required=True),
        ])
        self.assertFalse(result.passed)
        statuses = {r.asset_id: r.status for r in result.asset_results}
        self.assertEqual(statuses["good"], "ok")
        self.assertEqual(statuses["missing"], "missing")

    # ------ serialisation ------

    def test_result_to_dict(self) -> None:
        content = b"test content"
        p, digest = self._write_asset("r.py", content)
        result = self._make_and_verify([AssetRecord("r", p.name, digest)])
        d = result.to_dict()
        self.assertIn("passed", d)
        self.assertIn("asset_results", d)
        self.assertIn("bundle_id", d)
        self.assertIsInstance(d["asset_results"], list)

    def test_result_json_round_trip(self) -> None:
        content = b"json test"
        p, digest = self._write_asset("j.py", content)
        result = self._make_and_verify([AssetRecord("j", p.name, digest)])
        # Must be JSON-serialisable
        text = json.dumps(result.to_dict())
        restored = json.loads(text)
        self.assertTrue(restored["passed"])


# ---------------------------------------------------------------------------
# Integration: BundleManifest.build → sign → verify via StartupVerifier
# ---------------------------------------------------------------------------

class TestBundleIntegration(unittest.TestCase):
    def test_full_build_sign_verify_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            content_a = b"module content"
            content_b = b"pack content"
            path_a = _write(tmpdir, "module.py", content_a)
            path_b = _write(tmpdir, "pack.yaml", content_b)

            # 1. Build the manifest from real files
            manifest = BundleManifest.build(
                bundle_id="airbench.integration.v0",
                bundle_version="0.1.0",
                asset_paths=[
                    ("src.module", "file", path_a),
                    ("pack.yaml", "pack", path_b),
                ],
                bundle_root=root,
            )

            # 2. Sign it
            signed = manifest.sign(SIGNING_KEY_32)

            # 3. Serialise and reload (simulating reading from disk)
            manifest_path = root / "bundle_manifest.json"
            manifest_path.write_text(signed.to_json(), encoding="utf-8")
            loaded = BundleManifest.from_file(manifest_path)

            # 4. Verify with StartupVerifier
            verifier = StartupVerifier(loaded, bundle_root=root, signing_key=SIGNING_KEY_32)
            result = verifier.verify()

            self.assertTrue(result.passed)
            self.assertTrue(result.signature_valid)
            self.assertEqual(len(result.asset_results), 2)
            self.assertTrue(all(r.status == "ok" for r in result.asset_results))

    def test_tampered_asset_detected_after_build_sign(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original = b"original module"
            path_a = _write(tmpdir, "module.py", original)

            manifest = BundleManifest.build(
                "airbench.tamper.v0", "0.1.0",
                [("src.module", "file", path_a)],
                bundle_root=root,
            )
            signed = manifest.sign(SIGNING_KEY_32)

            # Tamper the asset after signing
            path_a.write_bytes(b"tampered module content")

            verifier = StartupVerifier(signed, bundle_root=root, signing_key=SIGNING_KEY_32)
            result = verifier.verify()

            # Signature is valid (manifest wasn't changed), but the asset is tampered
            self.assertTrue(result.signature_valid)
            self.assertFalse(result.passed)
            self.assertEqual(result.asset_results[0].status, "hash_mismatch")


if __name__ == "__main__":
    unittest.main()
