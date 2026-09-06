# AirBench contracts (M1.1)

`contracts.models` is the provider-neutral boundary shared by the orchestrator, harness, router, workers, tools, verification, and ledger. Every model is a frozen dataclass with strict construction through `from_dict()`. Unknown fields, missing required fields, wrong primitive types, incompatible versions, resource-limit violations, and unsafe taint states fail closed with `ContractValidationError.to_dict()`.

## Usage

```python
from contracts import TaskEnvelope

task = TaskEnvelope.from_dict(payload)
wire_payload = task.to_dict()
replay_key = task.digest()
```

Use `stable_id(kind, ...)` for deterministic UUID5 identities and `idempotency_key(operation, ...)` for retry-safe operations. `canonical_json()` is sorted and compact for hashing and replay. The ledger envelope carries the payload hash, previous hash, sequence, parent event, and immutable flag; a ledger write failure must prevent the consequential action.

`FactEnvelope` always carries source, confidence, clearance, timestamps, derivation parents, and taint. `UntrustedEvidence` can never be marked clean. `ToolAction` accepts only clean, policy-cleared inputs. Worker/model outputs are proposals until deterministic orchestration and verification accept them.

## M5.1/M5.2 model and resource boundary

`model_registry.py` loads only a locally supplied, HMAC-signed registry. Each
target is bound to its artifact digest, tokenizer/template, quantization,
runtime/backend, exact role and modality, risk class, clearance, domain pack,
hardware profile, license, and qualification expiry. Artifact paths stay below
the supplied local artifact root and are hashed before use. Unsigned, stale,
tampered, or out-of-root targets fail closed; a reasoning qualification cannot
be reused for coding, vision, or verification.

`admission.py` accepts measured hardware values rather than probing a remote
service. It carries VRAM/RAM/KV-cache, model residency, latency, throughput,
sandbox limits, concurrency, and verified no-egress status. Admission returns
deterministic parallel, serial virtual-team, queued, or stopped plans. Every
admitted plan has an independent verifier reservation, and active reservations
are included in subsequent capacity checks.

M1.3 adds `HardwareProfile`, role-aware `ModelCallRequest` and `RoutingDecision`, resource admission through `TeamResourcePlan`, and strict tool/evidence gates. Model calls require a worker role, capability, attempt, idempotency key, and resource lease. Accepted routes require qualification and admitted resources. Resource plans require a verifier reservation and a declared execution mode. Hardware and resource values reject malformed or negative inputs before any state mutation.

M1.4 adds `EventLedger` and `build_event()`. Events are canonicalized, hash chained, immutable, sequence checked, and idempotent. Reusing an idempotency key for the same event is safe; reusing it for different content raises `IdempotencyConflict`. Invalid ordering, hashes, event names, or state preconditions raise a typed failure before append. `replay()` rebuilds task state from committed events, and `verify_chain()` checks the complete local chain. The example JSONL trace documents the wire shape; generated events should be used for executable replay fixtures.

M2.1 adds `SQLiteLedgerStore`, the first durable local adapter. It stores immutable event JSON, transaction seals, and checkpoints in SQLite; validates the hash chain after reload; commits related events atomically; rejects governed events without source/confidence/clearance/taint provenance; returns committed transaction IDs; supports clearance-filtered projections and signed exports; and keeps the signing key outside the database. A failed batch leaves no partial events or transaction seal.

M2.2 adds `ProjectionBuilder`, which rebuilds task, evidence, artifact, search, and audit views from committed events only. Each read-only snapshot records clearance, source sequence/head hash, event IDs, a content hash, and an HMAC signature. Projection rebuilding and export have no mutation path to the authoritative ledger.

M2.3 adds `RecoveryManager` for durable retry records, checkpoint validation, restart recovery, and consequential side-effect reservations. `run_once()` returns a committed result without invoking the effect again. An unfinished or uncertain reservation raises `SideEffectUncertain`, preventing an ambiguous crash from duplicating a tool or artifact action.

M2.4 adds offline-only `verify_signed_export()` and `verify_projection_export()` helpers. They validate serialized hashes and HMAC seals without a database, network, remote key service, or model runtime. The acceptance fixtures and tests cover tampering, duplicate writes, provenance rejection, clearance filtering, atomic failure, and recovery safety.

M3.1 adds `Orchestrator`, the only state-mutating control-plane API. It creates and authorizes bounded tasks, validates plans and replans, enforces explicit transition preconditions, records a checkpoint after each committed SQLite transition, and runs capped steps with deterministic retry keys. Worker/model callbacks return proposals only; they cannot call a transition or mark completion. Timeout exhaustion becomes a ledger-backed failure, and a transition or checkpoint write failure stops the task.

M3.2 adds `AuthorizationService` for local principal resolution, clearance ceilings, evidence/tool/risk/resource bounds, and required signed pack/policy references.

M3.3 adds typed `PlanProposal`/`PlanStep` validation for tools, evidence, budgets, dependency cycles, supported execution kinds, and completion criteria. M3.4 extends the executor to retrieval/world-model/verification kinds, generic typed step failures, cancellation, review requests, and dependency circuit breakers. All state changes remain orchestrator-owned and ledger-backed.

M3.5 adds the restart walking-skeleton acceptance test. It runs fake model, retrieval, tool, verification, and artifact adapters through the complete pipeline, closes and reopens the durable control plane after every transition, replays the final trace, and proves tool/artifact side effects are not repeated.

## M5.3 backend and routing boundary

`backend.py` defines the provider-neutral model adapter contract. It carries
typed messages, governed media references, tools, structured-output requests,
streaming and cancellation signals, normalized usage, typed failures, and
response provenance. `FakeBackend` is the deterministic offline adapter for
contract tests. `router.py` applies signed registry eligibility before backend
health/readiness and injected M5.2 resource admission. `Orchestrator.execute_model_call()`
records the routing decision and invokes the selected adapter through the
existing timeout, retry, and task-state machinery. Queued or rejected routes
never call a backend.

The compatibility rules are in `compatibility_policy.md`; the machine-readable registry and event/state catalogs are YAML and require no network or runtime service.
