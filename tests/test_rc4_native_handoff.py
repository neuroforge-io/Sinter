"""Portable parser/control regressions; synthetic evidence is not installation.

The local source runtime makes real fictional SQLite originals for these tests.
No X server, browser, Docker, installer, account or provider is invoked here.
"""

from __future__ import annotations

import copy
import json
import os
import socket
import stat
import subprocess
import sys
import threading
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest

from sinter.native_browser import SESSION_DETAILS, SESSION_NOTICE
from sinter.runtime import Runtime
from sinter.workbench import WORKFLOWS
from tests.test_installed_native_entry_contract import (
    legacy,
    outer_fixture,
    output,
    process,
    stream,
)
from tools import installed_native_container as owner
from tools import installed_native_entry_contract as old
from tools import installed_native_menu as menu
from tools import native_window_smoke as native
from tools import rc4_native_handoff as producer
from tools import rc4_native_handoff_contract as contract


def child(argv, raw=b"", stderr=b"", pid=700, code=0):
    return {
        **process(pid, code),
        "passed": code == 0,
        "argv": list(map(str, argv)),
        "streams_complete": True,
        "stdout": stream(raw),
        "stderr": stream(stderr),
    }


def interrupted_fixture(port):
    request = (
        f"POST /api/casebooks/save HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        f"Origin: http://127.0.0.1:{port}\r\nX-Sinter-Token: "
        + "a" * 43
        + '\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{"document":'
    ).encode()
    body = output({"error": "The request was interrupted before all data arrived."})
    response = (
        b"HTTP/1.0 400 Bad Request\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    return {
        "attempts": 1,
        "request": producer.original(request),
        "response": producer.original(response),
    }


def assert_source_listener_closed(server, thread):
    """QA ownership check; a timed-out connection never proves port closure."""
    assert not thread.is_alive()
    assert server.socket.fileno() == -1
    with socket.socket(server.address_family, socket.SOCK_STREAM) as probe:
        if sys.platform == "win32":
            # Winsock's exclusive second bind rejects even a live REUSEADDR
            # owner: https://learn.microsoft.com/en-us/windows/win32/winsock/so-exclusiveaddruse
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # POSIX allows this completed source journey's TIME_WAIT sockets,
            # while a still-listening owner at the same address remains a conflict.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(server.server_address)
        probe.listen(1)
        assert probe.getsockname() == server.server_address


@pytest.fixture
def synthetic(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "preferences.json").write_bytes(output(native.FICTIONAL_PREFERENCES))
    path = "/out/handoff/home/workspace"
    rows = []
    with Runtime(data) as runtime:
        operations = [
            ("save-legacy", "casebooks.save", {"document": contract.fixture()}),
            ("save-scoped", "casebooks.save", {"document": contract.scoped_fixture()}),
        ]
        results = []
        for role, name, body in operations:
            results.append(
                runtime.call(name, body, casebook_schema="sinter-casebook/v2")
            )
            rows.append((role, name, body, results[-1]))
        built = runtime.call(
            "casebooks.build",
            {"id": results[0]["id"], "revision": 1},
            casebook_schema="sinter-casebook/v2",
        )
        rows.append(
            (
                "build-legacy",
                "casebooks.build",
                {"id": results[0]["id"], "revision": 1},
                built,
            )
        )
        report = {**built, "markdown": contract.HISTORY + "\n\n" + built["markdown"]}
        history = runtime.call("reports.save", {"report": report})
        rows.append(("save-history", "reports.save", {"report": report}, history))
        status = runtime.call("runtime.status", {})
        rows.append(("status", "runtime.status", {}, status))
    version = "0.5.4rc4.dev0"

    def cli_row(role, name, body, result):
        envelope = {
            "schema": "sinter-operation-result/v1",
            "ok": True,
            "version": version,
            "operation": name,
            "result": result,
        }
        return {
            **child(
                [
                    str(menu.BINARY),
                    "run",
                    name,
                    "--input",
                    path + "/../" + role + ".json",
                    "--directory",
                    path,
                    "--format",
                    "json",
                ],
                output(envelope),
                b"Ready for review\n" if name == "casebooks.build" else b"",
            ),
            "role": role,
            "input": body,
            "input_bytes": producer.original(output(body)),
        }

    seeds = [cli_row(*row) for row in rows]
    snapshot = producer.disk_snapshot(data)
    source = {
        "commit": "a" * 40,
        "version": version,
        "archive_sha256": old.sha(b"archive"),
        "files": {name: {"bytes": 1, "sha256": "a" * 64} for name in contract.FILES},
    }
    package = {
        "entries": {},
        "binary_bytes": 5,
        "binary_sha256": "b" * 64,
        "package_version": "0.5.4~rc4~~dev0",
        "payload_tar_sha256": old.sha(b"payload"),
        "payload_tar_bytes": 7,
        "installer_sha256": "c" * 64,
        "receipt_sha256": "d" * 64,
    }
    window = {
        "pid": 500,
        "mapped": True,
        "title": native.TITLE,
        "window_id": "0x123",
        "width": 1120,
        "height": 820,
    }
    native_row = legacy(
        {
            **process(500),
            "argv": old.NATIVE + ["--directory", path],
            "workspace_home": "/out/handoff/home",
            "mapped_windows": [window],
            "owned_windows_remaining": [],
            "stdout": stream(),
            "stdout_complete": True,
        }
    )
    controls = [
        [
            "Fictional example",
            "Open project",
            "Keep unsaved work?:Yes",
            "Sinter — action could not finish:OK",
        ],
        ["Open full workbench", "Open full workbench:No"],
        ["Close Sinter and its workbench?:No"],
        [
            "WM_DELETE_WINDOW",
            "Close Sinter and its workbench?:Yes",
            "Unsaved source edits:No",
        ],
        ["Keep window open"],
        [
            "WM_DELETE_WINDOW",
            "Close Sinter and its workbench?:Yes",
            "Unsaved source edits:No",
        ],
        [],
        ["Close Sinter and its workbench?:Yes", "Unsaved source edits:No"],
    ]
    actions = []
    for phase, actual_controls in zip(contract.PHASES, controls):
        request = {"phase": phase, "pid": 500, "window_ids": ["0x123"]}
        result = {
            "schema": "sinter-native-handoff-action/v1",
            "phase": phase,
            "pid": 500,
            "window_id": "0x123",
            "fields": list(contract.FIELDS),
            "controls": actual_controls,
            "status": "no choices were cleared"
            if phase == "refuse-scoped"
            else contract.TIMEOUT_TEXT
            if phase == "inspect-timeout"
            else "",
        }
        actions.append(
            {
                "phase": phase,
                "request": request,
                "request_bytes": producer.original(output(request)),
                "command": child(
                    [
                        contract.PYTHON,
                        "-B",
                        "/source/" + contract.FILES[0],
                        "_driver",
                        "--request",
                        "/out/handoff/home/" + phase + "-request.json",
                    ],
                    output(result),
                    pid=600 + len(actions),
                ),
                "result": result,
            }
        )
    paths = [
        str(menu.BINARY),
        str(menu.ENTRY_DIR / "sinter.desktop"),
        str(menu.ENTRY_DIR / "sinter-native.desktop"),
    ]
    package_commands = [
        child(old.STATUS_QUERY, stderr=old.ABSENT, code=1),
        child(
            [
                contract.PYTHON,
                "-B",
                "-c",
                menu.ARCHIVE_READ,
                "/repository/" + menu.ARCHIVE_NAME,
            ],
            b"archive",
        ),
        *[
            child(["dpkg-deb", "-f", "/candidate/candidate.deb", field], body)
            for field, body in (
                ("Package", b"sinter\n"),
                ("Architecture", b"amd64\n"),
                ("Version", (package["package_version"] + "\n").encode()),
            )
        ],
        child(["dpkg-deb", "--fsys-tarfile", "/candidate/candidate.deb"], b"payload"),
        child(["dpkg", "-i", "/candidate/candidate.deb"]),
        child(old.STATUS_QUERY, b"install ok installed"),
        child(
            old.VERSION_QUERY,
            ("install ok installed\n" + package["package_version"] + "\n").encode(),
        ),
        child(["dpkg", "-r", "sinter"], stderr=old.SHARED_OPT_REMOVAL_WARNING),
        child(old.STATUS_QUERY, stderr=old.ABSENT, code=1),
        child(
            [contract.PYTHON, "-B", "-c", menu.FILESYSTEM_PROBE, *paths],
            output([{"path": p, "lexists": False} for p in paths]),
        ),
    ]
    display = legacy(
        {
            **process(900),
            "sigterm_sent": True,
            "passed": True,
            "stdout_observed": {"complete": True, "exit_code": 0, "record": stream()},
            "remaining_display_paths": [],
            "authority_remaining": False,
        }
    )
    inner = {
        "schema": contract.SCHEMA,
        "passed": True,
        "qualification": "dev",
        "source": source,
        "package": package,
        "tools": source["files"],
        "container": {
            "effective_uid": 0,
            "interfaces": ["lo"],
            "inherited_display": False,
            "docker_marker_present": True,
        },
        "source_origin": {
            "schema": "sinter-bound-git-source-archive-observed/v1",
            "archive_name": menu.ARCHIVE_NAME,
            "origin_name": menu.ORIGIN_NAME,
            "origin": producer.original(output(menu.archive_origin(source, 7))),
        },
        "archive_bytes": 7,
        "installer_name": "candidate.deb",
        "installed_package": {
            "status": "install ok installed",
            "version": package["package_version"],
            "command_index": 8,
        },
        "installed_entries": {},
        "installed_entries_after": {},
        "installed_binary": {"bytes": 5, "sha256": "b" * 64, "executable": True},
        "installed_binary_after": {"bytes": 5, "sha256": "b" * 64, "executable": True},
        "owner": native_row,
        "workspace": path,
        "seed": seeds,
        "snapshots": {
            name: copy.deepcopy(snapshot)
            for name in (
                "before_native",
                "after_refusal",
                "after_browser",
                "after_keep",
                "after_timeout",
                "before_final",
                "after_exit",
                "after_read",
            )
        },
        "actions": actions,
        "commands": package_commands,
        "display_evidence": {
            "commands": [
                child(
                    [
                        "xauth",
                        "-f",
                        "/out/handoff/home/xauthority",
                        "add",
                        ":97",
                        ".",
                        "<private owned X authorization>",
                    ]
                )
            ],
            "display": display,
        },
        "selected_scoped_id": results[1]["id"],
        "url": "http://127.0.0.1:32123/#campaigns",
        "port": 32123,
        "launch": {
            "url": "http://127.0.0.1:32123/#campaigns",
            "port": 32123,
            "pid": 501,
            "owner_pid": 500,
        },
        "hold": {
            "fixture": "admitted empty TCP connection",
            "admitted": True,
            "released_explicitly": True,
            "session": {
                "status": 200,
                "body": producer.original(
                    output(
                        {
                            "token": "a" * 43,
                            "version": version,
                            "workflows": WORKFLOWS,
                            "desktop": True,
                            "native_window_owner": True,
                            "session_notice": SESSION_NOTICE,
                            "session_details": SESSION_DETAILS,
                            "native_quit": {"state": "cancelled", "active_requests": 2},
                        }
                    )
                ),
            },
        },
        "timeout_ns": 5_500_000_000,
        "interrupted": interrupted_fixture(32123),
        "reads": [
            cli_row(
                "read-scoped", "casebooks.get", {"id": results[1]["id"]}, results[1]
            )
        ],
        "cleanup": {
            "listener_closed": True,
            "inner_relay_stopped": True,
            "inner_socket_absent": True,
            "display_stopped": True,
            "package_paths_absent": True,
        },
        "removal": package_commands[9],
        "removal_state": {"package_status": "absent", "paths_absent": True},
        "absence": {"paths": paths, "command_index": 11},
    }
    return inner, source, package


def test_complete_synthetic_parser_control_is_not_an_installed_claim(synthetic):
    inner, source, package = synthetic
    result = contract.validate_inner(inner, source, package)
    assert result["owner_pid"] == 500
    assert "release" not in result and "installed" not in result


@pytest.mark.parametrize(
    "field,bad",
    [
        ("pid", True),
        ("pid", 1.0),
        ("phase", "eval"),
        ("phase", "create"),
        ("window_ids", []),
        ("window_ids", ["0x1", "0x2"]),
        ("window_ids", ["../.display"]),
    ],
)
def test_driver_request_rejects_arbitrary_script_old_phase_or_untyped_identity(
    field, bad
):
    request = {"phase": "open-browser", "pid": 1, "window_ids": ["0x1"]}
    request[field] = bad
    with pytest.raises(ValueError):
        contract.action_request(request)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:32/#campaigns",
        "http://localhost:32/#campaigns",
        "http://127.0.0.1:0/#campaigns",
        "http://127.0.0.1:65536/#campaigns",
        "http://127.0.0.1:32/#settings",
        "http://user:secret@127.0.0.1:32/#campaigns",
        "http://127.0.0.1:32/?script=x#campaigns",
        "http://127.0.0.1:32/#campaigns\n",
        None,
    ],
)
def test_native_launch_url_cannot_become_a_general_origin_or_command(url):
    with pytest.raises(ValueError):
        contract.url_port(url)


@pytest.mark.parametrize(
    "attack",
    [
        "source",
        "package",
        "tool",
        "bool_pid",
        "float_pid",
        "changed_owner_pid",
        "wrong_argv",
        "stderr",
        "stdout",
        "early_capture",
        "forced_cleanup",
        "group_alive",
        "window_alive",
        "missing_phase",
        "duplicate_phase",
        "wrong_control",
        "lost_native_fields",
        "wrong_driver_argv",
        "driver_unreaped",
        "request_changed",
        "scope_cleared",
        "history_rewritten",
        "preferences",
        "metadata",
        "initial_metadata",
        "raw_row",
        "short_timeout",
        "bool_timeout",
        "float_timeout",
        "interrupted_replayed",
        "interrupted_200",
        "unknown_removal",
        "wrong_removal_index",
        "paths_remaining",
        "unknown_field",
        "read_downgraded",
        "display_alive",
        "display_stderr",
        "hold_unadmitted",
        "url_owner",
        "cold_snapshot_missing",
        "preflight_wrong_argv",
    ],
)
def test_resealed_semantic_changes_refuse(synthetic, attack):
    original_inner, source, package = synthetic
    inner = copy.deepcopy(original_inner)
    if attack == "source":
        inner["source"]["commit"] = "0" * 40
    elif attack == "package":
        inner["package"]["binary_sha256"] = "0" * 64
    elif attack == "tool":
        inner["tools"][contract.FILES[0]]["bytes"] = True
    elif attack == "bool_pid":
        inner["owner"]["pid"] = True
    elif attack == "float_pid":
        inner["owner"]["pid"] = 500.0
    elif attack == "changed_owner_pid":
        inner["owner"]["pid"] = 1001
    elif attack == "wrong_argv":
        inner["owner"]["argv"][3] = "headless"
    elif attack == "stderr":
        inner["owner"]["stderr_bytes"] = 1
    elif attack == "stdout":
        inner["owner"]["stdout"] = stream(b"warning")
    elif attack == "early_capture":
        inner["owner"]["stdout_complete"] = False
    elif attack == "forced_cleanup":
        inner["owner"]["forced_cleanup"] = True
    elif attack == "group_alive":
        inner["owner"]["owned_group_remaining"] = True
    elif attack == "window_alive":
        inner["owner"]["owned_windows_remaining"] = ["0x123"]
    elif attack == "missing_phase":
        inner["actions"].pop(4)
    elif attack == "duplicate_phase":
        inner["actions"][4] = copy.deepcopy(inner["actions"][3])
    elif attack in {"wrong_control", "lost_native_fields"}:
        row = inner["actions"][0]
        row["result"]["controls" if attack == "wrong_control" else "fields"][0] = (
            "wrong"
        )
        row["command"]["stdout"] = stream(output(row["result"]))
    elif attack == "wrong_driver_argv":
        inner["actions"][0]["command"]["argv"][-1] = "/tmp/arbitrary.tcl"
    elif attack == "driver_unreaped":
        inner["actions"][0]["command"]["streams_complete"] = False
    elif attack == "request_changed":
        inner["actions"][0]["request_bytes"] = producer.original(
            output({"script": "anything"})
        )
    elif attack in {
        "scope_cleared",
        "history_rewritten",
        "preferences",
        "metadata",
        "raw_row",
    }:
        s = inner["snapshots"]["after_refusal"]
        if attack == "preferences":
            s["preferences"]["model"] = "arbitrary-model"
        elif attack == "metadata":
            s["databases"]["workspace.sqlite3"]["metadata"]["user_version"] = True
        elif attack == "raw_row":
            s["databases"]["workspace.sqlite3"]["tables"]["casebooks"]["rows"][0][1] = (
                1.0
            )
        else:
            s["databases"]["workspace.sqlite3"]["tables"][
                "casebooks_scoped_v2" if attack == "scope_cleared" else "reports"
            ]["rows"] = []
    elif attack == "initial_metadata":
        for s in inner["snapshots"].values():
            s["databases"]["workspace.sqlite3"]["metadata"]["user_version"] = True
    elif attack == "short_timeout":
        inner["timeout_ns"] = 4_999_999_999
    elif attack == "bool_timeout":
        inner["timeout_ns"] = True
    elif attack == "float_timeout":
        inner["timeout_ns"] = 5_500_000_000.0
    elif attack == "interrupted_replayed":
        inner["interrupted"]["attempts"] = 2
    elif attack == "interrupted_200":
        inner["interrupted"]["response"] = producer.original(b"HTTP/1.0 200 OK\r\n\r\n")
    elif attack == "unknown_removal":
        inner["commands"][9]["stderr"] = stream(
            old.SHARED_OPT_REMOVAL_WARNING + b"unknown\n"
        )
    elif attack == "wrong_removal_index":
        inner["commands"][6]["stderr"] = stream(old.SHARED_OPT_REMOVAL_WARNING)
    elif attack == "paths_remaining":
        inner["commands"][11]["stdout"] = stream(
            output([{"path": str(menu.BINARY), "lexists": True}])
        )
    elif attack == "unknown_field":
        inner["script"] = "anything"
    elif attack == "read_downgraded":
        read = inner["reads"][0]
        result = json.loads(old.stream_bytes(read["stdout"]))
        result["result"]["document"].pop("question_scopes")
        read["stdout"] = stream(output(result))
    elif attack == "display_alive":
        inner["display_evidence"]["display"]["remaining_display_paths"] = [
            "/tmp/.X97-lock"
        ]
    elif attack == "display_stderr":
        inner["display_evidence"]["display"]["stderr_bytes"] = 1
    elif attack == "hold_unadmitted":
        inner["hold"]["session"]["body"] = producer.original(
            output({"native_window_owner": True, "native_quit": {"active_requests": 1}})
        )
    elif attack == "url_owner":
        inner["launch"]["owner_pid"] = 501
    elif attack == "cold_snapshot_missing":
        inner["snapshots"].pop("after_exit")
    elif attack == "preflight_wrong_argv":
        inner["commands"][6]["argv"][-1] = "/candidate/other.deb"
    with pytest.raises((ValueError, KeyError, TypeError)):
        contract.validate_inner(inner, source, package)


def test_fixed_creation_uses_reviewed_image_and_old_isolation_without_command_escape():
    pins = owner.pins_for(
        PurePosixPath("/owned/test"),
        "a" * 64,
        "b" * 40,
        "candidate.deb",
        "package.json",
    )
    pins["qualification"] = "dev"
    argv = contract.creation_argv(pins, "sinter-native-entry-abcdef012345")
    assert (
        argv[: argv.index(owner.IMAGE_ID)]
        == old.outer_argv(pins, "sinter-native-entry-abcdef012345")[
            : argv.index(owner.IMAGE_ID)
        ]
    )
    assert argv[argv.index(owner.IMAGE_ID) + 1 : 4 + argv.index(owner.IMAGE_ID)] == [
        "python3",
        "-B",
        "/source/tools/rc4_native_handoff.py",
    ]
    assert "--pull=never" in argv and "none" in argv
    assert "_inside" in argv and "--qualification" in argv
    assert "git" not in argv and "chromium" not in argv


def test_internal_producer_refuses_host_paths_before_creating_files(tmp_path):
    args = SimpleNamespace(
        output=tmp_path / "forbidden",
        repository=tmp_path,
        installer=tmp_path / "candidate.deb",
        package_receipt=tmp_path / "receipt.json",
    )
    with pytest.raises(ValueError):
        producer.inside(args)
    assert not args.output.exists()


def test_unknown_driver_phase_has_no_widget_side_effect():
    driver = producer.HandoffDriver.__new__(producer.HandoffDriver)
    with pytest.raises(ValueError):
        driver.run_handoff("eval anything")


def test_tool_help_has_no_resource_side_effect_and_no_command_script_option():
    result = subprocess.run(
        [sys.executable, "-B", str(producer.ROOT / contract.FILES[0]), "run", "--help"],
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0 and result.stderr == b""
    assert b"--qualification" in result.stdout and b"--producer-sha256" in result.stdout
    assert b"--script" not in result.stdout and b"--command" not in result.stdout


def test_canonical_unicode_json_writer_and_fixed_fixture_keep_originals(tmp_path):
    value = {"literal": "é 🐝 {kept}; [literal]", "revision": 1, "uncertain": False}
    path = tmp_path / "original.json"
    producer.write_json(path, value)
    assert old.json_object(path.read_bytes()) == value
    assert (
        contract.scoped_fixture()["documents"]
        == contract.validate(contract.fixture())["documents"]
    )


def browser_fixture(inner):
    scoped = json.loads(old.stream_bytes(inner["seed"][1]["stdout"]))["result"]
    return {
        "schema": "sinter-rc4-native-handoff-browser/v3",
        "temporary_directory": {
            "path": "/tmp/sinter-native-fixturea",
            "identity_before": {
                "st_dev": 1,
                "st_ino": 2,
                "st_mode": stat.S_IFDIR | 0o700,
                "st_uid": getattr(os, "geteuid", lambda: 0)(),
                "st_gid": getattr(os, "getegid", lambda: 0)(),
            },
            "identity_after": {
                "st_dev": 1,
                "st_ino": 2,
                "st_mode": stat.S_IFDIR | 0o700,
                "st_uid": getattr(os, "geteuid", lambda: 0)(),
                "st_gid": getattr(os, "getegid", lambda: 0)(),
            },
            "removed": True,
        },
        "origin": "http://127.0.0.1:32124",
        "relay_port": 32124,
        "debug_port": 32125,
        "title": contract.BROWSER_TITLE,
        "quit_posts": 2,
        "lost_ack_status": 200,
        "lost_ack_body": producer.original(output({"ok": True})),
        "confirmed_ack": {
            "status": 200,
            "body": producer.original(output({"ok": True})),
        },
        "native_notice": "Same local workspace. Keep the Sinter window open.",
        "quit_attempts": [
            "keep-working:no-post",
            "lost-ack:uncertain:no-replay",
            "confirmed-quit",
        ],
        "visible_checks": [
            "full-originals",
            "scoped-capability",
            "keep-working",
            "uncertain-quit-inputs-kept",
            "native-cancelled",
            "drain-cancelled",
            "timeout-refused",
            "confirmed-quit",
        ],
        "model_requests": 0,
        "external_requests": 0,
        "relay_errors": 0,
        "page_errors": [],
        "cleanup": {
            "browser_closed": True,
            "owned_pids_gone": True,
            "owned_driver_gone": True,
            "relay_idle": True,
            "relay_stopped": True,
            "relay_port_closed": True,
            "debug_port_closed": True,
        },
        "browser_pids": [901, 902],
        "chromium": {
            "path": str(contract.HOST_CHROMIUM),
            "sha256": "a" * 64,
            "sha256_after": "a" * 64,
            "version": "fixture",
        },
        "driver_process": {
            "pid": 903,
            "path": "/fixed/playwright/driver/node",
            "sha256": "b" * 64,
            "sha256_after": "b" * 64,
        },
        "chromium_process": child(
            contract.chromium_argv(PurePosixPath("/owned/client/browser-home")), pid=901
        ),
        "screenshots": {
            name: {"bytes": 1, "sha256": "a" * 64}
            for name in (
                "browser-scoped.png",
                "browser-timeout.png",
                "browser-uncertain.png",
            )
        },
        "scoped_response": {
            "path": "/api/casebooks/" + scoped["id"],
            "method": "GET",
            "capability": "sinter-casebook/v2",
            "status": 200,
            "body": producer.original(output(scoped)),
        },
    }


def test_complete_synthetic_browser_parser_control_has_no_release_admission(synthetic):
    inner, _, _ = synthetic
    assert contract.validate_browser(browser_fixture(inner), inner) is None


@pytest.mark.parametrize(
    "attack",
    [
        "replay",
        "bool_posts",
        "float_posts",
        "lost_ack_502",
        "lost_ack_body",
        "unknown",
        "scope_capability",
        "scope_response",
        "scope_id",
        "bool_status",
        "provider",
        "external",
        "relay_error",
        "page_error",
        "browser_live",
        "driver_live",
        "listener_live",
        "debug_live",
        "missing_pixels",
        "missing_visible",
        "bool_pid",
        "duplicate_pid",
        "chrome_unreaped",
        "chrome_signal",
        "bad_driver",
        "final_ack_missing",
        "final_ack_502",
        "final_ack_bool",
        "final_ack_body",
        "old_browser_schema",
        "temporary_owner",
        "temporary_inode",
        "temporary_mode",
        "temporary_unremoved",
        "temporary_unicode_path",
    ],
)
def test_browser_refuses_resealed_uncertain_replay_wrong_content_or_resource_claims(
    synthetic, attack
):
    inner, _, _ = synthetic
    value = browser_fixture(inner)
    if attack == "replay":
        value["quit_posts"] = 3
    elif attack == "bool_posts":
        value["quit_posts"] = True
    elif attack == "float_posts":
        value["quit_posts"] = 2.0
    elif attack == "lost_ack_502":
        value["lost_ack_status"] = 502
    elif attack == "lost_ack_body":
        value["lost_ack_body"] = producer.original(output({"error": "busy"}))
    elif attack == "unknown":
        value["arbitrary_origin"] = "https://anything.invalid"
    elif attack == "scope_capability":
        value["scoped_response"]["capability"] = None
    elif attack == "scope_response":
        value["scoped_response"]["body"] = producer.original(output({"document": {}}))
    elif attack == "scope_id":
        value["scoped_response"]["path"] = "/api/casebooks/" + "0" * 32
    elif attack == "bool_status":
        value["scoped_response"]["status"] = True
    elif attack == "provider":
        value["model_requests"] = 1
    elif attack == "external":
        value["external_requests"] = 1
    elif attack == "relay_error":
        value["relay_errors"] = 1
    elif attack == "page_error":
        value["page_errors"] = ["TypeError"]
    elif attack == "browser_live":
        value["cleanup"]["browser_closed"] = False
    elif attack == "driver_live":
        value["cleanup"]["owned_driver_gone"] = False
    elif attack == "listener_live":
        value["cleanup"]["relay_port_closed"] = False
    elif attack == "debug_live":
        value["cleanup"]["debug_port_closed"] = False
    elif attack == "missing_pixels":
        value["screenshots"].pop("browser-uncertain.png")
    elif attack == "missing_visible":
        value["visible_checks"].pop(2)
    elif attack == "bool_pid":
        value["browser_pids"][0] = True
    elif attack == "duplicate_pid":
        value["browser_pids"][1] = value["browser_pids"][0]
    elif attack == "chrome_unreaped":
        value["chromium_process"]["streams_complete"] = False
    elif attack == "chrome_signal":
        value["chromium_process"]["sigterm_sent"] = True
    elif attack == "bad_driver":
        value["driver_process"]["pid"] = 903.0
    elif attack == "final_ack_missing":
        value.pop("confirmed_ack")
    elif attack == "final_ack_502":
        value["confirmed_ack"]["status"] = 502
    elif attack == "final_ack_bool":
        value["confirmed_ack"]["status"] = True
    elif attack == "final_ack_body":
        value["confirmed_ack"]["body"] = producer.original(
            output({"error": "not accepted"})
        )
    elif attack == "old_browser_schema":
        value["schema"] = "sinter-rc4-native-handoff-browser/v2"
    elif attack == "temporary_owner":
        value["temporary_directory"]["identity_before"]["st_uid"] += 1
        value["temporary_directory"]["identity_after"]["st_uid"] += 1
    elif attack == "temporary_inode":
        value["temporary_directory"]["identity_after"]["st_ino"] += 1
    elif attack == "temporary_mode":
        value["temporary_directory"]["identity_before"]["st_mode"] |= 0o022
        value["temporary_directory"]["identity_after"]["st_mode"] |= 0o022
    elif attack == "temporary_unremoved":
        value["temporary_directory"]["removed"] = False
    elif attack == "temporary_unicode_path":
        value["temporary_directory"]["path"] = "/tmp/sinter-native-" + "資料🧭" * 12
    with pytest.raises((ValueError, TypeError, KeyError)):
        contract.validate_browser(value, inner)


def test_secondary_cleanup_failures_never_replace_primary_and_all_attempts_run():
    cleanup = producer.Cleanup()
    primary = RuntimeError("actual UI body failed")
    observed = []

    def fail(role):
        observed.append(role)
        raise OSError("secondary " + role)

    try:
        try:
            raise primary
        finally:
            cleanup.call("context.close", lambda: fail("context"))
            cleanup.call("browser.close", lambda: fail("browser"))
            cleanup.call("relay.shutdown", lambda: fail("relay"))
            cleanup.call("retain-response", lambda: observed.append("retained"))
    except RuntimeError as error:
        assert error is primary
    assert observed == ["context", "browser", "relay", "retained"]
    assert [error["role"] for error in cleanup.errors] == [
        "context.close",
        "browser.close",
        "relay.shutdown",
    ]


def test_malformed_create_id_can_never_target_a_name_or_unowned_resource(
    tmp_path, monkeypatch
):
    observed = []
    monkeypatch.setattr(old, "validate_image", lambda *_: {})

    def row(role, argv, *_args, **_kwargs):
        observed.append((role, argv))
        return (0, b"image") if role == "image" else (0, b"customer-container-name\n")

    monkeypatch.setattr(owner, "docker_row", row)
    pins = owner.pins_for(PurePosixPath("/owned/test"), "a" * 64)
    pins["qualification"] = "dev"
    with pytest.raises(ValueError):
        producer.handoff_lifecycle(
            tmp_path, {}, pins, [], [], [], contract.HOST_CHROMIUM
        )
    assert [role for role, _ in observed] == ["image", "create"]


def test_fixed_chromium_invocation_preserves_os_security_and_private_profile():
    argv = contract.chromium_argv(PurePosixPath("/owned/client/browser-home"))
    assert argv[0] == str(contract.HOST_CHROMIUM)
    assert "--user-data-dir=/owned/client/browser-home/profile" in argv
    assert "--remote-debugging-address=127.0.0.1" in argv
    assert "--no-sandbox" not in argv and "--disable-web-security" not in argv


@pytest.mark.parametrize("table", list(contract.TABLE_SCHEMAS))
def test_consistently_resealed_initial_sql_cannot_hide_schema_repair(synthetic, table):
    inner, source, package = synthetic
    database = "campaigns.sqlite3" if table == "campaigns" else "workspace.sqlite3"
    for snapshot in inner["snapshots"].values():
        snapshot["databases"][database]["tables"][table]["sql"] += (
            " /* concealed repair */"
        )
    with pytest.raises(ValueError, match="complete SQL"):
        contract.validate_inner(inner, source, package)


@pytest.mark.parametrize(
    "attack",
    [
        "replay",
        "arbitrary-route",
        "wrong-owner",
        "wrong-length",
        "completed-body",
        "wrong-response",
        "extra-response",
        "missing-length",
    ],
)
def test_interrupted_request_requires_original_fixed_wire_and_complete_refusal(attack):
    value = interrupted_fixture(32123)
    if attack == "replay":
        value["attempts"] = 2
    else:
        field = (
            "request"
            if attack
            in {"arbitrary-route", "wrong-owner", "wrong-length", "completed-body"}
            else "response"
        )
        raw = old.full_bytes(value[field])
        if attack == "arbitrary-route":
            raw = raw.replace(b"/api/casebooks/save", b"/api/chat")
        elif attack == "wrong-owner":
            raw = raw.replace(b"32123", b"32124")
        elif attack == "wrong-length":
            raw = raw.replace(b"Content-Length: 100", b"Content-Length: 12")
        elif attack == "completed-body":
            raw += b"{}}"
        elif attack == "wrong-response":
            raw = raw.replace(b"400 Bad Request", b"200 OK")
        elif attack == "extra-response":
            raw += b"{}"
        elif attack == "missing-length":
            raw = raw.replace(b"Content-Length: ", b"Unknown-Length: ")
        value[field] = producer.original(raw)
    with pytest.raises(ValueError):
        contract.validate_interrupted(value, 32123)


def test_actual_source_interrupted_http_refusal_keeps_fictional_originals(
    synthetic, tmp_path
):
    """Real isolated SOURCE HTTP route; no native/browser/installer claim."""
    from sinter.server import LocalServer

    data = tmp_path / "data"
    before = producer.disk_snapshot(data)
    with Runtime(data) as runtime:
        server = LocalServer(("127.0.0.1", 0), runtime.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            evidence = producer.interrupted_body(server.server_port)
            contract.validate_interrupted(evidence, server.server_port)
            assert producer.disk_snapshot(data) == before
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    assert_source_listener_closed(server, thread)


@pytest.fixture
def owned_source_listener():
    from sinter.server import LocalServer

    server = LocalServer(("127.0.0.1", 0), None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, thread
    finally:
        if thread.is_alive():
            server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_source_listener_closure_reacquires_owned_closed_address(owned_source_listener):
    server, thread = owned_source_listener
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    assert_source_listener_closed(server, thread)


def test_source_listener_closure_refuses_actual_still_active_owner(
    owned_source_listener,
):
    server, thread = owned_source_listener
    with pytest.raises(AssertionError):
        assert_source_listener_closed(server, thread)
    assert thread.is_alive() and server.socket.fileno() >= 0


@pytest.mark.parametrize("connection_timeout", [False, True])
def test_source_listener_closure_refuses_conflicting_live_listener_even_with_timeout(
    owned_source_listener, monkeypatch, connection_timeout
):
    server, thread = owned_source_listener
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    attempts = []

    def timed_out(*args, **kwargs):
        attempts.append((args, kwargs))
        raise TimeoutError("A live listener's connection probe timed out.")

    if connection_timeout:
        monkeypatch.setattr(socket, "create_connection", timed_out)
    with socket.socket(server.address_family, socket.SOCK_STREAM) as conflict:
        conflict.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        conflict.bind(server.server_address)
        conflict.listen(1)
        with pytest.raises(OSError):
            assert_source_listener_closed(server, thread)
    assert attempts == []


@pytest.mark.parametrize("conflict", [False, True])
def test_source_listener_windows_exclusive_option_precedes_bind(monkeypatch, conflict):
    """Mapped Winsock API order; actual Windows execution remains a CI gate."""
    observed = []
    exclusive = 12345

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            observed.append(("close",))

        def setsockopt(self, *args):
            observed.append(("option", *args))

        def bind(self, address):
            observed.append(("bind", address))
            if conflict:
                raise OSError("Exclusive address is still owned.")

        def listen(self, backlog):
            observed.append(("listen", backlog))

        def getsockname(self):
            return ("127.0.0.1", 32123)

    server = SimpleNamespace(
        socket=SimpleNamespace(fileno=lambda: -1),
        address_family=socket.AF_INET,
        server_address=("127.0.0.1", 32123),
    )
    thread = SimpleNamespace(is_alive=lambda: False)
    with monkeypatch.context() as patch:
        patch.setattr(sys, "platform", "win32")
        patch.setattr(socket, "SO_EXCLUSIVEADDRUSE", exclusive, raising=False)
        patch.setattr(socket, "socket", lambda *_: Probe())
        if conflict:
            with pytest.raises(OSError, match="still owned"):
                assert_source_listener_closed(server, thread)
        else:
            assert_source_listener_closed(server, thread)
    assert observed[:2] == [
        ("option", socket.SOL_SOCKET, exclusive, 1),
        ("bind", server.server_address),
    ]
    assert observed[-1] == ("close",)
    assert ("listen", 1) in observed if not conflict else ("listen", 1) not in observed


@pytest.mark.parametrize("journey", ["interrupted", "held"])
def test_real_source_journeys_do_not_use_timeout_as_closure_evidence(
    synthetic, tmp_path, monkeypatch, journey
):
    """Actual source bodies unchanged; the old Linux-only postcheck is injected."""

    def old_postcheck(_port):
        raise TimeoutError("Closed-loopback connect can time out on Windows.")

    monkeypatch.setattr(producer, "port_closed", old_postcheck)
    run = (
        test_actual_source_interrupted_http_refusal_keeps_fictional_originals
        if journey == "interrupted"
        else test_actual_source_held_api_body_matches_after_native_no_without_gui
    )
    run(synthetic, tmp_path)


def test_browser_body_failure_survives_every_secondary_close_and_retains_proof(
    tmp_path, monkeypatch
):
    """Only controlled mocks; no Chromium, display or Docker execution."""
    root = tmp_path / "handoff-container/out/handoff"
    root.mkdir(parents=True)
    (root.parent.parent / "client").mkdir()
    monkeypatch.setattr(contract, "preflight_browser_temporary", lambda: None)
    private = root.parent.parent / "client/controlled-browser-temp"

    def create(record):
        private.mkdir()
        record.update(path=str(private), identity_before={"controlled": True})

    def remove(record):
        private.rmdir()
        record.update(identity_after=record["identity_before"], removed=True)

    monkeypatch.setattr(producer, "create_browser_temporary", create)
    monkeypatch.setattr(producer, "remove_browser_temporary", remove)
    primary = RuntimeError("original visible UI body failed")
    observed = []

    def fail(role):
        observed.append(role)
        raise OSError("secondary " + role)

    relay = SimpleNamespace(
        server_address=("127.0.0.1", 32124),
        model_requests=0,
        errors=0,
        serve_forever=lambda: None,
        idle=lambda: fail("idle"),
        shutdown=lambda: fail("relay.shutdown"),
        server_close=lambda: fail("relay.close"),
    )
    thread = SimpleNamespace(
        start=lambda: None,
        join=lambda **_: observed.append("relay.join"),
        is_alive=lambda: False,
    )
    page = SimpleNamespace(
        on=lambda *_: None, goto=lambda *_: (_ for _ in ()).throw(primary)
    )
    context = SimpleNamespace(
        route_web_socket=lambda *_: None,
        route=lambda *_: None,
        new_page=lambda: page,
        close=lambda: fail("context.close"),
    )
    cdp = SimpleNamespace(send=lambda *_: {"processInfo": [{"id": 901}, {"id": 902}]})
    chrome = SimpleNamespace(
        new_browser_cdp_session=lambda: cdp,
        version="mock",
        new_context=lambda: context,
        close=lambda: fail("browser.close"),
    )
    engine = SimpleNamespace(
        chromium=SimpleNamespace(connect_over_cdp=lambda *_: chrome),
        stop=lambda: fail("playwright.stop"),
    )
    playwright = SimpleNamespace(__file__="/fixed/playwright/__init__.py")
    sync_api = SimpleNamespace(
        expect=lambda *_: None,
        sync_playwright=lambda: SimpleNamespace(start=lambda: engine),
    )
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    child_calls = iter([set(), {903}])
    monkeypatch.setattr(producer, "children", lambda: next(child_calls))
    monkeypatch.setattr(producer, "wait_file", lambda *_: {})
    monkeypatch.setattr(producer.transport, "Relay", lambda *_: relay)
    monkeypatch.setattr(producer.threading, "Thread", lambda **_: thread)
    monkeypatch.setattr(producer.native, "binary_digest", lambda *_: "a" * 64)
    monkeypatch.setattr(
        producer.os,
        "readlink",
        lambda *_: str(
            producer.Path(playwright.__file__).resolve().parent / "driver/node"
        ),
    )
    monkeypatch.setattr(producer, "alive", lambda *_: False)
    monkeypatch.setattr(producer, "port_closed", lambda *_: True)

    def popen(*_args, **_kwargs):
        profile = root.parent.parent / "client/browser-home/profile"
        profile.mkdir()
        (profile / "DevToolsActivePort").write_text(
            "32125\n/devtools/browser/a-b-c\n", encoding="ascii"
        )
        return SimpleNamespace(pid=901, returncode=None, poll=lambda: None)

    monkeypatch.setattr(producer.subprocess, "Popen", popen)
    monkeypatch.setattr(
        producer.native,
        "stop_process",
        lambda _process, row: row.update(
            exit_code=-15, sigterm_sent=True, owned_group_remaining=False
        ),
    )
    with pytest.raises(RuntimeError) as result:
        producer.browser(root, contract.HOST_CHROMIUM)
    assert result.value is primary
    value = producer.read_json(root.parent.parent / "browser.json")
    assert value["error"] == str(primary)
    assert "context.close" in observed and "browser.close" in observed
    assert (
        "relay.shutdown" in observed
        and "relay.close" in observed
        and "relay.join" in observed
    )
    assert [error["role"] for error in value["cleanup_errors"]] == [
        "context.close",
        "browser.close",
        "playwright.stop",
        "await-owned-resources",
        "observe-relay-idle",
        "relay.shutdown",
        "relay.server_close",
    ]
    assert (root / "chromium.stdout").is_file() and (root / "chromium.stderr").is_file()


def synthetic_outer():
    previous, pins = outer_fixture()
    pins["qualification"] = "dev"
    command = contract.creation_argv(pins, "sinter-native-entry-abcdefghijkl")
    rows = previous["commands"]
    rows[1]["argv"] = command
    for index in (2, 4):
        body = json.loads(old.stream_bytes(rows[index]["stdout"]))
        body[0]["Config"]["Cmd"] = command[command.index(pins["image_id"]) + 1 :]
        body[0]["Args"] = command[command.index(pins["image_id"]) + 2 :]
        rows[index]["stdout"] = stream(output(body))
    version = {
        **child(
            ["docker", "--version"], b"Docker version controlled-fixture\n", pid=1000
        ),
        "passed": True,
    }
    clients = [
        version,
        *[
            {
                **child(
                    row["argv"],
                    old.stream_bytes(row["stdout"]),
                    old.stream_bytes(row["stderr"]),
                    pid=1001 + index,
                    code=row["exit_code"],
                ),
                "passed": index != 6,
            }
            for index, row in enumerate(rows)
        ],
    ]
    bundle = {
        "schema": "sinter-owned-native-handoff-container/v1",
        "cleanup_commands": [],
        "commands": rows,
        "docker_client": {
            # This is a host binary identity, unlike Linux container paths.
            "path": os.path.abspath("fixed-docker"),
            "sha256": "a" * 64,
            "sha256_after": "a" * 64,
            "version": version,
        },
        "source_manifest": {},
        "source_manifest_sha256": "a" * 64,
        "tools": {},
    }
    return bundle, clients, pins


def test_complete_synthetic_outer_binds_fixed_lifecycle_to_every_actual_child():
    bundle, clients, pins = synthetic_outer()
    assert contract.validate_outer(bundle, clients, pins)["container_id"] == "2" * 64


def test_synthetic_outer_docker_identity_is_host_absolute():
    bundle, _, _ = synthetic_outer()
    assert Path(bundle["docker_client"]["path"]).is_absolute()


def test_synthetic_outer_keeps_host_windows_identity_separate_from_linux_namespace(
    monkeypatch,
):
    """Mapped Windows path semantics; no Windows process or Docker execution."""
    with monkeypatch.context() as patch:
        patch.setattr(os.path, "abspath", lambda _: "C:\\fixed\\docker.exe")
        patch.setattr(contract, "Path", PureWindowsPath)
        bundle, clients, pins = synthetic_outer()
        assert bundle["docker_client"]["path"] == "C:\\fixed\\docker.exe"
        assert (
            contract.validate_outer(bundle, clients, pins)["container_id"] == "2" * 64
        )


@pytest.mark.parametrize(
    "attack",
    [
        "missing-child",
        "wrong-child-argv",
        "detached-stream",
        "unreaped-child",
        "bool-exit",
        "float-exit",
        "same-child-pid",
        "changed-client",
        "version-error",
        "unknown-child-error",
        "emergency",
        "unknown-field",
        "created-false-pid",
        "missing-oom",
        "missing-error",
        "unordered-time",
        "mixed-absence",
    ],
)
def test_new_outer_keeps_strict_v4_state_lifecycle_stream_and_actual_child_admission(
    attack,
):
    bundle, clients, pins = synthetic_outer()
    if attack == "missing-child":
        clients.pop(3)
    elif attack == "wrong-child-argv":
        clients[4]["argv"][-1] = "customer-resource"
    elif attack == "detached-stream":
        clients[3]["stdout"] = stream(b"detached")
    elif attack == "unreaped-child":
        clients[3]["streams_complete"] = False
    elif attack == "bool-exit":
        clients[3]["exit_code"] = False
    elif attack == "float-exit":
        clients[3]["exit_code"] = 0.0
    elif attack == "same-child-pid":
        clients[3]["pid"] = clients[4]["pid"]
    elif attack == "changed-client":
        bundle["docker_client"]["sha256_after"] = "b" * 64
    elif attack == "version-error":
        clients[0]["stderr"] = stream(b"version error")
    elif attack == "unknown-child-error":
        clients[3]["body_error_type"] = "TimeoutError"
    elif attack == "emergency":
        bundle["cleanup_commands"] = [{"role": "cleanup-term"}]
    elif attack == "unknown-field":
        bundle["arbitrary_command"] = "execute"
    elif attack == "mixed-absence":
        bundle["commands"][6]["stderr"] = stream(
            b"Error: No such object: " + b"2" * 64 + b"\npermission denied\n"
        )
        clients[7]["stderr"] = copy.deepcopy(bundle["commands"][6]["stderr"])
    else:
        index = 4 if attack == "unordered-time" else 2
        body = json.loads(old.stream_bytes(bundle["commands"][index]["stdout"]))
        if attack == "created-false-pid":
            body[0]["State"]["Pid"] = False
        elif attack == "missing-oom":
            body[0]["State"].pop("OOMKilled")
        elif attack == "missing-error":
            body[0]["State"].pop("Error")
        elif attack == "unordered-time":
            body[0]["State"]["StartedAt"] = "2026-10-02T00:00:00.900000001Z"
        record = stream(output(body))
        bundle["commands"][index]["stdout"] = record
        clients[index + 1]["stdout"] = copy.deepcopy(record)
    with pytest.raises((ValueError, TypeError, KeyError)):
        contract.validate_outer(bundle, clients, pins)


def test_container_body_failure_preserves_primary_and_attempts_all_independent_cleanup(
    tmp_path, monkeypatch
):
    primary = RuntimeError("original browser handoff failed")
    observed, cleanup = [], []
    monkeypatch.setattr(old, "validate_image", lambda *_: None)
    monkeypatch.setattr(old, "validate_container_observation", lambda *_: None)

    def row(role, _argv, *_args, **_kwargs):
        observed.append(role)
        if role == "create":
            return 0, b"2" * 64 + b"\n"
        if role == "created":
            return 0, b"[{}]"
        if role in {"remove", "removed"}:
            raise OSError("secondary " + role)
        return 0, b""

    def capture(role, *_args, **_kwargs):
        observed.append(role)
        raise TimeoutError("secondary " + role)

    def thread(target, **_kwargs):
        def join(**_):
            observed.append("worker.join")
            raise OSError("secondary join")

        return SimpleNamespace(start=target, join=join, is_alive=lambda: False)

    monkeypatch.setattr(owner, "docker_row", row)
    monkeypatch.setattr(owner, "capture", capture)
    monkeypatch.setattr(producer.threading, "Thread", thread)
    monkeypatch.setattr(producer, "browser", lambda *_: (_ for _ in ()).throw(primary))
    pins = owner.pins_for(PurePosixPath("/owned/test"), "a" * 64)
    pins["qualification"] = "dev"
    with pytest.raises(RuntimeError) as result:
        producer.handoff_lifecycle(
            tmp_path, {}, pins, [], [], cleanup, contract.HOST_CHROMIUM
        )
    assert result.value is primary
    assert observed == [
        "image",
        "create",
        "created",
        "start",
        "cleanup-term",
        "cleanup-wait",
        "worker.join",
        "remove",
        "removed",
    ]
    assert [row["role"] for row in cleanup] == [
        "cleanup-term-error",
        "cleanup-wait-error",
        "cleanup-attached-client-error",
        "remove",
        "removed",
    ]


@pytest.mark.parametrize("failure", [False, True])
def test_owned_driver_inherits_only_fixed_fictional_environment_then_restores_caller(
    monkeypatch, failure
):
    monkeypatch.setenv("SINTER_TEST_SECRET_SENTINEL", "must-not-be-inherited")
    before = dict(producer.os.environ)
    private = {
        "HOME": "/fixed/fictional-home",
        "PATH": producer.os.defpath,
        "TMPDIR": "/fixed/private-tmp",
    }
    primary = RuntimeError("driver failed")

    def start():
        assert dict(producer.os.environ) == private
        if failure:
            raise primary
        return "mock owned driver"

    factory = lambda: SimpleNamespace(start=start)
    if failure:
        with pytest.raises(RuntimeError) as result:
            producer.start_playwright(factory, private)
        assert result.value is primary
    else:
        assert producer.start_playwright(factory, private) == "mock owned driver"
    assert dict(producer.os.environ) == before


def test_owned_native_stream_close_failures_preserve_body_and_attempt_both(monkeypatch):
    primary = RuntimeError("actual native body failed")
    observed = []

    def close(name):
        observed.append(name)
        raise OSError("secondary " + name)

    streams = iter(
        [
            SimpleNamespace(close=lambda: close("stdout")),
            SimpleNamespace(close=lambda: close("stderr")),
        ]
    )
    monkeypatch.setattr(producer.tempfile, "TemporaryFile", lambda: next(streams))
    cleanup = producer.Cleanup()
    with pytest.raises(RuntimeError) as result:
        with producer.owned_streams(cleanup):
            raise primary
    assert result.value is primary
    assert observed == ["stdout", "stderr"]
    assert [row["role"] for row in cleanup.errors] == [
        "native-stream.stdout.close",
        "native-stream.stderr.close",
    ]


@pytest.mark.parametrize(
    "attack",
    [
        "extra-file",
        "empty-directory",
        "nested-empty",
        "missing-file",
        "wrong-directory",
        "symlink",
        "special-type",
    ],
)
def test_closed_artifact_inventory_refuses_unlisted_entries_without_opening_them(
    tmp_path, monkeypatch, attack
):
    root = tmp_path / "proof"
    root.mkdir()
    (root / "nested").mkdir()
    (root / "nested/evidence.json").write_bytes(b"{}")
    expected = {"nested/evidence.json"}
    if attack == "extra-file":
        (root / "unlisted.json").write_bytes(b"{}")
    elif attack == "empty-directory":
        (root / "unlisted").mkdir()
    elif attack == "nested-empty":
        (root / "nested/unlisted").mkdir()
    elif attack == "missing-file":
        (root / "nested/evidence.json").unlink()
    elif attack == "wrong-directory":
        (root / "nested/evidence.json").unlink()
        (root / "nested/evidence.json").mkdir()
    elif attack in {"symlink", "special-type"}:
        # Portable type observation; never create/open a device or link here.
        original = producer.Path.lstat
        mode = 0o120777 if attack == "symlink" else 0o010600
        monkeypatch.setattr(
            producer.Path,
            "lstat",
            lambda path: (
                SimpleNamespace(st_mode=mode)
                if path.name == "evidence.json"
                else original(path)
            ),
        )
    with pytest.raises(ValueError):
        contract.closed_tree(root, expected)


def test_closed_inventory_accepts_exact_regular_artifacts_and_parent_directories(
    tmp_path,
):
    root = tmp_path / "proof"
    root.mkdir()
    (root / "nested").mkdir()
    (root / "nested/evidence.json").write_bytes(b"{}")
    contract.closed_tree(root, {"nested/evidence.json"})
    contract.closed_children(root, set(), {"nested"})


@pytest.mark.skipif(
    not hasattr(os, "mkfifo"),
    reason="Actual FIFO resource requires POSIX mkfifo; portable type negatives remain active.",
)
def test_unlisted_real_fifo_is_refused_before_any_read(tmp_path, monkeypatch):
    root = tmp_path / "proof"
    root.mkdir()
    os.mkfifo(root / "unlisted", 0o600)
    monkeypatch.setattr(
        producer.Path, "read_bytes", lambda *_: pytest.fail("FIFO must never be opened")
    )
    with pytest.raises(ValueError, match="Special"):
        contract.closed_tree(root, set())


@pytest.mark.parametrize(
    "mutation",
    [
        "launcher_owner",
        "driver_owner",
        "display_owner",
        "launcher_display",
        "driver_display",
        "launcher_open_driver",
        "launch_port",
        "launch_port_bool",
        "launch_extra",
        "hold_extra",
        "hold_response_extra",
        "hold_body_extra",
        "hold_state_closed",
        "hold_state_running",
        "hold_state_idle",
        "hold_state_extra",
        "hold_active_bool",
        "hold_token_bad",
        "hold_token_changed",
        "hold_version_bad",
        "hold_notice_bad",
        "action_extra",
        "action_command_diagnostic",
        "action_status_object",
        "action_signal_integer",
        "action_forced_integer",
        "action_passed_integer",
        "package_command_extra",
        "seed_command_extra",
        "reader_command_extra",
    ],
)
def test_independent_native_alias_nested_and_phase_witnesses_refuse(
    synthetic, mutation
):
    """Mapped controls preserve the independent mutation while using full API data."""
    value, source, package = copy.deepcopy(synthetic)
    contract.validate_inner(value, source, package)
    if mutation == "launcher_owner":
        value["launch"]["pid"] = value["owner"]["pid"]
    elif mutation == "driver_owner":
        value["actions"][0]["command"]["pid"] = value["owner"]["pid"]
    elif mutation == "display_owner":
        value["display_evidence"]["display"]["pid"] = value["owner"]["pid"]
    elif mutation == "launcher_display":
        value["launch"]["pid"] = value["display_evidence"]["display"]["pid"]
    elif mutation == "driver_display":
        value["actions"][0]["command"]["pid"] = value["display_evidence"]["display"][
            "pid"
        ]
    elif mutation == "launcher_open_driver":
        value["launch"]["pid"] = value["actions"][1]["command"]["pid"]
    elif mutation == "launch_port":
        value["launch"]["port"] += 1
    elif mutation == "launch_port_bool":
        value["launch"]["port"] = True
    elif mutation == "launch_extra":
        value["launch"]["unreviewed"] = True
    elif mutation == "hold_extra":
        value["hold"]["unreviewed"] = True
    elif mutation == "hold_response_extra":
        value["hold"]["session"]["unreviewed"] = True
    elif mutation.startswith("hold_"):
        session = old.json_object(old.full_bytes(value["hold"]["session"]["body"]))
        if mutation == "hold_body_extra":
            session["unreviewed"] = True
        elif mutation == "hold_state_extra":
            session["native_quit"]["unreviewed"] = True
        elif mutation == "hold_active_bool":
            session["native_quit"]["active_requests"] = True
        elif mutation == "hold_token_bad":
            session["token"] = "token-from-a-different-shape"
        elif mutation == "hold_token_changed":
            session["token"] = "b" * 43
        elif mutation == "hold_version_bad":
            session["version"] = "0.5.3"
        elif mutation == "hold_notice_bad":
            session["session_notice"] = "Owner can safely be discarded"
        else:
            session["native_quit"]["state"] = mutation.removeprefix("hold_state_")
        value["hold"]["session"]["body"] = producer.original(output(session))
    elif mutation == "action_extra":
        value["actions"][0]["unreviewed"] = True
    elif mutation == "action_command_diagnostic":
        value["actions"][0]["command"]["diagnostic"] = "actual native driver failure"
    elif mutation == "action_status_object":
        action = value["actions"][0]
        action["result"]["status"] = {"hidden": "diagnostic"}
        action["command"]["stdout"] = stream(output(action["result"]))
    elif mutation in {
        "action_signal_integer",
        "action_forced_integer",
        "action_passed_integer",
    }:
        flag = {
            "action_signal_integer": "sigterm_sent",
            "action_forced_integer": "forced_cleanup",
            "action_passed_integer": "passed",
        }[mutation]
        value["actions"][0]["command"][flag] = 0 if flag != "passed" else 1
    elif mutation == "package_command_extra":
        value["commands"][1]["diagnostic"] = "unbound source read diagnostic"
    elif mutation == "seed_command_extra":
        value["seed"][0]["diagnostic"] = "unbound seed diagnostic"
    else:
        value["reads"][0]["diagnostic"] = "unbound reader diagnostic"
    with pytest.raises((ValueError, TypeError, KeyError)):
        contract.validate_inner(value, source, package)


@pytest.mark.parametrize("role", ["main", "worker"])
def test_actual_driver_pid_is_disjoint_from_full_chrome_inventory(synthetic, role):
    inner, _, _ = synthetic
    value = browser_fixture(inner)
    contract.validate_browser(value, inner)
    value["driver_process"]["pid"] = (
        value["chromium_process"]["pid"] if role == "main" else value["browser_pids"][1]
    )
    with pytest.raises(ValueError, match="driver"):
        contract.validate_browser(value, inner)


def test_pid_reuse_across_finished_actions_and_other_namespaces_is_valid(synthetic):
    value, source, package = synthetic
    # These two UI lifetimes are sequential; neither aliases the continuing roles.
    value["actions"][2]["command"]["pid"] = value["actions"][0]["command"]["pid"]
    # Preparation is reaped before the continuing owner starts.
    value["seed"][0]["pid"] = value["owner"]["pid"]
    contract.validate_inner(value, source, package)
    browser = browser_fixture(value)
    # A host Chrome PID may numerically equal a container PID in another namespace.
    browser["browser_pids"][0] = value["owner"]["pid"]
    browser["chromium_process"]["pid"] = value["owner"]["pid"]
    contract.validate_browser(browser, value)


@pytest.mark.parametrize(
    "withdraw_fails,action_fails,destroy_fails",
    [
        (False, False, False),
        (False, True, False),
        (False, False, True),
        (False, True, True),
        (True, False, False),
        (True, False, True),
    ],
)
def test_driver_all_post_allocation_work_preserves_first_failure_and_destroy_trace(
    tmp_path, monkeypatch, withdraw_fails, action_fails, destroy_fails
):
    import traceback
    import types

    request = tmp_path / "request.json"
    producer.write_json(
        request, {"phase": "open-browser", "pid": 500, "window_ids": ["0x123"]}
    )
    observed = []
    primary = RuntimeError(
        "actual primary withdraw" if withdraw_fails else "actual primary action"
    )
    secondary = OSError("actual secondary destroy")

    class Root:
        def withdraw(self):
            observed.append("withdraw")
            if withdraw_fails:
                raise primary

        def destroy(self):
            observed.append("destroy")
            if destroy_fails:
                raise secondary

    def controller(*args):
        def run(*args):
            observed.append("action")
            if action_fails:
                raise primary
            return [], "success", list(contract.FIELDS)

        return SimpleNamespace(run_handoff=run, frame="0x123")

    tk = types.ModuleType("tkinter")
    tk.Tk = Root
    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setattr(producer.tk_driver, "admit_environment", lambda *args: None)
    monkeypatch.setattr(producer, "HandoffDriver", controller)
    caught = None
    try:
        result = producer.driver(request)
    except BaseException as error:
        caught = error
    assert observed[-1] == "destroy"
    if withdraw_fails or action_fails:
        assert caught is primary
        rendered = "".join(traceback.format_exception(caught))
        assert str(primary) in rendered
        if destroy_fails:
            assert caught.__cause__ is secondary and str(secondary) in rendered
    elif destroy_fails:
        assert caught is secondary
    else:
        assert caught is None and result["status"] == "success"


@pytest.mark.skipif(
    not callable(getattr(os, "killpg", None)),
    reason="Actual qualification collector requires POSIX process-group ownership.",
)
def test_fixed_command_shape_accepts_actual_reaped_ordinary_child_only(tmp_path):
    """Real child/byte shape, never a claim that dpkg or the GUI was invoked."""
    rows = []
    menu.command(
        [sys.executable, "-I", "-S", "-B", "-c", "pass"],
        rows,
        env={"PATH": os.defpath, "HOME": str(tmp_path)},
    )
    contract.command_fields(rows[-1])


@pytest.mark.parametrize(
    "mutation", [{"diagnostic": "hidden"}, {"sigterm_sent": 0}, {"passed": 1}]
)
def test_fixed_command_shape_portably_refuses_malformed_child_metadata(mutation):
    row = {**child(["fixed-child"]), "sigterm_sent": False}
    contract.command_fields(row)
    with pytest.raises(ValueError):
        contract.command_fields({**row, **mutation})


def test_actual_source_held_api_body_matches_after_native_no_without_gui(
    synthetic, tmp_path
):
    """Actual source loopback/API plus inert native-No prompt, no installed GUI."""
    import socket
    import time

    from sinter.native_browser import NativeBrowserWorkbench
    from sinter.native_window import NativeWindow

    data = tmp_path / "data"
    original = producer.disk_snapshot(data)
    with Runtime(data) as runtime:
        workbench = NativeBrowserWorkbench(runtime.app)
        window = NativeWindow.__new__(NativeWindow)
        window.closed = False
        window._browser_workbench = workbench
        window.messages = SimpleNamespace(askyesno=lambda *args, **kwargs: False)
        window.root = object()
        held = None
        try:
            window.request_close(browser_requested=True)
            held = socket.create_connection(
                ("127.0.0.1", workbench.server.server_port), timeout=2
            )
            deadline = time.monotonic() + 2
            while workbench.server.active_requests < 1 and time.monotonic() < deadline:
                time.sleep(0.005)
            response = producer.session_response(workbench.server.server_port)
            token = contract.validate_hold(
                {
                    "fixture": "admitted empty TCP connection",
                    "admitted": True,
                    "released_explicitly": True,
                    "session": response,
                },
                __import__("sinter").__version__,
            )
            producer.write_json(tmp_path / "held-session-response.json", response)
            held.shutdown(socket.SHUT_WR)
            held.close()
            held = None
            interrupted = producer.interrupted_body(workbench.server.server_port)
            contract.validate_interrupted(
                interrupted, workbench.server.server_port, token
            )
            producer.write_json(
                tmp_path / "interrupted-owner-response.json", interrupted
            )
            assert producer.disk_snapshot(data) == original
        finally:
            if held is not None:
                held.shutdown(socket.SHUT_WR)
                held.close()
            workbench.begin_close()
            deadline = time.monotonic() + 5
            while not workbench.closed and time.monotonic() < deadline:
                workbench.poll_close()
                time.sleep(0.005)
            assert workbench.closed
            assert not workbench.thread.is_alive()
        assert_source_listener_closed(workbench.server, workbench.thread)
