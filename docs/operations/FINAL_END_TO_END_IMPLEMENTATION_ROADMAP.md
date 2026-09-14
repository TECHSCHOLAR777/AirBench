# AirBench Final End-to-End Implementation Roadmap

Date: 2026-09-14  
Goal: run one real task from remote GPU startup and desktop intake through model routing, retrieval, verification, deliverable review, and replay without hidden failures.

## 1. Executive conclusion

The repository contains a substantial prototype, but the full real-model path is not yet proven.

The dependency order is:

1. deterministic runtime lifecycle;
2. remote GPU/tunnel readiness;
3. model qualification and routing admission;
4. real model-backed task execution;
5. complete knowledge-base ingestion and hybrid retrieval;
6. desktop readiness/error/evidence integration;
7. restart, recovery, security, and no-egress evidence;
8. real measurements and research tables.

The missing knowledge base is not the cause of the original task stopping at approval/planning. It is required for grounded local-manual, historical, image, and P&ID-context questions, but not for task creation, file intake, planning, authority approval, or a task-local deliverable.

## 2. Current status

| Area | Status | Remaining blocker |
|---|---|---|
| Node/API | Mostly implemented | Live execution depends on healthy/admitted models |
| Durable ledger | Implemented | Full restart/replay with all projections is not proven |
| File Intake | Implemented for core paths | Needs real multi-format corpus and recovery evidence |
| Text/table retrieval | Partial | No judged corpus; BGE/reranker runtime and quality unproven |
| Image evidence store | Partial | Real image corpus, preview, filtering, and supersession evidence remain |
| P&ID | Partial | Real vision runtime, graph review UI, labelled drawings, accuracy data |
| World Model graph | Partial | Full promotion/reconciliation/restart proof remains |
| Model serving | Configured, not operationally proven | Live run reported both targets unhealthy/not_ready |
| Qualification | Partial | Placeholder benchmark data, pending signatures, unqualified notes |
| Node execution | Implemented, live-blocked | No model target admitted during live worker step |
| Desktop UI | Partial | Real Tauri/live-Node run, readiness/failure UX, P&ID review |
| Remote GPU runbook | Present | Needs automated preflight and clear failure reasons |
| Research measurements | Not ready | No repeated generation, VRAM, concurrency, labelled quality, or ablation run |

## 3. Reproduced failures and their causes

### 3.1 Missing human authority

The supplied log showed:

- task created;
- task authorized;
- plan produced;
- plan approval returned HTTP 500;
- autonomy rejected the operator because role human_reviewer was missing.

This was a Node configuration/control-flow defect, not a knowledge-base problem. The demo launcher now explicitly sets the reviewer role and blank inherited role variables default safely.

### 3.2 Task identity collision

New tasks were derived only from principal, request text, and domain pack. Two different submissions with the same request could therefore reuse one task ID and collide in the durable ledger.

This has been fixed: API-created task IDs are now derived from the command idempotency key. A retry replays the same task; a new command creates a new task.

### 3.3 Invalid upload probe

A live multipart probe declared a byte count different from the actual uploaded bytes. File Intake correctly returned source_size_mismatch. Authorization then correctly refused because no task-bound manifest existed.

This is expected contract enforcement. The client must declare the exact uploaded byte size.

### 3.4 Model execution failure

After valid upload, authorization, and planning, live execution reached the worker. The worker could not admit a model target because both endpoint readiness checks were unhealthy/not_ready.

This is currently the highest-priority live blocker. It is caused by remote containers/tunnel/model readiness or qualification, not by an empty knowledge base.

### 3.5 Port collision

Starting another Node while an older Node process still owned port 8765 produced Windows error 10048. The project needs explicit one-Node lifecycle and fresh/resume state modes.

## 4. Ordered implementation plan

### Phase 0 — Clean runtime lifecycle

Problems:

- stale Node processes can remain alive;
- second launches fail on port 8765;
- old SQLite/WAL/SHM, corpus, artifact, world-model, and decision state can contaminate a new demo;
- startup assumes dependencies instead of proving them.

Implement:

1. Add a preflight that reports port owner, Node identity, protocol, ledger head, store paths, model readiness, and execution mode.
2. Make start_demo_node.ps1 refuse a port already owned by another process and print the process ID.
3. Add FreshDemo and ResumeDemo modes.
4. Print a machine-readable startup summary.
5. Make the UI show Node starting, ready, or degraded.

Done when:

- two launches cannot silently compete;
- fresh runs cannot see old tasks;
- resume runs prove replayable state;
- UI shows the actual Node identity and readiness.

Primary files:

- scripts/start_demo_node.ps1
- src/airbench/node/server.py
- src/airbench/node/api.py
- apps/desktop/src/platform/node/
- docs/operations/STARTUP_GUIDE.md

### Phase 1 — Remote GPU and SSH tunnel

The required topology is:

~~~text
Remote Docker vLLM containers
  -> remote ports 8001/8002
  -> SSH tunnel
  -> laptop ports 18001/18002
  -> AirBench Node model bindings
~~~

Before starting the Node:

~~~bash
ssh mmmut-server
docker start airbench-vllm-e2b airbench-vllm-12b
docker ps --filter name=airbench-vllm
nvidia-smi
curl -f http://127.0.0.1:8001/health
curl -f http://127.0.0.1:8002/health
curl -s http://127.0.0.1:8001/v1/models
curl -s http://127.0.0.1:8002/v1/models
~~~

Keep the tunnel open:

~~~powershell
ssh -N -L 127.0.0.1:18001:127.0.0.1:8001 -L 127.0.0.1:18002:127.0.0.1:8002 mmmut-server
~~~

Verify locally:

~~~powershell
Invoke-WebRequest http://127.0.0.1:18001/health
Invoke-WebRequest http://127.0.0.1:18002/health
Invoke-RestMethod http://127.0.0.1:18001/v1/models
Invoke-RestMethod http://127.0.0.1:18002/v1/models
~~~

Implement:

1. Add a model endpoint preflight script.
2. Check HTTP health and exact served model ID, not only TCP reachability.
3. Map served model ID to signed roster target ID.
4. Verify revision, quantization, adapter, and container digest.
5. Expose a reason for unhealthy, not_ready, model mismatch, adapter mismatch, qualification missing, and ready.
6. Prevent approval/execution admission when the required model lane is not ready.

Done when both endpoints report healthy/ready with the expected served model names and route trace records the selected target.

Primary files:

- scripts/start_demo_node.ps1
- src/airbench/node/model_serving.py
- src/contracts/adapters/vllm_adapter.py
- src/airbench/node/server.py
- src/airbench/node/task_execution.py
- apps/desktop/src/platform/node/

### Phase 2 — Model qualification and placeholders

Unresolved placeholder/provisional groups include:

- profiles/hardware/target_96gb_vram.yaml;
- benchmarks/model_hardware_results.yaml;
- benchmarks/quantization_matrix.yaml;
- benchmarks/backend_compatibility_matrix.yaml;
- qualifications/model_qualification_matrix.yaml;
- models/roster/v0/model_roster.yaml;
- models/roster/demo/two_endpoint_roster.yaml.

Examples:

- REPLACE_WITH_MEASURED;
- pending signatures;
- pending container digests;
- pending fixture hashes;
- UNQUALIFIED CANDIDATE notes;
- zero/provisional quality values;
- missing latency, throughput, VRAM, KV-cache, concurrency, and fallback values.

For the two demo targets only:

1. Capture container digest, model revision, served model name, tokenizer/chat-template hashes, GPU UUID/VRAM, driver, and CUDA.
2. Run repeated tests for first-token latency, end-to-end latency, throughput, error rate, stable concurrency, failure threshold, CPU/RAM/VRAM/scratch.
3. Run structured-output, inspection-review, citation, injection-resistance, cancellation, timeout, and no-egress tests.
4. Run scripts/airbench_qualify.py with complete evidence.
5. Sign only measured demo certificates.
6. Disable unmeasured roster entries rather than treating them as qualified.

Done when the demo roster and qualification matrix contain no unresolved runtime fields, the target is qualified for the exact role/task kind, and routing records its certificate.

### Phase 3 — Real model-backed task

Current path:

~~~text
desktop composer
 -> task.create
 -> task-bound File Intake
 -> task.authorize
 -> deterministic plan/hardware admission
 -> task.approve_plan
 -> autonomy authorization
 -> model route
 -> worker result
 -> verification
 -> deliverable render
 -> artifact review/sign-off
~~~

Implement/verify:

1. Preflight capability, risk class, hardware profile, endpoint readiness, qualification, and authority before approval.
2. Commit approval only after preflight succeeds.
3. Convert unexpected post-approval failures into typed terminal task states.
4. Record target ID, human-readable model, certificate, route decision, fallback, and readiness reason.
5. Run against live vLLM, not only fake backends.
6. Ensure UI polling stops on completed, failed, blocked, or needs-review states.

Done when one real uploaded inspection file produces a real model response, a committed verified artifact, visible selected-model information, and review/sign-off.

### Phase 4 — Knowledge base ingestion and storage separation

The stores must remain separate:

| Store | Owns |
|---|---|
| Local Intake/artifact store | Original files, rendered pages, images, OCR regions, overlays, GraphML/JSON, safe previews |
| Text/table vector store | Chunks, embeddings, provenance, clearance, revisions |
| SQLite World Model graph | Candidate/verified entities, facts, relations, revisions, conflicts |
| Decision store | Comparable decisions and outcomes |
| Append-only ledger | Events, authorization, provenance, hashes, replay |

Existing partial implementation:

- guarded bulk ingestion;
- Chroma/SQLite vector store;
- text/table chunking;
- image/source artifacts;
- P&ID adapter and graph candidate path;
- hybrid search API;
- desktop Knowledge search and folder ingestion;
- mixed-source supersession;
- per-file partial ingestion reporting.

Remaining:

1. Create a sanitized corpus with digital/scanned PDF, DOCX, XLSX, CSV, PNG/JPEG, P&ID, superseding revision, malformed input, low-confidence input, and restricted input.
2. Verify bulk and task uploads use the same File Intake Layer.
3. Verify text/table chunks, image artifacts, and P&ID graph candidates land in their correct stores.
4. Commit graph facts only after verification, consistency, autonomy, and review gates.
5. Add ingestion resume/retry and projection repair.
6. Add Node projections for counts, source/revision state, vector/graph health, and review queue.
7. Enforce source, revision, clearance, and taint filters on every search mode.
8. Return explicit no_match, needs_review, degraded, and unavailable states.
9. Ledger ingestion, projection, retrieval, and graph-query events.
10. Prove restart/replay for every projection.

Done when the UI can ingest the corpus, text search returns cited text/table evidence, image search returns regions, graph search returns gated relations, and hybrid search preserves the evidence types separately.

### Phase 5 — P&ID governed workflow

Existing partial modules:

- src/airbench/intake/pid/adapter.py;
- pipeline.py;
- symbol_detector.py;
- text_ocr.py;
- line_detector.py;
- topology_builder.py;
- exporters.py;
- signed pid_legend.yaml;
- PID API and integration tests.

Remaining:

1. Ensure normal File Intake manifests are the P&ID byte source.
2. Constrain raw-file fallback paths.
3. Preserve root-canvas coordinates, tile transforms, source regions, model identity, confidence, and artifacts.
4. Stage every symbol/text/line/junction/connector/edge as a candidate.
5. Gate candidates through verification, consistency, autonomy, and human review.
6. Expose original drawing, overlays, crops, graph export, unresolved regions, and review state.
7. Configure Ultralytics/EasyOCR in a writable offline settings directory.
8. Add seam, false-crossing, ambiguous-symbol, missing-weight, and OCR-unavailable tests.
9. Supply labelled drawings before claiming mAP, CER/WER, edge F1, coordinate error, or graph edit distance.

Done when a reviewer can navigate from a graph edge to drawing coordinates and ledger evidence, and no candidate becomes an engineering fact before the gates pass.

### Phase 6 — Backend recovery, security, and persistence

Remaining:

- projection coordinator for ledger/vector/artifact/graph consistency;
- repair/rebuild commands;
- durable ingestion-job state;
- terminal model/router/verification failure projections;
- retry/fallback evidence under health changes;
- complete ingestion/retrieval/P&ID ledger event catalog;
- clearance filtering before vector/graph exposure;
- provenance retention through all transformations;
- no-egress checks over normal/failure/restart/OCR/embedding/reranking/model paths;
- bounded resource admission;
- stale task reconciliation after restart;
- idempotent retry tests for every mutating command.

Done when every error is typed and terminal/recoverable, no partial commit is silent, no local component requires external network, and every consequential action has ledger/provenance evidence.

### Phase 7 — Desktop UI and backend integration

Existing:

- clean task composer;
- internal ID/hash hiding;
- model route display support;
- task refresh and artifact refresh;
- Knowledge search;
- native corpus folder selection;
- contract/accessibility checks.

Remaining:

1. Add startup/readiness surface with Node, pack, models, retrieval, graph/artifact store, and execution status.
2. Add actionable errors for tunnel, model readiness, qualification, intake, no evidence, P&ID dependency, clearance, and ledger failures.
3. Use readable phases: received, reading sources, preparing plan, waiting approval, running with model, checking, preparing document, ready review, completed/failed/needs review.
4. Add ingestion progress and per-file failure counts.
5. Add text/image/table/graph evidence tabs.
6. Add P&ID review for original image, overlays, candidates, unresolved regions, and relations.
7. Add artifact preview, verification checklist, source drawer, and sign-off.
8. Test reconnect, sequence gap, resync, stale task, and Node restart.
9. Run real Tauri/WebDriver against the live Python Node.

Done when a non-technical user can understand state without hashes, model outages differ from empty KB, and UI never claims success before Node commitment.

### Phase 8 — Measurements and research readiness

Do not fill placeholders with estimates.

Measure:

- GPU identity/UUID/VRAM/driver/CUDA;
- CPU/RAM/scratch;
- model load/unload;
- first-token and end-to-end latency;
- prompt/generation throughput;
- KV cache;
- concurrency and failure threshold;
- resource usage;
- fallback and routing;
- structured output;
- provenance/citation retention;
- injection resistance;
- cancellation/timeout;
- retrieval precision/recall/nDCG;
- P&ID symbol/OCR/topology metrics;
- end-to-end completion/review/escalation.

Research ablation tables remain unavailable until identical labelled inputs are run with and without each control.

### Phase 9 — Final acceptance run

Fresh run:

1. Stop all old Node/UI processes.
2. Start remote containers.
3. Verify remote health and served models.
4. Open SSH tunnel.
5. Verify local forwarded health and served models.
6. Start a fresh Node with explicit reviewer role and execution enabled.
7. Wait for both model lanes ready.
8. Start desktop and verify the approved profile.
9. Ingest the sanitized corpus.
10. Verify vector/artifact/graph/decision/ledger counts.
11. Create a task with a new command ID/idempotency key.
12. Upload a valid file with exact byte count.
13. Authorize and wait for plan ready.
14. Approve only after model preflight passes.
15. Observe model selection and route trace.
16. Wait for verification and rendering.
17. Inspect sources, graph/P&ID evidence, and artifact.
18. Sign off.
19. Export ledger/evidence.

Resume run:

1. Stop and restart Node.
2. Replay ledger.
3. Reopen every projection.
4. Verify task, evidence, artifact, graph, and retrieval revisions.
5. Resume or safely fail according to committed state.

Final acceptance requires:

- both models healthy and admitted;
- one real model-backed task complete;
- selected model visible;
- intake/retrieval/graph/verification/deliverable/ledger linked;
- separate text/image/table/P&ID stores;
- useful UI state;
- restart/replay;
- no-egress;
- no unresolved runtime placeholder for the selected lane;
- typed actionable failures;
- empty KB produces no_match/needs_review rather than a stuck task;
- reproducible evidence bundle.

## 5. Knowledge-base answer

Not required for:

- Node startup;
- model endpoint health;
- authentication;
- task creation;
- file upload/intake;
- task authorization;
- plan generation;
- hardware admission;
- human reviewer authority;
- a basic task-local deliverable.

Required for:

- local-manual/SOP questions;
- historical decision lookup;
- image evidence retrieval;
- P&ID historical context;
- hybrid text/image/graph questions;
- permanent-corpus evidence-backed deliverables.

~~~text
No knowledge base != reason for the original stuck approval.
No healthy/admitted model endpoint = reason the live task stopped during execution.
No labelled corpus = reason research accuracy tables cannot be filled honestly.
~~~

## 6. Primary files by workstream

| Workstream | Paths |
|---|---|
| Startup/runtime | scripts/start_demo_node.ps1, scripts/run_two_endpoint_demo.py, docs/operations/STARTUP_GUIDE.md |
| Model serving/routing | src/airbench/node/model_serving.py, src/contracts/adapters/vllm_adapter.py, models/roster/, qualifications/ |
| Node/API/execution | src/airbench/node/api.py, server.py, task_execution.py, task_planning.py |
| File Intake | src/airbench/intake/, src/airbench/node/intake_gateway.py |
| Knowledge | src/airbench/knowledge/, src/airbench/node/knowledge_gateway.py |
| P&ID | src/airbench/intake/pid/, src/airbench/node/api.py, packs/refinery_psu_v0/pid_legend.yaml |
| World Model | src/airbench/knowledge/world_model.py, graph_store.py, entity_extractor.py |
| Ledger/provenance | src/contracts/provenance/, src/contracts/execution/, event catalog |
| Deliverables | src/airbench/delivery/, src/airbench/node/deliverable_gateway.py |
| Desktop | apps/desktop/src/, apps/desktop/src-tauri/src/, apps/desktop/validation/ |
| Evaluation | acceptance/, benchmarks/, profiles/hardware/, scripts/airbench_qualify.py |

## 7. Exact next-session order

1. Clean old Node processes and choose FreshDemo or ResumeDemo.
2. Start and verify both remote containers.
3. Open and verify the SSH tunnel.
4. Make both targets healthy and qualified.
5. Run one real model-backed task to reviewed deliverable.
6. Add startup/model preflight so the same failure cannot reach deep execution.
7. Ingest the sanitized multi-input corpus.
8. Verify text, image, table, P&ID, vector, graph, and hybrid queries.
9. Complete UI readiness/error/evidence/P&ID surfaces.
10. Prove restart/replay/no-egress.
11. Replace measured placeholders for the selected lane.
12. Run final acceptance and update the research paper only from captured evidence.

