"""Install the synthetic refinery demo corpus into the local KB staging area.

Only files listed by ``document_catalog.yaml`` under
``01_knowledge_base_ingestion/`` are copied.  Presenter prompts, evaluator
reference assets, and optional external-source notes never enter the Node's
bulk-ingest root.  The extracted files remain untrusted evidence; this tool
only prepares the operator-approved local input directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


CORPUS_ROOT = "AirBench_Refinery_Demo_Corpus"
INGEST_PREFIX = "01_knowledge_base_ingestion/"
CATALOG_MEMBER = f"{CORPUS_ROOT}/document_catalog.yaml"


class CorpusPreparationError(ValueError):
    """Raised when the corpus cannot be safely admitted."""


def _member_name(name: str) -> str:
    normalized = str(PurePosixPath(name))
    if normalized.startswith("../") or normalized == ".." or "/../" in f"/{normalized}/":
        raise CorpusPreparationError("corpus archive contains path traversal")
    return normalized


def _catalog_records(catalog: dict[str, Any]) -> list[dict[str, str]]:
    records = catalog.get("records")
    if not isinstance(records, list) or not records:
        raise CorpusPreparationError("document catalog has no records")
    result: list[dict[str, str]] = []
    for record in records:
        if not isinstance(record, dict):
            raise CorpusPreparationError("document catalog record is not an object")
        path = record.get("path")
        digest = record.get("sha256")
        if not isinstance(path, str) or not path.startswith(INGEST_PREFIX):
            raise CorpusPreparationError("catalog contains a non-ingestion path")
        if not isinstance(digest, str) or len(digest) != 64:
            raise CorpusPreparationError(f"catalog hash is invalid for {path}")
        result.append({"path": path, "sha256": digest.lower()})
    return result


def prepare_corpus(archive: Path, destination: Path, *, force: bool = False) -> dict[str, Any]:
    """Validate and extract only the catalogued ingestion files."""

    if not archive.is_file():
        raise CorpusPreparationError(f"corpus archive does not exist: {archive}")
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        names = {_member_name(info.filename) for info in bundle.infolist()}
        if CATALOG_MEMBER not in names:
            raise CorpusPreparationError("corpus archive is missing document_catalog.yaml")
        catalog_bytes = bundle.read(CATALOG_MEMBER)
        try:
            catalog = yaml.safe_load(catalog_bytes)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise CorpusPreparationError("document catalog is unreadable") from exc
        if not isinstance(catalog, dict):
            raise CorpusPreparationError("document catalog must be a mapping")
        records = _catalog_records(catalog)
        staged: list[tuple[str, bytes]] = []
        for record in records:
            member = f"{CORPUS_ROOT}/{record['path']}"
            if member not in names:
                raise CorpusPreparationError(f"catalogued file is missing: {record['path']}")
            content = bundle.read(member)
            digest = hashlib.sha256(content).hexdigest()
            if digest != record["sha256"]:
                raise CorpusPreparationError(f"catalog hash mismatch: {record['path']}")
            staged.append((record["path"], content))

    if destination.exists() and any(destination.iterdir()) and not force:
        raise CorpusPreparationError(f"destination is not empty: {destination}; use --force to replace it")
    destination.mkdir(parents=True, exist_ok=True)
    if force:
        for child in destination.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    for relative, content in staged:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (destination / "document_catalog.yaml").write_bytes(catalog_bytes)
    return {
        "archive": str(archive.resolve()),
        "destination": str(destination),
        "file_count": len(staged),
        "catalog_sha256": hashlib.sha256(
            (destination / "document_catalog.yaml").read_bytes()
        ).hexdigest(),
        "excluded_prefixes": [
            "02_query_time_showcase/",
            "03_pid_review_assets/",
            "04_external_source_notes/",
        ],
        "files": [relative for relative, _ in staged],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--destination", type=Path, default=Path(".airbench-corpus"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        report = prepare_corpus(args.archive, args.destination, force=args.force)
    except CorpusPreparationError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
