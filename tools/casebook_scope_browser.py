"""Fictional casebook source choices, stale anchors and incomplete draft recovery."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.casebook_scope import SURROGATE_ENCODING, draft_context  # noqa: E402
from sinter.casebooks import validate  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

PATHS = (
    "src/sinter/casebooks.py",
    "src/sinter/casebook_scope.py",
    "src/sinter/runtime.py",
    "src/sinter/runtime_cli.py",
    "src/sinter/runtime_routes.py",
    "src/sinter/server.py",
    "src/sinter/web/api.js",
    "src/sinter/web/desktop.css",
    "src/sinter/web/casebooks.js",
    "src/sinter/web/casebook-scope.js",
    "src/sinter/web/casebook-backup.js",
    "src/sinter/web/local-backup.js",
    "src/sinter/web/campaign-backup.js",
    "tools/casebook_scope_browser.py",
)
QUESTIONS = "Which applicants are eligible?\nWhat production costs need checking?"
SOURCES = [
    {
        "title": "Fictional supplier enquiry"
        if index < 2
        else f"Fictional supplier enquiry {index}",
        "content": "Eligible applicants ask production costs. "
        "No quote, approval or owner "
        "is confirmed. 🐝 e\u0301 " + f"Retained original {index}.",
        "date": "",
        "url": "",
    }
    for index in range(3)
] + [
    {
        "title": "Fictional governing rule",
        "content": "Eligible applicants must check the governing rule. "
        "Eligibility is not "
        "confirmed. Current costs are not supplied.",
        "date": "2026-09-30",
        "url": "https://example.invalid/governing-rule",
    }
]


def capacity_profile(browser, base, artifacts, expect, width):
    """Measure the advertised input boundary using a fictional UI restore."""
    book = validate(
        {
            "title": "Fictional bounded capacity profile",
            "questions": "\n".join(
                f"Fictional eligibility item {n}?" for n in range(20)
            ),
            "documents": [
                {
                    "title": f"Fictional small source {n}",
                    "content": f"Fictional eligibility note {n}. "
                    "No funding is approved.",
                }
                for n in range(300)
            ],
        }
    )
    all_ids = [row["id"] for row in book["documents"]]
    book.update(
        schema="sinter-casebook/v2",
        question_scopes=[
            {
                "question_index": n,
                "question": question,
                "source_ids": all_ids[:],
            }
            for n, question in enumerate(book["questions"].splitlines())
        ],
    )
    book = validate(book)
    backup = json.dumps(book, ensure_ascii=False).encode()
    context = browser.new_context(viewport={"width": width, "height": 1000})
    external = []
    context.route(
        "**/*",
        lambda route: (
            route.continue_()
            if route.request.url.startswith(base + "/")
            else (external.append(route.request.url), route.abort())
        ),
    )
    page = context.new_page()
    page.set_default_timeout(20000)
    times = {}
    try:
        began = time.perf_counter()
        page.goto(base + "/#casebooks")
        expect(page.get_by_label("Project name", exact=True)).to_be_visible()
        times["initial_page_load_ms"] = (time.perf_counter() - began) * 1000
        page.get_by_text("Backups and project removal", exact=True).click()
        began = time.perf_counter()
        page.get_by_label("Restore a casebook backup", exact=True).set_input_files(
            {
                "name": "fictional-capacity.json",
                "mimeType": "application/json",
                "buffer": backup,
            }
        )
        expect(
            page.get_by_text("Backup opened as a new unsaved project.", exact=True)
        ).to_be_visible()
        times["restore_300_sources_20_scopes_ms"] = (time.perf_counter() - began) * 1000
        controls = '[data-question-scope-index] input[type="checkbox"]'
        counts = {"checkboxes_after_restore": page.locator(controls).count()}
        outer = page.locator("details").filter(
            has=page.get_by_text("Choose sources for each question", exact=True)
        )
        outer.locator("summary").first.click()
        first = page.locator('[data-question-scope-index="0"]')
        began = time.perf_counter()
        first.locator("summary").first.click()
        selected = first.get_by_role("checkbox").first
        expect(selected).to_be_checked()
        times["open_first_300_source_choice_ms"] = (time.perf_counter() - began) * 1000
        counts["checkboxes_after_first_open"] = page.locator(controls).count()
        began = time.perf_counter()
        selected.uncheck()
        expect(
            page.get_by_label("Question 1 source count", exact=True)
        ).to_contain_text("299 sources chosen")
        times["one_source_selection_change_ms"] = (time.perf_counter() - began) * 1000
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if width == 1440:
            page.set_viewport_size({"width": 390, "height": 844})
            expect(selected).not_to_be_checked()
            dimensions = page.evaluate("""() => ({
              rootWidth:document.documentElement.scrollWidth,
              viewport:innerWidth,
              elements:[...document.querySelectorAll('.casebook-editor *')]
                .filter(e=>e.getBoundingClientRect().right>innerWidth)
                .slice(0,25).map(e=>({tag:e.tagName,classes:e.className,
                  text:e.textContent.slice(0,100),width:e.getBoundingClientRect().width,
                  right:e.getBoundingClientRect().right,
                  columns:getComputedStyle(e).gridTemplateColumns,
                  visibility:getComputedStyle(e).contentVisibility}))})""")
            (artifacts / "capacity-resize-dimensions.json").write_text(
                json.dumps(dimensions, indent=2), encoding="utf-8"
            )
            page.screenshot(path=str(artifacts / "capacity-resize-viewport.png"))
            assert dimensions["rootWidth"] <= dimensions["viewport"]
            first.locator("summary").first.scroll_into_view_if_needed()
            page.screenshot(path=str(artifacts / "capacity-resized-mobile-choices.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
        began = time.perf_counter()
        page.get_by_label("Sources for question 1", exact=True).select_option("all")
        expect(
            page.get_by_label("Question 1 source count", exact=True)
        ).to_contain_text("All 300 supplied sources")
        times["one_question_mode_change_ms"] = (time.perf_counter() - began) * 1000
        counts["checkboxes_after_mode_change"] = page.locator(controls).count()
        assert not external
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(
            path=str(artifacts / f"capacity-{width}-20-questions-300-sources.png")
        )
        return {
            "fixture_only": True,
            "viewport_width": width,
            "resize_with_open_choices": width == 1440,
            "sources": 300,
            "questions": 20,
            "backup_bytes": len(backup),
            "raw_timings_ms": times,
            "rendered_controls": counts,
            "external_requests": external,
            "passed": True,
        }
    finally:
        context.close()


def explicit_clear_proof(
    page, server, base, label, artifacts, expect, save, open_scope
):
    """The current interface carries deliberate clear intent across recovery."""
    book = validate(
        {
            "title": "Fictional clear intent " + label,
            "questions": QUESTIONS,
            "documents": SOURCES,
        }
    )
    book.update(
        schema="sinter-casebook/v2",
        question_scopes=[
            {
                "question_index": 0,
                "question": QUESTIONS.splitlines()[0],
                "source_ids": [book["documents"][3]["id"]],
            }
        ],
    )
    saved = server.app.casebooks.save(book)
    requests = []

    def capture(request):
        if request.url == base + "/api/casebooks/save":
            requests.append(
                {"headers": request.headers, "payload": request.post_data_json}
            )

    page.on("request", capture)
    try:
        page.reload()
        tile = page.locator(".casebook-tile").filter(has_text=book["title"])
        tile.get_by_role("button", name="Open project", exact=True).click()
        expect(page.get_by_label("Project name", exact=True)).to_have_value(
            book["title"]
        )
        # A historical caller paired with the new common API module receives
        # no implicit capability. It cannot read or validate the v2 document.
        refused = page.evaluate(
            """async ({id,book}) => {
          const {request}=await import('/static/api.js');
          const results=[];
          for(const [path,options] of [
            ['/api/casebooks/'+id,{}],
            ['/api/casebooks/validate',{data:{document:book}}]]) {
            try {await request(path,options); results.push({accepted:true});}
            catch(error) {results.push({status:error.status,message:error.message});}
          }
          return results;
        }""",
            {"id": saved["id"], "book": book},
        )
        assert all(
            row.get("status") == 400 and "cannot preserve" in row["message"]
            for row in refused
        )
        assert server.app.casebooks.get(saved["id"]) == saved
        open_scope(page, 0)
        page.get_by_label("Sources for question 1", exact=True).select_option("all")
        expect(page.get_by_label("Project save state", exact=True)).to_contain_text(
            "Unsaved"
        )
        def navigate(label):
            page.get_by_role("button", name="Find a tool", exact=True).click()
            page.get_by_label("Find a Sinter tool", exact=True).fill(label)
            page.locator(".finder-results").get_by_text(label, exact=True).click()

        navigate("Getting started")
        expect(
            page.get_by_role(
                "heading", name="You do not need to be technical.", exact=True
            )
        ).to_be_visible()
        navigate("Community casebooks")
        expect(page.get_by_label("Project name", exact=True)).to_have_value(
            book["title"]
        )
        expect(
            page.get_by_label("Question 1 source count", exact=True)
        ).to_contain_text("All 4 supplied sources")

        def backup_text():
            panel = page.locator("details.card").filter(
                has=page.get_by_text("Backups and project removal", exact=True)
            )
            if panel.get_attribute("open") is None:
                panel.locator("summary").first.click()
            panel.get_by_role("button", name="Refresh backup text", exact=True).click()
            text = page.get_by_label("Project backup text", exact=True).input_value()
            return json.loads(text), text.encode()

        raw_clear, clear_bytes = backup_text()
        assert raw_clear["schema"] == "sinter-casebook/v1"
        assert raw_clear["question_scopes"] == []
        assert raw_clear["documents"] == saved["document"]["documents"]
        assert server.app.casebooks.get(saved["id"]) == saved
        page.screenshot(path=str(artifacts / (label + "-explicit-clear-unsaved.png")))
        save(page, 2)
        cleared = server.app.casebooks.get(saved["id"])
        assert requests[-1]["payload"]["document"]["question_scopes"] == []
        assert (
            requests[-1]["headers"]["x-sinter-casebook-schema"] == "sinter-casebook/v2"
        )
        assert cleared["document"]["schema"] == "sinter-casebook/v1"
        assert "question_scopes" not in cleared["document"]
        assert cleared["document"]["documents"] == saved["document"]["documents"]
        save(page, 3)
        assert "question_scopes" not in requests[-1]["payload"]["document"]

        # Validate intentionally normalizes v1. Restore carries only the exact
        # raw empty-list clear marker into the unsaved copy, without changing
        # the original saved project or silently retaining unknown fields.
        panel = page.locator("details.card").filter(
            has=page.get_by_text("Backups and project removal", exact=True)
        )
        if panel.get_attribute("open") is None:
            panel.locator("summary").first.click()
        page.get_by_label("Restore a casebook backup", exact=True).set_input_files(
            {
                "name": "fictional-deliberate-clear.json",
                "mimeType": "application/json",
                "buffer": clear_bytes,
            }
        )
        expect(
            page.get_by_text("Backup opened as a new unsaved project.", exact=True)
        ).to_be_visible()
        restored_raw, _ = backup_text()
        assert restored_raw["question_scopes"] == []
        assert restored_raw["documents"] == raw_clear["documents"]
        save(page, 1)
        assert requests[-1]["payload"]["document"]["question_scopes"] == []
        clone_id = requests[-1]["payload"].get("id")
        assert clone_id is None
        latest_copy = next(
            row
            for row in server.app.casebooks.list()
            if row["title"] == book["title"] and row["id"] != saved["id"]
        )
        assert (
            server.app.casebooks.get(latest_copy["id"])["document"]["documents"]
            == raw_clear["documents"]
        )
        assert server.app.casebooks.get(saved["id"])["revision"] == 3
        page.get_by_role("button", name="New project", exact=True).click()
        empty, _ = backup_text()
        assert (
            "question_scopes" not in empty and empty["schema"] == "sinter-casebook/v1"
        )
        assert not requests[-1]["payload"].get("id")
        return {
            "mixed_cached_caller_refused": refused,
            "clear_navigation_backup_restore_saved": True,
            "ordinary_v1_and_new_project_marker_absent": True,
            "original_sources_unchanged": True,
        }
    finally:
        page.remove_listener("request", capture)


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-casebook-scope-ui-proof-"))
    artifacts.chmod(0o700)
    hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PATHS
    }
    checks, errors, external, model_calls = [], [], [], []
    profile = {"passed": False}
    mode = {"value": "partial"}
    resources = {"browser_closed": False, "server_closed": False}

    def fixture_draft(messages, **options):
        packet = json.loads(messages[1].content)
        model_calls.append({"mode": mode["value"], "packet": packet})
        if mode["value"] == "partial":
            return client.ChatResult(
                "Fictional received partial ``` 🐝", finish_reason="length"
            )
        sections = [
            {
                "question_index": index,
                "question": row["question"],
                "text": "Clarify [" + row["excerpt_ids"][0] + "]"
                if row["excerpt_ids"]
                else "",
            }
            for index, row in enumerate(packet["questions"])
        ]
        if mode["value"] == "invalid":
            sections[1]["text"] = sections[0]["text"]
        if mode["value"] == "surrogate":
            sections[0]["text"] += (
                " Actual invalid units \ud800\udc00 literal \\u{D800} 🐝"
            )
        if mode["value"] == "surrogate_error":
            raise client.APIError("Fictional interrupted error \ud800", 504)
        return client.ChatResult(
            json.dumps({"sections": sections}, ensure_ascii=False), finish_reason="stop"
        )

    def save(page, revision):
        page.get_by_role("button", name="Save project", exact=True).click()
        expect(page.get_by_label("Project save state", exact=True)).to_have_text(
            f"Project inputs saved at revision {revision}."
        )
        expect(
            page.get_by_role("button", name="Save project", exact=True)
        ).to_be_enabled()

    def latest(server):
        return server.app.jobs.get(server.app.jobs.list()[0]["id"])

    def prepare(page):
        page.get_by_role(
            "button", name="Prepare source-only report", exact=True
        ).click()
        expect(
            page.get_by_text(
                "Ready to review. Source matches do not establish answers.", exact=True
            )
        ).to_be_visible()

    def open_scope(page, index):
        outer = page.locator("details").filter(
            has=page.get_by_text("Choose sources for each question", exact=True)
        )
        if outer.get_attribute("open") is None:
            outer.locator("summary").first.click()
        row = page.locator(f'[data-question-scope-index="{index}"]')
        if row.get_attribute("open") is None:
            row.locator("summary").first.click()
        return row

    with tempfile.TemporaryDirectory(prefix="sinter-casebook-scope-data-") as data:
        with (
            patch.object(
                client,
                "_open",
                side_effect=AssertionError("No hosted calls in this fictional proof"),
            ) as remote,
            patch.object(client, "chat", side_effect=fixture_draft),
        ):
            server = make_server(port=0, directory=data)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        for width, height in ((1440, 1000), (390, 844)):
                            label = f"{width}x{height}"
                            check = {"viewport": label, "passed": False}
                            context = browser.new_context(
                                viewport={"width": width, "height": height},
                                reduced_motion="reduce",
                            )
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
                            page.set_default_timeout(8000)
                            page.on(
                                "pageerror", lambda error: errors.append(str(error))
                            )
                            page.on("dialog", lambda dialog: dialog.accept())
                            try:
                                title = "Fictional scoped eligibility " + label
                                page.goto(base + "/#casebooks")
                                page.get_by_label("Project name", exact=True).fill(
                                    title
                                )
                                page.get_by_label(
                                    "What do you need to find out?", exact=True
                                ).fill(QUESTIONS)
                                for source_index, source in enumerate(SOURCES):
                                    panel = page.locator("details").filter(
                                        has=page.get_by_label(
                                            "Source title", exact=True
                                        )
                                    )
                                    if panel.get_attribute("open") is None:
                                        panel.locator("summary").first.click()
                                    for name, key in (
                                        ("Source title", "title"),
                                        (
                                            "Paste a note, policy or reference",
                                            "content",
                                        ),
                                        ("Source date (optional)", "date"),
                                        ("Source link (optional)", "url"),
                                    ):
                                        page.get_by_label(name, exact=True).fill(
                                            source[key]
                                        )
                                    page.get_by_role(
                                        "button", name="Add this source", exact=True
                                    ).click()
                                open_scope(page, 0)
                                page.get_by_label(
                                    "Sources for question 1", exact=True
                                ).select_option("selected")
                                for source_index, source in enumerate(SOURCES):
                                    expect(
                                        page.get_by_label(
                                            "Question 1 source: "
                                            + source["title"]
                                            + f" — unsaved source {source_index + 1}",
                                            exact=True,
                                        )
                                    ).to_be_disabled()
                                save(page, 1)
                                identifier = next(
                                    row["id"]
                                    for row in server.app.casebooks.list()
                                    if row["title"] == title
                                )
                                initial = server.app.casebooks.get(identifier)
                                duplicate_ids = [
                                    row["id"]
                                    for row in initial["document"]["documents"][:2]
                                ]
                                assert duplicate_ids[0] != duplicate_ids[1]
                                open_scope(page, 0)
                                duplicate_inputs = [
                                    page.get_by_label(
                                        "Question 1 source: "
                                        "Fictional supplier enquiry — " + identity,
                                        exact=True,
                                    )
                                    for identity in duplicate_ids
                                ]
                                state_before_inspect = page.get_by_label(
                                    "Project save state", exact=True
                                ).inner_text()
                                calls_before_inspect = len(model_calls)
                                for index, identity in enumerate(duplicate_ids):
                                    choice = page.locator(
                                        f'[data-question-scope-index="0"] '
                                        f'[data-source-choice-id="{identity}"]'
                                    )
                                    expect(choice.locator("pre")).to_have_count(0)
                                    inspect = choice.get_by_text(
                                        "Inspect this local source", exact=True
                                    )
                                    inspect.focus()
                                    inspect.press("Enter")
                                    expect(choice.locator("pre")).to_have_text(
                                        SOURCES[index]["content"]
                                    )
                                    expect(duplicate_inputs[index]).not_to_be_checked()
                                assert server.app.casebooks.get(identifier) == initial
                                assert len(model_calls) == calls_before_inspect
                                expect(
                                    page.get_by_label("Project save state", exact=True)
                                ).to_have_text(state_before_inspect)
                                page.locator(
                                    '[data-question-scope-index="0"]'
                                ).screenshot(
                                    path=str(artifacts / (label + "-local-inspect.png"))
                                )
                                check[
                                    "local_original_inspect_without_selection_save_or_upload"
                                ] = True
                                mode_control = page.get_by_label(
                                    "Sources for question 1", exact=True
                                )
                                mode_control.focus()
                                mode_control.press("Home")
                                expect(mode_control).to_have_value("all")
                                expect(mode_control).to_be_focused()
                                mode_control.press("End")
                                expect(mode_control).to_have_value("selected")
                                expect(mode_control).to_be_focused()
                                check["keyboard_mode_change_retains_question_focus"] = (
                                    True
                                )
                                duplicate_inputs[0].check()
                                save(page, 2)
                                assert (
                                    server.app.casebooks.get(identifier)["document"][
                                        "question_scopes"
                                    ][0]["source_ids"]
                                    == duplicate_ids[:1]
                                )
                                open_scope(page, 0)
                                duplicate_inputs[0].uncheck()
                                duplicate_inputs[1].check()
                                save(page, 3)
                                assert (
                                    server.app.casebooks.get(identifier)["document"][
                                        "question_scopes"
                                    ][0]["source_ids"]
                                    == duplicate_ids[1:]
                                )
                                open_scope(page, 0)
                                duplicate_inputs[1].uncheck()
                                rule_label = (
                                    "Question 1 source: Fictional governing rule — "
                                    + initial["document"]["documents"][-1]["id"]
                                )
                                open_scope(page, 0)
                                page.get_by_label(
                                    rule_label,
                                    exact=True,
                                ).check()
                                open_scope(page, 1)
                                page.get_by_label(
                                    "Sources for question 2", exact=True
                                ).select_option("selected")
                                expect(
                                    page.get_by_label(
                                        "Question 2 source count", exact=True
                                    )
                                ).to_contain_text("No source will be searched")
                                save(page, 4)
                                chosen = server.app.casebooks.get(identifier)
                                assert (
                                    chosen["document"]["schema"] == "sinter-casebook/v2"
                                )
                                assert (
                                    chosen["document"]["documents"]
                                    == initial["document"]["documents"]
                                )
                                assert (
                                    chosen["document"]["question_scopes"][1][
                                        "source_ids"
                                    ]
                                    == []
                                )
                                check["unsaved_sources_disabled_then_explicit_none"] = (
                                    True
                                )
                                before_open = server.app.casebooks.get(identifier)
                                first_scope = open_scope(page, 0)
                                assert (
                                    server.app.casebooks.get(identifier) == before_open
                                )
                                expect(
                                    page.get_by_label("Project save state", exact=True)
                                ).to_have_text("Project inputs saved at revision 4.")
                                first_scope.screenshot(
                                    path=str(
                                        artifacts / (label + "-source-choices.png")
                                    )
                                )
                                prepare(page)
                                report = copy.deepcopy(latest(server)["result"])
                                selected = {
                                    row["id"]: row for row in report["excerpts"]
                                }
                                assert all(
                                    selected[key]["source_id"]
                                    == chosen["document"]["documents"][-1]["id"]
                                    for key in report["question_index"][0][
                                        "excerpt_ids"
                                    ]
                                )
                                assert report["question_index"][1]["excerpt_ids"] == []
                                assert (
                                    report["question_index"][0]["status"]
                                    == "related_wording"
                                )
                                preview = page.locator("details").filter(
                                    has=page.get_by_text(
                                        "Optional: preview the exact context "
                                        "sent for a richer draft",
                                        exact=True,
                                    )
                                )
                                preview.locator("summary").click()
                                assert json.loads(
                                    preview.locator("pre").inner_text()
                                ) == draft_context(report)
                                page.screenshot(
                                    path=str(artifacts / (label + "-exact-context.png"))
                                )
                                with page.expect_download() as download:
                                    page.get_by_role(
                                        "button",
                                        name="Export project backup",
                                        exact=True,
                                    ).click()
                                backup_bytes = Path(download.value.path()).read_bytes()
                                backup = validate(json.loads(backup_bytes))
                                assert (
                                    backup
                                    == server.app.casebooks.get(identifier)["document"]
                                )
                                (artifacts / (label + "-backup.json")).write_bytes(
                                    backup_bytes
                                )
                                page.reload()
                                page.locator(".casebook-tile").filter(
                                    has=page.get_by_text(title, exact=True)
                                ).get_by_role(
                                    "button", name="Open project", exact=True
                                ).click()
                                open_scope(page, 0)
                                expect(
                                    page.get_by_label(
                                        rule_label,
                                        exact=True,
                                    )
                                ).to_be_checked()
                                open_scope(page, 1)
                                expect(
                                    page.get_by_label(
                                        "Question 2 source count", exact=True
                                    )
                                ).to_contain_text("No source will be searched")
                                check[
                                    "save_reopen_backup_originals_and_context_exact"
                                ] = True

                                # Explicit clicks request synthetic responses.
                                for failure_mode in (
                                    "partial",
                                    "invalid",
                                    "surrogate",
                                    "surrogate_error",
                                    "valid",
                                ):
                                    prepare(page)
                                    source_only = copy.deepcopy(
                                        latest(server)["result"]
                                    )
                                    mode["value"] = failure_mode
                                    before_calls = len(model_calls)
                                    preview = page.locator("details").filter(
                                        has=page.get_by_text(
                                            "Optional: preview the exact context "
                                            "sent for a richer draft",
                                            exact=True,
                                        )
                                    )
                                    preview.locator("summary").click()
                                    preview.get_by_role("checkbox").check()
                                    page.get_by_role(
                                        "button",
                                        name="Prepare an optional AI draft",
                                        exact=True,
                                    ).click()
                                    if failure_mode == "valid":
                                        expect(
                                            page.locator(".paper-label")
                                        ).to_have_text("MODEL-GENERATED DRAFT")
                                        expect(
                                            page.locator(".document-paper")
                                        ).to_contain_text("question remains unanswered")
                                    else:
                                        expect(
                                            page.locator(".paper-label")
                                        ).to_have_text("INCOMPLETE MODEL DRAFT")
                                        expect(
                                            page.locator(".document-paper")
                                        ).to_contain_text("No request was replayed")
                                    assert len(model_calls) == before_calls + 1
                                    assert model_calls[-1]["packet"] == draft_context(
                                        source_only
                                    )
                                    actual = latest(server)["result"]
                                    assert (
                                        actual["source_document_markdown"]
                                        == source_only["document_markdown"]
                                    )
                                    assert actual["excerpts"] == source_only["excerpts"]
                                    if failure_mode != "valid":
                                        assert actual["incomplete"] is True
                                        if failure_mode == "surrogate":
                                            encoded = actual["scoped_model_response"][
                                                "content"
                                            ]
                                            assert (
                                                encoded["encoding"]
                                                == SURROGATE_ENCODING
                                            )
                                            assert (
                                                "\\u{D800}\\u{DC00}"
                                                in encoded["escaped_text"]
                                            )
                                            expect(
                                                page.locator(".document-paper")
                                            ).to_contain_text(
                                                "not verbatim Unicode text"
                                            )
                                        if failure_mode == "surrogate_error":
                                            assert (
                                                actual["generation_error"][
                                                    "original_message"
                                                ]["encoding"]
                                                == SURROGATE_ENCODING
                                            )
                                        page.get_by_role(
                                            "button",
                                            name="Save to this computer",
                                            exact=True,
                                        ).click()
                                        expect(
                                            page.get_by_text(
                                                "Saved in My workspace, including "
                                                "your edits and original evidence.",
                                                exact=True,
                                            )
                                        ).to_be_visible()
                                    page.screenshot(
                                        path=str(
                                            artifacts
                                            / (
                                                label
                                                + "-"
                                                + failure_mode
                                                + "-draft.png"
                                            )
                                        )
                                    )
                                check[
                                    "synthetic_invalid_partial_unicode_error_and_valid_single_requests"
                                ] = True

                                historical = copy.deepcopy(report)
                                persisted = server.app.casebooks.get(identifier)
                                jobs_before = len(server.app.jobs.list())
                                page.get_by_label(
                                    "What do you need to find out?", exact=True
                                ).fill("\n".join(reversed(QUESTIONS.splitlines())))
                                page.get_by_role(
                                    "button",
                                    name="Prepare source-only report",
                                    exact=True,
                                ).click()
                                expect(
                                    page.locator(".casebooks-page .notice.error")
                                ).to_contain_text("Questions changed or moved")
                                assert server.app.casebooks.get(identifier) == persisted
                                assert len(server.app.jobs.list()) == jobs_before
                                assert report == historical
                                transfers = page.locator("details.card").filter(
                                    has=page.get_by_text(
                                        "Backups and project removal", exact=True
                                    )
                                )
                                if transfers.get_attribute("open") is None:
                                    transfers.locator("summary").first.click()
                                page.evaluate("""() => Object.defineProperty(
                                  navigator, 'clipboard', {configurable:true,
                                    value:{writeText:async()=>{
                                      throw new Error('Fictional denied clipboard')
                                    }}})""")
                                transfers.get_by_role(
                                    "button", name="Copy backup text", exact=True
                                ).click()
                                expect(
                                    transfers.get_by_text(
                                        "Clipboard unavailable. Select and copy "
                                        "the complete backup text below. This "
                                        "does not save the project or create a file.",
                                        exact=True,
                                    )
                                ).to_be_visible()
                                backup_text = page.get_by_label(
                                    "Project backup text", exact=True
                                )
                                captured = json.loads(backup_text.input_value())
                                assert (
                                    captured["question_scopes"]
                                    == persisted["document"]["question_scopes"]
                                )
                                assert captured["questions"] == "\n".join(
                                    reversed(QUESTIONS.splitlines())
                                )
                                assert (
                                    captured["documents"]
                                    == persisted["document"]["documents"]
                                )
                                transfers.get_by_role(
                                    "button", name="Select backup text", exact=True
                                ).click()
                                expect(backup_text).to_be_focused()
                                assert backup_text.evaluate(
                                    "e=>e.selectionStart===0 && "
                                    "e.selectionEnd===e.value.length"
                                )
                                page.evaluate("""() => Object.defineProperty(
                                  navigator, 'clipboard', {configurable:true,
                                    value:{writeText:()=>new Promise(resolve=>{
                                      window.releaseFictionalClipboard=resolve
                                    })}})""")
                                copying = transfers.get_by_role(
                                    "button", name="Copy backup text", exact=True
                                )
                                copying.click()
                                expect(copying).to_be_disabled()
                                page.get_by_label("Project name", exact=True).fill(
                                    title + " unsaved copy"
                                )
                                transfers.get_by_role(
                                    "button", name="Refresh backup text", exact=True
                                ).click()
                                assert (
                                    json.loads(backup_text.input_value())["title"]
                                    == title + " unsaved copy"
                                )
                                page.evaluate("window.releaseFictionalClipboard()")
                                expect(copying).to_be_enabled()
                                expect(
                                    transfers.get_by_text(
                                        "Backup text refreshed from your current "
                                        "inputs. Clipboard may contain an earlier "
                                        "snapshot; select the text below to copy "
                                        "manually. This does not save the project "
                                        "or create a file.",
                                        exact=True,
                                    )
                                ).to_be_visible()
                                page.get_by_label("Project name", exact=True).fill(
                                    title
                                )
                                source_panel = page.locator("details").filter(
                                    has=page.get_by_label("Source title", exact=True)
                                )
                                if source_panel.get_attribute("open") is None:
                                    source_panel.locator("summary").first.click()
                                page.get_by_label("Source title", exact=True).fill(
                                    "Fictional pending source"
                                )
                                before_pending_text = backup_text.input_value()
                                transfers.get_by_role(
                                    "button", name="Refresh backup text", exact=True
                                ).click()
                                expect(
                                    page.get_by_label(
                                        "Paste a note, policy or reference", exact=True
                                    )
                                ).to_be_focused()
                                assert backup_text.input_value() == before_pending_text
                                page.get_by_label("Source title", exact=True).fill("")
                                assert server.app.casebooks.get(identifier) == persisted
                                assert len(server.app.jobs.list()) == jobs_before
                                check[
                                    "manual_backup_retains_stale_choices_pending_guard_and_clipboard_failure_recovery"
                                ] = True
                                transfers.locator("summary").first.click()
                                open_scope(page, 0)
                                confirm = page.get_by_role(
                                    "button",
                                    name="Confirm source choices for question 1",
                                    exact=True,
                                )
                                confirm.focus()
                                confirm.press("Enter")
                                expect(
                                    page.get_by_label(
                                        "Sources for question 1", exact=True
                                    )
                                ).to_be_focused()
                                open_scope(page, 1)
                                confirm = page.get_by_role(
                                    "button",
                                    name="Confirm source choices for question 2",
                                    exact=True,
                                )
                                confirm.focus()
                                confirm.press("Enter")
                                expect(
                                    page.get_by_label(
                                        "Sources for question 2", exact=True
                                    )
                                ).to_be_focused()
                                check[
                                    "keyboard_anchor_confirmation_retains_question_focus"
                                ] = True
                                save(page, persisted["revision"] + 1)
                                confirmed = server.app.casebooks.get(identifier)
                                rule = (
                                    page.locator(".casebook-editor details.source")
                                    .filter(
                                        has=page.get_by_text(
                                            "Fictional governing rule", exact=True
                                        )
                                    )
                                    .filter(
                                        has=page.get_by_role(
                                            "button",
                                            name="Remove source",
                                            exact=True,
                                            include_hidden=True,
                                        )
                                    )
                                    .first
                                )
                                rule.locator("summary").first.click()
                                rule.get_by_role(
                                    "button", name="Remove source", exact=True
                                ).click()
                                page.get_by_role(
                                    "button", name="Save project", exact=True
                                ).click()
                                expect(
                                    page.locator(".notice.error").filter(
                                        has_text="no longer available"
                                    )
                                ).to_contain_text("no longer available")
                                assert server.app.casebooks.get(identifier) == confirmed
                                check[
                                    "reordered_questions_and_removed_source_require_review"
                                ] = True
                                page.screenshot(
                                    path=str(
                                        artifacts
                                        / (label + "-removed-source-refused.png")
                                    )
                                )

                                page.get_by_text(
                                    "Backups and project removal", exact=True
                                ).click()
                                page.get_by_label(
                                    "Restore a casebook backup", exact=True
                                ).set_input_files(
                                    {
                                        "name": "fictional-scoped.json",
                                        "mimeType": "application/json",
                                        "buffer": backup_bytes,
                                    }
                                )
                                expect(
                                    page.get_by_text(
                                        "Backup opened as a new unsaved project.",
                                        exact=True,
                                    )
                                ).to_be_visible()
                                save(page, 1)
                                restored = next(
                                    row
                                    for row in server.app.casebooks.list()
                                    if row["title"] == title and row["id"] != identifier
                                )
                                assert (
                                    server.app.casebooks.get(restored["id"])["document"]
                                    == backup
                                )
                                assert server.app.casebooks.get(identifier) == confirmed
                                assert page.evaluate(
                                    "document.documentElement.scrollWidth <= innerWidth"
                                )
                                check["separate_restore_and_no_horizontal_overflow"] = (
                                    True
                                )
                                # Removing one chosen same-title original must not
                                # substitute the other original with that title.
                                open_scope(page, 0)
                                page.get_by_label(rule_label, exact=True).uncheck()
                                page.get_by_label(
                                    "Question 1 source: Fictional supplier enquiry — "
                                    + duplicate_ids[1],
                                    exact=True,
                                ).check()
                                save(page, 2)
                                restored_saved = server.app.casebooks.get(
                                    restored["id"]
                                )
                                duplicate_source_rows = (
                                    page.locator(".casebook-editor details.source")
                                    .filter(
                                        has=page.get_by_text(
                                            "Fictional supplier enquiry", exact=True
                                        )
                                    )
                                    .filter(
                                        has=page.get_by_role(
                                            "button",
                                            name="Remove source",
                                            exact=True,
                                            include_hidden=True,
                                        )
                                    )
                                )
                                duplicate_source_rows.nth(1).locator("summary").click()
                                duplicate_source_rows.nth(1).get_by_role(
                                    "button", name="Remove source", exact=True
                                ).click()
                                page.get_by_role(
                                    "button", name="Save project", exact=True
                                ).click()
                                expect(
                                    page.locator(".notice.error").filter(
                                        has_text="no longer available"
                                    )
                                ).to_contain_text("no longer available")
                                assert (
                                    server.app.casebooks.get(restored["id"])
                                    == restored_saved
                                )
                                assert (
                                    restored_saved["document"]["question_scopes"][0][
                                        "source_ids"
                                    ]
                                    == duplicate_ids[1:]
                                )
                                check[
                                    "duplicate_titles_selection_save_and_no_substitution"
                                ] = True
                                check["cached_client_and_explicit_clear"] = (
                                    explicit_clear_proof(
                                        page,
                                        server,
                                        base,
                                        label,
                                        artifacts,
                                        expect,
                                        save,
                                        open_scope,
                                    )
                                )
                                check["passed"] = True
                            except Exception as exc:
                                check.update(
                                    error=type(exc).__name__ + ": " + str(exc),
                                    traceback=traceback.format_exc(),
                                )
                                page.screenshot(
                                    path=str(artifacts / (label + "-FAILED.png"))
                                )
                            finally:
                                context.close()
                                checks.append(check)
                                print(json.dumps(check), flush=True)
                        try:
                            runs = [
                                capacity_profile(
                                    browser, base, artifacts, expect, width
                                )
                                for width in (1440, 390)
                            ]
                            profile = {
                                "runs": runs,
                                "passed": all(row["passed"] for row in runs),
                            }
                        except Exception as exc:
                            profile = {
                                "passed": False,
                                "error": type(exc).__name__ + ": " + str(exc),
                                "traceback": traceback.format_exc(),
                            }
                        remote.assert_not_called()
                    finally:
                        browser.close()
                        resources["browser_closed"] = True
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                worker.join(timeout=5)
                resources["server_closed"] = not worker.is_alive()
    unchanged = hashes == {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PATHS
    }
    receipt = {
        "schema": "sinter-casebook-scope-browser/v1",
        "fixture_only": True,
        "checks": checks,
        "source_sha256": hashes,
        "source_unchanged_during_run": unchanged,
        "browser_errors": errors,
        "external_requests": external,
        "hosted_model_calls": 0,
        "synthetic_draft_requests": len(model_calls),
        "capacity_profile": profile,
        "resources": resources,
        "passed": all(row["passed"] for row in checks)
        and profile["passed"]
        and not errors
        and not external
        and unchanged
        and all(resources.values()),
    }
    target = artifacts / "browser-receipt.json"
    target.write_text(json.dumps(receipt, indent=2))
    for path in artifacts.iterdir():
        path.chmod(0o600)
    print(target)
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect the retained fictional source-choice proof.")


if __name__ == "__main__":
    main()
