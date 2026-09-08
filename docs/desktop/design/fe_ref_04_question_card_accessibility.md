# FE-REF-04: Question card accessibility slice

## Purpose

This slice makes the current read-only Node question card understandable and calm for keyboard and screen-reader users while the authoritative answer and intervention contracts are still being developed.

## Delivered behavior

- The card is exposed as a labeled region tied to its visible title and state text.
- A short decision-state title is announced through a polite live region.
- Question content is not placed in the live region, so a long or sensitive question is not repeatedly announced as a status update.
- Questions remain text data from the Node. No local option, text answer, pause, resume, stop, or revision action is created.
- Unsynchronized and terminal task states continue to show preserved context without reopening or mutating the task.

## Authority and security

- The Node owns question text, clearance filtering, authority, deadlines, continuation policy, expected sequence, and response commands.
- The desktop only presents the current projection and does not interpret question text as instructions.
- A screen-reader announcement does not imply that a response is available or that the task is waiting for local input.

## Verification

- `apps/desktop/src/operatorQuestion.test.ts` covers the bounded announcement and existing unsynchronized, waiting, and terminal states.
- The change uses the existing React presentation component and creates no transport or backend path.
- Full #108 closure still requires the versioned Node question projection, idempotent answer and intervention commands, clearance-safe text, and packaged keyboard and screen-reader evidence.
