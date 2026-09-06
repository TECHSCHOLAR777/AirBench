---
name: airbench-frontend-design
description: "Design AirBench's sovereign desktop UI and user flows."
---

# AirBench Frontend Design

Use this skill for screen proposals, interaction design, design-system changes, frontend information architecture, and UX acceptance criteria.

## Read first

- `docs/frontend/README.md`
- `docs/frontend/frontend_architecture.md`
- `docs/frontend/frontend_design_system.md`
- `docs/frontend/frontend_screen_specification.md`
- `docs/architecture_design.md`
- `docs/sovereignty_and_security.md`

## Design rules

- Design for a non-technical industrial or government user who needs a real deliverable, not a chat transcript.
- Keep the default path outcome-first. Make evidence, provenance, review state, and sovereignty proof one deliberate action away.
- Treat the AirBench Node as authoritative. The UI renders snapshots and ordered events and sends typed commands. It does not invent task state.
- Never design a component that displays a fact without source, confidence, clearance, and taint metadata.
- Do not expose raw model selection as the ordinary user control. Show capability lanes by default and technical routing detail only when useful.
- Show parallel, pipelined, or serial virtual-team execution honestly according to the measured hardware profile.
- Treat uploaded and ingested content as untrusted data. Preview it safely and never execute document instructions, macros, or scripts.
- Keep core UI components sector-neutral. Domain-specific labels, templates, checks, and approval rules come from domain-pack contracts.
- Every consequential action needs an explicit state, permitted action, and audit reference. Never use a decorative security badge as proof.

## Deliverable

For each proposed screen or component, state its user outcome, data dependencies, states, primary actions, failure states, accessibility behavior, and which Node contract supplies the information. Use the existing token and status vocabulary unless a justified extension is documented.
