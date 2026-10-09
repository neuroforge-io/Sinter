"""Explicit selected informational scope preserves the whole campaign record."""

import copy

import pytest

from sinter import campaigns


def selected_document(purpose, status="researching"):
    return campaigns.validate({
        "title": "Fictional mixed campaign", "organisation": "Fictional group",
        "objective": "Preserve every record; nothing is approved.",
        "opportunities": [
            {"name": "Other route", "status": "open", "application_mode": "required"},
            {"name": "Selected record", "status": status,
             "purpose": purpose, "application_mode": "unknown"},
        ],
        "actions": [{"opportunity": "Other route", "scope_confirmed": True,
                     "task": "Retain the other route's actual current task.",
                     "owner": "Casey Example", "owner_kind": "person",
                     "owner_confirmed": False, "due": "2026-10-01", "status": "open"}],
    })


def next_section(report):
    return report["document_markdown"].split("## Next recorded open action", 1)[1]


@pytest.mark.parametrize("purpose", ["discussion", "research"])
@pytest.mark.parametrize("status", ["researching", "submitted", "paused", "closed", "not_pursuing"])
def test_explicit_nonformal_focus_is_retained_without_using_other_route_action(purpose, status):
    original = selected_document(purpose, status)
    before = copy.deepcopy(original)
    selected = campaigns.prepare(original, "Selected record")
    overall = campaigns.prepare(original)
    assert "Route in focus: Selected record (selected in Sinter" in selected["document_markdown"]
    assert "No current open action is recorded for this selected route or campaign-wide scope" in next_section(selected)
    assert original["actions"][0]["task"] not in next_section(selected)
    assert original["actions"][0]["task"] in selected["markdown"]
    assert selected["readiness"] == overall["readiness"]
    assert selected["campaign"] == overall["campaign"] == before
    assert original == before


@pytest.mark.parametrize("purpose", ["discussion", "research"])
def test_selected_route_then_campaign_wide_actions_retain_exact_precedence(purpose):
    original = selected_document(purpose)
    global_action = {"opportunity": "", "scope_confirmed": True, "status": "open",
                     "task": "Review the whole campaign record.", "due": "",
                     "owner": "", "owner_kind": "unknown", "owner_confirmed": False}
    route_action = {**global_action, "opportunity": "Selected record",
                    "task": "Review the selected evidence.", "owner_kind": "unassigned"}
    original["actions"] += [global_action, route_action]
    original = campaigns.validate(original)
    before = copy.deepcopy(original)
    report = campaigns.prepare(original, "Selected record")
    assert route_action["task"] in next_section(report)
    assert "Proposed date: not set" in next_section(report)
    assert original == before
    global_only = {**original, "actions": original["actions"][:2]}
    global_report = campaigns.prepare(global_only, "Selected record")
    assert global_action["task"] in next_section(global_report)
    assert "Scope: Campaign-wide" in next_section(global_report)


@pytest.mark.parametrize("purpose", ["discussion", "research"])
def test_submitted_record_keeps_preparation_held_until_explicit_follow_up_phase(purpose):
    original = selected_document(purpose, "submitted")
    original["actions"].append({"opportunity": "Selected record", "scope_confirmed": True,
        "status": "open", "submission_phase": "pre_submission", "due": "",
        "task": "Retained unfinished preparation", "owner": "", "owner_kind": "unassigned",
        "owner_confirmed": False})
    before = copy.deepcopy(original)
    report = campaigns.prepare(original, "Selected record")
    assert "No current open action is recorded for this selected route" in next_section(report)
    assert report["readiness"]["actions_submission_phase_review"] == 1
    assert original == before
    changed = copy.deepcopy(original)
    changed["actions"][1].update(submission_phase="post_submission",
                                 task="Record a documented response.", due="2026-10-15")
    follow_up = campaigns.prepare(changed, "Selected record")
    assert changed["actions"][1]["task"] in next_section(follow_up)
    assert "Phase: After-submission follow-up" in next_section(follow_up)
    assert changed["opportunities"][1]["status"] == "submitted"


@pytest.mark.parametrize("purpose", [None, "unknown", "application"])
def test_legacy_selected_scope_retains_other_route_fallback_and_inactive_focus(purpose):
    original = selected_document("unknown")
    if purpose is None:
        del original["opportunities"][1]["purpose"]
    else:
        original["opportunities"][1]["purpose"] = purpose
    before = copy.deepcopy(original)
    report = campaigns.prepare(original, "Selected record")
    assert original["actions"][0]["task"] in next_section(report)
    assert original == before
    original["opportunities"][1]["status"] = "closed"
    historical = campaigns.prepare(original, "Selected record")
    assert "Route in focus: Other route (selected in Sinter" in historical["document_markdown"]
    assert "for this selected route or campaign-wide scope" not in next_section(historical)


def test_required_formal_workflow_preserves_conflict_and_legacy_next_action_fallback():
    original = selected_document("research")
    original["opportunities"][1]["application_mode"] = "required"
    before = copy.deepcopy(original)
    report = campaigns.prepare(original, "Selected record")
    assert report["readiness"]["purpose_workflow_conflicts"] == 1
    assert report["readiness"]["status"] == "needs_attention"
    assert original["actions"][0]["task"] in next_section(report)
    assert "for this selected route or campaign-wide scope" not in next_section(report)
    assert original == before


def test_no_explicit_selection_keeps_other_route_fallback_for_first_informational_route():
    original = selected_document("research")
    original["opportunities"].reverse()
    before = copy.deepcopy(original)
    report = campaigns.prepare(original)
    assert "Route in focus: Selected record (selected in Sinter" in report["document_markdown"]
    assert original["actions"][0]["task"] in next_section(report)
    assert "for this selected route or campaign-wide scope" not in next_section(report)
    assert original == before
