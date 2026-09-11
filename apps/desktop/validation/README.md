# AirBench frontend validation fixtures

These fixtures are synthetic and run only on the local validation workstation. They are not a replacement for the Python AirBench Node.

`node_fixture.py` exposes the minimum authenticated handshake used by the Tauri transport. The HTTPS fixture uses a local self-signed certificate. The certificate is trusted only through the explicit approved profile and is additionally checked by its SHA-256 leaf pin.

The fixture never prints bearer tokens or private keys. Generated certificates, profiles, logs, and temporary files belong in a temporary directory and must not be committed.

The Rust credential-store example uses the Windows Credential Manager through the `keyring` crate. The desktop webview receives only a credential reference, never the secret.

`validate-python-node-transport.ps1` starts the real Python `NodeApiService` with a temporary local `FileIntakeLayer` store. Its intake probe creates a Node task first, sends a task-bound query upload through the Rust bridge, reads the Node-generated safe source preview, and verifies a hash-preserving download plus ledger references. The validation composition now also accepts an explicit task authorization, commits a synthetic no-egress plan, accepts operator plan approval, runs the real M4 team runtime with a bounded local worker, runs deterministic source verification, and projects a real DOCX through the Deliverable Engine. The worker and hardware records are synthetic; this does not claim OCR or vision for scans unless a qualified adapter is configured, and it does not claim packaged, GPU, visual-renderer, or independent WebDriver evidence.

To retain a scrubbed success manifest for an issue or handoff, pass an explicit path outside the disposable run root:

```powershell
npm run validate:python-node -- -EvidencePath "$env:TEMP\AirBench-evidence\python-node.json"
```

The manifest records the run identity, branch, commit, machine, Python version, checks, and limitations. It contains no input document contents, credentials, or private model output. A successful manifest is still local development evidence; it is not packaged acceptance, independent runtime network monitoring, OCR/vision qualification, GPU qualification, or visual artifact approval.

The real-node desktop wrapper uses `@wdio/tauri-service`'s standalone session initializer. This lets the service provide its native driver host and port directly, avoiding WDIO local-runner's browser-driver bootstrap rejecting the service's browserName-free Tauri capabilities.

`validate-node-transport.ps1` and `validate-python-node-transport.ps1` build into
a disposable `CARGO_TARGET_DIR` under each temporary run directory. This is
intentional: Cargo dependency artifacts
can retain absolute paths from before the repository moved from
`frontend/src-tauri` to `apps/desktop/src-tauri`, including generated Tauri
permission files. The validation must not depend on, repair, or delete the
existing debug cache.

Validation runs are disposable and must not become a second model or build
store. The desktop runner removes its own temporary run directory on success,
failure, and handled interruption. The PowerShell transport validators also
remove their run roots after stopping fixture processes. To inspect abandoned
runs from an earlier interrupted process, use `npm run cleanup:test-artifacts`
from `apps/desktop`. It is a dry run by default. After confirming that no
AirBench WebDriver process is active, use
`npm run cleanup:test-artifacts -- --apply`. The command only considers known
AirBench temporary-run prefixes older than 24 hours and never touches the
repository Cargo target, local models, or the Hugging Face cache.

Validation runs are disposable and must not become a second model or build
store. The desktop runner removes its own temporary run directory on success,
failure, and handled interruption. To inspect abandoned runs from an earlier
interrupted process, use `npm run cleanup:test-artifacts` from `apps/desktop`.
It is a dry run by default. After confirming that no AirBench WebDriver
process is active, use `npm run cleanup:test-artifacts -- --apply`. The command
only considers known AirBench temporary-run prefixes older than 24 hours and
never touches the repository Cargo target, local models, or the Hugging Face
cache.
