"""Campaign admission, incomplete-cost truthfulness and concurrent edit recovery."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

import pytest

from sinter import campaigns


def campaign(**changes):
    return {
        "title": "Fictional community swim access",
        "organisation": "Banksia Volunteers",
        "objective": "Train two volunteers and purchase shared teaching equipment.",
        "opportunities": [{
            "name": "Fictional access fund", "funder": "Example Foundation",
            "url": "https://example.org/grants/access", "deadline": "2026-09-28",
            "decision_window": "Four to five months after closing",
            "ceiling": 5000, "fit": "One-off equipment and training",
            "status": "open",
        }],
        "requirements": [{
            "opportunity": "Fictional access fund",
            "rule": "Confirm the applicant type is accepted.",
            "status": "unknown", "evidence": "No funder confirmation received.",
            "source_url": "https://example.org/grants/access/eligibility",
            "source_quote": "Registered community associations may apply.",
            "checked_at": "2026-09-12",
        }],
        "answers": [{
            "opportunity": "Fictional access fund", "label": "Project purpose",
            "text": "Provide shared swim equipment.", "limit": 500, "status": "draft",
        }],
        "budget": [{
            "item": "Training places", "opportunity": "Fictional access fund",
            "quantity": 2, "unit_cost": None, "quote_reference": "",
        }, {
            "item": "Shared equipment", "opportunity": "Fictional access fund",
            "quantity": 10, "unit_cost": "12.50", "quote_reference": "Supplier quote A",
        }],
        "actions": [{"task": "Obtain training quotes", "owner": "Alex",
                     "due": "2026-09-17", "status": "open"}],
        "sources": [{"title": "Fictional fund guidelines",
                     "url": "https://example.org/grants/access",
                     "notes": "Manually checked for a fictional test campaign."}],
        **changes,
    }


def test_prepare_preserves_editable_input_and_generates_portable_pack_offline():
    document = campaign()
    before = copy.deepcopy(document)
    with patch("sinter.client.chat") as model, patch("sinter.client.search") as search:
        report = campaigns.prepare(document)
    assert document == before
    assert report["workflow"] == "campaign"
    assert report["document_title"] == document["title"]
    assert report["document_markdown"] == report["markdown"]
    assert all(value in report["document_markdown"] for value in (
        "Banksia Volunteers", "Train two volunteers", "Project purpose",
        "Provide shared swim equipment.", "https://example.org/grants/access",
        "Applicant evidence", "Registered community associations may apply.",
        "Obtain training quotes", "Supplier quote A",
    ))
    assert report["readiness"]["status"] == "needs_attention"
    assert campaigns.validate(report["campaign"]) == report["campaign"]
    assert json.loads(json.dumps(report, allow_nan=False)) == report
    model.assert_not_called()
    search.assert_not_called()


def test_unknown_cost_is_not_zero_and_totals_remain_incomplete():
    report = campaigns.prepare(campaign())
    budget = report["budget_summary"]
    assert report["campaign"]["budget"][0]["unit_cost"] is None
    assert budget["known_total"] == "125.00"
    assert budget["total"] is None and budget["complete"] is False
    assert budget["unknown_costs"] == 1 and budget["unquoted_costs"] == 1
    assert budget["by_opportunity"][0]["total"] is None
    assert "Known subtotal: 125.00. Total incomplete" in report["document_markdown"]
    assert "Not yet costed" in report["document_markdown"]


def test_zero_cost_and_small_decimal_costs_are_exact():
    rows = [{"item": "Volunteer work", "quantity": 1, "unit_cost": 0,
             "quote_reference": "Written in-kind commitment"},
            {"item": "Small item", "quantity": 3, "unit_cost": 0.1,
             "quote_reference": "Supplier B"}]
    report = campaigns.prepare(campaign(budget=rows))
    assert report["campaign"]["budget"][0]["unit_cost"] == "0.00"
    assert report["budget_summary"]["total"] == "0.30"
    assert report["budget_summary"]["complete"] is True
    assert report["readiness"]["unallocated_budget_items"] == 2
    assert "0.300000" not in report["document_markdown"]


def test_no_budget_is_not_a_complete_zero_budget():
    report = campaigns.prepare(campaign(budget=[]))
    assert report["budget_summary"]["total"] is None
    assert report["readiness"]["budget_incomplete"]
    assert "project total is unknown" in report["document_markdown"]


def test_known_subtotal_can_exceed_ceiling_with_other_costs_still_unknown():
    document = campaign()
    document["opportunities"][0]["ceiling"] = 100
    report = campaigns.prepare(document)
    assert report["budget_summary"]["by_opportunity"][0]["over_ceiling"] is True
    assert report["readiness"]["budgets_over_ceiling"] == 1
    assert report["budget_summary"]["total"] is None
    assert "exceeds the entered funding ceiling" in report["document_markdown"]


def test_answer_count_measures_exact_untrimmed_text_and_keeps_overlimit_draft():
    document = campaign()
    document["answers"][0].update(text=" A café 🏊\n", limit=9, status="reviewed")
    report = campaigns.prepare(document)
    metric = report["answer_metrics"][0]
    assert metric["characters"] == 10 and metric["words"] == 3
    assert metric["utf16_characters"] == 11
    assert metric["over_limit"] and metric["remaining"] == -1
    assert report["campaign"]["answers"][0]["text"] == " A café 🏊\n"
    assert report["readiness"]["answers_over_limit"] == 1
    assert "OVER LIMIT" in report["document_markdown"]


def test_empty_reviewed_answer_and_missing_limits_still_need_attention():
    document = campaign()
    document["answers"][0].update(text="  \n", limit=None, status="reviewed")
    report = campaigns.prepare(document)
    assert report["readiness"]["answers_empty"] == 1
    assert report["readiness"]["answer_limits_unknown"] == 1
    assert report["answer_metrics"][0]["remaining"] is None
    assert report["answer_metrics"][0]["over_limit"] is False
    assert "Answer not drafted yet" in report["document_markdown"]


@pytest.mark.parametrize("missing", ["source_url", "source_quote", "evidence",
                                    "checked_at"])
def test_marking_check_met_without_support_does_not_clear_readiness(missing):
    document = campaign()
    document["requirements"][0].update(status="met", **{missing: ""})
    report = campaigns.prepare(document)
    assert report["campaign"]["requirements"][0]["status"] == "met"
    assert report["readiness"]["claims_without_evidence"] == 1
    assert report["readiness"]["requirements_unresolved"] == 1
    assert "Marked met — supporting evidence incomplete" in report["document_markdown"]


def test_complete_entered_checks_never_become_an_eligibility_determination():
    document = campaign()
    document["requirements"][0]["status"] = "met"
    document["answers"][0]["status"] = "reviewed"
    document["budget"] = document["budget"][1:]
    document["actions"][0]["status"] = "done"
    report = campaigns.prepare(document)
    assert report["readiness"]["requirements_unresolved"] == 0
    assert report["readiness"]["status"] == "human_review"
    assert "does not determine eligibility" in report["document_markdown"]
    assert "eligible" not in report["readiness"] and "ready" not in report["readiness"]


def test_clarification_and_not_met_are_distinct_and_retained():
    document = campaign()
    original = document["requirements"][0]
    document["requirements"] = [{**original, "status": "clarification"},
                                {**original, "status": "not_met"}]
    report = campaigns.prepare(document)
    assert report["readiness"]["requirements_not_met"] == 1
    assert report["readiness"]["requirements_unresolved"] == 1
    assert "Clarification needed" in report["document_markdown"]
    assert "Marked not met" in report["document_markdown"]


def test_minimal_campaign_is_a_saveable_draft_with_explicit_missing_work():
    report = campaigns.prepare({"title": "New idea"})
    assert report["readiness"]["missing_sections"] == [
        "organisation", "objective", "opportunities",
    ]
    assert report["budget_summary"]["total"] is None
    document = campaign(requirements=[], answers=[])
    report = campaigns.prepare(document)
    assert report["readiness"]["opportunities_without_checks"] == 1
    assert report["readiness"]["opportunities_without_answers"] == 1


@pytest.mark.parametrize("value", [True, -1, "", "1,000", "1e2", "1.001",
                                    "NaN", "Infinity", float("nan"),
                                    float("inf"), Decimal("-Infinity"),
                                    "1000000000.01", {}, []])
def test_invalid_money_rejected_for_both_costs_and_funding_ceiling(value):
    document = campaign()
    document["budget"][0]["unit_cost"] = value
    with pytest.raises(ValueError):
        campaigns.prepare(document)
    document = campaign()
    document["opportunities"][0]["ceiling"] = value
    with pytest.raises(ValueError):
        campaigns.prepare(document)


@pytest.mark.parametrize("field", ["deadline", "due", "checked_at"])
@pytest.mark.parametrize("value", ["2026-02-30", "20260928", "2026-9-28",
                                    "2026-W39-1", "2026-09-28T12:00", None])
def test_invalid_or_ambiguous_dates_rejected(field, value):
    document = campaign()
    key = {"deadline": "opportunities", "due": "actions",
           "checked_at": "requirements"}[field]
    document[key][0][field] = value
    with pytest.raises(ValueError):
        campaigns.prepare(document)


@pytest.mark.parametrize("value", ["javascript:alert(1)", "file:///tmp/document",
                                    "https://user:password@example.org/",
                                    "//example.org",
                                    "https://example.org/\nx", "https://example.org/<x>",
                                    "https://example.org/\u00a0x",
                                    "https://example.org:99999/"])
def test_links_are_references_with_safe_schemes_and_no_credentials(value):
    document = campaign()
    document["requirements"][0]["source_url"] = value
    with pytest.raises(ValueError):
        campaigns.prepare(document)


@pytest.mark.parametrize("value", ["bad\x00text", "bad\x1btext", "bad\x85text",
                                  "bad\ud800"])
def test_invalid_text_rejected_before_rendering_or_encoding(value):
    document = campaign()
    document["answers"][0]["text"] = value
    with pytest.raises(ValueError, match="control characters|invalid Unicode"):
        campaigns.prepare(document)


def test_benign_markdown_and_html_stay_literal_and_links_remain_portable():
    document = campaign(title="<img src=x> [Campaign](javascript:alert(1))")
    document["answers"][0]["text"] = "<script>alert(1)</script>\n# New heading"
    document["opportunities"][0]["url"] = "https://example.org/grants/(access)"
    report = campaigns.prepare(document)
    assert "<script>" not in report["document_markdown"]
    assert "<img" not in report["document_markdown"]
    assert "\n# New heading" not in report["document_markdown"]
    assert "(<https://example.org/grants/(access)>)" in report["document_markdown"]
    assert report["campaign"]["answers"][0]["text"].startswith("<script>")


@pytest.mark.parametrize("field,value", [("ready", True), ("readiness", {}),
                                       ("workflow", "campaign"),
                                       ("schema", "other/v1")])
def test_unknown_top_level_keys_cannot_override_derived_readiness(field, value):
    with pytest.raises(ValueError):
        campaigns.prepare(campaign(**{field: value}))


def test_duplicate_and_broken_opportunity_references_do_not_silently_drop_work():
    document = campaign()
    document["opportunities"].append({**document["opportunities"][0],
                                      "name": "FICTIONAL ACCESS FUND"})
    with pytest.raises(ValueError, match="distinct name"):
        campaigns.prepare(document)
    for key in ("requirements", "answers", "budget"):
        document = campaign()
        document[key][0]["opportunity"] = "Deleted fund"
        with pytest.raises(ValueError, match="exact name"):
            campaigns.prepare(document)


@pytest.mark.parametrize("key,value", [("requirements", {"status": "eligible"}),
                                       ("opportunities", {"status": "ready"}),
                                       ("answers", {"status": "approved"}),
                                       ("actions", {"status": "cancelled"}),
                                       ("budget", {"quantity": True}),
                                       ("budget", {"quantity": 1.5}),
                                       ("answers", {"limit": 0}),
                                       ("answers", {"limit": True}),
                                       ("sources", {"hidden": "discard me"})])
def test_row_schema_and_status_are_explicit(key, value):
    document = campaign()
    document[key][0].update(value)
    with pytest.raises(ValueError):
        campaigns.prepare(document)


@pytest.mark.parametrize("key", campaigns.ROW_LIMITS)
def test_lists_are_bounded_and_malformed_rows_fail_cleanly(key):
    document = campaign()
    document[key] = [None]
    with pytest.raises(ValueError):
        campaigns.prepare(document)
    document[key] = [{}] * (campaigns.ROW_LIMITS[key] + 1)
    with pytest.raises(ValueError, match="at most"):
        campaigns.prepare(document)


def test_combined_payload_bound_counts_all_sections():
    document = campaign()
    document["answers"] = [{**document["answers"][0], "text": "x" * 20000}
                           for _ in range(11)]
    with pytest.raises(ValueError, match="200,000"):
        campaigns.prepare(document)


def test_store_reopens_same_identity_with_unknown_costs_and_new_revision(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    first = store.save(campaign())
    assert first["revision"] == 1
    assert campaigns.CampaignStore(tmp_path).get(first["id"]) == first
    edited = copy.deepcopy(first["document"])
    edited["answers"][0]["text"] = "An improved application answer."
    edited["budget"][0]["unit_cost"] = "250.25"
    second = store.save(edited, id=first["id"], revision=first["revision"])
    assert second["id"] == first["id"] and second["revision"] == 2
    assert store.get(second["id"]) == second
    listing = store.list()
    assert len(listing) == 1 and listing[0]["revision"] == 2
    assert set(listing[0]) == {"id", "revision", "title", "updated_at"}
    assert (tmp_path / "campaigns.sqlite3").exists()
    assert campaigns.prepare(second["document"])["budget_summary"]["total"] == "625.50"


def test_invalid_save_and_stale_save_leave_latest_document_untouched(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(campaign())
    bad = {**saved["document"], "ready": True}
    with pytest.raises(ValueError):
        store.save(bad, saved["id"], saved["revision"])
    assert store.get(saved["id"]) == saved
    edited = {**saved["document"], "title": "New title"}
    newer = store.save(edited, saved["id"], saved["revision"])
    with pytest.raises(ValueError, match="another window"):
        store.save(saved["document"], saved["id"], saved["revision"])
    assert store.get(saved["id"]) == newer


def test_two_windows_cannot_overwrite_same_revision(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(campaign())
    barrier = Barrier(2)

    def edit(title):
        other = campaigns.CampaignStore(tmp_path)
        barrier.wait(timeout=5)
        try:
            return other.save({**saved["document"], "title": title},
                              saved["id"], saved["revision"])
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(edit, ["Window one", "Window two"]))
    successes = [reply for reply in replies if isinstance(reply, dict)]
    assert len(successes) == 1
    assert store.get(saved["id"]) == successes[0]
    assert any("another window" in reply for reply in replies if isinstance(reply, str))


def test_delete_requires_exact_latest_revision(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(campaign())
    newer = store.save(saved["document"], saved["id"], saved["revision"])
    with pytest.raises(ValueError, match="changed"):
        store.delete(saved["id"], saved["revision"])
    assert store.get(saved["id"]) == newer
    store.delete(newer["id"], newer["revision"])
    assert store.list() == []
    with pytest.raises(KeyError, match="not found"):
        store.get(newer["id"])
    with pytest.raises(ValueError, match="removed"):
        store.delete(newer["id"], newer["revision"])


def test_missing_identity_or_revision_cannot_accidentally_create_a_new_copy(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(campaign())
    for revision in (None, True, "1", 0, -1):
        with pytest.raises(ValueError, match="revision"):
            store.save(saved["document"], saved["id"], revision)
    with pytest.raises(ValueError, match="existing campaign"):
        store.save(saved["document"], revision=1)
    with pytest.raises(ValueError, match="ID"):
        store.get("../../private")
    assert len(store.list()) == 1


def test_storage_limit_is_atomic_and_does_not_prevent_existing_edits(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    with patch.object(campaigns, "MAX_CAMPAIGNS", 2):
        first = store.save(campaign())
        store.save(campaign(title="Another campaign"))
        with pytest.raises(ValueError, match="Export and remove"):
            store.save(campaign(title="Excess campaign"))
        changed = store.save({**first["document"], "title": "Edited first"},
                             first["id"], first["revision"])
    assert len(store.list()) == 2
    assert store.get(first["id"]) == changed
