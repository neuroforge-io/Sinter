"""Closed, distinct Linux RC4 replacement evidence; historical gates stay frozen.

The installed route requires the separately reviewed native-owner shared parser.
Source fixture and source-browser receipts cannot satisfy this contract.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
from pathlib import Path
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import rc4_host_tools as host_tools  # noqa: E402
from tools.published_rc3_fixture import PUBLISHED_E  # noqa: E402
from tools.qualified_priors import QUALIFIED_PRIORS  # noqa: E402

VERSION = "0.5.4rc4"
SCHEMA = "sinter-installed-rc4-replacement/v1"
MATRIX_SCHEMA = "sinter-installed-rc4-replacement-matrix/v1"
PRIORS = MappingProxyType({**QUALIFIED_PRIORS, PUBLISHED_E.version: PUBLISHED_E})
CHECKSUMS = MappingProxyType(
    {
        "0.5.3": "32d4ac442ba823b6bd53b49e84b696252e8d81f6b3eb92eff0650180c9ab2b20",
        "0.5.4rc1": "c833b1c93a8af9d8d3f88336b727b3718b30edc19ab29d9b45e5f4f72a0eb1b6",
        "0.5.4rc2": "492e82f8972d7ee23d191dd0888bcf43d140a5ff9f24d4b5c7786ebaaefc2ff5",
        "0.5.4rc3": "dc7221487c31fdf015c650cdb35797c049e77d6fc3b179728b1b90fd650c1892",
    }
)
MOUNTS = (
    ("source_directory", "/source", False),
    ("repository", "/repository", False),
    ("prior_directory", "/prior", False),
    ("candidate_directory", "/candidate", False),
    ("output_directory", "/out", True),
)
PHASES = (
    "prior",
    "candidate",
    "candidate-cold",
    "prior-protocol",
    "candidate-protocol",
)
PACKAGE_ROLES = (
    "initial-absence",
    "install-prior",
    "prior-status",
    "prior-status-after",
    "replace",
    "candidate-status",
    "candidate-status-after",
    "cold-status-after",
    "remove",
    "removed-status",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


RUN_ORDER = (
    "prior",
    "prior-protocol",
    "candidate",
    "candidate-protocol",
    "candidate-cold",
)


def observe_host_identity(chromium, browser_tmp):
    """Observe each selected actual host file independently, including failures."""
    import importlib.metadata
    import shutil

    def driver_root():
        import playwright

        return Path(playwright.__file__).resolve(strict=True).parent / "driver"

    # Every discovery and file read stays in its independent callback, so one
    # removed/redirected file or missing library cannot skip other observations.
    # Fixed collector environment excludes PLAYWRIGHT_NODEJS_PATH and selects
    # this installed library's bundled Node/CLI.
    callbacks = {
        "docker": lambda: host_tools.fingerprint(
            Path(shutil.which("docker", path=os.defpath) or "/missing-docker").resolve(
                strict=True
            )
        ),
        "chromium": lambda: host_tools.fingerprint(Path(chromium)),
        "python": lambda: host_tools.fingerprint(Path(sys.executable).resolve()),
        "playwright_node": lambda: host_tools.fingerprint(
            (driver_root() / "node").resolve()
        ),
        "driver_cli": lambda: host_tools.fingerprint(
            (driver_root() / "package/cli.js").resolve()
        ),
        "collector_source": lambda: host_tools.fingerprint(
            Path(__file__).with_name("rc4_replacement_probe.py").resolve()
        ),
        "playwright_version": lambda: importlib.metadata.version("playwright"),
    }
    records, errors, primary = host_tools.observe(callbacks)
    return (
        {
            "tools": {name: records[name] for name in host_tools.TOOLS},
            "browser_tmp": str(browser_tmp),
            "python_launch": str(Path(sys.executable)),
            **{
                name: records[name]
                for name in ("driver_cli", "collector_source", "playwright_version")
            },
        },
        errors,
        primary,
    )


def host_identity(chromium, browser_tmp):
    """Require a complete actual before snapshot; no app admission is implied."""
    result, errors, primary = observe_host_identity(chromium, browser_tmp)
    if primary is not None:
        primary.host_observation_errors = errors
        raise primary
    host_tools.validate_host_snapshot(result)
    return result


def collector_argv(folder, chromium, phase, browser_tmp):
    require(phase in RUN_ORDER, "Use a fixed replacement phase.")
    return [
        sys.executable,
        "-B",
        str(Path(__file__).with_name("rc4_replacement_probe.py")),
        "--runtime",
        str(folder / "bridge" / phase),
        "--chromium",
        str(chromium),
        "--phase",
        phase,
        "--browser-tmp",
        str(browser_tmp),
    ]


def validate_bridge(bridge, process, expected, phase, workspace, folder):
    from tools.rc4_replacement_probe import bridge_request

    runtime = folder.parent.parent / "bridge" / phase
    require(
        type(bridge) is dict
        and set(bridge)
        == {
            "request",
            "response",
            "failure",
            "inner_thread_alive",
            "inner_socket_remaining",
            "inner_workers_remaining",
            "inner_connections_remaining",
        }
        and bridge["failure"] is None
        and bridge["inner_thread_alive"] is False
        and bridge["inner_socket_remaining"] is False
        and not (runtime / "relay.sock").exists(),
        "Inner relay failed or remains alive.",
    )
    require(
        type(bridge["inner_workers_remaining"]) is int
        and bridge["inner_workers_remaining"] == 0
        and type(bridge["inner_connections_remaining"]) is int
        and bridge["inner_connections_remaining"] == 0,
        "Inner relay retains request workers or sockets.",
    )
    request = json_value(regular(runtime / "state.json", 2_000_000))
    actual_expected = regular(runtime / "expected.json", 2_000_000)
    require(
        equal(json_value(actual_expected), expected)
        and equal(bridge["request"], request),
        "Actual bridge expected data or request differs.",
    )
    bridge_request(request, phase, actual_expected)
    from tools.rc4_replacement_probe import API

    require(
        API(regular(folder / "opened-url.txt", 4096).decode("utf-8").strip()).port
        == request["port"],
        "Inner relay does not target the captured actual installed listener.",
    )
    require(
        request["pid"] == process["pid"]
        and request["workspace"] == str(workspace)
        and request["binary_sha256"] == process["binary_sha256"],
        "Bridge substituted a process, package or workspace.",
    )
    response = json_value(regular(runtime / "response.json", 2_000_000))
    require(
        equal(bridge["response"], response)
        and type(response) is dict
        and set(response) == {"request", "ui", "failure", "resources"}
        and equal(response["request"], request)
        and response["failure"] is None,
        "Actual host response is missing, failed or belongs to another phase.",
    )
    resources = response["resources"]
    require(
        type(resources) is dict
        and set(resources)
        == {
            "host_port",
            "host_connect_errno",
            "thread_alive",
            "connections_remaining",
            "relay_errors",
            "model_route_requests",
            "workers_remaining",
            "sockets_remaining",
            "browser_temp_remaining",
        }
        and type(resources["host_port"]) is int
        and 1 <= resources["host_port"] <= 65535
        and type(resources["host_connect_errno"]) is int
        and resources["host_connect_errno"] != 0
        and resources["thread_alive"] is False
        and resources["connections_remaining"] is False
        and type(resources["relay_errors"]) is int
        and resources["relay_errors"] == 0
        and type(resources["model_route_requests"]) is int
        and resources["model_route_requests"] == 0,
        "Actual host relay resources or error types differ.",
    )
    require(
        type(resources["workers_remaining"]) is int
        and resources["workers_remaining"] == 0
        and type(resources["sockets_remaining"]) is int
        and resources["sockets_remaining"] == 0,
        "Host relay retains request workers or sockets.",
    )
    require(
        equal(resources["browser_temp_remaining"], []),
        "Host browser temporary resources remain.",
    )
    for path, observed in (
        (runtime / "host-diagnostics.json", resources),
        (runtime / "ui-diagnostics.json", response["ui"]["resources"]),
        (folder / "inner-diagnostics.json", bridge),
    ):
        diagnostics = json_value(regular(path, 2_000_000))
        require(
            type(diagnostics) is dict
            and set(diagnostics) == {"failure", "cleanup_failures", "resources"}
            and diagnostics["failure"] is None
            and diagnostics["cleanup_failures"] == []
            and equal(diagnostics["resources"], observed),
            "Actual primary or cleanup diagnostics contradict successful evidence.",
        )
    from tools.rc4_replacement_probe import closed_port

    require(
        closed_port(resources["host_port"]) != 0, "Host relay listener is still open."
    )
    for image in response["ui"]["screenshots"]:
        require(
            type(image) is dict
            and type(image.get("name")) is str
            and re.fullmatch(r"(?:report-[0-9]+|campaign|actions)\.png", image["name"]),
            "Host screenshot path differs from its fixed roles.",
        )
        require(
            equal(
                blob(regular(runtime / image["name"], 2_000_000)),
                blob(regular(folder / image["name"], 2_000_000)),
            ),
            "Host screenshot bytes were substituted in inner output.",
        )
    return response["ui"]


def validate_collectors(rows, folder, chromium, probes, browser_tmp):
    require(
        type(rows) is list and len(rows) == len(RUN_ORDER),
        "All five actual host collectors are required.",
    )
    pids = set()
    for phase, row in zip(RUN_ORDER, rows):
        require(
            type(row) is dict
            and set(row)
            == {
                "role",
                "argv",
                "pid",
                "exit_code",
                "reaped",
                "stdout",
                "stderr",
                "forced_cleanup",
                "group_remaining",
            }
            and row["role"] == phase
            and equal(row["argv"], collector_argv(folder, chromium, phase, browser_tmp))
            and type(row["pid"]) is int
            and row["pid"] > 1
            and row["pid"] not in pids
            and type(row["exit_code"]) is int
            and row["exit_code"] == 0
            and row["reaped"] is True
            and row["forced_cleanup"] is False
            and row["group_remaining"] is False
            and raw_blob(row["stdout"])
            == b"Owned replacement host phase retained and closed.\n"
            and raw_blob(row["stderr"]) == b"",
            "Actual host collector argv, process, streams or cleanup differs.",
        )
        require(
            equal(
                row,
                json_value(
                    regular(folder / (phase + "-collector-command.json"), 2_000_000)
                ),
            )
            and raw_blob(row["stdout"])
            == regular(folder / "host-streams" / (phase + ".stdout"))
            and raw_blob(row["stderr"])
            == regular(folder / "host-streams" / (phase + ".stderr")),
            "Complete post-reap host streams differ from their retained raw sidecars.",
        )
        require(
            equal(
                probes[phase]["bridge"],
                json_value(regular(folder / "run" / phase / "bridge.json", 2_000_000)),
            ),
            "Actual inner bridge observation differs from its raw sidecar.",
        )
        pids.add(row["pid"])


def outer_sidecars(rows, folder):
    tree_entries(folder)
    pids = set()
    for row in rows:
        actual = json_value(
            regular(folder / (row["role"] + "-command.json"), 2_000_000)
        )
        require(
            type(actual) is dict
            and set(actual)
            == {"role", "argv", "pid", "exit_code", "reaped", "stdout", "stderr"}
            and type(actual["pid"]) is int
            and actual["pid"] > 1
            and actual["pid"] not in pids
            and actual["reaped"] is True
            and type(actual["exit_code"]) is int
            and all(
                equal(actual[key], row[key])
                for key in ("role", "argv", "exit_code", "reaped")
            ),
            "Raw actual outer command/PID sidecar differs.",
        )
        for channel in ("stdout", "stderr"):
            raw = raw_blob(actual[channel], 128 * 1024 * 1024)
            require(
                raw
                == regular(folder / "outer-streams" / (row["role"] + "." + channel)),
                "Complete outer post-reap stream bytes differ.",
            )
            require(
                equal(
                    row[channel],
                    {
                        **blob(raw[:65536]),
                        "bytes": len(raw),
                        "sha256": sha(raw),
                        "text": raw[:65536].decode("utf-8", errors="replace"),
                        "truncated": len(raw) > 65536,
                    },
                ),
                "Shared lifecycle sample/count/digest differs from the raw stream.",
            )
        pids.add(actual["pid"])


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def equal(left, right):
    return encoded(left) == encoded(right)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path, limit=128 * 1024 * 1024):
    path = Path(path)
    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode) and before.st_size <= limit,
        "Use a bounded regular file, without links.",
    )
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
    )
    with os.fdopen(descriptor, "rb") as stream:
        current = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(current.st_mode)
            and current.st_size <= limit
            and (before.st_dev, before.st_ino) == (current.st_dev, current.st_ino),
            "Evidence changed while opening.",
        )
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "Evidence exceeds its bound.")
    return raw


def tree_entries(directory):
    """Inventory only real directories and regular files; never open special entries."""
    directory = Path(directory)
    require(stat.S_ISDIR(directory.lstat().st_mode), "Use a real evidence directory.")
    entries, pending = [], [directory]
    while pending:
        parent = pending.pop()
        for path in sorted(parent.iterdir()):
            info = path.lstat()
            require(
                stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode),
                "Evidence trees admit only regular files and real directories.",
            )
            entries.append((path, info))
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
    return entries


def hashes(directory):
    directory = Path(directory)
    return {
        path.relative_to(directory).as_posix(): sha(regular(path))
        for path, info in tree_entries(directory)
        if stat.S_ISREG(info.st_mode)
    }


def blob(raw):
    return {
        "bytes": len(raw),
        "sha256": sha(raw),
        "base64": base64.b64encode(raw).decode("ascii"),
    }


def raw_blob(row, limit=16 * 1024 * 1024):
    require(
        type(row) is dict and set(row) == {"bytes", "sha256", "base64"},
        "Complete original bytes are required.",
    )
    try:
        raw = base64.b64decode(row["base64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid original byte encoding.") from exc
    require(
        type(row["bytes"]) is int
        and row["bytes"] == len(raw) <= limit
        and type(row["sha256"]) is str
        and row["sha256"] == sha(raw),
        "Original count or digest differs.",
    )
    return raw


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key.")
        result[key] = value
    return result


def json_value(raw):
    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )


def snapshot(directory):
    tree_entries(directory)
    from tools.published_rc3_fixture_seed import workspace_snapshot

    directory = Path(directory)
    for name in ("preferences.json", "workspace.sqlite3", "campaigns.sqlite3"):
        regular(directory / name)
    for name in ("workspace.sqlite3", "campaigns.sqlite3"):
        with sqlite3.connect(
            (directory / name).resolve().as_uri() + "?mode=ro", uri=True
        ) as db:
            require(
                db.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
                "Persistent database integrity differs.",
            )
    result = workspace_snapshot(directory)
    result["preferences_original"] = blob(regular(directory / "preferences.json"))
    return result


def preserve(before, after, empty_schema):
    """Conserve every prior typed row and preference byte; add exact empty tables."""
    require(
        type(before) is dict
        and type(after) is dict
        and set(before)
        == set(after)
        == {"preferences", "preferences_sha256", "preferences_original", "databases"},
        "Complete preservation snapshots are required.",
    )
    for key in ("preferences", "preferences_sha256", "preferences_original"):
        require(
            equal(before[key], after[key]), "Original preferences or selection changed."
        )
    raw = raw_blob(after["preferences_original"])
    require(
        sha(raw) == after["preferences_sha256"]
        and equal(json_value(raw), after["preferences"]),
        "Preference originals differ.",
    )
    require(
        set(before["databases"])
        == set(after["databases"])
        == set(empty_schema)
        == {"workspace.sqlite3", "campaigns.sqlite3"},
        "Both databases are required.",
    )
    for name, initial in before["databases"].items():
        current = after["databases"][name]
        require(
            set(initial) == set(current) == {"metadata", "tables"},
            "Database schema or metadata is incomplete.",
        )
        require(
            equal(initial["metadata"], current["metadata"]), "SQLite metadata changed."
        )
        allowed = {**initial["tables"]}
        for table, row in empty_schema[name]["tables"].items():
            if table not in allowed:
                require(
                    row["rows"] == [],
                    "Only source-derived empty additions are allowed.",
                )
                allowed[table] = row
        require(
            equal(current["tables"], allowed),
            "A logical row, history, original document, schema or table changed.",
        )


def select_prior(version, commit, target=VERSION):
    require(
        type(version) is str
        and type(commit) is str
        and type(target) is str
        and target == VERSION
        and version in PRIORS
        and PRIORS[version].source_commit == commit,
        "Only four exact published priors to final Linux RC4 are supported.",
    )
    return PRIORS[version]


def stopped(row, argv, workspace, binary_sha, version):
    require(
        type(row) is dict
        and set(row)
        == {
            "argv",
            "workspace",
            "binary_sha256",
            "pid",
            "exit_code",
            "reaped",
            "forced_cleanup",
            "group_remaining",
            "listener_closed",
            "stdout",
            "stderr",
        },
        "A complete post-reap process observation is required.",
    )
    require(
        equal(row["argv"], argv)
        and row["workspace"] == str(workspace)
        and row["binary_sha256"] == binary_sha,
        "Process/workspace identity differs.",
    )
    require(
        type(row["pid"]) is int
        and row["pid"] > 1
        and type(row["exit_code"]) is int
        and row["exit_code"] == 0,
        "Actual installed process did not exit normally.",
    )
    require(
        all(
            row[key] is value
            for key, value in (
                ("reaped", True),
                ("forced_cleanup", False),
                ("group_remaining", False),
                ("listener_closed", True),
            )
        ),
        "Stopped-process ownership is incomplete.",
    )
    stdout, stderr = raw_blob(row["stdout"]), raw_blob(row["stderr"])
    if version in {"0.5.4rc3", VERSION}:
        require(
            re.fullmatch(
                rb"Sinter local workspace: http://127\.0\.0\.1:[1-9][0-9]{0,4}\n",
                stdout,
            )
            and stderr
            == (
                b"Press Ctrl+C to stop. "
                b"Closing a browser tab alone does not quit Sinter.\n"
            ),
            "Actual complete browser-mode streams contain unexpected diagnostics.",
        )
    else:
        require(
            stdout == stderr == b"",
            "Actual legacy browser streams contain unexpected diagnostics.",
        )


def command_sidecars(row, folder):
    """Bind complete post-reap files, including bytes beyond any displayed sample."""
    for channel in ("stdout", "stderr"):
        actual = regular(folder / (row["role"] + "." + channel))
        require(
            equal(blob(actual), row[channel]),
            "Actual complete command sidecar differs: " + row["role"] + "." + channel,
        )


def package_commands(
    rows, prior_package, candidate_package, prior_path, candidate_path, folder
):
    tree_entries(folder)
    require(
        type(rows) is list and len(rows) == len(PACKAGE_ROLES),
        "Every package transition is required.",
    )
    status = ["dpkg-query", "-W", "-f=${Status}\n${Version}\n", "sinter"]
    commands = [
        status,
        ["dpkg", "-i", str(prior_path)],
        status,
        status,
        ["dpkg", "-i", str(candidate_path)],
        status,
        status,
        status,
        ["dpkg", "-r", "sinter"],
        status,
    ]
    for index, (row, role, argv) in enumerate(zip(rows, PACKAGE_ROLES, commands)):
        require(
            type(row) is dict
            and set(row)
            == {"role", "argv", "pid", "exit_code", "reaped", "stdout", "stderr"}
            and row["role"] == role
            and equal(row["argv"], argv)
            and type(row["pid"]) is int
            and row["pid"] > 1
            and row["reaped"] is True
            and type(row["exit_code"]) is int,
            "Package command identity, order or reap differs.",
        )
        out, err = raw_blob(row["stdout"]), raw_blob(row["stderr"])
        command_sidecars(row, folder)
        if index in {0, 9}:
            require(
                row["exit_code"] == 1
                and out == b""
                and err == b"dpkg-query: no packages found matching sinter\n",
                "An arbitrary status failure cannot prove absence.",
            )
        else:
            common, _owner = shared()
            require(
                row["exit_code"] == 0
                and (
                    err == b""
                    or (role == "remove" and err == common.SHARED_OPT_REMOVAL_WARNING)
                ),
                "Package transition failed.",
            )
            if index in {2, 3, 5, 6, 7}:
                version = prior_package if index < 4 else candidate_package
                require(
                    out == ("install ok installed\n" + version + "\n").encode(),
                    "Actual dpkg status and Version differ.",
                )


def shared():
    """No fallback parser: require the separately reviewed common owner composition."""
    try:
        from tools import installed_native_entry_contract as contract
        from tools import installed_native_menu as owner
    except ImportError as exc:
        raise ValueError(
            "Compose the separately reviewed native owner tools first."
        ) from exc
    require(
        callable(getattr(contract, "validate_lifecycle", None)),
        "The strict shared lifecycle parser is unavailable.",
    )
    return contract, owner


def private_paths(args, source):
    root = args.owned_root.resolve(strict=True)
    require(
        root.is_dir() and not args.owned_root.is_symlink(),
        "Use an actual private owning root.",
    )
    for path in (source, args.repository, args.candidate, args.priors, args.output):
        resolved = path.resolve()
        require(
            resolved != root and resolved.is_relative_to(root),
            "Every source/input/output path must be inside the private owning root.",
        )
        require(not path.is_symlink(), "Mounted path links are refused.")


def outer_argv(pins, name):
    argv = [
        "docker",
        "create",
        "--pull=never",
        "--name",
        name,
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "64",
        "--user",
        "0:0",
        "--workdir",
        "/",
    ]
    for key, destination, writable in MOUNTS:
        argv += [
            "--mount",
            "type=bind,src="
            + pins[key]
            + ",dst="
            + destination
            + ("" if writable else ",readonly"),
        ]
    for value in (
        "PYTHONDONTWRITEBYTECODE=1",
        "TMPDIR=/out",
        "GIT_CONFIG_COUNT=1",
        "GIT_CONFIG_KEY_0=safe.directory",
        "GIT_CONFIG_VALUE_0=/repository",
    ):
        argv += ["--env", value]
    return argv + [
        pins["image_id"],
        "python3",
        "-B",
        "/source/tools/rc4_replacement.py",
        "inner",
        "--repository",
        "/repository",
        "--source-route",
        "archive",
        "--source-commit",
        pins["source_commit"],
        "--prior-version",
        pins["prior_version"],
        "--candidate",
        "/candidate",
        "--output",
        "/out/run",
    ]


def subset(original, current):
    if type(original) is dict:
        require(
            type(current) is dict and set(original).issubset(current),
            "An original field is absent.",
        )
        for key, value in original.items():
            subset(value, current[key])
    elif type(original) is list:
        require(
            type(current) is list and len(original) == len(current),
            "Original array length changed.",
        )
        for first, second in zip(original, current):
            subset(first, second)
    else:
        require(
            type(original) is type(current) and original == current,
            "Original typed value changed.",
        )


def book_view(original, current):
    subset(original, current)
    if original["document"].get("schema") == "sinter-casebook/v2":
        require(
            equal(original["document"], current["document"]),
            "Closed scoped document acquired fields or changed explicit selections.",
        )


def rendered_words(value):
    """The saved fictional documents use headings, quotes, lists and inline code."""
    result = []
    for line in value.splitlines():
        line = re.sub(r"^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+\.\s+)+", "", line)
        line = re.sub(
            r"\*\*(.*?)\*\*|`([^`]+)`", lambda match: match[1] or match[2], line
        )
        if line.strip():
            result.append(" ".join(line.split()))
    return result


def rendered_document(value):
    """Preserve the complete ordered wording and multiplicity across paragraphs."""
    return " ".join(rendered_words(value))


def ordered_rendered_words(value, actual):
    """Consume complete saved segments once, in order, allowing list labels."""
    segments = rendered_words(value)
    require(bool(segments), "Original saved report wording is empty.")
    cursor = 0
    for line in segments:
        pattern = re.compile(r"(?<!\S)" + re.escape(line) + r"(?!\S)")
        match = pattern.search(actual, cursor)
        if match is None:
            return False
        cursor = match.end()
    return True


def report_text(report, text, include_title=True):
    require(
        type(text) is str and (not include_title or report["title"] in text),
        "Saved report did not render.",
    )
    reference = report.get("document_edits", {}).get(
        "markdown", report.get("document_markdown", report.get("markdown", ""))
    )
    require(
        type(reference) is str and reference.strip(), "Saved report wording is missing."
    )
    actual = " ".join(text.split())
    require(
        ordered_rendered_words(reference, actual),
        "Complete ordered original saved report wording did not visibly render.",
    )


def visible_campaign_semantics(visible, campaign, version):
    """Bind visible semantic fields; source quotations may contain any words."""
    facts = visible.get("opportunity_facts")
    require(
        visible.get("owner_semantics_capability")
        == (
            "legacy fields only" if version == "0.5.3" else "conservative owner fields"
        ),
        "Visible owner capability was misclassified.",
    )
    require(type(facts) is list and facts, "Visible opportunity fields are missing.")
    by_label = {}
    campaign_text = " ".join(visible["campaign"].split())
    for row in facts:
        require(
            type(row) is dict
            and set(row) == {"label", "text", "visible"}
            and type(row["label"]) is str
            and type(row["text"]) is str
            and row["visible"] is True
            and row["label"] not in by_label,
            "Opportunity semantic field is hidden, duplicated or malformed.",
        )
        require(
            " ".join((row["label"] + " " + row["text"]).split()) in campaign_text,
            "Visible opportunity fields differ from actual campaign content.",
        )
        by_label[row["label"]] = row["text"]
    require(
        by_label.get("Decision timing") == "Not confirmed",
        "Visible decision timing promoted an unconfirmed date.",
    )
    if version == "0.5.3":
        require(
            by_label.get("Application closes") == "Not confirmed",
            "Legacy visible closing date was promoted.",
        )
        require(
            visible.get("owner_semantics") == []
            and visible.get("owner_types") == []
            and visible.get("owner_acceptance") == [],
            "Legacy owner fields cannot claim newer confirmation controls.",
        )
        return
    require(
        by_label.get("Application window") == "Not checked"
        and by_label.get("Application lead") == "Application process not confirmed",
        "Visible application window or applicant process was promoted.",
    )
    owners = visible.get("owner_semantics")
    require(
        type(owners) is list and len(owners) == len(campaign["actions"]),
        "Visible owner semantic rows are missing.",
    )
    action_text = " ".join(visible["actions"].split())
    for index, (row, original) in enumerate(zip(owners, campaign["actions"])):
        require(
            type(row) is dict
            and set(row)
            == {
                "index",
                "task",
                "summary",
                "detail",
                "owner_type_label",
                "date_text",
                "visible",
            }
            and type(row["index"]) is int
            and row["index"] == index
            and row["task"] == original["task"]
            and row["visible"] is True
            and all(
                type(row[key]) is str
                for key in (
                    "task",
                    "summary",
                    "detail",
                    "owner_type_label",
                    "date_text",
                )
            ),
            "Visible action identity or field visibility differs.",
        )
        kind = original["owner_kind"]
        require(
            kind in {"unknown", "unassigned"}, "Use the closed fictional owner profile."
        )
        summary = (
            "Owner type not confirmed: " + original["owner"]
            if kind == "unknown"
            else "No person named; owner needed"
        )
        detail = (
            "Confirm whether this entry is a named person or a suggested role "
            "before recording acceptance."
            if kind == "unknown"
            else "Owner needed — no person is recorded. Assign a named person "
            "before marking acceptance."
        )
        require(
            summary in row["summary"]
            and row["detail"] == detail
            and row["owner_type_label"]
            == ("Type needs confirmation" if kind == "unknown" else "No owner assigned")
            and "Confirm timing with the owner." in row["date_text"],
            "Visible owner or proposed-date meaning was promoted.",
        )
        if not original["due"]:
            require(
                row["date_text"]
                == "No target date set. Confirm timing with the owner.",
                "Visible unknown target date was promoted.",
            )
        require(
            all(
                " ".join(row[key].split()) in action_text
                for key in ("task", "summary", "detail", "date_text")
            ),
            "Visible owner fields differ from actual actions content.",
        )


def validate_probe(proof, expected, phase, workspace, binary_sha, folder):
    from tools.installed_workflow_browser import browser_launch_command

    require(
        type(proof) is dict
        and set(proof)
        == {"process", "api", "ui", "failure", "version_command", "bridge"}
        and proof["failure"] is None,
        "Complete successful installed observations are required.",
    )
    version = expected["prior_version"] if phase.startswith("prior") else VERSION
    stopped(
        proof["process"],
        browser_launch_command(["/opt/neuroforge/sinter/Sinter"], version),
        workspace,
        binary_sha,
        version,
    )
    require(
        equal(proof, json_value(regular(folder / "probe.json", 2_000_000)))
        and raw_blob(proof["process"]["stdout"]) == regular(folder / "stdout")
        and raw_blob(proof["process"]["stderr"]) == regular(folder / "stderr"),
        "Complete installed post-reap streams differ from their raw sidecars.",
    )
    require(
        equal(
            validate_bridge(
                proof["bridge"], proof["process"], expected, phase, workspace, folder
            ),
            proof["ui"],
        ),
        "Installed UI differs from the separately owned host response.",
    )
    query = proof["version_command"]
    require(
        equal(query, json_value(regular(folder / "version-command.json", 2_000_000))),
        "Actual version process observation differs from its retained sidecar.",
    )
    require(
        type(query) is dict
        and set(query) == {"argv", "pid", "exit_code", "reaped", "stdout", "stderr"}
        and equal(query["argv"], ["/opt/neuroforge/sinter/Sinter", "--version"])
        and type(query["exit_code"]) is int
        and type(query["pid"]) is int
        and query["pid"] > 1
        and query["pid"] != proof["process"]["pid"]
        and query["exit_code"] == 0
        and query["reaped"] is True
        and raw_blob(query["stdout"]) == (version + "\n").encode()
        and raw_blob(query["stderr"]) == b"",
        "Actual executable version differs.",
    )
    validate_views(proof, expected, phase, folder)


def validate_views(proof, expected, phase, folder):
    """Typed API and visible-content checks; process admission stays separate."""
    version = expected["prior_version"] if phase.startswith("prior") else VERSION
    tree_entries(folder)
    rows = proof["api"]
    require(
        type(rows) is list and 8 <= len(rows) <= 450,
        "Bounded complete HTTP observations required.",
    )
    parsed = []
    for row in rows:
        require(
            type(row) is dict
            and set(row)
            == {"name", "method", "path", "capabilities", "body", "status", "response"}
            and type(row["status"]) is int
            and type(row["capabilities"]) is list,
            "Actual HTTP observation fields or types differ.",
        )
        body = raw_blob(row["body"], 2_000_000)
        value = json_value(raw_blob(row["response"], 2_000_000))
        require(
            row["method"] == ("POST" if body else "GET"), "Actual HTTP method differs."
        )
        if row["status"] == 400:
            require(
                type(value) is dict
                and set(value) == {"error"}
                and type(value["error"]) is str
                and value["error"],
                "Refusal explanation is absent.",
            )
        parsed.append((row, json_value(body) if body else None, value))

    def take(name, path, body=None, capabilities=(), status=200):
        require(parsed, "Required HTTP observation is missing.")
        row, actual_body, value = parsed.pop(0)
        require(
            row["name"] == name
            and row["path"] == path
            and equal(body, actual_body)
            and equal(row["capabilities"], list(capabilities))
            and row["status"] == status,
            "Actual request identity/capability/order/status differs: " + name,
        )
        return value

    session = take("session", "/api/session")
    require(
        session.get("version") == version
        and session.get("desktop") is True
        and type(session.get("token")) is str
        and session["token"],
        "Actual owned session differs.",
    )
    settings = take("settings", "/api/settings")
    subset(expected["settings"], settings["settings"])
    require(
        settings.get("has_session_key") is False
        and settings.get("environment_override", False) is False
        and settings.get("warning") == "",
        "Settings silently fell back or inherited caller state.",
    )
    campaign_view = take("campaign", "/api/campaigns/" + expected["campaign"]["id"])
    subset(expected["campaign"], campaign_view)
    for action in campaign_view["document"]["actions"]:
        require(
            action.get("owner_confirmed", False) is False,
            "An unconfirmed owner was promoted by the installed reader.",
        )
    for opportunity in campaign_view["document"]["opportunities"]:
        require(
            opportunity.get("application_window", "unknown") == "unknown"
            and opportunity.get("applicant_confirmed", False) is False,
            "Unknown dates or an unconfirmed applicant were promoted.",
        )
    scoped = "scoped_casebook" in expected
    books = (
        [("plain", expected["plain_casebook"]), ("scoped", expected["scoped_casebook"])]
        if scoped
        else [("plain", expected["casebook"])]
    )
    for name, book in books:
        book_view(
            book,
            take(
                name,
                "/api/casebooks/" + book["id"],
                capabilities=("sinter-casebook/v2",) if name == "scoped" else (),
            ),
        )
    reports = (
        [(row["report_id"], row["stored_report"]) for row in expected["raw_reports"]]
        if scoped
        else [(expected["report_id"], expected["report"])]
    )
    for index, (identifier, report) in enumerate(reports):
        subset(report, take("report-" + str(index), "/api/reports/" + identifier))
    listing = take("reports", "/api/reports")
    require(
        {row["id"] for row in listing["reports"]} == {row[0] for row in reports},
        "Installed saved history list changed.",
    )
    watches = take("watches", "/api/watches")
    subset([expected["watch"]], watches["watches"])
    require(
        type(watches["watches"][0]["enabled"]) is int
        and watches["watches"][0]["enabled"] == 0,
        "A retained SQLite watch was enabled or its integer type changed.",
    )
    require(
        equal(take("jobs", "/api/jobs"), {"jobs": []}),
        "Opening retained work queued work.",
    )
    if phase.endswith("protocol"):
        require(
            equal(take("jobs-before", "/api/jobs"), {"jobs": []}),
            "Protocol started with queued work.",
        )
        book = expected["scoped_casebook"] if scoped else expected["casebook"]
        work = {"id": book["id"], "revision": book["revision"]}
        path = "/api/casebooks/" + book["id"]
        capability = ("sinter-casebook/v2",) if scoped else ()
        if scoped:
            for name, caps in (
                ("missing", ()),
                ("wrong", ("sinter-casebook/v1",)),
                ("duplicate", ("sinter-casebook/v2", "sinter-casebook/v2")),
            ):
                take("read-" + name, path, capabilities=caps, status=400)
            book_view(book, take("read-capable", path, capabilities=capability))
            body = {"document": book["document"]}
            take("validate-missing", "/api/casebooks/validate", body, status=400)
            require(
                equal(
                    take(
                        "validate-capable", "/api/casebooks/validate", body, capability
                    ),
                    body,
                ),
                "Capable backup validation changed explicit selections.",
            )
            broad = {
                key: value
                for key, value in book["document"].items()
                if key not in {"question_scopes", "fingerprint"}
            }
            broad["schema"] = "sinter-casebook/v1"
            take(
                "old-reader-save",
                "/api/casebooks/save",
                {**work, "document": broad},
                status=400,
            )
            for name, route, caps in (
                ("build-missing", "build", ()),
                ("draft-missing", "draft", ()),
                ("draft-without-consent", "draft", capability),
            ):
                take(name, "/api/casebooks/" + route, work, caps, 400)
            require(
                equal(take("jobs-after-refusals", "/api/jobs"), {"jobs": []}),
                "Refused requests queued work.",
            )
        queued = take("source-build", "/api/casebooks/build", work, capability, 202)
        require(
            type(queued.get("id")) is str and queued["id"],
            "Source-only job identity absent.",
        )
        completed = None
        while parsed and parsed[0][0]["name"] == "source-job":
            completed = take("source-job", "/api/jobs/" + queued["id"])
            require(
                completed["status"] in {"queued", "running", "done"},
                "Source-only job failed.",
            )
        require(
            completed is not None and completed["status"] == "done",
            "Source-only job did not finish.",
        )
        result = completed["result"]
        if scoped:
            questions = result["question_index"]
            require(
                len(questions) == 3
                and equal(
                    questions[0]["source_scope"]["source_ids"],
                    book["document"]["question_scopes"][0]["source_ids"],
                )
                and questions[1]["source_scope"]["source_ids"] == []
                and questions[1]["excerpt_ids"] == []
                and questions[2]["source_scope"]["mode"] == "all",
                "Selected, deliberately empty or default-all source choices changed.",
            )
        else:
            require(
                result["coverage"]["documents_supplied"] == 1
                and expected["source_text"] in result["markdown"],
                "Original source-only work changed.",
            )
        book_view(book, take("read-after-protocol", path, capabilities=capability))
    require(
        equal(take("quit", "/api/desktop/quit", {}), {"ok": True}) and not parsed,
        "Actual normal quit is absent or unexpected HTTP work occurred.",
    )
    visual = proof["ui"]
    require(
        type(visual) is dict
        and set(visual)
        == {"visible", "screenshots", "page_errors", "external_requests", "resources"}
        and visual["page_errors"] == visual["external_requests"] == [],
        "UI errors or external requests occurred.",
    )
    require(
        equal(
            visual["resources"],
            {"context_pages_after_close": 0, "browser_connected_after_close": False},
        ),
        "Private host browser or context remains open.",
    )
    visible = visual["visible"]
    bodies = visible.get("report_bodies")
    require(
        type(bodies) is list and len(bodies) == len(reports),
        "Actual visible saved document bodies are missing.",
    )
    for index, (_identifier, report) in enumerate(reports):
        text = visible["report-" + str(index)]
        report_text(report, text)
        body = bodies[index]
        require(
            type(body) is dict
            and set(body) == {"report_id", "text", "visible"}
            and body["report_id"] == _identifier
            and body["visible"] is True,
            "Actual saved document body is hidden or belongs to another report.",
        )
        report_text(report, body["text"], include_title=False)
    require(
        type(visible.get("casebook")) is str
        and "Opening your workspace..." not in visible["casebook"]
        and type(visible.get("campaign")) is str
        and "Opening your workspace..." not in visible["campaign"]
        and expected["campaign"]["document"]["title"] in visible["campaign"],
        "UI was observed before retained content became visible.",
    )
    if scoped:
        require(
            equal(visible.get("scope_modes"), ["selected", "selected", "all"]),
            "UI broadened saved choices.",
        )
        require(
            equal(
                visible.get("scope_checks"),
                [
                    {
                        "question_index": question,
                        "source_id": row["id"],
                        "checked": row["id"]
                        in expected["scoped_casebook"]["document"]["question_scopes"][
                            question
                        ]["source_ids"],
                        "visible": True,
                    }
                    for question in (0, 1)
                    for row in expected["scoped_casebook"]["document"]["documents"]
                ],
            ),
            "Actual visible source controls differ from saved selections.",
        )
    campaign = expected["campaign"]["document"]
    visible_campaign_semantics(visible, campaign, version)
    if version != "0.5.3":
        require(
            equal(
                visible.get("owner_types"),
                [row["owner_kind"] for row in campaign["actions"]],
            )
            and equal(
                visible.get("owner_acceptance"), [False] * len(campaign["actions"])
            ),
            "Actual owner controls confirmed an unknown or unassigned owner.",
        )
        require(
            "this excerpt was checked 2026-09-12" in visible["campaign"]
            and "linked source record is now dated 2026-09-29" in visible["campaign"],
            "Actual stale-source warning was not visible.",
        )
    require(
        type(visual["screenshots"]) is list
        and len(visual["screenshots"]) == len(reports) + 2,
        "Actual screenshots are incomplete.",
    )
    require(
        {image.get("name") for image in visual["screenshots"]}
        == {
            "campaign.png",
            "actions.png",
            *[f"report-{i}.png" for i in range(len(reports))],
        },
        "Actual screenshot roles are duplicated or missing.",
    )
    for image in visual["screenshots"]:
        require(
            type(image) is dict
            and set(image) == {"name", "bytes", "sha256"}
            and type(image["name"]) is str
            and re.fullmatch(r"(?:report-[0-9]+|campaign|actions)\.png", image["name"]),
            "Screenshot artifact identity differs.",
        )
        raw = regular(folder / image["name"], 2_000_000)
        require(
            type(image["bytes"]) is int
            and image["bytes"] == len(raw)
            and image["sha256"] == sha(raw)
            and raw.startswith(b"\x89PNG\r\n\x1a\n"),
            "Actual screenshot bytes differ.",
        )


def validate_filesystem(receipt, package, prior_payload, folder):
    tree_entries(folder)
    from tools.rc4_replacement import FILESYSTEM_PROGRAM

    rows = receipt["filesystem_commands"]
    phases = ("initial", "prior", "candidate", "removed")
    paths = {
        "/opt/neuroforge/sinter/Sinter",
        "/usr/share/applications/sinter.desktop",
        "/usr/share/applications/sinter-native.desktop",
    }
    require(
        type(rows) is list
        and len(rows) == 4
        and set(receipt["filesystem"]) == set(phases),
        "Four actual filesystem observations are required.",
    )
    for row, phase in zip(rows, phases):
        require(
            type(row) is dict
            and set(row)
            == {"role", "argv", "pid", "exit_code", "reaped", "stdout", "stderr"}
            and row["role"] == phase
            and equal(
                row["argv"], ["python3", "-I", "-S", "-B", "-c", FILESYSTEM_PROGRAM]
            )
            and type(row["pid"]) is int
            and row["pid"] > 1
            and row["reaped"] is True
            and type(row["exit_code"]) is int
            and row["exit_code"] == 0
            and raw_blob(row["stderr"]) == b"",
            "Actual filesystem command identity differs.",
        )
        observed = json_value(raw_blob(row["stdout"]))
        command_sidecars(row, folder)
        require(
            equal(observed, receipt["filesystem"][phase]) and set(observed) == paths,
            "Actual raw filesystem response differs.",
        )
        for path, value in observed.items():
            if phase in {"initial", "removed"} or (
                phase == "prior"
                and path.endswith("sinter-native.desktop")
                and "sinter-native.desktop" not in prior_payload["entries"]
            ):
                require(
                    equal(value, {"exists": False, "errno": 2}),
                    "Actual filesystem absence is not proven.",
                )
            else:
                require(
                    type(value) is dict
                    and set(value) == {"exists", "mode", "bytes", "sha256"}
                    and value["exists"] is True
                    and type(value["mode"]) is int
                    and stat.S_ISREG(value["mode"])
                    and type(value["bytes"]) is int
                    and value["bytes"] > 0
                    and type(value["sha256"]) is str
                    and re.fullmatch("[0-9a-f]{64}", value["sha256"]),
                    "Installed path is not an actual bounded regular file.",
                )
                if path.endswith("/Sinter"):
                    expected = prior_payload if phase == "prior" else package
                    require(
                        value["sha256"] == expected["binary_sha256"]
                        and value["bytes"] == expected["binary_bytes"],
                        "Installed executable payload differs.",
                    )
                else:
                    entry = (prior_payload if phase == "prior" else package)["entries"][
                        Path(path).name
                    ]
                    require(
                        value["sha256"] == entry["sha256"]
                        and value["bytes"] == entry["bytes"],
                        "Installed desktop entry differs from actual package/source.",
                    )


def prior_metadata(rows, prior, payload, folder):
    from tools.package_native import debian_package_version

    fields = (
        ("Package", "sinter"),
        ("Architecture", "amd64"),
        ("Version", debian_package_version(prior["version"])),
    )
    require(
        type(rows) is list and len(rows) == 4,
        "Complete actual prior payload observations required.",
    )
    installer = "/prior/Sinter-" + prior["version"] + "-linux-x64.deb"
    for index, row in enumerate(rows):
        require(
            type(row) is dict
            and set(row)
            == {"role", "argv", "pid", "exit_code", "reaped", "stdout", "stderr"}
            and type(row["pid"]) is int
            and row["pid"] > 1
            and row["reaped"] is True
            and type(row["exit_code"]) is int
            and row["exit_code"] == 0
            and raw_blob(row["stderr"]) == b"",
            "Prior payload command failed or was not reaped.",
        )
        if index < 3:
            field, value = fields[index]
            require(
                row["role"] == "control-" + field
                and equal(row["argv"], ["dpkg-deb", "-f", installer, field])
                and raw_blob(row["stdout"]) == (value + "\n").encode(),
                "Actual prior Package/Architecture/Version differs.",
            )
        else:
            require(
                row["role"] == "payload"
                and equal(row["argv"], ["dpkg-deb", "--fsys-tarfile", installer])
                and equal(
                    row["stdout"],
                    {
                        "name": "payload.stdout",
                        "bytes": payload["payload_bytes"],
                        "sha256": payload["payload_sha256"],
                    },
                ),
                "Complete actual prior payload stream identity differs.",
            )
            raw = regular(folder / "prior-payload/payload.stdout")
            require(
                len(raw) == payload["payload_bytes"]
                and sha(raw) == payload["payload_sha256"],
                "Complete prior payload differs from independently read DEB.",
            )


def validate_inner(receipt, folder, source, package, prior, prior_payload):
    from tools.package_native import debian_package_version
    from tools.rc4_replacement import empty_schema

    require(
        type(receipt) is dict
        and set(receipt)
        == {
            "schema",
            "failure",
            "cleanup_failure",
            "package_commands",
            "probes",
            "snapshots",
            "filesystem",
            "filesystem_commands",
            "source",
            "package",
            "prior",
            "prior_payload",
            "prior_metadata",
            "fixture",
            "expected",
            "original_hashes",
            "empty_schema",
            "original_hashes_after",
            "prior_inputs_after",
            "candidate_source_after",
        }
        and receipt["schema"] == SCHEMA
        and receipt["failure"] is None,
        "Require the distinct complete installed replacement receipt, without failure.",
    )
    require(receipt["cleanup_failure"] is None, "Actual cleanup failed.")
    for key, value in (
        ("source", source),
        ("candidate_source_after", source),
        ("package", package),
        ("prior", prior),
        ("prior_inputs_after", prior),
        ("prior_payload", prior_payload),
    ):
        require(
            equal(receipt[key], value),
            "Independently read input identity differs: " + key,
        )
    package_commands(
        receipt["package_commands"],
        debian_package_version(prior["version"]),
        "0.5.4~rc4",
        "/prior/Sinter-" + prior["version"] + "-linux-x64.deb",
        "/candidate/Sinter-0.5.4rc4-linux-x64.deb",
        folder / "commands",
    )
    validate_filesystem(receipt, package, prior_payload, folder / "fs")
    prior_metadata(receipt["prior_metadata"], prior, prior_payload, folder)
    e_profile = prior["version"] == "0.5.4rc3"
    original_name = "original-E-workspace" if e_profile else "original"
    copy_name = "copied-for-eventual-replacement" if e_profile else "replacement-copy"
    original = folder / "fixture" / original_name
    copied = folder / "fixture" / copy_name
    expected_path = (
        folder
        / "fixture"
        / ("fixture-originals.json" if e_profile else "expected.json")
    )
    expected = json_value(regular(expected_path, 2_000_000))
    require(
        equal(receipt["expected"], expected)
        and expected["prior_version"] == prior["version"],
        "Actual published-source fixture originals differ.",
    )
    require(
        equal(receipt["original_hashes"], hashes(original))
        and equal(receipt["original_hashes_after"], hashes(original)),
        "Original fixture file bytes changed during replacement or inspection.",
    )
    if e_profile:
        from tools import published_rc3_fixture

        fixture_observation = json_value(
            regular(folder / "fixture/fixture-preparation.json", 2_000_000)
        )
        require(
            equal(receipt["fixture"], fixture_observation)
            and fixture_observation["schema"] == "sinter-published-rc3-fixture/v1"
            and fixture_observation["fixture_created"] is True
            and all(
                fixture_observation[key] is False
                for key in (
                    "candidate_admitted",
                    "candidate_tested",
                    "prior_binary_tested",
                    "package_replacement_tested",
                )
            )
            and fixture_observation["prior_version"] == prior["version"]
            and fixture_observation["prior_source_commit"] == prior["commit"]
            and fixture_observation["prior_source_archive_sha256"]
            == prior["source_archive_sha256"]
            and fixture_observation["prior_installer_sha256"]
            == prior["installer_sha256"]
            and equal(fixture_observation["prior_source_hashes"], prior["source_files"])
            and equal(fixture_observation["original_fixture_hashes"], hashes(original))
            and equal(fixture_observation["copied_fixture_hashes"], hashes(original))
            and fixture_observation["fixture_originals_sha256"]
            == sha(regular(expected_path))
            and equal(
                fixture_observation["source_protocol_checks"],
                expected["source_protocol_checks"],
            )
            and fixture_observation["replacement_fixture_profile"] == VERSION
            and fixture_observation["target"] == "linux-x64"
            and fixture_observation["producer_sha256"]
            == sha(regular(Path(published_rc3_fixture.__file__)))
            and fixture_observation["seed_sha256"]
            == sha(
                regular(
                    Path(published_rc3_fixture.__file__).with_name(
                        "published_rc3_fixture_seed.py"
                    )
                )
            ),
            "Published-E fixture meaning, original data or source identity changed.",
        )
    else:
        require(
            equal(
                receipt["fixture"],
                {"scope": "fictional published-source seed; no installed admission"},
            ),
            "Older source fixture was relabelled as installed evidence.",
        )
    before = snapshot(original)
    require(
        equal(receipt["snapshots"]["before"], before),
        "Raw original persistent snapshot differs.",
    )
    require(
        set(receipt["snapshots"]) == {"before", *PHASES}
        and set(receipt["probes"]) == set(PHASES),
        "Prior, candidate, cold reopen and protocol observations are required.",
    )
    require(
        len({receipt["probes"][phase]["process"]["pid"] for phase in PHASES})
        == len(PHASES),
        "A process observation cannot substitute for a fresh cold reopen.",
    )
    import tempfile

    with tempfile.TemporaryDirectory(prefix="replacement-verifier-") as temporary:
        actual_schema = empty_schema(Path(temporary))
    require(
        equal(receipt["empty_schema"], actual_schema),
        "Empty schema was not derived from exact candidate source.",
    )
    preserve(before, receipt["snapshots"]["prior"], before["databases"])
    for phase in PHASES:
        preserve(
            before,
            receipt["snapshots"][phase],
            before["databases"] if phase.startswith("prior") else actual_schema,
        )
        protocol = phase.endswith("protocol")
        workspace = (
            Path("/out/run") / (phase + "-workspace")
            if protocol
            else Path("/out/run/fixture") / copy_name
        )
        binary = prior_payload if phase.startswith("prior") else package
        validate_probe(
            receipt["probes"][phase],
            expected,
            phase,
            workspace,
            binary["binary_sha256"],
            folder / phase,
        )
    require(
        equal(snapshot(copied), receipt["snapshots"]["candidate-cold"]),
        "Actual cold-reopened persistent files differ from their retained observation.",
    )
    for phase in ("prior-protocol", "candidate-protocol"):
        require(
            equal(
                snapshot(folder / (phase + "-workspace")), receipt["snapshots"][phase]
            ),
            "Actual disposable protocol copy differs.",
        )
    return {
        "prior_version": prior["version"],
        "prior_commit": prior["commit"],
        "candidate_version": VERSION,
        "source_commit": source["commit"],
        "prior_installer_sha256": prior["installer_sha256"],
        "candidate_installer_sha256": package["installer_sha256"],
        "preserved_preferences_sha256": before["preferences_sha256"],
    }


def verify(args):
    """Read package/source bytes and each separately pinned actual outer owner."""
    shared_contract, owner = shared()
    private_paths(args, Path(__file__).resolve().parents[1])
    require(
        type(args.outer_owner_sha256) is str
        and re.fullmatch("[0-9a-f]{64}", args.outer_owner_sha256)
        and sha(regular(args.outer_owner_file, 2_000_000)) == args.outer_owner_sha256,
        "A separately reviewed exact outer owner file pin is required.",
    )
    source = owner.source_identity(args.repository, args.source_commit, [])
    require(
        (args.owned_root / "t").is_dir() and not any((args.owned_root / "t").iterdir()),
        "Actual private host browser temporary resources remain or are missing.",
    )
    require(
        source["version"] == VERSION, "Only exact committed final RC4 can be admitted."
    )
    args.installer = args.candidate / "Sinter-0.5.4rc4-linux-x64.deb"
    args.package_receipt = args.candidate / "Sinter-0.5.4rc4-linux-x64-test.json"
    package = owner.package_preflight(args, source, [])
    require(
        {path.name for path in args.candidate.iterdir()}
        == {args.installer.name, args.package_receipt.name},
        "Candidate mount has unadmitted inputs.",
    )
    require(
        sha(regular(Path(__file__).with_name("rc4_replacement.py")))
        == args.outer_owner_sha256,
        "Pinned outer owner does not match the byte-admitted candidate source.",
    )
    matrix = json_value(regular(args.output / "matrix.json", 16_000_000))
    require(
        type(matrix) is dict
        and set(matrix) == {"schema", "scope", "source", "package", "runs"}
        and matrix["schema"] == MATRIX_SCHEMA
        and equal(matrix["source"], source)
        and equal(matrix["package"], package)
        and set(matrix["runs"]) == set(PRIORS),
        "Require all four exact prior replacements of one identical candidate.",
    )
    stage = args.output / "staging"
    observed_source = owner.archive_source_identity(stage, args.source_commit, [])
    require(
        equal(observed_source, source),
        "Mounted source archive differs from actual Git rearchive.",
    )
    from tools.rc4_replacement import payload, prior_inputs

    results, identifiers = [], set()
    for version in PRIORS:
        folder = args.output / version
        require(
            equal(
                matrix["runs"][version],
                {
                    "outer": str(folder / "outer.json"),
                    "inner": str(folder / "run/replacement.json"),
                },
            ),
            "Matrix receipt path differs from its exact owned output.",
        )
        prior, _archive, installer = prior_inputs(args.priors / version, version)
        import tempfile

        with tempfile.TemporaryDirectory(prefix="replacement-payload-") as temporary:
            prior_payload, _metadata = payload(installer, version, Path(temporary))
        pins = {
            "image_id": args.image_id,
            "source_commit": args.source_commit,
            "source_directory": str(Path(__file__).resolve().parents[1]),
            "repository": str(stage.resolve()),
            "prior_directory": str((args.priors / version).resolve()),
            "candidate_directory": str(args.candidate.resolve()),
            "output_directory": str(folder.resolve()),
            "prior_version": version,
        }
        outer = json_value(regular(folder / "outer.json", 16_000_000))
        require(
            type(outer) is dict
            and set(outer)
            == {
                "schema",
                "owner_sha256",
                "pins",
                "commands",
                "failure",
                "cleanup_failure",
                "host",
                "collectors",
            }
            and outer["schema"] == "sinter-rc4-replacement-owner/v2"
            and outer["failure"] is None
            and outer["cleanup_failure"] is None
            and outer["owner_sha256"] == args.outer_owner_sha256
            and equal(outer["pins"], pins),
            "Actual outer owner/input mount identity differs.",
        )
        host_tools.validate_host_pair(outer["host"])
        require(
            equal(
                outer["host"]["before"],
                host_identity(args.chromium, args.owned_root / "t"),
            ),
            "Private actual host collector/browser runtime identity differs.",
        )
        owned = shared_contract.validate_lifecycle(
            outer["commands"], pins, outer_argv, MOUNTS
        )
        outer_sidecars(outer["commands"], folder)
        require(
            owned["container_id"] not in identifiers
            and owned["start_stdout"]
            == (
                b"Replacement observations retained; "
                b"run the independent replacement contract.\n"
            ),
            "Owning process output differs or a container was reused.",
        )
        identifiers.add(owned["container_id"])
        inner = json_value(regular(folder / "run/replacement.json", 16_000_000))
        validate_collectors(
            outer["collectors"],
            folder,
            args.chromium,
            inner["probes"],
            args.owned_root / "t",
        )
        results.append(
            {
                "container_id": owned["container_id"],
                **validate_inner(
                    inner, folder / "run", source, package, prior, prior_payload
                ),
            }
        )
    return {
        "schema": "sinter-installed-rc4-replacement-admission/v1",
        "scope": "four Linux installed replacements only",
        "source_commit": source["commit"],
        "candidate_installer_sha256": package["installer_sha256"],
        "replacements": results,
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "repository",
        "candidate",
        "priors",
        "output",
        "outer-owner-file",
        "owned-root",
        "chromium",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("source-commit", "image-id", "outer-owner-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(args)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        parser.exit(1, "Installed replacement admission refused: " + str(exc) + "\n")
    print(encoded(result))


if __name__ == "__main__":
    main()
