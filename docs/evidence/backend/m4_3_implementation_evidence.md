# M4.3 handoff and join-barrier implementation evidence

## Scope

M4.3 adds the serialized synchronization boundary after M4.1 worker
contexts and M4.2 resource leases. The implementation is core-only and
sector-neutral. It does not run models, parse files, select a model, probe a
GPU, or make a domain correctness decision.

## Implemented behavior

- `WorkPacket` is immutable at the contract boundary and carries a canonical
  SHA-256 packet hash. The hash covers the versioned packet content, excluding
  only the hash field itself.
- `HandoffSubmission` binds task, team, source assignment, source worker,
  destination assignment and stage, active resource lease, plan version,
  policy version, clearance, taint, deadline, packet hash, and idempotency.
- `JoinBarrier` is an immutable versioned projection. Its accepted and missing
  predecessor sets must be disjoint and cover the committed dependency graph.
- `HandoffCoordinator` validates topology, identity, active lease, deadline,
  clearance, taint monotonicity, fact and evidence references, artifact hashes,
  and destination scope before changing its projection.
- Accepted packets produce `worker.handoff` plus either
  `join_barrier.waiting` or `join_barrier.completed`. Rejected packets produce
  `worker.handoff.rejected`. Late packets produce `worker.handoff.late` and do
  not satisfy the old barrier version.
- Conflicting packets resolve the barrier to `conflicting`. Missing and
  timed-out work can be resolved only after the deadline. Completion cannot be
  manually asserted for a barrier.
- Duplicate handoffs are idempotent. Reconciliation rebuilds only committed
  handoff and barrier snapshots and never invokes a worker, model, tool, or
  parser.
- In-memory and SQLite ledger writes preserve atomicity for one synchronization
  transition. A failed ledger append does not update the coordinator
  projection.
- Orchestrator and ledger replay project the new join-barrier events into the
  task state machine. Core contracts are regenerated for the desktop boundary.

## Verification

Focused command:

```text
python -m pytest -q tests/test_m43_handoffs.py
```

Result: 11 passing tests.

The focused regression command for the preceding slices also passes:

```text
python -m pytest -q tests/test_m41_worker_contexts.py tests/test_m42_scheduler.py tests/test_contracts.py tests/test_orchestrator.py
```

Repository verification passes:

```text
python -m pytest -q
python -m compileall -q contracts airbench
python scripts/generate_frontend_contracts.py --check
git diff --check
```

Tests use synthetic typed records. They do not claim real GPU admission,
model serving, file intake, or production deployment evidence. Those remain
later hardware, serving, intake, and deployment acceptance work.

## Explicit boundary

The coordinator transfers references and provenance metadata. It does not
interpret the meaning of an inspection finding, approve a deliverable, or
write authoritative numeric values. Domain-specific interpretation remains a
domain-pack responsibility, while state, control flow, synchronization, and
ledger authority remain in the core orchestrator.
