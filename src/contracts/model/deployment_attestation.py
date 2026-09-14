"""Signed identity for model artifacts that remain on a remote serving host.

The Node cannot hash files that are not mounted locally.  A deployment
attestation is therefore a separate, signed supply-chain record produced on
the inference host.  It binds the remote file hashes and runtime to the
developer-loopback endpoints; it never turns endpoint health into artifact
integrity.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping
from urllib.parse import urlparse

from .model_registry import ModelRegistry, ModelTarget, RegistryError


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _expiry(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("attestation timestamps require a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class RemoteTargetAttestation:
    target_id: str
    repository: str
    revision: str
    artifact_digest: str
    artifact_digest_scheme: str
    artifact_hashes: tuple[tuple[str, str], ...]
    tokenizer_digest: str
    chat_template_digest: str
    processor_digest: str
    runtime_version: str
    container_digest: str
    adapter_id: str
    adapter_version: str
    endpoint_id: str
    developer_endpoint_url: str
    served_model_name: str
    remote_loopback_port: int
    max_images: int
    max_videos: int
    processor_min_pixels: int
    processor_max_pixels: int

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RemoteTargetAttestation":
        required = {
            "target_id", "repository", "revision", "artifact_digest", "artifact_digest_scheme",
            "artifact_hashes", "tokenizer_digest", "chat_template_digest", "processor_digest",
            "runtime_version", "container_digest", "adapter_id", "adapter_version", "endpoint_id",
            "developer_endpoint_url", "served_model_name", "remote_loopback_port", "max_images",
            "max_videos", "processor_min_pixels", "processor_max_pixels",
        }
        if set(value) != required:
            raise ValueError(f"remote attested target fields must be exactly {sorted(required)}")
        raw_hashes = value["artifact_hashes"]
        if not isinstance(raw_hashes, list) or any(not isinstance(item, Mapping) for item in raw_hashes):
            raise ValueError("artifact_hashes must be an array of objects")
        pairs = tuple((str(item.get("path", "")), str(item.get("sha256", ""))) for item in raw_hashes)
        target = cls(
            target_id=str(value["target_id"]), repository=str(value["repository"]), revision=str(value["revision"]),
            artifact_digest=str(value["artifact_digest"]), artifact_digest_scheme=str(value["artifact_digest_scheme"]),
            artifact_hashes=pairs, tokenizer_digest=str(value["tokenizer_digest"]),
            chat_template_digest=str(value["chat_template_digest"]), processor_digest=str(value["processor_digest"]),
            runtime_version=str(value["runtime_version"]), container_digest=str(value["container_digest"]),
            adapter_id=str(value["adapter_id"]), adapter_version=str(value["adapter_version"]),
            endpoint_id=str(value["endpoint_id"]), developer_endpoint_url=str(value["developer_endpoint_url"]),
            served_model_name=str(value["served_model_name"]), remote_loopback_port=int(value["remote_loopback_port"]),
            max_images=int(value["max_images"]), max_videos=int(value["max_videos"]),
            processor_min_pixels=int(value["processor_min_pixels"]), processor_max_pixels=int(value["processor_max_pixels"]),
        )
        target.validate()
        return target

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id, "repository": self.repository, "revision": self.revision,
            "artifact_digest": self.artifact_digest, "artifact_digest_scheme": self.artifact_digest_scheme,
            "artifact_hashes": [{"path": path, "sha256": digest} for path, digest in self.artifact_hashes],
            "tokenizer_digest": self.tokenizer_digest, "chat_template_digest": self.chat_template_digest,
            "processor_digest": self.processor_digest, "runtime_version": self.runtime_version,
            "container_digest": self.container_digest, "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version, "endpoint_id": self.endpoint_id,
            "developer_endpoint_url": self.developer_endpoint_url, "served_model_name": self.served_model_name,
            "remote_loopback_port": self.remote_loopback_port, "max_images": self.max_images,
            "max_videos": self.max_videos, "processor_min_pixels": self.processor_min_pixels,
            "processor_max_pixels": self.processor_max_pixels,
        }

    def validate(self) -> None:
        if not all(isinstance(getattr(self, name), str) and getattr(self, name).strip() for name in (
            "target_id", "repository", "revision", "artifact_digest", "artifact_digest_scheme", "tokenizer_digest",
            "chat_template_digest", "processor_digest", "runtime_version", "container_digest", "adapter_id",
            "adapter_version", "endpoint_id", "developer_endpoint_url", "served_model_name",
        )):
            raise ValueError("remote attested target identity fields are required")
        for name in ("artifact_digest", "tokenizer_digest", "chat_template_digest", "processor_digest"):
            if len(getattr(self, name)) != 64 or any(char not in "0123456789abcdef" for char in getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if not self.container_digest.startswith("sha256:") or len(self.container_digest) != 71:
            raise ValueError("container_digest must be a pinned sha256 digest")
        if self.artifact_digest_scheme != "sha256:file-manifest-v1":
            raise ValueError("remote attestation requires sha256:file-manifest-v1")
        if not self.artifact_hashes or len({path for path, _ in self.artifact_hashes}) != len(self.artifact_hashes):
            raise ValueError("artifact_hashes must contain unique files")
        for path, digest in self.artifact_hashes:
            if (not path or path.startswith(('/', '\\'))
                    or PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute()
                    or PureWindowsPath(path).drive
                    or ".." in PurePosixPath(path).parts or ".." in PureWindowsPath(path).parts):
                raise ValueError("artifact hash paths must be safe relative paths")
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError("artifact file hashes must be lowercase SHA-256 digests")
        manifest = [{"path": path, "sha256": digest} for path, digest in self.artifact_hashes]
        expected_manifest_digest = hashlib.sha256(_canonical(manifest)).hexdigest()
        if not hmac.compare_digest(expected_manifest_digest, self.artifact_digest):
            raise ValueError("artifact_digest does not match the attested file manifest")
        parsed = urlparse(self.developer_endpoint_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("developer endpoint must be loopback HTTP")
        if self.remote_loopback_port not in range(1, 65536):
            raise ValueError("remote_loopback_port must be a valid port")
        for name in ("max_images", "max_videos", "processor_min_pixels", "processor_max_pixels"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")

    def matches(self, target: ModelTarget, endpoint: Any) -> bool:
        return (
            self.target_id == target.target_id and self.repository == target.repository and self.revision == target.revision
            and self.artifact_digest == target.artifact_digest and self.artifact_digest_scheme == target.artifact_digest_scheme
            and tuple(path for path, _ in self.artifact_hashes) == target.artifact_files
            and self.tokenizer_digest == target.tokenizer_digest and self.chat_template_digest == target.chat_template_digest
            and self.processor_digest == target.processor_digest and self.runtime_version == target.runtime_version
            and self.container_digest == target.container_digest and self.adapter_id == target.adapter_id
            and self.adapter_version == target.adapter_version and self.endpoint_id == endpoint.endpoint_id
            and self.developer_endpoint_url == endpoint.base_url and self.served_model_name == endpoint.served_model_name
            and self.max_images == target.max_images and self.max_videos == target.max_videos
            and self.processor_min_pixels == target.processor_min_pixels
            and self.processor_max_pixels == target.processor_max_pixels
        )


@dataclass(frozen=True, slots=True)
class RemoteDeploymentAttestation:
    attestation_id: str
    schema_version: str
    host_id: str
    execution_location: str
    transport_policy: str
    endpoint_policy: str
    runtime_image: str
    runtime_version: str
    container_digest: str
    gpu_profile: str
    precision: str
    issued_at: str
    valid_until: str
    targets: tuple[RemoteTargetAttestation, ...]
    signature: str

    @classmethod
    def from_dict(cls, document: Mapping[str, Any], *, signing_key: bytes,
                  now: datetime | None = None) -> "RemoteDeploymentAttestation":
        required = {
            "attestation_id", "schema_version", "host_id", "execution_location", "transport_policy",
            "endpoint_policy", "runtime_image", "runtime_version", "container_digest", "gpu_profile",
            "precision", "issued_at", "valid_until", "targets", "signature",
        }
        if set(document) != required:
            raise ValueError(f"deployment attestation fields must be exactly {sorted(required)}")
        expected = hmac.new(signing_key, _canonical({key: document[key] for key in document if key != "signature"}), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(document["signature"])):
            raise ValueError("deployment attestation signature is invalid")
        expiry = _expiry(str(document["valid_until"]))
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if current >= expiry:
            raise ValueError("deployment attestation is stale")
        targets = tuple(RemoteTargetAttestation.from_dict(item) for item in document["targets"])
        result = cls(
            attestation_id=str(document["attestation_id"]), schema_version=str(document["schema_version"]),
            host_id=str(document["host_id"]), execution_location=str(document["execution_location"]),
            transport_policy=str(document["transport_policy"]), endpoint_policy=str(document["endpoint_policy"]),
            runtime_image=str(document["runtime_image"]), runtime_version=str(document["runtime_version"]),
            container_digest=str(document["container_digest"]), gpu_profile=str(document["gpu_profile"]),
            precision=str(document["precision"]), issued_at=str(document["issued_at"]),
            valid_until=str(document["valid_until"]), targets=targets, signature=str(document["signature"]),
        )
        result.validate()
        return result

    @classmethod
    def load_file(cls, path: Path, *, signing_key: bytes,
                  now: datetime | None = None) -> "RemoteDeploymentAttestation":
        try:
            import yaml  # type: ignore[import-not-found]
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("deployment attestation could not be read") from exc
        if not isinstance(document, Mapping):
            raise ValueError("deployment attestation must be an object")
        return cls.from_dict(document, signing_key=signing_key, now=now)

    def validate(self) -> None:
        if self.schema_version != "1.0" or self.execution_location != "remote":
            raise ValueError("unsupported deployment attestation schema or location")
        if self.transport_policy != "ssh_loopback_tunnel" or self.endpoint_policy != "developer_loopback_only":
            raise ValueError("deployment attestation transport policy is not approved")
        if not self.targets or len({target.target_id for target in self.targets}) != len(self.targets):
            raise ValueError("deployment attestation targets must be unique and non-empty")
        if not self.container_digest.startswith("sha256:") or len(self.container_digest) != 71:
            raise ValueError("deployment runtime container digest is not pinned")
        if not _expiry(self.issued_at) < _expiry(self.valid_until):
            raise ValueError("deployment attestation interval is invalid")

    def verify_bindings(self, registry: ModelRegistry, endpoints: tuple[Any, ...]) -> None:
        by_target = {target.target_id: target for target in registry.targets}
        by_attestation = {target.target_id: target for target in self.targets}
        if set(by_target) != set(by_attestation) or {spec.target_id for spec in endpoints} != set(by_target):
            raise RegistryError("remote attestation, roster, and endpoint target sets do not match")
        for spec in endpoints:
            target = by_target[spec.target_id]
            attested = by_attestation[spec.target_id]
            if not attested.matches(target, spec):
                raise RegistryError(f"remote deployment attestation does not match target {target.target_id}")
            if target.container_digest != self.container_digest or target.runtime_version != self.runtime_version:
                raise RegistryError(f"remote runtime identity does not match target {target.target_id}")


__all__ = ["RemoteDeploymentAttestation", "RemoteTargetAttestation"]
