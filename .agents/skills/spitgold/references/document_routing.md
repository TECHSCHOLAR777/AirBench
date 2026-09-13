# Document routing

Always read `README.md`, `docs/README.md`, and `airbench_capability_map.md` first. Then select the smallest document set that fully governs the requested sub-section.

| Requested content | Read before writing |
| --- | --- |
| Product overview, problem, USPs, or complete workflow | `docs/foundations/01_architecture_design.md`, `docs/foundations/02_domain_pack_framework.md` |
| File upload, scanned documents, OCR, images, or document intelligence | `docs/foundations/03_file_intake_layer.md`, `docs/foundations/05_knowledge_and_retrieval_engine.md`, `docs/assurance/sovereignty_and_security.md` |
| Retrieval, organizational knowledge, evidence, ontology, or World Model | `docs/foundations/04_world_model_engine.md`, `docs/foundations/05_knowledge_and_retrieval_engine.md`, `docs/foundations/02_domain_pack_framework.md` |
| Planning, task states, worker roles, harness, or multi-agent execution | `docs/foundations/06_orchestration_engine.md`, `docs/runtime/airbench_harness.md`, `docs/assurance/memory_and_audit_ledger.md` |
| Models, GPU use, local serving, routing, or fallback | `docs/foundations/07_serving_and_routing.md`, `docs/assurance/model_qualification_framework.md`, `docs/runtime/models.md` |
| Code execution, tools, sandbox, sovereignty, clearance, or security | `docs/assurance/sovereignty_and_security.md`, `docs/foundations/06_orchestration_engine.md` |
| Verification, consistency, approvals, human review, or autonomy | `docs/foundations/08_verification_framework.md`, `docs/foundations/09_consistency_engine.md`, `docs/foundations/10_autonomy_governor.md` |
| Ledger, provenance, replay, proof, or audit trace | `docs/assurance/memory_and_audit_ledger.md`, `docs/assurance/sovereignty_and_security.md` |
| Word, Excel, PowerPoint, code, calculations, charts, or artifact checks | `docs/delivery/deliverable_engine.md`, `docs/foundations/08_verification_framework.md` |
| P&ID, engineering drawings, symbols, lines, topology, or drawing evidence | `docs/intake/pid.md`, `docs/foundations/03_file_intake_layer.md`, `docs/foundations/04_world_model_engine.md`, `docs/foundations/02_domain_pack_framework.md`, `docs/assurance/sovereignty_and_security.md` |

For a mixed section, read the documents for each named system component. For example, a slide about a scanned P&ID becoming an approval note requires File Intake, the P&ID document, the World Model, Verification, and Deliverable Engine documents.

Do not describe a future or incomplete subsystem as measured production evidence. In complete-product narrative mode, describe its intended operational behavior and controls without inventing results.
