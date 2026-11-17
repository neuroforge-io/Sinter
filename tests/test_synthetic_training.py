"""Verify the shipped fictional exercises without credentials or external I/O."""
import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest

from sinter import client
from sinter.evidence import Excerpt, Source, select, validate_excerpt
from sinter.workbench import run

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "synthetic-training"


@pytest.fixture(autouse=True)
def block_external_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Synthetic training must not use external I/O")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(client, "search", forbidden)
    monkeypatch.setattr(client, "chat", forbidden)


def payload(kind):
    return json.loads((EXAMPLES / f"{kind}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind", ["research", "grants", "brief", "meeting"])
def test_shipped_exercises_preserve_evidence_and_unknowns(kind):
    data = payload(kind)
    assert data["demo"] is True
    assert data["use_search"] is False and data["use_model"] is False
    result = run(data)
    assert result["review_status"] == "draft" and result["demo"] is True
    assert "Fictional example" in result["document_markdown"]
    sources = [Source(**row) for row in result["sources"]]
    for row in result["excerpts"]:
        excerpt = Excerpt(**row)
        assert validate_excerpt(excerpt, sources)
        assert not validate_excerpt(replace(excerpt, quote="Invented answer"), sources)
    if kind == "research":
        assert result["excerpts"]
        assert "No opening time has been agreed." in result["document_markdown"]
    elif kind == "grants":
        assert result["screening"]["checks"][0]["status"] == "unknown"
        assert result["screening"]["status"] == "review_required"
    elif kind == "brief":
        assert "No booking or spending has been approved." in (
            result["document_markdown"]
        )
        assert data["opening_paragraph"] in result["document_markdown"]
        assert "FICTIONAL TRAINING ONLY" not in result["document_markdown"]
        assert any(data["notes"] in source.content for source in sources)
        assert "What would the booking cost" in result["document_markdown"]
    else:
        assert result["segments"][0]["text"] == "We did approve the booking."
        assert result["corrections"][0]["replacement"] == (
            "We did not approve the booking."
        )
        assert result["corrections"][0]["reason"] == data["corrections"][0]["reason"]
        assert "We did not approve the booking." in result["document_markdown"]
        assert "No vote was taken today." in result["document_markdown"]


@pytest.mark.parametrize("reply", ["valid", "invented"])
def test_mock_assistance_can_only_rank_fictional_existing_excerpts(monkeypatch, reply):
    sources = [Source(**row) for row in run(payload("research"))["sources"]]
    chosen, _ = select(sources, "workshop entrance seating opening time")
    calls = []

    def synthetic_chat(messages, **kwargs):
        request = json.loads(messages[-1].content)
        calls.append(request)
        ids = [row["id"] for row in request["excerpts"]]
        answer = ids[::-1] if reply == "valid" else ["E-invented-source"]
        return client.ChatResult(
            json.dumps({"evidence_ids": answer}), finish_reason="stop"
        )

    monkeypatch.setattr(client, "chat", synthetic_chat)
    ranked, warnings = select(
        sources, "workshop entrance seating opening time", use_model=True
    )
    assert len(calls) == 1 and calls[0]["excerpts"]
    assert {row.id for row in ranked} == {row.id for row in chosen}
    assert all(validate_excerpt(row, sources) for row in ranked)
    if reply == "valid":
        assert ranked[0].id == calls[0]["excerpts"][-1]["id"]
    else:
        assert ranked == chosen
        assert any("generated prose was discarded" in warning for warning in warnings)
