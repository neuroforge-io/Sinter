"""Quote arithmetic remains useful without becoming an application decision."""

from __future__ import annotations

import copy
import io
import json
import zipfile
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Inexact,
    Rounded,
    getcontext,
    localcontext,
)
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from sinter import campaigns, client
from sinter.campaign_budget import (
    AMOUNT_BASIS_NOTE,
    quoted_budget_summary,
    quoted_budget_total,
)
from sinter.docx_export import W, export_docx
from sinter.store import Store


def fixture():
    return {
        "schema": "sinter-campaign/v1",
        "title": "Fictional mixed quote amounts",
        "organisation": "Example group",
        "objective": "Keep source amounts without qualifying an application.",
        "opportunities": [
            {"name": "Current route", "status": "open", "ceiling": "3305"},
            {"name": "Historical route", "status": "submitted", "ceiling": "10"},
        ],
        "budget": [
            {
                "item": "Fictional quote inc GST 🐝",
                "opportunity": "Current route",
                "quantity": 2,
                "unit_cost": "1550.00",
                "quote_reference": "Written quote: GST included. e\u0301 <exact>.",
            },
            {
                "item": "Fictional quote ex GST",
                "opportunity": "Current route",
                "quantity": 1,
                "unit_cost": "200.00",
                "quote_reference": "Written quote: excluding GST; not reviewed.",
            },
            {
                "item": "Unpriced",
                "opportunity": "Current route",
                "quantity": 1,
                "unit_cost": None,
                "quote_reference": "",
            },
            {
                "item": "Recorded zero",
                "opportunity": "",
                "quantity": 1,
                "unit_cost": "0.00",
                "quote_reference": "Tax basis not supplied.",
            },
            {
                "item": "Historical quote",
                "opportunity": "Historical route",
                "quantity": 1,
                "unit_cost": "1000.00",
                "quote_reference": "Historical estimate; preserve exact amount.",
            },
        ],
    }


@pytest.mark.parametrize(
    "ceiling,crossing", [("3200", True), ("3300", False), ("3305", False)]
)
def test_mixed_gst_quote_subtotal_never_qualifies_an_application(ceiling, crossing):
    original = fixture()
    original["opportunities"][0]["ceiling"] = ceiling
    before = copy.deepcopy(original)
    with patch.object(client, "chat") as model, patch.object(client, "_open") as remote:
        report = campaigns.prepare(original)
    assert original == before
    model.assert_not_called()
    remote.assert_not_called()
    budget = report["budget_summary"]
    assert budget["known_total"] == "3300.00"
    assert budget["total"] is None and budget["complete"] is False
    assert budget["unknown_costs"] == 1
    current, historical = budget["by_opportunity"]
    assert current["quoted_subtotal_over_ceiling"] is crossing
    assert current["over_ceiling"] is None
    assert historical["quoted_subtotal_over_ceiling"] is True
    assert historical["over_ceiling"] is None
    assert current["comparison_note"] == ""
    assert current["amount_basis_note"] == AMOUNT_BASIS_NOTE
    assert report["readiness"]["budgets_over_ceiling"] == 0
    assert report["readiness"]["quoted_subtotals_above_ceiling"] == int(crossing)
    assert report["readiness"]["funding_currency_review"] == 0
    assert report["readiness"]["budget_amount_basis_review"] == 2
    for text in (report["markdown"], report["document_markdown"]):
        assert "quoted subtotal" in text.lower()
        assert "No GST conversion was made" in text
        assert (
            "Sinter has not qualified eligible costs or the application amount" in text
        )
        assert "A$3,320" not in text
        assert "within the funding ceiling" not in text
        assert "exceeds the entered funding ceiling" not in text


@pytest.mark.parametrize(
    "reference",
    [
        "GST included",
        "GST excluded",
        "GST free",
        "No GST registration",
        "Unknown 🐝 e\u0301",
        "",
    ],
)
def test_free_text_quote_reference_is_never_a_tax_or_amount_instruction(reference):
    original = fixture()
    original["budget"] = [
        {
            "item": "Entered amount",
            "opportunity": "Current route",
            "quantity": 3,
            "unit_cost": "0.10",
            "quote_reference": reference,
        }
    ]
    report = campaigns.prepare(original)
    assert report["campaign"]["budget"] == original["budget"]
    assert report["budget_summary"]["known_total"] == "0.30"
    assert report["budget_summary"]["total"] == "0.30"
    assert report["budget_summary"]["complete"] is True
    group = report["budget_summary"]["by_opportunity"][0]
    assert group["quoted_subtotal_over_ceiling"] is False
    assert group["over_ceiling"] is None
    assert group["amount_basis_note"] == AMOUNT_BASIS_NOTE
    assert report["readiness"]["status"] != "eligible"
    assert report["readiness"]["budget_amount_basis_review"] == 1


@pytest.mark.parametrize(
    "rows,known,total,complete,unknown",
    [
        ([], "0.00", None, False, 0),
        ([{"unit_cost": None}], "0.00", None, False, 1),
        ([{"unit_cost": "0.00"}], "0.00", "0.00", True, 0),
        ([{"unit_cost": "0.00"}, {"unit_cost": None}], "0.00", None, False, 1),
    ],
)
def test_absence_unpriced_and_explicit_zero_remain_distinct(
    rows,
    known,
    total,
    complete,
    unknown,
):
    original = fixture()
    original["budget"] = [
        {
            "item": f"Line {index}",
            "opportunity": "Current route",
            "quantity": 1,
            "quote_reference": "",
            **row,
        }
        for index, row in enumerate(rows)
    ]
    report = campaigns.prepare(original)
    budget = report["budget_summary"]
    assert (
        budget["known_total"],
        budget["total"],
        budget["complete"],
        budget["unknown_costs"],
    ) == (known, total, complete, unknown)
    group = budget["by_opportunity"][0]
    assert group["quoted_subtotal_over_ceiling"] is False
    assert group["over_ceiling"] is None
    assert report["readiness"]["budget_incomplete"] is not complete
    for text in (report["markdown"], report["document_markdown"]):
        assert AMOUNT_BASIS_NOTE in text
        assert "within the funding ceiling" not in text


@pytest.mark.parametrize("currency", ["USD", "EUR", "unconfirmed", "other"])
def test_currency_exclusion_is_separate_from_unqualified_amount_basis(currency):
    original = fixture()
    original["opportunities"][0]["ceiling_currency"] = currency
    report = campaigns.prepare(original)
    group = report["budget_summary"]["by_opportunity"][0]
    assert group["known_total"] == "3300.00"
    assert group["quoted_subtotal_over_ceiling"] is None
    assert group["over_ceiling"] is None
    assert "No currency conversion" in group["comparison_note"]
    assert group["amount_basis_note"] == AMOUNT_BASIS_NOTE
    assert report["readiness"]["funding_currency_review"] == 1
    assert report["readiness"]["quoted_subtotals_above_ceiling"] == 0


@pytest.mark.parametrize(
    "changes", [{"route_type": "non_cash_support"}, {"ceiling": None}]
)
def test_no_cash_or_unrecorded_ceiling_has_no_numeric_crossing(changes):
    original = fixture()
    original["opportunities"][0].update(changes)
    report = campaigns.prepare(original)
    group = report["budget_summary"]["by_opportunity"][0]
    assert group["quoted_subtotal_over_ceiling"] is None
    assert group["over_ceiling"] is None
    assert group["comparison_note"] == ""
    assert report["readiness"]["funding_currency_review"] == 0
    assert report["readiness"]["quoted_subtotals_above_ceiling"] == 0


def test_pure_quote_policy_preserves_order_and_historical_exclusions():
    original = campaigns.validate(fixture())
    before = copy.deepcopy(original)
    summary = quoted_budget_summary(original, campaigns.ACTIONABLE_OPPORTUNITY_STATES)
    assert original == before
    assert [group["opportunity"] for group in summary["by_opportunity"]] == [
        "Current route",
        "Historical route",
    ]
    assert summary["known_total"] == "3300.00"
    assert summary["historical"]["known_total"] == "1000.00"
    assert summary["active_items"] == 4 and summary["historical_items"] == 1
    assert summary["unallocated_items"] == 1
    changed = copy.deepcopy(original)
    changed["opportunities"][0]["status"] = "paused"
    report = campaigns.prepare(changed)
    assert report["budget_summary"]["known_total"] == "0.00"
    assert report["budget_summary"]["historical"]["known_total"] == "4300.00"
    assert report["readiness"]["quoted_subtotals_above_ceiling"] == 0
    assert report["readiness"]["budgets_over_ceiling"] == 0
    assert summary["known_total"] == "3300.00"


def context_snapshot(context):
    return {
        "prec": context.prec,
        "rounding": context.rounding,
        "Emin": context.Emin,
        "Emax": context.Emax,
        "capitals": context.capitals,
        "clamp": context.clamp,
        "traps": dict(context.traps),
        "flags": dict(context.flags),
    }


@pytest.mark.parametrize(
    "rounding",
    [
        ROUND_CEILING,
        ROUND_DOWN,
        ROUND_FLOOR,
        ROUND_HALF_DOWN,
        ROUND_HALF_EVEN,
        ROUND_HALF_UP,
        ROUND_UP,
    ],
)
@pytest.mark.parametrize("strict_traps", [False, True])
def test_quote_sum_and_raw_comparison_ignore_caller_decimal_context(
    rounding, strict_traps
):
    original = campaigns.validate(fixture())
    original["budget"] = [
        {
            "item": "Exact original quote",
            "opportunity": "Current route",
            "quantity": 3,
            "unit_cost": "111.11",
            "quote_reference": "Supplier's exact quote 🐝; GST unknown.",
        },
        {
            "item": "Exact additional amount",
            "opportunity": "Current route",
            "quantity": 1,
            "unit_cost": "1.02",
            "quote_reference": "Free text is unchanged.",
        },
        {
            "item": "Unpriced original",
            "opportunity": "Current route",
            "quantity": 1,
            "unit_cost": None,
            "quote_reference": "",
        },
        {
            "item": "Historical quote",
            "opportunity": "Historical route",
            "quantity": 2,
            "unit_cost": "11.11",
            "quote_reference": "Historical GST wording retained.",
        },
    ]
    original["opportunities"][0]["ceiling"] = "334.34"
    before = copy.deepcopy(original)
    outside = context_snapshot(getcontext())
    with localcontext() as caller:
        caller.prec = 2
        caller.rounding = rounding
        caller.Emin = -2
        caller.Emax = 2
        caller.capitals = 0
        caller.clamp = 1
        caller.traps[Inexact] = strict_traps
        caller.traps[Rounded] = strict_traps
        caller.clear_flags()
        # Existing caller flags must neither be cleared nor acquire new signals.
        caller.flags[Inexact] = True
        settings = context_snapshot(caller)
        summary = quoted_budget_summary(
            original, campaigns.ACTIONABLE_OPPORTUNITY_STATES
        )
        assert summary["known_total"] == "334.35"
        assert summary["total"] is None
        assert summary["complete"] is False
        assert summary["unknown_costs"] == 1
        assert summary["historical"]["total"] == "22.22"
        current, historical = summary["by_opportunity"]
        assert current["quoted_subtotal_over_ceiling"] is True
        assert historical["quoted_subtotal_over_ceiling"] is True
        assert current["over_ceiling"] is None
        assert getcontext() is caller
        assert context_snapshot(caller) == settings
        equal = copy.deepcopy(original)
        equal["opportunities"][0]["ceiling"] = "334.35"
        assert (
            quoted_budget_summary(equal, campaigns.ACTIONABLE_OPPORTUNITY_STATES)[
                "by_opportunity"
            ][0]["quoted_subtotal_over_ceiling"]
            is False
        )
        assert context_snapshot(caller) == settings
    assert context_snapshot(getcontext()) == outside
    assert original == before


@pytest.mark.parametrize(
    "last_unit, last_quantity, expected",
    [
        ("1000000000.00", 100000, "20000000000000000.00"),
        ("0.10", 3, "19900000000000000.30"),
    ],
)
def test_admitted_quote_bound_remains_exact_with_low_precision_and_traps(
    last_unit, last_quantity, expected
):
    rows = [
        {
            "unit_cost": "1000000000.00",
            "quantity": 100000,
            "quote_reference": "Literal maximum quote; amount basis unqualified.",
        }
        for _ in range(200)
    ]
    rows[-1].update(unit_cost=last_unit, quantity=last_quantity)
    before = copy.deepcopy(rows)
    with localcontext() as caller:
        caller.prec = 1
        caller.rounding = ROUND_UP
        caller.Emin = -1
        caller.Emax = 1
        caller.clamp = 1
        caller.traps[Inexact] = True
        caller.traps[Rounded] = True
        caller.clear_flags()
        settings = context_snapshot(caller)
        result = quoted_budget_total(rows)
        assert result["known_total"] == result["total"] == expected
        assert result["complete"] is True
        assert result["unknown_costs"] == 0
        assert result["items"] == 200
        assert result["amount_basis_note"] == AMOUNT_BASIS_NOTE
        assert getcontext() is caller
        assert context_snapshot(caller) == settings
    assert rows == before


def test_v1_save_reopen_backup_and_explicit_failed_save_retry_keep_inputs(tmp_path):
    normalized = campaigns.validate(fixture())
    assert all(
        set(row) == {"item", "opportunity", "quantity", "unit_cost", "quote_reference"}
        for row in normalized["budget"]
    )
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(normalized)
    assert saved["document"] == normalized
    assert campaigns.CampaignStore(tmp_path).get(saved["id"]) == saved
    encoded = json.dumps(saved["document"], ensure_ascii=False, indent=2)
    restored = store.save(json.loads(encoded))
    assert restored["document"] == normalized and restored["id"] != saved["id"]
    malformed = copy.deepcopy(saved["document"])
    malformed["budget"][0]["gst_included"] = True
    with pytest.raises(ValueError, match="unsupported fields"):
        store.save(malformed, saved["id"], saved["revision"])
    assert store.get(saved["id"]) == saved
    retry = copy.deepcopy(saved["document"])
    retry["budget"][0]["unit_cost"] = "1549.90"
    updated = store.save(retry, saved["id"], saved["revision"])
    assert updated["revision"] == 2
    assert (
        campaigns.prepare(updated["document"])["budget_summary"]["known_total"]
        == "3299.80"
    )
    assert store.get(restored["id"])["document"] == normalized
    assert json.loads(encoded) == normalized


def test_historical_report_view_does_not_rewrite_original_report_or_editor(tmp_path):
    normalized = campaigns.validate(fixture())
    original = {
        "workflow": "campaign",
        "title": normalized["title"],
        "created_at": "2026-09-12T12:00:00Z",
        "campaign": normalized,
        "budget_summary": {"known_total": "3300.00", "over_ceiling": True},
        "readiness": {"budgets_over_ceiling": 1},
        "markdown": "Original older budget verdict.",
        "document_markdown": "Original older decision brief.",
        "document_edits": {
            "markdown": "Literal historical user edit 🐝",
            "author": "user",
            "edited_at": "2026-09-12",
        },
    }
    before = copy.deepcopy(original)
    store = Store(tmp_path)
    identifier = store.save_report(original)
    with store.connect() as db:
        raw_before = db.execute(
            "SELECT document FROM reports WHERE id=?", (identifier,)
        ).fetchone()[0]
    view = store.report(identifier)
    group = view["budget_summary"]["by_opportunity"][0]
    assert group["over_ceiling"] is None
    assert group["known_total"] == "3300.00"
    assert view["document_edits"] == original["document_edits"]
    assert view["created_at"] == original["created_at"]
    with store.connect() as db:
        raw_after = db.execute(
            "SELECT document FROM reports WHERE id=?", (identifier,)
        ).fetchone()[0]
    assert raw_after == raw_before
    assert json.loads(raw_after) == before
    assert original == before
    assert "Original older budget verdict" not in view["markdown"]
    assert AMOUNT_BASIS_NOTE in view["markdown"]


@pytest.mark.parametrize("part", ["markdown", "document_markdown"])
def test_word_has_quote_subtotal_basis_caveat_and_exact_source_wording(part):
    original = fixture()
    report = campaigns.prepare(original)
    package = export_docx({"title": original["title"], "markdown": report[part]})
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert archive.testzip() is None
        root = ET.fromstring(archive.read("word/document.xml"))
    text = " ".join(node.text or "" for node in root.iter(f"{{{W}}}t"))
    assert "quoted subtotal" in text.lower()
    assert "GST basis may be unknown or mixed" in text
    assert "No GST conversion was made" in text
    assert "Sinter has not qualified eligible costs or the application amount" in text
    assert "within the funding ceiling" not in text
    if part == "markdown":
        assert "Written quote: GST included. e\u0301 <exact>." in text
        assert "excluding GST; not reviewed" in text
        assert "Historical quoted subtotal (excluded above): A$1,000.00" in text


@pytest.mark.parametrize(
    "active,unallocated,historical,expected",
    [
        (False, False, False, 0),
        (False, False, True, 0),
        (False, True, True, 1),
        (True, False, True, 1),
        (True, True, True, 2),
    ],
)
def test_amount_basis_review_counts_recorded_groups_not_tax_wording_or_prices(
    active,
    unallocated,
    historical,
    expected,
):
    original = fixture()
    original["budget"] = []
    for include, route in [
        (active, "Current route"),
        (unallocated, ""),
        (historical, "Historical route"),
    ]:
        if include:
            original["budget"].extend(
                [
                    {
                        "item": "Written GST wording",
                        "opportunity": route,
                        "quantity": 1,
                        "unit_cost": "0.00",
                        "quote_reference": "GST included; supplied source statement.",
                    },
                    {
                        "item": "Still unpriced",
                        "opportunity": route,
                        "quantity": 1,
                        "unit_cost": None,
                        "quote_reference": "",
                    },
                ]
            )
    report = campaigns.prepare(original)
    assert report["readiness"]["budget_amount_basis_review"] == expected
    assert report["readiness"]["funding_currency_review"] == 0
    assert report["readiness"]["budgets_over_ceiling"] == 0
    assert all(
        group["over_ceiling"] is None
        for group in report["budget_summary"]["by_opportunity"]
    )
    if expected:
        for part in ["markdown", "document_markdown"]:
            assert "not a finding of missing GST wording or a tax error" in report[part]
