"""Real offline browser journeys for pending sources and unsaved document edits."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    """Exercise the real local save service and recover edits without a model."""
    args = browser_arguments(__doc__, argv)
    started = time.perf_counter()
    from playwright.sync_api import expect, sync_playwright

    out = ROOT / "browser-artifacts"
    out.mkdir(exist_ok=True)
    receipt = out / "report-recovery-summary.json"
    receipt.write_text(json.dumps({"passed": False, "state": "running"}))
    checks: list[str] = []
    errors: list[str] = []
    external: list[str] = []
    warn = """() => {
        const event = new Event('beforeunload', {cancelable: true});
        window.dispatchEvent(event); return event.defaultPrevented;
    }"""
    with tempfile.TemporaryDirectory(prefix="sinter-report-recovery-") as data:
        with patch.object(
            client,
            "_open",
            side_effect=AssertionError(
                "Offline recovery attempted an external request."
            ),
        ) as network:
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 1000},
                        reduced_motion="reduce",
                        accept_downloads=True,
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
                    page.on("dialog", lambda dialog: dialog.accept())
                    page.goto(base + "/#casebooks")
                    page.get_by_role(
                        "button", name="Try a fictional community example"
                    ).click()
                    page.get_by_role("button", name="Save project", exact=True).click()
                    expect(
                        page.get_by_text("Saved revision 1.", exact=False)
                    ).to_be_visible()
                    assert not page.evaluate(warn)
                    page.get_by_text("Add notes and references", exact=True).click()
                    pending_content = (
                        "The quote is pending. No order has been approved."
                    )
                    pending = {
                        "Source title": "Fictional supplier reply",
                        "Paste a note, policy or reference": pending_content,
                        "Source date (optional)": "2026-09-30",
                        "Source link (optional)": "https://example.invalid/quote",
                    }
                    for label, value in pending.items():
                        page.get_by_label(label, exact=True).fill(value)
                    assert page.evaluate(warn)
                    page.get_by_role("link", name="Overview", exact=True).click()
                    page.get_by_role(
                        "link", name="Community casebooks", exact=True
                    ).click()
                    for label, value in pending.items():
                        expect(page.get_by_label(label, exact=True)).to_have_value(
                            value
                        )
                    checks.append(
                        "all four pending source fields survive navigation "
                        "and protect exit"
                    )
                    revision = server.app.casebooks.list()[0]["revision"]
                    for name in [
                        "Save project",
                        "Prepare source-only report",
                        "Export project backup",
                    ]:
                        page.get_by_role("button", name=name, exact=True).click()
                        expect(page.get_by_role("alert")).to_contain_text(
                            "source that has not been added"
                        )
                        assert server.app.casebooks.list()[0]["revision"] == revision
                        assert not server.app.jobs.list()
                    checks.append(
                        "save, prepare and backup refuse to omit a pending source"
                    )
                    page.get_by_role(
                        "button", name="Add this source", exact=True
                    ).click()
                    page.get_by_role("button", name="Save project", exact=True).click()
                    expect(
                        page.get_by_text("Saved revision 2.", exact=False)
                    ).to_be_visible()
                    assert not page.evaluate(warn)
                    saved = server.app.casebooks.get(
                        server.app.casebooks.list()[0]["id"]
                    )
                    assert (
                        saved["document"]["documents"][-1]["content"]
                        == pending["Paste a note, policy or reference"]
                    )
                    checks.append(
                        "explicit Add and save persist original source "
                        "and clear dirty state"
                    )
                    page.get_by_label("Prepare a", exact=True).select_option("handover")
                    page.get_by_role(
                        "button", name="Prepare source-only report", exact=True
                    ).click()
                    report = page.get_by_role("region", name="Your draft report")
                    expect(report).to_be_visible()
                    assert page.evaluate(
                        "document.activeElement.id === 'casebook-output'"
                    )
                    expect(report.get_by_label("Document save state")).to_contain_text(
                        "Prepared locally; not saved"
                    )
                    assert page.evaluate(warn)
                    page.get_by_role("link", name="My workspace", exact=True).click()
                    page.get_by_role(
                        "button", name="Open unsaved draft", exact=True
                    ).click()
                    report = page.get_by_role("region", name="Your draft report")
                    expect(report.get_by_label("Document save state")).to_have_text("Unsaved changes.")
                    expect(page.get_by_label("Find saved drafts", exact=True)).to_be_hidden()
                    assert page.evaluate(warn)
                    checks.append(
                        "unedited prepared report survives navigation under exit protection"
                    )
                    page.get_by_role(
                        "link", name="Community casebooks", exact=True
                    ).click()
                    report = page.get_by_role("region", name="Your draft report")
                    expect(report).to_be_visible()
                    report.get_by_role("tab", name="Evidence", exact=True).click()
                    citation = report.get_by_role(
                        "button", name=re.compile(r"^Show source:")
                    ).first
                    expect(citation).to_be_visible()
                    citation.click()
                    opened_source = report.locator(".source-jump[open]")
                    expect(opened_source).to_have_count(1)
                    expect(opened_source.locator("pre")).to_be_visible()
                    report.get_by_role("tab", name="Document", exact=True).click()
                    checks.append(
                        "casebook citations open their exact original source "
                        "despite the longer identity format"
                    )
                    report.locator(".export-menu > summary").click()
                    report.get_by_role("button", name="Edit draft", exact=True).click()
                    edited = (
                        "# Fictional handover\n\nNo order has been approved."
                        "\n\nA user-edited next step."
                    )
                    report.get_by_label("Edit your draft", exact=True).fill(edited)
                    assert page.evaluate(warn)
                    report.get_by_role("button", name="Apply edits", exact=True).click()
                    expect(report).to_contain_text(
                        "Edits applied. Save this draft to keep them."
                    )
                    page.get_by_role("button", name="Save project", exact=True).click()
                    expect(
                        page.get_by_text("This saves the project inputs", exact=False)
                    ).to_be_visible()
                    assert page.evaluate(warn), (
                        "Project save erased report dirty protection."
                    )
                    checks.append(
                        "prepared report receives focus; project saving "
                        "cannot erase report dirty state"
                    )
                    page.get_by_role("link", name="Overview", exact=True).click()
                    page.get_by_role("link", name="My workspace", exact=True).click()
                    page.get_by_role(
                        "button", name="Open unsaved draft", exact=True
                    ).click()
                    report = page.get_by_role("region", name="Your draft report")
                    expect(report).to_contain_text("A user-edited next step.")
                    report.get_by_role("tab", name="Evidence", exact=True).click()
                    expect(report).to_contain_text("No order has been approved.")
                    report.get_by_role("tab", name="Document", exact=True).click()
                    checks.append(
                        "applied edits are recoverable in My workspace "
                        "with unchanged original evidence"
                    )
                    save_posts = []

                    def record_save_request(request):
                        if request.method == "POST" and request.url == base + "/api/reports":
                            save_posts.append(request.post_data_json)

                    page.on("request", record_save_request)

                    def begin_save(label, *, additional=False, cancel_once=False):
                        before = len(save_posts)
                        control = report.get_by_role("button", name=label, exact=True)
                        control.click()
                        if additional:
                            choice = page.get_by_role("dialog", name="Save an additional copy?", exact=True)
                            expect(choice).to_be_visible()
                            assert len(save_posts) == before
                            if cancel_once:
                                choice.get_by_role("button", name="Cancel", exact=True).click()
                                expect(choice).to_be_hidden()
                                assert len(save_posts) == before
                                assert page.evaluate(warn)
                                control.click()
                                expect(choice).to_be_visible()
                                assert len(save_posts) == before
                            choice.get_by_role("button", name="Save new copy", exact=True).click()
                        else:
                            expect(page.get_by_role("dialog")).to_have_count(0)
                        return before

                    def show_saved_copies():
                        menu = report.locator(".export-menu")
                        if menu.get_attribute("open") is None:
                            menu.locator(":scope > summary").click()
                        before = len(save_posts)
                        report.get_by_role("button", name="Check saved copies", exact=True).click()
                        saved_filter = page.get_by_label("Find saved drafts", exact=True)
                        expect(saved_filter).to_be_visible()
                        expect(saved_filter).to_be_focused()
                        expect(report).to_be_visible()
                        assert len(save_posts) == before
                        return saved_filter

                    failures = []

                    def fail_once(route):
                        if route.request.method == "POST" and not failures:
                            failures.append(True)
                            route.fulfill(
                                status=503,
                                content_type="application/json",
                                body=json.dumps(
                                    {"error": "Fictional local save failure."}
                                ),
                            )
                        else:
                            route.continue_()

                    page.route("**/api/reports", fail_once)
                    rejections = []

                    def reject_once(route):
                        if route.request.method == "POST" and not rejections:
                            rejections.append(True)
                            route.fulfill(
                                status=400,
                                content_type="application/json",
                                body=json.dumps({"error": "Fictional rejected save."}),
                            )
                        else:
                            route.fallback()

                    page.route("**/api/reports", reject_once)
                    before_send = begin_save("Save draft")
                    expect(report.get_by_label("Document save state")).to_have_text(
                        "The latest save was rejected."
                    )
                    expect(report.get_by_label("Document save state")).not_to_contain_text(
                        "Save outcome unknown"
                    )
                    assert len(save_posts) == before_send + 1
                    assert page.evaluate(warn)
                    assert not server.app.store.reports()
                    page.unroute("**/api/reports", reject_once)
                    checks.append(
                        "observed rejection retains local draft without claiming an unknown write"
                    )
                    malformed_requests = []
                    for malformed in (None, {}, {"id": "not-a-saved-document-id"}):

                        def malformed_ack(route):
                            if route.request.method == "POST":
                                malformed_requests.append(route.request.post_data_json)
                                route.fulfill(
                                    status=201,
                                    content_type="application/json",
                                    body=json.dumps(malformed),
                                )
                            else:
                                route.fallback()

                        page.route("**/api/reports", malformed_ack)
                        count = len(malformed_requests)
                        before_send = begin_save(
                            "Save draft" if count == 0 else "Save an additional copy",
                            additional=count > 0, cancel_once=count == 1,
                        )
                        expect(report.get_by_label("Document save state")).to_have_text(
                            "Save outcome unknown. Check saved copies before another save."
                        )
                        expect(report.get_by_role("alert")).to_contain_text(
                            "valid saved-document acknowledgement"
                        )
                        assert len(malformed_requests) == count + 1
                        assert len(save_posts) == before_send + 1
                        assert page.evaluate(warn)
                        assert not server.app.store.reports()
                        if count == 0:
                            saved_filter = show_saved_copies()
                            expect(report).to_contain_text("A user-edited next step.")
                            assert len(malformed_requests) == count + 1
                            page.get_by_role("button", name="Return to open draft", exact=True).click()
                            expect(saved_filter).to_be_hidden()
                            expect(report).to_be_visible()
                            assert len(save_posts) == before_send + 1
                        page.unroute("**/api/reports", malformed_ack)
                    checks.append(
                        "null, absent and invalid saved IDs remain unconfirmed after one POST each"
                    )
                    before_send = begin_save("Save an additional copy", additional=True)
                    expect(report.get_by_role("alert")).to_contain_text(
                        "Fictional local save failure"
                    )
                    expect(report.get_by_label("Document save state")).to_have_text(
                        "Save outcome unknown. Check saved copies before another save."
                    )
                    assert len(save_posts) == before_send + 1
                    assert page.evaluate(warn)
                    assert not server.app.store.reports()
                    before_success = len(server.app.store.reports())
                    before_send = begin_save("Save an additional copy", additional=True)
                    expect(report).to_contain_text("Saved in My workspace")
                    expect(report.get_by_label("Document save state")).to_have_text("Saved locally.")
                    expect(report.get_by_role("button", name="Save new copy", exact=True)).to_be_hidden()
                    assert len(save_posts) == before_send + 1
                    assert len(server.app.store.reports()) == before_success + 1
                    expect(report).not_to_contain_text("Edits applied. Save this draft to keep them.")
                    assert not page.evaluate(warn)
                    assert (
                        server.app.store.report(server.app.store.reports()[0]["id"])[
                            "document_edits"
                        ]["markdown"]
                        == edited
                    )
                    checks.append(
                        "failed save retains edits; explicit successful save "
                        "alone clears exit protection"
                    )
                    page.unroute("**/api/reports", fail_once)
                    report.locator(".export-menu > summary").click()
                    report.get_by_role("button", name="Edit draft", exact=True).click()
                    report.get_by_label("Edit your draft", exact=True).fill(
                        "Unapplied fictional handover wording."
                    )
                    page.get_by_role("link", name="Overview", exact=True).click()
                    page.get_by_role("link", name="My workspace", exact=True).click()
                    page.get_by_role(
                        "button", name="Open unsaved draft", exact=True
                    ).click()
                    report = page.get_by_role("region", name="Your draft report")
                    expect(
                        report.get_by_label("Edit your draft", exact=True)
                    ).to_have_value("Unapplied fictional handover wording.")
                    expect(report.get_by_role("button", name="Save new copy", exact=True)).to_be_disabled()
                    expect(report.get_by_label("Document save state")).to_have_text(
                        "Apply or cancel the pending inputs before saving."
                    )
                    report.get_by_role(
                        "button", name="Cancel edits", exact=True
                    ).click()
                    assert not page.evaluate(warn)
                    checks.append(
                        "unapplied editor text survives navigation; save refuses "
                        "omission; cancel restores clean state"
                    )
                    held = []
                    page.route(
                        "**/api/reports",
                        lambda route: (
                            held.append(route)
                            if route.request.method == "POST"
                            else route.continue_()
                        ),
                    )

                    def apply_text(text: str) -> None:
                        report.locator(".export-menu > summary").click()
                        report.get_by_role(
                            "button", name="Edit draft", exact=True
                        ).click()
                        report.get_by_label("Edit your draft", exact=True).fill(text)
                        report.get_by_role(
                            "button", name="Apply edits", exact=True
                        ).click()

                    apply_text("First version sent to save.")
                    before_send = begin_save("Save new copy", additional=True)
                    page.wait_for_timeout(100)
                    assert len(held) == 1
                    assert len(save_posts) == before_send + 1
                    expect(report.get_by_label("Document save state")).to_have_text(
                        "Saving a new copy..."
                    )
                    expect(report.get_by_role("button", name="Saving new copy...", exact=True)).to_be_disabled()
                    assert (
                        held[0].request.post_data_json["report"]["document_edits"]["markdown"]
                        == "First version sent to save."
                    )
                    page.get_by_role("link", name="Overview", exact=True).click()
                    page.get_by_role("link", name="My workspace", exact=True).click()
                    page.get_by_role(
                        "button", name="Open unsaved draft", exact=True
                    ).click()
                    report = page.get_by_role("region", name="Your draft report")
                    expect(report.get_by_label("Document save state")).to_have_text(
                        "Saving a new copy..."
                    )
                    save = report.get_by_role("button", name="Saving new copy...", exact=True)
                    expect(save).to_be_disabled()
                    save.evaluate("node => {node.disabled = false; node.click();}")
                    page.wait_for_timeout(100)
                    assert len(held) == 1
                    assert len(save_posts) == before_send + 1
                    expect(page.get_by_role("dialog")).to_have_count(0)
                    apply_text("Newer version edited while saving.")
                    expect(report.get_by_label("Document save state")).to_have_text(
                        "Saving an earlier version. Newer edits are unsaved."
                    )
                    held[0].continue_()
                    expect(report.get_by_label("Document save state")).to_have_text("Unsaved changes.")
                    document = report.get_by_role(
                        "tabpanel", name="Document", exact=True
                    )
                    expect(document).to_contain_text(
                        "Newer version edited while saving."
                    )
                    expect(document).not_to_contain_text("First version sent to save.")
                    assert (
                        server.app.store.report(server.app.store.reports()[0]["id"])[
                            "document_edits"
                        ]["markdown"]
                        == "First version sent to save."
                    )
                    assert page.evaluate(warn)
                    expect(report.get_by_role("button", name="Save new copy", exact=True)).to_be_enabled()
                    checks.append(
                        "a delayed save records its exact snapshot "
                        "and leaves newer edits protected"
                    )
                    checks.append(
                        "reopened pending view prevents a second POST and refreshes when the first settles"
                    )
                    page.screenshot(
                        path=str(out / "report-recovery-unsaved-newer-edit.png"),
                        full_page=True,
                    )
                    page.unroute("**/api/reports")
                    page.evaluate("""async () => {
                        const drafts = await import('/static/report-drafts.js');
                        const reports = await import('/static/reports.js');
                        const report = drafts.unsavedReportDrafts()[0].report;
                        document.querySelector('.report-area').replaceWith(reports.renderReport(
                            report, {onSaved: async () => {throw new Error('Fictional refresh failure.');}}
                        ));
                    }""")
                    report = page.get_by_role("region", name="Your draft report")
                    before_refresh_save = len(server.app.store.reports())
                    before_send = begin_save("Save to My workspace", additional=True)
                    expect(
                        report.get_by_role("note").filter(
                            has_text="Fictional refresh failure"
                        )
                    ).to_contain_text(
                        "The submitted document was saved, but refreshing the view failed"
                    )
                    expect(report.get_by_label("Document save state")).to_have_text(
                        "Saved locally in My workspace."
                    )
                    assert len(save_posts) == before_send + 1
                    assert len(server.app.store.reports()) == before_refresh_save + 1
                    assert not page.evaluate(warn)
                    assert (
                        server.app.store.report(server.app.store.reports()[0]["id"])[
                            "document_edits"
                        ]["markdown"]
                        == "Newer version edited while saving."
                    )
                    checks.append(
                        "throwing refresh callback cannot relabel acknowledged persistence or replay a save"
                    )
                    page.evaluate("""async () => {
                        const drafts = await import('/static/report-drafts.js');
                        const reports = await import('/static/reports.js');
                        const old = document.querySelector('.report-area');
                        const report = {title: 'Fictional post-ack UI failure',
                            markdown: 'A complete locally entered finding.',
                            document_markdown: 'A complete locally entered finding.', sources: []};
                        old.replaceWith(reports.renderReport(report));
                        const status = document.querySelector('.document-save-state');
                        const descriptor = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
                        let failed = false;
                        Object.defineProperty(status, 'textContent', {configurable: true,
                            get() {return descriptor.get.call(this);},
                            set(value) {
                                if (!failed && value === 'Saved locally in My workspace.') {
                                    failed = true; throw new Error('Fictional first post-ack refresh failure.');
                                }
                                descriptor.set.call(this, value);
                            }
                        });
                    }""")
                    report = page.get_by_role("region", name="Your draft report")
                    writes = []

                    def count_write(route):
                        if route.request.method == "POST":
                            writes.append(route.request.post_data_json)
                        route.continue_()

                    page.route("**/api/reports", count_write)
                    report.get_by_role(
                        "button", name="Save to My workspace", exact=True
                    ).click()
                    expect(
                        report.get_by_role("note").filter(
                            has_text="Fictional first post-ack refresh failure"
                        )
                    ).to_contain_text("Fictional first post-ack refresh failure")
                    expect(report.get_by_label("Document save state")).to_have_text(
                        "Saved locally in My workspace."
                    )
                    assert len(writes) == 1
                    assert not page.evaluate(warn)
                    checks.append(
                        "first post-ack view failure keeps confirmed save state and sends exactly one POST"
                    )

                    # A real downloaded report restores independently of the editor.
                    # A committed write with a deliberately lost acknowledgement
                    # must not be replayed as if nothing reached local storage.
                    page.close()
                    page = context.new_page()
                    page.set_default_timeout(7000)
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("dialog", lambda dialog: dialog.accept())
                    page.on("request", record_save_request)
                    source_row = next(
                        row for row in server.app.store.reports()
                        if server.app.store.report(row["id"]).get("sources")
                    )
                    original = server.app.store.report(source_row["id"])
                    page.goto(base + "/#library")
                    page.get_by_label("Find saved drafts", exact=True).fill(source_row["id"])
                    page.get_by_role("button", name="Open draft", exact=True).click()
                    report = page.get_by_role("region", name="Your draft report")
                    expect(page.get_by_label("Find saved drafts", exact=True)).to_be_hidden()
                    report.locator(".export-menu > summary").click()
                    with page.expect_download() as downloading:
                        report.get_by_role("button", name="Download evidence pack", exact=True).click()
                    downloaded = Path(data) / "restore-fixture.json"
                    downloading.value.save_as(downloaded)
                    exported = json.loads(downloaded.read_text(encoding="utf-8"))
                    assert exported == original
                    report.get_by_role("button", name="Edit draft", exact=True).click()
                    preserved_editor = "KEEP CURRENT EDITOR — not applied or included in the backup."
                    report.get_by_label("Edit your draft", exact=True).fill(preserved_editor)
                    show_saved_copies()
                    expect(report.get_by_label("Edit your draft", exact=True)).to_have_value(preserved_editor)
                    page.get_by_text("Restore draft JSON", exact=True).click()
                    selected = page.get_by_label("Choose draft JSON", exact=True)
                    restore = page.get_by_role("button", name="Restore as a new saved copy", exact=True)
                    count_before = len(server.app.store.reports())
                    selected.set_input_files(str(downloaded))
                    expect(page.get_by_label("Restored wording preview", exact=True)).to_be_visible()
                    expect(restore).to_be_enabled()
                    expect(report.get_by_label("Edit your draft", exact=True)).to_have_value(preserved_editor)
                    assert len(server.app.store.reports()) == count_before
                    selected.set_input_files({
                        "name": "oversized-unicode.json", "mimeType": "application/json",
                        "buffer": json.dumps(
                            {"title": "Oversized Unicode", "markdown": "🐝" * 500_001},
                            ensure_ascii=False,
                        ).encode("utf-8"),
                    })
                    expect(restore).to_be_disabled()
                    expect(page.get_by_role("alert")).to_contain_text("2,000,000 bytes")
                    assert len(server.app.store.reports()) == count_before
                    selected.set_input_files(str(downloaded))
                    expect(restore).to_be_enabled()
                    attempts = []
                    restored_ids = []
                    fail_refresh = [False]

                    def restore_reply(route):
                        if route.request.method == "POST":
                            attempts.append(route.request.post_data_json)
                            response = route.fetch()
                            assert response.status == 201
                            restored_ids.append(response.json()["id"])
                            if len(attempts) == 1:
                                route.abort("failed")
                            else:
                                fail_refresh[0] = True
                                route.fulfill(response=response)
                        elif fail_refresh[0]:
                            fail_refresh[0] = False
                            route.fulfill(
                                status=503, content_type="application/json",
                                body=json.dumps({"error": "Fictional post-restore refresh failure"}),
                            )
                        else:
                            route.continue_()

                    page.route("**/api/reports", restore_reply)
                    restore.click()
                    state = page.get_by_label("Draft restore state", exact=True)
                    expect(state).to_contain_text("Save not confirmed")
                    additional = page.get_by_role("button", name="Restore an additional copy", exact=True)
                    expect(additional).to_be_disabled()
                    assert len(attempts) == 1
                    assert len(server.app.store.reports()) == count_before + 1
                    assert server.app.store.report(restored_ids[0]) == exported
                    assert server.app.store.report(source_row["id"]) == original
                    expect(report.get_by_label("Edit your draft", exact=True)).to_have_value(preserved_editor)
                    assert page.evaluate(warn)
                    check_saved = page.get_by_role("button", name="Check saved list before retrying", exact=True)
                    check_saved.click()
                    expect(additional).to_be_enabled()
                    expect(page.get_by_label('Find saved drafts', exact=True)).to_have_value('')
                    expect(page.get_by_text('Reference ' + restored_ids[0][:8], exact=True)).to_be_visible()
                    assert len(attempts) == 1
                    additional.click()
                    page.get_by_role("dialog").get_by_role("button", name="Cancel", exact=True).click()
                    assert len(attempts) == 1

                    pending_copy = page.get_by_role("region", name="Unsaved document or form work").locator(
                        "article"
                    ).filter(has_text="Save not confirmed")
                    pending_copy.get_by_role("button", name="Open unsaved draft", exact=True).click()
                    page.get_by_role("dialog").get_by_role("button", name="Cancel", exact=True).click()
                    expect(report.get_by_label("Edit your draft", exact=True)).to_have_value(preserved_editor)
                    pending_copy.get_by_role("button", name="Open unsaved draft", exact=True).click()
                    page.get_by_role("dialog").get_by_role("button", name="Open selected draft", exact=True).click()
                    report = page.get_by_role("region", name="Your draft report")
                    report.get_by_role("button", name="Edit draft", exact=True).click()
                    report.get_by_label("Edit your draft", exact=True).fill("UNAPPLIED IMPORTED TEXT")
                    show_saved_copies()
                    expect(report.get_by_label("Edit your draft", exact=True)).to_have_value("UNAPPLIED IMPORTED TEXT")
                    expect(additional).to_be_disabled()
                    assert len(attempts) == 1
                    report.get_by_role("button", name="Cancel edits", exact=True).click()
                    check_saved.click()
                    expect(additional).to_be_enabled()
                    additional.click()
                    page.get_by_role("dialog").get_by_role(
                        "button", name="Restore additional copy", exact=True
                    ).click()
                    expect(state).to_contain_text("Restored copy acknowledged")
                    expect(page.get_by_role("note").filter(
                        has_text="Fictional post-restore refresh failure"
                    )).to_contain_text("Do not restore again to refresh")
                    assert len(attempts) == 2
                    assert len(set(restored_ids)) == 2
                    assert len(server.app.store.reports()) == count_before + 2
                    for saved_id in restored_ids:
                        assert server.app.store.report(saved_id) == exported
                    expect(page.get_by_role("button", name="Restored to My workspace", exact=True)).to_be_disabled()
                    report.get_by_role("button", name="Edit draft", exact=True).click()
                    report.get_by_label("Edit your draft", exact=True).fill("Later applied imported wording.")
                    report.get_by_role("button", name="Apply edits", exact=True).click()
                    expect(report.get_by_role("button", name="Save new copy", exact=True)).to_be_enabled()
                    expect(page.get_by_role("button", name="Restored to My workspace", exact=True)).to_be_disabled()
                    assert len(attempts) == 2
                    page.screenshot(path=str(out / "report-json-restoration.png"), full_page=True)
                    show_saved_copies()
                    expect(report).to_contain_text("Later applied imported wording.")
                    assert len(attempts) == 2
                    original_pending = page.get_by_role("region", name="Unsaved document or form work").locator(
                        "article"
                    ).filter(has_text="Draft text is waiting to be applied")
                    original_pending.get_by_role("button", name="Open unsaved draft", exact=True).click()
                    page.get_by_role("dialog").get_by_role("button", name="Open selected draft", exact=True).click()
                    expect(page.get_by_label("Edit your draft", exact=True)).to_have_value(preserved_editor)
                    assert len(attempts) == 2
                    assert server.app.store.report(source_row["id"]) == original
                    checks.extend([
                        "actual downloaded report stages locally without replacing pending editor text",
                        "oversized Unicode selection clears candidate without writing",
                        "real committed restore with lost acknowledgement remains uncertain without replay",
                        "list check and cancelled copy decision never repeat the write",
                        "unapplied imported text blocks retry; original editor stays recoverable",
                        "explicit additional copy preserves all evidence with a distinct identity",
                        "post-ack refresh failure and later edits cannot re-enable Restore",
                    ])
                    page.unroute("**/api/reports", restore_reply)

                    assert not errors, errors
                    assert not external, external
                    network.assert_not_called()
                    browser.close()
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
    receipt.write_text(
        json.dumps(
            {
                "schema": "sinter-report-recovery-browser/v1",
                "passed": True,
                "checks": checks,
                "external_requests": external,
                "browser_errors": errors,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "file_sha256": {
                    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in [
                        "src/sinter/web/report-drafts.js",
                        "src/sinter/web/casebooks.js",
                        "src/sinter/web/reports.js",
                        "src/sinter/web/report-citations.js",
                        "src/sinter/web/report-backup.js",
                        "src/sinter/web/saved-report-restore.js",
                        "src/sinter/web/library.js",
                        "src/sinter/web/saved-report-list.js",
                    ]
                },
            },
            indent=2,
        )
    )
    print(
        f"PASS: {len(checks)} offline report/source recovery journeys; "
        "no external calls."
    )


if __name__ == "__main__":
    main()
