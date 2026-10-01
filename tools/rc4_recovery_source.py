"""Rehearse fictional campaign recovery with real source stops and reopens.

This separate source-only route never installs a package or admits a release.
Historical RC3 recovery/defaults/receipts remain unchanged. See the new contract
and docs/RC4_LOCAL_RECOVERY.md for the bounded campaign subset and missing gates.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import installed_recovery_browser as legacy  # noqa: E402
from tools import installed_workflow_browser as transport  # noqa: E402
from tools.installed_menu_browser import browser_notice  # noqa: E402
from tools.rc4_recovery_contract import (  # noqa: E402
    LOCAL_NOTE,
    OTHER_NOTE,
    QUIT_NOTE,
    RECEIPT,
    SAVE_NOTE,
    SCHEMA,
    UNCERTAIN_TITLE,
)
from tools.rc4_recovery_worker import canonical, protected, snapshot  # noqa: E402


def write_json(path: Path, value: object) -> None:
    """Atomically retain literal owned proof as UTF-8 with stable LF newlines."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    temporary.replace(path)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(65536):
            result.update(chunk)
    return result.hexdigest()


def verify_source(args):
    """Admit a complete externally pinned frozen source; no candidate admission."""
    from tools.installed_workflow_qualification import json_object

    if (
        args.source_manifest.is_symlink()
        or not args.source_manifest.is_file()
        or args.source_manifest.stat().st_size > 1024 * 1024
        or not re.fullmatch(r"[0-9a-f]{64}", args.source_manifest_sha256)
        or digest(args.source_manifest) != args.source_manifest_sha256
    ):
        raise ValueError("Use the pinned source manifest.")
    manifest = json_object(args.source_manifest.read_bytes())
    if (
        type(args.source_commit) is not str
        or not re.fullmatch(r"[0-9a-f]{40}", args.source_commit)
        or manifest.get("base_commit") != args.source_commit
    ):
        raise ValueError("The source base commit differs from the pinned manifest.")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("The pinned source inventory is missing.")
    observed = {}
    for path in ROOT.rglob("*"):
        if path.is_symlink():
            raise ValueError("Use a frozen source without linked entries.")
        if path.is_file():
            name = path.relative_to(ROOT).as_posix()
            if name not in files or path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("The complete source inventory differs.")
            observed[name] = digest(path)
    if observed != files:
        raise ValueError("The complete source inventory differs.")
    if (
        args.output.exists()
        or args.output.is_symlink()
        or args.output.resolve().is_relative_to(ROOT)
    ):
        raise ValueError("Choose a fresh output outside the frozen source.")
    if ROOT.is_relative_to(args.output.resolve()):
        raise ValueError("The output must not contain the frozen source.")
    init = (ROOT / "src/sinter/__init__.py").read_text(encoding="utf-8")
    version = re.search(r'__version__\s*=\s*["\']([^"\']+)', init)
    if not version:
        raise ValueError("The source version is missing.")
    return {"files": observed, "version": version[1], "manifest": manifest}


def capture_stream(path):
    """Parent has exited; retain full stream hash/count and reversible prefix."""
    count = path.stat().st_size
    with path.open("rb") as stream:
        prefix = stream.read(65536)
    return {
        "bytes": count,
        "sha256": digest(path),
        "sample_base64": base64.b64encode(prefix).decode(),
        "sample_complete": count <= 65536,
    }


class SourceLifecycle:
    """Own only isolated source children; preserve diagnostics before observations."""

    def __init__(self, runtime, output, identity, baseline):
        self.runtime, self.output = runtime, output
        self.notice = identity["notice"]
        self.identity = {
            key: value for key, value in identity.items() if key != "notice"
        }
        self.baseline = baseline
        self.process = None
        self.rows = []
        self.failure = None
        self.closed = False

    def command(self, control, *extra):
        return [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(ROOT / "tools/rc4_recovery_worker.py"),
            "--source",
            str(ROOT),
            "--data",
            str(self.runtime / "data"),
            "--control",
            str(control),
            *extra,
        ]

    def environment(self):
        return {"PATH": os.defpath, "HOME": str(self.runtime / "home")}

    def run(self):
        inner = transport.InnerRelay(self.runtime)
        thread = threading.Thread(target=inner.serve_forever, daemon=True)
        thread.start()
        run, finished, stop_method = 0, False, "interface_quit"
        try:
            while True:
                if self.process is None:
                    if canonical(
                        protected(snapshot(self.runtime / "data"))
                    ) != canonical(self.baseline):
                        raise ValueError(
                            "Protected originals changed before source reopen."
                        )
                    run += 1
                    capture = self.runtime / "launch-url.txt"
                    capture.unlink(missing_ok=True)
                    stdout = self.output / f"process/run-{run}.stdout"
                    stderr = self.output / f"process/run-{run}.stderr"
                    control = self.output / f"process/run-{run}.json"
                    self.streams = [stdout.open("wb"), stderr.open("wb")]
                    self.process = subprocess.Popen(
                        self.command(control, "--launch-url", str(capture)),
                        env=self.environment(),
                        stdin=subprocess.DEVNULL,
                        stdout=self.streams[0],
                        stderr=self.streams[1],
                    )
                    deadline = time.monotonic() + 20
                    while not capture.exists() and time.monotonic() < deadline:
                        if self.process.poll() is not None:
                            raise ValueError(
                                "Source desktop stopped before captured launch."
                            )
                        time.sleep(0.02)
                    _, inner.port = transport.inner_address(
                        capture.read_text(encoding="utf-8")
                    )
                    finished, stop_method = False, "interface_quit"
                    write_json(
                        self.runtime / "state.json",
                        {
                            **self.identity,
                            "phase": "running",
                            "run": run,
                            "pid": self.process.pid,
                            "port": inner.port,
                        },
                    )
                if self.process.poll() is not None and not finished:
                    for stream in self.streams:
                        stream.close()
                    row = {
                        "run": run,
                        "pid": self.process.pid,
                        "returncode": self.process.returncode,
                        "stop_method": stop_method,
                        "stdout": capture_stream(stdout),
                        "stderr": capture_stream(stderr),
                    }
                    self.rows.append(
                        row
                    )  # Retain streams even if later cleanup reads fail.
                    with socket.socket() as probe:
                        probe.settimeout(1)
                        row["port_closed"] = (
                            probe.connect_ex(("127.0.0.1", inner.port)) != 0
                        )
                    row["persistent_snapshot"] = snapshot(self.runtime / "data")
                    row["control"] = json.loads(control.read_text(encoding="utf-8"))
                    if (
                        row["stderr"]["bytes"] != len(self.notice)
                        or stderr.read_bytes() != self.notice
                    ):
                        raise ValueError(
                            "Unexpected source diagnostic; raw streams retained."
                        )
                    if canonical(protected(row["persistent_snapshot"])) != canonical(
                        self.baseline
                    ):
                        raise ValueError(
                            "Source stop changed protected work or settings."
                        )
                    finished = True
                    write_json(
                        self.runtime / "state.json",
                        {
                            **self.identity,
                            "phase": "stopped",
                            "run": run,
                            "pid": self.process.pid,
                            "port": inner.port,
                            "exit_code": self.process.returncode,
                            "stop_method": stop_method,
                            "port_closed": row["port_closed"],
                        },
                    )
                path = self.runtime / "control.json"
                if path.exists():
                    action = json.loads(path.read_text(encoding="utf-8"))["action"]
                    path.unlink()
                    if action == "stop" and self.process.poll() is None:
                        stop_method = "terminate"
                        legacy.stop_owned(self.process)
                    elif (
                        action == "restart"
                        and self.process.poll() is not None
                        and finished
                    ):
                        self.process = None
                    elif action == "cleanup":
                        break
                    else:
                        raise ValueError("Invalid source lifecycle control.")
                time.sleep(0.02)
        except Exception as error:
            self.failure = type(error).__name__ + ": " + str(error)
            write_json(self.runtime / "state.json", {"phase": "failed"})
        finally:
            # Cleanup faults cannot suppress the original body failure or raw streams.
            cleanup_errors = []
            if self.process is not None:
                try:
                    legacy.stop_owned(self.process)
                except Exception as error:
                    cleanup_errors.append("process stop: " + str(error))
            for stream in getattr(self, "streams", []):
                try:
                    stream.close()
                except Exception as error:
                    cleanup_errors.append("stream close: " + str(error))
            if self.process is not None and not finished:
                row = next((r for r in self.rows if r["run"] == run), None)
                if row is None:
                    row = {
                        "run": run,
                        "pid": self.process.pid,
                        "returncode": self.process.returncode,
                        "stop_method": "cleanup",
                    }
                    self.rows.append(row)
                for name, path in (("stderr", stderr), ("stdout", stdout)):
                    try:
                        row[name] = capture_stream(path)
                    except Exception as error:
                        cleanup_errors.append(name + " capture: " + str(error))
            for name, action in (
                ("inner shutdown", inner.shutdown),
                ("inner close", inner.server_close),
            ):
                try:
                    action()
                except Exception as error:
                    cleanup_errors.append(name + ": " + str(error))
            thread.join(timeout=5)
            self.closed = not thread.is_alive() and (
                self.process is None or self.process.poll() is not None
            )
            if cleanup_errors:
                message = "; ".join(cleanup_errors)
                self.failure = (
                    self.failure + "; cleanup: " + message
                    if self.failure
                    else "cleanup: " + message
                )
            write_json(
                self.output / "processes.json",
                {"rows": self.rows, "failure": self.failure, "closed": self.closed},
            )


def advanced_workflow(args, runtime, relay, phases):
    """Actual conflicting writes and lost acknowledgements; never auto replay."""
    from playwright.sync_api import expect, sync_playwright

    from tools._support import launch_chromium

    origin = f"http://127.0.0.1:{relay.server_address[1]}"
    external, errors, chrome_dialogs, posts = [], [], [], []
    result = {}
    current_run = 5
    write_json(runtime / "control.json", {"action": "restart"})
    transport.wait_state(runtime, "running", current_run)
    with sync_playwright() as driver:
        browser = launch_chromium(driver, args.chromium)
        try:
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                reduced_motion="reduce",
                accept_downloads=True,
                service_workers="block",
            )
            context.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if route.request.url.startswith(origin + "/")
                    else (external.append(route.request.url), route.abort())
                ),
            )
            context.route_web_socket(
                "**/*", lambda route: (external.append("websocket"), route.close())
            )

            def page():
                p = context.new_page()
                p.set_default_timeout(10000)
                p.on("pageerror", lambda e: errors.append(str(e)))
                p.on(
                    "dialog",
                    lambda dialog: (
                        chrome_dialogs.append(dialog.type),
                        dialog.dismiss(),
                    ),
                )
                p.on(
                    "request",
                    lambda request: (
                        posts.append(urlsplit(request.url).path)
                        if request.method == "POST"
                        else None
                    ),
                )
                p.goto(origin + "/#campaigns")
                return p

            def transfers(p):
                details = (
                    p.locator("details")
                    .filter(
                        has=p.get_by_text("Import or back up a campaign", exact=True)
                    )
                    .last
                )
                if details.get_attribute("open") is None:
                    details.locator("summary").click()

            def objective(p, text):
                details = p.locator(".campaign-details")
                if details.get_attribute("open") is None:
                    details.locator("summary").click()
                p.get_by_label(
                    "What will this campaign make possible?", exact=True
                ).fill(text)

            def open_saved(p, title):
                selected = p.locator(".campaign-saved-item").filter(has_text=title)
                expect(selected).to_have_count(1)
                selected.get_by_role("button").click()

            def save(p):
                p.get_by_role("button", name="Save campaign", exact=True).click()
                expect(p.get_by_text(legacy.SAVED, exact=True)).to_be_visible()
                row = next(
                    r
                    for r in legacy.read_json(p, "/api/campaigns")["campaigns"]
                    if r["title"] == UNCERTAIN_TITLE
                )
                return legacy.read_json(p, "/api/campaigns/" + row["id"])

            def backup(p, name):
                transfers(p)
                with p.expect_download() as pending:
                    p.get_by_role(
                        "button", name="Export campaign backup", exact=True
                    ).click()
                path = args.output / ("advanced/" + name + ".json")
                pending.value.save_as(path)
                return json.loads(path.read_text(encoding="utf-8"))

            p = page()
            transfers(p)
            imported = copy.deepcopy(phases["resumed"]["document"])
            imported["title"] = UNCERTAIN_TITLE
            input_path = args.output / "advanced/control-import.json"
            write_json(input_path, imported)
            p.get_by_label("Import campaign backup", exact=True).set_input_files(
                input_path
            )
            expect(
                p.get_by_text(
                    "Campaign imported locally. Save campaign to keep this copy.",
                    exact=True,
                )
            ).to_be_visible()
            base = save(p)
            # Show the old human mark and the current source mismatch together.
            p.get_by_role("tab", name="Opportunities", exact=True).click()
            requirement = p.locator(".campaign-requirement").nth(1)
            if requirement.get_attribute("open") is None:
                requirement.locator("summary").first.click()
            check = requirement.locator(".campaign-proof-status")
            expect(check).to_be_visible()
            check.scroll_into_view_if_needed()
            expect(check).to_be_in_viewport()
            expect(check).to_contain_text(
                "re-read the exact wording and update the check date"
            )
            expect(p.locator(".campaign-check-state").nth(1)).to_contain_text(
                "User-marked met · unverified"
            )
            p.screenshot(path=str(args.output / "advanced/stale-source.png"))
            result["stale_source"] = {
                "stored_mark": imported["requirements"][1]["status"],
                "registered_date": imported["sources"][0]["checked_at"],
                "excerpt_checked_date": imported["requirements"][1]["checked_at"],
                "warning_visible": True,
                "stored_original_preserved": True,
            }
            local = copy.deepcopy(imported)
            local["objective"] += LOCAL_NOTE
            objective(p, local["objective"])
            second = page()
            open_saved(second, UNCERTAIN_TITLE)
            other = copy.deepcopy(imported)
            other["objective"] += OTHER_NOTE
            objective(second, other["objective"])
            other_saved = save(second)
            before = len(posts)
            p.get_by_role("button", name="Save campaign", exact=True).click()
            expect(p.get_by_role("alert")).to_contain_text("changed in another window")
            assert len(posts) == before + 1
            assert backup(p, "conflict-backup") == local
            assert (
                legacy.read_json(second, "/api/campaigns/" + base["id"]) == other_saved
            )
            result["conflict"] = {
                "base": base,
                "other_saved": other_saved,
                "local_document": local,
                "failed_save_posts": 1,
                "stored_original_preserved": True,
            }
            p.screenshot(path=str(args.output / "advanced/conflict.png"))
            p.close()
            second.close()
            p = page()
            open_saved(p, UNCERTAIN_TITLE)
            uncertain = copy.deepcopy(other_saved["document"])
            uncertain["objective"] += SAVE_NOTE
            objective(p, uncertain["objective"])
            acknowledgements = []

            def lose_save(route):
                response = route.fetch()
                body = response.body()
                assert response.status == 200
                acknowledgements.append(json.loads(body))
                (args.output / "advanced/actual-save-response.json").write_bytes(body)
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"error":"Fictional save acknowledgement lost."}',
                )

            p.route("**/api/campaigns/save", lose_save)
            before = len(posts)
            p.get_by_role("button", name="Save campaign", exact=True).click()
            expect(p.get_by_role("alert")).to_contain_text("acknowledgement lost")
            p.wait_for_timeout(250)
            assert len(posts) == before + 1 and len(acknowledgements) == 1
            actual = legacy.read_json(p, "/api/campaigns/" + base["id"])
            assert actual == acknowledgements[0] and actual["document"] == uncertain
            assert backup(p, "uncertain-save-backup") == uncertain
            p.unroute("**/api/campaigns/save", lose_save)
            result["uncertain_save"] = {
                "before": other_saved,
                "actual_saved": actual,
                "working_document": uncertain,
                "actual_status": 200,
                "reported_status": 503,
                "save_posts": 1,
                "automatic_replays": 0,
            }
            dirty = copy.deepcopy(uncertain)
            dirty["objective"] += QUIT_NOTE
            objective(p, dirty["objective"])
            quit_button = p.get_by_role("button", name="Quit Sinter", exact=True)
            before = len(posts)
            quit_button.click()
            decision = p.get_by_role("dialog", name="Quit Sinter?", exact=True)
            expect(decision).to_be_visible()
            decision.get_by_role("button", name="Keep working", exact=True).click()
            assert (
                len(posts) == before
                and json.loads((runtime / "state.json").read_text(encoding="utf-8"))[
                    "phase"
                ]
                == "running"
            )
            expect(
                p.get_by_label("What will this campaign make possible?", exact=True)
            ).to_have_value(dirty["objective"])
            quit_responses = []

            def lose_quit(route):
                response = route.fetch()
                body = response.body()
                assert response.status == 200
                quit_responses.append(json.loads(body))
                (args.output / "advanced/actual-quit-response.json").write_bytes(body)
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"error":"Fictional quit acknowledgement lost."}',
                )

            p.route("**/api/desktop/quit", lose_quit)
            quit_button.click()
            expect(decision).to_be_visible()
            decision.get_by_role("button", name="Quit Sinter", exact=True).click()
            expect(p.get_by_role("alert").first).to_contain_text(
                "Quit was not confirmed"
            )
            stopped = transport.wait_state(runtime, "stopped", current_run)
            assert stopped["exit_code"] == 0 and stopped["port_closed"] is True
            p.wait_for_timeout(250)
            assert posts[before:] == ["/api/desktop/quit"] and quit_responses == [
                {"ok": True}
            ]
            assert backup(p, "uncertain-quit-backup") == dirty
            expect(
                p.get_by_label("What will this campaign make possible?", exact=True)
            ).to_have_value(dirty["objective"])
            p.screenshot(path=str(args.output / "advanced/uncertain-quit.png"))
            result["uncertain_quit"] = {
                "working_document": dirty,
                "keep_working_posts": 0,
                "keep_working_retained_input": True,
                "actual_status": 200,
                "reported_status": 503,
                "quit_posts": 1,
                "automatic_replays": 0,
                "input_retained_after_stop": True,
            }
            context.close()
            write_json(runtime / "control.json", {"action": "restart"})
            transport.wait_state(runtime, "running", 6)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                reduced_motion="reduce",
                service_workers="block",
            )
            context.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if route.request.url.startswith(origin + "/")
                    else (external.append(route.request.url), route.abort())
                ),
            )
            context.route_web_socket(
                "**/*", lambda route: (external.append("websocket"), route.close())
            )
            p = page()
            assert legacy.read_json(p, "/api/campaigns/" + base["id"]) == actual
            assert (
                legacy.read_json(p, "/api/campaigns/" + phases["resumed"]["id"])
                == phases["resumed"]
            )
            result["reopened_uncertain_save"] = actual
            p.get_by_role("button", name="Quit Sinter", exact=True).click()
            expect(
                p.get_by_text(
                    "Sinter has stopped. You can close this window.", exact=True
                )
            ).to_be_visible()
            stopped = transport.wait_state(runtime, "stopped", 6)
            assert stopped["exit_code"] == 0 and stopped["port_closed"] is True
            context.close()
        finally:
            browser.close()
    assert not external and not errors and not chrome_dialogs
    result.update({"external_requests": 0, "page_errors": 0, "browser_dialogs": 0})
    write_json(args.output / "advanced/observations.json", result)
    return result


def rehearse(args, pinned):
    from playwright.sync_api import sync_playwright  # noqa: F401

    from tools.rc4_recovery_contract import validate_rehearsal

    args.output.mkdir(mode=0o700)
    for name in ("installed-recovery", "advanced", "process"):
        (args.output / name).mkdir()
    receipt = {
        "schema": SCHEMA,
        "execution": "source",
        "profile": "rc4-local-campaign-recovery",
        "source_base_commit": args.source_commit,
        "observed_version": pinned["version"],
        "source_manifest_sha256": args.source_manifest_sha256,
        "source_files_sha256": pinned["files"],
        "candidate_admitted": False,
        "installed_tested": False,
        "release_qualified": False,
        "source_rehearsal_passed": False,
        "resources": {},
        "failure": None,
        "artifacts": {},
    }
    relay = relay_thread = controller = lifecycle = None
    temporary = tempfile.TemporaryDirectory(prefix="srr-")
    try:
        runtime = Path(temporary.name)
        (runtime / "home").mkdir(mode=0o700)
        command = [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(ROOT / "tools/rc4_recovery_worker.py"),
            "--source",
            str(ROOT),
            "--data",
            str(runtime / "data"),
            "--control",
            str(args.output / "seed-control.json"),
            "--seed-only",
        ]
        seeded = subprocess.run(
            command,
            env={"PATH": os.defpath, "HOME": str(runtime / "home")},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
        (args.output / "seed.stdout").write_bytes(seeded.stdout)
        (args.output / "seed.stderr").write_bytes(seeded.stderr)
        if seeded.returncode != 0 or seeded.stderr:
            raise ValueError("Source seed failed; retained diagnostics are not a pass.")
        seed = json.loads(
            (args.output / "seed-control.json").read_text(encoding="utf-8")
        )
        baseline = protected(seed["seed"]["snapshot"])
        source = {
            n: p.read_bytes()
            for n, p in (
                (p.relative_to(ROOT).as_posix(), p)
                for p in (ROOT / "src/sinter/web").iterdir()
            )
            if p.is_file()
        }
        notice = browser_notice((ROOT / "src/sinter/desktop.py").read_bytes())
        identity = {
            "version": pinned["version"],
            "binary_sha256": digest(Path(sys.executable)),
            "web": {n: hashlib.sha256(data).hexdigest() for n, data in source.items()},
        }
        lifecycle = SourceLifecycle(
            runtime, args.output, {**identity, "notice": notice}, baseline
        )
        # State JSON excludes bytes; the controller owns the capture expectation.
        controller = threading.Thread(target=lifecycle.run, daemon=True)
        controller.start()
        transport.wait_state(runtime, "running", 1)
        relay = transport.Relay(runtime)
        relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
        relay_thread.start()
        legacy_args = argparse.Namespace(
            output=args.output,
            source_fixture=True,
            version=pinned["version"],
            chromium=args.chromium,
        )
        base_results = legacy.browser_workflow(legacy_args, runtime, relay, source)
        write_json(args.output / "base-observations.json", base_results)
        phases = json.loads(
            (args.output / "installed-recovery/campaign-phases.json").read_text(
                encoding="utf-8"
            )
        )
        advanced_workflow(args, runtime, relay, phases)
        if relay.model_requests or relay.errors:
            raise ValueError(
                "The source relay observed a provider request or transport error."
            )
        receipt["resources"]["browser_closed"] = True
        write_json(runtime / "control.json", {"action": "cleanup"})
        controller.join(timeout=15)
        if controller.is_alive() or lifecycle.failure or not lifecycle.closed:
            raise ValueError("Source lifecycle did not complete owned cleanup.")
        receipt["resources"]["source_processes_stopped"] = True
    except Exception as error:
        receipt["failure"] = type(error).__name__ + ": " + str(error)
        (args.output / "failure.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
    finally:
        cleanup_errors = []
        if relay is not None:
            for name, action in (
                ("outer shutdown", relay.shutdown),
                ("outer close", relay.server_close),
            ):
                try:
                    action()
                except Exception as error:
                    cleanup_errors.append(name + ": " + str(error))
            relay_thread.join(timeout=5)
            receipt["resources"]["outer_relay_closed"] = (
                not relay_thread.is_alive() and relay.idle()
            )
        if controller is not None and controller.is_alive():
            try:
                write_json(runtime / "control.json", {"action": "cleanup"})
                controller.join(timeout=15)
            except Exception as error:
                cleanup_errors.append("controller cleanup: " + str(error))
            receipt["resources"]["source_processes_stopped"] = (
                not controller.is_alive() and lifecycle.closed
            )
        receipt["resources"]["inner_relay_closed"] = (
            lifecycle.closed if lifecycle else False
        )
        if cleanup_errors:
            message = "; ".join(cleanup_errors)
            receipt["failure"] = (
                receipt["failure"] + "; cleanup: " + message
                if receipt["failure"]
                else "cleanup: " + message
            )
        receipt["source_files_conserved"] = False
        try:
            receipt["source_files_conserved"] = (
                verify_source(
                    argparse.Namespace(
                        **{**vars(args), "output": args.output / "unused-proof"}
                    )
                )["files"]
                == pinned["files"]
            )
        except Exception:
            pass
        receipt["artifacts"] = {
            p.relative_to(args.output).as_posix(): {
                "sha256": digest(p),
                "bytes": p.stat().st_size,
            }
            for p in sorted(args.output.rglob("*"))
            if p.is_file() and p.name != RECEIPT
        }
        write_json(args.output / RECEIPT, receipt)
        temporary.cleanup()
    if receipt["failure"] or not receipt["source_files_conserved"]:
        raise ValueError("Source recovery failed; retained receipt is not a pass.")
    try:
        validate_rehearsal(
            args.output,
            pinned["files"],
            args.source_commit,
            args.source_manifest_sha256,
            _pending=True,
        )
    except Exception as error:
        receipt["failure"] = type(error).__name__ + ": " + str(error)
        (args.output / "validation-failure.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
        write_json(args.output / RECEIPT, receipt)
        raise ValueError(
            "Source evidence validation failed; receipt is not a pass."
        ) from error
    receipt["source_rehearsal_passed"] = True
    write_json(args.output / RECEIPT, receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument(
        "--source-commit",
        required=True,
        help="Exact base commit of the pinned private composition.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chromium", default=os.environ.get("SINTER_CHROMIUM"))
    args = parser.parse_args(argv)
    if sys.flags.optimize:
        parser.exit(1, "Run the source rehearsal without Python optimisation.\n")
    if sys.platform != "linux":
        parser.exit(1, "This source recovery rehearsal supports Linux only.\n")
    try:
        pinned = verify_source(args)
        from tools._support import require_module

        require_module(
            parser,
            "playwright.sync_api",
            "Playwright",
            "python -m pip install '.[browser]'",
        )
        rehearse(args, pinned)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Source recovery rehearsal refused: {error}\n")
    print("Source recovery rehearsal completed; no installed or release qualification.")


if __name__ == "__main__":
    main()
