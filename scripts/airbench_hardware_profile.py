"""Measure the local host/GPU and fill the signed HardwareProfile JSON.

Replaces the ``PENDING``/``REPLACE_WITH_MEASURED`` placeholders in
``profiles/hardware/<name>.json`` with real measurements from the machine it is
run on (the GPU box).  Values that cannot be measured are preserved.

Usage (run on the model host):
    python3 scripts/airbench_hardware_profile.py --write
    python3 scripts/airbench_hardware_profile.py --profile profiles/hardware/workstation_04.json --write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = REPO_ROOT / "profiles" / "hardware" / "workstation_04.json"
MIB = 1024 * 1024


def _run(*command: str) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _cpu_model() -> str:
    if Path("/proc/cpuinfo").exists():
        for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    if platform.system() == "Windows":
        output = _run("powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name")
        if output:
            return output.splitlines()[0].strip()
    return platform.processor() or "unknown-cpu"


def _ram_bytes() -> int:
    if Path("/proc/meminfo").exists():
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    if platform.system() == "Windows":
        output = _run("powershell", "-NoProfile", "-Command",
                      "[int64](Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
        if output.isdigit():
            return int(output)
    return 0


def _os_name() -> str:
    if Path("/etc/os-release").exists():
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    return platform.platform()


def _gpu() -> dict:
    if not shutil.which("nvidia-smi"):
        return {}
    name = _run("nvidia-smi", "--query-gpu=name", "--format=csv,noheader").splitlines()
    memory = _run("nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits").splitlines()
    driver = _run("nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader").splitlines()
    cuda = _run("nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader").splitlines()
    if not name:
        return {}
    vram_mib = int(memory[0]) if memory and memory[0].isdigit() else 0
    return {
        "gpu_model": name[0].strip(),
        "gpu_count": len(name),
        "vram_bytes": vram_mib * MIB,
        "driver_version": (driver[0] if driver else "").strip(),
        "compute_capability": (cuda[0] if cuda else "").strip(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--write", action="store_true", help="Write measured values into the profile.")
    parser.add_argument("--force", action="store_true", help="Allow overwriting a profile whose GPU model differs.")
    parser.add_argument("--context-tokens", type=int, default=None)
    parser.add_argument("--kv-cache-bytes", type=int, default=4_294_967_296)
    parser.add_argument("--safe-parallel-slots", type=int, default=None)
    parser.add_argument("--scratch-bytes", type=int, default=None)
    parser.add_argument("--network-check-id", default="network-check.workstation-04")
    args = parser.parse_args(argv)

    if not args.profile.exists():
        print(f"ERROR: profile not found: {args.profile}", file=sys.stderr)
        return 1
    profile = json.loads(args.profile.read_text(encoding="utf-8"))

    measured = {
        "cpu_model": _cpu_model(),
        "cpu_cores": os.cpu_count() or 0,
        "ram_bytes": _ram_bytes() or profile.get("ram_bytes", 0),
        "storage_bytes": profile.get("storage_bytes", 0),
        "scratch_bytes": args.scratch_bytes or profile.get("scratch_bytes", 0),
        "kernel": platform.release(),
        "os": _os_name(),
    }
    measured.update(_gpu())

    context_tokens = args.context_tokens or profile.get("model_context_tokens", 8192)
    safe_slots = args.safe_parallel_slots or profile.get("safe_parallel_slots", 1)
    measured["kv_cache_bytes"] = args.kv_cache_bytes

    # Only write fields that are part of the frozen HardwareProfile contract.
    updated = dict(profile)
    updated["cpu_model"] = measured["cpu_model"] or profile.get("cpu_model", "unknown-cpu")
    updated["cpu_cores"] = measured["cpu_cores"] or profile.get("cpu_cores", 1)
    updated["ram_bytes"] = measured["ram_bytes"] or profile.get("ram_bytes", 1)
    updated["storage_bytes"] = measured["storage_bytes"] or profile.get("storage_bytes", 1)
    updated["scratch_bytes"] = measured["scratch_bytes"] or profile.get("scratch_bytes", 1)
    for key in ("gpu_model", "gpu_count", "vram_bytes", "driver_version"):
        if measured.get(key):
            updated[key] = measured[key]
    updated["model_context_tokens"] = context_tokens
    updated["kv_cache_bytes"] = args.kv_cache_bytes
    updated["safe_parallel_slots"] = safe_slots
    updated["egress_policy"] = "deny-all"
    updated["network_check_id"] = args.network_check_id
    updated["sandbox_runtime"] = profile.get("sandbox_runtime", "firejail")
    updated["measurement_hash"] = hashlib.sha256(json.dumps(measured, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    print(json.dumps(measured, indent=2, sort_keys=True))
    print("measurement_hash:", updated["measurement_hash"])

    declared_gpu = str(profile.get("gpu_model", ""))
    measured_gpu = str(measured.get("gpu_model", ""))
    if (args.write and not args.force and declared_gpu and "PENDING" not in declared_gpu
            and measured_gpu and declared_gpu != measured_gpu):
        print(f"ERROR: this machine's GPU ({measured_gpu}) does not match the profile ({declared_gpu}).",
              file=sys.stderr)
        print("Run this on the model host, or pass --force to overwrite.", file=sys.stderr)
        return 2

    if args.write:
        args.profile.write_text(json.dumps(updated, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.profile}")
    else:
        print("Dry run. Re-run with --write to update the profile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
