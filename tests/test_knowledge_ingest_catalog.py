from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import yaml

from airbench.intake.layer import FileIntakeLayer
from airbench.knowledge.retrieval import DeterministicEmbeddingProvider, LocalIndexer, LocalVectorIndex
from airbench.node.knowledge_gateway import LocalNodeKnowledgeService
from contracts import Clearance, EventLedger, Orchestrator


def _service(root: Path, catalog: Path, ledger: EventLedger, index: LocalVectorIndex) -> LocalNodeKnowledgeService:
    embeddings = DeterministicEmbeddingProvider()
    Orchestrator(ledger).create_task(
        principal_id="operator", clearance=Clearance.internal,
        request="Bulk knowledge ingestion", domain_pack_ref="pack.test",
        risk_class="low", autonomy_ceiling="system", task_id="task.knowledge.ingest",
    )
    return LocalNodeKnowledgeService(
        layer=FileIntakeLayer(ledger),
        indexer=LocalIndexer(index, embeddings, ledger=ledger),
        ingest_root=root / "01_knowledge_base_ingestion",
        catalog_path=catalog,
        task_id="task.knowledge.ingest",
        clearance_context=Clearance.internal,
        ledger=ledger,
    )


def _catalog(catalog: Path, relative_path: str, content: bytes) -> None:
    catalog.write_text(
        yaml.safe_dump(
            {
                "collection_id": "test-corpus",
                "clearance": "internal-technical",
                "trust_class": "synthetic_demonstration_data",
                "taint": "untrusted_evidence",
                "records": [{
                    "path": f"01_knowledge_base_ingestion/{relative_path}",
                    "document_profile": "maintenance_manual",
                    "sha256": sha256(content).hexdigest(),
                    "revision": "SD-01",
                }],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_catalog_ingest_uses_stable_relative_source_and_ledger_events(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    ingest = root / "01_knowledge_base_ingestion" / "nested"
    ingest.mkdir(parents=True)
    content = b"seal leakage requires isolation and a work permit"
    (ingest / "sop.txt").write_bytes(content)
    catalog = root / "document_catalog.yaml"
    _catalog(catalog, "nested/sop.txt", content)
    ledger = EventLedger()
    index = LocalVectorIndex()

    result = _service(root, catalog, ledger, index).ingest_directory(path=".")

    assert result["status"] == "completed"
    assert result["file_count"] == 1
    assert result["chunk_count"] == 1
    assert result["files"][0]["source_ref"] == "ingest:nested/sop.txt"
    assert result["files"][0]["transaction_id"]
    event_types = [event.event_type for event in ledger.events]
    assert "knowledge.ingest.started" in event_types
    assert "knowledge.ingest.file_completed" in event_types
    assert "knowledge.ingest.completed" in event_types


def test_catalog_hash_mismatch_is_reported_and_never_indexed(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    ingest = root / "01_knowledge_base_ingestion"
    ingest.mkdir(parents=True)
    (ingest / "sop.txt").write_text("changed content", encoding="utf-8")
    catalog = root / "document_catalog.yaml"
    _catalog(catalog, "sop.txt", b"different content")
    ledger = EventLedger()
    index = LocalVectorIndex()

    result = _service(root, catalog, ledger, index).ingest_directory(path=".")

    assert result["status"] == "failed"
    assert result["file_count"] == 0
    assert result["chunk_count"] == 0
    assert result["failures"][0]["code"] == "ingest_catalog_hash_mismatch"
    assert not index.chunks


def test_repeating_catalog_ingest_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    ingest = root / "01_knowledge_base_ingestion"
    ingest.mkdir(parents=True)
    content = b"maintenance isolation procedure"
    (ingest / "sop.txt").write_bytes(content)
    catalog = root / "document_catalog.yaml"
    _catalog(catalog, "sop.txt", content)
    ledger = EventLedger()
    index = LocalVectorIndex()
    service = _service(root, catalog, ledger, index)

    first = service.ingest_directory(path=".")
    event_count = len(ledger.events)
    second = service.ingest_directory(path=".")

    assert first["status"] == second["status"] == "completed"
    assert len(index.chunks) == 1
    assert len(ledger.events) == event_count


def test_svg_enters_the_same_intake_and_indexes_visible_text(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    ingest = root / "01_knowledge_base_ingestion"
    ingest.mkdir(parents=True)
    content = b'<svg xmlns="http://www.w3.org/2000/svg"><text>P-101</text><text>pump</text></svg>'
    (ingest / "drawing.svg").write_bytes(content)
    catalog = root / "document_catalog.yaml"
    _catalog(catalog, "drawing.svg", content)
    ledger = EventLedger()
    index = LocalVectorIndex()

    result = _service(root, catalog, ledger, index).ingest_directory(path=".")

    assert result["status"] == "completed"
    assert result["chunk_count"] == 1
    assert "P-101" in index.chunks[0].text
