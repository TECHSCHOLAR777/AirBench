# AirBench Frontend Validation Plan

Status: validation design and issue decomposition. Execution begins when the corresponding implementation fixture exists. No validation result is claimed by this document.

## 1. Purpose

These validations prove that the frontend can be shipped as a sovereign desktop application, not merely rendered in a browser. They cover packaging, trust, task streaming, multimodal document work, no-egress behavior, and desktop-level integration.

The six tracks are independent enough to develop in parallel after the shared contract and shell fixture are established. The final desktop flow is serialized because it integrates all six boundaries.

## 2. Validation matrix

| Track | GitHub reference | Can start after | Main evidence | Final dependency |
| --- | --- | --- | --- | --- |
| FE-VAL-1 | Offline installer and WebView2 | None | Signed or hashed installer, offline startup log, blocked network capture | Blocks FE-VAL-6 release run |
| FE-VAL-2 | Local and remote Node connection | Contract fixture and FE-VAL-1 shell | Trust handshake, endpoint identity, local and internal-remote logs | Blocks FE-VAL-3 end-to-end |
| FE-VAL-3 | Sequence-numbered event stream | Contract fixture, FE-VAL-2 transport | Replay, gap, duplicate, reconnect, and resync evidence | Blocks integrated live task |
| FE-VAL-4 | Scanned intake and artifact preview | File Intake fixture and Node artifact contract | Intake manifest, source hash, safe preview, clearance-aware download | Blocks integrated inspection demo |
| FE-VAL-5 | No-egress proof | FE-VAL-1 bundle and FE-VAL-2 transport | Network monitor capture, deny logs, blocked navigation/resource test | Must pass before any user data demo |
| FE-VAL-6 | Tauri WebDriver desktop test | FE-VAL-1 shell, FE-VAL-2 and FE-VAL-3 fixtures | Desktop test report, IPC mocks, backend logs, multiremote evidence | Final release gate |

## 3. FE-VAL-1: Offline Tauri installation and bundled WebView2

### Goal

Prove that an authorized operator can install and start the desktop application on a supported Windows machine with the network disabled and with the required WebView2 runtime bundled or installed from the approved offline package.

### Scope

- Tauri bundle format and signing or hash verification.
- WebView2 offline or fixed-runtime strategy selected for the deployment profile.
- Startup without DNS, proxy, public internet, or CDN access.
- Local assets, fonts, icons, preview workers, and JavaScript.
- Version display and installation evidence.

### Test cases

1. Install on a clean supported Windows image with network adapters disabled.
2. Start the application with no DNS route and no proxy.
3. Confirm the shell renders all local assets.
4. Confirm the application does not attempt external resource requests.
5. Launch with missing or incompatible WebView2 package and verify a clear fail-closed message.
6. Verify version, bundle hash, and runtime identity.
7. Uninstall or upgrade using the approved offline path without contacting the internet.

### Evidence

- installer hash and version;
- offline install transcript;
- startup log;
- local asset manifest;
- process and network capture;
- screenshots of successful and blocked startup;
- failure reason for unsupported runtime.

### Pass criteria

The application starts and shows a useful connection screen with network access disabled. No external request, CDN dependency, remote font, analytics call, or silent update occurs.

## 4. FE-VAL-2: Secure local and remote AirBench Node connection

### Goal

Prove that the UI connects only to an approved local or internal remote AirBench Node and rejects an untrusted or unauthorized endpoint.

### Test cases

1. Connect to an approved local Node over loopback or the approved local transport.
2. Connect to an approved remote Node over the private organizational network.
3. Verify endpoint identity, certificate or pinned trust, protocol version, and authenticated user.
4. Reject an endpoint with the wrong certificate or identity.
5. Reject an endpoint that is reachable but not an AirBench Node.
6. Drop the connection during a task and transition to the documented reconnect state.
7. Confirm that model-server URLs and arbitrary user-entered URLs are not accepted by the UI.

### Evidence

- connection profile fixture;
- trust and handshake logs;
- endpoint identity and protocol version;
- successful local and remote task snapshot;
- rejected endpoint logs;
- certificate or pin mismatch evidence;
- ledger references for connection and policy decisions.

### Pass criteria

Only approved Node profiles connect. Local and internal remote deployment are both demonstrated. Trust and authentication failure block consequential work.

## 5. FE-VAL-3: Reconnectable streaming task events

### Goal

Prove that the UI renders server-authoritative task progress from ordered events and recovers without lost or duplicated state.

### Test cases

1. Apply a snapshot and an ordered event range.
2. Ignore a duplicate event at or below the applied sequence.
3. Detect a sequence gap and pause projection.
4. Replay the missing range and resume.
5. Force replay refusal and replace the projection with a fresh snapshot.
6. Disconnect during a running worker, tool call, approval request, and artifact creation.
7. Reconnect with a stale cursor and verify resynchronization.
8. Reconnect after a task completed on the Node and show the completed state without rerunning it.
9. Attempt an approval or stop action while not current and verify the documented policy.

### Evidence

- deterministic event fixture with sequence numbers;
- client event-store diagnostics;
- replay and resync logs;
- duplicate and gap test results;
- screenshots or trace of reconnect states;
- no-duplicate command evidence;
- ledger references for the underlying task events.

### Pass criteria

The UI never guesses a state transition, applies events out of order, duplicates a consequential action, or hides an event gap.

## 6. FE-VAL-4: Scanned-document upload, preview, and download

### Goal

Prove the end-to-end multimodal user path without creating a second parser or an unsafe browser preview.

### Test cases

1. Select a scanned PDF through the native picker.
2. Send it to the File Intake Layer with the correct query-upload switch.
3. Display the returned intake manifest, source hash, page count, OCR or vision status, clearance, and taint.
4. Open a safe page or image preview with exact source-region reference.
5. Display an evidence item with source, confidence, clearance, derivation, and ledger reference.
6. Display a generated Word or PDF artifact preview from the Node.
7. Download an allowed artifact and record the download command.
8. Block download for insufficient clearance.
9. Test a malicious or instruction-bearing document and confirm that it remains data.
10. Test corrupted, oversized, unsupported, and partially uploaded files.

### Evidence

- native picker and intake request log;
- intake manifest and source hash;
- safe preview fixture;
- provenance rendering;
- download hash and permission result;
- blocked-download evidence;
- malicious-document safety test;
- File Intake and ledger event references.

### Pass criteria

Every file uses the File Intake Layer. The UI displays safe preview artifacts, preserves provenance and clearance, does not execute content, and cannot download unauthorized material.

## 7. FE-VAL-5: Network-monitor proof of no external contact

### Goal

Prove with observation and policy that the shipped UI cannot contact external services.

### Test cases

1. Start the application with all network interfaces monitored.
2. Visit every reachable first-release screen.
3. Submit a mock task and receive events from the approved internal Node.
4. Attempt external navigation through a typed URL, document link, image link, preview content, and command menu input.
5. Attempt to load remote fonts, scripts, source maps, analytics, update checks, and crash reporting.
6. Run with DNS sinkhole or explicit deny rules and inspect both client and OS logs.
7. Confirm that only the approved internal Node endpoint is reachable.

### Evidence

- packet or connection capture;
- OS firewall or deny logs;
- Tauri capability and CSP configuration;
- application resource manifest;
- blocked-navigation and blocked-resource logs;
- internal-node-only allowlist evidence;
- reproducible test script and environment hash.

### Pass criteria

No external connection succeeds or is silently attempted. The only permitted network path is the approved internal AirBench Node path. A network monitor provides evidence, not a UI claim.

## 8. FE-VAL-6: Tauri WebDriver desktop integration

### Goal

Prove the real packaged desktop flow with Tauri WebDriver, including IPC mocking, backend log capture, and multiremote behavior where the test environment supports it.

### Test cases

1. Start the packaged desktop application under WebDriver.
2. Mock the Tauri IPC boundary and return deterministic snapshots and events.
3. Capture Rust transport logs and backend fixture logs.
4. Complete the task composer to plan review path.
5. Complete live task event rendering with a reconnect.
6. Open evidence and artifact preview.
7. Exercise approval blocking and approval success paths.
8. Exercise local and remote node profile selection.
9. Run two desktop clients or windows against the same fixture where multiremote is supported and verify cursor and permission behavior.
10. Run keyboard and accessibility assertions on critical paths.

### Evidence

- WebDriver test report;
- packaged app version and hash;
- IPC mock definitions;
- Rust and backend logs;
- screenshots or trace for the six critical flows;
- multiremote or multi-window result;
- accessibility result;
- no-egress evidence from FE-VAL-5.

### Pass criteria

The shipped desktop application completes the critical workflows under WebDriver, preserves event and permission behavior, captures the evidence needed to debug failures, and passes no-egress and accessibility gates.

## 9. Parallel and serial execution

### Parallel after contract fixture

- FE-VAL-1 packaging and offline runtime.
- FE-VAL-2 connection fixture.
- FE-VAL-3 event store and reconnect fixture.
- FE-VAL-4 intake and preview fixture.
- FE-VAL-5 static no-egress review and network policy fixture.

### Serial integration

- FE-VAL-6 final desktop integration depends on FE-VAL-1 and the executable fixtures from FE-VAL-2 through FE-VAL-5.
- The final inspection-report demonstration is run only after FE-VAL-4 and FE-VAL-5 pass.
- Production readiness is not declared until all six tracks have evidence.

## 10. Validation record format

Every issue update records:

- environment and hardware;
- application and Node versions;
- fixture or test-data hashes;
- exact command;
- expected result;
- observed result;
- logs, screenshots, traces, and packet evidence;
- failure or limitation;
- whether the result is pass, fail, blocked, or needs review.

Sensitive test data stays inside the organization and is never uploaded to a third-party CI or issue attachment service.
