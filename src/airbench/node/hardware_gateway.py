"""Load a signed hardware profile and project it for the Node settings surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from contracts import HardwareProfile


class HardwareProfileError(RuntimeError):
    """A hardware profile could not be loaded."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def load_hardware_profile(path: str | Path) -> HardwareProfile:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise HardwareProfileError("profile_unreadable", "the hardware profile could not be read") from exc
    try:
        payload = yaml.safe_load(text) if source.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
    except (yaml.YAMLError, ValueError) as exc:
        raise HardwareProfileError("profile_invalid", "the hardware profile is not valid YAML or JSON") from exc
    if not isinstance(payload, dict):
        raise HardwareProfileError("profile_invalid", "the hardware profile must be an object")
    try:
        return HardwareProfile.from_dict(payload)
    except Exception as exc:  # contract validation
        raise HardwareProfileError("profile_invalid", "the hardware profile failed contract validation") from exc


def hardware_status(profile: HardwareProfile) -> dict[str, Any]:
    """Project a hardware profile for the Node settings card."""
    return {
        "profile_id": profile.profile_id,
        "gpu_model": profile.gpu_model,
        "gpu_count": profile.gpu_count,
        "vram_bytes": profile.vram_bytes,
        "vram_gb": round(profile.vram_bytes / (1024 ** 3), 1),
        "cpu_model": profile.cpu_model,
        "cpu_cores": profile.cpu_cores,
        "ram_bytes": profile.ram_bytes,
        "ram_gb": round(profile.ram_bytes / (1024 ** 3), 1),
        "safe_parallel_slots": profile.safe_parallel_slots,
        "supported_execution_modes": list(profile.supported_execution_modes),
        "egress_policy": profile.egress_policy,
        "sandbox_runtime": profile.sandbox_runtime,
    }


__all__ = ["HardwareProfileError", "hardware_status", "load_hardware_profile"]
