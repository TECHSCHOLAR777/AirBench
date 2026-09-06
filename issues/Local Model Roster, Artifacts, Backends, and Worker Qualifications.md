# Freeze v0 Local Model Roster, Artifacts, Backends, and Worker Qualifications

## Issue type

M5 model-serving and qualification issue: freeze the exact local model targets, artifact identities, quantization, serving runtime, backend adapters, and qualified worker roles for the first AirBench deployment.

## Objective

Freeze a reproducible, local-only model bundle for the first AirBench refinery/PSU inspection-report vertical slice.

Every model must be pinned to an exact artifact and qualified for an exact role, task kind, risk class, hardware profile, input modality, output contract, and serving backend before the router can use it.

The deployment must run without cloud APIs, remote credentials, Hugging Face access, NVIDIA NGC access, telemetry, background updates, or any other external network dependency.

## Reference hardware

The primary qualification target is the hardware profile defined by the hardware-aware scheduling issue:

```text
GPU count: 1
GPU memory: 96 GB VRAM
Execution: local-only and air-gapped
Primary workload: refinery/PSU inspection-report review and approval-note preparation
```

All measurements must reference a signed `HardwareProfile` ID. A model that is qualified on another machine or configuration is not automatically qualified for the 96 GB deployment.

The roster must support both:

- a large-profile path using Gemma 4 31B Q4 where measured capacity permits it;
- a practical workstation path using the measured 4-bit Gemma 4 26B A4B target.

The smaller target is a qualified fallback, not an implicit quality downgrade. Its use, reason, hardware profile, and qualification certificate must be recorded in the routing and audit trace.

## Initial model targets

The following targets are the initial roster. Exact repository commits, artifact hashes, runtime versions, and qualification results must be filled from the frozen local bundle before the issue is closed.

| Capability | Initial target | Required role | Initial quantization direction |
|---|---|---|---|
| Lead and high-quality reasoning | Gemma 4 31B instruction-tuned target | lead worker, high-quality reasoning worker | Q4 on a qualified large profile |
| Practical lead and fast lane | Gemma 4 26B A4B instruction-tuned target | workstation lead, reasoning fallback | measured 4-bit target |
| Coding and executable calculations | Qwen3-Coder-30B-A3B-Instruct | code worker | qualified 4-bit target when BF16 does not fit |
| Scanned reports and images | Qwen2.5-VL-7B-Instruct | vision/evidence worker | qualified 4-bit target when BF16 does not fit |
| Retrieval embeddings | BAAI/bge-m3 | embedding service | CPU or small local service where admission improves |
| Retrieval reranking | BAAI/bge-reranker-v2-m3 | reranking service | CPU or small local service where admission improves |

These are target identities, not qualification grants. Each row requires independent qualification for the actual task and backend combination.

## Required artifact pinning

Create a signed model-roster manifest at:

```text
models/roster/v0/model_roster.yaml
```

For every target, record:

- logical target ID;
- model family and display name;
- exact repository and namespace;
- exact repository commit or immutable revision digest;
- local artifact directory or bundle ID;
- local storage content hash;
- model weight file hashes;
- tokenizer files and hashes;
- tokenizer version;
- chat template ID and content hash;
- processor/image-preprocessor version and hash where applicable;
- quantization format, method, and calibration artifact hash;
- precision mode, including BF16 or 4-bit;
- container/image digest;
- serving runtime and exact version;
- backend adapter ID and version;
- hardware profile IDs tested;
- context-window limit;
- maximum output-token limit;
- image dimensions and image-token limit where applicable;
- maximum tested batch size and concurrency;
- tool-call parser ID and version;
- structured-output schema mode;
- streaming behavior;
- cancellation behavior;
- license and usage restrictions;
- source and supply-chain evidence;
- qualification certificate IDs;
- signer key ID, manifest hash, and signature.

No target may be referenced by a mutable tag such as `latest`, an unpinned branch, an unverified container tag, or an unrecorded local directory.

## Proposed manifest shape

The roster manifest must be schema-validated and signed. It should contain a structure equivalent to:

```yaml
roster:
  roster_id: airbench-model-roster-v0
  schema_version: "1.0"
  created_at: timestamp
  hardware_profiles:
    - target_96gb_vram
  serving_defaults:
    runtime: pinned-runtime-id
    backend: vllm
    network_policy: air_gapped_no_egress
  targets:
    - target_id: gemma4-31b-it-q4
      repository: exact/repository
      revision: immutable-commit-or-digest
      artifact_hash: sha256:...
      tokenizer:
        repository: exact/tokenizer-source
        revision: immutable-commit-or-digest
        hash: sha256:...
      chat_template_hash: sha256:...
      quantization:
        format: INT4_AWQ
        artifact_hash: sha256:...
      serving:
        container_digest: sha256:...
        runtime: vllm
        runtime_version: exact-version
        adapter_id: exact-adapter
        adapter_version: exact-version
      limits:
        context_tokens: integer
        max_output_tokens: integer
        image_tokens: null
        max_concurrency: integer
      qualified_roles:
        - role: lead_worker
          certificate_id: certificate-id
          qualification_hash: sha256:...
      license: license-id
      signature: signature
```

The implementation may use JSON, YAML, or a typed Python representation internally, but the signed exported manifest must be deterministic and independently verifiable offline.

## Role-specific qualification

A model is qualified only for the exact role and contract it passed. Qualification must not be inferred from model size, general capability, or a successful health check.

At minimum, qualify these worker/service combinations:

### Gemma 4 31B instruction-tuned target

Potential qualification scopes:

- lead planning;
- high-quality evidence synthesis;
- approval-note prose proposal;
- reasoning over retrieved evidence.

It must not automatically receive coding-worker or verifier qualification.

### Gemma 4 26B A4B instruction-tuned target

Potential qualification scopes:

- workstation lead;
- reasoning fast lane;
- approval-note prose proposal;
- bounded evidence synthesis.

Its qualification must state the quality and latency envelope relative to the large-profile target. It cannot silently replace the 31B target when a task requires the higher-qualified target.

### Qwen3-Coder-30B-A3B-Instruct

Potential qualification scopes:

- code generation for deterministic calculations;
- code repair within the sandbox;
- executable test generation;
- structured coding output.

The coding target must be tested through the actual Tool Gateway and no-network sandbox. It must not receive final approval authority.

### Qwen2.5-VL-7B-Instruct

Potential qualification scopes:

- scanned-page interpretation;
- OCR-assisted evidence extraction;
- inspection photographs;
- handwriting and visual-region interpretation.

It must be evaluated on the actual local inspection-report fixtures, including scans, tables, photographs, page coordinates, and low-quality text. It is not qualified for engineering drawing topology extraction.

### BAAI/bge-m3

Qualify for:

- local embedding generation;
- exact embedding dimension and normalization behavior;
- deterministic index compatibility;
- CPU or dedicated local-service execution.

### BAAI/bge-reranker-v2-m3

Qualify for:

- local retrieval reranking;
- deterministic input/output schema;
- CPU or dedicated local-service execution;
- clearance-filtered retrieval compatibility.

## Qualification certificate

Create or extend the model qualification contract at:

```text
contracts/model_qualification.schema.yaml
qualifications/model_qualification_matrix.yaml
```

Each qualification certificate must include:

- certificate ID;
- target ID and exact artifact hash;
- tokenizer and chat-template hashes;
- runtime, container, and adapter versions;
- hardware profile ID;
- exact worker role;
- task kind and risk class;
- modality;
- input fixture set;
- output schema;
- tool permissions, if any;
- context and image-token limits;
- benchmark scores and failure results;
- structured-output pass rate;
- tool-call pass rate;
- citation/provenance retention result;
- cancellation and timeout result;
- safety/injection-resistance result;
- no-egress startup result;
- evaluator identity and qualification date;
- expiry or requalification trigger;
- signer key ID and signature.

Qualification must be role-specific. For example:

```text
qualified(gemma4-31b, lead_worker) != qualified(gemma4-31b, verification_worker)
```

The verifier qualification must be independently evaluated, even if the verifier uses the same model family as a generator.

## Backend matrix

Create:

```text
benchmarks/backend_compatibility_matrix.yaml
```

Test each target through the selected vLLM adapter. Test NVIDIA NIM only where the model and runtime officially support the target and the complete bundle can be installed and started offline.

The matrix must record, per target/backend/runtime combination:

- startup and shutdown;
- readiness and health;
- local model loading;
- exact artifact identity observed at runtime;
- structured request acceptance;
- structured output validity;
- tool-call schema validity;
- tool-call refusal for unauthorized tools;
- streaming chunks and final response;
- cancellation and timeout;
- malformed request behavior;
- context overflow behavior;
- image/multimodal request behavior;
- concurrency behavior;
- resource-limit behavior;
- error mapping;
- retry safety and idempotency;
- no-egress startup;
- no Hugging Face, NGC, telemetry, update, or remote-credential calls;
- ledger event compatibility;
- pass/fail and known limitations.

OpenAI-compatible HTTP is only a transport compatibility signal. It is not evidence of semantic compatibility with AirBench tool schemas, structured outputs, streaming, cancellation, provenance, or safety behavior.

## Quantization matrix

Create:

```text
benchmarks/quantization_matrix.yaml
```

For Gemma 4 31B, test Q4 on the large profile where capacity permits.

For Gemma 4 26B A4B, test and freeze the measured 4-bit target for the practical 96 GB workstation path.

For the coder and vision targets, test BF16 where it fits and a qualified 4-bit artifact where full precision does not fit.

For each precision/quantization variant, record:

- artifact identity and hash;
- peak VRAM;
- context and KV-cache capacity;
- load time;
- throughput and latency;
- task-quality evaluation;
- structured-output and tool-call results;
- vision/image-token result where applicable;
- failure modes;
- supported hardware profile;
- qualification decision.

Quantization is not an automatic fallback. A 4-bit target may be selected only after it passes the same role, risk, modality, and output-contract qualification required by the task.

## Router contract

The router must receive a fully authorized `ModelCallRequest` from the orchestrator. It must not select a model directly from a raw user request.

Hard eligibility gates must include:

- task kind;
- worker role;
- modality;
- tool requirements;
- structured-output requirements;
- context and image-token limits;
- clearance;
- domain-pack version;
- risk class;
- hardware profile and current reservations;
- exact target qualification;
- backend compatibility;
- model and container artifact integrity;
- local-only network policy.

The router must emit a `RoutingDecision` containing:

- task, team, worker, and stage IDs;
- eligible target set;
- selected target;
- exact artifact and container hashes;
- qualification certificate;
- hardware profile and resource lease;
- route policy/version hash;
- selection reason;
- fallback candidates;
- session affinity;
- attempt number;
- audit event ID.

Each worker assignment is routed independently. A document/vision worker may select Qwen2.5-VL while a coding worker selects Qwen3-Coder and a lead selects one of the qualified Gemma targets.

## Fallback rules

A fallback is valid only when it preserves:

- the same task step;
- the same worker role or an explicitly compatible role;
- the same evidence scope and clearance;
- the same risk class;
- the same output schema;
- the same verification threshold;
- the same provenance and taint requirements;
- the same audit trail.

Examples of valid behavior:

- Gemma 4 31B unavailable: queue, or use the qualified Gemma 4 26B fast lane if the task policy permits it and the route records the substitution.
- Vision target unavailable: queue or stop the evidence stage; do not replace it with an unqualified text-only model for scanned-page interpretation.
- Coder unavailable: queue or stop the executable-calculation step; do not route code generation to a reasoning target without coding qualification.
- Verifier target unavailable: enter `needs_review` or stop; never complete by trusting the generator.

Examples of invalid behavior:

- selecting an unqualified model because it is loaded;
- lowering verification thresholds to make a target pass;
- skipping the verifier because of VRAM pressure;
- changing the task risk class to enable a fallback;
- accepting a free-form answer where structured output is required;
- replacing a vision step with unsupported OCR assumptions;
- allowing a backend to download missing weights at startup.

## Air-gapped startup and supply-chain requirements

The complete model and backend bundle must start in an isolated environment without:

- Hugging Face access;
- NVIDIA NGC access;
- package-index access;
- remote credential validation;
- telemetry;
- crash-report uploads;
- update checks;
- external DNS resolution;
- external model or tokenizer downloads.

The startup test must begin with network access unavailable, not merely with an unused API key. Missing artifacts, invalid hashes, invalid signatures, unsupported runtime versions, or missing tokenizer/chat-template files must cause a clear local startup failure.

Record:

- startup command and configuration hash;
- environment and image identity;
- local asset manifest;
- process/model identities;
- network/isolation policy;
- attempted external destinations, if any;
- denied-egress evidence;
- readiness result;
- ledger event IDs.

## Local storage and bundle layout

The frozen offline bundle should have a deterministic structure equivalent to:

```text
bundle/
  manifest.yaml
  signatures/
  models/
    gemma4-31b-it-q4/
    gemma4-26b-a4b-4bit/
    qwen3-coder-30b-a3b-4bit/
    qwen2.5-vl-7b-4bit/
    bge-m3/
    bge-reranker-v2-m3/
  tokenizers/
  processors/
  runtimes/
  containers/
  adapters/
  qualifications/
  benchmarks/
  sbom/
```

Every directory and file needed for offline startup must appear in the signed manifest or in a signed referenced manifest. The deployment must verify the local storage hash before loading a target.

## Acceptance scenarios

### Scenario A: inspection-report team

Run the refinery/PSU inspection task with:

- vision/evidence worker using the qualified Qwen2.5-VL target;
- lead/reasoning worker using the qualified Gemma target selected by hardware admission;
- coding worker using the qualified Qwen3-Coder target for deterministic calculations;
- independent verifier using a separately qualified verifier target;
- render/review stage using the qualified output path.

Record all route decisions, model identities, artifact hashes, resource leases, worker handoffs, verification results, and final artifact references.

### Scenario B: coding companion

Route a coding or executable-calculation request to Qwen3-Coder. Execute the result only in the restricted no-network sandbox. Verify tests, output schema, resource limits, and provenance before promoting it to evidence.

### Scenario C: vision evidence

Route scanned pages, photographs, and handwriting fixtures to Qwen2.5-VL. Confirm page-level evidence, coordinates or regions where available, confidence, and source references.

### Scenario D: constrained fallback

Make the primary target unavailable or over budget. Confirm that the router queues, selects an already-qualified fallback, or stops. Confirm that the task step, verification threshold, provenance, and audit trail remain unchanged.

### Scenario E: verifier unavailable

Make the independent verifier unavailable. Confirm the result is `needs_review` or stopped and is never marked complete.

## Acceptance matrix

Create:

```text
acceptance/model_roster_matrix.yaml
```

The matrix must map each requirement to a test, an observable result, an artifact, and a ledger event.

| Requirement | Observable result | Ledger evidence |
|---|---|---|
| Exact target selection | Signed roster contains immutable model/artifact identities | `model.registry.loaded` |
| Role-specific qualification | Each worker role has its own certificate | `model.qualification.checked` |
| 96 GB deployment support | Targets benchmarked against signed 96 GB profile | `hardware.profile.referenced` |
| Quantization decision | BF16/4-bit results and selected variants recorded | `model.variant.qualified` |
| Backend compatibility | vLLM matrix passes required semantics | `backend.compatibility.completed` |
| Optional NIM support | NIM tested only where supported and offline-capable | `backend.nim.checked` |
| Tool calling | Valid and unauthorized tool-call behavior recorded | `model.tool_call.tested` |
| Structured output | Required schemas pass validation | `model.structured_output.tested` |
| Multimodal input | Vision fixtures pass through local target | `model.multimodal.tested` |
| Streaming/cancellation | Stream and cancellation semantics are verified | `model.lifecycle.tested` |
| Independent routing | Each worker assignment receives its own route decision | `routing.decision` |
| Safe fallback | Fallback preserves role, risk, provenance, and audit | `routing.fallback.selected` |
| Air-gapped startup | Bundle starts without remote calls or credentials | `backend.airgap_startup.checked` |
| Supply-chain integrity | Hashes/signatures match local assets | `artifact.integrity.verified` |
| No verifier bypass | Missing verifier blocks completion | `completion.blocked` |

## Required ledger events

At minimum, emit immutable events for:

```text
model.registry.loaded
model.registry.signature.verified
model.artifact.integrity.verified
model.qualification.checked
model.variant.qualified
backend.compatibility.started
backend.compatibility.completed
backend.airgap_startup.checked
model.loaded
model.resident
model.evicted
model.unloaded
model.call.started
model.call.completed
model.call.failed
model.tool_call.tested
model.structured_output.tested
model.multimodal.tested
model.lifecycle.tested
routing.decision
routing.fallback.selected
routing.queued
verification.reservation.confirmed
completion.blocked
completion.ready
```

Each event must include target ID, exact artifact hash, runtime/backend identity, qualification ID, hardware profile ID, task/team/worker IDs, policy and pack versions, input/output manifest hashes, timestamps, attempt number, and previous/event hashes.

## Required tests

### Manifest and supply chain

- Mutable model tag is rejected.
- Missing or mismatched model hash is rejected.
- Missing tokenizer or chat template is rejected.
- Invalid container/runtime hash is rejected.
- Invalid signature is rejected.
- Local storage tampering is detected.
- Offline bundle inventory is complete.

### Qualification

- Reasoning qualification does not imply coding qualification.
- Coding qualification does not imply verifier qualification.
- Vision qualification does not imply engineering-drawing qualification.
- Qualification is tied to hardware, runtime, backend, artifact, role, and risk class.
- Expired or superseded certificates are rejected.

### Backend behavior

- vLLM startup and readiness.
- Supported NIM startup where applicable.
- Tool-call schema handling.
- Structured-output handling.
- Multimodal input handling.
- Streaming.
- Cancellation.
- Timeout and malformed-input errors.
- Context overflow.
- Concurrency and resource limits.
- No-egress startup.

### Router and fallback

- Independent route per worker assignment.
- Qualified-target-only routing.
- 96 GB hardware admission.
- Safe fallback with complete audit trail.
- Queue or stop when no qualified target is available.
- Verifier unavailability blocks completion.
- No silent model substitution.

## Required deliverables

- `models/roster/v0/model_roster.yaml`;
- signed offline model bundle;
- model, tokenizer, processor, runtime, container, and adapter hashes;
- `contracts/model_qualification.schema.yaml`;
- `qualifications/model_qualification_matrix.yaml`;
- `benchmarks/backend_compatibility_matrix.yaml`;
- `benchmarks/quantization_matrix.yaml`;
- model load, context, KV-cache, latency, throughput, and concurrency results;
- 96 GB hardware-profile references;
- air-gapped startup evidence;
- supply-chain and local-storage integrity evidence;
- routing traces for document/vision, reasoning, coding, and verification;
- fallback and verifier-unavailable traces;
- `acceptance/model_roster_matrix.yaml`;
- signed ledger export and offline replay result;
- passing test report.

## Definition of done

This issue is complete only when:

- all initial target identities are frozen to immutable artifacts;
- tokenizer, chat template, quantization, runtime, adapter, and container are pinned;
- the 96 GB VRAM hardware profile is referenced in every applicable qualification;
- each target has exact-role qualification certificates;
- BF16 and 4-bit decisions are supported by measured results;
- the vLLM adapter passes the required semantic compatibility tests;
- NIM is included only where the target is supported and air-gapped startup passes;
- the local bundle starts without Hugging Face, NGC, telemetry, remote credentials, or external network;
- the router independently selects targets per worker assignment;
- every fallback preserves task step, risk, provenance, clearance, and auditability;
- verifier unavailability blocks completion;
- model and backend decisions are written to the append-only ledger;
- the refinery/PSU inspection task and coding companion produce reproducible traces;
- the acceptance matrix is complete;
- all supply-chain, security, backend, routing, and failure-path tests pass.

## References

- `docs/models.md`
- `docs/model_qualification_framework.md`
- `docs/serving_and_routing.md`
- `docs/model_routing_review.md`
- `docs/airbench_harness.md`
- `docs/sovereignty_and_security.md`
- `docs/memory_and_audit_ledger.md`
- `docs/backend_development_plan.md`
- [Gemma model card](https://ai.google.dev/gemma/docs/core/model_card_4)
- [Qwen3-Coder-30B-A3B-Instruct](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)
- [Qwen2.5-VL](https://github.com/QwenLM-corp/Qwen2.5-VL)
- [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)
- [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3)
