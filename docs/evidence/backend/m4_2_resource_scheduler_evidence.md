# M4.2 resource scheduler evidence

## Scope

This slice implements the deterministic physical scheduling boundary for an
AirBench virtual worker team. It is a Python-only component in
`src/contracts/execution/scheduler.py`. It does not probe hardware, load a model, parse a
file, or open a network connection.

The scheduler consumes a previously produced `HardwareProfile` and
`HardwareMeasurement`, then creates an immutable `TeamResourcePlan`. It
accounts for VRAM, RAM, CPU millicores, KV cache, context tokens, scratch
storage, execution slots, GPU placement, model residency, queue priority,
dependency topology, and the independent verifier requirement.

## Implemented behavior

- Parallel admission is granted only when all worker reservations fit every
  measured resource dimension and the GPU placement map.
- Pipelined admission requires an explicit stage map and uses the same
  concurrent capacity proof as parallel admission.
- Serial virtual-team admission keeps the full logical team but grants one
  worker lease at a time.
- Temporarily unavailable work is queued in priority then FIFO order. A retry
  receives a higher immutable plan version; the old queued plan is retained as
  ledger history.
- A worker that cannot fit even as a single serial turn is stopped. The
  scheduler never removes the verifier or lowers an authority requirement.
- Leases are identity-bound to task, team, plan, worker, hardware measurement,
  model target, qualification, policy, reservation, clearance, and taint.
- Lease lifecycle transitions include granted, activated, released, expired,
  cancelled, and failed terminal states. Repeated grants are idempotent.
- Plan and lease decisions can be committed to the append-only ledger and
  reconstructed from ledger events after restart.
- Multi-GPU reservations require per-device VRAM measurements. Aggregate
  VRAM alone is not treated as enough evidence for placement on a multi-GPU
  node.

## Verification performed

`tests/test_m42_scheduler.py` covers:

- parallel admission and all-worker lease grants;
- explicit pipelined admission;
- serial lease exclusivity and handoff after release;
- temporary capacity queueing and higher plan-version retry;
- permanent resource shortfall and cyclic dependency rejection;
- missing qualified target rejection;
- activation, expiry, and terminal lease behavior;
- ledger event coverage and restart reconciliation;
- refusal to schedule multi-GPU work without per-device measurement.

The focused test command is:

```text
python -m pytest -q tests/test_m42_scheduler.py
```

The result for this slice is 10 passing tests. Existing M4.1 and M5 admission,
acceptance, and contract tests also pass after the contract additions.

## Hardware qualification boundary

This evidence uses synthetic profiles and measurements only. It proves the
arithmetic, state ownership, contract validation, ledger path, and restart
behavior. It does not prove CUDA discovery, real VRAM accounting, model
residency, throughput, or a production no-egress probe. Those require the
hardware qualification work in M5.2 and must be run on the target deployment
node before a production claim is made.

## Remaining integration gate

M4.3 must consume this finalized plan and lease interface for typed handoffs
and join barriers. It must not duplicate resource accounting or mutate a
committed plan. The M4.3 implementation remains serialized behind the reviewed
M4.1 and M4.2 slices.
