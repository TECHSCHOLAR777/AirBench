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

M1.3 adds `HardwareProfile`, role-aware `ModelCallRequest` and `RoutingDecision`, resource admission through `TeamResourcePlan`, and strict tool/evidence gates. Model calls require a worker role, capability, attempt, idempotency key, and resource lease. Accepted routes require qualification and admitted resources. Resource plans require a verifier reservation and a declared execution mode. Hardware and resource values reject malformed or negative inputs before any state mutation.

M1.4 adds `EventLedger` and `build_event()`. Events are canonicalized, hash chained, immutable, sequence checked, and idempotent. Reusing an idempotency key for the same event is safe; reusing it for different content raises `IdempotencyConflict`. Invalid ordering, hashes, event names, or state preconditions raise a typed failure before append. `replay()` rebuilds task state from committed events, and `verify_chain()` checks the complete local chain. The example JSONL trace documents the wire shape; generated events should be used for executable replay fixtures.

M2.1 adds `SQLiteLedgerStore`, the first durable local adapter. It stores immutable event JSON, transaction seals, and checkpoints in SQLite; validates the hash chain after reload; commits related events atomically; rejects governed events without source/confidence/clearance/taint provenance; returns committed transaction IDs; supports clearance-filtered projections and signed exports; and keeps the signing key outside the database. A failed batch leaves no partial events or transaction seal.

M2.2 adds `ProjectionBuilder`, which rebuilds task, evidence, artifact, search, and audit views from committed events only. Each read-only snapshot records clearance, source sequence/head hash, event IDs, a content hash, and an HMAC signature. Projection rebuilding and export have no mutation path to the authoritative ledger.

M2.3 adds `RecoveryManager` for durable retry records, checkpoint validation, restart recovery, and consequential side-effect reservations. `run_once()` returns a committed result without invoking the effect again. An unfinished or uncertain reservation raises `SideEffectUncertain`, preventing an ambiguous crash from duplicating a tool or artifact action.

The compatibility rules are in `compatibility_policy.md`; the machine-readable registry and event/state catalogs are YAML and require no network or runtime service.
