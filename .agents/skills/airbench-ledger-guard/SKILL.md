---
name: airbench-ledger-guard
description: Check that consequential AirBench operations create append-only, replayable, clearance-aware audit events with sufficient identity and hashes.
metadata:
  short-description: Protect auditability and replay
---

# AirBench ledger guard

Use when changing orchestrator transitions, model calls, routing, tool execution, facts, retrieval, verification, human approval, retries, cancellation, or completion.

Require events for at least:

- task and team creation;
- worker assignment and handoff;
- model request, route decision, response hash, and failure;
- tool request, authorization decision, execution, and result;
- intake and evidence creation;
- fact candidate and committed state;
- verification and evaluator outcomes;
- retry, fallback, escalation, human sign-off, completion, and cancellation.

Check append-only ordering, event identity, parent task and worker identity, model or tool version, input and output hashes, clearance, and failure visibility. A ledger write failure must block or quarantine the consequential action; it must not disappear into ordinary logs.

