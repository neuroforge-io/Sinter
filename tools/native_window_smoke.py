"""Qualify frozen Linux native launch on an explicitly supplied local X display.

This checks a mapped, process-owned Tk window, repeat launch, clean SIGTERM
shutdown and preservation of saved fictional sources/preferences.
It never opens a browser, starts an X server, exercises inference or uses a real
workspace. A pass is launch qualification for this artifact/display only.

An optional fixed native-entry command adapter records separate invocation
observations for an owning installed-menu producer. It does not qualify entry
bytes, package identity, full native editing/handoff or package removal. The
default command and v1 receipt contract remain unchanged.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import ctypes.util
import hashlib
import json
import os
import platform
import re
import signal
import sqlite3
import subprocess
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

TITLE = "Sinter — portable source workspace"
START_SECONDS = 12
STOP_SECONDS = 5
MAX_WINDOWS = 512
MAX_STDERR_BYTES = 65_536
MAX_CLI_BYTES = 128_000
FICTIONAL_DOCUMENT = {
    "schema": "sinter-casebook/v1",
    "title": "Fictional garden handover — native launch qualification",
    "questions": "Is approval confirmed?\nWho will check the quote?",
    "document_type": "handover",
    "documents": [
        {
            "title": "Fictional original note",
            "content": (
                "Approval is unconfirmed — 🐝. The quote checker is unknown.\n"
                "This fictional source must survive both native shutdowns exactly."
            ),
            "url": "",
            "date": "",
        }
    ],
}
FICTIONAL_PREFERENCES = {
    "schema_version": 1,
    "theme": "light",
    "text_size": "large",
    "density": "compact",
    "reduce_motion": True,
    "api_url": "https://example.invalid/v1",
    "model": "fictional-explicit-offline-model",
    "provider": "openai-compatible",
    "max_tokens": 256,
    "full_name": "Fictional operator",
    "organisation": "Fictional garden group",
}


class WindowAttributes(ctypes.Structure):
    """Xlib's XWindowAttributes layout, including fields after map_state."""

    _fields_ = [
        (name, kind)
        for names, kind in (
            (("x", "y", "width", "height", "border_width", "depth"), ctypes.c_int),
            (("visual",), ctypes.c_void_p),
            (("root",), ctypes.c_ulong),
            (
                ("window_class", "bit_gravity", "win_gravity", "backing_store"),
                ctypes.c_int,
            ),
            (("backing_planes", "backing_pixel"), ctypes.c_ulong),
            (("save_under",), ctypes.c_int),
            (("colormap",), ctypes.c_ulong),
            (("map_installed", "map_state"), ctypes.c_int),
            (
                ("all_event_masks", "your_event_mask", "do_not_propagate_mask"),
                ctypes.c_long,
            ),
            (("override_redirect",), ctypes.c_int),
            (("screen",), ctypes.c_void_p),
        )
        for name in names
    ]


class X11Observer:
    """Read only X11 properties; matching titles alone cannot establish ownership."""

    def __init__(self, display):
        library = ctypes.util.find_library("X11")
        if not library:
            raise RuntimeError("libX11 is required to inspect the native window.")
        self.x = ctypes.CDLL(library)
        pointer, window = ctypes.c_void_p, ctypes.c_ulong
        self.x.XOpenDisplay.argtypes, self.x.XOpenDisplay.restype = (
            [ctypes.c_char_p],
            pointer,
        )
        self.x.XCloseDisplay.argtypes = [pointer]
        self.x.XDefaultRootWindow.argtypes, self.x.XDefaultRootWindow.restype = (
            [pointer],
            window,
        )
        self.x.XInternAtom.argtypes = [pointer, ctypes.c_char_p, ctypes.c_int]
        self.x.XInternAtom.restype = window
        self.x.XQueryTree.argtypes = [
            pointer,
            window,
            ctypes.POINTER(window),
            ctypes.POINTER(window),
            ctypes.POINTER(ctypes.POINTER(window)),
            ctypes.POINTER(ctypes.c_uint),
        ]
        self.x.XGetWindowAttributes.argtypes = [
            pointer,
            window,
            ctypes.POINTER(WindowAttributes),
        ]
        self.x.XGetWindowProperty.argtypes = [
            pointer,
            window,
            window,
            ctypes.c_long,
            ctypes.c_long,
            ctypes.c_int,
            window,
            ctypes.POINTER(window),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
        ]
        self.x.XFree.argtypes = [pointer]
        self.x.XSetErrorHandler.argtypes, self.x.XSetErrorHandler.restype = (
            [pointer],
            pointer,
        )
        self.display = self.x.XOpenDisplay(display.encode("ascii"))
        if not self.display:
            raise RuntimeError("The supplied local X display could not be opened.")
        # Windows can disappear between tree and property reads during cleanup.
        # A failed read is ignored; it can never satisfy the mapped-window check.
        callback = ctypes.CFUNCTYPE(ctypes.c_int, pointer, pointer)
        self.error_handler = callback(lambda *_: 0)
        self.previous_handler = self.x.XSetErrorHandler(self.error_handler)

    def _property(self, window, name):
        atom = self.x.XInternAtom(self.display, name.encode("ascii"), True)
        if not atom:
            return None
        actual, form = ctypes.c_ulong(), ctypes.c_int()
        count, remaining = ctypes.c_ulong(), ctypes.c_ulong()
        data = ctypes.POINTER(ctypes.c_ubyte)()
        status = self.x.XGetWindowProperty(
            self.display,
            window,
            atom,
            0,
            1024,
            False,
            0,
            ctypes.byref(actual),
            ctypes.byref(form),
            ctypes.byref(count),
            ctypes.byref(remaining),
            ctypes.byref(data),
        )
        try:
            if status != 0 or not data or remaining.value:
                return None
            if form.value == 8:
                return ctypes.string_at(data, count.value).decode(
                    "utf-8", errors="replace"
                )
            if form.value == 32 and count.value == 1:
                # Xlib expands 32-bit property items to native unsigned longs.
                return ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))[0]
            return None
        finally:
            if data:
                self.x.XFree(data)

    def windows(self, pid, *, mapped_only=False):
        pending = [self.x.XDefaultRootWindow(self.display)]
        seen, result = set(), []
        while pending:
            window = pending.pop()
            if window in seen:
                continue
            seen.add(window)
            if len(seen) > MAX_WINDOWS:
                raise RuntimeError(
                    "X window tree exceeds the bounded inspection limit."
                )
            root, parent, count = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_uint()
            children = ctypes.POINTER(ctypes.c_ulong)()
            if self.x.XQueryTree(
                self.display,
                window,
                ctypes.byref(root),
                ctypes.byref(parent),
                ctypes.byref(children),
                ctypes.byref(count),
            ):
                try:
                    if count.value > MAX_WINDOWS:
                        raise RuntimeError(
                            "X window tree exceeds the bounded inspection limit."
                        )
                    pending.extend(children[index] for index in range(count.value))
                finally:
                    if children:
                        self.x.XFree(children)
            if self._property(window, "_NET_WM_PID") != pid:
                continue
            title = self._property(window, "_NET_WM_NAME") or self._property(
                window, "WM_NAME"
            )
            attributes = WindowAttributes()
            if not self.x.XGetWindowAttributes(
                self.display, window, ctypes.byref(attributes)
            ):
                continue
            mapped = (
                attributes.map_state == 2
                and attributes.width > 0
                and attributes.height > 0
            )
            if not mapped_only or (title == TITLE and mapped):
                result.append(
                    {
                        "window_id": hex(window),
                        "pid": pid,
                        "title": title,
                        "mapped": mapped,
                        "width": attributes.width,
                        "height": attributes.height,
                    }
                )
        return result

    def close(self):
        self.x.XSetErrorHandler(self.previous_handler)
        self.x.XCloseDisplay(self.display)


def clean_environment(home, display, authority=None):
    """Forward only the authorised display, never inherited account settings."""
    home = Path(home)
    result = {
        "PATH": os.defpath,
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "TZ": "UTC",
        "DISPLAY": display,
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_DATA_HOME": str(home / "data"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "TMPDIR": str(home),
    }
    if authority:
        result["XAUTHORITY"] = authority
    return result


def group_alive(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def stop_process(process, row):
    """Signal only the process group created for this test; escalation fails it."""
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            row["sigterm_sent"] = True
        except ProcessLookupError:
            row["sigterm_sent"] = False
        try:
            row["exit_code"] = process.wait(timeout=STOP_SECONDS)
        except subprocess.TimeoutExpired:
            row["forced_cleanup"] = True
            os.killpg(process.pid, signal.SIGKILL)
            row["exit_code"] = process.wait(timeout=2)
    else:
        row["exit_code"] = process.returncode
    if group_alive(process.pid):
        row["forced_cleanup"] = True
        os.killpg(process.pid, signal.SIGKILL)
        deadline = time.monotonic() + 2
        while group_alive(process.pid) and time.monotonic() < deadline:
            time.sleep(0.05)
    row["owned_group_remaining"] = group_alive(process.pid)


def capture_stderr(stream: BinaryIO, row: dict) -> None:
    """Retain bounded exact diagnostic bytes and bind the complete stream."""
    stream.seek(0)
    digest, prefix, size = hashlib.sha256(), bytearray(), 0
    while block := stream.read(65_536):
        digest.update(block)
        size += len(block)
        prefix.extend(block[: max(0, MAX_STDERR_BYTES - len(prefix))])
    row.update(
        stderr=bytes(prefix).decode("utf-8", errors="replace"),
        stderr_base64=base64.b64encode(prefix).decode("ascii"),
        stderr_bytes=size,
        stderr_sha256=digest.hexdigest(),
        stderr_truncated=size > MAX_STDERR_BYTES,
    )


def binary_digest(binary: Path) -> str:
    """Bind the complete explicitly supplied executable before and after proof."""
    digest = hashlib.sha256()
    with binary.open("rb") as stream:
        while content := stream.read(1024 * 1024):
            digest.update(content)
    return digest.hexdigest()


def local_operation(
    binary: Path,
    workspace: Path,
    environment: dict[str, str],
    operation: str,
    payload: dict,
    receipt: dict,
    *,
    observation=None,
) -> dict:
    """Use only the tested executable's offline CLI, retaining failure evidence."""
    if operation not in {"casebooks.save", "casebooks.get", "runtime.status"}:
        raise ValueError(
            "Native launch qualification allows only fictional local operations."
        )
    request = workspace.parent / "qualification-request.json"
    request.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if observation is not None and (type(observation) is not dict or observation):
        raise ValueError("Provide a fresh separate offline process observation.")
    arguments = [
        str(binary),
        "run",
        operation,
        "--input",
        str(request),
        "--directory",
        str(workspace),
        "--format",
        "json",
    ]
    row = {"operation": operation, "passed": False}
    receipt["offline_commands"].append(row)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            arguments,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        row["pid"] = process.pid
        if observation is not None:
            observation.update(argv=arguments.copy(), pid=process.pid)
        try:
            process.wait(timeout=10)
        finally:
            try:
                stop_process(process, row)
            finally:
                try:
                    capture_stderr(stderr, row)
                finally:
                    if observation is not None:
                        observe_process_streams(
                            stdout, stderr, process, row, observation
                        )
                stdout.seek(0)
                raw = stdout.read(MAX_CLI_BYTES + 1)
                row["stdout"] = raw[:MAX_CLI_BYTES].decode("utf-8", errors="replace")
                row["stdout_truncated"] = len(raw) > MAX_CLI_BYTES
        if (
            row["exit_code"] != 0
            or row.get("forced_cleanup")
            or row["owned_group_remaining"]
            or row["stderr_bytes"]
            or row["stdout_truncated"]
        ):
            raise RuntimeError(
                "Fictional offline CLI preparation/read failed; see evidence."
            )
        envelope = json.loads(raw)
        if (
            not isinstance(envelope, dict)
            or envelope.get("schema") != "sinter-operation-result/v1"
            or envelope.get("operation") != operation
            or envelope.get("version") != receipt["frozen_diagnostics"]["version"]
            or envelope.get("ok") is not True
            or not isinstance(envelope.get("result"), dict)
        ):
            raise RuntimeError(
                "Fictional offline CLI returned an unexpected result identity."
            )
        row["passed"] = True
        return envelope["result"]


def workspace_snapshot(workspace: Path) -> dict[str, str | int]:
    """Read original preference bytes and all logical SQLite schema/row bytes."""
    preferences = (workspace / "preferences.json").read_bytes()
    path = workspace / "workspace.sqlite3"
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("The fictional saved workspace failed SQLite integrity.")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        metadata = {
            "sqlite_" + name: db.execute("PRAGMA " + name).fetchone()[0]
            for name in ("application_id", "encoding", "page_size")
        }
        dump = "\n".join(db.iterdump()).encode("utf-8")
    return {
        "preferences_sha256": hashlib.sha256(preferences).hexdigest(),
        "sqlite_logical_sha256": hashlib.sha256(dump).hexdigest(),
        "sqlite_user_version": version,
        **metadata,
    }


def same_json(left: object, right: object) -> bool:
    """Require exact JSON values/types without Python's bool/int coercion."""
    options = {
        "sort_keys": True,
        "ensure_ascii": True,
        "separators": (",", ":"),
        "allow_nan": False,
    }
    return json.dumps(left, **options) == json.dumps(right, **options)


def sqlite_observation(path: Path) -> dict:
    """Observe typed original rows from a regular database without migration."""
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Use a regular fictional database observation.")
    tables = {}
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("Fictional workspace integrity observation failed.")
        metadata = {
            name: db.execute("PRAGMA " + name).fetchone()[0]
            for name in ("user_version", "application_id", "encoding", "page_size")
        }
        for name, sql in db.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ):
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [
                row[1] for row in db.execute("PRAGMA table_info(" + quoted + ")")
            ]
            rows = []
            for values in db.execute("SELECT * FROM " + quoted):
                cells = []
                for value in values:
                    kind = (
                        "null"
                        if value is None
                        else "integer"
                        if type(value) is int
                        else "real"
                        if type(value) is float
                        else "text"
                        if type(value) is str
                        else "blob"
                        if type(value) is bytes
                        else "unsupported"
                    )
                    if kind == "unsupported":
                        raise RuntimeError(
                            "Unexpected SQLite value in fictional observation."
                        )
                    cells.append(
                        {
                            "type": kind,
                            "value": value.hex() if kind == "blob" else value,
                        }
                    )
                rows.append(cells)
            tables[name] = {
                "sql": sql,
                "columns": columns,
                "rows": sorted(
                    rows,
                    key=lambda row: json.dumps(row, sort_keys=True, allow_nan=False),
                ),
            }
    return {"metadata": metadata, "tables": tables}


def retained_workspace_snapshot(workspace: Path) -> dict:
    """Separate V3 observation: full preferences and both typed live databases."""
    raw = (workspace / "preferences.json").read_bytes()
    if len(raw) > 128_000 or (workspace / "preferences.json").is_symlink():
        raise RuntimeError("Fictional preference observation exceeds its boundary.")
    return {
        "preferences": {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "base64": base64.b64encode(raw).decode("ascii"),
        },
        "sqlite": sqlite_observation(workspace / "workspace.sqlite3"),
        "campaigns": sqlite_observation(workspace / "campaigns.sqlite3"),
    }


def stdout_observation(stream, process, row) -> dict:
    """Separate evidence; never turn a pre-reap sample into a final stream."""
    before = process.poll()
    final_before = (
        type(before) is int
        and type(row.get("exit_code")) is int
        and before == row["exit_code"]
        and row.get("owned_group_remaining") is False
    )
    captured = {}
    capture_stderr(stream, captured)
    return {
        "complete": final_before and process.poll() == before,
        "exit_code": before,
        "record": {
            key.removeprefix("stderr").lstrip("_") or "text": value
            for key, value in captured.items()
        },
    }


def observe_process_streams(stdout, stderr, process, row, observation):
    """Keep both complete-stream observations separate from historical v1 rows."""
    first_error = None
    for name, stream in (("stdout", stdout), ("stderr", stderr)):
        try:
            observation[name] = stdout_observation(stream, process, row)
        except BaseException as error:
            observation[name + "_capture_error_type"] = type(error).__name__
            first_error = first_error or error
    if first_error:
        raise first_error


def operation_observation_argument(observations):
    if observations is None:
        return {}
    if type(observations) is not list:
        raise ValueError("Provide a separate actual offline invocation list.")
    row = {}
    observations.append(row)
    return {"observation": row}


def verify_fictional_workspace(
    binary: Path,
    workspace: Path,
    environment: dict[str, str],
    saved: dict,
    receipt: dict,
    row: dict,
    *,
    operation_observations=None,
) -> None:
    """Check original saved data and the target's explicit connection selection."""
    snapshot = workspace_snapshot(workspace)
    row["workspace_snapshot"] = snapshot
    row["saved_workspace_exact"] = (
        snapshot == receipt["fictional_workspace"]["original"]
    )
    if not row["saved_workspace_exact"]:
        raise RuntimeError(
            "The fictional saved workspace/preferences changed during launch."
        )
    actual = local_operation(
        binary,
        workspace,
        environment,
        "casebooks.get",
        {"id": saved["id"]},
        receipt,
        **operation_observation_argument(operation_observations),
    )
    row["saved_casebook_exact"] = same_json(actual, saved)
    status = local_operation(
        binary,
        workspace,
        environment,
        "runtime.status",
        {},
        receipt,
        **operation_observation_argument(operation_observations),
    )
    expected = {
        key: FICTIONAL_PREFERENCES[key]
        for key in ("api_url", "model", "provider", "max_tokens")
    }
    row["explicit_model_selection_exact"] = same_json(
        status.get("connection"), expected
    )
    row["preferences_read_without_warning"] = status.get("preferences_warning") == ""
    row["offline_status_exact"] = status.get("provider_tested") is False and same_json(
        status.get("counts"),
        {"casebooks": 1, "campaigns": 0, "reports": 0, "watches": 0},
    )
    row["cli_read_preserved_saved_bytes"] = workspace_snapshot(workspace) == snapshot
    if not all(
        row[key]
        for key in (
            "saved_casebook_exact",
            "explicit_model_selection_exact",
            "preferences_read_without_warning",
            "offline_status_exact",
            "cli_read_preserved_saved_bytes",
        )
    ):
        raise RuntimeError(
            "The tested executable did not recover the exact fictional "
            "saved work/settings."
        )


def native_entry_arguments(binary, command):
    """Admit only the fixed native-menu prefix, never an arbitrary command."""
    expected = (str(binary), "app", "--mode", "native")
    if (
        type(command) is not tuple
        or len(command) != len(expected)
        or any(type(part) is not str for part in command)
        or command != expected
    ):
        raise RuntimeError(
            "The native-entry adapter requires the exact tested executable "
            "followed by app --mode native."
        )
    return list(command)


def launch_once(
    binary,
    workspace,
    environment,
    observer,
    row,
    *,
    entry_command=None,
    invocation=None,
    stream_observation=None,
):
    arguments = (
        [str(binary)]
        if entry_command is None
        else native_entry_arguments(binary, entry_command)
    ) + ["--directory", str(workspace)]
    if entry_command is not None:
        if type(invocation) is not dict or invocation:
            raise RuntimeError("Provide a fresh native-entry invocation observation.")
        invocation.update(argv=arguments.copy(), started=False)
    elif invocation is not None:
        raise RuntimeError("Invocation observations require the native-entry adapter.")
    if stream_observation is not None and (
        entry_command is None
        or type(stream_observation) is not dict
        or stream_observation
    ):
        raise RuntimeError(
            "Provide a fresh separate adapted-launch stream observation."
        )
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            arguments,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        if invocation is not None:
            invocation.update(started=True, pid=process.pid)
        if stream_observation is not None:
            stream_observation.update(argv=arguments.copy(), pid=process.pid)
        row.update(pid=process.pid, sigterm_sent=False, forced_cleanup=False)
        try:
            deadline = started + START_SECONDS
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        "Frozen native application exited "
                        "before a mapped window appeared."
                    )
                windows = observer.windows(process.pid, mapped_only=True)
                if windows:
                    row["mapped_windows"] = windows
                    row["mapped_after_seconds"] = round(time.monotonic() - started, 4)
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError(
                    "No mapped native window with matching title "
                    "and process ownership appeared."
                )
        finally:
            try:
                stop_process(process, row)
                row["owned_windows_remaining"] = observer.windows(process.pid)
            finally:
                try:
                    capture_stderr(stderr, row)
                finally:
                    if stream_observation is not None:
                        stream_observation["stdout"] = stdout_observation(
                            stdout, process, row
                        )
                stdout.seek(0)
                row["stdout"] = stdout.read(4096).decode("utf-8", errors="replace")
                row["elapsed_seconds"] = round(time.monotonic() - started, 4)
        if row["stderr_bytes"]:
            raise RuntimeError(
                "Native shutdown emitted diagnostics (including possible "
                "Tk/Tcl callback "
                "failure); a zero exit code is insufficient. See exact stderr evidence."
            )
        if (
            row["exit_code"] != 0
            or not row["sigterm_sent"]
            or row["forced_cleanup"]
            or row["owned_group_remaining"]
            or row["owned_windows_remaining"]
        ):
            raise RuntimeError(
                "Native SIGTERM or owned process/window cleanup "
                "did not complete cleanly."
            )
        row["passed"] = True


def diagnose(binary, environment, evidence=None, *, observation=None):
    if observation is not None and (type(observation) is not dict or observation):
        raise ValueError("Provide a fresh separate diagnostic process observation.")
    evidence = {} if evidence is None else evidence
    evidence["passed"] = False
    cleanup = {"sigterm_sent": False, "forced_cleanup": False}
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            [str(binary), "--diagnose"],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        if observation is not None:
            observation.update(argv=[str(binary), "--diagnose"], pid=process.pid)
        try:
            process.wait(timeout=10)
        finally:
            try:
                stop_process(process, cleanup)
            finally:
                evidence.update(cleanup)
                try:
                    capture_stderr(stderr, evidence)
                finally:
                    if observation is not None:
                        observe_process_streams(
                            stdout, stderr, process, cleanup, observation
                        )
                stdout.seek(0)
                content = stdout.read(32_001)
                evidence["stdout"] = content[:32_000].decode("utf-8", errors="replace")
                evidence["stdout_truncated"] = len(content) > 32_000
    if evidence["stderr_bytes"]:
        raise RuntimeError(
            "Frozen launch diagnostics emitted stderr; see exact retained evidence."
        )
    if (
        cleanup["exit_code"] != 0
        or cleanup["forced_cleanup"]
        or cleanup["owned_group_remaining"]
        or len(content) > 32_000
    ):
        raise RuntimeError(
            "Frozen launch diagnostics failed or exceeded the output bound."
        )
    receipt = json.loads(content)
    if (
        receipt.get("schema") != "sinter-launch-check/v1"
        or not isinstance(receipt.get("version"), str)
        or not receipt["version"]
    ):
        raise RuntimeError("Frozen launch diagnostics have an invalid schema/version.")
    for name in (
        "frozen",
        "core_assets_available",
        "native_toolkit_available",
        "Tcl_resources_available",
        "bundled_Tk_resources_available",
    ):
        if receipt.get(name) is not True:
            raise RuntimeError(f"Frozen launch diagnostics did not establish {name}.")
    evidence["passed"] = True
    return {
        name: receipt[name]
        for name in (
            "schema",
            "version",
            "frozen",
            "core_assets_available",
            "native_toolkit_available",
            "Tcl_resources_available",
            "bundled_Tk_resources_available",
        )
    }


def smoke(
    binary, *, native_entry_command=None, invocation_log=None, entry_observations=None
):
    receipt = {
        "schema": "sinter-frozen-native-window-test/v1",
        "passed": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "system": platform.system(),
        "machine": platform.machine(),
        "launches": [],
        "offline_commands": [],
        "boundary": (
            "Frozen Linux mapped native launch, repeat clean SIGTERM shutdown "
            "and saved fictional workspace/preferences preservation on "
            "supplied X display; not full native editing, installed upgrade "
            "or customer-desktop qualification"
        ),
        "provider_inference_exercised": False,
        "api_credentials_supplied": False,
        "private_workspace_used": False,
        "browser_policy_tested": False,
    }
    observer = None
    try:
        if platform.system() != "Linux":
            raise RuntimeError(
                "This frozen-window qualification tool supports Linux X11 only."
            )
        display = os.environ.get("DISPLAY", "")
        if not re.fullmatch(r":\d+(?:\.\d+)?", display):
            raise RuntimeError(
                "Provide an authorised local DISPLAY, "
                "for example through CI's xvfb-run."
            )
        binary = Path(binary).resolve(strict=True)
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise RuntimeError("Choose an executable frozen Sinter artifact.")
        receipt["binary_sha256"] = binary_digest(binary)
        if native_entry_command is not None:
            native_entry_arguments(binary, native_entry_command)
            if type(invocation_log) is not list or invocation_log:
                raise RuntimeError(
                    "Provide a fresh separate invocation log for the native-entry "
                    "adapter; v1 launch evidence alone does not qualify a menu entry."
                )
            if entry_observations is not None:
                if type(entry_observations) is not dict or entry_observations:
                    raise RuntimeError("Provide fresh separate V3 entry observations.")
                entry_observations.update(
                    streams=[], workspaces=[], offline=[], diagnostic={}
                )
        elif invocation_log is not None:
            raise RuntimeError(
                "Invocation observations require the native-entry adapter."
            )
        elif entry_observations is not None:
            raise RuntimeError(
                "Separate V3 observations require the native-entry adapter."
            )
        observer = X11Observer(display)
        with tempfile.TemporaryDirectory(prefix="sinter-frozen-window-") as temp:
            home = Path(temp)
            workspace = home / "workspace"
            if entry_observations is not None:
                entry_observations["workspace_path"] = str(workspace)
            environment = clean_environment(home, display, os.environ.get("XAUTHORITY"))
            receipt["diagnostic_process"] = {"passed": False}
            receipt["frozen_diagnostics"] = diagnose(
                binary,
                environment,
                receipt["diagnostic_process"],
                **(
                    {"observation": entry_observations["diagnostic"]}
                    if entry_observations is not None
                    else {}
                ),
            )
            workspace.mkdir(mode=0o700)
            (workspace / "preferences.json").write_text(
                json.dumps(FICTIONAL_PREFERENCES, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            saved = local_operation(
                binary,
                workspace,
                environment,
                "casebooks.save",
                {"document": FICTIONAL_DOCUMENT},
                receipt,
                **operation_observation_argument(
                    entry_observations["offline"]
                    if entry_observations is not None
                    else None
                ),
            )
            if (
                not isinstance(saved.get("id"), str)
                or type(saved.get("revision")) is not int
                or saved["revision"] != 1
                or not isinstance(saved.get("document"), dict)
            ):
                raise RuntimeError(
                    "The tested executable did not save the fictional casebook."
                )
            document = saved["document"]
            sources = document.get("documents", [])
            if (
                any(
                    document.get(key) != FICTIONAL_DOCUMENT[key]
                    for key in ("schema", "title", "questions", "document_type")
                )
                or not isinstance(sources, list)
                or len(sources) != 1
                or not isinstance(sources[0], dict)
                or any(
                    sources[0].get(key) != value
                    for key, value in FICTIONAL_DOCUMENT["documents"][0].items()
                )
                or not isinstance(sources[0].get("id"), str)
                or sources[0].get("sha256")
                != hashlib.sha256(
                    FICTIONAL_DOCUMENT["documents"][0]["content"].encode("utf-8")
                ).hexdigest()
            ):
                raise RuntimeError(
                    "The tested executable changed the fictional source inputs."
                )
            receipt["fictional_workspace"] = {
                "original": workspace_snapshot(workspace),
                "source_id": sources[0]["id"],
                "source_sha256": sources[0]["sha256"],
                "saved_revision": saved["revision"],
            }
            verify_fictional_workspace(
                binary,
                workspace,
                environment,
                saved,
                receipt,
                receipt["fictional_workspace"],
                **(
                    {"operation_observations": entry_observations["offline"]}
                    if entry_observations is not None
                    else {}
                ),
            )
            if entry_observations is not None:
                entry_observations["workspaces"].append(
                    {
                        "phase": "original",
                        "snapshot": retained_workspace_snapshot(workspace),
                    }
                )
            for index in (1, 2):
                row = {"launch": index, "passed": False}
                receipt["launches"].append(row)
                try:
                    if native_entry_command is None:
                        launch_once(binary, workspace, environment, observer, row)
                    else:
                        invocation = {}
                        invocation_log.append(invocation)
                        separate = None
                        if entry_observations is not None:
                            separate = {}
                            entry_observations["streams"].append(separate)
                        launch_once(
                            binary,
                            workspace,
                            environment,
                            observer,
                            row,
                            entry_command=native_entry_command,
                            invocation=invocation,
                            **(
                                {"stream_observation": separate}
                                if separate is not None
                                else {}
                            ),
                        )
                except Exception:
                    # Retain original launch failure even if the separate local
                    # preservation check also fails. Neither check replays AI.
                    row["passed"] = False
                    try:
                        verify_fictional_workspace(
                            binary,
                            workspace,
                            environment,
                            saved,
                            receipt,
                            row,
                            **(
                                {
                                    "operation_observations": entry_observations[
                                        "offline"
                                    ]
                                }
                                if entry_observations is not None
                                else {}
                            ),
                        )
                    except Exception as exc:
                        row.update(
                            workspace_verification_error_type=type(exc).__name__,
                            workspace_verification_error=str(exc)[:4096],
                        )
                    raise
                row["passed"] = False
                verify_fictional_workspace(
                    binary,
                    workspace,
                    environment,
                    saved,
                    receipt,
                    row,
                    **(
                        {"operation_observations": entry_observations["offline"]}
                        if entry_observations is not None
                        else {}
                    ),
                )
                row["passed"] = True
                if entry_observations is not None:
                    entry_observations["workspaces"].append(
                        {
                            "phase": "after_launch_" + str(index),
                            "snapshot": retained_workspace_snapshot(workspace),
                        }
                    )
        if entry_observations is not None:
            entry_observations["workspace_removed"] = not home.exists()
        receipt["binary_sha256_after"] = binary_digest(binary)
        receipt["binary_unchanged"] = (
            receipt["binary_sha256_after"] == receipt["binary_sha256"]
        )
        if not receipt["binary_unchanged"]:
            raise RuntimeError("The tested executable changed during qualification.")
        receipt["passed"] = True
    except Exception as exc:
        receipt.update(error_type=type(exc).__name__, error=str(exc)[:4096])
    finally:
        if observer is not None:
            try:
                observer.close()
            except Exception as exc:
                receipt.update(passed=False, display_cleanup_error=type(exc).__name__)
        receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=Path("dist/Sinter/Sinter"))
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.receipt.resolve() == args.binary.resolve() or (
        args.receipt.exists()
        and args.binary.exists()
        and args.receipt.samefile(args.binary)
    ):
        parser.error("The receipt must not overwrite the tested executable.")
    receipt = smoke(args.binary)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        "Frozen native window: "
        + ("passed" if receipt["passed"] else "failed; see receipt")
    )
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
