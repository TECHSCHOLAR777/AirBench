"""Model endpoint preflight for the remote-GPU two-lane demo.

Verifies, before the AirBench Node starts, that every roster lane is actually
served through the SSH tunnel with the exact expected model identity:

  1. the signed roster and remote deployment attestation load and verify;
  2. each target's HTTP health endpoint answers;
  3. ``/v1/models`` lists the exact served model name declared by the roster;
  4. the roster pins revision, quantization, adapter identity, and container
     digest for the mapped target (no placeholders);
  5. the target carries qualification certificates for its roles.

Usage:
    python scripts/model_endpoint_preflight.py
    python scripts/model_endpoint_preflight.py --roster models/roster/aimslab/qwen_vllm_roster.yaml \
        --attestation models/attestations/aimslab_qwen_vllm.yaml --signing-key .airbench_signing_key --json

Exit codes: 0 all lanes ready, 1 at least one lane not ready, 2 roster invalid.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from types import SimpleNamespace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from contracts import ModelRegistry, RegistryError, RemoteDeploymentAttestation  # noqa: E402

_PLACEHOLDERS = ("replace_with", "pending", "unqualified", "tbd", "n/a-qat-placeholder")


def _placeholder(value: str) -> bool:
    return value.strip().lower() in _PLACEHOLDERS or value.strip().startswith("REPLACE_WITH")


def _get_ok(url: str, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - roster-declared loopback URL
            return 200 <= response.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _get_json(url: str, timeout: float) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - roster-declared loopback URL
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _probe_lane(item: dict[str, Any], target: Any, timeout: float) -> dict[str, Any]:
    serving = item.get("serving", {}) or {}
    base_url = str(serving.get("developer_endpoint_url", serving.get("demo_endpoint_url", ""))).rstrip("/")
    served_name = str(serving.get("served_model_name", serving.get("demo_served_model_name", "")))
    lane: dict[str, Any] = {
        "target_id": str(item.get("target_id", "")),
        "endpoint_url": base_url,
        "expected_model": served_name,
        "revision": str(item.get("revision", "")),
        "quantization": str((item.get("quantization") or {}).get("format", "")),
        "adapter": f"{serving.get('adapter_id', '')}/{serving.get('adapter_version', '')}",
        "container_digest": str(serving.get("container_digest", "")),
        "reason": "ready",
        "served_models": [],
    }
    if not base_url or not served_name:
        lane["reason"] = "not_ready"
        return lane
    if not _get_ok(base_url + "/health", timeout):
        lane["reason"] = "unhealthy"
        return lane
    models = _get_json(base_url + "/v1/models", timeout)
    if models is None:
        lane["reason"] = "not_ready"
        return lane
    served = sorted({
        entry.get("id") for entry in models.get("data", [])
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    })
    lane["served_models"] = served
    if served_name not in served:
        lane["reason"] = "model_mismatch"
        return lane
    if str(serving.get("adapter_id", "")) != "airbench.vllm":
        lane["reason"] = "adapter_mismatch"
        return lane
    if (not lane["revision"] or _placeholder(lane["revision"])
            or not lane["quantization"] or _placeholder(lane["quantization"])
            or not lane["container_digest"].startswith("sha256:")
            or _placeholder(lane["container_digest"])):
        lane["reason"] = "identity_incomplete"
        return lane
    if target is None or not target.qualification_certificate or not target.role_qualifications:
        lane["reason"] = "qualification_missing"
        return lane
    return lane


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roster", default=str(REPO_ROOT / "models" / "roster" / "aimslab" / "qwen_vllm_roster.yaml"))
    parser.add_argument("--signing-key", default=str(REPO_ROOT / ".airbench_signing_key"))
    parser.add_argument("--attestation", default=None, help="signed remote deployment attestation")
    parser.add_argument("--attestation-signing-key", default=None, help="key for the deployment attestation")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    roster_path = Path(args.roster)
    key_path = Path(args.signing_key)
    default_roster = (REPO_ROOT / "models" / "roster" / "aimslab" / "qwen_vllm_roster.yaml").resolve()
    if args.attestation is None and roster_path.resolve() == default_roster:
        args.attestation = str(REPO_ROOT / "models" / "attestations" / "aimslab_qwen_vllm.yaml")
    if not roster_path.is_file() or not key_path.is_file():
        print(json.dumps({"status": "roster_invalid", "reason": f"missing roster or signing key: {roster_path} / {key_path}"}))
        return 2
    try:
        import yaml  # type: ignore[import-not-found]

        document = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
        registry = ModelRegistry.load_roster_file(
            roster_path, signing_key=key_path.read_bytes(),
            artifact_root=REPO_ROOT, verify_artifacts=False,
        )
    except (RegistryError, OSError, ValueError) as exc:
        print(json.dumps({"status": "roster_invalid", "reason": str(exc)}))
        return 2

    targets = {target.target_id: target for target in registry.targets}
    network_policy = str((document.get("roster") or {}).get("network_policy", ""))
    if network_policy == "remote_approved_ssh_loopback" and not args.attestation:
        print(json.dumps({"status": "attestation_required", "reason": "remote roster requires a signed deployment attestation"}))
        return 2
    if args.attestation:
        attestation_key = Path(args.attestation_signing_key or args.signing_key)
        try:
            attestation = RemoteDeploymentAttestation.load_file(
                Path(args.attestation), signing_key=attestation_key.read_bytes(),
            )
            specs = tuple(
                SimpleNamespace(
                    target_id=str(item.get("target_id", "")),
                    endpoint_id=str((item.get("serving") or {}).get("endpoint_id", "")),
                    base_url=str((item.get("serving") or {}).get("developer_endpoint_url", "")).rstrip("/"),
                    served_model_name=str((item.get("serving") or {}).get("served_model_name", "")),
                )
                for item in document.get("roster", {}).get("targets", [])
                if isinstance(item, dict)
            )
            attestation.verify_bindings(registry, specs)
        except (OSError, ValueError, RegistryError) as exc:
            print(json.dumps({"status": "attestation_invalid", "reason": str(exc)}))
            return 2
    lanes = [
        _probe_lane(item, targets.get(str(item.get("target_id", ""))), args.timeout)
        for item in document.get("roster", {}).get("targets", [])
        if isinstance(item, dict)
    ]
    ready = bool(lanes) and all(lane["reason"] == "ready" for lane in lanes)
    report = {"status": "ready" if ready else "degraded", "lanes": lanes}

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for lane in lanes:
            mark = "OK " if lane["reason"] == "ready" else "FAIL"
            print(f"[{mark}] {lane['target_id']} at {lane['endpoint_url']}: {lane['reason']}")
            if lane["reason"] != "ready":
                print(f"       expected model: {lane['expected_model']!r}, served: {lane['served_models']}")
            print(f"       revision={lane['revision']} quantization={lane['quantization']} "
                  f"adapter={lane['adapter']} container={lane['container_digest'][:19]}...")
        print(f"Model endpoint preflight: {report['status']}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
