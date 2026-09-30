"""Fictional offline proof that exports never omit pending editor wording."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402


def word_text(path: Path) -> str:
    """Read the wording from an actual downloaded Word document."""
    with zipfile.ZipFile(path) as archive:
        tree = ElementTree.fromstring(archive.read("word/document.xml"))
    return "\n".join(
        "".join(node.itertext())
        for node in tree.findall(
            ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
        )
    )


def main(argv: list[str] | None = None) -> None:
    """Run real export controls in a fresh fictional local workspace."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-document-export-proof-"))
    checks, errors, external, downloads, word_requests = [], [], [], [], []
    campaign_requests = []
    resources = {"browser_closed": False, "server_closed": False}
    source_paths = (
        "src/sinter/web/documents.js",
        "src/sinter/web/reports.js",
        "src/sinter/web/report-drafts.js",
        "src/sinter/web/campaign-letter.js",
    )
    source_hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in source_paths
    }
    receipt = {"passed": False}

    def open_options(report):
        menu = report.locator(".export-menu")
        if not menu.evaluate("element => element.open"):
            menu.locator("summary").click()

    def download(page, report, name, filename):
        if "Word" not in name:
            open_options(report)
        with page.expect_download() as received:
            report.get_by_role("button", name=name, exact=True).click()
        path = artifacts / filename
        received.value.save_as(path)
        return path

    def blocked_exports(page, report, editor_label, controls, pending):
        page.evaluate("navigator.clipboard.writeText('Fictional clipboard sentinel')")
        paper = report.locator(".document-paper").inner_text()
        before = (len(downloads), len(word_requests))
        print_before = page.evaluate("window.fictionalPrintCalls")
        for name in controls:
            if name not in controls[:2]:
                open_options(report)
            report.get_by_role("button", name=name, exact=True).click()
            expect(
                report.locator(".document-feedback").get_by_role("alert")
            ).to_contain_text("Apply or cancel")
            editor = report.get_by_label(editor_label, exact=True)
            expect(editor).to_have_value(pending)
            expect(editor).to_be_focused()
            assert report.locator(".document-paper").inner_text() == paper
            assert (len(downloads), len(word_requests)) == before
            assert page.evaluate("window.fictionalPrintCalls") == print_before
            assert page.evaluate("navigator.clipboard.readText()") == (
                "Fictional clipboard sentinel"
            )

    def campaign_letter_log(page, server, base, choice):
        """Exercise pending edits through the real campaign clarification flow."""
        title = "Fictional pending campaign letter " + choice
        route = "Fictional clarification route"
        source_id = "e" * 32
        before = server.app.campaigns.save(
            {
                "title": title,
                "organisation": "Fictional community association",
                "opportunities": [
                    {
                        "name": route,
                        "funder": "Fictional programme team",
                        "url": "https://example.invalid/route",
                        "status": "clarification",
                    }
                ],
                "sources": [
                    {
                        "id": source_id,
                        "title": "Fictional retained programme notes",
                        "url": "https://example.invalid/notes",
                        "checked_at": "2026-09-29",
                        "notes": "No cash is committed. Permission is unknown.",
                    }
                ],
                "requirements": [
                    {
                        "opportunity": route,
                        "rule": "Cash contribution requirements",
                        "status": "unknown",
                        "source_id": source_id,
                        "source_url": "https://example.invalid/notes",
                        "source_quote": "No cash is committed.",
                        "checked_at": "2026-09-29",
                    }
                ],
                "actions": [
                    {
                        "task": "Confirm the quote before deciding",
                        "opportunity": route,
                        "owner": "",
                        "due": "",
                        "status": "open",
                    }
                ],
                "communications": [
                    {
                        "opportunity": route,
                        "date": "2026-09-29",
                        "direction": "incoming",
                        "status": "received",
                        "channel": "email",
                        "subject": "Fictional historical clarification",
                        "content": "A quote is pending; no approval is recorded.",
                    }
                ],
            }
        )
        page.goto(base + "/#campaigns")
        expect(page.locator(".campaign-save-bar")).to_be_visible()
        page.locator(".campaign-saved-item").filter(has_text=title).get_by_role(
            "button"
        ).click()
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(title)
        expect(
            page.get_by_role("button", name="Save campaign", exact=True)
        ).to_be_enabled()
        page.get_by_role("tab", name="Opportunities", exact=True).click()
        page.get_by_role(
            "button", name="Draft clarification letter", exact=True
        ).click()
        page.get_by_role("button", name="Prepare my draft", exact=True).click()
        report = page.get_by_role("region", name="Your draft report")
        expect(report).to_be_visible()
        open_options(report)
        report.get_by_role("button", name="Edit draft", exact=True).click()
        editor = report.get_by_label("Edit your draft", exact=True)
        initial = editor.input_value()
        original_plain = page.evaluate(
            """async value => {
            const {plainDocument} = await import('/static/documents.js');
            return plainDocument(value).trim();
        }""",
            initial,
        )
        pending = (
            "Fictional reviewed letter\n\nExact 🐝 é wording. "
            "No cash is committed; this draft has not been sent."
        )
        editor.fill(pending)
        paper = report.locator(".document-paper").inner_text()
        before_requests = len(campaign_requests)
        report.get_by_role(
            "button", name="Save draft to campaign log", exact=True
        ).click()
        expect(
            report.locator(".document-feedback").get_by_role("alert")
        ).to_contain_text(
            "Apply or cancel your pending draft edits before saving to the campaign log"
        )
        expect(editor).to_have_value(pending)
        expect(editor).to_be_focused()
        expect(
            report.get_by_role("button", name="Save draft to campaign log", exact=True)
        ).to_be_enabled()
        assert len(campaign_requests) == before_requests
        assert server.app.campaigns.get(before["id"]) == before
        assert report.locator(".document-paper").inner_text() == paper
        if choice == "apply":
            page.screenshot(path=str(artifacts / "pending-campaign-log.png"))
        report.get_by_role(
            "button",
            name="Apply edits" if choice == "apply" else "Cancel edits",
            exact=True,
        ).click()
        if choice == "cancel":
            open_options(report)
            report.get_by_role("button", name="Edit draft", exact=True).click()
            expect(editor).to_have_value(initial)
            expect(editor).to_be_visible()
        report.get_by_label(
            "Draft channel for the campaign log", exact=True
        ).select_option("letter")
        report.get_by_role(
            "button", name="Save draft to campaign log", exact=True
        ).click()
        expect(
            report.get_by_role("button", name="Saved as a draft · not sent", exact=True)
        ).to_be_disabled()
        after = server.app.campaigns.get(before["id"])
        assert after["revision"] == before["revision"] + 1
        document = after["document"]
        for key, value in before["document"].items():
            if key != "communications":
                assert document[key] == value, key
        assert document["communications"][:-1] == before["document"]["communications"]
        logged = document["communications"][-1]
        assert logged["content"] == (pending if choice == "apply" else original_plain)
        assert logged["direction"] == "outgoing" and logged["status"] == "draft"
        assert logged["date"] == "" and logged["channel"] == "letter"
        assert logged["opportunity"] == route
        assert any(link["source_id"] == source_id for link in logged["evidence_links"])
        assert (
            sum(method == "POST" for method in campaign_requests[before_requests:]) == 1
        )
        checks.append(
            "Campaign letter pending edits refuse log save without a campaign request "
            "or revision change; explicit "
            + choice.capitalize()
            + " logs the selected wording as an undated unsent draft, preserving "
            "all original campaign records."
        )

    with tempfile.TemporaryDirectory(prefix="sinter-export-workspace-") as data:
        with patch.object(
            client, "_open", side_effect=AssertionError("Offline export only")
        ) as remote:
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        context = browser.new_context(
                            viewport={"width": 1440, "height": 1000},
                            accept_downloads=True,
                            permissions=["clipboard-read", "clipboard-write"],
                        )
                        context.route(
                            "**/*",
                            lambda route: (
                                route.continue_()
                                if route.request.url.startswith(base + "/")
                                else (external.append(route.request.url), route.abort())
                            ),
                        )
                        page = context.new_page()
                        page.set_default_timeout(7000)
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on("download", lambda value: downloads.append(value))
                        page.on(
                            "request",
                            lambda request: (
                                word_requests.append(True)
                                if request.url.endswith("/api/documents/docx")
                                else None
                            ),
                        )
                        page.on(
                            "request",
                            lambda request: (
                                campaign_requests.append(request.method)
                                if "/api/campaigns" in request.url
                                else None
                            ),
                        )
                        # Count browser print calls without opening an OS dialog.
                        # Word, HTML, Markdown and JSON remain actual downloads.
                        page.add_init_script(
                            "window.fictionalPrintCalls = 0;"
                            "window.print = () => window.fictionalPrintCalls++;"
                        )
                        page.goto(base + "/#casebooks")
                        page.get_by_role(
                            "button", name="Try a fictional community example"
                        ).click()
                        page.get_by_label("Prepare a", exact=True).select_option(
                            "handover"
                        )
                        page.get_by_role(
                            "button", name="Prepare source-only report", exact=True
                        ).click()
                        report = page.get_by_role("region", name="Your draft report")
                        expect(report).to_be_visible()
                        original_book = server.app.casebooks.get(
                            server.app.casebooks.list()[0]["id"]
                        )
                        original_copy = json.loads(json.dumps(original_book))
                        controls = [
                            "Copy draft text",
                            "Download Word (.docx)",
                            "Download document",
                            "Download Markdown",
                            "Download evidence pack",
                            "Print / save PDF",
                        ]
                        open_options(report)
                        report.get_by_role(
                            "button", name="Edit draft", exact=True
                        ).click()
                        unchanged = report.get_by_label(
                            "Edit your draft", exact=True
                        ).input_value()
                        word = download(
                            page, report, controls[1], "unchanged-open-editor.docx"
                        )
                        assert "No booking has been confirmed." in word_text(word)
                        checks.append("An unchanged open editor can still export.")
                        pending = "# Fictional edited draft\n\nExact 🐝 é wording."
                        report.get_by_label("Edit your draft", exact=True).fill(pending)
                        blocked_exports(
                            page, report, "Edit your draft", controls, pending
                        )
                        report.get_by_role(
                            "button", name="Save to this computer", exact=True
                        ).click()
                        expect(
                            report.get_by_role("alert").filter(has_text="before saving")
                        ).to_be_visible()
                        assert not server.app.store.reports()
                        checks.append(
                            "All six controls block pending text without download, "
                            "Word request, clipboard write, print or report change; "
                            "Save keeps its existing refusal."
                        )
                        page.get_by_role(
                            "link", name="My workspace", exact=True
                        ).click()
                        page.get_by_role(
                            "button", name="Open unsaved draft", exact=True
                        ).click()
                        report = page.get_by_role("region", name="Your draft report")
                        blocked_exports(
                            page, report, "Edit your draft", controls, pending
                        )
                        checks.append(
                            "Recovered pending editor text remains exact and "
                            "all six controls stay guarded."
                        )
                        page.screenshot(path=str(artifacts / "pending-editor.png"))
                        report.get_by_role(
                            "button", name="Apply edits", exact=True
                        ).click()
                        word = download(page, report, controls[1], "applied-word.docx")
                        assert "Exact 🐝 é wording." in word_text(word)
                        markdown = download(
                            page, report, controls[3], "applied-markdown.md"
                        )
                        assert markdown.read_text() == pending
                        evidence = json.loads(
                            download(
                                page, report, controls[4], "applied-evidence.json"
                            ).read_text()
                        )
                        assert evidence["document_edits"]["markdown"] == pending
                        assert (
                            evidence["sources"][0]["content"]
                            == (original_copy["document"]["documents"][0]["content"])
                        )
                        checks.append(
                            "Explicit Apply permits real Word, Markdown and JSON "
                            "with exact edited wording and original sources."
                        )
                        open_options(report)
                        report.get_by_role(
                            "button", name="Edit draft", exact=True
                        ).click()
                        report.get_by_label("Edit your draft", exact=True).fill("")
                        blocked_exports(page, report, "Edit your draft", controls, "")
                        report.get_by_role(
                            "button", name="Cancel edits", exact=True
                        ).click()
                        html = download(
                            page, report, controls[2], "cancelled-editor.html"
                        ).read_text()
                        assert "Exact 🐝 é wording." in html
                        assert unchanged not in html
                        report.get_by_role(
                            "button", name=controls[0], exact=True
                        ).click()
                        assert "Exact 🐝 é wording." in page.evaluate(
                            "navigator.clipboard.readText()"
                        )
                        open_options(report)
                        report.get_by_role(
                            "button", name=controls[5], exact=True
                        ).click()
                        assert page.evaluate("window.fictionalPrintCalls") == 1
                        assert server.app.casebooks.get(original_book["id"]) == (
                            original_copy
                        )
                        open_options(report)
                        report.get_by_role(
                            "button", name="Edit draft", exact=True
                        ).click()
                        expect(
                            report.get_by_label("Edit your draft", exact=True)
                        ).to_have_value(pending)
                        report.get_by_role(
                            "button", name="Save to this computer", exact=True
                        ).click()
                        expect(
                            report.get_by_role("note").filter(
                                has_text="Saved in My workspace"
                            )
                        ).to_be_visible()
                        assert len(server.app.store.reports()) == 1
                        expect(
                            report.get_by_label("Edit your draft", exact=True)
                        ).to_have_value(pending)
                        checks.append(
                            "Empty pending text blocks exports; explicit Cancel "
                            "restores exports of the last applied draft without "
                            "changing saved project originals. An unchanged open "
                            "editor also permits a normal local save."
                        )

                        for workflow in ("campaign", "assistant"):
                            page.evaluate(
                                """async workflow => {
                                const {renderReport} = await import(
                                    '/static/reports.js');
                                const report = {
                                    workflow, title: 'Fictional export boundary',
                                    document_markdown: 'No order has been approved.',
                                    markdown: 'Original fictional audit wording.',
                                    sources: [{title: 'Fictional source',
                                        content: 'No permission has been granted.'}],
                                    incomplete: workflow === 'assistant',
                                    campaign: workflow === 'campaign' ? {
                                        signatory: 'Fictional signatory',
                                        contact_details: 'fictional@example.invalid',
                                        communications: []
                                    } : undefined
                                };
                                document.getElementById('view').replaceChildren(
                                    renderReport(report));
                            }""",
                                workflow,
                            )
                            report = page.get_by_role(
                                "region", name="Your draft report"
                            )
                            is_campaign = workflow == "campaign"
                            editor_label = (
                                "Edit the decision brief"
                                if is_campaign
                                else "Edit your draft"
                            )
                            open_options(report)
                            if is_campaign:
                                privacy = report.get_by_label(
                                    "Include full communication records and personal "
                                    "contact details in this download",
                                    exact=True,
                                )
                                privacy.check()
                            report.get_by_role(
                                "button",
                                name="Edit decision brief"
                                if is_campaign
                                else "Edit draft",
                                exact=True,
                            ).click()
                            variant_controls = [
                                "Copy decision brief" if is_campaign else controls[0],
                                "Download Word brief (.docx)"
                                if is_campaign
                                else controls[1],
                                "Download decision brief"
                                if is_campaign
                                else controls[2],
                                "Download Markdown brief"
                                if is_campaign
                                else controls[3],
                                "Download evidence pack with private details"
                                if is_campaign
                                else controls[4],
                                controls[5],
                            ]
                            report.get_by_label(editor_label, exact=True).fill(pending)
                            blocked_exports(
                                page, report, editor_label, variant_controls, pending
                            )
                            if is_campaign:
                                open_options(report)
                                expect(privacy).to_be_checked()
                            report.get_by_role(
                                "button", name="Apply edits", exact=True
                            ).click()
                            word = download(
                                page, report, variant_controls[1], workflow + ".docx"
                            )
                            assert "Exact 🐝 é wording." in word_text(word)
                            if is_campaign:
                                private_pack = json.loads(
                                    download(
                                        page,
                                        report,
                                        variant_controls[4],
                                        "campaign-private-evidence.json",
                                    ).read_text()
                                )
                                assert (
                                    private_pack["export_privacy"][
                                        "campaign_private_details"
                                    ]
                                    == "included_by_user_choice"
                                )
                                open_options(report)
                                expect(privacy).not_to_be_checked()
                            else:
                                assert "INCOMPLETE MODEL DRAFT" in word_text(word)
                            checks.append(
                                workflow + " uses the same six guards; "
                                "Apply preserves export/privacy/incomplete semantics."
                            )
                        for choice in ("apply", "cancel"):
                            campaign_letter_log(page, server, base, choice)
                        assert not errors and not external
                        remote.assert_not_called()
                        receipt = {"passed": True}
                    finally:
                        browser.close()
                        resources["browser_closed"] = True
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
                resources["server_closed"] = not thread.is_alive()
    unchanged_sources = source_hashes == {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in source_paths
    }
    receipt.update(
        {
            "schema": "sinter-document-export-browser/v1",
            "fixture_only": True,
            "checks": checks,
            "browser_errors": errors,
            "external_requests": external,
            "model_operations_requested": 0,
            "resources": resources,
            "source_sha256": source_hashes,
            "source_unchanged_during_run": unchanged_sources,
            "print_proof": "Browser print function counter; no OS PDF dialog opened.",
            "downloads": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in artifacts.iterdir()
                if path.is_file()
            },
        }
    )
    (artifacts / "browser-receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(artifacts / "browser-receipt.json")
    if not receipt["passed"] or not all(resources.values()) or not unchanged_sources:
        raise SystemExit("FAIL: inspect retained fictional browser receipt.")


if __name__ == "__main__":
    main()
