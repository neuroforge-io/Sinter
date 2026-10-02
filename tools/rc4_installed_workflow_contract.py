"""Original-tree admission for the owned installed RC4 garden workflow.

This is not a portable historical reader, a release gate, or a Python-free install
claim. The unchanged installed-workflow validator retains its own UI semantics.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path, PurePosixPath

from tools import installed_native_entry_contract as native
from tools import rc4_installed_recovery_contract as recovery

VERSION = "0.5.4rc4"
SCHEMA = "sinter-owned-rc4-installed-workflow/v1"
CONFIG = "sinter-owned-rc4-workflow-input/v1"
INNER = "sinter-owned-rc4-workflow-install/v1"
CONTROLLER = "sinter-owned-rc4-workflow-controller/v1"
HOST = "sinter-owned-rc4-workflow-host/v1"
SOURCE_FILE = "tools/rc4_installed_workflow.py"
CONTRACT_FILE = "tools/rc4_installed_workflow_contract.py"
IMAGE = "sha256:a6abf8768b5d981009b5fd68c7663ed14f87ade82ba8e5aa9be7f856f9313268"
BINARY = "/opt/neuroforge/sinter/Sinter"
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MOUNTS = native.DEFAULT_MOUNT_SPEC + (("workflow_directory", "/proof", True),)
INSTALLED_PATHS = recovery.INSTALLED_PATHS
require = recovery.require
equal = recovery.equal
regular = recovery.regular
sha = recovery.sha
record = recovery.record
full_record = recovery.record_full
full = recovery.full
read_json = recovery.json_object


def read_json_list(raw):
    value = json.loads(
        raw,
        object_pairs_hook=recovery.unique,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError("Nonfinite inspection.")
        ),
    )
    require(
        type(value) is list and len(value) == 1 and type(value[0]) is dict,
        "Exactly one complete container inspection required.",
    )
    return value


def qa_inventory(value):
    require(
        type(value) is dict
        and 2 <= len(value) <= 8192
        and {SOURCE_FILE, CONTRACT_FILE}.issubset(value),
        "Complete reviewed source inventory required.",
    )
    total = 0
    for name, row in value.items():
        require(
            type(name) is str
            and name
            and not PurePosixPath(name).is_absolute()
            and str(PurePosixPath(name)) == name
            and ".." not in PurePosixPath(name).parts
            and "\\" not in name
            and len(PurePosixPath(name).parts) <= 16
            and type(row) is dict
            and set(row) == {"bytes", "sha256"}
            and type(row["bytes"]) is int
            and 0 <= row["bytes"] <= MAX_FILE
            and type(row["sha256"]) is str
            and re.fullmatch("[0-9a-f]{64}", row["sha256"]),
            "Source identity exceeds its closed typed role/byte bounds.",
        )
        total += row["bytes"]
        require(total <= MAX_TOTAL, "Complete source exceeds its finite byte bound.")
    return value


def config(value):
    fields = {
        "schema",
        "source_commit",
        "version",
        "qa_files",
        "installer_name",
        "package_receipt_name",
        "installer_sha256",
        "package_receipt_sha256",
        "uid",
        "gid",
        "browser",
        "owner_sha256",
        "repository",
    }
    require(
        type(value) is dict and set(value) == fields, "Exact workflow inputs required."
    )
    require(
        value["schema"] == CONFIG and value["version"] == VERSION,
        "Only a final RC4 candidate is supported; source and DEV are not installed proof.",
    )
    require(
        type(value["source_commit"]) is str
        and re.fullmatch("[0-9a-f]{40}", value["source_commit"]),
        "Full commit required.",
    )
    for key in ("installer_sha256", "package_receipt_sha256", "owner_sha256"):
        require(
            type(value[key]) is str and re.fullmatch("[0-9a-f]{64}", value[key]),
            "Exact externally pinned input hash required.",
        )
    require(
        value["installer_name"] == f"Sinter-{VERSION}-linux-x64.deb"
        and value["package_receipt_name"] == f"Sinter-{VERSION}-linux-x64-test.json",
        "Canonical candidate names required.",
    )
    for key in ("uid", "gid"):
        require(
            type(value[key]) is int
            and (1 if key == "uid" else 0) <= value[key] <= 2**31 - 1,
            "Observed nonprivileged UID and numeric fictional-workspace GID required.",
        )
    qa_inventory(value["qa_files"])
    require(
        value["qa_files"][SOURCE_FILE]["sha256"] == value["owner_sha256"],
        "Owner pin differs from the source archive.",
    )
    browser = value["browser"]
    require(
        type(browser) is dict
        and set(browser) == {"path", "sha256"}
        and type(browser["path"]) is str
        and Path(browser["path"]).is_absolute()
        and type(browser["sha256"]) is str
        and re.fullmatch("[0-9a-f]{64}", browser["sha256"]),
        "One explicitly selected host Chromium identity required.",
    )
    require(
        type(value["repository"]) is str and Path(value["repository"]).is_absolute(),
        "Original Git repository path required.",
    )
    return value


def outer_argv(pins, name):
    argv = native.outer_argv(pins, name)
    insertion = argv.index("--env")
    argv[insertion:insertion] = [
        "--mount",
        "type=bind,src=" + pins["workflow_directory"] + ",dst=/proof",
    ]
    index = argv.index(pins["image_id"])
    return argv[: index + 1] + ["python3", "-B", "/source/" + SOURCE_FILE, "inner"]


def exec_argv(identifier, inputs):
    config(inputs)
    require(
        type(identifier) is str and re.fullmatch("[0-9a-f]{64}", identifier),
        "Only the actually created container may own a controller.",
    )
    return [
        "docker",
        "exec",
        "--user",
        f"{inputs['uid']}:{inputs['gid']}",
        identifier,
        "python3",
        "-B",
        "/source/" + SOURCE_FILE,
        "controller",
    ]


def host_argv(root, inputs, python):
    return [
        str(python),
        "-B",
        str(root / "source" / SOURCE_FILE),
        "host",
        "--proof-root",
        str(root),
        "--chromium",
        inputs["browser"]["path"],
    ]


def streams(row, folder, names=("stdout", "stderr"), *, directory=False):
    """Read complete original sidecars, even when a diagnostic is nonempty."""
    from tools.installed_native_menu import stream_record

    for name in names:
        path = (
            folder / name if directory else folder.with_name(folder.name + "." + name)
        )
        raw = regular(path, MAX_FILE)
        require(
            equal(row[name], stream_record(io.BytesIO(raw))),
            "Complete original stream differs from its post-reap record.",
        )


def command(row, argv, *, status=0):
    native.stopped(row, expected_exit=status)
    require(
        row.get("argv") == list(map(str, argv)) and row["streams_complete"] is True,
        "Fixed command argv or complete post-reap ownership differs.",
    )
    native.stream_bytes(row["stdout"], complete=False)
    native.stream_bytes(row["stderr"], complete=False)
    if "passed" in row:
        require(
            row["passed"] is (status == 0), "Actual command status projection differs."
        )


def source_commands(root, inputs):
    """Bind retained Git command ownership to each actual original archive stream."""
    value = read_json(regular(root / "raw/source-commands.json", 2 * 1024 * 1024))
    require(
        set(value) == {"commands"}
        and type(value["commands"]) is list
        and len(value["commands"]) == 2,
        "Exactly two actual Git archive commands required.",
    )
    for fmt, name, row in zip(
        ("tar", "zip"),
        ("committed-source.tar", f"sinter-{VERSION}-source.zip"),
        value["commands"],
        strict=True,
    ):
        command(
            row,
            [
                "git",
                "-C",
                inputs["repository"],
                "archive",
                "--format=" + fmt,
                inputs["source_commit"],
            ],
        )
        streams(row, root / "raw" / ("source-" + fmt))
        native.quiet(row["stderr"])
        require(
            regular(root / "raw" / ("source-" + fmt + ".stdout"), MAX_FILE)
            == regular(root / "repository" / name, MAX_FILE),
            "Original Git stdout and source archive bytes differ.",
        )
        for stream in ("stdout", "stderr"):
            require(
                row.get(stream + "_file")
                == str(root / "raw" / ("source-" + fmt + "." + stream)),
                "Original Git stream filename differs.",
            )


def docker_client(value, root):
    client = value["docker_client"]
    require(
        type(client) is dict
        and set(client) == {"path", "sha256", "version", "sha256_after"}
        and type(client["path"]) is str
        and Path(client["path"]).is_absolute()
        and type(client["sha256"]) is str
        and re.fullmatch("[0-9a-f]{64}", client["sha256"])
        and client["sha256_after"] == client["sha256"]
        and sha(regular(Path(client["path"]), MAX_FILE)) == client["sha256"],
        "Actual original Docker client changed.",
    )
    command(client["version"], ["docker", "--version"])
    streams(client["version"], root / "raw/client-version")
    native.quiet(client["version"]["stderr"])
    version = native.stream_bytes(client["version"]["stdout"])
    require(
        version.startswith(b"Docker version ")
        and version.endswith(b"\n")
        and len(version) < 200,
        "Actual Docker version output differs.",
    )
    rows = value["client_commands"]
    require(
        type(rows) is list and len(rows) == 8 and equal(rows[0], client["version"]),
        "Complete post-reap Docker client ledger required.",
    )
    for row, projection in zip(rows[1:], value["commands"], strict=True):
        command(row, projection["argv"], status=projection["exit_code"])
        require(
            equal(
                {
                    "role": projection["role"],
                    "argv": row["argv"],
                    "exit_code": row["exit_code"],
                    "stdout": row["stdout"],
                    "stderr": row["stderr"],
                    "reaped": row["streams_complete"],
                },
                projection,
            ),
            "Lifecycle projection differs from actual client ownership.",
        )
        for name in ("stdout", "stderr"):
            require(
                row.get(name + "_file")
                == str(root / "raw" / (projection["role"] + "." + name)),
                "Original Docker sidecar path differs.",
            )


def install_commands(value, inputs, root):
    from tools.installed_native_menu import FILESYSTEM_PROBE

    rows = value["commands"]
    require(
        type(rows) is list and len(rows) == 12,
        "Complete fixed install command sequence required.",
    )
    expected = [
        ["dpkg-query", "-W", "-f=${Status}", "sinter"],
        *[
            ["dpkg-deb", "-f", "/candidate/" + inputs["installer_name"], field]
            for field in ("Package", "Architecture", "Version")
        ],
        ["dpkg-deb", "--fsys-tarfile", "/candidate/" + inputs["installer_name"]],
        ["dpkg", "-i", "/candidate/" + inputs["installer_name"]],
        ["dpkg-query", "-W", "-f=${Status}\n${Version}\n", "sinter"],
        [BINARY, "--self-test", "/out/evidence/selftest.json"],
        [BINARY, "operations", "--format", "json"],
        ["dpkg", "-r", "sinter"],
        ["dpkg-query", "-W", "-f=${Status}", "sinter"],
        rows[-1]["argv"],
    ]
    require(
        type(expected[-1]) is list
        and len(expected[-1]) == 7
        and type(expected[-1][0]) is str
        and expected[-1][0].startswith("/")
        and expected[-1][1:] == ["-B", "-c", FILESYSTEM_PROBE, *INSTALLED_PATHS],
        "Independent filesystem query differs.",
    )
    for index, (row, argv) in enumerate(zip(rows, expected)):
        status = (
            1
            if index == 0
            or index == 10
            and value["removal"]["package_state"] == "absent"
            else 0
        )
        command(row, argv, status=status)
        if index != 4:
            streams(row, root / "out/evidence" / f"command-{index:02d}")
        if index not in (0, 9, 10):
            native.quiet(row["stderr"])
    require(
        native.stream_bytes(rows[0]["stdout"]) == b""
        and native.stream_bytes(rows[0]["stderr"]) == native.ABSENT,
        "Actual initial package absence is not proven.",
    )
    require(
        rows[6]["stdout"]["bytes"] == len(b"install ok installed\n0.5.4~rc4\n")
        and native.stream_bytes(rows[6]["stdout"])
        == b"install ok installed\n0.5.4~rc4\n",
        "Actual installed dpkg version differs.",
    )
    require(
        value["package_control_indexes"] == [1, 2, 3]
        and value["package_payload_command_index"] == 4
        and equal(value["selftest_command"], rows[7]),
        "Command roles cannot be substituted by summary records.",
    )


def app_rows(value, inputs, notice, folder):
    require(
        type(value) is dict
        and set(value)
        == {
            "schema",
            "uid",
            "gid",
            "pid",
            "argv",
            "cmdline",
            "rows",
            "resources",
            "failure",
            "cleanup_errors",
            "cleanup_attempts",
            "acquisition_cleanup",
        }
        and value["schema"] == CONTROLLER,
        "Complete controller observations required.",
    )
    require(
        value["uid"] == inputs["uid"]
        and type(value["uid"]) is int
        and value["gid"] == inputs["gid"]
        and type(value["gid"]) is int,
        "Actual controller UID/GID differs from its fixed Docker exec.",
    )
    expected_controller = ["python3", "-B", "/source/" + SOURCE_FILE, "controller"]
    require(
        value["argv"] == expected_controller
        and full(value["cmdline"], 4096).split(b"\0")[:-1]
        == [part.encode() for part in expected_controller],
        "Actual continuing controller command differs.",
    )
    require(
        type(value["pid"]) is int
        and value["pid"] > 1
        and value["failure"] is None
        and value["cleanup_errors"] == []
        and value["acquisition_cleanup"] == [],
        "Controller work/cleanup failure refuses admission.",
    )
    rows = value["rows"]
    require(
        type(rows) is list and len(rows) == 2,
        "Exactly two installed app lifetimes required.",
    )
    pids, ports = set(), set()
    for index, row in enumerate(rows, 1):
        require(
            type(row) is dict
            and set(row)
            == {
                "run",
                "pid",
                "argv",
                "stop_method",
                "forced_cleanup",
                "sigterm_sent",
                "cmdline",
                "opener",
                "port",
                "exit_code",
                "owned_group_remaining",
                "stdout",
                "stderr",
                "streams_complete",
                "port_closed",
                "returncode",
                "cleanup_observation",
            }
            and row["run"] == index
            and type(row["run"]) is int
            and type(row["pid"]) is int
            and row["pid"] > 1
            and row["pid"] != value["pid"],
            "App/controller roles alias in the same container namespace.",
        )
        pids.add(row["pid"])
        argv = [BINARY, "app", "--mode", "browser", "--directory", "/proof/data"]
        command(row, argv)
        require(
            equal(
                read_json(
                    regular(
                        folder / "process" / f"run-{index}" / "observation.json",
                        MAX_FILE,
                    )
                ),
                row,
            ),
            "Original app observation differs from controller row.",
        )
        require(
            equal(
                row["cleanup_observation"],
                {
                    "errors": [],
                    "attempts": [
                        {"resource": name, "succeeded": True}
                        for name in (
                            "app stop",
                            "stdout close",
                            "stderr close",
                            "stdout retention",
                            "stderr retention",
                            "listener observation",
                        )
                    ],
                },
            ),
            "Complete independent app reap observations required.",
        )
        require(
            full(row["cmdline"], 4096).split(b"\0")[:-1]
            == [part.encode() for part in argv],
            "Actual app cmdline differs.",
        )
        require(
            row["stop_method"] == "interface_quit"
            and row["sigterm_sent"] is False
            and row["port_closed"] is True
            and type(row["returncode"]) is int
            and row["returncode"] == row["exit_code"],
            "Only observed normal UI quit may qualify.",
        )
        opener = full(row["opener"], 1024).decode("ascii").strip()
        from tools.installed_workflow_browser import inner_address

        _host, port = inner_address(opener)
        require(
            type(row["port"]) is int and row["port"] == port,
            "Opener and actual listener identity differ.",
        )
        ports.add(port)
        streams(row, folder / "process" / f"run-{index}", directory=True)
        require(
            regular(folder / "process" / f"run-{index}" / "stdout", MAX_FILE) == b""
            and regular(folder / "process" / f"run-{index}" / "stderr", MAX_FILE)
            == notice,
            "Installed app emitted unexpected actual diagnostics.",
        )
    require(
        equal(
            value["resources"],
            {
                "inner_thread_closed": True,
                "inner_requests_closed": True,
                "inner_socket_absent": True,
                "app_groups_absent": True,
            },
        ),
        "Independent stopped controller resources incomplete.",
    )
    require(
        equal(
            value["cleanup_attempts"],
            [
                {"resource": name, "succeeded": True}
                for name in (
                    "app final reap",
                    "relay shutdown",
                    "relay close",
                    "relay join",
                    "relay socket removal",
                    "controller final observation",
                )
            ],
        ),
        "Every independent controller cleanup attempt required.",
    )
    return pids, ports


def host_resources(value, folder):
    require(
        type(value) is dict
        and set(value)
        == {
            "schema",
            "failure",
            "cleanup_errors",
            "cleanup_attempts",
            "session",
            "relay",
            "chrome",
            "driver",
            "browser_pids",
            "owned_pids_gone",
        }
        and value["schema"] == HOST,
        "Complete host browser observations required.",
    )
    require(
        value["failure"] is None and value["cleanup_errors"] == [],
        "Host UI/cleanup failure refuses admission.",
    )
    session = value["session"]
    require(
        type(session) is dict
        and set(session)
        == {
            "phase",
            "driver_closed",
            "browser_closed",
            "contexts_closed",
            "cleanup_errors",
            "cleanup_attempts",
        }
        and session["phase"] == "core-workflow"
        and session["driver_closed"] is True
        and session["browser_closed"] is True
        and session["contexts_closed"] is True
        and session["cleanup_errors"] == [],
        "Accepted owned browser session did not close all resources.",
    )
    attempts = session["cleanup_attempts"]
    require(
        type(attempts) is list
        and 4 <= len(attempts) <= 64
        and all(
            type(row) is dict
            and set(row) == {"resource", "succeeded"}
            and row["succeeded"] is True
            and row["resource"]
            in {
                "context",
                "context retry",
                "browser",
                "browser final",
                "driver",
            }
            for row in attempts
        )
        and all(
            any(row["resource"] == name for row in attempts)
            for name in ("context", "browser", "browser final", "driver")
        ),
        "Complete accepted browser-session close ledger required.",
    )
    require(
        equal(
            value["relay"],
            {
                "stopped": True,
                "idle": True,
                "port_closed": True,
                "model_routes": 0,
                "errors": 0,
            },
        )
        and all(type(value["relay"][key]) is int for key in ("model_routes", "errors")),
        "Actual host relay ownership or bounded model-route observation differs.",
    )
    chrome = value["chrome"]
    native.stopped(chrome)
    require(
        chrome["streams_complete"] is True
        and chrome["debug_port_closed"] is True
        and chrome["sigterm_sent"] is False,
        "Chromium did not close normally.",
    )
    require(
        full(chrome["cmdline"], 8192).split(b"\0")[:-1]
        == [part.encode() for part in chrome["argv"]],
        "Actual Chromium cmdline differs.",
    )
    streams(chrome, folder / "chrome", directory=True)
    driver = value["driver"]
    require(
        type(driver) is dict
        and set(driver) == {"pid", "path", "sha256", "cmdline", "gone"}
        and type(driver["pid"]) is int
        and driver["pid"] > 1
        and driver["gone"] is True
        and type(driver["path"]) is str
        and Path(driver["path"]).is_absolute()
        and Path(driver["path"]).name == "node"
        and type(driver["sha256"]) is str
        and re.fullmatch("[0-9a-f]{64}", driver["sha256"]),
        "Actual managed driver ownership missing.",
    )
    full(driver["cmdline"], 4096)
    require(
        full(driver["cmdline"], 4096).split(b"\0")[:-1]
        == [
            driver["path"].encode(),
            str(Path(driver["path"]).parent / "package/cli.js").encode(),
            b"run-driver",
        ],
        "Actual Node driver cmdline differs.",
    )
    pids = value["browser_pids"]
    require(
        type(pids) is list
        and pids
        and all(type(pid) is int and pid > 1 for pid in pids)
        and len(set(pids)) == len(pids)
        and chrome["pid"] in pids
        and driver["pid"] not in pids
        and value["owned_pids_gone"] is True,
        "Concurrent host browser/Node owners alias or survive.",
    )
    require(
        equal(
            value["cleanup_attempts"],
            [
                {"resource": name, "succeeded": True}
                for name in (
                    "browser close request",
                    "chrome reap",
                    "chrome stdout",
                    "chrome stderr",
                    "chrome stdout close",
                    "chrome stderr close",
                    "relay shutdown",
                    "relay close",
                    "relay join",
                    "host resource observation",
                    "installed cleanup request",
                )
            ],
        ),
        "All independent host cleanup attempts must succeed.",
    )
    return set(pids) | {driver["pid"]}


def installed_runtime(root, inner, source_bytes, inputs):
    """Use actual installed self-test, operations and raw runtime observations."""
    from tools.installed_menu_browser import browser_notice
    from tools.installed_workflow_qualification import validate_operations_catalog

    require(
        equal(
            read_json(regular(root / "out/evidence/selftest.json", 2 * 1024 * 1024)),
            inner["selftest"],
        ),
        "Original installed self-test bytes differ.",
    )
    rows = inner["commands"]
    operations = regular(root / "out/evidence/operations.json", 2 * 1024 * 1024)
    require(
        operations == regular(root / "out/evidence/operations.stdout", 2 * 1024 * 1024)
        and operations == native.stream_bytes(rows[8]["stdout"]),
        "Actual installed catalogue output differs from retained bytes.",
    )
    catalog = read_json(operations)
    validate_operations_catalog(catalog, source_bytes, VERSION)
    runtime = inner["runtime"]
    require(
        type(runtime) is dict
        and set(runtime) == {"os_release", "libc"}
        and type(runtime["os_release"]) is str
        and runtime["libc"] == ["glibc", "2.35"],
        "Original installed runtime observation differs.",
    )
    release = dict(
        line.split("=", 1) for line in runtime["os_release"].splitlines() if "=" in line
    )
    require(
        release["ID"].strip('"') == "ubuntu"
        and release["VERSION_ID"].strip('"') == "22.04",
        "Observed original Ubuntu baseline differs.",
    )
    ready = read_json(regular(root / "runtime/ready.json", 2 * 1024 * 1024))
    require(
        equal(
            ready,
            {
                "phase": "ready",
                "package": "sinter",
                "architecture": "amd64",
                "version": VERSION,
                "package_version": "0.5.4~rc4",
                "installed_package_version": "0.5.4~rc4",
                "binary_sha256": inner["package"]["binary_sha256"],
                "web": {
                    name: sha(raw)
                    for name, raw in source_bytes.items()
                    if name.startswith("src/sinter/web/")
                },
                "os_release": {"ID": "ubuntu", "VERSION_ID": "22.04"},
                "libc": runtime["libc"],
                "frozen_test": inner["selftest"],
                "operations_catalog": catalog,
                "notice_base64": full_record(
                    browser_notice(source_bytes["src/sinter/desktop.py"])
                )["base64"],
            },
        ),
        "Ready projection differs from original installed runtime evidence.",
    )
    require(
        equal(
            read_json(regular(root / "runtime/remove.json", 1024)),
            {"action": "remove", "exec_reaped": True, "host_reaped": True},
        ),
        "Original post-reap removal acknowledgement differs.",
    )
    state = read_json(regular(root / "runtime/state.json", 2 * 1024 * 1024))
    require(
        equal(
            state,
            {
                **ready,
                "phase": "stopped",
                "run": 2,
                "exit_code": 0,
                "port_closed": True,
            },
        ),
        "Actual second app lifetime did not stop normally.",
    )


def verify_original(args, *, pending=False):
    """Recheck actual original paths and pinned raw evidence; never install/run UI."""
    from tools import installed_native_container as owner
    from tools import rc4_installed_recovery as installed
    from tools import rc4_installed_workflow as producer
    from tools.installed_menu_browser import browser_notice
    from tools.installed_workflow_qualification import (
        source_operations,
        verify_installed_workflow,
    )

    root = args.proof_root.resolve(strict=True)
    inputs = config(
        read_json(regular(root / "candidate/workflow-input.json", 2 * 1024 * 1024))
    )
    qa = installed.source_records(producer.ROOT)
    require(
        equal(inputs["qa_files"], qa)
        and inputs["owner_sha256"] == args.owner_sha256
        and inputs["source_commit"] == args.source_commit
        and inputs["installer_sha256"] == args.installer_sha256
        and inputs["package_receipt_sha256"] == args.package_receipt_sha256,
        "Original-tree external source/tool/package pins differ.",
    )
    source = installed.source_binding(
        regular(root / "repository/committed-source.tar", MAX_TOTAL),
        args.source_commit,
        qa,
        "candidate",
    )
    source_bytes = {name: regular(root / "source" / name, MAX_FILE) for name in qa}
    require(
        equal(installed.source_records(root / "source"), qa),
        "Staged complete source changed.",
    )
    zip_path = root / "repository" / f"sinter-{VERSION}-source.zip"
    producer.validate_zip(regular(zip_path, MAX_FILE), args.source_commit, qa)
    source_commands(root, inputs)
    receipt_path = root / "candidate" / inputs["package_receipt_name"]
    package_receipt = read_json(regular(receipt_path, 2 * 1024 * 1024))
    require(
        sha(regular(receipt_path, MAX_FILE)) == args.package_receipt_sha256
        and sha(regular(root / "candidate" / inputs["installer_name"], MAX_FILE))
        == args.installer_sha256,
        "Actual candidate bytes differ.",
    )
    outer = read_json(regular(root / "workflow-owner.json", 16 * 1024 * 1024))
    require(
        set(outer)
        == {
            "schema",
            "owner_sha256",
            "source",
            "pins",
            "commands",
            "client_commands",
            "host_python",
            "failure",
            "cleanup_errors",
            "cleanup",
            "parallel_failures",
            "cleanup_attempts",
            "browser",
            "passed",
            "docker_client",
            "host_command",
            "exec_command",
            "qa_files_after",
            *([] if pending else ["verification"]),
        }
        and outer["schema"] == SCHEMA
        and outer["owner_sha256"] == args.owner_sha256
        and equal(outer["source"], source)
        and outer["failure"] is None
        and outer["cleanup_errors"] == []
        and outer["cleanup"] == []
        and outer["parallel_failures"] == []
        and equal(outer["qa_files_after"], qa),
        "Outer failure/source identity differs.",
    )
    require(
        equal(
            outer["cleanup_attempts"],
            [
                {"resource": name, "succeeded": True}
                for name in (
                    "container removal",
                    "independent container absence",
                    "attach thread",
                    "controller thread",
                    "Docker identity",
                    "browser identity",
                    "post-reap browser cache",
                    "browser temp observation",
                    "source conservation",
                )
            ],
        ),
        "Every independent outer cleanup/observation required.",
    )
    require(
        outer["passed"] is (not pending),
        "Only complete installed owner evidence qualifies.",
    )
    pins = owner.pins_for(
        root,
        args.owner_sha256,
        args.source_commit,
        inputs["installer_name"],
        inputs["package_receipt_name"],
    )
    pins["workflow_directory"] = str(root / "runtime")
    lifecycle = native.validate_lifecycle(outer["commands"], pins, outer_argv, MOUNTS)
    require(lifecycle["start_stdout"] == b"", "Install owner stdout must be quiet.")
    require(outer["pins"] == pins, "Raw original owner mount labels differ.")
    docker_client(outer, root)
    for row in outer["commands"]:
        streams(row, root / "raw" / row["role"])
    command(outer["exec_command"], exec_argv(lifecycle["container_id"], inputs))
    streams(outer["exec_command"], root / "raw/controller")
    command(outer["host_command"], host_argv(root, inputs, outer["host_python"]))
    streams(outer["host_command"], root / "raw/host")
    require(
        native.stream_bytes(outer["exec_command"]["stdout"]) == b""
        and native.stream_bytes(outer["exec_command"]["stderr"]) == b""
        and native.stream_bytes(outer["host_command"]["stdout"]) == b""
        and native.stream_bytes(outer["host_command"]["stderr"]) == b"",
        "Unexpected controller/collector diagnostics cannot be hidden.",
    )
    inner = read_json(regular(root / "out/evidence/inner.json", 16 * 1024 * 1024))
    require(
        set(inner)
        == {
            "schema",
            "source",
            "commands",
            "failure",
            "cleanup_errors",
            "passed",
            "container",
            "package",
            "package_control_indexes",
            "package_payload_command_index",
            "installed_entries",
            "installed_binary",
            "installed_package",
            "diagnostic",
            "diagnostic_process",
            "diagnostic_observation",
            "selftest_command",
            "selftest",
            "runtime",
            "installed_entries_after",
            "installed_binary_after",
            "removal_command",
            "removal",
            "absence",
            "qa_files_after",
        }
        and inner["schema"] == INNER
        and inner["failure"] is None
        and inner["cleanup_errors"] == []
        and equal(inner["source"], source)
        and equal(inner["qa_files_after"], qa)
        and inner["passed"] is True,
        "Actual install owner failed or changed source.",
    )
    require(
        equal(
            inner["container"],
            {
                "effective_uid": 0,
                "pid": 1,
                "interfaces": ["lo"],
                "inherited_display": False,
            },
        ),
        "Fixed installed owner is not isolated PID1/root with loopback only.",
    )
    recovery.validate_package_payload(root, inner, inputs, source)
    install_commands(inner, inputs, root)
    installed_runtime(root, inner, source_bytes, inputs)
    package = inner["package"]
    from tools.package_native import linux_desktop_entries

    require(
        equal(
            package["entries"],
            {
                name: full_record(text.encode("utf-8"))
                for name, text in linux_desktop_entries(True).items()
            },
        ),
        "Actual menu payload differs from the exact final source.",
    )
    require(
        package["installer_sha256"] == args.installer_sha256
        and package["receipt_sha256"] == args.package_receipt_sha256,
        "Actual installed package binding differs.",
    )
    require(
        equal(inner["installed_binary"], inner["installed_binary_after"])
        and equal(
            inner["installed_binary"],
            {
                "bytes": package["binary_bytes"],
                "sha256": package["binary_sha256"],
                "executable": True,
            },
        )
        and equal(inner["installed_entries"], package["entries"])
        and equal(inner["installed_entries_after"], package["entries"]),
        "Actual installed executable/menu bytes changed.",
    )
    require(
        equal(inner["selftest"], package_receipt["installed_test"])
        and inner["selftest"]["frozen"] is True
        and inner["selftest"]["version"] == VERSION,
        "Installed frozen self-test differs.",
    )
    native.diagnostic(
        inner["diagnostic_process"],
        inner["diagnostic"],
        VERSION,
        inner["diagnostic_observation"],
    )
    for name in ("stdout", "stderr"):
        require(
            regular(root / "out/evidence" / ("diagnose." + name), MAX_FILE)
            == native.stream_bytes(inner["diagnostic_observation"][name]["record"]),
            "Complete actual frozen diagnostic sidecar differs.",
        )
    rows = inner["commands"]
    remove = inner["removal_command"]
    recovery.validate_package_removal(
        remove["exit_code"], remove, inner["removal"], rows
    )
    recovery.validate_absence(inner["absence"], rows)
    controller = read_json(regular(root / "runtime/controller.json", 16 * 1024 * 1024))
    app_rows(
        controller,
        inputs,
        browser_notice(source_bytes["src/sinter/desktop.py"]),
        root / "runtime",
    )
    host = read_json(regular(root / "out/host.json", 16 * 1024 * 1024))
    host_pids = host_resources(host, root / "out")
    require(
        host["chrome"]["argv"]
        == producer.chrome_argv(
            root / "client/browser-home", inputs["browser"]["path"]
        ),
        "Actual Chrome flags/profile differ from the pinned private owner.",
    )
    require(
        outer["host_command"]["pid"] not in host_pids,
        "Host collector aliases its concurrent Chrome/Node children.",
    )
    require(
        outer["exec_command"]["pid"] != outer["host_command"]["pid"]
        and outer["exec_command"]["pid"] not in host_pids,
        "Concurrent host controller client and collector alias.",
    )
    browser = outer["browser"]
    require(
        type(browser) is dict
        and set(browser)
        == {
            "path",
            "sha256",
            "sha256_after",
            "temporary_empty_before",
            "temporary_empty_after",
            "cleanup",
        }
        and browser["path"] == inputs["browser"]["path"]
        and browser["sha256"] == inputs["browser"]["sha256"]
        and browser["sha256_after"] == browser["sha256"]
        and browser["temporary_empty_before"] is True
        and browser["temporary_empty_after"] is True
        and not any((root / "t").iterdir()),
        "Actual host browser/temp boundary changed.",
    )
    recovery.validate_browser_temp(browser["cleanup"])
    require(
        sha(regular(Path(host["driver"]["path"]), 512 * 1024 * 1024))
        == host["driver"]["sha256"],
        "Original managed Node executable changed.",
    )
    verify_installed_workflow(
        root / "out/workflow",
        VERSION,
        args.source_commit,
        {
            zip_path.name: sha(regular(zip_path, MAX_FILE)),
            inputs["package_receipt_name"]: args.package_receipt_sha256,
        },
        source_bytes,
        package_receipt,
        package["binary_sha256"],
    )
    producer.validate_inventory(root, inputs)
    result = {
        "schema": "sinter-owned-rc4-installed-workflow-admission/v1",
        "source_commit": args.source_commit,
        "version": VERSION,
        "installer_sha256": args.installer_sha256,
        "package_receipt_sha256": args.package_receipt_sha256,
        "binary_sha256": package["binary_sha256"],
        "container_id": lifecycle["container_id"],
        "app_lifetimes": 2,
        "operations_catalogue": len(source_operations(source_bytes)),
        "named_checks": 22,
        "workflow_roles": 13,
        "release_qualified": False,
        "cold_python_free_install": False,
        "historical_semantic_replay": False,
    }
    if not pending:
        require(
            equal(outer["verification"], result),
            "Original completed admission differs from raw revalidation.",
        )
    return result
