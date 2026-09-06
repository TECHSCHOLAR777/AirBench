# AirBench Frontend Contracts and State

## 1. Contract ownership

The AirBench Node owns authoritative state. The frontend consumes typed snapshots, ordered events, safe artifacts, and permission-aware command results.

The UI owns only presentation state:

- selected task, evidence, source, or artifact;
- open drawers and dialogs;
- local filters, sort, density, theme, and scroll position;
- unsent composer text;
- current connection display.

The UI cannot mark a task complete, approve an artifact, rewrite a fact, alter clearance, select an unqualified model, or bypass verification.

## 2. Common envelope fields

Every server object that can affect user decisions carries, directly or through a referenced object:

- stable ID;
- schema version;
- task, project, and artifact references where relevant;
- server timestamp;
- actor or subsystem;
- clearance context;
- provenance or ledger reference;
- hash or integrity reference where the object is authoritative;
- redaction or visibility reason when content is omitted.

The UI must not flatten these into plain strings and then lose the metadata.

## 3. Task snapshot

A task snapshot is the authoritative state base for a UI projection. It contains at least:

```text
TaskSnapshot
  task_id
  schema_version
  snapshot_id
  as_of_sequence
  title
  request_summary
  project_ref
  status
  phase
  clearance_context
  input_manifest_ref
  plan_ref
  active_workers
  execution_mode
  evidence_summary
  verification_summary
  approval_state
  artifact_refs
  unresolved_questions
  node_connection_ref
  ledger_head_ref
```

The snapshot may omit content the user is not cleared to see, but it must include a structured reason for omission.

## 3.1 Approved Node profile catalog

The desktop receives connection profiles only from the native Tauri boundary. A profile carries a stable ID, display label, transport kind, expected Node identity, protocol version, clearance context, certificate policy reference, and operating-system credential reference. The React layer does not accept an arbitrary URL, secret, certificate, or profile JSON from a user. The native catalog rejects invalid or unapproved entries before returning them. The initial implementation uses an administrator-provisioned application configuration file; signed policy verification and host ACL evidence remain release gates.

The webview receives only the stable `profile_id` when it invokes connection, event, intake, preview, or artifact-download commands. Rust resolves the full approved profile from the native catalog for each call. Endpoint URLs, certificate pins, credential references, and other transport policy material do not cross the IPC boundary.

## 4. Event envelope

The minimum event envelope is:

```text
TaskEvent
  event_id
  task_id
  sequence
  schema_version
  event_type
  occurred_at
  actor
  clearance_context
  payload
  payload_hash
  ledger_event_ref
```

The `sequence` is monotonic per task stream or per documented stream scope. The client stores the last applied sequence in memory and may persist only a safe cursor if the Node permits it.

Required event families include:

- `task.accepted`;
- `plan.created` and `plan.revised`;
- `worker.started` and `worker.completed`;
- `tool.started` and `tool.completed`;
- `evidence.added` and `evidence.revised`;
- `verification.completed` and `verification.failed`;
- `approval.required`, `approval.recorded`, and `approval.returned`;
- `artifact.ready` and `artifact.superseded`;
- `task.paused`, `task.resumed`, `task.blocked`, `task.failed`, `task.stopped`, and `task.completed`;
- `ledger.written` and `ledger.verification_changed`;
- `node.connection_changed` and `node.sovereignty_changed`.

Unknown event types are preserved in the diagnostic stream and do not mutate the projection until a compatible schema is available.

## 5. Command envelope

Every state-changing UI action becomes a typed command:

```text
Command
  command_id
  command_type
  task_id or resource_id
  actor
  expected_version or expected_sequence
  idempotency_key
  arguments
  client_version
```

Examples:

- `task.create`
- `task.submit`
- `task.approve_plan`
- `task.pause`
- `task.cancel`
- `task.resume`
- `task.answer_question`
- `artifact.approve`
- `artifact.return_for_changes`
- `ledger.verify_chain`
- `node.recheck`

The Node returns an accepted, rejected, or needs-review result. The UI waits for the corresponding event before changing authoritative status.

## 5.2 Live task workspace

The Live Task Workspace is a presentation of the Node snapshot plus the ordered task-local event stream. It may show status, phase, worker and tool summaries, evidence and verification summaries, plan mode, hardware references, unresolved questions, and ledger references. It must not infer progress from elapsed time, client receipt order, worker count, or model output.

The first desktop slice uses `task.cancel` for a bounded stop request. The command carries the last applied task sequence, authenticated actor, and idempotency key. The UI shows the command receipt but changes task status only after the Node emits the corresponding authoritative event. Pause, resume, and answer-question actions remain unavailable until their Node contracts and ledger transitions are defined.

## 5.1 Plan review projection

The Node exposes a typed `TaskPlanReview` projection for the plan review surface. It contains the committed team assignments, dependency graph, verification criteria, capability lanes, hardware profile reference, execution mode, hardware reason, authority requirement, plan and policy hashes, task-local sequence, and ledger reference. The projection can be `not_ready`, `ready`, `queued`, `needs_review`, `blocked`, or `rejected`.

The UI never infers parallelism from the number of displayed workers. It shows parallel, pipelined, or serial virtual-team mode only when the Node supplies a valid hardware admission record. Missing or invalid hardware admission is shown as a blocked review state. `task.approve_plan` carries the last server sequence and an idempotency key; the UI displays the accepted command but waits for the authoritative plan-approval event before changing task state.

## 6. Event application

The event store follows this algorithm:

1. Load a snapshot and its `as_of_sequence`.
2. Reject or quarantine events at or below the applied sequence unless the protocol explicitly marks them as a duplicate.
3. Apply only the next expected sequence.
4. On a gap, stop the projection, request replay, and show `Resynchronizing`.
5. On replay success, apply the ordered range.
6. On replay refusal or stale cursor, replace the projection with a fresh snapshot.
7. Preserve the cursor, snapshot ID, and resync result for diagnostics.

The UI must not fill gaps from local guesses or reorder events by client receipt time.

## 7. Reconnect behavior

Connection states are:

- `Connected and current`;
- `Connected, replaying`;
- `Reconnecting`;
- `Offline with cached records`;
- `Blocked by trust or policy`.

While not current:

- no consequential action is optimistically shown as complete;
- approval, stop, release, and delete-like commands are disabled unless the Node explicitly accepts offline queuing;
- the current known state remains visible with a stale indicator;
- the user sees whether the task may continue on the Node independently;
- the next event or snapshot determines the new authoritative state.

## 8. Provenance and fact rendering

The frontend projection for a fact must retain:

- fact ID;
- typed value and unit;
- source document and version;
- exact span, page, cell, or image region where available;
- extraction or derivation method;
- calibrated confidence;
- clearance;
- taint state;
- observed, valid, and ingested times where supplied;
- parent fact IDs for derived values;
- supersession state;
- ledger event reference.

For derived numbers, the UI shows the deterministic formula or calculation breakdown supplied by the Node. It never replaces the value with a model-written numeric token.

## 9. Artifact and preview contracts

An artifact reference contains:

- artifact ID and version;
- type and media type;
- task and project reference;
- status;
- clearance;
- content hash;
- render status;
- verification status;
- download permission;
- preview references generated by the Node;
- provenance and ledger references.

Preview content is data. The client accepts only typed preview formats such as sanitized text, image, PDF page, table data, slide image, or code text. It does not accept executable HTML or script-bearing document content as a trusted UI surface.

The File Intake Layer is the only file interpretation boundary. The desktop picker returns a native selection token and display metadata. Rust streams that selection to the Node query-upload switch, and the UI renders the returned manifest and safe preview. The UI does not inspect bytes, infer page count, run OCR, or create a second parse path. A preview must retain source hash, source region, confidence, clearance, taint, and ledger reference. Download is a separate Node-authorized command and is denied unless the returned permission and integrity checks succeed.

## 10. Clearance and redaction

The Node decides visibility. The UI receives either:

- permitted content;
- redacted content with a reason;
- metadata-only reference;
- explicit denial.

The frontend must not infer clearance from filenames, project names, or user-entered text. A redacted fact must not reappear through search, browser title, tooltip, error log, or local cache.

## 11. Versioning and compatibility

- Every snapshot, event, command, artifact preview, and error has a schema version.
- The frontend declares supported protocol versions during connection.
- Additive fields are ignored safely; breaking changes require a version negotiation result.
- A schema mismatch blocks consequential actions and directs the operator to the compatible application or Node version.
- Generated TypeScript types must come from the authoritative contract source. Handwritten duplicate interfaces are not acceptable for the wire protocol.

## 12. Ledger relationship

The UI displays ledger references returned by the Node. It does not create a second audit record.

User actions that change state must produce a server ledger event with:

- actor and clearance;
- command ID and idempotency key;
- previous and resulting state references;
- task or artifact reference;
- permission and policy result;
- timestamp;
- signature or chain reference.

If the Node cannot write the required ledger event, the state-changing action is not committed.
