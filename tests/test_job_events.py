"""Incremental job events support long recordings, cursors and cancellation."""
from __future__ import annotations

import threading
import time

import pytest

from sinter.jobs import Jobs


def wait_job(jobs: Jobs, identifier: str, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = jobs.get(identifier)
        if result["status"] in {"done", "failed", "cancelled"}:
            return result
        time.sleep(0.005)
    raise AssertionError("Job did not finish")


def test_segments_are_committed_incrementally_with_a_cursor():
    def operation(progress):
        progress({"event": "session", "session": {"id": "session-1"}})
        progress("Sending 2 seconds to ERAIS")
        for index, (start, end) in enumerate([(0.0, 2.0), (2.0, 4.0)]):
            progress({
                "event": "segments",
                "segments": [{
                    "start": start, "end": end, "text": f"words {index}",
                    "speaker": "Unidentified", "words": [],
                }],
                "received_s": end, "processed_s": end,
                "phase": "transcribing", "message": f"{end:.0f} seconds sent",
            })
        progress({"event": "progress", "received_s": 4.0})
        return {"segments": [{"start": 0.0, "end": 4.0, "text": "words 0 words 1"}]}

    jobs = Jobs()
    try:
        identifier = jobs.submit(operation)
        finished = wait_job(jobs, identifier)
        assert finished["status"] == "done"
        page = jobs.get(identifier, after=0)
        assert [event["sequence"] for event in page["events"]] == [1, 2, 3]
        assert page["events"][0]["event"] == "session"
        assert [event["event"] for event in page["events"][1:]] == [
            "segment", "segment"]
        assert page["events"][1]["start"] == 0.0
        assert page["events"][2]["text"] == "words 1"
        assert page["next_cursor"] == 3
        assert page["received_s"] == 4.0
        tail = jobs.get(identifier, after=3)
        assert tail["events"] == []
        assert tail["next_cursor"] == 3
        # Replaying the same cursor is idempotent for the caller.
        assert jobs.get(identifier, after=0)["events"] == page["events"]
        assert "events" not in jobs.get(identifier)
    finally:
        jobs.close()


def test_invalid_cursor_is_refused():
    jobs = Jobs()
    try:
        identifier = jobs.submit(lambda progress: {})
        wait_job(jobs, identifier)
        with pytest.raises(ValueError, match="cursor"):
            jobs.get(identifier, after=-1)
        with pytest.raises(ValueError, match="cursor"):
            jobs.get(identifier, after=True)
    finally:
        jobs.close()


def test_cancellation_keeps_partial_segments_and_reports_cleanup():
    started = threading.Event()

    def operation(progress):
        progress({"event": "session", "session": {"id": "session-2"}})
        progress({
            "event": "segments",
            "segments": [{"start": 0.0, "end": 1.0, "text": "first"}],
            "received_s": 1.0,
        })
        started.set()
        for index in range(1, 400):
            progress({
                "event": "segments",
                "segments": [{
                    "start": float(index), "end": float(index + 1),
                    "text": f"words {index}",
                }],
                "received_s": float(index + 1),
            })
            time.sleep(0.01)
        return {}

    jobs = Jobs()
    try:
        identifier = jobs.submit(operation)
        assert started.wait(3)
        jobs.cancel(identifier)
        cancelled = wait_job(jobs, identifier)
        assert cancelled["status"] == "cancelled"
        assert cancelled["result"] is None
        assert "partial transcript" in cancelled["message"]
        events = jobs.get(identifier, after=0)["events"]
        assert events[0]["event"] == "session"
        assert any(event["event"] == "segment" for event in events)
    finally:
        jobs.close()


def test_event_bound_fails_closed_and_keeps_committed_events(monkeypatch):
    import sinter.jobs as jobs_module

    monkeypatch.setattr(jobs_module, "MAX_JOB_EVENTS", 3)

    def operation(progress):
        for index in range(5):
            progress({
                "event": "segments",
                "segments": [{"start": float(index), "end": float(index + 1),
                              "text": f"words {index}"}],
            })
        return {"segments": []}

    jobs = Jobs()
    try:
        identifier = jobs.submit(operation)
        result = wait_job(jobs, identifier)
        assert result["status"] == "failed"
        assert "more events" in result["error"]
        page = jobs.get(identifier, after=0)
        assert len(page["events"]) == 3
        assert [event["sequence"] for event in page["events"]] == [1, 2, 3]
        assert [event["text"] for event in page["events"]] == [
            "words 0", "words 1", "words 2"]
    finally:
        jobs.close()


def test_cancelling_after_completion_preserves_the_result():
    jobs = Jobs()
    try:
        identifier = jobs.submit(
            lambda progress: {"segments": [{"start": 0.0, "end": 1.0,
                                            "text": "complete"}]})
        finished = wait_job(jobs, identifier)
        assert finished["status"] == "done"
        jobs.cancel(identifier)
        after = jobs.get(identifier)
        assert after["status"] == "done"
        assert after["result"]["segments"][0]["text"] == "complete"
        assert after["cancel_requested"] is False
    finally:
        jobs.close()
