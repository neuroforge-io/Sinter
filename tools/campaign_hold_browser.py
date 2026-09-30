"""Offline fictional action hold/resume, exact saved records and real exports."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
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


def fixture(width):
    return {
        "title": f"Fictional held work {width}",
        "organisation": "Example association",
        "objective": "Retain earlier scope without claiming completion.",
        "opportunities": [
            {"name": "Fictional active route", "status": "open"},
            {"name": "Fictional submitted route", "status": "submitted"},
        ],
        "actions": [
            {
                "task": "Earlier scope <retain exactly> 🐝",
                "status": "open",
                "opportunity": "Fictional active route",
                "scope_confirmed": True,
                "submission_phase": "pre_submission",
                "owner": "Example coordinator",
                "owner_kind": "role",
                "owner_confirmed": False,
                "due": "2026-09-01",
            },
            {
                "task": "Record an actual decision if received",
                "status": "open",
                "opportunity": "Fictional submitted route",
                "scope_confirmed": True,
                "submission_phase": "post_submission",
                "owner": "",
                "due": "2026-10-10",
            },
            {
                "task": "Already completed fictional work",
                "status": "done",
                "opportunity": "",
                "scope_confirmed": True,
                "owner": "",
                "due": "",
            },
            {
                "task": "Retained undated campaign-wide work",
                "status": "held",
                "opportunity": "",
                "scope_confirmed": True,
                "owner": "",
                "due": "",
            },
        ],
        "communications": [
            {
                "subject": "Retained fictional draft",
                "content": "No order approved.",
                "status": "draft",
                "direction": "outgoing",
                "date": "",
            }
        ],
        "sources": [
            {"title": "Fictional operator record", "notes": "No award or commitment."}
        ],
    }


class HoldChecks(CampaignChecks):
    @staticmethod
    def saved(page, title):
        return page.evaluate(
            """async title => {
          const {request} = await import('/static/api.js');
          const {campaigns} = await request('/api/campaigns');
          const item = campaigns.find(row => row.title === title);
          return await request('/api/campaigns/' + item.id);
        }""",
            title,
        )

    @staticmethod
    def action(page, index):
        result = page.locator(f'.campaign-action[data-action-index="{index}"]')
        if result.locator("details").get_attribute("open") is None:
            result.locator("summary").click()
        return result

    def lifecycle(self, page, width):
        from playwright.sync_api import expect

        page.set_viewport_size({"width": width, "height": 900})
        document = fixture(width)
        self.import_fixture(page, document)
        self.save(page)
        original = self.saved(page, document["title"])
        expected = copy.deepcopy(original["document"])
        page.get_by_role("tab", name="Next actions", exact=True).click()
        row = self.action(page, 0)
        row.get_by_label("Action status", exact=True).select_option("held")
        row = self.action(page, 0)
        expect(row.get_by_label("Action status", exact=True)).to_be_focused()
        expect(row).to_contain_text("On hold · not completed")
        expect(row).to_contain_text("Choose To do to resume")
        expect(row).to_contain_text("older previews cannot open these backups")
        expect(row.get_by_label("Next action", exact=True)).to_have_value(
            expected["actions"][0]["task"]
        )
        expect(row.get_by_label("Proposed target date", exact=True)).to_have_value(
            "2026-09-01"
        )
        expect(row.locator(".campaign-action-date-status")).to_have_attribute(
            "data-state", "held"
        )
        assert self.saved(page, document["title"]) == original
        self.save(page)
        expected["actions"][0]["status"] = "held"
        assert self.saved(page, document["title"])["document"] == expected
        self.screenshot(page, f"held-{width}")

        filename, contents = self.download(page, "Download actions CSV")
        assert filename.endswith(".csv")
        records = list(csv.DictReader(io.StringIO(contents)))
        assert len(records) == len(expected["actions"])
        assert records[0]["Action"] == expected["actions"][0]["task"]
        assert records[0]["Status"] == "held"
        assert records[0]["Proposed target date (unconfirmed)"] == "2026-09-01"
        assert "Example coordinator" in records[0]["Owner"]
        filename, calendar = self.download(page, "Download action dates")
        assert filename.endswith(".ics")
        assert expected["actions"][0]["task"] not in calendar
        assert expected["actions"][3]["task"] not in calendar
        assert "SUMMARY:Record an actual decision if received" in calendar

        with page.expect_response(
            lambda response: response.url.endswith("/api/campaigns/prepare")
        ) as prepared:
            page.get_by_role(
                "button", name="Prepare campaign brief", exact=True
            ).click()
        report = prepared.value.json()
        assert report["readiness"]["open_actions"] == 1
        assert report["readiness"]["actions_held"] == 2
        assert report["readiness"]["actions_without_owner"] == 1
        assert report["campaign"] == expected
        assert (
            "Earlier scope"
            not in report["document_markdown"].split("## Next recorded open action", 1)[
                1
            ]
        )
        assert "On hold · retained, not completed" in report["markdown"]

        self.transfers(page)
        _, backup = self.download(page, "Export campaign backup")
        assert json.loads(backup) == expected
        page.get_by_role("button", name="Start a new campaign", exact=True).click()
        page.get_by_role("button", name="Open " + document["title"], exact=True).click()
        page.get_by_role("tab", name="Next actions", exact=True).click()
        expect(
            self.action(page, 0).get_by_label("Action status", exact=True)
        ).to_have_value("held")
        assert self.saved(page, document["title"])["document"] == expected

        # A changed route cannot silently resume a deliberate hold.
        page.get_by_role("tab", name="Opportunities", exact=True).click()
        if not page.get_by_label("Opportunity status", exact=True).is_visible():
            page.get_by_text("Edit opportunity details", exact=True).click()
        page.get_by_label("Opportunity status", exact=True).select_option("closed")
        self.save(page)
        expected["opportunities"][0]["status"] = "closed"
        assert self.saved(page, document["title"])["document"] == expected
        page.get_by_role("tab", name="Next actions", exact=True).click()
        row = self.action(page, 0)
        expect(row.get_by_label("Action status", exact=True)).to_have_value("held")
        row.get_by_label("Action status", exact=True).select_option("open")
        row = self.action(page, 0)
        expect(
            page.get_by_role(
                "heading", name="Needs review before current work · 1", exact=True
            )
        ).to_be_visible()
        expect(row).to_contain_text("Hold reason: route recorded as closed.")
        self.save(page)
        expected["actions"][0]["status"] = "open"
        assert self.saved(page, document["title"])["document"] == expected
        page.get_by_role("tab", name="Opportunities", exact=True).click()
        if not page.get_by_label("Opportunity status", exact=True).is_visible():
            page.get_by_text("Edit opportunity details", exact=True).click()
        page.get_by_label("Opportunity status", exact=True).select_option("open")
        self.save(page)
        expected["opportunities"][0]["status"] = "open"
        assert self.saved(page, document["title"])["document"] == expected
        page.get_by_role("tab", name="Next actions", exact=True).click()
        expect(
            page.get_by_role("heading", name="Current work · 2", exact=True)
        ).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        self.screenshot(page, f"resumed-{width}")

        # Held history remains available for review, but not next-action requests.
        self.goto(page, "explore")
        page.get_by_text("Include existing actions", exact=True).click()
        held = page.get_by_role(
            "checkbox",
            name="Retained undated campaign-wide work · "
            "On hold · retained, not completed",
            exact=True,
        )
        current = page.get_by_role(
            "checkbox", name="Earlier scope <retain exactly> 🐝 · open", exact=True
        )
        expect(held).to_be_disabled()
        current.check()
        page.get_by_label("Help me with", exact=True).select_option("eligibility")
        expect(held).to_be_enabled()
        held.check()
        page.get_by_label("Help me with", exact=True).select_option("next_actions")
        expect(held).to_be_disabled()
        expect(held).not_to_be_checked()
        expect(current).to_be_checked()
        assert self.saved(page, document["title"])["document"] == expected


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-campaign-hold-proof-"))
    paths = (
        "src/sinter/campaigns.py",
        "src/sinter/community.py",
        "src/sinter/web/campaigns.js",
        "src/sinter/web/campaign-state.js",
        "src/sinter/web/campaign-decision.js",
        "src/sinter/web/campaign-plan.js",
        "src/sinter/web/assistant.js",
        "tools/campaign_hold_browser.py",
    )
    hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths
    }
    resources = {"browser_closed": False, "server_closed": False}
    with tempfile.TemporaryDirectory(prefix="sinter-campaign-hold-workspace-") as data:
        with ExitStack() as guard:
            for name in ("chat", "search", "_post", "_get"):
                guard.enter_context(
                    patch.object(
                        client,
                        name,
                        side_effect=AssertionError("Offline held-action proof"),
                    )
                )
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        checks = HoldChecks(
                            browser, f"http://127.0.0.1:{server.server_port}", artifacts
                        )
                        for width in (1440, 390):
                            checks.check(
                                f"hold-resume-{width}",
                                lambda page, width=width: checks.lifecycle(page, width),
                            )
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
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths
    }
    receipt = {
        "schema": "sinter-campaign-hold-browser/v1",
        "fixture_only": True,
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
        and unchanged
        and all(resources.values()),
    }
    (artifacts / "browser-receipt.json").write_text(json.dumps(receipt, indent=2))
    print(artifacts / "browser-receipt.json")
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect retained fictional browser receipt.")


if __name__ == "__main__":
    main()
