# Contract compatibility policy

All Python contracts use schema version `1.0` and compatibility identifier `airbench-core-contracts`. Patch changes are documentation-only. A minor release may add optional fields or enum values only when consumers fail closed on values they do not understand. Removing or renaming a required field, changing a type or enum meaning, or changing canonical serialization is a major breaking change.

Readers validate before state mutation. Persisted history is replayed using its original version and explicit named migrations; it is never rewritten in place. v1 rejects unknown fields. Validation errors use `contract_validation_failed`, a contract name, paths, stable codes, and messages that never echo secret values. Ledger failures block consequential transitions.
