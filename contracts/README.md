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

The compatibility rules are in `compatibility_policy.md`; the machine-readable registry and event/state catalogs are YAML and require no network or runtime service.
