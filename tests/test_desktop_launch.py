"""Portable launch behavior without sockets, providers or desktop permissions."""

import json
import runpy
import signal
import socket
import sqlite3
import sys
import threading
import types
from pathlib import Path

import pytest

from sinter import cli, client, desktop


@pytest.fixture
def offline_command_entry(tmp_path, monkeypatch):
    """Exercise the real command entry using only disposable local state."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("SINTER_DATA_DIR", str(tmp_path / "workspace"))
    for name in (
        "NEUROFORGE_BASE_URL",
        "NEUROFORGE_MODEL",
        "NEUROFORGE_API_KEY",
        "SINTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("Command discovery and local fixtures need no external access")

    monkeypatch.setattr(client, "_open", forbidden)
    monkeypatch.setattr(client, "_load_key", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(desktop, "make_server", forbidden)
    monkeypatch.setattr(desktop, "serve_desktop", forbidden)
    monkeypatch.setattr(desktop.webbrowser, "open", forbidden)
    native = types.ModuleType("sinter.native_window")
    native.NativeWindowError = RuntimeError
    native.run_native = forbidden
    monkeypatch.setitem(sys.modules, "sinter.native_window", native)

    def invoke(kind, arguments):
        try:
            if kind == "desktop":
                return desktop.main(arguments)
            launcher = Path(__file__).parents[1] / "packaging" / "desktop_entry.py"
            monkeypatch.setattr(sys, "argv", ["Sinter", *arguments])
            runpy.run_path(str(launcher), run_name="__main__")
        except SystemExit as exited:
            return exited.code
        pytest.fail("The packaging entry must return its process exit code")

    return invoke


@pytest.mark.parametrize("entry", ["desktop", "packaging"])
def test_portable_help_discovers_shared_commands_without_runtime(
    entry, offline_command_entry, tmp_path, capsys
):
    assert offline_command_entry(entry, ["--help"]) == 0
    output = capsys.readouterr()
    for command in ("operations", "run", "status", "app", "import", "export"):
        assert command in output.out
    for flag in ("--self-test", "--mode", "--directory", "--diagnose", "--version"):
        assert flag in output.out
    assert "Sinter operations --format json" in output.out
    assert output.err == "" and not (tmp_path / "workspace").exists()


@pytest.mark.parametrize("entry", ["desktop", "packaging"])
@pytest.mark.parametrize(
    "command", ["operations", "run", "status", "app", "import", "export"]
)
def test_portable_command_help_uses_real_cli_parser(
    entry, command, offline_command_entry, tmp_path, capsys
):
    assert offline_command_entry(entry, [command, "--help"]) == 0
    output = capsys.readouterr()
    assert "usage:" in output.out and f"sinter {command}" in output.out
    assert output.err == "" and not (tmp_path / "workspace").exists()


def test_cli_parser_can_describe_a_console_name_without_dispatch(
    offline_command_entry, tmp_path
):
    parser = cli.build_parser(prog="Sinter.exe")
    assert "usage: Sinter.exe" in parser.format_help()
    arguments = parser.parse_args(["operations", "--format", "json"])
    assert arguments.command == "operations"
    assert not (tmp_path / "workspace").exists()


@pytest.mark.parametrize("entry", ["desktop", "packaging"])
def test_portable_operations_print_one_json_result_without_workspace(
    entry, offline_command_entry, tmp_path, capsys
):
    assert offline_command_entry(entry, ["operations", "--format", "json"]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert len(output.out.splitlines()) == 1 and output.err == ""
    assert result["schema"] == "sinter-operation-result/v1" and result["ok"] is True
    assert result["operation"] == "operations"
    operations = {row["id"] for row in result["result"]["operations"]}
    assert {"runtime.status", "casebooks.save", "template.preview"} <= operations
    assert not (tmp_path / "workspace").exists()


@pytest.mark.parametrize("entry", ["desktop", "packaging"])
def test_portable_status_and_run_use_real_local_runtime(
    entry, offline_command_entry, tmp_path, capsys
):
    directory = tmp_path / "fictional-workspace"
    options = ["--directory", str(directory), "--format", "json"]
    assert offline_command_entry(entry, ["status", *options]) == 0
    output = capsys.readouterr()
    status = json.loads(output.out)
    assert len(output.out.splitlines()) == 1 and output.err == ""
    assert status["ok"] is True and status["operation"] == "runtime.status"
    assert status["result"]["workspace"] == str(directory.resolve())
    assert status["result"]["provider_tested"] is False
    assert status["result"]["watch_scheduler_started_by_runtime"] is False
    assert set(status["result"]["counts"].values()) == {0}
    assert (directory / "workspace.sqlite3").is_file()

    assert offline_command_entry(entry, ["run", "casebooks.list", *options]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert len(output.out.splitlines()) == 1 and output.err == ""
    assert result["ok"] is True and result["operation"] == "casebooks.list"
    assert result["result"] == {"casebooks": []}


@pytest.mark.parametrize("entry", ["desktop", "packaging"])
@pytest.mark.parametrize(
    "failure", ["unknown_operation", "invalid_input", "missing_item"]
)
def test_portable_commands_preserve_json_errors_and_exit_codes(
    entry, failure, offline_command_entry, tmp_path, capsys
):
    directory = tmp_path / "fictional-workspace"
    options = ["--directory", str(directory), "--format", "json"]
    if failure == "unknown_operation":
        arguments = ["run", "fictional.unsupported", *options]
        code, error = 2, "unknown_operation"
    else:
        source = tmp_path / "fictional-request.json"
        source.write_text(
            "{fictional malformed JSON}"
            if failure == "invalid_input"
            else json.dumps({"id": "f" * 32}),
            encoding="utf-8",
        )
        arguments = ["run", "casebooks.get", "--input", str(source), *options]
        code, error = (
            (2, "invalid_input") if failure == "invalid_input" else (1, "not_found")
        )
    assert offline_command_entry(entry, arguments) == code
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert len(output.out.splitlines()) == 1
    assert result["ok"] is False and result["error"]["code"] == error
    assert "Sinter:" in output.err and "Traceback" not in output.err
    if failure != "missing_item":
        assert not directory.exists()


@pytest.mark.parametrize("entry", ["desktop", "packaging"])
def test_portable_unknown_command_keeps_usage_exit_on_stderr(
    entry, offline_command_entry, tmp_path, capsys
):
    assert offline_command_entry(entry, ["fictional-unknown-command"]) == 2
    output = capsys.readouterr()
    assert output.out == "" and "invalid choice" in output.err
    assert "usage:" in output.err and "Traceback" not in output.err
    assert not (tmp_path / "workspace").exists()


def test_portable_version_and_self_test_keep_legacy_dispatch(
    offline_command_entry, tmp_path, monkeypatch, capsys
):
    assert offline_command_entry("packaging", ["--version"]) == 0
    output = capsys.readouterr()
    assert output.out.strip() == desktop.__version__ and output.err == ""
    calls = []
    monkeypatch.setattr(desktop, "self_test", lambda name: calls.append(name) or 1)
    destination = str(tmp_path / "fictional-self-test.json")
    assert offline_command_entry("packaging", ["--self-test", destination]) == 1
    assert calls == [destination] and not (tmp_path / "workspace").exists()


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
