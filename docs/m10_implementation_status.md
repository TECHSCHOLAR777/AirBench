# M10 Implementation Status

> **Issue:** [AirBench#15 — M10: Hardening, deployment, and backend-complete acceptance](https://github.com/TECHSCHOLAR777/AirBench/issues/15)
>
> **Goal:** Prove that the first backend is deployable, restartable, observable, and sovereign on a clean local node.

---

## Completion Summary

| Sub-Issue | Title | Status | Tests | Commit |
|-----------|-------|--------|-------|--------|
| M10.1 | Authenticated local endpoints & node server | ✅ DONE | 36/36 pass | `5e1f4ad9` |
| M10.2 | Offline bundle manifest & startup verification | ✅ DONE | 34/34 pass | `456e393a` |
| M10.3 | Audit views, metrics, resilience & latency tests | ✅ DONE | 26/26 pass (1 skip) | `a3bf79b3` |
| M10.4 | Final clean-node acceptance suite | ✅ DONE | 16/16 pass | `ff56877c` |

**Total M10 tests: 112 pass, 1 skip, 0 fail**

---

## M10.1 — Authenticated Local Endpoints

**Status: ✅ Implemented**

### Files Created
- [`src/airbench/node/server.py`](../src/airbench/node/server.py) — Node server entrypoint
- [`tests/test_m10_api_hardening.py`](../tests/test_m10_api_hardening.py) — 36 API hardening tests

### What Was Built
- **`NodeServerConfig`** — typed config from env vars or YAML; validates `node_identity`, `bearer_token`, `domain_pack_ref`, optional `ledger_path`
- **`run_startup_checks()`** — pre-bind checklist: config completeness, ledger path writability, signing key presence/size; returns `StartupCheckResult`
- **`_write_node_started()`** — writes sovereignty sidecar JSON (`node_started_<id>.json`) alongside the ledger file; follows M9 evidence pattern (not task ledger, which is task-scoped)
- **`build_node_app()`** — wires `EventLedger` → `Orchestrator` → `NodeApiConfig` → `NodeApiService` → FastAPI app with readiness route
- **`add_readiness_route()`** — unauthenticated `GET /api/v1/node/readiness` using raw Starlette Route to bypass FastAPI response-model validation pipeline

### Acceptance Criteria Met
- ✅ Bearer token required on all routes (401 without, 401 wrong token)
- ✅ Body size limits enforced (413 for oversized payloads)
- ✅ Malformed JSON rejected (400)
- ✅ Task-ID format validated
- ✅ Clearance ceiling enforced (403 for exceeded clearance)
- ✅ Readiness probe bypasses auth (unauthenticated, returns 200/503)
- ✅ Config integrity check (HMAC-SHA256 signing key size validation)

---

## M10.2 — Offline Bundle Manifest and Startup Verification

**Status: ✅ Implemented**

### Files Created
- [`src/airbench/node/bundle.py`](../src/airbench/node/bundle.py) — Bundle manifest and verifier
- [`tests/test_m10_bundle.py`](../tests/test_m10_bundle.py) — 34 bundle tests

### What Was Built
- **`AssetRecord`** — immutable typed record of one asset: `asset_id`, `path`, `expected_hash` (64-char hex SHA-256), `asset_type`, `required`
- **`BundleManifest`** — typed manifest listing all assets; supports:
  - `BundleManifest.build()` — hash real files and build a manifest
  - `.sign(key)` — HMAC-SHA256 sign over canonical JSON payload
  - `.verify_signature(key)` — constant-time comparison
  - `.to_json()` / `.from_json()` / `.from_file()` — full serialisation round-trip
- **`StartupVerifier`** — reads manifest, resolves paths, re-hashes each asset, checks:
  1. HMAC-SHA256 signature (if key supplied)
  2. Required assets present
  3. Hash integrity (always fails on mismatch even for optional assets — "optional" means absent is OK, not tampered)
- **`BundleVerificationResult`** — structured result with per-asset status (`ok` | `missing` | `hash_mismatch` | `not_required_ok`)

### Acceptance Criteria Met
- ✅ Backend installs and starts offline from verified assets
- ✅ Tampered asset detected even after successful signing
- ✅ Wrong signing key fails verification
- ✅ Full build → sign → export → reload → verify cycle works

---

## M10.3 — Audit Views, Metrics, and Recovery Tests

**Status: ✅ Implemented**

### Files Created
- [`scripts/run_m10_audit_view.py`](../scripts/run_m10_audit_view.py) — Offline ledger audit view CLI
- [`tests/test_m10_resilience.py`](../tests/test_m10_resilience.py) — Crash recovery, malformed input, execution mode tests
- [`tests/test_m10_latency.py`](../tests/test_m10_latency.py) — API latency smoke tests

### What Was Built

#### Audit View Script (`run_m10_audit_view.py`)
Reads a JSONL ledger export and produces:
- **Event summary table** — sequence, event_type, task_id, actor, clearance, occurred_at
- **Route trace** — all routing/model-call events grouped by task
- **Artifact hash manifest** — all `artifact.staged` and `evidence.created` events with hashes
- **Chain integrity** — `previous_event_hash` linkage verification (portable, no internal canonical form required)
- **No-egress evidence** — counts of denied vs completed egress calls; `no_egress=True` if no outbound calls
- CLI: `python scripts/run_m10_audit_view.py ledger.jsonl [--output report.json] [--format table|json]`

#### Resilience Tests
- **Crash recovery**: SQLite ledger survives close + reopen with all events and checkpoints intact
- **Idempotent side effects**: `RecoveryManager.run_once()` executes exactly once across duplicate calls
- **Uncertain side effects**: `SideEffectUncertain` raised when a reserved effect is replayed after a crash
- **Malformed input**: Binary body, truncated JSON, non-UTF8 multipart, deeply nested JSON — all rejected cleanly

#### Latency Tests (thresholds for in-memory transport)
| Endpoint | Threshold |
|----------|-----------|
| `GET /api/v1/health` | < 150 ms |
| `GET /api/v1/node/handshake` | < 150 ms |
| `POST /api/v1/tasks` | < 300 ms |
| `GET /api/v1/tasks/{id}` | < 300 ms |
| `GET /api/v1/tasks/{id}/events` | < 300 ms |
| `GET /api/v1/tasks/{id}/evidence` | < 300 ms |
| `GET /api/v1/tasks/{id}/route-trace` | < 300 ms |

Measurements written to `acceptance/m10_latency_measurements.json`.

---

## M10.4 — Final Clean-Node Acceptance Suite

**Status: ✅ Implemented**

### Files Created
- [`tests/test_m10_acceptance.py`](../tests/test_m10_acceptance.py) — 16 acceptance tests across 7 criteria

### Acceptance Criteria Verified

| Criterion | Description | Test Class |
|-----------|-------------|------------|
| A | Backend starts offline from verified config | `TestAcceptanceCriterionA` |
| B | All authenticated endpoints respond correctly | `TestAcceptanceCriterionB` |
| C | Task lifecycle API end-to-end | `TestAcceptanceCriterionC` |
| D | Ledger JSONL export and chain replay | `TestAcceptanceCriterionD` |
| E | SQLite persist + recovery | `TestAcceptanceCriterionE` |
| F | Audit view produces passing report | `TestAcceptanceCriterionFG` |
| G | All criteria pass — acceptance gate emits log | `TestAcceptanceCriterionFG` |

The **acceptance gate** (`test_fg_acceptance_gate`) runs all criteria programmatically and writes `acceptance/m10_acceptance_run.json` as machine-readable evidence. It emits `acceptance.run.completed` to the Python logger on success.

---

## Architecture Decisions

### Why no ledger events for node lifecycle?
The `EventLedger` is task-scoped — every non-`task.created` event must follow a prior `task.created` for that `task_id`. Node startup is not a task. Following the M9 sovereignty evidence pattern, node lifecycle is recorded in a signed JSON sidecar file (`node_started_<id>.json`) alongside the SQLite ledger, not in the task ledger.

### Why a raw Starlette Route for `/readiness`?
FastAPI's response-model validation pipeline intercepts `JSONResponse` returns and routes them through the custom `RequestValidationError` handler, which converts them to 400. The readiness probe is unauthenticated and must be 100% reliable. Using a raw `starlette.routing.Route` bypasses the FastAPI pipeline entirely.

### Why linkage-only chain verification in the audit view?
The `contracts` library's `event_hash` is computed over a canonical form that includes internal fields (`schema_version`, `compatibility_id`, `immutable`, etc.) that are not required in a JSONL export. Re-computing from a JSONL export would always mismatch. Linkage verification (`previous_event_hash` chain) is the safe, portable, and auditor-accessible approach.

---

## File Index

### New Source Files
| File | Purpose |
|------|---------|
| [`src/airbench/node/server.py`](../src/airbench/node/server.py) | Node server entrypoint, startup checks, sovereignty evidence |
| [`src/airbench/node/bundle.py`](../src/airbench/node/bundle.py) | Offline bundle manifest, signing, and asset verification |
| [`scripts/run_m10_audit_view.py`](../scripts/run_m10_audit_view.py) | Offline ledger audit view CLI tool |

### New Test Files
| File | Tests | Coverage |
|------|-------|---------|
| [`tests/test_m10_api_hardening.py`](../tests/test_m10_api_hardening.py) | 36 | Auth, body limits, readiness, startup, build_node_app |
| [`tests/test_m10_bundle.py`](../tests/test_m10_bundle.py) | 34 | AssetRecord, BundleManifest, StartupVerifier, integration |
| [`tests/test_m10_resilience.py`](../tests/test_m10_resilience.py) | 15+6 | Crash recovery, malformed input, execution modes, audit view |
| [`tests/test_m10_latency.py`](../tests/test_m10_latency.py) | 8+2 | Latency smoke tests + evidence export |
| [`tests/test_m10_acceptance.py`](../tests/test_m10_acceptance.py) | 16 | Clean-node acceptance gate (7 criteria) |

---

## What's Left / Follow-ups

- [ ] **Offline installer script**: A `scripts/install_offline_bundle.sh` / `.ps1` that copies assets, verifies the bundle manifest, and starts the node — not required by M10 criteria but useful for operators
- [ ] **Restart-from-checkpoint**: The `RecoveryManager.recover()` path is tested; a full restart loop (kill → reopen SQLite → resume) would complete the restartability proof but requires a process-level harness
- [ ] **Network evidence capture**: Automated network-tap evidence (e.g., `tcpdump` output) would strengthen the no-egress claim beyond ledger-level evidence
- [ ] **CI integration**: The M10 acceptance gate can be wired into the CI pipeline as a post-build step; the `acceptance/m10_acceptance_run.json` evidence file should be archived as a build artifact
