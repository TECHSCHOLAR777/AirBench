"""Compatibility policy for persisted AirBench contract payloads."""

from .errors import ContractValidationError, ValidationIssue


def ensure_compatible(payload: dict, expected_version: str = "1.0") -> None:
    actual = payload.get("schema_version", expected_version)
    if actual != expected_version:
        raise ContractValidationError("schema", [ValidationIssue("schema_version", "incompatible_version", f"expected {expected_version}, got {actual}")])


POLICY = """# Contract compatibility policy

Contracts use `schema_version` (major.minor) and `compatibility_id`. Patch changes are documentation-only. A minor release may add optional fields and enum values only when consumers fail closed on values they do not understand. Removing or renaming a required field, changing a field type, changing enum meaning, or changing canonical serialization is a major breaking change.

Readers accept the exact supported major version, validate before state mutation, and may apply an explicit named migration from an older version. Unknown fields are rejected by v1 models; forward payloads must be migrated before parsing. Persisted records are replayed from their original version and are never rewritten in place. Rejection is structured as `contract_validation_failed` with paths and stable error codes; secret values are never included.
"""
