# FE-REF-03: Audit-Safe Live Work Trace

## Status

Local implementation slice. The React workspace now turns the approved Node task projection into a readable work trace. It does not make the desktop authoritative for task state, routing, evidence, verification, or approvals.

## Operator outcome

An operator can see what AirBench has actually recorded for a task without being asked to interpret a raw event payload or trust a simulated progress indicator. The workspace explains the current Node state, completed records, waiting conditions, evidence, verification, artifacts, and the available plan-level hardware context.

## Authoritative inputs

The trace accepts only these existing typed values:

- `TaskProjection` for task state, phase, cursor, activity, evidence, questions, artifacts, diagnostics, connection identity, and ledger head.
- `TaskPlanReview` for the Node-issued execution mode, worker capability roles, hardware reason, plan and policy hashes, and plan ledger reference.
- The existing cursor-aware `TaskEventSynchronizer` for reconnect, replay, gap, and blocked state.

The desktop does not call a model endpoint, infer a worker state, synthesize a routing target, parse an input file, or write an audit record.

## Visible structure

The live task workspace is deliberately a task narrative, not an infrastructure dashboard.

1. **Current Node state** shows the authoritative task status and phase, plus the latest recorded event when one is available.
2. **Work trace** presents the fixed work order: Plan, Work, Evidence, Verification, Review, Artifacts, Outcome. Each stage is waiting, active, recorded, or needs attention.
3. **Supporting records** group worker and tool events, source-backed evidence, latest verification, Node-reported questions, and artifact references.
4. **Plan review** remains the existing Node-issued plan and approval surface.
5. **Chronological activity** keeps the ordered task records available for a user who needs an event-by-event account.
6. **Technical trace** is a collapsed disclosure with plan-level capability and hardware context and event metadata: event type, sequence, Node time, actor, clearance, payload hash, and ledger reference.

The trace keeps a defensive sequence sort for a valid but unordered projection. Normal ordering, duplicate rejection, replay, and gap handling remain the responsibility of `TaskEventSynchronizer` and the Node contract.

## Provenance and privacy boundary

Evidence cards retain source document ID, source location, confidence, clearance, taint, extraction method, and source ledger reference. Technical event details retain event identity, time, actor, clearance, payload hash, and ledger reference.

The UI deliberately does not render:

- raw model reasoning, hidden chain of thought, token streams, or private scratchpads;
- raw event payload JSON;
- fabricated worker progress, typing indicators, countdowns, completion, routing targets, fallback reasons, or policy decisions;
- a local answer, pause, resume, approve, or artifact action that lacks a typed Node command.

Typed event summaries are the explanatory boundary. They show user-safe fields from the Node contract, such as a worker role and label or a verification summary, while the complete ledger payload remains Node-owned.

## Routing and intervention gaps

The current task event contract exposes plan-level execution mode, worker capability lanes, hardware profile reference, hardware reason, plan hash, policy hash, and ledger reference. It does not expose an actual selected model target, fallback event, fallback rationale, routing policy reason, or a question-answer command.

The Python Node API has a route-trace endpoint, but the current desktop Rust transport does not expose it. Its response also lacks the approved profile identity and clearance envelope used by snapshot and event transport validation. The webview must not call that endpoint directly. A future typed, Rust-mediated route-trace response needs task identity, Node identity, protocol version, clearance context, ordered entries, and ledger references before this UI may display its selected targets or fallback decisions.

When plan context is absent, the technical disclosure says that routing is not supplied. When it is present, it identifies the available plan context and explicitly states that exact target and fallback records are not in the event contract. The task workspace displays unresolved questions but offers no response control until a sequence-aware, ledgered Node command exists. Pause and resume are also absent until supplied by the Node contract. These are fail-closed product states, not unfinished UI controls.

## Acceptance evidence

`frontend/src/workTrace.test.ts` covers:

- typed team, tool, evidence, verification, review, artifact, and completion records grouped into the seven visible stages;
- preservation of evidence confidence, clearance, taint, source location, and ledger reference;
- failure and blocked outcome presentation without invented completion;
- technical metadata without a raw payload field;
- deterministic presentation order when a valid event batch arrives out of sequence.

The production frontend build and contract, no-egress, and Tauri configuration checks remain required before the issue can be considered ready for integration. Packaged desktop visual evidence remains owned by FE-REF-06 and FE-VAL-6.
