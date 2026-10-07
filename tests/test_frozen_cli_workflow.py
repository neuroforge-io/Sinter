"""The packaged CLI qualification must perform a real shared source workflow."""

import errno
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import frozen_cli_smoke as producer
from tools.frozen_cli_smoke import Commands, workflow


@pytest.mark.parametrize("output_encoding", [None, "cp1252"])
def test_packaging_entry_runs_qualification_workflow_without_provider(
    tmp_path, output_encoding
):
    root = Path(__file__).parents[1]
    command = (
        "import sys,runpy; "
        f"sys.path.insert(0,{str(root / 'src')!r}); "
        f"runpy.run_path({str(root / 'packaging/desktop_entry.py')!r},"
        "run_name='__main__')"
    )
    receipt = {"checks": []}
    commands = Commands([sys.executable, "-B", "-c", command], tmp_path, receipt)
    if output_encoding:
        commands.environment["PYTHONIOENCODING"] = output_encoding
    assert workflow(commands) >= 52
    assert all(row["passed"] for row in receipt["checks"])
    assert all(row["exit_code"] in (0, 2) for row in receipt["checks"])


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_qualification_bounds_actual_child_output(tmp_path, stream):
    receipt = {"checks": []}
    code = f"import sys;sys.{stream}.write('x' * (2 * 1024 * 1024))"
    commands = Commands([sys.executable, "-B", "-c", code], tmp_path, receipt)
    with pytest.raises(RuntimeError, match="output bound"):
        commands.run("fictional_output_flood", [])
    assert receipt["checks"][-1]["owned_process_exited"] is True


def test_qualification_timeout_reaps_its_owned_child(tmp_path):
    receipt = {"checks": []}
    commands = Commands(
        [sys.executable, "-B", "-c", "import time;time.sleep(5)"], tmp_path, receipt
    )
    commands.deadline = time.monotonic() + 0.1
    with pytest.raises(RuntimeError, match="time bound"):
        commands.run("fictional_stopped_child", [])
    assert receipt["checks"][-1]["forced_cleanup"] is True
    assert receipt["checks"][-1]["owned_process_exited"] is True


@pytest.fixture
def inert_owned_command(tmp_path, monkeypatch):
    """Own one fake child; all signal and subprocess dependencies are injected."""
    receipt = {"checks": []}
    events = []
    state = {"flood": True, "finish_at_signal": False, "waits": [0], "posix": True}

    class Process:
        pid = 43210
        returncode = None

        def poll(self):
            events.append("poll")
            return self.returncode

        def wait(self, *, timeout):
            events.append(("wait", timeout))
            value = state["waits"].pop(0)
            if isinstance(value, BaseException):
                raise value
            self.returncode = value
            return value

        def terminate(self):
            raise AssertionError("No unassigned signal fallback is allowed.")

        def kill(self):
            raise AssertionError("No unassigned signal fallback is allowed.")

    process = Process()
    signals = SimpleNamespace(SIGTERM=15, SIGKILL=9)

    def spawn(argv, **kwargs):
        events.append(("spawn", argv))
        assert kwargs["start_new_session"] is state["posix"]
        assert kwargs["stdin"] == producer.subprocess.DEVNULL
        process.args = argv
        if state["flood"]:
            kwargs["stdout"].write(b"x" * (2 * 1024 * 1024))
            kwargs["stdout"].flush()
        return process

    def signal_owned(pid, kind):
        events.append(("signal", pid, kind))
        assert pid == process.pid and kind in (signals.SIGTERM, signals.SIGKILL)
        if state["finish_at_signal"]:
            process.returncode = 0
        raise PermissionError(errno.EPERM, "inert owned-group signal refusal")

    # Replacing this module's os reference avoids altering global Path behavior
    # on a Windows runner while exercising the precise POSIX cleanup branch.
    platform = SimpleNamespace(
        name="posix", environ=os.environ, fstat=os.fstat, killpg=signal_owned
    )
    monkeypatch.setattr(producer, "os", platform)
    monkeypatch.setattr(producer, "signal", signals)
    monkeypatch.setattr(producer.subprocess, "Popen", spawn)
    commands = Commands(["inert-owned-child"], tmp_path, receipt)
    return SimpleNamespace(
        receipt=receipt,
        events=events,
        state=state,
        process=process,
        commands=commands,
        signals=signals,
        platform=platform,
    )


@pytest.mark.parametrize("finish_at_signal", [False, True])
def test_output_refusal_keeps_primary_after_eperm_and_waits_owned_child(
    inert_owned_command, finish_at_signal
):
    proof = inert_owned_command
    proof.state["finish_at_signal"] = finish_at_signal
    with pytest.raises(RuntimeError, match="output bound"):
        proof.commands.run("inert-flood", [])
    row = proof.receipt["checks"][0]
    assert row["passed"] is False and row["owned_process_exited"] is True
    assert row["exit_code"] == 0 and row["forced_cleanup"] is True
    assert [error["type"] for error in row["cleanup_errors"]] == ["PermissionError"]
    assert [error["operation"] for error in row["cleanup_errors"]] == [
        "owned group SIGTERM"
    ]
    assert proof.events.count(("wait", 2)) == 1
    assert (
        sum(event[0] == "spawn" for event in proof.events if isinstance(event, tuple))
        == 1
    )
    assert proof.events.count(("signal", proof.process.pid, proof.signals.SIGTERM)) == 1


@pytest.mark.parametrize("final_exit", [0, None])
def test_output_refusal_retains_signal_and_bounded_wait_failures(
    inert_owned_command, final_exit
):
    proof = inert_owned_command
    first_timeout = producer.subprocess.TimeoutExpired("inert-owned-child", 2)
    proof.state["waits"] = [
        first_timeout,
        final_exit
        if final_exit is not None
        else producer.subprocess.TimeoutExpired("inert-owned-child", 2),
    ]
    with pytest.raises(RuntimeError, match="output bound"):
        proof.commands.run("inert-flood", [])
    row = proof.receipt["checks"][0]
    expected = ["PermissionError", "TimeoutExpired", "PermissionError"]
    if final_exit is None:
        expected.extend(["TimeoutExpired", "RuntimeError"])
    assert [error["type"] for error in row["cleanup_errors"]] == expected
    assert row["owned_process_exited"] is (final_exit is not None)
    assert row["passed"] is False and row["exit_code"] == final_exit
    assert proof.events.count(("wait", 2)) == 2
    assert [
        event
        for event in proof.events
        if isinstance(event, tuple) and event[0] == "signal"
    ] == [
        ("signal", proof.process.pid, proof.signals.SIGTERM),
        ("signal", proof.process.pid, proof.signals.SIGKILL),
    ]


def test_output_refusal_keeps_original_after_owned_wait_permission_failure(
    inert_owned_command,
):
    proof = inert_owned_command
    proof.state["waits"] = [PermissionError(errno.EPERM, "inert owned-child wait")]
    with pytest.raises(RuntimeError, match="output bound"):
        proof.commands.run("inert-flood", [])
    row = proof.receipt["checks"][0]
    assert [error["type"] for error in row["cleanup_errors"]] == [
        "PermissionError",
        "PermissionError",
        "RuntimeError",
    ]
    assert row["owned_process_exited"] is False and row["passed"] is False
    assert proof.events.count(("wait", 2)) == 1


def test_time_refusal_keeps_primary_after_eperm_and_owned_child_wait(
    inert_owned_command, monkeypatch
):
    proof = inert_owned_command
    proof.state["flood"] = False
    proof.commands.deadline = 90.0
    clock = iter((0.0, 21.0, 22.0))
    monkeypatch.setattr(
        producer, "time", SimpleNamespace(monotonic=lambda: next(clock))
    )
    with pytest.raises(RuntimeError, match="time bound"):
        proof.commands.run("inert-timeout", [])
    row = proof.receipt["checks"][0]
    assert row["passed"] is False and row["owned_process_exited"] is True
    assert row["cleanup_errors"][0]["type"] == "PermissionError"
    assert proof.events.count(("wait", 2)) == 1


def test_successful_owned_command_keeps_original_receipt_schema(inert_owned_command):
    proof = inert_owned_command
    proof.state["flood"] = False
    proof.process.returncode = 0
    result = proof.commands.run("inert-success", [])
    row = proof.receipt["checks"][0]
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    assert row["passed"] is True and row["owned_process_exited"] is True
    assert set(row) == {
        "check",
        "passed",
        "pid",
        "owned_process_exited",
        "seconds",
        "exit_code",
    }
    assert not any(
        isinstance(event, tuple) and event[0] in ("signal", "wait")
        for event in proof.events
    )


def test_nonposix_owned_timeout_escalates_only_its_child(
    inert_owned_command, monkeypatch
):
    proof = inert_owned_command
    proof.state["posix"] = False
    proof.platform.name = "nt"
    monkeypatch.setattr(producer, "signal", SimpleNamespace(SIGTERM=15))
    proof.process.terminate = lambda: proof.events.append("terminate owned child")
    proof.process.kill = lambda: proof.events.append("kill owned child")
    proof.state["waits"] = [
        producer.subprocess.TimeoutExpired("inert-owned-child", 2),
        0,
    ]
    with pytest.raises(RuntimeError, match="output bound"):
        proof.commands.run("inert-flood", [])
    row = proof.receipt["checks"][0]
    assert row["owned_process_exited"] is True and row["passed"] is False
    assert [error["type"] for error in row["cleanup_errors"]] == ["TimeoutExpired"]
    assert (
        "terminate owned child" in proof.events and "kill owned child" in proof.events
    )
    assert not any(
        isinstance(event, tuple) and event[0] == "signal" for event in proof.events
    )


def test_unknown_final_exit_cannot_become_a_successful_command(inert_owned_command):
    proof = inert_owned_command
    proof.state["flood"] = False
    proof.process.returncode = 0
    values = iter((0, 0))
    first = PermissionError(errno.EPERM, "inert final exit observation")

    def poll():
        try:
            return next(values)
        except StopIteration:
            raise first

    proof.process.poll = poll
    with pytest.raises(PermissionError) as raised:
        proof.commands.run("inert-unknown-exit", [])
    assert raised.value is first
    row = proof.receipt["checks"][0]
    assert row["owned_process_exited"] is False and row["passed"] is False
    assert [error["type"] for error in row["cleanup_errors"]] == [
        "PermissionError",
        "RuntimeError",
    ]
