# FE-REF-02 Launchpad Design and Contract Boundary

## Purpose

The Launchpad is the single entry surface for a new AirBench task. It should feel calm and capable to a non-technical operator while making the work boundary visible:

1. the operator describes a bounded outcome;
2. sources enter through File Intake;
3. the Node validates policy, clearance, authority, and available resources;
4. the Node chooses qualified worker capabilities and returns the task state;
5. later task views show the server-authoritative plan, activity, proof, and decisions.

The Launchpad does not act as a second orchestrator, model router, policy editor, knowledge browser, or tool permission system.

## Visual and interaction structure

The default view has one primary prompt, `What do you want AirBench to complete?`, followed by five compact context controls:

The prompt rests at three visible lines and uses the native textarea scrollbar for longer work briefs. It does not auto-grow the Launchpad or turn prompt length into a status signal. The translucent Launchpad and its focused border are presentation-only hierarchy; they neither claim task acceptance nor change the typed request envelope.

| Control | What it lets the user do now | What remains Node-authoritative |
| --- | --- | --- |
| Sources | Choose a local file, remove it before submission, and send its native selection token to File Intake | Parsing, OCR, image understanding, manifest creation, clearance, taint, safe preview, and source acceptance |
| Deliverable | State the intended artifact type in the existing task-create envelope | Values, calculations, verification, rendering, and final artifact acceptance |
| Auto route | Understand automatic qualified routing and inspect its safe high-level behavior | Capability selection, qualification, fallback, hardware admission, endpoints, and model roster |
| Task details | Provide bounded title, project reference, priority, and optional deadline fields already supported by the envelope | Task risk, autonomy ceiling, tool permissions, concurrency, and plan state |
| Review | Understand that the Node decides whether a plan needs review | Authority, approval requirements, approval acceptance, and ledger recording |

Only one context panel opens at a time. This protects the prompt as the visual center and keeps advanced details close to the decision they explain.

`Launch` is the only primary action. It is disabled until the existing UI readiness rule is satisfied: a verified Node connection, a non-empty outcome, no incomplete selected file, and no pending task-create request. `Ctrl+Enter` or `Cmd+Enter` invokes the same action only when that rule already allows it. It cannot bypass readiness.

## Routing boundary

Auto route is visible because users need to understand that AirBench deliberately matches qualified capabilities to individual steps. It is not a model picker.

The current task-create protocol does not include a Node-supplied, clearance-filtered catalog of qualified capability preferences. Therefore the advanced preference control is deliberately disabled and says why. The desktop client does not transmit a model name, endpoint, URL, credential, GPU setting, or fallback order.

When the routing-preference contract exists, it must meet all of these requirements before this control becomes interactive:

- The Node provides a catalog filtered by identity, clearance, domain pack, policy, qualification, and current availability.
- The client submits only a bounded advisory capability identity, never an endpoint or direct model identifier.
- The Node returns an effective disposition: accepted, narrowed, ignored, queued, or rejected, with a ledger reference.
- The task trace records the selected qualified capability, reason, resource admission, and fallback evidence without exposing model reasoning.

The contract work is tracked with the affected Node and router issues. This frontend slice intentionally does not modify those contracts.

## Knowledge, tools, and review

The Launchpad does not offer free-text knowledge collection names or tool permissions. A free-text selector would allow the client to suggest data access or tools outside the Node's governed catalog. Instead it explains that each requires a Node-provided policy-aware catalog or plan.

Review posture is also explanatory at launch. The Node decides whether the request needs approval after validation. It must record any required human decision in the ledger. A future task question or intervention card requires a typed, sequence-aware Node command and is not simulated in this view.

## File Intake boundary

The only source action in the Launchpad obtains a native file selection token. The original content is not parsed, OCRed, previewed, or interpreted by React. The upload action passes the token and an approved Node profile to the Rust boundary, then to the shared File Intake path. Node-generated manifest and safe-preview information remains visibly identified as untrusted source data.

## Evidence and tests

The implementation has source-level tests for:

- keyboard launch behavior that cannot bypass readiness;
- source status that distinguishes selected, uploading, failed, and File Intake ready;
- unavailable advanced routing preference with and without a verified Node;
- typed task-create compatibility through the existing task composer tests.

The desktop smoke specification also checks the new prompt and that the routing panel exposes a disabled preference rather than a model endpoint. Full desktop execution remains subject to the existing WebDriver service issue tracked in FE-VAL-6. A real clearance-mismatch presentation must wait for a Node response contract that reports the mismatch without leaking forbidden capability metadata.

## Deferred behavior

After a task begins, this screen should become the task follow-up and question response surface. It requires the same server-authoritative, sequence-aware question and response command contract used by the Live Work Trace. That behavior belongs to the intervention and task-trace slices, not a local Launchpad state machine.
