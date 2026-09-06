# Prove the MVP Is Sovereign, Safe, and Accountable

## Issue type

M10 MVP acceptance issue: freeze the observable evaluation set, default-fail completion gates, sovereignty proof, independent evaluation procedure, and reproducible end-to-end acceptance run.

## Objective

Freeze the observable proof that the first AirBench build solves the stated refinery/PSU inspection-report problem while remaining local, sovereign, safe, and accountable.

This is the final acceptance gate for the first vertical slice. The system must prove the complete path from scanned inspection input to review-status approval-note deliverable, including provenance, retrieval, routing, calculations, verification, artifact validation, auditability, and no-egress execution.

The proof must be understandable and executable by a fresh evaluator who has not seen the generation workers' internal narrative.

## Acceptance boundary

The MVP is accepted only when all required evidence is present in the local evidence package and every completion gate has been independently verified.

The generation narrative, model confidence claims, worker self-assessment, or a successful process exit are not acceptance evidence by themselves.

## Scope

### In scope

- A frozen MVP evaluation fixture set.
- Default-fail completion schema.
- Independent evaluator procedure and clean evaluator context.
- Full scanned inspection-report-to-approval-note acceptance run.
- Local OCR/vision and retrieval evidence.
- Model and route evidence.
- Coding and deterministic calculation evidence from the no-network sandbox.
- Computed-number verification.
- DOCX structural and visual validation.
- Independent review and human-review evidence.
- No-egress test plan covering IPv4, IPv6, DNS, proxy, NGC, Hugging Face, telemetry, and update paths.
- Local network-monitor evidence during the entire run.
- Offline model/container asset verification.
- Signed, append-only ledger export and offline replay.
- Success, failure, fallback, verifier-unavailable, and uncertain-result traces.

### Out of scope

- Cloud or remote evaluation.
- External hosted models or APIs.
- Engineering drawing/P&ID interpretation.
- Production fleet attestation.
- Identity-bound enterprise sign-off beyond the first-scope human-review record.
- Acceptance based only on screenshots or prose claims.
- Acceptance based on a model declaring its own result complete.

## Required repository layout

Create the following acceptance package:

```text
acceptance/
  mvp_evaluation_set.yaml
  completion_criteria.schema.yaml
  evaluator_procedure.md
  no_egress_test_plan.yaml
  network_monitor_evidence.schema.yaml
  acceptance_run_manifest.yaml
  acceptance_matrix.yaml
  fixtures/
    inspection_report_scanned.pdf
    inspection_report_photographs/
    manuals/
    sops/
    past_correspondence/
    coding_task/
  expected/
    findings.yaml
    retrieved_sources.yaml
    calculations.yaml
    required_ledger_events.yaml
  traces/
    success/
    failure_missing_source/
    failure_verifier_unavailable/
    fallback/
    restart_resume/
  evidence/
    network/
    ledger/
    artifacts/
    routing/
    sandbox/
  reports/
    acceptance_report.md
    offline_replay_report.md
```

The exact filenames may vary, but every required artifact must have a stable ID, content hash, producer, timestamp, and relationship to the acceptance run.

## MVP evaluation set
