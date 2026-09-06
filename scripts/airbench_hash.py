"""airbench_hash.py — M5.1/M5.2 Artifact Hashing Tool

Computes SHA-256 digests for all model artifacts in the airbench-models
directory, producing the exact values needed to fill:
  - models/roster/v0/model_roster.yaml
  - qualifications/model_qualification_matrix.yaml
  - benchmarks/model_hardware_results.yaml
  - benchmarks/quantization_matrix.yaml
  - benchmarks/backend_compatibility_matrix.yaml

No network access. No side effects. Pure read-only hashing.
Results are printed to stdout and also written to airbench_hashes_output.yaml.

Usage:
    python airbench_hash.py

Architecture note: Follows AirBench invariant — files are parsed only by the
File Intake Layer and are always untrusted data. This script is the intake
layer for the offline model bundle.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Configuration — which files to hash for each model
# ──────────────────────────────────────────────────────────────────────────────
BUNDLE_ROOT = Path(__file__).parent / "airbench-models"

# Each entry: (model_dir, artifact_files_to_hash, tokenizer_file, chat_template_file)
MODEL_TARGETS = [
    {
        "target_id": "gemma4-31b-it-q4",
        "dir": "gemma4-31b-it-q4",
        # Primary artifact = the main gguf weight file
        "artifact_files": ["gemma-4-31B_q4_0-it.gguf"],
        "tokenizer_file": None,  # gguf bundles tokenizer internally
        "chat_template_file": None,
        "mmproj_file": "gemma-4-31B-it-mmproj.gguf",
    },
    {
        "target_id": "gemma4-26b-a4b-4bit",
        "dir": "gemma4-26b-a4b-4bit",
        "artifact_files": ["gemma-4-26B_q4_0-it.gguf"],
        "tokenizer_file": None,
        "chat_template_file": None,
        "mmproj_file": "gemma-4-26B-it-mmproj.gguf",
    },
    {
        "target_id": "qwen2.5-vl-7b-4bit",
        "dir": "qwen2.5-vl-7b-awq",
        # Multi-shard safetensors — hash the index then each shard
        "artifact_files": [
            "model-00001-of-00002.safetensors",
            "model-00002-of-00002.safetensors",
        ],
        "tokenizer_file": "tokenizer.json",
        "chat_template_file": "tokenizer_config.json",
        "mmproj_file": None,
    },
    {
        "target_id": "qwen3-coder-30b-a3b-4bit",
        "dir": "qwen3-coder-30b-a3b-awq",
        "artifact_files": [
            "model-00001-of-00006.safetensors",
            "model-00002-of-00006.safetensors",
            "model-00003-of-00006.safetensors",
            "model-00004-of-00006.safetensors",
            "model-00005-of-00006.safetensors",
            "model-00006-of-00006.safetensors",
        ],
        "tokenizer_file": "tokenizer.json",
        "chat_template_file": "tokenizer_config.json",
        "mmproj_file": None,
    },
    {
        "target_id": "bge-m3",
        "dir": "bge-m3",
        "artifact_files": ["pytorch_model.bin"],
        "tokenizer_file": "tokenizer.json",
        "chat_template_file": "tokenizer_config.json",
        "mmproj_file": None,
    },
    {
        "target_id": "bge-reranker-v2-m3",
        "dir": "bge-reranker-v2-m3",
        "artifact_files": ["model.safetensors"],
        "tokenizer_file": "tokenizer.json",
        "chat_template_file": "tokenizer_config.json",
        "mmproj_file": None,
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Hashing helpers
# ──────────────────────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    """Stream-hash a file with SHA-256. Returns lowercase hex digest."""
    h = hashlib.sha256()
    chunk = 16 * 1024 * 1024  # 16 MB chunks
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def sha256_multi(paths: list[Path]) -> str:
    """Hash multiple files sequentially in order → single combined digest.

    This produces a deterministic 'artifact_digest' for multi-shard models.
    Convention: hash all shards in sorted filename order, feed into one SHA-256.
    """
    h = hashlib.sha256()
    chunk = 16 * 1024 * 1024
    for p in sorted(paths, key=lambda x: x.name):
        with open(p, "rb") as f:
            while True:
                block = f.read(chunk)
                if not block:
                    break
                h.update(block)
    return h.hexdigest()


def file_size_bytes(path: Path) -> int:
    return path.stat().st_size


# ──────────────────────────────────────────────────────────────────────────────
# Main hashing loop
# ──────────────────────────────────────────────────────────────────────────────

def hash_target(spec: dict) -> dict:
    model_dir = BUNDLE_ROOT / spec["dir"]
    result: dict = {
        "target_id": spec["target_id"],
        "model_dir": str(model_dir),
        "hashes": {},
        "sizes_bytes": {},
        "artifact_files": list(spec["artifact_files"]),
        "errors": [],
    }

    # Hash artifact files
    artifact_paths = [model_dir / f for f in spec["artifact_files"]]
    missing = [p for p in artifact_paths if not p.exists()]
    if missing:
        result["errors"].extend([f"MISSING: {p}" for p in missing])
    else:
        present = [p for p in artifact_paths if p.exists()]
        if len(present) == 1:
            digest = sha256_file(present[0])
            result["hashes"]["artifact_digest"] = digest
            result["hashes"]["local_storage_hash"] = digest  # same for single-file
            result["sizes_bytes"]["artifact"] = file_size_bytes(present[0])
        else:
            # Multi-shard: combined digest
            digest = sha256_multi(present)
            result["hashes"]["artifact_digest"] = digest
            result["hashes"]["local_storage_hash"] = digest
            total_size = sum(file_size_bytes(p) for p in present)
            result["sizes_bytes"]["artifact_total"] = total_size
            # Also hash each shard individually for traceability
            for p in sorted(present, key=lambda x: x.name):
                result["hashes"][f"shard_{p.name}"] = sha256_file(p)
                result["sizes_bytes"][f"shard_{p.name}"] = file_size_bytes(p)

    # Hash tokenizer
    if spec.get("tokenizer_file"):
        tok_path = model_dir / spec["tokenizer_file"]
        if tok_path.exists():
            result["hashes"]["tokenizer_digest"] = sha256_file(tok_path)
            result["sizes_bytes"]["tokenizer"] = file_size_bytes(tok_path)
        else:
            result["errors"].append(f"MISSING tokenizer: {tok_path}")

    # Hash chat template / tokenizer_config
    if spec.get("chat_template_file"):
        ct_path = model_dir / spec["chat_template_file"]
        if ct_path.exists():
            result["hashes"]["chat_template_digest"] = sha256_file(ct_path)
            result["sizes_bytes"]["chat_template"] = file_size_bytes(ct_path)
        else:
            result["errors"].append(f"MISSING chat_template: {ct_path}")

    # Hash mmproj (vision projection layer)
    if spec.get("mmproj_file"):
        mm_path = model_dir / spec["mmproj_file"]
        if mm_path.exists():
            result["hashes"]["mmproj_digest"] = sha256_file(mm_path)
            result["sizes_bytes"]["mmproj"] = file_size_bytes(mm_path)
        else:
            result["errors"].append(f"MISSING mmproj: {mm_path}")

    return result


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    print(f"\n{'='*70}")
    print(f"AirBench M5.1/M5.2 Artifact Hashing Tool")
    print(f"Run at: {now}")
    print(f"Bundle root: {BUNDLE_ROOT.resolve()}")
    print(f"{'='*70}\n")

    if not BUNDLE_ROOT.exists():
        print(f"ERROR: Bundle root does not exist: {BUNDLE_ROOT}", file=sys.stderr)
        sys.exit(1)

    all_results = []
    for spec in MODEL_TARGETS:
        print(f"Hashing: {spec['target_id']} ({spec['dir']}) ...")
        sys.stdout.flush()
        result = hash_target(spec)
        all_results.append(result)

        if result["errors"]:
            print(f"  ERRORS:")
            for e in result["errors"]:
                print(f"    {e}")
        else:
            for k, v in result["hashes"].items():
                print(f"  {k}: {v}")
            for k, v in result["sizes_bytes"].items():
                print(f"  size_{k}: {v:,} bytes")
        print()

    # Write YAML output
    out = Path(__file__).parent / "airbench_hashes_output.yaml"
    lines = [
        f"# AirBench M5.1/M5.2 measured artifact hashes",
        f"# Generated: {now}",
        f"# Bundle root: {BUNDLE_ROOT.resolve()}",
        f"# DO NOT COMMIT THIS FILE — copy values into model_roster.yaml",
        f"",
        f"hashes:",
    ]
    for r in all_results:
        lines.append(f"  - target_id: {r['target_id']}")
        lines.append(f"    model_dir: \"{r['model_dir']}\"")
        if r["errors"]:
            lines.append(f"    errors:")
            for e in r["errors"]:
                lines.append(f"      - \"{e}\"")
        else:
            for k, v in r["hashes"].items():
                lines.append(f"    {k}: \"{v}\"")
            for k, v in r["sizes_bytes"].items():
                lines.append(f"    size_{k}: {v}")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults written to: {out}")
    print(f"{'='*70}")

    # Exit non-zero if any target had errors
    errors_total = sum(len(r["errors"]) for r in all_results)
    if errors_total:
        print(f"\n{errors_total} error(s) — review output above", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
