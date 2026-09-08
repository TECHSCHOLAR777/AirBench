# M7 File Intake, Retrieval, and World Model — Implementation Record

This document is the working evidence record for GitHub issue #12 and its
sub-issues #42–#45. It is kept alongside the implementation so that the
status of each boundary, test, and remaining deployment gate stays explicit.

## Governing outcome

Make organizational documents and knowledge available to workers through one
governed local path:

`File Intake -> bounded extraction/OCR -> local index/embedding/rerank -> cited retrieval -> candidate world-model write`

The path is local and provider-neutral. Files and model output remain
untrusted data until the appropriate provenance, clearance, consistency,
verification, and ledger gates accept them.

## Sub-issue plan and status

| Sub-issue | Boundary | Status | Remaining acceptance evidence |
| --- | --- | --- | --- |
| M7.1 / #42 | Shared intake, manifests, rendered pages, parser boundary | Implemented locally | Production renderer/Node integration and deployment-specific parser evidence |
| M7.2 / #43 | Typed OCR and vision adapters over intake page inputs | Implemented locally | Qualified OCR/Qwen2.5-VL runtime evidence and live page corpus |
| M7.3 / #44 | Local vector index, embeddings, and reranking | Implemented locally | Qualified BGE-M3/reranker serving evidence and larger corpus measurements |
| M7.4 / #45 | Clearance-filtered cited retrieval and candidate world-model writes | Implemented locally | Live end-to-end acceptance evidence and deployment-scale graph/index validation |

## Non-goals

- No direct parser calls from retrieval, workers, domain packs, or deliverable code.
- No cloud search, hosted OCR, hosted embeddings, or network fallback.
- No model or worker authority to mutate the world model directly.
- No candidate fact promotion without explicit consistency, verification, and
  append-only ledger gates.
- No claim that deterministic fixtures replace qualified local runtime or
  production Node evidence.

## Contracts and ownership

- `FileIntakeLayer` owns bytes, source/revision identity, parser selection,
  page/region identity, rendered artifacts, extraction confidence, clearance,
  taint, and `evidence.created`.
- OCR and vision adapters consume typed `PageRecord`/rendered-page inputs and
  return typed extraction records; they never open source paths or parse files.
- Indexing owns local chunk identity and provider-neutral vector records.
  Embedding and reranking implementations are injected qualified adapters.
- The reference index persists typed chunks to an optional bounded local JSON
  file and reloads them with revision, clearance, taint, and provenance intact;
  deployments may replace this seam with a qualified vector store.
- Retrieval owns clearance filtering, bounded excerpts, citation references,
  source/revision preservation, and retrieval ledger events.
- The world-model writer owns candidate staging only. Consistency and
  verification callbacks decide whether a candidate may be committed.
- Candidate facts may carry typed, provenance-bearing graph relations. The
  store supports bounded relation traversal and applies clearance to both
  edges and target facts before returning results.
- The reference world-model store persists committed `FactEnvelope` values to
  an optional bounded local JSON file; candidates are never persisted as
  committed facts and restart tests verify the gate boundary.
- The orchestrator remains the owner of task state, retries, escalation, and
  completion.

## Required ledger and provenance behavior

Every governed result retains source/reference identity, confidence,
clearance, taint, extraction or derivation method, and stable hashes. The
implementation uses `evidence.created`, `vision.requested/completed/failed`,
`index.requested/completed/failed`, `retrieval.requested/completed/failed`,
`world_model.requested`, `fact.candidate`, and `fact.committed` event types.
Ledger failure blocks the operation; it never becomes a successful result.

## Acceptance commands

```text
python -m pytest -q tests/test_m71_intake.py tests/test_m72_ocr_vision.py tests/test_m73_retrieval.py tests/test_m74_world_model.py
python -m pytest -q
python -m compileall -q airbench contracts tests
python scripts/generate_frontend_contracts.py --check
git diff --check
```

The full suite may continue to exclude tests whose optional host/runtime
dependencies are not installed in the local development environment; those
exclusions will be recorded with the final evidence rather than hidden.

## Requirement-to-evidence matrix

| Requirement | Repository evidence |
| --- | --- |
| One intake boundary for bulk and query uploads | `tests/test_m71_intake.py`; `airbench/intake.py` |
| Typed OCR/vision with provenance, timeout, cancellation, and limits | `tests/test_m72_ocr_vision.py`; `airbench/vision.py` |
| M5 backend contract integration | `VisionAdapterTests.test_m5_backend_bridge_uses_typed_multimodal_request` |
| Local embeddings, reranking, resource limits, and timeouts | `tests/test_m73_retrieval.py`; `QualifiedEmbeddingProvider`; `QualifiedReranker` |
| Clearance-filtered cited retrieval | `RetrievalTests.test_secret_chunks_are_not_exposed_to_lower_clearance` and citation assertions |
| Supersession and deletion-safe current projections | `test_new_revision_supersedes_previous_current_chunks`; `test_superseded_revisions_remain_auditable_but_are_not_returned` |
| Candidate-only World Model writes with both gates | `WorldModelTests.test_candidate_requires_both_gates_before_query_visibility` and failed-gate coverage |
| Typed graph writes and bounded traversal | `test_gated_graph_relation_supports_clearance_filtered_traversal` |
| World Model supersession and identity conflict protection | `test_superseded_fact_remains_auditable_but_is_not_query_visible`; `_commit` conflict checks |
| Ledger and signed projection evidence | `ProjectionBuilder` verification in `test_candidate_requires_both_gates_before_query_visibility` |
| Restart and storage-limit behavior | persistence and pre-commit storage-limit tests in M7.3/M7.4 suites |

## Change log

- Initial record: contract boundaries, dependency order, and honest remaining
  deployment evidence captured before implementation.
- Implementation slice: added typed OCR/vision adapters, local index and
  retrieval seams, candidate-only world-model writes, ledger events, focused
  tests, and governing documentation. Focused M7 tests pass 40/40 including
  the existing M7.1 intake suite.
- Audit hardening: added an executable M5 backend-to-vision bridge test,
  restart-safe local index/world-model persistence, and storage-limit checks.
- Graph hardening: added typed gated relations, bounded traversal, clearance
  filtering, relation persistence, and traversal coverage.
- Provider hardening: qualified embedding and reranking seams now enforce
  bounded input/batch sizes, typed failures, and timeouts.
- Reconciliation hardening: new intake revisions supersede prior current
  chunks, and World Model superseding facts remain auditable but are removed
  from current query projections without allowing identity overwrites.
