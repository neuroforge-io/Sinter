"""Funding denominations never become an implicit project-budget conversion."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import campaigns, client
from sinter.campaign_currency import (
    CEILING_CURRENCIES,
    can_compare_ceiling,
    ceiling_comparison_note,
    funding_amount,
)
from sinter.store import Store


def fixture(currency=None, *, status="open", route_type="cash_grant"):
    route = {
        "name": "Fictional funding route",
        "funder": "Example Foundation",
        "ceiling": "50000",
        "route_type": route_type,
        "status": status,
        "application_mode": "not_required",
    }
    if currency is not None:
        route["ceiling_currency"] = currency
    return {
        "title": "Fictional currency campaign",
        "organisation": "Example Association",
        "objective": "Review a possible pilot without making a commitment.",
        "opportunities": [route],
        "budget": [
            {
                "item": "Fictional quote",
                "opportunity": route["name"],
                "quantity": 1,
                "unit_cost": "60000",
                "quote_reference": "AUD quote",
            }
        ],
        "actions": [
            {
                "task": "Retain recorded next action",
                "scope_confirmed": True,
                "owner": "Example Person",
                "owner_kind": "person",
                "owner_confirmed": True,
            }
        ],
    }


def test_legacy_absent_and_explicit_aud_keep_input_serialization_and_meaning():
    legacy = campaigns.validate(fixture())
    explicit = campaigns.validate(fixture("AUD"))
    assert legacy == explicit
    assert "ceiling_currency" not in legacy["opportunities"][0]
    encoded = json.dumps(legacy, sort_keys=True).encode()
    assert (
        hashlib.sha256(encoded).digest()
        == hashlib.sha256(json.dumps(explicit, sort_keys=True).encode()).digest()
    )
    for book in (legacy, explicit):
        report = campaigns.prepare(book)
        assert "**Cash award / ceiling:** A$50,000" in report["document_markdown"]
        group = report["budget_summary"]["by_opportunity"][0]
        assert group["over_ceiling"] is None
        assert group["quoted_subtotal_over_ceiling"] is True
        assert report["readiness"]["budgets_over_ceiling"] == 0
        assert report["readiness"]["quoted_subtotals_above_ceiling"] == 1
        assert report["readiness"]["funding_currency_review"] == 0


@pytest.mark.parametrize("currency", sorted(CEILING_CURRENCIES - {"AUD"}))
def test_non_aud_or_unconfirmed_ceiling_is_never_compared_with_aud(currency):
    original = fixture(currency)
    before = copy.deepcopy(original)
    with (
        patch.object(client, "chat") as model,
        patch.object(client, "search") as search,
    ):
        report = campaigns.prepare(original)
    assert original == before
    assert report["campaign"]["opportunities"][0]["ceiling_currency"] == currency
    group = report["budget_summary"]["by_opportunity"][0]
    assert group["known_total"] == "60000.00"
    assert group["over_ceiling"] is None
    assert group["quoted_subtotal_over_ceiling"] is None
    assert group["comparison_note"]
    assert report["readiness"]["budgets_over_ceiling"] == 0
    assert report["readiness"]["quoted_subtotals_above_ceiling"] == 0
    assert report["readiness"]["funding_currency_review"] == 1
    for wording in (report["markdown"], report["document_markdown"]):
        assert "project costs are AUD" in wording
        assert "No currency conversion or ceiling comparison was made" in wording
        assert "exceeds the entered funding ceiling" not in wording
        assert "A$50,000" not in wording
    assert report["campaign"]["actions"][0]["task"] == "Retain recorded next action"
    model.assert_not_called()
    search.assert_not_called()


@pytest.mark.parametrize("cost", ["0", "1", "50000", "60000", None])
@pytest.mark.parametrize("currency", ["USD", "unconfirmed", "other"])
def test_non_comparable_subtotals_remain_unknown_on_both_sides_of_ceiling(
    cost, currency
):
    document = fixture(currency)
    document["budget"][0]["unit_cost"] = cost
    report = campaigns.prepare(document)
    assert report["budget_summary"]["by_opportunity"][0]["over_ceiling"] is None
    assert report["readiness"]["budgets_over_ceiling"] == 0
    assert report["readiness"]["quoted_subtotals_above_ceiling"] == 0
    assert report["readiness"]["funding_currency_review"] == 1


@pytest.mark.parametrize("currency", [None, True, [], {}, "usd", "JPY", "", "AUD "])
def test_invalid_currency_refused_without_overwriting_saved_input(currency, tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(fixture())
    edited = copy.deepcopy(saved["document"])
    edited["opportunities"][0]["ceiling_currency"] = currency
    with pytest.raises(ValueError, match="funding ceiling"):
        store.save(edited, saved["id"], saved["revision"])
    assert store.get(saved["id"]) == saved


def test_currency_save_reopen_backup_and_historical_report_preservation(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(fixture())
    reports = Store(tmp_path)
    historical_id = reports.save_report(campaigns.prepare(saved["document"]))
    historical = reports.report(historical_id)
    edited = copy.deepcopy(saved["document"])
    edited["opportunities"][0]["ceiling_currency"] = "USD"
    next_saved = store.save(edited, saved["id"], saved["revision"])
    assert campaigns.CampaignStore(tmp_path).get(saved["id"]) == next_saved
    backup = json.loads(json.dumps(next_saved["document"]))
    backup["title"] = "Restored fictional currency campaign"
    restored = store.save(backup)
    assert restored["id"] != saved["id"]
    assert restored["document"]["opportunities"][0]["ceiling_currency"] == "USD"
    assert reports.report(historical_id) == historical
    assert "A$50,000" in historical["document_markdown"]
    assert store.get(saved["id"]) == next_saved


@pytest.mark.parametrize("currency", ["USD", "unconfirmed", "other", "AUD"])
def test_non_cash_route_remains_no_grant_cash_and_requires_no_currency_comparison(
    currency,
):
    report = campaigns.prepare(fixture(currency, route_type="non_cash_support"))
    assert "No grant cash (non-cash support)" in report["document_markdown"]
    assert report["budget_summary"]["by_opportunity"][0]["over_ceiling"] is None
    assert (
        report["budget_summary"]["by_opportunity"][0]["quoted_subtotal_over_ceiling"]
        is None
    )
    assert report["readiness"]["quoted_subtotals_above_ceiling"] == 0
    assert report["readiness"]["funding_currency_review"] == 0
    assert report["readiness"]["budgets_over_ceiling"] == 0


def test_inactive_currency_review_is_retained_but_does_not_block_current_routes():
    report = campaigns.prepare(fixture("USD", status="closed"))
    group = report["budget_summary"]["by_opportunity"][0]
    assert group["historical"] and group["comparison_note"]
    assert group["over_ceiling"] is None
    assert report["readiness"]["funding_currency_review"] == 0
    assert "USD 50,000" in report["markdown"]


def test_amounts_keep_exact_cents_zero_and_explicit_unknown_denominations():
    assert funding_amount({"ceiling": "0", "ceiling_currency": "USD"}) == "USD 0"
    assert funding_amount({"ceiling": "50000.50", "ceiling_currency": "USD"}) == (
        "USD 50,000.50"
    )
    assert funding_amount({"ceiling": None}) == "Not recorded"
    assert "currency unconfirmed" in funding_amount(
        {"ceiling": None, "ceiling_currency": "unconfirmed"}
    )
    assert ceiling_comparison_note({"ceiling": None, "ceiling_currency": "USD"}) == ""
    assert not can_compare_ceiling({"ceiling": "0", "ceiling_currency": "USD"})
    assert can_compare_ceiling({"ceiling": "0"})


def test_browser_currency_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the campaign currency presentation")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/campaign_currency.mjs"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
