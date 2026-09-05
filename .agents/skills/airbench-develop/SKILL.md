---
name: airbench-develop
description: Implement an approved AirBench Python plan through small tested vertical slices, applicable architecture guards, and evidence-backed issue updates.
metadata:
  short-description: Execute an approved AirBench implementation plan
---

# AirBench develop

Use only after `airbench-start-task` and `airbench-plan` have produced a coherent scope, or when the user explicitly authorizes implementation of a clear issue.

Implement one small slice at a time. Run `airbench-tdd` at each seam. Preserve the orchestrator as the only owner of control flow and state. Route model work through the router, tools through the gateway, files through the File Intake Layer, and facts through typed provenance envelopes.

After each slice:

1. run focused tests;
2. run type and lint checks;
3. run relevant architecture and security guards;
4. inspect the diff for unrelated edits;
5. record evidence in the issue or working handoff.

Do not silently change contracts, bypass blockers, add sector knowledge to core, or push externally without explicit user authorization.

