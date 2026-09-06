# FE-DEV-02 contract generation evidence

Status: shared core-contract generation slice complete. The full issue remains open until the backend Node envelope and real command transport are authoritative.

## Implemented

- `scripts/generate_frontend_contracts.py` imports the Python contract classes and ledger event catalog as the source of truth.
- The script generates `frontend/src/generated/core_contracts.ts` with schema identity, clearance values, taint values, contract status values, the ledger event catalog, and typed core contract interfaces.
- `frontend/src/protocol.ts` imports the generated clearance and taint types instead of defining competing wire unions.
- `npm run generate:contracts` regenerates the file during the frontend build.
- `npm run check:contracts` fails when the checked-in generated file is stale.
- `tests/test_frontend_contract_generation.py` protects the generated-file drift boundary.
- `TaskEventSynchronizer` now rejects inconsistent batches before projection, including wrong Node identity, protocol or clearance mismatch, malformed cursor progression, non-increasing sequences, event metadata mismatch, and ledger-reference misalignment.

## Evidence

From the repository root:

```text
python scripts/generate_frontend_contracts.py --check
python -m pytest -q
```

From `frontend/`:

```text
npm run check:contracts
npm run test
npm run build
npm run check:egress
npm run check:tauri-config
```

Observed results for this slice:

- Python contract generation check passed.
- Backend Python suite passed.
- Frontend suite passed with 35 tests.
- TypeScript and Vite production build passed.
- Static no-egress and Tauri policy checks passed.

## Backend Node API slice now available

The first Python Node API slice is implemented in `airbench/node_api.py` and documented in `docs/m10_1_node_api_evidence.md`. It provides authenticated handshake and health routes, task creation and lifecycle commands through the orchestrator, authoritative snapshots, task-local cursor event batches, evidence, route trace, and review projections. Its event batches use the Node clearance context required by the native transport while evidence and facts retain their individual clearance and taint.

This is an integration-ready backend slice, not a production-complete Node. The frontend must still connect its live command and snapshot paths to the API and verify the packaged local and internal-HTTPS deployment.

## Remaining issue scope

- Complete the authoritative versioned Node handshake, task snapshot, event batch, command, command-result, safe-preview, and download-receipt contracts in the backend.
- Replace provisional presentation event adapters with a real Node transport using those contracts.
- Add protocol negotiation and compatibility refusal at the live Node boundary.
- Prove command idempotency and ledger references against the Python Node rather than only synthetic fixtures.

The frontend must not connect task creation or consequential commands against the provisional presentation types until those backend contracts exist.
