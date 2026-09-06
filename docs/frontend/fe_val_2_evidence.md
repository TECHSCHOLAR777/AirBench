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

The UI will not accept model-server URLs, arbitrary endpoint input, or a direct browser transport. The connection command is implemented in the Tauri Rust boundary and returns a typed result to the frontend.

The current command is intentionally not described as a completed authentication solution. It proves the transport boundary and Node identity handshake. User authentication, credential-store or mTLS integration, a deterministic AirBench Node fixture, and full failure captures remain required before FE-VAL-2 can close.

## Passing evidence so far

From `frontend/`:

- `npm run test`, 13 tests passed;
- approved internal HTTPS profile accepted;
- arbitrary external endpoint rejected;
- credentials embedded in endpoint rejected;
- unpinned remote profile rejected;
- non-loopback local profile rejected;
- `npm run build`;
- `npm run check:egress`;
- `npm run check:tauri-config`.

## Required before closing #65

- Rust-owned local transport against a deterministic AirBench Node fixture;
- approved internal remote HTTPS fixture with certificate or public-key pin verification;
- a Node-side authentication mechanism that does not expose credentials or private keys to the webview;
- protocol version and authenticated identity result;
- rejection of wrong pin, wrong identity, non-AirBench endpoint, and arbitrary endpoint;
- connection loss during a task;
- redacted transport logs and Node ledger references;
- exact environment and fixture hashes.
