"""Qualify literal campaign-source previews and local draft logging offline.

Uses a new retained fictional workspace, actual local UI and clipboard/download
controls. The malformed-link case qualifies the real renderer only, not an
accepted campaign or stored report. No model, private workspace or external
navigation is used. Root operators run browser qualification after source freeze.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import tempfile
import threading
import io
import zipfile
from xml.etree import ElementTree as ET
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import launch_chromium, require_module  # noqa: E402
from tools.campaign_route_purpose_browser import (  # noqa: E402
    PurposeChecks, fixture as campaign_fixture, source_pins, write_json,
)


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default=os.environ.get("SINTER_CHROMIUM"))
    parser.add_argument("--output-dir", type=Path, help="New private evidence directory.")
    args = parser.parse_args(argv)
    require_module(parser, "playwright.sync_api", "Playwright",
                   "python -m pip install '.[browser]'")
    if args.chromium:
        try:
            executable = Path(args.chromium).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as problem:
            parser.error("Choose an existing executable Chromium path: " + str(problem))
        if not executable.is_file() or not os.access(executable, os.X_OK):
            parser.error("Choose an existing executable Chromium path.")
        args.chromium = str(executable)
    if args.output_dir:
        args.output_dir = args.output_dir.expanduser().absolute()
        if not args.output_dir.parent.is_dir():
            parser.error("The output parent must exist.")
        if args.output_dir.exists() or args.output_dir.is_symlink():
            parser.error("Retain existing evidence and choose a new directory.")
    return args


def pins():
    result = source_pins()
    for path in [Path(__file__).resolve(), ROOT / "tests/fixtures/literal_paragraph.v1.json"]:
        raw = path.read_bytes()
        result[path.relative_to(ROOT).as_posix()] = {
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return result


def fixture(purpose="discussion"):
    title = "Fictional source preview and draft log" if purpose == "discussion" else "Fictional research source preview and draft log"
    document = campaign_fixture(title, purpose)
    route = document["opportunities"][0]["name"]
    document.update(signatory="Fictional Example Coordinator",
                    contact_details="fictional@example.invalid", communications=[])
    document["sources"][0]["title"] = "Fictional café e\u0301 🐝 <literal> " + "UnbrokenTitle" * 19
    document["sources"][0]["url"] = "https://example.invalid/" + "source-segment-" * 24
    document["sources"][1]["title"] = "Fictional older source — original wording"
    document["requirements"] = []
    for index, source in enumerate(document["sources"]):
        document["requirements"].append({
            "opportunity": route, "rule": ("Please provide the current fictional terms before we proceed."
                if index == 0 else f"Could you clarify fictional source {index + 1}?"),
            "status": "unknown", "evidence": "No commitment or approval established.",
            "source_id": source["id"], "source_url": source["url"],
            "source_quote": f"Exact fictional quote {index + 1}: café e\u0301 🐝\r\n<literal> retained.",
            "checked_at": source["checked_at"],
        })
    document["requirements"].append({
        "opportunity": route, "rule": "Could you clarify the fictional manual source?",
        "status": "unknown", "source_url": "https://example.invalid/manual",
        "source_quote": "Exact manual source wording — no approval or agreement.",
        "evidence": "Fictional manual link, no registered source ID or check date.",
    })
    return document


class PreviewChecks(PurposeChecks):
    def __init__(self, *args):
        super().__init__(*args)
        self.layouts = []
        self.content_checks = []

    def layout(self, page, links, label):
        from playwright.sync_api import expect
        rows = page.locator(".campaign-draft-source-preview li")
        expect(rows).to_have_count(len(links))
        for index, link in enumerate(links):
            row = rows.nth(index)
            title = row.locator(".campaign-draft-source-title")
            meta = row.locator(".campaign-draft-source-meta")
            assert title.text_content() == (link["title"] or link["url"] or "Untitled source")
            expect(meta).to_contain_text("Source ID: " + link["source_id"]
                if link["source_id"] else "Manual link")
            expect(meta).to_contain_text("Checked: " + link["checked_at"]
                if link["checked_at"] else "Check date not recorded")
            expect(meta).to_contain_text("user-entered")
            title_bounds, meta_bounds = title.bounding_box(), meta.bounding_box()
            assert title_bounds and meta_bounds
            assert meta_bounds["y"] >= title_bounds["y"] + title_bounds["height"] - 0.5
            anchor = title.locator("a")
            if anchor.count():
                assert anchor.get_attribute("href") == link["url"]
                assert anchor.bounding_box()["height"] >= 44 - 0.5
            assert not row.locator("literal, script").count()
        metrics = page.evaluate("""() => ({width: innerWidth, height: innerHeight,
            overflow: document.documentElement.scrollWidth - innerWidth,
            rows: [...document.querySelectorAll('.campaign-draft-source-preview li')].map(row => {
                const title = row.querySelector('.campaign-draft-source-title');
                const meta = row.querySelector('.campaign-draft-source-meta');
                const rect = row.getBoundingClientRect();
                return {left: rect.left, right: rect.right, width: rect.width,
                    title: title.textContent, metadata: meta.textContent,
                    titleWhiteSpace: getComputedStyle(title).whiteSpace,
                    metadataFontSize: getComputedStyle(meta).fontSize};
            })})""")
        assert metrics["overflow"] <= 1, metrics
        for row in metrics["rows"]:
            assert row["left"] >= 0 and row["right"] <= metrics["width"] + 1, row
            assert float(row["metadataFontSize"].removesuffix("px")) >= 14
        self.layouts.append({"label": label, **metrics})
        rows.first.scroll_into_view_if_needed()
        self.screenshot(page, label, full_page=True)

    def evidence_export(self, page, label):
        button = page.get_by_role("button", name="Download evidence pack", exact=True)
        if not button.is_visible():
            page.get_by_text("More options", exact=True).click()
        path = self.artifacts / (label + ".json")
        with page.expect_download() as pending:
            button.click()
        pending.value.save_as(path)
        os.chmod(path, 0o600)
        raw = path.read_bytes()
        self.backups.append({"file": path.name, "bytes": len(raw),
                             "sha256": hashlib.sha256(raw).hexdigest()})
        return json.loads(raw)

    def actual_draft_copy_export_log(self, page, purpose="discussion"):
        from playwright.sync_api import expect
        saved = self.start(page, fixture(purpose))
        label_prefix = "" if purpose == "discussion" else "research-"
        baseline = saved["document"]
        page.get_by_role("button", name="Draft clarification letter", exact=True).click()
        request_wording = baseline["requirements"][0]["rule"]
        assert request_wording in page.get_by_label("Questions you need answered", exact=True).input_value()
        page.get_by_role("button", name="Prepare my draft", exact=True).click()
        report = page.get_by_role("region", name="Your draft report")
        expect(report).to_be_visible()
        document = report.locator(".document-paper")
        expect(document).to_contain_text(request_wording)
        expect(document).not_to_contain_text('requirement for “Please provide')
        opening = ("We would appreciate clarification on the points below "
                   + ("before deciding on a next step for this discussion." if purpose == "discussion"
                      else "to help us check the research question and its scope."))
        expect(document).to_contain_text(opening)
        expect(document).not_to_contain_text("programme could support a defined project")
        before = self.evidence_export(page, label_prefix + "draft-before-layout")
        assert before["input_snapshot"]["campaign_route_purpose"] == purpose
        assert before["campaign_route_purpose"] == purpose
        assert opening in before["document_markdown"]
        links = before["campaign_link"]["evidence_links"]
        assert page.locator(".report-area").evaluate("""report => {
            const log = report.querySelector('.campaign-draft-log');
            return ['.report-tabs', '.document-panel', '.evidence-panel']
                .every(selector => report.querySelector(selector)
                    .compareDocumentPosition(log) & Node.DOCUMENT_POSITION_FOLLOWING);
        }""")
        assert len(links) == 3
        for index, source in enumerate(baseline["sources"]):
            link = links[index]
            assert {key: link[key] for key in ("title", "url", "source_id", "checked_at")} == {
                "title": source["title"], "url": source["url"],
                "source_id": source["id"], "checked_at": source["checked_at"]}
            assert baseline["requirements"][index]["source_quote"] in link["notes"]
        assert links[2]["source_id"] == links[2]["checked_at"] == ""
        self.layout(page, links, label_prefix + "draft-source-desktop")
        page.set_viewport_size({"width": 390, "height": 844})
        self.layout(page, links, label_prefix + "draft-source-phone")
        after = self.evidence_export(page, label_prefix + "draft-after-layout")
        assert after == before
        assert self.store.get(saved["id"]) == saved
        page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=self.base)
        page.get_by_role("button", name="Copy draft text", exact=True).click()
        expect(page.get_by_text("Copied. Ready to paste into your email or document.", exact=True)).to_be_visible()
        copied = page.evaluate("navigator.clipboard.readText()")
        assert request_wording in copied
        assert opening in copied
        assert "programme could support a defined project" not in copied
        assert "Fictional Example Coordinator" in copied
        assert "<literal>" not in copied  # Source quotations are evidence, not letter prose.
        with page.expect_response(self.base + "/api/campaigns/save") as pending:
            page.get_by_role("button", name="Save draft to campaign log", exact=True).click()
        assert pending.value.status == 200
        logged = pending.value.json()
        expect(page.get_by_role("button", name="Saved as a draft · not sent", exact=True)).to_be_disabled()
        expected = copy.deepcopy(baseline)
        communication = logged["document"]["communications"][-1]
        assert communication["content"] == copied.strip()
        assert communication["evidence_links"] == links
        assert communication["direction"] == "outgoing" and communication["status"] == "draft"
        assert communication["date"] == "" and communication["opportunity"] == baseline["opportunities"][0]["name"]
        expected["communications"].append(communication)
        assert logged["document"] == expected
        assert self.store.get(saved["id"]) == logged
        self.goto(page, "campaigns")
        assert self.export(page, label_prefix + "campaign-after-source-draft-log") == expected
        self.content_checks.append({"purpose": purpose, "actual_draft_question_visible": True,
            "explicit_request_preserved_in_form_draft_copy_and_log": True,
            "explicit_purpose_opening_visible_copied_and_logged": True,
            "copy_matches_complete_logged_letter": True,
            "evidence_quotes_and_links_exact": True, "original_campaign_unchanged_except_one_unsent_draft": True})

    def followup_opening_recovery(self, page):
        from playwright.sync_api import expect
        saved = self.start(page, fixture())
        baseline = saved["document"]
        page.get_by_role("button", name="Draft clarification letter", exact=True).click()
        opening = "I'm following up on our recorded enquiry. Café e\u0301 🐝.\nNo submission or approval is confirmed."
        control = page.get_by_label("Opening paragraph for the recipient", exact=True)
        control.fill(opening)
        page.locator("summary").filter(has_text="Internal notes and evidence context").click()
        page.get_by_label("Internal notes and evidence context", exact=True).fill("PRIVATE_FOLLOWUP_NOTE_SENTINEL")
        page.get_by_role("button", name="Prepare my draft", exact=True).click()
        report = page.get_by_role("region", name="Your draft report")
        document = report.locator(".document-paper")
        opening_paragraph = document.locator("p").filter(has_text=opening.splitlines()[0])
        expect(opening_paragraph).to_be_visible()
        # textContent omits <br>; verify the line breaks a person actually sees.
        assert opening_paragraph.inner_text() == opening
        expect(document).not_to_contain_text("PRIVATE_FOLLOWUP_NOTE_SENTINEL")
        original = self.evidence_export(page, "followup-original")
        assert original["document_opening"] == original["input_snapshot"]["opening_paragraph"] == opening
        assert any(row["content"] == "PRIVATE_FOLLOWUP_NOTE_SENTINEL" for row in original["sources"])
        page.get_by_role("button", name="Edit draft", exact=True).click()
        edited = original["document_markdown"] + "\n\nHuman correction: keep this as an unsent enquiry."
        page.get_by_label("Edit your draft", exact=True).fill(edited)
        page.get_by_role("button", name="Apply edits", exact=True).click()
        prepared = self.evidence_export(page, "followup-edited")
        assert prepared["document_markdown"] == original["document_markdown"]
        assert prepared["document_edits"]["markdown"] == edited
        page.get_by_text("Review or edit project inputs", exact=True).click()
        control.fill("🐝" * 1200)
        assert control.input_value() == "🐝" * 1200 and control.evaluate("node => node.validity.valid")
        expect(page.get_by_text("1,200 / 1,200 characters", exact=True)).to_be_visible()
        oversized = "🐝" * 1201
        control.fill(oversized)
        assert control.input_value() == oversized and not control.evaluate("node => node.validity.valid")
        before_requests = sum(row["path"] == "/api/workbench" for row in self.local_responses)
        page.get_by_role("button", name="Prepare my draft", exact=True).click()
        assert sum(row["path"] == "/api/workbench" for row in self.local_responses) == before_requests
        assert self.evidence_export(page, "followup-invalid-retained") == prepared
        changed = "A changed opening for the next preparation. No commitment is established."
        control.fill(changed)
        stale = page.get_by_text("The draft below uses earlier inputs.", exact=False)
        expect(stale).to_be_visible()
        page.get_by_label("What are you preparing?", exact=True).select_option("agenda")
        expect(page.get_by_label("Purpose paragraph for this agenda", exact=True)).to_have_value(changed)
        expect(page.get_by_text("Optional. Used as the agenda’s purpose.", exact=False)).to_be_visible()
        page.get_by_label("What are you preparing?", exact=True).select_option("enquiry")
        # Explicitly injected failed local job: no work reaches the server and
        # no hosted operation is replayed. The earlier successful basis stays.
        failed_id = "f" * 32
        posts, polls = [], []
        def reject_job(route):
            posts.append(route.request.post_data_json)
            route.fulfill(status=200, json={"id": failed_id})
        def failed_job(route):
            polls.append(route.request.url)
            route.fulfill(status=200, json={"id": failed_id, "status": "failed",
                                          "error": "Fictional local preparation unavailable."})
        page.route(self.base + "/api/workbench", reject_job)
        page.route(self.base + "/api/jobs/" + failed_id, failed_job)
        try:
            page.get_by_role("button", name="Prepare my draft", exact=True).click()
            page.get_by_role("dialog", name="Prepare another draft?", exact=True).get_by_role(
                "button", name="Keep edits and prepare", exact=True).click()
            expect(page.get_by_text("Not completed. Your inputs and previous report are unchanged.", exact=True)).to_be_visible()
        finally:
            page.unroute(self.base + "/api/workbench", reject_job)
            page.unroute(self.base + "/api/jobs/" + failed_id, failed_job)
        assert len(posts) == len(polls) == 1 and posts[0]["opening_paragraph"] == changed
        assert control.input_value() == changed
        expect(stale).to_be_visible()
        assert self.evidence_export(page, "followup-failure-retained") == prepared
        control.fill(opening)
        expect(stale).to_be_hidden()  # Failure did not replace the successful basis.
        page.set_viewport_size({"width": 390, "height": 844})
        self.screenshot(page, "followup-inputs-phone", full_page=True)
        page.get_by_role("button", name="Save to My workspace", exact=True).click()
        expect(page.get_by_text("Saved in My workspace, including your edits and original evidence.", exact=True)).to_be_visible()
        page.reload()
        self.goto(page, "library")
        card = page.locator("article.card").filter(has=page.get_by_role("heading", name=original["title"], exact=True))
        card.get_by_role("button", name="Open draft", exact=True).click()
        reopened = self.evidence_export(page, "followup-reopened")
        assert reopened == prepared
        page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=self.base)
        page.get_by_role("button", name="Copy draft text", exact=True).click()
        expect(page.get_by_text("Copied. Ready to paste into your email or document.", exact=True)).to_be_visible()
        copied = page.evaluate("navigator.clipboard.readText()")
        assert opening in copied and "Human correction:" in copied and "PRIVATE_FOLLOWUP_NOTE_SENTINEL" not in copied
        with page.expect_response(self.base + "/api/campaigns/save") as pending:
            page.get_by_role("button", name="Save draft to campaign log", exact=True).click()
        assert pending.value.status == 200
        logged = pending.value.json()
        expected = copy.deepcopy(baseline)
        communication = logged["document"]["communications"][-1]
        assert communication["content"] == copied.strip() and communication["status"] == "draft"
        assert communication["date"] == "" and communication["evidence_links"] == prepared["campaign_link"]["evidence_links"]
        expected["communications"].append(communication)
        assert logged["document"] == expected
        self.goto(page, "campaigns")
        assert self.export(page, "followup-campaign-after-log") == expected
        self.content_checks.append({"scope": "Actual opening/edit/save/browser-reload/reopen/export/copy/log; injected local failed job only",
            "raw_opening_retained": True, "internal_notes_not_in_letter": True,
            "oversized_unicode_retained_without_request": True, "failed_job_not_replayed": True,
            "successful_input_basis_unchanged_after_failure": True, "original_and_edits_distinct": True,
            "campaign_changes_exactly_one_unsent_log": True})

    def draft_replacement_recovery(self, page):
        """Actual draft controls; two explicitly delayed fictional completions."""
        from playwright.sync_api import expect
        baseline = self.start(page, fixture())["document"]
        page.get_by_role("button", name="Draft clarification letter", exact=True).click()
        first_opening = "This fictional enquiry seeks clarification, not approval."
        opening = page.get_by_label("Opening paragraph for the recipient", exact=True)
        opening.fill(first_opening)
        prepare = page.get_by_role("button", name="Prepare my draft", exact=True)
        prepare.click()
        report = page.get_by_role("region", name="Your draft report", exact=True)
        nav = page.get_by_role("region", name="Workbench drafts", exact=True)
        picker = nav.locator(".draft-switcher-disclosure")
        expect(report).to_have_count(1)
        first = self.evidence_export(page, "replacement-original-a")
        page.get_by_role("button", name="Edit draft", exact=True).click()
        applied = first["document_markdown"] + "\n\nHuman wording that must remain available."
        editor = page.get_by_label("Edit your draft", exact=True)
        editor.fill(applied)
        save = report.get_by_role("button", name="Save to My workspace", exact=True)
        expect(save).to_be_disabled()
        expect(report.get_by_role("status", name="Document save state", exact=True)).to_contain_text(
            "Apply or cancel the text in the editor before saving.")
        page.get_by_role("button", name="Apply edits", exact=True).click()
        expect(save).to_be_enabled()
        first_edited = self.evidence_export(page, "replacement-applied-a")
        page.get_by_text("Review or edit project inputs", exact=True).click()
        next_opening = "A separate fictional follow-up with a different opening."
        opening.fill(next_opening)
        attempts = []
        page.on("request", lambda request: attempts.append(request.url)
                if request.method == "POST" and request.url == self.base + "/api/workbench" else None)
        prepare.scroll_into_view_if_needed()
        before_cancel = page.evaluate("({x:scrollX,y:scrollY})")
        prepare.click()
        decision = page.get_by_role("dialog", name="Prepare another draft?", exact=True)
        expect(decision).to_be_visible()
        page.keyboard.press("Escape")
        expect(decision).to_have_count(0)
        expect(prepare).to_be_focused()
        after_cancel = page.evaluate("({x:scrollX,y:scrollY})")
        assert abs(after_cancel["x"] - before_cancel["x"]) <= 1
        assert abs(after_cancel["y"] - before_cancel["y"]) <= 1
        assert attempts == []
        assert self.evidence_export(page, "replacement-cancel-keeps-a") == first_edited

        # Each click starts one separately authorised fictional completion.
        # Editing while each result is pending must retain both outside Drafts.
        delayed_id = "e" * 32
        released = {"value": False}
        posts, polls = [], []
        completed = copy.deepcopy(first)
        completed.update(id="d" * 32, document_opening=next_opening,
                         document_markdown=first["document_markdown"].replace(first_opening, next_opening))
        completed.pop("document_edits", None)

        def delayed_start(route):
            posts.append(route.request.post_data_json)
            route.fulfill(status=200, json={"id": delayed_id})

        def delayed_result(route):
            polls.append(route.request.url)
            route.fulfill(status=200, json={"id": delayed_id,
                "status": "done" if released["value"] else "running",
                "message": "Fictional replacement held for the edit check.",
                **({"result": completed} if released["value"] else {})})

        page.route(self.base + "/api/workbench", delayed_start)
        page.route(self.base + "/api/jobs/" + delayed_id, delayed_result)
        try:
            prepare.click()
            decision.get_by_role("button", name="Keep edits and prepare", exact=True).click()
            expect(page.get_by_text("Fictional replacement held for the edit check.", exact=True)).to_be_visible()
            page.get_by_role("button", name="Edit draft", exact=True).click()
            pending = applied + "\n\nUnapplied last keystrokes while preparation runs."
            editor.fill(pending)
            released["value"] = True
            ready_b = nav.get_by_role("button", name="Open prepared draft 2", exact=True)
            expect(ready_b).to_be_enabled()
            expect(nav.locator(".draft-switcher-current")).to_have_text("Draft 1 · Text waiting to apply")
            picker.locator("summary").click()
            row_b = nav.get_by_role("button", name="Open draft 2", exact=True)
            old_row = row_b.element_handle()

            third_opening = "A third fictional draft, still requiring a separate decision."
            opening.fill(third_opening)
            completed = copy.deepcopy(first)
            completed.update(id="c" * 32, document_opening=third_opening,
                document_markdown=first["document_markdown"].replace(first_opening, third_opening))
            completed.pop("document_edits", None)
            released["value"] = False
            prepare.click()
            decision.get_by_role("button", name="Keep edits and prepare", exact=True).click()
            expect(page.get_by_text("Fictional replacement held for the edit check.", exact=True)).to_be_visible()
            pending += "\n\nAnother exact edit while the third draft is prepared."
            editor.fill(pending)
            assert row_b.evaluate("(node, previous) => node === previous", old_row)
            expect(picker).to_have_attribute("open", "")
            released["value"] = True
            ready_c = nav.get_by_role("button", name="Open prepared draft 3", exact=True)
            expect(ready_c).to_be_enabled()
            expect(ready_b).to_be_enabled()
            expect(picker).to_have_attribute("open", "")
        finally:
            page.unroute(self.base + "/api/workbench", delayed_start)
            page.unroute(self.base + "/api/jobs/" + delayed_id, delayed_result)
        assert len(posts) == len(attempts) == 2
        assert [row["opening_paragraph"] for row in posts] == [next_opening, third_opening]
        assert polls
        expect(editor).to_have_value(pending)
        expect(nav).to_contain_text("Unsaved work is kept only in this open page.")
        ready_b.scroll_into_view_if_needed()
        before_cancel = page.evaluate("({x:scrollX,y:scrollY})")
        ready_b.click()
        open_b = page.get_by_role("dialog", name="Open draft 2?", exact=True)
        expect(open_b).to_be_visible()
        open_b.get_by_role("button", name="Keep editing", exact=True).click()
        expect(editor).to_have_value(pending)
        expect(ready_b).to_be_focused()
        expect(picker).to_have_attribute("open", "")
        after_cancel = page.evaluate("({x:scrollX,y:scrollY})")
        assert abs(after_cancel["x"] - before_cancel["x"]) <= 1
        assert abs(after_cancel["y"] - before_cancel["y"]) <= 1
        ready_b.click()
        open_b.get_by_role("button", name="Open draft 2", exact=True).click()
        expect(nav.locator(".draft-switcher-current")).to_have_text("Draft 2 · Not saved")
        expect(picker).not_to_have_attribute("open", "")
        expect(report.locator(".report-heading h2")).to_be_focused()
        expect(ready_c).to_be_visible()
        second = self.evidence_export(page, "replacement-completed-b")
        assert second["input_snapshot"]["opening_paragraph"] == next_opening
        assert second["sources"] == first["sources"]
        picker.locator("summary").click()
        nav.get_by_role("button", name="Open draft 1", exact=True).click()
        expect(page.get_by_role("dialog")).to_have_count(0)
        expect(editor).to_have_value(pending)
        expect(report.locator(".report-heading h2")).to_be_focused()
        stale = page.get_by_text("The draft below uses earlier inputs.", exact=False)
        expect(stale).to_be_visible()
        page.get_by_text("Review or edit project inputs", exact=True).click()
        opening.fill(first_opening)
        expect(stale).to_be_hidden()

        page.get_by_text("Review or edit project inputs", exact=True).click()

        # Full text stays in the bounded-height phone editor. Tab reaches the
        # actual Apply and Cancel controls in logical order.
        page.set_viewport_size({"width": 390, "height": 844})
        editor.focus()
        page.keyboard.press("Tab")
        apply = page.get_by_role("button", name="Apply edits", exact=True)
        expect(apply).to_be_focused()
        page.keyboard.press("Tab")
        expect(page.get_by_role("button", name="Cancel edits", exact=True)).to_be_focused()
        apply.scroll_into_view_if_needed()
        geometry = apply.evaluate("""node => {
            const r=node.getBoundingClientRect(), hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
            return {width:r.width,height:r.height,hit:!!hit&&(hit===node||node.contains(hit)),
                overflow:document.documentElement.scrollWidth-innerWidth};
        }""")
        assert geometry["width"] >= 44 and geometry["height"] >= 44 and geometry["hit"]
        assert geometry["overflow"] <= 1
        self.layouts.append({"label": "replacement-phone-apply", **geometry})
        self.screenshot(page, "replacement-phone-editor", full_page=True)
        apply.click()
        recovered = self.evidence_export(page, "replacement-recovered-a")
        assert recovered["document_markdown"] == first["document_markdown"]
        assert recovered["document_edits"]["markdown"] == pending
        assert recovered["input_snapshot"] == first["input_snapshot"]
        assert recovered["sources"] == first["sources"]
        save.click()
        state = report.get_by_role("status", name="Document save state", exact=True)
        expect(state).to_have_attribute("data-state", "saved")
        expect(nav.locator(".draft-switcher-current")).to_have_text("Draft 1 · Saved locally")
        picker.locator("summary").click()
        nav.get_by_role("button", name="Open draft 2", exact=True).click()
        expect(page.get_by_role("dialog")).to_have_count(0)
        expect(nav.locator(".draft-switcher-current")).to_have_text("Draft 2 · Not saved")

        # Delay only a real local-save acknowledgement. Its exact HTTP 201 is
        # fulfilled once, without another write; disclosure and focus stay put.
        held = []

        def hold_save_reply(route):
            response = route.fetch()
            held.append({"route": route, "response": response, "fulfilled": False})

        page.route(self.base + "/api/reports", hold_save_reply)
        try:
            save.click()
            expect(state).to_have_attribute("data-state", "saving")
            for _ in range(500):
                if held:
                    break
                page.wait_for_timeout(20)
            assert len(held) == 1, f"Expected one held save response, observed {len(held)}"
            assert held[0]["response"].status == 201, (
                "Report creation must return 201; observed "
                + str(held[0]["response"].status)
            )
            picker.locator("summary").click()
            saved_a = nav.get_by_role("button", name="Open draft 1", exact=True)
            saved_a.focus()
            saved_a_node = saved_a.element_handle()
            held[0]["route"].fulfill(response=held[0]["response"])
            held[0]["fulfilled"] = True
            expect(state).to_have_attribute("data-state", "saved")
            expect(saved_a).to_be_focused()
            expect(picker).to_have_attribute("open", "")
            assert saved_a.evaluate("(node, previous) => node === previous", saved_a_node)
            expect(nav.locator(".draft-switcher-current")).to_have_text("Draft 2 · Saved locally")
            expect(ready_c).to_be_visible()
        finally:
            for row in held:
                if not row["fulfilled"]:
                    row["route"].fulfill(response=row["response"])
            page.unroute(self.base + "/api/reports", hold_save_reply)
        assert len(attempts) == 2  # Switching and saving do not prepare again.
        self.screenshot(page, "replacement-saved-phone", full_page=True)
        self.goto(page, "campaigns")
        assert self.export(page, "replacement-campaign-unchanged") == baseline
        self.content_checks.append({"scope": "Actual draft controls plus two delayed fictional completions and one delayed real-save acknowledgement",
            "cancel_no_request_focus_and_scroll_preserved": True,
            "applied_and_pending_edits_retained": True,
            "both_deferred_results_visible_outside_disclosure": True,
            "keyed_nodes_and_disclosure_retained_on_edit_and_save": True,
            "successful_switch_focuses_new_heading": True,
            "pending_text_blocks_save_with_visible_instruction": True,
            "phone_editor_tab_order_and_apply_target": True,
            "specific_a_b_a_recovery": True,
            "each_input_basis_and_sources_preserved": True,
            "two_explicit_preparations_no_replay": True,
            "separate_drafts_saved_with_independent_states": True,
            "canonical_fixture_campaign_unchanged": True})

    def meeting_correction_input_basis(self, page):
        """A reviewed fictional correction adopts only that result's basis."""
        from playwright.sync_api import expect
        self.goto(page, "meeting")
        page.get_by_label("Project name", exact=True).fill("Fictional quote discussion")
        transcript = "Alex: We agreed to request a coat; no purchase was approved.\nSam: I will ask for the written estimate."
        page.get_by_label("Transcript", exact=True).fill(transcript)
        page.get_by_role("button", name="Prepare my draft", exact=True).click()
        report = page.get_by_role("region", name="Your draft report", exact=True)
        expect(report).to_have_count(1)
        first = self.evidence_export(page, "correction-original-basis")
        page.get_by_text("Make a traceable transcript correction", exact=True).click()
        replacement = "We agreed to request a quote; no purchase was approved."
        page.get_by_label("Reviewed replacement", exact=True).fill(replacement)
        page.get_by_label("Why is this correction justified?", exact=True).fill(
            "Fictional regression: the operator confirmed quote, not coat.")
        # Corrupt one local request deliberately: rejection must remain visible
        # beside the correction, without changing the report or replaying it.
        rejected = []

        def mismatched_pin(route):
            body = route.request.post_data_json
            body["transcript_source"]["id"] = "S" + "0" * 16
            rejected.append(body)
            route.continue_(post_data=json.dumps(body))

        page.route("**/api/workbench", mismatched_pin)
        try:
            page.get_by_role("button", name="Apply reviewed correction", exact=True).click()
            panel = page.get_by_text("Make a traceable transcript correction", exact=True).locator("..")
            expect(panel.get_by_role("alert")).to_contain_text("no longer matches the original notes")
            expect(page.get_by_label("Reviewed replacement", exact=True)).to_have_value(replacement)
            expect(page.get_by_label("Why is this correction justified?", exact=True)).to_have_value(
                "Fictional regression: the operator confirmed quote, not coat.")
            unchanged = self.evidence_export(page, "correction-rejected-basis")
            for key in ("sources", "input_snapshot", "segments", "corrections", "document_markdown"):
                assert unchanged[key] == first[key], "Rejected correction changed " + key
            assert len(rejected) == 1, "The rejected request was automatically replayed"
        finally:
            page.unroute("**/api/workbench", mismatched_pin)
        # The next click is an explicit retry of a known rejected request.
        page.get_by_role("button", name="Apply reviewed correction", exact=True).click()
        expect(page.get_by_role("dialog", name="Prepare another draft?", exact=True)).to_have_count(0)
        nav = page.get_by_role("region", name="Workbench drafts", exact=True)
        expect(nav.locator(".draft-switcher-current")).to_have_text("Draft 2 · Not saved")
        corrected = self.evidence_export(page, "correction-reviewed-basis")
        assert corrected["input_snapshot"]["notes"] == transcript, "Correction changed raw transcript input"
        assert corrected["input_snapshot"]["corrections"][0]["replacement"] == replacement, "Reviewed correction missing"
        assert corrected["sources"] == first["sources"], "Correction changed original transcript source snapshot"
        stale = page.get_by_text("The draft below uses earlier inputs.", exact=False)
        expect(stale).to_be_hidden()
        nav.locator(".draft-switcher-disclosure > summary").click()
        nav.get_by_role("button", name="Open draft 1", exact=True).click()
        expect(stale).to_be_hidden()
        recovered = self.evidence_export(page, "correction-recovered-basis")
        assert recovered["input_snapshot"] == first["input_snapshot"], "Recovery changed original preparation inputs"
        assert recovered["sources"] == first["sources"], "Recovery changed original transcript source snapshot"
        self.content_checks.append({"scope": "Fictional meeting correction through the actual interface",
            "synthetic_source_mismatch_visible_and_original_retained": True,
            "rejected_request_not_replayed": True,
            "explicit_correction_adopts_its_own_basis": True,
            "no_false_stale_notice_after_correction_or_recovery": True,
            "original_transcript_and_sources_retained": True})

    def literal_opening_copy_and_word(self, page):
        from playwright.sync_api import expect
        saved = self.start(page, fixture("research"))
        page.get_by_role("button", name="Draft clarification letter", exact=True).click()
        cases = json.loads((ROOT / "tests/fixtures/literal_paragraph.v1.json").read_text(encoding="utf-8"))["cases"]
        raw = "\n".join(row[0] for row in cases)
        page.get_by_label("Opening paragraph for the recipient", exact=True).fill(raw)
        page.get_by_role("button", name="Prepare my draft", exact=True).click()
        paragraph = page.locator(".document-paper p").filter(has_text="Following up: café")
        expect(paragraph).to_be_visible()
        assert paragraph.inner_text() == raw
        assert paragraph.locator("a,code,strong,em,script,hr").count() == 0
        assert paragraph.locator("br").count() == len(cases) - 1
        original = self.evidence_export(page, "literal-opening-evidence")
        assert original["document_opening"] == original["input_snapshot"]["opening_paragraph"] == raw
        page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=self.base)
        page.get_by_role("button", name="Copy draft text", exact=True).click()
        expect(page.get_by_text("Copied. Ready to paste into your email or document.", exact=True)).to_be_visible()
        assert raw in page.evaluate("navigator.clipboard.readText()")
        path = self.artifacts / "literal-opening.docx"
        with page.expect_download() as pending:
            page.get_by_role("button", name="Download Word (.docx)", exact=True).click()
        pending.value.save_as(path)
        with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        exported = "".join((node.text or "") if node.tag == ns + "t" else "\n" if node.tag == ns + "br" else ""
                           for node in document.iter())
        assert raw in exported
        assert self.store.get(saved["id"]) == saved
        self.screenshot(page, "literal-opening-visible", full_page=True)
        self.content_checks.append({"scope": "Actual plain opening through HTML/copy/Word export",
            "raw_unicode_and_line_breaks_exact": True, "markup_not_interpreted": True,
            "canonical_campaign_unchanged": True})

    def unsafe_or_missing_link_retains_title(self, page):
        self.goto(page, "brief")
        links = [{"title": "Exact unsafe title café e\u0301 🐝 <literal>",
                  "url": "javascript:alert('fictional')", "source_id": "a" * 32,
                  "checked_at": "2019-01-01", "notes": "Original quote remains unchanged."},
                 {"title": "Exact missing-URL title <literal>", "url": "",
                  "source_id": "", "checked_at": "", "notes": "Original manual note."}]
        report = {"workflow": "brief", "title": "Fictional renderer boundary only",
                  "markdown": "# Fictional renderer boundary\n\nNot a stored campaign.",
                  "sources": [], "campaign_link": {"id": "f" * 32, "revision": 1,
                      "dirty": False, "opportunity": "Fictional route", "evidence_links": links}}
        result = page.evaluate("""async report => {
            const before = JSON.stringify(report);
            const {renderReport} = await import('/static/reports.js');
            document.getElementById('view').replaceChildren(renderReport(report));
            return {before, after: JSON.stringify(report)};
        }""", report)
        assert result["before"] == result["after"]
        assert page.locator(".campaign-draft-source-title a").count() == 0
        assert page.locator(".campaign-draft-source-meta").all_text_contents() == [
            "Source ID: " + "a" * 32 + " · Checked: 2019-01-01 · user-entered · No valid external link supplied",
            "Manual link · Check date not recorded · user-entered · No valid external link supplied"]
        self.layout(page, links, "renderer-link-boundaries-desktop")
        page.set_viewport_size({"width": 390, "height": 844})
        self.layout(page, links, "renderer-link-boundaries-phone")
        self.content_checks.append({"scope": "Renderer-only malformed/blank URL fixture; no save or navigation",
                                    "exact_titles_retained": True, "report_unmutated": True, "unsafe_anchors": 0})


def main(argv=None):
    args = arguments(argv)
    from playwright.sync_api import sync_playwright
    artifacts = args.output_dir or Path(tempfile.mkdtemp(prefix="sinter-source-preview-proof-", dir="/var/tmp"))
    if args.output_dir:
        artifacts.mkdir(mode=0o700)
    os.chmod(artifacts, 0o700)
    workspace = artifacts / "fictional-workspace"
    workspace.mkdir(mode=0o700)
    receipt = {"schema": "sinter-report-source-preview-browser/v1", "passed": False,
               "fictional_only": True, "workspace": str(workspace),
               "scope": "Actual offline draft/copy/export/log plus explicitly renderer-only unsafe-link boundary"}
    server = thread = browser = checks = before = after = None
    resources = {"browser_closed": False, "server_closed": False}
    fatal, counts = [], {}
    try:
        before = pins()
        write_json(artifacts / "started.json", {**receipt, "source_files": before})
        with ExitStack() as stack:
            guards = {name: stack.enter_context(patch.object(client, name,
                side_effect=AssertionError("Forbidden hosted operation: " + name)))
                for name in ("chat", "search", "_open", "_load_key")}
            try:
                server = make_server(port=0, directory=workspace)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                with sync_playwright() as driver:
                    try:
                        browser = launch_chromium(driver, args.chromium)
                        receipt["browser_version"] = browser.version
                        checks = PreviewChecks(browser, f"http://127.0.0.1:{server.server_port}", artifacts, server.app.campaigns)
                        checks.check("actual-local-draft-copy-export-log", checks.actual_draft_copy_export_log)
                        checks.check("actual-research-draft-copy-export-log",
                                     lambda page: checks.actual_draft_copy_export_log(page, "research"))
                        checks.check("followup-opening-recovery", checks.followup_opening_recovery)
                        checks.check("literal-opening-copy-word", checks.literal_opening_copy_and_word)
                        checks.check("draft-replacement-recovery", checks.draft_replacement_recovery)
                        checks.check("meeting-correction-input-basis", checks.meeting_correction_input_basis)
                        checks.check("renderer-only-unsafe-and-missing-link", checks.unsafe_or_missing_link_retains_title)
                    finally:
                        if browser:
                            browser.close()
                            resources["browser_closed"] = True
            finally:
                counts = {name: mock.call_count for name, mock in guards.items()}
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
            after = pins()
        except Exception as problem:
            fatal.append("Final source pins: " + str(problem))
        for path in artifacts.rglob("*"):
            if path.is_file() and not path.is_symlink():
                os.chmod(path, 0o600)
        receipt.update({"checks": checks.results if checks else [], "layouts": checks.layouts if checks else [],
            "content_checks": checks.content_checks if checks else [], "screenshots": checks.screenshots if checks else [],
            "backups": checks.backups if checks else [], "fixture_inputs": checks.fixture_inputs if checks else [],
            "page_errors": checks.errors if checks else [], "external_requests": checks.external if checks else [],
            "local_responses": checks.local_responses if checks else [], "fatal_errors": fatal, "resources": resources,
            "hosted_operation_attempts": counts, "model_operations_requested": sum(counts.get(n, 0) for n in ("chat", "search")),
            "source_files_before": before, "source_files_after": after, "source_unchanged": before is not None and before == after})
        receipt["passed"] = (bool(checks) and len(checks.results) == 7
            and all(row["passed"] and row["context_closed"] for row in checks.results)
            and not checks.errors and not checks.external and not fatal and all(resources.values())
            and all(value == 0 for value in counts.values()) and before is not None and before == after)
        write_json(artifacts / "browser-receipt.json", receipt)
    for row in receipt["checks"]:
        if not row["passed"]:
            print(f"FAIL DETAIL ({row['check']}): {row.get('error', 'No diagnostic recorded')[:3000]}", flush=True)
    print(artifacts / "browser-receipt.json", flush=True)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
