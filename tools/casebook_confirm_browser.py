"""Fictional in-page casebook decisions preserve work on cancellation and failure."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import threading
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.casebooks import validate  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

PATHS = (
    "src/sinter/web/confirm-action.js",
    "src/sinter/web/casebooks.js",
    "src/sinter/web/workspace.css",
    "src/sinter/web/api.js",
    "src/sinter/web/casebook-scope.js",
    "src/sinter/web/casebook-backup.js",
    "src/sinter/web/local-backup.js",
    "src/sinter/casebooks.py",
    "tools/casebook_confirm_browser.py",
)
SNAPSHOT = """() => ({
    fields: [...document.querySelectorAll(
      '.casebook-editor input:not([type=file]), ' +
      '.casebook-editor textarea, .casebook-editor select')]
      .map(el => ({label: el.labels?.[0]?.textContent, value: el.value,
        checked: el.checked})),
    sources: [...document.querySelectorAll('.casebook-editor details.source')]
      .map(el => el.textContent),
    scopes: document.querySelector('.casebook-editor > details')?.textContent,
    saveState: document.querySelector('[aria-label="Project save state"]').textContent,
    report: document.querySelector('#casebook-output').textContent,
    reportEditors: [...document.querySelectorAll('#casebook-output textarea')]
      .map(el => el.value)
})"""

COMPONENT = """async () => {
  const {confirmAction} = await import('/static/confirm-action.js');
  const options = {title:'Fictional helper decision',
    description:'No real work.', confirmLabel:'Proceed'};
  let decision = confirmAction(options), conflict = false;
  try { await confirmAction(options); } catch { conflict = true; }
  document.querySelector('.action-confirmation button').click();
  const cancel = await decision;
  decision = confirmAction(options);
  const local = document.querySelector('.action-confirmation');
  local.querySelector('button.primary').click();
  local.dispatchEvent(new Event('close'));
  const approved = await decision;
  decision = confirmAction(options);
  window.dispatchEvent(new Event('pagehide'));
  const hidden = await decision;
  const original = HTMLDialogElement.prototype.showModal;
  HTMLDialogElement.prototype.showModal = () => {
    throw Error('Fictional unsupported dialog');
  };
  let refused = false;
  try { await confirmAction(options); } catch { refused = true; }
  finally { HTMLDialogElement.prototype.showModal = original; }
  decision = confirmAction(options);
  document.querySelector('.action-confirmation button').click();
  const reusable = await decision;
  return {conflict, cancel, approved, hidden, refused, reusable,
    remaining:document.querySelectorAll('.action-confirmation').length};
}
"""


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import TimeoutError as BrowserTimeout
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-casebook-confirm-proof-"))
    artifacts.chmod(0o700)
    hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PATHS
    }
    errors, external, native, checks, hover_samples = [], [], [], [], []
    resources = {"browser_closed": False, "server_closed": False}

    def panel(page):
        area = page.locator("details.card").filter(
            has=page.get_by_text("Backups and project removal", exact=True)
        )
        if area.get_attribute("open") is None:
            area.locator("summary").first.click()
        return area

    def manual(page):
        panel(page)
        page.get_by_role("button", name="Refresh backup text", exact=True).click()
        return json.loads(page.get_by_label("Project backup text").input_value())

    def go_tool(page, label):
        # Mobile uses the visible tool finder, rather than hidden sidebar links.
        page.locator("#tool-finder-button").click()
        finder = page.get_by_role(
            "dialog", name="What would you like to do?", exact=True
        )
        finder.get_by_role("searchbox", name="Find a Sinter tool").fill(label)
        finder.get_by_role("button", name=label).click()
        expect(finder).not_to_be_visible()

    def assert_book(actual, expected):
        assert validate(actual) == validate(expected), json.dumps(
            {"actual": actual, "expected": expected}, ensure_ascii=False
        )
        assert actual["documents"] == expected["documents"]
        assert actual.get("question_scopes") == expected.get("question_scopes")

    def fill_pending(page):
        area = page.locator("details").filter(
            has=page.get_by_label("Source title", exact=True)
        )
        if area.get_attribute("open") is None:
            area.locator("summary").first.click()
        for label, value in (
            ("Source title", "Fictional pending duplicate 🐝"),
            (
                "Paste a note, policy or reference",
                "Original pending e\u0301 🐝 <literal>",
            ),
            ("Source date (optional)", "2026-09-30"),
            ("Source link (optional)", "https://example.invalid/pending"),
        ):
            page.get_by_label(label, exact=True).fill(value)

    def dialog(page, heading, width):
        local = page.get_by_role("dialog", name=heading, exact=True)
        expect(local).to_be_visible()
        expect(local.get_by_role("button", name="Cancel", exact=True)).to_be_focused()
        assert local.evaluate("el => !el.closest('.casebook-editor')")
        assert page.locator(".casebook-editor").evaluate("el => el.disabled")
        box = local.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= width
        assert page.evaluate("document.documentElement.scrollWidth") == width
        if heading == "Replace this unsaved editor?":
            expect(local).to_contain_text(
                "discards unsaved project changes and unadded sources"
            )
            expect(local).to_contain_text("My workspace for this session")
        if heading == "Remove this saved project?":
            accept = local.get_by_role(
                "button", name="Remove saved project", exact=True
            )
            bounds = accept.bounding_box()
            assert bounds
            # This pointer position made the global one-pixel hover lift
            # oscillate its own hit boundary every frame on the mobile journey.
            page.mouse.move(
                bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] - 0.5
            )
            frames = accept.evaluate("""async el => {
              const samples=[];
              for(let n=0;n<8;n++) {
                await new Promise(requestAnimationFrame);
                const b=el.getBoundingClientRect();
                samples.push({x:b.x,y:b.y,w:b.width,h:b.height,
                  transform:getComputedStyle(el).transform});
              }
              return samples;
            }""")
            hover_samples.append({"viewport_width": width, "frames": frames})
            assert len({tuple(frame.items()) for frame in frames}) == 1
            assert all(frame["transform"] == "none" for frame in frames)
        return local

    def finish(page, local, choice):
        local.get_by_role("button", name=choice, exact=True).click()
        expect(local).to_have_count(0)
        expect(page.get_by_label("Project name", exact=True)).to_be_enabled()

    with tempfile.TemporaryDirectory(prefix="sinter-casebook-confirm-data-") as data:
        with patch.object(
            client, "_open", side_effect=AssertionError("Fictional offline UI only")
        ) as remote:
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
                            result = {"viewport": label, "passed": False, "checks": []}
                            checks.append(result)
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
                            page.set_default_timeout(12000)
                            page.on(
                                "pageerror", lambda error: errors.append(str(error))
                            )
                            # Record and dismiss browser-chrome dialogs; never approve.
                            page.on(
                                "dialog",
                                lambda item: (native.append(item.type), item.dismiss()),
                            )
                            requests = []
                            page.on(
                                "request",
                                lambda item: (
                                    requests.append(
                                        {"url": item.url, "method": item.method}
                                    )
                                    if "/api/casebooks" in item.url
                                    else None
                                ),
                            )
                            try:
                                book = validate(
                                    {
                                        "title": "Fictional decision original " + label,
                                        "questions": (
                                            "Who is eligible?\nWhich costs need "
                                            "checking?"
                                        ),
                                        "document_type": "handover",
                                        "handover_evidence": "selected_appendix",
                                        "recipient": "Fictional incoming volunteers",
                                        "signatory": "Fictional reviewer",
                                        "sender_role": "Volunteer",
                                        "organisation": "Fictional community",
                                        "contact_details": "",
                                        "documents": [
                                            {
                                                "title": "Fictional duplicate",
                                                "content": (
                                                    (
                                                        "Eligibility and costs remain"
                                                        " unconfirmed. "
                                                    )
                                                    + f"Original {n} 🐝 e\u0301."
                                                ),
                                            }
                                            for n in range(3)
                                        ],
                                    }
                                )
                                book.update(
                                    schema="sinter-casebook/v2",
                                    question_scopes=[
                                        {
                                            "question_index": 0,
                                            "question": book["questions"].splitlines()[
                                                0
                                            ],
                                            "source_ids": [book["documents"][0]["id"]],
                                        },
                                        {
                                            "question_index": 1,
                                            "question": book["questions"].splitlines()[
                                                1
                                            ],
                                            "source_ids": [],
                                        },
                                    ],
                                )
                                book = validate(book)
                                original = server.app.casebooks.save(book)
                                other = server.app.casebooks.save(
                                    {
                                        "title": "Fictional destination " + label,
                                        "questions": "What remains unknown?",
                                        "recipient": "",
                                        "signatory": "",
                                        "sender_role": "",
                                        "organisation": "",
                                        "contact_details": "",
                                        "documents": [
                                            {
                                                "title": "Fictional destination note",
                                                "content": (
                                                    "No approval is confirmed. 🐝"
                                                ),
                                            }
                                        ],
                                    }
                                )
                                page.goto(base + "/#casebooks")

                                def open_saved(record):
                                    return (
                                        page.locator(".casebook-tile")
                                        .filter(
                                            has=page.get_by_text(
                                                record["document"]["title"], exact=True
                                            )
                                        )
                                        .get_by_role(
                                            "button", name="Open project", exact=True
                                        )
                                    )

                                open_saved(original).click()
                                expect(
                                    page.get_by_label("Project name", exact=True)
                                ).to_have_value(book["title"])
                                expect(
                                    page.locator(".action-confirmation")
                                ).to_have_count(0)
                                page.get_by_role(
                                    "button",
                                    name="Prepare source-only report",
                                    exact=True,
                                ).click()
                                expect(
                                    page.get_by_text(
                                        (
                                            "Ready to review. Source matches do "
                                            "not establish answers."
                                        ),
                                        exact=True,
                                    )
                                ).to_be_visible()
                                historical = {
                                    row["id"]: server.app.store.report(row["id"])
                                    for row in server.app.store.reports()
                                }
                                original = server.app.casebooks.get(original["id"])
                                pending_report = (
                                    "Fictional unsaved report text 🐝 e\u0301"
                                )
                                page.locator(
                                    "#casebook-output .export-menu > summary"
                                ).click()
                                page.get_by_role(
                                    "button", name="Edit draft", exact=True
                                ).click()
                                page.get_by_label("Edit your draft", exact=True).fill(
                                    pending_report
                                )
                                panel(page)
                                report_only = page.evaluate(SNAPSHOT)
                                report_requests = len(requests)
                                report_backup = json.dumps(
                                    book, ensure_ascii=False
                                ).encode()
                                for action in ("open", "new", "example", "backup"):
                                    if action == "open":
                                        open_saved(other).click()
                                    elif action == "new":
                                        page.get_by_role(
                                            "button", name="New project", exact=True
                                        ).click()
                                    elif action == "example":
                                        page.get_by_role(
                                            "button",
                                            name="Try a fictional community example",
                                            exact=True,
                                        ).click()
                                    else:
                                        page.get_by_label(
                                            "Restore a casebook backup", exact=True
                                        ).set_input_files(
                                            {
                                                "name": "fictional-report-only.json",
                                                "mimeType": "application/json",
                                                "buffer": report_backup,
                                            }
                                        )
                                    local = dialog(
                                        page, "Replace this unsaved editor?", width
                                    )
                                    finish(page, local, "Cancel")
                                    assert page.evaluate(SNAPSHOT) == report_only
                                    assert len(requests) == report_requests
                                    expect(
                                        page.get_by_label("Edit your draft", exact=True)
                                    ).to_have_value(pending_report)
                                result["checks"].append(
                                    "Report-only edits guard all four replacements."
                                )
                                result["checks"].append(
                                    "clean open; actual offline source report"
                                )
                                fill_pending(page)
                                panel(page)
                                before = page.evaluate(SNAPSHOT)
                                before_requests = len(requests)
                                backup_bytes = json.dumps(
                                    book, ensure_ascii=False
                                ).encode()
                                restore = page.get_by_label(
                                    "Restore a casebook backup", exact=True
                                )

                                # All four replacement callers require a real DOM
                                # decision.
                                for action, cancel in (
                                    ("open", "Cancel"),
                                    ("new", "Escape"),
                                    ("example", "Enter"),
                                    ("backup", "Cancel"),
                                ):
                                    if action == "open":
                                        open_saved(other).click()
                                    elif action == "new":
                                        page.get_by_role(
                                            "button", name="New project", exact=True
                                        ).click()
                                    elif action == "example":
                                        page.get_by_role(
                                            "button",
                                            name="Try a fictional community example",
                                            exact=True,
                                        ).click()
                                    else:
                                        restore.set_input_files(
                                            {
                                                "name": "fictional-scoped.json",
                                                "mimeType": "application/json",
                                                "buffer": backup_bytes,
                                            }
                                        )
                                    local = dialog(
                                        page, "Replace this unsaved editor?", width
                                    )
                                    if action == "open":
                                        page.keyboard.press("Tab")
                                        expect(
                                            local.get_by_role(
                                                "button",
                                                name="Replace editor",
                                                exact=True,
                                            )
                                        ).to_be_focused()
                                        page.keyboard.press("Tab")
                                        expect(
                                            local.get_by_role(
                                                "button", name="Cancel", exact=True
                                            )
                                        ).to_be_focused()
                                        page.keyboard.press("Shift+Tab")
                                        expect(
                                            local.get_by_role(
                                                "button",
                                                name="Replace editor",
                                                exact=True,
                                            )
                                        ).to_be_focused()
                                        page.keyboard.press("Shift+Tab")
                                    if cancel in ("Escape", "Enter"):
                                        page.keyboard.press(cancel)
                                        expect(local).to_have_count(0)
                                        expect(
                                            page.get_by_label(
                                                "Project name", exact=True
                                            )
                                        ).to_be_enabled()
                                    else:
                                        finish(page, local, "Cancel")
                                    assert page.evaluate(SNAPSHOT) == before, action
                                    assert len(requests) == before_requests, action
                                    assert (
                                        server.app.casebooks.get(original["id"])
                                        == original
                                    )
                                    assert (
                                        server.app.casebooks.get(other["id"]) == other
                                    )
                                    if action == "backup":
                                        assert restore.input_value() == ""
                                    result["checks"].append(
                                        action + " cancel exact; no destination request"
                                    )
                                page.screenshot(
                                    path=str(
                                        artifacts / (label + "-cancel-preserved.png")
                                    )
                                )

                                clear = page.get_by_role(
                                    "button", name="Clear pending source", exact=True
                                )
                                clear.click()
                                local = dialog(
                                    page, "Clear this pending source?", width
                                )
                                page.screenshot(
                                    path=str(
                                        artifacts / (label + "-clear-decision.png")
                                    )
                                )
                                finish(page, local, "Cancel")
                                assert page.evaluate(SNAPSHOT) == before
                                expect(clear).to_be_focused()
                                result["checks"].append(
                                    "pending source cancellation and focus exact"
                                )

                                # A failed destination preserves current report and
                                # pending originals.
                                destination = base + "/api/casebooks/" + other["id"]
                                page.route(
                                    destination,
                                    lambda route: route.fulfill(
                                        status=503,
                                        json={
                                            "error": "Fictional destination unavailable"
                                        },
                                    ),
                                )
                                open_saved(other).click()
                                local = dialog(
                                    page, "Replace this unsaved editor?", width
                                )
                                finish(page, local, "Replace editor")
                                expect(
                                    page.locator(".casebooks-page .notice.error")
                                ).to_contain_text("Fictional destination unavailable")
                                assert page.evaluate(SNAPSHOT) == before
                                page.unroute(destination)
                                result["checks"].append(
                                    (
                                        "failed saved GET preserves report, "
                                        "source, scope and pending inputs"
                                    )
                                )

                                # JSON parsing and server validation happen only after
                                # explicit approval.
                                for raw, failure in (
                                    (b"{not JSON", "JSON"),
                                    (
                                        json.dumps({"title": "No sources"}).encode(),
                                        "question",
                                    ),
                                ):
                                    restore.set_input_files(
                                        {
                                            "name": "fictional-invalid.json",
                                            "mimeType": "application/json",
                                            "buffer": raw,
                                        }
                                    )
                                    local = dialog(
                                        page, "Replace this unsaved editor?", width
                                    )
                                    finish(page, local, "Replace editor")
                                    expect(
                                        page.locator(".casebooks-page .notice.error")
                                    ).to_be_visible()
                                    assert page.evaluate(SNAPSHOT) == before, failure
                                    assert restore.input_value() == ""
                                result["checks"].append(
                                    (
                                        "malformed and refused backups preserve "
                                        "exact editor"
                                    )
                                )
                                large = artifacts / (
                                    label + "-oversized-fictional.json"
                                )
                                with large.open("wb") as handle:
                                    handle.write(b" " * 10000001)
                                n = len(requests)
                                restore.set_input_files(large)
                                expect(
                                    page.locator(".casebooks-page .notice.error")
                                ).to_contain_text("This backup is too large")
                                expect(
                                    page.locator(".action-confirmation")
                                ).to_have_count(0)
                                assert (
                                    len(requests) == n
                                    and page.evaluate(SNAPSHOT) == before
                                )
                                result["checks"].append(
                                    "oversized backup refused before prompt or request"
                                )

                                held = []
                                page.route(
                                    destination, lambda route: held.append(route)
                                )
                                trigger = open_saved(other)
                                trigger.click()
                                local = dialog(
                                    page, "Replace this unsaved editor?", width
                                )
                                local.get_by_role(
                                    "button", name="Replace editor", exact=True
                                ).click()
                                expect(local).to_have_count(0)
                                expect(
                                    page.get_by_label("Project name", exact=True)
                                ).to_be_disabled()
                                assert len(held) == 1
                                trigger.click()
                                page.evaluate("location.hash = '#library'")
                                expect(page).to_have_url(base + "/#casebooks")
                                page.keyboard.press("Control+k")
                                expect(page.get_by_role("dialog")).to_have_count(0)
                                assert (
                                    len(held) == 1 and page.evaluate(SNAPSHOT) == before
                                )
                                assert page.locator("#casebook-output").evaluate(
                                    "el => el.inert"
                                )
                                try:
                                    page.locator(
                                        "#casebook-output .export-menu > summary"
                                    ).click(timeout=500)
                                except BrowserTimeout:
                                    pass
                                else:
                                    raise AssertionError(
                                        "Report accepted edits during replacement"
                                    )
                                assert page.evaluate(SNAPSHOT) == before
                                held[0].fulfill(status=200, json=other)
                                expect(
                                    page.get_by_label("Project name", exact=True)
                                ).to_be_enabled()
                                expect(
                                    page.get_by_label("Project name", exact=True)
                                ).to_have_value(other["document"]["title"])
                                expect(trigger).to_be_focused()
                                assert_book(manual(page), other["document"])
                                go_tool(page, "My workspace")
                                page.get_by_role(
                                    "button", name="Open unsaved draft", exact=True
                                ).click()
                                expect(
                                    page.get_by_label("Edit your draft", exact=True)
                                ).to_have_value(pending_report)
                                go_tool(page, "Community casebooks")
                                expect(
                                    page.get_by_label("Project name", exact=True)
                                ).to_have_value(other["document"]["title"])
                                result["checks"].append(
                                    "Approved replace keeps report session recovery."
                                )
                                page.unroute(destination)
                                assert not page.locator("#casebook-output").evaluate(
                                    "el => el.inert"
                                )
                                result["checks"].append(
                                    (
                                        "slow GET locks editor/navigation and "
                                        "refuses overlapping replacement"
                                    )
                                )

                                result["checks"].append(
                                    "Pending GET blocks report editing; output unlocks."
                                )
                                assert not page.locator("#casebook-output").evaluate(
                                    "el => el.inert"
                                )
                                # Clean replacement does not prompt; the clone is exact
                                # and unsaved.
                                restore.set_input_files(
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
                                expect(
                                    page.locator(".action-confirmation")
                                ).to_have_count(0)
                                assert_book(manual(page), book)
                                expect(
                                    page.get_by_label("Project save state", exact=True)
                                ).to_contain_text("Unsaved project changes")
                                clone = manual(page)
                                open_saved(other).click()
                                local = dialog(
                                    page, "Replace this unsaved editor?", width
                                )
                                finish(page, local, "Cancel")
                                assert manual(page) == clone
                                result["checks"].append(
                                    (
                                        "scoped unsaved restore then Open "
                                        "cancellation preserves complete clone"
                                    )
                                )

                                # The explicit empty-list downgrade marker must not
                                # disappear on Cancel.
                                clear_marker = copy.deepcopy(book)
                                clear_marker.update(
                                    schema="sinter-casebook/v1", question_scopes=[]
                                )
                                restore.set_input_files(
                                    {
                                        "name": "fictional-clear.json",
                                        "mimeType": "application/json",
                                        "buffer": json.dumps(
                                            clear_marker, ensure_ascii=False
                                        ).encode(),
                                    }
                                )
                                local = dialog(
                                    page, "Replace this unsaved editor?", width
                                )
                                finish(page, local, "Replace editor")
                                expect(
                                    page.get_by_text(
                                        "Backup opened as a new unsaved project.",
                                        exact=True,
                                    )
                                ).to_be_visible()
                                assert_book(manual(page), clear_marker)
                                fill_pending(page)
                                marker_before = page.evaluate(SNAPSHOT)
                                open_saved(other).click()
                                local = dialog(
                                    page, "Replace this unsaved editor?", width
                                )
                                finish(page, local, "Cancel")
                                assert page.evaluate(SNAPSHOT) == marker_before
                                clear.click()
                                local = dialog(
                                    page, "Clear this pending source?", width
                                )
                                finish(page, local, "Clear pending source")
                                assert_book(manual(page), clear_marker)
                                assert (
                                    server.app.casebooks.get(original["id"]) == original
                                )
                                result["checks"].append(
                                    (
                                        "explicit clear marker and exact sources "
                                        "survive Cancel and pending Clear"
                                    )
                                )

                                page.get_by_role(
                                    "button", name="New project", exact=True
                                ).click()
                                local = dialog(
                                    page, "Replace this unsaved editor?", width
                                )
                                finish(page, local, "Replace editor")
                                empty = manual(page)
                                assert (
                                    empty["documents"] == []
                                    and "question_scopes" not in empty
                                )
                                page.get_by_label("Project name", exact=True).fill(
                                    "Fictional temporary editor"
                                )
                                page.get_by_role(
                                    "button",
                                    name="Try a fictional community example",
                                    exact=True,
                                ).click()
                                local = dialog(
                                    page, "Replace this unsaved editor?", width
                                )
                                finish(page, local, "Replace editor")
                                assert len(manual(page)["documents"]) == 3
                                result["checks"].append(
                                    (
                                        "New and example affirmative decisions "
                                        "replace only working editor"
                                    )
                                )

                                open_saved(other).click()
                                local = dialog(
                                    page, "Replace this unsaved editor?", width
                                )
                                finish(page, local, "Replace editor")
                                remove = panel(page).get_by_role(
                                    "button", name="Remove saved project", exact=True
                                )
                                remove_before = manual(page)
                                remove.click()
                                local = dialog(
                                    page, "Remove this saved project?", width
                                )
                                page.screenshot(
                                    path=str(
                                        artifacts / (label + "-remove-decision.png")
                                    )
                                )
                                finish(page, local, "Cancel")
                                assert manual(page) == remove_before
                                assert server.app.casebooks.get(other["id"]) == other
                                endpoint = base + "/api/casebooks/delete"
                                page.route(
                                    endpoint,
                                    lambda route: route.fulfill(
                                        status=400,
                                        json={"error": "Fictional removal conflict"},
                                    ),
                                )
                                remove.click()
                                local = dialog(
                                    page, "Remove this saved project?", width
                                )
                                finish(page, local, "Remove saved project")
                                expect(
                                    page.locator(".casebooks-page .notice.error")
                                ).to_contain_text("Fictional removal conflict")
                                assert manual(page) == remove_before
                                assert server.app.casebooks.get(other["id"]) == other
                                page.unroute(endpoint)
                                remove.click()
                                local = dialog(
                                    page, "Remove this saved project?", width
                                )
                                finish(page, local, "Remove saved project")
                                expect(
                                    page.get_by_text(
                                        (
                                            "Saved project removed. The current "
                                            "editor is kept as unsaved work."
                                        ),
                                        exact=True,
                                    )
                                ).to_be_visible()
                                assert manual(page) == remove_before
                                try:
                                    server.app.casebooks.get(other["id"])
                                except KeyError:
                                    pass
                                else:
                                    raise AssertionError(
                                        "Fictional record was not removed"
                                    )
                                assert (
                                    server.app.casebooks.get(original["id"]) == original
                                )
                                for identifier, saved in historical.items():
                                    assert server.app.store.report(identifier) == saved
                                result["checks"].append(
                                    (
                                        "Remove Cancel/error preserve saved "
                                        "identity; approved removal keeps "
                                        "editor/history"
                                    )
                                )

                                component = page.evaluate(COMPONENT)
                                assert component == {
                                    "conflict": True,
                                    "cancel": False,
                                    "approved": True,
                                    "hidden": False,
                                    "refused": True,
                                    "reusable": False,
                                    "remaining": 0,
                                }
                                result["component"] = component
                                result["checks"].append(
                                    (
                                        "helper settles once, rejects overlap, "
                                        "cancels pagehide, fails closed and "
                                        "remains reusable"
                                    )
                                )
                                assert not native and not errors and not external
                                result["passed"] = True
                            except Exception:
                                result["failure"] = traceback.format_exc()
                                page.screenshot(
                                    path=str(artifacts / (label + "-failure.png"))
                                )
                            finally:
                                context.close()
                    finally:
                        browser.close()
                        resources["browser_closed"] = True
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)
                server.app.close()
                resources["server_closed"] = not worker.is_alive()
            hosted = remote.call_count
    receipt = {
        "source_sha256": hashes,
        "checks": checks,
        "page_errors": errors,
        "external_requests": external,
        "native_dialog_events": native,
        "confirmation_hover_samples": hover_samples,
        "hosted_calls": hosted,
        "resources": resources,
        "installed_qualification": False,
        "passed": all(row["passed"] for row in checks)
        and not (errors or external or native or hosted)
        and all(resources.values()),
    }
    (artifacts / "browser-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    )
    print(artifacts)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if not receipt["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
