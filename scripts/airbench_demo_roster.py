"""Build the signed two-endpoint Gemma demo roster.

The full reference roster contains several still-placeholder targets that
cannot be normalized or verified yet.  For the controlled two-endpoint demo we
only need the E2B and 12B candidates, so this tool:

  1. extracts those two targets from the main roster;
  2. replaces still-``PENDING`` role records with clearly-labelled *candidate*
     records (a deterministic integrity digest, not an evaluation result);
  3. refuses to continue if any real artifact/tokenizer/template digest is
     still ``PENDING`` — run scripts/airbench_hash.py first;
  4. signs each target and the manifest with the local signing key.

The output is a small roster the Node can load with AIRBENCH_MODEL_ROSTER_PATH.
Candidate records unblock a controlled demo only; they are not qualification.
No network access.

Usage:
    python scripts/airbench_demo_roster.py
    python scripts/airbench_demo_roster.py --no-sign
    python scripts/airbench_demo_roster.py --key .airbench_signing_key
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

from contracts.model.model_registry import _target_from_roster  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "models" / "roster" / "v0" / "model_roster.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "models" / "roster" / "demo" / "two_endpoint_roster.yaml"
DEFAULT_KEY = REPO_ROOT / ".airbench_signing_key"
DEMO_TARGET_IDS = ("airbench-gemma-4-e2b", "airbench-gemma-4-12b")
RETRIEVAL_TARGET_IDS = ("bge-m3", "bge-reranker-v2-m3")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _clear_custom_container_digest(target: dict) -> None:
    """A non-containerized (local Python) retrieval service has no image digest."""
    serving = target.get("serving") or {}
    digest = str(serving.get("container_digest", ""))
    if str(serving.get("runtime", "")) == "custom" and digest.startswith("PENDING:"):
        serving["container_digest"] = ""
        target["serving"] = serving
_REQUIRED_DIGEST_PATHS = ("artifact_hash", "local_storage_hash", "tokenizer.hash", "chat_template.hash")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _candidate_qualification(target: dict) -> None:
    for role in target.get("qualified_roles", []) or []:
        certificate = str(role.get("certificate_id", ""))
        if certificate.startswith("PENDING:") or not certificate.strip():
            certificate = f"candidate.{target.get('target_id')}.{role.get('role', 'role')}"
            role["certificate_id"] = certificate
        qualification_hash = str(role.get("qualification_hash", ""))
        if not _HEX64.fullmatch(qualification_hash):
            role["qualification_hash"] = hashlib.sha256(_canonical(
                [target.get("target_id"), role.get("role", ""), certificate]
            )).hexdigest()


def _pending_digests(target: dict) -> list[str]:
    pending = []
    if not _HEX64.fullmatch(str(target.get("artifact_hash", ""))):
        pending.append("artifact_hash")
    if not _HEX64.fullmatch(str(target.get("local_storage_hash", ""))):
        pending.append("local_storage_hash")
    for parent, key in (("tokenizer", "hash"), ("chat_template", "hash")):
        value = str((target.get(parent) or {}).get(key, ""))
        # "none"/"bundled" are resolved by the loader; treat only PENDING as blocking.
        if value.startswith("PENDING:"):
            pending.append(f"{parent}.{key}")
    return pending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--no-sign", action="store_true", help="Write the roster without signatures.")
    parser.add_argument("--include-retrieval", action="store_true",
                        help="Also include the local BGE embedding and reranker targets.")
    args = parser.parse_args(argv)

    wanted = list(DEMO_TARGET_IDS) + (list(RETRIEVAL_TARGET_IDS) if args.include_retrieval else [])
    if not args.source.exists():
        print(f"ERROR: source roster not found: {args.source}", file=sys.stderr)
        return 1
    document = yaml.safe_load(args.source.read_text(encoding="utf-8"))
    roster = document.get("roster", {}) if isinstance(document, dict) else {}
    targets = [item for item in roster.get("targets", []) if item.get("target_id") in wanted]
    missing = [tid for tid in wanted if tid not in {item.get("target_id") for item in targets}]
    if missing:
        print(f"ERROR: demo targets not found in source roster: {missing}", file=sys.stderr)
        return 1

    unresolved: dict[str, list[str]] = {}
    for target in targets:
        _clear_custom_container_digest(target)
        pending = _pending_digests(target)
        if pending:
            unresolved[str(target.get("target_id"))] = pending
        _candidate_qualification(target)

    if unresolved:
        print("ERROR: real hashes are still PENDING for:", file=sys.stderr)
        for target_id, fields in unresolved.items():
            print(f"  {target_id}: {', '.join(fields)}", file=sys.stderr)
        print("Run: AIRBENCH_MODEL_STORE=<store> python scripts/airbench_hash.py "
              "--target airbench-gemma-4-e2b --target airbench-gemma-4-12b", file=sys.stderr)
        return 1

    demo = {
        "roster": {
            "roster_id": "airbench-two-endpoint-demo",
            "schema_version": "1.0",
            "network_policy": "air_loopback_no_egress",
            "targets": targets,
        },
        "registry_id": "airbench-two-endpoint-demo",
        "manifest_version": "1.0",
        "valid_until": document.get("valid_until", "2030-01-01T00:00:00Z"),
    }

    if not args.no_sign:
        if not args.key.exists() or len(args.key.read_bytes()) != 32:
            print(f"ERROR: a 32-byte signing key is required at {args.key}", file=sys.stderr)
            return 1
        key = args.key.read_bytes()
        for target in targets:
            normalized = _target_from_roster(target)
            target["qualification_signature"] = hmac.new(key, _canonical(normalized.qualification_payload()), hashlib.sha256).hexdigest()
        # Sign the whole document except the manifest signature, matching the registry.
        demo["signature"] = hmac.new(
            key, _canonical({k: v for k, v in demo.items() if k != "signature"}), hashlib.sha256,
        ).hexdigest()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(demo, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {len(targets)} demo target(s) to {args.output}")
    if args.no_sign:
        print("Not signed. Sign with: python scripts/airbench_sign.py --roster " + str(args.output))
    else:
        print("Signed target qualification records and manifest signature.")
    print("These are DEMO CANDIDATE records, not qualification. Complete the evaluation before production use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
