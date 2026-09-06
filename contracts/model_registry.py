"""Signed, local-only model target registry for M5.1.

The registry is deliberately independent of a model server.  It proves that a
pre-staged artifact is the exact, qualified target before a later router may
select it.  No method in this module performs network I/O.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .models import Clearance, ModelCallRequest

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED = {
    "target_id", "repository", "artifact_digest", "artifact_path", "quantization",
    "tokenizer_digest", "chat_template_digest", "runtime_version", "backend",
    "capabilities", "roles", "modalities", "risk_classes", "allowed_clearances",
    "pack_refs", "hardware_profile_refs", "context_limit", "image_token_limit",
    "tool_call_parser", "structured_output_modes", "license_id", "local_storage_hash",
    "qualification_certificate", "qualification_expires_at", "qualification_signature",
    "model_family", "display_name", "revision", "container_digest",
}
_REQUIRED = _ALLOWED - {"model_family", "display_name", "revision", "container_digest"}
_SHA256_PREFIXED = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


class RegistryError(ValueError):
    """A target cannot be trusted or cannot be used for the requested role."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise RegistryError("qualification_expires_at must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise RegistryError("qualification_expires_at must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ModelTarget:
    target_id: str
    repository: str
    artifact_digest: str
    artifact_path: str
    quantization: str
    tokenizer_digest: str
    chat_template_digest: str
    runtime_version: str
    backend: str
    capabilities: tuple[str, ...]
    roles: tuple[str, ...]
    modalities: tuple[str, ...]
    risk_classes: tuple[str, ...]
    allowed_clearances: tuple[Clearance, ...]
    pack_refs: tuple[str, ...]
    hardware_profile_refs: tuple[str, ...]
    context_limit: int
    image_token_limit: int
    tool_call_parser: str
    structured_output_modes: tuple[str, ...]
    license_id: str
    local_storage_hash: str
    qualification_certificate: str
    qualification_expires_at: str
    qualification_signature: str
    model_family: str = ""
    display_name: str = ""
    revision: str = ""
    container_digest: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelTarget":
        unknown = set(payload) - _ALLOWED
        missing = _REQUIRED - set(payload)
        if unknown:
            raise RegistryError(f"unknown model target fields: {sorted(unknown)}")
        if missing:
            raise RegistryError(f"missing model target fields: {sorted(missing)}")
        try:
            values = dict(payload)
            values["capabilities"] = tuple(values["capabilities"])
            values["roles"] = tuple(values["roles"])
            values["modalities"] = tuple(values["modalities"])
            values["risk_classes"] = tuple(values["risk_classes"])
            values["allowed_clearances"] = tuple(Clearance(x) for x in values["allowed_clearances"])
            values["pack_refs"] = tuple(values["pack_refs"])
            values["hardware_profile_refs"] = tuple(values["hardware_profile_refs"])
            values["structured_output_modes"] = tuple(values["structured_output_modes"])
            target = cls(**values)
        except (TypeError, ValueError) as exc:
            raise RegistryError(f"invalid model target: {exc}") from exc
        target.validate()
        return target

    def to_dict(self) -> dict[str, Any]:
        result = {field: getattr(self, field) for field in _ALLOWED}
        result["allowed_clearances"] = [x.value for x in self.allowed_clearances]
        for field in ("capabilities", "roles", "modalities", "risk_classes", "pack_refs", "hardware_profile_refs", "structured_output_modes"):
            result[field] = list(getattr(self, field))
        return {key: result[key] for key in sorted(result)}

    def qualification_payload(self) -> dict[str, Any]:
        return {key: value for key, value in self.to_dict().items() if key != "qualification_signature"}

    def verify_qualification_signature(self, signing_key: bytes) -> bool:
        expected = hmac.new(signing_key, _canonical(self.qualification_payload()), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.qualification_signature)

    def validate(self) -> None:
        for name in ("target_id", "repository", "artifact_digest", "artifact_path", "quantization", "tokenizer_digest", "chat_template_digest", "runtime_version", "backend", "tool_call_parser", "license_id", "local_storage_hash", "qualification_certificate", "qualification_expires_at", "qualification_signature"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise RegistryError(f"{name} is required")
        for name in ("artifact_digest", "tokenizer_digest", "chat_template_digest", "local_storage_hash"):
            if not _HEX64.fullmatch(getattr(self, name)):
                raise RegistryError(f"{name} must be a lowercase SHA-256 digest")
        if self.backend not in {"vllm", "nim"}:
            raise RegistryError("backend must be vllm or nim")
        if self.revision and not (re.fullmatch(r"[0-9a-f]{40}", self.revision) or _SHA256_PREFIXED.fullmatch(self.revision)):
            raise RegistryError("revision must be an immutable commit SHA or sha256 digest")
        if self.container_digest and not _SHA256_PREFIXED.fullmatch(self.container_digest):
            raise RegistryError("container_digest must be a sha256 digest")
        if self.quantization not in {"bf16", "fp16", "int8", "int4_awq", "int4_gptq", "int4"}:
            raise RegistryError("unsupported quantization")
        if type(self.context_limit) is not int or self.context_limit < 1:
            raise RegistryError("context_limit must be positive")
        if type(self.image_token_limit) is not int or self.image_token_limit < 0:
            raise RegistryError("image_token_limit must be non-negative")
        if not self.roles or not self.modalities or not self.risk_classes or not self.pack_refs or not self.hardware_profile_refs:
            raise RegistryError("qualification scope cannot be empty")
        _parse_time(self.qualification_expires_at)

    def is_current(self, now: datetime | None = None) -> bool:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return current < _parse_time(self.qualification_expires_at)

    def matches(self, request: ModelCallRequest, *, pack_ref: str, hardware_profile_ref: str, now: datetime | None = None) -> bool:
        return (
            self.is_current(now)
            and request.role in self.roles
            and request.modality in self.modalities
            and request.action_risk in self.risk_classes
            and request.required_capability in self.capabilities
            and request.clearance in self.allowed_clearances
            and pack_ref in self.pack_refs
            and hardware_profile_ref in self.hardware_profile_refs
            and request.resource_budget.get("context_tokens", 0) <= self.context_limit
        )


@dataclass(frozen=True, slots=True)
class ModelRegistry:
    registry_id: str
    manifest_version: str
    targets: tuple[ModelTarget, ...]
    signature: str
    valid_until: str

    @classmethod
    def load(cls, payload: Mapping[str, Any], *, signing_key: bytes, artifact_root: Path, now: datetime | None = None) -> "ModelRegistry":
        required = {"registry_id", "manifest_version", "targets", "signature", "valid_until"}
        unknown = set(payload) - required
        if unknown or set(payload) != required:
            raise RegistryError(f"registry fields must be exactly {sorted(required)}")
        unsigned = {key: payload[key] for key in payload if key != "signature"}
        expected = hmac.new(signing_key, _canonical(unsigned), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(payload["signature"])):
            raise RegistryError("unsigned or invalid model registry")
        expiry = _parse_time(str(payload["valid_until"]))
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if current >= expiry:
            raise RegistryError("stale model registry")
        targets = tuple(ModelTarget.from_dict(item) for item in payload["targets"])
        if any(not target.verify_qualification_signature(signing_key) for target in targets):
            raise RegistryError("unsigned or invalid target qualification")
        registry = cls(str(payload["registry_id"]), str(payload["manifest_version"]), targets, str(payload["signature"]), str(payload["valid_until"]))
        registry.verify_artifacts(artifact_root)
        return registry

    def verify_artifacts(self, artifact_root: Path) -> None:
        root = artifact_root.resolve()
        for target in self.targets:
            # Mutable tag check: reject paths containing ':latest' or any '<name>:<tag>' pattern
            # that implies a mutable container reference instead of a pinned local file path.
            if ":" in target.artifact_path:
                raise RegistryError(
                    f"artifact_path contains a mutable tag (colons not allowed in local paths): {target.target_id}"
                )
            path = (root / target.artifact_path).resolve()
            if root not in path.parents:
                raise RegistryError(f"artifact path escapes local artifact root: {target.target_id}")
            if not path.exists() or not (path.is_file() or path.is_dir()):
                raise RegistryError(f"missing pre-staged artifact: {target.target_id}")
            digest = _artifact_digest(path, root)
            # Verify artifact_digest (primary supply-chain integrity check)
            if not hmac.compare_digest(digest, target.artifact_digest):
                raise RegistryError(f"artifact digest mismatch: {target.target_id}")
            # Verify local_storage_hash (secondary on-disk tamper check).
            # local_storage_hash must equal the actual file hash; a mismatch means
            # the locally staged artifact was modified after the manifest was signed.
            if not hmac.compare_digest(digest, target.local_storage_hash):
                raise RegistryError(f"local storage hash mismatch (artifact tampered on disk): {target.target_id}")

    def eligible_targets(self, request: ModelCallRequest, *, pack_ref: str, hardware_profile_ref: str, now: datetime | None = None) -> tuple[ModelTarget, ...]:
        return tuple(target for target in self.targets if target.matches(request, pack_ref=pack_ref, hardware_profile_ref=hardware_profile_ref, now=now))

    @classmethod
    def load_roster_file(cls, path: Path, *, signing_key: bytes, artifact_root: Path, now: datetime | None = None) -> "ModelRegistry":
        """Load the repository's nested YAML roster without permitting remote I/O."""
        if path.suffix.lower() not in {".yaml", ".yml"}:
            raise RegistryError("model roster must be YAML")
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RegistryError("PyYAML is required to load the offline roster") from exc
        with path.open("r", encoding="utf-8") as stream:
            roster = yaml.safe_load(stream)
        if not isinstance(roster, dict) or not isinstance(roster.get("roster"), dict):
            raise RegistryError("roster must contain a roster object")
        body = roster["roster"]
        targets = tuple(_target_from_roster(item) for item in body.get("targets", ()))
        manifest = {"registry_id": body.get("roster_id"), "manifest_version": body.get("schema_version"), "targets": [target.to_dict() for target in targets], "valid_until": body.get("valid_until", "2099-01-01T00:00:00Z")}
        manifest["signature"] = body.get("signature", "")
        return cls.load(manifest, signing_key=signing_key, artifact_root=artifact_root, now=now)


def _artifact_digest(path: Path, root: Path) -> str:
    """Hash one file or a deterministic directory manifest, never file order."""
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    entries: list[dict[str, str]] = []
    for child in sorted((item for item in path.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        entries.append({"path": child.relative_to(root).as_posix(), "sha256": hashlib.sha256(child.read_bytes()).hexdigest()})
    return hashlib.sha256(_canonical({"files": entries})).hexdigest()


def _target_from_roster(item: Mapping[str, Any]) -> ModelTarget:
    """Convert the human-maintained nested roster shape to the frozen core shape."""
    serving = item.get("serving", {})
    limits = item.get("limits", {})
    tokenizer = item.get("tokenizer", {})
    template = item.get("chat_template", {})
    quantization = item.get("quantization", {})
    roles = item.get("qualified_roles", [])
    if not isinstance(serving, Mapping) or not isinstance(limits, Mapping) or not isinstance(tokenizer, Mapping) or not isinstance(template, Mapping) or not isinstance(quantization, Mapping):
        raise RegistryError(f"invalid nested roster target: {item.get('target_id', '<unknown>')}")
    certificates = tuple(str(role.get("certificate_id", "")) for role in roles if isinstance(role, Mapping))
    role_names = tuple(str(role.get("role", "")) for role in roles if isinstance(role, Mapping))
    return ModelTarget.from_dict({
        "target_id": item.get("target_id"), "repository": item.get("repository"), "artifact_digest": item.get("artifact_hash"),
        "artifact_path": item.get("artifact_path"), "quantization": str(quantization.get("format", "")).lower(),
        "tokenizer_digest": tokenizer.get("hash"), "chat_template_digest": template.get("hash"),
        "runtime_version": f"{serving.get('runtime', '')}-{serving.get('runtime_version', '')}", "backend": serving.get("runtime", ""),
        "capabilities": item.get("capabilities", []), "roles": role_names, "modalities": item.get("modalities", []),
        "risk_classes": item.get("risk_classes", []), "allowed_clearances": item.get("allowed_clearances", []),
        "pack_refs": item.get("pack_refs", []), "hardware_profile_refs": item.get("hardware_profile_refs", []),
        "context_limit": limits.get("context_tokens", 0), "image_token_limit": limits.get("image_tokens", 0),
        "tool_call_parser": item.get("tool_call_parser", ""), "structured_output_modes": item.get("structured_output_modes", []),
        "license_id": item.get("license", ""), "local_storage_hash": item.get("local_storage_hash"),
        "qualification_certificate": certificates[0] if certificates else "", "qualification_expires_at": item.get("qualification_expires_at", ""),
        "qualification_signature": item.get("qualification_signature", ""), "model_family": item.get("model_family", ""),
        "display_name": item.get("display_name", ""), "revision": item.get("revision", ""), "container_digest": serving.get("container_digest", ""),
    })
