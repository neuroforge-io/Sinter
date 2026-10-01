"""Installed launcher admission checks; no processes, browser or sockets."""

import base64
import hashlib
import json
import os
import signal
import subprocess
import sys
import types
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from tools import installed_menu_browser as tool
from tools import package_native

EXPECTED_NOTICE = (
    b"Press Ctrl+C to stop. Closing a browser tab alone does not quit Sinter.\n"
)


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


def diagnostic_process(monkeypatch, raw, *, needs_cleanup=False):
    """Write genuine stream bytes through a fake process; never create a child."""
    process = SimpleNamespace(pid=12345, poll=lambda: None if needs_cleanup else 0)

    def start(*_, **kwargs):
        kwargs["stderr"].write(raw)
        kwargs["stderr"].flush()
        return process

    monkeypatch.setattr(tool.subprocess, "Popen", start)
    monkeypatch.setattr(tool, "wait_launch", lambda *_: "http://127.0.0.1:1234")
    monkeypatch.setattr(tool, "group_alive", lambda _: False)
    return process


def test_unexpected_callback_diagnostic_refuses_success(tmp_path, monkeypatch):
    raw = (
        b"Exception in callback\nRuntimeError: fictional saved-menu callback failure\n"
    )
    diagnostic_process(monkeypatch, raw)
    row = {"launch": 1, "passed": False}
    with pytest.raises(RuntimeError, match="diagnostic"):
        with tool.installed_launch(
            [], tmp_path, tmp_path / "capture.py", "fictional", row
        ):
            row["passed"] = True
    assert row["passed"] is False
    assert row.get("stderr_bytes") == len(raw)


def test_large_diagnostic_records_full_stream_and_bounded_sample(tmp_path, monkeypatch):
    raw = b"Fictional diagnostic line\n" * 3000
    diagnostic_process(monkeypatch, raw)
    row = {"launch": 1, "passed": False}
    refusal = None
    try:
        with tool.installed_launch(
            [], tmp_path, tmp_path / "capture.py", "fictional", row
        ):
            row["passed"] = True
    except RuntimeError as error:
        refusal = error
    assert row.get("stderr_bytes") == len(raw)
    assert row.get("stderr_sha256") == hashlib.sha256(raw).hexdigest()
    assert row.get("stderr_truncated") is True
    assert base64.b64decode(row["stderr_base64"]) == raw[:65_536]
    assert row["passed"] is False
    assert refusal is not None and "diagnostic" in str(refusal)


def test_cleanup_failure_retains_original_diagnostic(tmp_path, monkeypatch):
    raw = b"Fictional diagnostic before cleanup failure\n"
    diagnostic_process(monkeypatch, raw, needs_cleanup=True)
    failure = RuntimeError("Fictional cleanup observation failure")

    def cleanup(*_):
        raise failure

    monkeypatch.setattr(tool, "stop_process", cleanup)
    row = {"launch": 1, "passed": False}
    with pytest.raises(RuntimeError) as raised:
        with tool.installed_launch(
            [], tmp_path, tmp_path / "capture.py", "fictional", row
        ):
            row["passed"] = True
    assert raised.value is failure
    assert row.get("stderr_bytes") == len(raw)
    assert row.get("stderr_sha256") == hashlib.sha256(raw).hexdigest()
    assert row.get("stderr_truncated") is False
    assert row["passed"] is False


def test_exact_source_browser_notice_is_accepted(tmp_path, monkeypatch):
    raw = tool.browser_notice((tool.ROOT / "src/sinter/desktop.py").read_bytes())
    assert len(raw) == 72
    diagnostic_process(monkeypatch, raw)
    row = {"launch": 1, "passed": False}
    with tool.installed_launch([], tmp_path, tmp_path / "capture.py", "fictional", row):
        row["passed"] = True
    assert row["passed"] is True
    assert row["stderr_expected_browser_notice"] is True
    assert row["stderr_bytes"] == len(raw)
    assert row["stderr_sha256"] == hashlib.sha256(raw).hexdigest()
    assert base64.b64decode(row["stderr_base64"]) == raw
    assert row["stderr_truncated"] is False


@pytest.mark.parametrize(
    "raw",
    [b"", b" \n", b"\xff", EXPECTED_NOTICE + b"\n", EXPECTED_NOTICE * 2],
)
def test_only_exact_notice_is_accepted(tmp_path, monkeypatch, raw):
    diagnostic_process(monkeypatch, raw)
    row = {"launch": 1, "passed": False}
    with pytest.raises(RuntimeError, match="diagnostic"):
        with tool.installed_launch(
            [], tmp_path, tmp_path / "capture.py", "fictional", row
        ):
            row["passed"] = True
    assert row["passed"] is False
    assert row["stderr_expected_browser_notice"] is False
    assert row["stderr_bytes"] == len(raw)
    assert row["stderr_sha256"] == hashlib.sha256(raw).hexdigest()
    assert base64.b64decode(row["stderr_base64"]) == raw


def test_group_observation_failure_still_captures_stderr(tmp_path, monkeypatch):
    diagnostic_process(monkeypatch, EXPECTED_NOTICE)
    failure = OSError("Fictional group observation failure")

    def group(*_):
        raise failure

    monkeypatch.setattr(tool, "group_alive", group)
    row = {"launch": 1, "passed": False}
    with pytest.raises(OSError) as raised:
        with tool.installed_launch(
            [], tmp_path, tmp_path / "capture.py", "fictional", row
        ):
            row["passed"] = True
    assert raised.value is failure
    assert row["cleanup_error"] == "OSError"
    assert base64.b64decode(row["stderr_base64"]) == EXPECTED_NOTICE
    assert row["stderr_expected_browser_notice"] is True
    assert row["passed"] is False


@pytest.mark.parametrize(
    "failure", [RuntimeError("Fictional browser failure"), KeyboardInterrupt()]
)
def test_original_body_failure_survives_cleanup_and_diagnostics(
    tmp_path, monkeypatch, failure
):
    raw = b"Fictional diagnostic before body and cleanup failures\n"
    diagnostic_process(monkeypatch, raw, needs_cleanup=True)

    def cleanup(*_):
        raise OSError("Fictional cleanup failure")

    monkeypatch.setattr(tool, "stop_process", cleanup)
    row = {"launch": 1, "passed": False}
    with pytest.raises(type(failure)) as raised:
        with tool.installed_launch(
            [], tmp_path, tmp_path / "capture.py", "fictional", row
        ):
            raise failure
    assert raised.value is failure
    assert row["cleanup_error"] == "OSError"
    assert base64.b64decode(row["stderr_base64"]) == raw
    assert row["stderr_expected_browser_notice"] is False
    assert row["passed"] is False


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_capture_failure_is_explicit_and_preserves_cleanup_priority(
    tmp_path, monkeypatch, cleanup_fails
):
    diagnostic_process(monkeypatch, EXPECTED_NOTICE, needs_cleanup=cleanup_fails)
    capture_failure = OSError("Fictional diagnostic stream read failure")
    cleanup_failure = RuntimeError("Fictional cleanup failure")

    def capture(*_):
        raise capture_failure

    def cleanup(*_):
        raise cleanup_failure

    monkeypatch.setattr(tool, "capture_stderr", capture)
    monkeypatch.setattr(tool, "stop_process", cleanup)
    row = {"launch": 1, "passed": False}
    with pytest.raises(RuntimeError if cleanup_fails else OSError) as raised:
        with tool.installed_launch(
            [], tmp_path, tmp_path / "capture.py", "fictional", row
        ):
            row["passed"] = True
    assert raised.value is (cleanup_failure if cleanup_fails else capture_failure)
    assert row["stderr_capture_error"] == "OSError"
    assert "stderr_bytes" not in row
    assert row["stderr_expected_browser_notice"] is False
    assert row["passed"] is False and "seconds" in row


def notice_source():
    return (
        "import sys\n"
        "def serve_desktop():\n"
        f"    print({EXPECTED_NOTICE[:-1].decode('ascii')!r}, file=sys.stderr)\n"
    ).encode("utf-8")


def test_notice_must_be_the_actual_stderr_print_in_source():
    assert tool.browser_notice(notice_source()) == EXPECTED_NOTICE


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace(b"Closing", b"Fictional"),
        lambda s: s.replace(b"file=sys.stderr", b"file=sys.stdout"),
        lambda s: s.replace(b"print(", b"# print("),
        lambda s: s.replace(b"print(", b"value = ("),
        lambda s: s.replace(b"serve_desktop", b"other_function"),
        lambda s: s + s,
        lambda s: s + s.split(b"def serve_desktop():\n")[1].lstrip(),
        lambda s: s + b"\xff",
    ],
)
def test_edited_missing_duplicate_or_malformed_notice_source_refuses(change):
    with pytest.raises(ValueError, match="notice"):
        tool.browser_notice(change(notice_source()))


def test_candidate_notice_is_bound_to_build_commit_and_checkout(tmp_path, monkeypatch):
    source = notice_source()
    path = tmp_path / "src/sinter/desktop.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(source)
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    calls = []

    def git(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=source)

    monkeypatch.setattr(tool.subprocess, "run", git)
    commit = "1" * 40
    assert tool.source_browser_notice(commit) == (
        EXPECTED_NOTICE,
        hashlib.sha256(source).hexdigest(),
    )
    args, kwargs = calls[0]
    assert args == ["git", "show", commit + ":src/sinter/desktop.py"]
    assert kwargs == dict(cwd=tmp_path, capture_output=True, check=True, timeout=10)
    path.write_bytes(source + b"# Fictional changed checkout\n")
    with pytest.raises(ValueError, match="differs"):
        tool.source_browser_notice(commit)


@pytest.mark.parametrize("commit", ["", "1" * 39, "1" * 41, "g" * 40, 1, True])
def test_notice_source_identity_refuses_before_git(monkeypatch, commit):
    monkeypatch.setattr(
        tool.subprocess, "run", lambda *_a, **_kw: pytest.fail("No Git read admitted")
    )
    with pytest.raises(ValueError, match="identity"):
        tool.source_browser_notice(commit)


def test_missing_build_object_remains_a_distinct_failure(monkeypatch):
    failure = subprocess.CalledProcessError(128, ["git", "show", "fictional"])

    def git(*_a, **_kw):
        raise failure

    monkeypatch.setattr(tool.subprocess, "run", git)
    with pytest.raises(subprocess.CalledProcessError) as raised:
        tool.source_browser_notice("1" * 40)
    assert raised.value is failure


@pytest.mark.parametrize(
    "notice", [b"", b"Fictional arbitrary warning\n", "notice", True]
)
def test_callable_notice_override_cannot_admit_other_output(
    tmp_path, monkeypatch, notice
):
    monkeypatch.setattr(
        tool.subprocess, "Popen", lambda *_a, **_kw: pytest.fail("No child admitted")
    )
    with pytest.raises(ValueError, match="exact candidate"):
        with tool.installed_launch(
            [],
            tmp_path,
            tmp_path / "capture.py",
            "fictional",
            {"launch": 1},
            expected_notice=notice,
        ):
            pytest.fail("No launch admitted")


def test_run_rejects_notice_source_drift_before_any_launch(tmp_path, monkeypatch):
    def forbidden(*_a, **_kw):
        pytest.fail("No application, browser or provider trap admitted")

    api = types.ModuleType("playwright.sync_api")
    api.sync_playwright = forbidden
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    monkeypatch.setattr(tool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tool, "HTTPServer", forbidden)
    monkeypatch.setattr(tool.subprocess, "Popen", forbidden)
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    source = tmp_path / "src/sinter/desktop.py"
    source.parent.mkdir(parents=True)
    original = notice_source()
    source.write_bytes(original + b"# Fictional checkout drift\n")
    monkeypatch.setattr(
        tool.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(stdout=original)
    )
    binary = tmp_path / "Fictional-Sinter"
    binary.write_bytes(b"Fictional never-run executable")
    monkeypatch.setattr(tool, "BINARY", binary)
    installer = tmp_path / "fictional.deb"
    installer.write_bytes(b"Fictional never-installed archive")
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps(
            {
                "passed": True,
                "source_commit": "1" * 40,
                "installer_sha256": tool.digest(installer),
                "frozen_cli_test": {"binary_sha256": tool.digest(binary)},
            }
        )
    )
    receipt = tmp_path / "receipt.json"
    args = SimpleNamespace(
        source_commit="1" * 40,
        installer=installer,
        package_receipt=package,
        receipt=receipt,
    )
    with pytest.raises(ValueError, match="differs"):
        tool.run(args)
    result = json.loads(receipt.read_bytes())
    assert result["schema"] == "sinter-installed-menu-first-run/v1"
    assert result["passed"] is False and result["launches"] == []
    assert "workflow_passed" not in result
    assert source.read_bytes() == original + b"# Fictional checkout drift\n"
