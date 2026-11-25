# SPDX-License-Identifier: Apache-2.0
"""Cross-passage organizational events, not keyword-only claims."""
from __future__ import annotations

from sinter.meetings import minutes

NOTES = (
    "Alex: We should allocate $600 for the replacement equipment.\n"
    "Sam: Can we make that $450 instead?\n"
    "Alex: Yes, that works.\n"
    "Chris: I'll organize the purchase before Friday.\n"
)


def _claims(result):
    return {(row["claim_type"], row["source_passage_id"]): row
            for row in result["claims"]}


def test_motion_amendment_acceptance_and_responsibility_compose():
    result = minutes("Fictional committee", NOTES)
    assert len(result["motions"]) == 1
    motion = result["motions"][0]
    amounts = [row["amount"]["raw"] for row in motion["amount_history"]]
    assert amounts == ["$600", "$450"]
    assert motion["acceptance"] == "stated_agreement"
    assert motion["acceptance"] != "approved"
    assert len(motion["responsibility_ids"]) == 1
    assert motion["related_event_ids"]
    events = {event["event_type"]: event for event in result["organizational_events"]}
    assert events["amendment"]["motion_id"] == motion["event_id"]
    assert events["acceptance"]["motion_id"] == motion["event_id"]
    responsibility = events["responsibility"]
    assert responsibility["motion_id"] == motion["event_id"]
    assert responsibility["due_date"] == "Friday"
    claims = _claims(result)
    assert claims[("motion", "T0001")]["semantic_event"]["amount"]["raw"] == "$600"
    assert claims[("motion_amendment", "T0002")]["semantic_event"]["amount"]["raw"] == "$450"
    assert claims[("decision", "T0003")]["semantic_event"]["acceptance_status"] == "stated_agreement"
    assert claims[("action", "T0004")]["semantic_event"]["action"].startswith("organize")
    assert claims[("due_date", "T0004")]["semantic_event"]["due_date"] == "Friday"


def test_changed_responsibility_invalidates_action_and_deadline_only():
    change = {
        "segment_id": "T0004",
        "original": "I'll organize the purchase before Friday.",
        "replacement": "Michael will organize the purchase before Friday.",
        "reason": "Recording confirms Michael accepted the action.",
    }
    result = minutes("Fictional committee", NOTES, corrections=[change])
    claims = _claims(result)
    assert claims[("action", "T0004")]["claim_status"] == "stale"
    assert claims[("due_date", "T0004")]["claim_status"] == "stale"
    assert claims[("motion", "T0001")]["claim_status"] == "current"
    revision = claims[("action", "T0004")]["semantic_revision"]
    assert revision["actor"]["original"] == "Chris"
    assert revision["actor"]["corrected"] == "Michael"
    assert claims[("action", "T0004")]["transcript_revision"]["replacement"].startswith(
        "Michael will organize")


def test_amendment_amount_change_invalidates_the_motion_chain_and_budget():
    change = {
        "segment_id": "T0002",
        "original": "Can we make that $450 instead?",
        "replacement": "Can we make that $300 instead?",
        "reason": "Recording confirms the amendment was $300.",
    }
    result = minutes("Fictional committee", NOTES, corrections=[change])
    claims = _claims(result)
    assert claims[("motion", "T0001")]["claim_status"] == "stale"
    assert claims[("motion_amendment", "T0002")]["claim_status"] == "stale"
    assert claims[("motion_amendment", "T0002")]["semantic_revision"]["amount"] == {
        "original": {"raw": "$450", "value": 450.0, "currency": "USD"},
        "corrected": {"raw": "$300", "value": 300.0, "currency": "USD"},
    }
    assert claims[("financial", "T0002")]["claim_status"] == "stale"
    assert claims[("decision", "T0003")]["claim_status"] == "current"


def test_acceptance_correction_removes_agreement_without_faking_approval():
    change = {
        "segment_id": "T0003",
        "original": "Yes, that works.",
        "replacement": "We discussed it but did not agree.",
        "reason": "The agreement was not reached.",
    }
    result = minutes("Fictional committee", NOTES, corrections=[change])
    claims = _claims(result)
    assert result["motions"][0]["acceptance"] is None
    assert claims[("motion", "T0001")]["claim_status"] == "stale"
    assert claims[("motion", "T0001")]["semantic_revision"]["acceptance"]
    assert claims[("discussion", "T0003")]["claim_status"] == "stale"
    assert claims[("financial", "T0001")]["claim_status"] == "current"


def test_cross_passage_event_without_keyword_claim_language():
    notes = (
        "Alex: I propose we spend $600 on equipment.\n"
        "Sam: Can we change that to $450?\n"
        "Alex: Agreed.\n"
    )
    result = minutes("Fictional committee", notes)
    motion = result["motions"][0]
    assert [row["amount"]["raw"] for row in motion["amount_history"]] == [
        "$600", "$450"]
    assert motion["acceptance"] == "stated_agreement"
    assert any(
        claim["claim_type"] == "motion_amendment"
        for claim in result["claims"])


def test_injected_semantic_interpreter_drives_the_same_composition():
    from sinter.meeting_semantics import Passage, analyze

    def interpreter(passage):
        if passage.passage_id == "T0001":
            return [{
                "event_type": "motion", "actor": passage.speaker,
                "object": "equipment",
                "amount": {"raw": "$600", "value": 600.0,
                           "currency": "USD"},
                "evidence": passage.text,
            }]
        if passage.passage_id == "T0002":
            return [{
                "event_type": "amendment", "actor": passage.speaker,
                "amount": {"raw": "$450", "value": 450.0,
                           "currency": "USD"},
                "evidence": passage.text,
            }]
        return []

    result = analyze([
        Passage("T0001", "Alex", "unstructured wording"),
        Passage("T0002", "Sam", "unstructured wording"),
    ], interpreter=interpreter)
    motion = result["motions"][0]
    assert [row["amount"]["raw"] for row in motion["amount_history"]] == [
        "$600", "$450"]
    assert result["events"][1]["motion_id"] == motion["event_id"]
    assert any(claim["claim_type"] == "motion_amendment"
               for claim in result["claims"])
