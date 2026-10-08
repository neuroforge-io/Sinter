"""Closed, separate admission for an installed native owner's browser handoff.

The existing four-launch native-entry contract is a prerequisite, never widened.
Synthetic receipts test this parser; only the producer's actual installed run
with complete original artifacts can earn the new admission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from sinter.casebooks import build, validate  # noqa: E402
from tools import installed_native_container as owner  # noqa: E402
from tools import installed_native_entry_contract as old  # noqa: E402
from tools import installed_native_menu as menu  # noqa: E402
from tools import native_window_smoke as native  # noqa: E402
from tools.rc4_scoped_recovery_contract import QUESTIONS, fixture  # noqa: E402

SCHEMA = "sinter-installed-native-browser-handoff/v1"
ADMISSION = "sinter-installed-native-browser-handoff-admission/v1"
FILES = (
    "tools/rc4_native_handoff.py",
    "tools/rc4_native_handoff_contract.py",
    "tests/test_rc4_native_handoff.py",
    "docs/RC4_NATIVE_HANDOFF.md",
)
BROWSER_TEMP_PARENT = Path("/tmp")
BROWSER_TEMP_PREFIX = "sinter-native-"
BROWSER_TEMP_MAX_BYTES = 55
BROWSER_TEMP_IDENTITY = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")


def preflight_browser_temporary():
    """Admit the fixed short namespace before acquiring any owned resource."""
    parent = BROWSER_TEMP_PARENT
    old.require(
        str(parent) == "/tmp"
        and parent.resolve(strict=True) == parent
        and stat.S_ISDIR(parent.lstat().st_mode),
        "Use the canonical fixed browser temporary parent.",
    )
    observed = parent.lstat()
    old.require(
        observed.st_uid in {0, os.geteuid()}
        and (not observed.st_mode & 0o022 or observed.st_mode & stat.S_ISVTX),
        "The fixed browser temporary parent is not safe for exclusive creation.",
    )
    old.require(
        BROWSER_TEMP_PREFIX == "sinter-native-"
        and len(os.fsencode(parent / (BROWSER_TEMP_PREFIX + "a" * 8)))
        <= BROWSER_TEMP_MAX_BYTES,
        "Browser temporary UTF-8 socket paths exceed the finite budget.",
    )
    old.require(
        shutil.rmtree.avoids_symlink_attacks,
        "Owned browser cleanup requires descriptor-safe removal.",
    )
    return parent


def validate_browser_temporary(value):
    """Require exact private ownership, unchanged inode and completed removal."""
    old.require(
        type(value) is dict
        and set(value) == {"path", "identity_before", "identity_after", "removed"},
        "Browser temporary ownership fields differ.",
    )
    path = value["path"]
    old.require(
        type(path) is str
        and len(path.encode("utf-8")) <= BROWSER_TEMP_MAX_BYTES
        and re.fullmatch(r"/tmp/sinter-native-[a-z0-9_]{8}", path)
        and PurePosixPath(path).parent == PurePosixPath("/tmp"),
        "Browser temporary path is outside its finite fixed namespace.",
    )
    before = value["identity_before"]
    old.require(
        type(before) is dict
        and set(before) == set(BROWSER_TEMP_IDENTITY)
        and all(type(before[k]) is int and before[k] >= 0 for k in before)
        and before["st_ino"] > 0
        and before["st_mode"] == (stat.S_IFDIR | 0o700)
        and before["st_uid"] == getattr(os, "geteuid", lambda: 0)()
        and before["st_gid"] == getattr(os, "getegid", lambda: 0)(),
        "Browser temporary root is not one exclusively owned private directory.",
    )
    exact(value["identity_after"], before, "Browser temporary root was replaced.")
    exact(value["removed"], True, "Browser temporary root remains.")
    old.require(
        not os.path.lexists(path), "Observed browser temporary root still exists."
    )

PHASES = (
    "refuse-scoped",
    "open-browser",
    "native-no",
    "close-keep",
    "cancel-keep",
    "close-timeout",
    "inspect-timeout",
    "close-final",
)
COMMANDS = ("hold-request", "release-request", "interrupt-request")
FIELDS = (
    "Unsaved native handoff — {literal}; [no execution] 🐝",
    "Who owns watering?\nIs the date confirmed? é 🐝",
    "Unsaved full original — é",
    "Owner unassigned. Date unconfirmed.\nFull original tail {kept}; [literal] 🐝.",
)
BROWSER_TITLE = "Unsaved browser handoff — é 🐝"
HOST_CHROMIUM = Path(
    "/home/lloyd/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)
PYTHON = "/opt/qualification-python/bin/python3"
HISTORY = "HISTORICAL HUMAN EDIT — owner unassigned; date unconfirmed. 🐝 é"
TIMEOUT_TEXT = (
    "Close refused: local requests or listener cleanup did not finish. "
    "Your native runtime and inputs remain open. Check saved work, then close "
    "again explicitly; no request was replayed."
)
TABLE_SCHEMAS = {
    "casebooks": (
        "CREATE TABLE casebooks (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, title TEXT NOT NULL, updated_at REAL NOT NULL, document TEXT NOT NULL)",
        ["id", "revision", "title", "updated_at", "document"],
    ),
    "casebooks_scoped_v2": (
        "CREATE TABLE casebooks_scoped_v2 (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, title TEXT NOT NULL, updated_at REAL NOT NULL, document TEXT NOT NULL)",
        ["id", "revision", "title", "updated_at", "document"],
    ),
    "reports": (
        "CREATE TABLE reports ( id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL, document TEXT NOT NULL )",
        ["id", "title", "created_at", "document"],
    ),
    "watches": (
        "CREATE TABLE watches ( id TEXT PRIMARY KEY, title TEXT NOT NULL, query TEXT NOT NULL, interval INTEGER NOT NULL, next_run REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, last_run REAL, lease_until REAL NOT NULL DEFAULT 0, lease_token TEXT NOT NULL DEFAULT '', results TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '', failures INTEGER NOT NULL DEFAULT 0, deadline TEXT NOT NULL DEFAULT '' )",
        [
            "id",
            "title",
            "query",
            "interval",
            "next_run",
            "enabled",
            "last_run",
            "lease_until",
            "lease_token",
            "results",
            "error",
            "failures",
            "deadline",
        ],
    ),
    "campaigns": (
        "CREATE TABLE campaigns (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, title TEXT NOT NULL, updated_at TEXT NOT NULL, document TEXT NOT NULL)",
        ["id", "revision", "title", "updated_at", "document"],
    ),
}


def chromium_argv(home):
    """Own one fresh host profile/debugger; never inherit an account profile."""
    return [
        str(HOST_CHROMIUM),
        "--headless=new",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--metrics-recording-only",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=0",
        "--user-data-dir=" + str(home / "profile"),
        "about:blank",
    ]


def scoped_fixture():
    document = validate(fixture())
    document["title"] += " — scoped"
    document["schema"] = "sinter-casebook/v2"
    document["question_scopes"] = [
        {
            "question_index": 0,
            "question": QUESTIONS[0],
            "source_ids": [document["documents"][0]["id"]],
        },
        {"question_index": 1, "question": QUESTIONS[1], "source_ids": []},
    ]
    return validate(document)


def creation_argv(pins, name):
    """Exactly one producer; no caller command, Tcl or origin override."""
    argv = old.outer_argv({**pins, "source_route": "archive"}, name)
    argv = argv[: argv.index(pins["image_id"]) + 1]
    return argv + [
        "python3",
        "-B",
        "/source/tools/rc4_native_handoff.py",
        "_inside",
        "--repository",
        "/repository",
        "--source-commit",
        pins["source_commit"],
        "--installer",
        "/candidate/" + pins["installer_name"],
        "--package-receipt",
        "/candidate/" + pins["package_receipt_name"],
        "--output",
        "/out/handoff",
        "--qualification",
        pins["qualification"],
    ]


def action_request(value):
    old.require(
        type(value) is dict and set(value) == {"phase", "pid", "window_ids"},
        "Use one closed native action request.",
    )
    old.require(
        type(value["phase"]) is str and value["phase"] in PHASES,
        "Unknown native action.",
    )
    old.require(
        type(value["pid"]) is int and value["pid"] > 0,
        "Native owner PID must be a positive builtin integer.",
    )
    windows = value["window_ids"]
    old.require(
        type(windows) is list
        and len(windows) == 1
        and type(windows[0]) is str
        and re.fullmatch(r"0x[0-9a-f]+", windows[0]),
        "One actual mapped owner window is required.",
    )
    return value


def url_port(value):
    old.require(type(value) is str, "Native browser address must be text.")
    match = re.fullmatch(r"http://127\.0\.0\.1:([0-9]{1,5})/#campaigns", value)
    old.require(
        match is not None and 1 <= int(match[1]) <= 65535,
        "Only the actual loopback campaign URL is permitted.",
    )
    return int(match[1])


def exact(value, expected, message):
    if type(expected) is bytes:
        old.require(type(value) is bytes and value == expected, message)
    else:
        old.exact(value, expected, message)


def operation(row, operation_name, body, version, workspace, input_path):
    command_fields(row, {"role", "input", "input_bytes"})
    exact(
        row["argv"],
        [
            str(menu.BINARY),
            "run",
            operation_name,
            "--input",
            input_path,
            "--directory",
            workspace,
            "--format",
            "json",
        ],
        "Installed CLI invocation differs.",
    )
    old.stopped(row, signal_expected=False)
    old.require(row.get("streams_complete") is True, "CLI streams were not reaped.")
    exact(
        old.stream_bytes(row["stderr"]),
        b"Ready for review\n" if operation_name == "casebooks.build" else b"",
        "Unknown installed CLI diagnostic.",
    )
    exact(
        old.json_object(old.full_bytes(body)),
        row["input"],
        "Original CLI input changed.",
    )
    result = old.json_object(old.stream_bytes(row["stdout"]))
    old.require(
        result.get("ok") is True
        and result.get("version") == version
        and result.get("schema") == "sinter-operation-result/v1"
        and result.get("operation") == operation_name
        and type(result.get("result")) is dict,
        "Actual frozen CLI response identity or completion differs.",
    )
    return result["result"]


def command_fields(row, extra=()):
    """Close this route's fixed child records without changing the old schemas.

    The shared collector always emits completion and emits signal/escalation
    fields only when applicable. Any present optional flag has its actual
    builtin Boolean meaning; mapped source controls never invent an observation.
    """
    required = {
        "argv",
        "pid",
        "exit_code",
        "owned_group_remaining",
        "passed",
        "streams_complete",
        "stdout",
        "stderr",
        *extra,
    }
    old.require(
        type(row) is dict
        and required <= set(row) <= required | {"sigterm_sent", "forced_cleanup"}
        and type(row["argv"]) is list
        and all(type(argument) is str for argument in row["argv"])
        and type(row["exit_code"]) is int
        and row["owned_group_remaining"] is False
        and row["streams_complete"] is True,
        "Fixed command fields/types differ.",
    )
    for flag in ("sigterm_sent", "forced_cleanup"):
        if flag in row:
            old.require(row[flag] is False, "Fixed command cleanup flag differs.")
    old.require(
        row["passed"] is (row["exit_code"] == 0),
        "Fixed command completion flag differs.",
    )


def validate_launch(value, owner_pid, port, url):
    old.require(
        type(value) is dict
        and set(value) == {"url", "port", "pid", "owner_pid"}
        and type(value["pid"]) is int
        and value["pid"] > 0
        and type(value["owner_pid"]) is int
        and value["owner_pid"] == owner_pid
        and type(value["port"]) is int
        and value["port"] == port
        and value["url"] == url
        and url_port(value["url"]) == port,
        "Fixed captured launch identity/port differs.",
    )


def validate_hold(value, version):
    from sinter.native_browser import SESSION_DETAILS, SESSION_NOTICE
    from sinter.workbench import WORKFLOWS

    old.require(
        type(value) is dict
        and set(value) == {"fixture", "admitted", "released_explicitly", "session"},
        "Fixed held-request fields differ.",
    )
    exact(
        {k: value[k] for k in ("fixture", "admitted", "released_explicitly")},
        {
            "fixture": "admitted empty TCP connection",
            "admitted": True,
            "released_explicitly": True,
        },
        "Controlled drain fixture differs.",
    )
    response = value["session"]
    old.require(
        type(response) is dict and set(response) == {"status", "body"},
        "Fixed held-session response fields differ.",
    )
    exact(response["status"], 200, "Held request was not independently admitted.")
    session = old.json_object(old.full_bytes(response["body"]))
    old.require(
        set(session)
        == {
            "token",
            "version",
            "workflows",
            "desktop",
            "native_window_owner",
            "session_notice",
            "session_details",
            "native_quit",
        }
        and type(session["token"]) is str
        and re.fullmatch(r"[A-Za-z0-9_-]{43}", session["token"]),
        "Complete fixed held-session API body differs.",
    )
    exact(
        {k: v for k, v in session.items() if k not in {"token", "native_quit"}},
        {
            "version": version,
            "workflows": WORKFLOWS,
            "desktop": True,
            "native_window_owner": True,
            "session_notice": SESSION_NOTICE,
            "session_details": SESSION_DETAILS,
        },
        "Held session does not belong to the current native workbench.",
    )
    state = session["native_quit"]
    old.require(
        type(state) is dict
        and set(state) == {"state", "active_requests"}
        and state["state"] == "cancelled"
        and type(state["active_requests"]) is int
        and 2 <= state["active_requests"] <= 16,
        "Held session must follow native-No while requests remain admitted.",
    )
    return session["token"]


def container_identities(value):
    """Only concurrent roles share a disjointness requirement in this namespace."""
    owner_pid = value["owner"]["pid"]
    display_pid = value["display_evidence"]["display"]["pid"]
    launcher_pid = value["launch"]["pid"]
    old.require(
        all(
            type(pid) is int and pid > 0
            for pid in (owner_pid, display_pid, launcher_pid)
        )
        and len({owner_pid, display_pid, launcher_pid}) == 3,
        "Concurrent native owner/display/launcher PIDs alias.",
    )
    for action in value["actions"]:
        pid = action["command"]["pid"]
        old.require(
            type(pid) is int and pid > 0 and pid not in {owner_pid, display_pid},
            "Concurrent native control PID aliases owner/display.",
        )
        if action["phase"] == "open-browser":
            old.require(
                pid != launcher_pid, "Concurrent open control/launcher PIDs alias."
            )


def validate_seed(value, version, workspace):
    exact(
        [r["role"] for r in value],
        ["save-legacy", "save-scoped", "build-legacy", "save-history", "status"],
        "Seed operations differ or were omitted.",
    )
    results = []
    operations = (
        "casebooks.save",
        "casebooks.save",
        "casebooks.build",
        "reports.save",
        "runtime.status",
    )
    for row, name in zip(value, operations):
        results.append(
            operation(
                row,
                name,
                row["input_bytes"],
                version,
                workspace,
                workspace + "/../" + row["role"] + ".json",
            )
        )
    legacy, scoped, built, history, status = results
    for saved, document in ((legacy, validate(fixture())), (scoped, scoped_fixture())):
        old.require(
            type(saved.get("id")) is str
            and re.fullmatch(r"[0-9a-f]{32}", saved["id"])
            and type(saved.get("revision")) is int
            and saved["revision"] == 1,
            "Fictional saved identity changed.",
        )
        exact(
            saved.get("document"), document, "Full original evidence or scopes changed."
        )
    old.require(legacy["id"] != scoped["id"], "The two projects must be distinct.")
    exact(value[0]["input"], {"document": fixture()}, "Legacy seed changed.")
    exact(value[1]["input"], {"document": scoped_fixture()}, "Scoped seed changed.")
    exact(value[2]["input"], {"id": legacy["id"], "revision": 1}, "Build seed changed.")
    old.require(
        type(built.get("markdown")) is str
        and type(built.get("source_register")) is list,
        "Source-only build omitted its report.",
    )
    expected_build = build(fixture())
    old.require(
        type(built.get("created_at")) is str
        and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00",
            built["created_at"],
        ),
        "Actual source report creation time differs.",
    )
    expected_build["created_at"] = built["created_at"]
    exact(
        built,
        expected_build,
        "Actual source report, review status, citations or full evidence differ.",
    )
    expected_report = {**built, "markdown": HISTORY + "\n\n" + built["markdown"]}
    exact(
        value[3]["input"],
        {"report": expected_report},
        "Historical human report changed.",
    )
    old.require(type(history.get("id")) is str, "Historical report was not saved.")
    exact(value[4]["input"], {}, "Status seed changed.")
    exact(
        status.get("connection"),
        {
            k: native.FICTIONAL_PREFERENCES[k]
            for k in ("api_url", "model", "provider", "max_tokens")
        },
        "Explicit model changed.",
    )
    old.require(
        status.get("provider_tested") is False
        and status.get("preferences_warning") == "",
        "A provider was used or settings repaired.",
    )
    return {
        "legacy": legacy,
        "scoped": scoped,
        "history": history,
        "report": expected_report,
    }


def validate_actions(rows, process):
    old.require(
        type(rows) is list and len(rows) == len(PHASES),
        "Fixed action inventory differs.",
    )
    for row in rows:
        old.require(
            type(row) is dict
            and set(row) == {"phase", "request", "request_bytes", "command", "result"}
            and type(row["result"]) is dict
            and type(row["result"].get("status")) is str
            and len(row["result"]["status"]) <= 8192,
            "Fixed action fields/status differ.",
        )
        command_fields(row["command"])
    exact(
        [r["phase"] for r in rows], list(PHASES), "Native action order/count differs."
    )
    expected_controls = (
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
    )
    for row, controls in zip(rows, expected_controls):
        action_request(row["request"])
        exact(row["request"]["phase"], row["phase"], "Driver phase differs.")
        exact(row["request"]["pid"], process["pid"], "Driver observed another owner.")
        exact(
            row["request"]["window_ids"],
            [process["mapped_windows"][0]["window_id"]],
            "Driver observed another window.",
        )
        old.stopped(row["command"], signal_expected=False)
        exact(
            row["command"]["argv"],
            [
                PYTHON,
                "-B",
                "/source/" + FILES[0],
                "_driver",
                "--request",
                process["workspace_home"] + "/" + row["phase"] + "-request.json",
            ],
            "Driver command is not the fixed UI-only action.",
        )
        exact(
            old.json_object(old.full_bytes(row["request_bytes"])),
            row["request"],
            "Original driver request changed.",
        )
        old.quiet(row["command"]["stderr"])
        old.require(
            row["command"].get("streams_complete") is True, "Driver streams incomplete."
        )
        output = old.json_object(old.stream_bytes(row["command"]["stdout"]))
        exact(output, row["result"], "Original driver response changed.")
        exact(
            output,
            {
                "schema": "sinter-native-handoff-action/v1",
                "phase": row["phase"],
                "pid": process["pid"],
                "window_id": row["request"]["window_ids"][0],
                "fields": list(FIELDS),
                "controls": controls,
                "status": row["result"]["status"],
            },
            "Closed driver result differs.",
        )
    old.require(
        "no choices were cleared" in rows[0]["result"]["status"],
        "Native scoped refusal was not observed.",
    )
    exact(
        rows[6]["result"]["status"],
        TIMEOUT_TEXT,
        "Actual five-second refusal was omitted.",
    )


def seed_snapshot(value, seeds):
    """Admit the original typed disk projection before any native/cold reader."""
    exact(
        sorted(value),
        ["databases", "preferences", "preferences_bytes", "preferences_sha256"],
        "Original projection fields differ.",
    )
    exact(
        value["preferences"],
        native.FICTIONAL_PREFERENCES,
        "Original preferences differ.",
    )
    raw_preferences = old.full_bytes(value["preferences_bytes"])
    exact(
        old.json_object(raw_preferences),
        native.FICTIONAL_PREFERENCES,
        "Original preference bytes changed.",
    )
    exact(
        value["preferences_sha256"],
        hashlib.sha256(raw_preferences).hexdigest(),
        "Preference hash differs.",
    )
    databases = value["databases"]
    exact(
        sorted(databases),
        ["campaigns.sqlite3", "workspace.sqlite3"],
        "Raw database inventory differs.",
    )
    for name, db in databases.items():
        exact(
            sorted(db), ["metadata", "tables"], "Raw database projection fields differ."
        )
        exact(
            db["metadata"],
            {
                "user_version": 1 if name == "workspace.sqlite3" else 0,
                "application_id": 0,
                "encoding": "UTF-8",
                "page_size": 4096,
            },
            "Initial live metadata differs.",
        )
        for table, projection in db["tables"].items():
            old.require(table in TABLE_SCHEMAS, "Unsupported initial table schema.")
            exact(
                sorted(projection),
                ["columns", "rows", "sql"],
                "Original table projection fields differ.",
            )
            sql, columns = TABLE_SCHEMAS[table]
            old.require(type(projection["sql"]) is str, "Original SQL must be text.")
            exact(
                re.sub(r"\s+", " ", projection["sql"]),
                sql,
                "Original complete SQL schema differs.",
            )
            exact(
                projection["columns"], columns, "Original full column schema differs."
            )
    tables = databases["workspace.sqlite3"]["tables"]
    exact(
        sorted(tables),
        ["casebooks", "casebooks_scoped_v2", "reports", "watches"],
        "Original schema inventory differs.",
    )
    for table, saved in (
        ("casebooks", seeds["legacy"]),
        ("casebooks_scoped_v2", seeds["scoped"]),
    ):
        row = tables[table]
        exact(
            row["columns"],
            ["id", "revision", "title", "updated_at", "document"],
            "Original project columns differ.",
        )
        old.require(
            type(row["rows"]) is list
            and len(row["rows"]) == 1
            and len(row["rows"][0]) == 5,
            "Original project row is absent or duplicated.",
        )
        actual = row["rows"][0]
        exact(
            actual[:3],
            [saved["id"], 1, saved["document"]["title"]],
            "Typed original project identity differs.",
        )
        old.require(
            type(actual[3]) is float and actual[3] > 0,
            "Original timestamp type differs.",
        )
        exact(
            old.json_object(actual[4].encode("utf-8")),
            saved["document"],
            "Raw original source evidence or scopes changed.",
        )
    reports = tables["reports"]
    exact(
        reports["columns"],
        ["id", "title", "created_at", "document"],
        "Original report columns differ.",
    )
    old.require(
        type(reports["rows"]) is list
        and len(reports["rows"]) == 1
        and len(reports["rows"][0]) == 4,
        "Historical report row is absent or duplicated.",
    )
    row = reports["rows"][0]
    exact(
        row[:2],
        [seeds["history"]["id"], seeds["report"]["title"]],
        "Historical report identity differs.",
    )
    old.require(
        type(row[2]) is float and row[2] > 0, "Historical timestamp type differs."
    )
    exact(
        old.json_object(row[3].encode("utf-8")),
        seeds["report"],
        "Raw historical edits/review/citations changed.",
    )
    exact(tables["watches"]["rows"], [], "Qualification must not activate watches.")
    campaigns = databases["campaigns.sqlite3"]["tables"]
    exact(sorted(campaigns), ["campaigns"], "Campaign schema inventory differs.")
    exact(campaigns["campaigns"]["rows"], [], "Unexpected campaign data exists.")


def validate_interrupted(value, port, token=None):
    exact(
        sorted(value),
        ["attempts", "request", "response"],
        "Interrupted request evidence differs.",
    )
    exact(value["attempts"], 1, "Interrupted request was replayed.")
    request = old.full_bytes(value["request"])
    prefix = (
        f"POST /api/casebooks/save HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        f"Origin: http://127.0.0.1:{port}\r\nX-Sinter-Token: "
    ).encode()
    suffix = (
        b'\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{"document":'
    )
    old.require(
        re.fullmatch(
            re.escape(prefix) + rb"[A-Za-z0-9_-]{43}" + re.escape(suffix), request
        ),
        "The actual interrupted request is not the fixed owned partial JSON POST.",
    )
    if token is not None:
        old.require(
            type(token) is str and re.fullmatch(r"[A-Za-z0-9_-]{43}", token),
            "The held owner token is invalid.",
        )
        exact(
            request,
            prefix + token.encode("ascii") + suffix,
            "Interrupted request belongs to another session owner.",
        )
    raw = old.full_bytes(value["response"])
    headers, separator, body = raw.partition(b"\r\n\r\n")
    old.require(
        len(raw) < 128_000
        and separator
        and headers.startswith(b"HTTP/1.0 400 Bad Request\r\n"),
        "Actual interrupted-body HTTP refusal is absent.",
    )
    exact(
        old.json_object(body),
        {"error": "The request was interrupted before all data arrived."},
        "Actual interrupted refusal body differs.",
    )
    old.require(
        b"Content-Length: " + str(len(body)).encode() + b"\r\n" in headers + b"\r\n"
        and b"Content-Type: application/json; charset=utf-8\r\n" in headers + b"\r\n",
        "Complete interrupted refusal headers differ.",
    )


def validate_commands(value, source, package):
    rows = value["commands"]
    expected = [
        old.STATUS_QUERY,
        [PYTHON, "-B", "-c", menu.ARCHIVE_READ, "/repository/" + menu.ARCHIVE_NAME],
        *[
            ["dpkg-deb", "-f", "/candidate/" + value["installer_name"], field]
            for field in ("Package", "Architecture", "Version")
        ],
        ["dpkg-deb", "--fsys-tarfile", "/candidate/" + value["installer_name"]],
        ["dpkg", "-i", "/candidate/" + value["installer_name"]],
        old.STATUS_QUERY,
        old.VERSION_QUERY,
        ["dpkg", "-r", "sinter"],
        old.STATUS_QUERY,
        [
            PYTHON,
            "-B",
            "-c",
            menu.FILESYSTEM_PROBE,
            str(menu.BINARY),
            str(menu.ENTRY_DIR / "sinter.desktop"),
            str(menu.ENTRY_DIR / "sinter-native.desktop"),
        ],
    ]
    old.require(
        type(rows) is list and len(rows) == len(expected),
        "Actual installation/source/removal command inventory differs.",
    )
    for index, (row, argv) in enumerate(zip(rows, expected)):
        command_fields(row)
        exact(row["argv"], argv, "An unsupported command was used.")
        expected_exit = (
            1
            if index == 0
            or index == 10
            and value["removal_state"]["package_status"] == "absent"
            else 0
        )
        old.stopped(row, signal_expected=False, expected_exit=expected_exit)
        old.require(
            row.get("streams_complete") is True,
            "Actual command streams are incomplete.",
        )
        stderr = old.stream_bytes(row["stderr"])
        if index in {0, 10} and expected_exit == 1:
            exact(stderr, old.ABSENT, "Package absence is a query error.")
        elif index == 9:
            old.require(
                stderr in {b"", old.SHARED_OPT_REMOVAL_WARNING},
                "Unknown removal diagnostic.",
            )
        else:
            exact(stderr, b"", "Unexpected command diagnostic.")
    for index, expected_bytes in (
        (2, b"sinter\n"),
        (3, b"amd64\n"),
        (4, (package["package_version"] + "\n").encode()),
        (7, b"install ok installed"),
        (8, ("install ok installed\n" + package["package_version"] + "\n").encode()),
    ):
        exact(
            old.stream_bytes(rows[index]["stdout"]),
            expected_bytes,
            "Actual package control/version differs.",
        )
    for index, sha, size in (
        (1, source["archive_sha256"], value["archive_bytes"]),
        (5, package["payload_tar_sha256"], package["payload_tar_bytes"]),
    ):
        old.stream_bytes(rows[index]["stdout"], complete=False)
        exact(
            rows[index]["stdout"]["sha256"],
            sha,
            "Actual complete source/payload hash differs.",
        )
        exact(
            rows[index]["stdout"]["bytes"],
            size,
            "Actual complete source/payload size differs.",
        )
    exact(
        rows[9], value["removal"], "Removal row was detached from actual command order."
    )
    paths = [
        str(menu.BINARY),
        str(menu.ENTRY_DIR / "sinter.desktop"),
        str(menu.ENTRY_DIR / "sinter-native.desktop"),
    ]
    exact(
        json.loads(old.stream_bytes(rows[11]["stdout"]), object_pairs_hook=old.unique),
        [{"path": path, "lexists": False} for path in paths],
        "Actual installed-path absence differs.",
    )
    exact(
        value["absence"],
        {"paths": paths, "command_index": 11},
        "Cleanup probe was detached.",
    )
    display = value["display_evidence"]
    old.require(
        type(display) is dict and set(display) == {"commands", "display"},
        "Fixed private-display evidence fields differ.",
    )
    old.require(
        type(display["commands"]) is list and len(display["commands"]) == 1,
        "Private X authority command differs.",
    )
    command = display["commands"][0]
    command_fields(command)
    exact(
        command["argv"],
        [
            "xauth",
            "-f",
            value["owner"]["workspace_home"] + "/xauthority",
            "add",
            ":97",
            ".",
            "<private owned X authorization>",
        ],
        "X authority argv differs.",
    )
    old.stopped(command, signal_expected=False)
    old.quiet(command["stdout"])
    old.quiet(command["stderr"])
    row = display["display"]
    old.stopped(row, signal_expected=True)
    old.legacy_stderr(row)
    exact(row["stdout_observed"]["exit_code"], 0, "Display exit differs.")
    old.require(
        row["stdout_observed"]["complete"] is True, "Display streams incomplete."
    )
    old.quiet(row["stdout_observed"]["record"])
    exact(row["remaining_display_paths"], [], "Display resources remain.")
    exact(row["authority_remaining"], False, "Private display authorization remains.")


def validate_inner(value, source, package):
    old.require(
        type(value) is dict
        and value.get("schema") == SCHEMA
        and value.get("passed") is True
        and not any("error" in k for k in value),
        "A failed or historical handoff receipt cannot qualify.",
    )
    exact(
        sorted(value),
        sorted(
            {
                "schema",
                "qualification",
                "passed",
                "commands",
                "seed",
                "actions",
                "snapshots",
                "cleanup",
                "container",
                "source_origin",
                "source",
                "archive_bytes",
                "installer_name",
                "tools",
                "package",
                "installed_package",
                "installed_entries",
                "installed_binary",
                "display_evidence",
                "workspace",
                "selected_scoped_id",
                "owner",
                "url",
                "port",
                "launch",
                "hold",
                "timeout_ns",
                "interrupted",
                "reads",
                "installed_entries_after",
                "installed_binary_after",
                "removal",
                "removal_state",
                "absence",
            }
        ),
        "Unknown or incomplete handoff evidence fields.",
    )
    exact(value["source"], source, "Complete source identity differs.")
    exact(value["package"], package, "Package identity differs.")
    origin = value["source_origin"]
    exact(
        sorted(origin),
        ["archive_name", "origin", "origin_name", "schema"],
        "Source origin evidence fields differ.",
    )
    exact(
        origin["schema"],
        "sinter-bound-git-source-archive-observed/v1",
        "Unknown source origin.",
    )
    exact(origin["archive_name"], menu.ARCHIVE_NAME, "Source archive path override.")
    exact(origin["origin_name"], menu.ORIGIN_NAME, "Source origin path override.")
    exact(
        old.json_object(old.full_bytes(origin["origin"])),
        menu.archive_origin(source, value["archive_bytes"]),
        "Original Git archive origin/source/revision differs.",
    )
    exact(
        value["installed_package"],
        {
            "status": "install ok installed",
            "version": package["package_version"],
            "command_index": 8,
        },
        "Actual installed version observation differs.",
    )
    exact(
        value["tools"],
        {name: source["files"][name] for name in FILES},
        "Four reviewed tools differ.",
    )
    exact(
        value["container"],
        {
            "effective_uid": 0,
            "interfaces": ["lo"],
            "inherited_display": False,
            "docker_marker_present": True,
        },
        "Fresh isolated handoff container differs.",
    )
    for suffix in ("", "_after"):
        exact(
            value["installed_entries" + suffix],
            package["entries"],
            "Installed menu bytes changed.",
        )
        exact(
            value["installed_binary" + suffix],
            {
                "bytes": package["binary_bytes"],
                "sha256": package["binary_sha256"],
                "executable": True,
            },
            "Installed binary changed.",
        )
    process = value["owner"]
    old.stopped(process, signal_expected=False)
    exact(
        process["argv"],
        old.NATIVE + ["--directory", value["workspace"]],
        "Native argv differs.",
    )
    old.mapped_windows(process)
    exact(process.get("owned_windows_remaining"), [], "Fifth owner windows remain.")
    old.quiet(process["stdout"])
    old.legacy_stderr(process)
    old.require(
        process.get("stdout_complete") is True, "Owner stdout observed before reap."
    )
    seeds = validate_seed(value["seed"], source["version"], value["workspace"])
    snapshot = value["snapshots"]["before_native"]
    seed_snapshot(snapshot, seeds)
    old.require(
        set(value["snapshots"])
        == {
            "before_native",
            "after_refusal",
            "after_browser",
            "after_keep",
            "after_timeout",
            "before_final",
            "after_exit",
            "after_read",
        },
        "Raw pre-reopen or interruption snapshot is missing.",
    )
    for observed in value["snapshots"].values():
        exact(
            observed,
            snapshot,
            "Raw schema/metadata/original/history/preferences changed.",
        )
    validate_actions(value["actions"], process)
    validate_commands(value, source, package)
    container_identities(value)
    exact(
        value["selected_scoped_id"],
        seeds["scoped"]["id"],
        "Native refused the wrong project.",
    )
    exact(
        value["url"],
        "http://127.0.0.1:" + str(value["port"]) + "/#campaigns",
        "URL capture differs.",
    )
    old.require(
        type(value["port"]) is int and url_port(value["url"]) == value["port"],
        "Port type differs.",
    )
    validate_launch(value["launch"], process["pid"], value["port"], value["url"])
    read = value["reads"]
    old.require(
        type(read) is list and len(read) == 1 and read[0]["role"] == "read-scoped",
        "Cold CLI scoped reader omitted.",
    )
    result = operation(
        read[0],
        "casebooks.get",
        read[0]["input_bytes"],
        source["version"],
        value["workspace"],
        value["workspace"] + "/../read-scoped.json",
    )
    exact(
        read[0]["input"], {"id": seeds["scoped"]["id"]}, "Reader used another project."
    )
    exact(
        result,
        seeds["scoped"],
        "Current capable CLI failed to recover the exact scoped project.",
    )
    token = validate_hold(value["hold"], source["version"])
    old.require(
        type(value["timeout_ns"]) is int
        and 5_000_000_000 <= value["timeout_ns"] < 12_000_000_000,
        "Actual unchanged five-second timeout was not measured.",
    )
    validate_interrupted(value["interrupted"], value["port"], token)
    exact(
        value["cleanup"],
        {
            "listener_closed": True,
            "inner_relay_stopped": True,
            "inner_socket_absent": True,
            "display_stopped": True,
            "package_paths_absent": True,
        },
        "New owner cleanup remains incomplete.",
    )
    removal = value["removal"]
    exact(removal["argv"], ["dpkg", "-r", "sinter"], "Wrong package removal.")
    old.stopped(removal, signal_expected=False)
    removal_stdout = old.stream_bytes(removal["stdout"])
    old.require(
        removal_stdout == b""
        or re.fullmatch(
            rb"\(Reading database \.\.\. [0-9]+ files and directories currently installed\.\)\nRemoving sinter \("
            + re.escape(package["package_version"].encode())
            + rb"\) \.\.\.\n",
            removal_stdout,
        ),
        "Unknown package-removal stdout.",
    )
    old.require(
        old.stream_bytes(removal["stderr"]) in {b"", old.SHARED_OPT_REMOVAL_WARNING},
        "Unknown removal stderr cannot qualify.",
    )
    exact(value["removal_state"]["paths_absent"], True, "Installed paths remain.")
    old.require(
        value["removal_state"]["package_status"]
        in {"absent", "deinstall ok config-files"},
        "Sinter remains installed.",
    )
    return {"owner_pid": process["pid"], "scoped_project_id": seeds["scoped"]["id"]}


def validate_browser(value, inner):
    exact(
        sorted(value),
        sorted(
            {
                "schema",
                "origin",
                "relay_port",
                "page_errors",
                "external_requests",
                "quit_posts",
                "visible_checks",
                "quit_attempts",
                "chromium",
                "browser_pids",
                "native_notice",
                "title",
                "lost_ack_status",
                "lost_ack_body",
                "model_requests",
                "relay_errors",
                "cleanup",
                "screenshots",
                "scoped_response",
                "driver_process",
                "chromium_process",
                "debug_port",
                "confirmed_ack",
                "temporary_directory",
            }
        ),
        "Browser evidence fields differ.",
    )
    exact(
        value["schema"],
        "sinter-rc4-native-handoff-browser/v3",
        "Unknown actual browser observation schema.",
    )
    validate_browser_temporary(value["temporary_directory"])
    chromium = value["chromium"]
    old.require(
        type(chromium) is dict
        and set(chromium) == {"path", "sha256", "sha256_after", "version"}
        and chromium["path"] == str(HOST_CHROMIUM)
        and type(chromium["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", chromium["sha256"])
        and type(chromium["version"]) is str
        and bool(chromium["version"]),
        "Actual selected Chromium identity is incomplete.",
    )
    exact(
        chromium["sha256_after"],
        chromium["sha256"],
        "Actual Chromium changed during qualification.",
    )
    exact(
        value["origin"],
        "http://127.0.0.1:" + str(value["relay_port"]),
        "Relay origin differs.",
    )
    old.require(
        type(value["relay_port"]) is int
        and 0 < value["relay_port"] <= 65535
        and value["relay_port"] != inner["port"],
        "Relay port differs.",
    )
    exact(value["title"], BROWSER_TITLE, "Browser unsaved inputs changed.")
    exact(
        value["quit_attempts"],
        ["keep-working:no-post", "lost-ack:uncertain:no-replay", "confirmed-quit"],
        "Explicit attempts or uncertainty were rewritten.",
    )
    exact(value["quit_posts"], 2, "An uncertain quit request was replayed or omitted.")
    exact(value["lost_ack_status"], 200, "No real lost acknowledgement was retained.")
    exact(
        old.json_object(old.full_bytes(value["lost_ack_body"])),
        {"ok": True},
        "Lost acknowledgement original body is missing.",
    )
    exact(
        sorted(value["confirmed_ack"]),
        ["body", "status"],
        "Confirmed quit evidence fields differ.",
    )
    exact(
        value["confirmed_ack"]["status"],
        200,
        "Final explicit quit acknowledgement failed.",
    )
    exact(
        old.json_object(old.full_bytes(value["confirmed_ack"]["body"])),
        {"ok": True},
        "Actual final quit response body differs.",
    )
    exact(
        value["native_notice"],
        "Same local workspace. Keep the Sinter window open.",
        "Wrong owner notice.",
    )
    exact(
        value["visible_checks"],
        [
            "full-originals",
            "scoped-capability",
            "keep-working",
            "uncertain-quit-inputs-kept",
            "native-cancelled",
            "drain-cancelled",
            "timeout-refused",
            "confirmed-quit",
        ],
        "Visible browser checks differ.",
    )
    exact(value["model_requests"], 0, "A model/provider route was used.")
    exact(value["external_requests"], 0, "Browser accessed an external origin.")
    exact(value["page_errors"], [], "Browser execution failed.")
    exact(value["relay_errors"], 0, "The owned relay failed.")
    exact(
        value["cleanup"],
        {
            "browser_closed": True,
            "owned_pids_gone": True,
            "owned_driver_gone": True,
            "relay_idle": True,
            "relay_stopped": True,
            "relay_port_closed": True,
            "debug_port_closed": True,
        },
        "Browser resources remain.",
    )
    old.require(
        type(value["browser_pids"]) is list
        and value["browser_pids"]
        and all(type(pid) is int and pid > 0 for pid in value["browser_pids"])
        and len(set(value["browser_pids"])) == len(value["browser_pids"]),
        "Browser PIDs are untyped.",
    )
    exact(
        sorted(value["screenshots"]),
        ["browser-scoped.png", "browser-timeout.png", "browser-uncertain.png"],
        "Visible screenshots are missing.",
    )
    scoped = old.json_object(old.stream_bytes(inner["seed"][1]["stdout"]))["result"]
    response = value["scoped_response"]
    exact(
        sorted(response),
        ["body", "capability", "method", "path", "status"],
        "Browser response evidence differs.",
    )
    exact(
        {key: response[key] for key in ("capability", "method", "path", "status")},
        {
            "capability": "sinter-casebook/v2",
            "method": "GET",
            "path": "/api/casebooks/" + scoped["id"],
            "status": 200,
        },
        "Actual browser used an unsupported or wrong project reader.",
    )
    exact(
        old.json_object(old.full_bytes(response["body"])),
        scoped,
        "Actual browser lost full original scoped inputs.",
    )
    old.require(
        type(value["debug_port"]) is int
        and 0 < value["debug_port"] <= 65535
        and value["debug_port"] not in {value["relay_port"], inner["port"]},
        "Owned debugger port differs.",
    )
    chrome = value["chromium_process"]
    old.stopped(chrome, signal_expected=False)
    old.require(
        chrome.get("streams_complete") is True
        and chrome["pid"] in value["browser_pids"],
        "Owned Chromium process/streams are incomplete.",
    )
    old.stream_bytes(chrome["stdout"], complete=False)
    old.stream_bytes(chrome["stderr"], complete=False)
    driver = value["driver_process"]
    old.require(
        type(driver) is dict
        and set(driver) == {"pid", "path", "sha256", "sha256_after"}
        and type(driver["pid"]) is int
        and driver["pid"] > 0
        and driver["pid"] not in value["browser_pids"]
        and type(driver["path"]) is str
        and driver["path"].startswith("/")
        and type(driver["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", driver["sha256"]),
        "Actual owned browser-driver identity is incomplete.",
    )
    exact(
        driver["sha256_after"],
        driver["sha256"],
        "Actual Playwright Node changed during qualification.",
    )


def validate_outer(value, clients, pins):
    """Bind every V4 lifecycle row to its reaped actual host child, separately."""
    exact(
        sorted(value),
        [
            "cleanup_commands",
            "commands",
            "docker_client",
            "schema",
            "source_manifest",
            "source_manifest_sha256",
            "tools",
        ],
        "Owned outer evidence fields differ.",
    )
    exact(
        value["schema"],
        "sinter-owned-native-handoff-container/v1",
        "Unknown outer handoff schema.",
    )
    exact(value["cleanup_commands"], [], "Emergency container cleanup cannot qualify.")
    lifecycle = old.validate_lifecycle(value["commands"], pins, creation_argv)
    old.require(
        lifecycle["start_stdout"] == b"", "Container producer stdout is not quiet."
    )
    identity = value["docker_client"]
    exact(
        sorted(identity),
        ["path", "sha256", "sha256_after", "version"],
        "Actual Docker client identity differs.",
    )
    old.require(
        type(identity["path"]) is str
        and Path(identity["path"]).is_absolute()
        and type(identity["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", identity["sha256"]),
        "Actual Docker client binary identity is incomplete.",
    )
    exact(identity["sha256_after"], identity["sha256"], "Docker client changed.")
    old.require(
        type(clients) is list and len(clients) == 8,
        "All actual Docker client children are required.",
    )
    exact(
        clients[0],
        identity["version"],
        "Docker version summary was detached from its original child.",
    )
    exact(
        clients[0]["argv"], ["docker", "--version"], "Docker version command differs."
    )
    version = old.stream_bytes(clients[0]["stdout"])
    old.require(
        version.startswith(b"Docker version ")
        and version.endswith(b"\n")
        and len(version) < 200,
        "Actual Docker version output is missing.",
    )
    old.quiet(clients[0]["stderr"])
    for index, row in enumerate(clients):
        old.require(
            type(row) is dict
            and set(row).issubset(
                {
                    "argv",
                    "passed",
                    "pid",
                    "exit_code",
                    "owned_group_remaining",
                    "forced_cleanup",
                    "sigterm_sent",
                    "streams_complete",
                    "stdout",
                    "stderr",
                    "stdout_file",
                    "stderr_file",
                }
            ),
            "Unknown Docker child error or command fields.",
        )
        exact(row.get("passed"), index != 7, "Actual Docker child completion differs.")
        old.stopped(row, signal_expected=False, expected_exit=1 if index == 7 else 0)
        exact(
            row.get("streams_complete"),
            True,
            "Actual Docker client streams were observed before reap.",
        )
        for name in ("stdout", "stderr"):
            old.stream_bytes(row[name])
        if index:
            observed = value["commands"][index - 1]
            exact(
                {key: row[key] for key in ("argv", "exit_code", "stdout", "stderr")},
                {
                    key: observed[key]
                    for key in ("argv", "exit_code", "stdout", "stderr")
                },
                "Lifecycle summary was detached from its original actual child.",
            )
    old.require(
        len({row["pid"] for row in clients}) == len(clients),
        "Actual Docker child IDs were reused.",
    )
    return lifecycle


def tree_shape(root):
    """Observe bounded entry types without opening links, sockets or FIFOs."""
    old.require(
        stat.S_ISDIR(root.lstat().st_mode), "Evidence root is not a real directory."
    )
    files, directories, pending = set(), set(), [root]
    while pending:
        folder = pending.pop()
        for entry in folder.iterdir():
            old.require(
                len(files) + len(directories) < 10_000,
                "Owned inventory exceeds its bound.",
            )
            mode = entry.lstat().st_mode
            name = entry.relative_to(root).as_posix()
            if stat.S_ISDIR(mode):
                directories.add(name)
                pending.append(entry)
            else:
                old.require(
                    stat.S_ISREG(mode), "Special or redirected evidence entry: " + name
                )
                files.add(name)
    return files, directories


def closed_tree(root, files):
    observed, directories = tree_shape(root)
    expected = set(files)
    parents = {
        p.as_posix()
        for name in expected
        for p in Path(name).parents
        if p.as_posix() != "."
    }
    exact(
        sorted(observed), sorted(expected), "Unknown or missing owned artifact entry."
    )
    exact(sorted(directories), sorted(parents), "Unexpected owned artifact directory.")


def closed_children(root, files, directories):
    old.require(
        stat.S_ISDIR(root.lstat().st_mode), "Owned root is not a real directory."
    )
    observed_files, observed_directories = set(), set()
    for entry in root.iterdir():
        mode = entry.lstat().st_mode
        if stat.S_ISDIR(mode):
            observed_directories.add(entry.name)
        else:
            old.require(
                stat.S_ISREG(mode),
                "Special or redirected owned root entry: " + entry.name,
            )
            observed_files.add(entry.name)
    exact(sorted(observed_files), sorted(files), "Unknown or missing root artifact.")
    exact(
        sorted(observed_directories), sorted(directories), "Unexpected root directory."
    )


def audit_evidence(root, source, installer_name, receipt_name):
    """Closed proof entries; variable runtime/profile internals are only regular."""
    closed_children(root, {"owner-run.json"}, {"baseline", "handoff-container"})
    handoff = root / "handoff-container"
    closed_children(
        handoff,
        {"outer.json", "client-commands.json", "browser.json"},
        {"source", "repository", "candidate", "out", "tmp", "client", "raw"},
    )
    closed_tree(handoff / "source", source["files"])
    closed_tree(handoff / "candidate", {installer_name, receipt_name})
    closed_tree(
        handoff / "raw",
        {
            role + "." + stream
            for role in ("client-version", *old.ROLES)
            for stream in ("stdout", "stderr")
        },
    )
    closed_children(handoff / "out", set(), {"handoff"})
    closed_children(
        handoff / "out/handoff",
        {
            "launch.json",
            "state.json",
            "control.json",
            "inner.json",
            "chromium.stdout",
            "chromium.stderr",
            "browser-scoped.png",
            "browser-timeout.png",
            "browser-uncertain.png",
        },
        {"home"},
    )
    closed_children(handoff / "client", set(), {".docker", "browser-home"})
    for variable in (
        handoff / "repository",
        handoff / "tmp",
        handoff / "client",
        handoff / "out/handoff/home",
    ):
        tree_shape(variable)


def verify(args):
    """Re-read both separate raw proofs; source archives are actual re-archives."""
    root = args.output.resolve(strict=True)
    baseline = root / "baseline"
    handoff = root / "handoff-container"
    from types import SimpleNamespace

    baseline_args = SimpleNamespace(
        receipt=baseline / "out/native-entry/installed-native-entry-test.json",
        outer_bundle=baseline / "outer-container.json",
        outer_owner_file=ROOT / owner.SOURCE_FILE,
        outer_owner_sha256=args.owner_sha256,
        outer_output=baseline / "out",
        owned_root=baseline,
        repository=baseline / "repository",
        source_commit=args.source_commit,
        installer=baseline / "candidate" / args.installer.name,
        package_receipt=baseline / "candidate" / args.package_receipt.name,
        image_id=owner.IMAGE_ID,
    )
    # The old verifier's ROOT is its own source tree; use its actual separate CLI.
    commands = []
    code, raw = menu.command(
        [
            sys.executable,
            "-B",
            baseline / "source/tools/installed_native_entry_contract.py",
            "--receipt",
            baseline_args.receipt,
            "--outer-bundle",
            baseline_args.outer_bundle,
            "--outer-owner-file",
            baseline / "source" / owner.SOURCE_FILE,
            "--outer-owner-sha256",
            args.owner_sha256,
            "--outer-output",
            baseline_args.outer_output,
            "--owned-root",
            baseline,
            "--repository",
            baseline_args.repository,
            "--source-commit",
            args.source_commit,
            "--installer",
            baseline_args.installer,
            "--package-receipt",
            baseline_args.package_receipt,
            "--image-id",
            owner.IMAGE_ID,
        ],
        commands,
        timeout=60,
    )
    old.require(code == 0, "Unchanged four-launch baseline admission failed.")
    admitted_baseline = old.json_object(raw)
    raw_inner = menu.regular_bytes(handoff / "out/handoff/inner.json", 16 * 1024 * 1024)
    inner = old.json_object(raw_inner)
    source = menu.source_identity(args.repository, args.source_commit, [])
    audit_evidence(root, source, args.installer.name, args.package_receipt.name)
    old.require(
        args.qualification in {"dev", "candidate"}
        and (args.qualification == "dev" or source["version"] == "0.5.4rc4"),
        "Canonical candidate cannot use a DEV source version.",
    )
    exact(
        inner["qualification"],
        args.qualification,
        "DEV/candidate evidence was relabelled.",
    )
    # strict_archive binds complete source set and every byte to this verifier's ROOT.
    actual_archive = menu.regular_bytes(
        handoff / "repository" / menu.ARCHIVE_NAME, menu.MAX_ARCHIVE
    )
    exact(
        menu.strict_archive(actual_archive, args.source_commit),
        source,
        "Handoff archive differs from actual Git.",
    )
    exact(
        old.json_object(
            menu.regular_bytes(
                handoff / "repository" / menu.ORIGIN_NAME, 2 * 1024 * 1024
            )
        ),
        menu.archive_origin(source, len(actual_archive)),
        "Source origin differs.",
    )
    package = menu.package_preflight(args, source, [])
    exact(
        owner.source_records(handoff / "source"),
        source["files"],
        "Actual mounted handoff source changed.",
    )
    exact(
        sorted(p.name for p in (handoff / "candidate").iterdir()),
        sorted([args.installer.name, args.package_receipt.name]),
        "Candidate input set differs.",
    )
    for name, expected_sha in (
        (args.installer.name, package["installer_sha256"]),
        (args.package_receipt.name, package["receipt_sha256"]),
    ):
        exact(
            native.binary_digest(handoff / "candidate" / name),
            expected_sha,
            "Candidate bytes changed.",
        )
    pins = owner.pins_for(
        handoff,
        args.owner_sha256,
        args.source_commit,
        args.installer.name,
        args.package_receipt.name,
    )
    pins["qualification"] = args.qualification
    outer = old.json_object(
        menu.regular_bytes(handoff / "outer.json", 16 * 1024 * 1024)
    )
    clients = json.loads(
        menu.regular_bytes(handoff / "client-commands.json", 16 * 1024 * 1024),
        object_pairs_hook=old.unique,
    )
    lifecycle = validate_outer(outer, clients, pins)
    actual_client = Path(
        shutil.which("docker", path=os.defpath) or "/missing-docker"
    ).resolve(strict=True)
    exact(
        outer["docker_client"]["path"],
        str(actual_client),
        "Actual host Docker executable differs.",
    )
    exact(
        native.binary_digest(actual_client),
        outer["docker_client"]["sha256"],
        "Host Docker executable changed.",
    )
    for index, row in enumerate(clients):
        role = "client-version" if index == 0 else outer["commands"][index - 1]["role"]
        for name in ("stdout", "stderr"):
            raw = menu.regular_bytes(
                handoff / "raw" / (role + "." + name), 32 * 1024 * 1024
            )
            exact(
                row[name + "_file"],
                str(handoff / "raw" / (role + "." + name)),
                "Docker stream retention path differs.",
            )
            exact(
                row[name]["bytes"],
                len(raw),
                "Original complete Docker stream size differs.",
            )
            exact(
                row[name]["sha256"],
                old.sha(raw),
                "Original complete Docker stream hash differs.",
            )
    old.require(
        lifecycle["container_id"] != admitted_baseline["container_id"],
        "Fresh handoff container was reused.",
    )
    result = validate_inner(inner, source, package)
    browser = old.json_object(
        menu.regular_bytes(handoff / "browser.json", 2 * 1024 * 1024)
    )
    validate_browser(browser, inner)
    for name, record in browser["screenshots"].items():
        raw = menu.regular_bytes(handoff / "out/handoff" / name, 8 * 1024 * 1024)
        exact(
            record,
            {"bytes": len(raw), "sha256": old.sha(raw)},
            "Original screenshot bytes differ.",
        )
        old.require(
            raw.startswith(b"\x89PNG\r\n\x1a\n") and raw.endswith(b"IEND\xaeB`\x82"),
            "Visible artifact is not a complete PNG.",
        )
    exact(
        browser["chromium_process"]["argv"],
        chromium_argv(handoff / "client/browser-home"),
        "Fixed owned browser invocation differs.",
    )
    for name in ("stdout", "stderr"):
        raw = menu.regular_bytes(
            handoff / "out/handoff" / ("chromium." + name), 32 * 1024 * 1024
        )
        exact(
            len(raw),
            browser["chromium_process"][name]["bytes"],
            "Complete browser stream length differs.",
        )
        exact(
            old.sha(raw),
            browser["chromium_process"][name]["sha256"],
            "Complete browser stream hash differs.",
        )
    exact(
        browser["chromium"]["path"], str(HOST_CHROMIUM), "Browser executable differs."
    )
    exact(
        browser["chromium"]["sha256"],
        args.chromium_sha256,
        "Browser review pin differs.",
    )
    exact(
        native.binary_digest(HOST_CHROMIUM),
        args.chromium_sha256,
        "Host browser changed after qualification.",
    )
    import playwright

    driver_path = Path(playwright.__file__).resolve().parent / "driver/node"
    exact(
        browser["driver_process"]["path"],
        str(driver_path),
        "Browser driver executable differs from this installed dependency.",
    )
    exact(
        browser["driver_process"]["sha256"],
        native.binary_digest(driver_path),
        "Browser driver bytes changed.",
    )
    exact(outer["source_manifest"], source["files"], "Mounted source set differs.")
    exact(
        outer["source_manifest_sha256"],
        owner.records_hash(source["files"]),
        "Source manifest differs.",
    )
    for path in FILES:
        exact(
            outer["tools"][path],
            source["files"][path],
            "Reviewed handoff tool pin differs.",
        )
    exact(outer["cleanup_commands"], [], "Emergency container cleanup cannot qualify.")
    exact(
        outer["docker_client"]["sha256"],
        outer["docker_client"]["sha256_after"],
        "Docker client changed.",
    )
    return {
        "schema": ADMISSION,
        "source_commit": source["commit"],
        "version": source["version"],
        "qualification": args.qualification,
        "source_archive_sha256": source["archive_sha256"],
        "installer_sha256": package["installer_sha256"],
        "inner_sha256": old.sha(raw_inner),
        "baseline": admitted_baseline,
        "handoff_container_id": lifecycle["container_id"],
        "owner_identity": {
            "container_id": lifecycle["container_id"],
            "pid": result["owner_pid"],
        },
        **result,
        "boundary": "Installed Linux private X11/browser owner handoff only; not physical-menu, prior replacement, release or other-platform qualification.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "repository", "installer", "package-receipt"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--owner-sha256", required=True)
    parser.add_argument("--qualification", choices=("dev", "candidate"), required=True)
    parser.add_argument("--chromium-sha256", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(verify(args), ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
