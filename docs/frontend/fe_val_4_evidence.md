# FE-VAL-4 evidence record

Status: File Intake and safe-preview fixture validation in progress. No complete packaged desktop pass is claimed yet.

## Implemented boundary

- Native file selection is owned by the Tauri Rust shell. The webview receives a selection token and metadata, not a file path it can substitute later.
- The Rust shell streams the selected bytes to the approved Node `query_upload` endpoint. It does not parse PDF, image, OCR, Office, or drawing content.
- The Node returns the intake manifest with source hash, revision, parser metadata, page and OCR or vision state, clearance, taint, preview reference, artifact reference, and ledger reference.
- Preview is a typed Node response containing safe text plus source-region, confidence, clearance, taint, and ledger references. The UI does not render arbitrary HTML or document script.
- Artifact preview is a separate typed Node response containing only bounded text blocks, artifact identity, clearance, taint, and a ledger reference. The UI never receives or renders the Office/PDF package itself.
- `frontend/src/intakeBridge.ts` exposes typed upload, safe-preview, and Node-authorized download calls. It validates the approved profile before IPC and passes only the native selection token for upload; it does not expose file bytes or parse content in React.
- Preview and artifact references are treated as opaque Node-issued path segments. The shell no longer requires a fixture-specific prefix, but rejects traversal, separators, query syntax, control characters, and overlong references before constructing a request path.
- Artifact download is Node-authorized. Rust verifies the response hash and ledger header before saving through a native save dialog.

## Synthetic fixture evidence

Command from `frontend/`:

```text
npm run validate:node
```

The validation runner creates a synthetic scanned PDF containing instruction-bearing text, uploads it through the fixture File Intake endpoint, compares the returned source hash with the selected file, checks that source and artifact preview taint remain `untrusted`, displays both safe preview contracts, verifies the downloaded artifact hash and ledger reference, rejects a denied artifact download, and rejects an unsupported `.exe` file.

Run: `AirBenchNodeValidation-20260906-173337-4902af3ae5ef4d5aa4239c8e5211d9d3`

The run passed local and pinned internal HTTPS connection handshakes, event replay, query-upload intake, source-hash comparison, untrusted taint preservation, safe preview metadata, artifact hash verification, denied artifact download, and unsupported-document rejection. The fixture produced redacted JSONL logs under the run directory and retained the limitation that it is not a packaged desktop or production Python Node proof.

The fixture parses only the multipart envelope needed to receive the bytes. It does not interpret document instructions or execute content. It is not the production File Intake Layer.

The packaged Tauri smoke suite now drives the same trust boundary with IPC mocks. The test builds the WebDriver binary, launches the packaged debug executable through external `tauri-driver`, connects an approved profile, uploads a selected scanned-document fixture, renders the Node-generated safe preview with `untrusted` taint, renders the bounded artifact preview, and exercises the Node-authorized download receipt. This is one packaged UI path, not a complete FE-VAL-4 pass.

## Remaining acceptance evidence

- packaged Tauri native-picker run under WebDriver;
- packaged artifact download UI and allowed or denied download assertions;
- real Python File Intake Layer and artifact service contracts;
- corrupted, oversized, interrupted, and clearance-mismatch cases;
- malicious preview-link and macro-bearing artifact tests;
- screenshot and ledger packet from the approved internal Node environment.
