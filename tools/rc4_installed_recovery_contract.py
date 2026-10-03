"""Closed installed recovery evidence, separate from source/prior/release policies."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTER = "sinter-rc4-installed-recovery-owner/v1"
INNER = "sinter-rc4-installed-recovery-inner/v1"
SEED = "sinter-installed-recovery-fictional-seed/v1"
RPC_REQUEST = "sinter-installed-recovery-observation-request/v1"
RPC_RESPONSE = "sinter-installed-recovery-observation-response/v1"
OPERATIONS = {
    "campaign": frozenset({"snapshot"}),
    "scoped": frozenset({"snapshot", "protocol"}),
}
INSTALLED_PATHS = [
    "/opt/neuroforge/sinter/Sinter",
    "/usr/share/applications/sinter.desktop",
    "/usr/share/applications/sinter-native.desktop",
]
REMOVAL_NOTICE = (
    b"dpkg: warning: while removing sinter, directory '/opt' not empty so not removed\n"
)
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 40 * 1024 * 1024
MAX_PROFILE_ENTRIES = 512
MAX_PROFILE_DEPTH = 8


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def equal(a, b):
    return canonical(a) == canonical(b)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, "Duplicate evidence field.")
        result[k] = v
    return result


def json_object(raw):
    value = json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda v: (_ for _ in ()).throw(
            ValueError("Nonfinite evidence.")
        ),
    )
    require(type(value) is dict, "Require one JSON object.")
    return value


def regular(path, limit):
    path = Path(path)
    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode) and before.st_size <= limit,
        "Use a bounded regular file.",
    )
    with path.open("rb") as stream:
        observed = os.fstat(stream.fileno())
        require(
            (before.st_dev, before.st_ino) == (observed.st_dev, observed.st_ino)
            and stat.S_ISREG(observed.st_mode),
            "File changed while opening.",
        )
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "Read exceeds finite bound.")
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def record(raw):
    return {"bytes": len(raw), "sha256": sha(raw)}


def record_full(raw):
    return {**record(raw), "base64": base64.b64encode(raw).decode("ascii")}


def full(row, limit=MAX_FILE):
    require(
        type(row) is dict
        and set(row) == {"bytes", "sha256", "base64"}
        and type(row["bytes"]) is int
        and 0 <= row["bytes"] <= limit
        and type(row["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
        and type(row["base64"]) is str,
        "Complete byte evidence differs.",
    )
    raw = base64.b64decode(row["base64"], validate=True)
    require(equal(row, record_full(raw)), "Byte count/hash/sample differs.")
    return raw


def validate_request(request, profile, session, sequence):
    require(
        type(request) is dict
        and set(request) == {"schema", "profile", "session", "sequence", "operation"}
        and request["schema"] == RPC_REQUEST
        and type(request["profile"]) is str
        and request["profile"] == profile
        and profile in OPERATIONS
        and type(request["session"]) is str
        and request["session"] == session
        and type(request["sequence"]) is int
        and request["sequence"] == sequence
        and 1 <= sequence <= 64
        and type(request["operation"]) is str
        and request["operation"] in OPERATIONS[profile],
        "Fixed observation request refused.",
    )


def validate_rpc(request, response):
    require(type(request) is dict, "Require the original observation request.")
    validate_request(
        request, request.get("profile"), request.get("session"), request.get("sequence")
    )
    require(
        type(response) is dict
        and set(response) == set(request) | {"result", "error"}
        and response["schema"] == RPC_RESPONSE
        and equal(
            {
                k: v
                for k, v in response.items()
                if k not in {"schema", "result", "error"}
            },
            {k: v for k, v in request.items() if k != "schema"},
        )
        and (
            response["error"] is None
            or (type(response["error"]) is str and len(response["error"]) <= 1024)
        )
        and (
            (response["error"] is None and type(response["result"]) is dict)
            or (response["error"] is not None and response["result"] is None)
        ),
        "Observation response identity/result refused.",
    )


def validate_config(config):
    require(
        type(config) is dict
        and set(config)
        == {
            "source_commit",
            "version",
            "mode",
            "installer_name",
            "package_receipt_name",
            "installer_sha256",
            "package_receipt_sha256",
            "session",
            "qa_files",
            "browser",
        }
        and type(config["source_commit"]) is str
        and re.fullmatch(r"[0-9a-f]{40}", config["source_commit"])
        and type(config["session"]) is str
        and re.fullmatch(r"[0-9a-f]{32}", config["session"])
        and type(config["qa_files"]) is dict
        and config["qa_files"]
        and type(config["mode"]) is str
        and config["mode"] in {"development", "candidate"}
        and type(config["version"]) is str
        and config["version"]
        == ("0.5.4rc4.dev0" if config["mode"] == "development" else "0.5.4rc4")
        and all(
            type(config[n]) is str and re.fullmatch(r"[0-9a-f]{64}", config[n])
            for n in ("installer_sha256", "package_receipt_sha256")
        )
        and type(config["package_receipt_name"]) is str
        and config["package_receipt_name"]
        == "Sinter-" + config["version"] + "-linux-x64-test.json"
        and type(config["installer_name"]) is str
        and config["installer_name"]
        == "Sinter-" + config["version"] + "-linux-x64.deb",
        "Closed reviewed installed recovery inputs differ.",
    )
    browser = config["browser"]
    require(
        type(browser) is dict
        and set(browser) == {"path", "sha256"}
        and type(browser["path"]) is str
        and browser["path"].startswith("/")
        and type(browser["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", browser["sha256"]),
        "Explicit headless launch pin unavailable.",
    )


def admitted_create(row, raw):
    """Assign cleanup ownership only after the complete successful create record."""
    from tools.installed_native_entry_contract import stream_bytes

    require(
        type(row) is dict
        and row.get("role") == "create"
        and type(row.get("exit_code")) is int
        and row["exit_code"] == 0
        and row.get("reaped") is True
        and stream_bytes(row["stderr"]) == b""
        and stream_bytes(row["stdout"]) == raw
        and type(raw) is bytes
        and re.fullmatch(rb"[0-9a-f]{64}\n", raw),
        "Create identity differs; no cleanup ID admitted.",
    )
    return raw[:-1].decode("ascii")


def validate_package_removal(code, row, state, commands):
    from tools.installed_native_entry_contract import stopped, stream_bytes

    stopped(row)
    require(
        type(code) is int
        and code == 0
        and type(row.get("exit_code")) is int
        and row["exit_code"] == 0
        and row.get("streams_complete") is True
        and row.get("argv") == ["dpkg", "-r", "sinter"],
        "Package removal process refused.",
    )
    require(
        type(commands) is list
        and 1 <= len(commands) <= 256
        and all(type(entry) is dict for entry in commands),
        "Require the bounded actual inner command inventory.",
    )
    matches = [
        entry for entry in commands if entry.get("argv") == ["dpkg", "-r", "sinter"]
    ]
    require(
        len(matches) == 1 and equal(matches[0], row),
        "Removal process differs from its unique actual inner command.",
    )
    # Dpkg can report progress; validate its complete bytes without requiring silence.
    stream_bytes(row["stdout"])
    raw = stream_bytes(row["stderr"])
    require(raw in (b"", REMOVAL_NOTICE), "Unexpected package removal diagnostic.")
    require(
        type(state) is dict
        and set(state) == {"package_state", "remaining_paths", "passed"}
        and state["package_state"] in {"absent", "deinstall ok config-files"}
        and state["remaining_paths"] == []
        and state["passed"] is True,
        "Both menu entries and Sinter executable must actually be absent.",
    )


def validate_processes(data, profile, binding, package, session):
    from tools.installed_menu_browser import browser_notice
    from tools.rc4_recovery_worker import protected
    from tools.rc4_scoped_recovery_contract import seed_projection

    seed = json_object(data["seed.json"])
    require(
        set(seed)
        == {"schema", "source_commit", "source_files", "seed", "instrumentation"}
        and seed["schema"] == SEED
        and seed["source_commit"] == binding["commit"]
        and equal(
            seed["source_files"],
            {n: r for n, r in binding["files"].items() if n.startswith("src/")},
        )
        and seed["instrumentation"]
        == "source-prepared fictional disabled watch; scheduler unchanged",
        "Fictional seed provenance differs; source worker markers refuse.",
    )
    original = seed["seed"]["snapshot"]
    preferences = original["preferences"]
    require(
        equal(preferences, seed["seed"]["settings"])
        and preferences["model"] == "fictional-recovery-model"
        and preferences["provider"] == "openai-compatible"
        and seed["seed"]["connection"]["api_key"] == ""
        and seed["seed"]["connection"]["inherit_key"] is False
        and seed["seed"]["public_settings"]["environment_override"] is False
        and seed["seed"]["public_settings"]["has_session_key"] is False,
        "Explicit fictional model/settings isolation differs.",
    )

    def projection(value):
        return (
            protected(value)
            if profile == "campaign"
            else seed_projection(value, original)
        )

    processes = json_object(data["processes.json"])
    require(
        set(processes) == {"rows", "failure", "closed", "resources"}
        and processes["closed"] is True
        and processes["failure"] is None
        and equal(
            processes["resources"],
            {
                "inner_thread_closed": True,
                "inner_requests_closed": True,
                "inner_socket_absent": True,
            },
        )
        and type(processes["rows"]) is list
        and len(processes["rows"]) == (6 if profile == "campaign" else 4),
        "Mandatory installed process profile is incomplete.",
    )
    pids = set()
    notice = browser_notice((ROOT / "src/sinter/desktop.py").read_bytes())
    for index, row in enumerate(processes["rows"], 1):
        require(
            type(row) is dict
            and set(row)
            == {
                "run",
                "pid",
                "argv",
                "binary_sha256",
                "workspace",
                "stop_method",
                "forced_cleanup",
                "sigterm_sent",
                "opener",
                "cmdline",
                "port",
                "exit_code",
                "owned_group_remaining",
                "stdout",
                "stderr",
                "returncode",
                "port_closed",
                "persistent_snapshot",
            },
            "Installed process fields differ; worker markers refuse.",
        )
        require(
            type(row["exit_code"]) is int
            and row["exit_code"] == row["returncode"]
            and type(row["sigterm_sent"]) is bool,
            "Installed process cleanup types differ.",
        )
        require(
            type(row["run"]) is int
            and row["run"] == index
            and type(row["pid"]) is int
            and row["pid"] > 0
            and row["pid"] not in pids
            and type(row["returncode"]) is int
            and row["returncode"] == 0
            and row["stop_method"]
            == ("terminate" if index in (2, 3) else "interface_quit")
            and row["port_closed"] is True
            and row.get("forced_cleanup") is False
            and not row.get("owned_group_remaining")
            and type(row["port"]) is int
            and 0 < row["port"] < 65536,
            "Actual installed exit/PID/closed port differs.",
        )
        pids.add(row["pid"])
        workspace = "/out/runtime/" + profile + "/data"
        expected = [
            "/opt/neuroforge/sinter/Sinter",
            "app",
            "--mode",
            "browser",
            "--directory",
            workspace,
        ]
        require(
            equal(row["argv"], expected)
            and row["workspace"] == workspace
            and row["binary_sha256"] == package["binary_sha256"]
            and full(row["cmdline"], 4096)
            == b"\x00".join(v.encode() for v in expected) + b"\x00",
            "A source worker cannot substitute for the installed binary.",
        )
        require(
            full(row["opener"], 1024) == f"http://127.0.0.1:{row['port']}".encode(),
            "Actual captured browser request differs.",
        )
        require(
            equal(row, json_object(data[f"process/run-{index}.json"])),
            "Process row differs from independently retained file.",
        )
        for name in ("stderr", "stdout"):
            raw = data[f"process/run-{index}.{name}"]
            observed = {
                "bytes": len(raw),
                "sha256": sha(raw),
                "sample_base64": base64.b64encode(raw[:65536]).decode(),
                "sample_complete": len(raw) <= 65536,
            }
            require(
                equal(row[name], observed) and len(raw) <= 65536,
                "Complete post-reap process stream evidence differs.",
            )
        require(
            data[f"process/run-{index}.stderr"] == notice,
            "Unexpected installed callback diagnostics refuse.",
        )
        for name in (f"run-{index}", f"stopped-{index}"):
            before = json_object(data[f"process/{name}.before-reader.json"])
            require(
                equal(projection(before), projection(original)),
                "Originals, schema, metadata or prefs changed before a reader.",
            )
        require(
            equal(projection(row["persistent_snapshot"]), projection(original))
            and equal(
                row["persistent_snapshot"],
                json_object(data[f"process/run-{index}.snapshot.json"]),
            ),
            "Stopped typed records/settings differ.",
        )
        if profile == "scoped":
            validate_cli(data, index, row["persistent_snapshot"], binding["version"])
    return processes


def validate_cli_stderr(operation, raw, exported):
    """Admit only the fixed local readers' complete source-defined progress."""
    require(type(raw) is bytes, "Supporting CLI diagnostics must be raw bytes.")
    if operation in {"casebooks.get", "casebooks.validate"}:
        require(raw == b"", "Supporting CLI reader diagnostics differ.")
    elif operation == "export":
        require(
            type(exported) is str
            and exported
            and len(exported.encode("utf-8")) <= 512
            and not any(c in exported for c in "\r\n\x00")
            and raw == ("Saved: " + exported + "\n").encode("utf-8"),
            "Supporting CLI export diagnostics differ from its fixed output.",
        )
    elif operation == "casebooks.build":
        # Runtime.wait samples the job state, so it can omit intermediate
        # messages. This fixed three-source/three-question fixture never admits
        # arbitrary diagnostics, reordered stages or repeated terminal messages.
        trace = [
            b"Waiting for an available worker\n",
            b"Starting\n",
            b"Indexing the supplied text locally; nothing is being uploaded\n",
            *(f"Reading document {n} of 3\n".encode("ascii") for n in range(1, 4)),
            *(
                [
                    b"Matching a question to exact passages, "
                    b"including surrounding wording\n"
                ]
                * 3
            ),
            b"Validating citations and recording retrieval coverage\n",
            b"Ready for review\n",
        ]
        require(
            0 < len(raw) <= sum(map(len, trace)) and raw.endswith(trace[-1]),
            "Supporting CLI build progress is incomplete or over bound.",
        )
        position = 0
        for line in raw.splitlines(keepends=True):
            try:
                position = trace.index(line, position) + 1
            except ValueError:
                raise ValueError(
                    "Supporting CLI build progress differs from its fixed trace."
                ) from None
    else:
        raise ValueError("Unknown supporting CLI diagnostic operation.")


def validate_cli(data, index, snapshot, version):
    from tools.rc4_scoped_recovery_contract import TITLE, wrappers

    originals = [
        r
        for r in wrappers(snapshot, "casebooks_scoped_v2")
        if r["document"]["title"] == TITLE
    ]
    require(len(originals) == 1, "Supporting CLI lost scoped original.")
    stored = originals[0]
    rows = json_object(data[f"process/run-{index}.cli.json"])
    require(
        set(rows) == {"before", "after", "operations", "reader_snapshots"}
        and equal(rows["before"], snapshot)
        and equal(rows["before"], rows["after"])
        and set(rows["operations"])
        == {"casebooks.get", "casebooks.validate", "casebooks.build", "export"},
        "Installed CLI changed originals or inventory.",
    )
    from tools import installed_native_entry_contract as native

    require(
        set(rows["reader_snapshots"]) == set(rows["operations"]),
        "Supporting CLI reader admissions incomplete.",
    )
    for op, result in rows["operations"].items():
        suffix = op.replace(".", "-")
        prefix = f"process/run-{index}.{suffix}"
        admissions = rows["reader_snapshots"][op]
        require(
            type(admissions) is dict
            and set(admissions) == {"before", "after"}
            and equal(admissions["before"], snapshot)
            and equal(admissions["before"], admissions["after"])
            and equal(
                admissions["before"], json_object(data[prefix + ".before-reader.json"])
            )
            and equal(
                admissions["after"], json_object(data[prefix + ".after-reader.json"])
            ),
            "Supporting CLI raw before/after evidence differs.",
        )
        body = (
            {"document": stored["document"]}
            if op == "casebooks.validate"
            else {"id": stored["id"]}
        )
        if op == "casebooks.build":
            body["revision"] = stored["revision"]
        require(
            equal(json_object(data[prefix + ".input.json"]), body),
            "Supporting CLI input differs.",
        )
        workspace = "/out/runtime/scoped/data"
        expected_argv = (
            [
                "/opt/neuroforge/sinter/Sinter",
                "export",
                "casebook",
                stored["id"],
                "--directory",
                workspace,
                "-o",
                f"/out/evidence/scoped/process/run-{index}.cli-export.json",
                "--machine",
            ]
            if op == "export"
            else [
                "/opt/neuroforge/sinter/Sinter",
                "run",
                op,
                "--input",
                f"/out/evidence/scoped/{prefix}.input.json",
                "--directory",
                workspace,
                "--format",
                "json",
            ]
        )
        native.stopped(result)
        require(
            result["argv"] == expected_argv and result["streams_complete"] is True,
            "Actual installed CLI command/ownership differs.",
        )
        for stream in ("stdout", "stderr"):
            raw = data[prefix + "." + stream]
            sample = native.stream_bytes(result[stream], complete=False)
            require(
                result[stream]["bytes"] == len(raw)
                and result[stream]["sha256"] == sha(raw)
                and sample == raw[:65536]
                and result[stream + "_file"]
                == "/out/evidence/scoped/" + prefix + "." + stream,
                "Supporting CLI complete stream/file identity differs.",
            )
        envelope = json_object(data[prefix + ".stdout"])
        validate_cli_stderr(
            op,
            data[prefix + ".stderr"],
            f"/out/evidence/scoped/process/run-{index}.cli-export.json",
        )
        require(
            envelope["ok"] is True
            and envelope["version"] == version
            and envelope["schema"] == "sinter-operation-result/v1"
            and envelope["operation"] == ("casebooks.get" if op == "export" else op),
            "Actual installed CLI identity/result differs.",
        )
        if op == "casebooks.get":
            require(equal(envelope["result"], stored), "CLI changed full stored input.")
        elif op == "casebooks.validate":
            require(
                equal(envelope["result"]["document"], stored["document"]),
                "CLI changed v2 input.",
            )
        elif op == "casebooks.build":
            require(
                equal(
                    envelope["result"]["question_scopes"],
                    stored["document"]["question_scopes"],
                ),
                "CLI broadened scope.",
            )
    require(
        equal(
            json_object(data[f"process/run-{index}.cli-export.json"]),
            stored["document"],
        ),
        "Installed CLI export lost full originals/source choices.",
    )


def profile_roles(profile):
    from tools.installed_recovery_contract import ARTIFACT_PATHS
    from tools.rc4_recovery_contract import ADVANCED
    from tools.rc4_scoped_recovery_contract import CORE

    require(profile in OPERATIONS, "Unknown recovery profile.")
    common = {"seed.json", "processes.json", "host-observations.json"}
    ui = (
        set(ARTIFACT_PATHS.values())
        | {"base-observations.json"}
        | {"advanced/" + n for n in ADVANCED}
        if profile == "campaign"
        else {
            n
            for n in CORE
            if not n.startswith("process/")
            and n
            not in {"seed-control.json", "seed.stdout", "seed.stderr", "processes.json"}
        }
    )
    count = 6 if profile == "campaign" else 4
    process = {
        f"process/run-{n}.{suffix}"
        for n in range(1, count + 1)
        for suffix in (
            "json",
            "stdout",
            "stderr",
            "snapshot.json",
            "before-reader.json",
        )
    }
    process |= {f"process/stopped-{n}.before-reader.json" for n in range(1, count + 1)}
    if profile == "scoped":
        process |= {
            f"process/run-{n}.{suffix}"
            for n in range(1, 5)
            for suffix in (
                "cli-export.json",
                "cli.json",
                *(
                    op + "." + stream
                    for op in (
                        "casebooks-get",
                        "casebooks-validate",
                        "casebooks-build",
                        "export",
                    )
                    for stream in (
                        "stdout",
                        "stderr",
                        "input.json",
                        "before-reader.json",
                        "after-reader.json",
                    )
                ),
            )
        }
    rpc_count = 6 if profile == "campaign" else 15
    rpc = {
        f"{directory}/{n:02d}.{kind}.json"
        for directory in ("rpc", "inner-rpc")
        for n in range(1, rpc_count + 1)
        for kind in ("request", "response")
    }
    return common | ui | process | rpc


def validate_browser_temp(observation):
    from tools.rc4_installed_recovery import (
        CACHE_DIRECTORY,
        CACHE_NAME,
        OWNED_TEMP_FILE,
        OWNED_TEMP_LIMIT,
    )

    require(
        type(observation) is dict
        and set(observation)
        == {"attempted", "inventory", "outcomes", "complete", "failure"}
        and observation["attempted"] is True
        and observation["complete"] is True
        and observation["failure"] is None,
        "Complete post-reap browser cache cleanup required.",
    )
    inventory = observation["inventory"]
    require(
        type(inventory) is dict and len(inventory) <= 64,
        "Bounded cache inventory required.",
    )
    for name, row in inventory.items():
        require(
            type(name) is str
            and type(row) is dict
            and type(row.get("bytes")) is int
            and row["bytes"] >= 0,
            "Cache inventory types differ.",
        )
        parts = name.split("/")
        if row.get("type") == "directory":
            require(
                len(parts) == 1
                and re.fullmatch(CACHE_DIRECTORY, name)
                and set(row) == {"type", "bytes"},
                "Unknown cache directory refused.",
            )
        else:
            if len(parts) == 1 and re.fullmatch(OWNED_TEMP_FILE, name):
                metadata = row.get("metadata")
                require(
                    row.get("type") == "file"
                    and set(row) == {"type", "bytes", "sha256", "metadata"}
                    and row["bytes"] <= OWNED_TEMP_LIMIT
                    and type(row["sha256"]) is str
                    and re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
                    and type(metadata) is dict
                    and set(metadata)
                    == {
                        "dev",
                        "ino",
                        "mode",
                        "uid",
                        "gid",
                        "nlink",
                        "size",
                        "mtime_ns",
                        "ctime_ns",
                    }
                    and all(
                        type(value) is int and value >= 0 for value in metadata.values()
                    )
                    and metadata["dev"] > 0
                    and metadata["ino"] > 0
                    and metadata["mode"] == stat.S_IFREG | 0o600
                    and metadata["uid"] == (os.getuid() if hasattr(os, "getuid") else 0)
                    and metadata["gid"] == (os.getgid() if hasattr(os, "getgid") else 0)
                    and metadata["nlink"] == 1
                    and metadata["size"] == row["bytes"],
                    "Unknown or non-private top-level temporary file refused.",
                )
                continue
            require(
                len(parts) == 2
                and re.fullmatch(CACHE_DIRECTORY, parts[0])
                and parts[1] == CACHE_NAME
                and row.get("type") == "file"
                and set(row) == {"type", "bytes", "sha256"}
                and row["bytes"] <= 32768
                and type(row["sha256"]) is str
                and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
                "Unknown cache file refused.",
            )
    require(
        type(observation["outcomes"]) is list
        and equal(
            sorted(observation["outcomes"], key=lambda v: v["path"]),
            [{"path": name, "removed": True} for name in sorted(inventory)],
        ),
        "Every actual cache removal outcome required.",
    )


def validate_absence(absence, commands):
    from tools import installed_native_entry_contract as native
    from tools.installed_native_menu import FILESYSTEM_PROBE

    require(
        type(absence) is dict
        and set(absence) == {"paths", "command_index"}
        and equal(absence["paths"], INSTALLED_PATHS)
        and type(absence["command_index"]) is int
        and 0 <= absence["command_index"] < len(commands),
        "Independent actual path absence missing.",
    )
    row = commands[absence["command_index"]]
    native.stopped(row)
    native.quiet(row["stderr"])
    # The fixed source-pinned probe has exactly this deterministic output.
    expected = (
        json.dumps(
            [{"path": p, "lexists": False} for p in INSTALLED_PATHS], sort_keys=True
        )
        + "\n"
    ).encode()
    require(
        row["streams_complete"] is True
        and type(row["argv"]) is list
        and len(row["argv"]) == 7
        and type(row["argv"][0]) is str
        and row["argv"][0].startswith("/")
        and row["argv"][1:] == ["-B", "-c", FILESYSTEM_PROBE, *INSTALLED_PATHS]
        and native.stream_bytes(row["stdout"]) == expected,
        "Exact stopped filesystem probe bytes differ.",
    )


def validate_host_observations(host, profile):
    require(
        type(host) is dict
        and set(host)
        == {
            "relay_closed",
            "model_route_requests",
            "relay_errors",
            "observation_requests",
            "body_failure",
            "cleanup_errors",
            "cleanup_attempts",
            "browser_sessions",
        },
        "Complete browser/relay cleanup response required.",
    )
    require(
        host["relay_closed"] is True
        and host["body_failure"] is None
        and type(host["model_route_requests"]) is int
        and host["model_route_requests"] == 0
        and type(host["relay_errors"]) is int
        and host["relay_errors"] == 0
        and host["cleanup_errors"] == [],
        "Actual browser/relay failure refused.",
    )
    require(
        equal(
            host["cleanup_attempts"],
            [
                {"resource": r, "succeeded": True}
                for r in (
                    "installed cleanup request",
                    "relay shutdown",
                    "relay close",
                    "relay join",
                )
            ],
        ),
        "Every independent host cleanup must be observed.",
    )
    phases = (
        ["campaign-base", "campaign-advanced"]
        if profile == "campaign"
        else ["scoped-base"]
    )
    sessions = host["browser_sessions"]
    require(
        type(sessions) is list and len(sessions) == len(phases),
        "Every browser session required.",
    )
    for session, phase in zip(sessions, phases, strict=True):
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
            and session["phase"] == phase
            and session["driver_closed"] is True
            and session["browser_closed"] is True
            and session["contexts_closed"] is True
            and session["cleanup_errors"] == [],
            "Every owned browser/context/driver must close without diagnostics.",
        )
        attempts = session["cleanup_attempts"]
        require(
            type(attempts) is list
            and len(attempts) >= 4
            and all(
                type(row) is dict
                and set(row) == {"resource", "succeeded"}
                and row["resource"]
                in {"context", "context retry", "browser", "browser final", "driver"}
                and row["succeeded"] is True
                for row in attempts
            )
            and all(
                any(row["resource"] == resource for row in attempts)
                for resource in ("context", "browser", "browser final", "driver")
            ),
            "Complete browser close attempts missing.",
        )


def validate_package_payload(root, inner, config, binding):
    from tools import installed_native_entry_contract as native
    from tools.installed_native_menu import package_members, stream_record
    from tools.package_native import debian_package_version, linux_desktop_entries

    rows = inner["commands"]
    indexes = inner["package_control_indexes"]
    require(
        type(indexes) is list
        and len(indexes) == 3
        and all(type(n) is int and 0 <= n < len(rows) for n in indexes)
        and len(set(indexes)) == 3,
        "Actual package control indexes differ.",
    )
    for index, (field, expected) in zip(
        indexes,
        (
            ("Package", "sinter"),
            ("Architecture", "amd64"),
            ("Version", debian_package_version(binding["version"])),
        ),
        strict=True,
    ):
        row = rows[index]
        native.stopped(row)
        native.quiet(row["stderr"])
        require(
            row["streams_complete"] is True
            and row["argv"]
            == ["dpkg-deb", "-f", "/candidate/" + config["installer_name"], field]
            and native.stream_bytes(row["stdout"]) == (expected + "\n").encode(),
            "Actual package control bytes differ.",
        )
    index = inner["package_payload_command_index"]
    require(
        type(index) is int and 0 <= index < len(rows),
        "Actual package payload command missing.",
    )
    row = rows[index]
    native.stopped(row)
    native.quiet(row["stderr"])
    require(
        row["streams_complete"] is True
        and row["argv"]
        == ["dpkg-deb", "--fsys-tarfile", "/candidate/" + config["installer_name"]],
        "Actual package extraction command differs.",
    )
    for name in ("stdout", "stderr"):
        raw = regular(root / "out/evidence" / ("package." + name), 128 * 1024 * 1024)
        require(
            row.get(name + "_file") == "/out/evidence/package." + name
            and equal(row[name], stream_record(io.BytesIO(raw))),
            "Complete package raw sidecar differs.",
        )
        if name == "stdout":
            payload = raw
    package = inner["package"]
    members = package_members(payload)
    binary = members["opt/neuroforge/sinter/Sinter"]
    entries = {
        name: record_full(members["usr/share/applications/" + name])
        for name in linux_desktop_entries(True)
    }
    require(
        package["payload_tar_bytes"] == len(payload)
        and type(package["payload_tar_bytes"]) is int
        and package["payload_tar_sha256"] == sha(payload)
        and package["binary_bytes"] == len(binary)
        and type(package["binary_bytes"]) is int
        and package["binary_sha256"] == sha(binary)
        and equal(package["entries"], entries),
        "Retained actual payload cannot disagree with package/binary/menu records.",
    )


def profile_artifacts(folder):
    require(
        folder.is_dir() and not folder.is_symlink(), "Require a private profile bundle."
    )
    data, total, count, directories = {}, 0, 0, set()
    pending = [folder]
    while pending:
        parent = pending.pop()
        for p in parent.iterdir():
            count += 1
            relative = p.relative_to(folder)
            require(
                count <= MAX_PROFILE_ENTRIES
                and len(relative.parts) <= MAX_PROFILE_DEPTH,
                "Profile entry count or depth exceeds finite bound.",
            )
            mode = p.lstat().st_mode
            require(not stat.S_ISLNK(mode), "Linked evidence refused.")
            require(
                stat.S_ISDIR(mode) or stat.S_ISREG(mode),
                "Special evidence entries refused.",
            )
            if stat.S_ISDIR(mode):
                directories.add(relative.as_posix())
                pending.append(p)
                continue
            raw = regular(p, MAX_FILE)
            if p.suffix == ".png":
                from tools.installed_workflow_qualification import validate_png

                validate_png(raw)
            total += len(raw)
            require(total <= MAX_TOTAL, "Profile evidence exceeds finite bound.")
            data[relative.as_posix()] = raw
    expected_directories = {
        parent.as_posix()
        for name in data
        for parent in Path(name).parents
        if parent != Path(".")
    }
    require(
        directories == expected_directories,
        "Unlisted empty profile directories refused.",
    )
    return data


def validate(root, receipt, pins, config, *, _pending=False):
    """Read actual installed artifacts without source or release promotion."""
    from tools import installed_native_entry_contract as native
    from tools.rc4_installed_recovery import outer_argv, source_binding

    require(
        type(receipt) is dict
        and set(receipt)
        == {
            "schema",
            "source",
            "owner_sha256",
            "commands",
            "resources",
            "failure",
            "installed_rehearsal_passed",
            "release_qualified",
            "prior_replacement_tested",
            "native_tested",
            "qa_files_after",
            "cleanup",
            "cleanup_errors",
            "docker_client",
            "host_process",
            "browser",
            *([] if _pending else ["verification"]),
        }
        and receipt["installed_rehearsal_passed"] is (False if _pending else True),
        "Require the distinct complete installed receipt.",
    )
    require(
        receipt["schema"] == OUTER
        and receipt["failure"] is None
        and receipt["release_qualified"] is False
        and receipt["native_tested"] is False
        and receipt["prior_replacement_tested"] is False
        and not receipt["cleanup"],
        "Installed rehearsal cannot replace source, prior, native or release proof.",
    )
    validate_config(config)
    client = receipt["docker_client"]
    require(
        type(client) is dict
        and set(client) == {"path", "sha256", "version", "sha256_after"}
        and client["sha256"] == client["sha256_after"],
        "Actual Docker client identity changed.",
    )
    native.stopped(client["version"])
    native.quiet(client["version"]["stderr"])
    require(
        client["version"]["argv"] == ["docker", "--version"]
        and client["version"]["streams_complete"] is True,
        "Actual Docker version command differs.",
    )
    require(
        native.stream_bytes(client["version"]["stdout"]).startswith(b"Docker version "),
        "Actual Docker version output missing.",
    )
    host = receipt["host_process"]
    native.stopped(host)
    native.quiet(host["stderr"])
    native.quiet(host["stdout"])
    expected_host = [
        sys.executable,
        "-B",
        str(root / "source/tools/rc4_installed_recovery.py"),
        "host",
        "--proof-root",
        str(root),
    ]
    browser = receipt["browser"]
    require(
        type(browser) is dict
        and set(browser)
        == {
            "path",
            "sha256",
            "sha256_after",
            "temporary_directory",
            "temporary_empty_before",
            "temporary_empty_after",
            "temporary_cleanup",
        }
        and equal({k: browser[k] for k in ("path", "sha256")}, config["browser"])
        and browser["sha256"] == browser["sha256_after"]
        and browser["temporary_directory"] == str(root / "t")
        and len(browser["temporary_directory"].encode()) <= 55
        and browser["temporary_empty_before"] is True
        and browser["temporary_empty_after"] is True,
        "Headless launch identity or owned temporary cleanup differs.",
    )
    validate_browser_temp(browser["temporary_cleanup"])
    require(
        host["streams_complete"] is True
        and host["argv"] == expected_host + ["--chromium", browser["path"]],
        "Actual host collector invocation or cleanup differs.",
    )
    native.validate_lifecycle(receipt["commands"], pins, outer_argv)
    binding = source_binding(
        regular(root / "repository/committed-source.tar", 128 * 1024 * 1024),
        config["source_commit"],
        receipt["source"]["qa_files"],
        config["mode"],
    )
    require(
        equal(binding, receipt["source"])
        and equal(receipt["qa_files_after"], binding["qa_files"]),
        "QA/candidate identity changed.",
    )
    inner = json_object(regular(root / "out/evidence/inner.json", 16 * 1024 * 1024))
    require(
        type(inner) is dict
        and set(inner)
        == {
            "schema",
            "source",
            "commands",
            "failure",
            "profiles",
            "provider_attempts",
            "passed",
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
            "removal_command",
            "removal",
            "absence",
            "qa_files_after",
            "cleanup_errors",
        },
        "Installed owner fields differ; old worker markers refuse.",
    )
    require(
        inner["schema"] == INNER
        and inner["cleanup_errors"] == []
        and receipt["cleanup_errors"] == []
        and inner["passed"] is True
        and inner["failure"] is None
        and inner["provider_attempts"] == "unmeasured"
        and equal(inner["source"], binding)
        and equal(inner["qa_files_after"], binding["qa_files"])
        and set(inner["profiles"]) == set(OPERATIONS),
        "Actual installed owner identity differs.",
    )
    package = inner["package"]
    require(
        package["installer_sha256"] == config["installer_sha256"]
        and sha(
            regular(root / "candidate" / config["installer_name"], 128 * 1024 * 1024)
        )
        == package["installer_sha256"]
        and package["receipt_sha256"] == config["package_receipt_sha256"],
        "Actual candidate bytes differ.",
    )
    package_receipt_raw = regular(
        root / "candidate" / config["package_receipt_name"], 2 * 1024 * 1024
    )
    require(
        sha(package_receipt_raw) == config["package_receipt_sha256"],
        "Actual package receipt bytes differ.",
    )
    expected = json_object(package_receipt_raw)
    validate_package_payload(root, inner, config, binding)
    require(
        expected["passed"] is True
        and expected["frozen"] is True
        and expected["source_commit"] == binding["commit"]
        and expected["version"] == binding["version"]
        and expected["installer_sha256"] == package["installer_sha256"],
        "Package receipt source/installer identity differs.",
    )
    from tools.package_native import debian_package_version, linux_desktop_entries

    entries = {
        n: record_full(v.encode("utf-8"))
        for n, v in linux_desktop_entries(True).items()
    }
    require(
        equal(package["entries"], entries)
        and equal(inner["installed_entries"], entries)
        and equal(
            inner["installed_binary"],
            {
                "bytes": package["binary_bytes"],
                "sha256": package["binary_sha256"],
                "executable": True,
            },
        ),
        "Both source-bound installed menu bytes and actual binary differ.",
    )
    package_status = inner["installed_package"]
    require(
        package_status["status"] == "install ok installed"
        and package_status["version"] == debian_package_version(binding["version"]),
        "Actual installed package status/version differs.",
    )
    row = inner["commands"][package_status["command_index"]]
    native.stopped(row)
    native.quiet(row["stderr"])
    require(
        row["argv"] == ["dpkg-query", "-W", "-f=${Status}\n${Version}\n", "sinter"]
        and native.stream_bytes(row["stdout"])
        == (
            "install ok installed\n" + debian_package_version(binding["version"]) + "\n"
        ).encode(),
        "Actual dpkg status/version output differs.",
    )
    native.diagnostic(
        inner["diagnostic_process"],
        inner["diagnostic"],
        binding["version"],
        inner["diagnostic_observation"],
    )
    row = inner["selftest_command"]
    native.stopped(row)
    native.quiet(row["stderr"])
    require(
        row["argv"]
        == [
            "/opt/neuroforge/sinter/Sinter",
            "--self-test",
            "/out/evidence/selftest.json",
        ]
        and row["streams_complete"] is True,
        "Actual installed selftest command differs.",
    )
    native.stream_bytes(row["stdout"])
    require(
        equal(inner["selftest"], expected["installed_test"])
        and inner["selftest"]["frozen"] is True
        and expected["frozen_cli_test"]["binary_sha256"] == package["binary_sha256"],
        "Source/frozen selftest cannot substitute for actual installed bytes.",
    )
    validate_package_removal(
        0, inner["removal_command"], inner["removal"], inner["commands"]
    )
    validate_absence(inner["absence"], inner["commands"])
    require(
        type(receipt["resources"]) is dict
        and set(receipt["resources"]) == set(OPERATIONS)
        and type(inner["profiles"]) is dict
        and set(inner["profiles"]) == set(OPERATIONS),
        "Both mandatory profile observations must be complete.",
    )
    for profile in OPERATIONS:
        require(
            equal(
                inner["profiles"][profile],
                {
                    "closed": True,
                    "failure": None,
                    "lifetimes": 6 if profile == "campaign" else 4,
                },
            ),
            "Inner mandatory profile lifetime/cleanup differs.",
        )
        data = profile_artifacts(root / "out/evidence" / profile)
        require(
            set(data) == profile_roles(profile),
            "Closed installed profile role inventory differs.",
        )
        processes = validate_processes(
            data, profile, binding, package, config["session"]
        )
        if profile == "campaign":
            validate_campaign(data, processes)
        else:
            validate_scoped(data)
        host = json_object(data["host-observations.json"])
        validate_host_observations(host, profile)
        require(
            equal(host, receipt["resources"][profile]),
            "Host complete retained response differs.",
        )
        count = 6 if profile == "campaign" else 15
        require(
            type(host["observation_requests"]) is int
            and host["observation_requests"] == count,
            "Fixed snapshot/protocol inventory differs.",
        )
        responses = []
        for n in range(1, count + 1):
            request = json_object(data[f"rpc/{n:02d}.request.json"])
            response = json_object(data[f"rpc/{n:02d}.response.json"])
            validate_request(request, profile, config["session"], n)
            validate_rpc(request, response)
            responses.append((request["operation"], response["result"]))
            require(
                response["error"] is None
                and data[f"rpc/{n:02d}.request.json"]
                == data[f"inner-rpc/{n:02d}.request.json"]
                and data[f"rpc/{n:02d}.response.json"]
                == data[f"inner-rpc/{n:02d}.response.json"],
                "Host/inner complete observation bytes differ.",
            )
        validate_observation_results(data, profile, responses)
    return {
        "schema": "sinter-rc4-installed-recovery-verified/v1",
        "execution": "installed",
        "candidate_commit": binding["commit"],
        "boundary": binding["mode"],
        "installed_lifetimes": 10,
        "release_qualified": False,
        "native_tested": False,
        "prior_replacement_tested": False,
        "provider_attempts": "unmeasured",
    }


def validate_observation_results(data, profile, responses):
    """Bind complete inner observations to their exact UI phase consumers."""
    from tools.rc4_recovery_worker import protected
    from tools.rc4_scoped_recovery_contract import seed_projection

    original = json_object(data["seed.json"])["seed"]["snapshot"]
    projection = (
        protected
        if profile == "campaign"
        else lambda value: seed_projection(value, original)
    )
    expected = (
        ["snapshot"] * 6 if profile == "campaign" else ["protocol"] + ["snapshot"] * 14
    )
    require(
        [op for op, value in responses] == expected,
        "Fixed profile observation order differs.",
    )
    for operation, value in responses:
        if operation == "snapshot":
            require(
                equal(projection(value), projection(original)),
                "Inner raw observation changed original records/settings.",
            )
    values = [v for _, v in responses]
    if profile == "campaign":
        require(
            all(equal(values[n], values[n // 3 * 3]) for n in range(6)),
            "Offline campaign inner raw observations changed.",
        )
        return
    observed = json_object(data["observations.json"])
    phases = {row["name"]: row["snapshot"] for row in observed["phases"]}
    require(
        equal(values[0], json_object(data["protocol.json"])),
        "Protocol UI result differs from inner response.",
    )
    targets = {
        1: observed["conflict"]["snapshot_before"],
        2: observed["conflict"]["snapshot_before"],
        3: observed["conflict"]["snapshot_after"],
        4: phases["saved-use"],
        5: phases["stopped-1"],
        6: phases["reopened-use"],
        7: observed["offline"]["clipboard"]["snapshot_before"],
        8: phases["stopped-2"],
        9: observed["offline"]["clipboard"]["snapshot_after"],
        10: observed["offline"]["manual"]["snapshot_before"],
        11: phases["stopped-3"],
        12: observed["offline"]["manual"]["snapshot_after"],
        13: phases["restored-both"],
        14: phases["stopped-4"],
    }
    require(
        all(equal(values[n], value) for n, value in targets.items()),
        "Scoped UI raw phase differs from its complete inner observation.",
    )


def validate_campaign(data, processes):
    """Validate literal campaign semantics; installed provenance is separate."""
    from tools.installed_recovery_contract import (
        ARTIFACT_PATHS,
        CAMPAIGN_SOURCE,
        _calendar,
        _csv,
        _offline,
        _phases,
        fictional_states,
    )
    from tools.rc4_recovery_contract import (
        LOCAL_NOTE,
        OTHER_NOTE,
        QUIT_NOTE,
        SAVE_NOTE,
        UNCERTAIN_TITLE,
    )

    states = fictional_states({CAMPAIGN_SOURCE: (ROOT / CAMPAIGN_SOURCE).read_bytes()})
    phases = _phases(data[ARTIFACT_PATHS["phases"]], states)
    base = json_object(data["base-observations.json"])
    require(
        set(base)
        == {"processes", "offline", "page_errors", "external_requests", "result_hashes"}
        and equal([base["page_errors"], base["external_requests"]], [0, 0]),
        "Base recovery observations differ.",
    )
    _offline(base["offline"])
    for branch in ("clipboard", "manual"):
        reference = data[ARTIFACT_PATHS[branch + "_reference"]]
        text = data[ARTIFACT_PATHS[branch + "_text"]]
        require(
            reference == text and equal(json_object(text), states["working"]),
            "Recovery backup omitted or changed original input.",
        )
        selected = base["offline"][branch]
        require(
            selected["textarea_selection_start"] == 0
            and selected["textarea_selection_end"]
            == len(text.decode().encode("utf-16-le")) // 2,
            "Recovery selection does not cover the full payload.",
        )
    _csv(data[ARTIFACT_PATHS["held_csv"]], states["held"])
    for role, phase in (
        ("held_calendar", "held"),
        ("resumed_closed_calendar", "resumed_closed"),
        ("resumed_calendar", "resumed"),
    ):
        _calendar(data[ARTIFACT_PATHS[role]], states[phase])
    advanced = json_object(data["advanced/observations.json"])
    require(
        set(advanced)
        == {
            "conflict",
            "stale_source",
            "uncertain_save",
            "uncertain_quit",
            "reopened_uncertain_save",
            "external_requests",
            "page_errors",
            "browser_dialogs",
        }
        and all(
            type(advanced[k]) is int and advanced[k] == 0
            for k in ("external_requests", "page_errors", "browser_dialogs")
        ),
        "Advanced recovery observations differ.",
    )
    imported = {**states["resumed"], "title": UNCERTAIN_TITLE}
    require(
        equal(json_object(data["advanced/control-import.json"]), imported),
        "Recovery control import differs.",
    )
    require(
        equal(
            advanced["stale_source"],
            {
                "stored_mark": imported["requirements"][1]["status"],
                "registered_date": imported["sources"][0]["checked_at"],
                "excerpt_checked_date": imported["requirements"][1]["checked_at"],
                "warning_visible": True,
                "stored_original_preserved": True,
            },
        ),
        "Stale source meaning or original human mark differs.",
    )
    conflict = advanced["conflict"]
    require(
        set(conflict)
        == {
            "base",
            "other_saved",
            "local_document",
            "failed_save_posts",
            "stored_original_preserved",
        }
        and equal(conflict["failed_save_posts"], 1)
        and conflict["stored_original_preserved"] is True,
        "Conflict observations differ.",
    )

    def wrapper(value, revision):
        return (
            isinstance(value, dict)
            and set(value) == {"id", "revision", "document"}
            and type(value["id"]) is str
            and re.fullmatch(r"[0-9a-f]{32}", value["id"])
            and type(value["revision"]) is int
            and value["revision"] == revision
        )

    require(
        wrapper(conflict["base"], 1) and wrapper(conflict["other_saved"], 2),
        "Conflict wrapper identity differs.",
    )
    require(
        type(conflict["base"]["revision"]) is int
        and conflict["base"]["revision"] == 1
        and equal(conflict["base"]["document"], imported),
        "Conflict baseline differs.",
    )
    local = {**imported, "objective": imported["objective"] + LOCAL_NOTE}
    other = {**imported, "objective": imported["objective"] + OTHER_NOTE}
    require(
        equal(conflict["local_document"], local)
        and equal(json_object(data["advanced/conflict-backup.json"]), local),
        "Conflict lost local recovery input.",
    )
    current = conflict["other_saved"]
    require(
        current["id"] == conflict["base"]["id"]
        and type(current["revision"]) is int
        and current["revision"] == 2
        and equal(current["document"], other),
        "Conflict changed the other saved original.",
    )
    saved = advanced["uncertain_save"]
    require(
        set(saved)
        == {
            "before",
            "actual_saved",
            "working_document",
            "actual_status",
            "reported_status",
            "save_posts",
            "automatic_replays",
        }
        and equal(saved["before"], current)
        and equal(
            [
                saved[k]
                for k in (
                    "actual_status",
                    "reported_status",
                    "save_posts",
                    "automatic_replays",
                )
            ],
            [200, 503, 1, 0],
        ),
        "Uncertain save observations differ.",
    )
    working = {**other, "objective": other["objective"] + SAVE_NOTE}
    actual = saved["actual_saved"]
    require(wrapper(actual, 3), "Uncertain save wrapper identity differs.")
    require(
        actual["id"] == current["id"]
        and type(actual["revision"]) is int
        and actual["revision"] == 3
        and equal(actual["document"], working)
        and equal(saved["working_document"], working)
        and equal(json_object(data["advanced/actual-save-response.json"]), actual)
        and equal(json_object(data["advanced/uncertain-save-backup.json"]), working)
        and equal(advanced["reopened_uncertain_save"], actual),
        "Uncertain save lost actual stored wording or input.",
    )
    quit_state = advanced["uncertain_quit"]
    dirty = {**working, "objective": working["objective"] + QUIT_NOTE}
    expected = {
        "working_document": dirty,
        "keep_working_posts": 0,
        "keep_working_retained_input": True,
        "actual_status": 200,
        "reported_status": 503,
        "quit_posts": 1,
        "automatic_replays": 0,
        "input_retained_after_stop": True,
    }
    require(
        equal(quit_state, expected)
        and equal(json_object(data["advanced/uncertain-quit-backup.json"]), dirty)
        and equal(
            json_object(data["advanced/actual-quit-response.json"]), {"ok": True}
        ),
        "Uncertain quit cleared input, replayed or falsely claimed confirmation.",
    )
    # The reopened live-file campaigns must contain exactly three recovery rows
    # plus the deliberately separate uncertain control; no original is rewritten.
    last = processes["rows"][-1]["persistent_snapshot"]["databases"][
        "campaigns.sqlite3"
    ]["tables"]["campaigns"]
    indexes = {name: index for index, name in enumerate(last["columns"])}
    wrappers = [
        {
            "id": row[indexes["id"]],
            "revision": row[indexes["revision"]],
            "document": json.loads(row[indexes["document"]]),
        }
        for row in last["rows"]
    ]
    wanted = [
        phases["resumed"],
        phases["restored_clipboard"],
        phases["restored_manual"],
        actual,
    ]
    require(
        equal(
            sorted(wrappers, key=lambda row: row["id"]),
            sorted(wanted, key=lambda row: row["id"]),
        ),
        "Cold reopen changed originals, separate copies or actual uncertain save.",
    )
    return phases


def validate_scoped(data):
    """Validate originals, scopes, Word and recovery; process checks are separate."""
    sys.path.insert(0, str(ROOT / "src"))
    from sinter.campaigns import validate as validate_campaign
    from sinter.casebooks import validate
    from tools.rc4_scoped_recovery_contract import (
        ACTION,
        QUESTIONS,
        TITLE,
        WARNING,
        fixture,
        seed_projection,
        validate_report,
        wrappers,
    )

    initial = json_object(data["seed.json"])["seed"]["snapshot"]
    observe = json_object(data["observations.json"])
    require(
        set(observe)
        == {
            "phases",
            "stale_scope",
            "conflict",
            "offline",
            "errors",
            "external",
            "dialogs",
            "warnings",
            "scoped",
            "report_id",
            "report",
            "campaign",
            "clipboard_restored",
            "manual_restored",
        },
        "Scoped observation fields differ",
    )
    require(
        observe["errors"] == observe["external"] == observe["dialogs"] == [],
        "Browser emitted an error or outside request",
    )
    require(
        observe["warnings"] == [WARNING],
        "The visible older-reader scope warning differs",
    )
    require(
        equal(json_object(data["fixture.json"]), fixture()),
        "Fictional original fixture differs",
    )
    expected = validate(fixture())
    ids = [row["id"] for row in expected["documents"]]
    expected = validate(
        {
            **expected,
            "schema": "sinter-casebook/v2",
            "question_scopes": [
                {"question_index": 0, "question": QUESTIONS[0], "source_ids": [ids[0]]},
                {"question_index": 1, "question": QUESTIONS[1], "source_ids": []},
            ],
        }
    )
    saved = observe["scoped"]
    require(
        set(saved) == {"id", "revision", "document"}
        and type(saved["revision"]) is int
        and saved["revision"] == 3
        and re.fullmatch(r"[0-9a-f]{32}", saved["id"]),
        "Scoped saved identity differs",
    )
    require(
        equal(saved["document"], expected)
        and equal(
            json_object(data["reopened.json"]),
            {k: v for k, v in expected.items() if k != "fingerprint"},
        ),
        "Selected/empty/all scopes or full original inputs changed",
    )
    stale = observe["stale_scope"]
    require(
        set(stale) == {"working", "stored", "posts", "warning"}
        and type(stale["posts"]) is int
        and stale["posts"] == 0
        and stale["warning"]
        == "Questions changed or moved. Review their source choices before saving.",
        "Stale question source choices were not blocked locally",
    )
    stale_expected = {k: v for k, v in expected.items() if k != "fingerprint"}
    stale_expected["questions"] = (
        QUESTIONS[0] + " Revised wording?\n" + "\n".join(QUESTIONS[1:])
    )
    require(
        equal(stale["working"], stale_expected)
        and equal(json_object(data["stale-scope.json"]), stale_expected)
        and equal(stale["stored"], {**saved, "revision": 2}),
        "Stale question scope backup or original changed",
    )
    conflict = observe["conflict"]
    require(
        set(conflict)
        == {
            "initial",
            "saved",
            "working",
            "posts",
            "automatic_replays",
            "snapshot_before",
            "snapshot_after",
            "warning",
        },
        "Scoped conflict fields differ",
    )
    control_expected = validate({**expected, "title": TITLE + " — conflict control"})
    require(
        equal(conflict["initial"]["document"], control_expected)
        and type(conflict["initial"]["revision"]) is int
        and conflict["initial"]["revision"] == 1
        and conflict["initial"]["id"] != saved["id"]
        and conflict["saved"]["id"] == conflict["initial"]["id"]
        and conflict["saved"]["revision"] == 2
        and equal(
            conflict["saved"]["document"],
            validate(
                {
                    **control_expected,
                    "recipient": "Fictional other-window saved wording",
                }
            ),
        ),
        "Scoped conflict changed unrelated original or saved wrong wording",
    )
    conflict_working = {k: v for k, v in control_expected.items() if k != "fingerprint"}
    conflict_working["recipient"] = "Fictional local unsaved conflict 🐝"
    require(
        equal(conflict["working"], conflict_working)
        and equal(json_object(data["scoped-conflict.json"]), conflict_working)
        and equal(json_object(data["control-import.json"]), expected)
        and type(conflict["posts"]) is int
        and conflict["posts"] == 1
        and type(conflict["automatic_replays"]) is int
        and conflict["automatic_replays"] == 0
        and equal(conflict["snapshot_before"], conflict["snapshot_after"])
        and "changed in another window" in conflict["warning"],
        "Scoped conflict lost inputs, changed typed records or replayed",
    )
    report = observe["report"]
    validate_report(report, expected, data["handover.docx"])
    require(
        type(observe["report_id"]) is str
        and re.fullmatch(r"[0-9a-f]{32}", observe["report_id"]),
        "Report ID is missing",
    )
    for excerpt in report["excerpts"]:
        original = next(
            row for row in expected["documents"] if row["id"] == excerpt["source_id"]
        )
        require(
            excerpt["quote"] == original["content"][excerpt["start"] : excerpt["end"]],
            "Passage range no longer binds the full original",
        )
    require(
        report["question_index"][0]["source_scope"]["source_ids"] == [ids[0]]
        and report["question_index"][1]["source_scope"]["source_ids"] == []
        and report["question_index"][2]["source_scope"]["mode"] == "all",
        "Report source choices broadened",
    )
    with zipfile.ZipFile(io.BytesIO(data["handover.docx"])) as archive:
        word = ET.fromstring(archive.read("word/document.xml"))
    text = "".join(
        row.text or ""
        for row in word.iter(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
        )
    )
    require(
        "Fictional human partial handover" in text
        and "No sources were selected" in text
        and "No application or enquiry was sent." in text,
        "Actual Word export lost scope or applied wording",
    )
    raw_fixture = json_object(
        (ROOT / "src/sinter/web/offline-garden-campaign.json").read_bytes()
    )
    campaign = validate_campaign(raw_fixture)
    campaign["actions"][0]["task"] = ACTION
    require(
        equal(observe["campaign"]["document"], campaign),
        "Campaign edit changed unknown owners/date/history/evidence",
    )
    phase_names = [r["name"] for r in observe["phases"]]
    require(
        phase_names
        == [
            "saved-use",
            "stopped-1",
            "reopened-use",
            "stopped-2",
            "stopped-3",
            "restored-both",
            "stopped-4",
        ],
        "Actual stop/reopen/use phases differ",
    )
    for row in observe["phases"]:
        require(
            equal(seed_projection(row["snapshot"], initial), initial),
            "Seeded typed rows, settings/model or persistent metadata changed",
        )
    for branch in ("clipboard", "manual"):
        offline = observe["offline"][branch]
        require(
            set(offline)
            == {
                "document",
                "selection",
                "clipboard",
                "snapshot_before",
                "snapshot_after",
            },
            "Offline recovery fields differ",
        )
        document = {
            **expected,
            "recipient": "Fictional " + branch + " recovery 🐝 e\u0301",
        }
        # Backup is the complete editable payload (normalization fingerprint excluded).
        working = {k: v for k, v in document.items() if k != "fingerprint"}
        require(
            equal(offline["document"], working)
            and equal(json_object(data[branch + ".json"]), working)
            and equal(json_object(data[branch + "-reference.json"]), working),
            "Offline recovery omitted full original inputs or scope",
        )
        raw = data[branch + ".json"].decode("utf-8")
        require(
            type(offline["selection"]) is list
            and len(offline["selection"]) == 2
            and all(type(endpoint) is int for endpoint in offline["selection"])
            and offline["selection"] == [0, len(raw.encode("utf-16-le")) // 2]
            and equal(offline["snapshot_before"], offline["snapshot_after"]),
            "Stopped backup changed local records or truncated manual selection",
        )
        require(
            equal(
                offline["clipboard"],
                {"attempts": 1, "successes": int(branch == "clipboard")},
            ),
            "Clipboard branch was not exercised",
        )
        restored = observe[branch + "_restored"]
        require(
            restored["id"] != saved["id"]
            and type(restored["revision"]) is int
            and restored["revision"] == 1
            and equal(
                restored["document"],
                validate({**working, "title": TITLE + " — " + branch + " restored"}),
            ),
            "Restore overwrote original or omitted full source choices",
        )
    require(
        observe["clipboard_restored"]["id"] != observe["manual_restored"]["id"],
        "Recovery copies share an identity",
    )
    protocol = json_object(data["protocol.json"])
    require(
        set(protocol)
        == {
            "matrix",
            "capable_get",
            "capable_validate",
            "snapshot_before",
            "snapshot_after",
            "jobs_before",
            "jobs_after",
        }
        and equal(protocol["snapshot_before"], protocol["snapshot_after"])
        and equal(protocol["jobs_before"], protocol["jobs_after"]),
        "Unsupported protocol work changed rows or queued work",
    )
    pairs = {(row["route"], row["variant"]) for row in protocol["matrix"]}
    require(
        len(protocol["matrix"]) == 30
        and pairs
        == {
            (r, v)
            for r in (
                "get",
                "validate",
                "save_scoped",
                "save_v1_over_scoped",
                "build",
                "draft",
            )
            for v in (
                "missing",
                "wrong",
                "duplicate_valid",
                "valid_wrong",
                "wrong_valid",
            )
        },
        "Protocol capability matrix is incomplete",
    )
    require(
        all(
            type(row["status"]) is int
            and row["status"] == 400
            and "no choices were cleared" in row["response"]["error"]
            for row in protocol["matrix"]
        )
        and equal(protocol["capable_get"], saved)
        and equal(protocol["capable_validate"], expected),
        "Protocol admission or friendly refusal differs",
    )
    processes = json_object(data["processes.json"])
    final = processes["rows"][-1]["persistent_snapshot"]
    scoped_rows = wrappers(final, "casebooks_scoped_v2")
    require(
        equal(
            sorted(scoped_rows, key=lambda r: r["id"]),
            sorted(
                [
                    saved,
                    observe["clipboard_restored"],
                    observe["manual_restored"],
                    conflict["saved"],
                ],
                key=lambda r: r["id"],
            ),
        ),
        "Stored scoped original/copies differ after real cold reopen",
    )
    final_tables = final["databases"]["workspace.sqlite3"]["tables"]
    initial_tables = initial["databases"]["workspace.sqlite3"]["tables"]
    require(
        all(
            equal(table, initial_tables[name])
            for name, table in final_tables.items()
            if name not in {"casebooks_scoped_v2", "reports"}
        ),
        "Recovery introduced foreign v1 rows or modified original history",
    )
    report_table = final["databases"]["workspace.sqlite3"]["tables"]["reports"]
    require(
        len(report_table["rows"]) == len(initial_tables["reports"]["rows"]) + 1
        and any(
            row[0] == observe["report_id"] and equal(json.loads(row[-1]), report)
            for row in report_table["rows"]
        ),
        "Original report ID/raw JSON/history lost",
    )
    require(
        equal(wrappers(final, "campaigns", "campaigns.sqlite3"), [observe["campaign"]]),
        "Campaign action/history altered by recovery",
    )
    return observe
