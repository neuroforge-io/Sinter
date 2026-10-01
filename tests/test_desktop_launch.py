"""Portable launch behavior without sockets, providers or desktop permissions."""

import runpy
import signal
import sqlite3
import sys
import threading
import types
from pathlib import Path

import pytest

from sinter import cli, desktop


def test_packaged_commands_use_existing_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "main", lambda args: calls.append(args))
    monkeypatch.setattr(desktop, "make_server", lambda **_: pytest.fail("No server"))
    assert desktop.main(["operations", "--format", "json"]) == 0
    assert calls == [["operations", "--format", "json"]]


def test_source_launcher_defaults_to_native_app_without_browser_or_server(monkeypatch):
    launcher = Path(__file__).parents[1] / "start.py"
    monkeypatch.setattr(sys, "argv", [str(launcher)])
    monkeypatch.setattr(sys, "path", sys.path.copy())
    calls = []
    monkeypatch.setattr(desktop, "main", lambda args: calls.append(args) or 0)
    monkeypatch.setattr(
        "sinter.server.serve", lambda *_: pytest.fail("No browser server")
    )
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(str(launcher), run_name="__main__")
    assert exited.value.code == 0
    assert calls == [["--mode", "native"]]


@pytest.mark.parametrize("arguments", [[], ["--mode", "native"]])
def test_default_native_launch_needs_no_browser_or_socket(monkeypatch, arguments):
    module = types.ModuleType("sinter.native_window")
    module.NativeWindowError = RuntimeError
    called = []
    module.run_native = lambda directory: called.append(directory) or 0
    monkeypatch.setitem(sys.modules, "sinter.native_window", module)
    monkeypatch.setattr(desktop, "make_server", lambda **_: pytest.fail("No server"))
    monkeypatch.setattr(
        desktop.webbrowser, "open", lambda *_: pytest.fail("No browser")
    )
    assert desktop.main(arguments + ["--directory", "selected-workspace"]) == 0
    assert called == ["selected-workspace"]


def test_native_failure_does_not_start_browser_fallback(monkeypatch, capsys):
    module = types.ModuleType("sinter.native_window")
    module.NativeWindowError = RuntimeError

    def unavailable(_):
        raise RuntimeError("No graphical display available.")

    module.run_native = unavailable
    monkeypatch.setitem(sys.modules, "sinter.native_window", module)
    monkeypatch.setattr(desktop, "make_server", lambda **_: pytest.fail("No server"))
    monkeypatch.setattr(
        desktop.webbrowser, "open", lambda *_: pytest.fail("No browser")
    )
    assert desktop.main([]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert (
        "No graphical display" in output.err
        and "No server or browser fallback" in output.err
    )
    assert "Traceback" not in output.err


@pytest.mark.parametrize(
    "failure",
    [
        OSError("fictional storage error"),
        sqlite3.DatabaseError("fictional corrupt database"),
    ],
)
def test_native_storage_failure_returns_guidance_without_fallback(
    monkeypatch, capsys, failure
):
    module = types.ModuleType("sinter.native_window")
    module.NativeWindowError = RuntimeError

    def unavailable(_):
        raise failure

    module.run_native = unavailable
    monkeypatch.setitem(sys.modules, "sinter.native_window", module)
    monkeypatch.setattr(desktop, "make_server", lambda **_: pytest.fail("No server"))
    assert desktop.main([]) == 1
    output = capsys.readouterr()
    assert output.out == "" and "local workspace" in output.err
    assert "Traceback" not in output.err and "fictional" not in output.err


@pytest.mark.parametrize(
    "arguments, expected",
    [
        (["--mode", "headless"], False),
        (["--no-browser"], False),
        (["--mode", "browser"], True),
        (["--mode", "native", "--no-browser"], False),
    ],
)
def test_browser_and_headless_modes_are_explicit(monkeypatch, arguments, expected):
    calls = []
    monkeypatch.setattr(
        desktop,
        "serve_desktop",
        lambda directory, **kwargs: calls.append((directory, kwargs)) or 0,
    )
    assert desktop.main(arguments + ["--directory", "fictional"]) == 0
    assert calls == [("fictional", {"open_browser": expected})]


def test_diagnostics_do_not_open_workspace_server_or_provider(monkeypatch, capsys):
    monkeypatch.setattr(desktop, "make_server", lambda **_: pytest.fail("No server"))
    monkeypatch.setattr(
        desktop.webbrowser, "open", lambda *_: pytest.fail("No browser")
    )
    assert desktop.main(["--diagnose"]) == 0
    import json

    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "sinter-launch-check/v1"
    assert result["core_assets_available"] is True
    assert result["native_display_tested"] is False
    assert result["browser_policy_tested"] is False and result["provider_requests"] == 0


class FakeServer:
    """Own a cancellable serving thread, with no actual networking."""

    server_port = 45678

    def __init__(self):
        self.stopped = threading.Event()
        self.closed = False
        self.app_closed = False
        self.scheduled = False
        self.app = types.SimpleNamespace(close=self.close_app, scheduler=self.schedule)

    def serve_forever(self):
        self.stopped.wait(5)

    def shutdown(self):
        self.stopped.set()

    def server_close(self):
        self.closed = True

    def close_app(self):
        self.app_closed = True

    def schedule(self):
        self.scheduled = True


@pytest.mark.parametrize(
    "outcome", [False, OSError("Unavailable"), desktop.webbrowser.Error("Unavailable")]
)
def test_failed_browser_launch_exits_and_cleans_owned_server(
    monkeypatch, capsys, outcome
):
    instance = FakeServer()
    previous = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr(desktop, "make_server", lambda **_: instance)

    def browser(_):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(desktop.webbrowser, "open", browser)
    assert desktop.serve_desktop("fictional", open_browser=True) == 1
    assert instance.closed and instance.app_closed and instance.stopped.is_set()
    assert not instance.scheduled
    assert signal.getsignal(signal.SIGTERM) is previous
    output = capsys.readouterr()
    assert "http://127.0.0.1:45678" in output.out
    assert "local server has stopped" in output.err


def test_headless_interrupt_cleans_server_and_restores_signal(monkeypatch, capsys):
    instance = FakeServer()
    previous = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr(desktop, "make_server", lambda **_: instance)
    original_join = threading.Thread.join
    interrupted = False

    def join(thread, timeout=None):
        nonlocal interrupted
        if thread.name == "sinter-http" and not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return original_join(thread, timeout)

    monkeypatch.setattr(threading.Thread, "join", join)
    assert desktop.serve_desktop("fictional") == 0
    assert instance.closed and instance.app_closed and instance.stopped.is_set()
    assert signal.getsignal(signal.SIGTERM) is previous
    assert "Stopped." in capsys.readouterr().err


def test_denied_socket_has_clear_error_and_no_traceback(monkeypatch, capsys):
    def denied(**_):
        raise PermissionError("socket denied")

    monkeypatch.setattr(desktop, "make_server", denied)
    assert desktop.serve_desktop("fictional") == 1
    output = capsys.readouterr()
    assert output.out == "" and "PermissionError" in output.err
    assert (
        "native workspace or offline CLI" in output.err
        and "Traceback" not in output.err
    )
