# FE-DEV-02 contract generation evidence

Status: FE-DEV-02 implementation and live Python Node transport evidence complete. Packaged installer and production identity gates remain tracked by their separate issues.

## Implemented

- `scripts/generate_frontend_contracts.py` imports the Python contract classes and ledger event catalog as the source of truth.
- The script generates `frontend/src/generated/core_contracts.ts` with schema identity, clearance values, taint values, contract status values, the ledger event catalog, and typed core contract interfaces.
- `frontend/src/protocol.ts` imports the generated clearance and taint types instead of defining competing wire unions.
- `npm run generate:contracts` regenerates the file during the frontend build.
- `npm run check:contracts` fails when the checked-in generated file is stale.
- `tests/test_frontend_contract_generation.py` protects the generated-file drift boundary.
- `TaskEventSynchronizer` now rejects inconsistent batches before projection, including wrong Node identity, protocol or clearance mismatch, malformed cursor progression, non-increasing sequences, event metadata mismatch, and ledger-reference misalignment.
- Generated contracts now include `NodeCommandEnvelope` and `NodeCommandResult`, which are the authoritative Python command wire types used by the typed Rust and TypeScript bridges.
- The Rust-owned transport now provides typed snapshot reads, task creation, and allowlisted authorize, cancel, and review commands. The webview does not call a Node URL directly.
- Python now owns the versioned Node response contracts for handshake, task snapshots, task events, event batches, provenance, evidence, and facts. The generated TypeScript view is produced from those classes; it is not a second handwritten wire schema.
- Node responses carry `airbench-node-protocol` compatibility metadata. Core envelopes retain `airbench-core-contracts`. Rust refuses missing or incompatible envelopes before returning data to the webview or accepting a consequential response.
- Event normalization is explicit and fail-closed: known event families become the typed projection union, malformed or unknown events become blocked diagnostics, and batch-level core compatibility is checked before replay.
- Facts and evidence are normalized through typed Node contracts so confidence, clearance, taint, source, derivation, and ledger references remain attached at the snapshot and event boundaries.
- `frontend/validation/validate-python-node-transport.ps1` starts the real Python `NodeApiService` and drives it through the Rust transport for handshake, task creation, snapshot, event replay, command retry, and ledger-reference checks.

## Evidence

From the repository root:

```text
python scripts/generate_frontend_contracts.py --check
python -m pytest -q
```

From `frontend/`:

```text
npm run check:contracts
npm run test
npm run build
npm run check:egress
npm run check:tauri-config
npm run validate:python-node
```

Observed results for this slice:

- Python contract generation check passed.
- Backend Python suite passed.
- Frontend suite passed with 80 tests.
- TypeScript and Vite production build passed.
- Static no-egress and Tauri policy checks passed.
- `npm run validate:node` passed fixture-backed local and pinned internal-HTTPS handshake, typed snapshot, event replay, task creation, authorization command, and credential rejection. Run: `AirBenchNodeValidation-20260909-005911-4d475cdbf9124df8a86bd9905422d81e`.
- `npm run validate:python-node` passed against the real Python `NodeApiService`, through the Rust transport, covering handshake negotiation, create-snapshot, event-batch, command-idempotency, and ledger-reference checks. Run: `AirBenchPythonNodeValidation-20260909-005911-c5b65b6d93f4495896f1ed4bd0acf373`.
- `cargo test --manifest-path frontend/src-tauri/Cargo.toml` passed all Rust unit tests; the environment blocked rustdoc execution under its application-control policy, so the doctest runner itself was not executed.

## Backend Node API slice now available

The first Python Node API slice is implemented in `airbench/node_api.py` and documented in `docs/m10_1_node_api_evidence.md`. It provides authenticated handshake and health routes, typed versioned task commands with expected-sequence and idempotency checks, task creation and lifecycle commands through the orchestrator, authoritative snapshots, task-local cursor event batches, evidence, route trace, and review projections. Its event batches use the Node clearance context required by the native transport while evidence and facts retain their individual clearance and taint.

This is an integration-ready backend slice, not a production-complete Node. The frontend must still connect its live command and snapshot paths to the API and verify the packaged local and internal-HTTPS deployment.

## Boundary of this issue

FE-DEV-02 now owns the typed Node protocol and projection boundary. Preview, download, installer, WebView2, and final packaged desktop acceptance remain separate frontend validation and release gates. They consume this boundary and must not add another parser, model endpoint, or handwritten Node response schema.
