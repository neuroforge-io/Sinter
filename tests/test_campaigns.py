"""Campaign admission, incomplete-cost truthfulness and concurrent edit recovery."""
import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
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
        "actions": [{"opportunity": "", "scope_confirmed": True,
                     "task": "Obtain training quotes", "owner": "Alex",
                     "due": "2026-09-17", "status": "open"}],
        "sources": [{"title": "Fictional fund guidelines",
                     "url": "https://example.org/grants/access",
                     "notes": "Manually checked for a fictional test campaign."}],
        **changes,
    }


def test_prepare_preserves_editable_input_and_generates_portable_pack_offline():
    document = campaign()
    document["opportunities"][0].update(
        application_mode="required", applicant="Banksia Volunteers",
        applicant_confirmed=True)
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


def test_legacy_campaign_defaults_to_empty_asset_register_without_changing_funding_readiness():
    document = campaign()
    report = campaigns.prepare(document)

    assert report["campaign"]["assets"] == []
    assert report["portfolio_summary"] == {
        "assets_total": 0, "assets_without_funding_routes": 0,
        "contributor_records_unverified": 0,
        "rights_records_unverified": 0, "disclosure_dates_unknown": 0,
        "prior_art_not_started": 0, "prior_art_leads_recorded": 0,
        "evidence_references": 0,
    }
    assert "assets_total" not in report["readiness"]
    assert "Product and IP research register" not in report["markdown"]


def test_asset_register_preserves_unknowns_and_separates_research_from_eligibility():
    asset = {
        "name": "Example research system", "kind": "research", "stage": "prototype",
        "public_summary": "Public page describes a bounded research prototype.",
        "funding_opportunities": ["Fictional access fund"],
        "differentiation_question": "Which exact system behavior differs from published methods?",
        "contributors_status": "unknown", "contributor_notes": "",
        "rights_status": "public_license_stated",
        "rights_notes": "Public licence statement does not establish company title.",
        "disclosure_status": "unknown", "first_public_date": "",
        "disclosure_notes": "", "prior_art_status": "leads_recorded",
        "prior_art_notes": "MoEfication is a lead to compare against.",
        "prior_art_checked_at": "2026-09-29",
        "references": [{"kind": "rights", "source_id": "1" * 32,
                        "title": "Public licence page",
                        "excerpt": "Public repository licence statement.",
                        "notes": "Public licence only."},
                       {"kind": "prior_art", "source_id": "2" * 32,
                        "title": "Research paper",
                        "excerpt": "The abstract describes the related approach.",
                        "notes": "Abstract only; not a legal review."}],
    }
    document = campaign(assets=[asset], sources=[
        {"id": "1" * 32, "title": "Public licence page",
         "url": "https://example.org/license", "checked_at": "2026-09-29",
         "notes": "Public licence only."},
        {"id": "2" * 32, "title": "Research paper",
         "url": "https://example.org/paper", "checked_at": "2026-09-29",
         "notes": "Abstract only; not a legal review."},
    ])
    before = copy.deepcopy(document)

    report = campaigns.prepare(document)
    normalized = report["campaign"]["assets"][0]

    assert document == before
    assert normalized["contributors_status"] == "unknown"
    assert normalized["rights_status"] == "public_license_stated"
    assert normalized["disclosure_status"] == "unknown"
    assert normalized["first_public_date"] == ""
    assert normalized["prior_art_status"] == "leads_recorded"
    assert normalized["references"][0]["checked_at"] == "2026-09-29"
    assert re.fullmatch(r"[0-9a-f]{32}", normalized["id"])
    assert campaigns.validate(report["campaign"])["assets"][0]["id"] == normalized["id"]
    assert report["portfolio_summary"] == {
        "assets_total": 1, "assets_without_funding_routes": 0,
        "contributor_records_unverified": 1,
        "rights_records_unverified": 1, "disclosure_dates_unknown": 1,
        "prior_art_not_started": 0, "prior_art_leads_recorded": 1,
        "evidence_references": 2,
    }
    assert "## Portfolio IP workstream · separate from funding eligibility" in report["document_markdown"]
    assert "not proof of company title" in report["markdown"]
    assert "not a novelty, patentability or freedom-to-operate conclusion" in report["markdown"]
    assert "Which exact system behavior differs from published methods?" in report["markdown"]
    assert "Research paper" in report["markdown"]
    assert "Source ID 11111111" in report["markdown"]
    assert "Date checked (campaign-entered): 2026-09-29" in report["markdown"]
    assert "Funding routes to assess: Fictional access fund" in report["markdown"]
    assert "Product and IP research register" not in report["document_markdown"]
    assert "## Product and IP research register" in report["markdown"]
    assert campaigns.validate(report["campaign"]) == report["campaign"]


def test_asset_evidence_keeps_its_source_snapshot_and_warns_after_source_refresh():
    source_id = "f" * 32
    old_url = "https://example.org/research/paper-v1"
    current_url = "https://example.org/research/paper-v2"
    document = campaign(
        sources=[{"id": source_id, "title": "Updated research record",
                  "url": current_url, "checked_at": "2026-09-30"}],
        assets=[{"name": "Sinter", "references": [{
            "kind": "prior_art", "source_id": source_id,
            "title": "Original research paper", "url": old_url,
            "excerpt": "The original passage assessed for this asset.",
            "checked_at": "2026-09-12",
        }]}],
    )

    report = campaigns.prepare(document)
    reference = report["campaign"]["assets"][0]["references"][0]

    assert reference == {
        "kind": "prior_art", "source_id": source_id,
        "title": "Original research paper", "url": old_url,
        "excerpt": "The original passage assessed for this asset.",
        "checked_at": "2026-09-12", "notes": "",
    }
    assert (
        campaigns.validate(report["campaign"])["assets"][0]["references"][0]
        == reference
    )
    assert "[Original research paper](<" + old_url + ">)" in report["markdown"]
    assert "Checked date (campaign-entered): 2026-09-12" in report["markdown"]
    assert (
        "RECHECK RECOMMENDED — linked source title, URL, checked date changed"
        in report["markdown"]
    )
    assert (
        "Current source register: [Updated research record](<"
        + current_url + ">)" in report["markdown"]
    )
    assert "checked: 2026-09-30" in report["markdown"]
    assert (
        "Re-open the saved passage, confirm it still applies, and update this reference"
        in report["markdown"]
    )


def test_new_asset_evidence_link_captures_current_source_fields_once():
    source_id = "e" * 32
    source = {"id": source_id, "title": "Current guidance",
              "url": "https://example.org/guidance", "checked_at": "2026-09-30"}

    normalized = campaigns.validate(campaign(
        sources=[source],
        assets=[{"name": "Sinter", "references": [{
            "kind": "other", "source_id": source_id,
            "excerpt": "A passage newly checked against the linked source.",
        }]}],
    ))

    reference = normalized["assets"][0]["references"][0]
    assert reference["title"] == source["title"]
    assert reference["url"] == source["url"]
    assert reference["checked_at"] == source["checked_at"]
    assert "RECHECK RECOMMENDED" not in campaigns.prepare(normalized)["markdown"]


def test_blank_asset_snapshot_fields_remain_unknown_after_source_update():
    source_id = "a" * 32
    source = {"id": source_id, "title": "Saved source title",
              "url": "https://example.org/current", "checked_at": "2026-09-30"}
    asset = {"name": "Sinter", "references": [{
        "kind": "other", "source_id": source_id,
        "title": "Saved source title", "url": "", "excerpt": "Saved passage",
        "checked_at": "",
    }]}

    report = campaigns.prepare(campaign(sources=[source], assets=[asset]))
    reference = report["campaign"]["assets"][0]["references"][0]

    assert reference["url"] == ""
    assert reference["checked_at"] == ""
    assert (
        "RECHECK RECOMMENDED — linked source URL, checked date changed"
        in report["markdown"]
    )
    assert (
        "Current source register: [Saved source title](<"
        + source["url"] + ">)" in report["markdown"]
    )


@pytest.mark.parametrize(("field", "value", "label"), [
    ("title", "Renamed source", "title"),
    ("url", "https://example.org/updated", "URL"),
    ("checked_at", "2026-09-30", "checked date"),
])
def test_asset_evidence_source_metadata_drift_recommends_recheck(field, value, label):
    source_id = "d" * 32
    source = {"id": source_id, "title": "Original source",
              "url": "https://example.org/original", "checked_at": "2026-09-12"}
    updated_source = {**source, field: value}
    asset = {"name": "Sinter", "references": [{
        "kind": "other", "source_id": source_id,
        "title": source["title"], "url": source["url"],
        "excerpt": "Saved passage", "checked_at": source["checked_at"],
    }]}

    report = campaigns.prepare(campaign(sources=[updated_source], assets=[asset]))

    assert (
        "RECHECK RECOMMENDED — linked source " + label + " changed"
        in report["markdown"]
    )


@pytest.mark.parametrize("field,value,match", [
    ("kind", "company", "valid product or asset type"),
    ("stage", "commercialised", "valid product or asset stage"),
    ("contributors_status", "complete", "valid contributor record status"),
    ("rights_status", "owned", "valid rights record status"),
    ("prior_art_status", "novel", "valid prior-art research status"),
    ("first_public_date", "not sure", "YYYY-MM-DD"),
])
def test_asset_register_rejects_unbounded_or_conclusive_statuses(field, value, match):
    asset = {"name": "Example asset", field: value}
    with pytest.raises(ValueError, match=match):
        campaigns.validate(campaign(assets=[asset]))


def test_asset_disclosure_date_and_evidence_reference_are_validated():
    with pytest.raises(ValueError, match="Record a first public disclosure date"):
        campaigns.validate(campaign(assets=[{
            "name": "Example asset", "disclosure_status": "date_recorded",
        }]))
    with pytest.raises(ValueError, match="valid asset evidence type"):
        campaigns.validate(campaign(assets=[{
            "name": "Example asset", "references":[{
                "kind": "ownership_proven", "title": "A record",
            }],
        }]))
    with pytest.raises(ValueError, match=r"HTTP\(S\) link"):
        campaigns.validate(campaign(assets=[{
            "name": "Example asset", "references":[{
                "kind": "rights", "title": "Local contract", "url": "file:///home/user/contract.pdf",
            }],
        }]))


def test_asset_reference_placeholder_is_ignored_but_partial_reference_needs_title():
    normalized = campaigns.validate(campaign(assets=[{
        "name": "Example asset", "references": [{"kind": "other"}],
    }]))
    assert normalized["assets"][0]["references"] == []

    with pytest.raises(ValueError, match="asset evidence title"):
        campaigns.validate(campaign(assets=[{
            "name": "Example asset", "references": [{
                "kind": "rights", "url": "https://example.org/record",
            }],
        }]))


@pytest.mark.parametrize(("field", "status", "reference_kind", "message"), [
    ("contributors_status", "evidence_recorded", "rights",
     "contributor evidence reference"),
    ("rights_status", "public_license_stated", "public_claim",
     "rights evidence reference"),
    ("rights_status", "evidence_recorded", "other",
     "rights evidence reference"),
    ("prior_art_status", "leads_recorded", "public_claim",
     "prior-art evidence reference"),
    ("prior_art_status", "preliminary_screen", None,
     "prior-art evidence reference"),
])
def test_asset_recorded_workstreams_require_matching_evidence_reference(
        field, status, reference_kind, message):
    asset = {"name": "Example asset", field: status}
    if reference_kind:
        asset["references"] = [{"kind": reference_kind, "title": "Record"}]
    with pytest.raises(ValueError, match=message):
        campaigns.validate(campaign(assets=[asset]))


def test_asset_ids_are_stable_for_legacy_names_and_unique_when_supplied():
    first = campaigns.validate(campaign(assets=[{"name": "Stable asset"}]))
    second = campaigns.validate(campaign(assets=[{"name": "Stable asset"}]))
    assert first["assets"][0]["id"] == second["assets"][0]["id"]

    with pytest.raises(ValueError, match="distinct record ID"):
        campaigns.validate(campaign(assets=[
            {"name": "One", "id": "a" * 32},
            {"name": "Two", "id": "a" * 32},
        ]))


def test_campaign_sources_get_stable_ids_and_asset_links_cannot_dangle():
    source = {"title": "Prior art paper", "url": "https://example.org/paper",
              "checked_at": "2026-09-29"}
    first = campaigns.validate(campaign(sources=[source]))
    second = campaigns.validate(campaign(sources=[source]))
    source_id = first["sources"][0]["id"]
    assert re.fullmatch(r"[0-9a-f]{32}", source_id)
    assert second["sources"][0]["id"] == source_id
    assert first["sources"][0]["checked_at"] == "2026-09-29"

    with pytest.raises(ValueError, match="source that no longer exists"):
        campaigns.validate(campaign(assets=[{"name": "Sinter", "references": [{
            "kind": "prior_art", "source_id": "f" * 32,
        }]}]))

    with pytest.raises(ValueError, match="distinct record ID"):
        campaigns.validate(campaign(sources=[
            {"id": "a" * 32, "title": "One"},
            {"id": "a" * 32, "title": "Two"},
        ]))


def test_application_workflow_and_applicant_are_explicit_and_backward_compatible():
    legacy = campaigns.validate(campaign())
    assert legacy["opportunities"][0]["application_mode"] == "unknown"
    assert legacy["opportunities"][0]["applicant"] == ""
    assert legacy["opportunities"][0]["applicant_confirmed"] is False

    explicit = campaign()
    explicit["opportunities"][0].update(
        application_mode="required", applicant="Warraburra State School")
    normalized = campaigns.validate(explicit)
    assert normalized["opportunities"][0]["application_mode"] == "required"
    assert normalized["opportunities"][0]["applicant"] == "Warraburra State School"
    assert normalized["opportunities"][0]["applicant_confirmed"] is False
    explicit["opportunities"][0]["applicant_confirmed"] = True
    assert campaigns.validate(explicit)["opportunities"][0]["applicant_confirmed"] is True
    with pytest.raises(ValueError, match="true or false"):
        campaigns.validate(campaign(opportunities=[{
            **campaign()["opportunities"][0], "applicant_confirmed": "yes",
        }]))
    with pytest.raises(ValueError, match="named applicant"):
        campaigns.validate(campaign(opportunities=[{
            **campaign()["opportunities"][0], "application_mode": "required",
            "applicant_confirmed": True,
        }]))
    with pytest.raises(ValueError, match="required application"):
        campaigns.validate(campaign(opportunities=[{
            **campaign()["opportunities"][0], "application_mode": "not_required",
            "applicant": "School", "applicant_confirmed": True,
        }]))
    with pytest.raises(ValueError, match="valid application workflow"):
        campaigns.validate(campaign(opportunities=[{
            **campaign()["opportunities"][0], "application_mode": "maybe",
        }]))


def test_only_routes_with_confirmed_application_and_applicant_need_answer_drafts():
    non_application = campaign()
    non_application["opportunities"][0].update(
        route_type="non_cash_support", application_mode="not_required", applicant="")
    non_application["answers"] = []
    report = campaigns.prepare(non_application)
    assert report["readiness"]["application_workflow_to_confirm"] == 0
    assert report["readiness"]["opportunities_without_answers"] == 0
    assert "no formal application recorded" in report["document_markdown"]

    unknown = campaigns.prepare(campaign(answers=[]))
    assert unknown["readiness"]["application_workflow_to_confirm"] == 1
    assert unknown["readiness"]["opportunities_without_answers"] == 0

    required = campaign(answers=[])
    required["opportunities"][0].update(
        application_mode="required", applicant="Banksia Volunteers")
    report = campaigns.prepare(required)
    assert report["readiness"]["application_workflow_to_confirm"] == 1
    assert report["readiness"]["opportunities_without_answers"] == 0

    pending = campaign()
    pending["answers"][0]["text"] = "PRIVATE HELD ANSWER MUST NOT APPEAR"
    pending["answers"][0]["limit"] = 8
    pending["opportunities"][0].update(
        application_mode="required", applicant="Proposed Banksia Volunteers")
    pending_report = campaigns.prepare(pending)
    assert pending_report["readiness"]["answers_on_unconfirmed_application_routes"] == 1
    assert pending_report["readiness"]["answers_over_limit"] == 0
    assert pending_report["readiness"]["answers_empty"] == 0
    assert pending_report["readiness"]["answers_unreviewed"] == 0
    assert "named applicant is recorded but not directly confirmed" in pending_report["markdown"]
    assert "PRIVATE HELD ANSWER MUST NOT APPEAR" not in pending_report["markdown"]
    assert "Project purpose" not in pending_report["markdown"]
    assert pending_report["campaign"]["answers"][0]["text"] == ""
    assert pending_report["campaign"]["answers"][0]["label"] == (
        "Held answer details omitted from report")
    assert pending_report["campaign"]["answers"][0]["limit"] is None
    assert pending_report["answer_metrics"] == []
    assert "PRIVATE HELD ANSWER MUST NOT APPEAR" not in json.dumps(pending_report)
    assert "Project purpose" not in json.dumps(pending_report)
    assert pending["answers"][0]["text"] == "PRIVATE HELD ANSWER MUST NOT APPEAR"
    assert "text omitted" in pending_report["markdown"]
    pending["opportunities"][0]["applicant_confirmed"] = True
    report = campaigns.prepare(pending)
    assert report["readiness"]["application_workflow_to_confirm"] == 0
    assert report["readiness"]["opportunities_without_answers"] == 0
    assert report["readiness"]["answers_over_limit"] == 1
    assert report["campaign"]["answers"][0]["text"] == "PRIVATE HELD ANSWER MUST NOT APPEAR"
    assert report["answer_metrics"][0]["label"] == "Project purpose"
    assert "PRIVATE HELD ANSWER MUST NOT APPEAR" in report["markdown"]

    pending["opportunities"][0]["status"] = "closed"
    historical = campaigns.prepare(pending)
    assert historical["campaign"]["answers"][0]["text"] == ""
    assert historical["campaign"]["answers"][0]["label"] == (
        "Held answer details omitted from report")
    assert historical["answer_metrics"] == []
    assert "Project purpose" not in historical["markdown"]
    assert "PRIVATE HELD ANSWER MUST NOT APPEAR" not in json.dumps(historical)


def test_linked_communication_evidence_preserves_its_original_source_snapshot():
    source = {"id": "c" * 32, "title": "Official guidance",
              "url": "https://example.org/guidance", "checked_at": "2026-09-29"}
    normalized = campaigns.validate(campaign(sources=[source], communications=[{
        "direction": "outgoing", "status": "draft", "channel": "email",
        "evidence_links": [{"source_id": "c" * 32, "title": "Stale title",
                            "url": "https://example.org/old", "checked_at": "2026-01-01"}],
    }]))
    link = normalized["communications"][0]["evidence_links"][0]
    assert link["source_id"] == "c" * 32
    assert link["title"] == "Stale title"
    assert link["url"] == "https://example.org/old"
    assert link["checked_at"] == "2026-01-01"

    req_campaign = campaign(sources=[source])
    req_campaign["requirements"][0].update(source_id="c" * 32,
                                          checked_at="2026-01-01")
    req_campaign["opportunities"][0].update(application_mode="required",
                                             applicant="Banksia Volunteers")
    normalized_requirement = campaigns.validate(req_campaign)["requirements"][0]
    assert normalized_requirement["checked_at"] == "2026-01-01"
    assert normalized_requirement["source_url"] == "https://example.org/grants/access/eligibility"


def test_changed_linked_source_keeps_communication_snapshot_and_warns_in_audit():
    source = {"id": "c" * 32, "title": "Official guidance",
              "url": "https://example.org/guidance", "checked_at": "2026-09-29"}
    document = campaign(sources=[source], communications=[{
        "direction": "outgoing", "status": "draft", "channel": "email",
        "evidence_links": [{"source_id": source["id"],
                            "title": source["title"], "url": source["url"],
                            "checked_at": source["checked_at"]}],
    }])
    linked = campaigns.validate(document)
    linked["sources"][0].update(
        title="Updated official guidance",
        url="https://example.org/guidance/current", checked_at="2026-09-30")
    refreshed = campaigns.validate(linked)

    saved_link = refreshed["communications"][0]["evidence_links"][0]
    assert saved_link == {
        "source_id": source["id"], "title": "Official guidance",
        "url": "https://example.org/guidance", "checked_at": "2026-09-29",
        "notes": "",
    }
    report = campaigns.prepare(refreshed)
    assert "Saved source snapshot differs from the current source register; recheck before reuse." in report["markdown"]
    assert "https://example.org/guidance" in report["markdown"]
    assert "https://example.org/guidance/current" in report["markdown"]


def test_blank_requirement_source_date_does_not_inherit_a_fresh_registry_date():
    today = date.today().isoformat()
    source = {"id": "e" * 32, "title": "Official guidance",
              "url": "https://example.org/current", "checked_at": today}
    document = campaign(sources=[source])
    document["requirements"][0].update(source_id=source["id"], source_url="",
                                      source_quote="An old saved quotation.", checked_at="")
    normalized = campaigns.validate(document)
    requirement = normalized["requirements"][0]
    assert requirement["source_url"] == ""
    assert requirement["checked_at"] == ""
    assert not campaigns._supported(requirement, date.today(), normalized["sources"])


def test_refreshing_a_linked_source_does_not_refresh_old_requirement_evidence():
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    source = {"id": "d" * 32, "title": "Official eligibility rules",
              "url": "https://example.org/eligibility", "checked_at": yesterday}
    document = campaign(sources=[source])
    document["requirements"] = [{
        "opportunity": "Fictional access fund",
        "rule": "The applicant has the required business registration.",
        "status": "met", "evidence": "The user-entered company record is present.",
        "source_id": source["id"], "source_url": source["url"],
        "source_quote": "Applicants must hold the listed registration.",
        "checked_at": yesterday,
    }]
    normalized = campaigns.validate(document)
    check = normalized["requirements"][0]
    assert campaigns._supported(check, today, normalized["sources"])

    refreshed = copy.deepcopy(normalized)
    refreshed["sources"][0]["checked_at"] = today.isoformat()
    refreshed = campaigns.validate(refreshed)
    refreshed_check = refreshed["requirements"][0]
    assert refreshed_check["checked_at"] == yesterday
    assert refreshed_check["source_quote"] == check["source_quote"]
    assert not campaigns._supported(refreshed_check, today, refreshed["sources"])

    report = campaigns.prepare(refreshed)
    assert report["readiness"]["claims_without_evidence"] == 1


def test_preliminary_prior_art_and_disclosure_dates_need_linked_source_passages():
    source = {"id": "b" * 32, "title": "Public record",
              "url": "https://example.org/record", "checked_at": "2026-09-29"}
    asset = {"name": "Sinter", "prior_art_status": "preliminary_screen",
             "references": [{"kind": "prior_art", "source_id": "b" * 32,
                             "excerpt": "Short research passage."}]}
    normalized = campaigns.validate(campaign(sources=[source], assets=[asset]))
    assert normalized["assets"][0]["references"][0]["checked_at"] == "2026-09-29"

    with pytest.raises(ValueError, match="checked source, date and relevant passage"):
        campaigns.validate(campaign(sources=[source], assets=[{
            **asset, "references": [{"kind": "prior_art", "source_id": "b" * 32}],
        }]))

    with pytest.raises(ValueError, match="checked disclosure source, date and relevant passage"):
        campaigns.validate(campaign(sources=[source], assets=[{
            "name": "Sinter", "disclosure_status": "date_recorded",
            "first_public_date": "2026-09-01",
            "references": [{"kind": "disclosure", "source_id": "b" * 32}],
        }]))


def test_communications_report_warns_before_sharing_message_text():
    report = campaigns.prepare(campaign(communications=[{
        "direction": "outgoing", "status": "draft", "channel": "email",
        "content": "Draft with private details",
    }]))
    assert "DRAFT · NOT SENT" in report["markdown"]
    assert "This report includes message text and may include personal information." in report["markdown"]
    assert "use the redacted evidence-pack export" in report["markdown"]


def test_asset_register_bounds_rows_references_and_duplicate_names():
    with pytest.raises(ValueError, match="distinct name"):
        campaigns.validate(campaign(assets=[{"name": "Sinter"}, {"name": "sinter"}]))
    with pytest.raises(ValueError, match="Use at most 20 evidence references"):
        campaigns.validate(campaign(assets=[{"name": "Sinter", "references": [
            {"title": f"Ref {number}"} for number in range(21)
        ]}]))
    with pytest.raises(ValueError, match="Use at most 60 assets rows"):
        campaigns.validate(campaign(assets=[{"name": f"Asset {number}"}
                                             for number in range(61)]))
    with pytest.raises(ValueError, match="does not match an opportunity name"):
        campaigns.validate(campaign(assets=[{
            "name": "Sinter", "funding_opportunities": ["Nonexistent route"],
        }]))


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
            {"opportunity": "Active route", "task": "Confirm the active route evidence", "owner": "Grant lead",
             "due": "2026-10-02", "status": "open"},
            {"opportunity": "Closed route", "task": "SECOND_ACTION_MUST_STAY_IN_AUDIT_ONLY", "owner": "Treasurer",
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
    assert "Active route" in brief and "Status entered:** clarification" in brief
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
    assert "· Owner: Owner type not confirmed: Grant lead" in brief
    assert "Proposed date: 2 Oct 2026 (proposed, not confirmed)" in brief
    assert campaigns.NOTICE in brief

    assert "Closed route" in audit and "Paused route" in audit
    assert "### Historical answer drafts · inactive route" in audit
    assert "1 historical answer row(s) retained; question labels and text omitted" in audit
    assert "Historical answer label" not in audit
    assert "HISTORICAL_ANSWER_TEXT" not in audit
    assert "PRIVATE\\_SOURCE\\_NOTE" in audit
    assert "## Source references" in audit
    # Legacy campaign fixtures omit newer optional signatory/owner fields;
    # validation supplies defaults and both views remain renderable.
    assert report["campaign"]["signatory"] == ""
    assert report["campaign"]["actions"][0]["owner_confirmed"] is False


def test_decision_brief_uses_the_focused_route_action_before_global_or_other_work():
    base = campaign()
    first, focused = base["opportunities"][0], {
        **base["opportunities"][0], "name": "Focused route",
    }
    document = campaign(
        opportunities=[first, focused],
        actions=[
            {"opportunity": first["name"], "task": "Other route action",
             "owner": "", "due": "", "status": "open"},
            {"opportunity": "", "scope_confirmed": True, "task": "Campaign-wide action", "owner": "",
             "due": "", "status": "open"},
            {"opportunity": focused["name"], "task": "Focused route action",
             "owner": "", "due": "", "status": "open"},
        ],
    )

    brief = campaigns.prepare(document, "Focused route")["document_markdown"]

    assert "Focused route action" in brief
    assert "Scope: Focused route" in brief
    assert "Other route action" not in brief
    assert "Campaign-wide action" not in brief


def test_decision_brief_falls_back_to_campaign_wide_action_for_the_focused_route():
    base = campaign()
    document = campaign(
        opportunities=[
            base["opportunities"][0],
            {**base["opportunities"][0], "name": "Focused route"},
        ],
        actions=[
            {"opportunity": base["opportunities"][0]["name"],
             "task": "Wrong route action",
             "owner": "", "due": "", "status": "open"},
            {"opportunity": "", "scope_confirmed": True, "task": "Campaign-wide action", "owner": "",
             "due": "", "status": "open"},
        ],
    )

    brief = campaigns.prepare(document, "Focused route")["document_markdown"]

    assert "Campaign-wide action" in brief
    assert "Scope: Campaign-wide" in brief
    assert "Wrong route action" not in brief


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
    assert (
        "Known quoted subtotal: A$125.00. Quoted total incomplete"
        in report["markdown"]
    )
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
    assert "quoted total is unknown" in report["markdown"]
    assert (
        "current quoted subtotal not entered; quoted total unknown"
        in report["markdown"]
    )


def test_known_subtotal_can_exceed_ceiling_with_other_costs_still_unknown():
    document = campaign()
    document["opportunities"][0]["ceiling"] = 100
    report = campaigns.prepare(document)
    assert report["budget_summary"]["by_opportunity"][0]["over_ceiling"] is None
    assert (
        report["budget_summary"]["by_opportunity"][0]["quoted_subtotal_over_ceiling"]
        is True
    )
    assert report["readiness"]["budgets_over_ceiling"] == 0
    assert report["readiness"]["quoted_subtotals_above_ceiling"] == 1
    assert report["budget_summary"]["total"] is None
    assert "numerically above the recorded AUD ceiling" in report["markdown"]
    assert "application comparison unqualified" in report["markdown"]


def test_answer_count_measures_exact_untrimmed_text_and_keeps_overlimit_draft():
    document = campaign()
    document["opportunities"][0].update(
        application_mode="required", applicant="Banksia Volunteers",
        applicant_confirmed=True)
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
    document["opportunities"][0].update(
        application_mode="required", applicant="Banksia Volunteers",
        applicant_confirmed=True)
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
        "User-marked met · unverified — source record incomplete or stale"
        in report["markdown"]
    )


def test_eligibility_evidence_must_be_current_and_not_future_dated():
    today = date.today()
    row = {"evidence": "Applicant-specific detail", "source_url": "https://example.org/rules",
           "source_quote": "Exact source wording", "checked_at": today.isoformat()}
    assert campaigns._supported(row, today)
    row["checked_at"] = (today - timedelta(days=90)).isoformat()
    assert campaigns._supported(row, today)
    row["checked_at"] = (today - timedelta(days=91)).isoformat()
    assert not campaigns._supported(row, today)
    row["checked_at"] = (today + timedelta(days=1)).isoformat()
    assert not campaigns._supported(row, today)


def test_future_dated_user_marked_eligibility_evidence_stays_unresolved():
    document = campaign()
    document["opportunities"][0].update(application_mode="required",
                                         applicant="Banksia Volunteers")
    document["requirements"][0]["status"] = "met"
    document["requirements"][0]["checked_at"] = (date.today() + timedelta(days=1)).isoformat()
    report = campaigns.prepare(document)
    assert report["readiness"]["claims_without_evidence"] == 1
    assert report["readiness"]["requirements_unresolved"] == 1
    assert "source record incomplete or stale" in report["markdown"]


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
    closing = date.today() + timedelta(days=14)
    source_id = campaigns.validate(document)["sources"][0]["id"]
    document["sources"][0]["checked_at"] = date.today().isoformat()
    document["opportunities"][0].update(
        deadline=closing.isoformat(), application_window="fixed",
        window_source_id=source_id,
        window_source_url=document["sources"][0]["url"],
            window_source_quote=f"Applications close on {closing.isoformat()}.",
            window_checked_at=date.today().isoformat(),
            application_mode="required", applicant="Banksia Volunteers",
            applicant_confirmed=True,
    )
    document["requirements"][0]["status"] = "met"
    document["answers"][0]["status"] = "reviewed"
    document["budget"] = document["budget"][1:]
    document["actions"][0]["status"] = "done"
    report = campaigns.prepare(document)
    assert report["readiness"]["requirements_unresolved"] == 0
    assert report["readiness"]["status"] == "human_review"
    assert report["readiness"]["budget_amount_basis_review"] == 1
    assert report["readiness"]["quoted_subtotals_above_ceiling"] == 0
    above = copy.deepcopy(document)
    above["opportunities"][0]["ceiling"] = "100.00"
    observation = campaigns.prepare(above)
    assert observation["readiness"]["quoted_subtotals_above_ceiling"] == 1
    assert observation["readiness"]["budgets_over_ceiling"] == 0
    assert observation["readiness"]["status"] == "human_review"
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
    assert report["readiness"]["opportunities_without_answers"] == 0
    assert report["readiness"]["application_workflow_to_confirm"] == 1


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
    assert report["readiness"]["opportunities_without_answers"] == 0
    assert report["readiness"]["application_workflow_to_confirm"] == 1
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
    assert "Application window: Fixed closing date: 2026-10-04" in markdown
    assert "Historical record · User-entered status · not checked" in markdown
    assert "not-pursued" in markdown


def test_rolling_application_window_is_normalized_and_reported_without_a_fake_deadline():
    document = campaign()
    opportunity = document["opportunities"][0]
    source_id = campaigns.validate(document)["sources"][0]["id"]
    document["sources"][0]["checked_at"] = "2026-09-29"
    opportunity.update(
        deadline="", application_window="rolling",
        window_source_id=source_id,
        window_source_url=document["sources"][0]["url"],
        window_source_quote="Applications are accepted all year round.",
        window_checked_at="2026-09-29",
    )
    normalized = campaigns.validate(document)
    row = normalized["opportunities"][0]
    assert row["application_window"] == "rolling"
    assert row["deadline"] == ""
    assert row["window_source_quote"] == "Applications are accepted all year round."
    assert row["window_checked_at"] == "2026-09-29"
    markdown = campaigns.prepare(document)["markdown"]
    assert "Application window: Rolling / year-round" in markdown
    assert "Applications are accepted all year round." in markdown
    assert "Application deadline: Not confirmed" not in markdown
    brief = campaigns.prepare(document)["document_markdown"]
    assert "**Cash award / ceiling:** A$5,000" in brief
    report = campaigns.prepare(document)
    assert report["readiness"]["application_windows_to_check"] == 0


def test_requirement_links_follow_the_registered_source_id_when_its_url_changes():
    document = campaign()
    source_id = campaigns.validate(document)["sources"][0]["id"]
    document["sources"][0]["id"] = source_id
    old_url = document["sources"][0]["url"]
    document["requirements"][0].update(source_id=source_id, source_url=old_url)
    document["sources"][0]["url"] = "https://example.org/current-guidance"

    normalized = campaigns.validate(document)
    requirement = normalized["requirements"][0]
    assert requirement["source_id"] == source_id
    assert requirement["source_url"] == old_url
    assert not campaigns._supported(requirement, date.today(), normalized["sources"])
    markdown = campaigns.prepare(document)["markdown"]
    assert "[Fictional fund guidelines](<https://example.org/grants/access>)" in markdown
    assert "Source ID " + source_id[:8] in markdown


def test_application_window_can_link_a_registered_source_in_reports():
    document = campaign()
    source_id = campaigns.validate(document)["sources"][0]["id"]
    document["sources"][0]["checked_at"] = "2026-09-29"
    document["opportunities"][0].update(
        application_window="rolling",
        window_source_id=source_id,
        window_source_url=document["sources"][0]["url"],
        window_source_quote="Applications are accepted all year round.",
        window_checked_at="2026-09-29",
    )

    report = campaigns.prepare(document)
    assert report["campaign"]["opportunities"][0]["window_source_id"] == source_id
    assert "linked source: [Fictional fund guidelines]" in report["markdown"]
    assert "Source ID " + source_id[:8] in report["document_markdown"]


@pytest.mark.parametrize("snapshot_field,snapshot_value", [
    ("window_source_url", ""),
    ("window_source_url", "https://example.org/older-guidance"),
    ("window_checked_at", "2026-09-28"),
])
def test_window_reports_describe_stale_source_snapshots_without_claiming_the_source_changed(
    snapshot_field, snapshot_value,
):
    document = campaign()
    normalized = campaigns.validate(document)
    source = normalized["sources"][0]
    source["checked_at"] = "2026-09-29"
    route = normalized["opportunities"][0]
    route.update(
        application_window="rolling",
        window_source_id=source["id"],
        window_source_url=source["url"],
        window_source_quote="Expressions of interest are accepted year-round.",
        window_checked_at=source["checked_at"],
    )
    route[snapshot_field] = snapshot_value

    report = campaigns.prepare(normalized)

    for output in (report["markdown"], report["document_markdown"]):
        assert "saved source snapshot is missing or out of date" in output
        assert "recheck against the linked source before use" in output
        assert "source changed since wording was checked" not in output


@pytest.mark.parametrize("collection,key", [
    ("requirements", "source_id"),
    ("opportunities", "window_source_id"),
])
def test_campaign_source_links_reject_missing_or_malformed_source_ids(collection, key):
    document = campaign()
    document[collection][0][key] = "not-a-source-id"
    with pytest.raises(ValueError, match="campaign source"):
        campaigns.validate(document)


def test_campaign_brief_formats_money_and_dates_for_people():
    document = campaign(actions=[{
        "opportunity": "Fictional access fund", "task": "Confirm the application plan",
        "owner": "Grant lead", "due": "2026-10-02", "status": "open",
    }])
    document["opportunities"][0].update(
        status="open", deadline="2026-10-04", application_window="fixed",
        window_source_quote="Applications close on 4 October 2026.",
        window_checked_at="2026-09-29", ceiling="60000",
    )

    brief = campaigns.prepare(document)["document_markdown"]
    assert "Fixed closing date: 4 Oct 2026" in brief
    assert "checked: 29 Sept 2026" in brief
    assert "**Cash award / ceiling:** A$60,000" in brief
    assert "Proposed date: 2 Oct 2026 (proposed, not confirmed)" in brief

    document["opportunities"][0]["ceiling"] = "60000.50"
    assert "**Cash award / ceiling:** A$60,000.50" in campaigns.prepare(document)["document_markdown"]


def test_decision_brief_flags_stale_or_future_application_window_checks():
    document = campaign()
    opportunity = document["opportunities"][0]
    opportunity.update(
        deadline="", application_window="rolling",
        window_source_quote="Applications are accepted all year round.",
        window_checked_at=(date.today() - timedelta(days=91)).isoformat(),
    )
    brief = campaigns.prepare(document)["document_markdown"]
    assert "last checked 91 days ago; recheck before use" in brief
    assert "1 active application window(s) need current official wording" in brief

    opportunity["window_checked_at"] = (date.today() + timedelta(days=1)).isoformat()
    brief = campaigns.prepare(document)["document_markdown"]
    assert "future-dated check; correct before use" in brief


def test_active_route_without_a_dated_window_source_is_counted_as_open_review_work():
    report = campaigns.prepare(campaign())

    assert report["readiness"]["application_windows_to_check"] == 1
    assert "1 active application window(s) need current official wording" in report["document_markdown"]


def test_application_window_check_is_current_through_day_90_and_stale_on_day_91():
    today = date.today()
    normalized = campaigns.validate(campaign())
    route = normalized["opportunities"][0]
    source = normalized["sources"][0]
    source["checked_at"] = (today - timedelta(days=90)).isoformat()
    route.update(application_window="rolling", deadline="",
                 window_source_id=source["id"], window_source_url=source["url"],
                 window_source_quote="Applications are accepted year-round.")
    route["window_checked_at"] = (today - timedelta(days=90)).isoformat()
    assert campaigns._application_window_is_current(route, today, [source])
    route["window_checked_at"] = (today - timedelta(days=91)).isoformat()
    assert not campaigns._application_window_is_current(route, today, [source])


def test_refreshing_the_window_source_does_not_refresh_its_old_quote():
    today = date.today()
    normalized = campaigns.validate(campaign())
    route = normalized["opportunities"][0]
    source = normalized["sources"][0]
    source["checked_at"] = today.isoformat()
    route.update(application_window="rolling", deadline="",
                 window_source_id=source["id"], window_source_url=source["url"],
                 window_source_quote="Applications are accepted year-round.",
                 window_checked_at=today.isoformat())
    assert campaigns._application_window_is_current(route, today, [source])
    source["checked_at"] = (today - timedelta(days=1)).isoformat()
    assert not campaigns._application_window_is_current(route, today, [source])


def test_unlinked_application_window_quote_cannot_be_current():
    today = date.today()
    normalized = campaigns.validate(campaign())
    route = normalized["opportunities"][0]
    route.update(application_window="rolling", deadline="",
                 window_source_quote="Applications are accepted year-round.",
                 window_checked_at=today.isoformat())
    assert not campaigns._application_window_is_current(route, today, normalized["sources"])


def test_legacy_application_deadlines_migrate_as_fixed_and_blank_as_unknown():
    document = campaign()
    normalized = campaigns.validate(document)
    assert normalized["opportunities"][0]["application_window"] == "fixed"
    assert normalized["opportunities"][0]["window_source_quote"] == ""
    document["opportunities"][0]["deadline"] = ""
    normalized = campaigns.validate(document)
    assert normalized["opportunities"][0]["application_window"] == "unknown"


def test_invalid_application_window_is_rejected_instead_of_silently_changed():
    document = campaign()
    document["opportunities"][0]["application_window"] = "whenever"
    with pytest.raises(ValueError, match="valid application window"):
        campaigns.validate(document)


def test_action_scope_is_optional_but_must_reference_a_campaign_opportunity():
    document = campaign(actions=[{
        "opportunity": "Fictional access fund", "task": "Confirm the match",
        "owner": "", "due": "", "status": "open",
    }])
    assert campaigns.validate(document)["actions"][0]["opportunity"] == "Fictional access fund"
    document["actions"][0]["opportunity"] = "Other fund"
    with pytest.raises(ValueError, match="opportunity reference does not match"):
        campaigns.validate(document)


def test_next_open_action_uses_earliest_upcoming_deadline_before_undated_work():
    today = date.today()
    document = campaigns.validate(campaign(actions=[
        {"opportunity": "Fictional access fund", "task": "Undated route work",
         "owner": "", "due": "", "status": "open"},
        {"opportunity": "Fictional access fund", "task": "Later route deadline",
         "owner": "", "due": (today + timedelta(days=9)).isoformat(), "status": "open"},
        {"opportunity": "Fictional access fund", "task": "First route deadline",
         "owner": "", "due": (today + timedelta(days=2)).isoformat(), "status": "open"},
    ]))

    assert campaigns._next_open_action(document, "Fictional access fund")["task"] == "First route deadline"


def test_legacy_action_without_scope_needs_confirmation_and_is_not_current_work():
    document = campaign(actions=[{
        "task": "Submit the closed application", "owner": "",
        "due": "2026-09-01", "status": "open",
    }])
    document["opportunities"][0]["status"] = "closed"

    report = campaigns.prepare(document)

    assert report["campaign"]["actions"][0]["scope_confirmed"] is False
    assert report["readiness"]["actions_scope_unconfirmed"] == 1
    assert report["readiness"]["open_actions"] == 0
    assert "Submit the closed application" not in report["document_markdown"]
    assert "1 open action(s) need scope confirmation" in report["document_markdown"]
    assert "Scope: Not confirmed" in report["markdown"]
    assert "Submit the closed application" in report["markdown"]


def test_submitted_route_actions_need_explicit_after_submission_classification():
    document = campaign(actions=[{
        "opportunity": "Fictional access fund", "task": "Check whether the funder received the application",
        "owner": "", "due": "2026-10-01", "status": "open",
    }, {
        "opportunity": "", "task": "Confirm the active campaign plan",
        "owner": "", "due": "", "status": "open",
    }])
    document["opportunities"][0]["status"] = "submitted"
    document["opportunities"].append({"name": "Separate active route", "status": "open"})

    report = campaigns.prepare(document)

    assert report["readiness"]["open_actions"] == 1
    assert report["readiness"]["actions_submission_phase_review"] == 1
    assert "Check whether the funder received the application" not in report["document_markdown"]
    assert "1 unfinished pre-submission action(s) on submitted route(s) need review" in report["document_markdown"]
    assert "Fictional access fund · Phase: Before submission" in report["markdown"]

    document["actions"][0]["submission_phase"] = "post_submission"
    report = campaigns.prepare(document)
    assert report["readiness"]["open_actions"] == 2
    assert "**Fictional access fund** — status entered: submitted" in report["document_markdown"]
    document["actions"][1]["status"] = "done"
    report = campaigns.prepare(document)
    assert "Check whether the funder received the application" in report["document_markdown"]
    assert "Scope: Fictional access fund (submitted route) · Phase: After-submission follow-up" in report["document_markdown"]


def test_reopened_route_holds_post_submission_actions_until_reclassified():
    document = campaign(actions=[{
        "opportunity": "Fictional access fund", "submission_phase": "post_submission",
        "task": "Check the previous submission", "owner": "", "due": "2026-10-14",
        "status": "open",
    }])
    document["opportunities"][0]["status"] = "open"

    report = campaigns.prepare(document)

    assert report["readiness"]["open_actions"] == 0
    assert report["readiness"]["actions_phase_reclassification"] == 1
    assert report["readiness"]["actions_to_classify"] == 1
    assert "1 post-submission action(s) on active route(s) need reclassification" in report["document_markdown"]
    assert "Check the previous submission" not in report["document_markdown"]


def test_invalid_action_submission_phase_is_rejected():
    document = campaign()
    document["actions"][0]["submission_phase"] = "whenever"
    with pytest.raises(ValueError, match="valid action submission phase"):
        campaigns.validate(document)


def test_inactive_route_actions_are_counted_as_held_and_kept_out_of_current_work():
    document = campaign(actions=[{
        "opportunity": "Fictional access fund", "task": "Submit the closed round",
        "owner": "", "due": "", "status": "open",
    }])
    document["opportunities"][0]["status"] = "closed"

    report = campaigns.prepare(document)

    assert report["readiness"]["open_actions"] == 0
    assert report["readiness"]["actions_without_owner"] == 0
    assert report["readiness"]["actions_inactive_route_review"] == 1
    assert report["readiness"]["actions_to_classify"] == 1
    assert "0 open actions" in report["document_markdown"]
    held = "1 open action(s) are held on closed, paused or not-pursued routes"
    assert held in report["document_markdown"]
    assert report["document_markdown"].count(
        held) == 1
    assert "No current open action is recorded. Review held tasks above" in report["document_markdown"]
    assert "Submit the closed round" not in report["document_markdown"]
    assert "Submit the closed round" in report["markdown"]


def test_closed_route_answer_drafts_are_clearly_archived_not_current_answers():
    document = campaign()
    document["opportunities"][0]["status"] = "closed"
    report = campaigns.prepare(document)
    markdown = report["markdown"]
    assert "### Historical answer drafts · inactive route" in markdown
    assert "are not for submission" in markdown
    assert "does not show whether anything was submitted" in markdown
    assert "1 historical answer row(s) retained; question labels and text omitted" in markdown
    assert "Project purpose" not in markdown
    assert "Provide shared swim equipment." not in markdown
    assert "### Application answers" not in markdown


def test_role_suggestions_are_not_counted_as_confirmed_action_owners():
    document = campaign(actions=[
        {"opportunity": "", "task": "Check the portal", "owner": "P&C Treasurer (unassigned)",
         "due": "", "status": "open"},
        {"opportunity": "", "task": "Request school confirmation", "owner": "",
         "due": "", "status": "open"},
    ])
    report = campaigns.prepare(document)
    assert report["readiness"]["actions_without_owner"] == 2
    assert "2 open actions have no user-confirmed owner" in report["markdown"]


def test_owner_needs_an_explicit_user_confirmation():
    document = campaign(actions=[{
        "opportunity": "", "task": "Confirm school approval", "owner": "P&C Treasurer",
        "owner_kind": "person",
        "due": "2026-10-02", "status": "open",
    }])
    report = campaigns.prepare(document)
    assert report["readiness"]["actions_without_owner"] == 1
    assert "Named person: P&amp;C Treasurer; acceptance unconfirmed" in report["markdown"]
    assert "Proposed target: 2026-10-02 · proposed target, not confirmed" in report["markdown"]
    assert "Proposed date: 2 Oct 2026 (proposed, not confirmed)" in report["document_markdown"]
    assert "Named person: P&amp;C Treasurer; acceptance unconfirmed" in report["document_markdown"]

    document["actions"][0]["owner_confirmed"] = True
    report = campaigns.prepare(document)
    assert report["readiness"]["actions_without_owner"] == 0
    assert "Named person: P&amp;C Treasurer; user-marked accepted, not independently verified" in report["markdown"]
    assert "Named person: P&amp;C Treasurer; user-marked accepted, not independently verified" in report["document_markdown"]


def test_action_owner_type_is_explicit_validated_and_migrated_conservatively():
    document = campaign(actions=[{
        "opportunity": "", "task": "Confirm who can apply", "owner": "Treasurer",
        "owner_kind": "role", "owner_confirmed": False, "due": "", "status": "open",
    }])
    validated = campaigns.validate(document)
    assert validated["actions"][0]["owner_kind"] == "role"
    report = campaigns.prepare(document)
    assert report["readiness"]["actions_without_owner"] == 1
    assert "Suggested role only; no person named" in report["document_markdown"]

    document["actions"][0]["owner_confirmed"] = True
    with pytest.raises(ValueError, match="named person's agreement"):
        campaigns.validate(document)

    legacy = campaign(actions=[{
        "opportunity": "", "task": "Confirm who can apply", "owner": "Treasurer",
        "owner_confirmed": False, "due": "", "status": "open",
    }])
    assert campaigns.validate(legacy)["actions"][0]["owner_kind"] == "unknown"

    ambiguous_legacy = campaign(actions=[{
        "opportunity": "", "task": "Confirm who can apply", "owner": "Casey",
        "owner_confirmed": True, "due": "", "status": "open",
    }])
    migrated_ambiguous = campaigns.validate(ambiguous_legacy)["actions"][0]
    assert migrated_ambiguous["owner_kind"] == "unknown"
    assert migrated_ambiguous["owner_confirmed"] is False

    marked_unknown = campaign(actions=[{
        "opportunity": "", "task": "Confirm who can apply",
        "owner": "Treasurer (suggested)", "owner_kind": "unknown",
        "owner_confirmed": False, "due": "", "status": "open",
    }])
    assert campaigns.validate(marked_unknown)["actions"][0]["owner_kind"] == "role"
    marked_person = copy.deepcopy(marked_unknown)
    marked_person["actions"][0]["owner_kind"] = "person"
    with pytest.raises(ValueError, match="suggested role"):
        campaigns.validate(marked_person)

    accepted_role_legacy = campaign(actions=[{
        "opportunity": "", "task": "Confirm who can apply",
        "owner": "Treasurer (suggested)", "owner_confirmed": True,
        "due": "", "status": "open",
    }])
    migrated_role = campaigns.validate(accepted_role_legacy)["actions"][0]
    assert migrated_role["owner_kind"] == "role"
    assert migrated_role["owner_confirmed"] is False


def test_action_brief_does_not_claim_acceptance_without_a_named_person():
    document = campaign(actions=[{
        "opportunity": "Fictional access fund", "task": "Get the school approval",
        "owner": "", "due": "", "status": "open",
    }])
    report = campaigns.prepare(document)
    assert "Owner: No person named; owner needed" in report["document_markdown"]
    assert "acceptance unconfirmed" not in report["document_markdown"]

    document["actions"][0]["owner"] = "P&C Treasurer (suggested)"
    report = campaigns.prepare(document)
    assert ("Suggested role only; no person named (P&amp;C Treasurer)"
            in report["document_markdown"])
    assert "P&amp;C Treasurer (suggested) (suggested role" not in report["document_markdown"]
    assert "acceptance unconfirmed" not in report["document_markdown"]


def test_decision_brief_surfaces_next_action_before_the_portfolio_register():
    report = campaigns.prepare(campaign(
        actions=[{"opportunity": "Fictional access fund",
                  "task": "Confirm the match against the current funder rules",
                  "owner": "", "due": "2026-10-02", "status": "open"}],
        assets=[{"name": "Sinter"}],
    ))
    brief = report["document_markdown"]
    assert brief.index("## Next recorded open action") < brief.index(
        "## Portfolio IP workstream")
    assert "Confirm the match against the current funder rules" in brief


def test_owner_confirmation_rejects_unassigned_or_non_boolean_values():
    document = campaign(actions=[{
        "task": "Confirm school approval", "owner": "Unassigned",
        "owner_kind": "unassigned", "owner_confirmed": True,
        "due": "", "status": "open",
    }])
    with pytest.raises(ValueError, match="named person's agreement"):
        campaigns.prepare(document)
    document["actions"][0].update(owner="Alex", owner_confirmed="yes")
    with pytest.raises(ValueError, match="true or false"):
        campaigns.prepare(document)
    document["actions"][0].update(owner="Treasurer", owner_kind="role",
                                  owner_confirmed=True)
    with pytest.raises(ValueError, match="named person's agreement"):
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
    assert "Quoted subtotal: A$25.00" in markdown
    assert "### Historical budget items · inactive routes" in markdown
    assert "These costs belong to closed, submitted, paused or not-pursued routes." in markdown
    assert "Historical quoted subtotal (excluded above): A$250.00" in markdown
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
    document["opportunities"][0].update(
        application_mode="required", applicant="Banksia Volunteers",
        applicant_confirmed=True)
    document["answers"][0]["text"] = "First line\nSecond\tpart\rFinal line"
    report = campaigns.prepare(document)
    assert report["campaign"]["answers"][0]["text"] == document["answers"][0]["text"]


def test_benign_markdown_and_html_stay_literal_and_links_remain_portable():
    document = campaign(title="<img src=x> [Campaign](javascript:alert(1))")
    document["opportunities"][0].update(
        application_mode="required", applicant="Banksia Volunteers",
        applicant_confirmed=True)
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


def test_store_reopens_legacy_role_suggestion_with_stale_acceptance_flag(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(campaign())
    legacy = copy.deepcopy(saved["document"])
    action = legacy["actions"][0]
    action.update(owner="Treasurer (suggested)", owner_confirmed=True)
    action.pop("owner_kind")
    with store._connect() as db:
        db.execute("UPDATE campaigns SET document=? WHERE id=?",
                   (json.dumps(legacy), saved["id"]))

    reopened = store.get(saved["id"])
    migrated = reopened["document"]["actions"][0]
    assert migrated["owner"] == "Treasurer (suggested)"
    assert migrated["owner_kind"] == "role"
    assert migrated["owner_confirmed"] is False


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
