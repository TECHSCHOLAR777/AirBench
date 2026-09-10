# Frontend Execution Plan

## Purpose

This is the working delivery plan for the first-release AirBench desktop application. It turns the open frontend issues into safe implementation lanes without letting the React application invent Node authority, provenance, approval, routing, or file interpretation.

The plan is intentionally honest about two kinds of work:

- **Buildable presentation work** consumes an existing typed Node or Rust bridge contract and can be implemented and tested locally.
- **Contract-blocked work** requires a new Node-owned, versioned, clearance-aware projection or command. It must not be represented by a decorative control or local mock state.

## Current foundation

The local desktop foundation already covers the initial shell and connection path:

- #73, #74, #75, #76, #77, and #78 provide the Tauri shell, approved Node profile path, typed task create and plan commands, cursor-aware task projection, and a non-optimistic stop request.
- #106, #107, and #110 provide the Obsidian Signal and Ledger Paper shell, compact Launchpad, audit-safe Live Work Trace, local workspace command menu, and truthful empty task workspace state.
- #81 and #82 now also provide truthful pre-contract gateways for Review, Artifacts, History, and Audit. They do not confuse an absent Node query with an empty queue, library, history, or ledger.
- #65 through #67 have local fixtures or real Python Node checks. They remain open until their production evidence gates are met. The packaged release evidence formerly split across #64, #68, #69, and #85 is consolidated in #124.

The Tauri debug shell may be used for local smoke tests. It is not evidence of a packaged installer, WebDriver flow, or full no-egress proof.

The implementation portions of #73, #75, #76, #77, #78, #79, #107, #109, and #110 are closed with local evidence. Their remaining target, generated-deliverable, packaged, and independent-observation gates are tracked by the validation issues and [#123](https://github.com/TECHSCHOLAR777/AirBench/issues/123). Closing an implementation issue does not waive those gates.

## Local shell-command boundary

The #107 command menu is deliberately constrained to local presentation actions. It can focus a new brief, navigate to an already-projected task, open Node settings, or open Display preferences. It cannot create a task, send a model request, route work, download an artifact, approve or stop work, or alter Node state. Any future consequential command requires a typed Rust-owned Node contract, permission result, idempotency behavior, and ledger evidence before it can appear in this menu.

## Delivery lanes

### Lane A: evidence and artifact proof, current user-visible work

| Issue | Build now | Explicit limit | Primary files |
| --- | --- | --- | --- |
| #79 FE-DEV-07 | Implemented. Render Node-projected evidence and facts with source, confidence, clearance, taint, location, derivation, supersession, and ledger identity. Reuse the safe preview already returned through Rust when a permitted preview exists. | Qualified scan extraction, exact production regions, and local vertical evidence remain in #67 and #123. | `apps/desktop/src/components/ProofInspectorPanel.tsx`, `apps/desktop/src/features/provenance/proofInspector.ts`, `apps/desktop/src/app/App.tsx`, tests, styles |
| #80 FE-DEV-08 | Open Node-generated artifact previews and controlled downloads through the existing Rust bridge. Distinguish read-only Node-returned content from an approved deliverable, and show download permission as a Node decision before the local save receipt. | Artifact status, verification breakdown, deterministic value bindings, approval, return, comparison, and clarification need a typed artifact-review projection and command contract. | same proof components, `intakeBridge.ts`, tests, styles |
| #109 FE-REF-05 | Implemented. Compose the evidence and artifact surfaces into an adaptive, keyboard-accessible right-side proof inspector. | Final artifact-review projection, approval state, and production preview evidence remain in #80, #111, and #123. | same proof components, docs, visual tests |

This lane is serialized because it shares the task workspace, safe-preview presentation, and proof component files.

### Lane B: question and intervention presentation

| Issue | Build now | Blocked contract |
| --- | --- | --- |
| #108 FE-REF-04 | Render an accessible, anchored, read-only Node question card from the current unresolved-question projection. It identifies the preserved Node task state, ledger head, synchronization state, and unavailable action rather than inventing an answer form. The card is a labeled region with a bounded live announcement, so question content is not repeatedly read as status. | A versioned question object with options, authority, deadline, continuation policy, clearance-safe text, expected task sequence, and `task.answer_question`, pause, resume, or revision command availability. |

The first interactive answer control starts only when the Node exposes its typed and ledgered command. The UI may never turn a free-text response into a task transition by itself.

### Lane C: records and administration

| Issue | Required Node projection before implementation | Why it is serialised |
| --- | --- | --- |
| #81 FE-DEV-09 | Until the query exists, render a truthful gateway that identifies the missing clearance-filtered review or artifact projection and offers only local navigation. If the current task projection is resynchronizing or blocked, the gateway must not present its context as current. Full implementation needs a clearance-filtered review queue and artifact-library query plus policy-controlled actions. | Queue membership, authority, and artifact visibility are Node policy decisions. |
| #82 FE-DEV-10 | Until the query exists, render a truthful gateway that identifies the missing history or ledger projection and offers only local navigation. Full implementation needs paged task-history, ledger query, chain verification, and offline export contracts. | The client must not create a second audit store or export reconstructed local records. |
| #83 FE-DEV-11 | Render the existing verified handshake as connection proof: approved profile, Node identity, authenticated operator, clearance, domain-pack reference, transport, protocol, and handshake ledger reference. Show hardware, sandbox, workload, qualification, and router detail as explicitly not supplied until the Node projection exists. Full implementation needs node health, qualified capability catalog, identity, and policy projections. | The UI must not infer health, qualification, model roster, or sovereignty. |

These are parallel only after the shared generated contracts are accepted. They must have separate files and worktrees. Contract changes are serialized through #74.

### Lane D: validation and release hardening

| Issue | Work that can proceed now | Final blocker |
| --- | --- | --- |
| #65 FE-VAL-2 | fixture-based approved-profile and trust behavior | packaged run against the real Node identity path |
| #66 FE-VAL-3 | deterministic projection, duplicate, gap, replay, and resync tests | packaged reconnect evidence against a live authoritative event stream |
| #67 FE-VAL-4 | native picker, safe preview, hash and clearance tests | real File Intake and artifact service plus negative corpus and packaged evidence |
| #124 FE-RELEASE-01 | offline WebView2, provisioned WebDriver, packaged critical flow, accessibility smoke, and independent no-egress capture | clean supported release environment with #123 and the independent transport/intake evidence |
| #84 FE-DEV-12 and #111 FE-REF-06 | component failure, explicit recovery guidance, keyboard, contrast, reduced-motion, and static visual-baseline harness work | all first-release screens and packaged desktop evidence |

## Shared contract queue

The following contracts are not frontend-owned and must be introduced through the serialized protocol work in #74 and its follow-up contract work, with matching Python, Rust, generated TypeScript, and replay tests:

1. `EvidenceProjection` with Node identity, protocol version, clearance context, integrity reference, evidence, facts, source preview references, and redaction reasons.
2. `ArtifactReviewProjection` with version, status, verification, deterministic values, calculation references, permitted preview and download references, approval blocking reasons, and ledger identity.
3. `TaskQuestionProjection` and its bounded answer or intervention commands, including expected sequence and idempotency behavior.
4. Clearance-filtered review queue, artifact library, history, ledger, health, qualification, and router-detail projections.

The React client must never call the corresponding Python routes directly. Every new read or command travels through a Rust-owned allowlisted Tauri command and is validated before it reaches the webview.

## Execution order

1. The view-only proof inspector and current safe source-preview pathway for #79 and #109 are implemented. #80 remains open for the real artifact-review projection. Preview state, download state, and artifact approval state stay separate.
2. Add a truthful unavailable question-card state for #108, without a response input or false action.
3. Add focused failure, keyboard, contrast, reduced-motion, and no-egress tests as the components land. This contributes to #84 and #111 but does not close either issue.
4. Keep the packaged-driver and release harness work isolated from user-visible work; its acceptance is tracked in #124.
5. Extend shared Node contracts only after their owner accepts the field definitions and compatibility tests. Then implement #81, #82, #83, full #108, and full #80 in parallel by disjoint directory.
6. Run the serial packaged validation path #65 through #67, #84, #111, and #124 after the functional work is integrated.
7. Run #123 before packaged release work so the first local desktop vertical slice is proven against the real Python Node.

## Completion evidence

Every implementation update records the issue, environment, exact command, fixture or input hash, observed outcome, screenshot or local log where safe, and remaining limitation. A UI screen is not closed merely because it renders. It needs the relevant typed Node contract, failure-path coverage, no-egress review, and desktop evidence required by its issue.
