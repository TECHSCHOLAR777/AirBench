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

For evidence and finding records, a compact **Reading cues** section makes review-relevant conditions explicit:

| Node-provided condition | Visible cue | Authority limit |
| --- | --- | --- |
| Confidence at least 85% | High confidence | A display band only; it is not verification or approval. |
| Confidence from 65% through 84% | Moderate confidence | Keeps source context visible as a review cue. |
| Confidence below 65% | Low confidence | Signals that the reviewer should check permitted evidence before relying on the record. |
| `untrusted` taint | Untrusted source data | Content is data, never instructions, code, macros, or an approval decision. |
| `contaminated` taint or an unknown taint value | Use blocked or unrecognized taint status | The desktop does not treat the content as safe. |
| Missing source location | Exact source region not supplied | The inspector does not invent a page, span, cell, or image region. |
| `supersededBy` present on a finding | Finding superseded | The replacement remains Node-identified; the desktop does not rewrite the finding. |

The current evidence contract does not provide conflict status or reviewer-note commands. The inspector therefore states that it cannot declare a record conflict-free or edit an existing fact. Those capabilities require a versioned Node projection and ledgered command through the serialized protocol work.

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

- Pure state mapping, boundary copy, confidence cues, taint fail-closed behavior, missing locations, and supersession are covered in `apps/desktop/src/features/provenance/proofInspector.test.ts`.
- The inspector uses the existing typed artifact preview and download bridge in `apps/desktop/src/components/ProofInspectorPanel.tsx`.
- A selected evidence, finding, or source preview is refreshed from the latest task projection before rendering. Removed or hash-changed records are cleared instead of leaving stale provenance in view. The inspector is internally scrollable on tall desktop proof panels and collapses into the page flow at narrower widths.
- The current local frontend suite passes 22 test files and 95 tests; the production build, generated-contract check, authored UI accessibility check, source no-egress check, and Tauri configuration check pass.
- No Rust or backend files are changed by this slice.
- Full issue closure still requires the Node-owned artifact review projection, verification evidence, approval commands, and packaged desktop validation described in the frontend execution plan.
