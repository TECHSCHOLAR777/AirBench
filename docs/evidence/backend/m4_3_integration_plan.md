# M4.3 Integration Checkpoint and Implementation Plan

Status: implemented and verified. This file records the M4.3 design and
integration contract. Implementation evidence is in
`docs/evidence/backend/m4_3_implementation_evidence.md`.

Date: 2026-09-08

## 1. Understanding checkpoint

### Issue and sequencing

- Issue: [#31, M4.3 WorkPackets, handoffs, and join barriers](https://github.com/TECHSCHOLAR777/AirBench/issues/31)
- Parent: [#9, M4 AirBench Harness and worker teams](https://github.com/TECHSCHOLAR777/AirBench/issues/9)
- State: open.
- Assignee: `TECHSCHOLAR777`.
- Language: Python.
- Lane: serial.
- Prerequisites: M4.1/#29 and M4.2/#30. Both are currently open.
- Closed upstream prerequisites: M3.1/#24 and M1.3/#18.
- Next sibling: M4.4/#32, which depends on M4.3 and must not start before this
  integration gate passes.

The intended sequence is:

```text
M4.1/#29 isolated worker assignments and scopes  \
                                                     +--> M4.3/#31 handoffs and barriers --> M4.4/#32 execution modes
M4.2/#30 resource plans, leases, and scheduling  /
```

M4.1 and M4.2 were developed in separate worktrees. M4.3 was serialized after
their contracts were available. Shared contract edits, orchestrator transition
edits, ledger catalog edits, and integration tests were kept serialized.

### User outcome

AirBench can accept a worker's immutable, typed result as a controlled handoff,
validate that it is allowed to cross the declared team boundary, and make a
deterministic join-barrier decision. The same semantics must work for parallel
workers and a serial virtual team. A worker cannot directly message a peer,
skip an upstream dependency, turn a proposal into authority, or cause a
barrier to pass without the orchestrator and ledger accepting it.

### Definition of done interpreted for M4.3

The implementation is complete only when it has:

1. Typed, immutable packet and handoff contracts with deterministic hashes.
2. Orchestrator-owned validation of task, team, source, destination, stage,
   dependency, clearance, taint, evidence, artifact, and lease references.
3. Explicit join-barrier states, absolute deadlines, and deterministic handling
   of missing, conflicting, late, timed-out, and cancelled packets.
4. Append-only events that make accepted and rejected handoffs and barrier
   outcomes replayable.
5. Restart behavior rebuilt from committed ledger events, not in-memory worker
   state or model summaries.
6. Focused normal, malformed, failure, timeout, cancellation, replay,
   provenance, clearance, tamper, idempotency, and no-egress tests.
7. Regression evidence showing that M4.1 scopes and M4.2 leases are consumed,
   not bypassed.

## 2. Governing architecture and ownership

The following documents govern this issue:

- `docs/foundations/01_architecture_design.md`: the request lifecycle, deterministic
  orchestrator, three cross-system properties, and core versus pack boundary.
- `docs/foundations/02_domain_pack_framework.md`: the core contains no sector rules. M4.3
  accepts generic stages, capabilities, evidence references, and policies; it
  must not contain refinery, defence, government, or other sector assumptions.
- `docs/runtime/backend_development_plan.md`: typed Python boundaries, ledger events,
  deterministic fixtures, restart tests, and no-network evidence are required.
- `docs/operations/agent_development_workflow.md`: M4 uses
  `docs/runtime/airbench_harness.md`, `docs/foundations/06_orchestration_engine.md`, `docs/foundations/07_serving_and_routing.md`,
  and `docs/delivery/deployment_and_scale.md`; shared schemas and orchestrator transitions
  are serialized.
- `docs/runtime/airbench_harness.md`: workers are stateless and isolated; WorkPackets
  are the only team communication; the orchestrator owns synchronization and
  completion; default-fail verification is mandatory.
- `docs/foundations/06_orchestration_engine.md`: only the orchestrator advances state; team
  substates and barriers are state-machine transitions with timeouts and
  idempotency keys.
- `docs/foundations/07_serving_and_routing.md`: routing is per worker assignment; a resource
  lease and qualified target are prerequisites for a model call; routing does
  not own handoffs or completion.
- `docs/delivery/deployment_and_scale.md`: parallel, pipelined, and serial virtual-team
  modes preserve the same logical team and audit semantics.
- `docs/assurance/memory_and_audit_ledger.md`: handoffs, packet hashes, barriers,
  disagreement, cancellation, and replay are authoritative ledger history.
- `docs/assurance/sovereignty_and_security.md`: worker isolation, no peer channel,
  least-privilege scope, untrusted evidence treatment, and ledger-backed
  security decisions apply at this boundary.

### Ownership decisions

| Concern | Owner | M4.3 relationship |
|---|---|---|
| Worker identity, assignment, scoped evidence, tools, scratch, deadline | M4.1/#29 | Consume the final assignment and scope; do not recreate them |
| Hardware measurement and resource admission | M5.2/#34 | Consume its measured profile and finalized admission result |
| Worker lease issuance and scheduling | M4.2/#30 | Require a valid lease reference; do not allocate resources |
| Model qualification and target selection | M5 | Treat model output and target identity as evidence, not routing authority |
| Team plan and state transitions | Orchestrator/M3 plus M4 integration | Only the orchestrator commits handoff and barrier state |
| Handoff validation and barrier projection | M4.3/#31 | Primary implementation scope |
| Parallel and serial worker loops | M4.4/#32 | Not implemented here |
| Field rules, source quality, risk, and deliverable criteria | Domain pack | Read through generic contracts only |

## 3. Current repository baseline and contract findings

The current branch is `main`, synchronized with `origin/main`. The working
tree was clean at the start of preparation and the command
`python -m pytest -q` completed successfully at that point. During this
preparation, concurrent M4.1/M4.2 work appeared in the working tree. Those
changes are not part of this artifact and were not edited, staged, reset, or
committed here.

### Existing contracts

`src/contracts/models.py` currently provides:

- `TeamPlan` with assignment IDs and a dependency graph keyed by assignment ID.
- `WorkerAssignment` with task/team/worker identity, role, stage, input and
  output schemas, evidence references, allowed tools, clearance, taint,
  capability requirement, deadline, and idempotency key.
- Frozen `WorkPacket` with task/team/source worker, `destination_stage`, fact and
  evidence references, artifact references, checks, unresolved questions,
  proposed result, clearance, taint, and `packet_hash`.
- `WorkerResult` with a packet reference, but no handoff or barrier semantics.
- `TeamResourcePlan` with reservations, execution mode, priority, admission,
  and verifier capacity.
- `ModelCallRequest`, which already requires `role` and `resource_lease_id`.
- `LedgerEventEnvelope`, which is frozen, canonicalized, hash chained, and
  append-only.

`src/contracts/security/admission.py` contains an in-memory `AdmissionController` that
makes VRAM-oriented parallel, serial, queued, and stopped decisions. The
concurrent uncommitted M4.2 work also adds richer measurement inputs,
dependency/stage metadata, and `ResourceReservation`/`ResourceLease` models.
It is not yet safe to treat those edits as the final merged interface, and the
controller is not yet a complete per-worker durable lease manager. M4.3 must
not extend that responsibility. M4.2 and M5.2 must provide the finalized
lease identity and active lease semantics before M4.3 integration.

### Contract gaps that must be resolved after M4.1 and M4.2 merge

These are deliberate integration blockers, not reasons to edit shared code now.

1. **Packet destination identity.** `WorkPacket` has a destination stage but no
   destination worker or assignment. A stage alone is ambiguous when a plan
   has multiple workers at that stage. M4.3 needs an explicit typed handoff
   envelope containing `destination_assignment_id`, or a formally defined
   one-to-one stage resolution rule. The recommended design is explicit
   destination assignment in the handoff request, with the packet's declared
   destination stage checked against that assignment.
2. **Source assignment identity.** The packet identifies `source_worker_id`,
   while `TeamPlan.dependency_graph` is keyed by assignment IDs. M4.3 must
   resolve the worker to exactly one active assignment and include the source
   assignment identity in the durable handoff record.
3. **Packet hash semantics.** `packet_hash` exists, but current validation does
   not recompute it and existing fixtures use placeholder values. The final
   rule must be deterministic, for example SHA-256 of canonical packet JSON
   with the `packet_hash` field excluded. New M4.3 fixtures must contain real
   hashes; old fixtures need an explicit compatibility treatment.
4. **Referenced-record resolution.** WorkPackets carry IDs rather than full
   facts. The handoff validator needs a read-only resolver for committed
   `FactEnvelope`, `UntrustedEvidence`, artifact manifests, and assignment
   records. It must not parse files or read raw document paths.
5. **TeamResourcePlan and lease shape.** The committed Python model was
   smaller than `src/contracts/schemas/team_resource_plan.schema.yaml`, which describes
   plan identity, per-worker target and reservation details, deadlines,
   dependency graph, scheduling, safety invariants, and provenance. Concurrent
   M4.2 edits now add many of those fields and a `ResourceLease`, but they are
   still uncommitted and require their own tests and merge review. M4.3 must
   consume the final M4.2 interface rather than selecting fields from one
   representation by convention.
6. **Orchestrator transition coverage.** The current orchestrator allows
   `barrier.waiting` but does not yet expose M4-specific `worker.handoff`,
   `join_barrier.waiting`, or `join_barrier.completed` as controlled
   transitions. M4.3 must add them only after M4.1's assignment transition
   changes are merged.
7. **Replay state coverage.** `src/contracts/provenance/ledger.py` has generic task replay,
   but `_apply_event` does not project worker handoff or join-barrier state.
   M4.3 needs a deterministic team/barrier projection or equivalent replay
   reducer without making the event ledger mutable.

## 4. Proposed typed M4.3 interface

The implementation must preserve the existing provider-neutral contract style.
No raw model/provider type, untyped control dictionary, or natural-language
instruction is authoritative.

### WorkPacket

`WorkPacket` remains an immutable content packet. Its fields are validated
before any handoff state changes. The implementation must ensure:

- `schema_version` and `compatibility_id` are present or handled by the
  existing compatibility rule;
- task and team IDs match the current task and TeamPlan;
- source worker ID resolves to the source assignment;
- destination stage is non-empty and matches the destination assignment;
- facts, evidence, or artifact references are non-empty as required by the
  packet contract;
- all reference IDs are stable and resolvable through governed projections;
- checks contain only typed boolean results with named check identities;
- unresolved questions and limitations remain visible and are not converted to
  a clean or verified state;
- proposed output cannot contain completion, authority, tool-grant, or policy
  mutation fields;
- clearance is never higher than the task and receiving worker permit;
- taint is monotonic and never silently downgraded;
- `packet_hash` is recomputed from the canonical immutable packet content;
- the packet object cannot be mutated after validation.

The packet should carry references and bounded proposal text, not raw uploaded
document content or a worker's private transcript. Raw files remain
`UntrustedEvidence` and are accessible only through the File Intake Layer and
governed read interfaces.

### Handoff envelope

The recommended new typed envelope is an immutable `HandoffSubmission` or
equivalent contract. It should contain:

- handoff ID and schema version;
- task ID and team ID;
- source assignment ID and source worker ID;
- destination assignment ID and destination stage;
- immutable WorkPacket reference and packet hash, with the canonical packet
  available through a governed packet store or included in the event payload;
- join-barrier ID and barrier version;
- source resource lease ID, when the final M4.2 contract requires it;
- submission timestamp and absolute deadline context;
- idempotency key;
- policy and plan version references.

The envelope is a routing and audit record, not a second mutable packet. A
duplicate handoff with the same identity and hash is idempotent. Reusing an
identity with a different hash is rejected as tampering or idempotency
conflict.

### Join barrier

The recommended typed `JoinBarrier` contract should contain:

- barrier ID and monotonically increasing barrier version;
- task ID, team ID, destination stage, and target assignment ID;
- required predecessor assignment IDs;
- accepted packet IDs and hashes;
- missing predecessor IDs;
- conflict packet IDs and hashes;
- deadline and clock/reference time;
- join policy, with `join_all` as the safe default;
- cancellation and timeout policy;
- clearance, taint summary, plan version, and policy version;
- status and idempotency key.

Recommended barrier statuses are:

```text
waiting
completed
missing
conflicting
timed_out
cancelled
needs_review
```

`missing` and `conflicting` describe a blocked barrier condition and may be
resolved only by a new orchestrator-committed barrier version or an explicit
review outcome. `completed`, `timed_out`, `cancelled`, and `needs_review` are
terminal for that barrier version. A late packet is a handoff outcome and does
not silently reopen a timed-out barrier.

## 5. Handoff validation rules

The orchestrator-facing coordinator should validate in this order, before
committing any accepted handoff or satisfying a barrier.

### Identity and plan checks

1. Validate the typed envelope and nested packet before state mutation.
2. Confirm the task exists and is not terminal or cancelled.
3. Confirm the task ID and team ID agree across the task, TeamPlan, packet,
   envelope, and barrier.
4. Confirm the plan version is the currently committed version. A stale plan
   may be recorded as rejected, but it cannot satisfy a current barrier.
5. Resolve the source assignment by assignment ID and verify its worker ID,
   role, stage, task, team, and status.
6. Resolve the destination assignment and verify its worker ID, stage, task,
   team, status, and declared input schema.
7. Reject self-handoffs unless a plan explicitly declares one and the
   orchestrator has a bounded reason. Direct peer channels remain forbidden.

### Source, destination, and dependency checks

- The source worker must belong to the committed TeamPlan.
- The source worker ID must not be supplied by packet text alone; it must come
  from the validated assignment and the orchestrator-side identity.
- The destination assignment must be explicit. If only a stage is supplied,
  acceptance is allowed only when that stage resolves to exactly one assignment
  under the committed plan.
- `packet.destination_stage` must equal the destination assignment stage.
- The destination assignment's direct predecessors must be read from the
  TeamPlan dependency graph, which is keyed by assignment IDs.
- A source may satisfy a destination only when it is a declared direct
  predecessor, or when the plan explicitly declares a fan-in stage that the
  barrier contract understands.
- All required predecessors must be represented before a `join_all` barrier
  can complete. A model cannot claim that an absent predecessor is equivalent
  to an empty packet.
- A packet from a worker in another team, a stale assignment, or an undeclared
  stage is rejected and cannot be used as evidence.

### Provenance, clearance, and taint checks

For every referenced fact and evidence record, the coordinator must resolve and
check:

- source identity and source revision remain addressable;
- confidence is present and remains attached to the referenced fact;
- clearance is within the task, source assignment, destination assignment, and
  requesting principal's effective read ceiling;
- taint is retained exactly or conservatively worsened;
- an `UntrustedEvidence` reference remains untrusted data and cannot become an
  instruction, capability, policy, or authority grant;
- artifact references resolve to manifests and hashes, not arbitrary paths;
- derived facts preserve parent references and computation evidence;
- packet-level clearance is no higher than the most restrictive permitted
  boundary and packet-level taint is no cleaner than its governed inputs.

The coordinator may create a clearance-filtered projection for the receiving
worker, but it must not overwrite the authoritative packet or replace
confidence with prose such as "high confidence". Any projection must carry the
source packet hash and an audit reference.

### Hash and idempotency checks

- Recompute the packet content hash using the agreed canonical algorithm.
- Verify every artifact and referenced evidence manifest hash available at the
  boundary.
- Verify the handoff envelope hash or digest before accepting it.
- Use a deterministic key including task, team, barrier version, source
  assignment, destination assignment, packet identity, and attempt.
- The same valid submission can be replayed without a second barrier effect.
- The same idempotency key with changed packet, destination, deadline, or policy
  data fails closed.

### Lease and scope checks

M4.3 does not issue or renew leases. When M4.2's contract includes the lease
reference in an assignment or handoff, the coordinator must verify:

- lease ID belongs to the task, team, source worker, and assignment;
- lease is active and not expired or revoked at submission time;
- lease capability and clearance match the assignment;
- the packet does not claim resources, tools, paths, or authority beyond the
  assignment scope;
- an expired source lease cannot produce an accepted handoff unless the
  orchestrator explicitly records a policy-approved recovery path.

## 6. Join-barrier state machine

All barrier state changes are orchestrator-owned and ledger-backed. The clock
is injected or supplied as a recorded observation so tests do not depend on
sleep timing.

```text
waiting
  | all required accepted packets and checks satisfied
  v
completed

waiting --required packet absent at deadline--> timed_out
waiting --packet conflict or policy ambiguity--> conflicting -> needs_review
waiting --missing required packet is explicitly unresolved--> missing
waiting --task/team cancellation-------------------------> cancelled

late handoff after deadline -> late handoff outcome; barrier does not pass
```

More precise rules:

- A barrier is opened with an absolute RFC3339 deadline and a committed plan
  version.
- On opening, the missing set is the required predecessor set minus already
  accepted packets from the same plan version.
- A valid packet removes exactly its source predecessor from the missing set.
- A duplicate packet does not change the set or create another downstream
  transition.
- Multiple different packets for the same source and barrier are retained. If
  the plan does not explicitly allow alternatives, the barrier becomes
  `conflicting` and cannot complete.
- If a packet arrives after the deadline, validate it for audit purposes but
  mark the handoff late. It cannot satisfy the expired barrier version.
- At or after the recorded deadline, the orchestrator resolves a barrier with
  required missing packets as `timed_out`; no background timer is authoritative.
- Cancellation resolves all waiting barriers and dependent work as
  `cancelled`, releases no resource itself, and delegates lease release to
  M4.2/M4.4.
- `join_any_with_fallback` is not the default and must not be used where it
  would remove required independent verification. If supported, the plan must
  name the fallback and the verifier requirement explicitly.
- A completed barrier does not verify packet content or authorize completion;
  it only proves that the declared synchronization precondition was met.

## 7. Failure and recovery behavior

### Missing packets

Keep the barrier waiting until its deadline when policy permits. Record the
missing assignment IDs in the barrier projection. At the deadline, resolve as
`timed_out` or `needs_review` according to the committed policy. Never treat a
missing verifier or missing required evidence packet as success.

### Conflicting packets

Preserve every packet and hash. M4.3 must not choose by majority vote, recency,
model confidence, or prose quality. The barrier becomes `conflicting` and the
orchestrator routes the preserved evidence to deterministic verification,
consistency review, or human review. The domain pack may define what a later
checker should compare, but M4.3 does not hard-code that rule.

### Late packets

A late packet is not silently merged into committed state. Record its arrival,
deadline comparison, source, destination, packet hash, and reason. The
orchestrator may create a new barrier version only if the task policy permits
reopening; the old barrier and its timeout remain immutable history.

### Timeout

Timeout is a typed state outcome, not a Python exception hidden in a worker.
It records barrier ID/version, deadline, observed time, missing IDs, lease
references, and the next policy action. Dependents are cancelled, retried, or
escalated only through the orchestrator's bounded policy.

### Cancellation

Cancellation is orchestrator initiated. The coordinator records the barrier
and unresolved handoffs as cancelled, prevents a late worker from satisfying
the barrier, and leaves resource release to the lease owner. A cancellation
acknowledgement may be recorded, but a worker cannot veto task cancellation.

### Ledger failure

If the ledger append or checkpoint fails:

- the handoff is not accepted;
- the barrier is not advanced;
- no dependent worker is released to start;
- the packet may remain in a non-authoritative quarantine or be retried with
  the same idempotency key;
- the failure is surfaced as a typed storage failure.

## 8. Restart and replay model

The ledger and immutable packet/artifact manifests are authoritative. Private
worker context, scratch directories, process memory, and model-generated
summaries are not.

On restart the coordinator must:

1. Verify the ledger chain and committed transaction seals.
2. Replay events in sequence order.
3. Reconstruct the current committed TeamPlan version and M4.1 assignment
   scopes.
4. Reconstruct accepted handoffs by handoff identity and packet hash.
5. Reconstruct each barrier version, accepted set, missing set, conflict set,
   deadline, and terminal state.
6. Reject or quarantine events whose packet or referenced manifest hash no
   longer matches the committed record.
7. Re-run only deterministic, idempotent projection work. Never invoke a model,
   tool, or peer worker merely because a process restarted.
8. Resume only from the last committed orchestrator checkpoint. A barrier that
   had not committed its acceptance remains unresolved.

Replay must produce the same barrier state and downstream eligibility for the
same committed event stream. A packet that was in memory but not in the
ledger is not accepted after restart.

## 9. Ledger events and catalog gaps

### Existing events to use

The repository already lists these events in `src/contracts/models.py` and
`src/contracts/schemas/ledger_event_catalog.yaml`:

- `worker.handoff`: accepted immutable handoff record, including packet hash,
  source and destination identities, barrier version, lease reference, and
  provenance summary.
- `join_barrier.waiting`: barrier version opened or still waiting, including
  required and missing assignment IDs and deadline.
- `join_barrier.completed`: all required handoffs and checks satisfied for the
  barrier version.
- `worker.failed`: source work failed before producing a usable handoff.
- `worker.cancelled`: worker cancellation and associated lease-release
  reference.
- `escalation.required`: conflict, timeout, or policy outcome requires review.
- `task.cancelled` and `task.failed`: task-level terminal outcomes.
- `checkpoint.committed`: the orchestrator checkpoint after a committed
  transition.

The generic `barrier.waiting` and `barrier.completed` events are already used
by earlier orchestration tests. They should remain compatible aliases for
existing traces, but M4.3 should use the more specific `join_barrier.*` events
for worker-team barriers. Do not create two events for one M4.3 transition.

### Required payload contracts

Event payloads must be typed and versioned, even though the current catalog is
primarily an event-name list. Add payload contracts for:

- `HandoffRecord` or equivalent accepted/rejected handoff attempt;
- `JoinBarrierRecord` or equivalent barrier snapshot and outcome;
- the packet manifest used for replay.

Payloads must include at least task, team, plan version, worker/assignment
identities, stage, packet/barrier IDs, hashes, clearance, taint summary,
provenance references, lease ID where applicable, policy version, observed
time, and idempotency key. Rejection and failure payloads must include a
bounded failure code and reason.

### Catalog gaps to resolve before implementation

The existing catalog has no distinct event for a rejected handoff or a
non-completed barrier resolution. The recommended minimal additions are:

- `worker.handoff.rejected`: typed validation failure; no downstream effect.
- `worker.handoff.late`: valid packet received after the barrier deadline; no
  satisfaction of the old barrier version.
- `join_barrier.resolved`: outcome in `missing`, `conflicting`, `timed_out`,
  `cancelled`, or `needs_review`, with the missing/conflict sets and policy
  action.

If the implementation instead encodes these outcomes in existing events, that
choice must be documented and tested so replay cannot confuse an accepted
handoff with a rejected, late, or unresolved one. Adding event names requires
keeping `LEDGER_EVENT_TYPES` and `src/contracts/schemas/ledger_event_catalog.yaml` in
sync.

The current orchestrator transition map and
`src/contracts/schemas/state_transition_table.yaml` also need a coordinated M4.3 update.
The table is currently a generic older state list and does not describe team
barrier substates. Do not update it in this preparation task.

## 10. Exact M4.3 ownership after M4.1 and M4.2 merge

M4.3 should own only the following paths during its serialized implementation
window:

```text
src/contracts/models.py                    # additive typed handoff/barrier contracts and hash rules
src/contracts/__init__.py                  # exports for the new typed contracts
src/contracts/schemas/handoff_barrier.schema.yaml  # machine-readable packet/handoff/barrier payload contract
src/contracts/schemas/schema_registry.yaml         # register new contract identities
src/contracts/schemas/ledger_event_catalog.yaml    # add only approved M4.3 event names
src/contracts/schemas/state_transition_table.yaml  # reconcile team barrier transitions
src/contracts/execution/orchestrator.py              # orchestrator-owned handoff/barrier API and transition guards
src/contracts/execution/handoffs.py                  # deterministic validation and replay coordinator
tests/test_m43_handoffs.py             # packet and handoff contract/validation tests
tests/test_m43_barriers.py             # barrier lifecycle and deadline tests
tests/test_m43_replay.py               # restart and ledger reconstruction tests
tests/test_m43_integration.py          # M4.1 assignment plus M4.2 lease seam tests
tests/fixtures/m43/                    # sanitized typed packets, manifests, and event traces
docs/evidence/backend/m4_3_implementation_evidence.md   # implementation evidence, limits, and unresolved risks
```

The exact filename of the coordinator may be changed during the post-merge
contract checkpoint, but there must be one owner for the coordination logic.
Do not create a second handoff implementation under `src/airbench/` or a second
parser, scheduler, router, or peer channel.

M4.3 may edit `src/contracts/models.py`, `src/contracts/execution/orchestrator.py`, and the
ledger/state catalogs only in its serialized window after the M4.1 and M4.2
branches have merged. Neither M4.1 nor M4.2 should concurrently edit these
M4.3-owned integration additions.

## 11. Focused test plan

### Contract and validation tests

- Valid WorkPacket and handoff round-trip through canonical serialization.
- Frozen packet and envelope reject mutation.
- Unknown fields, missing IDs, incompatible versions, malformed timestamps,
  empty evidence, and invalid check types fail closed.
- Packet hash mismatch is rejected.
- Duplicate valid handoff is idempotent.
- Same idempotency key with a different packet or destination is rejected.
- Wrong task, team, plan version, source worker, source assignment,
  destination assignment, or stage is rejected.
- Source not in the dependency graph is rejected.
- A graph with missing required predecessor cannot complete its barrier.
- Multiple assignments at one stage require explicit destination identity.

### Provenance and security tests

- Missing source, confidence, clearance, or taint on a referenced governed fact
  is rejected.
- A packet carrying untrusted evidence cannot become clean.
- A higher-clearance fact cannot cross to a lower-authority worker.
- A packet cannot add a tool, path, permission, worker, policy, or authority.
- Artifact reference hash mismatch is rejected.
- Raw file paths and raw document content are never read by the coordinator.
- Worker peer-to-peer or hidden scratch references have no accepted API.
- Coordinator imports and execution have no network client, DNS, socket, model
  endpoint, subprocess, or package-download path.

### Barrier lifecycle tests

- Barrier opens with the correct required predecessor set and deadline.
- One valid packet leaves the correct missing set.
- All valid packets complete a `join_all` barrier exactly once.
- Duplicate packets do not advance the barrier twice.
- Conflicting packet hashes are preserved and block completion.
- Missing required packet remains waiting before the deadline.
- Missing required packet becomes timed out at the deadline.
- A late packet is audited but cannot satisfy the expired version.
- Cancellation resolves the barrier and prevents later satisfaction.
- Timeout, conflict, or missing packet produces the configured review/escalation
  outcome and never an implicit pass.
- Required verifier packet is never treated as optional.

### Restart and ledger tests

- Event hash chain and transaction seal are verified before replay.
- Restart rebuilds accepted packets, missing sets, conflicts, deadlines, and
  terminal barrier state.
- An uncommitted in-memory handoff is absent after restart.
- Replaying the same committed events produces the same downstream eligibility.
- Ledger append failure leaves no accepted handoff or barrier advancement.
- Checkpoint failure stops further consequential work.
- Replayed duplicate handoff does not re-run a model or tool.
- Clearance-filtered replay does not expose hidden packet content.

### M4.1 and M4.2 seam tests

- A packet from a valid M4.1 worker context is accepted only within its scoped
  evidence, tools, clearance, taint, and deadline.
- A packet with a missing, expired, wrong-team, or wrong-worker M4.2 lease is
  rejected.
- Parallel and serial synthetic plans produce the same packet and barrier
  semantics, with different scheduling metadata only.
- M4.3 does not perform GPU measurement, admission, model routing, or worker
  execution.

## 12. Acceptance commands and evidence

After implementation, run from the repository root:

```text
python -m pytest -q tests/test_contracts.py tests/test_orchestrator.py tests/test_m35_walking_skeleton.py tests/test_m43_handoffs.py tests/test_m43_barriers.py tests/test_m43_replay.py tests/test_m43_integration.py
python -m pytest -q
python -m compileall contracts airbench
```

The implementation evidence must include:

- exact changed files and contract version decision;
- the finalized M4.1 and M4.2 interface hashes used by the tests;
- event trace showing accepted, rejected, late, conflict, timeout, and
  cancellation paths;
- replay output before and after a simulated restart;
- provenance, clearance, taint, and packet-hash assertions;
- ledger failure evidence;
- no-egress/static security evidence for the coordinator;
- explicit statement that no real GPU hardware was required for M4.3 software
  correctness and that GPU validation remains with the later hardware issue;
- remaining risks and the exact prerequisites for M4.4.

## 13. Non-goals

M4.3 must not implement or claim:

- worker execution loops, parallel execution, or serial virtual-team lifecycle;
- GPU probing, hardware measurement, VRAM/KV accounting, or lease issuance;
- model routing, target ranking, backend invocation, vLLM, or NIM adapters;
- domain rules, refinery assumptions, P&ID logic, approval authority, or
  sector-specific conflict resolution;
- peer-to-peer worker channels, shared hidden scratch, or unlogged messages;
- parsing uploaded or ingested files outside the File Intake Layer;
- context compaction or model-generated summaries as authoritative state;
- verification of the packet's substantive domain correctness;
- final task completion, human sign-off, or deliverable approval.

M4.3 proves synchronization eligibility and preserves evidence. M4.4 proves
that workers can execute through those synchronized boundaries.

## 14. Condition before M4.3 implementation begins

M4.3 implementation may start only when all of the following are true:

1. M4.1/#29 and M4.2/#30 have merged and their focused tests pass.
2. The M4.1 assignment/context scope and M4.2 lease/resource-plan contracts
   are frozen with version or digest references.
3. The destination assignment and source assignment identity ambiguity is
   resolved in a typed contract decision.
4. Packet hash semantics and compatibility handling for existing fixtures are
   approved.
5. The canonical event set and payload contracts are agreed, including how
   rejected, late, conflicting, timed-out, and cancelled outcomes replay.
6. The orchestrator transition map and state-transition table ownership is
   available for this serialized change.
7. A separate worktree is created for M4.3, with no concurrent edits to its
   shared contract, orchestrator, ledger catalog, or integration-test paths.

Until those conditions are met, M4.3 is prepared but not implementation-ready.
