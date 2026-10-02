"""Own two separate installed proofs and an explicit native/browser handoff.

This development tool never uses the customer's desktop, workspace, accounts or
provider. The unchanged four-launch gate runs first. A fresh network-none
container then owns one continuing installed native process and authenticated
Xvfb; a private host Chromium reaches only its listener through an owned relay.
"""

from __future__ import annotations

import argparse
import base64
import copy
import http.client
import json
import os
import platform
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import installed_native_container as owner  # noqa: E402
from tools import installed_native_entry_contract as old  # noqa: E402
from tools import installed_native_menu as menu  # noqa: E402
from tools import installed_native_tk as tk_driver  # noqa: E402
from tools import installed_workflow_browser as transport  # noqa: E402
from tools import native_window_smoke as native  # noqa: E402
from tools import rc4_native_handoff_contract as contract  # noqa: E402
from tools.rc4_recovery_worker import snapshot  # noqa: E402


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def original(raw):
    return {
        "bytes": len(raw),
        "sha256": old.sha(raw),
        "base64": base64.b64encode(raw).decode("ascii"),
    }


class Cleanup:
    """Independent cleanup attempts retain secondary failures without masking work."""

    def __init__(self):
        self.errors = []
        self.first_error = None

    def call(self, role, callback):
        try:
            return callback()
        except BaseException as error:
            if self.first_error is None:
                self.first_error = error
            self.errors.append(
                {
                    "role": role,
                    "error_type": type(error).__name__,
                    "error": str(error)[:4096],
                }
            )
            return None


@contextmanager
def owned_streams(cleanup):
    """Close both private native stream files without replacing a body failure."""
    streams = {}
    try:
        for name in ("stdout", "stderr"):
            streams[name] = tempfile.TemporaryFile()
        yield streams["stdout"], streams["stderr"]
    finally:
        for name, stream in streams.items():
            cleanup.call("native-stream." + name + ".close", stream.close)


def start_playwright(factory, environment):
    """Start only the owned driver with the same private no-account environment."""
    previous = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(environment)
        return factory().start()
    finally:
        os.environ.clear()
        os.environ.update(previous)


def read_json(path, limit=2 * 1024 * 1024):
    return old.json_object(menu.regular_bytes(Path(path), limit))


def wait_file(path, predicate=lambda value: True, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            value = read_json(path)
            if "error_type" in value:
                raise RuntimeError("Owned peer failed: " + value["error_type"])
            if predicate(value):
                return value
        time.sleep(0.04)
    raise TimeoutError("Owned peer did not finish its fixed phase: " + path.name)


def capture_url(output, url):
    """Only a closed native webbrowser launcher; it neither fetches nor opens UI."""
    old.require(
        Path("/.dockerenv").is_file()
        and platform.system() == "Linux"
        and {p.name for p in Path("/sys/class/net").iterdir()} == {"lo"},
        "URL capture belongs only to the owned network-none container.",
    )
    port = contract.url_port(url)
    output = Path(output)
    old.require(
        output.parent.resolve() == Path("/out/handoff")
        and output.name == "launch.json"
        and not os.path.lexists(output),
        "Capture exactly one owned native launch address.",
    )
    write_json(
        output,
        {"url": url, "port": port, "pid": os.getpid(), "owner_pid": os.getppid()},
    )


class HandoffDriver(tk_driver.Driver):
    """Fixed widget actions only. No script/command argument is exposed."""

    def later(self, *arguments):
        self.send("after", 0, self.tk.call("list", *arguments))

    def modal(self, title, choice):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            matches = [
                p
                for p in self.widgets()
                if str(self.send("winfo", "toplevel", p)) == p
                and str(self.send("wm", "title", p)) == title
            ]
            if len(matches) == 1:
                dialog = matches[0]
                buttons = [
                    p
                    for p in self.widgets(dialog)
                    if self.kind(p) in {"TButton", "Button"}
                    and str(self.send(p, "cget", "-text")).lower() == choice.lower()
                ]
                if len(buttons) != 1:
                    raise ValueError("Missing or ambiguous fixed modal choice.")
                self.later(buttons[0], "invoke")
                return
            if len(matches) > 1:
                raise ValueError("The native modal identity is ambiguous.")
            time.sleep(0.025)
        raise TimeoutError("Native confirmation did not appear: " + title)

    def field_values(self):
        title, questions, source_title, source_text, _ = self.fields()
        return [
            str(self.send(title, "get")),
            str(self.send(questions, "get", "1.0", "end-1c")),
            str(self.send(source_title, "get")),
            str(self.send(source_text, "get", "1.0", "end-1c")),
        ]

    def status(self, contains=None, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            labels = [
                str(self.send(p, "cget", "-text"))
                for p in self.widgets()
                if self.kind(p) == "TLabel"
            ]
            matches = [text for text in labels if contains is None or contains in text]
            if contains is not None and len(matches) == 1:
                return matches[0]
            time.sleep(0.025)
        if contains is None:
            return ""
        raise TimeoutError("The actual native status did not appear: " + contains)

    def close_confirmation(self):
        self.modal("Close Sinter and its workbench?", "Yes")
        self.modal("Unsaved source edits", "No")

    def run_handoff(self, phase):
        old.require(
            type(phase) is str and phase in contract.PHASES,
            "Unknown fixed native control phase.",
        )
        controls, status = [], ""
        if phase == "refuse-scoped":
            self.send(self.button("Fictional example"), "invoke")
            self.send("update")
            title, questions, source_title, source_text, tree = self.fields()
            self.select_source(tree)
            for path, value, text in zip(
                (title, questions, source_title, source_text),
                contract.FIELDS,
                (False, True, False, True),
            ):
                self.replace(path, value, text=text)
            tree = self.saved_tree()
            items = self.tk.splitlist(self.send(tree, "children", ""))
            matches = [
                item
                for item in items
                if str(self.send(tree, "item", item, "-text"))
                == contract.scoped_fixture()["title"]
            ]
            # The two fixed titles distinguish their actual saved IDs in the
            # visible catalogue; neither ID is supplied as a control payload.
            if len(matches) != 1:
                raise ValueError(
                    "Scoped saved project is missing or ambiguous in the actual catalogue."
                )
            self.send(tree, "selection", "set", matches[0])
            self.later(self.button("Open project"), "invoke")
            self.modal("Keep unsaved work?", "Yes")
            self.modal("Sinter — action could not finish", "OK")
            status = self.status("no choices were cleared")
            controls = [
                "Fictional example",
                "Open project",
                "Keep unsaved work?:Yes",
                "Sinter — action could not finish:OK",
            ]
        else:
            old.exact(
                self.field_values(),
                list(contract.FIELDS),
                "Unsaved native fields changed.",
            )
            if phase == "open-browser":
                self.later(self.button("Open full workbench"), "invoke")
                self.modal("Open full workbench", "No")
                status = self.status("Browser launch requested")
                controls = ["Open full workbench", "Open full workbench:No"]
            elif phase == "native-no":
                self.modal("Close Sinter and its workbench?", "No")
                controls = ["Close Sinter and its workbench?:No"]
            elif phase in {"close-keep", "close-timeout"}:
                protocol = str(self.send("wm", "protocol", ".", "WM_DELETE_WINDOW"))
                old.require(
                    re.fullmatch(r"[0-9]+request_close", protocol),
                    "No actual WM close control.",
                )
                self.later(protocol)
                self.close_confirmation()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    try:
                        self.button("Keep window open")
                        break
                    except ValueError:
                        time.sleep(0.025)
                else:
                    raise TimeoutError("Close did not enter cancellable draining.")
                controls = [
                    "WM_DELETE_WINDOW",
                    "Close Sinter and its workbench?:Yes",
                    "Unsaved source edits:No",
                ]
            elif phase == "cancel-keep":
                self.send(self.button("Keep window open"), "invoke")
                controls = ["Keep window open"]
                status = self.status("Close cancelled. Both views")
            elif phase == "inspect-timeout":
                status = self.status("Close refused:", timeout=9)
            elif phase == "close-final":
                self.close_confirmation()
                controls = [
                    "Close Sinter and its workbench?:Yes",
                    "Unsaved source edits:No",
                ]
                # The final confirmation closes the peer; do not query a dead
                # interpreter or invent a post-exit in-memory observation.
                return controls, "", list(contract.FIELDS)
        fields = self.field_values()
        old.exact(
            fields, list(contract.FIELDS), "Native edits were replaced or cleared."
        )
        return controls, status, fields


def driver(request_path):
    import tkinter as tk

    # Reuse the old private display/request ownership guard, but admit this
    # distinct closed phase schema locally rather than widening its v1 schema.
    tk_driver.admit_environment(request_path)
    request = contract.action_request(read_json(request_path, 8192))
    root = tk.Tk()
    primary = None
    try:
        root.withdraw()
        ui = HandoffDriver(
            root, [int(w, 16) for w in request["window_ids"]], request["pid"]
        )
        controls, status, fields = ui.run_handoff(request["phase"])
        return {
            "schema": "sinter-native-handoff-action/v1",
            "phase": request["phase"],
            "pid": request["pid"],
            "window_id": ui.frame,
            "controls": controls,
            "status": status,
            "fields": fields,
        }
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            root.destroy()
        except BaseException as cleanup_error:
            if primary is not None:
                # Keep the original selected exception and both actual traces.
                # The child's retained stderr records the explicit cleanup cause.
                raise primary from cleanup_error
            raise


def cli(workspace, environment, role, name, payload, rows):
    path = workspace.parent / (role + ".json")
    write_json(path, payload)
    code, raw = menu.command(
        [
            menu.BINARY,
            "run",
            name,
            "--input",
            str(workspace) + "/../" + path.name,
            "--directory",
            workspace,
            "--format",
            "json",
        ],
        rows,
        env=environment,
        timeout=15,
    )
    row = rows[-1]
    row.update(
        role=role, input=copy.deepcopy(payload), input_bytes=original(path.read_bytes())
    )
    old.require(
        code == 0
        and old.stream_bytes(row["stderr"])
        == (b"Ready for review\n" if name == "casebooks.build" else b""),
        "Installed local preparation failed or emitted an unknown diagnostic.",
    )
    result = old.json_object(raw)
    old.require(result.get("ok") is True, "Installed CLI operation did not complete.")
    return result["result"]


def port_closed(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return False
    except ConnectionRefusedError:
        return True


def disk_snapshot(workspace):
    value = snapshot(workspace)
    value["preferences_bytes"] = original((workspace / "preferences.json").read_bytes())
    return value


def session_response(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/api/session")
        response = connection.getresponse()
        return {"status": response.status, "body": original(response.read(128_000))}
    finally:
        connection.close()


def interrupted_body(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/api/session")
        response = connection.getresponse()
        old.require(
            response.status == 200,
            "Interrupted fixture could not observe its own session.",
        )
        token = old.json_object(response.read(128_000))["token"]
    finally:
        connection.close()
    request = (
        f"POST /api/casebooks/save HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        f"Origin: http://127.0.0.1:{port}\r\nX-Sinter-Token: {token}\r\n"
        'Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{"document":'
    )
    with socket.create_connection(("127.0.0.1", port), timeout=5) as channel:
        channel.sendall(request.encode())
        channel.shutdown(socket.SHUT_WR)
        received = bytearray()
        while chunk := channel.recv(4096):
            received.extend(chunk)
            old.require(
                len(received) < 128_000, "Interrupted response exceeded its bound."
            )
    return {
        "attempts": 1,
        "request": original(request.encode()),
        "response": original(bytes(received)),
    }


def inside(args):
    old.require(
        ROOT == Path("/source")
        and args.output == Path("/out/handoff")
        and args.repository == Path("/repository")
        and args.installer.parent == Path("/candidate")
        and args.package_receipt.parent == Path("/candidate"),
        "Internal producer paths are fixed to the owned container namespace.",
    )
    args.output.mkdir(mode=0o777, exist_ok=False)
    args.output.chmod(0o777)
    result = {
        "schema": contract.SCHEMA,
        "qualification": args.qualification,
        "passed": False,
        "commands": [],
        "seed": [],
        "actions": [],
        "snapshots": {},
        "cleanup": {},
    }
    attempted, process, relay, relay_thread, held = False, None, None, None, None
    cleanup = Cleanup()
    try:
        old.exact(
            sys.executable,
            contract.PYTHON,
            "Use the unchanged image's exact qualification interpreter.",
        )
        old.require(
            platform.system() == "Linux"
            and os.geteuid() == 0
            and Path("/.dockerenv").is_file()
            and {p.name for p in Path("/sys/class/net").iterdir()} == {"lo"}
            and not os.environ.get("DISPLAY"),
            "Use the fresh isolated Linux container only.",
        )
        result["container"] = {
            "effective_uid": 0,
            "interfaces": ["lo"],
            "inherited_display": False,
            "docker_marker_present": True,
        }
        old.require(
            menu.package_state(result["commands"]) == "absent"
            and not any(
                os.path.lexists(p)
                for p in (
                    menu.BINARY,
                    menu.ENTRY_DIR / "sinter.desktop",
                    menu.ENTRY_DIR / "sinter-native.desktop",
                )
            ),
            "Existing package or residual paths cannot qualify.",
        )
        args.source_route = "archive"
        result["source_origin"] = {}
        source = result["source"] = menu.selected_source_identity(
            args, result["commands"], result["source_origin"]
        )
        result["archive_bytes"] = (args.repository / menu.ARCHIVE_NAME).stat().st_size
        result["installer_name"] = args.installer.name
        old.require(
            args.qualification == "dev" or source["version"] == "0.5.4rc4",
            "Candidate handoff binds only the final RC4 source, never a DEV package.",
        )
        result["tools"] = {name: source["files"][name] for name in contract.FILES}
        package = result["package"] = menu.package_preflight(
            args, source, result["commands"]
        )
        attempted = True
        code, _ = menu.command(
            ["dpkg", "-i", args.installer], result["commands"], timeout=60
        )
        old.require(
            code == 0
            and menu.package_state(result["commands"]) == "install ok installed",
            "Explicit fresh handoff installation failed.",
        )
        result["installed_package"] = menu.installed_package_version(
            package["package_version"], result["commands"]
        )
        result["installed_entries"], result["installed_binary"] = {}, {}
        prefix = menu.installed_identity(
            package,
            observations=result["installed_entries"],
            binary_observation=result["installed_binary"],
        )
        home = args.output / "home"
        home.mkdir(mode=0o700)
        result["display_evidence"] = {"commands": []}
        with menu.display(home, result["display_evidence"]) as (display, authority):
            environment = native.clean_environment(home, display, authority)
            workspace = home / "workspace"
            workspace.mkdir(mode=0o700)
            (workspace / "preferences.json").write_text(
                json.dumps(native.FICTIONAL_PREFERENCES, ensure_ascii=True),
                encoding="utf-8",
            )
            result["workspace"] = str(workspace)
            legacy = cli(
                workspace,
                environment,
                "save-legacy",
                "casebooks.save",
                {"document": contract.fixture()},
                result["seed"],
            )
            scoped = cli(
                workspace,
                environment,
                "save-scoped",
                "casebooks.save",
                {"document": contract.scoped_fixture()},
                result["seed"],
            )
            built = cli(
                workspace,
                environment,
                "build-legacy",
                "casebooks.build",
                {"id": legacy["id"], "revision": legacy["revision"]},
                result["seed"],
            )
            report = {
                **built,
                "markdown": contract.HISTORY + "\n\n" + built["markdown"],
            }
            cli(
                workspace,
                environment,
                "save-history",
                "reports.save",
                {"report": report},
                result["seed"],
            )
            cli(workspace, environment, "status", "runtime.status", {}, result["seed"])
            result["selected_scoped_id"] = scoped["id"]
            result["snapshots"]["before_native"] = disk_snapshot(workspace)
            environment["BROWSER"] = (
                f"{sys.executable} -B /source/tools/rc4_native_handoff.py _capture --output /out/handoff/launch.json %s"
            )
            observer = native.X11Observer(display)
            row = result["owner"] = {
                "argv": [*prefix, "--directory", str(workspace)],
                "workspace_home": str(home),
            }
            with owned_streams(cleanup) as (stdout, stderr):
                try:
                    process = subprocess.Popen(
                        row["argv"],
                        env=environment,
                        stdin=subprocess.DEVNULL,
                        stdout=stdout,
                        stderr=stderr,
                        start_new_session=True,
                    )
                    row["pid"] = process.pid
                    deadline = time.monotonic() + native.START_SECONDS
                    while time.monotonic() < deadline:
                        old.require(
                            process.poll() is None,
                            "Native owner stopped before its window appeared.",
                        )
                        windows = observer.windows(process.pid, mapped_only=True)
                        if len(windows) == 1:
                            row["mapped_windows"] = windows
                            break
                        time.sleep(0.05)
                    else:
                        raise TimeoutError("No mapped installed native owner window.")

                    def action(phase):
                        request = {
                            "phase": phase,
                            "pid": process.pid,
                            "window_ids": [windows[0]["window_id"]],
                        }
                        path = home / (phase + "-request.json")
                        write_json(path, request)
                        path.chmod(0o600)
                        rows = []
                        observation = {
                            "phase": phase,
                            "request": request,
                            "request_bytes": original(path.read_bytes()),
                        }
                        result["actions"].append(observation)
                        try:
                            code, raw = menu.command(
                                [
                                    sys.executable,
                                    "-B",
                                    ROOT / contract.FILES[0],
                                    "_driver",
                                    "--request",
                                    path,
                                ],
                                rows,
                                env=environment,
                                timeout=14,
                            )
                        finally:
                            if rows:
                                observation["command"] = rows[0]
                        old.require(code == 0, "Actual native control failed: " + phase)
                        value = old.json_object(raw)
                        observation["result"] = value

                    action("refuse-scoped")
                    result["snapshots"]["after_refusal"] = disk_snapshot(workspace)
                    action("open-browser")
                    launched = wait_file(args.output / "launch.json")
                    result.update(
                        url=launched["url"], port=launched["port"], launch=launched
                    )
                    result["snapshots"]["after_browser"] = disk_snapshot(workspace)
                    relay = transport.InnerRelay(args.output)
                    relay.port = result["port"]
                    relay_thread = threading.Thread(
                        target=relay.serve_forever, daemon=True
                    )
                    relay_thread.start()
                    write_json(
                        args.output / "state.json",
                        {"phase": "ready", "port": result["port"]},
                    )
                    phases = (
                        "native-no",
                        "hold-request",
                        "close-keep",
                        "cancel-keep",
                        "close-timeout",
                        "inspect-timeout",
                        "release-request",
                        "interrupt-request",
                        "close-final",
                    )
                    timeout_started = None
                    for phase in phases:
                        command = wait_file(
                            args.output / "control.json",
                            lambda v: v.get("phase") == phase,
                            40,
                        )
                        old.exact(
                            command,
                            {"phase": phase},
                            "Only the next fixed peer phase is permitted.",
                        )
                        if phase in contract.PHASES:
                            if phase == "close-timeout":
                                timeout_started = time.monotonic_ns()
                            action(phase)
                            if phase == "inspect-timeout":
                                result["timeout_ns"] = (
                                    time.monotonic_ns() - timeout_started
                                )
                                result["snapshots"]["after_timeout"] = disk_snapshot(
                                    workspace
                                )
                            elif phase == "cancel-keep":
                                result["snapshots"]["after_keep"] = disk_snapshot(
                                    workspace
                                )
                        elif phase == "hold-request":
                            held = socket.create_connection(
                                ("127.0.0.1", result["port"]), timeout=10
                            )
                            time.sleep(0.15)
                            result["hold"] = {
                                "fixture": "admitted empty TCP connection",
                                "admitted": True,
                                "released_explicitly": False,
                                "session": session_response(result["port"]),
                            }
                        elif phase == "release-request":
                            held.shutdown(socket.SHUT_WR)
                            held.close()
                            held = None
                            result["hold"]["released_explicitly"] = True
                        elif phase == "interrupt-request":
                            result["interrupted"] = interrupted_body(result["port"])
                            result["snapshots"]["before_final"] = disk_snapshot(
                                workspace
                            )
                        write_json(
                            args.output / "state.json",
                            {"phase": phase, "port": result["port"]},
                        )
                    row["exit_code"] = process.wait(timeout=8)
                finally:
                    if held is not None:
                        cleanup.call("held-request.close", held.close)
                    if relay is not None:
                        cleanup.call("inner-relay.shutdown", relay.shutdown)
                        cleanup.call("inner-relay.server_close", relay.server_close)
                        cleanup.call(
                            "inner-relay.thread.join",
                            lambda: relay_thread.join(timeout=2),
                        )
                        cleanup.call(
                            "inner-relay.socket.remove",
                            lambda: (args.output / "relay.sock").unlink(
                                missing_ok=True
                            ),
                        )
                    if process is not None:
                        cleanup.call(
                            "native.stop", lambda: native.stop_process(process, row)
                        )
                        row["owned_windows_remaining"] = cleanup.call(
                            "native.windows", lambda: observer.windows(process.pid)
                        )
                        cleanup.call(
                            "native.stderr", lambda: native.capture_stderr(stderr, row)
                        )
                        observed = cleanup.call(
                            "native.stdout",
                            lambda: native.stdout_observation(stdout, process, row),
                        )
                        if observed is not None:
                            row.update(
                                stdout=observed["record"],
                                stdout_complete=observed["complete"],
                            )
                    cleanup.call("observer.close", observer.close)
            result["snapshots"]["after_exit"] = disk_snapshot(workspace)
            result["reads"] = []
            cli(
                workspace,
                environment,
                "read-scoped",
                "casebooks.get",
                {"id": scoped["id"]},
                result["reads"],
            )
            result["snapshots"]["after_read"] = disk_snapshot(workspace)
            result["cleanup"].update(
                listener_closed=port_closed(result["port"]),
                inner_relay_stopped=not relay_thread.is_alive(),
                inner_socket_absent=not os.path.lexists(args.output / "relay.sock"),
            )
        result["cleanup"]["display_stopped"] = (
            result["display_evidence"]["display"]["passed"] is True
        )
        result["installed_entries_after"], result["installed_binary_after"] = {}, {}
        menu.installed_identity(
            package,
            observations=result["installed_entries_after"],
            binary_observation=result["installed_binary_after"],
        )
        old.require(
            not cleanup.errors,
            "Owned inner cleanup failed; see retained secondary diagnostics.",
        )
        result["passed"] = True
    except BaseException as error:
        result.update(
            passed=False, error_type=type(error).__name__, error=str(error)[:4096]
        )
        cleanup.call(
            "retain-peer-error",
            lambda kind=type(error).__name__: write_json(
                args.output / "state.json", {"error_type": kind}
            ),
        )
    finally:
        if attempted:
            try:
                removal_code, _ = menu.command(
                    ["dpkg", "-r", "sinter"], result["commands"], timeout=60
                )
                result["removal"] = result["commands"][-1]
                state = menu.removal_state(result["commands"])
                result["removal_state"] = {
                    "package_status": state["package_state"],
                    "paths_absent": not state["remaining_paths"],
                }
                result["absence"] = menu.observed_absence(
                    [
                        menu.BINARY,
                        menu.ENTRY_DIR / "sinter.desktop",
                        menu.ENTRY_DIR / "sinter-native.desktop",
                    ],
                    result["commands"],
                )
                result["cleanup"]["package_paths_absent"] = state["passed"]
                if removal_code != 0 or state["passed"] is not True:
                    result["passed"] = False
            except BaseException as error:
                result["passed"] = False
                cleanup.errors.append(
                    {
                        "role": "package-removal",
                        "error_type": type(error).__name__,
                        "error": str(error)[:4096],
                    }
                )
        if cleanup.errors:
            result["secondary_cleanup_errors"] = cleanup.errors
        write_json(args.output / "inner.json", result)
    return 0 if result["passed"] is True else 1


def control(root, phase):
    write_json(root / "control.json", {"phase": phase})
    return wait_file(root / "state.json", lambda state: state.get("phase") == phase, 35)


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def children():
    """Read only this Linux main thread's owned child IDs, never host inventory."""
    raw = menu.regular_bytes(Path(f"/proc/self/task/{os.getpid()}/children"), 8192)
    old.require(
        re.fullmatch(rb"(?:[0-9]+ ?)*", raw), "Owned-child process observation differs."
    )
    return {int(value) for value in raw.split()}


def browser(root, executable):
    from playwright.sync_api import expect, sync_playwright

    wait_file(root / "state.json", lambda v: v.get("phase") == "ready", 90)
    proof = {
        "schema": "sinter-rc4-native-handoff-browser/v2",
        "page_errors": [],
        "external_requests": 0,
        "quit_posts": 0,
        "visible_checks": [],
        "quit_attempts": [],
        "screenshots": {},
        "chromium": {
            "path": str(executable),
            "sha256": native.binary_digest(executable),
            "sha256_after": None,
        },
    }
    chrome, context, relay, thread = None, None, None, None
    browser_home = root.parent.parent / "client/browser-home"
    old_tmp = os.environ.get("TMPDIR")
    primary = None
    playwright = None
    chrome_process = None
    chrome_streams = {}
    try:
        browser_home.mkdir(mode=0o700)
        (browser_home / "tmp").mkdir(mode=0o700)
        os.environ["TMPDIR"] = str(browser_home / "tmp")
        previous_children = children()
        for name in ("stdout", "stderr"):
            chrome_streams[name] = tempfile.TemporaryFile()
        relay = transport.Relay(root)
        thread = threading.Thread(target=relay.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{relay.server_address[1]}"
        proof.update(origin=origin, relay_port=relay.server_address[1])
        browser_environment = {
            "PATH": os.defpath,
            "HOME": str(browser_home),
            "TMPDIR": str(browser_home / "tmp"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        playwright = start_playwright(sync_playwright, browser_environment)
        new_children = children() - previous_children
        old.require(
            len(new_children) == 1,
            "One continuing owned Playwright driver is required.",
        )
        driver_pid = next(iter(new_children))
        driver_path = Path(os.readlink(f"/proc/{driver_pid}/exe"))
        import playwright as installed_playwright

        expected_driver = (
            Path(installed_playwright.__file__).resolve().parent / "driver/node"
        )
        old.exact(
            str(driver_path),
            str(expected_driver),
            "The owned browser driver executable differs.",
        )
        proof["driver_process"] = {
            "pid": driver_pid,
            "path": str(driver_path),
            "sha256": native.binary_digest(driver_path),
            "sha256_after": None,
        }
        chrome_row = proof["chromium_process"] = {
            "argv": contract.chromium_argv(browser_home)
        }
        chrome_process = subprocess.Popen(
            chrome_row["argv"],
            stdin=subprocess.DEVNULL,
            stdout=chrome_streams["stdout"],
            stderr=chrome_streams["stderr"],
            start_new_session=True,
            env=browser_environment,
        )
        chrome_row["pid"] = chrome_process.pid
        deadline = time.monotonic() + 10
        active_file = browser_home / "profile/DevToolsActivePort"
        while time.monotonic() < deadline:
            old.require(
                chrome_process.poll() is None,
                "Owned Chromium exited before its private debugger appeared.",
            )
            if active_file.is_file():
                active = (
                    menu.regular_bytes(active_file, 1024).decode("ascii").splitlines()
                )
                if (
                    len(active) == 2
                    and re.fullmatch(r"[0-9]{1,5}", active[0])
                    and re.fullmatch(r"/devtools/browser/[0-9a-f-]+", active[1])
                ):
                    proof["debug_port"] = int(active[0])
                    old.require(
                        0 < proof["debug_port"] <= 65535, "Debugger port is invalid."
                    )
                    break
            time.sleep(0.025)
        else:
            raise TimeoutError("Owned Chromium debugger did not appear.")
        chrome = playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{proof['debug_port']}"
        )
        cdp = chrome.new_browser_cdp_session()
        proof["browser_pids"] = [
            int(p["id"]) for p in cdp.send("SystemInfo.getProcessInfo")["processInfo"]
        ]
        proof["chromium"]["version"] = chrome.version
        context = chrome.new_context()
        context.route_web_socket("**/*", lambda channel: channel.close())

        def route(request):
            if not request.request.url.startswith(origin + "/"):
                proof["external_requests"] += 1
                request.abort()
            else:
                request.continue_()

        context.route("**/*", route)
        page = context.new_page()

        def screen(name):
            raw = page.screenshot(path=str(root / name), full_page=True)
            proof["screenshots"][name] = {"bytes": len(raw), "sha256": old.sha(raw)}

        page.on("pageerror", lambda error: proof["page_errors"].append(str(error)))
        page.on(
            "request",
            lambda request: (
                proof.update(quit_posts=proof["quit_posts"] + 1)
                if request.method == "POST"
                and request.url == origin + "/api/desktop/quit"
                else None
            ),
        )

        def observe_response(response):
            path = response.url.removeprefix(origin)
            if re.fullmatch(r"/api/casebooks/[0-9a-f]{32}", path):
                old.require(
                    "scoped_response" not in proof,
                    "The project was automatically fetched twice.",
                )
                proof["scoped_response"] = {
                    "path": path,
                    "method": response.request.method,
                    "capability": response.request.header_value(
                        "X-Sinter-Casebook-Schema"
                    ),
                    "status": response.status,
                    "body": original(response.body()),
                }
            elif path == "/api/desktop/quit" and response.request.method == "POST":
                old.require(
                    "confirmed_ack" not in proof,
                    "A confirmed quit request was replayed.",
                )
                proof["confirmed_ack"] = {
                    "status": response.status,
                    "body": original(response.body()),
                }

        page.on("response", observe_response)
        page.goto(origin + "/#casebooks")
        expect(
            page.get_by_text(
                "Same local workspace. Keep the Sinter window open.", exact=True
            )
        ).to_be_visible()
        proof["native_notice"] = "Same local workspace. Keep the Sinter window open."
        tile = page.locator("article.casebook-tile").filter(
            has=page.get_by_text(contract.scoped_fixture()["title"], exact=True)
        )
        expect(tile).to_have_count(1)
        tile.get_by_role("button", name="Open project", exact=True).click()
        expect(page.get_by_label("Project name", exact=True)).to_have_value(
            contract.scoped_fixture()["title"]
        )
        originals = page.locator("details.source").filter(
            has=page.get_by_role("button", name="Remove source", exact=True)
        )
        expect(originals).to_have_count(3)
        for row, source in zip(originals.all(), contract.fixture()["documents"]):
            if row.get_attribute("open") is None:
                row.locator("summary").click()
            expect(row.locator("pre")).to_have_text(source["content"])
        scope = page.locator("details.card").filter(
            has=page.get_by_text("Choose sources for each question", exact=True)
        )
        scope.locator("summary").first.click()
        question_rows = scope.locator("details.source")
        for row in question_rows.all():
            row.locator("summary").click()
        expect(page.get_by_label("Sources for question 1", exact=True)).to_have_value(
            "selected"
        )
        expect(page.get_by_label("Sources for question 2", exact=True)).to_have_value(
            "selected"
        )
        expect(page.get_by_label("Sources for question 3", exact=True)).to_have_value(
            "all"
        )
        expect(
            page.get_by_label("Question 2 source count", exact=True)
        ).to_contain_text("No source will be searched")
        proof["visible_checks"] += ["full-originals", "scoped-capability"]
        screen("browser-scoped.png")
        page.get_by_label("Project name", exact=True).fill(contract.BROWSER_TITLE)
        proof["title"] = page.get_by_label("Project name", exact=True).input_value()
        page.get_by_role("button", name="Quit Sinter", exact=True).click()
        page.get_by_role("button", name="Keep working", exact=True).click()
        expect(page.get_by_label("Project name", exact=True)).to_have_value(
            contract.BROWSER_TITLE
        )
        old.require(
            proof["quit_posts"] == 0, "Keep working unexpectedly sent a quit request."
        )
        proof["quit_attempts"].append("keep-working:no-post")
        proof["visible_checks"].append("keep-working")

        def lose_ack(route):
            response = route.fetch()
            proof["lost_ack_status"] = response.status
            proof["lost_ack_body"] = original(response.body())
            control(root, "native-no")
            route.abort()

        page.route("**/api/desktop/quit", lose_ack, times=1)
        page.get_by_role("button", name="Quit Sinter", exact=True).click()
        page.get_by_role("button", name="Request quit", exact=True).click()
        expect(
            page.locator(".notice.error")
            .filter(has_text="Quit was not confirmed")
            .first
        ).to_be_visible()
        expect(page.get_by_label("Project name", exact=True)).to_have_value(
            contract.BROWSER_TITLE
        )
        proof["quit_attempts"].append("lost-ack:uncertain:no-replay")
        proof["visible_checks"] += ["uncertain-quit-inputs-kept", "native-cancelled"]
        screen("browser-uncertain.png")
        control(root, "hold-request")
        control(root, "close-keep")
        control(root, "cancel-keep")
        expect(
            page.get_by_text("Quit cancelled. Both views stay open.", exact=True)
        ).to_be_visible()
        proof["visible_checks"].append("drain-cancelled")
        control(root, "close-timeout")
        control(root, "inspect-timeout")
        expect(
            page.get_by_text(
                "Close refused: local work is still running. Both views stay open. Nothing was retried.",
                exact=True,
            )
        ).to_be_visible()
        expect(page.get_by_label("Project name", exact=True)).to_have_value(
            contract.BROWSER_TITLE
        )
        proof["visible_checks"].append("timeout-refused")
        screen("browser-timeout.png")
        control(root, "release-request")
        control(root, "interrupt-request")
        page.get_by_role("button", name="Quit Sinter", exact=True).click()
        page.get_by_role("button", name="Request quit", exact=True).click()
        expect(
            page.get_by_text(
                "Quit requested. Check Sinter; inputs stay here.", exact=True
            ).first
        ).to_be_visible()
        old.require(
            "confirmed_ack" in proof,
            "Actual confirmed quit acknowledgement was omitted.",
        )
        # Stop browser polling only after its explicit final request and visible
        # acknowledgement, before the native owner drains that same listener.
        context.close()
        context = None
        control(root, "close-final")
        proof["quit_attempts"].append("confirmed-quit")
        proof["visible_checks"].append("confirmed-quit")
        cdp.send("Browser.close")
        chrome_process.wait(timeout=5)
        chrome.close()
        chrome = None
    except BaseException as error:
        primary = error
        proof.update(error_type=type(error).__name__, error=str(error)[:4096])
    finally:
        cleanup = Cleanup()
        clean = cleanup.call
        if context is not None:
            clean("context.close", context.close)
        if chrome is not None:
            clean("browser.close", chrome.close)
        if chrome_process is not None:
            clean(
                "chromium.stop",
                lambda: native.stop_process(chrome_process, proof["chromium_process"]),
            )
            for name, stream_file in chrome_streams.items():
                record = clean(
                    "chromium." + name, lambda f=stream_file: menu.stream_record(f)
                )
                if record is not None:
                    proof["chromium_process"][name] = record

                    def retain(f=stream_file, n=name):
                        f.seek(0)
                        (root / ("chromium." + n)).write_bytes(
                            f.read(32 * 1024 * 1024 + 1)
                        )

                    clean("retain-chromium." + name, retain)
            proof["chromium_process"]["streams_complete"] = (
                chrome_process.poll() is not None
                and proof["chromium_process"].get("owned_group_remaining") is False
            )
        for stream_file in chrome_streams.values():
            clean("stream.close", stream_file.close)
        if playwright is not None:
            clean("playwright.stop", playwright.stop)

        def await_resources():
            deadline = time.monotonic() + 3
            while (
                relay is not None
                and not relay.idle()
                or any(alive(pid) for pid in proof.get("browser_pids", []))
                or proof.get("driver_process")
                and alive(proof["driver_process"]["pid"])
            ) and time.monotonic() < deadline:
                time.sleep(0.03)

        clean("await-owned-resources", await_resources)
        idle = clean("observe-relay-idle", relay.idle) if relay is not None else False
        if relay is not None:
            clean("relay.shutdown", relay.shutdown)
            clean("relay.server_close", relay.server_close)
        if thread is not None:
            clean("relay.thread.join", lambda: thread.join(timeout=2))
        proof.update(
            model_requests=relay.model_requests if relay is not None else 0,
            relay_errors=relay.errors if relay is not None else 0,
            cleanup={
                "browser_closed": chrome_process is not None
                and chrome_process.poll() == 0,
                "owned_pids_gone": clean(
                    "observe-browser-pids",
                    lambda: all(
                        not alive(pid) for pid in proof.get("browser_pids", [])
                    ),
                ),
                "owned_driver_gone": bool(proof.get("driver_process"))
                and clean(
                    "observe-driver-pid",
                    lambda: not alive(proof["driver_process"]["pid"]),
                ),
                "relay_idle": idle,
                "relay_stopped": thread is not None and not thread.is_alive(),
                "relay_port_closed": clean(
                    "observe-relay-port", lambda: port_closed(proof["relay_port"])
                )
                if "relay_port" in proof
                else False,
                "debug_port_closed": clean(
                    "observe-debug-port", lambda: port_closed(proof["debug_port"])
                )
                if "debug_port" in proof
                else False,
            },
        )
        proof["chromium"]["sha256_after"] = clean(
            "observe-chromium-after", lambda: native.binary_digest(executable)
        )
        if "driver_process" in proof:
            proof["driver_process"]["sha256_after"] = clean(
                "observe-driver-after",
                lambda: native.binary_digest(Path(proof["driver_process"]["path"])),
            )
        if cleanup.errors:
            proof["cleanup_errors"] = cleanup.errors
        clean(
            "retain-browser-proof",
            lambda: write_json(root.parent.parent / "browser.json", proof),
        )
        if old_tmp is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = old_tmp
    if primary is not None:
        raise primary
    if cleanup.errors:
        cleanup.first_error.cleanup_errors = cleanup.errors
        raise cleanup.first_error
    return proof


def handoff_lifecycle(root, environment, pins, rows, client_rows, cleanup, executable):
    """Small custom dispatch; all raw V4 lifecycle semantics are reused."""
    identifier, exited, worker = None, False, None
    primary = None
    try:
        code, raw = owner.docker_row(
            "image",
            ["docker", "image", "inspect", owner.IMAGE_ID],
            root,
            environment,
            rows,
            client_rows,
        )
        old.require(code == 0, "Reviewed local image is absent; never pull.")
        old.validate_image(raw, pins)
        name = "sinter-native-entry-" + secrets.token_hex(6)
        code, raw = owner.docker_row(
            "create",
            contract.creation_argv(pins, name),
            root,
            environment,
            rows,
            client_rows,
        )
        old.require(code == 0, "Fresh handoff container creation failed.")
        candidate_id = raw.decode("ascii").strip()
        menu.exact_text(candidate_id, r"[0-9a-f]{64}", "owned handoff container")
        old.require(raw == (candidate_id + "\n").encode(), "Create ID grammar differs.")
        identifier = candidate_id
        code, raw = owner.docker_row(
            "created",
            ["docker", "inspect", identifier],
            root,
            environment,
            rows,
            client_rows,
        )
        old.require(code == 0, "Created handoff container observation failed.")
        observation = json.loads(raw, object_pairs_hook=old.unique)
        old.require(
            type(observation) is list and len(observation) == 1,
            "Require one created handoff container.",
        )
        old.validate_container_observation(
            observation[0], pins, contract.creation_argv, name, identifier, "created"
        )
        outcome = {}

        def start():
            try:
                outcome["result"] = owner.docker_row(
                    "start",
                    ["docker", "start", "-a", identifier],
                    root,
                    environment,
                    rows,
                    client_rows,
                    timeout=180,
                )
            except BaseException as error:
                outcome["error"] = error

        worker = threading.Thread(target=start, daemon=True)
        worker.start()
        browser(root / "out/handoff", executable)
        worker.join(timeout=30)
        old.require(
            not worker.is_alive()
            and "error" not in outcome
            and outcome["result"][0] == 0,
            "Owned handoff producer did not finish normally.",
        )
        code, raw = owner.docker_row(
            "exited",
            ["docker", "inspect", identifier],
            root,
            environment,
            rows,
            client_rows,
        )
        old.require(code == 0, "Exit observation failed.")
        state = json.loads(raw)[0]["State"]
        exited = state.get("Running") is False and state.get("Status") == "exited"
        old.require(exited, "Owned container remains running.")
    except BaseException as error:
        primary = error
    finally:
        if identifier is not None:
            if not exited:
                for role, argv in (
                    (
                        "cleanup-term",
                        ["docker", "kill", "--signal", "SIGTERM", identifier],
                    ),
                    ("cleanup-wait", ["docker", "wait", identifier]),
                ):
                    try:
                        owner.capture(role, argv, root, environment, cleanup, timeout=8)
                    except BaseException as error:
                        cleanup.append(
                            {
                                "role": role + "-error",
                                "error_type": type(error).__name__,
                                "error": str(error)[:4096],
                            }
                        )
                if worker:
                    try:
                        worker.join(timeout=10)
                        if worker.is_alive():
                            attached = [
                                row
                                for row in client_rows
                                if row.get("argv")
                                == ["docker", "start", "-a", identifier]
                            ]
                            old.require(
                                len(attached) == 1
                                and type(attached[0].get("pid")) is int
                                and attached[0]["pid"] > 0,
                                "Cannot signal an unobserved attached Docker client.",
                            )
                            pid = attached[0]["pid"]
                            diagnostic = {
                                "role": "cleanup-attached-client",
                                "pid": pid,
                                "argv": attached[0]["argv"],
                                "sigterm_sent": False,
                                "sigkill_sent": False,
                            }
                            cleanup.append(diagnostic)
                            if native.group_alive(pid):
                                os.killpg(pid, signal.SIGTERM)
                                diagnostic["sigterm_sent"] = True
                            worker.join(timeout=3)
                            if worker.is_alive() and native.group_alive(pid):
                                os.killpg(pid, signal.SIGKILL)
                                diagnostic["sigkill_sent"] = True
                            worker.join(timeout=3)
                            diagnostic.update(
                                worker_stopped=not worker.is_alive(),
                                owned_group_remaining=native.group_alive(pid),
                                streams_complete=attached[0].get("streams_complete")
                                is True,
                            )
                            old.require(
                                diagnostic["worker_stopped"]
                                and not diagnostic["owned_group_remaining"],
                                "Attached Docker client cleanup remains incomplete.",
                            )
                    except BaseException as error:
                        cleanup.append(
                            {
                                "role": "cleanup-attached-client-error",
                                "error_type": type(error).__name__,
                                "error": str(error)[:4096],
                            }
                        )
            for role, argv in (
                ("remove", ["docker", "rm", *([] if exited else ["-f"]), identifier]),
                ("removed", ["docker", "inspect", identifier]),
            ):
                try:
                    owner.docker_row(role, argv, root, environment, rows, client_rows)
                except BaseException as error:
                    cleanup.append(
                        {
                            "role": role,
                            "error_type": type(error).__name__,
                            "error": str(error)[:4096],
                        }
                    )
                    if primary is None:
                        primary = error
    if primary is not None:
        raise primary
    return old.validate_lifecycle(rows, pins, contract.creation_argv)["container_id"]


def observe_handoff_outer(
    root, environment, pins, commands, client_rows, cleanup, chromium, client, records
):
    """Retain actual Docker-after and all sidecars without masking the first error."""
    primary, identifier = None, None
    observations = Cleanup()
    try:
        identifier = handoff_lifecycle(
            root, environment, pins, commands, client_rows, cleanup, chromium
        )
    except BaseException as error:
        primary = error
    finally:
        client["sha256_after"] = observations.call(
            "observe-docker-after", lambda: native.binary_digest(Path(client["path"]))
        )
        observations.call(
            "retain-client-commands",
            lambda: write_json(root / "client-commands.json", client_rows),
        )
        outer = {
            "schema": "sinter-owned-native-handoff-container/v1",
            "commands": commands,
            "cleanup_commands": cleanup,
            "docker_client": client,
            "source_manifest": records,
            "source_manifest_sha256": observations.call(
                "observe-source-manifest", lambda: owner.records_hash(records)
            ),
            "tools": observations.call(
                "observe-reviewed-tools",
                lambda: {name: records[name] for name in contract.FILES},
            ),
        }
        if observations.errors:
            outer["observation_errors"] = observations.errors
        observations.call(
            "retain-handoff-outer", lambda: write_json(root / "outer.json", outer)
        )
    if primary is not None:
        primary.host_observation_errors = observations.errors
        raise primary
    if observations.first_error is not None:
        observations.first_error.host_observation_errors = observations.errors
        raise observations.first_error
    return identifier


def run(args):
    old.require(platform.system() == "Linux", "Only the Linux host route is supported.")
    old.require(not os.path.lexists(args.output), "Use a new private output root.")
    output = args.output.resolve()
    for path in (
        ROOT,
        args.repository.resolve(),
        args.installer.parent.resolve(),
        args.package_receipt.parent.resolve(),
    ):
        old.require(
            output != path
            and not output.is_relative_to(path)
            and not path.is_relative_to(output),
            "Owned output must be disjoint from every input before creating any files.",
        )
    old.require(
        args.chromium == contract.HOST_CHROMIUM
        and args.chromium.resolve(strict=True) == args.chromium
        and os.access(args.chromium, os.X_OK),
        "Use the fixed private host Chromium executable.",
    )
    menu.exact_text(args.chromium_sha256, r"[0-9a-f]{64}", "reviewed host Chromium")
    old.require(
        native.binary_digest(args.chromium) == args.chromium_sha256,
        "Host Chromium review pin differs.",
    )
    old.require(
        args.output.parent.stat().st_uid == os.geteuid()
        and not args.output.parent.stat().st_mode & 0o022,
        "Use an owned non-shared parent.",
    )
    for name, pin in (
        (contract.FILES[0], args.producer_sha256),
        (contract.FILES[1], args.contract_sha256),
    ):
        menu.exact_text(pin, r"[0-9a-f]{64}", "independently reviewed tool")
        old.require(
            old.sha(menu.regular_bytes(ROOT / name, 2 * 1024 * 1024)) == pin,
            "Tool review pin differs.",
        )
    args.output.mkdir(mode=0o700)
    context = {
        "schema": "sinter-native-handoff-owner-run/v1",
        "passed": False,
        "boundary": "Actual installed run only when all proofs admit; DEV is not a release.",
    }
    write_json(args.output / "owner-run.json", context)
    try:
        baseline_args = SimpleNamespace(
            **{**vars(args), "mode": "run-archive", "output": args.output / "baseline"}
        )
        baseline = owner.run(baseline_args)
        old.require(
            baseline.get("installed_admission") is not None
            and "error_type" not in baseline,
            "Unchanged baseline refused; do not launch the fifth owner.",
        )
        handoff_args = SimpleNamespace(
            **{
                **vars(args),
                "mode": "run-archive",
                "output": args.output / "handoff-container",
            }
        )
        root, environment, records = owner.prepare(handoff_args)
        for name in ("source", "repository", "candidate"):
            if name != "source":
                shutil.copytree(
                    args.output / "baseline" / name, root / name, dirs_exist_ok=True
                )
            for path in (root / name).rglob("*"):
                old.require(not path.is_symlink(), "Readonly inputs cannot redirect.")
                path.chmod(0o555 if path.is_dir() else 0o444)
            (root / name).chmod(0o555)
        old.exact(
            records,
            baseline["source_manifest"],
            "Both owners must execute identical full source.",
        )
        client_rows, commands, cleanup = [], [], []
        client = owner.client_identity(root, environment, client_rows)
        old.exact(
            client["sha256"],
            read_json(args.output / "baseline/image-proof/container-mechanics.json")[
                "docker_client"
            ]["sha256"],
            "Both owners must use the same observed Docker client.",
        )
        pins = owner.pins_for(
            root,
            args.owner_sha256,
            args.source_commit,
            args.installer.name,
            args.package_receipt.name,
        )
        pins["qualification"] = args.qualification
        identifier = observe_handoff_outer(
            root,
            environment,
            pins,
            commands,
            client_rows,
            cleanup,
            args.chromium,
            client,
            records,
        )
        admission = contract.verify(args)
        old.exact(
            admission["handoff_container_id"],
            identifier,
            "Verifier admitted another owner.",
        )
        context.update(passed=True, admission=admission)
    except BaseException as error:
        context.update(error_type=type(error).__name__, error=str(error)[:4096])
        if hasattr(error, "host_observation_errors"):
            context["host_observation_errors"] = error.host_observation_errors
    finally:
        write_json(args.output / "owner-run.json", context)
    return 0 if context["passed"] is True else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    external = sub.add_parser(
        "run", help="Explicitly install/run in disposable owned containers"
    )
    inner = sub.add_parser("_inside", help=argparse.SUPPRESS)
    for child in (external, inner):
        for name in ("repository", "installer", "package-receipt", "output"):
            child.add_argument("--" + name, type=Path, required=True)
        child.add_argument("--source-commit", required=True)
        child.add_argument(
            "--qualification", choices=("dev", "candidate"), required=True
        )
    for name in ("owner-sha256", "producer-sha256", "contract-sha256"):
        external.add_argument("--" + name, required=True)
    external.add_argument("--chromium", type=Path, required=True)
    external.add_argument("--chromium-sha256", required=True)
    action = sub.add_parser("_driver", help=argparse.SUPPRESS)
    action.add_argument("--request", type=Path, required=True)
    capture = sub.add_parser("_capture", help=argparse.SUPPRESS)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("url")
    args = parser.parse_args(argv)
    if args.mode == "_capture":
        capture_url(args.output, args.url)
        return 0
    if args.mode == "_driver":
        print(json.dumps(driver(args.request), ensure_ascii=True, allow_nan=False))
        return 0
    previous = signal.getsignal(signal.SIGTERM)

    def interrupted(*_):
        raise KeyboardInterrupt("Owned handoff interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        return inside(args) if args.mode == "_inside" else run(args)
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
