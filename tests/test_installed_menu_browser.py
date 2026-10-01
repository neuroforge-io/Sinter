"""Installed launcher admission checks; no processes, browser or sockets."""

import os
import signal
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from tools import installed_menu_browser as tool
from tools import package_native


@pytest.mark.parametrize("native", [False, True])
def test_actual_package_entry_uses_one_explicit_runtime(tmp_path, native):
    path = tmp_path / "sinter.desktop"
    path.write_text(
        package_native.linux_desktop_entry(
            presentation="native" if native else "browser"
        )
    )
    assert tool.menu_command(path, native=native) == [
        tool.BINARY_COMMAND,
        "app",
        "--mode",
        "native" if native else "browser",
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("Exec", "/tmp/Fictional-Sinter app --mode browser"),
        ("Exec", "/opt/neuroforge/sinter/Sinter"),
        ("Exec", "/opt/neuroforge/sinter/Sinter app --mode native"),
        ("Exec", "/opt/neuroforge/sinter/Sinter app --mode browser --no-browser"),
        ("Exec", "sh -c 'fictional command'"),
        ("Terminal", "true"),
        ("Type", "Link"),
        ("Name", "Fictional other app"),
    ],
)
def test_conflicting_installed_entry_refuses_before_launch(tmp_path, field, value):
    text = package_native.linux_desktop_entry()
    text = "\n".join(
        f"{field}={value}" if line.startswith(field + "=") else line
        for line in text.splitlines()
    )
    path = tmp_path / "sinter.desktop"
    path.write_text(text)
    with pytest.raises(ValueError, match="menu command"):
        tool.menu_command(path)
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid",
        "http://localhost:1234",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:1234/path",
        "http://127.0.0.1:1234#fragment",
        "http://user:fictional@127.0.0.1:1234",
        "http://127.0.0.1:1234\n",
        "http://[::1]:1234",
    ],
)
def test_capture_refuses_unexpected_destinations(url):
    with pytest.raises(ValueError):
        tool.launch_url(url)


def test_exact_loopback_capture_is_accepted():
    assert tool.launch_url("http://127.0.0.1:65535") == "http://127.0.0.1:65535"


def test_linux_menu_admission_keeps_posix_command_on_windows(tmp_path, monkeypatch):
    path = tmp_path / "sinter.desktop"
    path.write_text(package_native.linux_desktop_entry())
    monkeypatch.setattr(tool, "BINARY", PureWindowsPath(tool.BINARY_COMMAND))
    assert tool.menu_command(path)[0] == "/opt/neuroforge/sinter/Sinter"


def test_saved_report_identity_is_separate_from_the_real_store_body(tmp_path):
    from sinter.store import Store

    store = Store(tmp_path / "fictional")
    original = {
        "title": "Fictional source note",
        "markdown": "Fictional approval unknown.",
    }
    identifier = store.save_report(original)
    project = {"id": "p" * 32, "document": {"title": "Fictional project"}}

    def read(path):
        if path == "/api/casebooks":
            return {"casebooks": [{"id": project["id"]}]}
        if path == "/api/casebooks/" + project["id"]:
            return project
        if path == "/api/reports":
            return {"reports": store.reports()}
        assert path == "/api/reports/" + identifier
        return store.report(identifier)

    before = tool.saved_snapshots(read)
    assert before["report_id"] == identifier
    assert before["report"] == store.report(identifier)
    assert "id" not in before["report"]
    assert before["report"]["markdown"] == original["markdown"]


def test_launch_environment_excludes_inherited_settings_and_keys(tmp_path, monkeypatch):
    for key in ("NEUROFORGE_API_KEY", "SINTER_API_KEY", "GH_TOKEN", "NEUROFORGE_MODEL"):
        monkeypatch.setenv(key, "fictional-never-forwarded")
    env = tool.launch_environment(
        tmp_path,
        tmp_path / "capture",
        Path("fictional capture.py"),
        "http://127.0.0.1:1234/v1",
    )
    assert all(
        key not in env
        for key in (
            "NEUROFORGE_API_KEY",
            "SINTER_API_KEY",
            "GH_TOKEN",
            "NEUROFORGE_MODEL",
        )
    )
    assert env["HOME"] == str(tmp_path)
    assert env["SINTER_DATA_DIR"] == str(tmp_path / "workspace")
    assert env["PATH"] == os.defpath
    assert env["NEUROFORGE_BASE_URL"] == "http://127.0.0.1:1234/v1"
    assert not (tmp_path / "workspace").exists()


def test_driver_sigterm_unwinds_owned_child_and_restores_handler(tmp_path, monkeypatch):
    original = signal.getsignal(signal.SIGTERM)
    process = SimpleNamespace(pid=12345, poll=lambda: None)
    stopped = []
    monkeypatch.setattr(tool.subprocess, "Popen", lambda *_, **__: process)
    monkeypatch.setattr(tool, "wait_launch", lambda *_: "http://127.0.0.1:1234")
    monkeypatch.setattr(tool, "group_alive", lambda _: False)
    monkeypatch.setattr(tool, "stop_process", lambda p, r: stopped.append(p.pid))
    row = {"launch": 1}
    with pytest.raises(KeyboardInterrupt), tool.cancellation_cleanup():
        with tool.installed_launch(
            [], tmp_path, tmp_path / "capture.py", "fictional", row
        ):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    assert stopped == [12345]
    assert signal.getsignal(signal.SIGTERM) is original
    assert row["pid"] == 12345 and "seconds" in row
