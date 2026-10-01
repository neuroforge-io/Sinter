"""Fictional proof of delayed download handoff and truthful request feedback.

The controlled 1.6-second anchor delay exercises Sinter's Blob lifetime. It does
not reproduce or inspect an embedded browser's implementation or certify an OS
file save outside the actual Chromium downloads retained by this tool.
"""

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

HANDOFF_SCRIPT = """() => {
    const click = HTMLAnchorElement.prototype.click;
    const revoke = URL.revokeObjectURL.bind(URL);
    window.downloadHandoff = {delay: 0, fail: false, events: []};
    URL.revokeObjectURL = url => {
        window.downloadHandoff.events.push({type: 'revoke'});
        return revoke(url);
    };
    HTMLAnchorElement.prototype.click = function () {
        if (!this.download) return click.call(this);
        const state = window.downloadHandoff;
        if (state.fail) throw new Error('Fictional blocked handoff');
        const anchor = this, delay = state.delay;
        state.events.push({type: 'queued', delay});
        setTimeout(() => {
            state.events.push({type: 'consumed', delay});
            click.call(anchor);
        }, delay);
    };
}"""
PRIVATE_REPORT_SCRIPT = """async () => {
    const {renderReport} = await import('/static/reports.js');
    window.fictionalTitleReport = {
        workflow: 'campaign', title: 'Fictional private export',
        document_markdown: 'Internal fictional draft. Nothing agreed.',
        markdown: 'Original fictional audit text.',
        document_edits: {markdown: 'Applied fictional private draft.'},
        sources: [], campaign: {
            signatory: 'Fictional operator',
            contact_details: 'fictional@example.invalid',
            communications: [{subject: 'Fictional question',
                content: 'Unconfirmed fictional terms.'}]
        }
    };
    document.getElementById('view').replaceChildren(
        renderReport(window.fictionalTitleReport));
}"""
REVOCATION_COUNT = (
    "window.downloadHandoff.events.filter(event => event.type === 'revoke').length"
)


def word_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    return "".join(
        node.text or ""
        for node in root.findall(
            ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
        )
    )


def main(argv: list[str] | None = None) -> None:
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-download-lifecycle-proof-"))
    source_paths = (
        "src/sinter/web/ui.js",
        "src/sinter/web/documents.js",
        "src/sinter/web/reports.js",
        "src/sinter/web/report-drafts.js",
        "src/sinter/document_markup.py",
        "src/sinter/docx_export.py",
    )
    source_hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in source_paths
    }
    checks, errors, external, word_requests = [], [], [], []
    resources = {"browser_closed": False, "server_closed": False}
    receipt = {"passed": False}

    def options(report):
        menu = report.locator(".export-menu")
        if not menu.evaluate("element => element.open"):
            menu.locator("summary").click()

    def downloaded(page, report, control, name):
        if "Word" not in control:
            options(report)
        with page.expect_download() as received:
            report.get_by_role("button", name=control, exact=True).click()
        path = artifacts / name
        assert received.value.failure() is None
        received.value.save_as(path)
        assert path.is_file() and path.stat().st_size > 0
        return path

    def apply_text(report, text):
        options(report)
        report.get_by_role("button", name="Edit draft", exact=True).click()
        report.get_by_label("Edit your draft", exact=True).fill(text)
        report.get_by_role("button", name="Apply edits", exact=True).click()

    try:
        with tempfile.TemporaryDirectory(prefix="sinter-download-workspace-") as data:
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
                            context = browser.new_context(accept_downloads=True)
                            context.route(
                                "**/*",
                                lambda route: (
                                    route.continue_()
                                    if route.request.url.startswith(base + "/")
                                    else (
                                        external.append(route.request.url),
                                        route.abort(),
                                    )
                                ),
                            )
                            page = context.new_page()
                            page.set_default_timeout(7000)
                            page.on(
                                "pageerror", lambda error: errors.append(str(error))
                            )
                            page.on(
                                "request",
                                lambda request: (
                                    word_requests.append(request.post_data_json)
                                    if request.url.endswith("/api/documents/docx")
                                    else None
                                ),
                            )
                            held, all_downloads = [], []
                            hold = {"enabled": False}
                            context.route(
                                base + "/api/documents/docx",
                                lambda route: (
                                    held.append(route)
                                    if hold["enabled"]
                                    else route.continue_()
                                ),
                            )
                            page.on("download", lambda item: all_downloads.append(item))
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
                            report = page.get_by_role(
                                "region", name="Your draft report"
                            )
                            expect(report).to_be_visible()
                            original_book = server.app.casebooks.get(
                                server.app.casebooks.list()[0]["id"]
                            )
                            options(report)
                            report.get_by_role(
                                "button", name="Edit draft", exact=True
                            ).click()
                            editor = report.get_by_label("Edit your draft", exact=True)
                            edited = (
                                "# Fictional operator cover\n\n"
                                "No cash or attendance is confirmed. 🌱 é\n\n"
                                + editor.input_value()
                            )
                            editor.fill(edited)
                            report.get_by_role(
                                "button", name="Apply edits", exact=True
                            ).click()
                            report.get_by_role(
                                "button", name="Save to My workspace", exact=True
                            ).click()
                            expect(report).to_contain_text("Saved in My workspace")
                            saved = server.app.store.report(
                                server.app.store.reports()[0]["id"]
                            )
                            assert saved["document_edits"]["markdown"] == edited
                            page.evaluate(HANDOFF_SCRIPT)
                            immediate = downloaded(
                                page,
                                report,
                                "Download Word (.docx)",
                                "immediate-word.docx",
                            )
                            assert (
                                "No cash or attendance is confirmed. 🌱 é"
                                in word_text(immediate)
                            )
                            feedback = report.locator(".document-feedback")
                            expect(feedback).to_contain_text("Word download requested")
                            expect(feedback).to_contain_text(
                                "Check your browser’s downloads"
                            )
                            assert "downloaded" not in feedback.inner_text().lower()
                            checks.append(
                                "An actual Word download carries applied text; "
                                "feedback describes a request, not an OS save."
                            )
                            page.evaluate("window.downloadHandoff.delay = 1600")
                            delayed = downloaded(
                                page,
                                report,
                                "Download Word (.docx)",
                                "delayed-word.docx",
                            )
                            assert word_text(delayed) == word_text(immediate)
                            assert len(word_requests) == 1
                            checks.append(
                                "An explicit matching retry uses the same prepared "
                                "Word file without another compile request; a "
                                "controlled 1.6-second handoff still saves it."
                            )
                            pack = downloaded(
                                page,
                                report,
                                "Download evidence pack",
                                "delayed-edited-pack.json",
                            )
                            assert json.loads(pack.read_text()) == saved
                            assert (
                                server.app.casebooks.get(original_book["id"])
                                == original_book
                            )
                            assert (
                                server.app.store.report(
                                    server.app.store.reports()[0]["id"]
                                )
                                == saved
                            )
                            checks.append(
                                "Delayed edited JSON preserves the exact saved "
                                "report and source snapshot; downloads do not "
                                "mutate either local record."
                            )
                            revokes = page.evaluate(REVOCATION_COUNT)
                            page.evaluate("window.downloadHandoff.fail = true")
                            report.get_by_role(
                                "button", name="Download Word (.docx)", exact=True
                            ).click()
                            expect(feedback.get_by_role("alert")).to_have_text(
                                "Fictional blocked handoff"
                            )
                            expect(
                                report.get_by_role(
                                    "button", name="Download Word (.docx)", exact=True
                                )
                            ).to_be_enabled()
                            assert page.evaluate(REVOCATION_COUNT) == revokes + 1
                            page.evaluate("window.downloadHandoff.fail = false")
                            retry = downloaded(
                                page,
                                report,
                                "Download Word (.docx)",
                                "explicit-retry-word.docx",
                            )
                            assert word_text(retry) == word_text(immediate)
                            assert len(word_requests) == 1
                            checks.append(
                                "A blocked click releases its URL immediately, "
                                "shows the error and permits an explicit retry "
                                "without replaying the compile request."
                            )
                            changed = edited + "\n\nExplicit later fictional wording."
                            apply_text(report, changed)
                            changed_word = downloaded(
                                page,
                                report,
                                "Download Word (.docx)",
                                "changed-word.docx",
                            )
                            assert "Explicit later fictional wording." in word_text(
                                changed_word
                            )
                            assert len(word_requests) == 2
                            checks.append(
                                "Changed applied text compiles a new Word file; "
                                "the previous cached file is never substituted."
                            )
                            compilation_text = (
                                changed + "\n\nFictional compile in flight."
                            )
                            apply_text(report, compilation_text)
                            hold["enabled"] = True
                            with page.expect_request(base + "/api/documents/docx"):
                                report.get_by_role(
                                    "button", name="Download Word (.docx)", exact=True
                                ).click()
                            options(report)
                            report.get_by_role(
                                "button", name="Edit draft", exact=True
                            ).click()
                            pending = (
                                "Unapplied fictional wording remains in the editor."
                            )
                            editor = report.get_by_label("Edit your draft", exact=True)
                            editor.fill(pending)
                            assert len(held) == 1
                            before_downloads = len(all_downloads)
                            hold["enabled"] = False
                            held.pop().continue_()
                            expect(feedback.get_by_role("alert")).to_contain_text(
                                "Apply or cancel"
                            )
                            expect(editor).to_have_value(pending)
                            expect(
                                report.get_by_role(
                                    "button", name="Download Word (.docx)", exact=True
                                )
                            ).to_be_enabled()
                            report.get_by_role(
                                "button", name="Download Word (.docx)", exact=True
                            ).click()
                            assert len(word_requests) == 3
                            assert len(all_downloads) == before_downloads
                            report.get_by_role(
                                "button", name="Cancel edits", exact=True
                            ).click()
                            cancelled = downloaded(
                                page,
                                report,
                                "Download Word (.docx)",
                                "cancelled-pending-retry.docx",
                            )
                            assert "Fictional compile in flight." in word_text(
                                cancelled
                            )
                            assert "Unapplied fictional wording" not in word_text(
                                cancelled
                            )
                            assert len(word_requests) == 3
                            checks.append(
                                "Pending edits before and after a held compile "
                                "prevent downloads without losing editor text. "
                                "Explicit Cancel then retries the matching file "
                                "without a compile replay."
                            )
                            old_applied = (
                                changed + "\n\nOlder in-flight fictional wording."
                            )
                            apply_text(report, old_applied)
                            hold["enabled"] = True
                            with page.expect_request(base + "/api/documents/docx"):
                                report.get_by_role(
                                    "button", name="Download Word (.docx)", exact=True
                                ).click()
                            newest = (
                                changed
                                + "\n\nNewest explicitly applied fictional wording."
                            )
                            apply_text(report, newest)
                            before_downloads = len(all_downloads)
                            assert len(held) == 1
                            hold["enabled"] = False
                            held.pop().continue_()
                            expect(feedback).to_contain_text(
                                "The draft changed while Word was being prepared"
                            )
                            expect(
                                report.get_by_role(
                                    "button", name="Download Word (.docx)", exact=True
                                )
                            ).to_be_enabled()
                            assert len(all_downloads) == before_downloads
                            newest_word = downloaded(
                                page,
                                report,
                                "Download Word (.docx)",
                                "newest-explicit-retry.docx",
                            )
                            assert (
                                "Newest explicitly applied fictional wording."
                                in word_text(newest_word)
                            )
                            assert (
                                "Older in-flight fictional wording."
                                not in word_text(newest_word)
                            )
                            assert len(word_requests) == 5
                            assert (
                                server.app.store.report(
                                    server.app.store.reports()[0]["id"]
                                )
                                == saved
                            )
                            assert (
                                server.app.casebooks.get(original_book["id"])
                                == original_book
                            )
                            checks.append(
                                "Applied text changed during a held compile "
                                "refuses the earlier file. An explicit retry "
                                "compiles current text; saved originals stay intact."
                            )
                            page.evaluate(PRIVATE_REPORT_SCRIPT)
                            report = page.get_by_role(
                                "region", name="Your draft report"
                            )
                            options(report)
                            privacy = report.get_by_label(
                                "Include full communication records and personal "
                                "contact details in this download",
                                exact=True,
                            )
                            privacy.check()
                            private = downloaded(
                                page,
                                report,
                                "Download evidence pack with private details",
                                "delayed-private-pack.json",
                            )
                            private_pack = json.loads(private.read_text())
                            assert (
                                private_pack["campaign"]["communications"][0]["content"]
                                == "Unconfirmed fictional terms."
                            )
                            assert (
                                private_pack["document_edits"]["markdown"]
                                == "Applied fictional private draft."
                            )
                            assert (
                                private_pack["export_privacy"][
                                    "campaign_private_details"
                                ]
                                == "included_by_user_choice"
                            )
                            expect(
                                report.locator(".document-feedback")
                            ).to_contain_text(
                                "Download requested with private campaign details"
                            )
                            expect(
                                report.locator(".document-feedback")
                            ).to_contain_text("Check your browser’s downloads")
                            options(report)
                            expect(privacy).not_to_be_checked()
                            checks.append(
                                "An explicitly chosen private JSON handoff retains "
                                "the fictional content, resets the checkbox and "
                                "uses truthful requested/check-downloads feedback."
                            )
                            page.evaluate("window.downloadHandoff.delay = 0")
                            downloaded(
                                page,
                                report,
                                "Download Word brief (.docx)",
                                "first-title.docx",
                            )
                            assert len(word_requests) == 6
                            page.evaluate(
                                "window.fictionalTitleReport.document_title = "
                                "'Fictional second title'"
                            )
                            downloaded(
                                page,
                                report,
                                "Download Word brief (.docx)",
                                "second-title.docx",
                            )
                            assert len(word_requests) == 7
                            assert all_downloads[-1].suggested_filename == (
                                "sinter-Fictional second title-DRAFT.docx"
                            )
                            assert (
                                word_requests[-1]["title"] == "Fictional second title"
                            )
                            checks.append(
                                "A title-only change recompiles the exact applied "
                                "text and requests the matching new filename."
                            )
                            page.evaluate(
                                "window.fictionalTitleReport.document_title = "
                                "'Fictional older title'"
                            )
                            hold["enabled"] = True
                            with page.expect_request(base + "/api/documents/docx"):
                                report.get_by_role(
                                    "button",
                                    name="Download Word brief (.docx)",
                                    exact=True,
                                ).click()
                            page.evaluate(
                                "window.fictionalTitleReport.document_title = "
                                "'Fictional newest title'"
                            )
                            before_downloads = len(all_downloads)
                            assert len(held) == 1
                            hold["enabled"] = False
                            held.pop().continue_()
                            expect(
                                report.locator(".document-feedback")
                            ).to_contain_text(
                                "The draft changed while Word was being prepared"
                            )
                            expect(
                                report.get_by_role(
                                    "button",
                                    name="Download Word brief (.docx)",
                                    exact=True,
                                )
                            ).to_be_enabled()
                            assert len(all_downloads) == before_downloads
                            downloaded(
                                page,
                                report,
                                "Download Word brief (.docx)",
                                "newest-title.docx",
                            )
                            assert len(word_requests) == 9
                            assert all_downloads[-1].suggested_filename == (
                                "sinter-Fictional newest title-DRAFT.docx"
                            )
                            assert (
                                word_requests[-1]["title"] == "Fictional newest title"
                            )
                            checks.append(
                                "A controlled title change during compilation "
                                "refuses the previous title; an explicit retry "
                                "compiles and downloads the current title."
                            )
                            assert not errors and not external
                            remote.assert_not_called()
                            receipt = {
                                "passed": True,
                                "handoff_events": page.evaluate(
                                    "window.downloadHandoff.events"
                                ),
                            }
                            page.screenshot(
                                path=str(artifacts / "requested-feedback.png")
                            )
                        finally:
                            browser.close()
                            resources["browser_closed"] = True
                finally:
                    server.shutdown()
                    server.app.close()
                    server.server_close()
                    thread.join(timeout=5)
                    resources["server_closed"] = not thread.is_alive()
    finally:
        receipt.update(
            {
                "schema": "sinter-download-lifecycle-browser/v1",
                "fixture_only": True,
                "checks": checks,
                "browser_errors": errors,
                "external_requests": external,
                "model_operations_requested": 0,
                "resources": resources,
                "source_sha256": source_hashes,
                "source_unchanged_during_run": source_hashes
                == {
                    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in source_paths
                },
                "controlled_handoff_delay_ms": 1600,
                "actual_in_app_browser_cause_reproduced": False,
                "local_word_compile_requests": len(word_requests),
                "limitation": (
                    "Controlled fictional anchor delay; successful retained "
                    "Chromium files only. Does not certify another browser, "
                    "its handoff, an OS dialog or installed release."
                ),
                "artifact_sha256": {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in artifacts.iterdir()
                    if p.is_file()
                },
            }
        )
        path = artifacts / "browser-receipt.json"
        path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(path)
    if (
        not receipt["passed"]
        or not all(resources.values())
        or not receipt["source_unchanged_during_run"]
    ):
        raise SystemExit("FAIL: inspect retained fictional download receipt.")


if __name__ == "__main__":
    main()
