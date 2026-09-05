# AirBench Architecture Design

## What AirBench is

AirBench is a sovereign AI worker that a sensitive organization runs entirely inside its own walls. Nothing it touches leaves the building. It reads the organization's own messy documents, builds a structured picture of that organization's world, plans and carries out real multi step work, checks its own output against the rules of the field, decides how much to do on its own based on how risky the task is, and records and can prove every step it took.

It is not a chat box with private hosting. It is a system that can own a complete, sensitive, accountable task end to end and hand back a finished, checkable deliverable.

## What we are concretely building first

The first build is a single-node, local vertical slice rather than the full fleet product. It must demonstrate:

- a user request becoming a bounded, checkpointed task;
- a scanned inspection report becoming sourced structured evidence and a draft approval note;
- a coding request being routed to a qualified coding model and executed in a no-network sandbox;
- local document retrieval and one meaningful, linked World Model query;
- model selection across at least two task kinds, with the route and reason recorded;
- a verified Word deliverable with computed values supplied by the system; and
- an offline-visible execution and audit trace.

The drawing pipeline is intentionally not implemented in this scope. Its future adapter is reserved, but the rest of the system must treat it as an optional typed graph-fragment producer rather than inventing drawing behavior in the core.

The full-hardened requirements deliberately deferred from this first scope are recorded in `future_full_fledged_must_have.md`.

## The one idea the whole system is built on

There are two layers, and keeping them apart is the most important decision in the entire design.

The **core engine** is identical for every customer in every industry. It knows nothing about oil, medicine, banking, or law. It knows how to run models safely, plan work, build a world model from documents, check work against supplied rules, decide autonomy by risk, remember things provably, and prove sovereignty.

The **domain pack** is the only part that changes per sector. It teaches the core engine a particular field: what the important documents are, what the world is made of, what the rules are, what a finished deliverable looks like, and what counts as a serious action.

A new industry is a new pack, never a rebuilt engine. If a sector assumption ever leaks into the core, the platform quietly collapses back into a single sector tool. Guarding that boundary is a standing rule, not a preference. The pack contract is specified in `domain_pack_framework.md`.

## The parts, and where each is documented

Every part below is a working component with its own responsibilities, interfaces, and failure behavior. Each has its own spec.

Core engines and frameworks:

- **World Model Engine** (`world_model_engine.md`) builds and serves the structured, queryable picture of the organization's world from its own records.
- **File Intake Layer** (`file_intake_layer.md`) is the one shared layer that parses every file type. Both bulk ingestion and files uploaded during a query go through it, so file handling can never drift apart between the two.
- **Knowledge and Retrieval Engine** (`knowledge_and_retrieval_engine.md`) indexes documents on top of the intake layer and answers questions from them with sources.
- **Reference Model Roster** (`models.md`) pins the actual models chosen and the jobs each is qualified for.
- **Orchestration Engine** (`orchestration_engine.md`) is the deterministic controller that runs the agent loop, plans work, executes checked steps, and holds all state.
- **Serving and Routing** (`serving_and_routing.md`) hosts the models on the hardware and sends each task to the right one.
- **Verification Framework** (`verification_framework.md`) checks that an answer is valid by the rules of the field, not just well written.
- **Consistency Engine** (`consistency_engine.md`) keeps the organization's decisions consistent over time and flags unjustified deviations.
- **Autonomy Governor** (`autonomy_governor.md`) decides how much the system may do on its own for each action, based on harm, reversibility, and confidence.
- **Model Qualification Framework** (`model_qualification_framework.md`) tests and clears a model for a specific job before it is allowed to do that job.
- **Memory and Audit Ledger** (`memory_and_audit_ledger.md`) is the append only, signed record of everything the system knows and did.
- **Sovereignty and Security** (`sovereignty_and_security.md`) enforces and proves that no data leaves, and defends against poisoning and misuse.
- **Deliverable Engine** (`deliverable_engine.md`) turns verified facts into finished Word, Excel, and slide outputs.
- **Deployment and Scale** (`deployment_and_scale.md`) covers how AirBench is installed, updated, and run on fixed hardware and across sites.

External input specified separately:

- The **Engineering Drawing Pipeline** is one source that feeds the World Model Engine. It is owned and documented outside this set. The rest of the architecture treats it as a producer of structured graph fragments with confidence scores, and nothing here depends on how it works internally.

## How the parts fit together

There are two flows.

The **ingest flow** fills the system's knowledge. Documents come in, the Knowledge Engine parses and indexes them, the World Model Engine turns the authoritative ones into a structured model of the world, and both write into the stores through the Memory and Audit Ledger so every fact carries its source and its clearance.

The **work flow** answers a request. A user asks for something. Clearance is checked. The Orchestration Engine plans the task, then runs it in short steps, calling models through Serving and Routing, pulling facts through the Knowledge and Retrieval Engine and the World Model Engine, and running domain checks through the Verification Framework. The Consistency Engine checks the decision against past decisions. The Autonomy Governor decides whether the system may finish alone or must escalate. The Deliverable Engine produces the file. A human reviews the result. Every step is written to the Memory and Audit Ledger, and the Sovereignty layer records local execution evidence.

In the first scope, “human signs off” means that a person can inspect the verified draft and trace; a full identity-bound approval workflow is deferred. No draft is presented as an approved organizational decision merely because the first-scope review screen was passed.

## The three things that must hold across every part

These are properties of the whole system, not features of any one component. If any part violates one, that part is wrong.

1. **Authority is deterministic, intelligence is not.** The orchestrator is plain, predictable software and it owns all control and all state. Models are workers that answer one call at a time and never drive the loop.

2. **Confidence, source, and clearance travel with every fact.** They are attached when a fact is created and are never dropped at a boundary. A low confidence fact stays labeled all the way into the final document. A user never sees a fact above their clearance.

3. **Everything is provable after the fact.** Every model call, tool call, decision, and human approval is written to an append only, signed record that can be replayed and independently checked, offline, by someone who trusts neither the vendor nor a network.

The first implementation makes these properties concrete with four shared contracts:

- `FactEnvelope` for sourced, confidence-bearing, clearance-labelled facts and derived values;
- `UntrustedEvidence` for uploaded or ingested content that models may inspect but that can never become an instruction or permission;
- `ToolAction` and `TaskPolicy` for schema-validated, orchestrator-authorized tool use; and
- immutable ledger events plus rebuildable projections for state, search, and graph views.

`FactEnvelope` carries a fact ID, typed value and unit, source document/version and exact span or region where available, extraction method, trust class, calibrated confidence, clearance, valid/observed/ingested times, parent fact IDs, and supersession status. Derived values retain the complete parent chain. A boundary may narrow visibility or confidence, but may not drop provenance metadata.

## The request lifecycle, end to end

1. A request arrives and the user's clearance is resolved.
2. The Orchestration Engine forms a plan and checks the plan is sane before running anything.
3. It converts the plan into a bounded state-machine run. Each step may call a qualified model, search the Knowledge Engine, query the World Model, or run a tool in the sandbox, but a model output cannot advance state by itself.
4. Each step is checked by an external check, never by the model judging itself. Facts are validated by the Verification Framework against the domain pack's rules.
5. For any decision, the Consistency Engine surfaces relevant past decisions and flags an unjustified deviation.
6. The Autonomy Governor scores the action's risk and either allows the system to proceed alone or routes it to the required level of human authority.
7. The Deliverable Engine assembles the output from verified facts, where the model writes the words and the system owns the numbers.
8. A person reviews the verified draft in the first scope. The complete electronic sign-off workflow is deferred; if a sign-off exists, it is still recorded as a ledger event.
9. The Sovereignty layer has been proving zero egress throughout, and the whole run sits in the audit ledger for later review.

## What makes it different, in one line

Everyone can now run a private model with search and agents. AirBench is the layer that makes that private system actually own a sensitive, regulated task, check its own work against the field's rules, know when to stop and ask, and prove everything it did, and it fits a new industry by loading a new pack rather than being rebuilt.
