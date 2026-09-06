# M6 and M7 runtime implementation evidence

This record covers the first Python runtime slices for M6.1 and M7.1. It is deliberately separate from the GitHub issue state because passing unit tests does not prove host-level isolation or production parser coverage.

## M7.1 File Intake Layer

Implemented in `airbench/intake.py`.

- `FileIntakeLayer` is the only entry point for `bulk_ingest` and `query_upload`.
- Both modes use the same parser object and the same manifest, provenance, taint, and ledger path.
- The three caller switches are explicit: destination, trust profile, and latency profile.
- Source hash, revision identity, intake identity, page identity, source region, extraction method, confidence, clearance, taint, and parser identity are stable and retained.
- Text, images, and digital PDF text are handled by the built-in safe parser. PDF extraction uses the declared `pypdf` adapter with page, per-page text, and total text bounds. Encrypted or malformed PDFs fail before ledger evidence is written. A scanned PDF with no text remains an untrusted page set with zero extraction confidence and is ready for the later OCR or vision adapter. Image inputs are verified with the declared Pillow dependency and bounded by dimensions and pixel count, but pixels are not decoded for OCR in this layer. CSV rows are normalized to deterministic tabular text. DOCX text and simple tables are read from bounded WordprocessingML parts. XLSX sheets are read as bounded tabular text with formulas preserved as data and never evaluated by intake. OCR, vision, and drawing interpretation remain behind their later adapter issues.
- DOCX and XLSX are treated as untrusted ZIP archives. The parser rejects malformed archives, path traversal, backslash or absolute paths, symlink entries, macro payloads, excessive member counts, and excessive uncompressed size. It reads selected XML parts without extracting archive paths or executing embedded content.
- This slice does not claim full Office layout fidelity, rich styling, drawing relationships, formula recalculation, macro support, scanned-document OCR, handwriting, or engineering-drawing understanding. Those require qualified adapters and verification evidence.
- Uploaded content is never treated as an instruction. Page text is retained as untrusted data and can be omitted from a manifest projection.
- `evidence.created` is appended before a manifest is returned. A ledger failure returns an intake failure instead of an apparently successful manifest.
- File names cannot contain path syntax. Empty, oversized, malformed, and unsupported files fail closed.
- `LocalIntakeStore` stages source bytes and optional rendered page bytes under a deployment-local root. It writes the manifest only after the ledger evidence event is accepted, then atomically publishes the intake directory.
- A renderer is an explicit typed adapter. Supplying a renderer without a store fails closed so rendered bytes cannot be silently discarded. Renderer identity and version are included in the intake identity and extraction settings.
- Repeating an intake with the same local store and ledger returns the persisted manifest without reparsing or appending a duplicate evidence event. A stored manifest without its ledger evidence is rejected as an inconsistent recovery state.
- Storage preparation and ledger failure paths remove staged files. The store uses only local filesystem operations and does not create network clients.

The M7.1 issue should not be closed until the production parser adapter set, rendered-page artifact storage, and real Node integration are present. This slice now establishes bounded digital PDF extraction and structural image validation in addition to the shared boundary, bounded Office XML baseline, and replayable manifest contract. It still does not claim OCR, vision, drawing interpretation, or production Node integration.

## M6.1 sandbox

Implemented in `airbench/sandbox.py`.

- `SandboxRunner` accepts only a validated `ToolAction` for `python.execute`.
- Execution receives a fresh scratch directory, a sanitized environment, bounded wall time, bounded code size, bounded output, and read or write path checks.
- Scratch directories are removed after success, timeout, worker failure, or malformed worker output. Worker launch and result decoding failures still produce a `tool.result` event with a failed status.
- Python-level network, DNS, proxy, subprocess, package-install, and unsafe native-module paths are denied in the worker wrapper.
- Tool request, authorization, and result events are written to the append-only ledger. Results retain output hash, clearance, source reference, confidence, and taint.
- The result marks hard network isolation only when the policy both requires it and the deployment supplies the declared hard-isolation capability. A capability flag alone is not treated as proof.
- A policy can require hard OS network isolation. If the deployment cannot provide that capability, the runner fails closed with `network_isolation_unavailable`.

The Python guard is defense in depth. It is not a substitute for a verified container, namespace, job-object, or firewall boundary. The current Windows development account has not supplied that hard isolation evidence, so M6.1 remains open pending the host enforcement provider and no-egress test.

## Verification

From the repository root:

```text
python -m pytest -q tests/test_m61_sandbox.py tests/test_m71_intake.py
python -m pytest -q
python -m compileall -q airbench contracts tests
```

Observed result: the full Python suite and compile check pass after the bounded PDF adapter tests. The exact count is intentionally taken from the CI run rather than maintained manually in this evidence note.

## Files

- `airbench/intake.py`
- `airbench/sandbox.py`
- `tests/test_m71_intake.py`
- `tests/test_m61_sandbox.py`
- `pyproject.toml`
