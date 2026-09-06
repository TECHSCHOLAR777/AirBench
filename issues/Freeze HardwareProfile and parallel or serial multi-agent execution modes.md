# Freeze Hardware-Aware Scheduling and Resource Management

## Issue type

M4/M5 infrastructure issue: hardware measurement, model admission, worker-team scheduling, and reproducible execution evidence.

## Objective

Measure the target AirBench workstation or GPU server and freeze how the same logical multi-agent team runs under the available local compute budget.

AirBench is local-only and cannot use cloud capacity as a fallback. The scheduler must therefore treat physical hardware as a signed, measurable resource budget while preserving worker identity, provenance, verification, clearance, authority, and auditability.

The reference deployment for this issue is:

```text
GPU count: 1
GPU memory: 96 GB VRAM
Execution boundary: local-only, no external network dependency
Primary workload: refinery/PSU inspection-report review and approval-note preparation
```

The design must also support a different measured workstation or GPU server through the same typed contracts. Hardware changes execution timing and concurrency; it must not change the logical team, required evidence, verification threshold, or authority boundary.

## Required decisions

This issue must produce evidence-backed decisions for:

- GPU model, count, identity, and fingerprint;
- total, reserved, and available VRAM;
- driver and CUDA or equivalent runtime version;
- CPU model, count, and available capacity;
- system RAM and available RAM;
- local storage capacity and available scratch capacity;
- local model-serving runtime and container/image identity;
- model load and unload time;
- context-window and KV-cache limits;
- prompt and generation throughput;
- first-token and end-to-end latency;
- measured concurrency and safe concurrency ceiling;
- model residency and eviction policy;
- worker resource reservations;
- parallel, pipelined, or serial execution mode;
- queue, priority, preemption, cancellation, and retry behavior;
- resource-exhaustion behavior;
- background-ingestion yielding behavior;
- reproducible ledger and artifact evidence.

## Scope

### In scope

- A signed `HardwareProfile` schema.
- A signed `TeamResourcePlan` schema.
- A local hardware probe with normalized measurements.
- Candidate-model load, latency, throughput, context, and concurrency benchmarks.
- Admission control for bounded worker teams.
- Parallel execution when reservations fit simultaneously.
- Serial virtual-team execution when workers cannot fit concurrently.
- Pipelined execution where safe and useful.
- Model residency, unload, and reload behavior.
- Interactive-task priority over background ingestion.
- Queueing, explicit degradation with review, safe stop, cancellation, and recovery.
- The refinery/PSU inspection-report team executed with the same logical workers in both supported modes.
- Ledger events for measurement, reservation, scheduling, execution, model swaps, failures, and completion.
- No-network and local-only execution evidence.

### Out of scope

- Cloud bursting or remote model workers.
- Distributed cross-site worker execution.
- Splitting a single model across GPUs unless separately qualified and explicitly supported.
- Changing domain rules based on hardware pressure.
- Removing the verifier or review worker.
- Lowering confidence, evidence, or verification thresholds.
- Replacing a qualified model with an unqualified model.
- Implementing the engineering drawing pipeline.
- Production fleet management, automatic updates, or hardware-backed attestation.

## HardwareProfile contract

Create a typed schema and signed artifact at:

```text
contracts/hardware_profile.schema.yaml
profiles/hardware/target_96gb_vram.yaml
```

The schema must contain, at minimum:

```yaml
hardware_profile:
  profile_id: string
  schema_version: string
  measured_at: timestamp
  measurement_tool_version: string
  host:
    hostname_or_local_id: string
    os_and_kernel: string
    architecture: string
  gpu:
    count: integer
    devices:
      - index: integer
        model: string
        device_id: string
        fingerprint: string
        vram_total_bytes: integer
        vram_available_bytes: integer
        driver_version: string
        cuda_or_equivalent_version: string
        interconnect: string|null
  cpu:
    model: string
    logical_cores: integer
    physical_cores: integer|null
    available_capacity_percent: number
  memory:
    ram_total_bytes: integer
    ram_available_bytes: integer
  storage:
    root_total_bytes: integer
    root_available_bytes: integer
    scratch_path: string
    scratch_total_bytes: integer
    scratch_available_bytes: integer
  runtime:
    model_server: string
    model_server_version: string
    sandbox_runtime: string
    sandbox_version: string
    container_or_image_fingerprints: [string]
  isolation:
    egress_policy: string
    network_check_id: string
    host_socket_access: boolean
  benchmark_summary:
    safe_parallel_slots: integer
    supported_execution_modes: [parallel|pipelined|serial_virtual_team]
  provenance:
    source_measurements: [string]
    evidence_hashes: [string]
    signer_key_id: string
    signature: string
```

The profile must distinguish total capacity from currently available capacity. Measurements must include timestamp, probe version, command/tool identity, and evidence hash. A profile without a valid signature or required measurements must not be admitted for consequential work.

The target profile must explicitly record the 96 GB VRAM GPU. The exact GPU model, driver, runtime, CPU, RAM, storage, and scratch values must come from measurement, not assumptions.

## Model benchmark contract

Create a reproducible benchmark runner and store results at:

```text
benchmarks/model_hardware_results.yaml
```

For every candidate target, record:

- exact model artifact and content hash;
- quantization and runtime configuration;
- qualification certificate ID;
- model role/capability;
- prompt and context fixture IDs;
- input and output token counts;
- image/page dimensions for vision workloads;
- cold load time;
- warm load time or residency state;
- unload time and peak memory;
- first-token latency;
- end-to-end latency;
- prompt-processing throughput;
- generation throughput;
- context-window limit;
- KV-cache allocation and limit;
- stable maximum concurrency;
- failure threshold and observed failure mode;
- CPU, RAM, VRAM, and scratch usage;
- benchmark repetitions and variance;
- runtime and hardware profile IDs;
- pass/fail result for each candidate role.

The benchmark must run offline using local fixtures. It must not download models, call hosted APIs, emit telemetry, or depend on an external registry.

At minimum, benchmark the capabilities required by the inspection task:

- document/OCR/vision extraction;
- reasoning and evidence synthesis;
- coding or deterministic calculation assistance;
- independent verification;
- rendering/review support if model-backed.

The benchmark result is not itself qualification. A target is schedulable only when it has both a valid capability qualification and a hardware admission result.

## TeamResourcePlan contract

Create a typed schema at:

```text
contracts/team_resource_plan.schema.yaml
```

The plan must contain:

```yaml
team_resource_plan:
  plan_id: string
  task_id: string
  team_id: string
  hardware_profile_id: string
  plan_version: string
  created_at: timestamp
  requested_mode: parallel|pipelined|serial_virtual_team|auto
  admitted_mode: parallel|pipelined|serial_virtual_team|queued|stopped
  admission: admitted|queued|degraded_needs_review|rejected
  admission_reason: string
  priority: interactive|scheduled|background
  reservations:
    - worker_id: string
      role: string
      capability: string
      model_target_id: string
      qualification_id: string
      gpu_indices: [integer]
      vram_reserved_bytes: integer
      cpu_reserved_millicores: integer
      ram_reserved_bytes: integer
      scratch_reserved_bytes: integer
      context_tokens_reserved: integer
      kv_cache_reserved_bytes: integer
      start_deadline: timestamp
      execution_deadline: timestamp
      residency: resident|load_on_demand|evictable
  dependency_graph: object
  concurrency:
    max_parallel_workers: integer
    barrier_policy: string
    pipeline_stages: [string]
  scheduling:
    queue_class: string
    preemption_policy: string
    cancellation_policy: string
    retry_policy: string
    unload_policy: string
  safety_invariants:
    verifier_required: true
    review_required: true
    verification_threshold: string
    qualified_targets_only: true
    provenance_required: true
  provenance:
    hardware_profile_hash: string
    qualification_hashes: [string]
    policy_hash: string
    signer_key_id: string
    signature: string
```

The plan must be committed before worker execution. A worker, model response, uploaded document, or benchmark result cannot enlarge the plan or add authority.

## Scheduling modes

### Parallel mode

Parallel mode is admitted only when the scheduler proves that all required reservations fit within the measured hardware budget, including model weights, runtime overhead, context, KV cache, safety headroom, CPU, RAM, and scratch.

The plan must record:

- all concurrently admitted workers;
- per-worker reservations;
- maximum concurrency;
- GPU assignment;
- model residency;
- expected barrier timing;
- safety headroom;
- admission reason.

The parallel team must retain the normal logical topology:

```text
lead
  -> evidence/vision + reasoning
  -> join barrier
  -> independent verifier
  -> render/review
  -> completion gate
```

### Serial virtual-team mode

Serial virtual-team mode is used when the same logical team cannot fit concurrently on the measured hardware. Workers execute one at a time or as a safe pipeline, with explicit model load/unload or residency transitions.

Serial mode must preserve:

- the same task ID and team ID;
- the same worker identities and roles;
- separate worker assignments and contexts;
- typed immutable WorkPackets;
- the same evidence, clearance, confidence, and taint fields;
- the same join barrier semantics;
- the same independent verifier stage;
- the same render/review stage;
- the same completion criteria;
- the same ledger trace semantics.

Serial execution is a scheduling change, not a quality or authority change.

### Pipelined mode

Pipelining may be admitted only when stage overlap does not create unsafe shared state, provenance ambiguity, resource overcommitment, or verifier dependence on an incomplete upstream result. Each stage must have an explicit reservation, handoff contract, and barrier condition.

## Admission and resource exhaustion

The scheduler must perform these checks before each worker starts:

1. Hardware profile is valid, signed, current, and locally measurable.
2. Required model target is qualified for the exact role, modality, risk class, and output contract.
3. Model artifact and runtime fingerprints match the qualified record.
4. VRAM, KV cache, context, CPU, RAM, scratch, and time reservations fit.
5. Worker clearance and evidence scope fit the task policy.
6. Required verifier and review capacity are reserved.
7. Required ledger and isolation services are available.

If resources do not fit, the result must be one of:

- `queued`: wait for safe capacity;
- `degraded_needs_review`: use an explicitly qualified lower-capability mode while preserving all checks and human review;
- `serial_virtual_team`: serialize the unchanged logical team;
- `stopped`: stop safely when minimum requirements cannot be met;
- `rejected`: refuse an invalid or unsafe plan.

Silent degradation is forbidden. In particular, the scheduler must never:

- remove the independent verifier;
- lower a verification threshold;
- accept an unqualified model;
- broaden a worker's clearance;
- reuse hidden worker context as a shortcut;
- skip a required evidence source;
- mark an incomplete artifact complete;
- convert a timeout or missing result into success.

## Queueing, priority, and preemption

Interactive complex inspection tasks have priority over background ingestion.

Required behavior:

- background ingestion yields GPU, CPU, RAM, and scratch capacity to an admitted interactive task;
- yielding must be recorded as a scheduling event;
- preemption must be cooperative or safely cancellable;
- a partially processed background document remains resumable and auditable;
- interactive work may not inherit uncommitted background state;
- the interactive task may queue if minimum safe reservations are unavailable;
- priority must never bypass clearance, qualification, or verification gates.

Define and test priority classes:

```text
interactive_high_consequence
interactive_normal
scheduled_domain_work
background_ingestion
maintenance
```

## Model residency and unload policy

The scheduler must define:

- which targets remain resident on the 96 GB GPU;
- minimum idle time before eviction;
- eviction priority;
- whether KV cache is discarded between workers;
- model load timeout;
- unload timeout;
- cleanup behavior after worker cancellation or failure;
- memory accounting after unload;
- recovery if the runtime reports stale or inconsistent memory.

Model swaps must be explicit ledger events. A failed unload or uncertain memory state must block the next consequential reservation until the state is remeasured or the machine is safely reset.

## Worker-team demonstration

Run the frozen refinery/PSU inspection-report task from the domain-pack issue using the hardware scheduler.

The demonstration must show:

1. Hardware measurement and signed profile loading.
2. Candidate model benchmark results.
3. Team plan creation and admission decision.
4. Logical worker assignments for lead, evidence/vision, reasoning, verifier, and render/review.
5. Parallel execution when the 96 GB profile admits required reservations.
6. Serial virtual-team execution when reservations are intentionally constrained or a serial profile is selected.
7. Identical worker IDs, typed handoffs, criteria, verifier stage, and review state in both modes.
8. Model load/residency/unload behavior.
9. A resource-exhaustion scenario producing queue, explicit review degradation, or stop.
10. Background ingestion yielding to the interactive task.
11. Final approval-note artifact and evidence package.
12. Reproducible ledger replay of scheduling and execution.

If only one physical 96 GB machine is available, the parallel-capable and serial profiles may be produced as two signed scheduling profiles over the same measured hardware, provided the parallel profile is supported by benchmarked reservations and the serial profile is exercised end to end. The evidence must clearly distinguish measured behavior from a simulated capacity limit.

## Ledger requirements

Every scheduling decision and resource transition must be recorded in the append-only ledger.

Required events include:

```text
hardware.measurement.started
hardware.measurement.completed
hardware.profile.loaded
model.benchmark.started
model.benchmark.completed
model.qualification.checked
team.resource_plan.created
team.resource_plan.admitted
team.resource_plan.queued
team.resource_plan.degraded_needs_review
team.resource_plan.rejected
worker.resource_reserved
worker.started
worker.preempted
worker.cancelled
worker.completed
model.loaded
model.resident
model.evicted
model.unloaded
execution.mode.selected
execution.mode.changed
join_barrier.waiting
join_barrier.completed
background.work.yielded
resource.exhaustion.detected
resource.recovered
verification.reservation.confirmed
verification.completed
artifact.completed
completion.blocked
completion.ready
```

Each event must include:

- task, team, worker, and parent IDs;
- hardware profile ID and hash;
- resource lease ID;
- execution mode;
- model target and qualification ID;
- reservation and measured usage;
- policy and pack versions;
- evidence/artifact references;
- timestamp;
- attempt, retry, cancellation, or failure reason;
- previous ledger hash and event hash.

## Acceptance matrix

Create:

```text
acceptance/hardware_scheduling_matrix.yaml
```

The matrix must map every acceptance requirement to:

- requirement ID;
- test or demo scenario;
- observable result;
- expected ledger event;
- evidence artifact;
- pass/fail rule.

Minimum rows:

| Requirement | Observable result | Ledger evidence |
|---|---|---|
| Hardware measurement | Signed profile with exact GPU/CPU/RAM/storage data | `hardware.measurement.completed` |
| 96 GB reference target | Profile records measured 96 GB VRAM device | `hardware.profile.loaded` |
| Model measurements | Load, latency, throughput, context, KV, and concurrency results | `model.benchmark.completed` |
| Signed schemas | Valid `HardwareProfile` and `TeamResourcePlan` | `schema.validation.completed` |
| Parallel mode | Multiple workers admitted with fitting reservations | `team.resource_plan.admitted` |
| Serial mode | Same team executed serially or pipelined | `execution.mode.selected` |
| Same logical team | Same roles, IDs, handoffs, verifier, and completion criteria | `worker.assigned`, `work_packet.committed` |
| Resource exhaustion | Queue, explicit review degradation, or stop | `resource.exhaustion.detected` |
| No silent safety degradation | Verifier and thresholds remain present | `verification.reservation.confirmed` |
| Background priority | Ingestion yields to interactive task | `background.work.yielded` |
| Model residency | Load, resident, eviction, and unload are visible | `model.loaded`, `model.evicted` |
| Auditability | Trace can be replayed from ledger export | `evidence_package.sealed` |
| Local sovereignty | No external calls during measurement or execution | `egress.check.completed` |

## Required tests

### Schema and integrity tests

- Valid and invalid `HardwareProfile` documents.
- Valid and invalid `TeamResourcePlan` documents.
- Signature and content-hash verification.
- Stale-profile rejection.
- Hardware/profile mismatch rejection.
- Model qualification and artifact-hash mismatch rejection.
- Reservation arithmetic and safety-headroom checks.
- No missing required verifier reservation.

### Scheduling tests

- Parallel admission when all reservations fit.
- Parallel rejection when VRAM or KV-cache reservations exceed capacity.
- Serial fallback with unchanged worker identities and handoffs.
- Safe pipeline admission.
- Queue behavior when capacity is temporarily unavailable.
- Explicit `degraded_needs_review` behavior.
- Safe stop when minimum verifier resources cannot be obtained.
- Interactive task preempts or causes background ingestion to yield.
- Background task resumes from an auditable checkpoint.
- Cancellation releases reservations.
- Worker failure releases or reconciles reservations.
- Model load timeout produces a typed failure.
- Unload failure blocks unsafe subsequent admission.
- Hardware pressure never removes verification or lowers thresholds.

### End-to-end tests

- Refinery/PSU inspection task in parallel-capable mode.
- Refinery/PSU inspection task in serial virtual-team mode.
- Same final evidence and completion criteria in both modes.
- DOCX artifact generated and checked in both modes.
- Coding companion remains no-network and locally auditable.
- Ledger replay reconstructs reservations, mode, worker trace, and completion result.

## Required deliverables

- `contracts/hardware_profile.schema.yaml`
- `contracts/team_resource_plan.schema.yaml`
- `profiles/hardware/target_96gb_vram.yaml`
- signed hardware measurement export;
- model load/latency/throughput/context/KV/concurrency results;
- model qualification references;
- scheduling and admission policy;
- queue, preemption, cancellation, residency, and unload policy;
- parallel execution trace;
- serial virtual-team execution trace;
- resource-exhaustion trace;
- background-ingestion-yield trace;
- `acceptance/hardware_scheduling_matrix.yaml`;
- local audit-ledger export and replay result;
- no-egress evidence;
- passing test report.

## Definition of done

This issue is complete only when:

- the target machine has a signed, reproducible `HardwareProfile`;
- the 96 GB VRAM GPU is explicitly measured and recorded;
- every candidate target has benchmark evidence for its intended role;
- the `TeamResourcePlan` is signed, validated, and committed before execution;
- the inspection-report team runs in every supported execution mode;
- parallel mode is admitted only when reservations fit;
- serial mode preserves the same logical team and typed handoffs;
- verifier and review stages exist in both modes;
- resource exhaustion queues, explicitly degrades with review, or stops;
- background ingestion yields to interactive complex work;
- model load, residency, eviction, and unload behavior is recorded;
- no unqualified model or silent authority degradation is possible;
- all scheduling and execution decisions are ledger events;
- the execution trace is reproducible offline;
- local-only/no-egress evidence passes;
- the acceptance matrix is complete;
- all success, failure, cancellation, and security tests pass on a clean local node.

## Dependencies

This issue depends on:

- M1 typed contracts;
- M2 append-only ledger;
- M3 orchestrator state and policy;
- M4 AirBench Harness worker lifecycle;
- M5 model registry, serving, and qualification;
- M6 sandbox and Tool Gateway;
- M9 refinery/PSU inspection-report vertical slice for the end-to-end demonstration.

It must not be closed using a benchmark-only claim. The required result is the measured hardware profile plus a reproducible team execution trace and failure evidence.

## References

- `docs/architecture_design.md`
- `docs/airbench_harness.md`
- `docs/serving_and_routing.md`
- `docs/model_qualification_framework.md`
- `docs/orchestration_engine.md`
- `docs/memory_and_audit_ledger.md`
- `docs/sovereignty_and_security.md`
- `docs/backend_development_plan.md`
