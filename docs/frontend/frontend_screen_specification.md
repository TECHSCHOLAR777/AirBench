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

**Step 1, Outcome**: prompt, project, title, deliverable type, priority, optional deadline.

**Step 2, Sources**: files, knowledge sources, intake status, clearance compatibility, manifest identity, safe preview availability.

**Step 3, Preferences**: default Node-selected execution team, permitted review posture, deadline, notifications.

**Actions**: add files, remove files before intake commit, choose project, submit, return to edit.

**Rules**: all files go through File Intake; content is untrusted data; UI does not parse, OCR, or execute it.

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
- server-authoritative execution timeline;
- worker roles and hardware mode;
- tool and evidence summaries;
- verification progress;
- questions waiting for the user;
- emerging artifacts;
- stream cursor and connection status.

**Actions**: pause, stop, resume, answer question, open source, open artifact, open technical event detail.

**Rules**: no guessed completion; no optimistic stop or approval; reconnect by cursor replay or snapshot.

### S05 Evidence and Sources

**User outcome**: trace a finding to its source and understand its reliability.

**Layout**: source list, safe preview, fact and provenance detail.

**Content**: page, span, cell, or region; source hash; fact; confidence; clearance; taint; derivation; conflicts; verification state; ledger reference.

**Actions**: open exact source region, compare conflicts, filter low confidence, add auditable reviewer note, open ledger event.

**Rules**: source is data, not instruction; reviewer notes do not rewrite facts.

### S06 Review Queue

**User outcome**: find deliverables that require an authorized decision.

**Content**: priority, task, project, requestor, review reason, confidence, unresolved issues, authority, age, due date.

**Actions**: open review, filter assigned to me, return, request clarification.

**Rules**: the Node assigns authority and clearance; queue actions are ledgered.

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

### S08 Artifact Library

**User outcome**: find durable outputs and their versions.

**Content**: title, type, version, project, status, clearance, task ID, hash, source summary, verification summary.

**Actions**: open, compare, review, download when permitted, open provenance, archive through policy.

**Rules**: the UI cannot silently delete authoritative records.

### S09 Task History

**User outcome**: reconstruct earlier tasks and safely resume or clone when permitted.

**Content**: task list, project, requestor, status, phase, deliverables, review state, activity time.

**Task detail**: original request, input manifest, plan versions, event timeline, evidence, artifacts, failures, and policy-permitted recovery actions.

**Rules**: history is rebuilt from snapshots and ledger references, not a model-written summary.

### S10 Audit Ledger

**User outcome**: verify and export the record of what happened.

**Content**: event count, evidence links, signature and chain status, event table, event detail drawer, hashes, actors, model or tool capability, source references.

**Actions**: filter, inspect event, verify chain, export offline evidence.

**Rules**: read-only for ordinary users; exports come from the Node.

### S11 AirBench Node and Model Roster

**User outcome**: understand local execution health and qualified capability.

**Content**: node identity, transport, GPU and memory, active workloads, sandbox, intake, ledger, external network policy, model capabilities, quantization, context, qualification, health, and priority.

**Actions**: recheck health, open connection settings, inspect qualification, view router decision history.

**Rules**: UI cannot manually route around qualification or policy.

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
