"""Explicit route purpose preserves local evidence and formal application gates."""

import copy
import json
from unittest.mock import patch

import pytest

from sinter import campaigns
from sinter.campaign_capacity import text_characters


def document(purpose=None, *, mode="unknown"):
    route = {"name": "Fictional route", "status": "researching",
             "application_mode": mode}
    if purpose is not None:
        route["purpose"] = purpose
    return {"title": "Fictional route records", "organisation": "Example group",
            "objective": "Retain evidence and agree a next action; nothing is approved.",
            "opportunities": [route]}


@pytest.mark.parametrize("purpose", ["unknown", "application", "discussion", "research"])
def test_explicit_purpose_round_trips_save_reopen_backup_restore_prepare_focus(tmp_path, purpose):
    original = document(purpose)
    before = copy.deepcopy(original)
    store = campaigns.CampaignStore(tmp_path / "first")
    saved = store.save(original)
    reopened = campaigns.CampaignStore(tmp_path / "first").get(saved["id"])
    backup = json.loads(json.dumps(reopened["document"], ensure_ascii=False))
    restored = campaigns.CampaignStore(tmp_path / "restored").save(backup)
    assert reopened == saved and restored["document"] == saved["document"]
    assert campaigns.prepare(backup)["campaign"]["opportunities"][0]["purpose"] == purpose
    focused = campaigns.focused_document(backup, "Fictional route", "Fictional focused record")
    assert focused["document"]["opportunities"][0]["purpose"] == purpose
    assert original == before


def test_missing_legacy_purpose_stays_missing_in_all_local_projections(tmp_path):
    normalized = campaigns.validate(document())
    saved = campaigns.CampaignStore(tmp_path).save(normalized)
    focused = campaigns.focused_document(normalized, "Fictional route", "Fictional focus")
    variants = [normalized, saved["document"], json.loads(json.dumps(normalized)),
                campaigns.prepare(normalized)["campaign"], focused["document"]]
    assert all("purpose" not in value["opportunities"][0] for value in variants)
    assert campaigns.validate(normalized) == normalized


def test_legacy_at_exact_capacity_does_not_acquire_default_purpose(tmp_path):
    original = document()
    original["sources"] = [{"id": "1" * 32, "title": "Fictional source", "notes": ""}]
    original["communications"] = [{"content": "x" * 19900} for _ in range(10)]
    normalized = campaigns.validate(original)
    normalized["sources"][0]["notes"] = "x" * (200000 - text_characters(normalized))
    assert text_characters(normalized) == 200000
    normalized = campaigns.validate(normalized)
    assert "purpose" not in normalized["opportunities"][0]
    saved = campaigns.CampaignStore(tmp_path).save(json.loads(json.dumps(normalized)))
    assert saved["document"] == normalized
    assert campaigns.prepare(normalized)["campaign"] == normalized


@pytest.mark.parametrize("purpose", [None, True, 3, "", "Research", "research ", "adopted", {}, []])
def test_arbitrary_purpose_is_rejected_atomically(tmp_path, purpose):
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(document())
    bad = copy.deepcopy(saved["document"])
    bad["opportunities"][0]["purpose"] = purpose
    with pytest.raises(ValueError, match="[Rr]oute purpose"):
        store.save(bad, saved["id"], saved["revision"])
    assert store.get(saved["id"]) == saved


@pytest.mark.parametrize("purpose", ["discussion", "research"])
@pytest.mark.parametrize("mode", ["unknown", "not_required"])
def test_record_purpose_has_useful_nonapplication_brief_without_automatic_grant_pack(purpose, mode):
    original = document(purpose, mode=mode)
    with patch("sinter.client.chat") as model, patch("sinter.client.search") as search:
        report = campaigns.prepare(original)
    readiness = report["readiness"]
    for key in ["application_workflow_to_confirm", "application_windows_to_check",
                "opportunities_without_checks", "opportunities_without_sources",
                "opportunities_without_answers", "answers_on_unconfirmed_application_routes"]:
        assert readiness[key] == 0
    assert readiness["budget_incomplete"] is False
    for part in [report["markdown"], report["document_markdown"]]:
        assert purpose.title() + " record: retain evidence and next actions" in part
        assert "does not establish application requirements" in part
        assert "No application answers have been recorded" not in part
        assert "No recorded costs are linked" not in part
        assert "recorded cost total is unknown" not in part
        assert "no formal application required" not in part
        assert "final application with the funder" not in part
    model.assert_not_called()
    search.assert_not_called()


@pytest.mark.parametrize("purpose", ["discussion", "research"])
def test_record_purpose_preserves_explicit_stale_adverse_checks_owners_and_held_answers(purpose):
    original = document()
    original["opportunities"][0]["funding_tracking"] = {}
    original["sources"] = [{"id": "1" * 32, "title": "Fictional current source",
                            "url": "https://example.invalid/source", "checked_at": "2026-10-09"}]
    original["requirements"] = [{"opportunity": "Fictional route", "rule": "Recorded condition",
        "status": "not_met", "source_id": "1" * 32, "source_url": "https://example.invalid/old",
        "source_quote": "Original old wording", "evidence": "Condition has not been established",
        "checked_at": "2019-01-01"}]
    original["actions"] = [{"opportunity": "Fictional route", "task": "Ask about the condition",
        "scope_confirmed": True, "owner": "Proposed coordinator", "owner_kind": "person",
        "owner_confirmed": False, "due": "2026-10-20", "status": "open"}]
    original["answers"] = [{"opportunity": "Fictional route", "label": "PRIVATE HELD QUESTION",
                            "text": "PRIVATE ORIGINAL ANSWER", "status": "reviewed", "limit": 20}]
    before = campaigns.validate(original)
    changed = copy.deepcopy(before)
    changed["opportunities"][0]["purpose"] = purpose
    after = campaigns.validate(changed)
    stripped = copy.deepcopy(after)
    del stripped["opportunities"][0]["purpose"]
    assert stripped == before
    report = campaigns.prepare(after)
    assert after == changed
    assert report["readiness"]["requirements_not_met"] == 1
    assert report["readiness"]["claims_without_evidence"] == 1
    assert report["readiness"]["requirements_unresolved"] == 1
    assert report["readiness"]["actions_without_owner"] == 1
    assert report["readiness"]["status"] == "needs_attention"
    assert report["campaign"]["requirements"] == after["requirements"]
    assert report["campaign"]["actions"] == after["actions"]
    assert "Original old wording" in report["markdown"]
    assert "PRIVATE ORIGINAL ANSWER" not in json.dumps(report)
    assert after["answers"] == before["answers"]


@pytest.mark.parametrize("purpose", ["discussion", "research"])
@pytest.mark.parametrize("confirmed", [False, True])
def test_required_formal_workflow_overrides_record_purpose_and_flags_conflict(purpose, confirmed):
    original = document(purpose, mode="required")
    original["opportunities"][0].update(applicant="Example group", applicant_confirmed=confirmed)
    original["answers"] = [{"opportunity": "Fictional route", "label": "Formal question",
                            "text": "Retained formal answer", "limit": 100, "status": "draft"}]
    report = campaigns.prepare(original)
    assert report["readiness"]["purpose_workflow_conflicts"] == 1
    assert report["readiness"]["status"] == "needs_attention"
    assert report["readiness"]["application_workflow_to_confirm"] == int(not confirmed)
    assert report["readiness"]["application_windows_to_check"] == 1
    assert report["readiness"]["opportunities_without_checks"] == 1
    assert report["readiness"]["opportunities_without_sources"] == 1
    assert ("Retained formal answer" in report["markdown"]) is confirmed
    assert report["campaign"]["answers"][0]["text"] == ("Retained formal answer" if confirmed else "")


def test_mixed_legacy_and_record_routes_keep_formal_counts_and_explicit_evidence():
    original = document()
    original["opportunities"] += [{"name": "Discussion route", "purpose": "discussion"},
                                   {"name": "Research route", "purpose": "research"}]
    report = campaigns.prepare(original)
    for key in ["application_workflow_to_confirm", "application_windows_to_check",
                "opportunities_without_checks", "opportunities_without_sources"]:
        assert report["readiness"][key] == 1
    assert "purpose" not in report["campaign"]["opportunities"][0]
    assert "Discussion record" in report["markdown"] and "Research record" in report["markdown"]


def test_application_purpose_and_no_formal_workflow_are_a_conflict_not_an_exemption():
    original = document("application", mode="not_required")
    original["answers"] = [{"opportunity": "Fictional route", "label": "Held formal question",
                            "text": "PRIVATE HELD ANSWER", "status": "draft"}]
    report = campaigns.prepare(original)
    assert report["readiness"]["purpose_workflow_conflicts"] == 1
    assert report["readiness"]["status"] == "needs_attention"
    assert report["readiness"]["application_windows_to_check"] == 1
    assert report["campaign"]["opportunities"][0]["application_mode"] == "not_required"
    assert "PRIVATE HELD ANSWER" not in json.dumps(report)
    assert "conflicting purpose and formal workflow" in report["document_markdown"]


def test_inactive_record_routes_keep_historical_evidence_without_active_application_demands():
    original = document("research")
    original["opportunities"][0]["status"] = "submitted"
    original["communications"] = [{"opportunity": "Fictional route", "direction": "outgoing",
                                   "status": "draft", "content": "Original unsent follow-up"}]
    report = campaigns.prepare(original)
    assert "No route is currently recorded as active" in report["document_markdown"]
    assert "These user-entered statuses are not independently verified" in report["document_markdown"]
    assert report["campaign"]["communications"][0]["status"] == "draft"
    assert "DRAFT · NOT SENT" in report["markdown"]
    for part in [report["markdown"], report["document_markdown"]]:
        assert "final application with the funder" not in part
        assert "No recorded costs are linked" not in part
        assert "recorded cost total is unknown" not in part


def test_inactive_legacy_budget_gate_is_not_changed_by_optional_purpose_policy():
    original = document()
    original["opportunities"][0]["status"] = "paused"
    legacy = campaigns.prepare(original)
    assert legacy["readiness"]["budget_incomplete"] is True
    assert legacy["readiness"]["notice"] == campaigns.NOTICE
    assert "purpose" not in legacy["campaign"]["opportunities"][0]
    original["opportunities"][0]["purpose"] = "research"
    record = campaigns.prepare(original)
    assert record["readiness"]["budget_incomplete"] is False
    assert record["readiness"]["notice"] != campaigns.NOTICE
