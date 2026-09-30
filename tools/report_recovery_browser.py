"""Real offline browser journeys for pending sources and unsaved document edits."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import threading
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
                    report.get_by_text("More options", exact=True).click()
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
                    report.get_by_role(
                        "button", name="Save to this computer", exact=True
                    ).click()
                    expect(report.get_by_role("alert")).to_contain_text(
                        "Fictional local save failure"
                    )
                    assert page.evaluate(warn)
                    assert not server.app.store.reports()
                    report.get_by_role(
                        "button", name="Save to this computer", exact=True
                    ).click()
                    expect(report).to_contain_text("Saved in My workspace")
                    expect(report).not_to_contain_text(
                        "Edits applied. Save this draft to keep them."
                    )
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
                    report.get_by_text("More options", exact=True).click()
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
                    report.get_by_role(
                        "button", name="Save to this computer", exact=True
                    ).click()
                    expect(report.get_by_role("alert")).to_contain_text(
                        "Apply or cancel"
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
                        report.get_by_text("More options", exact=True).click()
                        report.get_by_role(
                            "button", name="Edit draft", exact=True
                        ).click()
                        report.get_by_label("Edit your draft", exact=True).fill(text)
                        report.get_by_role(
                            "button", name="Apply edits", exact=True
                        ).click()

                    apply_text("First version sent to save.")
                    report.get_by_role(
                        "button", name="Save to this computer", exact=True
                    ).click()
                    page.wait_for_timeout(100)
                    assert len(held) == 1
                    assert (
                        held[0].request.post_data_json["report"]["document_edits"][
                            "markdown"
                        ]
                        == "First version sent to save."
                    )
                    apply_text("Newer version edited while saving.")
                    held[0].continue_()
                    expect(report).to_contain_text("Your newer edits are still unsaved")
                    assert page.evaluate(warn)
                    expect(
                        report.get_by_role(
                            "button", name="Save to this computer", exact=True
                        )
                    ).to_be_enabled()
                    checks.append(
                        "a delayed save records its exact snapshot "
                        "and leaves newer edits protected"
                    )
                    page.screenshot(
                        path=str(out / "report-recovery-unsaved-newer-edit.png"),
                        full_page=True,
                    )
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
                "file_sha256": {
                    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in [
                        "src/sinter/web/report-drafts.js",
                        "src/sinter/web/casebooks.js",
                        "src/sinter/web/reports.js",
                        "src/sinter/web/report-citations.js",
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
