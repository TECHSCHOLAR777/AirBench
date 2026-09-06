# M10.1 Python Node API evidence

Status: implementation slice complete locally. Issue #54 remains open because production deployment, signed identity provisioning, live intake and artifact integration, and packaged end-to-end evidence are still downstream gates.

## Boundary

`airbench/node_api.py` is a thin local HTTP boundary around the existing deterministic `contracts.Orchestrator` and append-only ledger. It does not select models, call model servers, parse documents, execute tools, or make external network requests.

Mutating routes call the orchestrator. Read routes rebuild their response from committed ledger events and the task envelope. The API never writes a ledger event directly.

## Endpoints

All endpoints require a bearer credential. The bearer token is compared locally and is never included in errors, responses, or logs.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/v1/node/handshake` | Returns Node identity, protocol, clearance context, authenticated subject, the configured domain-pack reference, and the configured ledger connection reference. |
| GET | `/api/v1/health` | Verifies the local ledger chain and reports local readiness. |
| POST | `/api/v1/tasks` | Validates a versioned `NodeCommandEnvelope` for task creation and delegates creation to `Orchestrator.create_task`. |
| GET | `/api/v1/tasks/{task_id}` | Returns a clearance-filtered authoritative task snapshot. |
| GET | `/api/v1/tasks/{task_id}/events?after_sequence=N` | Returns a bounded replay batch with a task-local cursor, Node context, camelCase event envelopes, and immutable ledger references. |
| GET | `/api/v1/tasks/{task_id}/evidence` | Returns clearance-filtered evidence and fact projections with source, confidence, clearance, taint, and ledger references. |
| GET | `/api/v1/tasks/{task_id}/route-trace` | Returns bounded routing and model lifecycle evidence without exposing arbitrary event payloads. |
| GET | `/api/v1/tasks/{task_id}/review` | Projects pending and recorded human review state. |
| POST | `/api/v1/tasks/{task_id}/authorize` | Validates a task-authorize command, checks the expected task-local sequence, and delegates the transition to the orchestrator. |
| POST | `/api/v1/tasks/{task_id}/cancel` | Validates a task-cancel command, checks the expected task-local sequence, and delegates the transition to the orchestrator. |
| POST | `/api/v1/tasks/{task_id}/review` | Validates a task-review command, checks the expected task-local sequence, and delegates the transition to the orchestrator. |

FastAPI documentation and OpenAPI routes are disabled. JSON bodies are bounded to 1 MiB. Task IDs, lists, strings, and resource budgets are validated before reaching the orchestrator.

## Event and clearance semantics

The ledger sequence is global across all tasks. The API exposes a separate task-local sequence starting at one because the desktop event synchronizer replays one task at a time. Every projected event retains its original `ledgerEventRef` and `payloadHash`.

The batch and event `clearance_context` fields identify the authenticated Node context so they match the Rust and TypeScript transport contracts. Individual evidence and fact objects retain their own clearance and taint. Events above the Node context or task clearance are omitted rather than downgraded.

## Command envelope and retry semantics

Every mutating route accepts the generated `NodeCommandEnvelope` contract. The Node checks the client protocol version, authenticated actor, route target, command type, and expected task-local sequence before calling the orchestrator. A stale sequence returns a bounded conflict and cannot mutate the ledger.

The orchestrator commits a non-sensitive command receipt containing the authenticated actor, command ID, idempotency key, and command fingerprint alongside the real lifecycle event. Retrying the same idempotency key and content replays the committed result from the ledger. Reusing the key with different content returns an idempotency conflict. Secrets and command arguments are not copied into the receipt.

Unrecognized ledger events are represented as a bounded `ledger.written` summary. Arbitrary event payloads are not copied into the UI stream. Governed evidence is exposed only when its provenance contains source, confidence, clearance, and taint.

## Tests and evidence

From the repository root:

```text
python -m pytest -q tests/test_node_api.py
python -m pytest -q tests/test_m71_intake.py
python -m pytest -q
python -m compileall -q airbench contracts tests
```

The focused Node API tests cover authentication failure, disabled documentation routes, typed command validation, task mutation delegation, task-local cursor replay, ledger-reference alignment, clearance filtering, route projection, cursor-ahead rejection, stale-command refusal, idempotent create and transition replay, idempotency conflict, actor and protocol mismatch, invalid clearance, and oversized JSON rejection.

The File Intake parity regression test also passes for DOCX bulk and query paths. Raw source hashes remain different when ZIP metadata differs, while semantic revision and page identities remain stable for equivalent parsed content.

The frontend fixture transport run `AirBenchNodeValidation-20260907-015945-fb13075cb05e4b8f8fc916bb49847522` also exercised the typed snapshot and command boundary over loopback and pinned internal HTTPS, including the Node-selected domain-pack reference and bounded task metadata. It is synthetic fixture evidence only and does not replace a packaged run against Uvicorn and SQLite.

## Remaining acceptance gates

- Provision the bearer identity from the deployment credential store instead of a process configuration value.
- Run the API through the offline one-node packaging path with Uvicorn and a local SQLite ledger.
- Add the real File Intake query-upload, safe preview, artifact download, and approval command endpoints through their existing typed adapters.
- Add the remaining authoritative Node-specific snapshot, evidence, review, preview, and download-receipt schemas to the generated frontend contract source.
- Exercise the Rust-owned command and snapshot transport against a running packaged Python Node.
- Capture packaged local and pinned internal-HTTPS handshake, reconnect, and no-egress evidence against this API.
