# M8.1 Verification Framework evidence

This document records the completed core slice for GitHub issue #46.

## Implemented

`airbench.verification.VerificationRunner` is a deterministic, domain-neutral
runner. A domain pack supplies a finite `VerificationRule` set. The core owns
validation, execution, outcome aggregation, provenance propagation, clearance
gating, idempotency, and ledger writes.

The supported rule families are:

- source prefixes;
- confidence floors;
- exact units;
- inclusive numeric bounds;
- cross-fact comparisons;
- finite calculations using add, subtract, multiply, or divide with a target
  value or target fact and a declared tolerance.

The rule language does not evaluate Python, model-written expressions, regular
expressions, or arbitrary code. Missing facts, unavailable units, nonnumeric
values, inaccessible clearance, zero divisors, and missing calculation targets
produce `needs_review`. Deterministic predicate failures produce `failed`.
Only an all-passed set produces `passed`.

Each run appends `verification.requested` and `verification.completed` events.
The completed event includes typed check reasons, fact and source references,
confidence, clearance, taint, rule-set version, and an explicit provenance
object. It contains no fact values. Repeating the same verification ID replays
the sealed result without appending a second result.

## Tests

The focused suite in `tests/test_m81_verification.py` covers:

- all six check families in one successful run;
- failed predicates versus missing-evidence review;
- preservation of untrusted taint and higher fact clearance;
- missing calculation targets;
- ledger event order and provenance;
- idempotent replay;
- invalid rules and resource limits failing before ledger mutation;
- timeout handling and durable SQLite ledger integration.

Evidence commands:

```text
python -m pytest -q tests/test_m81_verification.py
python -m pytest -q
python -m compileall -q airbench contracts tests
git diff --check
```

Observed result: 8 focused tests passed and 56 repository tests passed.

## Boundary and remaining work

This closes the generic M8.1 runner slice, not the whole M8 milestone. Domain
packs still own field-specific rules, bounds, units, and rule-set versions.
M8.2 independent evaluator integration, M8.3 autonomy and consistency work,
and M8.4 cross-framework orchestration remain separate issues. The runner does
not claim that a verification result is a human approval or an organizational
decision.
