---
name: airbench-tdd
description: Apply red, green, refactor testing to AirBench Python work, including contract, failure, restart, provenance, and security tests at the affected seam.
metadata:
  short-description: Build AirBench through executable feedback loops
---

# AirBench TDD

Use while implementing or changing behavior. Begin with a failing test or contract fixture that expresses the issue acceptance criterion.

The minimum test set for a consequential seam includes:

- valid input and output;
- malformed or missing fields;
- timeout, retry, and cancellation behavior where applicable;
- restart or idempotency behavior where state is persisted;
- provenance and clearance preservation;
- ledger event creation;
- no-egress or path restriction behavior where tools or files are involved.

Keep model-dependent tests replayable with recorded, sanitized fixtures. Never make a live external service a required test dependency for the local backend.

