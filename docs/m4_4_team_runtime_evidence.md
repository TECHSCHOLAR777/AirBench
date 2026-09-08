# M4.4 Team Runtime Evidence

Status: implemented in the local Python reference runtime. The issue remains open until the acceptance evidence is reviewed and the manual hardware validation is completed.

Issue: [#32](https://github.com/TECHSCHOLAR777/AirBench/issues/32)

## What this slice delivers

`airbench.team_runtime.TeamRuntime` executes one already admitted `TeamPlan` through the existing AirBench authorities:

- `ResourceScheduler` owns physical admission, execution mode, and resource leases.
- `HandoffCoordinator` owns dependency barriers and typed packet acceptance.
- `Orchestrator` owns task state, runtime audit events, and consequential transitions.
- `WorkerContext` creates one isolated, signed context per worker.
- A worker callback receives one `WorkerInvocation` and one `CancellationToken`. It can return a `WorkerResult` proposal or a typed `WorkerExecution` containing proposals and `HandoffSubmission` records.

The runtime supports the scheduler's `parallel`, `pipelined`, and `serial_virtual_team` modes. Parallel work is submitted only for a deterministic ready set and is committed to the ledger in stable assignment order. Serial virtual-team work retains the same team identity and packet boundaries while holding at most one active lease.

## Safety and provenance behavior

- A runtime must receive an admitted or explicitly degraded resource plan. Queued and stopped plans do not execute.
- The assignment mapping and worker callback mapping must exactly match the committed team plan.
- Cyclic or undeclared dependency graphs are rejected before worker execution.
- Dependent work cannot start until a coordinator-owned barrier is completed by accepted handoffs.
- Handoffs are checked for source assignment, active source lease, destination topology, plan and policy identity, clearance, taint, and governed references.
- Worker results cannot mark themselves verified or complete. The runtime never records `completion.recorded`.
- Successful worker ledger payloads contain result hashes and provenance metadata, not unbounded worker output.
- Context compaction is a metadata-only manifest rebuilt from committed event IDs and hashes, accepted handoff packets, result IDs, evidence references, clearance, and taint. A model-generated summary is not used as authoritative state.
- Cancellation is cooperative. The host sets a shared token; the runtime records worker cancellation, releases leases, records team cancellation, and then transitions the task to `cancelled`.
- A timeout or worker failure records a typed failure, releases the lease, records team failure, and transitions the task to `failed`.
- Lifecycle interception is fail-closed. Interceptor calls and vetoes are ledger-audited. The hook seam includes task, team, worker, model, tool, barrier, compaction, and completion boundaries.

## Verification performed

Focused M4.4 tests:

```text
python -m pytest -q tests/test_m44_team_runtime.py
6 passed
```

The focused tests prove:

1. Two parallel callbacks overlap while `worker.completed` commits remain deterministic.
2. A serial sink cannot start until its source handoff completes the join barrier.
3. Cooperative cancellation produces a cancelled task and no active leases.
4. A deadline-bounded callback produces `worker_timeout`, a failed task, and no active leases.
5. Ledger-derived compaction is idempotent and retains the worker result reference.
6. A lifecycle veto prevents worker execution and records `lifecycle.blocked`.

Repository verification:

```text
python -m pytest -q
all tests passed
python -m compileall -q contracts airbench
python scripts/generate_frontend_contracts.py --check
git diff --check
```

These are software and synthetic-resource tests. They do not claim that a real GPU, model server, OCR pipeline, sandbox, or production ledger deployment has been qualified. Those checks remain part of the manual and hardware-dependent acceptance work, including issue #113.

## Known boundary for the next integration slice

The runtime intentionally accepts a worker callback instead of starting model servers or a process supervisor. The production adapter must bind that callback to the model router and tool gateway while preserving the same one-call boundary, signed `WorkerContext`, cancellation token, and orchestrator audit path. Hard process termination, model-server cancellation semantics, crash recovery of an in-flight callback, and multi-node scheduling require the deployment and serving workstreams and are not claimed by this issue.
