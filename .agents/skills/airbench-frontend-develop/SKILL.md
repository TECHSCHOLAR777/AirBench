---
name: airbench-frontend-develop
description: "Build AirBench frontend slices with typed offline-safe contracts."
---

# AirBench Frontend Develop

Use this skill only after a frontend issue, its validation criteria, and its Node contract have been approved.

## Required startup

1. Read `AGENTS.md` and the issue, including its M milestone and blockers.
2. Read `docs/frontend/README.md`, `frontend_architecture.md`, `frontend_contracts_and_state.md`, and the issue's validation document.
3. Load `airbench-architecture-guard`, `airbench-contract-guard`, and `airbench-security-guard` when their concerns are touched.
4. Produce an understanding checkpoint covering scope, non-goals, files, schemas, event transitions, provenance fields, security boundary, tests, and evidence.

## Implementation rules

- Use Tauri 2 with Rust as the desktop boundary, React and TypeScript for the UI, and Vite for the static bundle.
- Keep all transport allowlisted and Rust-owned. The frontend never calls model servers, vLLM, NIM, arbitrary URLs, cloud services, or a second file parser.
- Use typed snapshots, commands, and sequence-numbered events. Reconnect by cursor replay or explicit resync, never by guessed optimistic state.
- Keep authoritative task state in the Node. Frontend state is presentation state plus a reducer-built projection.
- Preserve source, confidence, clearance, taint, timestamps, derivation, and ledger references in every fact and evidence projection.
- Render document previews from safe Node-produced artifacts. Never execute document content, macros, or uploaded scripts in the webview.
- Show model routing as a capability request by default. Exact model and fallback information belongs in technical detail.
- Keep numerical values and calculations authoritative in the backend and deliverable engine.
- Build red, green, refactor slices with normal, failure, reconnect, accessibility, and no-egress tests.

## Completion evidence

Run focused unit and component tests, TypeScript checks, accessibility checks, Tauri desktop tests, and applicable security or no-egress validation. Update the issue with exact commands, results, screenshots or logs, and remaining limitations. Do not claim completion from a rendered screen alone.
