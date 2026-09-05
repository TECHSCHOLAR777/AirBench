---
name: airbench-plan
description: Convert a validated AirBench issue into a contract-first Python implementation plan with dependencies, tests, audit events, and acceptance evidence.
metadata:
  short-description: Plan a Python vertical slice from an issue
---

# AirBench plan

Start from the understanding checkpoint produced by `airbench-start-task`. Read the milestone document bundle before planning.

Write a plan that names:

- exact modules and allowed paths;
- typed Python schemas and version changes;
- state transitions owned by the orchestrator;
- model, tool, retrieval, and domain-pack seams;
- ledger events and provenance preservation;
- normal, failure, restart, and security tests;
- serial and parallel work boundaries;
- acceptance commands and artifacts.

Prefer one end-to-end vertical slice over a broad framework shell. Do not create service splits, abstractions, or deferred production requirements unless the issue requires them.

