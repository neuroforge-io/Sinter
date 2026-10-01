"""Synthetic semantic controls only: no Docker, installer, display or binary run."""

import base64
import copy
import io
import json
import os
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

from sinter.campaigns import CampaignStore
from sinter.casebooks import Casebooks
from sinter.store import Store
from tools import installed_native_entry_contract as contract
from tools import installed_native_menu as owner
from tools import native_window_smoke as native
from tools.installed_native_tk import FIXTURE
from tools.package_native import linux_desktop_entries


def stream(raw=b""):
    return {
        "text": raw[:65536].decode("utf-8", errors="replace"),
        "base64": base64.b64encode(raw[:65536]).decode(),
        "bytes": len(raw),
        "sha256": contract.sha(raw),
        "truncated": len(raw) > 65536,
    }


def process(pid=200, exit_code=0):
    return {
        "pid": pid,
        "exit_code": exit_code,
        "owned_group_remaining": False,
        "forced_cleanup": False,
    }


def legacy(row):
    row.update(
        {
            "stderr" if key == "text" else "stderr_" + key: value
            for key, value in stream().items()
        }
    )
    return row


def output(value):
    return json.dumps(value, ensure_ascii=False).encode()


@pytest.mark.parametrize(
    "raw,code,stderr",
    [
        (b"install ok installed\n0.5.4~rc4~~dev0\n", 0, b""),
        (b"install ok installed\n0.5.3~rc3\n", 0, b""),
        (b"deinstall ok config-files\n0.5.4~rc4~~dev0\n", 0, b""),
        (b"install ok installed\n0.5.4~rc4~~dev0\nextra", 0, b""),
        (b"install ok installed\n0.5.4~rc4~~dev0\n", 1, b""),
        (b"install ok installed\n0.5.4~rc4~~dev0\n", 0, b"warning"),
    ],
)
def test_actual_dpkg_status_and_version_are_required(monkeypatch, raw, code, stderr):
    def command(argv, rows, **kwargs):
        assert argv == contract.VERSION_QUERY
        rows.append({"stderr": stream(stderr)})
        return code, raw

    monkeypatch.setattr(owner, "command", command)
    if code == 0 and not stderr and raw == b"install ok installed\n0.5.4~rc4~~dev0\n":
        assert (
            owner.installed_package_version("0.5.4~rc4~~dev0", [])["command_index"] == 0
        )
    else:
        with pytest.raises(ValueError, match="Actual installed"):
            owner.installed_package_version("0.5.4~rc4~~dev0", [])


@pytest.mark.parametrize(
    "exits,remaining,complete",
    [
        ([0, 0], False, True),
        ([None, 0], False, False),
        ([0, 0], True, False),
        ([0, 1], False, False),
    ],
)
def test_final_stdout_requires_reap_before_capture_and_matching_exit(
    exits, remaining, complete
):
    values = iter(exits)
    payload = b" " * 65536 + b"hidden exact stdout tail\xff"
    observed = native.stdout_observation(
        io.BytesIO(payload),
        SimpleNamespace(poll=lambda: next(values)),
        {"exit_code": 0, "owned_group_remaining": remaining},
    )
    assert observed["complete"] is complete
    assert observed["record"] == stream(payload)
    assert contract.stream_bytes(observed["record"], complete=False) == payload[:65536]
    with pytest.raises(ValueError, match="prefix"):
        contract.stream_bytes(observed["record"])


@pytest.mark.parametrize(
    "attack", ["count", "hash", "text", "truncated", "bool_size", "extra"]
)
def test_exact_stream_identity_refuses_forged_counts_hashes_and_types(attack):
    row = stream(b"literal\xff\n")
    if attack == "count":
        row["bytes"] += 1
    elif attack == "hash":
        row["sha256"] = "0" * 64
    elif attack == "text":
        row["text"] = "normalized"
    elif attack == "truncated":
        row["truncated"] = True
    elif attack == "bool_size":
        row["bytes"] = True
    else:
        row["passed"] = True
    with pytest.raises(ValueError):
        contract.stream_bytes(row)


def inner_fixture(tmp_path):
    version = "0.5.4rc4.dev0"
    source = {
        "commit": "a" * 40,
        "version": version,
        "archive_sha256": contract.sha(b"archive"),
    }
    entries = {
        name: {
            "bytes": len(text.encode()),
            "sha256": contract.sha(text.encode()),
            "base64": base64.b64encode(text.encode()).decode(),
        }
        for name, text in linux_desktop_entries(True).items()
    }
    package = {
        "installer_sha256": "b" * 64,
        "binary_sha256": "c" * 64,
        "binary_bytes": 123,
        "payload_tar_bytes": 3,
        "payload_tar_sha256": contract.sha(b"tar"),
        "entries": entries,
        "package_version": "0.5.4~rc4~~dev0",
    }
    pins = {"installer_name": "fictional-never-installed.deb"}
    home = "/out/native-entry/sinter-native-entry-fictional"
    mapped_path = "/out/sinter-frozen-window-fictional/workspace"
    documents, snapshots = [], []
    for name, fixture, formatted in (
        ("tk", FIXTURE, False),
        ("mapped", native.FICTIONAL_DOCUMENT, True),
    ):
        path = tmp_path / name
        store = Store(path)
        books = Casebooks(store)
        CampaignStore(path)
        document = books.save(fixture)
        preferences = json.dumps(
            native.FICTIONAL_PREFERENCES,
            ensure_ascii=False,
            indent=2 if formatted else None,
        ) + ("\n" if formatted else "")
        (path / "preferences.json").write_text(preferences, encoding="utf-8")
        documents.append(document)
        snapshots.append(native.retained_workspace_snapshot(path))
    diag = {
        "schema": "sinter-launch-check/v1",
        "version": version,
        **{
            k: True
            for k in (
                "frozen",
                "core_assets_available",
                "native_toolkit_available",
                "Tcl_resources_available",
                "bundled_Tk_resources_available",
            )
        },
    }

    def diagnostic():
        return legacy(
            {**process(), "stdout": output(diag).decode(), "stdout_truncated": False}
        )

    def offline(operations, document):
        rows = []
        for op in operations:
            result = (
                document
                if op != "runtime.status"
                else {
                    "connection": {
                        k: native.FICTIONAL_PREFERENCES[k]
                        for k in ("api_url", "model", "provider", "max_tokens")
                    },
                    "provider_tested": False,
                    "preferences_warning": "",
                    "counts": {
                        "casebooks": 1,
                        "campaigns": 0,
                        "reports": 0,
                        "watches": 0,
                    },
                }
            )
            rows.append(
                legacy(
                    {
                        **process(),
                        "operation": op,
                        "stdout_truncated": False,
                        "stdout": output(
                            {
                                "schema": "sinter-operation-result/v1",
                                "operation": op,
                                "version": version,
                                "ok": True,
                                "result": result,
                            }
                        ).decode(),
                    }
                )
            )
        return rows

    def window(pid):
        return {
            "pid": pid,
            "window_id": "0x" + str(pid),
            "mapped": True,
            "title": native.TITLE,
            "width": 1000,
            "height": 800,
        }

    launches, invocations, mapped_launches, streams = [], [], [], []
    for phase, pid in (("create", 1001), ("reopen", 1002)):
        action = {
            "schema": "sinter-installed-native-tk-action/v1",
            "phase": phase,
            "project_id": documents[0]["id"],
            "window_id": window(pid)["window_id"],
            "fields_exact": True,
            "save_button_invoked": phase == "create",
            "wm_close_invoked": True,
        }
        launches.append(
            legacy(
                {
                    **process(pid),
                    "phase": phase,
                    "argv": contract.NATIVE + ["--directory", home + "/workspace"],
                    "passed": True,
                    "mapped_windows": [window(pid)],
                    "owned_windows_remaining": [],
                    "stdout": stream(),
                    "stdout_complete": True,
                    "sigterm_sent": False,
                    "action": action,
                    "driver_command_index": 10 if phase == "create" else 11,
                }
            )
        )
    for pid in (1003, 1004):
        argv = contract.NATIVE + ["--directory", mapped_path]
        invocations.append({"argv": argv, "started": True, "pid": pid})
        mapped_launches.append(
            legacy(
                {
                    **process(pid),
                    "passed": True,
                    "sigterm_sent": True,
                    "owned_windows_remaining": [],
                    "mapped_windows": [window(pid)],
                }
            )
        )
        streams.append(
            {
                "argv": argv,
                "pid": pid,
                "stdout": {"complete": True, "exit_code": 0, "record": stream()},
            }
        )
    cleanup_paths = [
        home,
        str(PurePosixPath(mapped_path).parent),
        "/tmp/.X11-unix/X97",
        "/tmp/.X97-lock",
        home + "/xauthority",
    ]
    removal_paths = [
        "/opt/neuroforge/sinter/Sinter",
        "/usr/share/applications/sinter.desktop",
        "/usr/share/applications/sinter-native.desktop",
    ]
    probe = lambda paths: [
        "/usr/bin/python3",
        "-B",
        "-c",
        owner.FILESYSTEM_PROBE,
        *paths,
    ]
    args = [
        contract.STATUS_QUERY,
        ["git", "-C", "/repository", "archive", source["commit"]],
        *[
            ["dpkg-deb", "-f", "/candidate/" + pins["installer_name"], field]
            for field in ("Package", "Architecture", "Version")
        ],
        ["dpkg-deb", "--fsys-tarfile", "/candidate/" + pins["installer_name"]],
        ["dpkg", "-i", "/candidate/" + pins["installer_name"]],
        contract.STATUS_QUERY,
        contract.VERSION_QUERY,
        [
            "xauth",
            "-f",
            home + "/xauthority",
            "add",
            ":97",
            ".",
            "<private owned X authorization>",
        ],
        *[
            [
                "/usr/bin/python3",
                "-B",
                "/source/tools/installed_native_tk.py",
                "--request",
                home + "/" + phase + "-tk-request.json",
            ]
            for phase in ("create", "reopen")
        ],
        contract.VERSION_QUERY,
        probe(cleanup_paths),
        ["git", "-C", "/repository", "archive", source["commit"]],
        ["dpkg", "-r", "sinter"],
        contract.STATUS_QUERY,
        probe(removal_paths),
    ]
    bodies = [
        b"",
        b"archive",
        b"sinter\n",
        b"amd64\n",
        b"0.5.4~rc4~~dev0\n",
        b"tar",
        b"",
        b"install ok installed",
        b"install ok installed\n0.5.4~rc4~~dev0\n",
        b"",
        *[output(row["action"]) for row in launches],
        b"install ok installed\n0.5.4~rc4~~dev0\n",
        output([{"path": p, "lexists": False} for p in cleanup_paths]),
        b"archive",
        b"",
        b"",
        output([{"path": p, "lexists": False} for p in removal_paths]),
    ]
    commands = [
        {
            **process(2000 + i, 1 if i in (0, 16) else 0),
            "argv": argv,
            "stdout": stream(raw),
            "stderr": stream(contract.ABSENT if i in (0, 16) else b""),
            "streams_complete": True,
        }
        for i, (argv, raw) in enumerate(zip(args, bodies))
    ]
    binary = {"bytes": 123, "sha256": package["binary_sha256"], "executable": True}
    receipt = {
        "schema": contract.INNER_SCHEMA,
        "passed": True,
        "workflow_passed": True,
        "source": source,
        "package": package,
        "container": {
            "effective_uid": 0,
            "interfaces": ["lo"],
            "inherited_display": False,
            "docker_marker_present": True,
        },
        "native_command": contract.NATIVE,
        "installed_entries": entries,
        "installed_entries_after": copy.deepcopy(entries),
        "installed_binary": binary,
        "installed_binary_after": binary.copy(),
        "commands": commands,
        "installed_package": {
            "status": "install ok installed",
            "version": package["package_version"],
            "command_index": 8,
        },
        "installed_package_recheck": {
            "status": "install ok installed",
            "version": package["package_version"],
            "command_index": 12,
        },
        "owned_home": home,
        "tk_launches": launches,
        "offline_commands": offline(
            ["casebooks.get", "casebooks.get", "runtime.status"] * 2, documents[0]
        ),
        "diagnostic_process": diagnostic(),
        "frozen_diagnostics": diag,
        "tk_workspaces": [
            {"phase": phase, "snapshot": copy.deepcopy(snapshots[0])}
            for phase in ("create", "reopen")
        ],
        "invocations": invocations,
        "mapped_native_proof": {
            "schema": "sinter-frozen-native-window-test/v1",
            "passed": True,
            "binary_sha256": package["binary_sha256"],
            "binary_sha256_after": package["binary_sha256"],
            "binary_unchanged": True,
            "launches": mapped_launches,
            "system": "Linux",
            "machine": "x86_64",
            "diagnostic_process": diagnostic(),
            "frozen_diagnostics": diag,
            "offline_commands": offline(
                [
                    "casebooks.save",
                    "casebooks.get",
                    "runtime.status",
                    "casebooks.get",
                    "runtime.status",
                    "casebooks.get",
                    "runtime.status",
                ],
                documents[1],
            ),
        },
        "mapped_observations": {
            "streams": streams,
            "workspace_path": mapped_path,
            "workspace_removed": True,
            "workspaces": [
                {"phase": phase, "snapshot": copy.deepcopy(snapshots[1])}
                for phase in ("original", "after_launch_1", "after_launch_2")
            ],
        },
        "display": legacy(
            {
                **process(1005),
                "sigterm_sent": True,
                "stdout_observed": {
                    "complete": True,
                    "exit_code": 0,
                    "record": stream(),
                },
                "remaining_display_paths": [],
                "authority_remaining": False,
            }
        ),
        "fictional_workspace_removed": True,
        "removal": {
            "package_state": "absent",
            "remaining_paths": [],
            "command_exit": 0,
            "passed": True,
        },
        "workspace_cleanup_probe": {"paths": cleanup_paths, "command_index": 13},
        "removal_cleanup_probe": {"paths": removal_paths, "command_index": 17},
    }

    def observed(row, argv):
        return {
            "argv": argv,
            "pid": row.get("pid", 200),
            "stdout": {
                "complete": True,
                "exit_code": 0,
                "record": stream(row["stdout"].encode()),
            },
            "stderr": {"complete": True, "exit_code": 0, "record": stream()},
        }

    receipt["diagnostic_observation"] = observed(
        receipt["diagnostic_process"], [contract.NATIVE[0], "--diagnose"]
    )
    receipt["diagnostic_process"].pop("pid")  # Historical v1 diagnostic rows omit PID.
    sidecar = receipt["mapped_observations"]
    sidecar["diagnostic"] = observed(
        receipt["mapped_native_proof"]["diagnostic_process"],
        [contract.NATIVE[0], "--diagnose"],
    )
    receipt["mapped_native_proof"]["diagnostic_process"].pop("pid")
    for key, original, path in (
        ("offline_observations", receipt, home + "/workspace"),
        ("offline", receipt["mapped_native_proof"], mapped_path),
    ):
        destination = receipt if key == "offline_observations" else sidecar
        destination[key] = [
            observed(
                row,
                [
                    contract.NATIVE[0],
                    "run",
                    row["operation"],
                    "--input",
                    str(PurePosixPath(path).parent / "qualification-request.json"),
                    "--directory",
                    path,
                    "--format",
                    "json",
                ],
            )
            for row in original["offline_commands"]
        ]
    return receipt, source, package, pins


def test_closed_inner_semantics_accept_only_complete_synthetic_controls(tmp_path):
    receipt, source, package, pins = inner_fixture(tmp_path)
    result = contract.validate_inner(receipt, source, package, 7, pins)
    assert result["entry_pids"] == [1001, 1002, 1003, 1004]
    assert (
        "passed" not in result
        and result["scope"] == "installed Linux native-entry command only"
    )


@pytest.mark.parametrize(
    "attack",
    [
        "old",
        "version",
        "pre_reap",
        "source",
        "entry",
        "binary",
        "pid",
        "driver",
        "source_text",
        "preferences",
        "typed_integer",
        "typed_extra",
        "campaign",
        "stdout",
        "display_stdout",
        "display_diagnostic",
        "cleanup",
        "probe",
        "model",
        "command_order",
        "mapped_directory",
        "offline_directory",
        "offline_stream",
        "diagnostic_stream",
    ],
)
def test_inner_refuses_supplied_pass_flags_without_closed_semantics(tmp_path, attack):
    receipt, source, package, pins = inner_fixture(tmp_path)
    source, package = copy.deepcopy(source), copy.deepcopy(package)
    if attack == "old":
        receipt["schema"] = "sinter-installed-native-entry-test/v1"
    elif attack == "version":
        receipt["commands"][8]["stdout"] = stream(b"install ok installed\nold\n")
    elif attack == "pre_reap":
        receipt["commands"][8]["streams_complete"] = False
    elif attack == "source":
        receipt["source"]["commit"] = "d" * 40
    elif attack == "entry":
        receipt["installed_entries_after"]["sinter.desktop"]["sha256"] = "0" * 64
    elif attack == "binary":
        receipt["installed_binary_after"]["bytes"] = 99
    elif attack == "pid":
        receipt["tk_launches"][0]["mapped_windows"][0]["pid"] = 9999
    elif attack == "driver":
        receipt["commands"][10]["argv"][2] = "/unbound/driver.py"
    elif attack == "source_text":
        receipt["tk_workspaces"][1]["snapshot"]["sqlite"]["tables"]["casebooks"][
            "rows"
        ][0][4]["value"] = "{}"
    elif attack == "preferences":
        receipt["tk_workspaces"][1]["snapshot"]["preferences"]["base64"] = (
            base64.b64encode(b"{}").decode()
        )
    elif attack == "typed_integer":
        receipt["tk_workspaces"][1]["snapshot"]["sqlite"]["tables"]["casebooks"][
            "rows"
        ][0][1]["value"] = True
    elif attack == "typed_extra":
        receipt["tk_workspaces"][1]["snapshot"]["sqlite"]["tables"]["watches"][
            "rows"
        ] = [[{"type": "null", "value": None}]]
    elif attack == "campaign":
        receipt["tk_workspaces"][1]["snapshot"]["campaigns"]["metadata"][
            "application_id"
        ] = 1
    elif attack == "stdout":
        receipt["mapped_observations"]["streams"][0]["stdout"]["record"] = stream(
            b" " * 65536 + b"hidden bad tail"
        )
    elif attack == "display_stdout":
        receipt["display"]["stdout_observed"]["complete"] = False
    elif attack == "display_diagnostic":
        receipt["display"].update(
            {
                "stderr" if k == "text" else "stderr_" + k: v
                for k, v in stream(b"Tk callback failure").items()
            }
        )
    elif attack == "cleanup":
        receipt["removal"]["remaining_paths"] = ["/opt/neuroforge/sinter/Sinter"]
    elif attack == "probe":
        receipt["commands"][17]["stdout"] = stream(
            output(
                [
                    {"path": p, "lexists": True}
                    for p in receipt["removal_cleanup_probe"]["paths"]
                ]
            )
        )
    elif attack == "model":
        value = json.loads(receipt["offline_commands"][2]["stdout"])
        value["result"]["provider_tested"] = True
        receipt["offline_commands"][2]["stdout"] = output(value).decode()
    elif attack == "mapped_directory":
        for row in receipt["invocations"]:
            row["argv"] = row["argv"][:-1] + ["/unowned/different-workspace"]
    elif attack == "offline_directory":
        receipt["offline_observations"][0]["argv"][6] = "/unowned/different-workspace"
    elif attack == "offline_stream":
        receipt["offline_observations"][0]["stdout"]["complete"] = False
    elif attack == "diagnostic_stream":
        receipt["diagnostic_observation"]["stdout"]["record"] = stream(
            b" " * 65536 + b"hidden tail"
        )
    else:
        receipt["commands"][15]["argv"] = ["dpkg", "-r", "another-package"]
    with pytest.raises(ValueError):
        contract.validate_inner(receipt, source, package, 7, pins)


def outer_fixture():
    pins = {
        "image_id": "sha256:" + "e" * 64,
        "outer_owner_sha256": "f" * 64,
        "source_commit": "a" * 40,
        "source_directory": "/home/lloyd/fictional-owner/source",
        "repository": "/home/lloyd/fictional-owner/repository",
        "candidate_directory": "/home/lloyd/fictional-owner/candidate",
        "output_directory": "/home/lloyd/fictional-owner/output",
        "installer_name": "fictional-never-installed.deb",
        "package_receipt_name": "fictional-package.json",
        "artifacts": {"inner_receipt_sha256": "1" * 64},
    }
    identifier, name = "2" * 64, "sinter-native-entry-abcdefghijkl"
    create = contract.outer_argv(pins, name)
    observed = {
        "Id": identifier,
        "Created": "2026-10-02T00:00:00.000000001Z",
        "Path": "python3",
        "Args": create[create.index(pins["image_id"]) + 2 :],
        "Name": "/" + name,
        "Image": pins["image_id"],
        "Config": {
            "User": "0:0",
            "WorkingDir": "/",
            "Cmd": create[create.index(pins["image_id"]) + 1 :],
            "Entrypoint": None,
            "Env": [
                "PATH=/usr/bin:/bin",
                "TMPDIR=/out",
                "GIT_CONFIG_COUNT=1",
                "GIT_CONFIG_KEY_0=safe.directory",
                "GIT_CONFIG_VALUE_0=/repository",
                "PYTHONDONTWRITEBYTECODE=1",
            ],
        },
        "HostConfig": {
            "NetworkMode": "none",
            "Privileged": False,
            "ReadonlyRootfs": False,
            "CapDrop": ["ALL"],
            "PidsLimit": 64,
            "SecurityOpt": ["no-new-privileges"],
            "PidMode": "",
            "IpcMode": "private",
        },
        "Mounts": [
            {"Type": "bind", "Source": pins[k], "Destination": destination, "RW": rw}
            for k, destination, rw in (
                ("source_directory", "/source", False),
                ("repository", "/repository", False),
                ("candidate_directory", "/candidate", False),
                ("output_directory", "/out", True),
            )
        ],
        "State": {
            "Status": "created",
            "Running": False,
            "Paused": False,
            "Restarting": False,
            "OOMKilled": False,
            "Dead": False,
            "Pid": 0,
            "ExitCode": 0,
            "Error": "",
            "StartedAt": "0001-01-01T00:00:00Z",
            "FinishedAt": "0001-01-01T00:00:00Z",
        },
    }
    after = copy.deepcopy(observed)
    after["State"] = {
        "Status": "exited",
        "Paused": False,
        "Restarting": False,
        "Dead": False,
        "StartedAt": "2026-10-02T00:00:00.100000001Z",
        "Running": False,
        "Pid": 0,
        "ExitCode": 0,
        "OOMKilled": False,
        "Error": "",
        "FinishedAt": "2026-10-02T00:00:00.200000001Z",
    }
    args = [
        ["docker", "image", "inspect", pins["image_id"]],
        create,
        ["docker", "inspect", identifier],
        ["docker", "start", "-a", identifier],
        ["docker", "inspect", identifier],
        ["docker", "rm", identifier],
        ["docker", "inspect", identifier],
    ]
    bodies = [
        output([{"Id": pins["image_id"], "Os": "linux", "Architecture": "amd64"}]),
        (identifier + "\n").encode(),
        output([observed]),
        b"",
        output([after]),
        (identifier + "\n").encode(),
        b"[]\n",
    ]
    commands = [
        {
            "role": role,
            "argv": argv,
            "exit_code": 1 if role == "removed" else 0,
            "stdout": stream(body),
            "stderr": stream(
                ("Error: No such object: " + identifier + "\n").encode()
                if role == "removed"
                else b""
            ),
            "reaped": True,
        }
        for role, argv, body in zip(contract.ROLES, args, bodies)
    ]
    return {
        "schema": contract.OUTER_SCHEMA,
        "owner_sha256": pins["outer_owner_sha256"],
        "artifacts": pins["artifacts"].copy(),
        "commands": commands,
    }, pins


def test_complete_synthetic_outer_lifecycle_has_no_release_pass_field():
    bundle, pins = outer_fixture()
    assert contract.validate_outer(bundle, pins) == "2" * 64


@pytest.mark.parametrize(
    "attack",
    [
        "owner",
        "missing",
        "argv",
        "unreaped",
        "image",
        "network",
        "entrypoint",
        "display",
        "host_mount",
        "exit",
        "still_running",
        "forced_rm",
        "fake_absence",
        "bool_exit",
        "stderr",
    ],
)
def test_outer_requires_actual_closed_isolation_exit_and_removal(attack):
    bundle, pins = outer_fixture()
    if attack == "owner":
        bundle["owner_sha256"] = "0" * 64
    elif attack == "missing":
        bundle["commands"].pop()
    elif attack == "argv":
        bundle["commands"][3]["argv"][-1] = "other"
    elif attack == "unreaped":
        bundle["commands"][3]["reaped"] = False
    elif attack == "forced_rm":
        bundle["commands"][5]["argv"].insert(2, "-f")
    elif attack == "fake_absence":
        bundle["commands"][6]["stderr"] = stream(b"permission denied\n")
    elif attack == "bool_exit":
        bundle["commands"][4]["exit_code"] = False
    elif attack == "stderr":
        bundle["commands"][3]["stderr"] = stream(b"hidden owner error")
    else:
        value = json.loads(
            base64.b64decode(
                bundle["commands"][4 if attack in {"exit", "still_running"} else 2][
                    "stdout"
                ]["base64"]
            )
        )
        row = value[0]
        if attack == "image":
            row["Image"] = "sha256:" + "0" * 64
        elif attack == "network":
            row["HostConfig"]["NetworkMode"] = "host"
        elif attack == "entrypoint":
            row["Config"]["Entrypoint"] = ["another-owner"]
        elif attack == "display":
            row["Config"]["Env"].append("DISPLAY=:0")
        elif attack == "host_mount":
            row["Mounts"].append(
                {
                    "Type": "bind",
                    "Source": "/home/lloyd",
                    "Destination": "/customer",
                    "RW": False,
                }
            )
        elif attack == "exit":
            row["State"]["ExitCode"] = 1
        else:
            row["State"]["Running"] = True
        bundle["commands"][4 if attack in {"exit", "still_running"} else 2][
            "stdout"
        ] = stream(output(value))
    with pytest.raises(ValueError):
        contract.validate_outer(bundle, pins)


def test_missing_outer_owner_refuses_before_reading_or_running_anything(monkeypatch):
    monkeypatch.setattr(
        owner,
        "regular_bytes",
        lambda *_: pytest.fail(
            "No evidence or package command before outer ownership admission"
        ),
    )
    with pytest.raises(ValueError, match="separate actual owning"):
        contract.verify(
            SimpleNamespace(
                image_id="sha256:" + "a" * 64,
                outer_owner_sha256="b" * 64,
                outer_bundle=None,
            )
        )


def test_complete_workspace_observation_preserves_typed_raw_bytes(tmp_path):
    receipt, _, _, _ = inner_fixture(tmp_path)
    snapshot = receipt["tk_workspaces"][0]["snapshot"]
    assert (
        json.loads(contract.full_bytes(snapshot["preferences"]))
        == native.FICTIONAL_PREFERENCES
    )
    assert snapshot["sqlite"]["tables"]["casebooks"]["rows"][0][1] == {
        "type": "integer",
        "value": 1,
    }
    assert snapshot["campaigns"]["tables"]["campaigns"]["rows"] == []


def test_outer_refuses_writable_ancestor_alias_of_readonly_inputs():
    bundle, pins = outer_fixture()
    pins["output_directory"] = "/home/lloyd/fictional-owner"
    with pytest.raises(ValueError, match="disjoint"):
        contract.validate_outer(bundle, pins)


@pytest.mark.skipif(
    not hasattr(os, "killpg"),
    reason="Requires an actual POSIX process-group cleanup probe.",
)
def test_workspace_cleanup_is_corroborated_by_the_actual_probe(tmp_path, monkeypatch):
    missing = tmp_path / "absent"
    rows = []
    result = owner.observed_absence([missing], rows)
    assert result == {"paths": [str(missing)], "command_index": 0}
    assert rows[0]["streams_complete"] is True
    missing.symlink_to(tmp_path / "missing-target")
    with pytest.raises(ValueError, match="actual probe"):
        owner.observed_absence([missing], rows)
    assert (
        json.loads(base64.b64decode(rows[-1]["stdout"]["base64"]))[0]["lexists"] is True
    )


OBSERVED_REMOVAL_WARNING = (
    b"dpkg: warning: while removing sinter, directory '/opt' not empty so not removed\n"
)


@pytest.mark.parametrize("raw", [b"", OBSERVED_REMOVAL_WARNING])
def test_exact_shared_opt_warning_keeps_full_removal_checks(tmp_path, raw):
    receipt, source, package, pins = inner_fixture(tmp_path)
    receipt["commands"][15]["stderr"] = stream(raw)
    result = contract.validate_inner(receipt, source, package, 7, pins)
    assert result["scope"] == "installed Linux native-entry command only"


@pytest.mark.parametrize(
    "attack",
    [
        "unknown",
        "mixed",
        "different_directory",
        "different_package",
        "wrong_index",
        "wrong_argv",
        "residual_binary",
        "residual_native_entry",
        "unconfirmed_absence",
        "nonzero_exit",
        "pre_reap",
        "truncated",
    ],
)
def test_shared_opt_warning_never_substitutes_for_removal(tmp_path, attack):
    receipt, source, package, pins = inner_fixture(tmp_path)
    row = receipt["commands"][15]
    row["stderr"] = stream(OBSERVED_REMOVAL_WARNING)
    if attack == "unknown":
        row["stderr"] = stream(b"dpkg: unrelated warning\n")
    elif attack == "mixed":
        row["stderr"] = stream(OBSERVED_REMOVAL_WARNING + b"unexpected\n")
    elif attack == "different_directory":
        row["stderr"] = stream(
            OBSERVED_REMOVAL_WARNING.replace(b"'/opt'", b"'/opt/neuroforge/sinter'")
        )
    elif attack == "different_package":
        row["stderr"] = stream(
            OBSERVED_REMOVAL_WARNING.replace(b"removing sinter", b"removing another")
        )
    elif attack == "wrong_index":
        row["stderr"] = stream()
        receipt["commands"][6]["stderr"] = stream(OBSERVED_REMOVAL_WARNING)
    elif attack == "wrong_argv":
        row["argv"] = ["dpkg", "-r", "another"]
    elif attack in ("residual_binary", "residual_native_entry"):
        probe = receipt["commands"][17]
        records = json.loads(contract.stream_bytes(probe["stdout"]))
        records[0 if attack == "residual_binary" else 2]["lexists"] = True
        probe["stdout"] = stream(output(records))
    elif attack == "unconfirmed_absence":
        receipt["commands"][16]["stderr"] = stream(b"dpkg-query: access denied\n")
    elif attack == "nonzero_exit":
        row["exit_code"] = 1
    elif attack == "pre_reap":
        row["streams_complete"] = False
    else:
        row["stderr"]["truncated"] = True
    with pytest.raises(ValueError):
        contract.validate_inner(receipt, source, package, 7, pins)
