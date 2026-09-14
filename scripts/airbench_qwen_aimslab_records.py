"""Create the signed Qwen roster and remote deployment attestation.

The values in this file are copied from ``AIMSLAB_VLLM_ENDPOINT_HANDOFF.md``.
It does not download weights or contact the inference host.  The attestation
is the signed record that lets a developer Node verify remote artifact
identity without pretending those bytes are in its local model store.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contracts.model.model_registry import _target_from_roster

KEY_DEFAULT = ROOT / ".airbench_signing_key"
ROSTER_DEFAULT = ROOT / "models" / "roster" / "aimslab" / "qwen_vllm_roster.yaml"
ATTESTATION_DEFAULT = ROOT / "models" / "attestations" / "aimslab_qwen_vllm.yaml"
CONTAINER_DIGEST = "sha256:f8fe15a8039343336945db10494eaad80ef941fe2b2a5fa6649fa38636051a65"
ATTESTATION_EXPIRY = "2026-10-15T00:00:00Z"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _manifest_digest(files: list[dict[str, str]]) -> str:
    return hashlib.sha256(_canonical(files)).hexdigest()


def _descriptor(component: str, source: str, artifact_digest: str) -> str:
    return hashlib.sha256(_canonical({"component": component, "source": [source, artifact_digest]})).hexdigest()


def _target_specs() -> list[dict[str, Any]]:
    vl_files = [
        {"path": "model-00001-of-00002.safetensors", "sha256": "4f75e3de726546ee43620d1227d3596cd3ba0fdd19f11faeea71de578d2d1052"},
        {"path": "model-00002-of-00002.safetensors", "sha256": "dae4128bbfd2b8d489e838048edc0bbe6e31f269d9b96fa3effe11cc534b8f0c"},
    ]
    qwen3_files = [
        {"path": "model-00001-of-00002.safetensors", "sha256": "6e112429856bc65e3837a9f38d6f6b71ffdda832cb46299a12f4fa8f6352516e"},
        {"path": "model-00002-of-00002.safetensors", "sha256": "20c2d6366ab85c90786ccdd829cd2b9e7d30ef3b2ebbb998280e7e4014b542ff"},
    ]
    vl_digest = _manifest_digest(vl_files)
    qwen3_digest = _manifest_digest(qwen3_files)
    common = {
        "artifact_digest_scheme": "sha256:file-manifest-v1",
        "quantization": {"format": "int4_awq", "method": "AWQ"},
        "serving": {
            "runtime": "vllm", "runtime_version": "0.28.0", "adapter_id": "airbench.vllm",
            "adapter_version": "0.5", "container_digest": CONTAINER_DIGEST,
        },
        "limits": {"context_tokens": 4096, "max_output_tokens": 4096, "max_concurrency": 2, "max_batch_size": 2},
        "allowed_clearances": ["internal", "restricted"],
        "pack_refs": ["refinery-psu-v0"],
        "hardware_profile_refs": ["aimslab-titan-rtx-24gb"],
        "risk_classes": ["inspection_review", "low_risk"],
        "license": "apache-2.0-or-upstream-model-license",
        "streaming": True, "cancellation": True, "qualification_status": "candidate",
        "source_evidence": "AIMSLAB_VLLM_ENDPOINT_HANDOFF.md",
        "qualification_expires_at": ATTESTATION_EXPIRY,
        "repository_host": "aims-dtu-lab",
    }
    vl = json.loads(json.dumps(common))
    vl.update({
        "target_id": "airbench-qwen25-vl-7b", "model_family": "qwen2.5-vl", "display_name": "Qwen2.5-VL 7B Instruct AWQ",
        "repository": "Qwen/Qwen2.5-VL-7B-Instruct-AWQ", "revision": "536a35794df8831aa814970ee8f89eff577e771f8",
        "artifact_hash": vl_digest, "artifact_path": "qwen2.5-vl-7b-instruct-awq", "artifact_files": [item["path"] for item in vl_files],
        "artifact_hashes": vl_files, "local_storage_hash": vl_digest,
        "tokenizer": {"hash": "5eee858c5123a4279c3e1f7b81247343f356ac767940b2692a928ad929543214", "path": "tokenizer.json"},
        "chat_template": {"template_id": "qwen2.5-vl-chat-template@536a3579", "hash": "bundled"},
        "image_processor": {"id": "qwen2.5-vl-image-processor@536a3579", "hash": "bundled", "min_pixels": 200704, "max_pixels": 1003520},
        "qualified_roles": [{"role": "vision_worker", "certificate_id": "candidate.airbench-qwen25-vl-7b.vision_worker", "qualification_hash": ""}],
        "capabilities": ["vision", "scanned_page_extraction"], "modalities": ["text", "image"],
        "tool_call_parser": "none", "structured_output_modes": ["json_object", "json_schema"],
        "limits": {**common["limits"], "image_tokens": 1280, "max_images": 1, "max_videos": 0},
        "serving": {**common["serving"], "endpoint_id": "endpoint-vision", "developer_endpoint_url": "http://127.0.0.1:18001", "remote_loopback_port": 8001, "served_model_name": "airbench-qwen25-vl-7b"},
    })
    qwen3 = json.loads(json.dumps(common))
    qwen3.update({
        "target_id": "airbench-qwen3-8b", "model_family": "qwen3", "display_name": "Qwen3 8B AWQ",
        "repository": "Qwen/Qwen3-8B-AWQ", "revision": "4da05a8edb55c6046cce958586c33b61da07bb79",
        "artifact_hash": qwen3_digest, "artifact_path": "qwen3-8b-awq", "artifact_files": [item["path"] for item in qwen3_files],
        "artifact_hashes": qwen3_files, "local_storage_hash": qwen3_digest,
        "tokenizer": {"hash": "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4", "path": "tokenizer.json"},
        "chat_template": {"template_id": "qwen3-chat-template@4da05a8e", "hash": "bundled"},
        "image_processor": {"id": "none", "hash": "none"},
        "qualified_roles": [
            {"role": "reasoning", "certificate_id": "candidate.airbench-qwen3-8b.reasoning", "qualification_hash": ""},
            {"role": "lead_worker", "certificate_id": "candidate.airbench-qwen3-8b.lead_worker", "qualification_hash": ""},
        ],
        "capabilities": ["reasoning", "lead_planning"], "modalities": ["text"],
        "tool_call_parser": "hermes", "structured_output_modes": ["json_object", "json_schema"],
        "limits": {**common["limits"], "image_tokens": 0, "max_images": 0, "max_videos": 0},
        "request_options": {"chat_template_kwargs": {"enable_thinking": False}},
        "serving": {**common["serving"], "endpoint_id": "endpoint-reasoning", "developer_endpoint_url": "http://127.0.0.1:18002", "remote_loopback_port": 8002, "served_model_name": "airbench-qwen3-8b"},
    })
    for target in (vl, qwen3):
        target["role_qualification_hashes"] = []
        for role in target["qualified_roles"]:
            role["qualification_hash"] = hashlib.sha256(_canonical({"target_id": target["target_id"], "role": role["role"], "status": "candidate", "evidence": target["source_evidence"]})).hexdigest()
    return [vl, qwen3]


def write_records(key: bytes, roster_path: Path, attestation_path: Path) -> None:
    targets = _target_specs()
    for item in targets:
        item["qualification_signature"] = "0" * 64
        normalized = _target_from_roster(item)
        item["qualification_signature"] = hmac.new(key, _canonical(normalized.qualification_payload()), hashlib.sha256).hexdigest()
    roster: dict[str, Any] = {
        "roster": {"roster_id": "airbench-aimslab-qwen-vllm", "schema_version": "1.0", "network_policy": "remote_approved_ssh_loopback", "targets": targets},
        "registry_id": "airbench-aimslab-qwen-vllm", "manifest_version": "1.0", "valid_until": ATTESTATION_EXPIRY,
    }
    roster["signature"] = hmac.new(key, _canonical(roster), hashlib.sha256).hexdigest()
    roster_path.parent.mkdir(parents=True, exist_ok=True)
    roster_path.write_text(yaml.safe_dump(roster, sort_keys=False), encoding="utf-8")

    attested_targets = []
    for item in targets:
        normalized = _target_from_roster(item)
        attested_targets.append({
            "target_id": normalized.target_id, "repository": normalized.repository, "revision": normalized.revision,
            "artifact_digest": normalized.artifact_digest, "artifact_digest_scheme": normalized.artifact_digest_scheme,
            "artifact_hashes": item["artifact_hashes"], "tokenizer_digest": normalized.tokenizer_digest,
            "chat_template_digest": normalized.chat_template_digest, "processor_digest": normalized.processor_digest,
            "runtime_version": normalized.runtime_version, "container_digest": normalized.container_digest,
            "adapter_id": normalized.adapter_id, "adapter_version": normalized.adapter_version,
            "endpoint_id": item["serving"]["endpoint_id"], "developer_endpoint_url": item["serving"]["developer_endpoint_url"],
            "served_model_name": item["serving"]["served_model_name"], "remote_loopback_port": item["serving"]["remote_loopback_port"],
            "max_images": normalized.max_images, "max_videos": normalized.max_videos,
            "processor_min_pixels": normalized.processor_min_pixels, "processor_max_pixels": normalized.processor_max_pixels,
        })
    attestation: dict[str, Any] = {
        "attestation_id": "attestation.aimslab.qwen-vllm.2026-09-15", "schema_version": "1.0", "host_id": "aimslab",
        "execution_location": "remote", "transport_policy": "ssh_loopback_tunnel", "endpoint_policy": "developer_loopback_only",
        "runtime_image": "vllm/vllm-openai:v0.28.0-ubuntu2404", "runtime_version": "vllm-0.28.0",
        "container_digest": CONTAINER_DIGEST, "gpu_profile": "NVIDIA TITAN RTX; 24 GiB; compute capability 7.5",
        "precision": "fp16; AWQ", "issued_at": "2026-09-15T00:00:00Z", "valid_until": ATTESTATION_EXPIRY,
        "targets": attested_targets,
    }
    attestation["signature"] = hmac.new(key, _canonical(attestation), hashlib.sha256).hexdigest()
    attestation_path.parent.mkdir(parents=True, exist_ok=True)
    attestation_path.write_text(yaml.safe_dump(attestation, sort_keys=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", type=Path, default=KEY_DEFAULT)
    parser.add_argument("--roster", type=Path, default=ROSTER_DEFAULT)
    parser.add_argument("--attestation", type=Path, default=ATTESTATION_DEFAULT)
    args = parser.parse_args()
    key = args.key.read_bytes()
    if len(key) != 32:
        raise SystemExit("a 32-byte signing key is required")
    write_records(key, args.roster, args.attestation)
    print(f"wrote signed Qwen roster: {args.roster}")
    print(f"wrote signed remote deployment attestation: {args.attestation}")
    print("targets remain candidate-only until role qualification is completed and explicitly enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
