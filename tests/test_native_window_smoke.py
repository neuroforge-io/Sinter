"""Tiny process/display mocks; these tests never launch GUI or frozen services."""

from __future__ import annotations

import base64
import hashlib
import json
import signal
import sqlite3
import subprocess
from pathlib import Path
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
OLD_CALLBACK_STDERR = (
    "Exception in Tkinter callback\n"
    "Traceback (most recent call last):\n"
    '  File "tkinter/__init__.py", line 1921, in __call__\n'
    '  File "tkinter/__init__.py", line 3569, in set\n'
    "_tkinter.TclError: invalid command name "
    '".!frame.!panedwindow.!notebook2.!frame.!frame4.!scrollbar"\n'
).encode()


@pytest.fixture
def harness(tmp_path, monkeypatch):
    from sinter import client

    def no_provider(*args, **kwargs):
        raise AssertionError("Native-window qualification must remain offline")

    for name in ("chat", "search", "_post", "_get", "_open"):
        monkeypatch.setattr(client, name, no_provider)
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
    processes, signals, observers, diagnostics, commands = [], [], [], [], []
    mode = {
        "window": True,
        "exit_code": 0,
        "force": False,
        "leftover_window": False,
        "stderr": b"",
        "mutate": None,
        "command_change": None,
        "command_stderr": b"",
    }
    diagnostic_body = {"value": DIAGNOSTICS, "timeout": False, "stderr": b""}

    class Process:
        def __init__(self, args, **kwargs):
            self.pid = 1000 + len(processes)
            self.returncode = None
            self.args, self.kwargs = args, kwargs
            if args[-1] == "--diagnose":
                self.pid = 900
                kwargs["stdout"].write(json.dumps(diagnostic_body["value"]).encode())
                kwargs["stderr"].write(diagnostic_body["stderr"])
                diagnostics.append(self)
            elif args[1] == "run":
                # This unit harness uses real local storage/admission without
                # launching a binary or contacting any provider.
                from sinter.runtime import Runtime

                self.pid = 2000 + len(commands)
                directory = args[args.index("--directory") + 1]
                request = json.loads(Path(args[args.index("--input") + 1]).read_text())
                with Runtime(directory) as runtime:
                    result = runtime.call(args[2], request)
                value = {
                    "schema": "sinter-operation-result/v1",
                    "operation": args[2],
                    "version": DIAGNOSTICS["version"],
                    "ok": True,
                    "result": result,
                }
                if mode["command_change"]:
                    mode["command_change"](value)
                kwargs["stdout"].write(json.dumps(value, ensure_ascii=False).encode())
                kwargs["stderr"].write(mode["command_stderr"])
                self.returncode = 0
                commands.append(self)
            else:
                kwargs["stderr"].write(mode["stderr"])
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
            if mode["mutate"] and process in processes:
                mode["mutate"](Path(process.args[-1]))
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
    monkeypatch.setattr(tool.os, "killpg", killpg, raising=False)
    monkeypatch.setattr(tool.signal, "SIGKILL", 9, raising=False)
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
        commands=commands,
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
    assert receipt["binary_unchanged"] is True
    assert receipt["binary_sha256_after"] == receipt["binary_sha256"]
    assert receipt["diagnostic_process"]["passed"] is True
    assert receipt["diagnostic_process"]["stderr_bytes"] == 0
    assert receipt["fictional_workspace"]["saved_revision"] == 1
    for row in receipt["launches"]:
        assert row["saved_workspace_exact"] is True
        assert row["saved_casebook_exact"] is True
        assert row["explicit_model_selection_exact"] is True
        assert row["preferences_read_without_warning"] is True
        assert row["cli_read_preserved_saved_bytes"] is True
        assert row["stderr_bytes"] == 0 and row["stderr_truncated"] is False
    assert [process.args[2] for process in harness.commands] == [
        "casebooks.save",
        "casebooks.get",
        "runtime.status",
        "casebooks.get",
        "runtime.status",
        "casebooks.get",
        "runtime.status",
    ]


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
    for process in harness.commands:
        assert process.kwargs["env"] == harness.processes[0].kwargs["env"]
        assert process.kwargs["stdin"] == subprocess.DEVNULL
        assert process.kwargs["start_new_session"] is True


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


@pytest.mark.parametrize(
    "stderr",
    [
        OLD_CALLBACK_STDERR,
        b"x" * 5000 + OLD_CALLBACK_STDERR,
        b"x" * 65_537 + OLD_CALLBACK_STDERR,
        b"unclassified native diagnostic: \xff\x00\n",
        b" \n\t",
    ],
    ids=[
        "actual-callback",
        "past-old-prefix",
        "past-new-prefix",
        "invalid-utf8",
        "whitespace",
    ],
)
def test_exit_zero_callback_or_unclassified_stderr_is_not_clean(harness, stderr):
    harness.mode["stderr"] = stderr
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and "zero exit code" in receipt["error"]
    assert len(receipt["launches"]) == 1
    row = receipt["launches"][0]
    assert row["exit_code"] == 0 and row["sigterm_sent"] is True
    assert row["forced_cleanup"] is False and row["passed"] is False
    assert row["saved_workspace_exact"] is True
    assert row["saved_casebook_exact"] is True
    assert row["explicit_model_selection_exact"] is True
    assert row["stderr_bytes"] == len(stderr)
    assert row["stderr_sha256"] == hashlib.sha256(stderr).hexdigest()
    assert base64.b64decode(row["stderr_base64"]) == stderr[: tool.MAX_STDERR_BYTES]
    assert row["stderr_truncated"] is (len(stderr) > tool.MAX_STDERR_BYTES)
    assert harness.observers[0].closed is True
    assert harness.signals == [(harness.processes[0].pid, signal.SIGTERM)]
    assert not row["owned_group_remaining"] and row["owned_windows_remaining"] == []


@pytest.mark.parametrize(
    "mutation", ["preference", "revision", "source", "schema", "version"]
)
def test_saved_fictional_bytes_must_survive_clean_shutdown(harness, mutation):
    def mutate(workspace):
        if mutation == "preference":
            preferences = workspace / "preferences.json"
            # Even semantically equivalent whitespace must not rewrite originals.
            preferences.write_bytes(preferences.read_bytes() + b" ")
            return
        with sqlite3.connect(workspace / "workspace.sqlite3") as db:
            if mutation == "revision":
                db.execute("UPDATE casebooks SET revision=revision+1")
            elif mutation == "schema":
                db.execute("CREATE TABLE unexpected_native_mutation (value TEXT)")
            elif mutation == "version":
                db.execute("PRAGMA user_version=0")
            else:
                document = json.loads(
                    db.execute("SELECT document FROM casebooks").fetchone()[0]
                )
                document["documents"][0]["content"] = (
                    "A rewritten source is not the original."
                )
                db.execute("UPDATE casebooks SET document=?", (json.dumps(document),))

    harness.mode["mutate"] = mutate
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and "changed during launch" in receipt["error"]
    assert len(receipt["launches"]) == 1
    row = receipt["launches"][0]
    assert row["exit_code"] == 0 and row["stderr_bytes"] == 0
    assert row["saved_workspace_exact"] is False and row["passed"] is False
    assert row["workspace_snapshot"] != receipt["fictional_workspace"]["original"]
    assert len(harness.commands) == 3  # No replay or repair after the failure.
    if mutation == "version":
        assert row["workspace_snapshot"]["sqlite_user_version"] == 0
        assert receipt["fictional_workspace"]["original"]["sqlite_user_version"] == 1
        assert (
            row["workspace_snapshot"]["sqlite_logical_sha256"]
            == (receipt["fictional_workspace"]["original"]["sqlite_logical_sha256"])
        )


@pytest.mark.parametrize(
    "change",
    [
        {"version": "wrong-candidate"},
        {"operation": "reports.save"},
        {"schema": "other/v1"},
        {"ok": False},
        {"result": []},
    ],
)
def test_fictional_cli_identity_failure_refuses_before_window(harness, change):
    harness.mode["command_change"] = lambda value: value.update(change)
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and "result identity" in receipt["error"]
    assert harness.processes == [] and receipt["launches"] == []
    assert len(receipt["offline_commands"]) == 1
    assert receipt["offline_commands"][0]["passed"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("connection", {"model": "silently-fallback-model"}),
        ("preferences_warning", "Original preferences unreadable"),
        ("provider_tested", True),
        ("counts", {"casebooks": 0, "campaigns": 0, "reports": 0, "watches": 0}),
    ],
)
def test_target_must_read_preserved_preferences_and_saved_work(harness, field, value):
    def change(envelope):
        if envelope["operation"] == "runtime.status":
            envelope["result"][field] = value

    harness.mode["command_change"] = change
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and "recover the exact" in receipt["error"]
    assert receipt["launches"] == [] and harness.processes == []
    assert receipt["fictional_workspace"]["saved_workspace_exact"] is True


def test_cli_diagnostic_evidence_is_retained_and_no_native_launch_replayed(harness):
    harness.mode["command_stderr"] = b"fictional offline command failure \xff\n"
    receipt = tool.smoke(harness.binary)
    assert (
        receipt["passed"] is False and "CLI preparation/read failed" in receipt["error"]
    )
    assert len(receipt["offline_commands"]) == 1 and receipt["launches"] == []
    row = receipt["offline_commands"][0]
    assert base64.b64decode(row["stderr_base64"]) == harness.mode["command_stderr"]
    assert row["passed"] is False and harness.processes == []


def test_cli_receipt_retains_actual_old_callback_bytes_after_exit_zero(
    harness, tmp_path
):
    harness.mode["stderr"] = OLD_CALLBACK_STDERR
    target = tmp_path / "native-window-receipt.json"
    assert tool.main(["--binary", str(harness.binary), "--receipt", str(target)]) == 1
    receipt = json.loads(target.read_text())
    row = receipt["launches"][0]
    assert row["exit_code"] == 0 and receipt["passed"] is False
    assert row["stderr"].encode() == OLD_CALLBACK_STDERR
    assert base64.b64decode(row["stderr_base64"]) == OLD_CALLBACK_STDERR


def test_launch_and_preservation_failures_are_both_retained(harness):
    harness.mode["stderr"] = OLD_CALLBACK_STDERR

    def corrupt(workspace):
        (workspace / "preferences.json").write_bytes(b"corrupted fictional preferences")

    harness.mode["mutate"] = corrupt
    receipt = tool.smoke(harness.binary)
    row = receipt["launches"][0]
    assert receipt["passed"] is False and row["passed"] is False
    assert "zero exit code" in receipt["error"]
    assert row["saved_workspace_exact"] is False
    assert "changed during launch" in row["workspace_verification_error"]
    assert base64.b64decode(row["stderr_base64"]) == OLD_CALLBACK_STDERR
    assert len(harness.processes) == 1 and len(harness.commands) == 3


def test_launch_producer_cannot_add_hosted_operation(harness, tmp_path):
    receipt = {"offline_commands": []}
    with pytest.raises(ValueError, match="fictional local operations"):
        tool.local_operation(harness.binary, tmp_path, {}, "template.run", {}, receipt)
    assert harness.commands == [] and harness.processes == []


@pytest.mark.parametrize(
    "stderr",
    [OLD_CALLBACK_STDERR, b" \n", b"\xff\x00", b" " * 65_537 + OLD_CALLBACK_STDERR],
    ids=["callback", "whitespace", "invalid-utf8", "tail"],
)
def test_diagnostic_stderr_fails_before_data_or_window_and_is_retained(harness, stderr):
    harness.diagnostic_body["stderr"] = stderr
    receipt = tool.smoke(harness.binary)
    assert (
        receipt["passed"] is False and "diagnostics emitted stderr" in receipt["error"]
    )
    assert receipt["offline_commands"] == [] and receipt["launches"] == []
    row = receipt["diagnostic_process"]
    assert row["passed"] is False and row["exit_code"] == 0
    assert row["stderr_bytes"] == len(stderr)
    assert row["stderr_sha256"] == hashlib.sha256(stderr).hexdigest()
    assert base64.b64decode(row["stderr_base64"]) == stderr[:65_536]
    assert row["stderr_truncated"] is (len(stderr) > 65_536)
    assert harness.processes == [] and harness.commands == []
    assert harness.observers[0].closed is True


def test_binary_mutation_rejects_otherwise_clean_repeat_proof(harness):
    harness.mode["mutate"] = lambda _: harness.binary.write_bytes(b"changed artifact")
    receipt = tool.smoke(harness.binary)
    assert (
        receipt["passed"] is False
        and "changed during qualification" in receipt["error"]
    )
    assert len(receipt["launches"]) == 2
    assert all(row["passed"] for row in receipt["launches"])
    assert receipt["binary_unchanged"] is False
    assert (
        receipt["binary_sha256_after"]
        == hashlib.sha256(b"changed artifact").hexdigest()
    )
    assert receipt["binary_sha256_after"] != receipt["binary_sha256"]
    assert harness.observers[0].closed is True


@pytest.mark.parametrize(
    "failure", ["native-stop", "diagnostic-stop", "observer-read", "seed-cli-stop"]
)
def test_cleanup_error_cannot_hide_available_stderr(harness, monkeypatch, failure):
    if failure == "diagnostic-stop":
        harness.diagnostic_body["stderr"] = OLD_CALLBACK_STDERR
    elif failure == "seed-cli-stop":
        harness.mode["command_stderr"] = OLD_CALLBACK_STDERR
    else:
        harness.mode["stderr"] = OLD_CALLBACK_STDERR
    if failure == "observer-read":
        original = tool.X11Observer.windows

        def broken_windows(observer, pid, *, mapped_only=False):
            if not mapped_only:
                raise OSError("Fictional final display read failed")
            return original(observer, pid, mapped_only=mapped_only)

        monkeypatch.setattr(tool.X11Observer, "windows", broken_windows)
    else:
        original = tool.stop_process

        def broken_stop(process, row):
            original(process, row)  # Owned process is actually cleaned first.
            if (
                (failure == "diagnostic-stop" and process in harness.diagnostics)
                or (failure == "native-stop" and process in harness.processes)
                or (failure == "seed-cli-stop" and process in harness.commands)
            ):
                raise OSError("Fictional cleanup observation failed")

        monkeypatch.setattr(tool, "stop_process", broken_stop)
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and receipt["error_type"] == "OSError"
    if failure == "diagnostic-stop":
        row = receipt["diagnostic_process"]
    elif failure == "seed-cli-stop":
        row = receipt["offline_commands"][0]
    else:
        row = receipt["launches"][0]
    assert row["passed"] is False
    assert row.get("stderr_bytes") == len(OLD_CALLBACK_STDERR)
    assert row["stderr_sha256"] == hashlib.sha256(OLD_CALLBACK_STDERR).hexdigest()
    assert base64.b64decode(row["stderr_base64"]) == OLD_CALLBACK_STDERR
    assert row["exit_code"] == 0 and row["owned_group_remaining"] is False
    assert harness.observers[0].closed is True
    if failure in {"native-stop", "observer-read"}:
        assert len(receipt["launches"]) == 1 and row["saved_workspace_exact"] is True
        assert row["saved_casebook_exact"] is True


@pytest.mark.parametrize(
    "change",
    [
        "bool-revision",
        "float-revision",
        "bool-counts",
        "float-counts",
        "float-connection",
        "nonfinite-counts",
    ],
)
def test_cli_json_types_are_not_coerced_into_exact_saved_work(harness, change):
    def mutate(envelope):
        result = envelope["result"]
        if envelope["operation"] == "casebooks.get":
            if change == "bool-revision":
                result["revision"] = True
            elif change == "float-revision":
                result["revision"] = 1.0
        if envelope["operation"] == "runtime.status":
            if change == "bool-counts":
                result["counts"] = {
                    "casebooks": True,
                    "campaigns": False,
                    "reports": False,
                    "watches": False,
                }
            elif change == "float-counts":
                result["counts"]["casebooks"] = 1.0
            elif change == "float-connection":
                result["connection"]["max_tokens"] = 256.0
            elif change == "nonfinite-counts":
                result["counts"]["casebooks"] = float("nan")

    harness.mode["command_change"] = mutate
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False
    assert receipt["launches"] == [] and harness.processes == []
    assert receipt["fictional_workspace"]["saved_workspace_exact"] is True
    if change.endswith("revision"):
        assert receipt["fictional_workspace"]["saved_casebook_exact"] is False
    elif change == "float-connection":
        assert receipt["fictional_workspace"]["explicit_model_selection_exact"] is False
    elif change != "nonfinite-counts":
        assert receipt["fictional_workspace"]["offline_status_exact"] is False
    else:
        assert receipt["error_type"] == "ValueError"  # Nonfinite JSON is rejected.


@pytest.mark.parametrize("name", ["application_id", "encoding", "page_size"])
def test_same_live_file_persistent_metadata_must_survive_launch(harness, name):
    def mutate(workspace):
        original = workspace / "workspace.sqlite3"
        if name == "encoding":
            # Reconstruct identical logical bytes in a differently encoded file.
            # No current source text or preference is edited by this probe.
            with sqlite3.connect(original) as db:
                dump = "\n".join(db.iterdump())
                version = db.execute("PRAGMA user_version").fetchone()[0]
            replacement = workspace / "fictional-reencoded.sqlite3"
            with sqlite3.connect(replacement) as db:
                db.execute("PRAGMA encoding='UTF-16le'")
                db.executescript(dump)
                db.execute("PRAGMA user_version=" + str(version))
            replacement.replace(original)
        else:
            with sqlite3.connect(original) as db:
                if name == "application_id":
                    db.execute("PRAGMA application_id=7319")
                elif name == "page_size":
                    db.execute("PRAGMA page_size=8192")
                    db.execute("VACUUM")

    harness.mode["mutate"] = mutate
    receipt = tool.smoke(harness.binary)
    assert receipt["passed"] is False and "changed during launch" in receipt["error"]
    row = receipt["launches"][0]
    previous = receipt["fictional_workspace"]["original"]
    after = row["workspace_snapshot"]
    assert row["saved_workspace_exact"] is False
    assert previous["sqlite_" + name] != after["sqlite_" + name]
    assert previous["sqlite_logical_sha256"] == after["sqlite_logical_sha256"]
    assert previous["preferences_sha256"] == after["preferences_sha256"]
    assert len(harness.processes) == 1 and len(harness.commands) == 3
