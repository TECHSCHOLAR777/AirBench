"""Run the local BGE retrieval stack (embedding + reranker) as a demo and,
optionally, produce qualification evidence.

Indexes a small built-in corpus, runs retrieval queries, prints the ranked,
cited excerpts, and (with ``--qualify``) writes qualification records and a
deterministic ``qualification_hash`` for the embedding and reranking services.

Uses the real local BGE models from ``AIRBENCH_MODEL_STORE`` (set it, or pass
``--model-store``).  Offline; no network.

Usage:
    python scripts/airbench_retrieval_demo.py --model-store C:\\airbench-models
    python scripts/airbench_retrieval_demo.py --model-store C:\\airbench-models --qualify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Native import order: the torch stack must initialise before pypdf (imported by
# File Intake) or the process can crash on Windows.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
try:
    import sentence_transformers  # noqa: F401
except ImportError:
    pass

from contracts import Clearance, Taint, stable_id  # noqa: E402
from airbench.knowledge.embedding_runtime import build_retrieval_runtime  # noqa: E402
from airbench.knowledge.retrieval import IndexChunk, RetrievalRequest  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORD_DIR = REPO_ROOT / "qualifications" / "records"
ROSTER_PATH = REPO_ROOT / "models" / "roster" / "v0" / "model_roster.yaml"

CORPUS = [
    {"source_ref": "doc:pump-manual", "text": "The pump discharge pressure must remain below 12 bar during normal operation. A high discharge pressure trip protects the casing."},
    {"source_ref": "doc:valve-sop", "text": "Before servicing a pressure relief valve, isolate the line, vent trapped pressure, and record the set pressure on the work permit."},
    {"source_ref": "doc:inspection-report", "text": "Inspection found corrosion on the pump base plate near the anchor bolts. Recommend ultrasonic thickness measurement at the next shutdown."},
]
QUERIES = [
    {"query": "maximum pump discharge pressure allowed", "expected": "doc:pump-manual"},
    {"query": "how to safely service a relief valve", "expected": "doc:valve-sop"},
    {"query": "corrosion found on pump base plate", "expected": "doc:inspection-report"},
]


def _sha(canonical: object) -> str:
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _index(runtime) -> int:
    chunks = []
    for index, doc in enumerate(CORPUS):
        embedding = runtime.indexer.embeddings.embed(doc["text"])
        chunks.append(IndexChunk(
            chunk_id=stable_id("chunk", doc["source_ref"], index), intake_id="intake.retrieval.demo",
            revision_id="rev.retrieval.demo", source_ref=doc["source_ref"], page_id=f"page-{index}",
            source_span=f"chars-0-{len(doc['text'])}", text=doc["text"],
            content_hash=hashlib.sha256(doc["text"].encode("utf-8")).hexdigest(), confidence=0.9,
            clearance=Clearance.internal, taint=Taint.untrusted, embedding=embedding,
            embedding_model=runtime.embedding_model_id,
            qualification_reference=runtime.embedding_qualification_reference, revision_state="current",
        ))
    runtime.index.upsert(chunks)
    return len(chunks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-store", default=None, help="Canonical model store (or set AIRBENCH_MODEL_STORE).")
    parser.add_argument("--qualify", action="store_true", help="Write qualification records and hashes.")
    parser.add_argument("--record-dir", type=Path, default=DEFAULT_RECORD_DIR)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--write-roster", action="store_true",
                        help="Write the BGE role qualification_hash values into the roster.")
    args = parser.parse_args(argv)

    model_store = args.model_store or os.environ.get("AIRBENCH_MODEL_STORE", "")
    if not model_store:
        print("ERROR: set AIRBENCH_MODEL_STORE or pass --model-store", file=sys.stderr)
        return 1

    runtime = build_retrieval_runtime(model_store=model_store)
    indexed = _index(runtime)
    print(f"indexed_chunks={indexed} embedding={runtime.embedding_model_id} reranker={runtime.reranker_model_id}")

    hits = 0
    reciprocal_ranks: list[float] = []
    for case in QUERIES:
        results = runtime.service.search(RetrievalRequest(
            task_id="task.retrieval.demo", query=case["query"], clearance=Clearance.internal, top_k=args.top_k))
        refs = [item.source_ref for item in results]
        rank = refs.index(case["expected"]) + 1 if case["expected"] in refs else 0
        hits += 1 if rank else 0
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        print(f"\nquery: {case['query']!r}")
        for item in results:
            print(f"  score={item.score:+.4f} source={item.source_ref} taint={item.taint.value} "
                  f"reranker={item.reranker_model} :: {item.excerpt[:80]}")

    recall_at_k = hits / len(QUERIES)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    print(f"\nrecall@{args.top_k}={recall_at_k:.2f} mrr={mrr:.3f}")

    if not args.qualify:
        return 0

    args.record_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    records = {
        "bge-m3.embedding_service": {
            "target_id": "bge-m3", "worker_role": "embedding_service",
            "embedding_model": runtime.embedding_model_id,
            "qualification_reference": runtime.embedding_qualification_reference,
            "corpus_size": len(CORPUS), "query_count": len(QUERIES),
            "recall_at_k": recall_at_k, "mrr": mrr, "top_k": args.top_k, "qualified_at": now,
        },
        "bge-reranker-v2-m3.reranking_service": {
            "target_id": "bge-reranker-v2-m3", "worker_role": "reranking_service",
            "reranker_model": runtime.reranker_model_id,
            "qualification_reference": runtime.reranker_qualification_reference,
            "corpus_size": len(CORPUS), "query_count": len(QUERIES),
            "recall_at_k": recall_at_k, "mrr": mrr, "top_k": args.top_k, "qualified_at": now,
        },
    }
    for name, record in records.items():
        record["qualification_hash"] = _sha({k: v for k, v in record.items() if k != "qualification_hash"})
        path = args.record_dir / f"{name}.json"
        path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        print(f"{name} qualification_hash={record['qualification_hash']}")
    print(f"records written to {args.record_dir}")

    if args.write_roster:
        import yaml  # type: ignore
        document = yaml.safe_load(ROSTER_PATH.read_text(encoding="utf-8"))
        role_by_target = {"bge-m3": "embedding_service", "bge-reranker-v2-m3": "reranking_service"}
        for target in document.get("roster", {}).get("targets", []):
            target_id = target.get("target_id")
            if target_id not in role_by_target:
                continue
            serving = target.get("serving") or {}
            if str(serving.get("runtime", "")) == "custom" and str(serving.get("container_digest", "")).startswith("PENDING:"):
                serving["container_digest"] = ""
                target["serving"] = serving
            record = records[f"{target_id}.{role_by_target[target_id]}"]
            for role in target.get("qualified_roles", []) or []:
                if role.get("role") == role_by_target[target_id]:
                    role["certificate_id"] = f"cert.{target_id}.{role_by_target[target_id]}.v0"
                    role["qualification_hash"] = record["qualification_hash"]
        ROSTER_PATH.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(f"Updated {ROSTER_PATH} BGE role qualification_hash values.")
        print("Note: re-signing the full reference roster is deferred until its reference-target")
        print("placeholders are filled; the demo roster can include BGE via --include-retrieval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
