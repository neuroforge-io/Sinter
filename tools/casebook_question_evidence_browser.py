"""Fictional read-only question/evidence review through the actual report interface."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.casebooks import build, validate  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

PATHS = (
    "src/sinter/web/casebook-question-evidence.js",
    "src/sinter/web/reports.js",
    "src/sinter/web/report-citations.js",
    "src/sinter/web/documents.css",
    "src/sinter/web/dom.js",
    "src/sinter/casebooks.py",
    "src/sinter/runtime_routes.py",
    "tools/casebook_question_evidence_browser.py",
)
QUESTIONS = (
    "What is the application closing deadline?",
    "Which insurance commitments are confirmed?",
    "Which supplier agreed?",
    "Is a zyzzyva certificate evidenced?",
)
TITLE = "<script>not markup</script> [Duplicate title](javascript:evil)"


def fixture():
    book = validate(
        {
            "title": "Fictional historical question review",
            "document_type": "handover",
            "questions": "\n".join(QUESTIONS),
            "documents": [
                {
                    "title": TITLE,
                    "content": "🐝 e\u0301 Application deadline discussion: "
                    "event proposed "
                    "for 8 August. No application closing date is supplied.",
                },
                {
                    "title": TITLE,
                    "content": "🐝 Application closing deadline is unknown. "
                    "A proposed event date does not establish it.",
                },
                {
                    "title": "Fictional cost note",
                    "content": "Only costs are recorded. No commitment is recorded.",
                },
            ],
        }
    )
    ids = [row["id"] for row in book["documents"]]
    book = validate(
        {
            **book,
            "schema": "sinter-casebook/v2",
            "question_scopes": [
                {"question_index": 1, "question": QUESTIONS[1], "source_ids": []},
                {"question_index": 2, "question": QUESTIONS[2], "source_ids": [ids[2]]},
            ],
        }
    )
    report = build(book, "handover")
    assert len(report["question_index"][0]["excerpt_ids"]) == 2
    assert not report["question_index"][2]["excerpt_ids"]
    report["document_edits"] = {
        "markdown": "# Fictional reviewed handover\n\n"
        "No deadline, eligibility or commitment confirmed."
    }
    return book, report


def run_flow(
    page, base, server, report, report_id, current_id, label, artifacts, expect
):
    requests, word_requests = [], []
    page.on("request", lambda request: requests.append(request.url))
    page.on(
        "request",
        lambda request: (
            word_requests.append(request.post_data_json)
            if request.url.endswith("/api/documents/docx")
            else None
        ),
    )
    started = time.perf_counter()
    page.goto(base + "/#library")
    tile = page.locator("article.card").filter(
        has=page.get_by_role("heading", name=report["title"], exact=True)
    )
    tile.get_by_role("button", name="Open draft", exact=True).click()
    expect(page.get_by_role("region", name="Your draft report")).to_be_visible()
    loaded_ms = (time.perf_counter() - started) * 1000
    original_document = page.locator(".document-paper").inner_text()
    before = copy.deepcopy(server.app.store.report(report_id))
    current_before = copy.deepcopy(server.app.casebooks.get(current_id))
    request_count = len(requests)
    started = time.perf_counter()
    page.get_by_role("tab", name="Evidence", exact=True).click()
    panel = page.get_by_role("region", name="Questions and evidence", exact=True)
    expect(panel).to_be_visible()
    evidence_ms = (time.perf_counter() - started) * 1000
    expect(panel.locator("article")).to_have_count(4)
    for index, question in enumerate(QUESTIONS):
        row = page.get_by_role("article", name=f"Question {index + 1} evidence")
        expect(row.locator(".question-evidence-question")).to_have_text(question)
    row = page.get_by_role("article", name="Question 1 evidence")
    expect(row.locator(".question-evidence-state")).to_have_text("Review required")
    expect(row).to_contain_text("All supplied sources")
    expect(row.locator("details")).to_have_count(2)
    expect(row.locator("details[open]")).to_have_count(0)
    expect(
        page.get_by_role("article", name="Question 2 evidence").locator(
            ".question-evidence-state"
        )
    ).to_have_text("No sources selected")
    expect(page.get_by_role("article", name="Question 3 evidence")).to_contain_text(
        "1 selected source"
    )
    expect(
        page.get_by_role("article", name="Question 4 evidence").locator(
            ".question-evidence-state"
        )
    ).to_have_text("No wording match")
    for index, excerpt_id in enumerate(report["question_index"][0]["excerpt_ids"]):
        excerpt = next(item for item in report["excerpts"] if item["id"] == excerpt_id)
        reference = next(
            item
            for item in report["document_references"]
            if item["excerpt_id"] == excerpt_id
        )
        quote = row.locator("details").nth(index)
        summary = quote.locator("summary")
        summary.focus()
        started = time.perf_counter()
        page.keyboard.press("Enter")
        expect(quote).to_have_attribute("open", "")
        quote_ms = (time.perf_counter() - started) * 1000
        expect(quote.locator("pre")).to_have_text(excerpt["quote"])
        expect(quote).to_contain_text(excerpt["id"])
        expect(quote).to_contain_text(excerpt["source_id"])
        expect(quote).to_contain_text(
            f"Unicode characters {excerpt['start']}–{excerpt['end']}"
        )
        expect(summary).to_contain_text(TITLE)
        assert not summary.locator("script,a").count()
        quote.get_by_role(
            "button", name="Open original source for " + reference["label"], exact=True
        ).click()
        original = page.locator(
            ".sources-panel [data-source-id='" + excerpt["source_id"] + "']"
        )
        expect(original).to_have_attribute("open", "")
        expect(original.locator("summary").first).to_be_focused()
        expected_source = next(
            source
            for source in report["sources"]
            if source["id"] == excerpt["source_id"]
        )
        expect(original.locator("pre")).to_have_text(expected_source["content"])
    assert len(requests) == request_count, "Opening evidence made a request"
    assert server.app.store.report(report_id) == before
    assert server.app.casebooks.get(current_id) == current_before
    page.get_by_role("tab", name="Document", exact=True).click()
    assert page.locator(".document-paper").inner_text() == original_document
    # The projection must neither replace applied wording nor pending editor text.
    page.get_by_text("More options", exact=True).click()
    page.get_by_role("button", name="Edit draft", exact=True).click()
    editor = page.get_by_role("textbox", name="Edit your draft", exact=True)
    pending_text = (
        report["document_edits"]["markdown"] + "\n\nPending local note 🐝 e\u0301."
    )
    editor.fill(pending_text)
    page.get_by_role("tab", name="Evidence", exact=True).click()
    expect(editor).to_have_value(pending_text)
    expect(panel).to_be_visible()
    page.get_by_role("button", name="Cancel edits", exact=True).click()
    with page.expect_download() as received:
        page.get_by_role("button", name="Download Word (.docx)", exact=True).click()
    downloaded = artifacts / (label + "-unchanged-reviewed-handover.docx")
    received.value.save_as(downloaded)
    with zipfile.ZipFile(downloaded) as archive:
        word = ElementTree.fromstring(archive.read("word/document.xml"))
    text = "".join(
        item.text or ""
        for item in word.findall(
            ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
        )
    )
    assert "Fictional reviewed handover" in text
    assert "No deadline, eligibility or commitment confirmed." in text
    assert "Pending local note" not in text and "Questions and evidence" not in text
    assert word_requests == [
        {
            "title": report.get("document_title") or report["title"],
            "markdown": report["document_edits"]["markdown"],
        }
    ]
    assert server.app.store.report(report_id) == before
    assert server.app.casebooks.get(current_id) == current_before

    page.get_by_role("tab", name="Evidence", exact=True).click()
    panel.screenshot(path=str(artifacts / (label + "-question-evidence-panel.png")))
    row.scroll_into_view_if_needed()
    page.screenshot(path=str(artifacts / (label + "-questions-and-evidence.png")))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if page.viewport_size["width"] > 500:
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(artifacts / "desktop-resize-phone.png"))
    return {
        "viewport": label,
        "passed": True,
        "historical_question_scope_quote_ids_unicode_exact": True,
        "duplicate_titles_literal_and_keyboard_source_jump": True,
        "stored_report_document_and_current_project_unchanged": True,
        "evidence_requests": 0,
        "word_compile_requests": len(word_requests),
        "pending_editor_and_actual_word_export_unchanged": True,
        "raw_timings_ms": {
            "load_saved_report": loaded_ms,
            "open_evidence_view": evidence_ms,
            "last_keyboard_quote_open": quote_ms,
        },
    }


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-private-question-evidence-proof-"))
    artifacts.chmod(0o700)
    hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in PATHS
    }
    book, report = fixture()
    errors, external, checks = [], [], []
    resources = {"browser_closed": False, "servers_closed": True}
    with (
        tempfile.TemporaryDirectory(prefix="sinter-question-evidence-data-") as data,
        patch.object(
            client, "_open", side_effect=AssertionError("No hosted calls")
        ) as remote,
        patch.object(
            client, "chat", side_effect=AssertionError("No model calls")
        ) as model,
    ):
        with sync_playwright() as driver:
            browser = launch_chromium(driver, args.chromium)
            report_id = None
            current_id = None
            try:
                for width, height in [(1440, 1000), (390, 844)]:
                    server = make_server(port=0, directory=data)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    base = f"http://127.0.0.1:{server.server_port}"
                    context = browser.new_context(
                        viewport={"width": width, "height": height},
                        reduced_motion="reduce",
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
                    label = f"{width}x{height}"
                    try:
                        if report_id is None:
                            report_id = server.app.store.save_report(report)
                            saved = server.app.casebooks.save(book)
                            changed = copy.deepcopy(saved["document"])
                            changed["questions"] = "Changed current project question?"
                            changed["question_scopes"] = []
                            changed["schema"] = "sinter-casebook/v1"
                            changed["documents"][0]["content"] = (
                                "CHANGED CURRENT SOURCE"
                            )
                            current = server.app.casebooks.save(
                                changed, saved["id"], saved["revision"]
                            )
                            current_id = current["id"]
                        checks.append(
                            run_flow(
                                page,
                                base,
                                server,
                                report,
                                report_id,
                                current_id,
                                label,
                                artifacts,
                                expect,
                            )
                        )
                        # Render a retained, malformed report locally: missing exact ID.
                        missing = copy.deepcopy(report)
                        missing["question_index"][0]["excerpt_ids"] = [
                            "missing-historical-excerpt"
                        ]
                        page.evaluate(
                            """async report => {
                          const {renderReport} = await import('/static/reports.js');
                          document.getElementById('view').replaceChildren(renderReport(report));
                        }""",
                            missing,
                        )
                        page.get_by_role("tab", name="Evidence", exact=True).click()
                        row = page.get_by_role("article", name="Question 1 evidence")
                        expect(row).to_contain_text("Evidence unavailable")
                        expect(row).to_contain_text("missing-historical-excerpt")
                        expect(row.locator("details")).to_have_count(0)
                        assert server.app.store.report(report_id) == report
                        checks[-1][
                            "missing_reference_no_current_project_substitution"
                        ] = True
                        # Reject empty historical wording.
                        for wording in ("", " \t\u0085\u00a0"):
                            blank = copy.deepcopy(report)
                            blank["question_index"][3]["question"] = wording
                            before_blank = json.dumps(blank, ensure_ascii=False)
                            page.evaluate(
                                """async report => {
                              const {renderReport} = await import('/static/reports.js');
                              window.historicalBlankReport = report;
                              document.getElementById('view').replaceChildren(renderReport(report));
                            }""",
                                blank,
                            )
                            page.get_by_role("tab", name="Evidence", exact=True).click()
                            unavailable = page.get_by_role(
                                "article", name="Question 4 evidence"
                            )
                            expect(
                                unavailable.locator(".question-evidence-state")
                            ).to_have_text("Review required")
                            expect(
                                unavailable.locator(".question-evidence-question")
                            ).to_have_text("Question wording unavailable")
                            expect(unavailable).to_contain_text(
                                "No current project wording was substituted"
                            )
                            assert (
                                page.evaluate(
                                    "window.historicalBlankReport.question_index[3].question"
                                )
                                == wording
                            )
                            retained = page.evaluate("window.historicalBlankReport")
                            assert (
                                json.dumps(retained, ensure_ascii=False) == before_blank
                            )
                            assert server.app.store.report(report_id) == report
                        checks[-1][
                            "blank_historical_wording_unavailable_exact_input_preserved"
                        ] = True
                        checks[-1]["fresh_app_reopen"] = width == 390
                    except Exception as error:
                        checks.append(
                            {
                                "passed": False,
                                "viewport": label,
                                "error": str(error),
                                "traceback": traceback.format_exc(),
                            }
                        )
                        page.screenshot(path=str(artifacts / (label + "-FAILED.png")))
                    finally:
                        context.close()
                        server.shutdown()
                        server.app.close()
                        server.server_close()
                        thread.join(timeout=5)
                        resources["servers_closed"] &= not thread.is_alive()
            finally:
                browser.close()
                resources["browser_closed"] = True
        remote.assert_not_called()
        model.assert_not_called()
    unchanged = hashes == {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in PATHS
    }
    receipt = {
        "schema": "sinter-private-question-evidence-proof/v1",
        "prototype_only": True,
        "source_root": str(ROOT),
        "source_sha256": hashes,
        "source_unchanged": unchanged,
        "checks": checks,
        "errors": errors,
        "external": external,
        "hosted_model_calls": 0,
        "real_workspace_mutations": 0,
        "resources": resources,
        "passed": all(row["passed"] for row in checks)
        and unchanged
        and not errors
        and not external
        and all(resources.values()),
    }
    target = artifacts / "question-evidence-receipt.json"
    target.write_text(json.dumps(receipt, indent=2) + "\n")
    for path in artifacts.iterdir():
        path.chmod(0o600)
    print(target)
    print(json.dumps(checks))
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect private prototype evidence")


if __name__ == "__main__":
    main()
