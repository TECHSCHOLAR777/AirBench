---
name: airbench-start-task
description: Start an AirBench implementation task by inspecting its GitHub issue, blockers, milestone, architecture documents, repository state, and tests before any code is written.
metadata:
  short-description: Understand the issue and governing docs before coding
---

# AirBench start task

Use this skill at the beginning of every implementation, bug fix, refactor, or architecture change.

Read `AGENTS.md`, `README.md`, `docs/README.md`, `docs/architecture_design.md`, `docs/domain_pack_framework.md`, `docs/backend_development_plan.md`, and `docs/agent_development_workflow.md`. Then identify the assigned GitHub issue and its M1-M10 parent. Inspect blockers, labels, sibling issues, acceptance criteria, current branch, working tree, relevant modules, and tests.

Select the milestone document bundle from `docs/agent_development_workflow.md`. Read those documents before proposing implementation.

Produce an understanding checkpoint with:

- user outcome and issue acceptance criteria;
- scope and non-goals;
- governing documents and sections;
- core versus domain-pack ownership;
- contracts, state transitions, and ledger events touched;
- provenance and security invariants;
- failure, retry, queue, escalation, and stop behavior;
- files allowed to change;
- tests and evidence required for completion.

Do not write code if the issue is missing, blocked, ambiguous, or inconsistent with the architecture. Ask for clarification or report the blocker. This skill does not authorize external pushes, releases, or production changes.

