# Ledger examples

`inspection_trace.jsonl` is a human-readable wire-format example covering task creation, team creation, and a review-required verification result. Its zero hashes are intentional placeholders for documentation and must not be accepted as a production ledger.

Executable tests should create traces with `contracts.build_event()` and append them through `contracts.EventLedger`, which computes and verifies the canonical payload and event hashes.
