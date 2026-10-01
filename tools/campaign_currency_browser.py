"""Use explicit funding currencies in a local fictional campaign, without conversion."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import threading
import zipfile
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, UUID, uuid5
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.campaign_browser import CampaignChecks  # noqa: E402


def fixture(title: str, currency: str | None = None) -> dict:
    """An explicitly fictional, fully scoped route with retained AUD costs."""
    today = date.today().isoformat()
    source = {
        "id": "a" * 32,
        "title": "Fictional programme terms",
        "url": "https://example.invalid/funding",
        "checked_at": today,
        "notes": "Fictional fixture only; no application, award or authority.",
    }
    route = {
        "name": "Fictional funding route",
        "funder": "Example Foundation",
        "url": source["url"],
        "ceiling": "50000",
        "route_type": "cash_grant",
        "status": "open",
        "application_mode": "not_required",
        "application_window": "rolling",
        "window_source_id": source["id"],
        "window_source_url": source["url"],
        "window_source_quote": "Applications are accepted year-round.",
        "window_checked_at": today,
        "fit": "Retain original fictional terms; no commitment is made.",
    }
    if currency is not None:
        route["ceiling_currency"] = currency
    return {
        "title": title,
        "organisation": "Fictional Community Association",
        "objective": (
            "Compare entered funding terms with a separately quoted AUD pilot."
        ),
        "opportunities": [route],
        "sources": [source],
        "requirements": [
            {
                "opportunity": route["name"],
                "rule": "Applicant type accepted",
                "status": "met",
                "source_id": source["id"],
                "source_url": source["url"],
                "source_quote": "Fictional community associations may apply.",
                "checked_at": today,
                "evidence": "User-entered fictional check; unverified.",
            }
        ],
        "budget": [
            {
                "item": "Fictional pilot quote",
                "opportunity": route["name"],
                "quantity": 1,
                "unit_cost": "60000",
                "quote_reference": "Fictional AUD 60,000 quote; GST included.",
            }
        ],
        "actions": [
            {
                "task": "Retain the explicitly recorded action",
                "opportunity": route["name"],
                "scope_confirmed": True,
                "owner": "Fictional Coordinator",
                "owner_kind": "person",
                "owner_confirmed": True,
                "status": "open",
            }
        ],
    }


class CurrencyChecks(CampaignChecks):
    def same_second_reopen_latest(self, page):
        from playwright.sync_api import expect

        with (
            patch("sinter.campaigns.utc_now", return_value="2026-10-01T12:00:00+00:00"),
            patch("sinter.campaigns.uuid") as campaign_uuid,
        ):
            # Scope IDs to the store; Playwright also uses the stdlib uuid module.
            campaign_uuid.uuid4.side_effect = [
                UUID(hex="1" * 32), UUID(hex="f" * 32)
            ]
            campaign_uuid.uuid5 = uuid5
            campaign_uuid.NAMESPACE_URL = NAMESPACE_URL
            self.import_fixture(page, fixture("Fictional older tied USD", "USD"))
            older = self.save_snapshot(page)
            self.import_fixture(page, fixture("Fictional latest tied other", "other"))
            latest = self.save_snapshot(page)

        assert [older["id"], latest["id"]] == ["1" * 32, "f" * 32]
        retained_older = self.app.campaigns.get(older["id"])
        assert retained_older == older, f"Older campaign changed: {retained_older!r}"
        page.reload()
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(
            latest["document"]["title"]
        )
        expect(self.details(page)).to_have_value("other")
        assert (
            self.app.campaigns.get(latest["id"]) == latest
        ), "Latest snapshot changed."
        assert self.app.campaigns.get(older["id"]) == older, "Older snapshot changed."
        self.screenshot(page, "currency-same-second-latest", full_page=True)

    def details(self, page):
        from playwright.sync_api import expect

        page.get_by_role("tab", name="Opportunities", exact=True).click()
        editor = page.locator(".campaign-opportunity-editor")
        if editor.get_attribute("open") is None:
            editor.locator("summary").click()
        control = page.get_by_label("Funding ceiling currency", exact=True)
        expect(control).to_be_visible()
        return control

    def backup(self, page, name):
        self.transfers(page)
        with page.expect_download() as downloaded:
            page.get_by_role(
                "button", name="Export campaign backup", exact=True
            ).click()
        path = self.artifacts / (name + ".json")
        downloaded.value.save_as(str(path))
        return json.loads(path.read_text())

    def brief(self, page):
        from playwright.sync_api import expect

        with page.expect_response("**/api/campaigns/prepare") as prepared:
            page.get_by_role(
                "button", name="Prepare campaign brief", exact=True
            ).click()
        region = page.get_by_role("region", name="Your draft report")
        expect(region).to_be_visible()
        return prepared.value.json(), region

    def save_snapshot(self, page):
        with page.expect_response("**/api/campaigns/save") as saved:
            self.save(page)
        return saved.value.json()

    def usd_save_reopen_restore_and_word(self, page):
        from playwright.sync_api import expect

        document = fixture("Fictional USD restoration")
        self.import_fixture(page, document)
        control = self.details(page)
        expect(control).to_have_value("AUD")
        saved_legacy = self.save_snapshot(page)
        assert "ceiling_currency" not in saved_legacy["document"]["opportunities"][0]
        legacy_report, region = self.brief(page)
        assert "A$50,000" in legacy_report["document_markdown"]
        quoted = legacy_report["budget_summary"]["by_opportunity"][0]
        assert quoted["over_ceiling"] is None
        assert quoted["quoted_subtotal_over_ceiling"] is True
        assert "No GST conversion was made" in quoted["amount_basis_note"]
        assert legacy_report["readiness"]["budgets_over_ceiling"] == 0
        with page.expect_response("**/api/reports") as saved_report:
            region.get_by_role(
                "button", name="Save to this computer", exact=True
            ).click()
        historical_id = saved_report.value.json()["id"]
        historical = self.app.store.report(historical_id)
        self.details(page).select_option("USD")
        expect(page.locator("#campaign-output")).to_have_attribute("data-stale", "true")
        expect(
            region.get_by_role("button", name="Download Word brief (.docx)", exact=True)
        ).to_be_disabled()
        expect(page.get_by_role("region", name="Selected opportunity")).to_contain_text(
            "Up to USD 50,000"
        )
        expect(page.locator(".campaign-summary")).to_contain_text(
            "1funding currencies to review"
        )
        expect(
            page.get_by_role("region", name="Campaign decision and next move")
        ).to_contain_text("project costs are AUD")
        expect(
            page.get_by_role("region", name="Campaign decision and next move")
        ).to_contain_text("Retain the explicitly recorded action")
        page.get_by_role("tab", name="Budget", exact=True).click()
        expect(page.locator(".campaign-budget-total")).to_have_text(
            "Recorded quoted subtotal (AUD): A$60,000.00"
        )
        expect(
            page.locator(".campaign-section .campaign-currency-comparison")
        ).to_contain_text("No currency conversion or ceiling comparison was made")
        saved_usd = self.save_snapshot(page)
        assert saved_usd["document"]["budget"] == saved_legacy["document"]["budget"]
        assert saved_usd["document"]["opportunities"][0]["ceiling_currency"] == "USD"
        report, region = self.brief(page)
        self.assert_not_compared(report, "USD")
        with page.expect_download() as downloaded:
            region.get_by_role(
                "button", name="Download Word brief (.docx)", exact=True
            ).click()
        word = self.artifacts / "usd-decision-brief.docx"
        downloaded.value.save_as(str(word))
        with zipfile.ZipFile(word) as package:
            xml = ElementTree.fromstring(package.read("word/document.xml"))
        text = " ".join(xml.itertext())
        assert "USD 50,000" in text and "A$60,000" in text, text
        assert "No currency conversion or ceiling comparison was made" in text, text
        assert "A$50,000" not in text, text
        backup = self.backup(page, "usd-saved-backup")
        assert backup == saved_usd["document"]
        page.reload()
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(
            document["title"]
        )
        expect(self.details(page)).to_have_value("USD")
        expect(page.get_by_label("Funding ceiling amount", exact=True)).to_have_value(
            "50000.00"
        )
        assert self.app.campaigns.get(saved_usd["id"]) == saved_usd
        restored = dict(backup, title="Restored fictional USD campaign")
        self.import_fixture(page, restored)
        expect(self.details(page)).to_have_value("USD")
        restored_saved = self.save_snapshot(page)
        assert restored_saved["id"] != saved_usd["id"]
        assert (
            restored_saved["document"]["opportunities"]
            == saved_usd["document"]["opportunities"]
        )
        assert self.app.campaigns.get(saved_usd["id"]) == saved_usd
        assert self.app.store.report(historical_id) == historical
        assert "A$50,000" in historical["document_markdown"]
        self.screenshot(page, "currency-usd-restored", full_page=True)

    def assert_not_compared(self, report, currency):
        row = report["budget_summary"]["by_opportunity"][0]
        assert row["ceiling_currency"] == currency and row["over_ceiling"] is None
        assert report["readiness"]["budgets_over_ceiling"] == 0
        assert report["readiness"]["funding_currency_review"] == 1
        for text in (report["markdown"], report["document_markdown"]):
            assert "No currency conversion or ceiling comparison was made" in text
            assert "A$50,000" not in text
            assert "exceeds the entered funding ceiling" not in text

    def unconfirmed_and_other(self, page):
        from playwright.sync_api import expect

        self.import_fixture(
            page, fixture("Fictional unconfirmed currency", "unconfirmed")
        )
        expect(self.details(page)).to_have_value("unconfirmed")
        expect(page.get_by_role("region", name="Selected opportunity")).to_contain_text(
            "50,000 (currency unconfirmed)"
        )
        self.save_snapshot(page)
        report, _ = self.brief(page)
        self.assert_not_compared(report, "unconfirmed")
        self.details(page).select_option("other")
        page.get_by_label("Project fit and timing", exact=True).fill(
            "Fictional JPY terms retained exactly; comparison unsupported."
        )
        saved = self.save_snapshot(page)
        report, _ = self.brief(page)
        self.assert_not_compared(report, "other")
        assert "Fictional JPY terms" in report["markdown"]
        backup = self.backup(page, "other-currency-backup")
        assert backup == saved["document"]
        page.reload()
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(
            saved["document"]["title"]
        )
        expect(self.details(page)).to_have_value("other")
        expect(page.get_by_label("Project fit and timing", exact=True)).to_have_value(
            "Fictional JPY terms retained exactly; comparison unsupported."
        )
        self.screenshot(page, "currency-other", full_page=True)

    def non_cash_and_new_unknown(self, page):
        from playwright.sync_api import expect

        document = fixture("Fictional non-cash currency", "USD")
        document["opportunities"][0]["route_type"] = "non_cash_support"
        self.import_fixture(page, document)
        expect(page.get_by_role("region", name="Selected opportunity")).to_contain_text(
            "No grant cash"
        )
        report, _ = self.brief(page)
        assert report["readiness"]["funding_currency_review"] == 0
        assert report["budget_summary"]["by_opportunity"][0]["over_ceiling"] is None
        assert "No grant cash" in report["document_markdown"]
        page.get_by_role("button", name="Add opportunity", exact=True).click()
        expect(self.details(page)).to_have_value("unconfirmed")
        page.get_by_label("Funding ceiling amount", exact=True).fill("50000.50")
        expect(page.get_by_role("region", name="Selected opportunity")).to_contain_text(
            "50,000.50 (currency unconfirmed)"
        )
        backup = self.backup(page, "new-unconfirmed-backup")
        assert backup["opportunities"][-1]["ceiling_currency"] == "unconfirmed"
        self.details(page).select_option("AUD")
        saved = self.save_snapshot(page)
        assert "ceiling_currency" not in saved["document"]["opportunities"][-1]
        assert saved["document"]["opportunities"][-1]["ceiling"] == "50000.50"
        assert saved["document"]["opportunities"][0]["ceiling_currency"] == "USD"
        self.screenshot(page, "currency-new-explicit-aud", full_page=True)

    def legacy_and_invalid_preservation(self, page):
        from playwright.sync_api import expect

        self.import_fixture(page, fixture("Fictional retained legacy AUD"))
        expect(self.details(page)).to_have_value("AUD")
        saved = self.save_snapshot(page)
        assert (
            "ceiling_currency"
            not in self.backup(page, "legacy-backup")["opportunities"][0]
        )
        malformed = dict(saved["document"], title="Invalid fictional currency")
        malformed["opportunities"] = [
            dict(malformed["opportunities"][0], ceiling_currency="JPY")
        ]
        self.transfers(page)
        with page.expect_response("**/api/campaigns/prepare") as refused:
            page.get_by_label("Import campaign backup", exact=True).set_input_files(
                {
                    "name": "invalid-currency.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(malformed).encode(),
                }
            )
        assert refused.value.status == 400
        expect(page.get_by_role("alert")).to_contain_text("funding ceiling")
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(
            saved["document"]["title"]
        )
        assert self.app.campaigns.get(saved["id"]) == saved
        expect(self.details(page)).to_have_value("AUD")
        self.errors[:] = [
            row
            for row in self.errors
            if not (
                row.get("check") == "currency-legacy_and_invalid_preservation"
                and row.get("url") == self.base + "/api/campaigns/prepare"
                and row["error"]
                == "Failed to load resource: the server responded with a status "
                "of 400 (Bad Request)"
            )
        ]


def main(argv: list[str] | None = None) -> None:
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-campaign-currency-proof-"))
    paths = (
        "src/sinter/campaign_currency.py",
        "src/sinter/campaigns.py",
        "src/sinter/web/campaign-currency.js",
        "src/sinter/web/campaign-decision.js",
        "src/sinter/web/campaigns.js",
        "tools/campaign_currency_browser.py",
    )
    hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths
    }
    resources = {"browser_closed": False, "server_closed": False}
    with tempfile.TemporaryDirectory(
        prefix="sinter-campaign-currency-workspace-"
    ) as data:
        with ExitStack() as guard:
            for name in ("chat", "search", "_post", "_get"):
                guard.enter_context(
                    patch.object(
                        client,
                        name,
                        side_effect=AssertionError("Offline currency workflow only"),
                    )
                )
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        checks = CurrencyChecks(
                            browser, f"http://127.0.0.1:{server.server_port}", artifacts
                        )
                        checks.app = server.app
                        for name in (
                            "same_second_reopen_latest",
                            "usd_save_reopen_restore_and_word",
                            "unconfirmed_and_other",
                            "non_cash_and_new_unknown",
                            "legacy_and_invalid_preservation",
                        ):
                            checks.check("currency-" + name, getattr(checks, name))
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
        "schema": "sinter-campaign-currency-browser/v1",
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
    receipt_path = artifacts / "browser-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))
    retained = ROOT / "browser-artifacts" / "campaign-currency"
    retained.mkdir(parents=True, exist_ok=True)
    for path in [receipt_path, *(artifacts / name for name in checks.screenshots)]:
        shutil.copyfile(path, retained / path.name)
    print(artifacts / "browser-receipt.json")
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect retained fictional currency receipt.")


if __name__ == "__main__":
    main()
