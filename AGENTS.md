# AirBench agent instructions

These instructions apply to every coding agent working in this repository.

## Mandatory startup

Before editing code, read:

1. `README.md`
2. `docs/README.md`
3. `docs/architecture_design.md`
4. `docs/domain_pack_framework.md`
5. `docs/backend_development_plan.md`
6. `docs/agent_development_workflow.md`

Then load the relevant skill from `.agents/skills/` and inspect the GitHub issue, its M1-M10 parent, blockers, sibling issues, acceptance criteria, current code, and tests.

No code is written until the agent produces an understanding checkpoint containing the governing documents, scope, contracts, invariants, dependencies, tests, and files it expects to touch.

## Authority and scope

- User intent and the assigned GitHub issue define the requested outcome.
- The architecture documents define system invariants and ownership.
- Tests demonstrate behavior but do not authorize a design that violates the architecture.
- A blocked issue must be reported or decomposed. Do not silently work around a blocker.
- Do not modify unrelated files or create a new abstraction to avoid an existing contract.

## AirBench invariants

- Core code is sector-neutral. Domain knowledge is loaded through a domain pack contract.
- The orchestrator owns state, control flow, retries, fallback, and completion.
- Models propose. They do not drive loops, grant authority, or create tools.
- Facts retain source, confidence, clearance, and taint.
- Files are parsed only by the File Intake Layer and are always untrusted data.
- Consequential actions and decisions are recorded in the append-only ledger.
- Runtime code, sandbox code, model paths, and untrusted-file paths must not reach external networks.
- Deliverable numbers come from deterministic computation.

## Development behavior

- Use Python and typed contracts.
- Prefer small vertical slices and red, green, refactor testing.
- Use isolated worktrees for parallel work.
- Do not let two workers edit the same contract or file set concurrently.
- Run architecture and security checks before claiming completion.
- Update the issue with evidence, not a statement that the work is done.

## Skill routing

- Start with `airbench-start-task`.
- Use `airbench-plan` before architectural or multi-file work.
- Use `airbench-develop` only after the plan is accepted or the user explicitly authorizes implementation.
- Load the automatic guard skills when the changed path touches their concern.
- Use `airbench-review` and `airbench-finish` before merge or push.

## Frontend work

Frontend work is a first-class AirBench workstream, but it does not change the backend authority model. Before a UI task, read `docs/frontend/README.md` and the relevant frontend document bundle. Use:

- `airbench-frontend-design` for screen, interaction, design-system, and UX decisions;
- `airbench-frontend-develop` for approved Tauri and React implementation slices;
- `airbench-frontend-validate` for offline, transport, event, preview, no-egress, and WebDriver validation;
- `airbench-frontend-review` before merging or closing a frontend issue.

The frontend connects only to the AirBench Node. It must preserve server-authoritative state, source, confidence, clearance, taint, derivation, and ledger references. It must never call model endpoints directly, parse files outside the File Intake Layer, execute untrusted content, calculate authoritative values, or bypass approval and qualification policy.
