# FE-VAL-3 evidence record

Status: cursor transport and projection validation in progress. No complete packaged desktop pass is claimed yet.

## Implemented boundary

- `frontend/src-tauri/src/node_transport.rs` exposes a Rust-owned `fetch_task_events` command.
- The command accepts only an approved Node profile, task identifier, and numeric cursor.
- It reads the bearer credential from the OS credential store, requests the cursor range from the Node, checks Node identity, protocol version, clearance context, and numeric event sequences, and returns the typed batch to the webview.
- `frontend/src/eventTransport.ts` is the only TypeScript entry point for this command.
- `frontend/src/eventStore.ts` applies a batch through the existing sequence-aware projection and stops at the first gap.
- `CommandDeduplicator` prevents a second in-flight reservation for the same idempotency key. Consequential commands remain blocked unless the projection is current.

## Synthetic fixture evidence

Command from `frontend/`:

```text
npm run validate:node
```

The runner starts a local authenticated Node fixture and a pinned internal-HTTPS fixture. It proves:

Run: `AirBenchNodeValidation-20260906-093801-1789648d61b9499e8a9cedb30ecd49fb`

- cursor `0` returns ordered event sequences `1,2,3,4,5`;
- cursor `3` returns replay sequences `4,5`;
- local and remote handshakes include the authenticated subject and ledger connection reference;
- wrong credential, wrong Node identity, wrong certificate pin, invalid AirBench endpoint, and invalid task identifiers are rejected;
- fixture logs do not contain bearer credential values.

The TypeScript suite also covers duplicate events, sequence gaps, replay requests, snapshot replacement, blocked consequential commands, and idempotency-key reservation. The Rust suite covers endpoint and cursor-boundary validation.

## Remaining acceptance evidence

- connection-drop traces during worker, tool, approval, and artifact states;
- real Python AirBench Node event endpoint and signed ledger references;
- packaged Tauri run with reconnect UI states;
- replay refusal and server-side completion after reconnect;
- no-duplicate command evidence from the real Node command endpoint.

The synthetic fixture is local test data only and is not a production Node implementation.
