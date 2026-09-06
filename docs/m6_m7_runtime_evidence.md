# M6 and M7 runtime implementation evidence

This record covers the first Python runtime slices for M6.1 and M7.1. It is deliberately separate from the GitHub issue state because passing unit tests does not prove host-level isolation or production parser coverage.

## M7.1 File Intake Layer

Implemented in `airbench/intake.py`.

- `FileIntakeLayer` is the only entry point for `bulk_ingest` and `query_upload`.
- Both modes use the same parser object and the same manifest, provenance, taint, and ledger path.
- The three caller switches are explicit: destination, trust profile, and latency profile.
- Source hash, revision identity, intake identity, page identity, source region, extraction method, confidence, clearance, taint, and parser identity are stable and retained.
- Text, images, and PDF metadata are handled by the built-in safe parser. PDF page text and OCR are intentionally not invented by this first core parser. OCR and vision belong behind the later adapter issue.
- Uploaded content is never treated as an instruction. Page text is retained as untrusted data and can be omitted from a manifest projection.
- `evidence.created` is appended before a manifest is returned. A ledger failure returns an intake failure instead of an apparently successful manifest.
- File names cannot contain path syntax. Empty, oversized, malformed, and unsupported files fail closed.

The M7.1 issue should not be closed until the production parser adapter set, rendered-page artifact storage, and real Node integration are present. This slice establishes the shared boundary and replayable manifest contract.

## M6.1 sandbox

Implemented in `airbench/sandbox.py`.

- `SandboxRunner` accepts only a validated `ToolAction` for `python.execute`.
- Execution receives a fresh scratch directory, a sanitized environment, bounded wall time, bounded code size, bounded output, and read or write path checks.
- Python-level network, DNS, proxy, subprocess, package-install, and unsafe native-module paths are denied in the worker wrapper.
- Tool request, authorization, and result events are written to the append-only ledger. Results retain output hash, clearance, source reference, confidence, and taint.
- A policy can require hard OS network isolation. If the deployment cannot provide that capability, the runner fails closed with `network_isolation_unavailable`.

The Python guard is defense in depth. It is not a substitute for a verified container, namespace, job-object, or firewall boundary. The current Windows development account has not supplied that hard isolation evidence, so M6.1 remains open pending the host enforcement provider and no-egress test.

## Verification

From the repository root:

```text
python -m pytest -q tests/test_m61_sandbox.py tests/test_m71_intake.py
python -m pytest -q
python -m compileall -q airbench contracts tests
```

Observed result: all tests pass. The full suite currently contains 48 passing tests.

## Files

- `airbench/intake.py`
- `airbench/sandbox.py`
- `tests/test_m71_intake.py`
- `tests/test_m61_sandbox.py`
- `pyproject.toml`
