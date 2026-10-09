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
    path = Path(__file__).resolve()
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
            "opportunity": route, "rule": f"Could you clarify fictional source {index + 1}?",
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
        page.get_by_role("button", name="Prepare my draft", exact=True).click()
        report = page.get_by_role("region", name="Your draft report")
        expect(report).to_be_visible()
        document = report.locator(".document-paper")
        expect(document).to_contain_text("Could you clarify fictional source 1?")
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
        assert "Could you clarify fictional source 1?" in copied
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
            "explicit_purpose_opening_visible_copied_and_logged": True,
            "copy_matches_complete_logged_letter": True,
            "evidence_quotes_and_links_exact": True, "original_campaign_unchanged_except_one_unsent_draft": True})

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
        receipt["passed"] = (bool(checks) and len(checks.results) == 3
            and all(row["passed"] and row["context_closed"] for row in checks.results)
            and not checks.errors and not checks.external and not fatal and all(resources.values())
            and all(value == 0 for value in counts.values()) and before is not None and before == after)
        write_json(artifacts / "browser-receipt.json", receipt)
    print(artifacts / "browser-receipt.json", flush=True)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
