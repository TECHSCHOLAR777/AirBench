# Freeze v0 Refinery/PSU Inspection-Report Domain Pack and Vertical Slice

## Issue type

M9 integration issue: domain-pack freeze, refinery/PSU document-review vertical slice, and acceptance evidence.

## Objective

Freeze the first AirBench domain pack and its demonstrable vertical slice against the original problem statement:

> Sensitive refinery, PSU, defence-linked manufacturing, and government-office knowledge work must run locally and produce accountable deliverables.

The first frozen domain pack will support refinery/PSU inspection-report review and preparation of an approval-note draft. The complete demonstration must run on the organization's own workstation or GPU server without cloud models, external APIs, telemetry, package downloads, or other network dependency.

The output is a real Word approval-note deliverable accompanied by source evidence, verification results, visible review status, structural and visual checks, routing decisions, worker trace, ledger export, and sovereignty/no-egress proof.

## Decision to freeze

The first pack is:

```text
refinery_psu_inspection_review_v0
```

The primary reference deployment is a single local workstation or GPU server with:

```text
GPU: one 96 GB VRAM GPU
Execution: local-only
Network: no egress from runtime, model-serving, intake, or sandbox paths
Team mode: parallel where the 96 GB hardware profile admits it; otherwise serial virtual team
```

The 96 GB VRAM profile is the reference qualification target for this issue. Model selection is capability-based and must be qualified against this hardware profile; the implementation must not silently substitute an unqualified model or remove required verification because of memory pressure.

## In scope

### Domain workflow

- Review of a scanned refinery or PSU inspection report.
- Preparation of an approval-note draft for human review.
- Local OCR and local vision understanding for scanned pages and photographs.
- Local retrieval against manuals, SOPs, inspection procedures, and past correspondence.
- Extraction of sourced findings and confidence-bearing evidence.
- Deterministic calculation of values that appear in the deliverable.
- Bounded AirBench worker team with:
  - lead worker;
  - evidence/vision worker;
  - reasoning worker;
  - independent verification worker;
  - render/review worker.
- Local model routing across document/vision work and coding/reasoning work.
- Coding companion request generated and verified in a no-network sandbox.
- Visible local audit trace and sovereignty evidence.
- Real DOCX generation, reopening, structural validation, PDF rendering, and visual validation.

### Input formats

The first demonstration must include at least one scanned PDF or mixed PDF containing text, scans, tables, and/or photographs. The intake contract may also support:

- digital PDF;
- PNG/JPEG photographs;
- DOCX manuals and correspondence;
- XLSX/CSV supporting tables;
- plain text and markup.

Every input enters through the File Intake Layer. Workers must not open uploaded files through ad hoc libraries or direct host paths.

### Hardware and execution modes

The signed hardware profile must record:

- GPU identity and fingerprint;
- 96 GB VRAM capacity;
- CPU and RAM capacity;
- local model residency and load state;
- context and KV-cache budget;
- permitted parallel slots;
- measured latency and throughput envelope;
- local storage and scratch limits;
- sandbox resource limits;
- egress/isolation status.

The demo must be runnable in both of these modes:

1. **Available parallel mode:** the scheduler admits the worker assignments concurrently when resource reservations fit within the 96 GB profile.
2. **Serial virtual-team mode:** the same logical workers execute serially or pipelined when concurrency is not admitted. Required roles, evidence thresholds, verifier, review stage, and completion rules remain unchanged.

Hardware pressure may change scheduling or select a smaller already-qualified target. It may not skip the verifier, weaken a check, lower a confidence threshold, broaden clearance, or convert an unverified draft into a completed task.

## Domain-pack contract

Create and sign:

```text
packs/refinery_psu_v0/manifest.yaml