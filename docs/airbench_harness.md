# AirBench Harness

## Purpose

The AirBench Harness is the controlled execution environment in which a task becomes a completed, checked, and reviewable result. It adapts the strongest ideas from modern coding-agent harnesses: persistent sessions, typed tool use, lifecycle interception, context management, isolated workers, structured progress, default-fail completion, and fresh evaluation.

AirBench does not copy Claude Code, embed the Claude Code runtime, or depend on the Agent SDK. The harness is an AirBench core-engine capability and works with AirBench's local model router, domain packs, tool gateway, verification runner, artifact store, and append-only ledger.

AirBench uses the product term "multi-agent team" for a complex task. The implementation term is "worker team" because each agent is a stateless, scoped worker without independent authority.

The harness exists to give a model a rich but bounded working environment while making progress, evidence, verification, and authority structural parts of that environment.

## The governing rule

The harness is not another agent. It is deterministic host software around stateless model workers.

```text
Session Ledger
      |
Deterministic Harness Supervisor
      |
Context Builder -> Model Router -> Stateless Worker
      |                                      |
Tool Gateway <---------------------- Structured Proposal
      |
Sandbox / Retrieval / World Model / Renderer
      |
Deterministic Verification
      |
Independent Evaluator
      |
Artifact and Evidence Package
```

The orchestrator remains the only component that owns workflow state, advances the task, authorizes a tool action, commits a transition, or declares completion.

## What the harness adapts

The harness adopts these patterns:

- an append-only session and event history;
- a host-controlled model and tool loop;
- strict tool schemas and typed results;
- core-owned lifecycle interceptors;
- deny, review, and allow authority decisions;
- isolated worker contexts and scoped capabilities;
- context compaction rebuilt from verified state;
- persistent task contracts, criteria, checkpoints, and handoffs;
- default-fail completion criteria;
- an independent evaluator that did not generate the result;
- staged artifact writes and provenance gates.

The harness does not adopt these patterns:

- prompt text as a security policy;
- project files or uploaded documents as executable configuration;
- uncontrolled peer-to-peer agent communication;
- model-directed control flow;
- Git as the authoritative task and audit state;
- automatic approval of repeated prompts;
- an external model, telemetry, or plugin dependency.

## Where it sits

The harness is a core engine service used by the Orchestration Engine. It coordinates:

- the TaskEnvelope and task state machine;
- session and checkpoint records;
- context construction and compaction;
- model routing and hardware admission;
- worker assignment and handoff;
- the Tool Gateway and sandbox;
- deterministic verification and independent evaluation;
- artifact and evidence packaging;
- lifecycle interceptors;
- Memory and Audit Ledger writes.

The domain pack supplies field-specific skills, document profiles, checks, risk mappings, decision types, and deliverable templates through its contract. It does not implement a second orchestrator or grant a worker authority.

## TaskEnvelope

Every run begins with an immutable TaskEnvelope. It is the authority boundary for the entire task.

```text
TaskEnvelope
  task_id
  principal and clearance
  request and allowed interpretation
  domain_pack and version
  risk class and autonomy ceiling
  allowed evidence scope
  permitted worker capabilities
  permitted tools
  model and hardware policy
  output contract
  verification criteria
  resource, time, and action budgets
  current state and parent task reference
```

The envelope is created by the orchestrator after authorization. A document, model output, worker, tool result, or domain-pack skill cannot enlarge it.

## Core harness contracts

### TeamPlan

A TeamPlan is an orchestrator-owned, validated execution plan for a complex task. It contains:

- team ID and parent task ID;
- worker roles and typed responsibilities;
- dependency graph and synchronization barriers;
- allowed evidence and clearance for each worker;
- permitted tools for each worker;
- model capability requirements, not hard-coded model names;
- resource reservations and concurrency ceiling;
- timeout, retry, and cancellation policy;
- required verification and review stages;
- completion criteria with default-fail values;
- plan and policy version hashes.

The plan may be proposed by a model, but only the orchestrator may validate and commit it. Replanning can shrink or rearrange work inside the original envelope; it cannot add authority, tools, clearance, or an unapproved worker capability.

### WorkerAssignment

Each worker receives a bounded assignment containing:

- team ID, worker ID, and parent task ID;
- role and stage;
- exact input and output schemas;
- allowed evidence references and excerpts;
- allowed tools and path scope;
- clearance, taint, and provenance requirements;
- model capability requirement;
- resource lease and deadline;
- expected checks and handoff destination.

The worker does not receive the entire task transcript or raw document corpus by default.

### WorkPacket

Workers communicate through immutable, typed WorkPackets. A packet contains:

- source worker and destination stage;
- facts and evidence references;
- confidence, source, clearance, and taint for every fact;
- artifacts and hashes;
- checks already run and their results;
- unresolved questions and known limitations;
- proposed next result, never an authority grant;
- packet schema and version.

There is no unlogged shared scratchpad and no direct worker-to-worker tool channel.

### WorkerResult

A worker returns one of:

- a typed result;
- a structured tool proposal;
- a typed failure;
- a needs-review result;
- a handoff packet;
- a cancellation acknowledgement.

The result is a proposal until the orchestrator validates it and commits the next state transition.

### CompletionRecord

CompletionRecord is produced only by the orchestrator after all required criteria are true. It references:

- the final task and team state;
- every required evidence set;
- verification and evaluator results;
- artifact hashes and render checks;
- human review or sign-off, when required;
- the policy, pack, model, and hardware identities in force.

No worker can set a completion flag directly.

## Execution modes

The harness has three execution modes.

### Single worker

Used for simple, low-risk, or narrowly scoped steps. One qualified worker performs the bounded step and an external check verifies it.

### Bounded worker team

Used for complex tasks where context isolation, modality separation, parallel exploration, or an independent evaluator materially improves quality. The orchestrator creates a finite set of workers with explicit dependencies and a concurrency ceiling.

### Serial virtual team

Used when the task needs multiple specialist perspectives but the machine cannot run them concurrently. Workers still have separate identities, contexts, capabilities, and handoffs, but their execution is serialized or pipelined through the hardware budget.

Serial execution is still a multi-worker team. Hardware changes timing and concurrency, not the required roles, checks, provenance, or authority.

## When a team is activated

The orchestrator may activate team mode when one or more of the following are true:

- the task combines document understanding, retrieval, calculation, coding, and artifact production;
- the task requires independent verification;
- the task uses materially different modalities;
- the task has a complex dependency graph;
- the task risk model requires separation between generation and checking;
- a single context would be too large or would mix incompatible evidence;
- the domain pack declares a required specialist role.

Team mode is not activated merely because more model calls are available. Extra workers must have a defined responsibility and a checkable handoff.

## Initial worker roles

These are core capability interfaces, not fixed model identities. A deployment may use one qualified model for more than one role only when each role has been separately qualified.

- `lead_worker`: decomposes the task into typed steps and coordinates proposed work. It cannot advance state.
- `research_worker`: performs read-only retrieval and evidence extraction through approved local interfaces.
- `vision_worker`: interprets images and scanned pages through the File Intake Layer and qualified vision targets.
- `reasoning_worker`: synthesizes evidence and proposes domain-relevant reasoning.
- `code_worker`: writes and runs code only through the sandbox, with calculations treated as executable evidence.
- `verification_worker`: independently checks outputs, facts, calculations, and criteria.
- `render_worker`: prepares prose and typed field bindings for the Deliverable Engine; it does not own layout or numbers.
- `review_worker`: performs final completeness, evidence, and presentation review from a fresh context.

The first complex demonstration may use a lead, research or vision worker, code or reasoning worker as needed, an independent verification worker, and a render or review worker. The team is selected from the task's actual stages rather than instantiated at a fixed size.

## Team topology and coordination

The normal topology is:

```text
Lead and plan
      |
Specialist workers
      |
Orchestrator join barrier
      |
Independent verifier
      |
Renderer and final reviewer
      |
Completion gate
```

The orchestrator mediates all communication. A worker cannot:

- spawn another worker;
- change the TeamPlan;
- send an unlogged message to a peer;
- call a tool outside its assignment;
- read another worker's hidden context;
- mark another worker complete;
- approve its own output;
- grant authority to a teammate.

The team does not vote on safety or correctness. Agreement between workers is evidence that may be considered by the Verification Framework, not a replacement for deterministic checks or human authority.

## Hardware-aware team scheduling

The team planner separates logical roles from physical execution. It receives a signed, measured HardwareProfile containing:

- GPU count and identity;
- total and available VRAM;
- CPU and RAM capacity;
- model residency and load state;
- context and KV-cache budget;
- permitted parallel slots;
- local storage and scratch capacity;
- measured latency and throughput envelope;
- sandbox resource limits;
- egress and isolation status.

It produces a TeamResourcePlan containing:

- per-worker target capability requirements;
- reserved GPU, CPU, RAM, storage, and time;
- maximum concurrency;
- execution mode: parallel, pipelined, or serial;
- preemption and queue priority;
- model load and unload allowance;
- minimum required verifier and review capacity;
- admission decision and reason.

### Scheduling rules

1. Use parallel workers only when reservations prove that they fit.
2. On one constrained GPU, serialize or pipeline the team rather than pretending that containers provide independent compute.
3. Queue or reduce concurrency before weakening a required check.
4. A smaller model may replace a larger one only if it is qualified for the same role, risk class, and output contract.
5. Hardware pressure may change timing, residency, and model choice within the qualified set. It may not change clearance, autonomy, required evidence, or verification thresholds.
6. The independent verifier cannot be removed silently because of GPU pressure.
7. Background ingestion yields to an interactive or high-consequence team.
8. A team that cannot obtain its minimum safe resources becomes queued, degraded with an explicit review state, or stopped.

The router selects targets for worker assignments. The harness and orchestrator decide whether the team exists, how it is synchronized, and when it is complete.

## Context construction and compaction

Every worker context is built from a bounded packet:

```text
stable policy head
+ TaskEnvelope slice
+ WorkerAssignment
+ selected skills
+ typed evidence references and bounded excerpts
+ prior verified WorkPackets
+ expected output schema
+ current constraints and budget
```

The context builder does not pass the entire transcript or unfiltered corpus. Uploaded and ingested material remains `UntrustedEvidence` and never enters the instruction or policy channel.

When context pressure requires compaction, the harness rebuilds the context from the ledger, current task state, verified WorkPackets, active constraints, and evidence references. It does not trust a model-generated summary as the authoritative state. The compaction event, input manifest, output manifest, and rehydration result are audited.

## Tools, permissions, and lifecycle interceptors

The model emits a structured proposal. The host validates it. The Tool Gateway executes it. The result returns as typed evidence.

Every tool proposal passes:

- hard deny policy;
- worker and task capability scope;
- clearance and taint checks;
- path and object allowlists;
- risk and Autonomy Governor decision;
- resource, timeout, and idempotency checks;
- expected output schema;
- provenance and ledger write requirements.

The harness provides core-owned interceptors:

```text
before_task
before_team_plan
after_team_plan
before_worker_start
before_model_call
after_model_call
before_tool_call
after_tool_call
after_tool_failure
before_context_compaction
after_context_compaction
before_join_barrier
after_join_barrier
before_step_complete
before_team_complete
before_task_complete
after_task_complete
```

These interceptors are not optional project hooks. A document, worker, domain skill, or uploaded repository cannot disable or replace them. A failed safety interceptor blocks or escalates the operation.

## Verification and default-fail completion

The harness creates explicit completion criteria before work starts. They begin false and can be changed only by the relevant deterministic engine or independent evaluator.

Example:

```json
{
  "inspection_findings_extracted": false,
  "sources_attached": false,
  "approval_note_rendered": false,
  "numbers_verified": false,
  "artifact_checked": false,
  "independent_review_complete": false
}
```

The generation workers cannot set these values. The Verification Framework, Deliverable Engine, and review workflow produce the evidence that changes them.

The independent evaluator receives the proposed result, source references, artifacts, and criteria. It receives a fresh context and does not rely on the generation worker's narrative of why the result should pass. If the evaluator cannot run, the result is `needs_review`, not pass.

## Evidence and audit

Every team and worker event is written to the Memory and Audit Ledger with:

- task, team, worker, stage, and parent IDs;
- principal and clearance;
- role and assignment version;
- model target and artifact identity;
- hardware profile and resource lease;
- input and output manifests;
- evidence references with source, confidence, clearance, and taint;
- tool calls and results;
- handoff packet hashes;
- verification and evaluator outcomes;
- policy, pack, and skill versions;
- timestamps, retry, cancellation, and failure reasons.

Worker scratch space and conversation context are not authoritative memory. The ledger and artifact store are authoritative. A successful procedure can be promoted to memory only after the entire team run passes its checks and the required human authority signs it.

## Failure and recovery

The harness handles failures as typed state transitions:

- worker transport failure: retry or route to another qualified target;
- malformed worker result: reject and retry within the step budget;
- tool failure: return typed failure and follow the task policy;
- worker disagreement: preserve both packets and route to verification or review;
- join barrier timeout: cancel dependents or continue only if the plan allows it;
- verifier failure: stop completion and escalate or re-run verification;
- hardware exhaustion: queue, serialize, or stop safely;
- context compaction failure: rebuild from the last committed checkpoint;
- ledger failure: do not commit the transition or execute the next consequential action.

No worker failure may cause the orchestrator to skip a required evidence source, check, or approval.

## Core and domain-pack boundary

The core harness provides:

- TaskEnvelope and TeamPlan contracts;
- worker lifecycle and isolation;
- context building and compaction;
- hardware-aware admission;
- routing requests;
- tool mediation;
- session and ledger events;
- verification orchestration;
- artifact and evidence packaging;
- completion gates and recovery.

The domain pack provides:

- domain task kinds and worker capability requirements;
- field-specific skills and document profiles;
- required evidence and source quality;
- field checks and completion criteria;
- risk and authority mappings;
- decision types and deliverable templates.

The pack cannot select an arbitrary model, grant tools, disable a hook, change the hardware isolation boundary, or mark a result verified.

## First-scope team demonstration

The first deployment should demonstrate one complex task with a bounded team on the measured workstation:

1. The orchestrator creates a TaskEnvelope and TeamPlan.
2. A research or vision worker reads the scanned report through the File Intake Layer.
3. A reasoning worker extracts findings and proposes the approval-note content.
4. A verification worker independently checks sources, findings, and required criteria.
5. A render worker supplies prose and named field bindings to the Deliverable Engine.
6. The Deliverable Engine renders and verifies the Word file.
7. A final review worker checks completeness from a fresh context.

If the workstation cannot run these roles concurrently, the harness must show the same team as a serial virtual team and record the hardware-driven schedule. The demo must expose the worker trace, handoffs, route decisions, resource mode, verification results, and final evidence package.

## Non-goals

The first harness does not attempt:

- unconstrained autonomous agent swarms;
- remote or cloud workers;
- workers with arbitrary host access;
- automatic policy learning from production traces;
- distributed cross-site team execution;
- peer consensus as a substitute for verification;
- a dependency on Claude Code or the Agent SDK.

## What makes the harness successful

The harness succeeds when a complex task can use multiple specialist contexts without losing deterministic control, provenance, clearance, hardware discipline, independent checking, or a complete offline proof of what happened.
