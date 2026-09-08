# M4.1 Worker Context Evidence

## Scope

M4.1 provides the runtime boundary for one worker assignment. It wraps the
existing `WorkerAssignment`, `TaskEnvelope`, `CapabilityScope`, and
`ModelCallRequest` contracts. It does not select models, run a worker loop,
measure hardware, parse files, or implement handoffs and barriers.

## Implemented behavior

- `create_worker_assignment` creates a deterministic typed assignment and
  narrows evidence, tools, capability, clearance, taint, and deadline from the
  task envelope.
- `create_worker_context` creates a distinct scratch root for each task, team,
  worker, and assignment. Scratch paths reject absolute paths, traversal, peer
  roots, and writes outside the worker root.
- Evidence access is reference-scoped and returns provenance metadata only.
  Source, confidence, clearance, taint, and content hash are preserved. A
  worker cannot read a permitted reference outside its assignment.
- Tool capability uses the existing signed `CapabilityScope`. A worker with no
  tools receives no tool token. A worker with tools receives only its task-
  narrowed tools and its own scratch root.
- Model-call construction binds task, team, worker, assignment role,
  capability, clearance, evidence references, deadline, and the required
  orchestrator resource lease. It does not select a target or call a model.
- `Orchestrator.assign_worker` accepts an assignment only after a committed
  team plan declares it. The transition is append-only and idempotent; a
  conflicting reuse of an assignment identity is rejected.

## Verification

The focused test file uses deterministic synthetic evidence and
`FakeBackend`. It covers:

- valid and malformed assignment creation;
- task-scope narrowing for evidence, tools, capability, clearance, and taint;
- distinct scratch roots and peer/shared-state access rejection;
- provenance preservation and clearance enforcement;
- signed tool-scope identity;
- model-call identity handoff and required lease;
- hard deadlines and bounded model timeout;
- orchestrator assignment audit transition, idempotency, and conflict;
- ledger failure without state mutation;
- SQLite restart and replay;
- absence of network imports in the worker-context module.

Run:

```text
python -m pytest -q tests/test_m41_worker_contexts.py
python -m pytest -q tests/test_contracts.py tests/test_orchestrator.py tests/test_m53_backend.py
```

## Explicit limitation

The evidence is software and synthetic-fixture evidence. No GPU, vLLM, NIM,
live model, or hardware concurrency claim is made. Real hardware qualification
remains a later validation issue owned by the hardware and serving milestones.
