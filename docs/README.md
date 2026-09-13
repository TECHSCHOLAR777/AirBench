# AirBench documentation map

This directory is organized by architectural responsibility. The repository root contains only public entry points and operational configuration. Python packages live under `src/`, the desktop application under `apps/desktop/`, and engineering records under `engineering_records/`.

## Required foundation reading

Read these in order before changing a system boundary:

1. [Architecture design](foundations/01_architecture_design.md)
2. [Domain pack framework](foundations/02_domain_pack_framework.md)
3. [File Intake Layer](foundations/03_file_intake_layer.md)
4. [World Model Engine](foundations/04_world_model_engine.md)
5. [Knowledge and Retrieval Engine](foundations/05_knowledge_and_retrieval_engine.md)
6. [Orchestration Engine](foundations/06_orchestration_engine.md)
7. [Serving and Routing](foundations/07_serving_and_routing.md)
8. [Verification Framework](foundations/08_verification_framework.md)
9. [Consistency Engine](foundations/09_consistency_engine.md)
10. [Autonomy Governor](foundations/10_autonomy_governor.md)

These documents establish the two flows and the three properties that hold throughout AirBench: deterministic authority, lossless fact provenance, and offline proof.

## Document collections

| Collection | Purpose |
| --- | --- |
| [foundations](foundations/) | System architecture and the first ten foundational documents |
| [runtime](runtime/) | Harness, model serving, routing, backend plan, and runtime contracts |
| [assurance](assurance/) | Qualification, ledger, security, and verification assurance |
| [delivery](delivery/) | Deliverables, packaging, deployment, and scale |
| [desktop](desktop/) | Tauri application design, contracts, workflows, and validation |
| [intake](intake/) | Controlled adapters for specialized file and visual-intake paths, including engineering drawings and P&IDs |
| [evidence/backend](evidence/backend/) | Backend implementation evidence and acceptance notes |
| [operations](operations/) | Agent workflow and current execution status |
| [future](future/) | Deliberately deferred full-fledge requirements |

## Boundary rules

- `src/airbench` is sector-neutral runtime code.
- `src/contracts` contains provider-neutral contracts and schemas.
- Domain-specific behavior belongs in a domain pack behind its contract; it must not leak into the core runtime.
- `apps/desktop` talks only to an approved AirBench Node and never to model endpoints.
- `engineering_records` is historical and planning material, not an executable source of truth.

For the complete directory rationale, see [repository map](repository_map.md). For desktop work, start at [desktop README](desktop/README.md).
