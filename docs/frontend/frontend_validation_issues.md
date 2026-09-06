# Frontend Validation Issue Index

This index is the source for creating and updating the frontend validation issues. Each validation has one issue, explicit evidence, failure tests, and dependency edges. The six issues are validation work, not permission to start product UI implementation.

## Tracking conventions

Suggested labels:

- `frontend`
- `validation`
- `P1`
- `security` where applicable
- `testing`
- `blocked` only when a concrete prerequisite is missing

Suggested milestone: `Frontend validation`.

Every issue update must include the environment, fixture hashes, exact commands, expected result, observed result, artifacts, and remaining limitation. Do not attach sensitive organization documents to a public issue. Use synthetic or sanitized fixtures and store sensitive evidence inside the organization.

## Dependency graph

```text
FE-VAL-1  Offline package and WebView2
    |\
    | \---- FE-VAL-5  No-egress proof
    |
    +------ FE-VAL-2  Node connection ----+
    |                                      |
    +------ FE-VAL-3  Event stream --------+---- FE-VAL-6  Tauri WebDriver integration
    |                                      |
    +------ FE-VAL-4  Intake and preview --+
```

FE-VAL-2, FE-VAL-3, and FE-VAL-4 can be developed in parallel after the typed fixture contracts exist. FE-VAL-5 can begin its static policy review in parallel, but its final packet evidence depends on the packaged shell and approved transport. FE-VAL-6 is the serialized integration gate and depends on all six tracks' executable fixtures and FE-VAL-5's no-egress evidence.

## FE-VAL-1: Prove offline Tauri packaging with bundled WebView2

**Title**: `[FE-VAL-1][P1] Prove offline Tauri installation with bundled WebView2`

**Labels**: `frontend`, `validation`, `P1`, `security`

**Purpose**: Prove that the supported desktop build installs and starts with network access disabled, all runtime assets local, and the approved WebView2 offline strategy.

**Dependencies**: None. This is the foundation issue.

**Work**:

- choose and document the supported WebView2 fixed-runtime or offline installer mode;
- produce a reproducible Tauri bundle;
- test a clean Windows image with DNS, proxy, and network interfaces disabled;
- verify local fonts, icons, scripts, styles, and preview workers;
- verify version, bundle hash, and runtime identity;
- test missing or incompatible WebView2 as a fail-closed startup state.

**Acceptance evidence**:

- installer and bundle hashes;
- offline installation transcript;
- startup log;
- local resource manifest;
- network capture showing no external traffic;
- successful and blocked startup screenshots;
- exact environment and reproduction commands.

**Failure tests**: missing runtime, failed bundle verification, blocked filesystem permission, no Node available, attempted resource request.

**Done when**: the desktop shell starts without internet access and no silent external request, update check, analytics call, CDN resource, or remote font.

## FE-VAL-2: Prove secure local and internal remote Node connection

**Title**: `[FE-VAL-2][P1] Prove secure local and remote AirBench Node connection`

**Labels**: `frontend`, `validation`, `P1`, `security`

**Dependencies**: Can develop against a contract fixture in parallel with FE-VAL-1. Final packaged run depends on FE-VAL-1.

**Work**:

- implement approved local and internal remote connection profiles;
- prove certificate or pinned trust, authenticated identity, protocol version, and clearance context;
- reject wrong certificate, wrong identity, non-AirBench endpoint, and arbitrary endpoint input;
- capture connection and policy decisions in local logs and Node ledger references;
- test connection loss during a running task.

**Acceptance evidence**:

- local and internal remote successful handshakes;
- endpoint identity and protocol negotiation;
- trust mismatch and unauthorized endpoint rejection;
- transport logs with secrets redacted;
- connection state transitions and ledger references;
- exact connection fixture and environment.

**Failure tests**: wrong pin, expired certificate, node protocol mismatch, revoked identity, endpoint reachable but not AirBench, connection drop during command.

**Done when**: only approved AirBench Node profiles connect, and trust or authentication uncertainty blocks consequential work.

## FE-VAL-3: Prove reconnectable sequence-numbered task events

**Title**: `[FE-VAL-3][P1] Prove reconnectable sequence-numbered task-event streaming`

**Labels**: `frontend`, `validation`, `P1`, `testing`

**Dependencies**: Can develop in parallel after the snapshot, event, and command fixture contract exists. Final packaged run depends on FE-VAL-1 and FE-VAL-2.

**Work**:

- implement snapshot plus ordered event projection;
- track stream cursor and applied sequence;
- detect duplicates and sequence gaps;
- replay missing events or request a fresh snapshot;
- show reconnecting and stale states;
- prevent optimistic approval, stop, release, or duplicate commands while not current;
- capture diagnostics for resync.

**Acceptance evidence**:

- deterministic event fixture;
- duplicate, gap, replay, stale-cursor, and snapshot replacement test results;
- disconnect traces during worker, tool, approval, and artifact states;
- no-duplicate command evidence;
- event-store diagnostics and ledger references.

**Failure tests**: out-of-order event, unknown event schema, replay refusal, reconnect after server-side completion, command timeout, duplicate submission.

**Done when**: the UI never guesses or duplicates an authoritative state transition and every event gap is visible and repaired or blocked.

## FE-VAL-4: Prove scanned-document intake, safe preview, and download

**Title**: `[FE-VAL-4][P1] Prove scanned-document upload, artifact preview, and download`

**Labels**: `frontend`, `validation`, `P1`, `security`

**Dependencies**: Can develop in parallel after File Intake and artifact preview fixtures exist. Final packaged run depends on FE-VAL-1 and FE-VAL-2.

**Work**:

- select a scanned PDF through the native picker;
- route it through the File Intake Layer query-upload switch;
- render manifest, source hash, page and OCR or vision state, clearance, and taint;
- open a safe page or image preview with source-region reference;
- render a Node-generated Word or PDF artifact preview;
- download only when the Node grants permission;
- test malicious, instruction-bearing, corrupted, oversized, unsupported, and partial files.

**Acceptance evidence**:

- picker and intake request logs;
- manifest and source hash;
- safe preview fixture and screenshot;
- provenance and clearance rendering;
- allowed and blocked download evidence;
- malicious-document safety result;
- File Intake and ledger references.

**Failure tests**: intake rejection, malformed preview, source hash mismatch, clearance mismatch, preview link injection, macro-bearing document, interrupted upload.

**Done when**: every file uses File Intake, content remains data, previews are safe, provenance is complete, and unauthorized downloads are blocked.

## FE-VAL-5: Prove no external UI contact

**Title**: `[FE-VAL-5][P1] Prove UI cannot contact external services`

**Labels**: `frontend`, `validation`, `P1`, `security`

**Dependencies**: Static allowlist review can run in parallel. Final network capture depends on FE-VAL-1 and the approved connection boundary from FE-VAL-2.

**Work**:

- inspect Tauri capabilities and content security policy;
- run every first-release screen under a network monitor;
- allow only the approved internal Node endpoint;
- attempt external navigation through typed URL, document link, image link, preview content, command menu input, remote font, script, source map, analytics, crash report, and update check;
- record OS firewall or deny logs;
- verify no secret or user data is sent to a third party.

**Acceptance evidence**:

- packet or connection capture;
- firewall and deny logs;
- capability and CSP snapshot;
- resource manifest;
- blocked navigation and resource traces;
- internal-node-only allowlist evidence;
- reproducible environment and commands.

**Failure tests**: external redirect, remote preview asset, remote font fallback, telemetry package, update check, navigation through untrusted document content.

**Done when**: no external connection succeeds or is silently attempted and the only allowed path is the approved internal Node path.

## FE-VAL-6: Prove packaged desktop behavior with Tauri WebDriver

**Title**: `[FE-VAL-6][P1] Prove desktop flows with Tauri WebDriver`

**Labels**: `frontend`, `validation`, `P1`, `testing`

**Dependencies**: Serial integration gate. Requires FE-VAL-1 and executable fixtures from FE-VAL-2 through FE-VAL-5.

**Work**:

- run the packaged application under Tauri WebDriver;
- mock Tauri IPC with deterministic snapshots and events;
- capture Rust transport and backend fixture logs;
- test task composer, plan review, live task, reconnect, evidence, artifact preview, approval blocking, approval success, local and remote node profiles;
- test multiremote or multi-window behavior when supported by the chosen driver setup;
- run keyboard and accessibility assertions.

**Acceptance evidence**:

- WebDriver report;
- packaged application hash and version;
- IPC mocks;
- Rust and Node fixture logs;
- screenshots or traces for critical flows;
- multiremote result or documented environment limitation;
- accessibility result;
- FE-VAL-5 network proof.

**Failure tests**: IPC timeout, backend event gap, node loss, blocked approval, permission denial, preview failure, two-client stale cursor.

**Done when**: the shipped desktop application completes the critical flows with evidence, preserves policy and event semantics, and passes the no-egress and accessibility gates.

## GitHub issue numbers

The six validation issues are open in `TECHSCHOLAR777/AirBench` and have the `frontend`, `validation`, and `P1` labels:

| Reference | GitHub issue | State |
| --- | --- | --- |
| FE-VAL-1 | [#64](https://github.com/TECHSCHOLAR777/AirBench/issues/64) | Open |
| FE-VAL-2 | [#65](https://github.com/TECHSCHOLAR777/AirBench/issues/65) | Open |
| FE-VAL-3 | [#66](https://github.com/TECHSCHOLAR777/AirBench/issues/66) | Open |
| FE-VAL-4 | [#67](https://github.com/TECHSCHOLAR777/AirBench/issues/67) | Open |
| FE-VAL-5 | [#68](https://github.com/TECHSCHOLAR777/AirBench/issues/68) | Open |
| FE-VAL-6 | [#69](https://github.com/TECHSCHOLAR777/AirBench/issues/69) | Open |

The issue definitions remain versioned in this file so the repository and GitHub descriptions do not drift.
