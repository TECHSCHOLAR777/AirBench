"""Typed configuration for a local model-serving endpoint.

The binding identifies a deployment separately from the qualified model target.
It is intentionally limited to loopback HTTP because local serving must not
turn this contract into an unrestricted remote transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ..errors import ContractValidationError, ValidationIssue
from ..models import Contract


@dataclass(frozen=True)
class LocalEndpointBinding(Contract):
    """Transport identity for one local serving process and one target."""

    endpoint_id: str
    target_id: str
    base_url: str
    served_model_name: str
    adapter_id: str
    adapter_version: str
    execution_location: str = "local"

    def __post_init__(self) -> None:
        # This contract is also constructed directly by the Node wiring.  Do
        # not rely on callers remembering to use ``from_dict`` for a security
        # boundary: credential-bearing or remote endpoints must fail closed at
        # construction time as well.
        issues = self._validate({})
        if issues:
            raise ContractValidationError(type(self).__name__, issues)

    def _validate(self, hints: dict[str, Any]) -> list[ValidationIssue]:
        issues = super()._validate(hints)
        for name in ("endpoint_id", "target_id", "base_url", "served_model_name", "adapter_id", "adapter_version"):
            if not getattr(self, name).strip():
                issues.append(ValidationIssue(name, "required", f"{name} is required"))
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            issues.append(ValidationIssue("base_url", "local", "local endpoints must use loopback HTTP"))
        if parsed.username or parsed.password:
            issues.append(ValidationIssue("base_url", "secret", "credentials must not appear in endpoint URLs"))
        if self.execution_location != "local":
            issues.append(ValidationIssue("execution_location", "location", "local endpoint location must be local"))
        return issues


__all__ = ["LocalEndpointBinding"]
