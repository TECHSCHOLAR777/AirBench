# M6 and M7 runtime implementation evidence

This record covers the Python runtime slices for M6.1 and M7.1–M7.4. It is deliberately separate from the GitHub issue state because passing unit tests does not prove host-level isolation, qualified model serving, or production Node integration.

## M7.1 File Intake Layer

Implemented in `src/airbench/intake/layer.py`.

- `FileIntakeLayer` is the only entry point for `bulk_ingest` and `query_upload`.
- Both modes use the same parser object and the same manifest, provenance, taint, and ledger path.
- The three caller switches are explicit: destination, trust profile, and latency profile.
- Source hash, revision identity, intake identity, page identity, source region, extraction method, confidence, clearance, taint, and parser identity are stable and retained.
- Text, images, and digital PDF text are handled by the built-in safe parser. PDF extraction uses the declared `pypdf` adapter with page, per-page text, and total text bounds. Encrypted or malformed PDFs fail before ledger evidence is written. A scanned PDF with no text remains an untrusted page set with zero extraction confidence and is ready for the OCR or vision adapter. Image inputs are verified with the declared Pillow dependency and bounded by dimensions and pixel count, but pixels are not decoded for OCR in this layer. CSV rows are normalized to deterministic tabular text. DOCX text and simple tables are read from bounded WordprocessingML parts. XLSX sheets are read as bounded tabular text with formulas preserved as data and never evaluated by intake. OCR and vision are now typed local adapter seams; drawing interpretation remains behind a later drawing-pipeline adapter.
- DOCX and XLSX are treated as untrusted ZIP archives. The parser rejects malformed archives, path traversal, backslash or absolute paths, symlink entries, macro payloads, excessive member counts, and excessive uncompressed size. It reads selected XML parts without extracting archive paths or executing embedded content.
- This slice does not claim full Office layout fidelity, rich styling, drawing relationships, formula recalculation, macro support, scanned-document OCR, handwriting, or engineering-drawing understanding. Those require qualified adapters and verification evidence.
- Uploaded content is never treated as an instruction. Page text is retained as untrusted data and can be omitted from a manifest projection.
- `evidence.created` is appended before a manifest is returned. A ledger failure returns an intake failure instead of an apparently successful manifest.
- File names cannot contain path syntax. Empty, oversized, malformed, and unsupported files fail closed.
- `LocalIntakeStore` stages source bytes and optional rendered page bytes under a deployment-local root. It writes the manifest only after the ledger evidence event is accepted, then atomically publishes the intake directory.
- A renderer is an explicit typed adapter. Supplying a renderer without a store fails closed so rendered bytes cannot be silently discarded. Renderer identity and version are included in the intake identity and extraction settings.
- Repeating an intake with the same local store and ledger returns the persisted manifest without reparsing or appending a duplicate evidence event. A stored manifest without its ledger evidence is rejected as an inconsistent recovery state.
- Storage preparation and ledger failure paths remove staged files. The store uses only local filesystem operations and does not create network clients.

The M7.1 issue still needs deployment-specific renderer and real Node evidence. The M7.2 adapter path is locally implemented and tested, but a qualified OCR or Qwen2.5-VL runtime must be provisioned before production acceptance.

## M7.3 local index and M7.4 governed retrieval/world-model path

- `src/airbench/knowledge/retrieval.py` provides typed `IndexChunk`, `LocalVectorIndex`, and `LocalIndexer` contracts. Embedding and reranking are injected qualified local providers with bounded input/batch sizes and typed timeout/failure behavior; deterministic fixture providers are used only for offline tests and do not claim BGE-M3 quality.
- `RetrievalService` applies clearance before returning bounded cited excerpts and records request/completion/failure ledger events without query text. `LocalVectorIndex` has an optional bounded, atomic local JSON persistence seam and reloads current/superseded/deleted revision state without exposing non-current chunks.
- `src/airbench/knowledge/world_model.py` provides clearance-filtered fact queries and bounded typed relation traversal. Candidate facts and graph relations become query-visible only after both consistency and verification gates approve them and `fact.committed` is accepted by the ledger.
- `WorldModelStore` has an optional bounded, atomic local JSON persistence seam for committed `FactEnvelope` values; restart tests confirm that staged candidates do not bypass the commit gates.

M7.3 still needs qualified BGE-M3/reranker runtime and corpus measurements. New revisions now supersede prior current index chunks automatically. M7.4 has a signed projection/export contract test and current/superseded graph projections; it still needs live end-to-end acceptance evidence and deployment-scale graph/index validation.

## M6.1 sandbox

Implemented in `src/airbench/tools/sandbox.py`.

- `SandboxProvider` is the typed provider boundary. The runner no longer
  accepts a caller-supplied hard-isolation boolean; capabilities come from the
  provider identity and are hashed into the authorization and result evidence.
- `LocalSubprocessProvider` is explicitly a development provider. It reports
  no hard network, filesystem, non-root, or syscall isolation, so it cannot
  satisfy a production hard-isolation policy.
- `PodmanProvider` is the first real provider adapter. It is Linux/POSIX-first
  so the host and container share the same explicit path semantics. It fails
  closed on Windows rather than silently translating `C:\\` paths into a
  Linux VM with different meaning.
- `PodmanProvider` requires a content-addressed image, verifies the local
  rootless runtime and seccomp state, verifies the exact image digest in the
  local store, and uses `--pull=never` for execution. It applies explicit
  `network=none`, read-only root, non-root UID/GID, dropped capabilities,
  no-new-privileges, bind mounts only for approved scopes, CPU, memory, disk,
  process, and wall-time controls. The current `--storage-opt size=...`
  control covers the container writable layer; total disk enforcement for
  bind-mounted scratch and output scopes is intentionally not claimed yet.
- `SandboxExecutionRequest` carries the command, working directory, read and
  write scopes, and resource limits explicitly to the OS/container provider. A
  provider that cannot enforce a configured CPU, memory, disk, or process
  limit is rejected before execution.
- Every run produces a typed `SandboxManifest` with provider identity,
  capability digest, policy hash, hashed path scopes, configured limits,
  enforced limits, resource usage, isolation evidence references, output hash,
  observed wall time, cleanup status, and a ledger reference.
- Worker stdout and stderr are capped inside the worker before being returned,
  and output overflow becomes a failed execution rather than an apparently
  successful result.
- `SandboxRunner` accepts only a validated `ToolAction` for `python.execute`.
- Execution receives a fresh scratch directory, a sanitized environment, bounded wall time, bounded code size, bounded output, and read or write path checks.
- Scratch directories are removed after success, timeout, worker failure, or malformed worker output. Worker launch and result decoding failures still produce a `tool.result` event with a failed status.
- Python-level network, DNS, proxy, subprocess, package-install, and unsafe native-module paths are denied in the worker wrapper.
- Tool request, authorization, and result events are written to the append-only ledger. Results retain output hash, clearance, source reference, confidence, and taint.
- The result marks hard network isolation only when the policy both requires it and the deployment supplies the declared hard-isolation capability. A capability flag alone is not treated as proof.
- A policy can require hard OS network isolation. If the deployment cannot provide that capability, the runner fails closed with `network_isolation_unavailable`.

The Python guard is defense in depth. It is not a substitute for a verified
container, namespace, job-object, or firewall boundary. A real Podman
workstation smoke run has verified the runtime flags and observed behavior,
including no route or TCP sockets in the container namespace, no DNS or direct
TCP access, read-only root, zero effective capabilities, non-root execution,
resource cgroups, absent host sockets, and clean removal. The integrated
provider path still requires a native Linux GPU-box run and independent network
observation before #113 can close. The target run must also verify that the
chosen disk-control mechanism covers every writable scratch and output path,
not only the container layer. If it does not, the provider must stage those
paths into a quota-controlled workspace or use an approved host filesystem
quota before the acceptance gate can close.

## Verification

From the repository root:

```text
python -m pytest -q tests/test_m61_sandbox.py tests/test_m61_podman_provider.py tests/test_m71_intake.py tests/test_m72_ocr_vision.py tests/test_m73_retrieval.py tests/test_m74_world_model.py
python -m pytest -q
python -m compileall -q airbench contracts tests
```

Observed result: the focused M7.1–M7.4 slice passes 40 tests, the full
Python suite passes 306 tests, and the compile check passes in the local
development environment. These are deterministic contract tests; they do not
replace host-level sandbox, qualified model-serving, or packaged Node evidence.

## Files

- `src/airbench/intake/layer.py`
- `src/airbench/tools/sandbox.py`
- `src/airbench/tools/podman_provider.py`
- `tests/test_m71_intake.py`
- `tests/test_m61_sandbox.py`
- `tests/test_m61_podman_provider.py`
- `pyproject.toml`
