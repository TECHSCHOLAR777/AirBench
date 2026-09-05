---
name: airbench-handoff
description: Create a compact, evidence-backed AirBench handoff so another agent can continue without trusting a conversation summary.
metadata:
  short-description: Preserve durable development context
---

# AirBench handoff

Write a handoff in the task's approved scratch or issue location containing:

- issue, parent milestone, branch, and worktree;
- completed behavior and remaining scope;
- governing documents and contracts touched;
- files changed and files intentionally untouched;
- tests and exact results;
- failing tests or blockers;
- decisions and rejected alternatives;
- security, provenance, ledger, and deployment risks;
- the next smallest action.

Do not treat a model-generated summary as authoritative system state. Reference repository files, test output, issue links, hashes, and ledger evidence instead.

