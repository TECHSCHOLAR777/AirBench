# FE-DEV-06 evidence record

Status: the first Live Task Workspace slice is implemented locally and remains open. It connects the existing sequence-aware event synchronizer to a server-authoritative task view. It is not a production completion claim.

## Delivered slice

- After a Node accepts a task, the desktop loads the returned snapshot and synchronizes task-local events through the existing cursor and replay boundary.
- The workspace renders Node-owned task status, phase, applied sequence, Node connection reference, ledger head, event activity, execution plan, and a technical event disclosure.
- Activity summaries are derived from typed event payloads. The UI does not expose raw model reasoning traces or infer completion from client timing.
- Reconnect, replaying, stale, and blocked synchronizer states are visible. Consequential controls are disabled unless the projection is current and the synchronizer permits the command.
- The workspace now runs one guarded event-sync loop per active task. It polls the Node cursor without overlapping requests, backs off while reconnecting, stops after a terminal Node result, and cannot publish a late result after the task view is replaced or unmounted.
- Plan approval is now disabled unless the task projection is current, the synchronizer is connected, the Node plan is ready, and no approval is already in flight or recorded. The same gate is enforced by the command handler, not only by button presentation.
- Controlled artifact download is also disabled while the task projection is stale, reconnecting, or blocked. The desktop requires a current Node projection before requesting a Node-authorized release.
- Stop uses the existing Node command contract as `task.cancel`, carries the last applied sequence and idempotency key, and waits for the authoritative stopped event. It does not optimistically change task state.
- Plan review and approval remain reachable from the live workspace. Approval is still a Node-authorized action and the UI waits for the corresponding event.
- Pause, resume, and answer-question controls are intentionally not fabricated. They remain disabled until their typed Node contracts and ledger behavior exist.

## Verification

- Frontend tests: 77 passed, including three event-loop lifecycle tests.
- Frontend TypeScript and production Vite build: passed.
- Static egress and Tauri policy checks: passed.
- `git diff --check`: passed.
- The existing event-store tests continue to cover ordered application, duplicate rejection, gap handling, snapshot replacement, replay refusal, retry, and consequential-command gating.

## Remaining gates

- Add UI-level tests for live announcements, stale and reconnecting states, event activity rendering, and disabled controls.
- Exercise the polling loop against a running Python Node and verify that task events update the workspace without a manual refresh.
- Exercise the workspace against the production Python Node event endpoint rather than only the fixture and local synchronizer tests.
- Add fixture coverage for worker, tool, evidence, approval, artifact, and completion activity in one realistic task stream.
- Add explicit disconnect tests during each consequential phase, including command rejection while stale and duplicate command replay.
- Add pause, resume, and answer-question commands only after the Node contracts, authorization rules, and ledger events are implemented.
- Complete packaged Tauri and WebDriver evidence. FE-VAL-1, FE-VAL-2, and FE-VAL-3 remain release dependencies.
