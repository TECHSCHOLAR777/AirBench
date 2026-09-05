---
name: airbench-debug
description: Diagnose AirBench bugs, test failures, routing failures, nondeterminism, and performance regressions through reproduction, instrumentation, root cause, and regression testing.
metadata:
  short-description: Debug systematically before changing code
---

# AirBench debug

Do not start with a speculative fix. Reproduce the failure with the smallest safe fixture, identify the exact state transition or boundary, and capture relevant ledger, route, tool, provenance, and resource evidence.

Use this loop:

1. reproduce;
2. minimize;
3. instrument;
4. state competing hypotheses;
5. test the hypotheses;
6. fix the root cause;
7. add a regression test;
8. rerun the affected acceptance slice.

Preserve sensitive data handling. Use sanitized fixtures and hashes instead of copying confidential documents into logs or issue comments.

