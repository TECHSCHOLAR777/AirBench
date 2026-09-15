# AirBench handoff for Deepanshu

**Read this before touching the repository.**

Deepanshu, this is the practical handoff for returning to AirBench after a break. It tells you what is real, what is only a development fixture, how to open the desktop application, how to run the local Node path, and what still needs to be proved by a person on the actual target machine.

This is not a celebration document and it is not a substitute for the GitHub issues. If this file and the repository disagree, trust the current code, the latest test output, and the issue acceptance criteria. Then update this document and the issue with the new evidence.

## 1. The one-paragraph status

AirBench currently has a working Python backend path, a Tauri and React desktop shell, typed Rust-to-Node transport, task creation, task-bound File Intake handoff, server-owned plan review, plan authorization, sequence-numbered event replay, provenance and ledger projections, a local DOCX artifact, safe preview, and Node-authorized download. The real desktop WebDriver runner has passed this path against the real Python NodeApiService on the development workstation. That is meaningful progress toward the local end-to-end product.

It is not yet a production or final sovereign acceptance. The remaining proof includes a human-run local flow, independent runtime network monitoring, deliberate connection loss and recovery checks, qualified OCR or vision on a real scanned document, qualified model and hardware evidence, native Linux sandbox acceptance, signed or provisioned policy material, and the packaged clean-machine release gate. Do not describe those as complete until their evidence exists.

## 2. Current repository checkpoint

At the time of this handoff:

| Item | Value |
| --- | --- |
| Repository | https://github.com/TECHSCHOLAR777/AirBench |
| Branch | main |
| Commit | cf139c2b20b98bbea72a091b5399acce2c471d39 |
| Last commit | integrate local node flow and harden model storage |
| Remote state | Local main was clean and synchronized with origin/main |
| Python package | AirBench core and Node API in the repository root |
| Desktop package | apps/desktop/ |
| Canonical model root | C:\AirBench-models |
| Current target | A locally demonstrable, integrated desktop flow before final packaging and target-host qualification |

Start every session with:

~~~
Set-Location 'C:\Users\HP\OneDrive\RISHI GARG LAB\AirBench'
git fetch origin
git pull --ff-only origin main
git status --short
git log -1 --oneline
~~~

Do not use git reset --hard, git checkout --, or a broad cleanup command to make the tree look clean. Existing changes may belong to another worker.

## 3. The AirBench flow

The first useful product path is an organization employee submitting a sensitive document task and receiving a reviewable deliverable without sending the document outside the organization's controlled environment.

The system path is:

~~~
User
  -> Tauri desktop and React UI
  -> Rust-owned typed boundary
  -> approved AirBench Node
  -> File Intake Layer
  -> task state and server-owned plan
  -> authorization and deterministic orchestrator
  -> local workers, tools, model router, and verification
  -> Deliverable Engine
  -> artifact review and controlled download
  -> UI-visible evidence and ledger references
~~~

The rules behind that flow matter more than the number of screens:

- The UI is a command and presentation surface. It is not a second orchestrator.
- The UI talks only to the AirBench Node through the Rust-owned boundary.
- The UI never calls vLLM, NVIDIA NIM, a model endpoint, a cloud service, or an arbitrary URL.
- The Node owns state, control flow, retries, fallback, authorization, and completion.
- A model is a stateless worker for one call. It cannot drive the loop or grant authority.
- Uploaded and ingested content is untrusted data. It is never treated as instructions.
- Files enter through the File Intake Layer. There must not be a second parser in the desktop or another backend path.
- Facts and evidence keep source, confidence, clearance, taint, timestamp, derivation, and ledger references.
- Deliverable values come from deterministic computation. A model may write prose and refer to named values, but it must not invent authoritative numbers.
- Consequential model calls, tool calls, decisions, state changes, and human sign-offs create append-only ledger records.
- A disconnected, stale, unapproved, or uncertain state fails closed for consequential actions.

## 4. What is genuinely ready

### 4.1 Backend and Node path

The real Python validation path currently proves the following against local loopback:

- authenticated and typed Node handshake;
- Node identity, protocol version, compatibility, clearance, domain-pack reference, and ledger reference checks;
- task creation through the Node command boundary;
- task-bound query upload through the same File Intake Layer used by the backend;
- untrusted source handling and manifest linkage;
- safe source preview and hash-preserving download;
- authoritative task snapshot and sequence-numbered event projection;
- route trace and admission projection;
- explicit task authorization and an admitted plan;
- plan approval through an idempotent Node command;
- the M4 local team runtime with a bounded local worker;
- deterministic verification;
- a real DOCX projection through the Deliverable Engine;
- artifact review projection, safe preview, and Node-authorized download;
- command idempotency, ledger references, replay, and integrity checks.

The server used for this validation is apps/desktop/validation/python_node_server.py. It is a local validation composition around the real NodeApiService, Orchestrator, FileIntakeLayer, local artifact store, and task execution coordinator. It is not a production daemon and it does not pretend that a synthetic worker is a qualified model.

### 4.2 Desktop and frontend path

The desktop shell currently includes these practical areas:

- Home and task launch;
- approved Node connection and readiness;
- task creation and File Intake handoff;
- plan review and authorization;
- live work trace with visible phases and authoritative event context;
- evidence and safe source preview;
- artifact review and controlled download;
- task history and audit-oriented views;
- Node and display settings.

The current UI deliberately shows the difference between planned work, recorded work, evidence, verification, review, and outcome. It does not show raw model chain of thought or fabricate activity that the Node did not report.

### 4.3 Model storage

The duplicate model cleanup is complete. The canonical local model directory is C:\AirBench-models and currently retains four model directories:

- gemma4-26b-a4b-4bit
- gemma4-31b-it-q4
- qwen2.5-vl-7b-awq
- qwen3-coder-30b-a3b-awq

The model store audit reported no remaining duplicate or incomplete large blobs. Do not delete these local models or the Hugging Face cache as part of normal issue work. Do not start another model download without a roster decision and a storage audit.

## 5. What is not yet proven

This list is the boundary between a useful local development slice and an accepted production capability.

| Area | Current truth | What would count as proof |
| --- | --- | --- |
| Human desktop use | The shell can be launched. The real path is automated through a visible WebDriver runner. | A person completes the critical flow, records the machine and result, and reports any confusing or blocked interaction. |
| Node provisioning | The development slice reads an administrator-provisioned approved-node-profiles.json. React cannot create arbitrary endpoints. | A real provisioning procedure, protected host ACL, approved credential, and policy evidence on the target host. |
| Network sovereignty | Static frontend egress checks pass. The packaged runtime smoke has shown why an unenforced host is not enough. | Independent process-tree monitoring or host firewall evidence showing no external connection during startup and the full task. |
| Event recovery | Typed cursor replay and reconnect state exist. | Deliberately interrupt the Node or connection, reconnect, confirm no gap or duplicate, then record the evidence. |
| Scanned documents | The current PDF fixture is synthetic and digitally readable. | A real scanned inspection report through qualified local OCR or vision, with safe preview, extracted evidence, confidence, taint, and human review. |
| Model inference | Router and registry work is tracked, but the current validation worker is synthetic. | Qualified local serving, hardware admission, measured latency and memory, route decision, fallback, and model identity recorded in the ledger. |
| Sandbox | The provider and Podman integration code exist. Windows path semantics correctly fail closed for the integrated adapter. | Native Linux target-host run through SandboxRunner, with resource usage, disk quota, network denial, cleanup, and independent evidence. |
| Artifact acceptance | DOCX is structurally produced and hash checked. Visual review is correctly Needs Review when no visual renderer is configured. | Human review, structural and visual checks, approval or return action, and full provenance evidence. |
| Packaging | Tauri packaging configuration and offline installer checks exist. | Clean target-host installation, bundled WebView2, provisioned WebDriver, full critical path, no-egress observation, and release manifest. |
| GPU box | No claim is made from the workstation validation. | Native Linux GPU-box run with the actual selected models and recorded hardware and qualification evidence. |

The words fixture, synthetic, validation, and real Python Node are not interchangeable. Keep those labels in every issue comment and test report.

## 6. Repository map

These are the folders you will use most often:

| Path | What belongs there |
| --- | --- |
| apps/desktop/ | Tauri desktop application, React UI, validation scripts, WebDriver tests, and desktop evidence |
| apps/desktop/src/app/ | Application composition and screen selection |
| apps/desktop/src/platform/node/ | Typed frontend calls for approved Node operations |
| apps/desktop/src/features/intake/ | File selection and the typed File Intake bridge |
| apps/desktop/src/features/tasks/ | Task manifest and command construction |
| apps/desktop/src/features/work_trace/ | Event-to-display projection and live work trace |
| apps/desktop/src/features/provenance/ | Safe evidence and provenance display |
| apps/desktop/src-tauri/src/ | Native Rust boundary, approved profiles, credentials, transport, and file save boundary |
| apps/desktop/validation/ | Local Node and transport validation compositions |
| apps/desktop/tests/desktop/ | WebDriver desktop journeys |
| src/airbench/ | Core Python engine, Node API, orchestrator, intake, ledger, router, verification, and deliverables |
| contracts/ | Shared typed contracts, catalogs, schemas, and state transitions |
| packs/ | Domain-pack implementations and pack fixtures. Core code must remain sector-neutral. |
| models/ | Model roster and model-storage documentation, not model bytes |
| tests/ | Python unit, contract, integration, and sandbox tests |
| scripts/ | Repository utilities such as contract generation and model-store auditing |
| docs/foundations/ | Foundational architecture source of truth |
| docs/runtime/ | Harness, routing, model roster, and backend execution plans |
| docs/assurance/ | Security, verification, qualification, consistency, autonomy, and ledger guidance |
| docs/desktop/ | Frontend architecture, design, workflow, validation, and evidence |
| docs/operations/ | Development workflow, status records, and handoffs |
| docs/future/ | Deferred full-fledged requirements |

## 7. How to open the backend

### 7.1 First run the composed validator

This is the safest first check because it starts and removes its own local Python Node and temporary stores:

~~~
Set-Location 'C:\Users\HP\OneDrive\RISHI GARG LAB\AirBench\apps\desktop'
npm run validate:python-node
~~~

Expected outcome: the command prints a JSON result with status: passed and checks for handshake, task creation, task-bound intake, plan and authorization, M4 runtime, deterministic verification, DOCX, artifact preview and download, idempotency, ledger, and replay. It is backend and Rust transport evidence. It does not open the desktop window.

The fixture-backed transport check is also useful when diagnosing the boundary:

~~~
npm run validate:node
~~~

### 7.2 Start a Python Node manually

Use this when you need to inspect server output or keep a local Node alive for a development experiment:

~~~
Set-Location 'C:\Users\HP\OneDrive\RISHI GARG LAB\AirBench'
$intakeRoot = Join-Path $env:TEMP 'AirBench-Deepanshu-Node\intakes'
New-Item -ItemType Directory -Force -Path $intakeRoot | Out-Null
python apps\desktop\validation\python_node_server.py --port 8765 --token airbench-local-token --node-identity deepanshu-local-node --subject deepanshu-validation --intake-root $intakeRoot
~~~

Keep that terminal open. This server is loopback-only for the local validation exercise. Stop it with Ctrl+C when finished. Do not put a real organizational bearer token in a command pasted into an issue or chat.

The desktop cannot simply be pointed at any URL. The approved profile is native-owned. In a normal Tauri build it is loaded from the application configuration directory as approved-node-profiles.json, and the credential is read from the operating-system credential store. The webview receives only the stable profile ID. This is why a fresh installation may say Connect a trusted Node to begin: the app has no approved profile yet, not because the model is missing.

The current development repository does not provide a general-purpose user-facing profile provisioning screen. Do not bypass that by adding an endpoint text box to React. Provisioning, host ACL protection, and signed policy verification belong to the later acceptance work.

## 8. How to open and see the frontend

### 8.1 Shell-only development

Open a second terminal:

~~~
Set-Location 'C:\Users\HP\OneDrive\RISHI GARG LAB\AirBench\apps\desktop'
npm ci
npm run tauri:dev
~~~

This opens the AirBench desktop window. It is the correct way to inspect the Tauri application locally. npm run dev only starts the Vite webview and is not the integrated desktop proof because it has no native Rust IPC boundary.

With no approved profile provisioned, inspect the shell, Node status, screens, empty states, and fail-closed messages. Do not expect task execution from this shell alone.

### 8.2 Real Python Node desktop journey

This is the current way to see the full local route in a disposable, repeatable run. It builds a dedicated WebDriver binary, starts a real local Python Node, provisions a temporary profile and OS credential, runs the Tauri application, drives the task, and removes temporary state at the end.

From PowerShell:

~~~
Set-Location 'C:\Users\HP\OneDrive\RISHI GARG LAB\AirBench\apps\desktop'

# Use the installed local tools. Do not enable driver downloads for sovereignty evidence.
$env:AIRBENCH_PYTHON = (Get-Command python).Source
$env:AIRBENCH_WDIO_DRIVER = 'external'
$env:TAURI_DRIVER_PATH = Join-Path $env:USERPROFILE '.cargo\bin\tauri-driver.exe'
$edgeDriver = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Temp\msedgedriver') -Filter msedgedriver.exe -File -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($null -eq $edgeDriver) { throw 'Install or provision Edge WebDriver locally before this test.' }
$env:PATH = (Split-Path -Parent $edgeDriver.FullName) + ';' + $env:PATH
Remove-Item Env:AIRBENCH_ALLOW_DRIVER_DOWNLOAD -ErrorAction SilentlyContinue

npm run test:desktop:real-node
~~~

The runner should end with status: passed and a result describing a real Python Node, a local PDF through the Rust File Intake boundary, and a Node-authorized DOCX downloaded through the Rust save boundary. During the run, watch the application window. The synthetic PDF is intentionally safe and minimal; it is not the scanned-document acceptance test.

If the command fails before the first application assertion, run:

~~~
npm run check:webdriver
~~~

The harness is deliberately offline-safe and does not download drivers unless AIRBENCH_ALLOW_DRIVER_DOWNLOAD=1 is explicitly set. Do not set that variable for acceptance evidence.

After an interrupted run, inspect first and clean only known old AirBench test roots:

~~~
npm run cleanup:test-artifacts
# After confirming no AirBench WebDriver process is active:
npm run cleanup:test-artifacts -- --apply
~~~

This cleanup does not touch the repository, C:\AirBench-models, the Hugging Face cache, or the normal Cargo target.

## 9. What to click and what each result means

The exact labels can change as the UI evolves, but the acceptance story must stay the same.

1. Open the desktop and go to Node and settings.
2. Confirm that the profile is an approved profile, not a typed arbitrary endpoint.
3. Connect and wait for the UI to show verified identity, clearance, protocol, and ledger reference.
4. Return to Home and create a task with a clear outcome. For the current validation path, use an inspection-report review note outcome.
5. Attach the input through the native picker. It must enter through File Intake after task creation. The UI should show that the source is untrusted data and should show a Node-generated preview when one exists.
6. Launch the task. A task accepted by the Node is not the same as a task authorized to execute.
7. Read the plan review. Check execution mode, team or worker assignments, concurrency ceiling, hardware reason, required verification, completion criteria, authority, and ledger reference.
8. Approve the plan only when the Node says it is current and approvable. A stale plan must be rejected or refreshed.
9. Watch the Live Work Trace. It should show only recorded Node events and bounded work context. It must not invent private model reasoning.
10. Open evidence and source preview. Check source references, confidence, clearance, taint, derivation, hashes, and ledger references.
11. Open the generated artifact. Needs Review is the correct state when a visual check is unavailable. Do not call it verified just because the file exists.
12. Use controlled download. The saved file must be Node-authorized, hash checked, and associated with a ledger receipt.
13. Record anything confusing, silent, misleading, or unexpectedly blocked. Human usability is part of the acceptance, especially for non-technical operators.

The current real WebDriver journey expects a synthetic task mode of SERIAL VIRTUAL TEAM, an artifact titled AirBench local validation review note, and a review state of Needs Review because visual artifact verification is not configured in that run. Those are test expectations, not universal UI copy.

## 10. Commands and evidence already available

Run from apps/desktop unless noted:

| Command | Latest known result | What it proves |
| --- | --- | --- |
| npm run validate:node | Passed | Fixture local and pinned internal-HTTPS transport path |
| npm run validate:python-node | Passed | Real Python Node through the Rust transport, including task-bound intake and deliverable path |
| npm test -- --run | 25 files and 143 tests passed | Frontend unit and contract behavior |
| npx tsc -b --pretty false | Passed | TypeScript project type checking |
| npm run build | Passed | Production frontend build and local resource manifest |
| npm run check:egress | Passed | No network-capable frontend API or external resource URL in authored source |
| npm run check:ui | Passed | Semantic UI baseline, both themes, local resources, and authored accessibility checks |
| npm run check:tauri-config | Passed | Offline-oriented Tauri configuration and CSP checks |
| npm run check:webdriver | Depends on local driver provisioning | WebDriver prerequisites without downloading drivers |
| npm run test:desktop:real-node | Passed on the current Windows workstation | Visible Tauri journey against real Python Node with disposable profile and credential |
| npm run cleanup:test-artifacts | Passed dry run | No known old AirBench test roots eligible for cleanup at the last check |

From the repository root:

~~~
python -m pytest -q
~~~

The latest full Python run passed with 2 skips and an existing datetime.utcnow deprecation warning. A warning is not a passing feature; record it if you touch the relevant code.

For formatting and native checks:

~~~
cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check
cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml --features wdio
git diff --check
~~~

Use a disposable CARGO_TARGET_DIR for acceptance or refactor validation when a command creates a new Tauri build. The old default Cargo cache can retain absolute paths from the former frontend/src-tauri layout. Do not treat that stale cache as product source, and do not delete it blindly while another build is running.

## 11. Deepanshu's active queue

These are the open issues currently assigned to you or specifically intended for your execution lane.

### #123: Complete the local desktop Python Node vertical slice

Issue: https://github.com/TECHSCHOLAR777/AirBench/issues/123

This is the most important next issue for the local product demonstration. It is not asking for another mockup. It asks for one truthful path through:

~~~
Tauri desktop
  -> approved local AirBench Node
  -> task creation
  -> task-bound File Intake
  -> server plan and authorization
  -> live authoritative events
  -> evidence and provenance
  -> real Deliverable Engine artifact
  -> review and controlled download
~~~

What is already present: the real Python Node validator and the real desktop WebDriver runner cover most of this sequence. What still needs your ownership before closure:

- run the journey yourself and confirm that the visible UI is understandable;
- capture the exact run command, commit, machine, Python version, Node identity, and output;
- add or finish negative cases for missing approval, stale plan, denied intake or artifact action, Node stop, and reconnect;
- prove cursor replay has no event gap or duplicate after a deliberate connection interruption;
- provide independent no-egress observation for the actual local run, not only the source scanner;
- distinguish the synthetic PDF and worker from a qualified OCR, vision, or model run;
- attach the evidence manifest and screenshots or logs that do not expose sensitive document contents;
- update the issue with the results and remaining limitations.

Do not close #123 merely because npm test passes or because the UI opens. Do not claim scanned-document OCR, GPU model inference, or packaged offline acceptance under this issue.

### #124: Complete packaged sovereign desktop acceptance

Issue: https://github.com/TECHSCHOLAR777/AirBench/issues/124

This is serial after the local vertical slice is stable. It consolidates the old packaged and no-egress acceptance concerns. It requires a clean target environment, offline Tauri installation with bundled WebView2, provisioned WebDriver, the critical task flow, accessibility checks, independent external-network monitoring, blocked external attempts, package and resource hashes, and an evidence manifest.

Your work on #124 is not to make the issue green by reusing the development workstation state. Use a clean or reset test environment and record:

- Windows version and architecture;
- Tauri package and application hash;
- WebView2 installation mode and version;
- provisioned tauri-driver and Edge WebDriver versions;
- Python Node and model-serving state;
- exact input fixture identity and hash;
- network-monitor or firewall evidence for the application process tree;
- successful and deliberately blocked external connection attempts;
- critical-flow screenshots, logs, download hash, and ledger references;
- failures, warnings, and any manual step that a non-technical operator would not know.

Do not start #124 as a replacement for #123. It depends on #123 and the validation gates represented by #65, #66, #67, #80, #84, and #111.

### #10: M5 model router and local serving

Issue: https://github.com/TECHSCHOLAR777/AirBench/issues/10

This is the backend route that lets the Node choose a suitable registered local model without the agent calling a model directly. It must remain provider-neutral across vLLM and NVIDIA NIM. A registry entry must carry capabilities, modalities, context length, hardware requirements, qualification identity, endpoint or local provider identity, health, priority, and policy state.

The router must:

- classify the required capability from the server-owned task step;
- filter by clearance, qualification, modality, context, hardware, and policy;
- make a deterministic selection;
- record the decision, eligible targets, reason, rule or threshold, model identity, and qualification reference;
- handle health failure and deterministic fallback;
- expose enough route trace for the UI without exposing secrets or raw private reasoning;
- never allow a model response to select the next loop step or grant authority.

Do not hard-code sector knowledge into the router. If the task needs a domain-specific capability, extend the domain-pack contract and register that capability.

### #34: M5.2 HardwareProfile and resource admission

Issue: https://github.com/TECHSCHOLAR777/AirBench/issues/34

This issue is the admission gate that decides whether a worker or model can run on available hardware. It must use explicit typed resource fields and a measured or qualified hardware identity. It must not silently treat a missing GPU, memory limit, disk limit, or runtime version as unlimited.

At minimum, verify:

- CPU, RAM, VRAM, disk, and concurrency limits;
- required model and runtime compatibility;
- capability and modality fit;
- timeout and resource budget;
- reason for admission or rejection;
- deterministic behavior under contention;
- ledger evidence for the decision;
- safe behavior when measurements are unavailable.

This can be developed with deterministic fixtures now, but real hardware measurements belong on the GPU box and must not be invented on this Windows workstation.

## 12. Issues you may encounter but should not silently absorb

These are open issues in the repository, grouped so the queue is understandable. They are not all your coding assignments.

### Local integration and release blockers

- #65, secure local and remote Node connection: https://github.com/TECHSCHOLAR777/AirBench/issues/65. The typed Rust path exists; production profile provisioning, host ACL, signed policy, and target-host proof remain.
- #66, reconnectable sequence-numbered task events: https://github.com/TECHSCHOLAR777/AirBench/issues/66. Cursor replay exists; deliberate connection-drop evidence and packaged proof remain.
- #67, scanned-document upload, artifact preview, and download: https://github.com/TECHSCHOLAR777/AirBench/issues/67. The local digital-PDF path exists; qualified scan OCR or vision and real evidence remain.
- #80, artifact review, approval, and controlled download: https://github.com/TECHSCHOLAR777/AirBench/issues/80. Preview and download projection exist; approval or return actions, visual checks, and full task-driven review remain.
- #84, recovery, accessibility, and frontend release hardening: https://github.com/TECHSCHOLAR777/AirBench/issues/84. Source-level checks exist; packaged keyboard, screen-reader, recovery, and release evidence remain.
- #111, visual regression, accessibility, and sovereign UI validation: https://github.com/TECHSCHOLAR777/AirBench/issues/111. Semantic and source checks pass; packaged visual baseline, accessibility, and independent no-egress evidence remain.
- #119, remaining acceptance gaps from the early backend issues: https://github.com/TECHSCHOLAR777/AirBench/issues/119. This is a cross-system acceptance tracker, not a reason to reimplement closed backend slices. It includes signed manifests, qualified hardware and models, complete vertical flow, no-egress, human review, visual and structural deliverable checks, replay, and signatures.
- #113, manual backend performance and sovereign Node evidence: https://github.com/TECHSCHOLAR777/AirBench/issues/113. This is the human target-host and GPU-box gate. It includes native Linux sandbox, real models, performance, no-egress, ledger export, and human evidence. Do not mark it complete from a VM or synthetic fixture.

### Backend work owned elsewhere or needing coordination

- #14, M9 deliverables and refinery vertical slice: https://github.com/TECHSCHOLAR777/AirBench/issues/14. It composes retrieval, verification, domain pack, and deliverables. Coordinate before changing shared contracts.
- #58, Qwen3-VL qualification for scanned documents and image understanding: https://github.com/TECHSCHOLAR777/AirBench/issues/58. It needs the actual local model and qualification evidence.
- #59, Qwen3-30B-A3B benchmark candidate: https://github.com/TECHSCHOLAR777/AirBench/issues/59. The benchmark covers planning, retrieval synthesis, low-risk drafting, tool formatting, and long-context handling.

### Frontend records and future work

- #81, Review Queue and Artifact Library: https://github.com/TECHSCHOLAR777/AirBench/issues/81.
- #82, Task History and Audit Ledger views: https://github.com/TECHSCHOLAR777/AirBench/issues/82.
- #83, Node, capability, and user settings administration: https://github.com/TECHSCHOLAR777/AirBench/issues/83.
- #86, coding-task workspace. Deferred future capability.
- #87, advanced administration. Deferred future capability.
- #88, fleet management and deployment operations. Deferred future capability.
- #89, collaborative review and editing. Deferred future capability.
- #90, rich local Office editing. Deferred future capability.

The current product objective is the local inspection-report vertical slice. Do not pull #86 through #90 into it unless the issue plan is deliberately changed.

## 13. Human testing instructions for you

You are the person who should close the evidence gap that automation cannot honestly close. For every target-host test, write down:

1. Date, time zone, operator, branch, and commit.
2. Operating system, architecture, Python, Rust, Node, Tauri, WebView2, container runtime, and driver versions.
3. CPU, RAM, GPU, VRAM, model files, quantization, model hash, and serving runtime.
4. The input fixture name and SHA-256. Do not upload or attach a real confidential document to GitHub.
5. The approved Node identity, protocol version, clearance context, and domain-pack reference.
6. The exact commands and UI steps used.
7. The resulting task ID, sequence range, artifact ID, artifact hash, and ledger references where safe to disclose.
8. Network-monitor evidence, including the process tree and whether any external connection was attempted or established.
9. Failures, retries, reconnects, blocked actions, warnings, and cleanup result.
10. A plain-language verdict: passed, failed, or blocked, with the reason.

### Native Linux and GPU-box test

The integrated Podman provider has a POSIX path and the repository includes these tests:

~~~
rg --files tests | grep -Ei 'm61|podman'
~~~

Use the exact test file present on the branch. The earlier expected path is now:

~~~
export AIRBENCH_PODMAN_INTEGRATION=1
export AIRBENCH_PODMAN_IMAGE='docker.io/library/python@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254'
export AIRBENCH_PODMAN_VERSION='5.7.0'
python -m pytest -q tests/test_m61_podman_integration.py
~~~

Run this on the native Linux target, not the Windows VM, when the GPU box is available. If the file or pinned image has changed on main, stop and use the current issue and test fixture instead of forcing an old command. The GPU-box run must go through AirBench's SandboxRunner and record the provider, runtime identity, image digest, resource limits, no-network behavior, cleanup, and any usage data.

### Real scanned document test

Do not use a handwritten or scanned confidential report until the target environment has a qualified local OCR or vision adapter and the input is approved for the test. The test must show:

- File Intake accepted the bytes and created a stable manifest;
- the document remained untrusted data;
- OCR or vision used a qualified local adapter;
- extracted facts retained source region, confidence, clearance, taint, timestamp, and derivation;
- low-confidence or conflicting findings were visible;
- the orchestrator requested review when policy required it;
- the approval note used deterministic values from the Node, not model-written numbers;
- the resulting DOCX was structurally and visually reviewed;
- the final download was hash checked and ledgered.

## 14. Common traps

### The app says Connect a trusted Node

That message means the native approved profile catalog is empty, unreadable, invalid, or not connected. It is a security boundary. Do not solve it by allowing React to type an arbitrary URL.

### The WebDriver test passed, so packaging is done

No. The current real-node runner uses a disposable debug WebDriver build and a temporary profile and credential. #124 still needs clean packaged installation, bundled WebView2, provisioned drivers, independent no-egress evidence, and target-host sign-off.

### The artifact downloaded, so it is verified

No. A download can be hash checked and still be Needs Review because visual verification or human approval is missing. Preserve that state.

### The PDF test proves scanned-document understanding

No. The current fixture is a tiny digitally readable PDF. It proves File Intake and artifact plumbing. It does not prove OCR, handwriting, engineering drawing understanding, or qualified vision.

### The model folder exists, so the router is proven

No. A model file on disk is not a qualification certificate, a serving endpoint, a hardware admission decision, or a measured route result.

### A VM run is the same as the GPU box

No. The VM can help develop and test typed behavior. It cannot substitute for native Linux sandbox isolation, real GPU measurements, or target-host no-egress evidence.

### A green source scanner proves no network traffic

No. Static egress checks are useful but do not observe the operating system. Keep source checks and independent runtime monitoring as separate evidence.

### I can clean all target, cache, and temp directories

No. Use the AirBench cleanup script for known test roots. Do not delete C:\AirBench-models, the Hugging Face cache, active Cargo targets, or another worker's temporary state without a storage audit and an explicit decision.

## 15. Documents to read before changing anything

Start with the repository instructions, then read only the bundle relevant to the issue:

1. [README.md](../../README.md)
2. [docs/README.md](../README.md)
3. [01_architecture_design.md](../foundations/01_architecture_design.md)
4. [02_domain_pack_framework.md](../foundations/02_domain_pack_framework.md)
5. [backend_development_plan.md](../runtime/backend_development_plan.md)
6. [agent_development_workflow.md](agent_development_workflow.md)
7. [AirBench desktop documentation](../desktop/README.md)
8. [Frontend execution plan](../desktop/workflow/frontend_execution_plan.md)
9. [Frontend validation plan](../desktop/validation/frontend_validation_plan.md)
10. [AirBench harness](../runtime/airbench_harness.md)
11. [Model roster](../runtime/models.md)
12. [Assigned issue execution status](assigned_issue_execution_status.md)

For a backend issue, use the M1 through M10 document map in agent_development_workflow.md. For a frontend issue, read the desktop architecture, contract, design, workflow, and validation documents before touching apps/desktop.

## 16. The next smallest responsible move

When you start, do this in order:

1. Pull main and verify the commit and clean state.
2. Run npm run validate:python-node.
3. Run npm run test:desktop:real-node with locally provisioned drivers and watch the application window.
4. Read the issue body and the latest comments on #123 and #124.
5. Run one controlled failure or reconnect test and save its evidence outside the repository until it is scrubbed.
6. Add independent runtime network observation to the local run.
7. Update #123 with exact evidence and an honest blocked or passed verdict.
8. Only after #123 is accepted, begin the serial packaged work in #124.

If a test fails three times for the same environmental reason, stop repeating it. Record the command, failure, environment, and the smallest decision needed from the team. Move to a bounded independent issue only when doing so does not hide the blocker.

## 17. Definition of a good issue update

Use this shape in GitHub comments:

~~~
Environment:
- branch and commit:
- OS and architecture:
- Python, Node, Rust, Tauri, WebView2, driver, runtime versions:

Commands:
- exact command:
- exact UI journey, if applicable:

Result:
- passed, failed, or blocked:
- test counts and key output:
- task, sequence, artifact, and ledger references:

Evidence:
- log or manifest path:
- screenshot path:
- network-monitor result:

Still not proved:
- ...

Next action:
- ...
~~~

Do not write working, done, or production ready without the evidence that makes that statement true.

## 18. Final reminder

The valuable part of AirBench is not that it can produce a fluent answer. The valuable part is that a user can see what the system accepted, what it planned, what it was authorized to do, what evidence it used, what remains uncertain, which artifact was produced, and who or what approved it, while the sensitive work stays inside the organization's boundary.

Your job in the next phase is to make that claim survive a real person, a real target host, a real connection failure, and a real network monitor.

