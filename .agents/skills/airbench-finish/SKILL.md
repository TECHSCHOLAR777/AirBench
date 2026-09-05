---
name: airbench-finish
description: Finish an AirBench issue by verifying tests, architecture guards, security evidence, documentation, issue state, and final diff before merge or push.
metadata:
  short-description: Produce completion evidence before handoff
---

# AirBench finish

Before claiming completion:

- run focused and relevant full tests;
- run type checking and linting;
- run the applicable contract, architecture, security, provenance, ledger, intake, router, and deliverable guards;
- inspect the final diff for unrelated changes and secrets;
- verify docs and issue acceptance criteria match the implementation;
- record exact commands, results, artifacts, and known risks on the issue;
- create a handoff if work remains.

Do not push, release, close, or merge unless the user or repository workflow explicitly authorizes that external mutation. A green test run is evidence, not permission.

