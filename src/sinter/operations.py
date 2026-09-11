"""Cooperative per-operation deadlines, independent of HTTP connection timeouts."""
from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar

_CURRENT = ContextVar('sinter_operation', default=None)


class Cancelled(Exception):
    """The user cancelled the surrounding operation."""


class DeadlineExceeded(TimeoutError):
    """The operation exhausted its total budget, not merely one socket read."""


def checkpoint():
    state = _CURRENT.get()
    if state is not None:
        deadline, cancellation = state
        if cancellation is not None and cancellation.is_set():
            raise Cancelled()
        if time.monotonic() >= deadline:
            raise DeadlineExceeded('This task reached its overall time limit. Your inputs are unchanged; review saved partial work before retrying.')


def remaining(default):
    checkpoint()
    state = _CURRENT.get()
    return min(default, max(.001, state[0] - time.monotonic())) if state is not None else default


@contextmanager
def budget(seconds, cancellation=None):
    parent = _CURRENT.get()
    deadline = time.monotonic() + seconds
    if parent is not None:
        deadline = min(deadline, parent[0])
        cancellation = cancellation or parent[1]
    token = _CURRENT.set((deadline, cancellation))
    try:
        checkpoint()
        yield
    finally:
        _CURRENT.reset(token)
