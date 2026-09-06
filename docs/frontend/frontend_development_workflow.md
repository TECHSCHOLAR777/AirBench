# AirBench Frontend Development Workflow

## 1. Purpose

The frontend and backend will be developed in parallel, but they integrate through explicit contracts. Frontend progress must not create a second backend authority or depend on guessed API behavior.

## 2. Required issue startup

Before implementation of any frontend issue:

1. Read `AGENTS.md` and the issue, parent milestone, blockers, and sibling issues.
2. Read `docs/frontend/README.md` and the document bundle named by the issue.
3. Load `airbench-frontend-design`, `airbench-frontend-develop`, or `airbench-frontend-validate` as applicable.
4. Produce an understanding checkpoint with user outcome, scope, non-goals, ownership, contracts, state transitions, provenance, security, tests, and files.
5. Confirm whether the issue is a design-only, contract, fixture, frontend, backend, or integration change.

No frontend issue starts by inventing mock data that contradicts the Node contract.

## 3. Workstream ownership

### Frontend workstream

Owns:

- Tauri shell and capability manifest;
- React screens and accessible components;
- event projection and reconnect presentation;
- typed command dispatch;
- safe preview rendering;
- UI tests and desktop test harness;
- offline and no-egress evidence from the client side.

### Backend workstream

Owns:

- task, plan, event, command, artifact, evidence, and error contracts;
- Node connection endpoint and trust configuration;
- orchestrator state and event emission;
- File Intake Layer and artifact preview production;
- provenance and clearance decisions;
- router, tools, verification, ledger, and sovereignty evidence.

### Shared contract work

The following are serialized integration points:

- protocol schemas and version negotiation;
- event sequence semantics;
- command idempotency behavior;
- artifact preview media types;
- clearance and redaction rules;
- ledger event references;
- no-egress allowlist.

Only one issue may own a shared contract at a time.

## 4. Recommended parallel plan

| Workstream | Can run in parallel with | Must wait for |
| --- | --- | --- |
| UI design tokens and screens | Backend contract design | Approved screen specification |
| Tauri shell spike | Backend mock Node | FE-VAL-1 environment choice |
| Event store and reconnect fixture | Intake and preview fixture | Event contract draft |
| Node transport fixture | Offline packaging | Connection and trust contract |
| Intake preview fixture | Event store | File Intake and artifact contract |
| No-egress policy review | All local fixture work | Final transport and resource allowlist |
| Desktop WebDriver integration | Component development | Stable shell and fixture contracts |
| Full inspection-report demo | None at final stage | FE-VAL-1 through FE-VAL-5 |

## 5. Vertical slice order

### Slice A: shell and trusted connection

- static Tauri shell;
- approved connection profile;
- Node identity and status;
- offline startup;
- no arbitrary navigation.

### Slice B: task intake and plan

- Home;
- New Task;
- File Intake handoff;
- plan review;
- typed task commands;
- initial ledger references.

### Slice C: live event projection

- task snapshot;
- ordered timeline;
- worker and hardware mode;
- reconnect and event gap;
- pause and stop policy.

### Slice D: evidence and artifact review

- source drawer;
- provenance strip;
- safe scanned-document preview;
- Word or PDF artifact preview;
- deterministic value display;
- approval gate.

### Slice E: records and administration

- review queue;
- artifact library;
- task history;
- audit ledger;
- node and model roster;
- settings and identity.

### Slice F: desktop hardening

- offline installer;
- no-egress monitor;
- WebDriver and IPC mocking;
- recovery injection;
- accessibility and performance checks.

## 6. Testing rules

Each slice includes:

- component tests for normal rendering;
- failure-state tests;
- keyboard and accessibility checks;
- contract fixture tests;
- reconnect or restart behavior when relevant;
- no-egress checks when transport or packaging changes;
- architecture and security guard review.

The frontend must be tested against deterministic fixtures and a real local Node path before a screen is called integrated.

## 7. Definition of done

A frontend issue is complete only when:

- the UI behavior matches the screen and contract documents;
- the Node remains authoritative;
- source, confidence, clearance, taint, derivation, and ledger references are preserved;
- untrusted content is displayed safely;
- normal, blocked, failure, reconnect, and permission states are covered;
- tests and type checks pass;
- applicable validation evidence exists;
- the issue contains exact commands and results;
- the final diff has been reviewed for no-egress and architecture violations.

## 8. Deferred scope

Do not pull these into the first frontend vertical slice without a new issue and architecture review:

- multi-site fleet administration;
- public cloud sync or telemetry;
- arbitrary third-party connectors;
- mobile phone application;
- full collaborative editing;
- unrestricted plugin marketplace;
- rich in-browser Office editing;
- identity-bound enterprise approval beyond the first-scope review gate;
- drawing-pipeline-specific UI before its contract is supplied.
