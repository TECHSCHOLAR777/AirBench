---
name: airbench-parallel-work
description: Plan and execute parallel AirBench issue work using dependency edges, isolated worktrees, explicit file ownership, and serialized integration points.
metadata:
  short-description: Coordinate safe parallel engineering work
---

# AirBench parallel work

Use when multiple M1-M10 sub-issues can be developed concurrently.

Before dispatch, verify native issue dependencies and divide work by contract or directory. Give each worker an issue, document bundle, allowed paths, expected outputs, test commands, and handoff format. Use separate worktrees or equivalent isolated branches.

Parallelize independent adapters, fixtures, tests, documentation, and isolated packages. Serialize shared schemas, migrations, orchestrator transitions, ledger formats, integration tests, and merge conflict resolution. No worker may silently edit another worker's contract or broaden its issue.

Every worker returns changed files, tests, decisions, risks, and unresolved blockers. The parent agent integrates only after specification and architecture review.

