"""Offline fictional focused-copy UI: selection, Cancel and uncertain one-shot Save.

Uses the licensed garden example and a disposable local workspace. No provider,
account, model, download or installed-release qualification is exercised.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    """Retain actual fictional source screenshots and request outcomes."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-campaign-focus-"))
    paths = (
        "src/sinter/campaigns.py",
        "src/sinter/runtime.py",
        "src/sinter/runtime_routes.py",
        "src/sinter/web/campaigns.js",
        "src/sinter/web/campaigns.css",
        "src/sinter/web/api.js",
        "tools/campaign_focus_browser.py",
    )
    before = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths
    }
    cases, errors, external = [], [], []
    closed = {"browser": False, "context": False, "server": False}
    fixture = json.loads((ROOT / "examples/offline-garden/campaign.json").read_text())
    selected = fixture["opportunities"][0]["name"]
    # The requested route follows an earlier linked dependency in original order.
    fixture["opportunities"].reverse()
    fixture["answers"].append(
        {
            "opportunity": selected,
            "label": "Unconfirmed answer",
            "text": "Held exact draft 🌱 <not HTML>. No application confirmed.",
            "limit": 20,
            "status": "draft",
        }
    )
    fixture["communications"] = [
        {
            "opportunity": selected,
            "direction": "incoming",
            "status": "received",
            "date": "2026-09-12",
            "content": "Historical programme response.",
        },
        {
            "opportunity": selected,
            "direction": "outgoing",
            "status": "draft",
            "date": "",
            "content": "Still unsent. Do not guess costs.",
        },
    ]
    fixture["assets"] = [
        {
            "name": "Fictional shared garden product",
            "funding_opportunities": [row["name"] for row in fixture["opportunities"]],
        }
    ]
    with tempfile.TemporaryDirectory(prefix="sinter-focused-workspace-") as data:
        with (
            patch.object(
                client, "_open", side_effect=AssertionError("Offline only")
            ) as remote,
            patch.object(client, "_load_key", side_effect=AssertionError("No keys")),
        ):
            server = make_server(port=0, directory=data)
            original = server.app.campaigns.save(fixture)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        context = browser.new_context(
                            viewport={"width": 390, "height": 844},
                            service_workers="block",
                        )
                        context.route(
                            "**/*",
                            lambda route: (
                                route.continue_()
                                if route.request.url.startswith(base + "/")
                                else (external.append(route.request.url), route.abort())
                            ),
                        )
                        context.on(
                            "page",
                            lambda page: page.on(
                                "pageerror", lambda e: errors.append(str(e))
                            ),
                        )
                        page = context.new_page()
                        page.set_default_timeout(8000)
                        page.goto(base + "/#campaigns")
                        expect(
                            page.get_by_role("heading", name=selected, exact=True)
                        ).to_be_visible()
                        entry = page.get_by_role(
                            "button", name="Make focused campaign…", exact=True
                        )
                        entry.click()
                        dialog = page.get_by_role(
                            "dialog", name="Make a focused campaign"
                        )
                        dialog.get_by_label("Name for the focused campaign").fill(
                            "Fictional focused garden"
                        )
                        with page.expect_response(
                            base + "/api/campaigns/focus"
                        ) as reply:
                            dialog.get_by_role(
                                "button", name="Preview selected material"
                            ).click()
                        result = reply.value.json()
                        assert (
                            result["document"]["answers"][0]["text"]
                            == fixture["answers"][-1]["text"]
                        )
                        dialog.get_by_text(
                            "Answers: 1 included, 1 omitted", exact=True
                        ).click()
                        answer = dialog.get_by_text(
                            fixture["answers"][-1]["text"], exact=True
                        )
                        expect(answer).to_be_visible()
                        answer.scroll_into_view_if_needed()
                        answer_box = answer.bounding_box()
                        footer_box = dialog.locator(
                            ":scope > .button-row"
                        ).bounding_box()
                        layout = {
                            "answer": answer_box,
                            "footer": footer_box,
                            "body": dialog.locator(".campaign-focused-body").evaluate(
                                "el => ({height: el.clientHeight, "
                                "scrollHeight: el.scrollHeight, "
                                "scrollTop: el.scrollTop, "
                                "overflowY: getComputedStyle(el).overflowY})"
                            ),
                        }
                        (artifacts / "selected-material-390-layout.json").write_text(
                            json.dumps(layout, indent=2) + "\n"
                        )
                        page.screenshot(
                            path=str(artifacts / "selected-material-390-viewport.png")
                        )
                        assert answer_box and footer_box
                        assert 0 <= answer_box["y"]
                        assert answer_box["y"] + answer_box["height"] <= footer_box["y"]
                        assert not dialog.locator("img").count()
                        page.screenshot(
                            path=str(artifacts / "selected-material-390.png"),
                            full_page=True,
                        )
                        dialog.get_by_role("button", name="Cancel", exact=True).click()
                        expect(page.locator(".campaign-focused-copy")).to_have_count(0)
                        expect(page.locator(".campaign-focus-heading h3")).to_have_text(
                            selected
                        )
                        assert server.app.campaigns.get(original["id"]) == original
                        assert len(server.app.campaigns.list()) == 1
                        cases.append(
                            "Cancel after actual material preview retains original "
                            "and creates no record"
                        )

                        page.locator(".campaign-details > summary").click()
                        page.get_by_label("Campaign name", exact=True).fill(
                            "Fictional original with unsaved edits"
                        )
                        page.locator(".campaign-details > summary").click()

                        entry.click()
                        dialog.get_by_label("Name for the focused campaign").fill(
                            "Fictional focused garden"
                        )
                        dialog.get_by_label(
                            "Include linked products and IP evidence, "
                            "keeping all their route links"
                        ).check()
                        dialog.get_by_role(
                            "button", name="Preview selected material"
                        ).click()
                        expect(
                            dialog.get_by_text(
                                "Additional route records are included", exact=False
                            )
                        ).to_be_visible()
                        dialog.get_by_label("Name for the focused campaign").fill(
                            "Fictional final focus"
                        )
                        expect(
                            dialog.get_by_role(
                                "button", name="Open unsaved focused campaign"
                            )
                        ).to_be_disabled()
                        dialog.get_by_role(
                            "button", name="Preview selected material"
                        ).click()
                        expect(
                            dialog.get_by_role(
                                "button", name="Open unsaved focused campaign"
                            )
                        ).to_be_enabled()
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        )
                        observed_dialogs = []

                        def refuse_replacement(prompt):
                            observed_dialogs.append(prompt.message)
                            prompt.dismiss()

                        page.on("dialog", refuse_replacement)
                        dialog.get_by_role(
                            "button", name="Open unsaved focused campaign"
                        ).click()
                        page.remove_listener("dialog", refuse_replacement)
                        assert len(observed_dialogs) == 1
                        assert "unsaved campaign edits" in observed_dialogs[0]
                        expect(dialog).to_be_visible()
                        assert server.app.campaigns.get(original["id"]) == original
                        with page.expect_download() as backup:
                            dialog.get_by_role(
                                "button", name="Download original snapshot backup"
                            ).click()
                        backup_path = artifacts / "original-unsaved-snapshot.json"
                        backup.value.save_as(backup_path)
                        assert json.loads(backup_path.read_text())["title"] == (
                            "Fictional original with unsaved edits"
                        )
                        page.once("dialog", lambda prompt: prompt.accept())
                        dialog.get_by_role(
                            "button", name="Open unsaved focused campaign"
                        ).click()
                        expect(page.locator(".campaign-focused-copy")).to_have_count(0)
                        expect(page.locator(".campaign-focus-heading h3")).to_have_text(
                            selected
                        )
                        expect(
                            page.get_by_text("Unsaved changes", exact=True)
                        ).to_be_visible()
                        assert len(server.app.campaigns.list()) == 1
                        cases.append(
                            "Explicit dependencies and changed options require "
                            "fresh preview; opening is unsaved and keeps the "
                            "requested second route selected"
                        )

                        held = []
                        page.route(
                            "**/api/campaigns/save", lambda route: held.append(route)
                        )
                        with patch.object(
                            server.app.campaigns,
                            "save",
                            wraps=server.app.campaigns.save,
                        ) as save:
                            page.get_by_role(
                                "button", name="Save campaign", exact=True
                            ).click()
                            expect(
                                page.get_by_role(
                                    "button", name="Save campaign", exact=True
                                )
                            ).to_be_disabled()
                            assert len(held) == 1
                            actual = held[0].fetch().json()
                            held[0].abort()
                            expect(
                                page.locator(".campaign-save-feedback")
                            ).to_contain_text("The save may have finished")
                            expect(
                                page.get_by_role(
                                    "button", name="Save campaign", exact=True
                                )
                            ).to_be_enabled()
                            assert len(held) == save.call_count == 1
                            assert save.call_args.args[1:] == (None, None)
                            assert (
                                actual["id"] != original["id"]
                                and actual["revision"] == 1
                            )
                            assert (
                                actual["document"]["communications"]
                                == original["document"]["communications"]
                            )
                            assert (
                                actual["document"]["opportunities"]
                                == (original["document"]["opportunities"])
                            )
                            assert server.app.campaigns.get(original["id"]) == original
                            assert len(server.app.campaigns.list()) == 2
                        page.screenshot(
                            path=str(artifacts / "uncertain-save-390.png"),
                            full_page=True,
                        )
                        page.screenshot(
                            path=str(artifacts / "uncertain-save-390-viewport.png")
                        )
                        cases.append(
                            "Pending Save disabled; lost successful acknowledgement "
                            "retained; one new-ID write, no replay"
                        )
                        assert not errors and not external
                        remote.assert_not_called()
                        context.close()
                        closed["context"] = True
                    finally:
                        browser.close()
                        closed["browser"] = True
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
                closed["server"] = not thread.is_alive()
    after = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths
    }
    assert before == after and all(closed.values())
    receipt = {
        "scope": "fictional source UI only; not installed qualification",
        "cases": cases,
        "errors": errors,
        "external_requests": external,
        "source_before": before,
        "source_after": after,
        "closed": closed,
        "artifacts": str(artifacts),
    }
    (artifacts / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
