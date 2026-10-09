"""Offline scoped-project use and full recovery through owned source processes.

Linux source rehearsal only: no package, native window, prior replacement or
candidate admission. Also executes the unchanged v1 campaign recovery profile.
"""

from __future__ import annotations

import argparse
import copy
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import installed_recovery_browser as legacy  # noqa: E402
from tools._support import expect_campaign_message, save_campaign
from tools import installed_workflow_browser as transport  # noqa: E402
from tools import rc4_recovery_source as base  # noqa: E402
from tools.installed_menu_browser import browser_notice  # noqa: E402
from tools.rc4_recovery_worker import canonical, snapshot  # noqa: E402
from tools.rc4_scoped_recovery_contract import (  # noqa: E402
    ACTION,
    NOTE,
    QUESTIONS,
    RECEIPT,
    SCHEMA,
    TITLE,
    fixture,
    seed_projection,
    validate_rehearsal,
)


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def protocol(runtime, output, saved):
    """Actual direct loopback protocol; duplicate headers stay duplicate on wire."""
    state = json.loads((runtime / "state.json").read_text(encoding="utf-8"))
    port = state["port"]

    def request(method, path, body=None, capabilities=()):
        channel = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            channel.putrequest(method, path)
            channel.putheader("Origin", f"http://127.0.0.1:{port}")
            if token is not None:
                channel.putheader("X-Sinter-Token", token)
            for value in capabilities:
                channel.putheader("X-Sinter-Casebook-Schema", value)
            payload = (
                json.dumps(body, allow_nan=False).encode() if body is not None else b""
            )
            if body is not None:
                channel.putheader("Content-Type", "application/json")
                channel.putheader("Content-Length", str(len(payload)))
            channel.endheaders(payload)
            response = channel.getresponse()
            data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise ValueError("Protocol response exceeded its bound")
            return response.status, json.loads(data)
        finally:
            channel.close()

    token = None
    status, session = request("GET", "/api/session")
    assert status == 200
    token = session["token"]
    before = snapshot(runtime / "data")
    jobs = request("GET", "/api/jobs")
    downgrade = {
        k: copy.deepcopy(v)
        for k, v in saved["document"].items()
        if k not in {"question_scopes", "scope_fingerprint"}
    }
    downgrade["schema"] = "sinter-casebook/v1"
    body = {"id": saved["id"], "revision": saved["revision"]}
    routes = [
        ("get", "GET", "/api/casebooks/" + saved["id"], None),
        (
            "validate",
            "POST",
            "/api/casebooks/validate",
            {"document": saved["document"]},
        ),
        (
            "save_scoped",
            "POST",
            "/api/casebooks/save",
            {**body, "document": saved["document"]},
        ),
        (
            "save_v1_over_scoped",
            "POST",
            "/api/casebooks/save",
            {**body, "document": downgrade},
        ),
        ("build", "POST", "/api/casebooks/build", body),
        ("draft", "POST", "/api/casebooks/draft", body),
    ]
    v2 = "sinter-casebook/v2"
    variants = {
        "missing": [],
        "wrong": ["sinter-casebook/v1"],
        "duplicate_valid": [v2, v2],
        "valid_wrong": [v2, "sinter-casebook/v1"],
        "wrong_valid": ["sinter-casebook/v1", v2],
    }
    results = []
    for name, method, path, payload in routes:
        for variant, capabilities in variants.items():
            status, response = request(method, path, payload, capabilities)
            assert status == 400 and "no choices were cleared" in response["error"]
            assert canonical(snapshot(runtime / "data")) == canonical(before)
            assert request("GET", "/api/jobs") == jobs
            results.append(
                {
                    "route": name,
                    "variant": variant,
                    "status": status,
                    "response": response,
                }
            )
    assert request("GET", "/api/casebooks/" + saved["id"], capabilities=[v2]) == (
        200,
        saved,
    )
    assert request(
        "POST", "/api/casebooks/validate", {"document": saved["document"]}, [v2]
    ) == (200, {"document": saved["document"]})
    result = {
        "matrix": results,
        "capable_get": saved,
        "capable_validate": saved["document"],
        "snapshot_before": before,
        "snapshot_after": snapshot(runtime / "data"),
        "jobs_before": jobs,
        "jobs_after": request("GET", "/api/jobs"),
    }
    write_json(output / "protocol.json", result)
    return result


def browser_workflow(
    args,
    runtime,
    relay,
    *,
    snapshot_observer=None,
    protocol_observer=None,
    browser_session=None,
):
    from playwright.sync_api import expect, sync_playwright

    from tools._support import launch_chromium

    observe_snapshot = snapshot if snapshot_observer is None else snapshot_observer
    observe_protocol = protocol if protocol_observer is None else protocol_observer
    origin = f"http://127.0.0.1:{relay.server_address[1]}"
    observations = {
        "phases": [],
        "offline": {},
        "errors": [],
        "external": [],
        "dialogs": [],
        "warnings": [],
    }
    output = args.output

    def read(p, path):
        return p.evaluate(
            "path=>fetch(path,{headers:{"
            "'X-Sinter-Casebook-Schema':'sinter-casebook/v2'}})"
            ".then(async r=>{if(!r.ok)throw Error('Local read failed');"
            "return r.json()})",
            path,
        )

    def phase(name):
        observations["phases"].append(
            {"name": name, "snapshot": observe_snapshot(runtime / "data")}
        )
        write_json(output / "observations.json", observations)

    def transfer(p):
        d = (
            p.locator("details")
            .filter(has=p.get_by_text("Backups and project removal", exact=True))
            .last
        )
        if d.get_attribute("open") is None:
            d.locator("summary").click()

    def open_project(p, title):
        tile = p.locator("article.casebook-tile").filter(
            has=p.get_by_text(title, exact=True)
        )
        expect(tile).to_have_count(1)
        tile.get_by_role("button", name="Open project", exact=True).click()
        expect(p.get_by_label("Project name", exact=True)).to_have_value(title)

    def save(p):
        p.get_by_role("button", name="Save project", exact=True).click()
        expect(p.get_by_label("Project save state", exact=True)).to_contain_text(
            "Project inputs saved at revision"
        )
        title = p.get_by_label("Project name", exact=True).input_value()
        rows = read(p, "/api/casebooks")["casebooks"]
        row = next(r for r in rows if r["title"] == title)
        return read(p, "/api/casebooks/" + row["id"])

    def download(p, path, label="Export project backup"):
        with p.expect_download() as received:
            p.get_by_role("button", name=label, exact=True).click()
        received.value.save_as(output / path)
        return json.loads((output / path).read_text(encoding="utf-8"))

    def stop(run, method="terminate"):
        if method == "terminate":
            write_json(runtime / "control.json", {"action": "stop"})
        state = transport.wait_state(runtime, "stopped", run)
        assert (
            state["exit_code"] == 0
            and state["port_closed"] is True
            and state["stop_method"] == method
        )
        phase(f"stopped-{run}")

    def restart(run):
        write_json(runtime / "control.json", {"action": "restart"})
        state = transport.wait_state(runtime, "running", run)
        assert state["run"] == run

    def quit(p, run):
        p.get_by_role("button", name="Quit Sinter", exact=True).click()
        dialog = p.get_by_role("dialog", name="Quit Sinter?", exact=True)
        if dialog.is_visible():
            dialog.get_by_role("button", name="Quit Sinter", exact=True).click()
        stop(run, "interface_quit")

    def originals(p, book):
        details = p.locator("details.source").filter(
            has=p.locator("button").filter(has_text="Remove source")
        )
        expect(details).to_have_count(len(book["documents"]))
        for i, row in enumerate(book["documents"]):
            d = details.nth(i)
            if d.get_attribute("open") is None:
                d.locator("summary").click()
            expect(d.locator("pre")).to_have_text(row["content"])
            assert d.locator("pre").text_content() == row["content"]

    with sync_playwright() if browser_session is None else browser_session() as driver:
        browser = (
            launch_chromium(driver, args.chromium)
            if browser_session is None
            else browser_session.launch(driver, args.chromium)
        )
        context = None
        try:
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                reduced_motion="reduce",
                accept_downloads=True,
                permissions=["clipboard-read", "clipboard-write"],
                service_workers="block",
            )
            context.route(
                "**/*",
                lambda r: (
                    r.continue_()
                    if r.request.url.startswith(origin + "/")
                    else (observations["external"].append(r.request.url), r.abort())
                ),
            )
            context.route_web_socket(
                "**/*",
                lambda r: (observations["external"].append("websocket"), r.close()),
            )

            def page():
                p = context.new_page()
                p.set_default_timeout(10000)
                p.on(
                    "pageerror", lambda error: observations["errors"].append(str(error))
                )
                p.on(
                    "dialog",
                    lambda dialog: (
                        observations["dialogs"].append(dialog.type),
                        dialog.dismiss(),
                    ),
                )
                p.goto(origin + "/#casebooks")
                return p

            p = page()
            transfer(p)
            write_json(output / "fixture.json", fixture())
            p.get_by_label("Restore a casebook backup", exact=True).set_input_files(
                output / "fixture.json"
            )
            expect(p.get_by_label("Project name", exact=True)).to_have_value(TITLE)
            initial = save(p)
            originals(p, initial["document"])
            scopes = (
                p.locator("details")
                .filter(
                    has=p.get_by_text("Choose sources for each question", exact=True)
                )
                .first
            )
            scopes.locator(":scope > summary").click()
            for index in (0, 1):
                q = p.locator(f'details[data-question-scope-index="{index}"]')
                if q.get_attribute("open") is None:
                    q.locator(":scope > summary").click()
                q.get_by_label(
                    f"Sources for question {index + 1}", exact=True
                ).select_option("selected")
                if index == 0:
                    # Inspection preserves selection and full original bytes.
                    q = p.locator('details[data-question-scope-index="0"]')
                    choice = q.locator("[data-source-choice-id]").nth(0)
                    choice.locator("summary").click()
                    expect(choice.locator("pre")).to_have_text(
                        initial["document"]["documents"][0]["content"]
                    )
                    choice.get_by_role("checkbox").check()
            warning = p.get_by_text(
                "Explicit source choices use casebook v2.", exact=False
            )
            warning.scroll_into_view_if_needed()
            expect(warning).to_be_visible()
            expect(warning).to_be_in_viewport()
            observations["warnings"].append(warning.inner_text())
            p.screenshot(path=output / "scope-warning.png")
            scoped = save(p)
            changed_questions = (
                QUESTIONS[0] + " Revised wording?\n" + "\n".join(QUESTIONS[1:])
            )
            p.get_by_label("What do you need to find out?", exact=True).fill(
                changed_questions
            )
            stale_requests = []
            p.on(
                "request",
                lambda request: (
                    stale_requests.append(request.url)
                    if request.method == "POST"
                    else None
                ),
            )
            p.get_by_role("button", name="Save project", exact=True).click()
            stale = p.get_by_role("alert").filter(has_text="Questions changed or moved")
            expect(stale).to_be_visible()
            stale.scroll_into_view_if_needed()
            expect(stale).to_be_in_viewport()
            transfer(p)
            working = download(p, "stale-scope.json")
            assert working["question_scopes"] == scoped["document"]["question_scopes"]
            assert read(p, "/api/casebooks/" + scoped["id"]) == scoped
            assert not stale_requests
            observations["stale_scope"] = {
                "working": working,
                "stored": scoped,
                "posts": len(stale_requests),
                "warning": stale.inner_text(),
            }
            stale.scroll_into_view_if_needed()
            expect(stale).to_be_in_viewport()
            p.screenshot(path=output / "stale-scope.png")
            changed_field = p.get_by_label("What do you need to find out?", exact=True)
            expect(changed_field).to_have_value(changed_questions)
            changed_field.scroll_into_view_if_needed()
            p.screenshot(path=output / "stale-inputs.png")
            choice = p.locator('details[data-question-scope-index="0"]')
            if choice.get_attribute("open") is None:
                choice.locator(":scope > summary").click()
            retained_choice = choice.get_by_text(
                "This choice needs review.", exact=False
            )
            retained_choice.scroll_into_view_if_needed()
            expect(retained_choice).to_be_visible()
            expect(retained_choice).to_be_in_viewport()
            expect(
                choice.locator("[data-source-choice-id]").first.get_by_role("checkbox")
            ).to_be_checked()
            p.screenshot(path=output / "stale-choice.png")
            p.get_by_label("What do you need to find out?", exact=True).fill(
                "\n".join(QUESTIONS)
            )

            p.get_by_role(
                "button", name="Prepare source-only report", exact=True
            ).click()
            report = p.get_by_role("region", name="Your draft report", exact=True)
            expect(report).to_be_visible()
            report.get_by_role("tab", name="Evidence", exact=True).click()
            expect(
                p.get_by_role("article", name="Question 1 evidence")
            ).to_contain_text("1 selected source")
            expect(
                p.get_by_role("article", name="Question 2 evidence")
            ).to_contain_text("No sources selected")
            expect(
                p.get_by_role("article", name="Question 3 evidence")
            ).to_contain_text("All supplied sources")
            quote = (
                p.get_by_role("article", name="Question 1 evidence")
                .locator(".question-evidence-quote")
                .first
            )
            quote.locator("summary").click()
            quote.get_by_role(
                "button", name="Open original source for Passage 1", exact=True
            ).click()
            opened = (
                p.locator(".sources-panel [data-source-id]")
                .filter(has=p.locator("pre"))
                .first
            )
            expect(opened.locator("pre")).to_have_text(
                initial["document"]["documents"][0]["content"]
            )
            report.get_by_role("tab", name="Document", exact=True).click()
            paper = report.locator(".document-paper")
            expect(paper).to_contain_text("No sources were selected for this question")
            report.get_by_text("More options", exact=True).click()
            report.get_by_role("button", name="Edit draft", exact=True).click()
            editor = report.get_by_label("Edit your draft", exact=True)
            editor.fill(editor.input_value() + NOTE)
            report.get_by_role("button", name="Apply edits", exact=True).click()
            source = {
                n: p.read_bytes()
                for n, p in (
                    (p.relative_to(ROOT).as_posix(), p)
                    for p in (ROOT / "src/sinter/web").iterdir()
                )
                if p.is_file()
            }
            report.get_by_role(
                "button", name=transport.report_save_label(source), exact=True
            ).click()
            expect(
                report.get_by_text(
                    "Saved in My workspace, including your edits "
                    "and original evidence.",
                    exact=True,
                )
            ).to_be_visible()
            scoped = read(p, "/api/casebooks/" + scoped["id"])
            report_rows = read(p, "/api/reports")["reports"]
            report_row = next(r for r in report_rows if r["title"] == TITLE)
            observations["scoped"] = scoped
            observations["report_id"] = report_row["id"]
            observations["report"] = read(p, "/api/reports/" + report_row["id"])
            with p.expect_download() as received:
                report.get_by_role(
                    "button", name="Download Word (.docx)", exact=True
                ).click()
            received.value.save_as(output / "handover.docx")
            p.screenshot(path=output / "handover.png")
            observe_protocol(runtime, output, scoped)
            # A separate scoped control proves current UI optimistic conflict.
            write_json(output / "control-import.json", scoped["document"])
            transfer(p)
            p.get_by_label("Restore a casebook backup", exact=True).set_input_files(
                output / "control-import.json"
            )
            expect(
                p.get_by_text("Backup opened as a new unsaved project.", exact=True)
            ).to_be_visible()
            p.get_by_label("Project name", exact=True).fill(
                TITLE + " — conflict control"
            )
            control = save(p)
            other = page()
            open_project(other, TITLE + " — conflict control")
            p.get_by_label("Recipient or audience", exact=True).fill(
                "Fictional local unsaved conflict 🐝"
            )
            other.get_by_label("Recipient or audience", exact=True).fill(
                "Fictional other-window saved wording"
            )
            updated = save(other)
            before = observe_snapshot(runtime / "data")
            conflict_posts = []
            p.on(
                "request",
                lambda request: (
                    conflict_posts.append(request.url)
                    if request.method == "POST"
                    and request.url.endswith("/api/casebooks/save")
                    else None
                ),
            )
            p.get_by_role("button", name="Save project", exact=True).click()
            conflict_warning = p.get_by_role("alert").filter(
                has_text="changed in another window"
            )
            expect(conflict_warning).to_be_visible()
            conflict_warning.scroll_into_view_if_needed()
            expect(conflict_warning).to_be_in_viewport()
            backup = download(p, "scoped-conflict.json")
            p.wait_for_timeout(250)
            assert (
                len(conflict_posts) == 1
                and read(p, "/api/casebooks/" + control["id"]) == updated
            )
            assert canonical(before) == canonical(observe_snapshot(runtime / "data"))
            assert read(p, "/api/casebooks/" + scoped["id"]) == scoped
            observations["conflict"] = {
                "initial": control,
                "saved": updated,
                "working": backup,
                "posts": 1,
                "automatic_replays": 0,
                "snapshot_before": before,
                "snapshot_after": observe_snapshot(runtime / "data"),
                "warning": conflict_warning.inner_text(),
            }
            conflict_warning.scroll_into_view_if_needed()
            expect(conflict_warning).to_be_in_viewport()
            p.screenshot(path=output / "scoped-conflict.png")
            conflict_input = p.get_by_label("Recipient or audience", exact=True)
            expect(conflict_input).to_have_value("Fictional local unsaved conflict 🐝")
            conflict_input.scroll_into_view_if_needed()
            p.screenshot(path=output / "conflict-inputs.png")
            other.close()

            p.goto(origin + "/#home")
            p.get_by_role(
                "region", name="Fictional garden practice project"
            ).get_by_role("button", name="Open garden campaign", exact=True).click()
            p.get_by_role("tab", name="Next actions", exact=True).click()
            card = legacy.action_card(p, 0)
            card.locator('[data-campaign-field="task"]').fill(ACTION)
            save_campaign(p)
            expect_campaign_message(p, transport.SAVED_CAMPAIGN, exact=True)
            campaign_row = read(p, "/api/campaigns")["campaigns"][0]
            observations["campaign"] = read(p, "/api/campaigns/" + campaign_row["id"])
            phase("saved-use")
            quit(p, 1)
            p.close()
            restart(2)
            p = page()
            open_project(p, TITLE)
            originals(p, scoped["document"])
            transfer(p)
            assert download(p, "reopened.json") == {
                k: v for k, v in scoped["document"].items() if k != "fingerprint"
            }
            assert read(p, "/api/reports/" + report_row["id"]) == observations["report"]
            assert (
                read(p, "/api/campaigns/" + campaign_row["id"])
                == observations["campaign"]
            )
            phase("reopened-use")
            # Stop, refuse saving, and restore each complete branch separately.
            for branch, run in (("clipboard", 2), ("manual", 3)):
                p.get_by_label("Recipient or audience", exact=True).fill(
                    "Fictional " + branch + " recovery 🐝 e\u0301"
                )
                reference = download(p, branch + "-reference.json")
                p.evaluate(
                    (
                        "mode=>{const original=navigator.clipboard.writeText.bind"
                        "(navigator.clipboard);window.scopedClipboard={attempts:0"
                        ",successes:0};Object.defineProperty(navigator.clipboard,"
                        "'writeText',{value:async text=>{window.scopedClipboard.a"
                        "ttempts++;if(mode==='manual')throw new DOMException('Fic"
                        "tional denial','NotAllowedError');await original(text);w"
                        "indow.scopedClipboard.successes++}})}"
                    ),
                    branch,
                )
                stop(run)
                persistent = observe_snapshot(runtime / "data")
                p.get_by_role("button", name="Save project", exact=True).click()
                expect(p.get_by_role("alert")).to_contain_text(
                    "Cannot reach the local Sinter app"
                )
                backup = p.get_by_role("region", name="Copy project backup", exact=True)
                backup.get_by_role(
                    "button", name="Copy backup text", exact=True
                ).click()
                expect(backup).to_contain_text(
                    "Backup text copied from your inputs"
                    if branch == "clipboard"
                    else "Clipboard unavailable."
                )
                text = backup.get_by_label("Project backup text", exact=True)
                actual = text.input_value()
                assert json.loads(actual) == reference
                backup.get_by_role(
                    "button", name="Select backup text", exact=True
                ).click()
                selection = text.evaluate("e=>[e.selectionStart,e.selectionEnd]")
                assert selection == [0, len(actual.encode("utf-16-le")) // 2]
                if branch == "clipboard":
                    assert p.evaluate("navigator.clipboard.readText()") == actual
                (output / (branch + ".json")).write_text(
                    actual, encoding="utf-8", newline="\n"
                )
                observations["offline"][branch] = {
                    "document": reference,
                    "selection": selection,
                    "clipboard": p.evaluate("window.scopedClipboard"),
                    "snapshot_before": persistent,
                    "snapshot_after": observe_snapshot(runtime / "data"),
                }
                assert canonical(persistent) == canonical(
                    observations["offline"][branch]["snapshot_after"]
                )
                p.screenshot(path=output / (branch + ".png"))
                p.close()
                restart(run + 1)
                p = page()
                transfer(p)
                p.get_by_label("Restore a casebook backup", exact=True).set_input_files(
                    output / (branch + ".json")
                )
                expect(
                    p.get_by_text("Backup opened as a new unsaved project.", exact=True)
                ).to_be_visible()
                p.get_by_label("Project name", exact=True).fill(
                    TITLE + " — " + branch + " restored"
                )
                copy_saved = save(p)
                observations[branch + "_restored"] = copy_saved
                assert copy_saved["id"] != scoped["id"]
                assert read(p, "/api/casebooks/" + scoped["id"]) == scoped
                originals(p, copy_saved["document"])
                transfer(p)
                if branch == "clipboard":
                    open_project(p, TITLE)
                    transfer(p)
            phase("restored-both")
            assert (
                observations["clipboard_restored"]["id"]
                != observations["manual_restored"]["id"]
            )
            quit(p, 4)
            assert (
                not observations["errors"]
                and not observations["external"]
                and not observations["dialogs"]
            )
            write_json(output / "observations.json", observations)
        finally:
            if context:
                context.close()
            browser.close()
    return observations


def rehearse(args, pinned):
    args.output.mkdir(mode=0o700)
    receipt = {
        "schema": SCHEMA,
        "execution": "source",
        "source_base_commit": args.source_commit,
        "source_manifest_sha256": args.source_manifest_sha256,
        "source_files_sha256": pinned["files"],
        "observed_version": pinned["version"],
        "candidate_admitted": False,
        "installed_tested": False,
        "native_tested": False,
        "prior_replacement_tested": False,
        "release_qualified": False,
        "source_rehearsal_passed": False,
        "source_files_conserved": False,
        "resources": {},
        "failure": None,
        "artifacts": {},
    }
    relay = relay_thread = controller = lifecycle = None
    temporary = tempfile.TemporaryDirectory(prefix="sr2-")
    (args.output / "process").mkdir()
    try:
        base.rehearse(
            argparse.Namespace(**{**vars(args), "output": args.output / "v1-profile"}),
            pinned,
        )
        runtime = Path(temporary.name)
        (runtime / "home").mkdir(mode=0o700)
        worker = ROOT / "tools/rc4_scoped_recovery_worker.py"
        proc = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(worker),
                "--source",
                str(ROOT),
                "--data",
                str(runtime / "data"),
                "--control",
                str(args.output / "seed-control.json"),
                "--seed-only",
            ],
            env={"PATH": os.defpath, "HOME": str(runtime / "home")},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
        (args.output / "seed.stdout").write_bytes(proc.stdout)
        (args.output / "seed.stderr").write_bytes(proc.stderr)
        if proc.returncode or proc.stderr:
            raise ValueError("Scoped seed failed; raw diagnostics retained")
        seeded = json.loads(
            (args.output / "seed-control.json").read_text(encoding="utf-8")
        )["seed"]["snapshot"]
        identity = {
            "version": pinned["version"],
            "binary_sha256": base.digest(Path(sys.executable)),
            "web": {
                p.relative_to(ROOT).as_posix(): base.digest(p)
                for p in (ROOT / "src/sinter/web").iterdir()
                if p.is_file()
            },
            "notice": browser_notice((ROOT / "src/sinter/desktop.py").read_bytes()),
        }

        def preserve(value):
            return seed_projection(value, seeded)

        lifecycle = base.SourceLifecycle(
            runtime,
            args.output,
            identity,
            preserve(seeded),
            preserve=preserve,
            worker=worker,
        )
        controller = threading.Thread(target=lifecycle.run, daemon=True)
        controller.start()
        transport.wait_state(runtime, "running", 1)
        relay = transport.Relay(runtime)
        relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
        relay_thread.start()
        browser_workflow(args, runtime, relay)
        write_json(runtime / "control.json", {"action": "cleanup"})
        controller.join(timeout=15)
        if controller.is_alive() or lifecycle.failure or not lifecycle.closed:
            raise ValueError("Scoped source cleanup failed")
        if relay.model_requests or relay.errors:
            raise ValueError("Scoped UI attempted model work or transport failed")
        receipt["resources"]["browser_closed"] = True
    except Exception as error:
        receipt["failure"] = type(error).__name__ + ": " + str(error)
        (args.output / "failure.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
    finally:
        cleanup = []
        if relay:
            for action in (relay.shutdown, relay.server_close):
                try:
                    action()
                except Exception as error:
                    cleanup.append(str(error))
            relay_thread.join(timeout=5)
            receipt["resources"]["outer_relay_closed"] = (
                not relay_thread.is_alive() and relay.idle()
            )
        if controller and controller.is_alive():
            write_json(runtime / "control.json", {"action": "cleanup"})
            controller.join(timeout=15)
        receipt["resources"]["source_processes_stopped"] = bool(
            lifecycle and not controller.is_alive() and lifecycle.closed
        )
        receipt["resources"]["inner_relay_closed"] = bool(
            lifecycle and lifecycle.closed
        )
        if cleanup:
            receipt["failure"] = (
                (receipt["failure"] or "") + "; cleanup: " + "; ".join(cleanup)
            )
        try:
            receipt["source_files_conserved"] = (
                base.verify_source(
                    argparse.Namespace(
                        **{**vars(args), "output": args.output / "unused"}
                    )
                )["files"]
                == pinned["files"]
            )
        except (OSError, ValueError) as error:
            receipt["failure"] = (receipt["failure"] or "") + "; source: " + str(error)
        receipt["artifacts"] = {
            p.relative_to(args.output).as_posix(): {
                "sha256": base.digest(p),
                "bytes": p.stat().st_size,
            }
            for p in sorted(args.output.rglob("*"))
            if p.is_file()
        }
        write_json(args.output / RECEIPT, receipt)
        temporary.cleanup()
    if receipt["failure"]:
        raise ValueError(
            "Scoped source recovery failed; retained receipt is not a pass"
        )
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
        write_json(args.output / RECEIPT, receipt)
        raise ValueError(
            "Scoped evidence validation failed; receipt is not a pass"
        ) from error
    receipt["source_rehearsal_passed"] = True
    write_json(args.output / RECEIPT, receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chromium", default=os.environ.get("SINTER_CHROMIUM"))
    args = parser.parse_args(argv)
    if sys.flags.optimize or sys.platform != "linux":
        parser.exit(1, "Use unoptimised Python on Linux for this source rehearsal.\n")
    try:
        pinned = base.verify_source(args)
        from tools._support import require_module

        require_module(
            parser,
            "playwright.sync_api",
            "Playwright",
            "python -m pip install '.[browser]'",
        )
        rehearse(args, pinned)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Scoped source rehearsal refused: {error}\n")
    print("Scoped source recovery completed; no installed or release qualification.")


if __name__ == "__main__":
    main()
