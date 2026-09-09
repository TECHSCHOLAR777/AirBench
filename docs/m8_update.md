# M8 implementation update

This is a new implementation handoff for issue #13. Existing solution documents are intentionally unchanged.

## Implemented in this worktree

- M8.1 remains available through the existing deterministic `VerificationRunner` and its typed checks, provenance, idempotency, timeout, and ledger behavior.
- M8.2 adds `IndependentEvaluator`, fresh-context worker identity checks, unavailable-evaluator `needs_review`, and a default-fail `CompletionGate`.
- M8.3 adds `AutonomyGovernor` with pack-driven risk rules, unknown-risk escalation, self-certification rejection, provenance-backed authority events, and `ConsistencyEngine` structured comparison with superseded-record filtering and deviation flags.
- M8.4 adds `CrossFrameworkGate`, which combines verification, independent evaluation, authority, and consistency outcomes and emits `completion.ready` or `completion.blocked` without allowing team agreement to override a failed gate.
- New ledger event types cover evaluator requests/results, consistency checks, authority decisions, and completion gate outcomes.

## Remaining / explicitly not claimed

- The live parent issue still has the repository-declared M4 dependency open; this work does not close that external dependency.
- Domain packs still own field-specific risk rules, decision types, and verification rules.
- The cross-framework gate is a typed core integration seam; wiring every production M4 team runtime path and the later M9 end-to-end inspection run remains integration work.
- No GitHub issue, PR, merge, push, or solution document was changed by this worktree.

## Verification

Focused M8 tests: `.venv\Scripts\python.exe -m pytest -q tests/test_m8_frameworks.py` — 5 passed.

Full Python suite: `.venv\Scripts\python.exe -m pytest -q` — 317 collected, 1 skipped, all remaining tests passed.

Additional checks passed: Python `compileall`, `git diff --check`, frontend contract generation, frontend accessibility, frontend no-egress, Tauri configuration, desktop production build, and 136 frontend tests across 25 files. Desktop dependencies were installed from the checked-in lockfile solely for validation; npm reported 16 existing dependency-audit findings (3 moderate, 13 high), which are outside M8 scope and were not force-upgraded.

## M9 follow-on implementation status

The M9 refinery vertical slice now has a signed detached-HMAC pack loader, typed refinery pack projections, File Intake Layer and local vision integration, local indexing and retrieval, hardware-profile-driven parallel or serial-virtual worker routes, per-worker routing events, sourced inspection findings, deterministic computed values, a real OOXML approval-note renderer driven by the pack template contract, structural and optional LibreOffice visual checks, artifact hashes and generator versions, typed verification plus independent evaluation, and an explicit human-review status. The implementation is in `src/airbench/m9/vertical_slice.py` with focused coverage in `tests/test_m9_vertical_slice.py`.

The offline demonstration can be reproduced with `python scripts/run_m9_demo.py --pack-key <deployment-key> --output-dir <trace-dir>`. It runs both serial and parallel modes, writes a detached `pack-signature.json`, two approval-note DOCX files, a JSONL ledger export, and a summary. `ledger.verify_chain()` is run before the export is written.

Remaining evidence is deployment-specific: measured-node model routes, operator-supplied scanned PDF and manuals, successful LibreOffice visual conversion on that node, no-egress observation, and the human review record must be captured in the acceptance run before the parent issue can claim production acceptance. The implementation intentionally does not claim release approval or replace those external gates.

The emitted trace can be independently replayed offline with `python scripts/verify_m9_trace.py <trace-dir>`. The verifier rebuilds the append-only ledger from JSONL, checks event hashes and replay transitions, confirms both execution modes, and re-hashes every staged artifact referenced by `artifact.checked` events.

The vertical slice now carries retrieved manual/SOP references into the approval-note source register and independent completion evidence, rejects unsupported hardware modes and non-local routes under a no-egress profile, and converts visual-renderer timeouts into a blocking artifact check rather than an uncaught failure.

The detached pack signature covers all declarative component YAML and the manifest declarations (excluding only the self-referential signature field); component or manifest tampering is rejected before execution.

Renderer-backed scanned PDFs are supported through the local intake store: rendered pages are staged, validated by intake identity, read back by page identity, and then passed to the typed local vision adapter without reopening the source file.

On hosts with Microsoft Word installed, the artifact checker can use a bounded headless Word COM conversion as a visual backend when LibreOffice is unavailable. The verified local host run produced `visual: passed`, `completion.ready`, and `verified draft for human review`; the fallback remains fail-closed when the renderer cannot be launched.

`artifact.checked` now records `visual_backend` and `check_reason` alongside the content hash, structural result, visual result, and generator version.

The M9.4 run now emits typed `worker.handoff` ledger events between every adjacent worker stage. Each event carries a validated `HandoffSubmission` and `WorkPacket` with fact/evidence references, packet hash, clearance, taint, and immutable plan/policy identities.

No-finding runs now fail closed with per-worker `worker.failed` events and a `team.execution.failed` event before raising the caller-visible error, preserving an auditable failure trace without changing the shared ledger terminal-state rules.
