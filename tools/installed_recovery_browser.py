"""Prove fictional campaign recovery using an actual desktop process and UI.

Installed qualification requires a pinned .deb/source ZIP/native receipt and an
existing offline Ubuntu qualification image. --source-fixture exercises the real
source desktop separately; it cannot produce an installed-release qualification.
No image pulls, product responses, model calls or private workspaces are used.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import traceback
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
INTERNAL = sys.argv[1:] == ["--container"]
if INTERNAL:
    import workflow_runtime as transport
else:
    sys.path.insert(0, str(ROOT))
    from tools import installed_workflow_browser as transport

BINARY = Path("/opt/neuroforge/sinter/Sinter")
SAVED = transport.SAVED_CAMPAIGN


def workspace_hashes(root: Path) -> dict[str, str]:
    """Bind saved bytes, excluding the private transport and process state."""
    return {
        path.relative_to(root).as_posix(): transport.digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def stop_owned(process: subprocess.Popen) -> None:
    """Stop only the process launched by this producer, with a bounded wait."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def lifecycle(root: Path, executable: list[str], identity: dict) -> None:
    """Observe actual exits and cold restarts without retaining launch tokens."""
    relay = transport.InnerRelay(root)
    relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
    relay_thread.start()
    (root / "home").mkdir(mode=0o700, exist_ok=True)
    process = None
    run = 0
    try:
        while True:
            if process is None:
                run += 1
                capture = root / "launch-url.txt"
                capture.unlink(missing_ok=True)
                capture_script = root / "capture.py"
                capture_script.write_text(
                    "import sys\nfrom pathlib import Path\n"
                    f"Path({str(capture)!r}).write_text(sys.argv[1])\n"
                )
                env = {
                    "PATH": "/usr/bin:/bin",
                    "HOME": str(root / "home"),
                    "SINTER_DATA_DIR": str(root / "data"),
                    "BROWSER": f"{sys.executable} {capture_script} %s",
                }
                if not INTERNAL:
                    env["PYTHONPATH"] = str(ROOT / "src")
                process = subprocess.Popen(
                    executable,
                    **(transport.qualification_application_user(root) if INTERNAL else {}),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                deadline = time.monotonic() + 25
                while not capture.exists() and time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise ValueError("The owned desktop stopped before launch.")
                    time.sleep(0.05)
                _, relay.port = transport.inner_address(capture.read_text())
                stop_method = "interface_quit"
                transport.write_json(
                    root / "state.json",
                    {
                        **identity,
                        "phase": "running",
                        "run": run,
                        "pid": process.pid,
                        "port": relay.port,
                    },
                )
            if process.poll() is not None:
                with socket.socket() as probe:
                    closed = probe.connect_ex(("127.0.0.1", relay.port)) != 0
                transport.write_json(
                    root / "state.json",
                    {
                        **identity,
                        "phase": "stopped",
                        "run": run,
                        "pid": process.pid,
                        "port": relay.port,
                        "exit_code": process.returncode,
                        "stop_method": stop_method,
                        "port_closed": closed,
                    },
                )
            control = root / "control.json"
            if control.exists():
                action = json.loads(control.read_text())["action"]
                control.unlink()
                if action == "stop" and process.poll() is None:
                    stop_method = "terminate"
                    stop_owned(process)
                elif action == "restart" and process.poll() is not None:
                    process = None
                elif action == "cleanup":
                    break
                else:
                    raise ValueError("Invalid owned-process lifecycle command.")
            time.sleep(0.05)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        transport.write_json(root / "state.json", {"phase": "failed"})
        raise
    finally:
        if process is not None:
            stop_owned(process)
        relay.shutdown()
        relay.server_close()
        relay_thread.join(timeout=5)
        transport.write_json(
            root / "lifecycle-closed.json",
            {
                "process_stopped": True,
                "inner_relay_closed": not relay_thread.is_alive(),
            },
        )


def container_main() -> None:
    """Install and remove the real package only in a disposable offline image."""
    if getattr(os, "geteuid", lambda: -1)() != 0 or not Path("/.dockerenv").is_file():
        raise ValueError("Internal mode requires a disposable root Docker container.")
    root = Path("/proof")
    (root / "data").mkdir(mode=0o700, exist_ok=True)
    installed = False
    try:
        if (
            subprocess.run(
                ["dpkg-query", "-W", "sinter"], capture_output=True, check=False
            ).returncode
            == 0
        ):
            raise ValueError("Qualification needs a fresh package installation.")
        package = transport.command("dpkg-deb", "-f", "/candidate.deb", "Package")
        if package != "sinter":
            raise ValueError("The input is not a Sinter installer.")
        transport.command("dpkg", "-i", "/candidate.deb", timeout=60)
        installed = True
        release = dict(
            line.split("=", 1)
            for line in Path("/etc/os-release").read_text().splitlines()
            if "=" in line
        )
        web = BINARY.parent / "_internal/sinter/web"
        transport.command(
            str(BINARY), "--self-test", str(root / "native.json"), timeout=60
        )
        identity = {
            "package": package,
            "package_version": transport.command(
                "dpkg-query", "-W", "-f=${Version}", "sinter"
            ),
            "architecture": transport.command(
                "dpkg-deb", "-f", "/candidate.deb", "Architecture"
            ),
            "version": transport.command(str(BINARY), "--version"),
            "binary_sha256": transport.digest(BINARY),
            "web": {
                "src/sinter/web/" + path.name: transport.digest(path)
                for path in sorted(web.iterdir())
                if path.is_file()
            },
            "frozen_test": json.loads((root / "native.json").read_text()),
            "os_release": {
                key: release[key].strip('"') for key in ("ID", "VERSION_ID")
            },
            "libc": list(platform.libc_ver()),
            "machine": os.uname().machine,
            "pointer_bits": struct.calcsize("P") * 8,
        }
        lifecycle(
            root,
            transport.browser_launch_command([str(BINARY)], identity["version"]),
            identity,
        )
    finally:
        removed = False
        if installed:
            transport.command("dpkg", "-r", "sinter", timeout=60)
            removed = not BINARY.exists()
        transport.write_json(root / "removed.json", {"package_removed": removed})
        uid = int(os.environ["SINTER_TEST_UID"])
        gid = int(os.environ["SINTER_TEST_GID"])
        for directory, directories, files in os.walk(root):
            for name in directories + files:
                os.chown(Path(directory) / name, uid, gid)


def read_json(page, path: str) -> dict:
    """Read actual local product output without returning session credentials."""
    return page.evaluate(
        "path => fetch(path).then(r => {if (!r.ok) throw Error('Local read failed');"
        "return r.json();})",
        path,
    )


def action_card(page, index: int):
    """Address canonical source indices even when visible actions are sorted."""
    card = page.locator(f'.campaign-action[data-action-index="{index}"]')
    if card.locator("details").get_attribute("open") is None:
        card.locator("summary").click()
    return card


def browser_workflow(args, runtime: Path, relay, source: dict[str, bytes]) -> dict:
    """Operate real garden controls, actual downloads and two offline restores."""
    from playwright.sync_api import expect, sync_playwright

    from tools._support import launch_chromium
    from tools.installed_recovery_contract import (
        ARTIFACT_PATHS,
        CONTROL_ACTION,
        COPY_NOTICE,
        HELD_ACTION_INDEX,
        MANUAL_NOTICE,
        OFFLINE_NOTE,
        PHASES,
        RESTORED_CLIPBOARD_TITLE,
        RESTORED_MANUAL_TITLE,
        _calendar,
        _csv,
        fictional_states,
    )

    states = fictional_states(source)
    phases, processes, offline = {}, [], {}
    origin = f"http://127.0.0.1:{relay.server_address[1]}"
    requests, errors, external, refusals = [], [], [], []
    stopped_save = False
    run = 1

    def path(role):
        return args.output / ARTIFACT_PATHS[role]

    def record_process(state):
        assert state["port_closed"] is True
        assert state["stop_method"] in {"interface_quit", "terminate"}
        assert (
            state["exit_code"] == 0
            if state["stop_method"] == "interface_quit"
            else state["exit_code"] in (0, -15)
        )
        processes.append(
            {
                "run": state["run"],
                "pid": state["pid"],
                "executable": str(BINARY)
                if not args.source_fixture
                else sys.executable,
                "binary_sha256": state["binary_sha256"],
                "stop_method": state["stop_method"],
                "returncode": state["exit_code"],
            }
        )

    with sync_playwright() as driver:
        browser = launch_chromium(driver, args.chromium)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                accept_downloads=True,
                reduced_motion="reduce",
                service_workers="block",
                permissions=["clipboard-read", "clipboard-write"],
            )

            def guard(route):
                parsed = urlsplit(route.request.url)
                if parsed.scheme != "http" or parsed.netloc != urlsplit(origin).netloc:
                    external.append(True)
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", guard)
            context.route_web_socket(
                "**/*", lambda route: (external.append(True), route.close())
            )

            def new_page():
                result = context.new_page()
                result.set_default_timeout(12_000)
                result.on(
                    "pageerror", lambda error: errors.append(type(error).__name__)
                )
                result.on("dialog", lambda dialog: dialog.accept())
                result.on(
                    "request",
                    lambda request: requests.append(urlsplit(request.url).path),
                )

                def failed(request):
                    if (
                        stopped_save
                        and urlsplit(request.url).path == "/api/campaigns/save"
                    ):
                        refusals.append(request.failure)

                result.on("requestfailed", failed)
                return result

            page = new_page()

            def screenshot(role):
                page.screenshot(path=str(path(role)), animations="disabled")

            def save(phase):
                page.get_by_role("button", name="Save campaign", exact=True).click()
                expect(page.get_by_text(SAVED, exact=True)).to_be_visible()
                campaigns = read_json(page, "/api/campaigns")["campaigns"]
                row = next(
                    row for row in campaigns if row["title"] == states[phase]["title"]
                )
                snapshot = read_json(page, "/api/campaigns/" + row["id"])
                assert snapshot["document"] == states[phase]
                phases[phase] = snapshot
                return snapshot

            def select_actions():
                page.get_by_role("tab", name="Next actions", exact=True).click()

            def route_status(value):
                page.get_by_role("tab", name="Opportunities", exact=True).click()
                details = page.locator(".campaign-opportunity-editor")
                if details.get_attribute("open") is None:
                    details.locator("summary").click()
                page.get_by_label("Opportunity status", exact=True).select_option(value)

            def transfers():
                details = (
                    page.locator("details")
                    .filter(
                        has=page.get_by_text("Import or back up a campaign", exact=True)
                    )
                    .last
                )
                if details.get_attribute("open") is None:
                    details.locator("summary").click()

            def download(role, label):
                with page.expect_download() as pending:
                    page.get_by_role("button", name=label, exact=True).click()
                pending.value.save_as(path(role))
                return path(role).read_bytes()

            def calendar(role, phase):
                _calendar(download(role, "Download action dates"), states[phase])

            def stop(method):
                if method == "interface_quit":
                    page.get_by_role("button", name="Quit Sinter", exact=True).click()
                else:
                    transport.write_json(runtime / "control.json", {"action": "stop"})
                state = transport.wait_state(runtime, "stopped", run)
                record_process(state)

            def restart():
                nonlocal run, page
                transport.write_json(runtime / "control.json", {"action": "restart"})
                run += 1
                state = transport.wait_state(runtime, "running", run)
                assert state["version"] == args.version
                page.close()
                context.clear_cookies()
                page = new_page()
                page.goto(origin + "/#campaigns")

            page.goto(origin + "/#home")
            identity = read_json(page, "/api/session")
            assert identity["version"] == args.version and identity["desktop"] is True
            page.get_by_role(
                "region", name="Fictional garden practice project"
            ).get_by_role("button", name="Open garden campaign", exact=True).click()
            select_actions()
            page.get_by_role("button", name="Add next action", exact=True).click()
            control = action_card(page, 4)
            control.get_by_label("Next action", exact=True).fill(CONTROL_ACTION["task"])
            control.get_by_label("Programme or scope", exact=True).select_option("")
            control = action_card(page, 4)
            control.get_by_label("Owner name or role", exact=True).fill(
                CONTROL_ACTION["owner"]
            )
            control.get_by_label("Owner type", exact=True).select_option("unknown")
            control.get_by_label("Proposed target date", exact=True).fill(
                CONTROL_ACTION["due"]
            )
            save("initial")
            action_card(page, HELD_ACTION_INDEX).get_by_label(
                "Action status", exact=True
            ).select_option("held")
            save("held")
            held_card = action_card(page, HELD_ACTION_INDEX)
            expect(held_card).to_contain_text("On hold · not completed")
            expect(held_card).to_contain_text("kept for reference")
            screenshot("held_screen")
            stop("interface_quit")
            restart()
            select_actions()
            held_card = action_card(page, HELD_ACTION_INDEX)
            expect(held_card.get_by_label("Action status", exact=True)).to_have_value(
                "held"
            )
            snapshot = read_json(page, "/api/campaigns/" + phases["held"]["id"])
            assert snapshot == phases["held"]
            phases["reopened_held"] = snapshot
            screenshot("reopened_screen")
            _csv(download("held_csv", "Download actions CSV"), states["held"])
            calendar("held_calendar", "held")

            route_status("closed")
            save("held_closed")
            select_actions()
            action_card(page, HELD_ACTION_INDEX).get_by_label(
                "Action status", exact=True
            ).select_option("open")
            save("resumed_closed")
            expect(action_card(page, HELD_ACTION_INDEX)).to_contain_text(
                "Hold reason: route recorded as closed."
            )
            calendar("resumed_closed_calendar", "resumed_closed")
            route_status("clarification")
            save("resumed")
            select_actions()
            calendar("resumed_calendar", "resumed")
            original_wrapper = phases["resumed"]

            for branch, mode, title in (
                ("clipboard", "written", RESTORED_CLIPBOARD_TITLE),
                ("manual", "denied", RESTORED_MANUAL_TITLE),
            ):
                # Reopen the original before the second branch, retaining copies.
                if branch == "manual":
                    page.goto(origin + "/#campaigns")
                    selected = page.locator(".campaign-saved-item").filter(
                        has_text=states["resumed"]["title"]
                    )
                    assert selected.count() == 1
                    selected.get_by_role("button").click()
                    assert (
                        read_json(page, "/api/campaigns/" + original_wrapper["id"])
                        == original_wrapper
                    )
                details = page.locator(".campaign-details")
                if details.get_attribute("open") is None:
                    details.locator("summary").click()
                page.get_by_label(
                    "What will this campaign make possible?", exact=True
                ).fill(states["resumed"]["objective"] + OFFLINE_NOTE)
                transfers()
                reference = download(branch + "_reference", "Export campaign backup")
                assert json.loads(reference) == states["working"]
                before = workspace_hashes(runtime / "data")
                page.evaluate(
                    """mode => {
                  const original = navigator.clipboard.writeText
                    .bind(navigator.clipboard);
                  window.recoveryClipboard = {attempts:0,successes:0};
                  Object.defineProperty(navigator.clipboard,'writeText',{
                    value:async text=>{
                    window.recoveryClipboard.attempts++;
                    if(mode==='denied') throw new DOMException(
                      'Fictional denial','NotAllowedError');
                    await original(text); window.recoveryClipboard.successes++;
                  }});
                }""",
                    mode,
                )
                stop("terminate")
                stopped_save = True
                count_refusals = len(refusals)
                page.get_by_role("button", name="Save campaign", exact=True).click()
                expect(page.get_by_role("alert")).to_contain_text(
                    "Cannot reach the local Sinter app"
                )
                assert len(refusals) == count_refusals + 1
                stopped_save = False
                assert workspace_hashes(runtime / "data") == before
                count_requests = len(requests)
                backup = page.get_by_role(
                    "region", name="Copy campaign backup", exact=True
                )
                backup.get_by_role(
                    "button", name="Copy backup text", exact=True
                ).click()
                text = backup.get_by_label("Campaign backup text", exact=True)
                notice = COPY_NOTICE if branch == "clipboard" else MANUAL_NOTICE
                expect(backup).to_contain_text(notice)
                assert text.input_value().encode() == reference
                if branch == "clipboard":
                    assert (
                        page.evaluate("navigator.clipboard.readText()")
                        == text.input_value()
                    )
                backup.get_by_role(
                    "button", name="Select backup text", exact=True
                ).click()
                selection = text.evaluate(
                    "element => [element.selectionStart,element.selectionEnd]"
                )
                assert selection == [
                    0,
                    len(reference.decode().encode("utf-16-le")) // 2,
                ]
                assert len(requests) == count_requests
                assert workspace_hashes(runtime / "data") == before
                path(branch + "_text").write_bytes(text.input_value().encode())
                screenshot(branch + "_screen")
                clipboard = page.evaluate("window.recoveryClipboard")
                offline[branch] = {
                    "mode": mode,
                    "save_connection_refusals": 1,
                    "backup_network_requests": len(requests) - count_requests,
                    "write_attempts": clipboard["attempts"],
                    "write_successes": clipboard["successes"],
                    "notice": notice,
                    "textarea_selection_start": selection[0],
                    "textarea_selection_end": selection[1],
                }
                restart()
                transfers()
                page.get_by_label("Import campaign backup", exact=True).set_input_files(
                    path(branch + "_text")
                )
                expect(
                    page.get_by_text(
                        "Campaign imported locally. Save campaign to keep this copy.",
                        exact=True,
                    )
                ).to_be_visible()
                details = page.locator(".campaign-details")
                if details.get_attribute("open") is None:
                    details.locator("summary").click()
                page.get_by_label("Campaign name", exact=True).fill(title)
                save("restored_" + branch)
                phases["original_after_" + branch + "_restore"] = read_json(
                    page, "/api/campaigns/" + original_wrapper["id"]
                )
                assert (
                    phases["original_after_" + branch + "_restore"] == original_wrapper
                )
            screenshot("restored_screen")
            assert set(phases) == set(PHASES)
            transport.write_json(path("phases"), phases)
            stop("interface_quit")
            context.close()
        finally:
            browser.close()
    assert not errors and not external and relay.model_requests == 0
    assert [record["run"] for record in processes] == [1, 2, 3, 4]
    assert len({record["pid"] for record in processes}) == 4
    return {
        "processes": processes,
        "offline": offline,
        "page_errors": len(errors),
        "external_requests": len(external),
        "result_hashes": {
            **{
                phase: transport.object_digest(phases[phase]["document"])
                for phase in PHASES
            },
            "working_copy": transport.object_digest(states["working"]),
        },
    }


def inventory(output: Path) -> list[dict]:
    """Retain only the closed fictional artifact roles, with actual byte hashes."""
    from tools.installed_recovery_contract import (
        ARTIFACT_PATHS,
        MAX_ARTIFACT_BYTES,
        MAX_TOTAL_BYTES,
    )
    from tools.installed_workflow_qualification import validate_png

    expected = {Path(value).name for value in ARTIFACT_PATHS.values()}
    directory = output / "installed-recovery"
    if {path.name for path in directory.iterdir()} != expected:
        raise ValueError("The recovery artifact inventory differs from its contract.")
    admitted, rows, total = [], [], 0
    for role, name in ARTIFACT_PATHS.items():
        path = output / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("A recovery artifact is not a regular retained file.")
        size = path.stat().st_size
        total += size
        if not 1 <= size <= MAX_ARTIFACT_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError("The recovery artifact size exceeds its closed bound.")
        admitted.append((role, name, path, size))
    for role, name, path, size in admitted:
        with path.open("rb") as stream:
            data = stream.read(size + 1)
        if len(data) != size:
            raise ValueError("A recovery artifact changed after size admission.")
        if role.endswith("_screen"):
            validate_png(data)
        rows.append(
            {
                "role": role,
                "path": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": size,
            }
        )
    return rows


def validate_inputs(args: argparse.Namespace) -> dict:
    """Fail before output/process creation unless identities and mode are exact."""
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("Choose a new proof directory; existing output is protected.")
    if any(char in str(args.output.resolve()) for char in (",", "\r", "\n")):
        raise ValueError("The proof path contains unsupported mount characters.")
    if args.chromium and (
        not Path(args.chromium).is_file() or not os.access(args.chromium, os.X_OK)
    ):
        raise ValueError("Choose an executable host Chromium path.")
    if args.source_fixture:
        if any(
            getattr(args, name) is not None
            for name in (
                "installer",
                "installer_sha256",
                "source_archive",
                "source_sha256",
                "native_receipt",
                "installed_workflow_receipt",
                "workflow_sha256",
                "version",
                "source_commit",
            )
        ):
            raise ValueError(
                "Source-fixture mode cannot accept installed proof inputs."
            )
        source = {
            path.relative_to(ROOT).as_posix(): path.read_bytes()
            for path in (ROOT / "src/sinter/web").iterdir()
            if path.is_file()
        }
        init = (ROOT / "src/sinter/__init__.py").read_text()
        args.version = re.search(r'__version__\s*=\s*["\']([^"\']+)', init)[1]
        args.source_commit = transport.command(
            "git", "-C", str(ROOT), "rev-parse", "HEAD"
        )
        return {"source": source, "workflow": None}
    required = (
        "installer",
        "installer_sha256",
        "source_archive",
        "source_sha256",
        "native_receipt",
        "installed_workflow_receipt",
        "workflow_sha256",
        "version",
        "source_commit",
    )
    if any(getattr(args, name) is None for name in required):
        raise ValueError(
            "Installed mode requires every pinned installer/source/workflow input."
        )
    from tools.installed_recovery_contract import VERSION

    if args.version != VERSION:
        raise ValueError(
            "Installed recovery is admitted only for the explicit RC3 version."
        )
    fixture, _ = transport.validate_inputs(args)
    path = args.installed_workflow_receipt
    if (
        not re.fullmatch(r"[0-9a-f]{64}", args.workflow_sha256)
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 1_000_000
        or transport.digest(path) != args.workflow_sha256
    ):
        raise ValueError("The preceding installed-workflow receipt is not pinned.")
    workflow = json.loads(path.read_text())
    identities = {
        "schema": "sinter-installed-workflow/v1",
        "passed": True,
        "source_commit": args.source_commit,
        "version": args.version,
        "installer_sha256": args.installer_sha256,
        "source_archive_sha256": args.source_sha256,
        "native_receipt_sha256": transport.digest(args.native_receipt),
        "web_assets_sha256": fixture["web"],
        "practice_fixture_sha256": fixture["practice_hashes"],
    }
    if any(workflow.get(key) != value for key, value in identities.items()):
        raise ValueError(
            "The preceding installed workflow binds different source/assets."
        )
    from tools.installed_workflow_contract import CHECKS, RECEIPT_FIELDS, RESOURCE_FLAGS

    if (
        set(workflow) != RECEIPT_FIELDS
        or tuple(workflow["checks"]) != CHECKS
        or set(workflow["resources"]) != set(RESOURCE_FLAGS)
        or not all(value is True for value in workflow["resources"].values())
    ):
        raise ValueError("The preceding installed workflow is incomplete.")
    with zipfile.ZipFile(args.source_archive) as archive:
        source = {name: archive.read(name) for name in fixture["web"]}
    return {"source": source, "workflow": workflow}


def qualify(args: argparse.Namespace, inputs: dict) -> dict:
    """Run an isolated real process; failure never creates an admitted receipt."""
    from tools.installed_recovery_contract import (
        CAMPAIGN_SOURCE,
        RECEIPT_PATH,
        RUNTIME_FIELDS,
        SCHEMA,
        fictional_states,
    )

    if sys.platform != "linux":
        raise ValueError("This local Unix-relay producer requires Linux.")
    source, workflow = inputs["source"], inputs["workflow"]
    states = fictional_states(source)
    args.output.mkdir(mode=0o700)
    (args.output / "installed-recovery").mkdir(mode=0o700)
    image = ""
    if not args.source_fixture:
        image = transport.command(
            "docker", "image", "inspect", args.image, "--format", "{{.Id}}"
        )
    receipt = {
        "schema": SCHEMA if not args.source_fixture else "sinter-source-recovery/v1",
        "version": args.version,
        "source_commit": args.source_commit,
        "installer_sha256": args.installer_sha256 or "",
        "source_archive_sha256": args.source_sha256 or "",
        "native_receipt_sha256": transport.digest(args.native_receipt)
        if args.native_receipt
        else "",
        "installed_binary_sha256": "",
        "installed_workflow_receipt_sha256": args.workflow_sha256 or "",
        "runtime": {},
        "processes": [],
        "offline": {},
        "artifacts": [],
        "input_hashes": {
            "garden_campaign": transport.object_digest(states["original"])
        },
        "result_hashes": {},
    }
    if args.source_fixture:
        receipt["qualification"] = False
        receipt["source_files_sha256"] = {
            path.relative_to(ROOT).as_posix(): transport.digest(path)
            for path in sorted((ROOT / "src/sinter").rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts
        }
        for name in (
            "tools/installed_recovery_browser.py",
            "tools/installed_recovery_contract.py",
            "tools/installed_workflow_browser.py",
            "tools/installed_workflow_contract.py",
            "tools/installed_workflow_qualification.py",
            "tools/_support.py",
        ):
            receipt["source_files_sha256"][name] = transport.digest(ROOT / name)
    receipt_path = args.output / (
        "source-recovery-browser.json" if args.source_fixture else RECEIPT_PATH
    )
    transport.write_json(receipt_path, receipt)
    resources = {
        key: False
        for key in (
            "browser_closed",
            "relay_closed",
            "installed_process_stopped",
            "container_removed",
            "package_removed",
        )
    }
    name = "sinter-installed-recovery-" + uuid.uuid4().hex
    created = False
    controller = relay = relay_thread = None
    with tempfile.TemporaryDirectory(prefix="sinter-recovery-private-") as temporary:
        runtime = Path(temporary)
        (runtime / "data").mkdir(mode=0o700)
        try:
            if args.source_fixture:
                identity = {
                    "version": args.version,
                    "binary_sha256": transport.digest(Path(sys.executable)),
                    "web": {
                        name: hashlib.sha256(data).hexdigest()
                        for name, data in source.items()
                    },
                }
                controller = threading.Thread(
                    target=lifecycle,
                    args=(
                        runtime,
                        transport.browser_launch_command(
                            [sys.executable, "-m", "sinter.desktop"], args.version
                        ),
                        identity,
                    ),
                    daemon=True,
                )
                controller.start()
            else:
                shutil.copyfile(Path(__file__), runtime / "helper.py")
                shutil.copyfile(
                    ROOT / "tools/installed_workflow_browser.py",
                    runtime / "workflow_runtime.py",
                )
                transport.command(
                    "docker",
                    "create",
                    "--pull=never",
                    "--network=none",
                    "--name",
                    name,
                    *transport.qualification_container_labels(),
                    "--env",
                    f"SINTER_TEST_UID={os.getuid()}",
                    "--env",
                    f"SINTER_TEST_GID={os.getgid()}",
                    "--mount",
                    f"type=bind,src={runtime},dst=/proof",
                    "--mount",
                    f"type=bind,src={args.installer.resolve()},dst=/candidate.deb,readonly",
                    image,
                    "/usr/bin/python3",
                    "/proof/helper.py",
                    "--container",
                )
                created = True
                transport.command("docker", "start", name)
                assert (
                    transport.command(
                        "docker",
                        "inspect",
                        name,
                        "--format",
                        "{{.HostConfig.NetworkMode}}",
                    )
                    == "none"
                )
            state = transport.wait_state(runtime, "running", 1, 100)
            assert state["version"] == args.version
            if args.source_fixture:
                runtime_fields = {
                    "system": platform.system(),
                    "target_arch": "x64",
                    "machine": platform.machine(),
                    "pointer_bits": struct.calcsize("P") * 8,
                    "frozen": False,
                    "desktop": True,
                    "installed_executable": "",
                    "image_id": "",
                    "container": "",
                    "network": "host loopback test; external browser requests blocked",
                    "network_mode": "host-source-fixture",
                    "host_installation": False,
                    "os_release": {},
                    "libc": list(platform.libc_ver()),
                    "external_requests": 0,
                    "page_errors": 0,
                    "model_calls": 0,
                    "resources": resources,
                    "web_assets_sha256": state["web"],
                    "practice_fixture_sha256": {
                        CAMPAIGN_SOURCE: __import__("hashlib")
                        .sha256(source[CAMPAIGN_SOURCE])
                        .hexdigest()
                    },
                }
            else:
                runtime_fields = copy.deepcopy(
                    {key: workflow[key] for key in RUNTIME_FIELDS}
                )
                assert state["binary_sha256"] == workflow["installed_binary_sha256"]
                assert state["web"] == workflow["web_assets_sha256"]
                assert state["package_version"] == args.version.replace("rc", "~rc")
                assert state["architecture"] == "amd64"
                assert state["os_release"] == {"ID": "ubuntu", "VERSION_ID": "22.04"}
                assert state["libc"] == ["glibc", "2.35"]
                frozen = state["frozen_test"]
                assert frozen["passed"] is True and frozen["frozen"] is True
                assert frozen["version"] == args.version
                assert frozen["system"] == workflow["system"] == "Linux"
                assert frozen["machine"] == state["machine"] == workflow["machine"]
                assert frozen["pointer_bits"] == state["pointer_bits"] == 64
                assert image == workflow["image_id"]
                runtime_fields["resources"] = resources
            receipt["installed_binary_sha256"] = state["binary_sha256"]
            receipt["runtime"] = runtime_fields
            relay = transport.Relay(runtime)
            relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
            relay_thread.start()
            results = browser_workflow(args, runtime, relay, source)
            receipt.update(
                {key: results[key] for key in ("processes", "offline", "result_hashes")}
            )
            runtime_fields.update(
                {key: results[key] for key in ("page_errors", "external_requests")}
            )
            assert relay.model_requests == 0 and relay.errors == 0
            if args.source_fixture:
                if any(
                    transport.digest(ROOT / name) != checksum
                    for name, checksum in receipt["source_files_sha256"].items()
                ):
                    raise ValueError("Source files changed during the fixture proof.")
            resources["browser_closed"] = True
            resources["installed_process_stopped"] = True
            receipt["artifacts"] = inventory(args.output)
        finally:
            if relay is not None:
                relay.shutdown()
                relay.server_close()
                relay_thread.join(timeout=5)
                resources["relay_closed"] = not relay_thread.is_alive() and relay.idle()
            if controller is not None or created:
                transport.write_json(runtime / "control.json", {"action": "cleanup"})
                if controller is not None:
                    controller.join(timeout=20)
                    resources["installed_process_stopped"] = not controller.is_alive()
                else:
                    deadline = time.monotonic() + 20
                    while (
                        not (runtime / "removed.json").exists()
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.05)
                    if (runtime / "removed.json").exists():
                        resources["package_removed"] = (
                            json.loads((runtime / "removed.json").read_text())[
                                "package_removed"
                            ]
                            is True
                        )
                    transport.command("docker", "rm", "--force", name)
                    resources["container_removed"] = True
            if receipt["runtime"]:
                receipt["runtime"]["resources"] = resources
            transport.write_json(receipt_path, receipt)
    required = ("browser_closed", "relay_closed", "installed_process_stopped")
    if not args.source_fixture:
        required = tuple(resources)
    if not all(resources[key] for key in required):
        raise ValueError("The recovery producer did not close all owned resources.")
    return receipt


def arguments(argv=None) -> argparse.Namespace:
    """Parse help before optional dependencies, protecting existing proof folders."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-fixture",
        action="store_true",
        help="Real source desktop proof only; never installed qualification.",
    )
    parser.add_argument("--output", type=Path, required=True)
    for name in (
        "installer",
        "source-archive",
        "native-receipt",
        "installed-workflow-receipt",
    ):
        parser.add_argument("--" + name, type=Path)
    for name in (
        "installer-sha256",
        "source-sha256",
        "source-commit",
        "version",
        "workflow-sha256",
    ):
        parser.add_argument("--" + name)
    parser.add_argument("--image", default="sinter-candidate-qualification:ubuntu2204")
    parser.add_argument("--chromium", default=os.environ.get("SINTER_CHROMIUM"))
    args = parser.parse_args(argv)
    try:
        args.inputs = validate_inputs(args)
    except (
        OSError,
        ValueError,
        KeyError,
        zipfile.BadZipFile,
        subprocess.SubprocessError,
    ) as error:
        parser.error(str(error))
    return args


def main(argv=None) -> None:
    """Produce observed recovery evidence or fail without an admitted success."""
    if (sys.argv[1:] if argv is None else argv) == ["--container"]:
        container_main()
        return
    args = arguments(argv)
    try:
        from playwright.sync_api import Error as BrowserError
    except ImportError:
        raise SystemExit(
            "Host Playwright is required: install .[browser] and Chromium."
        ) from None
    try:
        qualify(args, args.inputs)
    except (
        AssertionError,
        OSError,
        ValueError,
        KeyError,
        subprocess.SubprocessError,
        BrowserError,
    ) as error:
        frames = traceback.extract_tb(error.__traceback__)
        origin = (
            f" at {Path(frames[-1].filename).name}:{frames[-1].lineno}"
            if frames else ""
        )
        raise SystemExit(
            f"Recovery proof failed ({type(error).__name__}{origin}); "
            "no completed installed qualification was produced."
        ) from None
    print(
        "PASS: "
        + (
            "source fixture only; not installed qualification"
            if args.source_fixture
            else "actual installed offline campaign recovery"
        )
    )


if __name__ == "__main__":
    main()
