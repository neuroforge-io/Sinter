"""Fictional UI proof of casebook input save state, pending sources and recovery."""

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


def main(argv: list[str] | None = None) -> None:
    """Use real UI edits/downloads with fresh data and retain failures locally."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-casebook-save-state-proof-"))
    paths = (
        "src/sinter/web/casebooks.js",
        "src/sinter/web/casebook-drafts.js",
        "src/sinter/casebooks.py",
        "tools/casebook_save_state_browser.py",
    )
    hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths
    }
    results, errors, external = [], [], []
    resources = {"browser_closed": False, "server_closed": False}

    def guarded_page(browser, base, viewport):
        context = browser.new_context(viewport=viewport, reduced_motion="reduce")
        context.route(
            "**/*",
            lambda route: (
                route.continue_()
                if route.request.url.startswith(base + "/")
                else (external.append(route.request.url), route.abort())
            ),
        )
        page = context.new_page()
        page.set_default_timeout(8000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: dialog.accept())
        return context, page

    def save(page, revision):
        page.get_by_role("button", name="Save project", exact=True).click()
        expect(page.locator("[data-casebook-save-success]")).to_contain_text(
            f"Saved revision {revision}."
        )
        expect(page.get_by_label("Project save state", exact=True)).to_have_text(
            f"Project inputs saved at revision {revision}."
        )
        expect(
            page.get_by_role("button", name="Save project", exact=True)
        ).to_be_enabled()

    def enter_source(page, row):
        panel = page.locator("details").filter(
            has=page.get_by_label("Source title", exact=True)
        )
        if panel.get_attribute("open") is None:
            panel.locator("summary").first.click()
        for label, key in (
            ("Source title", "title"),
            ("Paste a note, policy or reference", "content"),
            ("Source date (optional)", "date"),
            ("Source link (optional)", "url"),
        ):
            page.get_by_label(label, exact=True).fill(row[key])

    with tempfile.TemporaryDirectory(prefix="sinter-casebook-save-state-data-") as data:
        with patch.object(
            client, "_open", side_effect=AssertionError("Offline fictional UI only")
        ) as remote:
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        for width, height in ((1440, 1000), (390, 844)):
                            label = f"{width}x{height}"
                            result = {
                                "check": "casebook-save-state-" + label,
                                "passed": False,
                            }
                            context, page = guarded_page(
                                browser, base, {"width": width, "height": height}
                            )
                            other_context = None
                            try:
                                title = "Fictional casebook save state " + label
                                page.goto(base + "/#casebooks")
                                state = page.get_by_label(
                                    "Project save state", exact=True
                                )
                                expect(state).to_contain_text("Project not saved yet.")
                                page.get_by_label("Project name", exact=True).fill(
                                    title
                                )
                                page.get_by_label(
                                    "What do you need to find out?", exact=True
                                ).fill("Has any support been approved?")
                                original = {
                                    "title": "Fictional initial note",
                                    "content": (
                                        "No support is approved. "
                                        "An owner is not assigned."
                                    ),
                                    "date": "",
                                    "url": "https://example.invalid/initial",
                                }
                                added = {
                                    "title": "Fictional second note <literal 🐝>",
                                    "content": (
                                        "Review is proposed only. No funding or "
                                        "e\u0301quipment owner is confirmed."
                                    ),
                                    "date": "2026-09-30",
                                    "url": "https://example.invalid/second",
                                }
                                enter_source(page, original)
                                page.get_by_role(
                                    "button", name="Add this source", exact=True
                                ).click()
                                save(page, 1)
                                saved_id = next(
                                    row["id"]
                                    for row in server.app.casebooks.list()
                                    if row["title"] == title
                                )
                                baseline = server.app.casebooks.get(saved_id)
                                assert len(baseline["document"]["documents"]) == 1
                                result["initial_save_exact"] = True

                                # A source still in its form must never appear saved.
                                saves, downloads = [], []
                                page.on(
                                    "request",
                                    lambda request: (
                                        saves.append(request.url)
                                        if request.url.endswith("/api/casebooks/save")
                                        else None
                                    ),
                                )
                                page.on(
                                    "download",
                                    lambda download: downloads.append(download),
                                )
                                enter_source(page, added)
                                expect(state).to_have_text(
                                    "Pending source is not added or saved. "
                                    "Add this source or clear it before saving."
                                )
                                expect(
                                    page.locator("[data-casebook-save-success]")
                                ).to_have_count(0)
                                page.get_by_role(
                                    "button", name="Save project", exact=True
                                ).click()
                                error_notice = page.locator(
                                    ".casebooks-page .notice.error"
                                )
                                expect(error_notice).to_contain_text(
                                    "You have a source that has not been added."
                                )
                                expect(
                                    page.get_by_label(
                                        "Paste a note, policy or reference", exact=True
                                    )
                                ).to_have_value(added["content"])
                                expect(
                                    page.get_by_label(
                                        "Paste a note, policy or reference", exact=True
                                    )
                                ).to_be_focused()
                                page.get_by_role(
                                    "button", name="Export project backup", exact=True
                                ).click()
                                expect(
                                    page.get_by_label(
                                        "Paste a note, policy or reference", exact=True
                                    )
                                ).to_be_focused()
                                assert not saves and not downloads
                                assert server.app.casebooks.get(saved_id) == baseline
                                retained_error = error_notice.inner_text()
                                page.get_by_label("Source title", exact=True).fill(
                                    added["title"]
                                )
                                expect(error_notice).to_have_text(retained_error)
                                result["pending_refusal_focused_and_preserved"] = True
                                page.get_by_role(
                                    "button", name="Clear pending source", exact=True
                                ).click()
                                expect(state).to_have_text(
                                    "Project inputs saved at revision 1."
                                )
                                expect(error_notice).to_have_text(retained_error)

                                # Adding the source changes only the editor until Save.
                                enter_source(page, added)
                                page.get_by_role(
                                    "button", name="Add this source", exact=True
                                ).click()
                                expect(state).to_contain_text(
                                    "Unsaved project changes."
                                )
                                expect(state).to_contain_text("Based on revision 1.")
                                expect(
                                    page.locator(".casebook-editor details.source")
                                ).to_have_count(2)
                                assert server.app.casebooks.get(saved_id) == baseline
                                page.screenshot(
                                    path=str(
                                        artifacts / (label + "-unsaved-source.png")
                                    )
                                )
                                save(page, 2)
                                expected = copy.deepcopy(baseline["document"])
                                expected["documents"].append(added)
                                expected = validate(expected)
                                assert (
                                    server.app.casebooks.get(saved_id)["document"]
                                    == expected
                                )
                                result["added_source_unsaved_then_saved_exact"] = True

                                # Ordinary project fields use the same dirty lifecycle.
                                recipient = "Fictional incoming review team 🐝"
                                page.get_by_label(
                                    "Recipient or audience", exact=True
                                ).fill(recipient)
                                expect(state).to_contain_text(
                                    "Unsaved project changes."
                                )
                                expect(
                                    page.locator("[data-casebook-save-success]")
                                ).to_have_count(0)
                                expected["recipient"] = recipient
                                expected = validate(expected)
                                save(page, 3)
                                assert (
                                    server.app.casebooks.get(saved_id)["document"]
                                    == expected
                                )
                                result["field_edit_save_reopen_exact"] = True
                                page.reload()
                                tile = page.locator(".casebook-tile").filter(
                                    has=page.get_by_text(title, exact=True)
                                )
                                tile.get_by_role(
                                    "button", name="Open project", exact=True
                                ).click()
                                expect(state).to_have_text(
                                    "Project inputs saved at revision 3."
                                )
                                expect(
                                    page.get_by_label(
                                        "Recipient or audience", exact=True
                                    )
                                ).to_have_value(recipient)
                                assert (
                                    server.app.casebooks.get(saved_id)["document"]
                                    == expected
                                )

                                # A real competing window must preserve pending edits.
                                other_context, other = guarded_page(
                                    browser, base, {"width": width, "height": height}
                                )
                                other.goto(base + "/#casebooks")
                                other.locator(".casebook-tile").filter(
                                    has=other.get_by_text(title, exact=True)
                                ).get_by_role(
                                    "button", name="Open project", exact=True
                                ).click()
                                expect(
                                    other.get_by_label("Project save state", exact=True)
                                ).to_have_text("Project inputs saved at revision 3.")
                                expect(
                                    other.get_by_label(
                                        "What do you need to find out?", exact=True
                                    )
                                ).to_have_value(expected["questions"])
                                remote_questions = "Which support remains unapproved?"
                                other.get_by_label(
                                    "What do you need to find out?", exact=True
                                ).fill(remote_questions)
                                save(other, 4)
                                remote_expected = copy.deepcopy(expected)
                                remote_expected["questions"] = remote_questions
                                remote_expected = validate(remote_expected)
                                pending_recipient = "Fictional unsaved conflict team"
                                page.get_by_label(
                                    "Recipient or audience", exact=True
                                ).fill(pending_recipient)
                                page.get_by_role(
                                    "button", name="Save project", exact=True
                                ).click()
                                expect(error_notice).to_contain_text(
                                    "This casebook changed in another window"
                                )
                                conflict_message = error_notice.inner_text()
                                further_question = "No new answer is established."
                                page.get_by_label(
                                    "What do you need to find out?", exact=True
                                ).fill(further_question)
                                expect(error_notice).to_have_text(conflict_message)
                                expect(state).to_contain_text(
                                    "Unsaved project changes."
                                )
                                assert (
                                    server.app.casebooks.get(saved_id)["document"]
                                    == remote_expected
                                ), json.dumps(
                                    {
                                        "actual": server.app.casebooks.get(saved_id),
                                        "expected": remote_expected,
                                    }
                                )
                                with page.expect_download() as download:
                                    page.get_by_role(
                                        "button",
                                        name="Export project backup",
                                        exact=True,
                                    ).click()
                                backup = Path(download.value.path()).read_bytes()
                                backup_expected = copy.deepcopy(expected)
                                backup_expected.update(
                                    recipient=pending_recipient,
                                    questions=further_question,
                                )
                                backup_expected = validate(backup_expected)
                                assert validate(json.loads(backup)) == backup_expected
                                result["conflict_error_edits_and_export_preserved"] = (
                                    True
                                )
                                page.screenshot(
                                    path=str(
                                        artifacts / (label + "-conflict-preserved.png")
                                    )
                                )

                                # Restore creates an unsaved copy without overwriting.
                                page.get_by_text(
                                    "Backups and project removal", exact=True
                                ).click()
                                page.get_by_label(
                                    "Restore a casebook backup", exact=True
                                ).set_input_files(
                                    {
                                        "name": "fictional-unsaved.json",
                                        "mimeType": "application/json",
                                        "buffer": backup,
                                    }
                                )
                                expect(state).to_contain_text(
                                    "Unsaved project changes."
                                )
                                expect(state).not_to_contain_text("Based on revision")
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
                                    if row["id"] != saved_id and row["title"] == title
                                )
                                assert (
                                    server.app.casebooks.get(restored["id"])["document"]
                                    == backup_expected
                                )
                                assert (
                                    server.app.casebooks.get(saved_id)["document"]
                                    == remote_expected
                                )
                                assert page.evaluate(
                                    "document.documentElement.scrollWidth <= innerWidth"
                                )
                                result["restored_separate_copy_exact"] = True
                                result["horizontal_overflow"] = False
                                result["passed"] = True
                            except Exception as error:
                                result["error"] = (
                                    type(error).__name__ + ": " + str(error)
                                )
                                result["traceback"] = traceback.format_exc()
                                page.screenshot(
                                    path=str(artifacts / (label + "-FAILED.png"))
                                )
                            finally:
                                if other_context:
                                    other_context.close()
                                context.close()
                                results.append(result)
                                print(json.dumps(result), flush=True)
                        remote.assert_not_called()
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
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths
    }
    receipt = {
        "schema": "sinter-casebook-save-state-browser/v1",
        "fixture_only": True,
        "checks": results,
        "source_sha256": hashes,
        "source_unchanged_during_run": unchanged,
        "browser_errors": errors,
        "external_requests": external,
        "model_operations_requested": 0,
        "resources": resources,
        "passed": all(row["passed"] for row in results)
        and not errors
        and not external
        and unchanged
        and all(resources.values()),
    }
    path = artifacts / "browser-receipt.json"
    path.write_text(json.dumps(receipt, indent=2))
    path.chmod(0o600)
    print(path)
    if not receipt["passed"]:
        raise SystemExit(
            "FAIL: inspect retained fictional casebook save-state receipt."
        )


if __name__ == "__main__":
    main()
