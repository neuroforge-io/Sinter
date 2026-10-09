"""Fictional offline Communications view: identity, chronology and saving.

Uses a fresh local workspace and the real browser/server. No private campaign,
mailbox, external website or model is used. Passing checks are not UX scores.
"""

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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.campaign_browser import CampaignChecks  # noqa: E402


def fixture(title):
    routes = [
        {"name": "Fictional route " + str(index), "status": "clarification"}
        for index in range(12)
    ]
    routes[5]["name"] = "all"
    sources = [
        {
            "id": f"{index + 1:032x}",
            "title": f"Current source {index}",
            "url": f"https://example.invalid/current/{index}",
            "notes": "Current fictional wording only.",
            "checked_at": "2026-09-30",
        }
        for index in range(76)
    ]

    def message(date, route, subject, content="Fictional record only.", **changes):
        row = {
            "date": date,
            "opportunity": route,
            "subject": subject,
            "content": content,
            "counterparty": "Fictional contact",
            "direction": "incoming",
            "status": "received",
            "channel": "email",
            "evidence_links": [],
        }
        row.update(changes)
        return row

    return {
        "title": title,
        "organisation": "Fictional Community Association",
        "opportunities": routes,
        "sources": sources,
        "communications": [
            message("2026-09-30", routes[0]["name"], "Duplicate title"),
            message("", "", "Unsent draft", direction="outgoing", status="draft"),
            message(
                "2026-09-20",
                routes[0]["name"],
                "Earlier offer",
                "Fictional historical cash wording.",
            ),
            message(
                "2026-09-28",
                routes[0]["name"],
                "Submission hold",
                "Fictional updated record: cash unavailable; no commitment.",
                evidence_links=[
                    {
                        "source_id": sources[0]["id"],
                        "title": "Earlier saved wording <keep 🌱>",
                        "url": "https://example.invalid/earlier/0",
                        "checked_at": "2026-09-20",
                        "notes": "Überprüfung 🌱",
                    }
                ],
            ),
            message("2026-09-28", routes[1]["name"], "Duplicate title"),
            message("2026-09-25", "all", "A route named all"),
        ],
    }


class CommunicationChecks(CampaignChecks):
    @staticmethod
    def visible_indexes(page):
        return page.locator(".campaign-communication:visible").evaluate_all(
            "cards => cards.map(card => Number(card.dataset.communicationIndex))"
        )

    @staticmethod
    def record(page, index):
        return page.locator(
            f'.campaign-communication[data-communication-index="{index}"]'
        )

    @staticmethod
    def snapshot(page, title):
        return page.evaluate(
            """async title => {
            const {request} = await import('/static/api.js');
            const shelf = await request('/api/campaigns');
            const item = shelf.campaigns.find(row => row.title === title);
            return await request('/api/campaigns/' + item.id);
        }""",
            title,
        )

    def start(self, page, title, document=None):
        self.import_fixture(page, document or fixture(title))
        self.save(page)
        page.get_by_role("tab", name="Communications", exact=True).click()
        return self.snapshot(page, title)["document"]

    def lazy_status_and_preview(self, page):
        from playwright.sync_api import expect

        title = "Fictional correspondence - lazy editors and status filters"
        document = fixture(title)
        document["communications"][2].update(direction="outgoing", status="sent")
        document["communications"].extend(
            {
                "date": "2026-09-26",
                "opportunity": "Fictional route 1",
                "subject": f"Fictional archived message {index}",
                "content": "Fictional saved wording. No agreement or award.",
                "counterparty": "Fictional organisation",
                "direction": "incoming",
                "status": "received",
                "channel": "email",
                "evidence_links": [
                    {
                        "source_id": document["sources"][1]["id"],
                        "title": "Fictional saved snapshot",
                        "url": document["sources"][1]["url"],
                        "checked_at": "2026-09-30",
                        "notes": "Fictional original evidence.",
                    }
                ],
            }
            for index in range(41)
        )
        before = self.start(page, title, document)
        expect(page.locator(".campaign-communication")).to_have_count(47)
        expect(page.locator(".campaign-communication-editor")).to_have_count(0)
        expect(page.locator(
            ".campaign-communication input, .campaign-communication textarea, "
            ".campaign-communication select"
        )).to_have_count(0)
        expect(self.record(page, 3).locator("summary")).to_contain_text(
            "1 saved evidence link"
        )
        expect(self.record(page, 3).locator("summary")).to_contain_text(
            "Open to view or edit"
        )
        statuses = page.get_by_label("Communication status filter", exact=True)
        statuses.select_option("draft")
        assert self.visible_indexes(page) == [1]
        statuses.select_option("sent")
        assert self.visible_indexes(page) == [2]
        statuses.select_option("received")
        assert len(self.visible_indexes(page)) == 45
        page.get_by_label("Find a communication", exact=True).fill("überprüfung 🌱")
        assert self.visible_indexes(page) == [3]
        preview = self.record(page, 3).locator(".campaign-communication-preview")
        expect(preview).to_have_text(
            "Saved evidence: Überprüfung 🌱"
        )
        page.get_by_label("Find a communication", exact=True).fill("<keep 🌱>")
        expect(preview).to_have_text(
            "Saved evidence: Earlier saved wording <keep 🌱>"
        )
        assert page.locator(".campaign-communication-preview keep").count() == 0
        self.record(page, 3).locator("summary").click()
        expect(page.locator(".campaign-communication-editor")).to_have_count(1)
        evidence_title = self.record(page, 3).get_by_label("Evidence title", exact=True)
        expect(evidence_title).to_have_value(
            "Earlier saved wording <keep 🌱>"
        )
        expect(evidence_title).to_be_disabled()
        # Filtering is a view choice; historical snapshots and hidden rows survive Save.
        expect(page.locator(".campaign-save-state")).to_have_text(
            "Saved on this computer"
        )
        self.save(page)
        assert self.snapshot(page, title)["document"] == before
        expect(statuses).to_have_value("received")
        expect(self.record(page, 3).locator("details")).to_have_attribute("open", "")
        expect(page.locator(".campaign-communication-editor")).to_have_count(1)
        page.get_by_role(
            "button", name="Clear communication filters", exact=True
        ).click()
        expect(statuses).to_have_value("all")
        assert len(self.visible_indexes(page)) == 47
        statuses.select_option("sent")
        self.record(page, 2).locator("summary").click()
        recorded_status = self.record(page, 2).get_by_label(
            "Communication status", exact=True
        )
        recorded_status.select_option("draft")
        assert self.visible_indexes(page) == []
        expect(page.locator(".campaign-save-state")).to_have_text("Unsaved changes")
        self.save(page)
        expected = json.loads(json.dumps(before))
        expected["communications"][2]["status"] = "draft"
        assert self.snapshot(page, title)["document"] == expected
        statuses.select_option("draft")
        assert self.visible_indexes(page) == [1, 2]
        expect(recorded_status).to_have_value("draft")
        # Direction changes preserve the saved wording and open editor state.
        statuses.select_option("all")
        self.record(page, 2).get_by_label("Direction", exact=True).select_option(
            "incoming"
        )
        expect(recorded_status).to_have_value("received")
        self.save(page)
        expected["communications"][2].update(direction="incoming", status="received")
        assert self.snapshot(page, title)["document"] == expected
        self.communication_scale_evidence = {
            "canonical_rows": 47,
            "initial_editors": 0,
            "initial_message_form_controls": 0,
            "editors_after_opening_one_saved_message": 1,
            "status_filtering_preserves_canonical_records": True,
            "hidden_status_edit_survives_save": True,
            "literal_historical_evidence_preview": True,
        }
        self.screenshot(page, "communication-lazy-status-filters")

    def evidence_navigation_transitions(self, page):
        from playwright.sync_api import expect

        title = "Fictional correspondence - current evidence navigation"
        before = self.start(page, title)
        row = self.record(page, 3)
        row.locator("summary").click()
        evidence = row.get_by_role(
            "article", name="Communication evidence link", exact=True
        ).nth(0)
        navigation = evidence.get_by_role(
            "link", name="Open evidence link", exact=True
        )
        original_link = before["communications"][3]["evidence_links"][0]
        expect(navigation).to_have_attribute("href", original_link["url"])
        source_b = before["sources"][1]
        picker = evidence.get_by_label("Link to a saved campaign source", exact=True)
        picker.fill(source_b["title"])
        evidence.get_by_role(
            "button",
            name=f"Link source: {source_b['title']} · example.invalid",
            exact=True,
        ).click()
        expect(evidence.get_by_label("Evidence link", exact=True)).to_have_value(
            source_b["url"]
        )
        expect(navigation).to_have_attribute("href", source_b["url"])
        evidence.get_by_role("button", name="Clear link", exact=True).click()
        link_url = evidence.get_by_label("Evidence link", exact=True)
        expect(link_url).to_be_enabled()
        # Unlinking keeps the saved snapshot; manual edits control navigation.
        expect(navigation).to_have_attribute("href", source_b["url"])
        link_url.fill("javascript:alert(1)")
        expect(navigation).to_have_count(0)
        expect(evidence).to_contain_text("No valid external link supplied")
        link_url.fill("")
        expect(navigation).to_have_count(0)
        manual_url = "https://example.invalid/manual/updated"
        link_url.fill(manual_url)
        expect(navigation).to_have_attribute("href", manual_url)
        row.get_by_role("button", name="Add evidence link", exact=True).click()
        blank = row.get_by_role(
            "article", name="Communication evidence link", exact=True
        ).nth(1)
        blank_navigation = blank.get_by_role(
            "link", name="Open evidence link", exact=True
        )
        expect(blank_navigation).to_have_count(0)
        source_c = before["sources"][2]
        blank.get_by_label("Link to a saved campaign source", exact=True).fill(
            source_c["title"]
        )
        blank.get_by_role(
            "button",
            name=f"Link source: {source_c['title']} · example.invalid",
            exact=True,
        ).click()
        expect(blank_navigation).to_have_attribute("href", source_c["url"])
        self.save(page)
        expected = json.loads(json.dumps(before))
        expected["communications"][3]["evidence_links"][0].update(
            source_id="", title=source_b["title"], url=manual_url,
            checked_at=source_b["checked_at"],
        )
        expected["communications"][3]["evidence_links"].append({
            "source_id": source_c["id"], "title": source_c["title"],
            "url": source_c["url"], "checked_at": source_c["checked_at"],
            "notes": "",
        })
        assert self.snapshot(page, title)["document"] == expected
        expect(navigation).to_have_attribute("href", manual_url)
        expect(blank_navigation).to_have_attribute("href", source_c["url"])

    def mobile_literal_preview(self, page):
        from playwright.sync_api import expect

        page.set_viewport_size({"width": 390, "height": 844})
        title = "Fictional correspondence - mobile saved evidence"
        before = self.start(page, title)
        page.get_by_label("Find a communication", exact=True).fill("überprüfung 🌱")
        assert self.visible_indexes(page) == [3]
        preview = self.record(page, 3).locator(".campaign-communication-preview")
        preview.scroll_into_view_if_needed()
        expect(preview).to_be_visible()
        expect(preview).to_have_text("Saved evidence: Überprüfung 🌱")
        expect(self.record(page, 3).locator("summary")).to_contain_text(
            "Recorded as received"
        )
        dimensions = page.evaluate("""() => ({
            viewport: window.innerWidth,
            content: document.documentElement.scrollWidth
        })""")
        assert dimensions["viewport"] == 390
        assert dimensions["content"] <= dimensions["viewport"] + 1
        assert self.snapshot(page, title)["document"] == before
        self.screenshot(page, "communication-mobile-literal-evidence")

    def unchanged_views(self, page):
        from playwright.sync_api import expect

        title = "Fictional chronology - unchanged views"
        before = self.start(page, title)
        assert self.visible_indexes(page) == [0, 1, 2, 3, 4, 5]
        expect(self.record(page, 0).locator("summary")).to_contain_text(
            "Fictional route 0"
        )
        expect(self.record(page, 1).locator("summary")).to_contain_text("Campaign-wide")
        self.record(page, 0).locator("summary").click()
        page.get_by_label("Communication order", exact=True).select_option("oldest")
        assert self.visible_indexes(page) == [2, 5, 3, 4, 0, 1]
        expect(self.record(page, 0).locator("details")).to_have_attribute("open", "")
        expect(self.record(page, 4).locator("details")).not_to_have_attribute(
            "open", ""
        )
        page.get_by_label("Find a communication", exact=True).fill("überprüfung 🌱")
        assert self.visible_indexes(page) == [3]
        page.get_by_label("Find a communication", exact=True).fill("Current source 0")
        assert self.visible_indexes(page) == []
        page.get_by_role(
            "button", name="Clear communication filters", exact=True
        ).click()
        page.get_by_label("Communication scope", exact=True).select_option("route:5")
        assert self.visible_indexes(page) == [5]
        page.get_by_label("Communication scope", exact=True).select_option("campaign")
        assert self.visible_indexes(page) == [1]
        page.get_by_label("Communication scope", exact=True).select_option("all")
        page.get_by_label("Communication order", exact=True).select_option("newest")
        assert self.visible_indexes(page) == [0, 3, 4, 5, 2, 1]
        page.get_by_role("tab", name="Sources", exact=True).click()
        page.get_by_role("tab", name="Communications", exact=True).click()
        assert self.visible_indexes(page) == [0, 3, 4, 5, 2, 1]
        expect(self.record(page, 0).locator("details")).to_have_attribute("open", "")
        expect(page.locator(".campaign-save-state")).to_have_text(
            "Saved on this computer"
        )
        self.save(page)
        assert self.snapshot(page, title)["document"] == before
        search = page.get_by_label("Find a communication", exact=True)
        search.scroll_into_view_if_needed()
        self.screenshot(page, "communication-view-chronology")

    def canonical_edit_and_removal(self, page):
        from playwright.sync_api import expect

        title = "Fictional chronology - canonical edit"
        before = self.start(page, title)
        page.get_by_label("Communication order", exact=True).select_option("oldest")
        self.record(page, 2).locator("summary").click()
        page.evaluate(
            "window.fictionalEditedCard = "
            "document.querySelector('[data-communication-index=\"2\"]')"
        )
        self.record(page, 2).get_by_label("Message text or summary", exact=True).fill(
            "Fictional edited historical wording; do not treat this as current."
        )
        page.get_by_label("Find a communication", exact=True).fill("historical wording")
        assert self.visible_indexes(page) == [2]
        page.get_by_label("Communication order", exact=True).select_option("newest")
        assert page.evaluate(
            "window.fictionalEditedCard === "
            "document.querySelector('[data-communication-index=\"2\"]')"
        )
        expect(
            self.record(page, 2).get_by_label("Message text or summary", exact=True)
        ).to_have_value(
            "Fictional edited historical wording; do not treat this as current."
        )
        expect(page.locator(".campaign-save-state")).to_have_text("Unsaved changes")
        self.save(page)
        expected = json.loads(json.dumps(before))
        expected["communications"][2]["content"] = (
            "Fictional edited historical wording; do not treat this as current."
        )
        assert self.snapshot(page, title)["document"] == expected
        page.get_by_role(
            "button", name="Clear communication filters", exact=True
        ).click()
        self.record(page, 0).locator("summary").click()
        self.record(page, 2).get_by_role(
            "button", name="Remove communication", exact=True
        ).click()
        expect(self.record(page, 0).locator("details")).to_have_attribute("open", "")
        # Duplicate text on a shifted row must not inherit another row's state.
        expect(self.record(page, 3).locator("details")).not_to_have_attribute(
            "open", ""
        )
        self.save(page)
        expected["communications"].pop(2)
        assert self.snapshot(page, title)["document"] == expected

    def add_draft_under_empty_filter(self, page):
        from playwright.sync_api import expect

        title = "Fictional chronology - blank draft"
        before = self.start(page, title)
        page.get_by_label("Communication order", exact=True).select_option("newest")
        page.get_by_label("Communication scope", exact=True).select_option("route:0")
        page.get_by_label("Communication status filter", exact=True).select_option(
            "received"
        )
        page.get_by_label("Find a communication", exact=True).fill("nothing-matches")
        assert self.visible_indexes(page) == []
        page.get_by_role("button", name="Add communication", exact=True).click()
        expect(page.get_by_label(
            "Communication status filter", exact=True
        )).to_have_value("all")
        assert self.visible_indexes(page) == [0, 3, 4, 5, 2, 1, 6]
        draft = self.record(page, 6)
        expect(draft.locator("details")).to_have_attribute("open", "")
        expect(draft.get_by_label("Subject or short title", exact=True)).to_be_focused()
        expect(
            draft.get_by_label("Communication date (user-entered)", exact=True)
        ).to_have_value("")
        expect(draft.get_by_label("Related opportunity", exact=True)).to_have_value("")
        expect(draft).to_contain_text("Draft · not sent")
        self.save(page)
        saved = self.snapshot(page, title)["document"]
        assert saved["communications"][:-1] == before["communications"]
        assert saved["communications"][-1] == {
            "opportunity": "",
            "date": "",
            "direction": "outgoing",
            "status": "draft",
            "channel": "email",
            "counterparty": "",
            "subject": "",
            "content": "",
            "evidence_links": [],
        }
        assert saved["sources"] == before["sources"]
        assert saved["opportunities"] == before["opportunities"]


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-communication-view-proof-"))
    receipt = {"passed": False}
    resources = {"browser_closed": False, "server_closed": False}
    with (
        tempfile.TemporaryDirectory(
            prefix="sinter-communication-view-workspace-"
        ) as temporary,
        ExitStack() as guard,
    ):
        for name in ("chat", "search", "_post", "_get"):
            guard.enter_context(
                patch.object(
                    client,
                    name,
                    side_effect=AssertionError("Unexpected remote " + name),
                )
            )
        server = make_server(port=0, directory=temporary)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright, args.chromium)
                try:
                    checks = CommunicationChecks(
                        browser, f"http://127.0.0.1:{server.server_port}", artifacts
                    )
                    checks.check(
                        "communication-unchanged-search-order-scope",
                        checks.unchanged_views,
                    )
                    checks.check(
                        "communication-canonical-edit-remove",
                        checks.canonical_edit_and_removal,
                    )
                    checks.check(
                        "communication-discoverable-blank-draft",
                        checks.add_draft_under_empty_filter,
                    )
                    checks.check(
                        "communication-lazy-editors-status-preview-hidden-save",
                        checks.lazy_status_and_preview,
                    )
                    checks.check(
                        "communication-current-safe-evidence-navigation",
                        checks.evidence_navigation_transitions,
                    )
                    checks.check(
                        "communication-mobile-literal-evidence-no-overflow",
                        checks.mobile_literal_preview,
                    )
                    receipt = {
                        "schema": "sinter-communication-view-browser/v1",
                        "fixture_only": True,
                        "fixture_route_count": 12,
                        "fixture_source_count": 76,
                        "communication_scale": getattr(
                            checks, "communication_scale_evidence", None
                        ),
                        "checks": checks.results,
                        "screenshots": checks.screenshots,
                        "browser_errors": checks.errors,
                        "external_requests": checks.external,
                        "model_operations_requested": 0,
                        "passed": all(row["passed"] for row in checks.results)
                        and not checks.errors
                        and not checks.external,
                    }
                finally:
                    browser.close()
                    resources["browser_closed"] = True
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
            resources["server_closed"] = not thread.is_alive()
    receipt["resources"] = resources
    receipt["source_sha256"] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            "src/sinter/web/campaigns.js",
            "src/sinter/web/campaign-communication-view.js",
            "src/sinter/web/campaign-communications.js",
            "src/sinter/web/campaigns.css",
        )
    }
    (artifacts / "browser-receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(artifacts / "browser-receipt.json")
    if not receipt["passed"] or not all(resources.values()):
        raise SystemExit("FAIL: inspect retained fictional browser receipt.")


if __name__ == "__main__":
    main()
