"""Typed, security-checked configuration for a remote model endpoint.

The endpoint is a transport location, not a model qualification record.  A
remote adapter may use this profile only after the profile signature, model
identity, freshness, allowlist, and egress policy have all been checked.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlparse

from .backend import BackendHealth, BackendReadiness
from ..errors import ContractValidationError, ValidationIssue
from .model_registry import ModelTarget
from ..models import Clearance, Contract, ModelCallRequest

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_PLACEHOLDER_MARKERS = ("REPLACE_WITH", "CHANGE_ME", "example.invalid", "<", ">")


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker.lower() in lowered for marker in _PLACEHOLDER_MARKERS)


def _parse_expiry(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("qualification expiry must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class RemoteEndpointProfile(Contract):
    """Signed endpoint metadata kept separate from a model artifact identity."""

    endpoint_id: str
    endpoint_url: str
    provider_type: str
    backend_type: str
    model_target_id: str
    artifact_digest: str
    tokenizer_digest: str
    chat_template_digest: str
    runtime_version: str
    adapter_id: str
    adapter_version: str
    capabilities: tuple[str, ...]
    roles: tuple[str, ...]
    modalities: tuple[str, ...]
    risk_classes: tuple[str, ...]
    allowed_clearances: tuple[Clearance, ...]
    license_id: str
    qualification_reference: str
    qualification_expires_at: str
    qualification_signature: str
    execution_location: str
    remote_execution_policy: str
    data_egress_policy: str
    allowed_hosts: tuple[str, ...]
    credential_env: str
    timeout_ms: int = 120_000
    max_retries: int = 0
    streaming: bool = False
    cancellation: bool = False
    certificate_fingerprint: str = ""
    health_state: BackendHealth = BackendHealth.unhealthy
    readiness_state: BackendReadiness = BackendReadiness.not_ready
    retry_only_idempotent: bool = True
    disabled: bool = False

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RemoteEndpointProfile":
        value = dict(payload)
        for name in ("capabilities", "roles", "modalities", "risk_classes", "allowed_hosts"):
            value[name] = tuple(value.get(name, ()))
        value["allowed_clearances"] = tuple(
            Clearance(item) for item in value.get("allowed_clearances", ())
        )
        return super().from_dict(value)  # type: ignore[return-value]

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        required = (
            "endpoint_id", "endpoint_url", "provider_type", "backend_type", "model_target_id",
            "runtime_version", "adapter_id", "adapter_version", "license_id",
            "qualification_reference", "qualification_expires_at", "qualification_signature",
            "execution_location", "data_egress_policy", "credential_env",
        )
        for name in required:
            if not getattr(self, name).strip():
                issues.append(ValidationIssue(name, "required", f"{name} is required"))
        for name in ("artifact_digest", "tokenizer_digest", "chat_template_digest", "qualification_signature"):
            if not _HEX64.fullmatch(getattr(self, name)):
                issues.append(ValidationIssue(name, "digest", f"{name} must be a lowercase SHA-256 digest"))
        if self.certificate_fingerprint and not re.fullmatch(r"[0-9a-fA-F:]{32,95}", self.certificate_fingerprint):
            issues.append(ValidationIssue("certificate_fingerprint", "tls", "invalid certificate fingerprint"))
        parsed = urlparse(self.endpoint_url)
        if parsed.scheme != "https":
            issues.append(ValidationIssue("endpoint_url", "tls", "remote endpoints must use HTTPS"))
        if not parsed.hostname:
            issues.append(ValidationIssue("endpoint_url", "url", "endpoint URL must contain a hostname"))
        if parsed.username or parsed.password:
            issues.append(ValidationIssue("endpoint_url", "secret", "credentials must not appear in endpoint URLs"))
        if not self.allowed_hosts:
            issues.append(ValidationIssue("allowed_hosts", "allowlist", "an explicit host allowlist is required"))
        elif parsed.hostname and parsed.hostname not in self.allowed_hosts:
            issues.append(ValidationIssue("allowed_hosts", "allowlist", "endpoint host is not allowlisted"))
        if not _ENV_NAME.fullmatch(self.credential_env):
            issues.append(ValidationIssue("credential_env", "credential", "credential_env must be an environment variable name"))
        if self.remote_execution_policy != "approved_remote_endpoint":
            issues.append(ValidationIssue("remote_execution_policy", "execution", "remote execution must be explicitly approved"))
        if self.data_egress_policy != "approved_remote_endpoint":
            issues.append(ValidationIssue("data_egress_policy", "egress", "remote execution requires approved_remote_endpoint policy"))
        if self.execution_location != "remote":
            issues.append(ValidationIssue("execution_location", "location", "remote endpoint location must be remote"))
        if type(self.timeout_ms) is not int or not 1 <= self.timeout_ms <= 86_400_000:
            issues.append(ValidationIssue("timeout_ms", "range", "timeout_ms must be 1..86400000"))
        if type(self.max_retries) is not int or not 0 <= self.max_retries <= 5:
            issues.append(ValidationIssue("max_retries", "range", "max_retries must be 0..5"))
        if not self.capabilities or not self.roles or not self.modalities or not self.risk_classes:
            issues.append(ValidationIssue("capabilities", "required", "endpoint capabilities, roles, modalities, and risks are required"))
        has_placeholder = any(_is_placeholder(str(getattr(self, name))) for name in (
            "endpoint_url", "endpoint_id", "model_target_id", "qualification_reference", "execution_location",
        ))
        if has_placeholder and not self.disabled:
            issues.append(ValidationIssue("profile", "placeholder", "placeholder endpoint profiles are disabled"))
        try:
            _parse_expiry(self.qualification_expires_at)
        except (TypeError, ValueError):
            issues.append(ValidationIssue("qualification_expires_at", "timestamp", "expiry must be an ISO-8601 timestamp with timezone"))
        return issues

    def qualification_payload(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("qualification_signature", None)
        return payload

    def verify_signature(self, signing_key: bytes) -> bool:
        expected = hmac.new(
            signing_key,
            json.dumps(
                self.qualification_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, self.qualification_signature)

    def is_fresh(self, *, now: datetime | None = None) -> bool:
        try:
            expiry = _parse_expiry(self.qualification_expires_at)
        except (TypeError, ValueError):
            return False
        current = now or datetime.now(timezone.utc)
        return expiry > current.astimezone(timezone.utc)

    def validate_target(self, target: ModelTarget, request: ModelCallRequest, *, now: datetime | None = None) -> None:
        """Apply endpoint and model identity gates before any network request."""
        problems: list[str] = []
        if self.model_target_id != target.target_id:
            problems.append("model target identity mismatch")
        if self.artifact_digest != target.artifact_digest:
            problems.append("artifact digest mismatch")
        if self.tokenizer_digest != target.tokenizer_digest:
            problems.append("tokenizer identity mismatch")
        if self.chat_template_digest != target.chat_template_digest:
            problems.append("chat template identity mismatch")
        if self.runtime_version != target.runtime_version:
            problems.append("runtime compatibility mismatch")
        if self.adapter_id != target.adapter_id or self.adapter_version != target.adapter_version:
            problems.append("adapter identity mismatch")
        if request.required_capability not in self.capabilities or request.required_capability not in target.capabilities:
            problems.append("required capability is not qualified")
        if self.license_id != target.license_id:
            problems.append("license identity mismatch")
        if request.role not in self.roles or request.role not in target.roles:
            problems.append("role is not qualified")
        if request.modality not in self.modalities or request.modality not in target.modalities:
            problems.append("modality is not qualified")
        if request.action_risk not in self.risk_classes or request.action_risk not in target.risk_classes:
            problems.append("risk class is not qualified")
        if request.clearance not in self.allowed_clearances or request.clearance not in target.allowed_clearances:
            problems.append("clearance is not allowed")
        if not self.is_fresh(now=now):
            problems.append("endpoint qualification is stale")
        if problems:
            raise ValueError("; ".join(problems))

    def credential(self) -> str:
        """Read a credential only from the configured environment variable."""
        return os.environ.get(self.credential_env, "")


__all__ = ["RemoteEndpointProfile"]
