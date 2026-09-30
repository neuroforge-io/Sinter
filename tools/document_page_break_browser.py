"""Export an explicitly inserted front-page boundary with fictional evidence intact."""

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
from sinter.document_markup import PAGE_BREAK_MARKER  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FRONT = (
    "# Fictional operator front page\n\n"
    "Purpose: discuss one proposed pilot, without committing costs.\n\n"
    "Owner acceptance and proposed dates remain unconfirmed.\n\n"
    "This is an operator summary; the selected source record follows.\n\n"
)


def main(argv: list[str] | None = None) -> None:
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-document-page-break-proof-"))
    paths = (
        "src/sinter/document_markup.py",
        "src/sinter/docx_export.py",
        "src/sinter/web/document-page-break.js",
        "src/sinter/web/markdown.js",
        "src/sinter/web/documents.js",
        "src/sinter/web/documents.css",
        "tests/fixtures/handover-appendix.json",
        "tools/document_page_break_browser.py",
    )
    hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths
    }
    checks, external, errors = [], [], []
    resources = {"browser_closed": False, "server_closed": False}
    receipt = {"passed": False, "fixture_only": True}

    def options(report):
        menu = report.locator(".export-menu")
        if menu.get_attribute("open") is None:
            menu.locator("summary").click()

    def download(page, report, name, filename):
        if "Word" not in name:
            options(report)
        with page.expect_download() as pending:
            report.get_by_role("button", name=name, exact=True).click()
        path = artifacts / filename
        pending.value.save_as(str(path))
        return path

    with tempfile.TemporaryDirectory(
        prefix="sinter-document-page-break-workspace-"
    ) as data:
        with patch.object(
            client, "_open", side_effect=AssertionError("Offline page-layout proof")
        ) as remote:
            server = make_server(port=0, directory=data)
            original = json.loads(
                (ROOT / "tests/fixtures/handover-appendix.json").read_text()
            )
            original["handover_evidence"] = "selected_appendix"
            saved_book = server.app.casebooks.save(original)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        context = browser.new_context(
                            viewport={"width": 1440, "height": 1000},
                            reduced_motion="reduce",
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
                        page.set_default_timeout(10000)
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on("dialog", lambda dialog: dialog.accept())
                        page.goto(base + "/#casebooks")
                        page.get_by_role(
                            "button", name="Open project", exact=True
                        ).click()
                        page.get_by_role(
                            "button", name="Prepare source-only report", exact=True
                        ).click()
                        report = page.get_by_role("region", name="Your draft report")
                        expect(report).to_be_visible()
                        with page.expect_response("**/api/reports") as saved:
                            report.get_by_role(
                                "button", name="Save to this computer", exact=True
                            ).click()
                        historical_id = saved.value.json()["id"]
                        historical = server.app.store.report(historical_id)
                        prepared_book = server.app.casebooks.get(saved_book["id"])
                        original_markdown = historical["document_markdown"]
                        options(report)
                        report.get_by_role(
                            "button", name="Edit draft", exact=True
                        ).click()
                        editor = report.get_by_label("Edit your draft", exact=True)
                        supplied = FRONT + original_markdown
                        editor.fill(supplied)
                        # Select text too: inserting a boundary must never delete it.
                        editor.evaluate(
                            "(node, at) => node.setSelectionRange(at, at + 12)",
                            len(FRONT),
                        )
                        report.get_by_role(
                            "button", name="Insert page break", exact=True
                        ).click()
                        expected = (
                            FRONT + PAGE_BREAK_MARKER + "\n\n" + original_markdown
                        )
                        expect(editor).to_have_value(expected)
                        assert editor.evaluate(
                            "node => node.selectionStart === node.selectionEnd"
                        )
                        before_requests = server.app.store.reports()
                        report.get_by_role(
                            "button", name="Download Word (.docx)", exact=True
                        ).click()
                        expect(report.get_by_role("alert")).to_contain_text(
                            "Apply or cancel"
                        )
                        expect(editor).to_have_value(expected)
                        assert server.app.store.reports() == before_requests
                        report.get_by_role(
                            "button", name="Cancel edits", exact=True
                        ).click()
                        expect(report.locator(".document-page-break")).to_have_count(0)
                        assert server.app.store.report(historical_id) == historical
                        checks.append(
                            "Insert retains selected text; pending export guard "
                            "and Cancel preserve original work."
                        )

                        options(report)
                        report.get_by_role(
                            "button", name="Edit draft", exact=True
                        ).click()
                        editor.fill(supplied)
                        editor.evaluate(
                            "(node, at) => node.setSelectionRange(at, at)", len(FRONT)
                        )
                        report.get_by_role(
                            "button", name="Insert page break", exact=True
                        ).click()
                        report.get_by_role(
                            "button", name="Apply edits", exact=True
                        ).click()
                        expect(
                            report.get_by_role(
                                "separator", name="Page break", exact=True
                            )
                        ).to_have_count(1)
                        report.get_by_role(
                            "button", name="Copy draft text", exact=True
                        ).click()
                        copied = page.evaluate("navigator.clipboard.readText()")
                        assert (
                            PAGE_BREAK_MARKER not in copied
                            and "Page break" not in copied
                        )
                        assert "Fictional operator front page" in copied
                        for excerpt in historical["excerpts"]:
                            assert excerpt["quote"] in copied, excerpt["id"]
                        with page.expect_response("**/api/reports") as saved:
                            report.get_by_role(
                                "button", name="Save to this computer", exact=True
                            ).click()
                        edited_id = saved.value.json()["id"]
                        edited = server.app.store.report(edited_id)
                        assert edited_id != historical_id
                        assert edited["document_edits"]["markdown"] == expected
                        assert edited["document_markdown"] == original_markdown
                        assert edited["excerpts"] == historical["excerpts"]
                        assert server.app.store.report(historical_id) == historical
                        assert (
                            server.app.casebooks.get(saved_book["id"]) == prepared_book
                        )
                        checks.append(
                            "Apply and Save retain original report, source "
                            "snapshots and every exact selected passage."
                        )

                        word = download(
                            page,
                            report,
                            "Download Word (.docx)",
                            "front-page-selected-evidence.docx",
                        )
                        html = download(
                            page,
                            report,
                            "Download document",
                            "front-page-selected-evidence.html",
                        )
                        markdown = download(
                            page,
                            report,
                            "Download Markdown",
                            "front-page-selected-evidence.md",
                        )
                        assert markdown.read_text() == expected
                        with zipfile.ZipFile(word) as package:
                            xml = ElementTree.fromstring(
                                package.read("word/document.xml")
                            )
                        word_text = "\n".join(
                            "".join(node.itertext())
                            for node in xml.findall(f".//{{{W}}}p")
                        )
                        assert (
                            len(xml.findall(f'.//{{{W}}}br[@{{{W}}}type="page"]')) == 1
                        )
                        assert PAGE_BREAK_MARKER not in word_text
                        for excerpt in historical["excerpts"]:
                            assert excerpt["quote"] in word_text, excerpt["id"]
                            assert excerpt["id"] in word_text, excerpt["id"]
                        page.screenshot(
                            path=str(artifacts / "applied-page-boundary.png"),
                            full_page=True,
                        )
                        page.reload()
                        page.get_by_role(
                            "link", name="My workspace", exact=True
                        ).click()
                        page.get_by_role(
                            "button", name="Open draft", exact=True
                        ).first.click()
                        report = page.get_by_role("region", name="Your draft report")
                        expect(
                            report.get_by_role(
                                "separator", name="Page break", exact=True
                            )
                        ).to_have_count(1)
                        assert server.app.store.report(edited_id) == edited
                        checks.append(
                            "Word, HTML and Markdown exports and a fresh page "
                            "reload retain the explicit boundary."
                        )

                        options(report)
                        report.get_by_role(
                            "button", name="Edit draft", exact=True
                        ).click()
                        editor = report.get_by_label("Edit your draft", exact=True)
                        fenced = (
                            "```text\nFictional literal source wording.\n```\n\n"
                            + expected
                        )
                        editor.fill(fenced)
                        caret = fenced.index("source wording")
                        editor.evaluate(
                            "(node, at) => node.setSelectionRange(at, at)", caret
                        )
                        report.get_by_role(
                            "button", name="Insert page break", exact=True
                        ).click()
                        expect(report.get_by_role("alert")).to_contain_text(
                            "between document paragraphs"
                        )
                        expect(editor).to_have_value(fenced)
                        expect(editor).to_be_focused()
                        assert server.app.store.report(edited_id) == edited
                        report.get_by_role(
                            "button", name="Apply edits", exact=True
                        ).click()
                        expect(
                            report.get_by_role("separator", name="Page break")
                        ).to_have_count(1)
                        refused_word = download(
                            page,
                            report,
                            "Download Word (.docx)",
                            "refused-fenced-insertion.docx",
                        )
                        with zipfile.ZipFile(refused_word) as package:
                            refused_xml = ElementTree.fromstring(
                                package.read("word/document.xml")
                            )
                        assert (
                            len(
                                refused_xml.findall(
                                    f'.//{{{W}}}br[@{{{W}}}type="page"]'
                                )
                            )
                            == 1
                        )
                        assert PAGE_BREAK_MARKER not in "".join(refused_xml.itertext())
                        checks.append(
                            "Literal fenced-caret insertion is refused without "
                            "changing text, saved work or the existing boundary."
                        )

                        # Render the downloaded portable HTML through the same browser,
                        # without file-origin access or external network requests.
                        html_page = context.new_page()
                        html_page.on(
                            "pageerror", lambda error: errors.append(str(error))
                        )
                        html_page.set_content(html.read_text())
                        expect(
                            html_page.get_by_role(
                                "separator", name="Page break", exact=True
                            )
                        ).to_have_count(1)
                        html_page.emulate_media(media="print")
                        assert (
                            html_page.locator(".document-page-break").evaluate(
                                "node => getComputedStyle(node).breakAfter"
                            )
                            == "page"
                        )
                        html_page.pdf(
                            path=str(artifacts / "portable-html.pdf"),
                            format="A4",
                            margin={
                                "top": "20mm",
                                "bottom": "20mm",
                                "left": "20mm",
                                "right": "20mm",
                            },
                            print_background=True,
                        )
                        html_page.close()
                        literal = context.new_page()
                        literal.on("pageerror", lambda error: errors.append(str(error)))
                        literal.goto(base + "/#home")
                        observed = literal.evaluate(
                            """async marker => {
                            const {markdown} = await import('/static/markdown.js');
                            const supplied = '> ' + marker + '\\n\\n```text\\n' + marker
                                + '\\n```\\n\\n<script>alert(1)</script>';
                            const node = markdown(supplied);
                            document.body.replaceChildren(node);
                            return {breaks:
                                node.querySelectorAll('.document-page-break').length,
                                scripts: node.querySelectorAll('script').length,
                                text: node.textContent};
                        }""",
                            PAGE_BREAK_MARKER,
                        )
                        assert observed["breaks"] == 0 and observed["scripts"] == 0
                        assert observed["text"].count(PAGE_BREAK_MARKER) == 2
                        literal.close()
                        checks.append(
                            "Portable HTML printing honors the boundary; "
                            "quoted/fenced markers and hostile HTML remain literal."
                        )
                        assert not errors and not external
                        remote.assert_not_called()
                        receipt["passed"] = True
                    finally:
                        browser.close()
                        resources["browser_closed"] = True
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
                resources["server_closed"] = not thread.is_alive()
                unchanged = hashes == {
                    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in paths
                }
                receipt.update(
                    {
                        "schema": "sinter-document-page-break-browser/v1",
                        "checks": checks,
                        "page_errors": errors,
                        "external_requests": external,
                        "model_calls": remote.call_count,
                        "resources": resources,
                        "source_sha256": hashes,
                        "source_unchanged_during_run": unchanged,
                        "artifacts_sha256": {
                            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in artifacts.iterdir()
                            if path.is_file()
                        },
                    }
                )
                receipt["passed"] = (
                    receipt["passed"] and unchanged and all(resources.values())
                )
                (artifacts / "browser-receipt.json").write_text(
                    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
                )
    print(
        f"PASS: {len(checks)} fictional explicit page-boundary journeys. "
        f"Receipt: {artifacts}"
    )


if __name__ == "__main__":
    main()
