"""Campaign correspondence stays explicit, bounded and user-entered."""
import json
import sqlite3

import pytest

from sinter import campaigns


def base_campaign(**changes):
    document = {
        "schema": "sinter-campaign/v1",
        "title": "Fictional community project",
        "organisation": "Fictional Community Association",
        "objective": "Confirm a fictional community project.",
        "opportunities": [{
            "name": "Example funding route", "funder": "Example Trust",
            "url": "https://example.invalid/funding", "deadline": "",
            "decision_window": "", "ceiling": None, "fit": "",
            "status": "open",
        }],
        "requirements": [], "answers": [], "budget": [], "actions": [],
        "sources": [],
    }
    document.update(changes)
    return document


def incoming(**changes):
    row = {
        "opportunity": "Example funding route", "date": "2026-09-28",
        "direction": "incoming", "status": "received", "channel": "email",
        "counterparty": "Example Trust", "subject": "Eligibility question",
        "content": "The fictional applicant may request a current application pack.",
        "evidence_links": [{
            "title": "Email record", "url": "https://example.invalid/mail/123",
            "notes": "Copied from the fictional test mailbox.",
            "source_id": "", "checked_at": "",
        }],
    }
    row.update(changes)
    return row


def test_old_v1_documents_receive_an_empty_communications_collection():
    normalized = campaigns.validate({
        "schema": "sinter-campaign/v1", "title": "Old campaign",
    })
    assert normalized["communications"] == []
    assert normalized["sources"] == []


def test_communications_normalize_and_preserve_incoming_and_outgoing_records():
    draft = {
        "opportunity": "", "date": "", "direction": "outgoing",
        "status": "draft", "channel": "letter", "counterparty": "Example Trust",
        "subject": "Ask for the current round dates",
        "content": "Could you confirm the application dates?",
        "evidence_links": [],
    }
    normalized = campaigns.validate(base_campaign(communications=[incoming(), draft]))
    assert normalized["communications"] == [incoming(), draft]
    report = campaigns.prepare(normalized)
    assert "RECORDED AS RECEIVED · UNVERIFIED" in report["markdown"]
    assert "DRAFT · NOT SENT" in report["markdown"]
    assert "user-entered, unverified" in report["markdown"]
    assert "Communication date (user-entered): 2026-09-28" in report["markdown"]
    assert "Communication date (user-entered): Not recorded" in report["markdown"]
    assert ("Sinter did not send, receive, open or independently verify"
            in report["markdown"])


@pytest.mark.parametrize(("direction", "status"), [
    ("incoming", "draft"), ("incoming", "sent"),
    ("outgoing", "received"),
])
def test_communication_status_must_match_direction(direction, status):
    with pytest.raises(ValueError, match="communication can only be marked"):
        campaigns.validate(base_campaign(communications=[
            incoming(direction=direction, status=status),
        ]))


@pytest.mark.parametrize(("changes", "message"), [
    ({"date": "2026-09-31"}, "YYYY-MM-DD"),
    ({"direction": "internal"}, "communication direction"),
    ({"channel": "social"}, "communication channel"),
    ({"opportunity": "Different route"}, "opportunity reference"),
    ({"evidence_links": [{"title": "Private", "url": "javascript:alert(1)"}]},
     "Communication evidence URL"),
    ({"evidence_links": [{"unexpected": "field"}]}, "unsupported fields"),
])
def test_communication_fields_reject_invalid_values(changes, message):
    with pytest.raises(ValueError, match=message):
        campaigns.validate(base_campaign(communications=[incoming(**changes)]))


def test_communications_and_evidence_links_are_bounded():
    with pytest.raises(ValueError, match="at most 10 evidence links"):
        campaigns.validate(base_campaign(communications=[incoming(
            evidence_links=[{"title": "Evidence"}] * 11,
        )]))
    with pytest.raises(ValueError, match="at most 200 communications"):
        campaigns.validate(base_campaign(communications=[{}] * 201))
    with pytest.raises(ValueError, match="Communication content"):
        campaigns.validate(base_campaign(
            communications=[incoming(content="x" * 20001)]))
    with pytest.raises(ValueError, match="200,000 text characters"):
        campaigns.validate(base_campaign(communications=[incoming(
            evidence_links=[{"title": "Evidence", "notes": "x" * 2000}
                            for _ in range(10)],
        ) for _ in range(11)]))


def test_communications_appear_in_internal_audit_but_not_decision_brief():
    message = "FullFictionalCommunicationContent7A91"
    report = campaigns.prepare(base_campaign(communications=[incoming(
        subject="SUBJECT_ONLY_FOR_AUDIT", content=message,
    )]))
    assert message in report["markdown"]
    assert "https://example.invalid/mail/123" in report["markdown"]
    assert "Email record" in report["markdown"]
    assert message not in report["document_markdown"]
    assert "SUBJECT_ONLY_FOR_AUDIT" not in report["document_markdown"]
    assert "example.invalid/mail/123" not in report["document_markdown"]


def test_legacy_sqlite_campaign_reads_with_empty_communications_and_can_be_updated(
        tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    old_document = {"schema": "sinter-campaign/v1", "title": "Legacy local campaign"}
    identity = "a" * 32
    with sqlite3.connect(store.path) as db:
        db.execute("INSERT INTO campaigns VALUES (?,?,?,?,?)", (
            identity, 3, old_document["title"], "2026-09-20T00:00:00Z",
            json.dumps(old_document),
        ))
    opened = store.get(identity)
    assert opened["revision"] == 3
    assert opened["document"]["communications"] == []
    updated = store.save({**opened["document"],
                          "communications": [incoming(opportunity="")]},
                         identity, opened["revision"])
    reopened = campaigns.CampaignStore(tmp_path).get(identity)
    assert reopened == updated
    assert reopened["document"]["communications"] == [incoming(opportunity="")]
