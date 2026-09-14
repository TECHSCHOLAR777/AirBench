# AirBench DeepFinal Handoff

Date: 2026-09-14  
Repository: `https://github.com/TECHSCHOLAR777/AirBench.git`  
Branch: `deepfinal`  
Worktree: `C:\Users\ALG\Downloads\SIH2026\AirBench-Deep`

## Current state

The branch is synced with `origin/deepfinal`. The latest visible commit is:

```text
ea4f0c4d feat: implement core contracts, node API, SQLite ledger, and desktop transport layer
```

Earlier completed commits include:

- `63385b91` — complete live Node execution pipeline;
- `6210e1f1` — operational status and task/query UX;
- `7e286c0a` — bound model health probes.

The worktree is not clean: `src/airbench/node/api.py` has an uncommitted ledger-failure handling change, and `.pytest-local/` is an untracked pytest temporary directory. Do not discard either without inspection.

## Completed behavior

- Backend task lifecycle is wired through create, authorize, plan, approval, execution, model call, artifact generation, and task snapshot/event refresh.
- Text-only task creation and execution are supported; a committed File Intake manifest is no longer required for a typed query.
- Node-owned autonomy approval records authority for the escalated execution action.
- Node operational projections cover hardware, model-serving health, and qualification status.
- Model-serving status distinguishes configured/ready/degraded/unavailable states.
- Live task events refresh the task workspace and route trace.
- Generated deliverable paths support DOCX, XLSX, and PPTX-related execution work; `openpyxl` and `python-pptx` are installed in the workspace runtime.
- Desktop task history is persisted locally and supports reopening/removing view entries from the UI work completed so far.
- Frontend checks and the real Python Node demo previously passed; see the evidence section below.

## Remaining scope

### Qualification and model serving

- `qualifications/model_qualification_matrix.yaml` still contains pending and replacement measurements. The gateway correctly fails closed, so targets remain `pending` until real qualification evidence is supplied.
- `scripts/airbench_qualify.py` does not yet produce every certificate criterion, including inspection accuracy, evidence faithfulness, hallucination rate, citation retention, cancellation/timeout, no-egress startup, and the required result fields.
- Model lanes remain external dependencies: vLLM containers and the SSH tunnel must be running before starting the Node.
- Restart the Node after code changes; an old PID on port 8765 previously predated the autonomy/tier changes.

### Frontend simplification/model indicator

- The requested outcome-first task UI is not fully landed yet: hashes, ledger references, event codes, and internal identifiers still appear in several normal task surfaces.
- Add a prominent human-readable `Model in use` card to the active task workspace.
- The model card must use the Node-authoritative route trace and roster `display_name`, never expose the target ID/hash, and show clear states such as selecting, active, unavailable, or no model call yet.
- The route-trace projection needs to preserve selected target information when it is nested under the routing decision payload and when it appears as a model-call `target_id`. The attempted local edit was not committed; inspect current files before reapplying.
- Move technical routing, provenance hashes, payload hashes, ledger IDs, and raw event codes behind an `Advanced details` disclosure.
- The current native white-screen report was caused by a stale Tauri process/orphaned Vite server on port 1420. Source TypeScript compiled successfully; restart the exact stale AirBench/Vite processes before launching `npm run tauri:dev`.

### Other known product gaps

- Harden autonomy approval to assert the pack's `required_human_authority` role instead of relying only on the authenticated subject.
- Share one Node operational projection across `HardwareCard`, `ModelRoster`, and `NodeReadinessPanel` without redundant fetches.
- Remove or reconnect the unused `buildNodeReadiness().operational` calculation.
- Improve the model-serving failure copy so HTTP 503/degraded is not shown as “Not supplied”.

## Governing documents and contracts

Read before continuing:

- `README.md`
- `docs/README.md`
- `docs/foundations/01_architecture_design.md`
- `docs/foundations/02_domain_pack_framework.md`
- `docs/runtime/backend_development_plan.md`
- `docs/operations/agent_development_workflow.md`
- `docs/desktop/README.md`
- `docs/desktop/architecture/frontend_architecture.md`
- `docs/desktop/architecture/frontend_contracts_and_state.md`
- `docs/desktop/design/frontend_design_system.md`
- `docs/desktop/design/frontend_screen_specification.md`
- `docs/desktop/validation/frontend_validation_plan.md`

Relevant contracts include `src/contracts/models.py`, the Node API projections in `src/airbench/node/api.py`, generated frontend contracts in `apps/desktop/src/generated/core_contracts.ts`, and the Tauri transport types in `apps/desktop/src-tauri/src/node_transport.rs`.

## Evidence

Previously recorded validation:

- Full Python suite passed with six skips and one existing deprecation warning.
- Focused Node/API tests passed for node API, intake, model serving, autonomy, hardware/qualification, and deliverable formats.
- Frontend Vitest passed: 31 test files, 177 tests.
- `npm run check:ui` passed.
- `npm run check:egress` passed.
- TypeScript compilation passed with `npx tsc -b --pretty false`.
- The real two-endpoint demo reached model-serving ready state, executed a text-only task, returned `needs_review`, produced artifacts, and recorded model-call route events.

The full Vite build could not be rerun in the restricted agent shell because esbuild was denied access to a parent directory. This is an environment restriction; run the build in a normal developer PowerShell session.

## Security and deployment risks

- UI must connect only to the AirBench Node; it must never call model endpoints directly.
- Model and file content remain untrusted. Keep parsing and authoritative calculations in backend-owned layers.
- Qualification must remain fail-closed; do not mark a target qualified by UI inference or placeholder measurements.
- Preserve provenance, clearance, taint, and ledger references even when hiding technical details from the default UI.
- Do not commit local SQLite files, credentials, temporary pytest directories, or model-serving secrets.

## Next smallest action

1. Inspect `git diff` and decide whether the uncommitted `api.py` ledger-failure catch belongs in the next commit.
2. Implement and test a pure frontend model-status/display-name projection from the Node route trace.
3. Hide technical identifiers from the default task view behind `Advanced details`.
4. Run `npm test`, `npm run check:ui`, `npm run check:egress`, `npm run build`, and the real Node demo.
5. Commit only intentional source changes and push `deepfinal`.
