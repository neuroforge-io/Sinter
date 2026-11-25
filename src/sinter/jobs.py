"""Bounded local jobs with cooperative cancellation and expiring private results."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass, field

from .client import APIError
from .operations import Cancelled, DeadlineExceeded, budget, checkpoint

log = logging.getLogger(__name__)

MAX_JOB_EVENTS = 20_000
TERMINAL = {"done", "failed", "cancelled"}


@dataclass
class Job:
    id: str
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    started_at: float | None = None
    updated_at: float = field(default_factory=time.time)
    label: str = "Task"
    status: str = "queued"
    message: str = "Waiting for an available worker"
    result: dict | None = None
    error: str = ""
    events: list[dict] = field(default_factory=list)
    received_s: float = 0.0
    processed_s: float = 0.0
    phase: str = "queued"
    cancel: threading.Event = field(default_factory=threading.Event)


class Jobs:
    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sinter-work")
        self._slots = threading.BoundedSemaphore(4)
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}

    def _purge(self):
        terminal = sorted((job for job in self._jobs.values() if job.status in TERMINAL),
                          key=lambda job: job.completed_at or job.created_at)
        for job in terminal:
            if time.time() - (job.completed_at or job.created_at) > 1800 or len(self._jobs) >= 20:
                self._jobs.pop(job.id, None)

    def submit(self, operation, *, label="Task", timeout=1800) -> str:
        if not isinstance(label, str) or len(label) > 200:
            raise ValueError("Use a short task label.")
        if type(timeout) not in {int, float} or not 1 <= timeout <= 7200:
            raise ValueError("Task time budget must be from 1 to 7200 seconds.")
        if not self._slots.acquire(blocking=False):
            raise ValueError("Four jobs are already active. Finish or cancel one before starting another.")
        job = Job(uuid.uuid4().hex, label=label)
        with self._lock:
            self._purge()
            self._jobs[job.id] = job

        def record(payload: dict) -> None:
            """Commit one incremental job event under the job lock."""
            with self._lock:
                kind = payload.get("event")
                if kind == "segments":
                    additions = [
                        {"event": "segment", **segment}
                        for segment in payload.get("segments") or ()
                        if isinstance(segment, dict)
                    ]
                elif kind in {"session", "warning", "phase"}:
                    additions = [dict(payload)]
                else:
                    additions = []
                for event in additions:
                    if len(job.events) >= MAX_JOB_EVENTS:
                        raise ValueError(
                            "The recording produced more events than this task can hold.")
                    job.events.append({"sequence": len(job.events) + 1, **event})
                for key in ("received_s", "processed_s"):
                    value = payload.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        setattr(job, key, float(value))
                phase = payload.get("phase")
                if isinstance(phase, str) and phase:
                    job.phase = phase[:40]
                if payload.get("message"):
                    job.message = str(payload["message"])[:500]
                job.updated_at = time.time()
                job.started_at = job.started_at or job.updated_at
                job.status = "running"

        def progress(message):
            checkpoint()
            if job.cancel.is_set():
                raise Cancelled()
            if isinstance(message, dict):
                record(message)
                return
            with self._lock:
                job.status, job.message = "running", str(message)[:500]
                job.updated_at = time.time()
                job.started_at = job.started_at or job.updated_at

        def execute():
            try:
                with budget(timeout, job.cancel):
                    progress("Starting")
                    result = operation(progress)
                with self._lock:
                    job.completed_at = time.time()
                    job.status, job.message, job.result = "done", "Ready for review", result
                    job.phase = "completed"
                    if job.cancel.is_set():
                        job.message = (
                            "Completed before the cancellation request took effect")
            except Cancelled:
                with self._lock:
                    job.completed_at = time.time()
                    job.status = "cancelled"
                    job.phase = "cancelled"
                    transcribed = sum(
                        1 for event in job.events if event.get("event") == "segment")
                    job.message = (
                        "Cancelled; the meeting session was closed and the partial "
                        f"transcript keeps {transcribed} segments."
                        if transcribed else
                        "Cancelled; no report was saved")
            except (APIError, ValueError, DeadlineExceeded) as exc:
                with self._lock:
                    job.completed_at = time.time()
                    job.status, job.phase = "failed", "failed"
                    job.error = str(exc)
                    job.result = getattr(exc, "partial_result", None)
            except Exception:
                log.exception("A workbench job failed")
                with self._lock:
                    job.completed_at = time.time()
                    job.status, job.error = "failed", "An unexpected error occurred. Your original inputs are unchanged."
            finally:
                self._slots.release()
        try:
            self._pool.submit(copy_context().run, execute)
        except RuntimeError as exc:
            self._slots.release()
            with self._lock:
                self._jobs.pop(job.id, None)
            raise ValueError("Sinter is shutting down. Restart before beginning another job.") from exc
        return job.id

    def get(self, identifier: str, after: int | None = None) -> dict:
        with self._lock:
            self._purge()
            job = self._jobs.get(identifier)
            if job is None:
                raise KeyError("This temporary result expired. Run it again or open a saved report.")
            payload = {"id": job.id, "status": job.status, "message": job.message,
                       "result": job.result, "error": job.error, "created_at": job.created_at, "completed_at": job.completed_at,
                       "started_at": job.started_at, "updated_at": job.updated_at, "label": job.label,
                       "cancel_requested": job.cancel.is_set(),
                       "received_s": round(job.received_s, 3),
                       "processed_s": round(job.processed_s, 3),
                       "phase": job.phase,
                       "next_cursor": len(job.events)}
            if after is not None:
                if isinstance(after, bool) or not isinstance(after, int) or after < 0:
                    raise ValueError("Job cursor must be a non-negative integer.")
                payload["events"] = [dict(event) for event in job.events[after:]]
            return payload

    def list(self) -> list[dict]:
        with self._lock:
            self._purge()
            return [{"id": j.id, "status": j.status, "message": j.message, "error": j.error,
                     "created_at": j.created_at, "completed_at": j.completed_at, "started_at": j.started_at,
                     "label": j.label, "cancel_requested": j.cancel.is_set(), "has_result": j.result is not None}
                    for j in sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)]

    def cancel(self, identifier: str) -> None:
        with self._lock:
            job = self._jobs.get(identifier)
            if job is None:
                raise KeyError("Job not found.")
            if job.status in {"queued", "running"}:
                job.cancel.set()
                job.message = "Stopping after the current bounded operation"

    def close(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                job.cancel.set()
        self._pool.shutdown(wait=False, cancel_futures=True)
