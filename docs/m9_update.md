# M9 implementation update

This is the implementation record for issue #14. Existing solution documents are intentionally unchanged.

## Implemented in this worktree

- **M9.1 — Declarative domain pack and approval-note contract**: `RefineryPack` loads the `packs/refinery_psu_v0/` component YAML files, canonicalises the full payload, and verifies an HMAC-SHA256 detached signature. Any component or manifest tampering is rejected before execution. The pack declares five bounded worker roles, a scanned-report document profile, a world schema, field rules, risk mappings, clearance roles, decision types, and the DOCX deliverable template with required section labels and computed-value placeholders.

- **M9.2 — Local vision, retrieval, reasoning, and verification with hardware-aware routing**: `RefineryVerticalSlice.run_from_file()` reads scanned PDFs and local images through `FileIntakeLayer` and stages rendered pages via `LocalIntakeStore`. A typed `LocalVisionAdapter` extracts inspection findings (pattern `F-01: P-101: severity: description`) with source references, confidence scores, clearance, and taint. Local manuals/SOPs are indexed through `DeterministicEmbeddingProvider` + `LocalVectorIndex` + `LexicalReranker`. Deterministic computed values (`finding_count`, `critical_finding_count`, `manual_match_count`) are produced through a guarded tool-request/authorize/result event chain. Independent evaluation runs through `IndependentEvaluator` with a separate worker identity; `CompletionGate` enforces all gates without allowing team agreement to override. Hardware profiles control safe parallel slot count, supported execution modes (parallel/serial), and no-egress route enforcement — non-local model routes are rejected when the profile is `no-egress`.

- **M9.3 — Deterministic approval-note rendering and structural/visual checks**: `ApprovalNoteRenderer` writes a valid OOXML `.docx` from verified findings, manual/SOP references, computed values, and review status — all driven by the pack template contract. Structural checking reopens the ZIP/XML and verifies required section labels and numeric values. Visual conversion uses LibreOffice (`soffice`) when available, falls back to a bounded Microsoft Word COM process on Windows, and records the visual backend, check reason, content hash, and generator version in an `artifact.checked` ledger event. Visual-converter timeouts are converted to a blocking artifact check rather than an uncaught failure. The `M9RunResult.artifact` carries the absolute generated DOCX path.

- **M9.4 — Measured-node vertical slice with handoffs, routes, hardware, evidence, failures, hashes, review state, and final ledger trace**: The five-worker chain (`lead_worker` → `evidence_vision_worker` → `reasoning_worker` → `independent_verification_worker` → `render_review_worker`) emits typed `worker.handoff` events between every adjacent stage. Each handoff carries a validated `HandoffSubmission` and `WorkPacket` with fact/evidence references, packet hash, clearance, taint, and immutable plan/policy identities. Empty-report runs fail closed with per-worker `worker.failed` events and a `team.execution.failed` event before raising the caller-visible error. Intake failures append a `task.failed` ledger event (failure_code, stage, message, retryable) before re-raising. `scripts/run_m9_demo.py` exercises serial and parallel modes and writes DOCX artifacts, a JSONL ledger export, and a pack-signature file. `scripts/verify_m9_trace.py` reconstructs the ledger from JSONL, verifies hash-chain integrity, checks required event types, and re-hashes every `artifact.checked` DOCX.

## Remaining / explicitly not claimed

- Authorized production pack signing: the pack `manifest.yaml` remains `signing_status: unsigned` and `status: draft_pending_external_acceptance`. A real operator signing key is an external input; no synthetic signature was added.
- Measured-node acceptance evidence: hardware profile evidence, qualified model evidence, no-egress observation, and the target scanned-report-to-approval-note run must be captured in the deployment environment.
- Human reviewer sign-off: `human.review.required` is always appended after the completion gate; the human identity, review decision, and sign-off artifact are external acceptance inputs.
- `acceptance/acceptance_run_manifest.yaml` external evidence entries remain intentionally unresolved until those artifacts are attached.

## Verification

Focused M9 tests: `.venv\Scripts\python.exe -m pytest -q tests/test_m9_vertical_slice.py` — **12 passed, 0 failed**.

Full Python suite: `.venv\Scripts\python.exe -m pytest -q` — 329 collected, 1 skipped, all remaining tests passed.

Additional checks passed: Python `compileall -q src tests scripts`, `git diff --check` (exit 0, no trailing-whitespace errors), serial and parallel offline demo traces generated, and offline ledger/artifact replay verifier passed against those traces.
