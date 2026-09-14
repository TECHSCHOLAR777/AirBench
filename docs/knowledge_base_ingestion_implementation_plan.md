# AirBench knowledge-base ingestion and retrieval implementation plan

Status: implementation plan, 2026-09-14

## Current implementation status

The prototype implementation has now begun against this plan.

Completed in the current worktree:

- P&ID package import no longer eagerly loads optional Ultralytics settings during ordinary Node/test startup; unavailable local vision dependencies are reported as typed adapter failures.
- P&ID upload uses the governed intake path and stages candidate graph facts through World Model gates.
- Text/vector, image/source-artifact, decision, and SQLite graph projections are composed behind the Node.
- `/api/v1/knowledge/search` supports text, graph, and hybrid modes.
- The desktop Knowledge screen can search the Node and select a native corpus folder for guarded bulk ingestion.
- Bulk ingestion reports completed, partial, and failed file outcomes instead of hiding a mid-corpus failure.
- Chroma mixed-source revision batches supersede each source independently.
- The desktop task composer and model route display are wired for the signed local reasoning lane, and completed task artifacts are refreshed automatically.
- The normal UI hides internal identifiers while preserving them in technical/audit views.

Still required before calling the prototype fully validated:

- run the full backend and desktop validation suites in the repository virtual environment;
- prove the live Node task path leaves Planning and reaches a terminal/review state after a fresh Node restart;
- exercise native corpus ingestion against the configured corpus root and verify text/image/graph results in the Knowledge screen;
- add/verify restart and projection-repair evidence for the durable stores;
- run the applicable architecture, intake, provenance, ledger, security, and frontend no-egress checks;
- record any environment-dependent limitation for real P&ID detector weights, OCR/vision runtime, and licensed source material.

This plan completes the AirBench ingestion and knowledge path for digital documents, scans, images, tables, text, and P&ID drawings, from the Tauri desktop application through the Python Node, local stores, verification, retrieval, World Model graph, and downstream deliverables.

It is a plan for the existing architecture, not a proposal for a second RAG system. The core engine remains sector-neutral; refinery/PSU document profiles, P&ID legends, object types, field rules, clearance roles, and deliverable templates remain in the signed domain pack.

## 1. Outcome and definition of done

An operator can use the desktop application to:

1. bulk-import an approved local corpus or upload one file to a task;
2. ingest PDF, scanned PDF, DOCX, XLSX, CSV, PNG/JPEG, plain text, markup, and P&ID page images through the single File Intake Layer;
3. inspect a safe preview and intake manifest before trusting any extracted content;
4. index text and tables into a clearance-filtered local retrieval store;
5. retain images, rendered pages, OCR regions, P&ID overlays, and graph artifacts in the local source/artifact store;
6. extract P&ID symbols, labels, lines, junctions, and candidate relations into a provenance-bearing `PIDRecord`;
7. submit P&ID candidates to verification, consistency, review, and World Model graph-commit gates;
8. retrieve cited text/image evidence and query verified graph relations through one Node boundary;
9. preserve source, revision, location, confidence, clearance, taint, derivation, time, model identity, and ledger references through every projection;
10. use the combined evidence in an orchestrated task and produce a verified deliverable; and
11. demonstrate restart/replay, clearance filtering, supersession, failure handling, and no-egress behavior.

Done means the evidence exists for the whole path. Passing a unit test or returning a successful HTTP response alone is not completion.

## 2. Architecture to implement

```text
                    ┌────────────────────────────────────────────┐
                    │              AirBench Desktop              │
                    │  Launchpad / intake review / live trace /  │
                    │  evidence / graph review / artifact review │
                    └───────────────────┬────────────────────────┘
                                        │ Rust-owned typed transport
                                        ▼
                    ┌────────────────────────────────────────────┐
                    │               AirBench Node                │
                    │ Orchestrator owns state, policy, retries,  │
                    │ review gates, and all consequential writes │
                    └───────────┬───────────────────┬────────────┘
                                │                   │
                                ▼                   ▼
                     ┌──────────────────┐   ┌────────────────────┐
                     │ File Intake Layer │   │ Knowledge services │
                     │ parse/render/OCR │   │ retrieval + graph  │
                     └─────────┬────────┘   └──────────┬─────────┘
                               │                       │
              ┌────────────────┼─────────────┐         │
              ▼                ▼             ▼         ▼
       Source/artifact    Text/table     P&ID      World Model
       store              chunks         adapter   graph candidates
       images/pages       embeddings     graph     and commits
              │                │             │         │
              └────────────────┴─────────────┴─────────┘
                               │
                         Ledger transaction
```

The stores are projections of the append-only ledger and must be recoverable or repairable from committed events:

| Projection/store | Contents | Current implementation | Target role |
| --- | --- | --- | --- |
| `LocalIntakeStore` / artifact store | Original bytes, rendered pages, image previews, OCR regions, overlays, GraphML/JSON, safe previews | Present | Visual and source evidence; never a text-search substitute |
| `SqliteVectorStore` or local `ChromaVectorStore` | `IndexChunk` text/table chunks, embeddings, provenance and revision state | Present | Clearance-filtered lexical/vector retrieval |
| `SqliteGraphStore` through `WorldModelStore` | Fact nodes, relations, supersession, fact history | Present | Verified equipment/P&ID/world graph |
| `SqliteDecisionStore` | Comparable decisions and outcomes | Present | Consistency and precedent memory |
| append-only ledger | Intake, evidence, projections, candidates, checks, routes, reviews, commits, artifacts | Present in core | Authority, replay, audit, and projection repair |

## 3. Governing contracts and invariants

### 3.1 Ownership

- The File Intake Layer is the only parser and renderer entry point.
- The Knowledge and Retrieval Engine owns indexing, search, reranking, citations, and document-version handling.
- The P&ID adapter owns visual extraction and candidate graph-fragment assembly, but never commits World Model facts.
- The World Model Engine owns candidate gating, reconciliation, time-aware graph state, and graph queries.
- The Orchestrator owns task state, sequencing, retries, fallback, review transitions, and completion.
- The Node owns clearance, provenance, verification, tools, routes, and ledger writes.
- Tauri/Rust owns transport and file-picker boundaries; React owns presentation only.
- The domain pack owns document profiles, authoritative-source declarations, world schema, P&ID legend, field rules, decision types, risk mapping, clearance roles, and templates.

### 3.2 Non-negotiable invariants

- Files and extracted content are untrusted data, never instructions.
- Bulk ingestion and query-time upload use the same File Intake Layer; only destination, trust/persistence, and latency switches differ.
- Every evidence item retains source identity, revision, location, extraction method, confidence, clearance, taint, timestamps, content hash, and ledger reference.
- Derived facts retain parent evidence and computation/derivation chains.
- Clearance is enforced before evidence is exposed to retrieval, graph queries, workers, or UI.
- A P&ID graph fragment is a candidate until verification, consistency, and review policy allow promotion.
- Current projections may hide superseded or tombstoned records, but the ledger never deletes their history.
- Retrieval returns bounded cited evidence, not bare strings.
- The World Model answers relation/time questions; vector retrieval answers source-text questions.
- Models propose extraction, classification, OCR, ranking, or prose; they do not grant trust, commit graph facts, choose tools, or advance state.
- Deterministic values are computed by governed tools and referenced by model-authored prose.
- No external network is used by intake, OCR, embeddings, reranking, P&ID extraction, stores, or the UI.

## 4. Input matrix and target behavior

| Input | Intake output | Permanent projections | Query behavior |
| --- | --- | --- | --- |
| Digital PDF | Text, tables, page regions, manifest | Text/vector index; authoritative facts where pack permits | Cited page excerpts |
| Scanned PDF | Rendered pages, OCR/vision evidence, regions, confidence | Source/artifact store; OCR text may enter vector index as evidence | Image/page preview plus cited OCR evidence |
| PNG/JPEG photograph | Image manifest, safe preview, vision evidence | Source/artifact store; extracted text/facts only after gates | Image evidence with region and confidence |
| DOCX/rich text | Structured paragraphs, headings, tables, revision metadata | Text/vector index and optional authoritative facts | Section/table citations |
| XLSX/CSV | Typed tables, headers, units, formulas, sheet/cell locations | Table chunks and deterministic source records | Cell/range citations; calculations use governed tool path |
| Plain text/markup | Bounded sections and source spans | Text/vector index | Span citations |
| P&ID PDF/image/normalized CAD render | Root canvas, tiles, visual evidence, `PIDRecord`, candidate graph fragment, overlays | Source/artifact store first; World Model graph only after gates | Visual evidence plus verified graph traversal |
| Query-time upload | Same manifest/evidence shape with task scope and low-trust default | Session scratch only unless explicit promotion | Available to current task, never silently permanent |

CAD support is limited to an approved normalized rendering path. Unsupported CAD formats fail closed; the P&ID adapter must not independently parse arbitrary CAD containers.

## 5. Contract work before implementation

Create or extend versioned contracts before wiring new code. The exact field names should reuse existing `FactEnvelope`, `UntrustedEvidence`, `IntakeManifest`, `PageRecord`, `IndexChunk`, `CandidateFact`, `WorldModelRelation`, and Node protocol envelopes wherever possible.

### 5.1 Intake contracts

Extend or confirm:

- `IntakeManifest`: stable `intake_id`, `source_ref`, `revision_id`, filename/media type, source hash, byte size, document profile, effective/observed/ingested times, clearance, trust class, taint, parser/render versions, page count, extraction settings, and supersession state.
- `PageRecord`: page identity/number, rendered-artifact reference, text, tables, regions, confidence, extraction method, image hash, dimensions, and ledger reference.
- `EvidenceReference`: source/revision/page/sheet/cell/region, content hash, extraction method, confidence, clearance, taint, derivation, and parent evidence IDs.
- `KnowledgeAsset`: a stable projection describing the original asset, current revision, available representations, review state, and clearance-filtered preview references.

### 5.2 P&ID contracts

Extend `PIDRecord` so each component, text region, segment, junction, connector, and relation carries:

- root-canvas identity and coordinate transform;
- page/tile identity and source region;
- extraction method and adapter version;
- detector/OCR/geometry model artifact and qualification references;
- confidence inputs, ambiguity state, clearance, taint, valid/observed/ingested times;
- parent evidence references and derivation chain;
- review/verification state;
- artifact references for original canvas, overlays, crops, GraphML, and JSON.

Add a typed `PIDGraphCandidate` projection containing `CandidateFact` nodes and `WorldModelRelation` edges. It must be impossible for `PIDRecord` serialization to be mistaken for a committed World Model fact.

### 5.3 Retrieval contracts

Confirm or version:

- `KnowledgeSearchRequest`: task/principal, query, clearance, collection/profile filters, top-k, relation mode, time/as-of, and whether graph lookup is requested.
- `KnowledgeSearchResult`: result kind (`text`, `table`, `image`, `graph`), cited evidence, score/rerank metadata, source/revision/location, confidence, clearance, taint, and ledger reference.
- `KnowledgeSearchResponse`: ordered results, graph results, no-match reason, projection versions, and query event reference.
- `KnowledgeIngestJob`: job ID, source root, profile selection, task/actor, counts, failures, retry state, and committed transaction IDs.

### 5.4 UI contracts

Extend generated Node/Rust/TypeScript contracts for:

- intake manifest and safe preview;
- bulk-ingest job status and per-file failures;
- evidence/asset library rows;
- knowledge search results with citations and provenance;
- graph query results and graph-review queue;
- P&ID extraction/review projection;
- projection health and replay status.

Every UI record must carry its stable ID, schema version, clearance context, provenance/ledger reference, hash or integrity reference, and redaction reason where content is hidden.

## 6. State machines and ledger events

### 6.1 Bulk ingestion state machine

```text
discovered
  -> admitted
  -> intake_started
  -> parsed
  -> representations_stored
  -> evidence_created
  -> text_indexed and/or graph_candidate_created
  -> provenance_checked
  -> review_required | promoted | rejected
  -> current | superseded | tombstoned
```

### 6.2 Query-time upload state machine

```text
upload_received
  -> task_bound
  -> intake_parsed
  -> preview_ready
  -> task_scoped_evidence
  -> used_by_task | explicitly_promoted | discarded
```

### 6.3 P&ID state machine

```text
pid_admitted
  -> intake_manifest_committed
  -> root_canvas_ready
  -> visual_extraction_running
  -> pid_record_created
  -> candidate_graph_staged
  -> verification/consistency/autonomy checks
  -> review_required | rejected | graph_commit_allowed
  -> world_model_committed
```

### 6.4 Required event families

At minimum, add or confirm:

- `intake.requested`, `intake.started`, `intake.parsed`, `intake.failed`, `intake.superseded`, `intake.tombstoned`;
- `evidence.created`, `evidence.revised`, `evidence.quarantined`, `evidence.promoted`;
- `projection.started`, `projection.committed`, `projection.failed`, `projection.repaired`;
- `retrieval.requested`, `retrieval.completed`, `retrieval.no_match`, `retrieval.failed`;
- `pid.extraction.started`, `pid.extracted`, `pid.candidate.staged`, `pid.review.required`, `pid.review.resolved`;
- `world_model.candidate_created`, `world_model.review_required`, `world_model.review_resolved`, `world_model.committed`, `world_model.conflict`;
- `knowledge.ingest.started`, `knowledge.ingest.file_completed`, `knowledge.ingest.file_failed`, `knowledge.ingest.completed`;
- existing task, worker, model, tool, verification, review, artifact, approval, retry, cancellation, and completion events.

Every event needs parent task/job identity, actor/subsystem, sequence, idempotency key, content/input/output hashes, schema version, clearance, provenance references, and failure details where relevant. If the ledger write fails, the consequential operation stops or is quarantined.

## 7. Implementation sequence

The sequence below is dependency-aware. Each slice follows red → green → refactor, then the applicable intake, provenance, ledger, security, architecture, and frontend guards.

### Slice 0 — Baseline and contract freeze

Owner: architecture/contracts; prerequisite for all later slices.

Inspect and freeze the existing behavior in:

- `src/airbench/intake/layer.py`
- `src/airbench/intake/raster_renderer.py`
- `src/airbench/intake/table_extractor.py`
- `src/airbench/intake/vision.py`
- `src/airbench/knowledge/retrieval.py`
- `src/airbench/knowledge/vector_store.py`
- `src/airbench/knowledge/world_model.py`
- `src/airbench/knowledge/graph_store.py`
- `src/airbench/knowledge/decision_store.py`
- `src/airbench/node/api.py`
- `src/airbench/node/server.py`
- `apps/desktop/src/generated/core_contracts.ts`
- `apps/desktop/src-tauri/`

Deliverables:

- contract compatibility matrix;
- input/profile/store matrix;
- event catalog and idempotency rules;
- projection transaction design;
- explicit list of existing behavior that must not regress.

Tests:

- existing M7/M9 intake and retrieval tests;
- existing Node API and generated-contract checks;
- clean `git diff --check`, compile, and focused baseline suite.

### Slice 1 — Unify intake representations for every supported input

Owner: M7 File Intake.

Implement/verify one `FileIntakeLayer` path for digital PDF, scanned PDF, image, DOCX, XLSX/CSV, text, markup, and normalized P&ID pages.

Work:

- complete parser/profile dispatch from the signed domain pack;
- ensure every parser produces `IntakeManifest` plus structured pages/sections/tables, never bare text;
- persist original bytes and rendered pages transactionally through `LocalIntakeStore`;
- add bounded safe previews for image, PDF, table, and text representations;
- preserve sheet/cell, page/region, and image-coordinate references;
- add duplicate and revision detection with supersession/tombstones;
- add explicit unsupported/malformed/encrypted/oversized/partial parse results;
- make bulk and query-upload switches explicit and test that they share parser behavior;
- add a normalized drawing-render input profile for P&ID/CAD without allowing standalone CAD parsing.

Primary files:

- `src/airbench/intake/layer.py`
- `src/airbench/intake/raster_renderer.py`
- `src/airbench/intake/table_extractor.py`
- `src/airbench/intake/vision.py`
- `src/airbench/intake/ocr_provider.py`
- `src/airbench/intake/__init__.py`
- `src/contracts/`
- `packs/refinery_psu_v0/document_profiles.yaml`
- `tests/test_m71_intake.py`, `tests/test_m75_ocr_provider.py`, and new per-format fixtures.

Acceptance:

- same input gets stable source/revision identity through bulk and query paths;
- preview never executes macros, embedded objects, links, or scripts;
- all representations retain provenance and taint;
- a failed parser is visible and retry/reviewable, never silently dropped.

### Slice 2 — Transactional projection coordinator

Owner: M2 ledger + M7 projections.

The current stores exist independently. Add a coordinator that commits an intake transaction and its projections consistently.

Work:

- define `KnowledgeProjectionCoordinator` or equivalent core interface;
- write a transaction record before projection work;
- commit source/artifact, vector chunks, graph candidates, and decision references with shared transaction ID;
- expose incomplete/pending projections rather than pretending a partial commit is complete;
- make restart repair rebuild projections from ledger events;
- ensure retries are idempotent by source/revision/profile/transaction identity;
- add projection status and repair APIs for operators.

Primary files:

- `src/contracts/ledger.py` and projection contracts;
- `src/airbench/intake/layer.py` and `src/airbench/intake/storage.py` if split is needed;
- `src/airbench/knowledge/vector_store.py`;
- `src/airbench/knowledge/graph_store.py`;
- `src/airbench/knowledge/decision_store.py`;
- `src/airbench/node/knowledge_gateway.py`;
- `tests/test_projections.py` plus new crash/restart tests.

Acceptance:

- a crash between any two projections leaves a visible incomplete transaction;
- replay repairs projections without duplicate chunks, facts, or events;
- a superseded source removes itself from current search/graph views but remains auditable.

### Slice 3 — Text, table, OCR, and image knowledge projection

Owner: M7 retrieval.

Complete the durable text/vector path while keeping image evidence in the source/artifact store.

Work:

- classify clean text, OCR text, tables, and image-only pages using profile rules;
- chunk by section/table boundaries without separating values from units;
- create `IndexChunk` records with page/sheet/cell/region references;
- use local BGE-M3 embeddings and local reranking only through qualified adapters;
- support deterministic lexical fallback where embeddings are unavailable, with explicit degraded status;
- index OCR text as evidence, never as trusted instructions;
- allow retrieval results to reference image/page artifacts and safe previews;
- add collection/profile filtering and as-of revision filtering;
- return honest no-match and low-confidence results.

Primary files:

- `src/airbench/knowledge/retrieval.py`
- `src/airbench/knowledge/retrieval_loop.py`
- `src/airbench/knowledge/embedding_runtime.py`
- `src/airbench/knowledge/reranker.py`
- `src/airbench/knowledge/vector_store.py`
- `src/airbench/node/knowledge_gateway.py`
- `tests/test_m73_retrieval.py`, `tests/test_m715_bge_end_to_end.py`, `tests/test_node_knowledge_api.py`.

Acceptance:

- search returns cited excerpts and never bare strings;
- clearance filtering happens inside the store/query path before exposure;
- image and OCR results retain source page/region and artifact references;
- current and superseded revisions behave correctly after restart.

### Slice 4 — World Model entity extraction and authoritative-table projection

Owner: M7 World Model.

Before P&ID graph work, make the graph useful with explicit identifiers from asset registers, line lists, PFDs, and approved tables.

Work:

- extend the domain pack world schema for equipment, units, lines, procedures, findings, and permitted links;
- extract typed candidate facts from `FactEnvelope`/evidence references;
- map stable asset/tag identifiers and source revisions;
- stage candidates through `CandidateFactWriter`;
- enforce consistency and verification gates before graph commit;
- support as-of and bounded traversal queries;
- preserve superseded facts and conflicts rather than overwriting them.

Primary files:

- `src/airbench/knowledge/entity_extractor.py`
- `src/airbench/knowledge/world_model.py`
- `src/airbench/knowledge/graph_store.py`
- `packs/refinery_psu_v0/world_schema.yaml`
- `packs/refinery_psu_v0/document_profiles.yaml`
- `tests/test_m74_world_model.py`, `tests/test_m79_world_model_store.py`, `tests/test_m79_node_graph_api.py`.

Acceptance:

- `P-101 -> E-201` can be queried as a graph relation with source and confidence;
- a low-confidence or conflicting candidate goes to review;
- public/internal/restricted queries expose only permitted nodes and edges;
- graph state can be reconstructed after restart.

### Slice 5 — Complete P&ID extraction as a governed intake adapter

Owner: P&ID adapter + M7/M8 integration.

The current `src/airbench/intake/pid/` pipeline is a partial extraction implementation. Complete its architecture integration.

Work:

1. Change the Node route so P&ID upload first creates an ordinary File Intake manifest and rendered-page/source artifact.
2. Pass only the intake-produced page bytes, manifest, profile, and scoped workspace to `PidIntakeAdapter`.
3. Add root-canvas, tile, region, mask, line, junction, connector, and model qualification provenance to `PIDRecord`.
4. Keep image/overlay/crop/GraphML/JSON artifacts in the local artifact/intake store with hashes.
5. Convert `PIDRecord` into `PIDGraphCandidate` nodes/edges; do not commit directly.
6. Run domain-pack symbol/relationship rules, verification, consistency, autonomy, and human-review gates.
7. Commit accepted candidate facts and relations through `CandidateFactWriter` and `WorldModelStore`.
8. Expose candidate/review/committed graph projections to the Node API and UI.
9. Add no-weight/no-dependency/unreconciled-seam/false-crossing/ambiguous-symbol failure paths.

Primary files:

- `src/airbench/intake/pid/adapter.py`
- `src/airbench/intake/pid/records.py`
- `src/airbench/intake/pid/pipeline.py`
- `src/airbench/intake/pid/topology_builder.py`
- `src/airbench/intake/pid/exporters.py`
- `src/airbench/node/api.py`
- `src/airbench/node/server.py`
- `src/airbench/knowledge/entity_extractor.py`
- `src/airbench/knowledge/world_model.py`
- `packs/refinery_psu_v0/pid_legend.yaml`
- `packs/refinery_psu_v0/world_schema.yaml`
- `tests/test_m717_pid_adapter.py`, `tests/test_m717_pid_pipeline.py`, `tests/test_node_pid_api.py`, plus candidate/commit tests.

Acceptance:

- no direct raw-file P&ID path remains;
- P&ID graph facts are not query-visible before gates pass;
- accepted relations are queryable through `/api/v1/knowledge/graph/query`;
- each edge can be traced to drawing coordinates, source hash, adapter/model identity, confidence, clearance, taint, review, and ledger event;
- the original drawing and overlays remain reviewable.

### Slice 6 — Unified knowledge query service

Owner: M7 retrieval + M3 orchestrator seam.

Provide one Node-owned query contract that can combine document, image, table, and graph evidence without flattening the types.

Work:

- evolve `/api/v1/knowledge/search` to accept `mode: text|image|table|graph|hybrid` or a typed equivalent;
- route relation/topology/as-of questions to World Model, source-text questions to retrieval, and hybrid questions through deterministic orchestration;
- enforce clearance before both vector and graph result exposure;
- return cited `KnowledgeSearchResult` objects with evidence kind, source, score, confidence, taint, and ledger reference;
- record the exact result-set hash and projection versions;
- return `no_match`, `needs_review`, `degraded`, or `unavailable` explicitly;
- make iterative retrieval bounded and orchestrator-owned.

Primary files:

- `src/airbench/knowledge/retrieval.py`
- `src/airbench/knowledge/retrieval_loop.py`
- `src/airbench/knowledge/world_model.py`
- `src/airbench/node/api.py`
- `src/airbench/node/server.py`
- `src/contracts/`
- `tests/test_node_knowledge_api.py`, graph API tests, retrieval loop tests.

Acceptance:

- “What does the SOP say?” returns cited text;
- “What is downstream of P-101?” returns graph facts/edges;
- “Which findings on P-101 conflict with the current line list?” combines both and retains distinct evidence types;
- no model is allowed to silently turn a weak text match into a graph fact.

### Slice 7 — Orchestrated knowledge task and deliverable path

Owner: M3/M8/M9 integration.

Drive a complete task through the orchestrator rather than exposing knowledge APIs as an ungoverned assistant.

Task stages:

```text
received
 -> authorized
 -> planned
 -> plan_validated
 -> executing
 -> intake/evidence
 -> retrieval/world-model query
 -> verification/consistency
 -> awaiting_review when required
 -> rendering
 -> deliverable_verified
 -> complete
```

Work:

- add typed knowledge/intake steps to plan validation;
- route vision/OCR, embeddings/reranking, reasoning, coding/calculation, and verification per step;
- record route and qualification evidence;
- use independent verification for high-risk extraction or graph changes;
- keep deterministic values in governed tool results;
- pass only cited evidence references and verified graph facts to the deliverable engine;
- include source links, image/region links, graph relation references, computed values, review state, and artifact hash in the final document.

Primary files:

- `src/airbench/orchestration/`
- `src/airbench/node/task_execution.py`
- `src/airbench/verification/`
- `src/airbench/delivery/`
- `src/airbench/m9/vertical_slice.py`
- `tests/test_m9_vertical_slice.py` and new combined-input acceptance tests.

Acceptance:

- a scanned inspection report plus SOP plus equipment/P&ID evidence produces a reviewed DOCX;
- all values are deterministic and traceable;
- a failed graph check or missing verifier blocks completion;
- the artifact is not labeled approved until the human review action occurs.

### Slice 8 — Node API and persistence administration

Owner: M10 Node/API plus operations.

Complete operator-visible status and recovery controls without exposing raw stores.

Add or confirm read projections for:

- intake and projection job status;
- knowledge collections and counts by source/profile/revision;
- vector store readiness and qualification;
- graph node/edge counts and review queue;
- P&ID artifact/review status;
- ledger head, transaction status, and projection-repair status;
- no-egress and model/adapter availability.

All writes remain Node-authorized commands with idempotency and clearance. No UI or worker opens SQLite/Chroma/GraphML files directly.

### Slice 9 — Desktop UI from launch to review

Owner: FE-DEV and frontend validation.

#### Screen A: Knowledge intake / Launchpad extension

User outcome: choose “Add to knowledge base” or “Use for this task,” select approved local files/folders, and declare purpose/profile where needed.

Data dependencies: approved Node profile, clearance, domain-pack document profiles, typed intake command, and accepted file manifest.

States: idle, selecting, uploading, intake-running, partial, blocked, completed, needs-review.

Rules:

- React never parses the file;
- Rust handles the approved file picker and sends bytes/handles through the typed Node boundary;
- the UI does not accept arbitrary URLs or model choices;
- the user sees whether the file is task-scoped or permanent-corpus candidate.

#### Screen B: Intake review and safe preview

User outcome: inspect pages/images/tables, source hash, document profile, confidence, clearance, taint, and parse warnings before continuing.

States: preview-ready, partially-readable, unsupported, blocked-clearance, parser-failed.

The UI renders only Node-produced safe previews. It never runs embedded content or makes an authority decision.

#### Screen C: Knowledge library and ingestion job

User outcome: see source/revision/current/superseded/review-required state, collection, profile, graph/vector projections, and failures.

Actions: retry failed file, request review, inspect provenance, tombstone through a typed Node command where permitted.

#### Screen D: Evidence and retrieval explorer

User outcome: search local knowledge and see text excerpts, image/page evidence, table ranges, and graph relations as distinct result types.

Every result shows source, revision, location, confidence, clearance, taint, derivation/parent references, and ledger reference.

#### Screen E: P&ID review

User outcome: inspect the original drawing, overlays, candidate symbols/labels/lines, unresolved regions, confidence, and proposed graph relations.

Actions: accept/reject/route for clarification through Node commands; never edit graph state directly in React.

#### Screen F: Live work trace and artifact review

User outcome: understand which intake, retrieval, graph query, verification, calculation, and artifact events produced the result.

Use existing sequence-numbered snapshots/events and keep raw model reasoning/private payloads out of the UI.

Frontend files likely touched:

- `apps/desktop/src/app/App.tsx`
- `apps/desktop/src/components/`
- `apps/desktop/src/generated/core_contracts.ts` via generation, not hand editing;
- `apps/desktop/src-tauri/src/` transport and allowlist;
- `apps/desktop/src/styles/` or existing token files;
- frontend contract and WebDriver tests.

Frontend acceptance:

- disconnected/gapped event stream stops authoritative projection and requests resync;
- clearance/taint metadata is never dropped from evidence rows;
- file preview and download use Node-authorized paths;
- UI cannot contact model endpoints, cloud services, arbitrary URLs, or external document links;
- keyboard, screen-reader, reduced-motion, contrast, and failure states are tested.

### Slice 10 — End-to-end evidence and release gates

Owner: M10 plus frontend release validation.

Create one sanitized/synthetic acceptance corpus containing:

- digital PDF;
- scanned PDF;
- PNG/JPEG inspection image;
- DOCX SOP;
- XLSX equipment register;
- CSV line list;
- prior approval note;
- P&ID PNG or normalized local drawing;
- one superseding revision;
- one malformed/unsupported input;
- one low-confidence and one clearance-restricted input.

Run the full local scenario:

1. bulk-ingest the corpus;
2. verify stores and ledger transactions;
3. upload a task-scoped scanned report;
4. retrieve SOP text and image evidence;
5. query equipment and P&ID graph relations;
6. trigger a conflict/review path;
7. resolve the review and query the committed graph;
8. calculate deterministic summary values;
9. render and verify the DOCX;
10. restart the Node and replay/rebuild projections;
11. inspect the desktop trace;
12. capture no-egress evidence.

## 8. Test and evidence matrix

| Concern | Required tests/evidence |
| --- | --- |
| Intake | Format fixtures, malformed/encrypted/oversized files, partial parses, duplicate/revision, bulk/query parity |
| Images/OCR | Safe preview, bounding regions, low confidence, missing OCR dependency, no raw-path access |
| Tables | Headers/units/formulas preserved, sheet/cell citations, deterministic calculation inputs |
| Vector retrieval | Restart, clearance filtering, supersession, no-match, BGE qualification, reranker failure/degraded result |
| World Model | Candidate gates, low-confidence review, conflict/supersession, as-of query, clearance-filtered edges |
| P&ID | Hash/taint rejection, missing weights, tile seam, false crossing, ambiguous symbol, coordinate provenance, candidate-only output |
| Projection consistency | Crash at each projection boundary, repair, idempotent retry, no orphaned references |
| Ledger | Event ordering/hash chain, input/output hashes, transaction identity, ledger failure blocks writes |
| Orchestrator | Bounded steps, retry/fallback ownership, restart, verifier unavailable, review escalation |
| UI transport | Typed command/receipt, sequence gap/replay/resync, safe preview/download, clearance/redaction |
| UI accessibility/security | Keyboard, screen reader names, reduced motion, CSP, blocked navigation, no-egress monitor |
| Deliverable | Numeric binding, source/evidence links, artifact hash, structural/visual checks, review status |

Required commands should include focused slices plus:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_m71_intake.py tests/test_m73_retrieval.py tests/test_m74_world_model.py
.venv\Scripts\python.exe -m pytest -q tests/test_m76_vector_store.py tests/test_m79_world_model_store.py tests/test_m717_pid_adapter.py tests/test_node_pid_api.py
.venv\Scripts\python.exe -m pytest -q tests/test_m715_bge_end_to_end.py tests/test_node_knowledge_api.py tests/test_m79_node_graph_api.py
.venv\Scripts\python.exe -m pytest -q tests/test_m9_vertical_slice.py
python -m compileall -q src tests scripts
git diff --check
```

Frontend evidence must additionally run the repository's contract, UI, build, WebDriver, reconnect, preview, and no-egress validation commands documented under `docs/desktop/validation/`.

## 9. Dependency graph and delivery order

```text
S0 contracts and baseline
  -> S1 unified intake
  -> S2 projection coordinator
  -> S3 text/image/table retrieval
  -> S4 explicit world-model extraction
  -> S5 P&ID candidate and graph integration
  -> S6 hybrid knowledge query
  -> S7 orchestrated task + deliverable
  -> S8 operator/API projections
  -> S9 desktop integration
  -> S10 end-to-end and release evidence
```

Parallel work is safe only after S0 and with file ownership separated:

- S3 retrieval work can proceed alongside S4 graph work after the intake contracts are frozen.
- S5 P&ID adapter internals can proceed separately from S4 graph integration, but their shared `PIDRecord`/candidate contracts are serialized.
- S9 UI contract/projection work can proceed against typed fixtures after S6 contracts stabilize; real Node integration waits for S7/S8.
- S10 is serial integration and must not be split across workers editing the same orchestrator, contracts, or acceptance fixtures.

## 10. Current blockers and risks

1. **P&ID route bypasses normal File Intake.** Fix before claiming architecture-compliant P&ID ingestion.
2. **P&ID output is ledger-recorded but not graph-committed.** Add candidate conversion and gated World Model promotion.
3. **Projection atomicity across stores is incomplete.** Add transaction/coordinator/replay semantics before large-scale ingestion.
4. **P&ID runtime qualification is environment-dependent.** Local detector weights, OCR/vision dependencies, model identities, and no-egress evidence must be supplied and measured.
5. **The signed refinery pack remains a policy boundary.** Do not promote engineering drawing semantics or authoritative equipment facts without an accepted pack and review policy.
6. **Frontend surface is incomplete for knowledge administration and P&ID review.** Do not bypass the Node by reading local stores from React/Tauri.
7. **Copyright/licensing and clearance need operational decisions.** External standards and real plant records must have storage/use authority before ingestion.
8. **Performance is a measured acceptance concern.** Large P&IDs, OCR, embeddings, reranking, and graph extraction need bounded resource admission and serial fallback on constrained hardware.

## 11. Recommended first vertical slice

Do not begin with the full corpus. Build this narrow but representative slice first:

```text
synthetic scanned inspection report
  + synthetic SOP PDF/DOCX
  + equipment_register.csv
  + line_list.csv
  + one P&ID PNG
  -> File Intake
  -> image/OCR evidence + text retrieval
  -> equipment graph + P&ID candidate graph
  -> review and World Model commit
  -> hybrid query
  -> deterministic summary
  -> verified approval-note DOCX
  -> desktop trace + replay + no-egress evidence
```

This slice proves the actual product boundary: one intake path, separate visual/text/graph projections, controlled retrieval, P&ID topology, provenance, verification, deterministic deliverables, and an inspectable audit trail. Expand the corpus and input coverage only after this slice passes.

## 12. Governing documents

- `docs/foundations/01_architecture_design.md`
- `docs/foundations/02_domain_pack_framework.md`
- `docs/foundations/03_file_intake_layer.md`
- `docs/foundations/04_world_model_engine.md`
- `docs/foundations/05_knowledge_and_retrieval_engine.md`
- `docs/foundations/06_orchestration_engine.md`
- `docs/intake/pid.md`
- `docs/assurance/memory_and_audit_ledger.md`
- `docs/assurance/sovereignty_and_security.md`
- `docs/delivery/deliverable_engine.md`
- `docs/runtime/backend_development_plan.md`
- `docs/desktop/architecture/frontend_architecture.md`
- `docs/desktop/architecture/frontend_contracts_and_state.md`
- `docs/desktop/validation/frontend_validation_plan.md`
- `docs/operations/two_endpoint_bge_runbook.md`
