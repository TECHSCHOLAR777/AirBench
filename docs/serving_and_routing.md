# Serving and Routing

## Purpose

This layer runs the models on the hardware and decides which model handles each task. It is what lets one machine behave like a team of specialists while staying within a fixed amount of memory.

## Where it sits

Core engine. It is called by the Orchestration Engine for every model call. Which models exist and what each is qualified for is governed by the Model Qualification Framework. It runs on the deployment described in `deployment_and_scale.md`.

## The router

The router is a deterministic policy engine with an optional local classifier. It never chooses from the whole model pool blindly. First it applies hard eligibility gates for modality, task kind, tool requirements, context window, clearance, pack version, hardware capacity, and current qualification. Only then may a routing policy choose among eligible targets.

The routing contract is deliberately provider-neutral. It separates:

- **client:** the local request protocol and model-call contract;
- **target:** one model artifact, serving endpoint, quantization, and capability certificate; and
- **route:** a client-visible policy that selects one eligible target.

This separation is one of the useful ideas in NVIDIA NeMo Switchyard. AirBench will use the shape of that idea without depending on a hosted provider or allowing an external inference path. The router's output is a typed `RoutingDecision`, not a model instruction.

### AirBench routing policy

1. **Hard route first.** Images and scanned pages require a qualified vision target. Code-generation steps require a qualified coder. Calculation steps require the coder plus the execution tool. High-risk or ambiguous work is not eligible for the fast lane.
2. **Capability route second.** For eligible text targets, a small local classifier may estimate whether an efficient target can solve the whole step. Its output is schema-validated and includes `p_solve`, `capability_boundary`, `primary_rule`, and `crux`. Invalid, missing, or inconsistent output selects the safer capable target.
3. **Stage route during agent work.** Once tool-result history exists, routing may use deterministic progress signals: exploration, error severity, spinning, recent production, test results, and context pressure. Exploratory, uncertain, and recovery turns go to the capable target; settled mechanical turns may use the efficient target.
4. **Quality-first default.** The first AirBench policy uses the capable target as the default for unknown or ambiguous turns. A later cost-first policy may use the efficient target by default only after calibration on the organization's evaluation set.
5. **Escalation is sticky for the task.** If a step is escalated after a failed check, later turns in that task retain the capable route unless the orchestrator explicitly starts a new qualified stage. The router never silently degrades a failed high-risk step to a weaker model.

The stage-router design is especially useful for AirBench because it uses signals already produced by the deterministic agent loop rather than adding a classifier call to every tool continuation. NVIDIA's published design uses corroborating progress/error signals, a critical-error override, explicit thresholds, handoff notes, context-window fallback, and a recorded decision source. AirBench adopts those concepts but recalibrates them on industrial document and coding tasks; thresholds from coding benchmarks are not reused.

The prefill-router pattern used in NVIDIA's recent Nemotron/NemoClaw work is also a useful candidate for later local experiments: a lightweight encoder predicts which registered model can meet an accuracy target, and a tolerance controls the quality-versus-cost tradeoff. In AirBench, that tolerance becomes a domain risk budget rather than a monetary setting. It cannot override qualification, clearance, or autonomy gates. It remains an optional policy until measured locally.

Session affinity is keyed only by the orchestrator's opaque task ID. Message-hash affinity is not used because identical opening text from different users must not share routing state or cache state.

## The serving tier

Models run as separate local services on the machine. The first scope needs only the qualified reasoner, efficient text target, coder, vision/OCR target, and embeddings service; reranking may be a CPU or small local service. The drawing service is not part of the current build and will be registered later through its typed adapter. Keeping model servers separate means a fault in one does not take down the others.

On a single large card the models share the memory as a managed pool with hard per model limits, not as fixed hardware slabs, because fixed slabs would strand memory for small models and starve the big one. Models that are needed often stay resident. Models that are needed rarely are parked in a sleep state that wakes in a second or two, far faster than loading from cold. The rule for staying resident is simple: a model earns permanent memory only if it is called often enough to justify it, and rare models live in the sleep slot.

## Handling a fixed amount of hardware

The machine has a fixed budget, so the only elastic resource is what the system chooses not to run at a given moment. The engine keeps a live budget of memory and compute and admits work against it. Under pressure it pauses background ingestion before an interactive task. It may select another qualified target only if that target remains inside the step's quality and risk envelope; it may not trade safety for availability. Precision is part of the target identity and therefore part of qualification.

## Scaling beyond one card

When one machine is not enough, models are replicated whole across cards or nodes behind the router, never split across cards, because the link between cards is too slow to split a model efficiently. The stateless parts, the agent workers and retrieval, scale out horizontally. The stores stay as carefully backed single points or small clusters. The model roster is curated so everything the organization needs fits on one card, which keeps this simple.

## Interfaces

Input: a model call from the orchestrator, carrying the task kind, modality, tool requirements, evidence summary, task ID, clearance, pack version, action risk, and resource budget.

Output: the model's answer plus a `RoutingDecision` containing the eligible-target set, selected target, route policy/version hash, decision source, threshold or hard rule, qualification certificate, session affinity, fallback, and resource admission result. The decision is written to the ledger before the model response is returned.

## Failure handling

If a chosen model is unavailable, the router selects another target only from the already-qualified eligible set or queues. A classifier failure, malformed verdict, context overflow, or missing capability certificate selects the capable target or stops the step. A model that repeatedly fails checks on a task kind is removed from that route and sent for requalification. Tool calls use small stable schemas, and the orchestrator validates them again before execution.

## What is core and what is pack

Core: the router, provider-neutral request types, hard eligibility gates, capability and stage routing policies, serving tier, memory pool management, budget and admission logic, route telemetry, and scaling model.

Pack: nothing directly. The pack influences routing only through the set of qualified models and their qualified task kinds.

Routing research references: NVIDIA NeMo Switchyard's [core concepts](https://github.com/NVIDIA-NeMo/Switchyard/blob/main/docs/core_concepts.md), [LLM-classifier routing](https://github.com/NVIDIA-NeMo/Switchyard/blob/main/docs/routing_algorithms/llm_classifier_routing.md), and [stage-router routing](https://github.com/NVIDIA-NeMo/Switchyard/blob/main/docs/routing_algorithms/stage_router_routing.md). NVIDIA's [NeMoClaw router documentation](https://github.com/NVIDIA/NemoClaw) is the reference for the optional local prefill-router experiment; its hosted-provider path is not suitable for AirBench's sovereignty boundary.
