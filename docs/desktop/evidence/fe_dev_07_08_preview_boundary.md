# FE-DEV-07 and FE-DEV-08: Preview and download boundary

## Purpose

This slice makes the evidence and artifact inspector honest and understandable for a non-technical reviewer. It exposes the current Node-returned preview path without implying that a preview is the original file, a verified deliverable, or an approval decision.

The slice supports #79, #80, and the proof-inspector composition in #109. It is a frontend presentation change only. The Node remains authoritative for document intake, clearance, taint, artifact status, verification, approval, and download permission.

## User-visible contract

When an artifact is selected, the inspector communicates three separate states:

1. Preview state: whether the desktop has requested a preview, is waiting for the Node, received one, or could not receive one.
2. Preview trust boundary: returned content is read-only presentation data, remains untrusted data, and is not the original document or an approval decision.
3. Download state: the desktop requests a permitted download from the Node. A local save receipt is shown only after the typed bridge returns it.

Clearance, taint, and ledger identity remain in the proof details. The inspector does not manufacture a filename, source location, verification result, deterministic value, approval status, or model decision.

## Preview state mapping

| Typed state | Visible state | Meaning |
| --- | --- | --- |
| `idle` | Preview not requested | No content is displayed because the preview request has not started. |
| `loading` | Requesting a read-only preview | The approved Node is preparing content. The desktop does not open the original file. |
| `ready` with preview | Read-only Node preview | The displayed blocks came from the Node and are not an approval or verification result. |
| `ready` without preview | Preview not supplied | The current Node projection did not provide safe preview content. |
| `failed` | Preview unavailable | The request failed closed. The original document remains unopened by the desktop. |

## Download state mapping

| Typed state | Visible state | Meaning |
| --- | --- | --- |
| `idle` | Request permitted download | The action sends a request to the Node. Permission is not presumed. |
| `downloading` | Checking download permission | The Node decides whether the copy may be returned and saved. |
| `downloaded` | Download saved | The typed bridge returned a download receipt and the desktop saved the permitted copy. |
| `failed` | Download not completed | The Node denied the request or the local save did not complete. |

## Security and authority boundary

- Preview content is rendered as text and is never interpreted as instructions, HTML, Office markup, or executable code.
- The webview calls no model endpoint, file parser, arbitrary URL, or backend route directly.
- The desktop does not infer approval from a successful preview or from a download receipt.
- The desktop does not calculate or rewrite deliverable values.
- The Node and its Rust-owned bridge provide clearance, taint, provenance, and ledger references.
- Missing artifact-review fields remain visibly unavailable until a versioned Node projection supplies them.

## Implementation evidence

- Pure state mapping and boundary copy are covered in `apps/desktop/src/proofInspector.test.ts`.
- The inspector uses the existing typed artifact preview and download bridge in `apps/desktop/src/components/ProofInspectorPanel.tsx`.
- No Rust or backend files are changed by this slice.
- Full issue closure still requires the Node-owned artifact review projection, verification evidence, approval commands, and packaged desktop validation described in the frontend execution plan.
