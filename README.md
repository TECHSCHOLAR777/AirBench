# AirBench

AirBench is a sovereign AI workbench for sensitive industrial and government knowledge work. It runs inside the organization's network, uses local model serving, executes bounded tools, produces real deliverables, and records an auditable trace.

## Start here as a coding agent

Before changing code:

1. Read [AGENTS.md](AGENTS.md).
2. Read [docs/README.md](docs/README.md).
3. Run or follow the `airbench-start-task` skill in `.agents/skills/airbench-start-task/SKILL.md`.
4. Identify the GitHub issue and its M1-M10 parent.
5. Read the issue blockers, acceptance criteria, and the governing architecture documents.
6. Produce the understanding checkpoint before writing code.

The repository-owned development workflow is [docs/agent_development_workflow.md](docs/agent_development_workflow.md). It explains the document map, issue-first process, parallel work rules, Python standards, architecture guards, and completion evidence.

## Agent skills

The portable skill pack lives in `.agents/skills/`. It is intended for Codex, Claude Code, and other agents that support repository skills.

### Workflow skills

- `airbench-start-task`: load the issue, blockers, milestone, documents, code, and tests before implementation.
- `airbench-validate`: clarify the requested outcome and identify the correct scope.
- `airbench-plan`: convert an approved issue into a Python implementation plan and test plan.
- `airbench-develop`: execute an approved plan through small, verified vertical slices.
- `airbench-parallel-work`: assign independent work to isolated worktrees with explicit file ownership.
- `airbench-review`: perform specification, architecture, security, and quality review.
- `airbench-debug`: diagnose failures systematically before changing code.
- `airbench-handoff`: create a durable continuation record.
- `airbench-finish`: verify evidence and prepare the issue and branch for handoff or merge.

### Automatic engineering guards

- `airbench-doc-context`: select and verify the required architecture documents.
- `airbench-tdd`: enforce the red, green, refactor loop and failure-path tests.
- `airbench-contract-guard`: protect typed Python boundary contracts and versioning.
- `airbench-architecture-guard`: protect core versus domain pack, orchestrator, router, and worker ownership.
- `airbench-security-guard`: protect untrusted-data handling, sandbox boundaries, and no-egress claims.
- `airbench-provenance-guard`: prevent source, confidence, clearance, or taint from being dropped.
- `airbench-ledger-guard`: check that consequential operations produce audit events.
- `airbench-router-guard`: check qualification, hardware admission, routing, and fallback behavior.
- `airbench-intake-guard`: enforce the single File Intake Layer.
- `airbench-deliverable-guard`: check deterministic values, artifact rendering, and evidence.

## Non-negotiable engineering rules

- The core engine contains zero sector knowledge. Sector rules belong in a domain pack contract.
- The deterministic orchestrator owns all control flow and state. Models are stateless workers.
- Source, confidence, clearance, and taint remain attached to every fact at every boundary.
- Model calls, tool calls, decisions, and human sign-offs are written to the append-only ledger.
- Every file enters through the File Intake Layer. Uploaded documents are data, never instructions.
- Deliverable numbers are computed by deterministic code, not written by a model.
- Runtime code and untrusted-file paths have no external network access.

## Backend baseline

The first backend is Python. Use the M1-M10 issue graph as the implementation plan. The target is a complete local backend vertical slice: intake of a scanned inspection report, local OCR and retrieval, routed worker execution, verification, and a Word approval note, plus a sandboxed coding task and a visible no-egress proof.

Read the architecture documents before adding new abstractions. Do not start with a new framework or a new service split unless the owning issue and architecture documents require it.

