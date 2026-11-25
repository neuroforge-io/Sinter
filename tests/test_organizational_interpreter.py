# SPDX-License-Identifier: Apache-2.0
"""Sinter validates the ERAIS organizational projection before composition."""
from __future__ import annotations

import pytest

from sinter import comprehension_bridge
from sinter.meeting_semantics import EVENT_SCHEMA, Passage, analyze
from sinter.organizational_interpreter import (
    ENV,
    EraisOrganizationalInterpreter,
    OrganizationalInterpreterError,
    from_environment,
)


def _event(passage, event_type="motion", **fields):
    return {
        "schema": EVENT_SCHEMA,
        "event_type": event_type,
        "source_passage_id": passage.passage_id,
        "evidence": passage.text,
        "actor": passage.speaker,
        **fields,
    }


def test_adapter_forwards_one_passage_and_validates_the_event():
    calls = []

    def request(path, *, method="GET", payload=None):
        calls.append((path, method, payload))
        return {
            "schema": EVENT_SCHEMA,
            "events": [{
                "schema": EVENT_SCHEMA,
                "event_type": "motion",
                "source_passage_id": "T1",
                "evidence": "I propose we spend $600 on equipment.",
                "actor": "Alex",
                "object": "equipment",
                "amount": {"raw": "$600", "value": 600.0,
                           "currency": "USD"},
            }],
        }

    passage = Passage("T1", "Alex",
                      "I propose we spend $600 on equipment.")
    events = EraisOrganizationalInterpreter(request)(passage)
    assert calls == [(
        comprehension_bridge.ORGANIZATIONAL, "POST",
        {"passage_id": "T1", "speaker": "Alex",
         "text": "I propose we spend $600 on equipment.",
         "start": None, "end": None})]
    assert events[0]["event_type"] == "motion"
    assert events[0]["actor"] == "Alex"


@pytest.mark.parametrize("payload", [
    {"schema": "other", "events": []},
    {"schema": EVENT_SCHEMA, "events": [{"event_type": "motion"}]},
    {"schema": EVENT_SCHEMA, "events": [{
        "schema": EVENT_SCHEMA, "event_type": "unknown",
        "evidence": "x"}]},
    {"schema": EVENT_SCHEMA, "events": [{
        "schema": EVENT_SCHEMA, "event_type": "motion",
        "source_passage_id": "T2", "evidence": "x"}]},
])
def test_adapter_rejects_invalid_projection(payload):
    def request(path, *, method="GET", payload=None):
        return payload

    with pytest.raises(OrganizationalInterpreterError):
        EraisOrganizationalInterpreter(request)(
            Passage("T1", "Alex", "I propose we spend $600."))


def test_environment_selection_is_explicit(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert from_environment() is None
    monkeypatch.setenv(ENV, "deterministic")
    assert from_environment() is None
    monkeypatch.setenv(ENV, "erais")
    assert isinstance(from_environment(), EraisOrganizationalInterpreter)
    monkeypatch.setenv(ENV, "other")
    with pytest.raises(OrganizationalInterpreterError):
        from_environment()


def test_projection_drives_sinter_motion_composition():
    def request(path, *, method="GET", payload=None):
        text = payload["text"]
        events = []
        if "propose" in text:
            events.append(_event(
                Passage(payload["passage_id"], payload["speaker"], text),
                "motion", object="equipment",
                amount={"raw": "$600", "value": 600.0,
                        "currency": "USD"}))
        elif "change" in text:
            events.append(_event(
                Passage(payload["passage_id"], payload["speaker"], text),
                "amendment",
                amount={"raw": "$450", "value": 450.0,
                        "currency": "USD"}))
        elif "Agreed" in text:
            events.append(_event(
                Passage(payload["passage_id"], payload["speaker"], text),
                "acceptance", acceptance_status="stated_agreement"))
        elif "order" in text:
            events.append(_event(
                Passage(payload["passage_id"], payload["speaker"], text),
                "responsibility", action="order the equipment",
                object="equipment", due_date="Friday"))
        return {"schema": EVENT_SCHEMA, "events": events}

    interpreter = EraisOrganizationalInterpreter(request)
    result = analyze([
        Passage("T1", "Alex", "I propose we spend $600 on equipment."),
        Passage("T2", "Sam", "Can we change that to $450?"),
        Passage("T3", "Alex", "Agreed."),
        Passage("T4", "Sam", "I will order the equipment by Friday."),
    ], interpreter=interpreter)
    motion = result["motions"][0]
    assert [row["amount"]["raw"] for row in motion["amount_history"]] == [
        "$600", "$450"]
    assert motion["acceptance"] == "stated_agreement"
    assert motion["responsibility_ids"]
    assert any(claim["claim_type"] == "motion_amendment"
               for claim in result["claims"])


def test_conditional_and_reported_acceptance_boundaries():
    # The composition layer must preserve conditional/reported status.
    def interpreter(passage):
        if passage.passage_id == "T1":
            return [{"event_type": "motion", "actor": "Alex",
                     "object": "equipment",
                     "amount": {"raw": "$690", "value": 690.0,
                                "currency": "USD"},
                     "evidence": passage.text}]
        if passage.passage_id == "T2":
            return [{"event_type": "acceptance", "actor": "Sam",
                     "acceptance_status": "conditional_stated_agreement",
                     "condition": "the finance committee approves it",
                     "evidence": passage.text}]
        if passage.passage_id == "T3":
            return [{"event_type": "motion", "actor": "Chair",
                     "outcome": "reported_carried",
                     "assertion_status": "reported",
                     "evidence": passage.text}]
        return []

    result = analyze([
        Passage("T1", "Alex", "proposal"),
        Passage("T2", "Sam", "conditional"),
        Passage("T3", "Chair", "reported"),
    ], interpreter=interpreter)
    conditional = next(
        motion for motion in result["motions"]
        if motion.get("acceptance") == "conditional_stated_agreement")
    assert conditional["acceptance_condition"]
    reported = next(
        motion for motion in result["motions"]
        if motion.get("acceptance") == "reported_outcome")
    assert reported["assertion_status"] == "reported"
