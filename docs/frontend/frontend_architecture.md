# AirBench Frontend Architecture

## 1. Purpose and boundary

The AirBench frontend is an offline-capable desktop application for non-technical users, reviewers, operators, and auditors. It presents work performed by the Python AirBench Node and sends explicit user commands back to that Node.

The frontend is not an autonomous runtime. It does not own the task loop, model routing, tool permissions, file parsing, verification, calculations, clearance decisions, artifact approval, or the audit ledger.

The central boundary is:

```text
User
  |
Tauri desktop shell
  |  Rust-owned commands, capability allowlist, trust and transport boundary
  |
AirBench Node
  |  Orchestrator, router, tools, intake, retrieval, verification, ledger
  |
Local or remote internal model-serving and storage services
```

The user may connect to a GPU server across the organization's private network. That is still an internal AirBench Node connection. It is not permission to access the public internet.

## 2. Runtime stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Native shell | Tauri 2 and Rust | Window lifecycle, capability permissions, approved transport, certificate or trust handling, secure file-picker handoff, and packaged offline runtime. |
| Webview UI | React 19 and TypeScript | Screens, interaction state, accessibility, event projections, previews, and typed command dispatch. |
| Build | Vite | Static frontend bundle and development server only. No Node runtime is shipped in production. |
| Accessible interaction | React Aria primitives | Focus, keyboard, dialog, menu, tabs, listbox, grid, and screen-reader behavior. |
| Styling | CSS Modules and AirBench tokens | Local component styles, density, color semantics, high contrast, and theme. |
| Backend protocol | Versioned typed API and event stream | Snapshot, command, event, artifact, evidence, clearance, and error contracts. |
| Test runtime | Vitest, React Testing Library, accessibility tooling, Tauri WebDriver, and local network fixtures | Unit, component, contract, desktop, recovery, and no-egress evidence. |

The actual package manager, exact Vite plugin set, and Tauri bundling commands are pinned by FE-VAL-1 before application implementation begins.

## 3. Process model

### 3.1 Tauri process

The Rust layer is the only frontend component allowed to perform privileged desktop operations. It owns:

- approved AirBench Node connection profiles;
- pinned endpoint or certificate verification;
- allowlisted request methods and paths;
- authenticated transport;
- connection lifecycle and reconnect coordination;
- safe handoff to the native file picker;
- command serialization and correlation IDs;
- prevention of arbitrary external navigation;
- capture of transport and backend logs needed by desktop tests.

The Rust layer does not reinterpret task policy or become a second orchestrator. It transports typed messages and enforces the desktop boundary.

### 3.2 Webview process

The React application owns:

- the current screen and local presentation state;
- rendering server snapshots and ordered events;
- local filters, selections, drawers, and unsent form text;
- accessible interactions;
- safe display of Node-produced previews;
- typed command requests through the Tauri bridge.

The webview must not:

- use arbitrary `fetch` or WebSocket calls;
- load resources from a URL supplied by a document or model;
- parse uploaded files as an alternative intake path;
- run document JavaScript or macros;
- select models or tools directly;
- calculate authoritative deliverable values;
- write authoritative task status to local storage;
- use a model response as an instruction to change UI authority.

Approved profile discovery is native-owned. The current development slice reads the administrator-provisioned `approved-node-profiles.json` from the Tauri application configuration directory, validates every profile before exposing it to the webview, and never accepts an endpoint form in React. Host ACL provisioning and signed policy verification remain release work for FE-DEV-03 and FE-VAL-2; a writable profile file is not sufficient evidence of production approval.

### 3.3 AirBench Node

The Python Node remains the authority for:

- deterministic orchestration and task state;
- hardware-aware team scheduling;
- model routing and qualification;
- tool gateway and sandbox policy;
- File Intake Layer;
- knowledge and retrieval;
- provenance, confidence, clearance, and taint;
- verification and consistency checks;
- autonomy and approval requirements;
- deliverable assembly and deterministic values;
- append-only signed Memory and Audit Ledger.

## 4. Deployment shapes

### Local workstation

```text
Tauri app on workstation
  -> loopback or approved local AirBench Node
  -> local model serving, stores, sandbox, and ledger
```

### Remote internal GPU server

```text
Tauri app on user workstation
  -> pinned authenticated internal Node endpoint
  -> AirBench Node on GPU server
  -> model serving, tools, stores, sandbox, and ledger on the private network
```

The UI must not connect directly to the model-serving tier in either shape. The Node is the single application boundary.

## 5. Security posture

On Windows, the packaged WebView2 window is started with background networking, component update, domain reliability, sync, crash reporting, and breakpad features disabled, and its proxy is a non-listening loopback endpoint. Tauri's default disabled WebView2 feature set is retained. These settings reduce incidental browser-runtime traffic but are not the sovereignty boundary. The current Windows shell also disables QUIC and applies a host-resolver rule that excludes only loopback names. The release profile must still apply an OS firewall or equivalent allowlist that permits only the approved AirBench Node transport, and FE-VAL-5 must capture the resulting deny and allow evidence.

The runtime harness records WebView2 descendants and fails when it observes a non-loopback established connection. An elevated host validation run must apply temporary outbound block rules scoped to the installed WebView2 executable paths, capture Windows Firewall dropped-packet logs, and restore the host policy after the run. The browser flags are reduction measures, not proof that WebView2 has no egress.

- Ship a static bundle with all fonts, icons, styles, preview workers, and runtime assets local to the installer.
- Bundle WebView2 for the supported Windows deployment profile and prove startup with the network disabled.
- Restrict Tauri capabilities to the exact commands needed by the current build.
- Disable arbitrary navigation and external window opening by default.
- Apply a restrictive content security policy with no external script, font, image, or connection source.
- Do not expose backend secrets, certificates, or private keys to the webview.
- Keep preview content isolated and sanitized. Prefer Node-generated PDF, image, text, and structured preview artifacts.
- Use local logs and hashes as evidence. Do not send diagnostics to a hosted service.
- Treat the UI sovereignty badge as a view of Node evidence, never as the evidence itself.

## 6. Core versus domain-pack boundary

The frontend core remains sector-neutral. It provides generic concepts:

- task;
- project;
- plan;
- worker role;
- evidence;
- source;
- artifact;
- verification;
- approval;
- clearance;
- ledger event;
- node and model capability.

A domain pack may provide labels, document profiles, field checks, artifact templates, risk descriptions, and approval rules through typed contracts. It may not inject sector logic into generic React components, bypass Node policy, or create a direct model or tool path.

If a domain needs a new UI concept that is valid across sectors, widen the typed contract. If it is specific to a field, render it through the domain-pack extension surface.

## 7. Architectural failure boundaries

| Failure | Frontend behavior | Authority |
| --- | --- | --- |
| Node unavailable | Show cached records if allowed, block new consequential work, offer reconnect | Node connection policy |
| Event gap | Stop applying new events, request replay or snapshot, show resync state | Event protocol |
| Certificate or trust failure | Block connection and explain that the endpoint is not trusted | Rust transport boundary |
| Model fallback | Show capability lane and fallback reason in technical detail | Router and ledger |
| Intake rejection | Show typed file reason and preserve the rejected manifest event | File Intake Layer |
| Clearance mismatch | Hide or redact content and block action | Node clearance policy |
| Verification failure | Keep artifact in draft or needs-review state | Verification Framework |
| Ledger failure | Do not commit the consequential transition or continue the action | Memory and Audit Ledger |
| Preview failure | Offer a safe alternate preview or download if permitted, never execute the original content | Deliverable and preview boundary |

## 8. Architectural acceptance

The frontend architecture is accepted only when it can demonstrate:

- one trusted path from desktop user to AirBench Node;
- no model-server or cloud path from the UI;
- reconnectable authoritative event state;
- safe intake and preview behavior for untrusted documents;
- preserved provenance and clearance in rendered facts;
- explicit approval and failure states;
- offline installation and no-egress evidence.
