"""Private fictional metadata-filter, keyboard focus and exact recovery proof."""

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

from sinter import casebooks, client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

PATHS = (
    "src/sinter/web/casebook-scope.js",
    "src/sinter/web/casebook-source-filter.js",
    "src/sinter/web/casebooks.js",
    "src/sinter/web/api.js",
    "src/sinter/web/desktop.css",
    "src/sinter/casebooks.py",
    "src/sinter/casebook_scope.py",
    "src/sinter/runtime.py",
    "src/sinter/runtime_cli.py",
    "src/sinter/runtime_routes.py",
    "src/sinter/server.py",
    "tools/casebook_source_filter_browser.py",
)


def fixture(label):
    book = casebooks.validate(
        {
            "title": "Fictional source filter " + label,
            "questions": "Which supplied rules need reviewing?\nWhat remains unknown?\n"
            + "\n".join(
                f"What is the fictional question {index}?" for index in range(3, 21)
            ),
            "documents": [
                {
                    "title": "Duplicate supplied title"
                    if index < 2
                    else f"Fictional source {index:03}",
                    "date": f"2026-09-0{index + 1}" if index < 2 else "",
                    "url": f"https://example.invalid/reference/{index}",
                    "content": f"Fictional original {index}. No answers are confirmed. "
                    + (
                        "Body-only unicorn appears here."
                        if index == 50
                        else "Rules need human review."
                    ),
                }
                for index in range(300)
            ],
        }
    )
    ids = [book["documents"][index]["id"] for index in [0, 1, 125, 299]]
    book.update(
        schema="sinter-casebook/v2",
        question_scopes=[
            {
                "question_index": 0,
                "question": book["questions"].splitlines()[0],
                "source_ids": ids,
            },
            {
                "question_index": 1,
                "question": book["questions"].splitlines()[1],
                "source_ids": [],
            },
        ],
    )
    return book


def run_flow(page, server, base, label, artifacts, expect):
    saved = server.app.casebooks.save(fixture(label))
    historical = casebooks.build(saved["document"])
    report_id = server.app.store.save_report(historical)
    before_packet = copy.deepcopy(casebooks.draft_context(historical))
    ids = saved["document"]["question_scopes"][0]["source_ids"]
    traffic, timings = [], {}
    page.on(
        "request",
        lambda request: traffic.append(request.url) if "/api/" in request.url else None,
    )
    page.goto(base + "/#casebooks")
    page.locator(".casebook-tile").filter(
        has_text=saved["document"]["title"]
    ).get_by_role("button", name="Open project", exact=True).click()
    expect(page.get_by_label("Project name", exact=True)).to_have_value(
        saved["document"]["title"]
    )
    page.get_by_role("button", name="Prepare source-only report", exact=True).click()
    expect(
        page.get_by_text(
            "Ready to review. Source matches do not establish answers.", exact=True
        )
    ).to_be_visible()
    saved = server.app.casebooks.get(saved["id"])
    assert saved["revision"] == 2
    prepared_text = page.locator("#casebook-output").inner_text()
    page.get_by_text("Choose sources for each question", exact=True).click()
    first = page.locator('[data-question-scope-index="0"]')
    first.locator("summary").first.click()
    search = first.get_by_label("Filter sources for question 1", exact=True)
    selected_only = first.get_by_label(
        "Show only selected sources for question 1", exact=True
    )
    counts = first.get_by_label("Question 1 source filter results", exact=True)
    expect(search).to_be_visible()
    expect(counts).to_have_text(
        "Showing 300 of 300 sources. 4 selected in total; 0 selected outside this view."
    )
    controls = first.locator('[data-source-choice-id] input[type="checkbox"]')
    assert controls.count() == 300

    def search_for(query, count, selected=4, outside=None):
        began = time.perf_counter()
        search.fill(query)
        expect(counts).to_contain_text(
            f"Showing {count} of 300 sources. {selected} selected in total"
        )
        expect(search).to_be_focused()
        assert first.locator("[data-source-choice-id]:visible").count() == count
        if outside is not None:
            expect(counts).to_contain_text(f"{outside} selected outside this view")
        timings[query or "clear_search"] = (time.perf_counter() - began) * 1000

    filtered_traffic = len(traffic)
    search_for("duplicate", 2, outside=2)
    search_for("unicorn", 0, outside=4)  # body content is deliberately excluded
    search_for("2026-09-02", 1, outside=3)
    search_for("/reference/125", 1, outside=3)
    search_for(ids[3], 1, outside=3)
    original = first.locator(f'[data-source-choice-id="{ids[3]}"]')
    original.get_by_text("Inspect this local source", exact=True).click()
    expect(original.locator("pre")).to_have_text(
        saved["document"]["documents"][299]["content"]
    )
    assert server.app.casebooks.get(saved["id"]) == saved
    assert casebooks.draft_context(casebooks.build(saved["document"])) == before_packet
    expect(page.get_by_label("Project save state", exact=True)).to_have_text(
        "Project inputs saved at revision 2."
    )
    assert len(traffic) == filtered_traffic
    assert page.locator("#casebook-output").inner_text() == prepared_text
    page.screenshot(
        path=str(artifacts / (label + "-exact-reference-local-inspect.png"))
    )

    def open_question(index):
        row = page.locator(f'[data-question-scope-index="{index}"]')
        if row.get_attribute("open") is None:
            row.locator("summary").first.click()
        return row

    def navigate(label):
        page.get_by_role("button", name="Find a tool", exact=True).click()
        page.get_by_label("Find a Sinter tool", exact=True).fill(label)
        page.locator(".finder-results").get_by_text(label, exact=True).click()

    # Navigation retains the local view and already prepared report without
    # dirtying evidence; pending source inputs remain separate from both.
    search_for("/reference/125", 1, outside=3)
    selected_only.check()
    page.get_by_text("Add notes and references", exact=True).click()
    page.get_by_label("Source title", exact=True).fill("Fictional pending source")
    page.get_by_label("Paste a note, policy or reference", exact=True).fill(
        "Pending literal original 🐝"
    )
    navigate("Getting started")
    expect(
        page.get_by_role("heading", name="You do not need to be technical.", exact=True)
    ).to_be_visible()
    navigate("Community casebooks")
    expect(page.get_by_label("Project name", exact=True)).to_have_value(
        saved["document"]["title"]
    )
    page.get_by_text("Choose sources for each question", exact=True).click()
    open_question(0)
    expect(search).to_have_value("/reference/125")
    expect(selected_only).to_be_checked()
    expect(counts).to_contain_text("Showing 1 of 300 sources. 4 selected")
    expect(page.get_by_label("Source title", exact=True)).to_have_value(
        "Fictional pending source"
    )
    expect(
        page.get_by_label("Paste a note, policy or reference", exact=True)
    ).to_have_value("Pending literal original 🐝")
    assert page.locator("#casebook-output").inner_text() == prepared_text
    assert server.app.casebooks.get(saved["id"]) == saved
    page.get_by_role("button", name="Clear pending source", exact=True).click()
    clear = page.get_by_role("dialog", name="Clear this pending source?", exact=True)
    expect(clear).to_be_visible()
    clear.get_by_role("button", name="Clear pending source", exact=True).click()
    expect(clear).to_have_count(0)
    expect(page.get_by_label("Project save state", exact=True)).to_have_text(
        "Project inputs saved at revision 2."
    )
    filtered_traffic = len(traffic)

    # A deliberate change to Q2 may invalidate the report, but must not erase
    # Q1's independent display filter. Restore Q2's original explicit-none scope.
    search_for("duplicate", 2, outside=2)
    open_question(1)
    page.get_by_label("Sources for question 2", exact=True).select_option("all")
    open_question(0)
    expect(search).to_have_value("duplicate")
    expect(selected_only).to_be_checked()
    expect(counts).to_contain_text("Showing 2 of 300 sources. 4 selected")
    open_question(1)
    page.get_by_label("Sources for question 2", exact=True).select_option("selected")
    open_question(0)
    expect(search).to_have_value("duplicate")
    expect(selected_only).to_be_checked()
    search_for("", 4, outside=0)
    expect(counts).to_contain_text("Showing 4 of 300 sources. 4 selected in total")
    assert server.app.casebooks.get(saved["id"]) == saved
    assert len(traffic) == filtered_traffic

    # A hidden unselected checkbox cannot retain keyboard focus. Prefer the
    # next visible choice, then the previous, then the selected-only control.
    focus_expectations = [
        (ids[0], ids[1]),
        (ids[3], ids[2]),
        (ids[2], ids[1]),
        (ids[1], None),
    ]
    for removed_count, (identity, next_identity) in enumerate(focus_expectations, 1):
        checkbox = first.locator(
            f'[data-source-choice-id="{identity}"] input[type="checkbox"]'
        )
        checkbox.focus()
        checkbox.press("Space")
        expect(checkbox).not_to_be_checked()
        target = (
            selected_only
            if next_identity is None
            else first.locator(
                f'[data-source-choice-id="{next_identity}"] input[type="checkbox"]'
            )
        )
        expect(target).to_be_focused()
        remaining = 4 - removed_count
        wording = (
            "Related wording is not an answer."
            if remaining
            else "No source will be searched for this question."
        )
        expect(page.get_by_label("Question 1 source count", exact=True)).to_have_text(
            f"{remaining} source{'s' if remaining != 1 else ''} chosen; "
            f"{remaining} currently available. {wording}"
        )
        expect(counts).to_have_text(
            f"Showing {remaining} of 300 sources. {remaining} selected in total; "
            "0 selected outside this view."
        )
    expect(counts).to_have_text(
        "Showing 0 of 300 sources. 0 selected in total; 0 selected outside this view."
    )
    expect(page.get_by_label("Question 1 source count", exact=True)).to_contain_text(
        "No source will be searched"
    )
    expect(page.get_by_label("Project save state", exact=True)).to_contain_text(
        "Unsaved project changes"
    )
    assert server.app.casebooks.get(saved["id"]) == saved
    assert len(traffic) == filtered_traffic
    page.screenshot(path=str(artifacts / (label + "-selected-only-empty-focus.png")))
    page.get_by_label("Sources for question 1", exact=True).select_option("all")
    page.get_by_label("Sources for question 1", exact=True).select_option("selected")
    expect(selected_only).to_be_checked()
    expect(counts).to_contain_text("Showing 0 of 300 sources. 0 selected")
    expect(
        first.get_by_text(
            "No sources match this view. Clear the filter or turn off selected only. "
            "Filtering does not change your evidence choices.",
            exact=True,
        )
    ).to_be_visible()
    selected_only.uncheck()
    search_for("duplicate", 2, selected=0, outside=0)
    first.locator("summary").first.click()
    first.locator("summary").first.click()
    expect(search).to_have_value("duplicate")
    expect(counts).to_contain_text("Showing 2 of 300 sources. 0 selected")
    if label.startswith("1440"):
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        expect(search).to_have_value("duplicate")
        page.screenshot(path=str(artifacts / "resized-mobile-filter.png"))
        page.set_viewport_size({"width": 1440, "height": 1000})

    transfers = page.locator("details.card").filter(
        has=page.get_by_text("Backups and project removal", exact=True)
    )
    transfers.locator("summary").first.click()
    transfers.get_by_role("button", name="Refresh backup text", exact=True).click()
    backup_bytes = (
        page.get_by_label("Project backup text", exact=True).input_value().encode()
    )
    backup = json.loads(backup_bytes)
    assert backup["documents"] == saved["document"]["documents"]
    assert [row["source_ids"] for row in backup["question_scopes"]] == [[], []]
    assert "filter" not in json.dumps(backup["question_scopes"])
    assert len(traffic) == filtered_traffic
    page.get_by_role("button", name="Save project", exact=True).click()
    expect(page.get_by_label("Project save state", exact=True)).to_have_text(
        "Project inputs saved at revision 3."
    )
    expect(page.get_by_role("button", name="Save project", exact=True)).to_be_enabled()
    updated = server.app.casebooks.get(saved["id"])
    assert updated["document"]["schema"] == "sinter-casebook/v2"
    assert updated["document"]["question_scopes"] == backup["question_scopes"]
    assert updated["document"]["documents"] == saved["document"]["documents"]
    questions = page.get_by_label("What do you need to find out?", exact=True)
    lines = questions.input_value().splitlines()
    lines[:2] = reversed(lines[:2])
    questions.fill("\n".join(lines))
    open_question(0)
    expect(search).to_have_value("")
    expect(selected_only).not_to_be_checked()
    page.get_by_role("button", name="Save project", exact=True).click()
    expect(page.locator(".casebooks-page .notice.error")).to_contain_text(
        "Questions changed or moved"
    )
    assert server.app.casebooks.get(saved["id"]) == updated
    questions.fill(saved["document"]["questions"])
    page.get_by_label("Restore a casebook backup", exact=True).set_input_files(
        {
            "name": "fictional-filtered-originals.json",
            "mimeType": "application/json",
            "buffer": backup_bytes,
        }
    )
    replace = page.get_by_role(
        "dialog", name="Replace this unsaved editor?", exact=True
    )
    expect(replace).to_be_visible()
    replace.get_by_role("button", name="Replace editor", exact=True).click()
    expect(replace).to_have_count(0)
    expect(
        page.get_by_text("Backup opened as a new unsaved project.", exact=True)
    ).to_be_visible()
    open_question(0)
    expect(search).to_have_value("")
    expect(selected_only).not_to_be_checked()
    page.get_by_role("button", name="Save project", exact=True).click()
    expect(page.get_by_label("Project save state", exact=True)).to_have_text(
        "Project inputs saved at revision 1."
    )
    expect(page.get_by_role("button", name="Save project", exact=True)).to_be_enabled()
    restored = next(
        row
        for row in server.app.casebooks.list()
        if row["title"] == saved["document"]["title"] and row["id"] != saved["id"]
    )
    assert server.app.casebooks.get(restored["id"])["document"] == casebooks.validate(
        backup
    )
    assert server.app.casebooks.get(saved["id"]) == updated
    assert server.app.store.report(report_id) == historical
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    return {
        "passed": True,
        "viewport": label,
        "source_count": 300,
        "question_count": 20,
        "filtered_visible_choices": {
            "title": 2,
            "date": 1,
            "link": 1,
            "reference": 1,
            "body_only": 0,
            "selected_only": 4,
        },
        "raw_filter_timings_ms": timings,
        "hidden_ids_originals_history_packet_preserved": True,
        "next_previous_empty_focus": True,
        "explicit_none_backup_restore_stale_refusal": True,
        "filter_and_inspection_api_requests": 0,
        "unrelated_question_navigation_prepared_report_pending_inputs_preserved": True,
        "replaced_anchor_and_new_project_view_reset": True,
    }


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-private-source-filter-proof-"))
    artifacts.chmod(0o700)
    hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in PATHS
    }
    checks, errors, external, native_dialogs = [], [], [], []
    resources = {"browser_closed": False, "server_closed": False}
    with (
        tempfile.TemporaryDirectory(
            prefix="sinter-private-source-filter-data-"
        ) as data,
        patch.object(
            client, "_open", side_effect=AssertionError("No hosted calls")
        ) as remote,
        patch.object(
            client, "chat", side_effect=AssertionError("No model calls")
        ) as model,
    ):
        server = make_server(port=0, directory=data)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as driver:
                browser = launch_chromium(driver, args.chromium)
                try:
                    for width, height in [(1440, 1000), (390, 844)]:
                        label = f"{width}x{height}"
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
                        page.on(
                            "dialog",
                            lambda dialog: (
                                native_dialogs.append(dialog.type), dialog.dismiss()
                            ),
                        )
                        try:
                            checks.append(
                                run_flow(page, server, base, label, artifacts, expect)
                            )
                        except Exception as error:
                            checks.append(
                                {
                                    "passed": False,
                                    "viewport": label,
                                    "error": str(error),
                                    "traceback": traceback.format_exc(),
                                }
                            )
                            page.screenshot(
                                path=str(artifacts / (label + "-FAILED.png"))
                            )
                        finally:
                            context.close()
                finally:
                    browser.close()
                    resources["browser_closed"] = True
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
            resources["server_closed"] = not thread.is_alive()
        remote.assert_not_called()
        model.assert_not_called()
    unchanged = hashes == {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in PATHS
    }
    receipt = {
        "schema": "sinter-private-source-filter-proof/v1",
        "prototype_only": True,
        "source_root": str(ROOT),
        "source_sha256": hashes,
        "source_unchanged": unchanged,
        "checks": checks,
        "errors": errors,
        "external": external,
        "native_dialog_events": native_dialogs,
        "hosted_model_calls": 0,
        "real_workspace_mutations": 0,
        "resources": resources,
        "passed": all(row["passed"] for row in checks)
        and unchanged
        and not errors
        and not external
        and not native_dialogs
        and all(resources.values()),
    }
    target = artifacts / "filter-receipt.json"
    target.write_text(json.dumps(receipt, indent=2) + "\n")
    for path in artifacts.iterdir():
        path.chmod(0o600)
    print(target)
    print(json.dumps(checks))
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect retained private prototype evidence.")


if __name__ == "__main__":
    main()
