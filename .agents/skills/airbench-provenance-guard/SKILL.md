---
name: airbench-provenance-guard
description: Check that AirBench facts and evidence retain source, confidence, clearance, timestamp, derivation, and taint through every transformation.
metadata:
  short-description: Protect fact provenance and evidence taint
---

# AirBench provenance guard

Use when changing intake, OCR, retrieval, world-model writes, worker packets, prompts, verification, or deliverables.

Find every conversion from a governed fact or evidence reference into a Python object, string, table, prompt fragment, cached record, or artifact. Require the provenance envelope to remain attached or require an explicit, audited projection that cannot be mistaken for authoritative fact state.

Check that:

- source identity and revision remain addressable;
- confidence is not replaced with prose wording;
- clearance is enforced before exposure;
- taint remains visible to policy and tool gates;
- derived values identify their inputs and computation;
- verification can trace a claim back to evidence.

Reject tests that assert only text equality when provenance is part of the contract.

