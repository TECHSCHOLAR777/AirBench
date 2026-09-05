---
name: airbench-architecture-guard
description: Review AirBench changes for core versus domain-pack ownership, deterministic orchestration, stateless workers, and clean module boundaries.
metadata:
  short-description: Protect AirBench architectural ownership
---

# AirBench architecture guard

Use when changing core engines, domain packs, orchestration, worker teams, routing, or shared modules.

Check:

- sector assumptions are behind the domain-pack contract;
- the orchestrator owns state, retries, fallback, barriers, and completion;
- models and workers return proposals and do not drive loops;
- the router selects only qualified targets and does not own verification;
- tools execute only through the Tool Gateway;
- the File Intake Layer is the only parser entry point;
- rendering and deterministic calculations remain separate from model prose;
- modules expose deep, testable interfaces instead of leaking implementation details.

If a change needs a sector rule in core, widen the pack contract and add a domain-pack conformance test instead.

