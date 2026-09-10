"""Offline bundle manifest and startup asset verification.

M10.2 — Package the Python control plane, model adapters, local model assets,
sandbox, stores, fonts, templates, and configuration as a signed offline bundle.
Add startup checks for missing or untrusted assets.

Design
------
An offline deployment ships one or more *asset records* — a file path and its
expected SHA-256 hex digest — together with a *bundle manifest* that lists them
all.  The manifest itself is signed with an HMAC-SHA256 key held by the
operator (the same key used to sign domain packs in M9).

``BundleManifest`` is the typed representation of the manifest.  It serialises
to and from a JSON dictionary.

``StartupVerifier`` reads the manifest, re-hashes every declared asset, and
produces a ``BundleVerificationResult``.  On success the node may bind its
socket; on failure it must not start.

Ledger events
~~~~~~~~~~~~~
``StartupVerifier`` does not write to the task ledger (which is task-scoped).
Instead it returns a structured ``BundleVerificationResult`` that
``server.build_node_app`` can include in the sovereignty evidence sidecar.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Asset record
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AssetRecord:
    """One file declared in a bundle manifest."""

    asset_id: str
    """Stable identifier, e.g. ``src.airbench`` or ``pack.refinery_psu_v0``."""

    path: str
    """Path relative to the bundle root, or an absolute path."""

    expected_hash: str
    """Lower-case hex SHA-256 of the file bytes."""

    asset_type: str = "file"
    """Semantic type tag (``file`` | ``model`` | ``pack`` | ``template`` | ``font``)."""

    required: bool = True
    """If ``True`` a missing or mismatched asset fails the verification."""

    def __post_init__(self) -> None:
        if not self.asset_id or not self.asset_id.strip():
            raise ValueError("AssetRecord.asset_id must not be empty")
        if not self.path or not self.path.strip():
            raise ValueError("AssetRecord.path must not be empty")
        if not self.expected_hash or len(self.expected_hash) != 64:
            raise ValueError("AssetRecord.expected_hash must be a 64-character hex string")
        try:
            bytes.fromhex(self.expected_hash)
        except ValueError as exc:
            raise ValueError(f"AssetRecord.expected_hash is not valid hex: {self.expected_hash!r}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "path": self.path,
            "expected_hash": self.expected_hash,
            "asset_type": self.asset_type,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssetRecord":
        if not isinstance(data, dict):
            raise TypeError(f"AssetRecord.from_dict expects a dict, got {type(data).__name__}")
        return cls(
            asset_id=str(data.get("asset_id", "")),
            path=str(data.get("path", "")),
            expected_hash=str(data.get("expected_hash", "")),
            asset_type=str(data.get("asset_type", "file")),
            required=bool(data.get("required", True)),
        )


# ---------------------------------------------------------------------------
# Bundle manifest
# ---------------------------------------------------------------------------

BUNDLE_MANIFEST_VERSION = "1.0"
BUNDLE_MANIFEST_ALGORITHM = "HMAC-SHA256"


@dataclass(frozen=True, slots=True)
class BundleManifest:
    """Typed, signable representation of the offline deployment bundle manifest.

    The manifest lists all assets that must be present and intact before the
    node is allowed to start.  It is signed with an HMAC-SHA256 key so that
    neither a tampered manifest nor a tampered asset can be silently accepted.
    """

    bundle_id: str
    """Unique identifier for this bundle release, e.g. ``airbench.v0.1.0``."""

    bundle_version: str
    """Human-readable version string, e.g. ``0.1.0``."""

    built_at: str
    """ISO-8601 UTC timestamp when the bundle was assembled."""

    schema_version: str
    """Manifest schema version; always ``"1.0"`` for this release."""

    assets: tuple[AssetRecord, ...]
    """Declared assets in the order they must be verified."""

    signature: str | None = None
    """HMAC-SHA256 hex signature over the canonical JSON of all other fields.

    ``None`` until :meth:`sign` is called.  An unsigned manifest is accepted
    only when no signing key is supplied to :class:`StartupVerifier`.
    """

    # ------------------------------------------------------------------
    # Canonical serialisation
    # ------------------------------------------------------------------

    def _canonical_payload(self) -> bytes:
        """Return the bytes that are signed/verified."""
        payload = {
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "built_at": self.built_at,
            "schema_version": self.schema_version,
            "assets": [a.to_dict() for a in self.assets],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

    def sign(self, key: bytes) -> "BundleManifest":
        """Return a new manifest with the HMAC-SHA256 signature filled in."""
        if not key:
            raise ValueError("A non-empty signing key is required")
        sig = hmac.new(key, self._canonical_payload(), hashlib.sha256).hexdigest()
        return BundleManifest(
            bundle_id=self.bundle_id,
            bundle_version=self.bundle_version,
            built_at=self.built_at,
            schema_version=self.schema_version,
            assets=self.assets,
            signature=sig,
        )

    def verify_signature(self, key: bytes) -> bool:
        """Return ``True`` if the signature is valid for ``key``."""
        if not self.signature or not key:
            return False
        expected = hmac.new(key, self._canonical_payload(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "built_at": self.built_at,
            "schema_version": self.schema_version,
            "assets": [a.to_dict() for a in self.assets],
            "signature": self.signature,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BundleManifest":
        if not isinstance(data, dict):
            raise TypeError(f"BundleManifest.from_dict expects a dict, got {type(data).__name__}")
        schema = str(data.get("schema_version", ""))
        if schema and schema != BUNDLE_MANIFEST_VERSION:
            raise ValueError(
                f"Unsupported bundle manifest schema version: {schema!r} "
                f"(expected {BUNDLE_MANIFEST_VERSION!r})"
            )
        raw_assets = data.get("assets") or []
        if not isinstance(raw_assets, list):
            raise TypeError("BundleManifest.assets must be a list")
        return cls(
            bundle_id=str(data.get("bundle_id", "")),
            bundle_version=str(data.get("bundle_version", "")),
            built_at=str(data.get("built_at", "")),
            schema_version=schema or BUNDLE_MANIFEST_VERSION,
            assets=tuple(AssetRecord.from_dict(a) for a in raw_assets),
            signature=str(data["signature"]) if data.get("signature") else None,
        )

    @classmethod
    def from_json(cls, text: str) -> "BundleManifest":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Bundle manifest is not valid JSON: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_file(cls, path: Path) -> "BundleManifest":
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FileNotFoundError(f"Bundle manifest not found: {path}") from exc
        return cls.from_json(text)

    # ------------------------------------------------------------------
    # Factory: build a manifest from a directory tree
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        bundle_id: str,
        bundle_version: str,
        asset_paths: list[tuple[str, str, Path]],
        *,
        bundle_root: Path | None = None,
    ) -> "BundleManifest":
        """Hash each asset file and build a manifest.

        Parameters
        ----------
        bundle_id:
            Unique bundle identifier.
        bundle_version:
            Human-readable version string.
        asset_paths:
            List of ``(asset_id, asset_type, absolute_path)`` tuples.
        bundle_root:
            If supplied, paths in the manifest are recorded as relative to
            this directory.  Otherwise the absolute path is stored.
        """
        assets: list[AssetRecord] = []
        for asset_id, asset_type, abs_path in asset_paths:
            content = abs_path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            path_str = str(abs_path.relative_to(bundle_root)) if bundle_root else str(abs_path)
            assets.append(AssetRecord(
                asset_id=asset_id,
                path=path_str,
                expected_hash=digest,
                asset_type=asset_type,
                required=True,
            ))
        return cls(
            bundle_id=bundle_id,
            bundle_version=bundle_version,
            built_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            schema_version=BUNDLE_MANIFEST_VERSION,
            assets=tuple(assets),
            signature=None,
        )


# ---------------------------------------------------------------------------
# Asset check result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AssetCheckResult:
    """Outcome of verifying one asset."""

    asset_id: str
    path: str
    status: str
    """``ok`` | ``missing`` | ``hash_mismatch`` | ``invalid_path`` | ``not_required_ok``"""
    expected_hash: str | None
    actual_hash: str | None
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status in ("ok", "not_required_ok")

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "path": self.path,
            "status": self.status,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Bundle verification result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BundleVerificationResult:
    """Summary produced by :class:`StartupVerifier`."""

    bundle_id: str
    bundle_version: str
    verified_at: str
    signature_valid: bool | None
    """``True`` / ``False`` if a key was supplied; ``None`` if no key."""
    asset_results: tuple[AssetCheckResult, ...]
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "verified_at": self.verified_at,
            "signature_valid": self.signature_valid,
            "passed": self.passed,
            "asset_results": [r.to_dict() for r in self.asset_results],
        }


# ---------------------------------------------------------------------------
# StartupVerifier
# ---------------------------------------------------------------------------

class StartupVerifier:
    """Verify the offline bundle before the node accepts API requests.

    Usage::

        manifest = BundleManifest.from_file(Path("bundle_manifest.json"))
        verifier = StartupVerifier(manifest, bundle_root=Path("."), signing_key=key)
        result = verifier.verify()
        if not result.passed:
            raise RuntimeError("Bundle verification failed — node will not start")

    The verifier:

    1. Checks the HMAC-SHA256 signature on the manifest (if a key is supplied).
    2. Resolves each asset path relative to ``bundle_root`` (if supplied).
    3. Re-hashes each asset file with SHA-256.
    4. Compares the actual hash against the declared ``expected_hash``.
    5. Marks required-but-missing or hash-mismatched assets as failures.
    """

    def __init__(
        self,
        manifest: BundleManifest,
        *,
        bundle_root: Path | None = None,
        signing_key: bytes | None = None,
    ) -> None:
        self.manifest = manifest
        self.bundle_root = bundle_root
        self.signing_key = signing_key

    def _resolve(self, asset: AssetRecord) -> Path:
        """Resolve an asset path, optionally relative to bundle_root."""
        p = Path(asset.path)
        if self.bundle_root is None:
            return p.resolve()
        root = self.bundle_root.resolve()
        resolved = (p if p.is_absolute() else root / p).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Asset path escapes bundle root: {asset.path!r}") from exc
        return resolved

    def _hash_file(self, path: Path) -> str | None:
        """Return lower-case hex SHA-256 of a file, or ``None`` if unreadable."""
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None

    def verify(self) -> BundleVerificationResult:
        """Run all checks and return a ``BundleVerificationResult``."""
        # 1. Signature check
        if self.signing_key is not None:
            signature_valid: bool | None = self.manifest.verify_signature(self.signing_key)
        else:
            signature_valid = None  # unsigned manifest; caller must decide if this is acceptable

        # 2. Asset checks
        asset_results: list[AssetCheckResult] = []
        all_passed = True

        for asset in self.manifest.assets:
            try:
                resolved = self._resolve(asset)
            except ValueError as exc:
                asset_results.append(AssetCheckResult(
                    asset_id=asset.asset_id,
                    path=asset.path,
                    status="invalid_path",
                    expected_hash=asset.expected_hash,
                    actual_hash=None,
                    detail=str(exc),
                ))
                all_passed = False
                continue
            if not resolved.exists():
                if asset.required:
                    asset_results.append(AssetCheckResult(
                        asset_id=asset.asset_id,
                        path=str(resolved),
                        status="missing",
                        expected_hash=asset.expected_hash,
                        actual_hash=None,
                        detail=f"Required asset not found at {resolved}",
                    ))
                    all_passed = False
                else:
                    asset_results.append(AssetCheckResult(
                        asset_id=asset.asset_id,
                        path=str(resolved),
                        status="not_required_ok",
                        expected_hash=asset.expected_hash,
                        actual_hash=None,
                        detail="Optional asset absent; skipping",
                    ))
                continue

            actual_hash = self._hash_file(resolved)
            if actual_hash is None:
                # File exists but is unreadable
                if asset.required:
                    asset_results.append(AssetCheckResult(
                        asset_id=asset.asset_id,
                        path=str(resolved),
                        status="missing",
                        expected_hash=asset.expected_hash,
                        actual_hash=None,
                        detail=f"Asset exists but could not be read: {resolved}",
                    ))
                    all_passed = False
                continue

            if hmac.compare_digest(actual_hash.lower(), asset.expected_hash.lower()):
                asset_results.append(AssetCheckResult(
                    asset_id=asset.asset_id,
                    path=str(resolved),
                    status="ok",
                    expected_hash=asset.expected_hash,
                    actual_hash=actual_hash,
                ))
            else:
                asset_results.append(AssetCheckResult(
                    asset_id=asset.asset_id,
                    path=str(resolved),
                    status="hash_mismatch",
                    expected_hash=asset.expected_hash,
                    actual_hash=actual_hash,
                    detail=(
                        f"Hash mismatch for {asset.asset_id}: "
                        f"expected {asset.expected_hash[:16]}… "
                        f"actual {actual_hash[:16]}…"
                    ),
                ))
                # A hash mismatch always fails, even for optional assets.
                # "optional" means the file may be absent; it does not mean
                # a present-but-tampered asset is acceptable.
                all_passed = False

        # 3. Signature failure overrides overall result
        if signature_valid is False:
            all_passed = False

        return BundleVerificationResult(
            bundle_id=self.manifest.bundle_id,
            bundle_version=self.manifest.bundle_version,
            verified_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            signature_valid=signature_valid,
            asset_results=tuple(asset_results),
            passed=all_passed,
        )
