# AirBench Frontend Screen Specification

## 1. Screen map

| ID | Screen | Initial release | Main question |
| --- | --- | --- | --- |
| S00 | Connect AirBench Node | Required | Which trusted execution node am I using? |
| S01 | Home | Required | What can I start or review now? |
| S02 | New Task and Intake | Required | What outcome and files should AirBench work on? |
| S03 | Task Plan Review | Required | What will AirBench do and what authority does it need? |
| S04 | Live Task Control Room | Required | What is happening and is progress healthy? |
| S05 | Evidence and Sources | Required | Why does AirBench believe this? |
| S06 | Review Queue | Required | Which deliverables need my decision? |
| S07 | Artifact Review | Required | Is this deliverable correct and ready to release? |
| S08 | Artifact Library | First release | Where are approved and draft outputs? |
| S09 | Task History | First release | What happened to previous work? |
| S10 | Audit Ledger | First release | Can I prove what the system did? |
| S11 | AirBench Node and Model Roster | First release | Is the execution environment healthy and qualified? |
| S12 | Settings and Identity | First release | What are my permissions and preferences? |
| S13 | Domain Pack Administration | Later | Which field rules, templates, and risk mappings are active? |
| S14 | Recovery and Blocked States | Required behavior | What failed, what is safe, and what happens next? |

## 2. Persistent shell

The shell contains:

- left rail with Workbench, Records, and Administration;
- top bar with breadcrumb, node status, sovereignty status, notifications, and command menu;
- main work surface;
- optional detail drawer for sources, provenance, technical details, or event payloads.

The rail collapses at medium width and becomes a drawer on a narrow desktop window. A phone layout is not a product target.

## 2.1 Simplified information architecture

The primary navigation is intentionally smaller than the complete screen inventory:

```text
Work
  Home
  Tasks
  Review

Records
  Artifacts
  History
  Audit

Administration
  Node and settings
```

Projects are a task filter and grouping, not a permanent destination. New Task is a primary action, not a permanent navigation item. Domain Pack Administration is hidden behind administrator settings.

Plan Review, Live Task, Evidence and Sources, and technical routing are modes or drawers inside the Task Workspace. They should not appear as four equal destinations to a non-technical user.

The prototype view switcher in the HTML mockup exists only to inspect representative states. It is not part of the production shell.

## 3. Screen contracts

### S00 Connect AirBench Node

**User outcome**: connect to an approved internal node or understand why the connection is blocked.

**Content**:

- organization and node identity;
- approved connection profile;
- trust or certificate result;
- authentication result;
- ledger availability;
- last sovereignty check;
- technical detail disclosure.

**Actions**: connect, recheck, open administrator settings, continue to cached records if policy allows.

**Blocked states**: unknown endpoint, trust failure, authentication failure, ledger unavailable, sovereignty check unknown.

**Rules**: no arbitrary URL in the ordinary flow; credentials stay outside the webview; failed trust blocks task submission.

### S01 Home

**User outcome**: start a task or continue work that needs attention.

**Content**:

- outcome-first task composer;
- recent work;
- review queue summary;
- node readiness;
- last sovereignty check.

**Actions**: start task, attach files, choose project, open history, open review queue, open node details.

**States**: first use, node offline, pending review, no recent work, cached-only mode.

### S02 New Task and Intake

**User outcome**: submit a bounded outcome and a complete input manifest.

**Launchpad core**: one compact, scrollable outcome prompt with a concise row of progressive controls for Sources, Deliverable, Auto route, Task details, and Review. The operator should not have to configure implementation details to begin useful work. A long brief scrolls inside the prompt field rather than expanding the task canvas.

**Outcome**: a bounded result request, plus optional project, title, priority, and deadline fields that already exist in the typed task-create envelope.

**Sources**: native file selection, File Intake state, manifest identity, and safe preview availability. Files, OCR, vision, clearance compatibility, and taint remain Node-owned.

**Deliverable**: a non-authoritative intent such as document, summary, spreadsheet, presentation, or code. The Node verifies final deliverables and computes authoritative values.

**Routing and review**: Auto route is always the default. The Node selects qualified capabilities, fallback, resource admission, and review posture after validation. An advanced preference is unavailable until the Node sends a clearance-filtered qualified catalog.

**Knowledge and tools**: only Node-provided governed catalogs can make these interactive. The desktop app does not offer free-text collection names or tool permissions.

**Actions**: add files, remove files before intake commit, choose deliverable intent, add bounded task context, launch, and return to edit.

**Rules**: all files go through File Intake; content is untrusted data; UI does not parse, OCR, or execute it. A keyboard shortcut may invoke Launch only when the same Node readiness rule has enabled the primary action. The UI never sends a direct model name, endpoint, or routing fallback.

### S03 Task Plan Review

**User outcome**: understand and approve the bounded plan before execution when policy requires it.

**Content**:

- task outcome and manifest;
- stage graph and dependencies;
- worker capability roles;
- parallel, pipeline, or serial virtual-team mode;
- hardware reason for serialization;
- risk and required authority;
- expected evidence and deliverables;
- technical routing disclosure.

**Actions**: approve and run, revise outcome, revise sources, request smaller scope, cancel.

**Rules**: Node plan is authoritative; user cannot select an unqualified model or bypass required verification.

### S04 Live Task Control Room

**User outcome**: follow execution and respond to questions without reading raw model traces.

**Content**:

- task status and current phase;
- current Node state and last recorded activity;
- server-authoritative staged work trace: Plan, Work, Evidence, Verification, Review, Artifacts, and Outcome;
- worker roles, tool activity, and plan-level hardware mode;
- source-backed evidence with confidence, clearance, taint, source location, and ledger reference;
- verification summaries and blocked or failed state;
- questions reported by the Node and emerging artifact references;
- stream cursor, reconnect, replay, gap, and connection status;
- collapsed technical trace with event metadata and the Node-supplied routing and hardware context.

**Actions**: stop when the current typed Node command allows it, refresh the projection, open permitted source or artifact paths, and open technical trace detail. Pause, resume, answer-question, source-open, and artifact-open controls appear only after their typed Node command or safe-preview contract exists.

**Rules**: no guessed completion, timer, typing indicator, raw model reasoning, raw event payload, or optimistic stop or approval. Reconnect by cursor replay or snapshot. The desktop shows an unavailable routing target or fallback as not supplied, never as a local estimate.

**Current question state**: a Node-reported question is a labeled, read-only region. Its decision-state title is announced politely and separately from the question content. Options, free-text answers, pause, resume, stop, and revision controls remain absent until the Node provides bounded, sequence-aware commands.

### S05 Evidence and Sources

**User outcome**: trace a finding to its source and understand its reliability.

**Layout**: source list, safe preview, fact and provenance detail.

**Content**: page, span, cell, or region; source hash; fact; confidence; clearance; taint; derivation; conflicts; verification state; ledger reference.

**Actions**: open exact source region, compare conflicts, filter low confidence, add auditable reviewer note, open ledger event.

**Rules**: source is data, not instruction; reviewer notes do not rewrite facts.

**Current preview boundary**: a Node-returned source or artifact preview is labeled read-only before its content is shown. It remains untrusted data and is not the original document, a verification result, or an approval decision. A missing preview is shown as unavailable, never replaced with a client-side interpretation.

### S06 Review Queue

**User outcome**: find deliverables that require an authorized decision.

**Content**: priority, task, project, requestor, review reason, confidence, unresolved issues, authority, age, due date.

**Actions**: open review, filter assigned to me, return, request clarification.

**Rules**: the Node assigns authority and clearance; queue actions are ledgered.

**Pre-contract state**: an absent Node review query is not an empty queue. The screen states that the clearance-filtered queue and ledgered actions have not been supplied, then offers only safe local navigation.

### S07 Artifact Review

**User outcome**: inspect and decide on a real deliverable.

**Layout**: outline and files, rendered preview, evidence and verification panel, approval bar.

**Content**: artifact version, render status, sources, calculated values, checks, conflicts, clearance, review history.

**Artifact variants**:

- Word: pages, source links, comments, version history.
- PowerPoint: slides, speaker notes, source links, layout warnings.
- Excel: sheets, formulas, computed values, cell provenance, recalculation status.
- Code: file tree, diff, sandbox run, tests, findings, approval state.
- Calculations: inputs, units, assumptions, deterministic steps, verification.

**Actions**: approve, return for changes, request clarification, download draft if permitted, compare version.

**Rules**: approval is disabled when required evidence, verification, clearance, or authority is missing. Numbers come from deterministic fields.

**Current desktop slice**: the inspector can present Node-generated preview blocks and can request a permitted download through the typed bridge. The download label explicitly means a Node permission check, and a local save receipt is separate from artifact approval. Artifact status, verification, deterministic values, approval, comparison, and clarification remain unavailable until their Node-owned projection and commands exist.

### S08 Artifact Library

**User outcome**: find durable outputs and their versions.

**Content**: title, type, version, project, status, clearance, task ID, hash, source summary, verification summary.

**Actions**: open, compare, review, download when permitted, open provenance, archive through policy.

**Rules**: the UI cannot silently delete authoritative records.

**Pre-contract state**: an absent Node artifact-library query is not an empty library. The screen states that status, clearance, version, provenance, and actions must come from the Node.

### S09 Task History

**User outcome**: reconstruct earlier tasks and safely resume or clone when permitted.

**Content**: task list, project, requestor, status, phase, deliverables, review state, activity time.

**Task detail**: original request, input manifest, plan versions, event timeline, evidence, artifacts, failures, and policy-permitted recovery actions.

**Rules**: history is rebuilt from snapshots and ledger references, not a model-written summary.

**Pre-contract state**: the desktop does not assemble a local history. Until a paged Node projection exists, the screen identifies the missing contract rather than showing an unverified recent-task list.

### S10 Audit Ledger

**User outcome**: verify and export the record of what happened.

**Content**: event count, evidence links, signature and chain status, event table, event detail drawer, hashes, actors, model or tool capability, source references.

**Actions**: filter, inspect event, verify chain, export offline evidence.

**Rules**: read-only for ordinary users; exports come from the Node.

**Pre-contract state**: the desktop does not create or reconstruct a ledger. Until the Node supplies the read-only query, chain status, and export permission, the screen identifies the missing contract rather than reporting an empty or healthy ledger.

### S11 AirBench Node and Model Roster

**User outcome**: understand local execution health and qualified capability.

**Content**: node identity, transport, GPU and memory, active workloads, sandbox, intake, ledger, external network policy, model capabilities, quantization, context, qualification, health, and priority.

**Actions**: recheck health, open connection settings, inspect qualification, view router decision history.

**Rules**: UI cannot manually route around qualification or policy.

**Current connection proof**: when the Rust-owned handshake is verified, show only the approved profile label, Node identity, authenticated subject, clearance context, domain-pack reference, transport kind, protocol version, and handshake ledger reference. Do not expose endpoint URLs, certificate material, credential references, or retained proof fields after a disconnect.

**Pre-contract operational state**: a trusted connection is not evidence that the GPU, sandbox, workload, model roster, qualification, or router history is healthy. Until the Node sends those typed projections, the screen shows them as not supplied and leaves model preference unavailable.

### S12 Settings and Identity

**User outcome**: understand identity and control permitted preferences.

**Content**: display, accessibility, shortcuts, notification settings, identity, clearance, projects, session, approved node profiles, retention and policy settings for administrators.

**Rules**: preference changes are local only when they are presentation state; authority, clearance, retention, tools, and model qualification changes require Node policy and ledger events.

### S13 Domain Pack Administration

**User outcome**: inspect active domain-pack rules without placing sector knowledge in the core.

**Content**: pack identity and version, contract compatibility, document profiles, task kinds, field checks, risk mappings, templates, source collections, qualification status.

**Rules**: pack cannot select arbitrary models, grant tools, disable hooks, or mark a result verified.

### S14 Recovery and Blocked States

Required states: node offline, reconnecting, event gap, model unavailable, hardware queue, file rejected, clearance mismatch, low confidence, conflicting sources, verification failure, sandbox failure, ledger failure, approval blocked, and artifact render failure.

Each state answers:

1. What happened?
2. What is preserved?
3. Is retry safe?
4. What is the next permitted action?
5. Where are technical details and ledger references?

## 4. Key journeys

### Scanned inspection report to approval note

Home -> New Task and Intake -> Plan Review -> Live Task -> Evidence -> Artifact Review -> Review Queue or approval -> Artifact Library -> Audit Ledger.

### Coding task

Home -> New Task -> Plan Review -> Live Task with sandbox events -> Artifact Review with diff and tests -> approved code package.

### Low-capacity workstation

Node Status -> Plan Review shows serial virtual team -> Live Task shows queued roles and current role -> same verification and approval gate.

## 5. Navigation and keyboard

- `Ctrl/Cmd + K`: command menu.
- `Ctrl/Cmd + N`: new task.
- `Ctrl/Cmd + Enter`: submit a valid composer.
- `Esc`: close a drawer or dialog.
- Focus returns to the invoking control after a drawer or dialog closes.
- Screen-reader announcements are limited to meaningful state changes.
