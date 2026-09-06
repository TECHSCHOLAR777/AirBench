---
name: airbench-frontend-review
description: "Review AirBench frontend quality, contracts, accessibility, and security."
---

# AirBench Frontend Review

Use this skill before merging frontend work or closing a frontend validation issue.

## Review order

1. Read the originating issue and `docs/frontend/README.md`.
2. Check the changed screen against `frontend_screen_specification.md` and `frontend_design_system.md`.
3. Check the Node boundary against `frontend_architecture.md` and `frontend_contracts_and_state.md`.
4. Check applicable AirBench guards: architecture, contract, security, provenance, intake, ledger, router, and deliverable.
5. Run the focused frontend tests and the relevant validation track from `frontend_validation_plan.md`.

## Review questions

- Does the UI represent server-authoritative state, including reconnect and event gaps?
- Can any untrusted file content become executable markup, instructions, macros, or navigation?
- Are source, confidence, clearance, taint, derivation, and ledger references retained at every boundary?
- Is the user shown a clear distinction between draft, verified, approved, blocked, and failed?
- Are parallel and serial worker modes represented honestly?
- Can a user or UI action bypass model qualification, clearance, approval, deterministic calculations, or audit logging?
- Does the surface work with keyboard navigation, screen readers, reduced motion, and high-contrast settings?
- Does the shipped bundle remain offline-safe with no external fonts, scripts, URLs, analytics, or arbitrary webview navigation?

## Review output

Report findings by severity with file and line references, concrete impact, and a required fix. State the commands and evidence run. Do not approve a screen solely because it looks polished.
