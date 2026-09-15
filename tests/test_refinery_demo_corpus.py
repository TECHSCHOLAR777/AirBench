from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import yaml

from scripts.prepare_refinery_demo_corpus import CorpusPreparationError, prepare_corpus


ARCHIVE = Path(r"C:\Users\ALG\Downloads\AirBench_Refinery_Demo_Corpus.zip")


def test_demo_corpus_archive_is_catalogued_and_excludes_presenter_assets(tmp_path: Path) -> None:
    report = prepare_corpus(ARCHIVE, tmp_path / "corpus")

    assert report["file_count"] == 21
    assert all(path.startswith("01_knowledge_base_ingestion/") for path in report["files"])
    assert not (tmp_path / "corpus" / "02_query_time_showcase").exists()
    assert yaml.safe_load((tmp_path / "corpus" / "document_catalog.yaml").read_text())[
        "collection_id"
    ] == "airbench-unit4-synthetic-demo"


def test_demo_corpus_rejects_catalog_hash_mismatch(tmp_path: Path) -> None:
    broken = tmp_path / "broken.zip"
    catalog = 'records:\n  - path: 01_knowledge_base_ingestion/file.txt\n    sha256: "' + "0" * 64 + '"\n'
    with zipfile.ZipFile(broken, "w") as bundle:
        bundle.writestr("AirBench_Refinery_Demo_Corpus/document_catalog.yaml", catalog)
        bundle.writestr("AirBench_Refinery_Demo_Corpus/01_knowledge_base_ingestion/file.txt", "data")

    with pytest.raises(CorpusPreparationError, match="catalog hash mismatch"):
        prepare_corpus(broken, tmp_path / "out")
