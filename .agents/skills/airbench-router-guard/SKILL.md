---
name: airbench-router-guard
description: Review AirBench routing and serving changes for qualified per-step selection, hardware admission, deterministic fallback, and provider-neutral adapters.
metadata:
  short-description: Protect model routing and serving policy
---

# AirBench router guard

Use when changing model registry, routing, hardware profiles, serving adapters, worker assignments, or fallback behavior.

Check that the orchestrator sends typed model-call requests and never selects model names directly. The router must apply hard eligibility gates before priority or optimization:

- capability and task kind;
- modality and context limit;
- qualification certificate and pack version;
- clearance and risk class;
- hardware capacity and resource lease;
- current health and admission state.

Fallback may use only an already-qualified eligible target or return queued, degraded, needs-review, or unavailable. Verification failure belongs to the orchestrator and verification framework, not to silent router retries.

