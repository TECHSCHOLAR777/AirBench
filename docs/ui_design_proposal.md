# AirBench Workbench UI Design Proposal

Status: design proposal, no product implementation started from this document.

This proposal defines the desktop experience for AirBench. It is designed for a non-technical employee who needs to give AirBench a sensitive task, understand what is happening, review the evidence, and receive a real deliverable. It also gives reviewers, operators, and auditors the depth they need without forcing ordinary users to think in terms of models, containers, GPU memory, or agent loops.

The design is for the actual AirBench problem: confidential industrial and government knowledge work, scanned and multimodal inputs, local knowledge, multi-step execution, deterministic verification, human review gates, model routing, and proof that the work stayed inside the organization's network.

## 1. Product decision

AirBench should be a desktop workbench, not a chat page wrapped around a model endpoint.

The application has three visible layers:

1. **Work**: start a task, follow progress, answer questions, and receive deliverables.
2. **Proof**: inspect sources, confidence, clearance, calculations, verification, and the signed audit trail.
3. **Administration**: connect to the AirBench Node, inspect hardware and qualified models, and manage user and policy settings.

The default screen keeps the user in the Work layer. Proof is always one deliberate click away. Administration is available to operators and administrators, but does not clutter the task experience.

The design language is **quiet industrial confidence**:

- a dark navy navigation shell;
- a light paper-like work surface for documents and task work;
- teal for trusted or completed states;
- blue for active information and evidence;
- amber for attention and review;
- red only for stop, failure, or destructive actions;
- restrained borders, generous spacing, and clear hierarchy instead of decorative gradients or consumer-chat effects.

The visual goal is the confidence of a professional operations application, with the clarity of Claude or Codex, while making AirBench's accountability and sovereignty visible.

## Simplification decision

The first proposal exposed too much of the internal system in the ordinary path. The revised UI is task-first:

- Home contains one outcome composer, a short Continue work list, a review reminder, and a quiet node status line.
- Plan, Activity, Sources, and Technical are modes or drawers inside one Task Workspace.
- Projects are filters and groupings, not a permanent navigation destination.
- GPU capacity, model roster, worker details, and ledger metrics move behind administration or technical detail.
- The production shell does not duplicate navigation with a second row of screen tabs. The prototype HTML keeps a small local view switcher only so the representative states can be inspected.
- Repeated records use rows and dividers. Cards are reserved for decisions, previews, and bounded interactive fields.
- Exact model names and internal role names are progressive disclosure, not default copy.

This makes AirBench feel like a serious work application instead of an AI control dashboard while preserving the proof surfaces that make the product defensible.

## 2. Updated UI stack

### 2.1 Chosen stack

| Layer | Decision | Reason |
| --- | --- | --- |
| Desktop shell | Tauri 2 with Rust | Small offline distributable, native OS integration, explicit capability permissions, and a narrow security boundary around the webview. |
| UI | React 19 with TypeScript | Strong ecosystem for dense application interfaces, document work, streaming state, and accessible component composition. |
| Build | Vite | Fast local development and a static production bundle with no Node runtime shipped to users. |
| Accessible primitives | React Aria | Keyboard, focus, dialog, menu, listbox, tabs, and grid behavior without coupling AirBench to a visual component library. |
| Styling | CSS Modules plus AirBench design tokens | Keeps styling local and intentional. Tokens make the shell, status semantics, spacing, and density consistent. |
| Event state | Typed event store using `useSyncExternalStore` and reducers | The UI rebuilds projections from server events and snapshots. It does not invent authoritative task state. |
| Request cache | A small typed request layer, with TanStack Query only where request caching is useful | Avoids introducing a second source of truth for the task event stream. |
| Large lists | TanStack Virtual | Needed for task history, ledger events, evidence lists, and large project inventories. |
| File and document preview | Safe, local preview artifacts supplied by the AirBench Node, including PDF or image previews | Prevents the webview from becoming a second file parser and keeps uploaded content in the File Intake Layer. |
| UI tests | Vitest, React Testing Library, accessibility checks, and Tauri WebDriver tests | Covers rendering, interaction, keyboard behavior, reconnect behavior, and the shipped desktop shell. |
| Backend connection | Rust-owned, typed, allowlisted transport to AirBench Node | The UI never calls vLLM, NVIDIA NIM, a model endpoint, an arbitrary URL, or a cloud service. |

The production frontend is a static bundle. There is no Node server in the shipped application. The Python AirBench Node remains authoritative for orchestration, routing, tools, verification, provenance, clearance, and the ledger.

### 2.2 What is deliberately not the main workbench stack

- **Astro** remains a good choice for a public landing page or product documentation site, but not for the live workbench. The workbench is dominated by streaming state, task transitions, evidence panels, document review, and keyboard-heavy interaction rather than static content islands.
- **Electron** is the fallback if system webview consistency becomes a hard blocker. It is not the default because the bundled runtime and Node-capable main process create a larger shipped security surface.
- **Flutter, Qt/PySide, WinUI, Avalonia, and Wails** are credible desktop technologies, but each introduces another primary language or UI ecosystem without solving a current AirBench requirement better than Tauri plus React.
- **A large generic component kit** should not define the product. Use accessible primitives and build AirBench-specific components so evidence, provenance, clearance, and review states are first-class concepts.

### 2.3 Offline and sovereignty requirements for the UI

- All fonts, icons, JavaScript, CSS, and preview workers are packaged locally.
- No CDN, analytics, crash upload, remote image, external link, or font request exists in the production bundle.
- The webview has a restrictive content security policy and cannot navigate to arbitrary origins.
- Tauri capabilities expose only the commands required by the current application surface.
- A remote GPU server is still an internal AirBench Node. The application connects to its pinned internal endpoint over the organization's private network, never to the public internet.
- The UI shows the node's last sovereignty check and connection state, but this visual is not treated as proof by itself. The signed ledger and network controls remain authoritative.

## 3. Users and default behavior

### 3.1 User roles

| Role | Main need | Default surfaces |
| --- | --- | --- |
| Requestor | Ask for an outcome and receive a usable result | Home, New Task, Live Task, Review, Artifacts |
| Technical reviewer | Inspect sources, calculations, uncertainty, and verification | Live Task, Evidence, Review, Task History |
| Approver | Make an authority-bound release decision | Review Queue, Review Artifact, Approval detail |
| Node operator | Keep the local execution environment healthy | Node Status, Model Roster, Connection settings |
| Auditor | Reconstruct what happened and verify the record | Audit Ledger, Task History, Artifact provenance |
| Administrator | Manage users, clearance, domain packs, policies, and retention | Settings, Administration |

The same person may have several roles, but the UI never infers authority from a display name. Clearance and permitted actions come from the AirBench Node.

### 3.2 Non-technical default

The user begins with a plain outcome prompt:

> “Read the scanned Unit 4 inspection report, identify the findings that need management attention, check them against the maintenance SOP, and prepare an approval note as a Word document.”

The interface asks only for information needed to scope the task. Technical details such as model identity, worker count, scheduling mode, and GPU memory are progressive disclosure. They are available to inspect, but never required for an ordinary task.

The user can always see:

- what AirBench is doing now;
- what it has found;
- what needs human attention;
- whether the task is blocked or waiting;
- which evidence supports a finding;
- what can be approved or downloaded;
- whether the node is connected and healthy.

## 4. Application shell and navigation

### 4.1 Desktop shell

The shell has four persistent areas:

1. **Left rail**: primary navigation and the connected-node chip.
2. **Top bar**: breadcrumb, current project or task, sovereignty status, notifications, and the command menu.
3. **Work surface**: the current screen, with one clear primary action.
4. **Optional detail drawer**: sources, provenance, policy explanations, event details, or technical information.

The left rail is grouped as:

**Workbench**

- Home
- New task
- Projects
- Review queue

**Records**

- Task history
- Artifacts
- Audit ledger

**Administration**

- AirBench Node
- Settings

The rail collapses to icons at medium width and becomes a compact drawer on a narrow window. A mobile phone layout is not a target. The responsive requirement is a usable small desktop or tablet-sized operator window.

### 4.2 Global controls

- `Ctrl/Cmd + K`: command menu.
- `Ctrl/Cmd + N`: new task.
- `Esc`: close a drawer, dialog, or command menu.
- `Ctrl/Cmd + Enter`: submit a valid task request from the composer.
- A visible connection status: `Node ready`, `Reconnecting`, `Offline`, or `Blocked`.
- A visible sovereignty status: `External network denied`, `Check required`, or `Unknown`.

Every global status uses text and iconography, not color alone.

## 5. Screen inventory

The following is the complete first product screen set. The screens marked **MVP** are required for the first convincing end-to-end demonstration. The remaining screens are still part of the product design, but can be delivered after the vertical slice.

| ID | Screen | Priority | Primary user question |
| --- | --- | --- | --- |
| S00 | Connect AirBench Node | MVP | “Which trusted execution node am I using?” |
| S01 | Home | MVP | “What can I start or review now?” |
| S02 | New Task and Intake | MVP | “What outcome and files should AirBench work on?” |
| S03 | Task Plan Review | MVP | “What will AirBench do, and what authority does it need?” |
| S04 | Live Task Control Room | MVP | “What is happening, and is progress healthy?” |
| S05 | Evidence and Sources | MVP | “Why does AirBench believe this?” |
| S06 | Review Queue | MVP | “Which deliverables need my decision?” |
| S07 | Artifact Review | MVP | “Is this deliverable correct and ready to release?” |
| S08 | Artifact Library | First release | “Where are my approved and draft outputs?” |
| S09 | Task History | First release | “What happened to previous work, and can I inspect it?” |
| S10 | Audit Ledger | First release | “Can I prove what the system did?” |
| S11 | AirBench Node and Model Roster | First release | “Is the local execution environment ready and qualified?” |
| S12 | Settings and Identity | First release | “What are my permissions, preferences, and connection settings?” |
| S13 | Domain Pack Administration | Later | “Which field rules, templates, and risk mappings are active?” |
| S14 | Recovery and Blocked States | MVP behavior | “What failed, what is safe, and what can I do next?” |

## 6. Detailed screen proposals

### S00. Connect AirBench Node

This is the first-run and recovery entry point. It is not a server discovery screen that probes arbitrary addresses.

**Layout**

- AirBench mark and short sovereignty statement.
- A connection profile selector containing only administrator-provided profiles.
- Node identity, pinned certificate or trust status, and organization name.
- A four-step readiness sequence: endpoint trust, authenticated connection, ledger availability, sovereignty check.
- A small “technical details” disclosure with endpoint identity and checksums.

**Actions**

- Connect to approved profile.
- Recheck node.
- Open administrator connection settings.
- Continue offline to review cached records, if policy permits.

**Rules**

- The user cannot type an arbitrary URL into the normal flow.
- Credentials and certificates are handled by the Rust boundary or approved OS credential storage, not browser local storage.
- A failed sovereignty check blocks task submission and explains the reason plainly.

### S01. Home

Home is the calm operational starting point. It should feel like a capable workbench, not a metrics dashboard.

**Primary region**

- Greeting and a large task composer with the prompt: “Describe the outcome you need, not the steps.”
- Attach files.
- Choose project.
- Optional “Use a template” entry for recurring work.
- Primary action: `Start task`.

**Secondary region**

- Recent work with status, project, last activity, and next action.
- Review queue count with the highest priority item.
- Node readiness: connection, GPU capacity, qualified model count, and last sovereignty check.

**Empty and degraded states**

- No previous tasks: show one realistic example and a `Start your first task` action.
- Node offline: keep history and drafts available, disable new execution, explain how to reconnect.
- Review pending: make it a first-class action, not a red notification badge hidden in a corner.

### S02. New Task and Intake

New Task is a guided intake flow. It prevents the user from having to understand the agent protocol while preserving the complete manifest and policy state in the backend.

**Step 1: Outcome**

- Outcome prompt.
- Project and task title.
- Desired deliverable type: Word, PowerPoint, Excel, code, calculation, or answer with sources.
- Optional deadline or priority.

**Step 2: Sources**

- Files selected through the desktop picker.
- Local knowledge sources or project sources.
- File cards showing name, type, size, clearance compatibility, and intake status.
- Clear warning: uploaded and ingested documents are data, not instructions.
- No preview parser runs in the UI. The File Intake Layer creates the manifest and safe previews.

**Step 3: Execution preferences**

- “Let AirBench choose the execution team” as the default.
- A simple risk preference only where the domain pack permits it, for example `Draft for review` versus `Prepare for release review`.
- Optional deadline and notification preference.
- No raw model picker in the normal flow.

**Finish state**

The Node returns a task summary and proposed plan. The user moves to S03 before execution when the task requires plan review. A low-risk task may enter execution immediately only when the autonomy policy permits it.

### S03. Task Plan Review

This screen makes multi-agent execution understandable without pretending that the model controls the plan.

**Main layout**

- Task outcome and input manifest at the top.
- A visual plan with stages and dependencies.
- Worker role cards such as `Research`, `Vision`, `Drafting`, and `Verification`.
- A compact execution mode label: `Parallel`, `Pipeline`, or `Serial virtual team`.
- A hardware note explaining when the team is serialized because of available GPU capacity.
- Risk and required authority panel.
- Expected deliverables and required evidence.

**Progressive technical detail**

- Capability lanes are shown by default, for example `vision`, `reasoning`, `coding`, and `verification`.
- The exact selected model, backend, qualification record, and fallback path are available under `Technical routing details`.
- The user cannot override a routing decision with an unqualified model.

**Actions**

- Approve plan and run.
- Edit outcome or sources.
- Ask for a smaller scope.
- Cancel.

The plan shown here is the orchestrator's server-authoritative plan. It is not a model-generated promise that the UI treats as truth.

### S04. Live Task Control Room

This is the central AirBench experience. It should make a complicated task feel understandable and accountable.

**Header**

- Task title, project, status, elapsed time, and current phase.
- `Pause`, `Stop`, or `Resume` according to the state.
- Connection and event-stream status.

**Main column: execution timeline**

- Server events grouped by stage.
- Completed, active, queued, blocked, and failed states.
- Short human-readable summaries, not raw model transcripts.
- Expand an event to see tool name, inputs and outputs by reference, model capability lane, duration, and ledger event ID.

**Right column**

- Team roster and worker roles.
- Parallel versus serialized execution indicator.
- Evidence count and verification count.
- Questions waiting for the user.
- Deliverables as they become available.

**Important interaction**

The UI consumes snapshots plus ordered events with a cursor. On reconnect it requests the missing range or a fresh snapshot. It never guesses that a worker completed because a request timed out.

### S05. Evidence and Sources

Evidence is not a footnote hidden below the answer. It is a first-class work surface.

**Three-pane layout**

1. Source list: files, knowledge-base entries, page numbers, and source hashes.
2. Safe preview: page, image, table, or OCR region supplied by the Node.
3. Fact detail: extracted value, source region, confidence, clearance, taint, timestamp, derivation, conflicts, and ledger reference.

**Interactions**

- Select a finding and jump to the exact source region.
- Show competing findings side by side when sources disagree.
- Filter by low confidence, unresolved conflict, clearance, or verification status.
- Open the task event that created or transformed the fact.
- Add a reviewer note as a new auditable annotation. Never silently edit the underlying fact.

**Safety**

- Source content is displayed as data in a safe preview surface.
- The UI never executes embedded scripts, macros, links, or instructions from a document.
- Any redaction or clearance decision is represented explicitly.

### S06. Review Queue

The Review Queue is the approver's inbox. It is separate from Task History because “needs a decision” is an actionable state.

**List columns**

- Priority.
- Deliverable and task.
- Requestor and project.
- Review reason.
- Confidence and unresolved issues.
- Required authority.
- Age and due date.

**Filters**

- Assigned to me.
- Clearance compatible.
- Waiting for evidence.
- Ready for decision.
- Returned for revision.

Each row opens S07 at the exact review state. A reviewer can approve, return with a reason, or request clarification. Each action is recorded in the ledger.

### S07. Artifact Review

Artifact Review is the release gate for Word, PowerPoint, Excel, code, calculations, and other deliverables.

**Layout**

- Left: document outline, files in the deliverable set, and attention markers.
- Center: rendered preview with page, slide, sheet, or code navigation.
- Right: evidence, verification, calculated values, clearance, and review checklist.
- Bottom action bar: `Approve`, `Return for changes`, `Request clarification`, and `Download draft` where permitted.

**Deliverable-specific behavior**

- Word: page preview, source links, comments, and version history.
- PowerPoint: slide sorter, speaker notes, source links, and layout warnings.
- Excel: sheet tabs, formula display, computed values, cell provenance, and recalculation status.
- Code: file tree, diff, test result, sandbox run, and approval status. Do not present unverified code as ready to deploy.
- Calculations: inputs, deterministic steps, units, assumptions, and verification result.

Numbers are displayed from deterministic fields and formulas. The UI may show model-written prose that refers to a value, but it must not accept a model-written number as the authoritative value.

The approval button is disabled when required evidence, verification, clearance, or authority is missing. The reason is shown next to the disabled action.

### S08. Artifact Library

Artifact Library is the durable output surface, not a generic file browser.

**Views**

- Grid for visual deliverables.
- List for documents and code packages.
- Table for audit-heavy environments.

**Metadata shown**

- Artifact title, type, version, project, status, clearance, creator, task ID, created time, and hash.
- Draft, review required, approved, superseded, or blocked status.
- Source and verification summary.

**Actions**

- Open review.
- Compare versions.
- Download when clearance allows.
- Open provenance.
- Archive through a policy-controlled action.

The library does not delete authoritative records from the UI. Retention and destruction remain policy-controlled and auditable.

### S09. Task History

Task History helps a user find previous work without exposing a misleading chat transcript as the system of record.

**List**

- Task name, project, requestor, status, last phase, last activity, deliverables, and review state.
- Search across task title and permitted metadata.
- Filters for status, project, date, owner, and clearance.

**Task detail**

- Original request and input manifest.
- Plan version history.
- Event timeline.
- Evidence and artifact links.
- Failure or pause explanation.
- Resume or clone action only when policy allows it.

Task detail is reconstructed from authoritative snapshots and ledger references. A model summary is a convenience view, never the authoritative history.

### S10. Audit Ledger

Audit Ledger is read-only for ordinary users and is designed for reconstruction, not decoration.

**Summary band**

- Event count.
- Evidence links.
- Signature and chain status.
- Last verification time.

**Event table**

- Time.
- Event type.
- Actor or subsystem.
- Task and artifact reference.
- Model or tool capability where relevant.
- Event ID.
- Hash or chain reference.

**Event detail drawer**

- Canonical event payload.
- Previous-event reference.
- Input and output hashes.
- Clearance and taint state.
- Related source facts.
- Signature verification result.

Exports are generated by the Node and include the verification evidence needed to check them offline. The UI does not generate a substitute audit log.

### S11. AirBench Node and Model Roster

This is the operator-facing infrastructure screen.

**Node health**

- Node identity and connection profile.
- Authenticated transport status.
- GPU inventory, allocated memory, active workloads, and queue pressure.
- Tool sandbox status.
- File Intake Layer status.
- Ledger write and signing status.
- External network policy result.

**Model roster**

- Capability lane: general, reasoning, coding, vision, retrieval, OCR, or verification.
- Model name and version.
- Quantization.
- Context limit.
- Hardware requirement.
- Qualification status and expiry.
- Health and last check.
- Current routing priority.

The roster is inspectable, but the user-facing task flow remains capability-based. The router, not the UI, selects the model.

**Hardware-aware team display**

The screen explains that one GPU may run a multi-worker team serially or as a pipeline. It must not claim parallel compute merely because several worker roles exist.

### S12. Settings and Identity

Settings is split into user settings and administrator settings. Ordinary preferences must not silently change authority or policy.

**User settings**

- Display density and theme.
- Reduced motion.
- Keyboard shortcuts.
- Default project.
- Review notifications.
- Preferred preview behavior.

**Identity and clearance**

- Signed-in identity.
- Current clearance and organization.
- Allowed projects and domain packs.
- Session expiry.
- Device trust state.

**Connection settings**

- Approved node profiles.
- Certificate or trust details.
- Reconnect behavior.
- Offline cache policy.

**Administrator settings**

- Retention and export policy.
- Allowed tools.
- Review authority mappings.
- Model qualification policy.
- Domain pack versions.

Sensitive changes require an explicit confirmation and are recorded in the ledger.

### S13. Domain Pack Administration

This screen is not visible to ordinary users. It makes the core versus domain-pack boundary visible to authorized administrators.

**Pack overview**

- Pack identity and version.
- Contract compatibility with the core engine.
- Task kinds supported.
- Risk mappings and required authority levels.
- Verification rules.
- Templates and artifact schemas.
- Retrieval source collections.
- Pack test and qualification status.

The screen must never encourage administrators to add sector assumptions to the core engine. Domain knowledge is edited and versioned behind the pack contract.

### S14. Recovery and Blocked States

These are designed states, not toast messages.

Required states include:

- Node offline.
- Reconnecting to the event stream.
- Event gap requiring resynchronization.
- Model unavailable with deterministic fallback.
- Hardware queue or insufficient capacity.
- File rejected by intake policy.
- Clearance mismatch.
- Low-confidence evidence requiring review.
- Conflicting sources.
- Verification failure.
- Sandbox failure.
- Ledger write failure.
- Approval blocked by missing authority.
- Artifact render failure.

Every state contains:

1. What happened in plain language.
2. Whether the task is safe to pause, retry, or stop.
3. What AirBench has preserved.
4. The next permitted action.
5. A technical detail disclosure for operators.

No retry button may blindly repeat a consequential action. The Node decides whether the operation is idempotent and whether retry is permitted.

## 7. Shared components that make the product coherent

These should be designed before individual screens are implemented.

### 7.1 Provenance strip

Every fact, finding, calculated value, or evidence-backed claim has a compact provenance strip containing:

- source;
- confidence;
- clearance;
- taint state;
- timestamp;
- derivation or calculation reference;
- ledger event reference.

The compact form appears in lists. The expanded form opens in a detail drawer. There must be no component that renders a fact without a provenance path.

### 7.2 Status vocabulary

Use a shared vocabulary across all screens:

- `Queued`
- `Running`
- `Waiting for you`
- `Waiting for capacity`
- `Needs review`
- `Verified`
- `Approved`
- `Returned`
- `Blocked`
- `Failed`
- `Stopped`
- `Archived`

Do not use “done” when the work is only drafted or awaiting approval.

### 7.3 Trust and security indicator

The top bar shows a concise status. Selecting it opens the actual Node-provided evidence:

- node identity;
- transport trust;
- last external-network check;
- ledger signing status;
- current connection time;
- any unresolved warning.

The indicator is never a decorative green badge with no underlying evidence.

### 7.4 Review gate

The review gate is shared by documents, spreadsheets, slides, code, and calculations. It checks:

- required evidence;
- clearance;
- verification;
- required authority;
- unresolved conflicts;
- render status;
- artifact version.

### 7.5 Source drawer

The source drawer is opened from a finding, paragraph, cell, slide element, or code line. It shows the exact source region and provenance. It is not a generic “citations” popover.

### 7.6 Command menu

The command menu is local and permission-aware. It can navigate to tasks, start a new task, open the review queue, reconnect the node, open the ledger, or show keyboard help. It must not become a hidden route around approval policy.

## 8. Visual system

### 8.1 Tokens

The initial light theme uses these roles:

| Role | Token direction | Meaning |
| --- | --- | --- |
| Navigation | deep navy | stable application chrome |
| Ink | dark blue-black | primary text |
| Paper | cool light gray | work surface |
| Surface | white | cards and previews |
| Trust | muted teal | verified, connected, approved |
| Information | steel blue | evidence, active work, links |
| Attention | muted amber | review, uncertainty, waiting |
| Failure | restrained red | stop, error, blocked |

Color is paired with text, icon, shape, and placement. A color-blind user must receive the same meaning.

### 8.2 Typography

- Use a bundled, legally distributable font only if the deployment image includes it. Otherwise use the platform system stack, with Segoe UI on Windows as the primary desktop fallback.
- Body text is optimized for long reading and evidence inspection, not oversized marketing headlines.
- Monospace is reserved for IDs, hashes, code, and technical values.
- Numbers in tables use tabular numerals where available.

### 8.3 Density and spacing

- Base spacing unit: 4 px.
- Primary controls: minimum 36 px height on desktop, 44 px for coarse pointer targets.
- Content column: 1,120 px maximum for review surfaces, with wider layouts for evidence and audit tables.
- Use a 12-column layout only where it materially helps. Do not turn every screen into a dashboard grid.
- Document review should prioritize the document and evidence relationship over decorative cards.

### 8.4 Motion

- Use short transitions for drawers, selection, and task state changes.
- Never animate a security or verification state in a way that suggests activity without an event.
- Respect the reduced-motion preference.
- No typing simulation is used to make model output appear more intelligent.

## 9. State and security contract between UI and AirBench Node

### 9.1 Authoritative state

The Node owns:

- task lifecycle;
- orchestration and worker team state;
- routing decisions;
- tool calls;
- evidence and fact metadata;
- verification results;
- approval requirements;
- artifact versions;
- ledger events.

The UI owns only presentation state:

- selected task or evidence item;
- open drawers and dialogs;
- local layout and density;
- unsent text in a composer;
- scroll position;
- local query filters.

The UI cannot mark a task complete, approve an artifact, rewrite a fact, select an unqualified model, or bypass a clearance decision.

### 9.2 Event stream requirements

The Node API should provide:

- an initial task snapshot;
- ordered events with sequence number and cursor;
- event type and schema version;
- task, project, artifact, and ledger references;
- reconnect and replay from cursor;
- explicit snapshot invalidation or resynchronization response;
- server timestamps;
- permission and clearance context.

Minimum event families exposed to the UI are:

- task accepted;
- plan created or changed;
- worker started or completed;
- tool started or completed;
- evidence added or revised;
- verification completed or failed;
- approval required;
- artifact ready or superseded;
- task paused, stopped, blocked, failed, or completed;
- ledger write or verification status.

### 9.3 Boundary rules

- The UI connects only to the AirBench Node.
- The UI never calls a model server directly.
- The UI never parses a source file outside the File Intake Layer.
- The UI never executes document content, spreadsheet macros, or code.
- The UI never calculates authoritative deliverable values.
- Every user action that changes system state is sent as a typed command and appears in the ledger.
- Every displayed fact keeps source, confidence, clearance, and taint metadata.

## 10. Key user journeys

### 10.1 Scanned inspection report to approval note

1. User opens Home and starts a task.
2. User attaches the scanned report and selects the project.
3. File Intake creates the manifest and safe preview.
4. AirBench shows the plan with vision, retrieval, drafting, and verification roles.
5. User approves the plan if the policy requires it.
6. Live Task shows intake, vision extraction, evidence review, and drafting.
7. Evidence shows page-level findings and confidence.
8. Verification checks facts and required SOP references.
9. Artifact Review shows the Word document, sources, calculations, and unresolved issues.
10. The approver approves or returns the artifact.
11. Artifact Library stores the approved version, and Audit Ledger records the full path.

### 10.2 Coding task

1. User describes the desired internal tool and attaches permitted project context.
2. The plan identifies coding, tool execution, and verification roles.
3. Live Task shows sandbox actions as bounded events.
4. Artifact Review shows the code tree, diff, test output, and security findings.
5. The user receives a code package only after the required checks and approval state pass.

### 10.3 Low-capacity workstation

1. Node Status reports available GPU capacity.
2. Plan Review states that worker roles will run as a serial virtual team or pipeline.
3. Live Task shows the current role and queued roles.
4. The orchestrator preserves the same checks and evidence requirements.
5. The UI never implies that serial execution is a degraded correctness mode.

## 11. Implementation sequence

The design should be implemented as vertical slices, not as a large empty screen catalogue.

### UI-0. Contract and shell spike

- Define typed snapshot, event, command, artifact, evidence, clearance, and error schemas.
- Build Tauri shell, restrictive capabilities, local static bundle, and mock AirBench Node adapter.
- Prove connect, disconnect, reconnect, and event replay.

### UI-1. Home and New Task

- Shell, navigation, node status, task composer, file intake handoff, and plan review.
- Use realistic scanned-report fixtures.

### UI-2. Live Task and recovery

- Server-authoritative timeline, worker roles, parallel or serial display, pause and stop behavior, and reconnect states.

### UI-3. Evidence and Artifact Review

- Source drawer, provenance strip, safe preview, verification checklist, deterministic values, and approval gate.

### UI-4. Records and administration

- Review Queue, Artifact Library, Task History, Audit Ledger, Node Status, Model Roster, and Settings.

### UI-5. Production hardening

- Offline installer and WebView2 validation.
- No-egress test and network monitor evidence.
- Accessibility and keyboard audit.
- Tauri WebDriver coverage.
- Large evidence and ledger list performance.
- Failure injection for node loss, model fallback, intake rejection, ledger failure, and incomplete verification.

No UI screen is complete merely because it renders. Each slice is complete only when it demonstrates the correct contract with the Node, preserves provenance, handles the required failure states, and leaves auditable evidence.

## 12. Acceptance criteria for the product UI

The UI design is accepted when a non-technical user can:

- connect to a trusted local AirBench Node without seeing cloud service concepts;
- submit a scanned document task and understand the required inputs;
- see whether the worker team is running in parallel, pipeline, or serial mode;
- follow progress without reading raw model traces;
- open a finding and reach its exact source region;
- see confidence, source, clearance, taint, derivation, and ledger references;
- understand why a human decision is required;
- review a Word, PowerPoint, Excel, code, or calculation artifact;
- distinguish draft, verified, approved, returned, and failed states;
- inspect the model routing and hardware details when needed;
- recover from a disconnected node without duplicated work;
- verify that no external network route was permitted;
- reconstruct the task from the audit ledger.

The first design artifact is the interactive workbench mockup at [`docs/airbench-workbench-mockup.html`](airbench-workbench-mockup.html). It covers the core shell plus Home, Live Task, Artifact Review, Audit Ledger, and Node Status states. This proposal defines the remaining screens and the contracts they must obey.

## 13. Decisions to hold before implementation

These are the only product decisions that should be finalized before UI-0:

1. Primary desktop support target: Windows 10/11 first, with Linux operator support if the deployment requires it.
2. Exact internal Node transport and certificate provisioning model.
3. Whether the first release renders document previews entirely from Node-generated PDFs and images, or also ships a local PDF worker.
4. Which user roles can approve which artifact types in the first domain pack.
5. The initial event and snapshot schema version.

The visual direction, screen map, stack choice, trust model, and boundary between UI and AirBench Node are otherwise settled by this document.
