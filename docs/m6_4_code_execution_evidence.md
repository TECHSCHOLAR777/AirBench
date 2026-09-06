# M6.4 code execution evidence

This document records the completed core code-execution manifest slice for
GitHub issue #41.

## Implemented

`airbench.code_execution.CodeExecutionRunner` runs one typed Python action and
then a bounded list of declared test actions through the existing
`SandboxRunner`. Each test is independently audited. A test must succeed for
the manifest to succeed.

The runner captures:

- main and test statuses;
- stdout and stderr hashes;
- sandbox ledger references;
- observed wall time;
- declared output artifact paths, SHA-256 hashes, sizes, and media types;
- a signed ledger manifest event with provenance.

Calculation evidence is accepted only from lines emitted by the sandbox using
the `AIRBENCH_CALCULATION:` machine-readable protocol. Values are parsed as
finite `Decimal` values and stored as named evidence with source, confidence,
clearance, and taint. Plain prose containing a number never becomes a
calculation result.

Missing artifacts or failed declared tests produce `failed`. Missing or
invalid calculation evidence produces `needs_review`. Main execution timeout
remains `timed_out`. The manifest does not mark a task complete or approved.

## Tests

`tests/test_m64_code_execution.py` covers:

- successful code, declared test, artifact hash, and calculation evidence;
- failed declared test blocking success;
- prose numbers being rejected as calculation evidence;
- out-of-scope artifacts being rejected before execution.

Evidence commands:

```text
python -m pytest -q tests/test_m64_code_execution.py
python -m pytest -q
python -m compileall -q airbench contracts tests
git diff --check
```

Observed result: 4 focused tests passed and 65 repository tests passed.

## Boundary and remaining work

The manifest reports configured sandbox limits and observed wall time. Host
CPU, RAM, disk, and fleet performance telemetry remain M10.3 work. The
manifest does not replace the hard OS isolation evidence still required by
M6.1, and it does not parse uploaded documents or spreadsheets. Those continue
to use the File Intake Layer.
