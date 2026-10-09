"""Finite subprocess controls; these do not reproduce Windows batch execution."""

import base64
import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

import wrapper_diagnostics as diagnostics
from wrapper_diagnostics import MAX_SAMPLE_BYTES, observe_wrapper


def test_timeout_retains_partial_bytes_marker_and_owned_parent_state(tmp_path):
    marker = tmp_path / "marker.json"
    value = {
        "executable": sys.executable,
        "arguments": ["fictional"],
        "cwd": str(tmp_path),
    }
    code = (
        "import os, sys, time\n"
        f"open({str(marker)!r}, 'w').write({json.dumps(value)!r})\n"
        "assert sys.stdin.buffer.read(1) == b''\n"
        "os.write(1, b'fictional partial output\\n')\n"
        "os.write(2, b'fictional diagnostic\\xff')\n"
        "time.sleep(3)\n"
    )
    observation, stdout = observe_wrapper(
        [sys.executable, "-I", "-S", "-B", "-c", code],
        tmp_path,
        marker,
        timeout=2,
    )
    assert observation["timed_out"] is True
    assert observation["returncode_before_cleanup"] is None
    assert observation["kill_attempted"] is True
    assert observation["parent_exited"] is True
    assert observation["cleanup_errors"] == []
    assert observation["returncode"] != 0
    assert observation["descendants_observed"] is False
    assert stdout == b"fictional partial output\n"
    assert (
        base64.b64decode(observation["stderr"]["sample_base64"])
        == b"fictional diagnostic\xff"
    )
    assert observation["marker"]["value"] == value


def test_exited_parent_does_not_wait_for_a_finite_inherited_writer(tmp_path):
    ready, release, finished = (
        tmp_path / "ready",
        tmp_path / "release",
        tmp_path / "finished",
    )
    child = (
        "import os, pathlib, time\n"
        "os.write(1, b'child ready\\n')\n"
        f"open({str(ready)!r}, 'w').write('ready')\n"
        f"release = pathlib.Path({str(release)!r})\n"
        "deadline = time.monotonic() + 3\n"
        "while not release.exists() and time.monotonic() < deadline: time.sleep(0.01)\n"
        "os.write(1, b'child finished\\n')\n"
        f"open({str(finished)!r}, 'w').write('finished')\n"
    )
    parent = (
        "import pathlib, subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', {child!r}], stdin=subprocess.DEVNULL)\n"
        f"ready = pathlib.Path({str(ready)!r})\n"
        "deadline = time.monotonic() + 2\n"
        "while not ready.exists() and time.monotonic() < deadline: time.sleep(0.01)\n"
        "assert ready.exists()\n"
        "print('parent finished', flush=True)\n"
    )
    try:
        observation, stdout = observe_wrapper(
            [sys.executable, "-I", "-S", "-B", "-c", parent],
            tmp_path,
            tmp_path / "no-marker",
            timeout=5,
        )
        assert observation["timed_out"] is False
        assert observation["returncode"] == 0
        assert observation["kill_attempted"] is False
        assert b"child ready" in stdout and b"parent finished" in stdout
        assert b"child finished" not in stdout
        assert observation["stdout"]["final_stream_proven"] is False
        assert observation["descendants_observed"] is False
    finally:
        # This test owns a deliberately finite descendant; await it separately.
        release.write_text("release")
        deadline = time.monotonic() + 4
        while not finished.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    assert finished.exists()
    assert (tmp_path / "wrapper.stdout.bin").stat().st_size > observation["stdout"][
        "size_after"
    ]


def test_large_binary_diagnostics_have_bounded_samples_without_a_full_hash(tmp_path):
    code = "import os; os.write(1, b'x' * 70000); os.write(2, b'\\xff' * 5000)"
    observation, stdout = observe_wrapper(
        [sys.executable, "-I", "-S", "-B", "-c", code],
        tmp_path,
        tmp_path / "missing",
    )
    assert observation["returncode"] == 0
    assert stdout is None
    assert observation["stdout"]["size_after"] == 70000
    assert observation["stdout"]["sample_bytes"] == MAX_SAMPLE_BYTES
    assert observation["stdout"]["sample_truncated"] is True
    assert observation["stdout"]["snapshot_sha256"] is None
    assert (
        observation["stdout"]["sample_sha256"]
        == hashlib.sha256(b"x" * MAX_SAMPLE_BYTES).hexdigest()
    )
    assert (
        base64.b64decode(observation["stderr"]["sample_base64"])
        == b"\xff" * MAX_SAMPLE_BYTES
    )


def _inert_process(
    monkeypatch, tmp_path, steps, *, exit_code=0, creation_delay=0.0, clock=None
):
    """One controlled parent and clock; never run cmd or a child interpreter."""
    if clock is None:
        clock = [0.0]
    calls = []

    class Parent:
        pid = 123
        args = ["inert-parent"]
        returncode = None

        def wait(self, timeout):
            if self.returncode is not None:
                return self.returncode
            calls.append(timeout)
            if not steps:
                clock[0] += timeout
                raise diagnostics.subprocess.TimeoutExpired(self.args, timeout)
            elapsed, write = steps.pop(0)
            clock[0] += elapsed
            write()
            if steps or exit_code is None:
                raise diagnostics.subprocess.TimeoutExpired(self.args, timeout)
            self.returncode = exit_code
            return exit_code

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -1

    parent = Parent()

    def create(*args, **kwargs):
        clock[0] += creation_delay
        return parent

    monkeypatch.setattr(diagnostics.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(diagnostics.subprocess, "Popen", create)
    return parent, calls


def test_inert_phase_samples_are_ordered_first_host_observations_with_equal_groups(
    tmp_path, monkeypatch
):
    batch, python = tmp_path / "batch.bin", tmp_path / "python.bin"
    _, calls = _inert_process(
        monkeypatch,
        tmp_path,
        [
            (0.04, lambda: batch.write_bytes(b"batch_entered\r\ntag_filter_begin\r\n")),
            (
                0.04,
                lambda: batch.write_bytes(
                    batch.read_bytes() + b"tag_filter_end\r\nquote_filter_begin\r\n"
                ),
            ),
            (
                0.01,
                lambda: python.write_bytes(
                    b"python_entered\nsys_imported\nruntime=not-a-phase\nmarker_written\n"
                ),
            ),
        ],
    )
    observation, _ = observe_wrapper(
        ["inert-parent"],
        tmp_path,
        tmp_path / "marker",
        timeout=5,
        phase_paths={"batch": batch, "python": python},
    )
    assert observation["returncode_before_cleanup"] == 0
    assert observation["timed_out"] is False
    timing = observation["phase_timing"]
    assert "not exact child boundaries" in timing["basis"]
    assert timing["final_stream_proven"] is False
    assert [r["phase"] for r in timing["samples"]] == [
        "batch_entered",
        "tag_filter_begin",
        "tag_filter_end",
        "quote_filter_begin",
        "python_entered",
        "sys_imported",
        "marker_written",
    ]
    assert [r["first_observed_elapsed_seconds"] for r in timing["samples"]] == [
        0.04,
        0.04,
        0.08,
        0.08,
        0.09,
        0.09,
        0.09,
    ]
    assert all(0 < wait <= diagnostics.PHASE_POLL_INTERVAL for wait in calls)
    assert "runtime=" not in json.dumps(timing)


def test_inert_phase_polling_uses_one_deadline_and_retains_pre_cleanup_state(
    tmp_path, monkeypatch
):
    batch = tmp_path / "batch.bin"
    parent, calls = _inert_process(monkeypatch, tmp_path, [], exit_code=None)
    observation, _ = observe_wrapper(
        ["inert-parent"],
        tmp_path,
        tmp_path / "marker",
        timeout=0.12,
        phase_paths={"batch": batch},
    )
    assert calls == pytest.approx([0.05, 0.05, 0.02])
    assert observation["timed_out"] is True
    assert observation["returncode_before_cleanup"] is None
    assert observation["returncode"] == parent.returncode == -1
    assert observation["kill_attempted"] is True
    assert observation["parent_exited"] is True
    assert observation["cleanup_errors"] == []
    assert observation["descendants_observed"] is False
    assert observation["phase_timing"]["samples"] == []
    assert observation["phase_timing"]["streams"]["batch"]["status"] == "not_observed"


def test_inert_phase_timestamp_records_completed_parent_read(tmp_path, monkeypatch):
    batch = tmp_path / "batch.bin"
    clock = [0.0]
    original_open = Path.open

    class SlowRead:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, size):
            data = self.stream.read(size)
            clock[0] += 0.02
            return data

    def read(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return SlowRead(stream) if path == batch and args == ("rb",) else stream

    monkeypatch.setattr(Path, "open", read)
    _inert_process(
        monkeypatch,
        tmp_path,
        [
            (0.01, lambda: batch.write_bytes(b"batch_entered\n")),
        ],
        clock=clock,
    )
    observation, _ = observe_wrapper(
        ["inert-parent"], tmp_path, tmp_path / "marker", phase_paths={"batch": batch}
    )
    assert observation["returncode"] == 0
    assert observation["phase_timing"]["samples"][0][
        "first_observed_elapsed_seconds"
    ] == pytest.approx(0.03)


def test_inert_creation_delay_does_not_consume_or_reset_original_wait_budget(
    tmp_path, monkeypatch
):
    _, calls = _inert_process(
        monkeypatch, tmp_path, [], exit_code=None, creation_delay=2.0
    )
    observation, _ = observe_wrapper(
        ["inert-parent"],
        tmp_path,
        tmp_path / "marker",
        timeout=5,
        phase_paths={"batch": tmp_path / "batch.bin"},
    )
    assert sum(calls) == pytest.approx(5)
    assert observation["timeout_seconds"] == 5
    assert observation["timed_out"] is True
    timing = observation["phase_timing"]
    assert timing["wait_started_elapsed_seconds"] == 2.0
    assert timing["wait_deadline_elapsed_seconds"] == 7.0
    assert timing["wait_budget_seconds"] == 5


@pytest.mark.parametrize("exit_code", [0, 7, None])
def test_inert_read_crossing_deadline_keeps_actual_parent_state(
    tmp_path, monkeypatch, exit_code
):
    batch, python = tmp_path / "batch.bin", tmp_path / "python.bin"
    batch.write_bytes(b"batch_entered\n")
    python.write_bytes(b"python_entered\n")
    clock = [0.0]
    parent, calls = _inert_process(
        monkeypatch, tmp_path, [], exit_code=None, clock=clock
    )
    original_open = Path.open
    reads = []
    phase_opens = []

    class SlowRead:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, size):
            reads.append(size)
            data = self.stream.read(size)
            clock[0] += 0.2
            parent.returncode = exit_code
            return data

    def read(path, *args, **kwargs):
        if path in (batch, python) and args == ("rb",):
            phase_opens.append(path)
        stream = original_open(path, *args, **kwargs)
        return SlowRead(stream) if path == batch and args == ("rb",) else stream

    monkeypatch.setattr(Path, "open", read)
    observation, _ = observe_wrapper(
        ["inert-parent"],
        tmp_path,
        tmp_path / "marker",
        timeout=0.12,
        phase_paths={"batch": batch, "python": python},
    )
    assert calls == []
    assert reads == [MAX_SAMPLE_BYTES + 1]
    assert phase_opens == [batch]
    assert observation["phase_timing"]["streams"]["python"]["status"] == "not_observed"
    assert observation["returncode_before_cleanup"] == exit_code
    assert observation["timed_out"] is (exit_code is None)
    assert observation["kill_attempted"] is (exit_code is None)
    assert observation["returncode"] == (-1 if exit_code is None else exit_code)
    assert observation["parent_exited"] is True
    assert observation["cleanup_errors"] == []
    assert observation["descendants_observed"] is False


def test_inert_phase_sample_cap_remains_explicit_on_later_unchanged_reads(
    tmp_path, monkeypatch
):
    batch = tmp_path / "batch.bin"
    monkeypatch.setattr(diagnostics, "MAX_PHASE_SAMPLES", 2)
    _inert_process(
        monkeypatch,
        tmp_path,
        [
            (
                0.02,
                lambda: batch.write_bytes(
                    b"batch_entered\ntag_filter_begin\ntag_filter_end\n"
                ),
            ),
            (0.01, lambda: None),
        ],
    )
    observation, _ = observe_wrapper(
        ["inert-parent"], tmp_path, tmp_path / "marker", phase_paths={"batch": batch}
    )
    timing = observation["phase_timing"]
    assert len(timing["samples"]) == 2
    assert timing["streams"]["batch"]["samples_truncated"] is True
    assert timing["streams"]["batch"]["status"] == "sample_limit"


@pytest.mark.parametrize(
    "content,status",
    [
        (b"batch_entered\r\ntag_filter_be", "incomplete"),
        (b"unexpected\n", "invalid"),
        (b"x" * (MAX_SAMPLE_BYTES + 1), "oversized"),
    ],
)
def test_inert_unknown_phase_timing_never_changes_successful_parent_result(
    tmp_path, monkeypatch, content, status
):
    batch = tmp_path / "batch.bin"
    _inert_process(monkeypatch, tmp_path, [(0.01, lambda: batch.write_bytes(content))])
    observation, _ = observe_wrapper(
        ["inert-parent"], tmp_path, tmp_path / "marker", phase_paths={"batch": batch}
    )
    assert observation["timed_out"] is False
    assert observation["returncode"] == 0
    timing = observation["phase_timing"]
    assert timing["streams"]["batch"]["status"] == status
    assert [s["phase"] for s in timing["samples"]] == (
        ["batch_entered"] if status == "incomplete" else []
    )


def test_inert_phase_read_failure_keeps_original_wait_result_and_diagnostics(
    tmp_path, monkeypatch
):
    batch = tmp_path / "denied.bin"
    original_open = Path.open

    def read(path, *args, **kwargs):
        if path == batch:
            raise PermissionError("inert phase read denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", read)
    _inert_process(monkeypatch, tmp_path, [(0.01, lambda: None)], exit_code=7)
    observation, _ = observe_wrapper(
        ["inert-parent"], tmp_path, tmp_path / "marker", phase_paths={"batch": batch}
    )
    assert observation["returncode_before_cleanup"] == observation["returncode"] == 7
    assert "operation_error" not in observation
    assert observation["kill_attempted"] is False
    state = observation["phase_timing"]["streams"]["batch"]
    assert state["status"] == "read_failed"
    assert state["read_failures"] == 2
    assert state["last_read_error"] == "PermissionError: inert phase read denied"
