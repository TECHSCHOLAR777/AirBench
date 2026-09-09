# FE-DEV-12 recovery guidance evidence

Status: an event-synchronization recovery slice is implemented locally. Issue
#84 remains open for the complete cross-feature recovery matrix, packaged
keyboard and screen-reader evidence, restart and long-task behavior, offline
runtime evidence, and observed no-egress proof.

## Delivered slice

- The Live Task Workspace now gives the operator a dedicated recovery panel for
  each authoritative synchronization state: not started, checking the Node,
  replaying ordered events, current, reconnecting, and blocked.
- Each state explains what remains preserved, whether retry is safe, and the
  next permitted action. Reconnecting explicitly keeps the last accepted task
  projection and ledger context as stale context, while blocked state refuses
  to imply that the view is current.
- Replay guidance distinguishes ordered event application from a transport
  interruption. The desktop does not reorder events, overlap synchronization,
  or invent progress from elapsed time.
- The recovery helper is presentation-only. The existing event synchronizer
  and Node command gates remain responsible for current-state and
  consequential-action authority.
- Validated Node command receipts now keep `accepted`, `needs_review`, and
  `rejected` outcomes distinct. Plan approval and stop-request surfaces show
  what happened, what remains preserved, whether retry is safe, the next
  permitted action, and the receipt ledger reference. A stop-request refresh
  occurs only after an accepted receipt; a deferred or rejected command does
  not cause the desktop to imply a state transition.
- The plan surface no longer routes rejected or deferred command receipts
  through the accepted-approval recovery copy. Node-provided reason text is
  rendered as text only and cannot create local authority.
- The initial activity, worker, and tool lists use a bounded presentation
  window for long tasks. The full Node projection remains intact, and the
  operator can reveal older recorded activity explicitly. This keeps the
  initial DOM work bounded without silently deleting task history.

## Contracts and files

- `apps/desktop/src/features/tasks/syncRecovery.ts` maps the existing typed
  `EventSyncStatus` and Node projection to operator-facing recovery guidance.
- `apps/desktop/src/app/App.tsx` renders that guidance beneath the live
  synchronization status without adding a client-side state transition.
- `apps/desktop/src/app/styles.css` gives the guidance the same restrained
  status hierarchy as the intake, plan, Node, and proof recovery surfaces.
- `apps/desktop/src/features/tasks/syncRecovery.test.ts` covers reconnect,
  replay, blocked, in-flight, current, and idle guidance.
- `apps/desktop/src/features/tasks/commandOutcome.ts` maps validated command
  receipts to the operator-facing outcome and recovery contract.
- `apps/desktop/src/features/tasks/commandOutcome.test.ts` covers accepted,
  review-required, rejected, and refresh-gating behavior.
- `apps/desktop/src/features/work_trace/activityWindow.ts` bounds the initial
  activity presentation window without mutating the Node projection.
- `apps/desktop/src/features/work_trace/activityWindow.test.ts` covers recent
  record retention, short tasks, invalid limits, and non-mutation.

## Verification

- `npm test -- --run`: 130 passed across 25 test files.
- `npm run build`: passed.
- `npm run check:contracts`: passed.
- `npm run check:ui`: passed, including the authored-source accessibility
  contract.
- `npm run check:egress`: passed; no network-capable frontend API or external
  resource URL was found.
- `npm run check:tauri-config`: passed.
- `git diff --check`: passed.
- `npm run tauri:build:webdriver` with a fresh temporary `CARGO_TARGET_DIR`:
  passed. The current Tauri source compiled to `airbench-desktop.exe`. The
  repository's existing debug target was not deleted; its cached build-script
  output still contains the historical `frontend/src-tauri` path, so that
  target cannot be used as clean release evidence until it is rebuilt.
- `npm run check:webdriver`: blocked before application launch because
  `msedgedriver.exe` is not provisioned on this host. No packaged desktop
  pass is claimed from the source-level checks.

## Remaining gates

- Exercise recovery states against a running Python Node and a real ordered
  task stream.
- Add restart, long-task, packaged keyboard, screen-reader, offline runtime,
  and OS-level no-egress evidence.
- Complete recovery coverage for model, hardware, sandbox, ledger, verification,
  clearance, and artifact failures when their Node projections are available.
