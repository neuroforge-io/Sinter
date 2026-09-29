"""Campaign admission, incomplete-cost truthfulness and concurrent edit recovery."""
import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
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
    assert report["document_markdown"] != report["markdown"]
    assert "INTERNAL · REVIEW BEFORE SHARING" in report["document_markdown"]
    assert all(value in report["markdown"] for value in (
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


def test_default_brief_hides_source_and_inactive_detail_but_audit_retains_it():
    base = campaign()
    document = campaign(
        opportunities=[
            {**base["opportunities"][0], "name": "Active route",
             "status": "clarification"},
            {**base["opportunities"][0], "name": "Closed route",
             "status": "closed"},
            {**base["opportunities"][0], "name": "Paused route",
             "status": "paused"},
        ],
        requirements=[
            {**base["requirements"][0], "opportunity": "Active route",
             "status": "unknown", "evidence": "Still needs a dated check."},
            {**base["requirements"][0], "opportunity": "Closed route"},
        ],
        answers=[
            {**base["answers"][0], "opportunity": "Active route",
             "label": "Current answer draft", "text": "ACTIVE_ANSWER_TEXT"},
            {**base["answers"][0], "opportunity": "Closed route",
             "label": "Historical answer label", "text": "HISTORICAL_ANSWER_TEXT"},
        ],
        budget=[
            {"item": "Active scope", "opportunity": "Active route",
             "quantity": 1, "unit_cost": None, "quote_reference": ""},
            {"item": "Old route cost", "opportunity": "Closed route",
             "quantity": 1, "unit_cost": "25.00", "quote_reference": "Old quote"},
        ],
        actions=[
            {"task": "Confirm the active route evidence", "owner": "Grant lead",
             "due": "2026-10-02", "status": "open"},
            {"task": "SECOND_ACTION_MUST_STAY_IN_AUDIT_ONLY", "owner": "Treasurer",
             "due": "2026-10-03", "status": "open"},
        ],
        sources=[{
            "title": "Private source record", "url": "https://example.org/private",
            "notes": "PRIVATE_SOURCE_NOTE do not repeat in the brief.",
        }],
    )

    report = campaigns.prepare(document)
    brief = report["document_markdown"]
    audit = report["markdown"]

    assert "INTERNAL · REVIEW BEFORE SHARING" in brief
    assert "Active route" in brief and "Status entered: clarification" in brief
    assert "Closed route" not in brief and "Paused route" not in brief
    assert "PRIVATE_SOURCE_NOTE" not in brief
    assert "Historical answer" not in brief
    assert "ACTIVE_ANSWER_TEXT" not in brief
    assert "HISTORICAL_ANSWER_TEXT" not in brief
    assert "## Source references" not in brief
    assert "https://example.org/private" not in brief
    assert "1 requirement check unresolved" in brief
    assert "1 cost remains unknown" in brief and "total unknown" in brief
    assert "Confirm the active route evidence" in brief
    assert "SECOND_ACTION_MUST_STAY_IN_AUDIT_ONLY" not in brief
    assert "Owner: Grant lead (acceptance unconfirmed)" in brief
    assert "Proposed date: 2026-10-02 (proposed, not confirmed)" in brief
    assert campaigns.NOTICE in brief

    assert "Closed route" in audit and "Paused route" in audit
    assert "### Historical answer drafts · inactive route" in audit
    assert "historical draft · draft" in audit
    assert "PRIVATE\\_SOURCE\\_NOTE" in audit
    assert "## Source references" in audit
    # Legacy campaign fixtures omit newer optional signatory/owner fields;
    # validation supplies defaults and both views remain renderable.
    assert report["campaign"]["signatory"] == ""
    assert report["campaign"]["actions"][0]["owner_confirmed"] is False


def test_objective_preserves_paragraphs_and_emphasizes_plain_text_labels():
    report = campaigns.prepare(campaign(objective=(
        "Purpose: Identify a distinct, costed community project.\n\n"
        "Decision — 29 September 2026: No application is supportable today.")))
    markdown = report["markdown"]
    assert "**Purpose:** Identify a distinct, costed community project." in markdown
    assert "\n\n**Decision — 29 September 2026:** No application is supportable today." in markdown


def test_objective_emphasizes_each_labelled_line_without_losing_line_breaks():
    report = campaigns.prepare(campaign(objective=(
        "Purpose: Find a suitable round.\n"
        "Decision: No application is ready.\n"
        "Unlabelled note stays plain.")))
    markdown = report["markdown"]
    assert ("**Purpose:** Find a suitable round.  \n"
            "**Decision:** No application is ready.  \n"
            "Unlabelled note stays plain.") in markdown


def test_browser_and_server_route_state_policies_match():
    source = Path(__file__).parents[1] / "src/sinter/web/campaign-state.js"
    browser_code = source.read_text(encoding="utf-8")
    match = re.search(r"ACTIONABLE_OPPORTUNITY_STATES = Object\.freeze\(\[(.*?)\]\)",
                      browser_code, re.DOTALL)
    assert match is not None
    browser_states = set(re.findall(r"'([a-z_]+)'", match.group(1)))
    assert browser_states == campaigns.ACTIONABLE_OPPORTUNITY_STATES


def test_unknown_cost_is_not_zero_and_totals_remain_incomplete():
    report = campaigns.prepare(campaign())
    budget = report["budget_summary"]
    assert report["campaign"]["budget"][0]["unit_cost"] is None
    assert budget["known_total"] == "125.00"
    assert budget["total"] is None and budget["complete"] is False
    assert budget["unknown_costs"] == 1 and budget["unquoted_costs"] == 1
    assert budget["by_opportunity"][0]["total"] is None
    assert "Known subtotal: 125.00. Total incomplete" in report["markdown"]
    assert "Not yet costed" in report["markdown"]


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
    assert "0.300000" not in report["markdown"]


def test_no_budget_is_not_a_complete_zero_budget():
    report = campaigns.prepare(campaign(budget=[]))
    assert report["budget_summary"]["total"] is None
    assert report["readiness"]["budget_incomplete"]
    assert "project total is unknown" in report["markdown"]
    assert "current project budget not entered; total unknown" in report["markdown"]


def test_known_subtotal_can_exceed_ceiling_with_other_costs_still_unknown():
    document = campaign()
    document["opportunities"][0]["ceiling"] = 100
    report = campaigns.prepare(document)
    assert report["budget_summary"]["by_opportunity"][0]["over_ceiling"] is True
    assert report["readiness"]["budgets_over_ceiling"] == 1
    assert report["budget_summary"]["total"] is None
    assert "exceeds the entered funding ceiling" in report["markdown"]


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
    assert "OVER LIMIT" in report["markdown"]


def test_empty_reviewed_answer_and_missing_limits_still_need_attention():
    document = campaign()
    document["answers"][0].update(text="  \n", limit=None, status="reviewed")
    report = campaigns.prepare(document)
    assert report["readiness"]["answers_empty"] == 1
    assert report["readiness"]["answer_limits_unknown"] == 1
    assert report["answer_metrics"][0]["remaining"] is None
    assert report["answer_metrics"][0]["over_limit"] is False
    assert "Answer not drafted yet" in report["markdown"]


@pytest.mark.parametrize("missing", ["source_url", "source_quote", "evidence",
                                    "checked_at"])
def test_marking_check_met_without_support_does_not_clear_readiness(missing):
    document = campaign()
    document["requirements"][0].update(status="met", **{missing: ""})
    report = campaigns.prepare(document)
    assert report["campaign"]["requirements"][0]["status"] == "met"
    assert report["readiness"]["claims_without_evidence"] == 1
    assert report["readiness"]["requirements_unresolved"] == 1
    assert (
        "User-marked met · unverified — source record incomplete"
        in report["markdown"]
    )


@pytest.mark.parametrize(("status", "label"), [
    ("met", "User-marked met · unverified"),
    ("not_met", "User-marked not met · unverified"),
    ("unknown", "User-entered status · not checked"),
    ("clarification", "User-entered status · clarification needed"),
])
def test_complete_freeform_source_record_is_never_presented_as_verified(status, label):
    document = campaign()
    document["requirements"][0].update(status=status)
    report = campaigns.prepare(document)
    rendered = report["markdown"]
    assert f"**{label}:**" in rendered
    assert "Applicant evidence (user-entered; unverified):" in rendered
    assert "Source wording (user-entered; unverified):" in rendered
    assert "User-entered source link; not checked by Sinter" in rendered
    assert "Date checked (user-entered): 2026-09-12" in rendered
    assert "Supported · human checked" not in rendered
    assert "Not supported · human checked" not in rendered


def test_complete_entered_checks_never_become_an_eligibility_determination():
    document = campaign()
    document["requirements"][0]["status"] = "met"
    document["answers"][0]["status"] = "reviewed"
    document["budget"] = document["budget"][1:]
    document["actions"][0]["status"] = "done"
    report = campaigns.prepare(document)
    assert report["readiness"]["requirements_unresolved"] == 0
    assert report["readiness"]["status"] == "human_review"
    assert "does not determine eligibility" in report["markdown"]
    assert "eligible" not in report["readiness"] and "ready" not in report["readiness"]


def test_clarification_and_not_met_are_distinct_and_retained():
    document = campaign()
    original = document["requirements"][0]
    document["requirements"] = [{**original, "status": "clarification"},
                                {**original, "status": "not_met"}]
    report = campaigns.prepare(document)
    assert report["readiness"]["requirements_not_met"] == 1
    assert report["readiness"]["requirements_unresolved"] == 1
    assert "User-entered status · clarification needed" in report["markdown"]
    assert "User-marked not met · unverified" in report["markdown"]


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


def test_closed_route_checks_are_retained_without_blocking_the_active_screen():
    document = campaign()
    closed_name = document["opportunities"][0]["name"]
    document["opportunities"][0]["status"] = "closed"
    document["opportunities"].append({
        "name": "Fictional future sponsor", "funder": "Example Council",
        "url": "https://example.org/future", "deadline": "",
        "decision_window": "Not confirmed", "ceiling": None,
        "fit": "Only if a distinct project is confirmed.", "status": "upcoming",
    })
    document["requirements"].append({
        **document["requirements"][0], "opportunity": "Fictional future sponsor",
        "rule": "A distinct project is confirmed.", "status": "unknown",
        "evidence": "", "source_url": "", "source_quote": "", "checked_at": "",
    })
    report = campaigns.prepare(document)
    assert report["readiness"]["requirements_total"] == 1
    assert report["readiness"]["requirements_archived"] == 1
    assert report["readiness"]["requirements_unresolved"] == 1
    assert report["readiness"]["opportunities_without_checks"] == 0
    assert report["readiness"]["opportunities_without_answers"] == 1
    assert "1 check is retained for paused, not-pursued, submitted or closed opportunity" in report["markdown"]
    assert closed_name in report["markdown"]


def test_not_pursuing_round_is_distinct_from_programme_closure_and_keeps_history():
    document = campaign()
    document["opportunities"][0]["deadline"] = "2026-10-04"
    document["opportunities"][0]["status"] = "not_pursuing"
    report = campaigns.prepare(document)
    markdown = report["markdown"]
    assert report["readiness"]["requirements_total"] == 0
    assert report["readiness"]["requirements_archived"] == 1
    assert "Campaign status entered: not pursuing this round" in markdown
    assert "Application deadline: 2026-10-04" in markdown
    assert "Historical record · User-entered status · not checked" in markdown
    assert "not-pursued" in markdown


def test_closed_route_answer_drafts_are_clearly_archived_not_current_answers():
    document = campaign()
    document["opportunities"][0]["status"] = "closed"
    report = campaigns.prepare(document)
    markdown = report["markdown"]
    assert "### Historical answer drafts · inactive route" in markdown
    assert "are not for submission" in markdown
    assert "does not show whether anything was submitted" in markdown
    assert "historical draft · draft" in markdown
    assert "Draft text omitted from this report." in markdown
    assert "Provide shared swim equipment." not in markdown
    assert "### Application answers" not in markdown


def test_role_suggestions_are_not_counted_as_confirmed_action_owners():
    document = campaign(actions=[
        {"task": "Check the portal", "owner": "P&C Treasurer (unassigned)",
         "due": "", "status": "open"},
        {"task": "Request school confirmation", "owner": "",
         "due": "", "status": "open"},
    ])
    report = campaigns.prepare(document)
    assert report["readiness"]["actions_without_owner"] == 2
    assert "2 open actions have no user-confirmed owner" in report["markdown"]


def test_owner_needs_an_explicit_user_confirmation():
    document = campaign(actions=[{
        "task": "Confirm school approval", "owner": "P&C Treasurer",
        "due": "2026-10-02", "status": "open",
    }])
    report = campaigns.prepare(document)
    assert report["readiness"]["actions_without_owner"] == 1
    assert "P&amp;C Treasurer (acceptance not recorded)" in report["markdown"]
    assert "Proposed target: 2026-10-02 · proposed target, not confirmed" in report["markdown"]

    document["actions"][0]["owner_confirmed"] = True
    report = campaigns.prepare(document)
    assert report["readiness"]["actions_without_owner"] == 0
    assert "P&amp;C Treasurer (user-marked accepted; confirm directly)" in report["markdown"]


def test_owner_confirmation_rejects_unassigned_or_non_boolean_values():
    document = campaign(actions=[{
        "task": "Confirm school approval", "owner": "Unassigned",
        "owner_confirmed": True, "due": "", "status": "open",
    }])
    with pytest.raises(ValueError, match="person's name"):
        campaigns.prepare(document)
    document["actions"][0].update(owner="Alex", owner_confirmed="yes")
    with pytest.raises(ValueError, match="true or false"):
        campaigns.prepare(document)


def test_inactive_route_costs_are_separated_from_current_project_total():
    document = campaign(
        opportunities=[
            campaign()["opportunities"][0],
            {"name": "Closed equipment round", "funder": "Old funder",
             "url": "https://example.org/old", "deadline": "2026-06-01",
             "decision_window": "Closed", "ceiling": 500,
             "fit": "Historical option", "status": "closed"},
        ],
        budget=[
            {"item": "Current transport", "opportunity": "Fictional access fund",
             "quantity": 1, "unit_cost": "25", "quote_reference": "Current quote"},
            {"item": "Old equipment", "opportunity": "Closed equipment round",
             "quantity": 1, "unit_cost": "250", "quote_reference": "Old estimate"},
        ],
    )
    report = campaigns.prepare(document)
    budget = report["budget_summary"]
    assert budget["known_total"] == "25.00"
    assert budget["total"] == "25.00" and budget["complete"]
    assert budget["historical"]["known_total"] == "250.00"
    groups = {row["opportunity"]: row for row in budget["by_opportunity"]}
    assert groups["Fictional access fund"]["status"] == "open"
    assert groups["Fictional access fund"]["historical"] is False
    assert groups["Closed equipment round"]["status"] == "closed"
    assert groups["Closed equipment round"]["historical"] is True
    groups = {row["opportunity"]: row for row in budget["by_opportunity"]}
    assert groups["Fictional access fund"]["status"] == "open"
    assert groups["Fictional access fund"]["historical"] is False
    assert groups["Closed equipment round"]["status"] == "closed"
    assert groups["Closed equipment round"]["historical"] is True
    markdown = report["markdown"]
    assert "Current entered cost: 25.00" in markdown
    assert "### Historical budget items · inactive routes" in markdown
    assert "These costs belong to closed, submitted, paused or not-pursued routes." in markdown
    assert "Historical known subtotal (excluded above): 250.00" in markdown
    assert "| Old equipment | Closed equipment round |" in markdown


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


@pytest.mark.parametrize("value", ["bad\x00text", "bad\x0btext", "bad\x0ctext",
                                  "bad\x1btext", "bad\x85text", "bad\x9ftext",
                                  "bad\ud800", "bad\udfff"])
def test_invalid_text_rejected_before_rendering_or_encoding(value):
    document = campaign()
    document["answers"][0]["text"] = value
    with pytest.raises(ValueError, match="control characters|invalid Unicode"):
        campaigns.prepare(document)


def test_campaign_text_preserves_tab_and_line_breaks():
    document = campaign()
    document["answers"][0]["text"] = "First line\nSecond\tpart\rFinal line"
    report = campaigns.prepare(document)
    assert report["campaign"]["answers"][0]["text"] == document["answers"][0]["text"]


def test_benign_markdown_and_html_stay_literal_and_links_remain_portable():
    document = campaign(title="<img src=x> [Campaign](javascript:alert(1))")
    document["answers"][0]["text"] = "<script>alert(1)</script>\n# New heading"
    document["opportunities"][0]["url"] = "https://example.org/grants/(access)"
    report = campaigns.prepare(document)
    assert "<script>" not in report["markdown"]
    assert "<img" not in report["markdown"]
    assert "\n# New heading" not in report["markdown"]
    assert "(<https://example.org/grants/(access)>)" in report["markdown"]
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
