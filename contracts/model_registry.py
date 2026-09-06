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
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping

from .models import Clearance, ModelCallRequest

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED = {
    "target_id", "repository", "artifact_digest", "artifact_path", "quantization",
    "artifact_files",
    "tokenizer_digest", "chat_template_digest", "runtime_version", "backend",
    "capabilities", "roles", "modalities", "risk_classes", "allowed_clearances",
    "pack_refs", "hardware_profile_refs", "context_limit", "image_token_limit",
    "tool_call_parser", "structured_output_modes", "license_id", "local_storage_hash",
    "qualification_certificate", "qualification_expires_at", "qualification_signature",
    "model_family", "display_name", "revision", "container_digest",
    "tokenizer_path", "chat_template_path", "processor_digest", "processor_path",
    "chat_template_id", "chat_template_required", "tokenizer_required",
    "adapter_id", "adapter_version", "max_output_tokens", "max_concurrency",
    "max_batch_size", "streaming", "cancellation", "source_evidence",
    "mmproj_digest",
    "role_qualifications", "role_qualification_hashes",
}
_OPTIONAL = {
    "artifact_files", "model_family", "display_name", "revision", "container_digest",
    "tokenizer_path", "chat_template_path", "processor_digest", "processor_path",
    "chat_template_id", "chat_template_required", "tokenizer_required",
    "adapter_id", "adapter_version", "max_output_tokens", "max_concurrency",
    "max_batch_size", "streaming", "cancellation", "source_evidence",
    "mmproj_digest",
    "role_qualifications", "role_qualification_hashes",
}
_REQUIRED = _ALLOWED - _OPTIONAL
_SHA256_PREFIXED = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_RELATIVE_PATH = re.compile(r"^[^/\\].*$")


def _is_safe_relative_path(value: Any) -> bool:
    """Reject absolute, drive-qualified, and traversal paths on either OS."""
    if not isinstance(value, str) or not _RELATIVE_PATH.fullmatch(value):
        return False
    return not (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or ".." in PurePosixPath(value).parts
        or ".." in PureWindowsPath(value).parts
    )


def _sha256_descriptor(*parts: str) -> str:
    """Return a stable digest for an embedded or intentionally absent component.

    GGUF can embed tokenizer/template metadata and embedding services do not
    have a chat template. These are still bound to the signed artifact rather
    than represented by the unsafe sentinel values ``bundled`` or ``none``.
    """
    payload = json.dumps({"component": parts[0], "source": parts[1:]}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_quantization(value: Any) -> str:
    if not isinstance(value, str):
        return value
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "q4_0": "int4",
        "gguf_q4_0": "int4",
        "int4_awq": "int4_awq",
        "awq_int4": "int4_awq",
        "int4_gptq": "int4_gptq",
        "gptq_int4": "int4_gptq",
        "bf16": "bf16",
        "fp16": "fp16",
        "int8": "int8",
        "int4": "int4",
    }
    return aliases.get(normalized, normalized)


def _tuple_field(values: Any, field: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise RegistryError(f"{field} must be an array")
    return tuple(values)


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
    artifact_files: tuple[str, ...] = ()
    role_qualifications: tuple[tuple[str, str], ...] = ()
    role_qualification_hashes: tuple[tuple[str, str], ...] = ()
    model_family: str = ""
    display_name: str = ""
    revision: str = ""
    container_digest: str = ""
    tokenizer_path: str = ""
    chat_template_path: str = ""
    processor_digest: str = ""
    processor_path: str = ""
    chat_template_id: str = ""
    chat_template_required: bool = True
    tokenizer_required: bool = True
    adapter_id: str = ""
    adapter_version: str = ""
    max_output_tokens: int = 0
    max_concurrency: int = 1
    max_batch_size: int = 1
    streaming: bool = False
    cancellation: bool = False
    source_evidence: str = ""
    mmproj_digest: str = ""

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
            for field in ("capabilities", "roles", "modalities", "risk_classes", "pack_refs", "hardware_profile_refs", "structured_output_modes"):
                values[field] = _tuple_field(values[field], field)
            values["allowed_clearances"] = tuple(Clearance(x) for x in _tuple_field(values["allowed_clearances"], "allowed_clearances"))
            values["artifact_files"] = _tuple_field(values.get("artifact_files", ()), "artifact_files")
            raw_role_qualifications = _tuple_field(values.get("role_qualifications", ()), "role_qualifications")
            if any(not isinstance(pair, (list, tuple)) or len(pair) != 2 for pair in raw_role_qualifications):
                raise RegistryError("role_qualifications entries must be [role, certificate] pairs")
            values["role_qualifications"] = tuple(
                (str(pair[0]), str(pair[1])) for pair in raw_role_qualifications
            )
            raw_role_qualification_hashes = _tuple_field(
                values.get("role_qualification_hashes", ()), "role_qualification_hashes"
            )
            if any(not isinstance(pair, (list, tuple)) or len(pair) != 2 for pair in raw_role_qualification_hashes):
                raise RegistryError("role_qualification_hashes entries must be [role, digest] pairs")
            values["role_qualification_hashes"] = tuple(
                (str(pair[0]), str(pair[1])) for pair in raw_role_qualification_hashes
            )
            values["quantization"] = _normalize_quantization(values["quantization"])
            target = cls(**values)
        except (TypeError, ValueError) as exc:
            raise RegistryError(f"invalid model target: {exc}") from exc
        target.validate()
        return target

    def to_dict(self) -> dict[str, Any]:
        defaults = {
            "artifact_files": (), "model_family": "", "display_name": "", "revision": "", "container_digest": "",
            "tokenizer_path": "", "chat_template_path": "", "processor_digest": "", "processor_path": "",
            "chat_template_id": "", "chat_template_required": True, "tokenizer_required": True,
            "adapter_id": "", "adapter_version": "", "max_output_tokens": 0, "max_concurrency": 1,
            "max_batch_size": 1, "streaming": False, "cancellation": False, "source_evidence": "",
            "mmproj_digest": "", "role_qualifications": (),
            "role_qualification_hashes": (),
        }
        result = {field: getattr(self, field) for field in _ALLOWED if field not in defaults or getattr(self, field) != defaults[field]}
        result["allowed_clearances"] = [x.value for x in self.allowed_clearances]
        for field in ("capabilities", "roles", "modalities", "risk_classes", "pack_refs", "hardware_profile_refs", "structured_output_modes", "artifact_files"):
            if field in result:
                result[field] = list(getattr(self, field))
        if self.role_qualifications:
            result["role_qualifications"] = [list(pair) for pair in self.role_qualifications]
        if self.role_qualification_hashes:
            result["role_qualification_hashes"] = [list(pair) for pair in self.role_qualification_hashes]
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
        if self.backend not in {"vllm", "nim", "custom"}:
            raise RegistryError("backend must be vllm, nim, or custom")
        if self.revision and not (re.fullmatch(r"[0-9a-f]{40}", self.revision) or _SHA256_PREFIXED.fullmatch(self.revision)):
            raise RegistryError("revision must be an immutable commit SHA or sha256 digest")
        if self.container_digest and not _SHA256_PREFIXED.fullmatch(self.container_digest):
            raise RegistryError("container_digest must be a sha256 digest")
        if self.backend in {"vllm", "nim"} and not self.container_digest:
            raise RegistryError("container_digest is required for container-backed backends")
        if not self.adapter_id or not self.adapter_version:
            raise RegistryError("adapter_id and adapter_version are required")
        for name in ("processor_digest", "mmproj_digest"):
            value = getattr(self, name)
            if value and not _HEX64.fullmatch(value):
                raise RegistryError(f"{name} must be a lowercase SHA-256 digest")
        for name in ("tokenizer_path", "chat_template_path", "processor_path"):
            value = getattr(self, name)
            if value and not _is_safe_relative_path(value):
                raise RegistryError(f"{name} must be a relative path without traversal")
        for name in ("chat_template_required", "tokenizer_required", "streaming", "cancellation"):
            if type(getattr(self, name)) is not bool:
                raise RegistryError(f"{name} must be boolean")
        for name in ("max_output_tokens", "max_concurrency", "max_batch_size"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise RegistryError(f"{name} must be a non-negative integer")
        if self.max_concurrency < 1 or self.max_batch_size < 1:
            raise RegistryError("max_concurrency and max_batch_size must be positive")
        if self.artifact_files and (
            len(set(self.artifact_files)) != len(self.artifact_files)
            or any(not _is_safe_relative_path(item) for item in self.artifact_files)
        ):
            raise RegistryError("artifact_files must contain relative paths without traversal")
        if self.role_qualifications:
            roles = {role for role, _certificate in self.role_qualifications}
            if len(roles) != len(self.role_qualifications) or roles != set(self.roles):
                raise RegistryError("role_qualifications must contain exactly one certificate per role")
        if self.role_qualification_hashes:
            roles = {role for role, _digest in self.role_qualification_hashes}
            if len(roles) != len(self.role_qualification_hashes) or roles != set(self.roles):
                raise RegistryError("role_qualification_hashes must contain exactly one digest per role")
            if any(not _HEX64.fullmatch(digest) for _role, digest in self.role_qualification_hashes):
                raise RegistryError("role qualification hashes must be lowercase SHA-256 digests")
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

    def qualification_certificate_for(self, role: str) -> str:
        """Return the certificate bound to exactly one worker role."""
        if self.role_qualifications:
            return dict(self.role_qualifications).get(role, "")
        return self.qualification_certificate if role in self.roles else ""

    def matches(self, request: ModelCallRequest, *, pack_ref: str, hardware_profile_ref: str, now: datetime | None = None) -> bool:
        return (
            self.is_current(now)
            and request.role in self.roles
            and bool(self.qualification_certificate_for(request.role))
            and request.modality in self.modalities
            and request.action_risk in self.risk_classes
            and request.required_capability in self.capabilities
            and request.clearance in self.allowed_clearances
            and pack_ref in self.pack_refs
            and hardware_profile_ref in self.hardware_profile_refs
            and request.resource_budget.get("context_tokens", 0) <= self.context_limit
            and request.resource_budget.get("image_tokens", 0) <= self.image_token_limit
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
        if not isinstance(signing_key, bytes) or not signing_key:
            raise RegistryError("signing_key is required")
        if not isinstance(payload.get("targets"), list) or not payload["targets"]:
            raise RegistryError("registry targets must be a non-empty array")
        unsigned = {key: payload[key] for key in payload if key != "signature"}
        expected = hmac.new(signing_key, _canonical(unsigned), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(payload["signature"])):
            raise RegistryError("unsigned or invalid model registry")
        expiry = _parse_time(str(payload["valid_until"]))
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if current >= expiry:
            raise RegistryError("stale model registry")
        targets = tuple(ModelTarget.from_dict(item) for item in payload["targets"])
        if len({target.target_id for target in targets}) != len(targets):
            raise RegistryError("registry target IDs must be unique")
        if any(not target.verify_qualification_signature(signing_key) for target in targets):
            raise RegistryError("unsigned or invalid target qualification")
        registry = cls(str(payload["registry_id"]), str(payload["manifest_version"]), targets, str(payload["signature"]), str(payload["valid_until"]))
        registry.verify_artifacts(artifact_root)
        return registry

    def verify_artifacts(self, artifact_root: Path) -> None:
        root = artifact_root.resolve()
        if not root.is_dir():
            raise RegistryError("artifact root must be an existing directory")
        for target in self.targets:
            # Mutable tag check: reject paths containing ':latest' or any '<name>:<tag>' pattern
            # that implies a mutable container reference instead of a pinned local file path.
            if ":" in target.artifact_path:
                raise RegistryError(
                    f"artifact_path contains a mutable tag (colons not allowed in local paths): {target.target_id}"
                )
            path = (root / target.artifact_path).resolve()
            raw_path = root / target.artifact_path
            if raw_path.is_symlink() or (path == root) or root not in path.parents:
                raise RegistryError(f"artifact path escapes local artifact root: {target.target_id}")
            if not path.exists() or not (path.is_file() or path.is_dir()):
                raise RegistryError(f"missing pre-staged artifact: {target.target_id}")
            digest = _artifact_digest(path, root, target.artifact_files)
            # Verify artifact_digest (primary supply-chain integrity check)
            if not hmac.compare_digest(digest, target.artifact_digest):
                raise RegistryError(f"artifact digest mismatch: {target.target_id}")
            # Verify local_storage_hash (secondary on-disk tamper check).
            # local_storage_hash must equal the actual file hash; a mismatch means
            # the locally staged artifact was modified after the manifest was signed.
            if not hmac.compare_digest(digest, target.local_storage_hash):
                raise RegistryError(f"local storage hash mismatch (artifact tampered on disk): {target.target_id}")
            for field, digest_value in (
                ("tokenizer_path", target.tokenizer_digest),
                ("chat_template_path", target.chat_template_digest),
                ("processor_path", target.processor_digest),
            ):
                relative_component = getattr(target, field)
                # An empty path means the component is embedded in the model
                # artifact or represented by a signed descriptor digest.
                if not relative_component:
                    continue
                component_path = (path / relative_component).resolve()
                if path not in component_path.parents or not component_path.is_file():
                    raise RegistryError(f"missing {field}: {target.target_id}")
                if not hmac.compare_digest(hashlib.sha256(component_path.read_bytes()).hexdigest(), digest_value):
                    raise RegistryError(f"{field} digest mismatch: {target.target_id}")

    def eligible_targets(self, request: ModelCallRequest, *, pack_ref: str, hardware_profile_ref: str, now: datetime | None = None) -> tuple[ModelTarget, ...]:
        return tuple(target for target in self.targets if target.matches(request, pack_ref=pack_ref, hardware_profile_ref=hardware_profile_ref, now=now))

    @classmethod
    def load_roster_file(cls, path: Path, *, signing_key: bytes, artifact_root: Path, now: datetime | None = None) -> "ModelRegistry":
        """Load the repository's nested YAML roster without permitting remote I/O."""
        if not isinstance(signing_key, bytes) or not signing_key:
            raise RegistryError("signing_key is required")
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
        if not isinstance(body.get("targets"), list) or not body["targets"]:
            raise RegistryError("roster.targets must be a non-empty array")
        signature = roster.get("signature", "")
        unsigned_roster = {key: value for key, value in roster.items() if key != "signature"}
        expected = hmac.new(signing_key, _canonical(unsigned_roster), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(signature)):
            raise RegistryError("unsigned or invalid model roster")
        if any(not isinstance(item, Mapping) for item in body["targets"]):
            raise RegistryError("roster targets must be objects")
        targets = tuple(_target_from_roster(item) for item in body["targets"])
        if len({target.target_id for target in targets}) != len(targets):
            raise RegistryError("roster target IDs must be unique")
        if any(not target.verify_qualification_signature(signing_key) for target in targets):
            raise RegistryError("unsigned or invalid target qualification")
        registry = cls(
            str(roster.get("registry_id", body.get("roster_id", ""))),
            str(roster.get("manifest_version", body.get("schema_version", ""))),
            targets,
            str(signature),
            str(roster.get("valid_until", body.get("valid_until", ""))),
        )
        expiry = _parse_time(registry.valid_until)
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if current >= expiry:
            raise RegistryError("stale model registry")
        registry.verify_artifacts(artifact_root)
        return registry


def _artifact_digest(path: Path, root: Path, artifact_files: tuple[str, ...] = ()) -> str:
    """Hash the exact staged artifact, using one canonical file-manifest format."""
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if artifact_files:
        files = [path / relative for relative in artifact_files]
        missing = [relative for relative, candidate in zip(artifact_files, files) if not candidate.is_file()]
        if missing:
            raise RegistryError(f"missing artifact files: {missing}")
        if any(candidate.is_symlink() for candidate in files):
            raise RegistryError("artifact_files may not contain symlinks")
    else:
        files = [item for item in path.rglob("*") if item.is_file()]
        if any(item.is_symlink() for item in files):
            raise RegistryError("directory artifacts may not contain symlinked files")
    digest = hashlib.sha256()
    for child in sorted(files, key=lambda item: item.relative_to(path).as_posix()):
        with child.open("rb") as stream:
            while block := stream.read(16 * 1024 * 1024):
                digest.update(block)
    # Keep the digest convention compatible with airbench_hash.py: the signed
    # artifact_files list supplies names/order, while the digest covers bytes.
    return digest.hexdigest()


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
    if not isinstance(roles, list) or not roles or any(not isinstance(role, Mapping) for role in roles):
        raise RegistryError(f"qualified_roles must be a non-empty array: {item.get('target_id', '<unknown>')}")
    certificates = tuple(str(role.get("certificate_id", "")) for role in roles)
    role_names = tuple(str(role.get("role", "")) for role in roles)
    role_qualifications = tuple((role_name, certificate) for role_name, certificate in zip(role_names, certificates))
    artifact_hash = item.get("artifact_hash")
    tokenizer_hash = tokenizer.get("hash")
    template_id = str(template.get("template_id", ""))
    if tokenizer_hash in {"bundled", "none"}:
        tokenizer_hash = _sha256_descriptor("tokenizer", str(tokenizer_hash), str(artifact_hash))
    if template.get("hash") in {"bundled", "none"} or template_id == "none":
        template_hash = _sha256_descriptor("chat_template", template_id or str(template.get("hash")), str(artifact_hash))
    else:
        template_hash = template.get("hash")
    if not isinstance(item.get("artifact_files"), list) or not item["artifact_files"]:
        raise RegistryError(f"artifact_files must be declared for target: {item.get('target_id', '<unknown>')}")
    return ModelTarget.from_dict({
        "target_id": item.get("target_id"), "repository": item.get("repository"), "artifact_digest": artifact_hash,
        "artifact_path": item.get("artifact_path"), "quantization": str(quantization.get("format", "")).lower(),
        "artifact_files": item.get("artifact_files"),
        "tokenizer_digest": tokenizer_hash, "chat_template_digest": template_hash,
        "runtime_version": f"{serving.get('runtime', '')}-{serving.get('runtime_version', '')}", "backend": serving.get("runtime", ""),
        "capabilities": item.get("capabilities", []), "roles": role_names, "modalities": item.get("modalities", []),
        "risk_classes": item.get("risk_classes", []), "allowed_clearances": item.get("allowed_clearances", []),
        "pack_refs": item.get("pack_refs", []), "hardware_profile_refs": item.get("hardware_profile_refs", []),
        "context_limit": limits.get("context_tokens", 0), "image_token_limit": limits.get("image_tokens", 0),
        "tool_call_parser": item.get("tool_call_parser", ""), "structured_output_modes": item.get("structured_output_modes", []),
        "license_id": item.get("license", ""), "local_storage_hash": item.get("local_storage_hash"),
        "qualification_certificate": certificates[0] if certificates else "", "qualification_expires_at": item.get("qualification_expires_at", ""),
        "qualification_signature": item.get("qualification_signature", ""), "model_family": item.get("model_family", ""),
        "role_qualifications": role_qualifications,
        "role_qualification_hashes": tuple(
            (role_name, str(role.get("qualification_hash", ""))) for role_name, role in zip(role_names, roles)
        ),
        "display_name": item.get("display_name", ""), "revision": item.get("revision", ""), "container_digest": serving.get("container_digest", ""),
        "chat_template_id": template_id, "chat_template_required": template_id != "none",
        "tokenizer_required": True, "tokenizer_path": str(tokenizer.get("path", "")),
        "chat_template_path": str(template.get("path", "")),
        "processor_path": str((item.get("image_processor", {}) or {}).get("path", "")) if isinstance(item.get("image_processor", {}), Mapping) else "",
        "processor_digest": (item.get("image_processor", {}) or {}).get("hash", "") if isinstance(item.get("image_processor", {}), Mapping) else "",
        "adapter_id": serving.get("adapter_id", ""), "adapter_version": serving.get("adapter_version", ""),
        "max_output_tokens": limits.get("max_output_tokens", 0), "max_concurrency": limits.get("max_concurrency", 1),
        "max_batch_size": limits.get("max_batch_size", 1), "streaming": bool(item.get("streaming", False)),
        "cancellation": bool(item.get("cancellation", False)), "source_evidence": item.get("source_evidence", ""),
        "mmproj_digest": (item.get("mmproj", {}) or {}).get("artifact_hash", "") if isinstance(item.get("mmproj", {}), Mapping) else "",
    })
