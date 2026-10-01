"""Tiny process/display mocks; these tests never launch GUI or frozen services."""

from __future__ import annotations

import json
import signal
import subprocess
from types import SimpleNamespace

import pytest

from tools import native_window_smoke as tool

DIAGNOSTICS = {
    "schema": "sinter-launch-check/v1",
    "version": "fictional-test",
    "frozen": True,
    "core_assets_available": True,
    "native_toolkit_available": True,
    "Tcl_resources_available": True,
    "bundled_Tk_resources_available": True,
}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    binary = tmp_path / "Sinter"
    binary.write_bytes(b"fictional executable fixture; never run")
    binary.chmod(0o700)
    monkeypatch.setenv("DISPLAY", ":42")
    monkeypatch.setenv("XAUTHORITY", "/fictional/ci-display-cookie")
    monkeypatch.setenv("NEUROFORGE_API_KEY", "fictional-key-that-must-not-be-forwarded")
    monkeypatch.setenv("SINTER_API_KEY", "fictional-key-that-must-not-be-forwarded")
    monkeypatch.setattr(tool.platform, "system", lambda: "Linux")
    clock = [0.0]

    def now():
        clock[0] += 0.1
        return clock[0]

    monkeypatch.setattr(
        tool, "time", SimpleNamespace(monotonic=now, sleep=lambda *_: None)
    )
    processes, signals, observers, diagnostics = [], [], [], []
    mode = {"window": True, "exit_code": 0, "force": False, "leftover_window": False}
    diagnostic_body = {"value": DIAGNOSTICS, "timeout": False}

    class Process:
        def __init__(self, args, **kwargs):
            self.pid = 1000 + len(processes)
            self.returncode = None
            self.args, self.kwargs = args, kwargs
            if args[-1] == "--diagnose":
                self.pid = 900
                kwargs["stdout"].write(json.dumps(diagnostic_body["value"]).encode())
                diagnostics.append(self)
            else:
                processes.append(self)

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            if self.pid == 900:
                if diagnostic_body["timeout"] and self.returncode is None:
                    raise subprocess.TimeoutExpired(self.args, timeout)
                self.returncode = 0
                return 0
            if mode["force"] and self.returncode is None:
                raise subprocess.TimeoutExpired(self.args, timeout)
            if self.returncode is None:
                self.returncode = mode["exit_code"]
            return self.returncode

    def killpg(pid, value):
        signals.append((pid, value))
        process = next(item for item in [*processes, *diagnostics] if item.pid == pid)
        if value == signal.SIGTERM and not mode["force"]:
            process.returncode = mode["exit_code"]
        if value == signal.SIGKILL:
            process.returncode = -9

    class Observer:
        def __init__(self, display):
            self.display, self.closed = display, False
            observers.append(self)

        def windows(self, pid, *, mapped_only=False):
            if mode["window"] and (mapped_only or mode["leftover_window"]):
                return [
                    {
                        "window_id": "0xf1",
                        "pid": pid,
                        "title": tool.TITLE,
                        "mapped": True,
                        "width": 1120,
                        "height": 820,
                    }
                ]
            return []

        def close(self):
            self.closed = True

    monkeypatch.setattr(tool.subprocess, "Popen", Process)
    monkeypatch.setattr(tool.os, "killpg", killpg)
    monkeypatch.setattr(tool, "group_alive", lambda *_: False)
    monkeypatch.setattr(tool, "X11Observer", Observer)
    return SimpleNamespace(
        binary=binary,
        processes=processes,
        signals=signals,
        observers=observers,
        diagnostics=diagnostics,
        mode=mode,
        diagnostic_body=diagnostic_body,
    )


def test_repeat_launch_requires_mapped_window_and_clean_sigterm_in_one_workspace(
    harness,
):
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is True and len(receipt["launches"]) == 2
    assert len(harness.processes) == 2
    assert harness.processes[0].args == harness.processes[1].args
    for row, process in zip(receipt["launches"], harness.processes):
        assert row["passed"] is True and row["exit_code"] == 0
        assert row["mapped_windows"][0]["pid"] == process.pid
        assert row["mapped_windows"][0]["mapped"] is True
        assert row["sigterm_sent"] is True and row["forced_cleanup"] is False
        assert (
            row["owned_group_remaining"] is False
            and row["owned_windows_remaining"] == []
        )
        assert process.kwargs["start_new_session"] is True
    assert harness.signals == [
        (process.pid, signal.SIGTERM) for process in harness.processes
    ]
    assert harness.observers[0].closed is True
    assert receipt["frozen_diagnostics"]["frozen"] is True
    assert receipt["provider_inference_exercised"] is False


def test_allowlisted_child_environment_does_not_inherit_provider_or_private_workspace(
    harness,
):
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is True
    for process in harness.processes:
        environment = process.kwargs["env"]
        assert set(environment) == {
            "PATH",
            "HOME",
            "LANG",
            "TZ",
            "DISPLAY",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_CACHE_HOME",
            "TMPDIR",
            "XAUTHORITY",
        }
        assert (
            "NEUROFORGE_API_KEY" not in environment
            and "SINTER_API_KEY" not in environment
        )
        assert environment["DISPLAY"] == ":42"
        assert environment["XAUTHORITY"] == "/fictional/ci-display-cookie"
        assert process.args[-1].startswith(environment["HOME"])
        assert process.kwargs["stdin"] == subprocess.DEVNULL
    assert harness.diagnostics[0].kwargs["env"] == harness.processes[0].kwargs["env"]
    assert harness.diagnostics[0].kwargs["start_new_session"] is True


def test_living_process_without_mapped_owned_window_fails_and_is_cleaned(harness):
    harness.mode["window"] = False
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and len(receipt["launches"]) == 1
    assert "mapped native window" in receipt["error"]
    assert harness.signals == [(harness.processes[0].pid, signal.SIGTERM)]
    assert receipt["launches"][0]["owned_group_remaining"] is False
    assert harness.observers[0].closed is True


def test_forced_kill_cannot_be_reported_as_sigterm_success(harness):
    harness.mode["force"] = True
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False
    assert receipt["launches"][0]["forced_cleanup"] is True
    assert [value for _, value in harness.signals] == [signal.SIGTERM, signal.SIGKILL]
    assert harness.observers[0].closed is True


@pytest.mark.parametrize("failure", ["exit", "window"])
def test_exit_failure_or_remaining_window_refuses_qualification(harness, failure):
    harness.mode["exit_code" if failure == "exit" else "leftover_window"] = (
        3 if failure == "exit" else True
    )
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False
    assert len(harness.processes) == 1
    assert harness.observers[0].closed is True


@pytest.mark.parametrize("display", ["", "remote.invalid:0", "localhost:0"])
def test_absent_or_nonlocal_display_fails_before_startup(harness, monkeypatch, display):
    monkeypatch.setenv("DISPLAY", display)
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and "authorised local DISPLAY" in receipt["error"]
    assert harness.processes == [] and harness.observers == []


def test_missing_x11_dependency_has_failure_receipt_without_process(
    harness, monkeypatch
):
    def missing(_):
        raise RuntimeError("libX11 unavailable in fictional test")

    monkeypatch.setattr(tool, "X11Observer", missing)
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and "libX11" in receipt["error"]
    assert harness.processes == []


@pytest.mark.parametrize(
    "capability",
    [
        "frozen",
        "core_assets_available",
        "native_toolkit_available",
        "Tcl_resources_available",
        "bundled_Tk_resources_available",
    ],
)
def test_missing_frozen_capability_fails_before_any_window_launch(
    harness, monkeypatch, capability
):
    harness.diagnostic_body["value"] = {**DIAGNOSTICS, capability: False}
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and capability in receipt["error"]
    assert harness.processes == [] and harness.observers[0].closed is True


def test_display_cleanup_failure_still_returns_a_failed_receipt(harness, monkeypatch):
    def broken_close(_):
        raise OSError("fictional X display close failure")

    monkeypatch.setattr(tool.X11Observer, "close", broken_close)
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and receipt["display_cleanup_error"] == "OSError"


def test_cli_writes_bounded_failure_evidence(harness, monkeypatch, tmp_path):
    monkeypatch.delenv("DISPLAY", raising=False)
    path = tmp_path / "artifacts" / "receipt.json"
    assert tool.main(["--binary", str(harness.binary), "--receipt", str(path)]) == 1
    receipt = json.loads(path.read_text())
    assert receipt["schema"] == "sinter-frozen-native-window-test/v1"
    assert receipt["passed"] is False and receipt["launches"] == []
    assert harness.processes == []


def test_receipt_cannot_overwrite_the_frozen_binary(harness):
    before = harness.binary.read_bytes()
    with pytest.raises(SystemExit) as error:
        tool.main(["--binary", str(harness.binary), "--receipt", str(harness.binary)])
    assert error.value.code == 2 and harness.binary.read_bytes() == before


def test_receipt_cannot_truncate_a_hardlink_to_the_binary(harness, tmp_path):
    alias = tmp_path / "receipt.json"
    alias.hardlink_to(harness.binary)
    before = harness.binary.read_bytes()
    with pytest.raises(SystemExit) as error:
        tool.main(["--binary", str(harness.binary), "--receipt", str(alias)])
    assert error.value.code == 2 and alias.read_bytes() == before


def test_diagnostic_timeout_stops_only_its_owned_group_before_receipt(harness):
    harness.diagnostic_body["timeout"] = True
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and receipt["error_type"] == "TimeoutExpired"
    assert harness.signals == [(900, signal.SIGTERM)]
    assert harness.processes == [] and harness.observers[0].closed is True


def test_oversized_diagnostic_output_fails_without_gui_launch(harness):
    harness.diagnostic_body["value"] = {**DIAGNOSTICS, "fictional_extra": "x" * 32_001}
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and "output bound" in receipt["error"]
    assert harness.processes == [] and harness.observers[0].closed is True


@pytest.mark.parametrize("change", [{"schema": "unsupported/v9"}, {"version": None}])
def test_diagnostic_schema_and_version_are_checked_before_gui_launch(harness, change):
    harness.diagnostic_body["value"] = {**DIAGNOSTICS, **change}
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and "schema/version" in receipt["error"]
    assert harness.processes == []
