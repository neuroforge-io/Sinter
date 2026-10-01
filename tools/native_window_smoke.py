"""Qualify frozen Linux native launch on an explicitly supplied local X display.

This checks a mapped, process-owned Tk window, repeat launch, clean SIGTERM
shutdown and preservation of saved fictional sources/preferences.
It never opens a browser, starts an X server, exercises inference or uses a real
workspace. A pass is launch qualification for this artifact/display only.
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
) -> dict:
    """Use only the tested executable's offline CLI, retaining failure evidence."""
    if operation not in {"casebooks.save", "casebooks.get", "runtime.status"}:
        raise ValueError(
            "Native launch qualification allows only fictional local operations."
        )
    request = workspace.parent / "qualification-request.json"
    request.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    row = {"operation": operation, "passed": False}
    receipt["offline_commands"].append(row)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            [
                str(binary),
                "run",
                operation,
                "--input",
                str(request),
                "--directory",
                str(workspace),
                "--format",
                "json",
            ],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        row["pid"] = process.pid
        try:
            process.wait(timeout=10)
        finally:
            try:
                stop_process(process, row)
            finally:
                capture_stderr(stderr, row)
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
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
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


def verify_fictional_workspace(
    binary: Path,
    workspace: Path,
    environment: dict[str, str],
    saved: dict,
    receipt: dict,
    row: dict,
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
        binary, workspace, environment, "casebooks.get", {"id": saved["id"]}, receipt
    )
    row["saved_casebook_exact"] = same_json(actual, saved)
    status = local_operation(
        binary, workspace, environment, "runtime.status", {}, receipt
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


def launch_once(binary, workspace, environment, observer, row):
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            [str(binary), "--directory", str(workspace)],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
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
                capture_stderr(stderr, row)
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


def diagnose(binary, environment, evidence=None):
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
        try:
            process.wait(timeout=10)
        finally:
            try:
                stop_process(process, cleanup)
            finally:
                evidence.update(cleanup)
                capture_stderr(stderr, evidence)
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


def smoke(binary):
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
        observer = X11Observer(display)
        with tempfile.TemporaryDirectory(prefix="sinter-frozen-window-") as temp:
            home = Path(temp)
            workspace = home / "workspace"
            environment = clean_environment(home, display, os.environ.get("XAUTHORITY"))
            receipt["diagnostic_process"] = {"passed": False}
            receipt["frozen_diagnostics"] = diagnose(
                binary, environment, receipt["diagnostic_process"]
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
            )
            for index in (1, 2):
                row = {"launch": index, "passed": False}
                receipt["launches"].append(row)
                try:
                    launch_once(binary, workspace, environment, observer, row)
                except Exception:
                    # Retain original launch failure even if the separate local
                    # preservation check also fails. Neither check replays AI.
                    row["passed"] = False
                    try:
                        verify_fictional_workspace(
                            binary, workspace, environment, saved, receipt, row
                        )
                    except Exception as exc:
                        row.update(
                            workspace_verification_error_type=type(exc).__name__,
                            workspace_verification_error=str(exc)[:4096],
                        )
                    raise
                row["passed"] = False
                verify_fictional_workspace(
                    binary, workspace, environment, saved, receipt, row
                )
                row["passed"] = True
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
