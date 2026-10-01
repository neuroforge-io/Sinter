"""Finite subprocess controls; these do not reproduce Windows batch execution."""

import base64
import hashlib
import json
import sys
import time

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
