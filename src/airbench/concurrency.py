"""Bounded daemon-thread execution helper.

A per-call ``ThreadPoolExecutor`` whose worker hangs (tesseract, a local
model, a black-holed endpoint) leaks a NON-daemon thread that Python joins at
interpreter exit, so one hung call could keep the whole Node process alive
forever.  This helper runs the call on a daemon thread instead: a timed-out
call surfaces its timeout error immediately and leaves behind only a daemon
thread that cannot block shutdown.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future
from typing import Callable, TypeVar

T = TypeVar("T")


def run_with_timeout(fn: Callable[[], T], timeout_s: float) -> T:
    """Run ``fn`` on a daemon thread and wait up to ``timeout_s`` seconds."""
    future: Future[T] = Future()

    def _run() -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(fn())
        except BaseException as exc:  # noqa: BLE001 - forwarded to the caller
            future.set_exception(exc)

    threading.Thread(target=_run, daemon=True, name="airbench-bounded-call").start()
    return future.result(timeout=timeout_s)


__all__ = ["run_with_timeout"]
