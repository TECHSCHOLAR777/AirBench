# FE-VAL-2 evidence record

Status: Rust-owned handshake implementation in progress. No secure Node connection pass is claimed yet.

## Current boundary

`frontend/src/nodeConnection.ts` defines the approved-profile boundary, and `frontend/src/nodeBridge.ts` is the only webview entry point into the Rust transport command.

- local profiles may target loopback only;
- internal remote profiles require HTTPS and a certificate pin;
- credentials may not appear in endpoint URLs;
- query strings and fragments are rejected;
- unapproved profiles are blocked;
- the result carries Node identity, protocol version, clearance, sovereignty state, and an explicit failure code.
- the Rust command builds the handshake URL, performs the request outside the webview, verifies the remote leaf certificate SHA-256 pin, and compares the returned Node identity, protocol version, and clearance context with the approved profile.
- the Rust command reads the bearer credential by reference from the OS credential store and checks that the Node returns an authenticated subject; the bearer value is never part of the webview contract or logs.
- `frontend/validation/node_fixture.py`, `generate_fixture_certificate.py`, and `validate-node-transport.ps1` provide a synthetic local and internal-HTTPS fixture with redacted JSONL logs and failure cases for wrong credentials, wrong identity, wrong pin, and a reachable non-AirBench endpoint.
- `frontend/src/nodeConnectionController.ts` provides the typed presentation state around that boundary. It blocks unapproved profiles before IPC, exposes verified identity, clearance, sovereignty, and ledger reference only after the Rust result succeeds, fails closed on disconnect, and reconnects only the saved approved profile. Connector failures are redacted before reaching the UI.

The UI will not accept model-server URLs, arbitrary endpoint input, or a direct browser transport. The connection command is implemented in the Tauri Rust boundary and returns a typed result to the frontend.

The current command now has an authenticated transport contract. The deterministic fixture run `AirBenchNodeValidation-20260906-093801-1789648d61b9499e8a9cedb30ecd49fb` passed its local and internal-HTTPS handshake cases. Production identity policy, real Python Node integration, and full failure captures remain required before FE-VAL-2 can close.

## Passing evidence so far

From `frontend/`:

- `npm run test`, 16 tests passed;
- approved internal HTTPS profile accepted;
- arbitrary external endpoint rejected;
- credentials embedded in endpoint rejected;
- unpinned remote profile rejected;
- non-loopback local profile rejected;
- `npm run build`;
- `npm run check:egress`;
- `npm run check:tauri-config`.
- `npm run validate:node`, including wrong credential, wrong identity, wrong certificate pin, invalid AirBench endpoint, invalid task identifier, denied artifact download, and unsupported file cases.
- `npm run test` passes 25 tests, including controller coverage for unapproved profiles, verified connection metadata, disconnect and reconnect gating, and secret-safe failure handling.

## Required before closing #65

- Rust-owned local transport against a deterministic AirBench Node fixture;
- approved internal remote HTTPS fixture with certificate or public-key pin verification;
- a Node-side authentication mechanism that does not expose credentials or private keys to the webview;
- successful local and HTTPS fixture runs from `npm run validate:node`;
- credential setup is piped to the OS credential-store helper rather than passed as a command-line argument;
- protocol version and authenticated identity result;
- rejection of wrong pin, wrong identity, non-AirBench endpoint, and arbitrary endpoint;
- connection loss during a task;
- packaged UI connection state transitions and a real Node connection controller wired to the screen;
- redacted transport logs and Node ledger references;
- exact environment and fixture hashes.
