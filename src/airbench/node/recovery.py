"""Startup reconciliation of stale task state after a Node restart.

Execution state that lived only in the coordinator process (``_prepared``,
``_runs``) is lost when a Node stops.  The durable ledger is authoritative, so
on startup every task whose committed state can only be advanced by the
process that died is reconciled to a typed state:

- mid-flight execution states (``executing``, ``awaiting_check``, ``rendering``)
  become ``task.failed`` with ``failure_code=node_restart_interrupted``;
- ``deliverable_verified`` reached without a recorded human sign-off
  (verification passed but the review request was never committed) is
  recovered to operator review via ``human.review.required``.  A task whose
  latest event is a ``human.signoff`` already carries the operator's decision
  and is left untouched.

Valid resting states (``created``, ``authorized``, ``planned``,
``needs_review``, ``awaiting_review`` and all terminal states) are left
untouched.  Reconciliation is idempotent: it replays committed ledger state
and uses the orchestrator's idempotent transitions.
"""

from __future__ import annotations

from typing import Any

INTERRUPTED_STATES = frozenset({"executing", "awaiting_check", "rendering"})
RECOVERABLE_REVIEW_STATES = frozenset({"deliverable_verified"})
NON_RESUMABLE_TASK_PREFIXES = ("task.knowledge.search",)


def _last_event(ledger: Any, task_id: str) -> Any:
    return next(
        (event for event in reversed(ledger.events) if event.task_id == task_id),
        None,
    )


def reconcile_stale_tasks(orchestrator: Any, ledger: Any) -> dict[str, Any]:
    """Reconcile non-resting task states against the committed ledger."""
    task_ids = list(dict.fromkeys(
        event.task_id for event in ledger.events if event.event_type == "task.created"
    ))
    interrupted: list[str] = []
    recovered_to_review: list[str] = []
    for task_id in task_ids:
        if task_id.startswith(NON_RESUMABLE_TASK_PREFIXES):
            # Knowledge search subjects record synchronous projection events.
            # They are not resumable coordinator tasks, so a process restart
            # must not convert a completed search subject into task.failed.
            continue
        state = orchestrator.state(task_id)
        last = _last_event(ledger, task_id)
        if state in INTERRUPTED_STATES:
            orchestrator.transition(task_id, "task.failed", {
                "failure_code": "node_restart_interrupted",
                "reason": "The Node restarted while this task was mid-execution; "
                          "the in-process execution state cannot be resumed.",
            })
            interrupted.append(task_id)
        elif state in RECOVERABLE_REVIEW_STATES and (
            last is None or last.event_type != "human.signoff"
        ):
            orchestrator.transition(task_id, "human.review.required", {
                "reason": "Verification had passed when the Node restarted; "
                          "the verified draft is recovered for operator review.",
            })
            recovered_to_review.append(task_id)
    return {
        "task_count": len(task_ids),
        "interrupted": interrupted,
        "recovered_to_review": recovered_to_review,
    }


__all__ = [
    "INTERRUPTED_STATES",
    "NON_RESUMABLE_TASK_PREFIXES",
    "RECOVERABLE_REVIEW_STATES",
    "reconcile_stale_tasks",
]
