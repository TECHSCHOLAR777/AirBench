# AirBench end-to-end audit report

Date: 2026-09-15

Scope: local repository audit covering the desktop application, Python Node, File Intake, P&ID processing, retrieval and World Model paths, deliverables, sandbox boundaries, and release evidence.

## Result in brief

The executable test suites are green after two repairs. The local implementation is not yet release-qualified because the repository acceptance package still requires measured hardware, model, network, packaging, and human-review evidence. Those gates remain open by design and have not been replaced with assumed or fabricated values.

## Repairs applied

- Added the twelve ledger event names used by the implemented knowledge-ingestion, P&ID, World Model, domain-pack, consistency, and authority paths to `src/contracts/schemas/ledger_event_catalog.yaml`.
- Corrected the Podman provider contract test to reflect the documented host-sensitive behavior. Non-XFS hosts use a bounded writable `tmpfs`, while verified XFS hosts use Podman storage quota. Added coverage for both branches.
- Installed the declared `deliverables` extras in the audit environment so DOCX, XLSX, and PPTX renderers could be exercised instead of being mistaken for code failures.
- The frontend usability and offline typography changes from commit `bb1eefa7` were rechecked during this audit. They remain green under the current frontend gates.

## Verification metrics

| Metric | Measured result | Evidence |
| --- | ---: | --- |
| Python tests collected | 729 | `python -m pytest --collect-only -q` |
| Python tests passed | 719 | `python -m pytest -q -r s` |
| Python tests skipped | 10 | Optional vision, raster, Podman host, real-model, and fixture-dependent checks |
| Frontend tests passed | 186 of 186 | `npm test` |
| P&ID and File Intake focused tests passed | 31 of 31 | P&ID, intake, raster, Node P&ID, and World Model integration slice |
| Retrieval and World Model focused tests passed | 66 of 72 | Six explicitly skipped real-model or dependency-path checks |
| Local end-to-end, deliverable, and sandbox tests passed | 61 of 61 | Offline restart, M9 vertical slice, DOCX/XLSX/PPTX, tool gateway, code execution, and sandbox slice |

The frontend production build emitted four local Poppins font assets, a 108.44 kB stylesheet, and a 442.04 kB JavaScript bundle. The frontend egress, UI, accessibility, and Tauri configuration checks all passed.

## Pipeline findings

### Frontend and Node boundary

The authored frontend tests passed, the contract generation check passed, the local-resource scan passed, and the no-egress source scan found no network-capable APIs or external resource URLs. The desktop WebDriver track could not run on this Windows host because `msedgedriver.exe` is not installed. This is an environment blocker, not evidence that the desktop workflow is verified.

### P&ID and File Intake

The focused local slice passed typed P&ID extraction, image validation, transactional intake storage, tamper detection, replay behavior, clearance-aware World Model candidate handling, and Node API authentication. Real OCR and raster paths remain represented by explicit skips when their optional dependencies or qualified model assets are absent.

### Retrieval and World Model

The local tests passed clearance filtering, durable vector index restart behavior, Chroma delegation, graph API authorization, entity extraction, World Model persistence, conflict recording, review resolution, and Node knowledge search. Real BGE model loading remains an opt-in qualification test and was not claimed from fixture-based retrieval tests.

### Deliverables and sandbox

The offline vertical slice passed DOCX structural output, XLSX output, PPTX output, deterministic value propagation, artifact review paths, tool-gateway controls, code execution controls, and local sandbox behavior. Podman integration on this Windows host remains skipped because the provider requires a native POSIX host with rootless Podman and an explicit integration opt-in.

## Release blockers that remain open

`python scripts/acceptance_audit.py` reports 538 blocking findings after the ledger catalog repair:

- 531 unresolved evidence placeholders in benchmark and qualification records
- 7 incomplete external gates in `acceptance/acceptance_run_manifest.yaml`

The seven gates are target hardware measurements, model qualification, no-egress observation, vertical-slice run evidence, DOCX structural and visual checks, human review, and authorized signatures. They require real environments, operators, or measured artifacts. Filling them with guessed values would invalidate the audit trail.

The host-level `python scripts/no_egress_check.py` observation also detected unrelated external connections from the workstation. It is therefore not valid application-specific no-egress proof. The desktop WebDriver requirement has the same status until a matching local driver is installed.

## Autonomous continuation policy

The agent may continue through safe local tests, fixture-based diagnosis, deterministic repairs, and documentation without manual intervention. It must stop and report when a step requires GPU hardware, native Linux isolation, a real model endpoint, a human signature, or a security decision. Autonomous continuation cannot turn an unavailable external condition into acceptance evidence.

## Final verification statement

AirBench is locally testable across its implemented contracts and vertical slices, and the identified code and test defects in this audit are repaired. It is not honestly possible to certify the complete deployable, hardware-qualified, no-egress, human-approved system from this workstation alone. The remaining work is captured as explicit acceptance evidence, not hidden behind a green unit-test result.
