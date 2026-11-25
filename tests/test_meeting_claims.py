# SPDX-License-Identifier: Apache-2.0
"""Meeting claims separate a stated assertion from an established fact."""
from __future__ import annotations

import pytest

from sinter import workbench
from sinter.meetings import minutes


NOTES = ("Alex: The motion was carried; the committee approved $500 for repairs.\n"
         "Sam: I will obtain the written quote by next Monday.\n"
         "Alex: The treasurer was absent.")


def _records(result):
    return {(row["claim_type"], row["source_passage_id"]): row
            for row in result["claims"]}


def test_claims_are_stated_and_unconfirmed_by_default():
    result = minutes("Fictional committee", NOTES)
    records = _records(result)
    motion = records[("motion", "T0001")]
    assert motion["assertion_status"] == "stated"
    assert motion["evidence_status"] == "transcript_only"
    assert motion["confirmation_status"] == "unconfirmed"
    assert motion["claim_status"] == "current"
    assert motion["reinterpretation_required"] is False
    assert records[("action", "T0002")]["source_speaker"] == "Sam"
    assert ("due_date", "T0002") in records
    assert ("attendance", "T0003") in records
    assert "not evidence that the asserted state" in result["markdown"]


def test_outcome_reversal_marks_dependent_claim_stale():
    change = {
        "segment_id": "T0001",
        "original": "The motion was carried; the committee approved $500 for repairs.",
        "replacement": "The motion was not carried; the committee approved $500 for repairs.",
        "reason": "Recording confirms the motion was not carried.",
    }
    result = minutes("Fictional committee", NOTES, corrections=[change])
    motion = _records(result)[("motion", "T0001")]
    assert motion["claim_status"] == "stale"
    assert motion["reinterpretation_required"] is True
    assert motion["transcript_revision"]["replacement"].startswith(
        "The motion was not carried")
    assert "Claims invalidated by transcript revision" in result["markdown"]


def test_amount_change_marks_financial_claim_stale():
    change = {
        "segment_id": "T0001",
        "original": "The motion was carried; the committee approved $500 for repairs.",
        "replacement": "The motion was carried; the committee approved $350 for repairs.",
        "reason": "Operator corrected the approved amount.",
    }
    result = minutes("Fictional committee", NOTES, corrections=[change])
    financial = _records(result)[("financial", "T0001")]
    assert financial["claim_status"] == "stale"
    assert financial["reinterpretation_required"] is True
    assert "350" in financial["transcript_revision"]["replacement"]


def test_wording_only_correction_keeps_claim_current_but_records_revision():
    change = {
        "segment_id": "T0002",
        "original": "I will obtain the written quote by next Monday.",
        "replacement": "I will obtain the signed quote by next Monday.",
        "reason": "Speaker confirmed the quote must be signed.",
    }
    result = minutes("Fictional committee", NOTES, corrections=[change])
    action = _records(result)[("action", "T0002")]
    assert action["claim_status"] == "current"
    assert action["reinterpretation_required"] is False
    assert action["transcript_revision"]["replacement"].startswith(
        "I will obtain the signed")


def test_workbench_meeting_projection_keeps_claims():
    report = workbench.run({
        "workflow": "meeting", "title": "Fictional meeting", "notes": NOTES})
    assert report["claims"]
    assert all(row["confirmation_status"] == "unconfirmed"
               for row in report["claims"])


def test_claim_requires_an_explicit_keyword():
    result = minutes("Fictional meeting", "Alex: The room is blue.")
    assert result["claims"] == []
