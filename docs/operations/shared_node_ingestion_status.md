# Shared Node Knowledge Ingestion Status

Status as of 2026-09-15: implementation is committed locally; remote runtime
deployment is not yet complete.

## Completed

- Catalog-driven ingestion now validates every catalogued file, including its
  SHA-256, document profile, revision, and safe relative path.
- Ingestion emits idempotent ledger events for job start, per-file success or
  failure, and job completion. Re-running the same catalog does not duplicate
  current vector chunks.
- SVG files are accepted by the File Intake Layer through bounded XML text
  extraction with entity and size checks.
- The Node accepts `AIRBENCH_KNOWLEDGE_CATALOG_PATH` and exposes the catalog in
  its startup status.
- A shared-node startup script persists ledger, intake, artifact, Chroma,
  world-model, and decision state below the node-owned `state` directory.
- Local verification completed: 53 focused M7/intake/retrieval/world-model/
  Chroma/Node API/P&ID integration tests passed. A real local 21-file corpus
  dry run completed with 21 files, 18 text chunks, zero failures, and 87 ledger
  events.
- On the model host, the application, corpus, and Python retrieval environment
  were staged. The BGE-M3 and BGE reranker artifacts were transferred to
  temporary operator staging but have not yet been activated by the shared
  Node.

## Remaining

- Resolve the model-host automount path race and move the staged embedding
  artifacts into the requested `airbench-serving/models` directory.
- Start the shared Node with an operator-provided bearer token, run the real
  catalog ingestion, and verify nonzero Chroma/vector counts through the Node
  API.
- Repeat the status/query check after a restart to prove persistence.
- Configure the approved internal HTTPS/authentication boundary if other
  operators need network access; the startup script intentionally binds to
  loopback and never exposes raw SQLite or Chroma files.
- P&ID graph extraction remains a separate capability and is not claimed by
  this ingestion slice; image OCR/graph qualification must be enabled and
  verified before reporting graph nodes or edges.

No SSH password or bearer token is stored in the repository.
