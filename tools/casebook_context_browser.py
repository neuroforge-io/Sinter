"""Fictional selected-source coverage and exact local-context operator proof."""

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
    "src/sinter/web/casebook-retained-context.js",
    "src/sinter/web/reports.js",
    "src/sinter/web/report-citations.js",
    "src/sinter/web/documents.js",
    "src/sinter/web/dom.js",
    "src/sinter/casebooks.py",
    "src/sinter/casebook_scope.py",
    "src/sinter/runtime_routes.py",
    "src/sinter/docx_export.py",
    "tools/casebook_context_browser.py",
)
TITLE = "<script>literal title</script> same title"
QUESTIONS = (
    "Where are the closing dates in Table 1?",
    "Who gave approval?",
    "Is the zyzzyva confirmation evidenced?",
)


def fixture():
    heading = "Table 1 — Closing dates\n"
    content = "🐝 e\u0301 Navigation.\n" + "menu " * 225 + "\n" + heading
    content += "Application stage | Fictional date\nOpening | 1 January 2030\nSubmission | 31 January 2030\n"
    book = validate(
        {
            "title": "Fictional local coverage inspection",
            "questions": "\n".join(QUESTIONS),
            "document_type": "handover",
            "documents": [
                {
                    "title": TITLE,
                    "content": "Closing dates are not confirmed by this overview. Table 1 must be read in the original guidelines.",
                },
                {"title": TITLE, "content": content},
                {
                    "title": TITLE,
                    "date": "2020-01-01",
                    "content": "An archival garden visit described volunteers and equipment.",
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
                {"question_index": 0, "question": QUESTIONS[0], "source_ids": ids},
                {"question_index": 1, "question": QUESTIONS[1], "source_ids": []},
                {"question_index": 2, "question": QUESTIONS[2], "source_ids": [ids[0]]},
            ],
        }
    )
    report = build(book, "handover")
    passage = next(row for row in report["excerpts"] if row["source_id"] == ids[1])
    assert passage["quote"].endswith(heading) and "Submission |" not in passage["quote"]
    assert len({row["source_id"] for row in report["excerpts"]}) == 2
    report["document_edits"] = {
        "markdown": "# Fictional operator wording\n\nApproval and eligibility remain unknown. 🐝 e\u0301."
    }
    return book, report, ids, passage


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-casebook-context-proof-"))
    artifacts.chmod(0o700)
    hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in PATHS
    }
    book, report, ids, passage = fixture()
    reference = next(
        row["label"]
        for row in report["document_references"]
        if row["excerpt_id"] == passage["id"]
    )
    checks, errors, external = [], [], []
    resources = {"browser_closed": False, "servers_closed": True}

    def check(name, condition, **extra):
        checks.append({"name": name, "passed": bool(condition), **extra})
        assert condition, name

    with (
        tempfile.TemporaryDirectory(prefix="sinter-context-fictional-") as data,
        patch.object(
            client, "_open", side_effect=AssertionError("No API calls")
        ) as remote,
        patch.object(client, "chat", side_effect=AssertionError("No models")) as model,
        sync_playwright() as driver,
    ):
        browser = launch_chromium(driver, args.chromium)
        report_id = None
        try:
            for width, height in [(1440, 1000), (390, 844)]:
                server = make_server(port=0, directory=data)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}"
                context = browser.new_context(
                    viewport={"width": width, "height": height}, reduced_motion="reduce"
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
                prefix = str(width)
                try:
                    if report_id is None:
                        report_id = server.app.store.save_report(report)
                        saved = server.app.casebooks.save(book)
                        changed = copy.deepcopy(saved["document"])
                        changed.update(
                            schema="sinter-casebook/v1",
                            question_scopes=[],
                            questions="Changed current question?",
                            title="Changed current project",
                        )
                        changed["documents"][1]["content"] = (
                            "CURRENT PROJECT IS NOT THIS REPORT"
                        )
                        current_id = server.app.casebooks.save(
                            changed, saved["id"], saved["revision"]
                        )["id"]
                    before = copy.deepcopy(server.app.store.report(report_id))
                    current_before = copy.deepcopy(server.app.casebooks.get(current_id))
                    prefs = (
                        server.app.preferences.path.read_bytes()
                        if server.app.preferences.path.exists()
                        else None
                    )
                    started = time.perf_counter()
                    page.goto(base + "/#library")
                    tile = page.locator("article.card").filter(
                        has=page.get_by_role(
                            "heading", name=report["title"], exact=True
                        )
                    )
                    tile.get_by_role("button", name="Open draft", exact=True).click()
                    expect(
                        page.get_by_role("region", name="Your draft report")
                    ).to_be_visible()
                    page.wait_for_load_state("networkidle")
                    load_ms = (time.perf_counter() - started) * 1000
                    document_text = page.locator(".document-paper").inner_text()
                    baseline_requests = len(requests)
                    page.get_by_role("tab", name="Evidence", exact=True).click()
                    row = page.get_by_role("article", name="Question 1 evidence")
                    expect(row.locator(".question-evidence-coverage")).to_have_text(
                        "Exact retained quotes from 2 of 3 chosen sources."
                    )
                    expect(row).to_contain_text(
                        "1 chosen source has no exact retained quote"
                    )
                    expect(row.locator(".question-evidence-state")).to_have_text(
                        "Review required"
                    )
                    check(
                        prefix + "/coverage is per question and non-semantic",
                        "eligibility confirmed" not in row.inner_text().lower(),
                    )
                    missing = row.locator(".question-evidence-unrepresented")
                    missing.locator("summary").focus()
                    page.keyboard.press("Enter")
                    expect(missing).to_contain_text(ids[2])
                    expect(missing).to_contain_text("not its original text")
                    check(
                        prefix
                        + "/identical titles retain distinct missing source identity",
                        missing.locator("script,a").count() == 0
                        and ids[0] not in missing.inner_text(),
                    )
                    row.locator(".question-evidence-coverage").evaluate(
                        "element => element.scrollIntoView({block: 'start'})"
                    )
                    page.screenshot(path=str(artifacts / (prefix + "-coverage.png")))
                    none = page.get_by_role("article", name="Question 2 evidence")
                    expect(none.locator(".question-evidence-coverage")).to_have_count(0)
                    expect(none).to_contain_text("No sources selected")
                    third = page.get_by_role("article", name="Question 3 evidence")
                    expect(third.locator(".question-evidence-coverage")).to_have_text(
                        "Exact retained quotes from 0 of 1 chosen source."
                    )
                    third.locator(".question-evidence-unrepresented summary").click()
                    third.get_by_role(
                        "button",
                        name=f"Inspect retained original for question 3, source {ids[0]}",
                        exact=True,
                    ).click()
                    original = page.locator(".sources-panel [data-source-id]").filter(
                        has=page.locator("summary").filter(has_text=TITLE)
                    )
                    target = page.locator(".sources-panel [data-source-id]").filter(
                        has=page.locator("pre").filter(
                            has_text=book["documents"][0]["content"]
                        )
                    )
                    expect(target.locator("summary").first).to_be_focused()
                    check(
                        prefix
                        + "/unused for this question can inspect retained original from other question",
                        target.locator("pre").inner_text()
                        == book["documents"][0]["content"],
                    )
                    quote = row.locator(".question-evidence-quote").filter(
                        has_text=passage["id"]
                    )
                    quote.locator("summary").focus()
                    page.keyboard.press("Enter")
                    expect(quote.locator("pre").first).to_have_text(passage["quote"])
                    started = time.perf_counter()
                    quote.get_by_role(
                        "button",
                        name=f"Inspect surrounding text for question 1 {reference}",
                        exact=True,
                    ).click()
                    expect(quote.locator(".question-evidence-context")).to_contain_text(
                        "Submission | 31 January 2030"
                    )
                    context_ms = (time.perf_counter() - started) * 1000
                    expect(quote.locator(".question-evidence-context")).to_contain_text(
                        "not included in this report’s quotations, Word document or optional AI preview"
                    )
                    expect(quote.locator("pre").first).to_have_text(passage["quote"])
                    check(
                        prefix
                        + "/context exposes adjoining cells while quote and request count stay exact",
                        len(requests) == baseline_requests,
                    )
                    quote.locator(".question-evidence-context").evaluate(
                        "element => element.scrollIntoView({block: 'start'})"
                    )
                    page.screenshot(path=str(artifacts / (prefix + "-context.png")))
                    quote.get_by_role(
                        "button",
                        name="Open original source for " + reference,
                        exact=True,
                    ).click()
                    original = page.locator(
                        f'.sources-panel [data-source-id="{ids[1]}"]'
                    )
                    expect(original.locator("summary").first).to_be_focused()
                    expect(original.locator("pre")).to_have_text(
                        book["documents"][1]["content"]
                    )
                    check(
                        prefix
                        + "/full original is historical despite current replacement",
                        "CURRENT PROJECT" not in original.inner_text(),
                    )
                    page.get_by_role("tab", name="Document", exact=True).click()
                    check(
                        prefix + "/document unchanged",
                        page.locator(".document-paper").inner_text() == document_text,
                    )
                    page.get_by_text("More options", exact=True).click()
                    page.get_by_role("button", name="Edit draft", exact=True).click()
                    editor = page.get_by_role(
                        "textbox", name="Edit your draft", exact=True
                    )
                    pending = (
                        report["document_edits"]["markdown"] + "\n\nPending note 🐝."
                    )
                    editor.fill(pending)
                    page.get_by_role("tab", name="Evidence", exact=True).click()
                    expect(editor).to_have_value(pending)
                    check(
                        prefix + "/pending editor and applied wording stay separate",
                        server.app.store.report(report_id) == before,
                    )
                    page.get_by_role("button", name="Cancel edits", exact=True).click()
                    with page.expect_download() as event:
                        page.get_by_role(
                            "button", name="Download Word (.docx)", exact=True
                        ).click()
                    word_path = artifacts / (prefix + "-unchanged-word.docx")
                    event.value.save_as(word_path)
                    with zipfile.ZipFile(word_path) as archive:
                        word = ElementTree.fromstring(archive.read("word/document.xml"))
                    text = "".join(
                        item.text or ""
                        for item in word.findall(
                            ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
                        )
                    )
                    check(
                        prefix
                        + "/actual Word request preserves exact applied markdown",
                        word_requests
                        == [
                            {
                                "title": report.get("document_title")
                                or report["title"],
                                "markdown": report["document_edits"]["markdown"],
                            }
                        ],
                    )
                    check(
                        prefix + "/context is absent from actual Word payload",
                        "31 January 2030" not in text
                        and "Pending note" not in text
                        and "Approval and eligibility remain unknown" in text,
                    )
                    page.get_by_role("tab", name="Evidence", exact=True).click()
                    row.scroll_into_view_if_needed()
                    page.screenshot(
                        path=str(artifacts / (prefix + "-coverage-and-context.png"))
                    )
                    check(
                        prefix + "/phone or desktop has no horizontal clipping",
                        page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        ),
                    )
                    if width == 1440:
                        page.set_viewport_size({"width": 390, "height": 844})
                        check(
                            prefix + "/desktop resize stays within phone width",
                            page.evaluate(
                                "document.documentElement.scrollWidth <= innerWidth"
                            ),
                        )
                        page.set_viewport_size({"width": width, "height": height})
                    for kind in (
                        "changed-adjacent",
                        "missing-original",
                        "ambiguous-register",
                        "missing-passage-list",
                        "malformed-passage-list",
                        "unresolved-passage-list",
                        "duplicate-passage-list",
                        "blank-question-wording",
                    ):
                        changed_report = copy.deepcopy(report)
                        if kind == "changed-adjacent":
                            next(
                                source
                                for source in changed_report["sources"]
                                if source["id"] == ids[1]
                            )["content"] = book["documents"][1]["content"].replace(
                                "31 January", "99 January"
                            )
                        elif kind == "missing-original":
                            changed_report["sources"] = [
                                source
                                for source in changed_report["sources"]
                                if source["id"] != ids[1]
                            ]
                        elif kind == "ambiguous-register":
                            changed_report["source_register"].append(
                                copy.deepcopy(changed_report["source_register"][1])
                            )
                        elif kind == "missing-passage-list":
                            del changed_report["question_index"][0]["excerpt_ids"]
                        elif kind == "malformed-passage-list":
                            changed_report["question_index"][0]["excerpt_ids"] = "[]"
                        elif kind == "unresolved-passage-list":
                            changed_report["question_index"][0]["excerpt_ids"] += [
                                "UnknownRetainedPassage"
                            ]
                        elif kind == "duplicate-passage-list":
                            changed_report["question_index"][0]["excerpt_ids"] += [
                                passage["id"]
                            ]
                        else:
                            changed_report["question_index"][0]["question"] = (
                                "\u2003\u0085"
                            )
                            changed_report["question_scopes"][0]["question"] = (
                                "\u2003\u0085"
                            )
                        page.evaluate(
                            """async report => {const {renderReport} = await import('/static/reports.js'); window.testRetainedReport = report; document.getElementById('view').replaceChildren(renderReport(report));}""",
                            changed_report,
                        )
                        page.get_by_role("tab", name="Evidence", exact=True).click()
                        altered_row = page.get_by_role(
                            "article", name="Question 1 evidence"
                        )
                        if kind == "changed-adjacent":
                            altered_quote = altered_row.locator(
                                ".question-evidence-quote"
                            ).filter(has_text=passage["id"])
                            altered_quote.locator("summary").click()
                            altered_quote.get_by_role(
                                "button",
                                name=f"Inspect surrounding text for question 1 {reference}",
                                exact=True,
                            ).click()
                            expect(altered_quote).to_contain_text(
                                "does not match its recorded source hash"
                            )
                            expect(
                                altered_quote.locator(".question-evidence-context")
                            ).to_be_empty()
                        else:
                            if kind in {
                                "missing-passage-list",
                                "malformed-passage-list",
                            }:
                                expect(altered_row).to_contain_text(
                                    "The recorded passage list is unavailable"
                                )
                            elif kind == "blank-question-wording":
                                expect(altered_row).to_contain_text(
                                    "Question wording unavailable"
                                )
                            else:
                                expect(altered_row).to_contain_text(
                                    "Evidence unavailable"
                                )
                            expect(
                                altered_row.locator(".question-evidence-coverage")
                            ).to_have_count(0)
                            expect(
                                altered_row.locator(".question-evidence-unrepresented")
                            ).to_have_count(0)
                        check(
                            prefix
                            + "/"
                            + kind
                            + " retains literal report without current substitution",
                            page.evaluate("window.testRetainedReport")
                            == changed_report,
                        )
                    check(
                        prefix
                        + "/stored report, current project, preferences and original fingerprint unchanged",
                        server.app.store.report(report_id) == before
                        and server.app.casebooks.get(current_id) == current_before
                        and prefs
                        == (
                            server.app.preferences.path.read_bytes()
                            if server.app.preferences.path.exists()
                            else None
                        )
                        and before["casebook_fingerprint"]
                        == report["casebook_fingerprint"],
                    )
                    # A historical report can retain 300 source records while
                    # only selected originals are embedded. Materialize missing
                    # identity lists only when that question is opened.
                    capacity = copy.deepcopy(report)
                    capacity["source_register"] += [
                        {
                            "id": f"Scapacity{index}",
                            "title": TITLE + f" {index}",
                            "date": "",
                            "url": "",
                            "sha256": hashlib.sha256(
                                f"Fictional original {index}".encode()
                            ).hexdigest(),
                        }
                        for index in range(297)
                    ]
                    all_ids = [item["id"] for item in capacity["source_register"]]
                    capacity["question_index"] = [
                        {
                            "question": f"Capacity question {index + 1}?",
                            "excerpt_ids": [report["excerpts"][index % 2]["id"]],
                            "status": "related_wording",
                        }
                        for index in range(20)
                    ]
                    capacity["question_scopes"] = [
                        {
                            "question_index": index,
                            "question": item["question"],
                            "source_ids": all_ids,
                        }
                        for index, item in enumerate(capacity["question_index"])
                    ]
                    started = time.perf_counter()
                    page.evaluate(
                        """async report => {const {renderReport} = await import('/static/reports.js'); window.testRetainedReport = report; document.getElementById('view').replaceChildren(renderReport(report));}""",
                        capacity,
                    )
                    page.get_by_role("tab", name="Evidence", exact=True).click()
                    capacity_panel = page.get_by_role(
                        "region", name="Questions and evidence"
                    )
                    expect(capacity_panel.locator("article")).to_have_count(20)
                    capacity_render_ms = (time.perf_counter() - started) * 1000
                    check(
                        prefix + "/capacity source lists remain lazy",
                        capacity_panel.locator(
                            ".question-evidence-unrepresented > div > div"
                        ).count()
                        == 0,
                    )
                    first = page.get_by_role("article", name="Question 1 evidence")
                    expect(first.locator(".question-evidence-coverage")).to_have_text(
                        "Exact retained quotes from 1 of 300 chosen sources."
                    )
                    started = time.perf_counter()
                    first.locator(".question-evidence-unrepresented summary").focus()
                    page.keyboard.press("Enter")
                    expect(
                        first.locator(".question-evidence-unrepresented > div > div")
                    ).to_have_count(299)
                    capacity_open_ms = (time.perf_counter() - started) * 1000
                    check(
                        prefix
                        + "/one capacity list opening leaves other19 lists untouched",
                        capacity_panel.locator(
                            ".question-evidence-unrepresented > div > div"
                        ).count()
                        == 299,
                    )
                    check(
                        prefix + "/capacity keyboard and safe literal titles",
                        first.locator(
                            ".question-evidence-unrepresented summary"
                        ).evaluate("(el)=>el===document.activeElement")
                        and not first.locator("script").count(),
                    )
                    check(
                        prefix + "/capacity exact view and originals are unchanged",
                        page.evaluate("window.testRetainedReport") == capacity
                        and server.app.store.report(report_id) == before
                        and server.app.casebooks.get(current_id) == current_before,
                    )
                    check(
                        prefix + "/capacity no horizontal clipping",
                        page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        ),
                    )
                    page.screenshot(path=str(artifacts / (prefix + "-capacity.png")))
                    checks.append(
                        {
                            "name": prefix + "/raw timings",
                            "passed": True,
                            "load_ms": load_ms,
                            "context_ms": context_ms,
                        }
                    )
                    checks[-1].update(
                        capacity_render_ms=capacity_render_ms,
                        capacity_open_ms=capacity_open_ms,
                    )
                except Exception:
                    checks.append(
                        {
                            "name": prefix + "/unexpected failure",
                            "passed": False,
                            "traceback": traceback.format_exc(),
                        }
                    )
                    page.screenshot(path=str(artifacts / (prefix + "-FAILED.png")))
                finally:
                    context.close()
                    server.shutdown()
                    server.server_close()
                    server.app.close()
                    thread.join(5)
                    resources["servers_closed"] &= not thread.is_alive()
        finally:
            browser.close()
            resources["browser_closed"] = True
        remote.assert_not_called()
        model.assert_not_called()
    unchanged = all(
        hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
        for path, digest in hashes.items()
    )
    receipt = {
        "schema": "sinter-local-context-browser-proof/v1",
        "scope": "Fictional source-only headless browser; not actual IAB, installed or provider qualification.",
        "source_root": str(ROOT),
        "source_sha256": hashes,
        "source_unchanged": unchanged,
        "checks": checks,
        "page_errors": errors,
        "external_requests": external,
        "model_calls": 0,
        "resources": resources,
        "passed": all(row["passed"] for row in checks)
        and unchanged
        and not errors
        and not external
        and all(resources.values()),
    }
    target = artifacts / "receipt.json"
    target.write_text(json.dumps(receipt, indent=2) + "\n")
    print(target)
    print(json.dumps({"passed": receipt["passed"], "checks": len(checks)}))
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect private fictional context proof")


if __name__ == "__main__":
    main()
