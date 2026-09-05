# Future Full-Fledged Must-Haves

This file records requirements deliberately deferred while the first AirBench vertical slice is being concreted. These are not discarded; they are not part of the current build scope unless a later decision promotes them.

## Deferred P0 items

### P0-1 - Hardware and performance profiles

The current design will be validated on one target machine first. A later full deployment must define supported GPU/RAM profiles, model quantization, context limits, concurrency, cold-start behavior, admission control, and measured p95 latency for each profile. The 96 GB reference roster must not be treated as the minimum deployment.

### P0-2 - Independent sovereignty proof

The first scope assumes a controlled local deployment and records local execution evidence. A full sovereign deployment must add independent host or network enforcement evidence, default-deny egress tests, IPv4/IPv6/DNS/proxy coverage, removable-media controls, signed machine-state attestations, and offline replay by an independently held verifier.

### P0-4 - Full identity and clearance enforcement

The first scope uses a narrow caller clearance contract. A full deployment must integrate with the organization's identity system and implement attribute-based access control, need-to-know, field/span-level labels, clearance-aware vector and graph queries, cache partitioning, denied-read auditing, inference-leakage protection, and secure session isolation.

### P0-6 - Exhaustive numeric-integrity enforcement

The current deliverable scope uses computed values and named template fields. A full deployment must add complete numeric-token scanning across prose, tables, charts, formulas, dates, units, identifiers, and rendered Office packages, with a hard block for any unbound value.

### P0-9 - Full file-format and drawing coverage

The current scope supports the common scanned-document, text-document, spreadsheet, image, and plain-text path. Full coverage must add hardened support for all intended formats, archive and parser limits, macro and embedded-object policy, handwriting, complex tables, engineering drawings, and the drawing pipeline supplied later. The drawing pipeline must have its own signed, versioned, confidence-bearing interface before it is connected.

## Deferred P1 items

### P1-5 - Full human approval and electronic sign-off workflow

The first scope may expose a verified draft and review trace without building the complete approval inbox. A full deployment must add identity-bound signatures, one- or two-person approval policies, source-linked review, fact diffs, rejection and revision flows, delegation, revocation, escalation SLAs, and final-artifact hash binding.

### P1-8 - Production packaging, key lifecycle, and fleet operations

The first scope does not attempt the complete offline appliance lifecycle. A full deployment must add organization-held root keys, rotation and revocation, signed bundles, SBOMs, staged updates, rollback, vulnerability handling, encrypted consistent backups, restore drills, secure deletion, and multi-site one-way distribution.

## Deferred P2 items

- A polished Claude/Codex-like workbench with progress, cancellation, task history, source navigation, artifact preview, approval prompts, and user-facing diagnostics.
- Production connectors for file shares, document-management systems, email exports, and other local repositories, including incremental sync, source ACL import, source deletion, and back-pressure.
- Multilingual OCR, handwriting support, local conventions, Indian number/date formats, and domain-specific unit dictionaries.
- Formal quality targets and continuous evaluation for OCR, extraction, retrieval, citations, calculations, code execution, end-to-end latency, human correction rate, and model calibration.
- Model, runtime, OCR, font, Office-library, and quantization license review and a complete software supply-chain inventory.
- Incident response for poisoned documents, unsafe generated code, clearance leaks, wrong calculations, compromised model weights, and bad pack updates.
- Full retention, classified-data handling, secure erasure from caches and backups, crash-dump controls, swap/pagefile controls, and GPU-memory cleanup.
- High-availability stores, disaster recovery, multi-node scaling, fleet health reporting, and site-to-site configuration comparison.
- Full outcome-aware Consistency Engine behavior: outcome capture, overturned-decision weighting, survivorship controls, drift analytics, and regulator-ready reporting.
- Independent attestation of host state and model identity, hardware-backed key custody, and continuous tamper-evident sovereignty proofs.

