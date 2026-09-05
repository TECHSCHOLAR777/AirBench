---
name: airbench-contract-guard
description: Review AirBench Python boundaries for typed schemas, version compatibility, explicit failure states, and lossless metadata propagation.
metadata:
  short-description: Protect typed contracts and schema evolution
---

# AirBench contract guard

Use when changing schemas, adapters, orchestrator transitions, worker packets, tool calls, routing, retrieval, ledger events, or domain-pack interfaces.

Check that every boundary has:

- typed request and response models;
- explicit schema and contract version;
- validation before state mutation or tool execution;
- deterministic serialization where replay requires it;
- clear distinction between proposal, accepted state, failure, queued, and needs-review;
- compatibility handling for persisted history;
- source, confidence, clearance, timestamp, and taint preserved where facts or evidence cross the boundary.

Reject untyped dictionaries, provider-specific types leaking into core, silent field defaults that change authority, and breaking changes without migration or replay tests.

