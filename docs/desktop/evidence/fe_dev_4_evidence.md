# FE-DEV-04 evidence record

Status: implementation slice complete and closed. The local Python-Node integration is now verified through the task-bound File Intake path. Issue #123 remains open for the complete desktop vertical slice, real execution, generated output, and release evidence.

## Delivered slice

- Home now collects an outcome, bounded title, optional project reference, deliverable type, priority, and optional deadline.
- A selected file is handed to the existing query-upload path only after Node task creation. Rust sends the native selection token and Node-issued task ID; the returned File Intake manifest reference is reconciled into the authoritative task snapshot.
- The UI does not parse, OCR, inspect, execute, or reinterpret file bytes.
- A manifest is treated as ready only when both OCR and vision statuses are terminal success or explicitly not applicable. Pending or running work remains processing, and failed, unavailable, or unknown statuses remain partial; the UI does not request or display a preview as if those results were complete.
- The webview re-validates the runtime payload returned by the native intake commands before it becomes React state. Intake identity, file bounds, hashes, statuses, clearance, taint, preview references, source regions, confidence, safe text limits, artifact blocks, and ledger references fail closed when malformed or over-cleared.
- The webview re-validates Node task snapshots before projection. Snapshot identity and clearance must match the approved Node, and every evidence and fact record must retain its wire envelope, source provenance, confidence, clearance, taint, and ledger reference. Evidence content hashes must be SHA-256 digests. The creation receipt also cross-checks the task envelope, snapshot task identity, command receipt, and shared ledger reference.
- The Node handshake supplies the domain-pack reference. The UI carries it in the command, while the Node rejects a value that differs from its configured pack.
- `task.create` is sent through the Rust-owned typed command bridge. The Python Node validates the command and creates the task envelope. Task-bound query upload then commits the evidence event through the same ledger and exposes the intake reference in the authoritative snapshot.
- The Home screen renders the Node acceptance receipt with task ID, task state, ledger reference, and sequence. It does not claim that the task has completed; later authoritative task state must arrive through the event stream.

## Contracts and files

- `src/contracts/models.py` and `src/contracts/execution/orchestrator.py` define the bounded task metadata and creation inputs.
- `src/airbench/node/api.py` exposes the Node-selected domain pack in the handshake and applies it as the authority for task creation.
- `apps/desktop/src/features/tasks/taskComposer.ts` builds and validates the typed command without selecting models, tools, or sector behavior.
- `apps/desktop/src/app/App.tsx` owns only presentation state and invokes the existing Node and File Intake bridges.
- `apps/desktop/src/features/intake/intakeBridge.ts` validates native IPC responses before exposing them to presentation state.
- `apps/desktop/src-tauri/src/node_transport.rs` carries the typed handshake domain-pack field without exposing arbitrary URLs or credentials to the webview.

## Verification

- `python -m pytest -q tests/test_node_api.py tests/test_contracts.py`: 24 passed.
- `npm test -- --run`: 119 passed across 22 test files.
- `npm run build`: passed.
- `npm run check:contracts`: passed.
- `npm run check:ui`: passed, including the authored-source accessibility contract.
- `npm run check:egress`: passed; no network-capable frontend API or external resource URL was found.
- `npm run check:tauri-config`: passed.
- `git diff --check`: passed.
- `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`: 14 passed.
- `npm run validate:node`: passed local and pinned internal-HTTPS fixture coverage. Run: `AirBenchNodeValidation-20260907-015945-fb13075cb05e4b8f8fc916bb49847522`.
- `npm run validate:python-node`: passed against the real Python `NodeApiService`, including task-bound intake, safe preview, task snapshot linkage, distinct access ledger references, and SHA-256 download verification. Run: `AirBenchPythonNodeValidation-20260910-034410-63b08a12b162440d9746b42e1541456b`.

## Remaining gates

- Run the local desktop UI against the real Python Node with its configured domain pack, ledger, and persistence through #123.
- Replace the current source-intake proof with a full authoritative sequence-numbered execution stream in #123.
- Add explicit UI coverage for disconnected, rejected, oversized, unsupported, partial-intake, and clearance-mismatch submission states.
- Capture packaged Tauri and no-egress evidence. The existing host-level egress probe still fails when firewall enforcement is not requested.
