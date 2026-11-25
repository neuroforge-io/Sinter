# SPDX-License-Identifier: Apache-2.0
"""Sinter sends verified transcript corrections to the ERAIS ledger."""
from __future__ import annotations

import pytest

from sinter import comprehension_bridge, meetings
from sinter.experience_feedback import (
    ENV,
    EraisExperienceFeedback,
    ExperienceFeedbackError,
    from_environment,
)


def test_feedback_posts_one_correction_and_returns_receipt():
    calls = []

    def request(path, *, method="GET", payload=None):
        calls.append((path, method, payload))
        return {"receipt": {"receipt_id": "X1", "schema":
                            "erais.application.experience-receipt.v1"}}

    receipt = EraisExperienceFeedback(request).record(
        {"segment_id": "S1", "original": "fifteen units",
         "replacement": "fifty units", "reason": "misheard amount"},
        scope_id="meeting-1", source_revision="sinter-rev")
    assert receipt["receipt_id"] == "X1"
    path, method, payload = calls[0]
    assert path == comprehension_bridge.EXPERIENCE
    assert method == "POST"
    assert payload["category"] == "recognition"
    assert payload["learning_scope"] == "organization"
    assert payload["scope_id"] == "meeting-1"
    assert payload["correction_id"].startswith("sinter:")


def test_feedback_rejects_a_missing_receipt():
    with pytest.raises(ExperienceFeedbackError):
        EraisExperienceFeedback(lambda *args, **kwargs: {}).record(
            {"segment_id": "S1", "original": "a", "replacement": "b"},
            scope_id="meeting-1")


def test_environment_selection(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert from_environment() is None
    monkeypatch.setenv(ENV, "disabled")
    assert from_environment() is None
    monkeypatch.setenv(ENV, "erais")
    assert isinstance(from_environment(), EraisExperienceFeedback)
    monkeypatch.setenv(ENV, "other")
    with pytest.raises(ExperienceFeedbackError):
        from_environment()


def test_minutes_records_reviewed_correction(monkeypatch):
    class Fake:
        def record(self, correction, *, scope_id, source_revision):
            assert correction["original"] == "The valve is damaged."
            assert scope_id.startswith("meeting:")
            return {"receipt_id": "X1", "failure_category": "recognition"}

    monkeypatch.setattr(
        meetings, "experience_from_environment", lambda: Fake())
    result = meetings.minutes(
        "Fictional committee",
        "Alex: The valve is damaged.\nSam: Agreed.\n",
        corrections=[{
            "segment_id": "T0001",
            "original": "The valve is damaged.",
            "replacement": "The valve is repaired.",
            "reason": "Inspection shows the valve repaired.",
        }])
    assert result["experience_receipts"][0]["receipt_id"] == "X1"
