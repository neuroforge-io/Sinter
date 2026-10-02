"""Fictional funding-record journeys through Sinter's existing local runtime.

Checks manual edits, exact source snapshots, server totals, persistence and late
responses. No model, external page, real funding claim or private record is used.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import threading
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.campaign_browser import CampaignChecks  # noqa: E402

CASH = "Fictional cash programme"
CREDITS = "Fictional credits programme"
TODAY = date.today().isoformat()


def fixture(title: str = "Fictional funding tracking") -> dict:
    sources = [
        {
            "id": key * 32,
            "title": name,
            "url": "https://example.invalid/" + suffix,
            "checked_at": TODAY,
            "notes": "Fictional test terms only; not an application, award or receipt.",
        }
        for key, name, suffix in (
            ("a", "Fictional cash terms", "cash-terms"),
            ("b", "Fictional credit terms", "credit-terms"),
            ("c", "Fictional revised cash terms", "cash-terms-v2"),
        )
    ]
    return {
        "schema": "sinter-campaign/v1",
        "title": title,
        "organisation": "Fictional Community Association",
        "objective": "Exercise recorded funding stages without making commitments.",
        "sources": sources,
        "opportunities": [
            {
                "name": name,
                "funder": "Example Foundation",
                "route_type": kind,
                "status": "open",
                "ceiling": amount,
                "ceiling_currency": currency,
                "application_mode": "not_required",
                "application_window": "rolling",
                "window_source_id": source["id"],
                "window_source_url": source["url"],
                "window_source_quote": "Fictional applications are accepted year-round.",
                "window_checked_at": TODAY,
                "url": source["url"],
                "fit": "Fictional fixture; no real eligibility, application or income.",
            }
            for name, kind, amount, currency, source in (
                (CASH, "cash_grant", "10000.00", "AUD", sources[0]),
                (CREDITS, "non_cash_support", "2000.00", "USD", sources[1]),
            )
        ],
    }


def portfolio_fixture(count: int, title: str) -> dict:
    document = fixture(title)
    route = document["opportunities"][0]
    document["opportunities"] = [
        dict(route, name=f"Fictional portfolio route {index + 1:02d}",
             status="closed" if index % 2 else "open")
        for index in range(count)
    ]
    return document


class FundingChecks(CampaignChecks):
    def recorded_deadline_visibility(self, page):
        from playwright.sync_api import expect

        document = fixture("Fictional recorded deadline visibility")
        row = document["opportunities"][0]
        row.update(application_window="unknown", deadline="2099-01-02",
                   window_checked_at="", window_source_quote="")
        document["opportunities"] = [row]
        self.import_fixture(page, document)
        baseline = self.update(page)
        saved = self.save_snapshot(page)
        page.get_by_role("tab", name="Opportunities", exact=True).click()
        facts = page.locator(".campaign-opportunity-facts")
        rail = page.locator(".campaign-opportunity")
        date_labels = facts.locator("dt:visible").filter(
            has_text=re.compile(r"^Recorded closing date$"))
        expect(date_labels).to_have_count(1)
        expect(facts).to_contain_text("2 Jan 2099")
        expect(facts).to_contain_text("Application window not verified")
        expect(rail).to_contain_text("Application window not verified")
        assert self.app.campaigns.get(saved["id"]) == saved
        details = page.locator(".campaign-opportunity-editor")
        if details.get_attribute("open") is None:
            details.locator("summary").click()
        date_input = page.get_by_label("Recorded closing date", exact=True)
        checked_input = page.get_by_label("Window wording checked on", exact=True)
        window_input = page.get_by_label("Application window", exact=True)
        status_input = page.get_by_label("Opportunity status", exact=True)
        expect(checked_input).to_have_value("")
        date_input.fill("")
        expect(date_labels).to_have_count(0)
        date_input.fill("2000-01-02")
        expect(date_labels).to_have_count(1)
        expect(facts).to_contain_text("2 Jan 2000")
        expect(rail).not_to_contain_text("Recorded closing date passed")
        for kind in ("fixed", "rolling", "unknown"):
            window_input.select_option(kind)
            expect(date_labels).to_have_count(0 if kind == "rolling" else 1)
            expect(checked_input).to_have_value("")
            if kind == "unknown":
                expect(facts).to_contain_text("Application window not verified")
        for status in ("submitted", "closed", "not_pursuing", "open"):
            status_input.select_option(status)
            expect(date_labels).to_have_count(1)
            if status in ("submitted", "closed"):
                expect(facts).not_to_contain_text("Application window not verified")
            else:
                expect(facts).to_contain_text("Application window not verified")
        date_input.fill("2099-01-02")
        restored = self.save_snapshot(page)
        assert restored["document"] == saved["document"]
        assert self.update(page) == baseline
        page.reload()
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(saved["document"]["title"])
        page.get_by_role("tab", name="Opportunities", exact=True).click()
        expect(page.locator(".campaign-opportunity-facts")).to_contain_text(
            "Application window not verified")
        expect(page.locator(".campaign-opportunity-facts")).to_contain_text("2 Jan 2099")
        assert self.app.campaigns.get(saved["id"]) == restored
        self.screenshot(page, "recorded-deadline-unverified", full_page=True)

    def submission_history_labels_separate_cash_and_other_events(self, page):
        from playwright.sync_api import expect

        document = fixture("Fictional mixed submission history")
        cash, credit = document["opportunities"]
        rows = []
        for index in range(11):
            credits = index in (6, 7)
            row = dict(credit if credits else cash,
                       name=f"Fictional recorded submission {index + 1}",
                       status="closed" if index == 7 else "submitted",
                       route_type="equity" if index > 7 else
                       "non_cash_support" if credits else "cash_grant")
            row["funding_tracking"] = {
                "round_key": row["name"], "benefit_type": "credits" if credits else "cash",
                "application_status": "submitted",
                "requested": {"amount": None if index == 5 else "10.00",
                              "currency": "USD" if credits else "AUD"},
            }
            rows.append(row)
        document["opportunities"] = rows
        self.import_fixture(page, document)
        summary = self.update(page)
        history = summary["counts"]["submission_history"]
        assert history["ever_recorded"] == {"cash": 6, "credits": 2, "equity": 3}
        assert history["not_marked_closed"] == {"cash": 6, "credits": 1, "equity": 3}
        assert history["marked_closed"] == {"credits": 1}
        visible = page.locator(".campaign-funding-submission-history")
        expect(visible).to_be_visible()
        expect(visible).to_contain_text("Ever recorded as submitted: Cash: 6 · Credits: 2 · Investment / EOI: 3")
        expect(visible).to_contain_text("Not marked closed: Cash: 6 · Credits: 1 · Investment / EOI: 3")
        expect(visible).to_contain_text("Marked closed: Credits: 1")
        expect(visible).to_contain_text("not a verified current application window")
        submitted = page.locator('[data-funding-stage="submitted"]')
        expect(submitted).to_contain_text("Submitted requests · all recorded history")
        expect(submitted).to_contain_text("not a cash-application count")
        expect(submitted).to_contain_text("11 rounds / records")
        expect(page.locator('[data-funding-stage="available"]')).to_contain_text(
            "Eligible recorded ceilings"
        )
        expect(page.locator('[data-funding-stage="available"]')).to_contain_text(
            "Not awards or guaranteed funding"
        )
        saved = self.save_snapshot(page)
        assert saved["document"]["opportunities"] == self.backup(
            page, "funding-mixed-submission-history"
        )["opportunities"]
        self.screenshot(page, "funding-mixed-submission-history", full_page=True)

    def tracking(self, page, opportunity=CASH):
        page.get_by_role("tab", name="Opportunities", exact=True).click()
        page.locator(".campaign-opportunity").filter(has_text=opportunity).click()
        details = page.locator(".campaign-funding-tracking")
        if details.get_attribute("open") is None:
            details.locator("summary").first.click()
        return details

    def source(self, scope, label, source_title):
        from playwright.sync_api import expect

        control = scope.get_by_label(label, exact=True)
        picker = scope.locator(".campaign-source-picker").filter(has_text=label)
        control.fill(source_title)
        link = picker.get_by_role("button", name=re.compile(r"^Link source: "))
        expect(link).to_have_count(1)
        link.click()

    def claim(self, tracking, label, source_title, quote, explanation):
        details = tracking.locator(".campaign-funding-claim").filter(has_text=label + " evidence")
        if details.get_attribute("open") is None:
            details.locator("summary").first.click()
        self.source(details, label + " saved source", source_title)
        details.get_by_label(label + " exact source wording", exact=True).fill(quote)
        details.get_by_label(label + " wording checked date", exact=True).fill(TODAY)
        details.get_by_label(label + " explanation", exact=True).fill(explanation)
        return details

    def amount(self, tracking, label, amount, currency, source_title, quote):
        details = tracking.locator(".campaign-funding-amount").filter(has_text=label + " amount and source")
        if details.get_attribute("open") is None:
            details.locator("summary").first.click()
        details.get_by_label(label + " amount", exact=True).fill(amount)
        details.get_by_label(label + " currency", exact=True).select_option(currency)
        details.get_by_label(label + " amount notes", exact=True).fill(
            "Fictional cumulative amount for this round; no real event is asserted."
        )
        evidence = details.locator(".campaign-funding-amount-evidence")
        if evidence.get_attribute("open") is None:
            evidence.locator("summary").first.click()
        self.source(evidence, label + " amount source", source_title)
        evidence.get_by_label(label + " exact amount wording", exact=True).fill(quote)
        evidence.get_by_label(label + " amount wording checked date", exact=True).fill(
            TODAY
        )
        return details

    def update(self, page):
        from playwright.sync_api import expect

        button = page.get_by_role("button", name="Update funding totals", exact=True)
        with page.expect_response("**/api/campaigns/funding-summary") as response:
            button.click()
        expect(button).to_be_enabled()
        expect(page.locator(".campaign-funding-summary")).to_have_attribute(
            "data-stale", "false"
        )
        result = response.value.json()
        assert result["schema"] == "sinter-funding-summary/v1"
        return result

    def save_snapshot(self, page):
        with page.expect_response("**/api/campaigns/save") as response:
            self.save(page)
        return response.value.json()

    def backup(self, page, name):
        self.transfers(page)
        with page.expect_download() as downloaded:
            page.get_by_role(
                "button", name="Export campaign backup", exact=True
            ).click()
        path = self.artifacts / (name + ".json")
        downloaded.value.save_as(str(path))
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def group(summary, stage, benefit, currency):
        return next(
            row for row in summary["stages"][stage]["groups"]
            if row["benefit_type"] == benefit and row["currency"] == currency
        )

    def legacy_read_is_not_an_edit(self, page):
        from playwright.sync_api import expect

        self.import_fixture(page, fixture("Fictional untouched legacy funding"))
        tracking = self.tracking(page)
        expect(tracking.get_by_label("Programme round key", exact=True)).to_have_value(
            ""
        )
        expect(tracking.get_by_label("Benefit being tracked", exact=True)).to_have_value(
            "unknown"
        )
        expect(tracking.get_by_label("Applicant eligibility", exact=True)).to_have_value(
            "unknown"
        )
        viewed = self.backup(page, "legacy-viewed")
        assert all("funding_tracking" not in row for row in viewed["opportunities"])
        summary = self.update(page)
        assert summary["counts"]["missing_round_keys"] == 2
        assert summary["stages"]["available"]["groups"] == []
        expect(page.locator(".campaign-funding-summary")).to_contain_text(
            "2 routes have no programme round key"
        )
        saved = self.save_snapshot(page)
        assert all(
            "funding_tracking" not in row for row in saved["document"]["opportunities"]
        )
        self.screenshot(page, "funding-legacy-unmodified")

    def workflow(self, page):
        from playwright.sync_api import expect

        self.import_fixture(page, fixture("Fictional cash and credit records"))
        tracking = self.tracking(page)
        tracking.get_by_label("Programme round key", exact=True).fill(
            "fictional-cash-2026"
        )
        tracking.get_by_label("Benefit being tracked", exact=True).select_option("cash")
        tracking.get_by_label("Applicant eligibility", exact=True).select_option(
            "eligible"
        )
        tracking.get_by_label(
            "Who the advertised ceiling applies to", exact=True
        ).select_option("individual")
        tracking.get_by_label("Application record", exact=True).select_option("preparing")
        self.claim(
            tracking, "Eligibility", "Fictional cash terms",
            "Fictional community associations may apply.",
            "The fictional test association matches the entered applicant type.",
        )
        self.claim(
            tracking, "Individual ceiling", "Fictional cash terms",
            "Fictional cash funding is up to AUD 10,000 for one project.",
            "The fictional ceiling applies to one applicant rather than a pool.",
        )
        self.amount(
            tracking, "Target", "2500.50", "AUD", "Fictional cash terms",
            "Fictional draft target AUD 2,500.50; no application has been submitted.",
        )
        cash_summary = self.update(page)
        assert self.group(cash_summary, "available", "cash", "AUD")["known_total"] == (
            "10000.00"
        )
        assert self.group(cash_summary, "targets", "cash", "AUD")["known_total"] == (
            "2500.50"
        )
        tracking = self.tracking(page, CREDITS)
        tracking.get_by_label("Programme round key", exact=True).fill(
            "fictional-credit-2026"
        )
        tracking.get_by_label("Benefit being tracked", exact=True).select_option(
            "credits"
        )
        tracking.get_by_label("Application record", exact=True).select_option("submitted")
        tracking.get_by_label("Award record", exact=True).select_option("awarded")
        tracking.get_by_label("Receipt record", exact=True).select_option("received")
        route = page.locator(".campaign-opportunity-editor")
        if route.get_attribute("open") is None:
            route.locator("summary").first.click()
        page.get_by_label("Opportunity status", exact=True).select_option("submitted")
        for label, amount in (
            ("Requested", "1800.50"), ("Awarded", "1500.25"), ("Received", "100.00")
        ):
            self.amount(
                tracking, label, amount, "USD", "Fictional credit terms",
                f"Fictional {label.lower()} nominal USD credits: {amount}.",
            )
        summary = self.update(page)
        assert summary["counts"]["missing_round_keys"] == 0
        for stage, amount in (
            ("submitted", "1800.50"), ("awarded", "1500.25"), ("received", "100.00")
        ):
            group = self.group(summary, stage, "credits", "USD")
            assert group["known_total"] == amount
            stage_card = page.locator(f'[data-funding-stage="{stage}"]')
            expect(stage_card).to_contain_text("Credits · USD")
            expect(stage_card).not_to_contain_text("Cash · USD")
        expect(page.locator('[data-funding-stage="targets"]')).to_contain_text(
            "AUD 2,500.50 known subtotal"
        )
        saved = self.save_snapshot(page)
        expect(page.locator(".campaign-funding-summary")).to_have_attribute(
            "data-stale", "true"
        )
        backup = self.backup(page, "funding-saved-backup")
        assert backup == saved["document"]
        cash, credit = backup["opportunities"]
        assert cash["funding_tracking"]["application_status"] == "preparing"
        assert cash["funding_tracking"]["target"]["source_quote"].startswith(
            "Fictional draft target"
        )
        receipt = credit["funding_tracking"]["received"]
        assert receipt["amount"] == "100.00" and receipt["currency"] == "USD"
        assert receipt["source_id"] == "b" * 32
        assert receipt["source_url"] == "https://example.invalid/credit-terms"
        assert receipt["checked_at"] == TODAY
        assert "nominal USD credits" in receipt["source_quote"]
        self.screenshot(page, "funding-cash-credits", full_page=True)
        page.reload()
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(
            saved["document"]["title"]
        )
        reopened = self.update(page)
        assert reopened == summary
        restored = dict(backup, title="Restored fictional funding records")
        self.import_fixture(page, restored)
        restored_saved = self.save_snapshot(page)
        assert restored_saved["id"] != saved["id"]
        assert restored_saved["document"]["opportunities"] == backup["opportunities"]
        assert self.app.campaigns.get(saved["id"]) == saved
        assert self.update(page) == summary
        tracking = self.tracking(page, CREDITS)
        expect(tracking.get_by_label("Benefit being tracked", exact=True)).to_have_value(
            "credits"
        )
        received = self.amount(
            tracking, "Received", "100.00", "USD", "Fictional credit terms",
            receipt["source_quote"],
        )
        expect(received.get_by_label("Received source URL snapshot", exact=True)).to_have_value(
            receipt["source_url"]
        )
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth + 1"
        ), "Funding view overflows the mobile viewport."
        self.screenshot(page, "funding-restored-mobile", full_page=True)

    def source_changes_and_protection(self, page):
        from playwright.sync_api import expect

        self.import_fixture(page, fixture("Fictional source-change checks"))
        tracking = self.tracking(page)
        tracking.get_by_label("Programme round key", exact=True).fill("fictional-source-check")
        tracking.get_by_label("Benefit being tracked", exact=True).select_option("cash")
        tracking.get_by_label("Applicant eligibility", exact=True).select_option("eligible")
        tracking.get_by_label(
            "Who the advertised ceiling applies to", exact=True
        ).select_option("individual")
        tracking.get_by_label("Application record", exact=True).select_option("preparing")
        eligibility = self.claim(
            tracking, "Eligibility", "Fictional cash terms", "Fictional applicant rule.",
            "Fictional entered eligibility explanation retained during source changes.",
        )
        self.claim(
            tracking, "Individual ceiling", "Fictional cash terms", "Fictional individual ceiling.",
            "Fictional individual ceiling explanation.",
        )
        target = self.amount(
            tracking, "Target", "200.00", "AUD", "Fictional cash terms",
            "Fictional draft target AUD 200.00.",
        )
        self.update(page)
        self.source(eligibility, "Eligibility saved source", "Fictional revised cash terms")
        expect(eligibility.get_by_label("Eligibility exact source wording", exact=True)).to_have_value("")
        expect(eligibility.get_by_label("Eligibility wording checked date", exact=True)).to_have_value("")
        expect(eligibility.get_by_label("Eligibility explanation", exact=True)).to_have_value(
            re.compile("retained during source changes")
        )
        expect(tracking.get_by_label("Applicant eligibility", exact=True)).to_have_value("eligible")
        summary = self.update(page)
        assert summary["stages"]["available"]["groups"] == []
        assert any(row["reason"] == "eligibility_evidence_missing" for row in summary["exclusions"])
        evidence = target.locator(".campaign-funding-amount-evidence")
        self.source(evidence, "Target amount source", "Fictional revised cash terms")
        expect(evidence.get_by_label("Target exact amount wording", exact=True)).to_have_value("")
        expect(evidence.get_by_label("Target source URL snapshot", exact=True)).to_have_value(
            "https://example.invalid/cash-terms-v2"
        )
        expect(evidence.get_by_label("Target amount wording checked date", exact=True)).to_have_value(TODAY)
        expect(target.get_by_label("Target amount", exact=True)).to_have_value("200.00")
        page.get_by_role("tab", name="Sources", exact=True).click()
        source = page.get_by_role("article", name="Campaign source: Fictional revised cash terms", exact=True)
        details = source.locator("details")
        if details.get_attribute("open") is None:
            details.locator("summary").click()
        source.get_by_role("button", name="Remove source", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("funding record")
        expect(source).to_be_visible()
        retained = self.backup(page, "funding-source-change-backup")
        record = retained["opportunities"][0]["funding_tracking"]
        assert record["eligibility_evidence"]["source_id"] == "c" * 32
        assert record["eligibility_evidence"]["checked_at"] == ""
        assert record["target"]["source_quote"] == ""
        assert record["target"]["amount"] == "200.00"
        self.screenshot(page, "funding-source-protected")

    def delayed_summary_cannot_replace_edited_records(self, page):
        from playwright.sync_api import expect

        document = fixture("Fictional delayed funding summary")
        document["opportunities"][0]["funding_tracking"] = {
            "round_key": "fictional-delay-2026", "benefit_type": "cash",
            "application_status": "preparing",
            "target": {"amount": "2500.50", "currency": "AUD"},
        }
        self.import_fixture(page, document)
        tracking = self.tracking(page)
        details = tracking.locator(".campaign-funding-amount").filter(has_text="Target amount and source")
        details.locator("summary").first.click()
        original = self.update(page)
        pending = []
        pattern = "**/api/campaigns/funding-summary"

        def hold(route):
            pending.append(route)

        page.route(pattern, hold)
        button = page.get_by_role("button", name="Update funding totals", exact=True)
        fulfilled = False
        try:
            with page.expect_request(pattern):
                button.click()
            expect(button).to_be_disabled()
            assert len(pending) == 1
            sent = pending[0].request.post_data_json
            assert sent["document"]["opportunities"][0]["funding_tracking"]["target"]["amount"] == "2500.50"
            # Exercise a queued/re-entrant editor input while its request is in
            # flight. User controls stay inert; no production test flag exists.
            tracking.get_by_label("Target amount", exact=True).evaluate(
                """input => {
                    input.value = '3300.75';
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                }"""
            )
            expect(page.locator(".campaign-funding-summary")).to_have_attribute(
                "data-stale", "true"
            )
            response = pending[0].fetch()
            assert response.ok
            assert response.json() == original
            pending[0].fulfill(response=response)
            fulfilled = True
            expect(button).to_be_enabled()
            expect(tracking.get_by_label("Target amount", exact=True)).to_have_value("3300.75")
            expect(page.locator(".campaign-funding-summary")).to_have_attribute(
                "data-stale", "true"
            )
            expect(page.locator('[data-funding-stage="targets"]')).to_contain_text(
                "AUD 2,500.50 known subtotal"
            )
        finally:
            if not fulfilled:
                for route in pending:
                    route.abort()
            page.unroute(pattern, hold)
        current = self.update(page)
        assert self.group(current, "targets", "cash", "AUD")["known_total"] == "3300.75"
        saved = self.save_snapshot(page)
        assert saved["document"]["opportunities"][0]["funding_tracking"]["target"]["amount"] == "3300.75"
        self.screenshot(page, "funding-late-response-edits-retained")

    def portfolio_view_retains_full_records_and_totals(self, page):
        from playwright.sync_api import expect

        self.import_fixture(page, portfolio_fixture(35, "Fictional 35-route portfolio"))
        initial = self.save_snapshot(page)
        full = self.update(page)
        assert full["counts"]["opportunities"] == 35
        cards = page.locator(".campaign-opportunity")
        count = page.get_by_label("Funding route list count", exact=True)
        expect(cards).to_have_count(20)
        expect(count).to_contain_text("35 of 35 routes match")
        expect(count).to_contain_text("page 1 of 2")
        page.get_by_role("button", name="Next funding routes page", exact=True).click()
        expect(cards).to_have_count(15)
        expect(count).to_contain_text("showing 21–35")
        expect(page.get_by_role("region", name="Selected opportunity", exact=True)).to_contain_text(
            "Fictional portfolio route 01"
        )
        cards.filter(has_text="Fictional portfolio route 35").click()
        search = page.get_by_label("Search funding routes", exact=True)
        search.fill("route 01")
        expect(cards).to_have_count(1)
        expect(page.get_by_label("Opportunity name", exact=True)).to_have_value(
            "Fictional portfolio route 35"
        )
        expect(page.get_by_label("Retained selected funding route", exact=True)).to_contain_text(
            "Retained outside the current filters"
        )
        expect(page.locator(".campaign-save-state")).to_have_text("Saved on this computer")
        expect(page.locator(".campaign-funding-summary")).to_have_attribute("data-stale", "false")
        assert self.update(page)["counts"]["opportunities"] == 35
        search.fill("no such fictional funding route")
        expect(cards).to_have_count(0)
        expect(count).to_contain_text("0 of 35 routes match")
        expect(page.get_by_text("No funding routes match.", exact=False)).to_be_visible()
        expect(page.get_by_role("button", name="Next funding routes page", exact=True)).to_be_disabled()
        page.get_by_role("button", name="Show selected route in list", exact=True).click()
        expect(search).to_have_value("")
        expect(count).to_contain_text("page 2 of 2")
        expect(cards).to_have_count(15)
        page.get_by_label("Filter funding routes by status", exact=True).select_option("closed")
        expect(cards).to_have_count(17)
        expect(count).to_contain_text("17 of 35 routes match")
        expect(page.get_by_label("Opportunity name", exact=True)).to_have_value(
            "Fictional portfolio route 35"
        )
        assert self.update(page)["counts"]["opportunities"] == 35
        expect(page.locator(".campaign-funding-summary")).to_have_attribute("data-stale", "false")
        page.get_by_role("button", name="Show selected route in list", exact=True).click()
        route = page.locator(".campaign-opportunity-editor")
        if route.get_attribute("open") is None:
            route.locator("summary").first.click()
        page.get_by_label("Opportunity name", exact=True).fill(
            "Fictional portfolio route 35 edited"
        )
        saved = self.save_snapshot(page)
        assert len(saved["document"]["opportunities"]) == 35
        assert saved["document"]["opportunities"][:34] == initial["document"]["opportunities"][:34]
        assert saved["document"]["opportunities"][34]["name"] == "Fictional portfolio route 35 edited"
        backup = self.backup(page, "funding-35-route-backup")
        assert backup == saved["document"]
        assert all("funding_tracking" not in row for row in backup["opportunities"])
        restored = dict(backup, title="Restored fictional 35-route portfolio")
        self.import_fixture(page, restored)
        restored_saved = self.save_snapshot(page)
        assert restored_saved["id"] != saved["id"]
        assert restored_saved["document"]["opportunities"] == saved["document"]["opportunities"]
        page.reload()
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(restored["title"])
        expect(cards).to_have_count(20)
        page.get_by_label("Search funding routes", exact=True).fill("route 35 edited")
        expect(cards).to_have_count(1)
        cards.first.click()
        expect(page.get_by_label("Opportunity name", exact=True)).to_have_value(
            "Fictional portfolio route 35 edited"
        )
        assert self.update(page)["counts"]["opportunities"] == 35
        assert self.app.campaigns.get(saved["id"]) == saved
        self.screenshot(page, "funding-35-route-filtered", full_page=True)

    def portfolio_add_limit_keeps_backup(self, page):
        from playwright.sync_api import expect

        self.import_fixture(page, portfolio_fixture(200, "Fictional bounded 200-route portfolio"))
        saved = self.save_snapshot(page)
        expect(page.locator(".campaign-opportunity")).to_have_count(20)
        page.get_by_role("button", name="Add opportunity", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("200-route limit")
        expect(page.get_by_role("alert")).to_contain_text("Export a campaign backup")
        expect(page.locator(".campaign-save-state")).to_have_text("Saved on this computer")
        retained = self.backup(page, "funding-200-route-retained-backup")
        assert len(retained["opportunities"]) == 200
        assert retained == saved["document"]
        assert self.app.campaigns.get(saved["id"]) == saved
        self.screenshot(page, "funding-200-route-add-held")


def main(argv: list[str] | None = None) -> None:
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-campaign-funding-proof-"))
    paths = (
        "src/sinter/campaign_funding.py", "src/sinter/campaigns.py",
        "src/sinter/runtime.py", "src/sinter/runtime_routes.py",
        "src/sinter/web/campaign-funding.js", "src/sinter/web/campaigns.js",
        "src/sinter/web/campaign-opportunity-view.js",
        "src/sinter/web/campaigns.css", "tools/campaign_funding_browser.py",
    )
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}
    resources = {"browser_closed": False, "server_closed": False}
    with tempfile.TemporaryDirectory(prefix="sinter-campaign-funding-workspace-") as data:
        with ExitStack() as guard:
            for name in ("chat", "search", "_post", "_get"):
                guard.enter_context(patch.object(client, name, side_effect=AssertionError(
                    "Fictional offline funding workflow only"
                )))
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        checks = FundingChecks(browser, f"http://127.0.0.1:{server.server_port}", artifacts)
                        checks.app = server.app
                        for name in (
                            "legacy_read_is_not_an_edit", "workflow", "source_changes_and_protection",
                            "delayed_summary_cannot_replace_edited_records",
                            "portfolio_view_retains_full_records_and_totals",
                            "portfolio_add_limit_keeps_backup",
                            "submission_history_labels_separate_cash_and_other_events",
                            "recorded_deadline_visibility",
                        ):
                            checks.check("funding-" + name, getattr(checks, name))
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
        "schema": "sinter-campaign-funding-browser/v1", "fixture_only": True,
        "checks": checks.results, "screenshots": checks.screenshots,
        "browser_errors": checks.errors, "external_requests": checks.external,
        "model_operations_requested": 0, "resources": resources,
        "source_sha256": hashes, "source_unchanged_during_run": unchanged,
        "passed": all(row["passed"] for row in checks.results) and not checks.errors
        and not checks.external and unchanged and all(resources.values()),
    }
    receipt_path = artifacts / "browser-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    retained = ROOT / "browser-artifacts" / "campaign-funding"
    retained.mkdir(parents=True, exist_ok=True)
    for path in [receipt_path, *(artifacts / name for name in checks.screenshots)]:
        shutil.copyfile(path, retained / path.name)
    print(receipt_path)
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect retained fictional funding workflow receipt.")


if __name__ == "__main__":
    main()
