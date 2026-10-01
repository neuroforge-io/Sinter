"""Qualify frozen Linux native launch on an explicitly supplied local X display.

This checks a mapped, process-owned Tk window, repeat launch, SIGTERM and cleanup.
It never opens a browser, starts an X server, exercises inference or uses a real
workspace. A pass is launch qualification for this artifact/display only.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

TITLE = "Sinter — portable source workspace"
START_SECONDS = 12
STOP_SECONDS = 5
MAX_WINDOWS = 512


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
            stop_process(process, row)
            row["owned_windows_remaining"] = observer.windows(process.pid)
            for name, stream in (("stdout", stdout), ("stderr", stderr)):
                stream.seek(0)
                row[name] = stream.read(4096).decode("utf-8", errors="replace")
            row["elapsed_seconds"] = round(time.monotonic() - started, 4)
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


def diagnose(binary, environment):
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
            stop_process(process, cleanup)
        stdout.seek(0)
        content = stdout.read(32_001)
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
        "boundary": (
            "Frozen Linux native window launch, repeat launch and "
            "SIGTERM cleanup on the supplied X display"
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
        digest = hashlib.sha256()
        with binary.open("rb") as stream:
            while content := stream.read(1024 * 1024):
                digest.update(content)
        receipt["binary_sha256"] = digest.hexdigest()
        observer = X11Observer(display)
        with tempfile.TemporaryDirectory(prefix="sinter-frozen-window-") as temp:
            home = Path(temp)
            workspace = home / "workspace"
            environment = clean_environment(home, display, os.environ.get("XAUTHORITY"))
            receipt["frozen_diagnostics"] = diagnose(binary, environment)
            for index in (1, 2):
                row = {"launch": index, "passed": False}
                receipt["launches"].append(row)
                launch_once(binary, workspace, environment, observer, row)
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
