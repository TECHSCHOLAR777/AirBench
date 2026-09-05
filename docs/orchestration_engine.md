# Orchestration Engine

## Purpose

The Orchestration Engine is the boss of the system. It takes a request and drives it to a finished, checked result, deciding what happens in what order, calling the models and tools, and holding all the state. It is the piece that keeps a sometimes unpredictable model on a leash.

## Where it sits

Core engine, and the center of the work flow. It calls Serving and Routing for model work, the Knowledge and Retrieval Engine and World Model Engine for facts, the Verification Framework for checks, the Consistency Engine and Autonomy Governor for judgment and gating, and the Deliverable Engine for output. It writes everything to the Memory and Audit Ledger.

## The core principle

The orchestrator is plain, predictable software, not a model. It owns all control flow and is the only thing that writes shared state. Models are workers that answer one call and never decide what happens next. To be precise, the control flow is repeatable and can be replayed for audit, even though the model outputs themselves are not identical run to run.

More precisely, the orchestrator owns workflow state. Other components may emit typed facts and events through the ledger API, but they do not mutate task state or advance a task. The workflow is an explicit state machine:

`received → authorized → planned → plan_validated → executing → awaiting_check → awaiting_review → rendering → deliverable_verified → complete`

Every transition has a precondition, bounded timeout, idempotency key, and audit event. A restart resumes from the last committed transition. A tool or model response can propose a result; only the orchestrator can commit the next transition.

For a team run, `executing` contains the controlled substates `team_planned`, `team_admitted`, `team_running`, `join_barrier`, and `independent_verification`. These are still orchestrator transitions with the same preconditions, timeouts, idempotency keys, and ledger events. A worker cannot advance one of them.

## How a task runs

1. **Create a bounded plan, then check it.** The engine has a model propose a short ordered list of typed steps, with constraints and an action budget attached, and then validates the plan against the request, available tools, clearance, and domain pack. Forming the initial plan before touching untrusted documents prevents a document from rewriting the initial authority envelope. Replanning is allowed only inside that envelope and is validated by the orchestrator.

2. **Run short, typed, capped steps.** Each step declares its input types, output types, permitted tools, timeout, retry budget, and expected evidence. A step may call a model, search knowledge, query the World Model, or run a tool in the sandbox. The model cannot add a tool, change a clearance, or enlarge the budget.

3. **Check every step from outside.** After each step an external check decides if it passed, using a tool result, a rule, or the Verification Framework, never the model grading itself. Transient failures may retry within the declared budget; deterministic failures produce a typed failure and move the task to retry, review, or stop.

4. **Keep memory and authority outside the model.** The plan, results, facts, and notes live in a store the engine feeds back into each step, giving the model only the slice it needs. Constraints are re-fed every step. Uploaded and ingested text enters the prompt as `UntrustedEvidence`; it is never merged into the instruction or policy channel.

5. **Judge and gate.** Before a decision is finalized, the Consistency Engine checks it against past decisions and the Autonomy Governor decides whether the system may finish alone or must escalate. A model cannot certify the risk of its own proposed action.

## The prompt shape that makes it fast

Each step's prompt is built in three zones so the system stays fast without losing the constraint discipline. A stable head that does not change, the instructions, the tool definitions, and the standing constraints. A middle that rarely changes, the plan. And a changing tail, this step's retrieved facts and this step's specific constraints. Because the head stays identical, the hardware can reuse its prior work on it, which sharply cuts the time to the first token, while the changing constraints ride in the tail. This is a rule about how prompts are assembled, not an optional trick.

## How it handles the real world

The engine treats the model tier as a shared, limited resource. It never fires unbounded parallel model calls, it queues with priority so a person waiting on a screen jumps ahead of a background job, and it puts a timeout and a circuit breaker on every external call so one hung dependency cannot hang the task. When a service like the drawing pipeline is unavailable, the task degrades and says so rather than crashing. Task state is checkpointed at every step, so a crash resumes from the last good step instead of starting over.

## Interfaces

Task state is checkpointed at every committed transition. A restart resumes from that transition rather than repeating the whole run, and any file-writing or knowledge-promotion action carries an idempotency key. Optional extractors may be unavailable; the orchestrator records the degradation and continues only when the task policy allows it.

Input: a request with the user's clearance.

Output: a finished, checked result, plus a full trace of every transition, model call, tool action, retrieved evidence set, check, route, and review event in the Memory and Audit Ledger. It calls out to the other engines through their stable interfaces and treats each as replaceable.

## Failure handling

A step that fails its check follows its declared retry and escalation policy. A plan that fails validation is reformed within the same task policy; repeated failure stops the task with a review reason. A tool result that came from an untrusted document is treated as data, never as an instruction. Nothing is finalized without passing the gates.

## What is core and what is pack

Core: the entire control loop, the planning, the step execution, the external check wiring, the memory handling, the queuing and resilience.

Pack: nothing directly. The orchestrator reads the pack indirectly, through the checks, the risk model, and the decision types that the other engines apply.

## The harness supervisor and worker teams

The Orchestration Engine is also the supervisor of the AirBench Harness. It may run a step with one worker or form a bounded worker team for a complex task. The choice is made from task complexity, modality, risk, required independent checks, and the measured hardware profile.

The team is a plan, not a society of autonomous agents. The orchestrator owns the TeamPlan, worker identities, dependencies, barriers, leases, handoffs, retries, cancellation, and completion. Workers are stateless model calls with isolated contexts. They cannot spawn peers, advance workflow state, grant authority, or write uncontrolled shared state.

The initial worker capability interfaces are `lead_worker`, `research_worker`, `vision_worker`, `reasoning_worker`, `code_worker`, `verification_worker`, `render_worker`, and `review_worker`. A task uses only the roles its stages require. A model may fill more than one role only when it has been qualified separately for each role.

## How a complex team runs

1. The orchestrator creates the immutable `TaskEnvelope` and proposes a bounded TeamPlan.
2. It validates the team roles, dependencies, evidence scope, tools, autonomy ceiling, completion criteria, and resource budget.
3. Serving and Routing admits a qualified target and a hardware lease for each worker assignment.
4. The lead or reasoning worker proposes typed work, while research, vision, code, or other specialists produce independent WorkPackets.
5. The orchestrator joins the packets at explicit barriers and records unresolved disagreement instead of letting workers resolve authority by consensus.
6. An independent verification worker checks the proposed result from a fresh context. It does not inherit the generator's private reasoning narrative.
7. The render worker supplies prose and named field bindings. The Deliverable Engine owns layout, formulas, numbers, and rendering.
8. A review stage checks the artifact and completion criteria. Only the orchestrator may commit the next state transition.

Every WorkPacket carries source, confidence, clearance, and taint for its facts. A packet is evidence or a proposal, never a permission.

## Hardware-aware execution

The orchestrator asks Serving and Routing for a TeamResourcePlan before starting a team. The plan states whether workers run in parallel, in a pipeline, or as a serial virtual team. A one-GPU machine may therefore run several isolated worker contexts one after another while retaining the same logical team and audit trace.

The scheduler may queue background work, serialize roles, use a smaller qualified target, or stop with a review reason when resources are insufficient. It may not silently remove an independent verifier, lower a verification threshold, expand a timeout without recording it, or route a high-risk role to an unqualified target. Hardware changes schedule and capacity, not authority.

## Harness lifecycle interceptors

The orchestrator runs core-owned interceptors around task, team, worker, model, tool, compaction, barrier, verification, and completion events. A failed interceptor blocks or escalates the operation. Uploaded documents, worker prompts, domain skills, and project-local files cannot disable these interceptors.

Context compaction is a state rebuild, not a trusted model summary. The orchestrator reconstructs worker context from the last committed transition, verified WorkPackets, active constraints, evidence references, and the current budget. The compaction input and output manifests are written to the ledger.

## Team-specific failure handling

Worker transport failure, malformed output, tool failure, barrier timeout, disagreement, verifier failure, and resource exhaustion each produce typed events. The orchestrator can retry or reroute only within the declared policy. If the independent verifier cannot run, the task becomes `needs_review` or stops; it does not complete by majority vote or by trusting the generator.

The complete harness contract, including TaskEnvelope, TeamPlan, WorkPacket, hardware modes, lifecycle interceptors, and default-fail completion, is specified in `airbench_harness.md`.
