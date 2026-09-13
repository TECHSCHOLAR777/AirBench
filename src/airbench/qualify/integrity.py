"""Qualification stage 1: check the model itself before running it.

Mirrors the framework's first stage: verify the artifact hash, confirm a safe
format, confirm the license, and confirm the model loads and runs in the
sandbox.  A model that fails this stage is never routed to, no matter how well
it scores on the evaluation set.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SAFE_FORMATS = {".safetensors", ".gguf", ".onnx"}


class IntegrityError(RuntimeError):
    """The integrity check could not be evaluated safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class IntegrityCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ModelIntegrity:
    checks: tuple[IntegrityCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.checks],
        }


def verify_model(
    *,
    artifact_path: str | Path,
    expected_hash: str = "",
    license_id: str = "",
    license_accepted: bool = False,
    sandbox_probe: Callable[[], bool] | None = None,
) -> ModelIntegrity:
    """Check signature/origin, safe format, license, and sandbox load."""
    path = Path(artifact_path)
    checks: list[IntegrityCheck] = []

    checks.append(IntegrityCheck("artifact_present", path.is_file(), f"artifact at {path.name}" if path.is_file() else "artifact file not found"))
    if path.is_file() and expected_hash:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        checks.append(IntegrityCheck(
            "artifact_hash", actual == expected_hash,
            "artifact hash matches the qualified record" if actual == expected_hash else "artifact hash does not match",
        ))
    elif not expected_hash:
        checks.append(IntegrityCheck("artifact_hash", False, "no expected artifact hash was supplied"))

    checks.append(IntegrityCheck(
        "safe_format", path.suffix.lower() in SAFE_FORMATS,
        f"format {path.suffix.lower() or 'unknown'} is {'safe' if path.suffix.lower() in SAFE_FORMATS else 'not allowed'}",
    ))

    checks.append(IntegrityCheck(
        "license", bool(license_id) and license_accepted,
        "license accepted" if license_id and license_accepted else "license id missing or not accepted",
    ))

    if sandbox_probe is None:
        checks.append(IntegrityCheck("sandbox_load", False, "sandbox load probe not configured"))
    else:
        try:
            loaded = bool(sandbox_probe())
        except Exception as exc:  # noqa: BLE001 - probe failure is a failed check, not a crash
            loaded = False
            checks.append(IntegrityCheck("sandbox_load", False, f"sandbox load raised {type(exc).__name__}"))
        else:
            checks.append(IntegrityCheck("sandbox_load", loaded, "model loaded in the sandbox" if loaded else "model did not load in the sandbox"))

    return ModelIntegrity(tuple(checks))


__all__ = ["IntegrityCheck", "IntegrityError", "ModelIntegrity", "SAFE_FORMATS", "verify_model"]
