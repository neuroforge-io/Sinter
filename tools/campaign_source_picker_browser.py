"""Select exact saved sources through visible controls in a fictional campaign."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.campaign_browser import CampaignChecks  # noqa: E402


def fixture(title: str, *, historical: bool = False) -> dict:
    """Use 81 fictional sources, including two colliding title/host choices."""
    sources = [
        {
            "id": f"{index:032x}",
            "title": "Fictional guide <saved 🐝>"
            if index < 3
            else f"Fictional reference {index}",
            "url": f"https://example.invalid/guide/{index}",
            "checked_at": "2026-09-28" if index == 1 else "2026-09-30",
            "notes": "Fictional only; no approval or commitment.",
        }
        for index in range(1, 82)
    ]
    first = sources[0]
    return {
        "title": title,
        "organisation": "Fictional Community Association",
        "opportunities": [
            {
                "name": "Fictional route",
                "status": "clarification",
                "application_window": "fixed",
                "deadline": "2026-10-15",
                "window_source_id": first["id"],
                "window_source_url": first["url"],
                "window_source_quote": "Existing exact window wording.",
                "window_checked_at": first["checked_at"],
            }
        ],
        "sources": sources,
        "communications": [
            {
                "opportunity": "",
                "date": "",
                "direction": "outgoing",
                "status": "draft",
                "channel": "email",
                "subject": "Fictional record",
                "content": "No cash is committed. This draft has not been sent.",
                "counterparty": "",
                "evidence_links": [
                    {
                        "source_id": first["id"] if historical else "",
                        "title": "Fictional archived guide" if historical else "",
                        "url": "https://example.invalid/historical"
                        if historical
                        else "",
                        "checked_at": "2026-09-10" if historical else "",
                        "notes": "Exact retained evidence note.",
                    }
                ],
            }
        ],
        "requirements": [
            {
                "opportunity": "Fictional route",
                "rule": "Fictional rule",
                "status": "met",
                "evidence": "Existing applicant evidence.",
                "source_id": first["id"],
                "source_url": first["url"],
                "source_quote": "Existing exact rule wording.",
                "checked_at": first["checked_at"],
            }
        ],
        "assets": [
            {
                "name": "Fictional research record",
                "references": [
                    {
                        "kind": "other",
                        "source_id": first["id"],
                        "title": first["title"],
                        "url": first["url"],
                        "excerpt": "Existing selected excerpt.",
                        "checked_at": first["checked_at"],
                        "notes": "Exact retained asset note.",
                    }
                ],
            }
        ],
    }


class SourcePickerChecks(CampaignChecks):
    @staticmethod
    def snapshot(page, title):
        return page.evaluate(
            """async title => {
            const {request} = await import('/static/api.js');
            const shelf = await request('/api/campaigns');
            const item = shelf.campaigns.find(row => row.title === title);
            return (await request('/api/campaigns/' + item.id)).document;
        }""",
            title,
        )

    def start(self, page, title, *, historical=False):
        self.import_fixture(page, fixture(title, historical=historical))
        self.save(page)
        return self.snapshot(page, title)

    @staticmethod
    def choose(scope, label, source):
        """Click an actual visible result, never dispatch a synthetic change."""
        scope.get_by_label(label, exact=True).fill(source["id"])
        scope.locator(f'button[data-campaign-source-id="{source["id"]}"]').click()

    @staticmethod
    def evidence(page):
        page.get_by_role("tab", name="Communications", exact=True).click()
        details = page.locator(".campaign-communication > details")
        if not details.evaluate("element => element.open"):
            details.locator("summary").click()
        return page.get_by_role("article", name="Communication evidence link")

    def large_explicit_selection(self, page):
        from playwright.sync_api import expect

        title = "Fictional 81-source explicit picker"
        before = self.start(page, title)
        evidence = self.evidence(page)
        picker = evidence.get_by_label("Link to a saved campaign source", exact=True)
        picker.fill("")
        expect(evidence.locator(".campaign-source-matches button")).to_have_count(8)
        expect(evidence).to_contain_text("81 matching saved sources · showing 8")
        picker.fill("Fictional guide")
        buttons = evidence.locator(".campaign-source-matches button")
        expect(buttons).to_have_count(2)
        assert len(set(buttons.all_text_contents())) == 2
        assert all("Source " in text for text in buttons.all_text_contents())
        picker.press("Enter")
        expect(evidence.get_by_label("Evidence title", exact=True)).to_have_value("")
        expect(page.locator(".campaign-save-state")).to_have_text(
            "Saved on this computer"
        )
        self.save(page)
        assert self.snapshot(page, title) == before
        evidence = self.evidence(page)
        evidence.get_by_label("Link to a saved campaign source", exact=True).fill(
            "Fictional guide"
        )
        evidence.locator(".campaign-source-picker").evaluate(
            "element => element.scrollIntoView({block: 'start'})"
        )
        self.screenshot(page, "visible-source-matches")
        chosen = before["sources"][1]
        evidence.locator(f'button[data-campaign-source-id="{chosen["id"]}"]').click()
        expect(evidence.get_by_label("Evidence link", exact=True)).to_have_value(
            chosen["url"]
        )
        self.save(page)
        expected = json.loads(json.dumps(before))
        expected["communications"][0]["evidence_links"][0].update(
            {
                key: chosen[key]
                for key in ("id", "title", "url", "checked_at")
                if key != "id"
            }
        )
        expected["communications"][0]["evidence_links"][0]["source_id"] = chosen["id"]
        assert self.snapshot(page, title) == expected
        evidence = self.evidence(page)
        picker = evidence.get_by_label("Link to a saved campaign source", exact=True)
        picker.fill("nothing matches")
        expect(evidence).to_contain_text("No matching saved sources")
        expect(evidence.get_by_label("Evidence link", exact=True)).to_have_value(
            chosen["url"]
        )
        picker.fill("Fictional reference 81")
        picker.press("ArrowDown")
        button = evidence.locator(".campaign-source-matches button")
        expect(button).to_be_focused()
        page.keyboard.press("Enter")
        expect(evidence.get_by_label("Evidence link", exact=True)).to_have_value(
            before["sources"][80]["url"]
        )
        self.save(page)
        expected["communications"][0]["evidence_links"][0].update(
            {
                "source_id": before["sources"][80]["id"],
                **{
                    key: before["sources"][80][key]
                    for key in ("title", "url", "checked_at")
                },
            }
        )
        assert self.snapshot(page, title) == expected

    def historical_snapshot(self, page):
        from playwright.sync_api import expect

        title = "Fictional source snapshot preservation"
        before = self.start(page, title, historical=True)
        evidence = self.evidence(page)
        self.choose(evidence, "Link to a saved campaign source", before["sources"][0])
        expect(evidence.get_by_label("Evidence title", exact=True)).to_have_value(
            "Fictional archived guide"
        )
        expect(evidence.locator(".notice.warning")).to_be_visible()
        self.save(page)
        assert self.snapshot(page, title) == before
        evidence = self.evidence(page)
        evidence.get_by_role("button", name="Clear link", exact=True).click()
        expect(
            evidence.get_by_label("Link to a saved campaign source", exact=True)
        ).to_be_focused()
        expect(evidence.get_by_label("Evidence title", exact=True)).to_have_value(
            "Fictional archived guide"
        )
        expect(evidence.get_by_label("Evidence title", exact=True)).to_be_enabled()
        self.choose(evidence, "Link to a saved campaign source", before["sources"][0])
        expect(evidence.locator(".notice.warning")).to_be_hidden()
        self.save(page)
        expected = json.loads(json.dumps(before))
        expected["communications"][0]["evidence_links"][0].update(
            {key: before["sources"][0][key] for key in ("title", "url", "checked_at")}
        )
        assert self.snapshot(page, title) == expected

    def window_check_and_asset_callbacks(self, page):
        from playwright.sync_api import expect

        title = "Fictional reusable source callbacks"
        before = self.start(page, title)
        chosen = before["sources"][1]
        self.choose(page, "Registered source for the application window", chosen)
        expect(
            page.get_by_label("Exact official wording for this window", exact=True)
        ).to_have_value("")
        expect(
            page.get_by_label("Window wording checked on", exact=True)
        ).to_have_value("")
        page.locator(".campaign-requirement > summary").click()
        check = page.get_by_role("article", name="Requirement check")
        self.choose(check, "Registered campaign source (optional)", chosen)
        self.save(page)
        after = self.snapshot(page, title)
        assert after["opportunities"][0]["window_source_id"] == chosen["id"]
        assert after["opportunities"][0]["window_source_quote"] == ""
        assert after["opportunities"][0]["window_checked_at"] == ""
        requirement = after["requirements"][0]
        assert requirement["source_id"] == chosen["id"]
        assert requirement["status"] == "unknown"
        assert requirement["source_quote"] == requirement["evidence"] == ""
        assert requirement["checked_at"] == chosen["checked_at"]
        assert after["sources"] == before["sources"]
        assert after["communications"] == before["communications"]
        page.get_by_role("tab", name="Products & IP", exact=True).click()
        page.locator(".campaign-asset > details > summary").click()
        reference = page.locator(".campaign-asset-reference")
        self.choose(reference, "Link a campaign source (optional)", chosen)
        expect(
            reference.get_by_label(
                "Relevant passage · quote or short paraphrase", exact=True
            )
        ).to_be_focused()
        self.save(page)
        saved = self.snapshot(page, title)
        selected = saved["assets"][0]["references"][0]
        assert selected["source_id"] == chosen["id"]
        assert selected["title"] == chosen["title"] and selected["url"] == chosen["url"]
        assert selected["excerpt"] == ""
        assert selected["checked_at"] == chosen["checked_at"]
        assert selected["notes"] == "Exact retained asset note."
        assert saved["sources"] == before["sources"]
        assert saved["communications"] == before["communications"]


def main(argv: list[str] | None = None) -> None:
    """Exercise real selection buttons against a fresh local save service."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-source-picker-proof-"))
    resources = {"browser_closed": False, "server_closed": False}
    paths = (
        "src/sinter/web/campaigns.js",
        "src/sinter/web/campaign-source-options.js",
        "src/sinter/web/campaigns.css",
    )
    hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths
    }
    with tempfile.TemporaryDirectory(prefix="sinter-source-picker-workspace-") as data:
        with ExitStack() as guard:
            for name in ("chat", "search", "_post", "_get"):
                guard.enter_context(
                    patch.object(
                        client,
                        name,
                        side_effect=AssertionError("Offline source picker only"),
                    )
                )
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        checks = SourcePickerChecks(
                            browser, f"http://127.0.0.1:{server.server_port}", artifacts
                        )
                        for name in (
                            "large_explicit_selection",
                            "historical_snapshot",
                            "window_check_and_asset_callbacks",
                            "communication_source_snapshot",
                        ):
                            checks.check("source-picker-" + name, getattr(checks, name))
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
        "schema": "sinter-campaign-source-picker-browser/v1",
        "fixture_only": True,
        "fixture_source_count": 81,
        "checks": checks.results,
        "screenshots": checks.screenshots,
        "browser_errors": checks.errors,
        "external_requests": checks.external,
        "model_operations_requested": 0,
        "resources": resources,
        "source_sha256": hashes,
        "source_unchanged_during_run": unchanged,
        "passed": all(row["passed"] for row in checks.results)
        and not checks.errors
        and not checks.external
        and unchanged,
    }
    (artifacts / "browser-receipt.json").write_text(json.dumps(receipt, indent=2))
    print(artifacts / "browser-receipt.json")
    if not receipt["passed"] or not all(resources.values()):
        raise SystemExit("FAIL: inspect retained fictional browser receipt.")


if __name__ == "__main__":
    main()
