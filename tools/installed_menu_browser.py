"""Exercise the actual installed Linux menu command with fictional offline work.

The caller installs/removes its same-run .deb on a disposable CI host. This tool
never installs software, starts a source app, uses private state, or invokes a
provider. It proves the installed entry's command, not a physical menu click.
"""

from __future__ import annotations

import argparse
import ast
import base64
import configparser
import hashlib
import json
import platform
import re
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.native_window_smoke import (  # noqa: E402
    capture_stderr,
    clean_environment,
    group_alive,
    stop_process,
)

BINARY_COMMAND = "/opt/neuroforge/sinter/Sinter"
BINARY = Path(BINARY_COMMAND)
ENTRIES = Path("/usr/share/applications")
TITLE = "Fictional installed-menu first-run handover"
NOTE = "\n\nFictional reviewer note: approval remains unconfirmed."
BROWSER_NOTICE = (
    b"Press Ctrl+C to stop. Closing a browser tab alone does not quit Sinter.\n"
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def browser_notice(source):
    """Admit only the known browser notice declared by this candidate source."""
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as error:
        raise ValueError("The candidate browser notice source is malformed.") from error
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "serve_desktop"
    ]
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == BROWSER_NOTICE[:-1].decode("ascii")
        and len(node.keywords) == 1
        and node.keywords[0].arg == "file"
        and isinstance(node.keywords[0].value, ast.Attribute)
        and isinstance(node.keywords[0].value.value, ast.Name)
        and node.keywords[0].value.value.id == "sys"
        and node.keywords[0].value.attr == "stderr"
    ]
    if (
        len(functions) != 1
        or len(matches) != 1
        or matches[0] not in ast.walk(functions[0])
    ):
        raise ValueError("The candidate browser notice is missing or ambiguous.")
    return BROWSER_NOTICE


def source_browser_notice(source_commit):
    """Bind the notice to the exact build commit and unchanged checkout bytes."""
    if not isinstance(source_commit, str) or not re.fullmatch(
        r"[0-9a-f]{40}", source_commit
    ):
        raise ValueError("Use an exact browser notice source identity.")
    source = subprocess.run(
        ["git", "show", f"{source_commit}:src/sinter/desktop.py"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=10,
    ).stdout
    if source != (ROOT / "src/sinter/desktop.py").read_bytes():
        raise ValueError("The browser notice checkout differs from the build source.")
    return browser_notice(source), hashlib.sha256(source).hexdigest()


def menu_command(path, *, native=False):
    """Refuse surprising installed commands before creating any process."""
    parsed = configparser.ConfigParser(interpolation=None, strict=True)
    parsed.read_string(Path(path).read_text(encoding="utf-8"))
    row = parsed["Desktop Entry"]
    expected = [BINARY_COMMAND, "app", "--mode", "native" if native else "browser"]
    if (
        row.get("Type") != "Application"
        or row.get("Terminal") != "false"
        or row.get("Name") != ("Sinter native source workspace" if native else "Sinter")
        or shlex.split(row.get("Exec", "")) != expected
    ):
        raise ValueError("The installed menu command does not match its presentation.")
    return expected


def launch_environment(home, capture, script, provider):
    """Construct an allowlist; inherited account/provider credentials never enter."""
    env = clean_environment(home, "")
    env.update(
        SINTER_DATA_DIR=str(home / "workspace"),
        NEUROFORGE_BASE_URL=provider,
        BROWSER=shlex.join([sys.executable, str(script), str(capture), "%s"]),
    )
    return env


def launch_url(text):
    if not re.fullmatch(r"http://127\.0\.0\.1:[1-9][0-9]{0,4}", text):
        raise ValueError("The installed command did not open an exact loopback URL.")
    if not 0 < urlsplit(text).port < 65536:
        raise ValueError("The launch port is invalid.")
    return text


def wait_launch(process, capture):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The installed command stopped before browser launch.")
        if capture.exists():
            return launch_url(capture.read_text())
        time.sleep(0.05)
    raise RuntimeError("The installed command did not request a browser in time.")


def finish(process, origin, row, *, interrupt=False):
    if interrupt:
        stop_process(process, row)
    else:
        row["exit_code"] = process.wait(timeout=8)
        row["owned_group_remaining"] = group_alive(process.pid)
    with socket.socket() as probe:
        probe.settimeout(1)
        row["port_closed"] = probe.connect_ex(("127.0.0.1", urlsplit(origin).port)) != 0
    if (
        row["exit_code"] != 0
        or row["owned_group_remaining"]
        or not row["port_closed"]
        or row.get("forced_cleanup")
    ):
        raise RuntimeError("Installed command shutdown or cleanup failed.")


@contextmanager
def cancellation_cleanup():
    """Unwind owned child/browser cleanup when the CLI driver is cancelled."""

    def cancelled(*_):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, cancelled)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


@contextmanager
def installed_launch(command, home, script, provider, row, *, expected_notice=None):
    if expected_notice is None:
        expected_notice = browser_notice((ROOT / "src/sinter/desktop.py").read_bytes())
    if not isinstance(expected_notice, bytes) or expected_notice != BROWSER_NOTICE:
        raise ValueError("Use the exact candidate browser notice.")
    capture = home / f"launch-{row['launch']}.txt"
    start = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            command,
            env=launch_environment(home, capture, script, provider),
            cwd=home,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        row["pid"] = process.pid
        body_failed = False
        try:
            origin = wait_launch(process, capture)
            row["origin"] = origin
            yield process, origin
        except BaseException:
            body_failed = True
            row["passed"] = False
            raise
        finally:
            cleanup_failure = capture_failure = None
            try:
                if process.poll() is None or group_alive(process.pid):
                    stop_process(process, row)
            except BaseException as error:
                cleanup_failure = error
                row["cleanup_error"] = type(error).__name__
                row["passed"] = False
            try:
                capture_stderr(stderr, row)
            except BaseException as error:
                capture_failure = error
                row["stderr_capture_error"] = type(error).__name__
                row["passed"] = False
            finally:
                row["seconds"] = round(time.monotonic() - start, 3)
            expected = (
                capture_failure is None
                and row.get("stderr_bytes") == len(expected_notice)
                and row.get("stderr_sha256")
                == hashlib.sha256(expected_notice).hexdigest()
                and row.get("stderr_base64")
                == base64.b64encode(expected_notice).decode("ascii")
                and row.get("stderr_truncated") is False
            )
            row["stderr_expected_browser_notice"] = expected
            if not expected:
                row["passed"] = False
            if not body_failed:
                if cleanup_failure is not None:
                    raise cleanup_failure
                if capture_failure is not None:
                    raise capture_failure
                if not expected:
                    raise RuntimeError(
                        "Installed browser command emitted unexpected diagnostics; "
                        "see exact retained stderr evidence."
                    )


def saved_snapshots(read):
    """Retain the list's report identity separately from its exact saved body."""
    books, reports = (
        read("/api/casebooks")["casebooks"],
        read("/api/reports")["reports"],
    )
    assert len(books) == len(reports) == 1
    return {
        "project": read("/api/casebooks/" + books[0]["id"]),
        "report_id": reports[0]["id"],
        "report": read("/api/reports/" + reports[0]["id"]),
    }


def first_journey(page, process, read, expect, row):
    card = page.get_by_role("region", name="Fictional garden practice project")
    expect(card).to_contain_text("No account or internet needed")
    fixture = read("/api/practice/garden")["casebook"]
    card.get_by_role("button", name="Open garden handover", exact=True).click()
    title = page.get_by_label("Project name", exact=True)
    title.fill(TITLE)
    dialogs = []
    page.once("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    page.get_by_role("button", name="Quit Sinter", exact=True).click()
    assert len(dialogs) == 1 and "save" in dialogs[0].lower()
    assert process.poll() is None and title.input_value() == TITLE
    assert read("/api/casebooks")["casebooks"] == []
    row["dirty_quit_cancelled"] = True
    page.get_by_role("button", name="Prepare source-only report", exact=True).click()
    report = page.get_by_role("region", name="Your draft report")
    expect(report.get_by_role("tabpanel", name="Document", exact=True)).to_contain_text(
        "Source-only handover checklist"
    )
    report.get_by_text("More options", exact=True).click()
    report.get_by_role("button", name="Edit draft", exact=True).click()
    editor = report.get_by_label("Edit your draft", exact=True)
    editor.fill(editor.input_value() + NOTE)
    report.get_by_role("button", name="Apply edits", exact=True).click()
    report.get_by_role("button", name="Save to My workspace", exact=True).click()
    expect(
        report.get_by_text(
            "Saved in My workspace, including your edits and original evidence.",
            exact=True,
        )
    ).to_be_visible()
    page.get_by_role("button", name="Save project", exact=True).click()
    expect(page.get_by_text("Saved revision 2.", exact=False)).to_be_visible()
    before = saved_snapshots(read)
    assert before["project"]["document"]["documents"] == fixture["documents"]
    assert NOTE.strip() in before["report"]["document_edits"]["markdown"]
    row["source_documents_exact"] = True
    return before


def browser_cycle(browser, process, origin, row, before, output, version, observations):
    from playwright.sync_api import expect

    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        reduced_motion="reduce",
        service_workers="block",
    )
    try:

        def route(request):
            url = urlsplit(request.request.url)
            if url.netloc == urlsplit(origin).netloc and url.scheme == "http":
                request.continue_()
            else:
                observations["external"].append(True)
                request.abort()

        context.route("**/*", route)
        context.route_web_socket(
            "**/*", lambda route: (observations["external"].append(True), route.close())
        )
        page = context.new_page()
        page.set_default_timeout(10_000)
        page.on("pageerror", lambda e: observations["errors"].append(type(e).__name__))
        page.goto(origin)
        expect(
            page.get_by_role(
                "heading", name="Your next piece of work starts here.", exact=True
            )
        ).to_be_visible()
        expect(
            page.get_by_text(
                "Use Save project for inputs and Save to My workspace "
                "for edited reports.",
                exact=False,
            )
        ).to_be_visible()

        def read(path):
            return page.evaluate(
                "p => fetch(p).then(r => {if(!r.ok) throw Error('read'); "
                "return r.json()})",
                path,
            )

        session = read("/api/session")
        assert session["version"] == version and session["desktop"] is True
        if before is None:
            before = first_journey(page, process, read, expect, row)
        else:
            assert (
                read("/api/casebooks/" + before["project"]["id"]) == before["project"]
            )
            assert read("/api/reports/" + before["report_id"]) == before["report"]
            page.get_by_role("link", name="My workspace", exact=True).click()
            page.get_by_role("button", name="Open draft", exact=True).click()
            expect(
                page.get_by_role("region", name="Your draft report")
            ).to_contain_text(NOTE.strip())
            row["saved_project_report_exact"] = True
        page.screenshot(path=str(output / f"installed-menu-{row['launch']}.png"))
        if row["launch"] == 3:
            finish(process, origin, row, interrupt=True)
        else:
            unexpected = []
            page.on("dialog", lambda d: (unexpected.append(d.message), d.dismiss()))
            page.get_by_role("button", name="Quit Sinter", exact=True).click()
            assert not unexpected, "Saved work unexpectedly warned on Quit"
            expect(
                page.get_by_text(
                    "Sinter has stopped. You can close this window.", exact=True
                )
            ).to_be_visible()
            finish(process, origin, row)
        row["passed"] = True
        return before
    finally:
        context.close()


def run(args):
    from playwright.sync_api import sync_playwright

    from tools._support import launch_chromium

    receipt = {
        "schema": "sinter-installed-menu-first-run/v1",
        "passed": False,
        "source_commit": args.source_commit,
        "launches": [],
        "physical_os_menu_click": False,
        "fixtures_only": True,
        "private_workspace_used": False,
        "credentials_supplied": False,
    }
    start = time.monotonic()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    try:
        if platform.system() != "Linux" or not re.fullmatch(
            r"[0-9a-f]{40}", args.source_commit
        ):
            raise ValueError("Use an exact Linux build identity.")
        package = json.loads(args.package_receipt.read_bytes())
        if (
            package.get("passed") is not True
            or package.get("source_commit") != args.source_commit
            or package.get("installer_sha256") != digest(args.installer)
            or package.get("frozen_cli_test", {}).get("binary_sha256") != digest(BINARY)
        ):
            raise ValueError("Bind the same-run package receipt and installed bytes.")
        notice, source_sha256 = source_browser_notice(args.source_commit)
        receipt.update(
            browser_notice_source_sha256=source_sha256,
            expected_browser_notice_bytes=len(notice),
            expected_browser_notice_sha256=hashlib.sha256(notice).hexdigest(),
        )
        command = menu_command(ENTRIES / "sinter.desktop")
        native = menu_command(ENTRIES / "sinter-native.desktop", native=True)
        receipt.update(
            version=package["version"],
            installer_sha256=digest(args.installer),
            binary_sha256=digest(BINARY),
            command=command,
            native_command=native,
            menu_sha256=digest(ENTRIES / "sinter.desktop"),
            native_menu_sha256=digest(ENTRIES / "sinter-native.desktop"),
        )
        observations = {"errors": [], "external": [], "provider": []}

        class Trap(BaseHTTPRequestHandler):
            def do_GET(self):
                observations["provider"].append(self.command)
                self.send_error(503)

            do_POST = do_GET

            def log_message(self, *_):
                pass

        trap = HTTPServer(("127.0.0.1", 0), Trap)
        trap_thread = threading.Thread(target=trap.serve_forever, daemon=True)
        trap_thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix="sinter-installed-menu-") as temp:
                home = Path(temp)
                script = home / "capture.py"
                script.write_text(
                    "import sys\nfrom pathlib import Path\n"
                    "Path(sys.argv[1]).write_text(sys.argv[2])\n"
                )
                provider = f"http://127.0.0.1:{trap.server_port}/v1"
                before = None
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        for index in range(1, 5):
                            row = {
                                "launch": index,
                                "passed": False,
                                "forced_cleanup": False,
                            }
                            receipt["launches"].append(row)
                            with installed_launch(
                                command,
                                home,
                                script,
                                provider,
                                row,
                                expected_notice=notice,
                            ) as launch:
                                before = browser_cycle(
                                    browser,
                                    *launch,
                                    row,
                                    before,
                                    args.receipt.parent,
                                    package["version"],
                                    observations,
                                )
                    finally:
                        browser.close()
                        receipt["browser_closed"] = True
                receipt["saved_state_sha256"] = hashlib.sha256(
                    json.dumps(before, sort_keys=True).encode()
                ).hexdigest()
            receipt["temporary_workspace_removed"] = not home.exists()
        finally:
            trap.shutdown()
            trap.server_close()
            trap_thread.join(timeout=3)
            receipt.update(
                provider_requests=len(observations["provider"]),
                browser_external_requests=len(observations["external"]),
                page_errors=observations["errors"],
                provider_trap_stopped=not trap_thread.is_alive(),
            )
        if (
            any(observations.values())
            or not all(
                r["passed"] is True and r["stderr_expected_browser_notice"] is True
                for r in receipt["launches"]
            )
            or not receipt["provider_trap_stopped"]
        ):
            raise RuntimeError("Installed offline first-run or isolation failed.")
        assert digest(BINARY) == receipt["binary_sha256"]
        # The caller still owns package removal. Overall qualification stays
        # false until that cleanup is observed and recorded by the CI step.
        receipt["workflow_passed"] = True
    finally:
        receipt["seconds"] = round(time.monotonic() - start, 3)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        "PASS: installed menu command; offline example, separate Save, cancelled "
        "Quit, restart, interruption and owned cleanup; zero provider requests."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--package-receipt", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--chromium")
    args = parser.parse_args(argv)
    with cancellation_cleanup():
        run(args)


if __name__ == "__main__":
    main()
