# AirBench Agent Development Workflow

This document is the operating contract for coding agents working on AirBench. The repository skills in `.agents/skills/` implement this workflow for Codex, Claude Code, and other compatible agents.

## Source of truth

The agent resolves conflicts in this order:

1. The user's current request.
2. The assigned GitHub issue and its acceptance criteria.
3. `architecture_design.md` and the governing architecture document.
4. The relevant contract and test fixtures.
5. Existing implementation details.

If a requested change conflicts with an architecture invariant, stop and report the conflict. Do not quietly reinterpret the request.

## Required startup sequence

Every implementation task begins with an understanding checkpoint.

1. Identify the issue number, M1-M10 parent, labels, blockers, dependencies, and sibling sub-issues.
2. Check that the issue is not blocked by an open prerequisite.
3. Read `docs/README.md`, `docs/architecture_design.md`, `docs/domain_pack_framework.md`, and `docs/backend_development_plan.md`.
4. Select the milestone document bundle below.
5. Inspect the repository tree, current branch, working tree, existing tests, and nearby modules.
6. Write the checkpoint with scope, non-goals, contracts, invariants, risks, files, and tests.
7. Only after the checkpoint is coherent may the agent plan or code.

## Milestone document map

| Milestone | Read these documents before implementation |
| --- | --- |
| M1 | `airbench_harness.md`, `domain_pack_framework.md`, `serving_and_routing.md`, `memory_and_audit_ledger.md` |
| M2 | `memory_and_audit_ledger.md`, `sovereignty_and_security.md`, `airbench_harness.md` |
| M3 | `orchestration_engine.md`, `airbench_harness.md`, `autonomy_governor.md`, `memory_and_audit_ledger.md` |
| M4 | `airbench_harness.md`, `orchestration_engine.md`, `serving_and_routing.md`, `deployment_and_scale.md` |
| M5 | `serving_and_routing.md`, `model_qualification_framework.md`, `models.md`, `model_routing_review.md` |
| M6 | `sovereignty_and_security.md`, `orchestration_engine.md`, `airbench_harness.md`, `deployment_and_scale.md` |
| M7 | `file_intake_layer.md`, `knowledge_and_retrieval_engine.md`, `world_model_engine.md`, `domain_pack_framework.md` |
| M8 | `verification_framework.md`, `consistency_engine.md`, `autonomy_governor.md`, `memory_and_audit_ledger.md` |
| M9 | `deliverable_engine.md`, `domain_pack_framework.md`, `file_intake_layer.md`, `verification_framework.md` |
| M10 | `deployment_and_scale.md`, `sovereignty_and_security.md`, `model_qualification_framework.md`, `backend_development_plan.md` |

Read `future_full_fledged_must_have.md` when a task appears to expand deferred scope. Do not pull deferred requirements into the current milestone without an issue change.

## Understanding checkpoint

The checkpoint must answer:

- What user outcome does the issue deliver?
- Which M milestone owns it?
- What is explicitly out of scope?
- Which core or domain-pack boundary is touched?
- Which schemas, state transitions, and ledger events change?
- Which source, confidence, clearance, and taint fields must survive?
- What can fail, retry, queue, escalate, or stop?
- Which tests demonstrate normal, failure, restart, and security behavior?
- Which files and directories may be edited?

## Implementation loop

Use a small vertical slice:

1. Write a failing test or contract fixture.
2. Implement the smallest behavior that satisfies it.
3. Run the focused test.
4. Add failure-path and boundary tests.
5. Run type checks, linting, and relevant integration tests.
6. Run the architecture, security, provenance, and ledger guards that apply.
7. Update the issue with commands, results, artifacts, and remaining risks.

## Parallel work

Parallel work is allowed only when issue dependencies and file ownership are explicit. Use separate worktrees. Shared contracts, migrations, orchestrator transitions, and integration tests are serialized. Each worker receives the issue, document bundle, allowed paths, expected outputs, and verification commands.

## Completion evidence

Do not claim completion from a model response. Completion requires:

- focused tests and the appropriate full test slice;
- type and lint checks;
- contract compatibility evidence;
- no-egress or security evidence when relevant;
- ledger event evidence for consequential behavior;
- artifact or rendering evidence for deliverables;
- issue update with exact commands and results;
- review of the final diff against the originating issue.

