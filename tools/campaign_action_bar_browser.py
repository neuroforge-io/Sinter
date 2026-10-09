"""Fictional desktop/mobile proof of persistent campaign Save controls and data."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from tools._support import expect_campaign_message, save_campaign  # noqa: E402
from sinter.campaigns import validate  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.campaign_source_picker_browser import fixture as source_fixture  # noqa: E402


def text_count(value: object) -> int:
    """Count retained string code points without counting object keys."""
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(text_count(item) for item in value)
    if isinstance(value, dict):
        return sum(text_count(item) for item in value.values())
    return 0


def portfolio(title: str) -> dict:
    """Generate the operator-scale portfolio without private or inferred facts."""
    document = source_fixture(title)
    first_route = document["opportunities"][0]["name"]
    document["opportunities"] += [
        {
            "name": f"Fictional route {index:02d}",
            "status": "submitted"
            if index == 12
            else "closed"
            if index == 13
            else "clarification",
            "deadline": "2026-10-13" if index == 12 else "",
        }
        for index in range(2, 14)
    ]
    for index, source in enumerate(document["sources"]):
        source["notes"] = (
            f"Fictional source {index}. No permission is confirmed. " * 40
        )[:1200]
    asset = document["assets"][0]
    document["assets"] = []
    for index in range(27):
        row = copy.deepcopy(asset)
        row["name"] = f"Fictional product {index:02d}"
        row["public_summary"] = (
            "Fictional only; a measured comparison is needed. " * 20
        )[:700]
        row["funding_opportunities"] = [first_route, "Fictional route 02"]
        document["assets"].append(row)
    communication = document["communications"][0]
    document["communications"] = []
    for index in range(10):
        row = copy.deepcopy(communication)
        row.update(
            subject=f"Fictional meeting record {index:02d}",
            content=("No cash is committed. This is fictional retained wording. " * 20)[
                :1000
            ],
            date="" if index in (2, 8) else f"2026-09-{20 + index:02d}",
            direction="outgoing" if index in (2, 8) else "incoming",
            status="draft" if index in (2, 8) else "received",
        )
        document["communications"].append(row)
    document["actions"] = [
        {
            "task": "Review a fictional itemised quote",
            "opportunity": first_route,
            "owner": "",
            "due": "",
            "status": "open",
        }
    ]
    document = validate(document)
    remaining = 170000 - text_count(document)
    assert remaining >= 0
    for source in document["sources"]:
        added = min(remaining, 6000 - len(source["notes"]))
        source["notes"] += ("Fictional unresolved evidence. " * (added // 30 + 2))[
            :added
        ]
        remaining -= added
        if not remaining:
            break
    assert remaining == 0
    document = validate(document)
    assert text_count(document) == 170000
    return document


def main(argv: list[str] | None = None) -> None:
    """Use actual UI controls, preserve failures and close every local resource."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-campaign-action-bar-proof-"))
    paths = (
        "src/sinter/web/campaigns.js",
        "src/sinter/web/campaigns.css",
        "src/sinter/campaigns.py",
        "src/sinter/web/campaign-currency.js",
        "src/sinter/web/campaign-feedback.js",
        "tools/_support.py",
        "tools/campaign_source_picker_browser.py",
        "tools/campaign_action_bar_browser.py",
    )
    hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths
    }
    results, errors, external, layouts = [], [], [], []
    resources = {"browser_closed": False, "server_closed": False}

    def context_page(browser, base, viewport):
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
        return context, page

    def save(page):
        save_campaign(page)

    def unobscured(page, field, name):
        """Check focused control, complete bar visibility and actual hit target."""
        bar = page.get_by_role("region", name="Campaign save and preview", exact=True)
        expect(bar).to_be_visible()
        expect(field).to_be_focused()
        bounds = bar.bounding_box()
        target = field.bounding_box()
        viewport = page.viewport_size
        assert bounds and target and viewport
        assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= viewport["height"]
        assert target["y"] >= bounds["y"] + bounds["height"], (bounds, target)
        assert target["y"] + target["height"] <= viewport["height"], target
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert bar.get_by_role("button", name="Save campaign", exact=True).evaluate(
            "element => {const b=element.getBoundingClientRect();"
            "return element.contains(document.elementFromPoint("
            "b.x+b.width/2,b.y+b.height/2));}"
        )
        layouts.append(
            {"view": name, "viewport": viewport, "bar": bounds, "focused_field": target}
        )

    with tempfile.TemporaryDirectory(prefix="sinter-action-bar-workspace-") as data:
        with patch.object(
            client, "_open", side_effect=AssertionError("Offline UI only")
        ) as remote:
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        for width, height in (
                            (1440, 1000),
                            (390, 844),
                            (320, 568),
                            (390, 400),
                            (320, 400),
                            (320, 501),
                            (320, 601),
                            (651, 400),
                        ):
                            label = f"{width}x{height}"
                            started = time.monotonic()
                            result = {"check": "action-bar-" + label, "passed": False}
                            context, page = context_page(
                                browser, base, {"width": width, "height": height}
                            )
                            try:
                                title = "Fictional persistent controls " + label
                                document = portfolio(title)
                                page.goto(base + "/#campaigns")
                                page.get_by_text(
                                    "Import or back up a campaign", exact=True
                                ).click()
                                page.get_by_label(
                                    "Import campaign backup", exact=True
                                ).set_input_files(
                                    {
                                        "name": "fictional-portfolio.json",
                                        "mimeType": "application/json",
                                        "buffer": json.dumps(document).encode(),
                                    }
                                )
                                expect(
                                    page.get_by_label("Campaign name", exact=True)
                                ).to_have_value(title)
                                save(page)
                                expect_campaign_message(
                                    page,
                                    "Campaign saved. Answers, costs, checks and actions "
                                    "will be here when you return.",
                                )
                                saved_id = next(
                                    row["id"]
                                    for row in server.app.campaigns.list()
                                    if row["title"] == title
                                )
                                assert (
                                    server.app.campaigns.get(saved_id)["document"]
                                    == document
                                )
                                expect(
                                    page.get_by_role(
                                        "button", name="Save campaign", exact=True
                                    )
                                ).to_have_count(1)
                                submitted = page.get_by_role(
                                    "button", name="Fictional route 12", exact=False
                                )
                                submitted.click()
                                expect(
                                    page.locator(".campaign-opportunity-facts")
                                ).to_contain_text("13 Oct 2026")
                                page.get_by_role(
                                    "button", name="Fictional route 13", exact=False
                                ).click()
                                expect(
                                    page.locator(".campaign-opportunity-facts")
                                ).to_contain_text("Not recorded")
                                expect(
                                    page.get_by_role(
                                        "button",
                                        name="Prepare campaign brief",
                                        exact=True,
                                    )
                                ).to_have_count(1)
                                page.get_by_role(
                                    "tab", name="Products & IP", exact=True
                                ).click()
                                asset = page.locator(".campaign-asset").first
                                asset.locator("details > summary").first.click()
                                funding = asset.locator(".campaign-asset-funding")
                                expect(funding.get_by_role("checkbox")).to_have_count(
                                    13
                                )
                                expect(funding).to_contain_text(
                                    "2 of 13 available route links selected."
                                )
                                expect(funding).to_contain_text(
                                    "Maximum 10 links per product or asset."
                                )
                                boxes = funding.get_by_role("checkbox")
                                for index in range(2, 10):
                                    boxes.nth(index).check()
                                expect(funding).to_contain_text(
                                    "10 of 13 available route links selected."
                                )
                                expect(funding).to_contain_text(
                                    "remove one before adding another"
                                )
                                for index in range(10, 13):
                                    expect(boxes.nth(index)).to_be_disabled()
                                for index in range(2, 10):
                                    boxes.nth(index).uncheck()
                                expect(funding).to_contain_text(
                                    "2 of 13 available route links selected."
                                )
                                product_name = asset.get_by_label(
                                    "Product or asset name", exact=True
                                )
                                product_name.click()
                                unobscured(page, product_name, label + " product")
                                page.get_by_role(
                                    "tab", name="Sources", exact=True
                                ).click()
                                source = document["sources"][-1]
                                details = page.locator(
                                    f'.campaign-source-details[data-source-id="{source["id"]}"]'
                                )
                                details.locator("summary").click()
                                notes = details.get_by_label(
                                    "Source wording and notes", exact=True
                                )
                                pending = (
                                    source["notes"] + "\nFictional operator checkpoint."
                                )
                                notes.fill(pending)
                                expect(
                                    page.locator(
                                        ".campaign-save-feedback .notice.success"
                                    )
                                ).to_have_count(0)
                                notes.click()
                                unobscured(page, notes, label + " source")
                                expect(
                                    page.locator(".campaign-save-state")
                                ).to_have_text("Unsaved changes")
                                page.screenshot(
                                    path=str(artifacts / (label + "-editing.png"))
                                )
                                notes.press("Tab")
                                date = details.get_by_label(
                                    "Source checked date · user-entered", exact=True
                                )
                                unobscured(page, date, label + " source keyboard")
                                save_control = page.get_by_role(
                                    "button", name="Save campaign", exact=True
                                )
                                save_control.focus()
                                save_control.press("Tab")
                                expect(
                                    page.get_by_role(
                                        "button",
                                        name="Prepare campaign brief",
                                        exact=True,
                                    )
                                ).to_be_focused()
                                save(page)
                                expected = copy.deepcopy(document)
                                expected["sources"][-1]["notes"] = pending
                                assert (
                                    server.app.campaigns.get(saved_id)["document"]
                                    == expected
                                )
                                page.reload()
                                expect(
                                    page.get_by_label("Campaign name", exact=True)
                                ).to_have_value(title)
                                page.get_by_role(
                                    "tab", name="Sources", exact=True
                                ).click()
                                details = page.locator(
                                    f'.campaign-source-details[data-source-id="{source["id"]}"]'
                                )
                                details.locator("summary").click()
                                notes = details.get_by_label(
                                    "Source wording and notes", exact=True
                                )
                                expect(notes).to_have_value(pending)
                                notes.click()
                                unobscured(page, notes, label + " reopened")
                                page.screenshot(
                                    path=str(artifacts / (label + "-reopened.png"))
                                )
                                # Competing real UI saves must expose the same refusal
                                # without overwriting the pending first-window text.
                                other_context, other = context_page(
                                    browser, base, {"width": width, "height": height}
                                )
                                try:
                                    other.goto(base + "/#campaigns")
                                    expect(
                                        other.get_by_label("Campaign name", exact=True)
                                    ).to_have_value(title)
                                    other.get_by_text(
                                        "Campaign details", exact=True
                                    ).click()
                                    changed_organisation = (
                                        "Fictional second-window team"
                                    )
                                    other.get_by_label(
                                        "Applicant organisation", exact=True
                                    ).fill(changed_organisation)
                                    save(other)
                                    other_expected = copy.deepcopy(expected)
                                    other_expected["organisation"] = (
                                        changed_organisation
                                    )
                                    assert (
                                        server.app.campaigns.get(saved_id)["document"]
                                        == other_expected
                                    )
                                    stale_text = (
                                        pending + "\nFictional pending revision."
                                    )
                                    notes.fill(stale_text)
                                    page.get_by_role(
                                        "button", name="Save campaign", exact=True
                                    ).click()
                                    feedback = page.locator(".campaign-save-feedback")
                                    expect(feedback).to_contain_text(
                                        "This campaign changed in another window"
                                    )
                                    expect(feedback).to_contain_text(
                                        "Your edits are still here."
                                    )
                                    expect(notes).to_have_value(stale_text)
                                    recovery = feedback.inner_text()
                                    still_pending = (
                                        stale_text + "\nFictional still pending."
                                    )
                                    notes.fill(still_pending)
                                    expect(feedback).to_have_text(recovery)
                                    expect(notes).to_have_value(still_pending)
                                    expect(
                                        page.locator(".campaign-save-state")
                                    ).to_have_text("Unsaved changes")
                                    expect(
                                        page.get_by_role(
                                            "button", name="Save campaign", exact=True
                                        )
                                    ).to_be_enabled()
                                    assert (
                                        server.app.campaigns.get(saved_id)["document"]
                                        == other_expected
                                    )
                                    notes.click()
                                    unobscured(page, notes, label + " refused save")
                                    feedback.focus()
                                    expect(feedback).to_be_focused()
                                    if feedback.evaluate(
                                        "element => element.scrollHeight "
                                        "> element.clientHeight"
                                    ):
                                        feedback.press("ArrowDown")
                                        page.wait_for_function(
                                            "element => element.scrollTop > 0",
                                            arg=feedback.element_handle(),
                                        )
                                    page.screenshot(
                                        path=str(artifacts / (label + "-conflict.png"))
                                    )
                                finally:
                                    other_context.close()
                                result["passed"] = True
                            except Exception as error:
                                result["error"] = (
                                    type(error).__name__ + ": " + str(error)
                                )
                                page.screenshot(
                                    path=str(artifacts / (label + "-FAILED.png"))
                                )
                            finally:
                                result["seconds"] = round(time.monotonic() - started, 2)
                                results.append(result)
                                context.close()
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
        "schema": "sinter-campaign-action-bar-browser/v1",
        "fixture_only": True,
        "portfolio": {
            "sources": 81,
            "products": 27,
            "communications": 10,
            "routes": 13,
            "retained_characters": 170000,
        },
        "checks": results,
        "layouts": layouts,
        "browser_errors": errors,
        "external_requests": external,
        "model_operations_requested": 0,
        "source_sha256": hashes,
        "source_unchanged_during_run": unchanged,
        "resources": resources,
        "passed": all(row["passed"] for row in results)
        and not errors
        and not external
        and unchanged,
    }
    path = artifacts / "browser-receipt.json"
    path.write_text(json.dumps(receipt, indent=2))
    print(path)
    if not receipt["passed"] or not all(resources.values()):
        raise SystemExit("FAIL: inspect retained fictional action-bar receipt.")


if __name__ == "__main__":
    main()
