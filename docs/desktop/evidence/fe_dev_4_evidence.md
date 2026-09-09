# FE-DEV-04 evidence record

Status: implementation slice complete locally. Issue #76 remains open for the real Python Node, authoritative event-driven task state, failure-state coverage, and packaged desktop evidence.

## Delivered slice

- Home now collects an outcome, bounded title, optional project reference, deliverable type, priority, and optional deadline.
- A selected file can be handed to the existing query-upload path. The UI sends only the native selection token and the returned File Intake manifest reference.
- The UI does not parse, OCR, inspect, execute, or reinterpret file bytes.
- A manifest is treated as ready only when both OCR and vision statuses are terminal success or explicitly not applicable. Pending or running work remains processing, and failed, unavailable, or unknown statuses remain partial; the UI does not request or display a preview as if those results were complete.
- The webview re-validates the runtime payload returned by the native intake commands before it becomes React state. Intake identity, file bounds, hashes, statuses, clearance, taint, preview references, source regions, confidence, safe text limits, artifact blocks, and ledger references fail closed when malformed or over-cleared.
- The Node handshake supplies the domain-pack reference. The UI carries it in the command, while the Node rejects a value that differs from its configured pack.
- `task.create` is sent through the Rust-owned typed command bridge. The Python Node validates the command, creates the task envelope, and preserves the bounded user metadata and manifest references.
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
- `npm test -- --run`: 110 passed across 22 test files.
- `npm run build`: passed.
- `npm run check:contracts`: passed.
- `npm run check:ui`: passed, including the authored-source accessibility contract.
- `npm run check:egress`: passed; no network-capable frontend API or external resource URL was found.
- `npm run check:tauri-config`: passed.
- `git diff --check`: passed.
- `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`: 14 passed.
- `npm run validate:node`: passed local and pinned internal-HTTPS fixture coverage. Run: `AirBenchNodeValidation-20260907-015945-fb13075cb05e4b8f8fc916bb49847522`.

## Remaining gates

- Run the same command against the real Python Node with its configured domain pack, ledger, and persistence.
- Replace the fixture acknowledgment path with the authoritative task snapshot and sequence-numbered event stream in FE-DEV-05 and FE-DEV-06.
- Add explicit UI coverage for disconnected, rejected, oversized, unsupported, partial-intake, and clearance-mismatch submission states.
- Capture packaged Tauri and no-egress evidence. The existing host-level egress probe still fails when firewall enforcement is not requested.
