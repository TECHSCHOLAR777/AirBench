# FE-DEV-05 evidence record

Status: the typed plan projection and approval transport slice is implemented and closed. Issue #123 remains open for a real orchestrator-generated executing plan, full revision flow, and local vertical evidence; packaged and target qualification gates remain separate.

## Delivered slice

- The orchestrator stores the validated `TeamPlan` in the append-only `task.plan.committed` event. The UI never generates or edits a plan.
- The Node exposes `GET /api/v1/tasks/{task_id}/plan` as a clearance-aware `TaskPlanReview` projection.
- The projection makes missing plan, missing hardware admission, queued capacity, degraded admission, rejected admission, and ready admission distinct states.
- Execution mode is supplied by the Node hardware admission record. The UI does not infer parallel versus serial execution from worker count.
- `task.approve_plan` is a separate typed command with expected task sequence, actor binding, and idempotency replay. The Node accepts it only for a ready plan with committed hardware admission.
- The React surface shows team, dependency graph, capability lanes, verification requirement, hardware reason, plan and policy hashes, ledger reference, and the plain-language authority requirement.
- Approval acceptance is shown as a command receipt only. The UI waits for the plan-approval event before changing task state.
- Approval is offered only when the plan task sequence matches the current Node task projection. The handler repeats this check immediately before IPC, so a plan cannot be approved from an older cursor.
- The plan review cancel action is unavailable for completed, failed, or stopped tasks and remains gated by a current, verified Node projection.
- The webview re-validates the runtime `TaskPlanReview` response before approval or work-trace presentation. It checks the core envelope, task and Node identity, protocol and clearance, supported state and execution mode, required independent verification, team and dependency structures, hardware reason, authority fields, hashes, ledger reference, and blocked-plan failure context. A malformed ready plan fails closed.
- State-changing command results are also re-validated before an approval or cancel receipt is shown. The result must match the submitted command ID, task ID, idempotency key, approved Node context, and clearance, and must carry a ledger reference.

## Verification

- Python focused Node API, orchestrator, and contract tests: 30 passed.
- Frontend tests: 22 files, 116 passed on 2026-09-09.
- Rust transport tests: 14 passed.
- Generated contract check, frontend build, static no-egress check, Tauri policy check, and Python compile checks passed.
- Fixture transport run `AirBenchNodeValidation-20260907-022035-cf89d512b74446c6b614eb4da0e565f9` passed typed plan retrieval with a parallel hardware-admitted plan and typed `task.approve_plan` command transport.

## Remaining gates

- Connect the projection to the production plan-generation and hardware-admission event writers rather than only the local test ledger and fixture.
- Add authoritative plan revision and stale-plan replacement behavior. The current slice rejects stale approval and explains the stale sequence, but does not expose replan commands.
- Add full UI coverage for queued, degraded, rejected, missing-authority, and missing-qualification plan fixtures.
- Complete the serial virtual-team fixture and packaged WebDriver decision-surface evidence.
- Do not treat this as final approval or organizational sign-off. The first scope still requires later verified execution and review events.
