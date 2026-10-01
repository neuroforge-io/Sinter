"""Closed admission for installed native-entry/v2; never an RC4 release gate.

The outer bundle must come from a separately reviewed owning Docker producer.
This module reads evidence and DEB metadata; it never installs or launches Sinter.
No outer owning producer is supplied by this source precursor.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from sinter.campaigns import CampaignStore  # noqa: E402
from sinter.casebooks import Casebooks, validate  # noqa: E402
from sinter.store import Store  # noqa: E402
from tools import installed_native_menu as owner  # noqa: E402
from tools import native_window_smoke as native  # noqa: E402
from tools.installed_native_tk import FIXTURE  # noqa: E402
from tools.installed_workflow_qualification import json_object  # noqa: E402

ROLES = (
    "image",
    "create",
    "created",
    "start",
    "exited",
    "remove",
    "removed",
)
NATIVE = ["/opt/neuroforge/sinter/Sinter", "app", "--mode", "native"]
VERSION_QUERY = ["dpkg-query", "-W", "-f=${Status}\n${Version}\n", "sinter"]
STATUS_QUERY = ["dpkg-query", "-W", "-f=${Status}", "sinter"]
ABSENT = b"dpkg-query: no packages found matching sinter\n"
# dpkg retains the shared /opt parent containing the qualification interpreter.
# Only this exact observed warning is accepted, and only for Sinter removal.
SHARED_OPT_REMOVAL_WARNING = (
    b"dpkg: warning: while removing sinter, directory '/opt' not empty so not removed\n"
)
OUTER_SCHEMA = "sinter-owned-native-entry-container/v1"
INNER_SCHEMA = "sinter-installed-native-entry-test/v2"
ARCHIVE_INNER_SCHEMA = owner.ARCHIVE_INNER_SCHEMA
ARCHIVE_OUTER_SCHEMA = "sinter-owned-native-entry-archive-container/v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact(actual, expected, message):
    require(native.same_json(actual, expected), message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def full_bytes(record):
    """Decode a complete original file; prefixes cannot substitute for originals."""
    require(
        type(record) is dict and set(record) == {"bytes", "sha256", "base64"},
        "Use complete original bytes.",
    )
    try:
        raw = base64.b64decode(record["base64"], validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("Original byte encoding is invalid.") from error
    require(
        type(record["bytes"]) is int
        and record["bytes"] == len(raw)
        and record["sha256"] == sha(raw),
        "Original byte count or hash differs.",
    )
    require(len(raw) <= 128_000, "Original fictional bytes exceed their bound.")
    return raw


def stream_bytes(record, *, complete=True):
    """Validate full counts/hashes plus exact bounded original stream samples."""
    require(
        type(record) is dict
        and set(record) == {"text", "base64", "bytes", "sha256", "truncated"},
        "Stream fields are incomplete or unknown.",
    )
    try:
        sample = base64.b64decode(record["base64"], validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("Stream sample encoding is invalid.") from error
    size = record["bytes"]
    require(
        type(size) is int and 0 <= size <= 128 * 1024 * 1024,
        "Stream size is outside its bound.",
    )
    require(
        type(record["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", record["sha256"]),
        "Use a complete stream hash.",
    )
    require(len(sample) == min(size, 65_536), "Stream prefix size differs.")
    exact(record["truncated"], size > 65_536, "Stream truncation identity differs.")
    exact(
        record["text"],
        sample.decode("utf-8", errors="replace"),
        "Stream text differs from its original sample.",
    )
    if size == len(sample):
        require(record["sha256"] == sha(sample), "Complete stream hash differs.")
    require(
        not complete or not record["truncated"],
        "A bounded prefix cannot replace the required complete stream.",
    )
    return sample


def quiet(record):
    require(
        stream_bytes(record) == b"", "Qualification emitted unexpected stream bytes."
    )


def stopped(row, *, signal_expected=None, expected_exit=0):
    require(
        type(row) is dict and type(row.get("pid")) is int and row["pid"] > 0,
        "Use an actual owned process identity.",
    )
    exact(row.get("exit_code"), expected_exit, "Owned child did not exit as required.")
    exact(
        row.get("owned_group_remaining"),
        False,
        "Owned process group remains or was not observed.",
    )
    require(
        row.get("forced_cleanup", False) is False,
        "Forced child cleanup cannot qualify.",
    )
    require(
        not any("error" in key for key in row),
        "A retained process failure cannot qualify.",
    )
    if signal_expected is not None:
        exact(
            row.get("sigterm_sent", False),
            signal_expected,
            "Owned signal journey differs.",
        )


def legacy_stderr(row):
    quiet(
        {
            key: row["stderr" if key == "text" else "stderr_" + key]
            for key in ("text", "base64", "bytes", "sha256", "truncated")
        }
    )


def outer_argv(pins, name):
    """One explicit future owner invocation, without inherited host resources."""
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
    for host, destination, readonly in (
        (pins["source_directory"], "/source", True),
        (pins["repository"], "/repository", True),
        (pins["candidate_directory"], "/candidate", True),
        (pins["output_directory"], "/out", False),
    ):
        argv += [
            "--mount",
            "type=bind,src="
            + host
            + ",dst="
            + destination
            + (",readonly" if readonly else ""),
        ]
    argv += [
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "TMPDIR=/out",
        "--env",
        "GIT_CONFIG_COUNT=1",
        "--env",
        "GIT_CONFIG_KEY_0=safe.directory",
        "--env",
        "GIT_CONFIG_VALUE_0=/repository",
        pins["image_id"],
    ]
    result = argv + [
        "python3",
        "-B",
        "/source/tools/installed_native_menu.py",
        "--repository",
        "/repository",
        "--source-commit",
        pins["source_commit"],
        "--installer",
        "/candidate/" + pins["installer_name"],
        "--package-receipt",
        "/candidate/" + pins["package_receipt_name"],
        "--output",
        "/out/native-entry",
    ]
    route = pins.get("source_route", "git")
    require(route in {"git", "archive"}, "Unsupported source route override.")
    return result + (["--source-route", "archive"] if route == "archive" else [])


def validate_outer(bundle, pins):
    """Derive isolation, image, actual exit and removal from raw Docker output."""
    require(
        type(bundle) is dict
        and set(bundle) == {"schema", "owner_sha256", "artifacts", "commands"},
        "Require the complete separate outer owning bundle.",
    )
    exact(
        bundle["schema"],
        ARCHIVE_OUTER_SCHEMA
        if pins.get("source_route", "git") == "archive"
        else OUTER_SCHEMA,
        "Unknown outer ownership contract.",
    )
    exact(
        bundle["owner_sha256"],
        pins["outer_owner_sha256"],
        "Outer owner differs from the independently reviewed pin.",
    )
    exact(
        bundle["artifacts"],
        pins["artifacts"],
        "Outer artifact identities differ from actual input files.",
    )
    result = _validate_lifecycle(bundle["commands"], pins, outer_argv)
    require(result["start_stdout"] == b"", "Installed outer owner start must be quiet.")
    return result["container_id"]


DEFAULT_MOUNT_SPEC = (
    ("source_directory", "/source", False),
    ("repository", "/repository", False),
    ("candidate_directory", "/candidate", False),
    ("output_directory", "/out", True),
)


def private_mounts(pins, mount_spec=None):
    """The trusted caller supplies its fixed map; evidence cannot select mounts."""
    spec = DEFAULT_MOUNT_SPEC if mount_spec is None else mount_spec
    require(
        type(spec) is tuple
        and 1 <= len(spec) <= 8
        and all(
            type(row) is tuple
            and len(row) == 3
            and type(row[0]) is str
            and type(row[1]) is str
            and type(row[2]) is bool
            for row in spec
        ),
        "Fixed caller mount specification is invalid.",
    )
    require(
        len({row[0] for row in spec}) == len(spec)
        and len({row[1] for row in spec}) == len(spec),
        "Fixed mount keys/destinations must be distinct.",
    )
    trees = [PurePosixPath(pins[key]) for key, _destination, _rw in spec]
    require(
        all(
            path.is_absolute() and ".." not in path.parts and str(path) == pins[key]
            for path, (key, _dst, _rw) in zip(trees, spec)
        ),
        "Use exact absolute private mount paths.",
    )
    require(
        all(
            left != right
            and not left.is_relative_to(right)
            and not right.is_relative_to(left)
            for index, left in enumerate(trees)
            for right in trees[index + 1 :]
        ),
        "Mounted private trees must be pairwise distinct and disjoint.",
    )
    return sorted(
        [
            {"Type": "bind", "Source": pins[key], "Destination": destination, "RW": rw}
            for key, destination, rw in spec
        ],
        key=lambda row: row["Destination"],
    )


def _validate_lifecycle(rows, pins, creation_argv):
    return validate_lifecycle(rows, pins, creation_argv)


def validate_lifecycle(rows, pins, creation_argv, mount_spec=None):
    """Shared strict raw seven-role checks; trusted callers fix argv/mount policy."""
    private_mounts(pins, mount_spec)
    require(
        type(rows) is list and len(rows) == len(ROLES),
        "Require every raw outer lifecycle observation.",
    )
    bodies = []
    for role, row in zip(ROLES, rows):
        require(
            type(row) is dict
            and set(row) == {"role", "argv", "exit_code", "stdout", "stderr", "reaped"},
            "Outer command evidence is incomplete or unknown.",
        )
        exact(row["role"], role, "Outer lifecycle order differs.")
        exact(row["reaped"], True, "Outer stream was observed before command reap.")
        require(type(row["exit_code"]) is int, "Outer exit is not an integer.")
        bodies.append(stream_bytes(row["stdout"]))
        if role != "removed":
            exact(row["exit_code"], 0, "Outer lifecycle failed.")
            quiet(row["stderr"])
    image = validate_image(bodies[0], pins)
    identifier = bodies[1].decode("ascii").strip()
    require(
        re.fullmatch(r"[0-9a-f]{64}", identifier),
        "Docker create did not return a full container identity.",
    )
    require(
        bodies[1] == (identifier + "\n").encode(),
        "Actual create ID response is not exact.",
    )
    before, after = (
        json.loads(bodies[index], object_pairs_hook=lambda pairs: unique(pairs))
        for index in (2, 4)
    )
    require(
        type(before) is list
        and len(before) == 1
        and type(after) is list
        and len(after) == 1,
        "Require one actual pre/post container inspection.",
    )
    before, after = before[0], after[0]
    name = before.get("Name", "").removeprefix("/")
    require(
        re.fullmatch(r"sinter-native-entry-[a-z0-9]{12}", name),
        "Use a fresh owning container name.",
    )
    expected = (
        ["docker", "image", "inspect", pins["image_id"]],
        creation_argv(pins, name),
        ["docker", "inspect", identifier],
        ["docker", "start", "-a", identifier],
        ["docker", "inspect", identifier],
        ["docker", "rm", identifier],
        ["docker", "inspect", identifier],
    )
    for row, argv in zip(rows, expected):
        exact(row["argv"], argv, "Raw outer command identity differs.")
    validate_container_observation(
        before, pins, creation_argv, name, identifier, "created", mount_spec
    )
    validate_container_observation(
        after, pins, creation_argv, name, identifier, "exited", mount_spec
    )
    exact(
        after.get("Created"),
        before["Created"],
        "Created identity changed during ownership.",
    )
    validate_removal(rows[5], rows[6], identifier)
    return {"container_id": identifier, "start_stdout": bodies[3], "image": image}


def validate_removal(removal, absence, identifier):
    """Require original successful removal and the exact recognized ID absence."""
    exact(removal["exit_code"], 0, "Owned container removal failed.")
    exact(removal["reaped"], True, "Removal stream was observed before reap.")
    quiet(removal["stderr"])
    require(
        stream_bytes(removal["stdout"]) == (identifier + "\n").encode(),
        "Actual removal response differs.",
    )
    exact(absence["reaped"], True, "Absence stream was observed before reap.")
    exact(
        absence["exit_code"],
        1,
        "Removed container still exists or inspection was not attempted.",
    )
    require(
        stream_bytes(absence["stdout"]) == b"[]\n", "Actual absence stdout differs."
    )
    require(
        stream_bytes(absence["stderr"])
        in {
            (prefix + identifier + "\n").encode()
            for prefix in ("Error: No such object: ", "error: no such object: ")
        },
        "An arbitrary inspection failure cannot prove container removal.",
    )


def validate_image(raw, pins):
    image = json.loads(raw, object_pairs_hook=unique)
    require(type(image) is list and len(image) == 1, "Use one actual inspected image.")
    exact(
        {k: image[0].get(k) for k in ("Id", "Os", "Architecture")},
        {"Id": pins["image_id"], "Os": "linux", "Architecture": "amd64"},
        "Outer image platform or immutable identity differs.",
    )
    return image[0]


def validate_container_observation(
    observed, pins, creation_argv, name, identifier, phase, mount_spec=None
):
    """Check actual pre-start/post-reap raw identity with the same admission predicate."""
    require(
        type(observed) is dict and phase in {"created", "exited"},
        "Actual container observation is missing.",
    )
    command = creation_argv(pins, name)
    mounts = private_mounts(pins, mount_spec)
    exact(observed.get("Id"), identifier, "Inspected container identity differs.")
    exact(
        observed.get("Image"),
        pins["image_id"],
        "Inspected container image differs.",
    )
    config, host = observed.get("Config", {}), observed.get("HostConfig", {})
    exact(
        config.get("User"),
        "0:0",
        "Installed owner requires disposable container root.",
    )
    require(
        config.get("Entrypoint") is None and config.get("WorkingDir") == "/",
        "An inherited image entrypoint/work directory could replace the admitted owner.",
    )
    exact(
        config.get("Cmd"),
        command[command.index(pins["image_id"]) + 1 :],
        "Container executed another owner command.",
    )
    env = config.get("Env", [])
    allowed_env = {
        "PATH",
        "LANG",
        "LC_ALL",
        "TZ",
        "HOME",
        "PYTHONDONTWRITEBYTECODE",
        "TMPDIR",
        "DEBIAN_FRONTEND",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
    }
    require(
        type(env) is list
        and all(
            type(value) is str and value.split("=", 1)[0] in allowed_env
            for value in env
        )
        and len({value.split("=", 1)[0] for value in env}) == len(env),
        "Host display, workspace, credentials or unknown settings were inherited.",
    )
    require(
        "TMPDIR=/out" in env and "PYTHONDONTWRITEBYTECODE=1" in env,
        "Outer owner temp/source isolation differs.",
    )
    require(
        all(
            not value.startswith("DEBIAN_FRONTEND=")
            or value == "DEBIAN_FRONTEND=noninteractive"
            for value in env
        ),
        "Unexpected inherited package frontend.",
    )
    require(
        {
            "GIT_CONFIG_COUNT=1",
            "GIT_CONFIG_KEY_0=safe.directory",
            "GIT_CONFIG_VALUE_0=/repository",
        }.issubset(env),
        "Git source read must trust only the owned /repository, never a wildcard or host configuration.",
    )
    exact(host.get("NetworkMode"), "none", "Outer network was not disabled.")
    exact(host.get("Privileged"), False, "Privileged container cannot qualify.")
    exact(
        host.get("ReadonlyRootfs"),
        False,
        "Owner needs its disposable writable root for installation.",
    )
    exact(host.get("CapDrop"), ["ALL"], "Outer capability isolation differs.")
    exact(host.get("PidsLimit"), 64, "Outer process bound differs.")
    exact(
        host.get("SecurityOpt"),
        ["no-new-privileges"],
        "Outer privilege isolation differs.",
    )
    require(
        host.get("PidMode", "") == ""
        and host.get("IpcMode") == "private"
        and not host.get("Devices")
        and not host.get("VolumesFrom")
        and not host.get("Binds")
        and not host.get("PortBindings"),
        "Host namespaces, devices or extra resources were shared.",
    )
    actual_mounts = sorted(
        [
            {k: row.get(k) for k in ("Type", "Source", "Destination", "RW")}
            for row in observed.get("Mounts", [])
        ],
        key=lambda item: item["Destination"],
    )
    exact(
        actual_mounts,
        mounts,
        "Observed mounts differ from the four admitted private paths.",
    )

    exact(observed.get("Name"), "/" + name, "Owned container name changed.")
    exact(observed.get("Path"), "python3", "Actual container entry executable differs.")
    exact(
        observed.get("Args"),
        command[command.index(pins["image_id"]) + 2 :],
        "Actual container entry arguments differ.",
    )
    state = observed.get("State")
    require(type(state) is dict, "Actual Docker State is missing.")
    fields = (
        "Status",
        "Running",
        "Paused",
        "Restarting",
        "OOMKilled",
        "Dead",
        "Pid",
        "ExitCode",
        "Error",
    )
    exact(
        {key: state.get(key) for key in fields},
        {
            "Status": phase,
            "Running": False,
            "Paused": False,
            "Restarting": False,
            "OOMKilled": False,
            "Dead": False,
            "Pid": 0,
            "ExitCode": 0,
            "Error": "",
        },
        "Actual " + phase + " State types or values differ.",
    )
    created = docker_timestamp(observed.get("Created"))
    if phase == "created":
        exact(
            state.get("StartedAt"),
            "0001-01-01T00:00:00Z",
            "Created container already started.",
        )
        exact(
            state.get("FinishedAt"),
            "0001-01-01T00:00:00Z",
            "Created container already finished.",
        )
    else:
        started, finished = (
            docker_timestamp(state.get("StartedAt")),
            docker_timestamp(state.get("FinishedAt")),
        )
        require(
            created <= started <= finished,
            "Actual Docker lifecycle timestamps are out of order.",
        )
    return created


def docker_timestamp(value):
    """Parse Docker UTC RFC3339 timestamps, including nanoseconds on Python 3.10."""
    require(
        type(value) is str
        and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z",
            value,
        ),
        "Actual Docker UTC timestamp is missing or malformed.",
    )
    try:
        whole, _, fraction = value[:-1].partition(".")
        parsed = datetime.fromisoformat(whole + "+00:00")
    except ValueError as error:
        raise ValueError("Actual Docker UTC timestamp is invalid.") from error
    require(parsed.year >= 1970, "A zero Docker lifecycle timestamp cannot qualify.")
    return parsed, int(fraction.ljust(9, "0") or "0")


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate raw observation key.")
        result[key] = value
    return result


def process_evidence(observation, row, argv):
    require(
        type(observation) is dict
        and set(observation) == {"argv", "pid", "stdout", "stderr"},
        "Require separate full actual process evidence.",
    )
    exact(
        observation["argv"],
        argv,
        "Diagnostic/offline invocation belongs to another binary/workspace.",
    )
    require(
        type(observation["pid"]) is int and observation["pid"] > 0,
        "Actual diagnostic/offline PID is missing.",
    )
    if "pid" in row:
        exact(observation["pid"], row["pid"], "Diagnostic/offline stream PID differs.")
    for name in ("stdout", "stderr"):
        stream = observation[name]
        require(
            type(stream) is dict and set(stream) == {"complete", "exit_code", "record"},
            "Complete separate process stream fields are missing.",
        )
        exact(
            stream["complete"],
            True,
            "Diagnostic/offline streams were captured before reap.",
        )
        exact(stream["exit_code"], 0, "Diagnostic/offline stream exit differs.")
        stream_bytes(stream["record"])
    quiet(observation["stderr"]["record"])
    raw = stream_bytes(observation["stdout"]["record"])
    exact(
        row.get("stdout"),
        raw.decode("utf-8"),
        "Legacy diagnostic/offline text differs from complete original stream.",
    )
    return raw


def diagnostic(row, observed, version, observation):
    require(type(row) is dict, "Diagnostic legacy observation is missing.")
    raw = process_evidence(observation, row, [NATIVE[0], "--diagnose"])
    stopped({**row, "pid": observation["pid"]})
    legacy_stderr(row)
    exact(row.get("stdout_truncated"), False, "Diagnostic output was truncated.")
    actual = json_object(raw)
    for key, value in observed.items():
        exact(
            actual.get(key),
            value,
            "Diagnostic raw output differs from its retained result.",
        )
    exact(
        observed,
        {
            "schema": "sinter-launch-check/v1",
            "version": version,
            **{
                key: True
                for key in (
                    "frozen",
                    "core_assets_available",
                    "native_toolkit_available",
                    "Tcl_resources_available",
                    "bundled_Tk_resources_available",
                )
            },
        },
        "Installed frozen diagnostic semantics differ.",
    )


def offline(rows, operations, version, document, observations, workspace_path):
    require(
        type(rows) is list and len(rows) == len(operations),
        "Offline read sequence differs.",
    )
    require(
        type(observations) is list and len(observations) == len(rows),
        "Separate actual offline invocation observations are missing.",
    )
    for row, operation, observation in zip(rows, operations, observations):
        stopped(row)
        legacy_stderr(row)
        exact(row.get("operation"), operation, "Offline operation identity differs.")
        exact(
            row.get("stdout_truncated"), False, "Offline original output was truncated."
        )
        raw = process_evidence(
            observation,
            row,
            [
                NATIVE[0],
                "run",
                operation,
                "--input",
                str(
                    PurePosixPath(workspace_path).parent / "qualification-request.json"
                ),
                "--directory",
                workspace_path,
                "--format",
                "json",
            ],
        )
        envelope = json_object(raw)
        require(
            envelope.get("schema") == "sinter-operation-result/v1"
            and envelope.get("operation") == operation
            and envelope.get("version") == version
            and envelope.get("ok") is True,
            "Offline raw result envelope differs.",
        )
        result = envelope.get("result")
        if operation == "runtime.status":
            require(type(result) is dict, "Offline status is missing.")
            exact(
                result.get("connection"),
                {
                    key: native.FICTIONAL_PREFERENCES[key]
                    for key in ("api_url", "model", "provider", "max_tokens")
                },
                "Explicit offline connection changed.",
            )
            exact(
                result.get("provider_tested"),
                False,
                "Provider work cannot qualify this offline entry journey.",
            )
            exact(
                result.get("preferences_warning"), "", "Preferences produced a warning."
            )
            exact(
                result.get("counts"),
                {"casebooks": 1, "campaigns": 0, "reports": 0, "watches": 0},
                "Fictional workspace counts differ.",
            )
        else:
            exact(result, document, "Original source/document/revision changed.")


def workspace(snapshot, document, preferences):
    require(
        type(snapshot) is dict
        and set(snapshot) == {"preferences", "sqlite", "campaigns"},
        "Require complete fictional workspace observations.",
    )
    require(
        full_bytes(snapshot["preferences"]) == preferences,
        "Original saved preferences changed.",
    )
    # Build only an empty local schema from this byte-admitted source; no UI,
    # accounts, scheduler, requests, binary or model work is started.
    with tempfile.TemporaryDirectory(prefix="native-entry-contract-") as temp:
        store = Store(temp)
        Casebooks(store)
        CampaignStore(temp)
        baseline = {
            "sqlite": native.sqlite_observation(Path(temp) / "workspace.sqlite3"),
            "campaigns": native.sqlite_observation(Path(temp) / "campaigns.sqlite3"),
        }
    for database in baseline:
        actual, empty = snapshot[database], baseline[database]
        exact(
            actual.get("metadata"),
            empty["metadata"],
            "SQLite metadata differs from source schema.",
        )
        require(
            type(actual.get("tables")) is dict
            and set(actual["tables"]) == set(empty["tables"]),
            "SQLite table set differs from source schema.",
        )
        for name, expected in empty["tables"].items():
            table = actual["tables"][name]
            require(
                type(table) is dict and set(table) == {"sql", "columns", "rows"},
                "Typed table observation is incomplete.",
            )
            exact(table["sql"], expected["sql"], "Original table SQL differs.")
            exact(
                table["columns"],
                expected["columns"],
                "Original column names/order differ.",
            )
            if database == "sqlite" and name == "casebooks":
                rows = table["rows"]
                require(
                    type(rows) is list and len(rows) == 1 and len(rows[0]) == 5,
                    "Require one original saved casebook row.",
                )
                values = rows[0]
                exact(
                    [value.get("type") for value in values],
                    ["text", "integer", "text", "real", "text"],
                    "Raw SQLite storage types changed.",
                )
                require(
                    all(
                        type(cell) is dict and set(cell) == {"type", "value"}
                        for cell in values
                    ),
                    "Raw typed row fields differ.",
                )
                exact(
                    [values[i]["value"] for i in (0, 1, 2)],
                    [document["id"], 1, document["document"]["title"]],
                    "Original typed project identity differs.",
                )
                timestamp = values[3]["value"]
                require(
                    type(timestamp) is float
                    and math.isfinite(timestamp)
                    and timestamp > 0,
                    "Original saved timestamp type/value differs.",
                )
                exact(
                    values[4]["value"],
                    json.dumps(
                        document["document"], ensure_ascii=False, allow_nan=False
                    ),
                    "Original stored JSON text was normalized or changed.",
                )
            else:
                exact(table["rows"], [], "Unexpected fictional workspace rows exist.")


def mapped_windows(row):
    windows = row.get("mapped_windows")
    require(
        type(windows) is list and 0 < len(windows) < 5, "Require actual mapped windows."
    )
    identifiers = set()
    for window in windows:
        require(
            type(window) is dict
            and type(window.get("pid")) is int
            and window["pid"] == row["pid"]
            and window.get("mapped") is True
            and window.get("title") == native.TITLE,
            "Mapped window ownership/title differs.",
        )
        identifier = window.get("window_id")
        require(
            type(identifier) is str
            and re.fullmatch(r"0x[0-9a-f]+", identifier)
            and identifier not in identifiers,
            "Mapped window identity is invalid or repeated.",
        )
        identifiers.add(identifier)
        require(
            all(
                type(window.get(key)) is int and window[key] > 0
                for key in ("width", "height")
            ),
            "Mapped window dimensions differ.",
        )
    return identifiers


def validate_inner(receipt, source, package, archive_bytes, pins):
    require(
        type(receipt) is dict
        and receipt.get("schema") in {INNER_SCHEMA, ARCHIVE_INNER_SCHEMA},
        "Only the new installed native-entry/v2 contract is admitted.",
    )
    require(
        receipt.get("passed") is True
        and receipt.get("workflow_passed") is True
        and not any("error" in key for key in receipt),
        "An incomplete or failed inner owner cannot qualify.",
    )
    exact(
        receipt.get("source"),
        source,
        "Source/producer/driver/checker identities differ from actual archive bytes.",
    )
    exact(receipt.get("package"), package, "Actual DEB/CLI/entry identities differ.")
    exact(
        receipt.get("container"),
        {
            "effective_uid": 0,
            "interfaces": ["lo"],
            "inherited_display": False,
            "docker_marker_present": True,
        },
        "Inner isolation observations differ.",
    )
    exact(receipt.get("native_command"), NATIVE, "Native entry prefix differs.")
    for field in ("installed_entries", "installed_entries_after"):
        exact(
            receipt.get(field),
            package["entries"],
            "Complete installed/source/DEB entry bytes differ.",
        )
    before_binary, after_binary = (
        receipt.get("installed_binary"),
        receipt.get("installed_binary_after"),
    )
    require(
        type(before_binary) is dict
        and set(before_binary) == {"bytes", "sha256", "executable"}
        and type(before_binary["bytes"]) is int
        and before_binary["bytes"] == package["binary_bytes"]
        and before_binary["sha256"] == package["binary_sha256"]
        and before_binary["executable"] is True,
        "Installed binary identity is incomplete.",
    )
    exact(after_binary, before_binary, "Installed binary changed during proof.")
    commands = receipt.get("commands")
    require(
        type(commands) is list and len(commands) == 18,
        "Require the complete fixed inner owning command sequence.",
    )
    for index, row in enumerate(commands):
        stopped(
            row,
            expected_exit=1
            if index == 0
            or index == 16
            and receipt.get("removal", {}).get("package_state") == "absent"
            else 0,
        )
        exact(
            row.get("streams_complete"),
            True,
            "Inner command streams were not observed after reap.",
        )
        stream_bytes(row["stdout"], complete=False)
        stream_bytes(row["stderr"])
        if index == 15:
            exact(row["argv"], ["dpkg", "-r", "sinter"], "Removal command differs.")
            require(
                stream_bytes(row["stderr"]) in (b"", SHARED_OPT_REMOVAL_WARNING),
                "Package removal emitted unexpected diagnostics.",
            )
        elif index not in (0, 16):
            quiet(row["stderr"])
    # Package-absence probes are the only permitted nonzero command exits.
    # Validate them separately before applying the normal stopped requirement.
    for field in ("installed_package", "installed_package_recheck"):
        record = receipt.get(field)
        require(
            type(record) is dict
            and set(record) == {"status", "version", "command_index"},
            "Actual dpkg version observation is incomplete.",
        )
        index = record["command_index"]
        require(
            type(index) is int and 0 <= index < len(commands),
            "Version command identity is invalid.",
        )
        row = commands[index]
        exact(
            row["argv"],
            VERSION_QUERY,
            "Version was inferred from the input DEB rather than dpkg.",
        )
        quiet(row["stderr"])
        require(
            stream_bytes(row["stdout"])
            == ("install ok installed\n" + package["package_version"] + "\n").encode(),
            "Actual installed dpkg version/status differs.",
        )
        exact(
            {key: record[key] for key in ("status", "version")},
            {"status": "install ok installed", "version": package["package_version"]},
            "Installed version summary differs from raw query.",
        )
    require(
        receipt["installed_package"]["command_index"]
        < receipt["installed_package_recheck"]["command_index"],
        "Installed version was not rechecked after native work.",
    )
    home = receipt.get("owned_home")
    require(
        type(home) is str
        and re.fullmatch(r"/out/native-entry/sinter-native-entry-[a-z0-9_]+", home),
        "Use a fresh private owner workspace.",
    )
    launches = receipt.get("tk_launches")
    require(
        type(launches) is list and len(launches) == 2,
        "Require two actual Tk native invocations.",
    )
    project = None
    pids = []
    for phase, row in zip(("create", "reopen"), launches):
        stopped(row, signal_expected=False)
        legacy_stderr(row)
        exact(row.get("phase"), phase, "Native Tk phase differs.")
        exact(
            row.get("argv"),
            NATIVE + ["--directory", home + "/workspace"],
            "Tk did not invoke the admitted entry against its owned workspace.",
        )
        exact(
            row.get("owned_windows_remaining"), [], "Tk window cleanup is incomplete."
        )
        exact(row.get("stdout_complete"), True, "Tk stdout was captured before reap.")
        quiet(row["stdout"])
        windows = mapped_windows(row)
        index = row.get("driver_command_index")
        require(
            type(index) is int and 0 <= index < len(commands),
            "Actual driver command identity is missing.",
        )
        driver = commands[index]
        require(
            driver["argv"][1:]
            == [
                "-B",
                "/source/tools/installed_native_tk.py",
                "--request",
                home + "/" + phase + "-tk-request.json",
            ]
            and driver["argv"][0].startswith("/"),
            "Tk action did not come from the bound driver/request.",
        )
        action = json_object(stream_bytes(driver["stdout"]))
        exact(
            action,
            row.get("action"),
            "Tk action summary differs from original driver output.",
        )
        require(
            set(action)
            == {
                "schema",
                "phase",
                "project_id",
                "window_id",
                "fields_exact",
                "save_button_invoked",
                "wm_close_invoked",
            }
            and action["schema"] == "sinter-installed-native-tk-action/v1"
            and action["phase"] == phase
            and action["fields_exact"] is True
            and action["wm_close_invoked"] is True
            and action["save_button_invoked"] is (phase == "create")
            and action["window_id"] in windows,
            "Actual Tk save/reopen/WM action semantics differ.",
        )
        require(
            type(action["project_id"]) is str
            and re.fullmatch(r"[0-9a-f]{32}", action["project_id"]),
            "Saved project identity is invalid.",
        )
        if project is not None:
            exact(action["project_id"], project, "Reopened project identity changed.")
        project = action["project_id"]
        pids.append(row["pid"])
    document = {"id": project, "revision": 1, "document": validate(FIXTURE)}
    offline(
        receipt.get("offline_commands"),
        ["casebooks.get", "casebooks.get", "runtime.status"] * 2,
        source["version"],
        document,
        receipt.get("offline_observations"),
        home + "/workspace",
    )
    diagnostic(
        receipt.get("diagnostic_process"),
        receipt.get("frozen_diagnostics"),
        source["version"],
        receipt.get("diagnostic_observation"),
    )
    snapshots = receipt.get("tk_workspaces")
    require(
        type(snapshots) is list
        and [row.get("phase") for row in snapshots] == ["create", "reopen"],
        "Tk workspace observations are incomplete.",
    )
    for row in snapshots:
        workspace(
            row["snapshot"],
            document,
            json.dumps(native.FICTIONAL_PREFERENCES, ensure_ascii=False).encode(),
        )
    exact(
        snapshots[0]["snapshot"],
        snapshots[1]["snapshot"],
        "Typed original work/preferences changed on reopen.",
    )
    mapped = receipt.get("mapped_native_proof")
    owner.admit_invocations(mapped, receipt.get("invocations"), tuple(NATIVE), package)
    require(
        mapped.get("system") == "Linux" and mapped.get("machine") == "x86_64",
        "Mapped proof platform differs.",
    )
    sidecar = receipt.get("mapped_observations")
    require(
        type(sidecar) is dict
        and set(sidecar)
        == {
            "streams",
            "workspaces",
            "workspace_path",
            "workspace_removed",
            "offline",
            "diagnostic",
        },
        "Require separate complete mapped observations.",
    )
    diagnostic(
        mapped.get("diagnostic_process"),
        mapped.get("frozen_diagnostics"),
        source["version"],
        sidecar["diagnostic"],
    )
    path = sidecar["workspace_path"]
    require(
        type(path) is str
        and re.fullmatch(r"/out/sinter-frozen-window-[a-z0-9_]+/workspace", path),
        "Mapped workspace was not privately owned.",
    )
    require(
        type(sidecar["streams"]) is list and len(sidecar["streams"]) == 2,
        "Mapped stream observations are missing.",
    )
    for row, invocation, original in zip(
        sidecar["streams"], receipt["invocations"], mapped["launches"]
    ):
        exact(
            row.get("argv"),
            NATIVE + ["--directory", path],
            "Mapped stdout belongs to another entry/workspace.",
        )
        exact(
            row.get("pid"), invocation["pid"], "Mapped stdout belongs to another PID."
        )
        exact(
            row.get("stdout", {}).get("complete"),
            True,
            "Mapped stdout was observed before reap.",
        )
        exact(
            invocation["argv"],
            row["argv"],
            "Mapped invocation and stream workspace identities differ.",
        )
        exact(row["stdout"].get("exit_code"), 0, "Mapped stdout exit differs.")
        quiet(row["stdout"]["record"])
        stopped(original, signal_expected=True)
        legacy_stderr(original)
        mapped_windows(original)
        pids.append(invocation["pid"])
    require(len(set(pids)) == 4, "Four separate native entry PIDs are required.")
    mapped_document = {
        "id": None,
        "revision": 1,
        "document": validate(native.FICTIONAL_DOCUMENT),
    }
    first = json_object(mapped["offline_commands"][0]["stdout"].encode())["result"]
    require(
        type(first.get("id")) is str and re.fullmatch(r"[0-9a-f]{32}", first["id"]),
        "Mapped saved project identity is invalid.",
    )
    mapped_document["id"] = first["id"]
    offline(
        mapped.get("offline_commands"),
        [
            "casebooks.save",
            "casebooks.get",
            "runtime.status",
            "casebooks.get",
            "runtime.status",
            "casebooks.get",
            "runtime.status",
        ],
        source["version"],
        mapped_document,
        sidecar["offline"],
        path,
    )
    retained = sidecar["workspaces"]
    require(
        type(retained) is list
        and [row.get("phase") for row in retained]
        == ["original", "after_launch_1", "after_launch_2"],
        "Mapped workspace observations are incomplete.",
    )
    for row in retained:
        workspace(
            row["snapshot"],
            mapped_document,
            (
                json.dumps(native.FICTIONAL_PREFERENCES, ensure_ascii=False, indent=2)
                + "\n"
            ).encode(),
        )
        exact(
            row["snapshot"],
            retained[0]["snapshot"],
            "Mapped original typed work/preferences changed.",
        )
    display = receipt.get("display")
    stopped(display, signal_expected=True)
    legacy_stderr(display)
    exact(
        display.get("stdout_observed", {}).get("exit_code"),
        0,
        "Display stdout exit type/value differs.",
    )
    require(
        display.get("stdout_observed", {}).get("complete") is True,
        "Display stdout was not observed after reap.",
    )
    quiet(display["stdout_observed"]["record"])
    exact(
        display.get("remaining_display_paths"),
        [],
        "Display lock/socket cleanup was not observed.",
    )
    exact(
        display.get("authority_remaining"),
        False,
        "Private display authorization remains.",
    )
    exact(
        receipt.get("fictional_workspace_removed"), True, "Owned Tk workspace remains."
    )
    exact(sidecar.get("workspace_removed"), True, "Owned mapped workspace remains.")
    removal = receipt.get("removal")
    require(
        type(removal) is dict
        and set(removal)
        == {"package_state", "remaining_paths", "passed", "command_exit"},
        "Removal observation is incomplete.",
    )
    exact(removal["command_exit"], 0, "Removal command exit type/value differs.")
    require(
        removal["package_state"] in {"absent", "deinstall ok config-files"}
        and removal["remaining_paths"] == []
        and removal["command_exit"] == 0,
        "Owned package removal failed.",
    )
    # The exact raw command order ties source/package/version/action/removal
    # observations together; summaries or a supplied checklist cannot replace it.
    archive_route = receipt["schema"] == ARCHIVE_INNER_SCHEMA
    exact(
        pins.get("source_route", "git"),
        "archive" if archive_route else "git",
        "Receipt source route differs from actual outer invocation.",
    )
    if archive_route:
        origin = receipt.get("source_origin")
        require(
            type(origin) is dict
            and set(origin) == {"schema", "archive_name", "origin_name", "origin"},
            "Original archive origin evidence is missing.",
        )
        exact(
            origin["schema"],
            "sinter-bound-git-source-archive-observed/v1",
            "Unknown source origin producer.",
        )
        exact(
            origin["archive_name"], owner.ARCHIVE_NAME, "Source archive path override."
        )
        exact(origin["origin_name"], owner.ORIGIN_NAME, "Source origin path override.")
        raw_origin = full_bytes(origin["origin"])
        exact(
            json_object(raw_origin),
            owner.archive_origin(source, archive_bytes),
            "Original source origin/revision/manifest differs.",
        )
        exact(
            receipt.get("source_origin_after"),
            origin,
            "Original source origin changed during proof.",
        )
        source_argv = commands[1]["argv"]
        require(
            type(source_argv) is list
            and len(source_argv) == 5
            and type(source_argv[0]) is str
            and source_argv[0].startswith("/"),
            "Actual source archive reader is missing.",
        )
        exact(
            source_argv[1:],
            ["-B", "-c", owner.ARCHIVE_READ, "/repository/" + owner.ARCHIVE_NAME],
            "Source producer/reader override.",
        )
    else:
        source_argv = ["git", "-C", "/repository", "archive", source["commit"]]
    expected_argv = [
        STATUS_QUERY,
        source_argv,
        *[
            ["dpkg-deb", "-f", "/candidate/" + pins["installer_name"], field]
            for field in ("Package", "Architecture", "Version")
        ],
        ["dpkg-deb", "--fsys-tarfile", "/candidate/" + pins["installer_name"]],
        ["dpkg", "-i", "/candidate/" + pins["installer_name"]],
        STATUS_QUERY,
        VERSION_QUERY,
        commands[9]["argv"],
        commands[10]["argv"],
        commands[11]["argv"],
        VERSION_QUERY,
        commands[13]["argv"],
        source_argv,
        ["dpkg", "-r", "sinter"],
        STATUS_QUERY,
        commands[17]["argv"],
    ]
    for row, argv in zip(commands, expected_argv):
        exact(
            row["argv"],
            argv,
            "Actual inner source/DEB/install/action/removal order differs.",
        )
    exact(
        receipt["installed_package"]["command_index"],
        8,
        "Initial actual version observation is out of order.",
    )
    exact(
        receipt["installed_package_recheck"]["command_index"],
        12,
        "Final actual version observation is out of order.",
    )
    exact(
        [row["driver_command_index"] for row in launches],
        [10, 11],
        "Tk action commands are out of order.",
    )
    require(
        commands[9]["argv"]
        == [
            "xauth",
            "-f",
            home + "/xauthority",
            "add",
            ":97",
            ".",
            "<private owned X authorization>",
        ],
        "Actual private display authorization command differs.",
    )
    require(
        commands[5]["stdout"]["bytes"] == package["payload_tar_bytes"]
        and commands[5]["stdout"]["sha256"] == package["payload_tar_sha256"],
        "Original DEB payload stream differs from the actual installer.",
    )
    for index in (1, 14):
        require(
            commands[index]["stdout"]["bytes"] == archive_bytes
            and commands[index]["stdout"]["sha256"] == source["archive_sha256"],
            "Original source archive changed before/after native work.",
        )
    for index, raw in (
        (2, b"sinter\n"),
        (3, b"amd64\n"),
        (4, (package["package_version"] + "\n").encode()),
        (7, b"install ok installed"),
    ):
        require(
            stream_bytes(commands[index]["stdout"]) == raw,
            "Original DEB/status command output differs.",
        )
    for index in (0, 16):
        row = commands[index]
        if index == 16 and removal["package_state"] == "deinstall ok config-files":
            require(
                row["exit_code"] == 0
                and stream_bytes(row["stdout"]) == b"deinstall ok config-files",
                "Removal status summary differs from original query.",
            )
            quiet(row["stderr"])
        else:
            require(
                row["exit_code"] == 1
                and stream_bytes(row["stdout"]) == b""
                and stream_bytes(row["stderr"]) == ABSENT,
                "Arbitrary package query failure cannot prove absence.",
            )
    for field, index, paths in (
        (
            "workspace_cleanup_probe",
            13,
            [
                home,
                str(PurePosixPath(path).parent),
                "/tmp/.X11-unix/X97",
                "/tmp/.X97-lock",
                home + "/xauthority",
            ],
        ),
        (
            "removal_cleanup_probe",
            17,
            [
                "/opt/neuroforge/sinter/Sinter",
                "/usr/share/applications/sinter.desktop",
                "/usr/share/applications/sinter-native.desktop",
            ],
        ),
    ):
        exact(
            receipt.get(field),
            {"paths": paths, "command_index": index},
            "Cleanup probe identity differs.",
        )
        row = commands[index]
        require(
            row["argv"][1:] == ["-B", "-c", owner.FILESYSTEM_PROBE, *paths]
            and row["argv"][0].startswith("/"),
            "Cleanup was asserted without the actual bounded filesystem probe.",
        )
        exact(
            json.loads(stream_bytes(row["stdout"])),
            [{"path": item, "lexists": False} for item in paths],
            "Original cleanup probe found residual owned paths.",
        )
    return {
        "scope": "installed Linux native-entry command only",
        "source_commit": source["commit"],
        "installer_sha256": package["installer_sha256"],
        "binary_sha256": package["binary_sha256"],
        "entry_pids": pids,
    }


def verify(args):
    """Independently read exact inputs, then derive both closed admissions."""
    owner.exact_text(args.image_id, r"sha256:[0-9a-f]{64}", "image")
    owner.exact_text(
        args.outer_owner_sha256, r"[0-9a-f]{64}", "reviewed outer producer"
    )
    require(
        args.outer_bundle is not None,
        "A separate actual owning Docker lifecycle bundle is required; source/UI/mock receipts cannot substitute.",
    )
    require(
        sha(owner.regular_bytes(args.outer_owner_file, 2 * 1024 * 1024))
        == args.outer_owner_sha256,
        "Actual outer owner source differs from the independent review pin.",
    )
    raw_inner = owner.regular_bytes(args.receipt, 16 * 1024 * 1024)
    inner = json_object(raw_inner)
    outer = json_object(owner.regular_bytes(args.outer_bundle, 16 * 1024 * 1024))
    require(
        inner.get("schema") in {INNER_SCHEMA, ARCHIVE_INNER_SCHEMA},
        "Old native-window/entry receipt meanings are not promoted.",
    )
    commands = []
    source = owner.source_identity(args.repository, args.source_commit, commands)
    archive_route = inner["schema"] == ARCHIVE_INNER_SCHEMA
    if archive_route:
        observed_source = owner.archive_source_identity(
            args.repository, args.source_commit, commands
        )
        exact(
            observed_source,
            source,
            "Staged source archive differs from independently re-archived actual Git repository.",
        )
    json_object(owner.regular_bytes(args.package_receipt, 2 * 1024 * 1024))
    package = owner.package_preflight(args, source, commands)
    require(
        args.installer.parent.resolve() == args.package_receipt.parent.resolve(),
        "Use one fresh private candidate input directory.",
    )
    owned_root = args.owned_root.resolve(strict=True)
    for path in (ROOT, args.repository, args.installer.parent, args.outer_output):
        require(
            path.resolve().is_relative_to(owned_root) and path.resolve() != owned_root,
            "Every mounted path must be inside the independent private owner root.",
        )
    trees = [
        path.resolve()
        for path in (ROOT, args.repository, args.installer.parent, args.outer_output)
    ]
    require(
        all(
            left != right
            and not left.is_relative_to(right)
            and not right.is_relative_to(left)
            for index, left in enumerate(trees)
            for right in trees[index + 1 :]
        ),
        "Mounted private trees must be pairwise distinct and disjoint; /out must not expose readonly input aliases.",
    )
    require(
        args.receipt.resolve()
        == args.outer_output.resolve()
        / "native-entry/installed-native-entry-test.json",
        "Outer receipt location differs from the owned producer output.",
    )
    require(
        {path.name for path in args.installer.parent.iterdir()}
        == {args.installer.name, args.package_receipt.name},
        "Candidate mount must contain only the two byte-admitted inputs.",
    )
    pins = {
        "image_id": args.image_id,
        "outer_owner_sha256": args.outer_owner_sha256,
        "source_commit": args.source_commit,
        "source_directory": str(ROOT),
        "repository": str(args.repository.resolve()),
        "candidate_directory": str(args.installer.parent.resolve()),
        "output_directory": str(args.outer_output.resolve()),
        "installer_name": args.installer.name,
        "package_receipt_name": args.package_receipt.name,
        "source_route": "archive" if archive_route else "git",
        "artifacts": {
            "inner_receipt_sha256": sha(raw_inner),
            "source_archive_sha256": source["archive_sha256"],
            "installer_sha256": package["installer_sha256"],
            "package_receipt_sha256": package["receipt_sha256"],
        },
    }
    if archive_route:
        pins["artifacts"]["source_origin_sha256"] = sha(
            owner.regular_bytes(args.repository / owner.ORIGIN_NAME, 2 * 1024 * 1024)
        )
    identifier = validate_outer(outer, pins)
    result = validate_inner(
        inner, source, package, commands[0]["stdout"]["bytes"], pins
    )
    return {
        "schema": "sinter-installed-native-entry-admission/v1",
        "container_id": identifier,
        **result,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in (
        "receipt",
        "outer-bundle",
        "outer-owner-file",
        "outer-output",
        "owned-root",
        "repository",
        "installer",
        "package-receipt",
    ):
        parser.add_argument("--" + field, type=Path, required=True)
    for field in ("source-commit", "image-id", "outer-owner-sha256"):
        parser.add_argument("--" + field, required=True)
    try:
        result = verify(parser.parse_args(argv))
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        UnicodeError,
        AttributeError,
        RuntimeError,
    ) as error:
        print(
            json.dumps(
                {
                    "schema": "sinter-installed-native-entry-admission-refusal/v1",
                    "error": str(error),
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
