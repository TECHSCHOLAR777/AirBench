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

The M9 refinery vertical slice now has a signed detached-HMAC pack loader, typed refinery pack projections, hardware-selected parallel or serial-virtual worker routes, locally grounded manual matching, sourced inspection findings, deterministic computed values, a real OOXML approval-note renderer, structural and optional LibreOffice visual checks, artifact hashes, independent-verifier ledger events, and an explicit human-review status. The implementation is in `src/airbench/m9/vertical_slice.py` with focused coverage in `tests/test_m9_vertical_slice.py`.

Remaining evidence is deployment-specific: measured-node model routes, operator-supplied scanned PDF and manuals, successful LibreOffice visual conversion on that node, no-egress observation, and the human review record must be captured in the acceptance run before the parent issue can claim production acceptance. The implementation intentionally does not claim release approval or replace those external gates.
