"""Fictional offline route-purpose journeys through the actual campaign UI.

Creates one new private evidence directory and an isolated retained workspace.
No private campaign, provider, mailbox, external page or installed release is
used. This qualifies recorded local flows, not eligibility or product scores.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import launch_chromium, require_module  # noqa: E402
from tools.campaign_browser import CampaignChecks  # noqa: E402


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default=os.environ.get("SINTER_CHROMIUM"))
    parser.add_argument("--output-dir", type=Path,
                        help="New private evidence directory; never reused.")
    args = parser.parse_args(argv)
    require_module(parser, "playwright.sync_api", "Playwright",
                   "python -m pip install '.[browser]'")
    if args.chromium:
        args.chromium = str(Path(args.chromium).expanduser().resolve(strict=True))
        if not Path(args.chromium).is_file() or not os.access(args.chromium, os.X_OK):
            parser.error("Choose an existing executable Chromium path.")
    if args.output_dir:
        args.output_dir = args.output_dir.expanduser().absolute()
        if not args.output_dir.parent.is_dir():
            parser.error("The output parent must exist.")
        if args.output_dir.exists() or args.output_dir.is_symlink():
            parser.error("Retain the existing output and choose a new directory.")
    return args


def write_json(path, value):
    """Create complete private evidence without replacing an earlier file."""
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
           + "\n").encode("utf-8")
    temporary = path.with_name(path.name + ".partial")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                         | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, path)
    temporary.unlink()
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def source_pins():
    paths = sorted(path for path in (ROOT / "src/sinter").rglob("*")
                   if path.is_file() and "__pycache__" not in path.parts
                   and path.suffix != ".pyc")
    paths.extend(ROOT / name for name in (
        "tools/_support.py", "tools/campaign_browser.py",
        "tools/deliverable_browser.py"))
    paths.append(Path(__file__).resolve())
    result = {}
    for path in paths:
        if path.is_symlink():
            raise ValueError("Do not qualify redirected runtime source.")
        raw = path.read_bytes()
        result[path.relative_to(ROOT).as_posix()] = {
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return result


def fixture(title, purpose=None, mode="unknown", *, history=False):
    """Fixed identities and literal old snapshots, with no real-world facts."""
    today = date.today().isoformat()
    name = "Fictional primary route"
    route = {"name": name, "funder": "Fictional Example Counterpart",
             "status": "open", "route_type": "other",
             "application_mode": mode,
             "fit": "Fictional scope only. No approval, agreement or income."}
    if purpose is not None:
        route["purpose"] = purpose
    document = {
        "schema": "sinter-campaign/v1", "title": title,
        "organisation": "Fictional Research Association",
        "objective": "Retain original evidence and clarify a practical next step.",
        "opportunities": [route],
        "sources": [
            {"id": "1" * 32, "title": "Fictional current source",
             "url": "https://example.invalid/current", "checked_at": today,
             "notes": "Current fictional register; not a verified decision."},
            {"id": "2" * 32, "title": "Fictional original snapshot",
             "url": "https://example.invalid/original", "checked_at": "2019-01-01",
             "notes": "Original café e\u0301 🐝\r\n<literal>. No commitment."},
        ],
        "answers": [{"opportunity": name, "label": "PRIVATE HELD QUESTION",
                     "text": "PRIVATE HELD ANSWER e\u0301 🐝 <literal>.",
                     "limit": 300, "status": "reviewed"}],
        "actions": [
            {"opportunity": name, "scope_confirmed": True,
             "submission_phase": "pre_submission", "task": "Fictional held task",
             "owner": "Possible coordinator", "owner_kind": "unknown",
             "owner_confirmed": False, "due": "", "status": "held"},
            {"opportunity": name, "scope_confirmed": True,
             "submission_phase": "pre_submission", "task": "Fictional unassigned hold",
             "owner": "", "owner_kind": "unassigned", "owner_confirmed": False,
             "due": "", "status": "held"},
        ],
        "communications": [{"opportunity": name, "direction": "outgoing",
            "status": "draft", "date": "", "subject": "Original unsent record",
            "content": "Fictional original draft. No message was sent.",
            "evidence_links": [{"source_id": "2" * 32,
                "title": "Fictional saved title", "url": "https://example.invalid/original",
                "checked_at": "2019-01-01", "notes": "Saved old wording e\u0301 🐝."}]}],
    }
    if history:
        document["requirements"] = [{
            "opportunity": name, "rule": "Fictional permission remains unresolved",
            "status": "not_met", "evidence": "No permission is established.",
            "source_id": "1" * 32, "source_url": "https://example.invalid/old-current",
            "source_quote": "Old exact wording e\u0301 🐝 <literal>.",
            "checked_at": "2019-01-01", "source_history": [{
                "state": "historical", "reason": "replaced", "record": {
                    "opportunity": name, "rule": "Original fictional condition",
                    "status": "met", "evidence": "Original note; no current confirmation.",
                    "source_id": "2" * 32, "source_url": "https://example.invalid/original",
                    "source_quote": "Original café 🐝\r\n<literal>.",
                    "checked_at": "2019-01-01"}}]}]
    return document


class PurposeChecks(CampaignChecks):
    def __init__(self, browser, base, artifacts, store):
        super().__init__(browser, base, artifacts)
        self.store = store
        self.contexts = []
        self.expected_console = []
        self.local_responses = []
        self.backups = []
        self.fixture_inputs = []
        self.transport_guards = []

    def check(self, name, action):
        """Retain every failed journey; no profile mutation or broad error filter."""
        started = time.monotonic()
        context = page = None
        result = {"check": name, "passed": False, "context_closed": False}
        origin = urlsplit(self.base)
        try:
            context = self.browser.new_context(viewport={"width": 1265, "height": 712},
                accept_downloads=True, reduced_motion="reduce", service_workers="block")
            def guard(route):
                target = urlsplit(route.request.url)
                if (target.scheme, target.hostname, target.port) == (
                        origin.scheme, origin.hostname, origin.port):
                    route.continue_()
                else:
                    self.external.append({"check": name, "url": route.request.url})
                    route.abort()
            context.route("**/*", guard)
            def attach(opened):
                opened.set_default_timeout(9000)
                opened.on("pageerror", lambda error: self.errors.append(
                    {"check": name, "kind": "pageerror", "error": str(error)}))
                opened.on("console", lambda message: self.errors.append(
                    {"check": name, "kind": "console", "error": message.text,
                     "url": message.location.get("url", "")})
                    if message.type == "error" else None)
                opened.on("dialog", lambda dialog: dialog.accept())
                opened.on("response", lambda response: self.local_responses.append(
                    {"check": name, "path": urlsplit(response.url).path,
                     "status": response.status, "method": response.request.method}))
            context.on("page", attach)
            page = context.new_page()
            action(page)
            assert not re.search(r"(?m)^\s*(?:null|undefined)\s*$",
                                 page.locator("body").inner_text())
            result["passed"] = True
        except Exception as problem:
            result["error"] = type(problem).__name__ + ": " + str(problem)
            if page:
                try:
                    self.screenshot(page, name + "-FAILED", full_page=True)
                except Exception as capture:
                    result["screenshot_error"] = str(capture)
        finally:
            if context:
                try:
                    context.close()
                    result["context_closed"] = True
                except Exception as problem:
                    result["cleanup_error"] = str(problem)
            result["seconds"] = round(time.monotonic() - started, 3)
            self.results.append(result)
            print(("PASS: " if result["passed"] else "FAIL: ") + name, flush=True)

    def save(self, page):
        from playwright.sync_api import expect
        with page.expect_response(self.base + "/api/campaigns/save") as reply:
            page.get_by_role("button", name="Save campaign", exact=True).click()
        assert reply.value.status == 200
        saved = reply.value.json()
        expect(page.locator(".campaign-save-state")).to_have_text("Saved on this computer")
        expect(page.get_by_role("button", name="Save campaign", exact=True)).to_be_enabled()
        assert self.store.get(saved["id"]) == saved
        return saved

    def start(self, page, document):
        path = self.artifacts / f"fixture-input-{len(self.fixture_inputs) + 1:02d}.json"
        write_json(path, document)
        raw = path.read_bytes()
        self.fixture_inputs.append({"file": path.name, "title": document["title"],
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        self.import_fixture(page, document)
        saved = self.save(page)
        return saved

    def export(self, page, label):
        self.transfers(page)
        path = self.artifacts / (label + ".json")
        with page.expect_download() as pending:
            page.get_by_role("button", name="Export campaign backup", exact=True).click()
        pending.value.save_as(path)
        os.chmod(path, 0o600)
        raw = path.read_bytes()
        self.backups.append({"file": path.name, "bytes": len(raw),
                             "sha256": hashlib.sha256(raw).hexdigest()})
        return json.loads(raw)

    @staticmethod
    def card(page):
        return page.get_by_role("region", name="Campaign decision and next move")

    @staticmethod
    def open_details(page):
        page.get_by_label("Campaign name", exact=True).evaluate(
            "field => {field.closest('details').open = true}")

    def prepare(self, page):
        from playwright.sync_api import expect
        with page.expect_response(self.base + "/api/campaigns/prepare") as reply:
            page.get_by_role("button", name="Prepare campaign brief", exact=True).click()
        assert reply.value.status == 200
        expect(page.get_by_role("region", name="Your draft report")).to_be_visible()
        return reply.value.json()

    def legacy_unchanged(self, page):
        from playwright.sync_api import expect
        saved = self.start(page, fixture("Fictional purpose — legacy stays absent"))
        before = saved["document"]
        expect(page.get_by_label("Route purpose", exact=True)).to_have_value("unknown")
        assert "purpose" not in before["opportunities"][0]
        report = self.prepare(page)
        assert "purpose" not in report["campaign"]["opportunities"][0]
        page.get_by_role("tab", name="Opportunities", exact=True).click()
        page.get_by_role("button", name="Make focused campaign…", exact=True).click()
        dialog = page.get_by_role("dialog", name="Make a focused campaign")
        dialog.get_by_label("Name for the focused campaign", exact=True).fill(
            "Fictional legacy focused preview")
        with page.expect_response(self.base + "/api/campaigns/focus") as reply:
            dialog.get_by_role("button", name="Preview selected material", exact=True).click()
        assert reply.value.status == 200
        focused = reply.value.json()["document"]
        assert "purpose" not in focused["opportunities"][0]
        assert focused["answers"] == before["answers"]
        dialog.get_by_role("button", name="Cancel", exact=True).click()
        assert self.export(page, "legacy-after-prepare-focus") == before
        assert self.store.get(saved["id"]) == saved
        self.screenshot(page, "purpose-legacy-unchanged")

    def explicit_local_next_actions(self, page):
        from playwright.sync_api import expect
        for purpose in ("discussion", "research"):
            saved = self.start(page, fixture("Fictional purpose — manual " + purpose))
            before = saved["document"]
            page.get_by_label("Route purpose", exact=True).select_option(purpose)
            card = self.card(page)
            expect(card.locator(".campaign-decision-state")).to_have_text(
                purpose.upper() + " IN PROGRESS")
            expect(card.locator(".campaign-decision-detail")).to_contain_text("recorded")
            task = card.locator(".campaign-decision-task").inner_text().strip()
            assert task and "current round" not in task and "funder" not in task
            expected = copy.deepcopy(before)
            expected["opportunities"][0]["purpose"] = purpose
            assert self.export(page, purpose + "-selected-no-auto-action") == expected
            assert self.store.get(saved["id"]) == saved
            card.get_by_role("button", name="Add suggested action", exact=True).click()
            expect(page.get_by_role("tab", name="Next actions", exact=True)).to_have_attribute(
                "aria-selected", "true")
            action = page.locator(f'[data-action-index="{len(before["actions"])}"]')
            expect(action.get_by_label("Next action", exact=True)).to_have_value(task)
            expect(action.get_by_label("Owner type", exact=True)).to_have_value("unassigned")
            expect(action.get_by_label("Owner name or role", exact=True)).to_have_value("")
            expect(action.get_by_label("Proposed target date", exact=True)).to_have_value("")
            new = {"opportunity": before["opportunities"][0]["name"],
                   "scope_confirmed": True, "submission_phase": "pre_submission",
                   "task": task, "owner": "", "owner_kind": "unassigned",
                   "owner_confirmed": False, "due": "", "status": "open"}
            expected["actions"].append(new)
            assert self.save(page)["document"] == expected
            page.reload()
            expect(page.get_by_label("Campaign name", exact=True)).to_have_value(before["title"])
            assert self.export(page, purpose + "-saved-reopened") == expected
            self.screenshot(page, "purpose-" + purpose + "-action")

    def conflicts_keep_formal_gates(self, page):
        from playwright.sync_api import expect
        for purpose, mode in [("discussion", "required"), ("research", "required"),
                              ("application", "not_required")]:
            saved = self.start(page, fixture(
                "Fictional purpose conflict — " + purpose, purpose, mode))
            card = self.card(page)
            expect(card.locator(".campaign-decision-state")).to_have_text("NOT READY")
            expect(card).to_contain_text("Reconcile the purpose and application workflow explicitly")
            expect(card.get_by_role("button", name="Add suggested action", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Create another clarification letter", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("Reconcile")
            assert page.url == self.base + "/#campaigns"
            assert self.store.get(saved["id"]) == saved
            report = self.prepare(page)
            assert report["readiness"]["purpose_workflow_conflicts"] == 1
            assert report["readiness"]["application_windows_to_check"] == 1
            assert "PRIVATE HELD ANSWER" not in json.dumps(report, ensure_ascii=False)
            page.get_by_role("tab", name="Application answers", exact=True).click()
            answer = page.get_by_role("article", name="Application answer", exact=True)
            expect(answer.get_by_label("Answer review", exact=True)).to_be_disabled()
            expect(answer.get_by_role("button", name=re.compile("^Copy unavailable"))).to_be_disabled()
            assert self.export(page, purpose + "-conflict-preserved") == saved["document"]
            self.screenshot(page, "purpose-conflict-" + purpose)

    def mixed_counts_and_scoped_clarification(self, page):
        from playwright.sync_api import expect
        document = fixture("Fictional purposes — mixed routes", "application")
        primary = document["opportunities"][0]
        document["opportunities"] += [
            {"name": "Fictional discussion route", "funder": "Fictional Discussion Contact",
             "purpose": "discussion", "status": "open", "application_mode": "unknown"},
            {"name": "Fictional research route", "funder": "Fictional Research Contact",
             "purpose": "research", "status": "open", "application_mode": "unknown"}]
        document["requirements"] = [{"opportunity": "Fictional discussion route",
            "rule": "Could you confirm the fictional discussion scope?", "status": "unknown",
            "source_id": "2" * 32, "source_url": "https://example.invalid/original",
            "source_quote": "Original discussion scope needs agreement.",
            "evidence": "No agreement is established.", "checked_at": "2019-01-01"}]
        saved = self.start(page, document)
        count = page.locator(".campaign-summary > div").filter(
            has=page.locator("span", has_text="application windows to verify"))
        expect(count.locator("strong")).to_have_text("1")
        page.locator('.campaign-opportunity[data-opportunity-index="1"]').click()
        expect(page.get_by_label("Route purpose", exact=True)).to_have_value("discussion")
        expect(self.card(page)).to_contain_text("fictional discussion scope")
        report = self.prepare(page)
        assert report["readiness"]["application_windows_to_check"] == 1
        assert report["readiness"]["requirements_unresolved"] == 1
        assert report["campaign"]["requirements"] == saved["document"]["requirements"]
        page.get_by_role("tab", name="Opportunities", exact=True).click()
        page.get_by_role("button", name="Draft clarification letter", exact=True).click()
        expect(page).to_have_url(self.base + "/#brief")
        questions = page.get_by_label("Questions you need answered", exact=True)
        expect(questions).to_be_visible()
        wording = questions.input_value()
        assert "fictional discussion scope" in wording.lower()
        assert not re.search(r"fixed or rolling|allowed to apply|official programme|application timetable",
                             wording, re.I), wording
        expect(page.get_by_label("Search the web for related material", exact=True)).not_to_be_checked()
        expect(page.get_by_label("Let the model rank a small set of source excerpts", exact=True)).not_to_be_checked()
        page.get_by_role("button", name="Prepare my draft", exact=True).click()
        report = page.get_by_role("region", name="Your draft report")
        expect(report).to_be_visible()
        expect(report).to_contain_text("Could you confirm the fictional discussion scope?")
        expect(page.locator(".workbench-page")).to_contain_text("It has not been sent")
        assert self.store.get(saved["id"]) == saved
        self.screenshot(page, "purpose-scoped-unsent-clarification")
        assert primary["purpose"] == "application"

    def history_stale_report_roundtrip(self, page):
        from playwright.sync_api import expect
        saved = self.start(page, fixture("Fictional purpose — preserve history", history=True))
        before = saved["document"]
        self.prepare(page)
        page.get_by_role("tab", name="Opportunities", exact=True).click()
        page.get_by_label("Route purpose", exact=True).select_option("research")
        expect(page.locator("#campaign-output")).to_have_attribute("data-stale", "true")
        expect(page.locator("#campaign-output .report-area")).to_have_attribute("inert", "")
        expect(self.card(page)).to_contain_text("marked not met")
        expected = copy.deepcopy(before)
        expected["opportunities"][0]["purpose"] = "research"
        assert self.save(page)["document"] == expected
        page.reload()
        expect(page.get_by_label("Route purpose", exact=True)).to_have_value("research")
        assert self.export(page, "history-saved-reopened") == expected
        page.get_by_role("button", name="Start a new campaign", exact=True).click()
        self.transfers(page)
        page.get_by_label("Import campaign backup", exact=True).set_input_files(
            self.artifacts / "history-saved-reopened.json")
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(before["title"])
        restored = self.save(page)
        assert restored["id"] != saved["id"]
        assert restored["document"] == expected
        assert self.store.get(saved["id"])["document"] == expected
        assert self.export(page, "history-restored") == expected
        self.screenshot(page, "purpose-history-restored")

    def delayed_save_blocks_suggested_action(self, page):
        from playwright.sync_api import expect
        saved = self.start(page, fixture("Fictional purpose — delayed save guard", "discussion"))
        card = self.card(page)
        suggestion = card.get_by_role("button", name="Add suggested action", exact=True)
        expect(suggestion).to_be_visible()
        pending = []
        save_url = self.base + "/api/campaigns/save"
        def hold(route):
            pending.append(route)
        page.context.route(save_url, hold)
        try:
            page.get_by_role("button", name="Save campaign", exact=True).click()
            expect(card).to_have_attribute("inert", "")
            deadline = time.monotonic() + 3
            while not pending and time.monotonic() < deadline:
                page.wait_for_timeout(20)
            assert len(pending) == 1
            assert pending[0].request.post_data_json["document"] == saved["document"]
            assert self.store.get(saved["id"]) == saved
            # A controlled DOM click deliberately bypasses native inert hit testing
            # to exercise the handler's independent busy guard. No API is mocked.
            suggestion.evaluate("button => button.click()")
            expect(page.get_by_role("tab", name="Opportunities", exact=True)).to_have_attribute(
                "aria-selected", "true")
            assert self.store.get(saved["id"]) == saved
            with page.expect_response(save_url) as reply:
                pending.pop().continue_()
            assert reply.value.status == 200
            confirmed = reply.value.json()
            expect(page.locator(".campaign-save-state")).to_have_text("Saved on this computer")
            expect(card).not_to_have_attribute("inert", "")
            assert confirmed["revision"] == saved["revision"] + 1
            assert confirmed["document"] == saved["document"]
            assert self.export(page, "delayed-save-blocked-action") == saved["document"]
            self.transport_guards.append({
                "fixture": "One actual save held before transmission; released exactly once",
                "native_inert_asserted": True, "controlled_dom_click_busy_guard": True,
                "saved_revision_increment": 1, "document_unchanged": True})
            self.screenshot(page, "purpose-delayed-save-guard")
        finally:
            for route in pending:
                route.abort()
            page.context.unroute(save_url, hold)

    def conflicting_saves_keep_local_work(self, page):
        from playwright.sync_api import expect
        saved = self.start(page, fixture("Fictional purpose — conflicting local edits"))
        second = page.context.new_page()
        try:
            second.goto(self.base + "/#campaigns")
            expect(second.get_by_label("Campaign name", exact=True)).to_have_value(saved["document"]["title"])
            self.open_details(second)
            newer_text = "Fictional newer change made through the second actual editor."
            second.get_by_label("What will this campaign make possible?", exact=True).fill(newer_text)
            newer = self.save(second)
            expected_newer = copy.deepcopy(saved["document"])
            expected_newer["objective"] = newer_text
            assert newer["document"] == expected_newer
            page.get_by_label("Route purpose", exact=True).select_option("discussion")
            self.open_details(page)
            local_text = "Fictional unsaved work must survive the rejected older revision."
            page.get_by_label("What will this campaign make possible?", exact=True).fill(local_text)
            with page.expect_response(lambda response: response.url == self.base + "/api/campaigns/save"
                                     and response.status == 400):
                page.get_by_role("button", name="Save campaign", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("Your edits are still here")
            expect(page.locator(".campaign-save-state")).to_have_text("Unsaved changes")
            expect(page.get_by_label("Route purpose", exact=True)).to_have_value("discussion")
            expect(page.get_by_label("What will this campaign make possible?", exact=True)).to_have_value(local_text)
            expected_local = copy.deepcopy(saved["document"])
            expected_local["objective"] = local_text
            expected_local["opportunities"][0]["purpose"] = "discussion"
            assert self.export(page, "conflict-retained-local-backup") == expected_local
            assert self.store.get(saved["id"]) == newer
            for item in list(self.errors):
                if (item["check"] == "purpose-conflicting-saves-retain-local-work"
                    and item.get("url") == self.base + "/api/campaigns/save"
                    and item["error"] == "Failed to load resource: the server responded with a status of 400 (Bad Request)"):
                    self.expected_console.append(item)
                    self.errors.remove(item)
            self.screenshot(page, "purpose-conflict-recovery")
        finally:
            second.close()


def main(argv=None):
    args = arguments(argv)
    from playwright.sync_api import sync_playwright
    artifacts = args.output_dir or Path(tempfile.mkdtemp(
        prefix="sinter-route-purpose-proof-", dir="/var/tmp"))
    if args.output_dir:
        artifacts.mkdir(mode=0o700)
    os.chmod(artifacts, 0o700)
    workspace = artifacts / "fictional-workspace"
    workspace.mkdir(mode=0o700)
    receipt = {"schema": "sinter-route-purpose-browser/v1", "passed": False,
        "fixture_only": True, "scope": "Offline source UI; no installed/AI/eligibility qualification",
        "fixture_date": date.today().isoformat(), "workspace": str(workspace)}
    resources = {"browser_closed": False, "server_closed": False}
    server = thread = browser = checks = None
    before = after = None
    fatal, remote_counts = [], {}
    try:
        before = source_pins()
        write_json(artifacts / "started.json", {**receipt, "source_files": before})
        write_json(artifacts / "fictional-input-example.json", fixture("Fictional retained input", history=True))
        with ExitStack() as guard:
            guards = {name: guard.enter_context(patch.object(client, name,
                side_effect=AssertionError("Forbidden hosted operation: " + name)))
                for name in ("chat", "search", "_open", "_load_key")}
            try:
                server = make_server(port=0, directory=workspace)
                thread = threading.Thread(target=server.serve_forever, daemon=True,
                    name="sinter-fictional-route-purpose-server")
                thread.start()
                with sync_playwright() as driver:
                    try:
                        browser = launch_chromium(driver, args.chromium)
                        receipt["browser_version"] = browser.version
                        checks = PurposeChecks(browser,
                            f"http://127.0.0.1:{server.server_port}", artifacts, server.app.campaigns)
                        for name, action in [
                            ("purpose-legacy-absent-unchanged", checks.legacy_unchanged),
                            ("purpose-explicit-local-discussion-research-actions", checks.explicit_local_next_actions),
                            ("purpose-required-and-application-conflicts", checks.conflicts_keep_formal_gates),
                            ("purpose-mixed-counts-scoped-unsent-clarification", checks.mixed_counts_and_scoped_clarification),
                            ("purpose-history-stale-report-save-reopen-restore", checks.history_stale_report_roundtrip),
                            ("purpose-delayed-save-blocks-suggested-action", checks.delayed_save_blocks_suggested_action),
                            ("purpose-conflicting-saves-retain-local-work", checks.conflicting_saves_keep_local_work)]:
                            checks.check(name, action)
                    finally:
                        if browser:
                            browser.close()
                            resources["browser_closed"] = True
            finally:
                remote_counts = {name: mock.call_count for name, mock in guards.items()}
                if server:
                    if thread and thread.is_alive():
                        server.shutdown()
                        thread.join(timeout=5)
                    server.app.close()
                    server.server_close()
                    resources["server_closed"] = not thread or not thread.is_alive()
    except BaseException as problem:
        fatal.append(type(problem).__name__ + ": " + str(problem))
    finally:
        try:
            after = source_pins()
        except Exception as problem:
            fatal.append("Final source pins: " + str(problem))
        for path in artifacts.rglob("*"):
            if path.is_file() and not path.is_symlink():
                os.chmod(path, 0o600)
        receipt.update({"checks": checks.results if checks else [],
            "screenshots": checks.screenshots if checks else [],
            "backups": checks.backups if checks else [],
            "fixture_inputs": checks.fixture_inputs if checks else [],
            "controlled_transport_fixtures": checks.transport_guards if checks else [],
            "page_errors": checks.errors if checks else [],
            "external_requests": checks.external if checks else [],
            "expected_conflict_console": checks.expected_console if checks else [],
            "local_responses": checks.local_responses if checks else [],
            "fatal_errors": fatal, "resources": resources,
            "hosted_operation_attempts": remote_counts,
            "model_operations_requested": sum(remote_counts.get(name, 0) for name in ("chat", "search")),
            "source_files_before": before, "source_files_after": after,
            "source_unchanged": before is not None and before == after,
            "no_automatic_replay": True})
        receipt["passed"] = (bool(checks) and len(checks.results) == 7
            and all(row["passed"] and row["context_closed"] for row in checks.results)
            and not checks.errors and not checks.external and not fatal
            and all(resources.values()) and all(value == 0 for value in remote_counts.values())
            and before is not None and before == after)
        write_json(artifacts / "browser-receipt.json", receipt)
    print(artifacts / "browser-receipt.json", flush=True)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
