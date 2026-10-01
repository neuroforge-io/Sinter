"""Installed-native producer boundaries; no installer or executable is run."""

import base64
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import installed_native_menu as tool
from tools.package_native import linux_desktop_entries


def archive(rows):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as bundle:
        for name, raw, kind in rows:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.size = len(raw) if kind == tarfile.REGTYPE else 0
            bundle.addfile(item, io.BytesIO(raw))
    return out.getvalue()


def package_rows():
    return [
        (
            "./opt/neuroforge/sinter/Sinter",
            b"fictional never executed binary",
            tarfile.REGTYPE,
        )
    ] + [
        ("./usr/share/applications/" + n, t.encode(), tarfile.REGTYPE)
        for n, t in linux_desktop_entries(True).items()
    ]


def test_full_unique_regular_installer_members_are_read_without_extraction(tmp_path):
    actual = tool.package_members(archive(package_rows()))
    assert actual["opt/neuroforge/sinter/Sinter"] == b"fictional never executed binary"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "attack", ["missing", "duplicate", "symlink", "oversize", "alias"]
)
def test_installer_member_conflicts_refuse(attack, monkeypatch):
    rows = package_rows()
    if attack == "missing":
        rows.pop()
    elif attack == "duplicate":
        rows.append(rows[-1])
    elif attack == "symlink":
        rows[-1] = (*rows[-1][:2], tarfile.SYMTYPE)
    elif attack == "oversize":
        monkeypatch.setattr(tool, "MAX_MEMBER", 2)
    else:
        rows[-1] = ("././" + rows[-1][0][2:], *rows[-1][1:])
    with pytest.raises(ValueError):
        tool.package_members(archive(rows))


@pytest.mark.parametrize("kind", ["symlink", "fifo", "large"])
def test_regular_read_refuses_without_following_or_blocking(tmp_path, kind):
    import os

    target = tmp_path / "record"
    if kind == "symlink":
        target.symlink_to(tmp_path / "missing")
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip(
                "Requires an actual POSIX FIFO, never a regular-file replacement."
            )
        os.mkfifo(target)
    else:
        target.write_bytes(b"too large")
    with pytest.raises(ValueError):
        tool.regular_bytes(target, 2)


def preflight(tmp_path, monkeypatch):
    installer = tmp_path / "never-installed.deb"
    installer.write_bytes(b"fictional container")
    binary = b"fictional never executed binary"
    body = {
        "passed": True,
        "version": "0.5.4rc4.dev0",
        "source_commit": "a" * 40,
        "installer_sha256": tool.digest(installer.read_bytes()),
        "frozen_cli_test": {"passed": True, "binary_sha256": tool.digest(binary)},
    }
    receipt = tmp_path / "package.json"
    receipt.write_text(json.dumps(body), encoding="utf-8")
    args = SimpleNamespace(installer=installer, package_receipt=receipt)
    replies = {
        "Package": b"sinter\n",
        "Architecture": b"amd64\n",
        "Version": b"0.5.4~rc4~~dev0\n",
    }

    def command(argv, *_args, **_kwargs):
        return (
            (0, archive(package_rows()))
            if argv[1] == "--fsys-tarfile"
            else (0, replies[argv[-1]])
        )

    monkeypatch.setattr(tool, "command", command)
    source = {"commit": "a" * 40, "version": "0.5.4rc4.dev0"}
    return args, source, body, replies


def test_preflight_binds_full_source_entries_and_payload_to_same_run_receipt(
    tmp_path, monkeypatch
):
    args, source, _, _ = preflight(tmp_path, monkeypatch)
    proof = tool.package_preflight(args, source, [])
    for name, raw in linux_desktop_entries(True).items():
        assert base64.b64decode(proof["entries"][name]["base64"]) == raw.encode()
    assert proof["binary_sha256"] == tool.digest(b"fictional never executed binary")


@pytest.mark.parametrize(
    "field,value",
    [
        ("passed", 1),
        ("version", "old"),
        ("source_commit", "b" * 40),
        ("installer_sha256", "0" * 64),
        ("frozen_cli_test", {"passed": True, "binary_sha256": "0" * 64}),
    ],
)
def test_preflight_refuses_unqualified_package_identity(
    tmp_path, monkeypatch, field, value
):
    args, source, body, _ = preflight(tmp_path, monkeypatch)
    body[field] = value
    args.package_receipt.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError):
        tool.package_preflight(args, source, [])


def test_source_binding_compares_every_archive_byte_and_requires_new_producer(
    tmp_path, monkeypatch
):
    rows = [
        (
            name,
            b"exact"
            if not name.endswith("__init__.py")
            else b'__version__ = "0.5.4rc4.dev0"\n',
            tarfile.REGTYPE,
        )
        for name in (
            *tool.OWN_PATHS,
            "src/sinter/__init__.py",
            "src/sinter/unchanged.py",
        )
    ]
    for name, raw, _ in rows:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    monkeypatch.setattr(tool, "command", lambda *_a, **_k: (0, archive(rows)))
    assert tool.source_identity(tmp_path, "a" * 40, [])["files"][
        "src/sinter/unchanged.py"
    ]["sha256"] == tool.digest(b"exact")
    (tmp_path / "src/sinter/unchanged.py").write_bytes(
        b"different outside the new modules"
    )
    with pytest.raises(ValueError, match="differs"):
        tool.source_identity(tmp_path, "a" * 40, [])
    rows = [r for r in rows if r[0] != "tools/installed_native_tk.py"]
    (tmp_path / "src/sinter/unchanged.py").write_bytes(b"exact")
    with pytest.raises(ValueError, match="does not contain"):
        tool.source_identity(tmp_path, "a" * 40, [])


@pytest.mark.parametrize("value", [True, None, "a" * 39, "A" * 40, "a" * 40 + "\n"])
def test_source_selector_refuses_before_command(value, monkeypatch):
    monkeypatch.setattr(
        tool,
        "command",
        lambda *_a, **_k: pytest.fail("No command before source admission"),
    )
    with pytest.raises(ValueError):
        tool.source_identity(Path("unused"), value, [])


@pytest.mark.parametrize(
    "residual", ["sinter.desktop", "sinter-native.desktop", "binary"]
)
def test_removal_checks_dangling_symlinks_not_exists(tmp_path, monkeypatch, residual):
    monkeypatch.setattr(tool, "ENTRY_DIR", tmp_path)
    monkeypatch.setattr(tool, "BINARY", tmp_path / "binary")
    monkeypatch.setattr(tool, "package_state", lambda *_: "absent")
    (tmp_path / residual).symlink_to(tmp_path / "absent")
    assert not (tmp_path / residual).exists()
    assert tool.removal_state([])["passed"] is False
    assert tool.removal_state([])["remaining_paths"] == [str(tmp_path / residual)]


class Process:
    pid = 12345

    def wait(self, timeout):
        return 0


def test_capture_retains_hidden_stderr_tail_and_redacts_auth_before_failure(
    monkeypatch,
):
    payload = b" " * 65536 + b"Exact failure \xff after bounded prefix\n"

    def popen(argv, **kwargs):
        assert argv[-1] == "never output this cookie"
        kwargs["stderr"].write(payload)
        return Process()

    monkeypatch.setattr(tool.subprocess, "Popen", popen)

    def stop(_p, row):
        row.update(exit_code=0, owned_group_remaining=False)

    monkeypatch.setattr(tool.native, "stop_process", stop)
    rows = []
    tool.command(["xauth", "never output this cookie"], rows, redact=(-1,))
    record = rows[0]["stderr"]
    assert (
        record["bytes"] == len(payload)
        and record["sha256"] == hashlib.sha256(payload).hexdigest()
    )
    assert (
        record["truncated"] is True and len(base64.b64decode(record["base64"])) == 65536
    )
    assert "never output this cookie" not in json.dumps(rows)


@pytest.mark.parametrize("body_error", [False, True])
def test_cleanup_error_retains_both_streams_and_preserves_body_priority(
    monkeypatch, body_error
):
    original = subprocess.TimeoutExpired("fictional", 1)

    class Broken(Process):
        def wait(self, timeout):
            if body_error:
                raise original
            return 0

    def popen(_argv, **kwargs):
        kwargs["stderr"].write(b"Exact original native error\xff")
        kwargs["stdout"].write(b"Exact observation")
        return Broken()

    monkeypatch.setattr(tool.subprocess, "Popen", popen)
    monkeypatch.setattr(
        tool.native,
        "stop_process",
        lambda *_: (_ for _ in ()).throw(OSError("cleanup evidence-only failure")),
    )
    rows = []
    with pytest.raises(subprocess.TimeoutExpired if body_error else OSError) as caught:
        tool.command(["fictional"], rows)
    if body_error:
        assert caught.value is original
    assert (
        rows[0]["stderr"]["base64"]
        == base64.b64encode(b"Exact original native error\xff").decode()
    )
    assert rows[0]["stdout"]["bytes"] == len(b"Exact observation")
    assert rows[0]["passed"] is False


def launch_evidence():
    sha = "a" * 64
    prefix = (str(tool.BINARY), "app", "--mode", "native")
    proof = {
        "schema": "sinter-frozen-native-window-test/v1",
        "passed": True,
        "binary_sha256": sha,
        "binary_sha256_after": sha,
        "binary_unchanged": True,
        "launches": [],
    }
    observations = []
    for pid in (111, 222):
        proof["launches"].append(
            {
                "pid": pid,
                "passed": True,
                "sigterm_sent": True,
                "forced_cleanup": False,
                "owned_group_remaining": False,
                "owned_windows_remaining": [],
                "stderr_bytes": 0,
                "exit_code": 0,
                "mapped_windows": [
                    {
                        "pid": pid,
                        "window_id": "0x123",
                        "mapped": True,
                        "title": tool.native.TITLE,
                        "width": 1000,
                        "height": 800,
                    }
                ],
            }
        )
        observations.append(
            {
                "argv": [*prefix, "--directory", "/owned/fictional/workspace"],
                "started": True,
                "pid": pid,
            }
        )
    return proof, observations, prefix, {"binary_sha256": sha}


def test_fresh_adapter_rows_bind_native_command_actual_pids_and_workspace():
    tool.admit_invocations(*launch_evidence())


@pytest.mark.parametrize(
    "attack",
    [
        "old",
        "missing",
        "samepid",
        "wrongpid",
        "boolpid",
        "wrongargv",
        "extrafield",
        "startfalse",
        "differentdir",
        "stderr",
        "exitbool",
        "forced",
        "windows_missing",
    ],
)
def test_old_or_tampered_launch_evidence_cannot_be_menu_proof(attack):
    proof, observations, prefix, package = launch_evidence()
    if attack == "old":
        observations = []
    elif attack == "missing":
        observations.pop()
    elif attack == "samepid":
        observations[1]["pid"] = 111
        proof["launches"][1]["pid"] = 111
    elif attack == "wrongpid":
        observations[0]["pid"] = 333
    elif attack == "boolpid":
        observations[0]["pid"] = True
    elif attack == "wrongargv":
        observations[0]["argv"][3] = "browser"
    elif attack == "extrafield":
        observations[0]["extra"] = True
    elif attack == "startfalse":
        observations[0]["started"] = False
    elif attack == "differentdir":
        observations[0]["argv"][-1] = "/other/fictional"
    elif attack == "stderr":
        proof["launches"][0]["stderr_bytes"] = 1
    elif attack == "exitbool":
        proof["launches"][0]["exit_code"] = False
    elif attack == "forced":
        proof["launches"][0]["forced_cleanup"] = True
    else:
        proof["launches"][0]["mapped_windows"] = []
    with pytest.raises(ValueError):
        tool.admit_invocations(proof, observations, prefix, package)


def test_preexisting_package_is_never_removed_or_launched(tmp_path, monkeypatch):
    monkeypatch.setattr(tool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tool.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    original_isfile = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda p: True if p == Path("/.dockerenv") else original_isfile(p),
    )
    original_iterdir = Path.iterdir
    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda p: (
            iter([Path("lo")]) if p == Path("/sys/class/net") else original_iterdir(p)
        ),
    )
    monkeypatch.setattr(tool, "package_state", lambda _: "install ok installed")
    monkeypatch.setattr(
        tool,
        "command",
        lambda *_a, **_k: pytest.fail(
            "Never remove or run an unowned installed package"
        ),
    )
    result = tool.run(SimpleNamespace(output=tmp_path / "out"))
    assert result["passed"] is False and result["removal"] == {
        "passed": False,
        "attempted": False,
    }
    assert "existing package" in result["error"]


@pytest.mark.parametrize(
    "diagnostic",
    [
        b"dpkg-query: no packages found matching sinter\n",
        b"permission denied\n",
        b"",
        b"dpkg-query: no packages found matching sinter\nextra error",
    ],
)
def test_absence_requires_exact_query_result_not_arbitrary_exit_one(
    monkeypatch, diagnostic
):
    def query(_argv, rows, **kwargs):
        assert kwargs["env"] == {"PATH": tool.os.defpath, "LC_ALL": "C.UTF-8"}
        rows.append(
            {
                "stderr": {
                    "bytes": len(diagnostic),
                    "sha256": tool.digest(diagnostic),
                    "base64": base64.b64encode(diagnostic).decode(),
                    "truncated": False,
                }
            }
        )
        return 1, b""

    monkeypatch.setattr(tool, "command", query)
    if diagnostic == b"dpkg-query: no packages found matching sinter\n":
        assert tool.package_state([]) == "absent"
    else:
        with pytest.raises(ValueError, match="absence"):
            tool.package_state([])


def owner_environment(monkeypatch):
    monkeypatch.setattr(tool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tool.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    original_isfile = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda p: True if p == Path("/.dockerenv") else original_isfile(p),
    )
    original_iterdir = Path.iterdir
    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda p: (
            iter([Path("lo")]) if p == Path("/sys/class/net") else original_iterdir(p)
        ),
    )
    monkeypatch.setattr(tool.os.path, "lexists", lambda _: False)


@pytest.mark.parametrize("install_exit,remove_exit", [(0, 0), (2, 0), (0, 7)])
def test_own_attempt_is_removed_after_body_failure_but_never_certified(
    tmp_path, monkeypatch, install_exit, remove_exit
):
    owner_environment(monkeypatch)
    installer = tmp_path / "never-installed.deb"
    installer.write_bytes(b"fictional")
    source = {"commit": "a" * 40, "version": "0.5.4rc4.dev0"}
    package = {"installer_sha256": tool.digest(b"fictional")}
    monkeypatch.setattr(tool, "source_identity", lambda *_: source)
    monkeypatch.setattr(tool, "package_preflight", lambda *_: package)
    calls = []

    def command(argv, *_a, **_k):
        calls.append(list(map(str, argv)))
        return (install_exit if argv[1] == "-i" else remove_exit), b""

    monkeypatch.setattr(tool, "command", command)
    states = iter(
        ["absent", "install ok installed", "absent"]
        if install_exit == 0
        else ["absent", "absent"]
    )
    monkeypatch.setattr(tool, "package_state", lambda _: next(states))
    monkeypatch.setattr(
        tool,
        "installed_identity",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("Exact body refusal")),
    )
    result = tool.run(
        SimpleNamespace(
            output=tmp_path / "out",
            installer=installer,
            repository=tmp_path,
            source_commit="a" * 40,
        )
    )
    assert calls == [["dpkg", "-i", str(installer)], ["dpkg", "-r", "sinter"]]
    assert result["passed"] is False
    assert result["removal"]["passed"] is (remove_exit == 0)
    assert result["error"] == (
        "Exact body refusal"
        if install_exit == 0
        else "Owned candidate installation failed."
    )
    assert (
        json.loads((tmp_path / "out/installed-native-entry-test.json").read_text())[
            "passed"
        ]
        is False
    )


def test_preflight_refusal_never_attempts_install_or_removal(tmp_path, monkeypatch):
    owner_environment(monkeypatch)
    monkeypatch.setattr(tool, "package_state", lambda _: "absent")
    monkeypatch.setattr(
        tool,
        "source_identity",
        lambda *_: (_ for _ in ()).throw(ValueError("Unqualified source")),
    )
    monkeypatch.setattr(
        tool,
        "command",
        lambda *_a, **_k: pytest.fail("No install/remove after preflight refusal"),
    )
    result = tool.run(
        SimpleNamespace(
            output=tmp_path / "out", repository=tmp_path, source_commit="a" * 40
        )
    )
    assert result["removal"] == {"passed": False, "attempted": False}
    assert result["error"] == "Unqualified source"


def test_wrong_native_prefix_refuses_before_ui_process(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tool.subprocess,
        "Popen",
        lambda *_a, **_k: pytest.fail("No child for wrong entry command"),
    )
    with pytest.raises(RuntimeError, match="exact tested"):
        tool.ui_launch(
            ("/different/binary", "app", "--mode", "native"),
            tmp_path,
            tmp_path,
            {},
            None,
            "create",
            {"tk_launches": []},
        )


def installed_fixture(tmp_path, monkeypatch):
    binary = tmp_path / "binary"
    binary.write_bytes(b"never executed")
    binary.chmod(0o700)
    entries = tmp_path / "entries"
    entries.mkdir()
    records = {}
    for name, text in linux_desktop_entries(True).items():
        raw = text.encode()
        (entries / name).write_bytes(raw)
        records[name] = {
            "bytes": len(raw),
            "sha256": tool.digest(raw),
            "base64": base64.b64encode(raw).decode(),
        }
    monkeypatch.setattr(tool, "BINARY", binary)
    monkeypatch.setattr(tool, "ENTRY_DIR", entries)
    return (
        {"binary_sha256": tool.digest(b"never executed"), "entries": records},
        entries,
        binary,
    )


def test_full_installed_bytes_are_observed_separately_from_package_expected(
    tmp_path, monkeypatch
):
    package, _, _ = installed_fixture(tmp_path, monkeypatch)
    observations = {}
    command = tool.installed_identity(package, observations=observations)
    assert command == ("/opt/neuroforge/sinter/Sinter", "app", "--mode", "native")
    assert observations == package["entries"] and observations is not package["entries"]


@pytest.mark.parametrize("attack", ["comment", "symlink", "binary"])
def test_semantically_same_entry_or_wrong_payload_does_not_pass_full_byte_admission(
    tmp_path, monkeypatch, attack
):
    package, entries, binary = installed_fixture(tmp_path, monkeypatch)
    if attack == "comment":
        path = entries / "sinter-native.desktop"
        path.write_bytes(path.read_bytes() + b"# changed outside Name/Exec\n")
        assert tool.menu_command(path, native=True)[-1] == "native"
    elif attack == "symlink":
        path = entries / "sinter-native.desktop"
        other = tmp_path / "copy"
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(other)
    else:
        binary.write_bytes(b"different never executed payload")
    with pytest.raises(ValueError):
        tool.installed_identity(package)


def test_auth_timeout_does_not_disclose_ephemeral_cookie(monkeypatch):
    original = subprocess.TimeoutExpired(["xauth", "ephemeral cookie"], 1)

    class Broken(Process):
        def wait(self, timeout):
            raise original

    monkeypatch.setattr(tool.subprocess, "Popen", lambda *_a, **_k: Broken())
    monkeypatch.setattr(
        tool.native,
        "stop_process",
        lambda _p, r: r.update(exit_code=1, owned_group_remaining=False),
    )
    rows = []
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        tool.command(["xauth", "ephemeral cookie"], rows, redact=(-1,))
    assert caught.value is original
    assert "ephemeral cookie" not in str(
        caught.value
    ) and "ephemeral cookie" not in json.dumps(rows)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pid", True),
        ("pid", 999),
        ("title", "different"),
        ("mapped", 1),
        ("width", True),
        ("window_id", "0x1; script"),
    ],
)
def test_mapped_window_observation_must_match_actual_native_pid_and_title(field, value):
    proof, observations, prefix, package = launch_evidence()
    proof["launches"][0]["mapped_windows"][0][field] = value
    with pytest.raises(ValueError, match="Mapped native"):
        tool.admit_invocations(proof, observations, prefix, package)


def ui_seam(tmp_path, monkeypatch, payload=b"", action_change=None, driver_error=None):
    phase = "create"
    prefix = (str(tool.BINARY), "app", "--mode", "native")
    proc = SimpleNamespace(pid=12345, returncode=None)
    proc.poll = lambda: proc.returncode

    def wait(timeout):
        proc.returncode = 0
        return 0

    proc.wait = wait

    def popen(argv, **kwargs):
        assert argv == [*prefix, "--directory", str(tmp_path / "fictional")]
        kwargs["stderr"].write(payload)
        return proc

    monkeypatch.setattr(tool.subprocess, "Popen", popen)
    stopped = []

    def stop(_p, row):
        stopped.append(_p.pid)
        row.update(
            exit_code=0,
            sigterm_sent=False,
            forced_cleanup=False,
            owned_group_remaining=False,
        )

    monkeypatch.setattr(tool.native, "stop_process", stop)
    action = {
        "schema": "sinter-installed-native-tk-action/v1",
        "phase": phase,
        "project_id": "a" * 32,
        "window_id": "0x123",
        "fields_exact": True,
        "save_button_invoked": True,
        "wm_close_invoked": True,
    }
    if action_change:
        action.update(action_change)

    def bridge(argv, rows, **kwargs):
        assert kwargs["timeout"] == 15 and "--request" in argv
        rows.append({"stderr": {"bytes": 0}, "pid": 67890})
        if driver_error:
            raise driver_error
        return 0, json.dumps(action).encode()

    monkeypatch.setattr(tool, "command", bridge)
    observer = SimpleNamespace(
        windows=lambda pid, **kwargs: (
            [
                {
                    "pid": pid,
                    "window_id": "0x123",
                    "mapped": True,
                    "title": tool.native.TITLE,
                    "width": 1000,
                    "height": 800,
                }
            ]
            if kwargs.get("mapped_only")
            else []
        )
    )
    receipt = {"tk_launches": [], "commands": []}
    return prefix, observer, receipt, stopped


def test_normal_tk_save_and_wm_quit_seam_keeps_exact_entry_argv(tmp_path, monkeypatch):
    prefix, observer, receipt, stopped = ui_seam(tmp_path, monkeypatch)
    assert (
        tool.ui_launch(
            prefix, tmp_path, tmp_path / "fictional", {}, observer, "create", receipt
        )
        == "a" * 32
    )
    assert receipt["tk_launches"][0]["passed"] is True and stopped == [12345]
    assert receipt["tk_launches"][0]["sigterm_sent"] is False


@pytest.mark.parametrize(
    "payload", [b"Tk callback traceback despite exit0\n", b" ", b"\xff"]
)
def test_normal_exit_with_any_tk_diagnostic_is_refused_with_exact_bytes(
    tmp_path, monkeypatch, payload
):
    prefix, observer, receipt, stopped = ui_seam(tmp_path, monkeypatch, payload=payload)
    with pytest.raises(RuntimeError, match="WM quit"):
        tool.ui_launch(
            prefix, tmp_path, tmp_path / "fictional", {}, observer, "create", receipt
        )
    row = receipt["tk_launches"][0]
    assert row["passed"] is False and row["stderr_bytes"] == len(payload)
    assert base64.b64decode(row["stderr_base64"]) == payload and stopped == [12345]


@pytest.mark.parametrize(
    "change",
    [
        {"fields_exact": 1},
        {"project_id": True},
        {"window_id": "0x999"},
        {"phase": "reopen"},
        {"unexpected": True},
    ],
)
def test_driver_missing_or_untyped_identity_refuses_before_native_success(
    tmp_path, monkeypatch, change
):
    prefix, observer, receipt, stopped = ui_seam(
        tmp_path, monkeypatch, action_change=change
    )
    with pytest.raises(ValueError, match="identity"):
        tool.ui_launch(
            prefix, tmp_path, tmp_path / "fictional", {}, observer, "create", receipt
        )
    assert stopped == [12345] and receipt["tk_launches"][0]["passed"] is False


def test_ui_timeout_is_not_replayed_and_keeps_available_native_stderr(
    tmp_path, monkeypatch
):
    error = subprocess.TimeoutExpired("fixed Tk driver", 15)
    payload = b"Available native callback evidence\xff"
    prefix, observer, receipt, stopped = ui_seam(
        tmp_path, monkeypatch, payload=payload, driver_error=error
    )
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        tool.ui_launch(
            prefix, tmp_path, tmp_path / "fictional", {}, observer, "create", receipt
        )
    assert caught.value is error and stopped == [12345]
    assert len(receipt["tk_launches"]) == len(receipt["commands"]) == 1
    assert base64.b64decode(receipt["tk_launches"][0]["stderr_base64"]) == payload
