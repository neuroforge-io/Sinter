"""Exercise the generated package-menu command through its real CLI adapters."""

import configparser
import shlex
import signal
import sys
import threading
import types

import pytest

from sinter import cli, desktop
from tools import package_native


def menu_command(tmp_path, native_window):
    entry = tmp_path / "sinter.desktop"
    entry.write_text(
        package_native.linux_desktop_entry(native_window), encoding="utf-8"
    )
    parsed = configparser.ConfigParser(interpolation=None)
    parsed.read(entry, encoding="utf-8")
    section = parsed["Desktop Entry"]
    assert section["Type"] == "Application"
    assert section["Terminal"] == "false"
    return shlex.split(section["Exec"])


def test_native_shortcut_keeps_explicit_native_launch(tmp_path, monkeypatch):
    entry = package_native.linux_desktop_entry(True, presentation="native")
    parsed = configparser.ConfigParser(interpolation=None)
    parsed.read_string(entry)
    assert parsed["Desktop Entry"]["Name"] == "Sinter native source workspace"
    command = shlex.split(parsed["Desktop Entry"]["Exec"])
    assert command == ["/opt/neuroforge/sinter/Sinter", "app", "--mode", "native"]
    module = types.ModuleType("sinter.native_window")
    module.NativeWindowError = RuntimeError
    calls = []
    module.run_native = lambda directory: calls.append(directory) or 0
    monkeypatch.setitem(sys.modules, "sinter.native_window", module)
    monkeypatch.setattr(desktop, "make_server", lambda **_: pytest.fail("No server"))
    monkeypatch.setattr(
        desktop.webbrowser, "open", lambda *_: pytest.fail("No browser")
    )
    workspace = tmp_path / "Fictional native workspace"
    with pytest.raises(SystemExit) as exited:
        cli.main(command[1:] + ["--directory", str(workspace)])
    assert exited.value.code == 0
    assert calls == [str(workspace)]


class MenuServer:
    """Observe serving and cleanup without a socket, model or personal workspace."""

    server_port = 45678

    def __init__(self):
        self.stopped = threading.Event()
        self.closed = False
        self.app_closed = False
        self.scheduled = threading.Event()
        self.app = types.SimpleNamespace(
            close=self.close_app, scheduler=self.scheduled.set
        )

    def serve_forever(self):
        self.stopped.wait(5)

    def shutdown(self):
        self.stopped.set()

    def server_close(self):
        self.closed = True

    def close_app(self):
        self.app_closed = True


@pytest.mark.parametrize("native_window", [False, True])
def test_primary_menu_runs_full_browser_pipeline(tmp_path, monkeypatch, native_window):
    command = menu_command(tmp_path, native_window)
    assert command == ["/opt/neuroforge/sinter/Sinter", "app", "--mode", "browser"]
    module = types.ModuleType("sinter.native_window")
    module.NativeWindowError = RuntimeError
    module.run_native = lambda *_: pytest.fail("No omitted native window or fallback")
    monkeypatch.setitem(sys.modules, "sinter.native_window", module)
    instance = MenuServer()
    server_inputs, browser_urls = [], []

    def make_server(**kwargs):
        server_inputs.append(kwargs)
        return instance

    def open_browser(url):
        browser_urls.append(url)
        instance.shutdown()
        return True

    monkeypatch.setattr(desktop, "make_server", make_server)
    monkeypatch.setattr(desktop.webbrowser, "open", open_browser)
    previous_signal = signal.getsignal(signal.SIGTERM)
    workspace = tmp_path / "Fictional browser workspace"
    with pytest.raises(SystemExit) as exited:
        cli.main(command[1:] + ["--directory", str(workspace)])
    assert exited.value.code == 0
    assert server_inputs == [{"port": 0, "directory": str(workspace)}]
    assert browser_urls == ["http://127.0.0.1:45678"]
    assert instance.scheduled.wait(1)
    assert instance.closed and instance.app_closed and instance.stopped.is_set()
    assert signal.getsignal(signal.SIGTERM) is previous_signal


def test_browser_only_package_has_no_unusable_native_shortcut():
    assert set(package_native.linux_desktop_entries(False)) == {"sinter.desktop"}
    with pytest.raises(ValueError, match="not bundled"):
        package_native.linux_desktop_entry(False, presentation="native")


def test_native_package_has_two_shortcuts_into_the_same_runtime():
    entries = package_native.linux_desktop_entries(True)
    assert set(entries) == {"sinter.desktop", "sinter-native.desktop"}
    for name, mode in (
        ("sinter.desktop", "browser"),
        ("sinter-native.desktop", "native"),
    ):
        parsed = configparser.ConfigParser(interpolation=None)
        parsed.read_string(entries[name])
        assert parsed["Desktop Entry"]["Terminal"] == "false"
        assert shlex.split(parsed["Desktop Entry"]["Exec"]) == [
            "/opt/neuroforge/sinter/Sinter",
            "app",
            "--mode",
            mode,
        ]
