#!/usr/bin/env python3
"""Audit or explicitly prune duplicate Hugging Face model-cache blobs.

This is a connected-machine provisioning utility, not runtime code.  It never
downloads models and it never touches the canonical runtime model store.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from airbench.model_store import ModelStoreError, audit_model_store, prune_verified_cache, targets_from_roster


def _default_roster() -> Path:
    return Path(__file__).resolve().parents[1] / "models" / "roster" / "v0" / "model_roster.yaml"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "prune"))
    parser.add_argument("--runtime-root", default=os.environ.get("AIRBENCH_MODEL_STORE"), help="canonical runtime model directory")
    parser.add_argument("--cache-root", default=os.environ.get("AIRBENCH_HF_CACHE"), help="Hugging Face hub cache directory")
    parser.add_argument("--roster", type=Path, default=_default_roster())
    parser.add_argument("--target-id", action="append", dest="target_ids", help="roster target to inspect; repeat for multiple targets")
    parser.add_argument(
        "--cache-repository",
        action="append",
        default=[],
        metavar="TARGET_ID=ORG/REPO",
        help="override the on-disk HF cache repository for a staged target; repeat when the artifact was downloaded from a quantizer fork",
    )
    parser.add_argument("--apply", action="store_true", help="delete only proven duplicate cache blobs")
    parser.add_argument(
        "--allow-stale-incomplete",
        action="store_true",
        help="allow pruning verified duplicates when every incomplete cache file is at least 24 hours old",
    )
    parser.add_argument(
        "--prune-stale-incomplete",
        action="store_true",
        help="with --apply, also delete incomplete cache files at least 24 hours old",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit a machine-readable report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.runtime_root or not args.cache_root:
        print("AIRBENCH_MODEL_STORE and AIRBENCH_HF_CACHE or both corresponding flags are required")
        return 2
    if args.command == "prune" and not args.apply:
        print("Refusing to prune without --apply. Run audit first, then repeat with --apply.")
        return 2
    if args.prune_stale_incomplete and not args.allow_stale_incomplete:
        print("Refusing to purge incomplete downloads without --allow-stale-incomplete")
        return 2
    try:
        overrides: dict[str, str] = {}
        for value in args.cache_repository:
            target_id, separator, repository = value.partition("=")
            if not separator or not target_id or not repository:
                raise ModelStoreError("--cache-repository must be TARGET_ID=ORG/REPO")
            if target_id in overrides:
                raise ModelStoreError(f"duplicate cache repository override: {target_id}")
            overrides[target_id] = repository
        targets = targets_from_roster(args.roster, args.target_ids, overrides)
        report = audit_model_store(
            Path(args.runtime_root),
            Path(args.cache_root),
            targets,
            allow_stale_incomplete=args.allow_stale_incomplete,
        )
        removed = prune_verified_cache(
            report,
            apply=args.command == "prune" and args.apply,
            prune_stale_incomplete=args.prune_stale_incomplete,
        )
    except (OSError, ModelStoreError) as exc:
        print(f"model-store operation failed: {exc}")
        return 2
    payload = report.to_dict()
    payload["removed_bytes"] = removed
    if args.as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"canonical runtime store: {report.runtime_root}")
        print(f"HF cache inspected: {report.cache_root}")
        for repository in report.repositories:
            print(
                f"{repository.target_id}: {repository.reason}; "
                f"duplicate={repository.duplicate_gib:.2f} GiB; safe={repository.safe_to_prune}"
            )
        if args.command == "prune":
            print(f"removed proven duplicate bytes: {removed}")
        else:
            print(f"proven duplicate bytes available for explicit pruning: {report.prunable_bytes}")
    return 0 if report.safe_to_prune else 1


if __name__ == "__main__":
    raise SystemExit(main())
