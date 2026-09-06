# AirBench Frontend Documentation

This folder defines the AirBench desktop workbench. It is the frontend contract and design source of truth for the Tauri application that connects users to an AirBench Node.

The frontend is not a second orchestrator, model client, parser, calculator, or audit system. It is a trusted presentation and command surface over the authoritative Python AirBench Node.

## Implementation status

The first frontend runtime now lives in the repository's `frontend/` directory. It is a Tauri 2 desktop shell with a React and TypeScript presentation layer. The initial slice is intentionally disconnected from the Node: it proves local startup, truthful disconnected state, local assets, and a fail-closed security boundary before transport is introduced.

The implementation order is tracked by the development issues below. The validation issues remain evidence gates and are not replaced by a rendered mockup.

| Development issue | Outcome | Lane |
| --- | --- | --- |
| [FE-DEV-01, #73](https://github.com/TECHSCHOLAR777/AirBench/issues/73) | Secure Tauri shell | Parallel foundation |
| [FE-DEV-02, #74](https://github.com/TECHSCHOLAR777/AirBench/issues/74) | Typed Node protocol and event projection | Serialized contract |
| [FE-DEV-03, #75](https://github.com/TECHSCHOLAR777/AirBench/issues/75) | Trusted Node connection | Serial critical path |
| [FE-DEV-04, #76](https://github.com/TECHSCHOLAR777/AirBench/issues/76) | Home, task creation, and File Intake handoff | Serial critical path |
| [FE-DEV-05, #77](https://github.com/TECHSCHOLAR777/AirBench/issues/77) | Task Plan Review | Serial critical path |
| [FE-DEV-06, #78](https://github.com/TECHSCHOLAR777/AirBench/issues/78) | Live Task Workspace | Serial critical path |
| [FE-DEV-07, #79](https://github.com/TECHSCHOLAR777/AirBench/issues/79) | Evidence and safe preview | Serial critical path |
| [FE-DEV-08, #80](https://github.com/TECHSCHOLAR777/AirBench/issues/80) | Artifact Review and approval | Serial critical path |
| [FE-DEV-09, #81](https://github.com/TECHSCHOLAR777/AirBench/issues/81) | Review Queue and Artifact Library | Parallel records |
| [FE-DEV-10, #82](https://github.com/TECHSCHOLAR777/AirBench/issues/82) | Task History and Audit Ledger | Parallel records |
| [FE-DEV-11, #83](https://github.com/TECHSCHOLAR777/AirBench/issues/83) | Node and settings administration | Parallel records |
| [FE-DEV-12, #84](https://github.com/TECHSCHOLAR777/AirBench/issues/84) | Recovery, accessibility, and hardening | Serial release gate |
| [FE-DEV-13, #85](https://github.com/TECHSCHOLAR777/AirBench/issues/85) | Packaged desktop end-to-end integration | Serial release gate |

Future frontend capabilities are tracked separately in [FE-FUT-01 through FE-FUT-05](https://github.com/TECHSCHOLAR777/AirBench/issues/86), and must not displace the first inspection-report vertical slice.

## Read in this order

1. `frontend_architecture.md` for the desktop runtime, deployment topology, process boundaries, and offline security model.
2. `frontend_design_system.md` for visual tokens, layout, interaction primitives, accessibility, and status vocabulary.
3. `frontend_interaction_analysis.md` for the Claude and Codex pattern analysis and the simplification decisions.
4. `frontend_screen_specification.md` for every screen, state, action, and user journey.
5. `frontend_contracts_and_state.md` for snapshots, sequence-numbered events, commands, provenance, permissions, and reconnect behavior.
6. `frontend_validation_plan.md` for the six validation tracks, evidence, pass criteria, and failure tests.
7. `frontend_development_workflow.md` for issue ownership, parallel work, integration order, and completion evidence.
8. `frontend_validation_issues.md` for the six GitHub issue definitions, dependencies, labels, and acceptance evidence.

## Frontend invariants

- The AirBench Node owns orchestration, routing, tools, verification, provenance, clearance, artifact state, and the audit ledger.
- The UI connects only to the AirBench Node through a Rust-owned, typed, allowlisted boundary.
- The UI never calls vLLM, NVIDIA NIM, a model endpoint, a cloud service, or an arbitrary URL.
- Uploaded and ingested documents are untrusted data. The UI does not execute their instructions, macros, scripts, or links.
- Files are parsed and normalized only by the File Intake Layer. The UI receives manifests and safe preview artifacts.
- Facts and evidence retain source, confidence, clearance, taint, timestamp, derivation, and ledger references.
- The UI never creates authoritative numbers, verifies its own output, changes clearance, selects an unqualified model, or marks an artifact approved.
- Every consequential UI command is typed, permission-checked by the Node, idempotency-aware, and written to the ledger.
- A disconnected or uncertain state fails closed for consequential actions.

## Validation issue map

The six validation issues are tracked in GitHub and map to `frontend_validation_plan.md`:

| Track | Scope |
| --- | --- |
| [FE-VAL-1](https://github.com/TECHSCHOLAR777/AirBench/issues/64) | Offline Tauri installation, bundled WebView2, and offline startup |
| [FE-VAL-2](https://github.com/TECHSCHOLAR777/AirBench/issues/65) | Secure local and remote AirBench Node connection |
| [FE-VAL-3](https://github.com/TECHSCHOLAR777/AirBench/issues/66) | Reconnectable sequence-numbered task-event streaming |
| [FE-VAL-4](https://github.com/TECHSCHOLAR777/AirBench/issues/67) | Scanned-document intake, safe artifact preview, and download |
| [FE-VAL-5](https://github.com/TECHSCHOLAR777/AirBench/issues/68) | Network-monitor and no-external-contact proof |
| [FE-VAL-6](https://github.com/TECHSCHOLAR777/AirBench/issues/69) | Tauri WebDriver desktop integration and multiremote evidence |

The IDs are stable design references. GitHub issue numbers are recorded in the issue index or in the milestone tracker when created.
