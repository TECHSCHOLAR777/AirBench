# Shared Node Knowledge Ingestion Status

Status as of 2026-09-15: the local knowledge-base ingestion path and the
shared Linux Node validation are complete for authenticated loopback use.
Production multi-operator HTTPS and qualified P&ID graph extraction remain
explicit follow-up gates.

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
- On the model host, the application, corpus, Python retrieval environment,
  BGE-M3 encoder, and BGE reranker were activated from the mounted
  `airbench-serving` volume. The shared launcher now handles the mounted
  application layout, selects the available virtual environment, and locates
  the signed domain pack beside the application source.
- Remote Node validation completed with the real catalog: 21 files were
  ingested, 18 text chunks were indexed, and zero files failed. Authenticated
  search returned three cited results from the catalog, and the persisted
  Chroma collection contained 18 chunks after the Node was stopped.
- Restart validation completed: the Node became ready again and returned the
  same cited search results from the persisted ledger and vector store.
- The local security boundary was checked: an unauthenticated request returned
  HTTP 401, the Node listener was `127.0.0.1:8765`, and no external listener
  was present. The temporary validation Node was stopped after the run.

## Remaining

- Configure and validate an approved internal HTTPS and authentication
  boundary if other operators need network access. The current launcher
  intentionally binds to loopback and does not expose raw SQLite or Chroma
  files. This requires an approved hostname, certificate, and reverse-proxy or
  equivalent boundary, so it is not silently enabled by this change.
- P&ID graph extraction remains a separate qualification gate. The remote host
  currently lacks the detector weights and the required computer-vision/OCR
  dependencies, so the adapter can be composed but no graph accuracy claim is
  made. Qualification still requires representative drawings, OCR and symbol
  checks, topology review, coordinate grounding, abstention checks, and
  domain-expert acceptance on the intended GPU host.

No SSH password or bearer token is stored in the repository.
