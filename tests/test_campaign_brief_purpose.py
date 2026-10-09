"""Explicit campaign discussion/research scope changes prose, never evidence or authority."""

import copy
import io
import json
import zipfile
from dataclasses import asdict
from xml.etree import ElementTree as ET

import pytest

from sinter import briefs, client, evidence, workbench
from sinter.docx_export import W, export_docx
from sinter.store import Store


OPENINGS = {
    "discussion": (
        "We would appreciate clarification on the points below before deciding on "
        "a next step for this discussion."
    ),
    "research": (
        "We would appreciate clarification on the points below to help us check "
        "the research question and its scope."
    ),
}
STAMP = "2026-10-09T00:00:00Z"


def project(**changes):
    return {
        "workflow": "brief", "document_type": "enquiry",
        "title": "Clarification: Fictional evidence review",
        "recipient": "Example reviewer", "organisation": "Example community group",
        "campaign_sender_review": True,
        "notes": "INTERNAL: review assumptions are unresolved. Never infer approval.",
        "questions": "Which evidence review scope should we agree?\nWhat data may be shared?",
        "query": "evidence review scope", "use_search": False, "use_model": False,
        "sources": [{"title": "Fictional review note",
                     "content": "The evidence review scope is proposed. Data transfer is NOT approved. Café 🐝.",
                     "url": "https://example.invalid/review", "retrieved_at": STAMP}],
        **changes,
    }


@pytest.fixture(autouse=True)
def no_hosted_requests(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unexpected hosted request")

    monkeypatch.setattr(client, "chat", forbidden)
    monkeypatch.setattr(client, "search", forbidden)
    monkeypatch.setattr(workbench, "utc_now", lambda: STAMP)
    monkeypatch.setattr(evidence, "utc_now", lambda: STAMP)


@pytest.mark.parametrize("purpose", OPENINGS)
def test_scoped_enquiry_uses_exact_opening_and_retains_identity_gates(purpose):
    payload = project(campaign_route_purpose=purpose)
    before = copy.deepcopy(payload)
    sources = evidence.collect(payload["sources"], payload["notes"])
    prepared = briefs.prepare_document(payload, sources)
    report = workbench.run(payload)
    document = report["document_markdown"]

    assert document == prepared["document_markdown"]
    assert OPENINGS[purpose] in document
    assert "this programme could support" not in document
    assert "I am writing on behalf of" not in document
    assert "INTERNAL:" not in document and "Never infer approval" not in document
    assert "Kind regards," not in document
    assert report["review_status"] == "draft" and report["document_ready"] is False
    assert {row["field"] for row in report["missing_fields"]} == {
        "signatory", "contact_details",
    }
    assert report["campaign_route_purpose"] == purpose
    assert report["document_questions"] == payload["questions"].splitlines()
    assert report["sources"] == [asdict(item) for item in sources]
    assert document in report["markdown"] and "NOT approved" in report["markdown"]
    assert payload == before


@pytest.mark.parametrize("purpose", OPENINGS)
def test_explicit_signoff_and_question_only_scope_are_retained(purpose):
    payload = project(campaign_route_purpose=purpose, notes="", sources=[],
                      signatory="Alex Example", sender_role="Recorded reviewer",
                      contact_details="alex@example.invalid")
    report = workbench.run(payload)
    document = report["document_markdown"]
    assert OPENINGS[purpose] in document
    assert "Alex Example\nRecorded reviewer\nExample community group\nalex@example.invalid" in document
    assert report["document_ready"] is True and report["missing_fields"] == []
    assert report["sources"] == [] and report["excerpts"] == []
    assert report["campaign_route_purpose"] == purpose


@pytest.mark.parametrize("organisation", ["", "Example community group"])
def test_absent_scope_keeps_exact_legacy_campaign_document_and_shape(organisation):
    payload = project(organisation=organisation)
    report = workbench.run(payload)
    opener = (
        f"{organisation} is assessing whether this programme could support a defined project. "
        if organisation else "We are assessing whether this programme could support a defined project. "
    ) + "We would appreciate guidance before deciding whether to proceed."
    assert report["document_markdown"] == "\n\n".join([
        "Dear Example reviewer,", "Re: Fictional evidence review", opener,
        "Could you please clarify the following?",
        "1. Which evidence review scope should we agree?\n2. What data may be shared?",
        "Please include any relevant details or links in your response.",
        "Thank you for your help.",
    ])
    assert "campaign_route_purpose" not in report
    assert "campaign_route_purpose" not in briefs.prepare_document(payload, [])


@pytest.mark.parametrize("value", [None, "", "unknown", "application", "Discussion", "discussion ", True, 1, [], {}])
def test_invalid_explicit_purpose_is_rejected_by_both_entry_points(value):
    payload = project(campaign_route_purpose=value, use_search=True, use_model=True)
    with pytest.raises(ValueError, match="purpose must be discussion or research"):
        workbench.run(payload)
    with pytest.raises(ValueError, match="purpose must be discussion or research"):
        briefs.prepare_document(payload, [])


@pytest.mark.parametrize("changes", [
    {"workflow": "research"}, {"workflow": "grants"}, {"workflow": "meeting"},
    {"campaign_sender_review": False}, {"campaign_sender_review": None},
])
def test_explicit_scope_requires_a_campaign_brief_before_hosted_processing(changes):
    payload = project(campaign_route_purpose="discussion", use_search=True,
                      use_model=True, **changes)
    with pytest.raises(ValueError):
        workbench.run(payload)
    with pytest.raises(ValueError, match="requires a brief with campaign sender review"):
        briefs.prepare_document(payload, [])


def test_missing_campaign_review_is_not_inferred_and_default_brief_is_allowed():
    payload = project(campaign_route_purpose="research")
    del payload["campaign_sender_review"]
    with pytest.raises(ValueError, match="requires a brief with campaign sender review"):
        workbench.run(payload)
    with pytest.raises(ValueError, match="requires a brief with campaign sender review"):
        briefs.prepare_document(payload, [])
    payload["campaign_sender_review"] = True
    del payload["workflow"]
    assert workbench.run(payload)["campaign_route_purpose"] == "research"


@pytest.mark.parametrize("kind", ["briefing", "agenda"])
@pytest.mark.parametrize("purpose", OPENINGS)
def test_other_brief_formats_retain_explicit_scope_without_changing_content(kind, purpose):
    base = project(document_type=kind)
    legacy = workbench.run(base)
    scoped = workbench.run({**base, "campaign_route_purpose": purpose})
    assert scoped.pop("campaign_route_purpose") == purpose
    assert scoped == legacy


@pytest.mark.parametrize("purpose", OPENINGS)
def test_optional_ranking_keeps_exact_declared_inputs_and_canonical_document(purpose, monkeypatch):
    payload = project(campaign_route_purpose=purpose, signatory="Alex Example",
                      contact_details="alex@example.invalid")
    before = copy.deepcopy(payload)
    local = workbench.run(payload)
    requests = []

    def rank(messages, **kwargs):
        transmitted = json.loads(messages[1].content)
        requests.append((messages, transmitted, kwargs))
        return client.ChatResult(json.dumps({
            "evidence_ids": [row["id"] for row in reversed(transmitted["excerpts"])],
        }), finish_reason="stop")

    monkeypatch.setattr(client, "chat", rank)
    ranked_payload = {**payload, "use_model": True}
    ranked_before = copy.deepcopy(ranked_payload)
    ranked = workbench.run(ranked_payload)
    assert len(requests) == 1
    messages, transmitted, options = requests[0]
    assert transmitted["question"] == (
        payload["title"] + " " + payload["query"] + " " + payload["questions"]
    )[:1000]
    assert transmitted["excerpts"] == local["excerpts"][:6]
    assert options == {"max_tokens": 256}
    assert "Do not write prose" in messages[0].content
    assert "alex@example.invalid" not in messages[1].content
    assert ranked["document_markdown"] == local["document_markdown"]
    assert ranked["document_details"] == local["document_details"]
    assert ranked["sources"] == local["sources"]
    assert {row["id"] for row in ranked["excerpts"]} == {row["id"] for row in local["excerpts"]}
    assert ranked["campaign_route_purpose"] == purpose
    assert payload == before and ranked_payload == ranked_before


@pytest.mark.parametrize("purpose", OPENINGS)
def test_local_report_reopen_json_and_word_export_keep_canonical_scoped_document(purpose, tmp_path):
    payload = project(campaign_route_purpose=purpose)
    report = workbench.run(payload)
    report["input_snapshot"] = copy.deepcopy(payload)
    store = Store(tmp_path / "fictional-workspace")
    identifier = store.save_report(report)
    reopened = Store(store.directory).report(identifier)
    exported = json.loads(json.dumps(reopened, ensure_ascii=False))
    assert reopened == report and exported == report
    assert exported["campaign_route_purpose"] == purpose
    assert exported["input_snapshot"] == payload
    word = export_docx({"title": report["document_title"],
                        "markdown": report["document_markdown"]})
    with zipfile.ZipFile(io.BytesIO(word.content)) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    text = "".join(node.text or "" for node in document.iter(f"{{{W}}}t"))
    assert OPENINGS[purpose] in text and "this programme could support" not in text
    assert "INTERNAL:" not in text
