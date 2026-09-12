# AirBench-Deep: 5 Code-Doable Issues + Pipeline Coverage Analysis

## Understanding Checkpoint

All changes go to **AirBench-Deep** (`c:\Users\ALG\Downloads\SIH2026\AirBench-Deep`), never AirBench.

### Governing invariants
- Orchestrator owns state; models never drive loops
- Facts retain source/confidence/clearance/taint
- Ledger is append-only and signed
- Desktop never computes authoritative values or bypasses Node
- All record views come from Node-authoritative data

---

## Pipeline Coverage: Ingestion Whole-Pipeline Status

The AirBench pipeline has **6 layers** visible in the README/architecture diagram and `pipeline.png`:

| Layer | Module | Status |
|-------|--------|--------|
| **File Intake Layer** | `src/airbench/intake/layer.py` (46 KB) + `vision.py` | ✅ Implemented — manifest, trust boundary, taint, clearance, safe repr. OCR/vision adapter present but requires local adapter for real scans (#67). |
| **World Model & Knowledge** | `src/airbench/knowledge/world_model.py` (17 KB) + `retrieval.py` (22 KB) | ✅ Implemented — source-bounded facts, retrieval pipeline, confidence, provenance. |
| **Deterministic Orchestrator** | `contracts/models.py` + `Orchestrator` class in `contracts/__init__.py` | ✅ Implemented — state machine, transitions, ledger. |
| **Team Runtime & Orchestration** | `src/airbench/orchestration/team_runtime.py` (50 KB) + `worker_context.py` (22 KB) | ✅ Implemented — parallel/pipelined/serial_virtual_team modes, barriers, handoffs. **HardwareProfile admission gate is NOT wired into plan formation** (#34). |
| **Model Router** | `src/airbench/model_store.py` (14 KB) + contracts adapters | ✅ Contracts complete, live calls on hold by instruction (#10). |
| **Deliverable Engine** | `src/airbench/delivery/engine.py` (29 KB) | ✅ Implemented — DOCX, XLSX, PPTX templates, deterministic value bindings. |
| **Verification** | `src/airbench/verification/runner.py` (26 KB) + `gate.py`, `autonomy.py` | ✅ Implemented — verification rules, autonomy gate. |
| **Node API** | `src/airbench/node/api.py` (77 KB) | ✅ Implemented — all endpoints except `approve_artifact`/`return_for_revision` (#80). |
| **Desktop Frontend** | `apps/desktop/src/app/App.tsx` (99 KB) | ✅ Mostly implemented. Missing: artifact approve/return (#80), Task History view (#82), Node settings detail (#83). |
| **WDIO Validation** | `apps/desktop/validation/python_node_server.py` | ✅ Real Node server wired. Missing: replay evidence JSON write (#66). |

### What is NOT yet end-to-end complete

1. **HardwareProfile → execution mode decision** is hardcoded as `serial_virtual_team` in the validation harness. The `HardwareProfile` contract and `ResourceScheduler.admit()` code exist and work, but the plan-formation code in `local_task_run.py` always uses a synthetic profile. **#34** wires real HardwareProfile JSON into the admission gate.
2. **Artifact approve/return** — `POST /api/v1/tasks/{id}/review` exists in `api.py` (calls `orchestrator.request_review`). But there is **no** `approve_artifact` / `return_for_revision` command. The spec in the issue says `{type: approve_artifact}` — this doesn't yet exist as an orchestrator transition either. The frontend `ProofInspectorPanel.tsx` shows the `ArtifactReviewPanel` but has no approve/return buttons. **#80** adds this end-to-end.
3. **Task History screen** — `homeWorkSummary.ts` builds a summary from a single current `TaskProjection`. There is no multi-task history screen or paged projection. **#82** adds a `TaskHistoryView`.
4. **Node settings detail** — `NodeSettingsView` shows the profile list and readiness panel but not the live handshake fields (node_identity, protocol_version, clearance_context, domain_pack_ref, ledger_head_ref). **#83** adds these.
5. **Replay evidence file** — `python_node_server.py` doesn't write a JSON file at task completion. The `AIRBENCH_WDIO_REPLAY_EVIDENCE_PATH` env var is referenced in WDIO test infrastructure but the server never creates the file. **#66** fixes this.

---

## Proposed Changes

### #66 — Cursor replay evidence file (30 min) — SMALLEST, FIRST

#### [MODIFY] [python_node_server.py](file:///c:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop\validation\python_node_server.py)

- At task completion (`approve_plan` success), compute `hasGap`, `hasDuplicate`, `sequenceNumbers` from the ledger events for the task.
- Read `AIRBENCH_WDIO_REPLAY_EVIDENCE_PATH` from env.
- Write the JSON file atomically.
- Guard: only write if `AIRBENCH_WDIO_REPLAY_EVIDENCE_PATH` is set.

---

### #80 — Artifact approve/return actions (2h)

> [!IMPORTANT]
> The `POST /api/v1/tasks/{id}/review` endpoint (`request_review`) exists and transitions the task to `human.review.required`. The issue refers to approve/return **of an artifact**, which maps to a `human.signoff` transition in the orchestrator. We need to add:
> 1. Backend: `approve_artifact` and `return_for_revision` methods to `NodeApiService` + routes.
> 2. Frontend: buttons on `ArtifactReviewPanel` that call `sendTaskCommand` via `nodeCommands.ts`.

#### [MODIFY] [api.py](file:///c:\Users\ALG\Downloads\SIH2026\AirBench-Deep\src\airbench\node\api.py)
- Add `approve_artifact(subject, task_id, payload)` method — calls `orchestrator.signoff()` (the `human.signoff` transition) with `artifact_id` and `decision="approved"`.
- Add `return_for_revision(subject, task_id, payload)` method — calls `orchestrator.request_review()` or a re-review transition with `artifact_id` and `decision="revision_requested"`.
- Register `POST /api/v1/tasks/{task_id}/approve-artifact` and `POST /api/v1/tasks/{task_id}/return-artifact` routes.

#### [MODIFY] [nodeCommands.ts](file:///c:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop\src\platform\node\nodeCommands.ts)
- Add `approveArtifact(profile, taskId, artifactId, expectedSequence)` function.
- Add `returnArtifactForRevision(profile, taskId, artifactId, reason, expectedSequence)` function.
- Both POST to new backend routes with proper `NodeCommandEnvelope` structure.

#### [MODIFY] [ProofInspectorPanel.tsx](file:///c:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop\src\components\ProofInspectorPanel.tsx)
- Add `onApproveArtifact` and `onReturnArtifact` props.
- In `ArtifactReviewPanel`, show Approve and Return buttons when `approvalState === "needs_review"`.
- Disable buttons while command is in-flight.

#### [MODIFY] [App.tsx](file:///c:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop\src\app\App.tsx)
- Add `artifactCommandState` and `artifactCommandResult` state variables.
- Wire `onApproveArtifact` and `onReturnArtifact` handlers.

---

### #34 — HardwareProfile admission gate (2-3h)

> [!IMPORTANT]
> The `LocalTaskExecutionCoordinator.prepare()` in `local_task_run.py` always creates a **synthetic** `HardwareProfile`. The fix reads the real profile from `hardware_profile_96gb_valid.json` fixture (or an env-configured path), validates it, and uses it in `ResourceScheduler.admit()`. The admission decision (`serial_virtual_team` vs `parallel`) then comes from `profile.supported_execution_modes` + `safe_parallel_slots`, not from a hardcoded string.

#### [MODIFY] [local_task_run.py](file:///c:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop\validation\local_task_run.py)
- Add optional `hardware_profile_path: Path | None` to `LocalTaskExecutionCoordinator.__init__`.
- In `prepare()`, if a path is supplied, load + validate `HardwareProfile.from_dict(json.loads(...))`, else fall back to the existing synthetic profile.
- Choose `requested_mode` based on `profile.supported_execution_modes` and `safe_parallel_slots > 1` (if both `parallel` is supported and `safe_parallel_slots >= 2`, use `parallel`; otherwise `serial_virtual_team`).
- Record `hardware_profile_ref = profile.profile_id` in the admission.

#### [MODIFY] [python_node_server.py](file:///c:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop\validation\python_node_server.py)
- Add `--hardware-profile` CLI arg that accepts an optional path to a HardwareProfile JSON.
- Pass it through to `LocalTaskExecutionCoordinator`.

---

### #82 — Task History and Audit Ledger views (2-2.5h)

#### [NEW] [TaskHistoryView.tsx](file:///c:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop\src\features\tasks\TaskHistoryView.tsx)
- A dedicated screen showing past task summaries.
- Uses `HomeWorkSummary` type from `homeWorkSummary.ts`.
- Shows: title, status badge, ledger head ref, last activity, verdict.
- Accepts a `tasks: HomeWorkSummary[]` prop.
- Shows an honest "History comes from the Node" placeholder when tasks is empty.

#### [MODIFY] [App.tsx](file:///c:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop\src\app\App.tsx)
- Add `taskHistory: HomeWorkSummary[]` state (accumulated from seen projections).
- When `state.screen === "history"`, render `<TaskHistoryView>` instead of the current `RecordGatewayView`.
- Accumulate completed tasks into `taskHistory` when `taskProjection.status` is terminal.

---

### #83 — Node settings admin screen (1h)

#### [MODIFY] [App.tsx](file:///c:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop\src\app\App.tsx)
- In `NodeSettingsView`, when `connection.state === "connected"`, add a display-only `NodeIdentityCard` showing:
  - Node identity
  - Protocol version
  - Clearance context
  - Authenticated subject
  - Domain-pack ref
  - Ledger event ref (from the handshake)
  - Sovereignty status
- All data comes from `connection` (the `NodeConnectionView`), which is already populated from the handshake response.

---

## Verification Plan

### Automated Tests
```bash
cd c:\Users\ALG\Downloads\SIH2026\AirBench-Deep
.venv\Scripts\python.exe -m pytest tests/test_node_api.py tests/test_contracts.py tests/test_m10_acceptance.py -x -q
cd apps/desktop && npm run check:contracts
```

### Manual Verification
- After #66: run `python_node_server.py` and check that a JSON file appears at `AIRBENCH_WDIO_REPLAY_EVIDENCE_PATH` after plan approval.
- After #80: see Approve/Return buttons in the artifact review panel with `approvalState === "needs_review"`.
- After #34: pass `--hardware-profile tests/fixtures/hardware_profile_96gb_valid.json` to the server; plan review shows `parallel` mode (since `safe_parallel_slots: 2` in the fixture).
- After #82: navigate to History screen; see completed task in the list.
- After #83: connect a Node; settings screen shows the identity card.

---

## Open Questions

> [!NOTE]
> **#80 (approve_artifact)**: The orchestrator contract currently has `request_review` (→ `human.review.required`) and `signoff` (→ `human.signoff`). The `signoff` transition is the approval path. The "return for revision" needs to map to a re-review or back-to-running transition. I'll use `request_review` for "return" (creates another review-required event) and `signoff` with `decision="approved"` for approve. Please confirm if a different orchestrator transition is expected.

> [!NOTE]
> **#34 (HardwareProfile)**: The fixture `hardware_profile_96gb_valid.json` has `safe_parallel_slots: 2` and `supported_execution_modes: ["serial_virtual_team", "parallel"]`. The current `AdmissionRequest` already has `requested_mode="serial_virtual_team"` hardcoded. After this fix, with the 96 GB profile, the requested mode will be `parallel` and the plan review UI will show "PARALLEL" instead of "SERIAL VIRTUAL TEAM". The WDIO smoke test checks for "SERIAL VIRTUAL TEAM" — this assertion will need updating for the 96 GB profile path, or the synthetic profile fallback remains the default for the WDIO test.
