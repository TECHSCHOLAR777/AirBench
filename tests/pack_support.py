"""Test helpers for loading the refinery domain pack.

The committed pack is signed with a deployment key that is not (and must not be)
in the repository.  Tests therefore materialize their own copy and either strip
the signature (to exercise the unsigned path) or re-sign it with a fixed test
key (to exercise verification), so no test ever depends on a real signing key.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REFINERY_PACK = REPO_ROOT / "packs" / "refinery_psu_v0"
TEST_PACK_KEY = b"p" * 32


def materialize_pack(destination: str | Path | None = None, *, signed: bool) -> Path:
    root = Path(destination) if destination is not None else Path(tempfile.mkdtemp(prefix="airbench-pack-"))
    dest = root / "refinery_psu_v0"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(REFINERY_PACK, dest)
    manifest_path = dest / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if signed:
        from airbench.node.pack_loader import compute_pack_signature

        manifest["signature"] = compute_pack_signature(dest, TEST_PACK_KEY)
        manifest["signing_status"] = "signed"
    else:
        manifest["signature"] = None
        manifest["signing_status"] = "unsigned"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8")
    return dest


def load_unsigned_pack(destination: str | Path | None = None):
    from airbench.node.pack_loader import PackLoader

    return PackLoader(allow_unsigned=True).load(materialize_pack(destination, signed=False))


def load_signed_pack(destination: str | Path | None = None):
    from airbench.node.pack_loader import PackLoader

    return PackLoader(signing_key=TEST_PACK_KEY).load(materialize_pack(destination, signed=True))
