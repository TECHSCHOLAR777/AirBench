# Model Routing Review

## Verdict

The central idea is right: the agent should call a router, not select model names itself. But the description is too coarse to serve as the AirBench routing contract. It conflicts with the existing architecture around orchestration ownership, verification, evidence propagation, and auditability.

The named Gemma 4 models are valid model variants, but that does not mean they are qualified for every AirBench task. A target must be qualified for its exact artifact, runtime, hardware profile, prompt/tool contract, and task kind.

## Ranked findings

### P0 - The request enters the wrong component

The proposed flow is:

`User Query -> Model Router -> Task Classification`

AirBench requires:

`User/UI -> Orchestrator -> validated task step -> Router -> backend -> model`

The orchestrator must first establish authorization, clearance, domain-pack version, task policy, tools, risk, and plan. Routing a raw user request before that allows the router to influence workflow state and authority.

The sharper contract is:

```text
User request
  -> Orchestrator creates TaskEnvelope
  -> Orchestrator validates a bounded Step
  -> Router receives ModelCallRequest
  -> Backend adapter calls one model
  -> Orchestrator verifies the result
```

The router must not receive raw uploaded documents as instructions or decide task control flow.

### P0 - “Fallback if verification fails” crosses ownership boundaries

Model availability and transport failures belong to the router. A failed domain check, unsafe calculation, invalid tool proposal, or failed deliverable check belongs to the orchestrator and Verification Framework.

The router must not decide that an output “failed verification” and silently retry elsewhere. The orchestrator should create a new attempt with:

- the same immutable step snapshot;
- a new call ID and attempt number;
- the failed result preserved as evidence;
- a deterministic fallback policy;
- no repeated side effects.

A weaker model must never silently replace a stronger model after a high-risk failure.

### P0 - The sovereign network boundary is missing

“Local container” is not enough. The router, serving backends, health endpoints, telemetry, registries, and container runtime all need an explicit no-egress design.

The branch needs to specify:

- no default routes or DNS from model/tool containers;
- internal-only service addresses;
- no NGC, Hugging Face, telemetry, or update calls;
- local image/model registry;
- signed model and container bundles;
- startup failure if required assets are missing;
- independently tested egress-denial evidence.

NIM air-gap deployment also requires model assets and caches to be pre-staged before deployment. Credentials and remote model URIs must not be required in the isolated phase.

An API key alone is not a sufficient boundary. The serving endpoints must be network-isolated and authenticated as internal services.

### P0 - “OpenAI-compatible” does not mean backend-equivalent

NIM and vLLM expose compatible APIs, but tool calling, structured output, multimodal inputs, chat templates, cancellation, streaming, and error behavior remain model- and runtime-specific.

Use a backend adapter with a conformance test suite:

```text
Router target
  -> BackendAdapter
      -> request normalization
      -> model-specific tool/parser configuration
      -> structured-output validation
      -> streaming/cancellation normalization
      -> typed error normalization
      -> response provenance
```

The orchestrator must never consume raw vLLM/NIM response formats directly.

### P1 - Routing must happen per step, not once per user task

A single task may contain:

1. scanned-document extraction;
2. knowledge retrieval;
3. calculation;
4. code generation;
5. approval-note drafting;
6. Word rendering;
7. final verification.

One model cannot be “the model for the task.” Routing must happen for each typed step. The route can remain sticky within a stage, but it must be possible to switch capability between stages.

### P1 - The classification input is under-specified

“Task type” is too small. The router needs a typed request containing at least:

- operation: plan, summarize, extract, code, calculate, draft, or classify;
- modality: text, image, scanned PDF, table, audio, or structured data;
- tool requirements;
- context and output limits;
- clearance and evidence taint;
- domain-pack and policy version;
- action risk;
- latency and resource budget;
- required structured-output schema;
- current stage and previous verification status.

The router should use the richer `ModelCallRequest` and `RoutingDecision` contracts in `serving_and_routing.md` rather than introducing a simpler parallel contract.

### P1 - The model mapping conflicts with the current roster

The proposed description maps coding to Gemma 4 31B. The current AirBench roster separately defines Qwen3-Coder-30B-A3B-Instruct for coding and executable calculations.

Coding requires qualification for:

- tool-call syntax;
- repository navigation;
- patch generation;
- sandbox execution;
- test repair;
- dependency restrictions;
- calculation reproducibility.

Gemma 4 may eventually pass those tests, but “large reasoning model” is not evidence that it should handle coding. Either route coding to the qualified coder target or qualify Gemma 4 31B explicitly for coding before registering it for that route.

Qwen2.5-VL is a sensible candidate for scanned documents, but AirBench still needs its own evaluation on industrial inspection reports, local scan quality, tables, handwriting, and page-level extraction.

### P1 - The registry is missing the identity needed for audit

The registry must include:

- exact model artifact digest;
- quantization and precision;
- tokenizer and chat-template version;
- serving runtime and container digest;
- backend adapter version;
- context and image-token limits;
- supported tool-call parser;
- structured-output capabilities;
- allowed task kinds;
- qualification certificate;
- pack and policy compatibility;
- clearance ceiling;
- latency and resource envelope;
- license and redistribution metadata.

“Priority” must not override qualification or risk gates.

### P1 - Health is not the same as routability

A model may be alive but unable to accept a request because of insufficient GPU memory, KV-cache exhaustion, queue saturation, incompatible context length, failed tool-parser configuration, or a restart between health check and inference.

The router needs separate liveness, readiness, capacity, and admission checks. It should reserve resources for the call or return `queued`, `degraded`, or `unavailable`. A health check followed by a later call creates a time-of-check/time-of-use race.

### P1 - The single-GPU deployment claim needs a concrete residency policy

Running Gemma 4 31B, Gemma 4 26B A4B, Qwen2.5-VL, a coder, embeddings, and reranking as separate containers on one mid-range GPU is not automatically feasible.

The design must specify:

- which targets are resident;
- which are unloaded or swapped;
- maximum GPU memory per target;
- model load time;
- admission behavior during swaps;
- background-ingestion throttling;
- whether embeddings and reranking use CPU;
- what happens when two model calls compete for the GPU.

“Independent scaling across Kubernetes nodes” is a later deployment claim, not a consequence of putting services in containers.

### P1 - Logging “the result” can leak sensitive data internally

The router should not indiscriminately log prompts and full model outputs into ordinary service logs. The audit ledger needs:

- request and response hashes;
- encrypted or clearance-filtered evidence references;
- token counts and latency;
- target and artifact identity;
- route policy hash;
- fallback reason;
- backend error class;
- health and admission decision;
- model response provenance.

“Feedback for future routing improvements” must be an offline, approved calibration pipeline. Production traces must not automatically change routing policy.

### P1 - The router’s classifier becomes another qualified model

If task classification uses an LLM, that classifier itself requires:

- a registered target;
- a qualification certificate;
- a schema-validated output;
- a latency and resource budget;
- an uncertainty path;
- a safe default.

It must not receive unbounded raw document text as an instruction channel. If classification is invalid or uncertain, route to the capable target or request clarification; never select the cheap model by default.

### P2 - Embedding, reranking, OCR, and drawing models are not covered

The description says the same approach may later support embeddings, reranking, OCR, and P&ID models, but it does not define whether these are routed through the same API, registered as different model roles, invoked by the orchestrator or retrieval engine, or subject to different contracts.

They need typed roles such as:

- `generator`;
- `vision_reader`;
- `embedding`;
- `reranker`;
- `ocr`;
- `drawing_extractor`.

An embedding model must not be treated as a chat-completion target merely because it appears in one registry.

## Corrected routing lifecycle

```text
1. User submits request
2. Orchestrator authenticates and creates TaskEnvelope
3. Domain pack and policy define permitted work
4. Orchestrator creates and validates one typed step
5. Router applies hard eligibility gates
6. Router selects a qualified target and admits resources
7. Backend adapter calls vLLM or NIM locally
8. Router returns normalized ModelCallResult
9. Orchestrator writes the call and route decision to the ledger
10. Verification checks the result
11. Orchestrator continues, retries, escalates, or stops
```

The router should return a `RoutingDecision` containing:

- eligible target set;
- selected target;
- policy version and hash;
- decision source;
- qualification certificate;
- resource admission result;
- fallback candidates;
- affinity and stage information.

## Minimum acceptance criteria for the routing branch

Before accepting the routing implementation, require:

1. A typed `ModelCallRequest` rather than raw user-query routing.
2. Per-step routing rather than one route per task.
3. Signed, versioned model registry entries.
4. Qualification enforcement before selection.
5. Backend adapters with vLLM/NIM conformance tests.
6. Explicit no-egress deployment and startup checks.
7. Deterministic fallback owned by the orchestrator.
8. Ledger events for route, target, health, admission, response, failure, and fallback.
9. GPU admission and model residency behavior for the single-workstation demo.
10. Separate target roles for generation, coding, vision, embedding, reranking, OCR, and future drawing extraction.

## Final assessment

The strongest part of the proposal is the separation:

`Agent -> Router -> Backend`

The required correction is that the router must be a deterministic, policy-constrained decision service inside the orchestrator’s lifecycle - not a second agent that classifies raw requests, owns verification, or controls fallback state.
