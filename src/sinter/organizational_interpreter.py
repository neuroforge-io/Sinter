"""Sinter adapter for the ERAIS canonical organizational projection.

ERAIS owns the semantic interpretation. This adapter only forwards one reviewed
passage to the local comprehension service, validates the returned event
contract and returns it to Sinter's composition layer. Cross-passage motion
chains, revision comparison and review status remain in Sinter.
"""
from __future__ import annotations

import os
from typing import Callable

from . import comprehension_bridge
from .meeting_semantics import EVENT_SCHEMA, Passage

ENV = "SINTER_ORGANIZATIONAL_INTERPRETER"
MAX_EVENTS = 512
EVENT_TYPES = {
    "motion", "amendment", "acceptance", "responsibility", "budget",
    "due_date", "attendance", "question", "discussion",
}


class OrganizationalInterpreterError(ValueError):
    """The ERAIS organizational response is invalid."""


def _validate(events: object, passage: Passage) -> list[dict]:
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise OrganizationalInterpreterError(
            "The semantic interpreter returned an invalid event list.")
    result = []
    for event in events:
        if not isinstance(event, dict):
            raise OrganizationalInterpreterError(
                "The semantic interpreter returned a non-object event.")
        if event.get("schema", EVENT_SCHEMA) != EVENT_SCHEMA:
            raise OrganizationalInterpreterError(
                "The semantic interpreter returned a foreign event schema.")
        if event.get("event_type") not in EVENT_TYPES:
            raise OrganizationalInterpreterError(
                "The semantic interpreter returned an unknown event type.")
        source = event.get("source_passage_id")
        if source is not None and source != passage.passage_id:
            raise OrganizationalInterpreterError(
                "The semantic interpreter cited another passage.")
        evidence = event.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise OrganizationalInterpreterError(
                "The semantic interpreter returned an event without evidence.")
        result.append(dict(event))
    return result


class EraisOrganizationalInterpreter:
    """Call the local ERAIS organizational projection for one passage."""

    def __init__(self, request: Callable[..., dict] | None = None):
        self._request = request or comprehension_bridge.request

    def __call__(self, passage: Passage) -> list[dict]:
        if not isinstance(passage, Passage):
            raise OrganizationalInterpreterError("expected a meeting passage")
        response = self._request(
            comprehension_bridge.ORGANIZATIONAL,
            method="POST",
            payload={
                "passage_id": passage.passage_id,
                "speaker": passage.speaker,
                "text": passage.text,
                "start": passage.start,
                "end": passage.end,
            })
        if not isinstance(response, dict):
            raise OrganizationalInterpreterError(
                "The semantic interpreter returned an invalid response.")
        if response.get("schema") != EVENT_SCHEMA:
            raise OrganizationalInterpreterError(
                "The semantic interpreter returned a foreign response schema.")
        return _validate(response.get("events"), passage)


def from_environment() -> EraisOrganizationalInterpreter | None:
    """Return the ERAIS interpreter when explicitly selected."""
    selected = os.environ.get(ENV, "").strip().lower()
    if selected in {"", "deterministic", "bounded", "fallback"}:
        return None
    if selected in {"erais", "canonical", "semantic"}:
        return EraisOrganizationalInterpreter()
    raise OrganizationalInterpreterError(
        f"{ENV} must select erais or deterministic.")


__all__ = [
    "ENV",
    "EraisOrganizationalInterpreter",
    "OrganizationalInterpreterError",
    "from_environment",
]
