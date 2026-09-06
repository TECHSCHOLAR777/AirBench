# M6.3 file, spreadsheet, and artifact tools evidence

This document records the completed core slice for GitHub issue #40.

## Implemented

`airbench.file_tools.FileToolRunner` provides bounded local byte reads and
writes, artifact inspection, SHA-256 manifests, media-type metadata, workspace
and source-mount allowlists, symlink-aware path resolution, and read/write size
limits. Every returned result carries source, confidence, clearance, and taint
and writes an audited ledger event.

`SpreadsheetTool` operates only on a typed `SpreadsheetTable`. It supports
column projection, equality filtering, deterministic decimal sums, and CSV
serialization through the file writer. Transformations preserve the source
provenance, revision identity, clearance, and taint. Numeric results are
computed with `Decimal`, and non-finite or nonnumeric values are rejected.

## Single-intake boundary

This implementation does not parse uploaded CSV, XLSX, PDF, or other document
bytes. The File Intake Layer remains the only file interpretation boundary.
Spreadsheet operations consume typed rows produced by that boundary, and
writing CSV is serialization of typed rows, not a second parser.

## Tests

`tests/test_m63_file_tools.py` covers:

- scoped read, write, inspect, hashing, and provenance;
- traversal, outside-mount, and size-limit rejection;
- typed table filtering, projection, and deterministic sums;
- shape and numeric validation failures;
- ledger event ordering for file and spreadsheet operations.

Evidence commands:

```text
python -m pytest -q tests/test_m63_file_tools.py
python -m pytest -q
python -m compileall -q airbench contracts tests
git diff --check
```

Observed result: 4 focused tests passed and 71 repository tests passed.

## Boundary and remaining work

Rich XLSX, Office rendering, macros, formula recalculation, and production
artifact rendering remain in the deliverable and future hardening work. This
slice is the safe tool boundary and typed-table core; it does not bypass File
Intake or claim rich Office support.
