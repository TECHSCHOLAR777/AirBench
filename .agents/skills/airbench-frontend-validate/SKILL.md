---
name: airbench-frontend-validate
description: "Validate AirBench desktop security, transport, streaming, and preview."
---

# AirBench Frontend Validate

Use this skill for the six frontend validation tracks and for release-readiness checks before UI implementation is called production-ready.

## Read first

- `docs/frontend/README.md`
- `docs/frontend/frontend_validation_plan.md`
- `docs/frontend/frontend_contracts_and_state.md`
- `docs/sovereignty_and_security.md`
- `docs/deployment_and_scale.md`
- `docs/file_intake_layer.md`

## Validation method

For each track, record the environment, exact command, input fixture, expected evidence, observed result, and limitation. A validation is not complete because a request succeeded once. Test the failure and recovery path as well.

Required tracks:

1. Offline Tauri installation with bundled WebView2 and no network access.
2. Secure local and remote AirBench Node connection with pinned trust and allowlisted transport.
3. Sequence-numbered task-event streaming with disconnect, replay, duplicate, gap, and resync behavior.
4. Scanned-document intake through the File Intake Layer, safe artifact preview, and clearance-aware download.
5. Network-monitor proof that the UI cannot contact external services, including blocked navigation and resource requests.
6. Tauri WebDriver coverage for IPC mocking, backend log capture, multiremote or multi-window behavior, and the critical end-to-end flows.

## Pass criteria

Use fail-closed behavior. If transport trust, clearance, ledger availability, preview safety, or event continuity cannot be proven, mark the track blocked or needs review. Preserve logs and hashes locally and never upload test data to a third-party service.
