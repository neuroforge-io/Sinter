"""Recipient prose remains explicit, literal and separate from campaign evidence."""
import copy
from dataclasses import asdict, replace
import io
import json
import zipfile
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from sinter import briefs, casebooks, client, evidence, workbench
from sinter.document_markup import Paragraph, parse
from sinter.docx_export import W, export_docx
from sinter.evidence import literal_paragraph
from sinter.store import Store

FIXTURE = json.loads((Path(__file__).parent / "fixtures/literal_paragraph.v1.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unexpected hosted request")
    monkeypatch.setattr(client, "chat", forbidden)
    monkeypatch.setattr(client, "search", forbidden)


def project(**changes):
    return {"workflow": "brief", "title": "Fictional follow-up", "recipient": "Example team",
            "campaign_sender_review": True, "notes": "PRIVATE_NOTE_SENTINEL",
            "questions": "Please provide the current terms.", "use_search": False,
            "use_model": False, "sources": [{"title": "Original reply",
                "content": "PRIVATE_SOURCE_SENTINEL: terms remain unconfirmed."}], **changes}


@pytest.mark.parametrize("raw, encoded", FIXTURE["cases"])
def test_literal_paragraph_matches_shared_fixture_and_word_text(raw, encoded):
    assert literal_paragraph(raw) == encoded
    blocks = parse(encoded)
    assert len(blocks) == 1 and isinstance(blocks[0], Paragraph)
    block = blocks[0]
    assert not any([block.heading, block.quote, block.code, block.list_id])
    assert all(not any([span.bold, span.italic, span.code, span.href]) for span in block.spans)
    assert "".join(span.text for span in block.spans) == raw
    result = export_docx({"title": "Fictional plain paragraph", "markdown": encoded})
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    assert "".join(node.text or "" for node in document.iter(f"{{{W}}}t")) == raw


@pytest.mark.parametrize("purpose", [None, "discussion", "research"])
def test_enquiry_uses_entered_opening_once_without_private_evidence_or_status_change(purpose):
    opening = "I'm following up on our 2 October enquiry. Café é 🐝.\nNo submission is authorised."
    payload = project(opening_paragraph=opening,
                      **({"campaign_route_purpose": purpose} if purpose else {}))
    before = copy.deepcopy(payload)
    report = workbench.run(payload)
    document = report["document_markdown"]
    assert document.count(literal_paragraph(opening)) == 1
    assert "PRIVATE_NOTE_SENTINEL" not in document and "PRIVATE_SOURCE_SENTINEL" not in document
    assert "programme could support" not in document and "I am writing about" not in document
    assert report["document_opening"] == opening
    assert report["review_status"] == "draft" and not report["document_ready"]
    assert report["sources"][0]["content"] == payload["notes"]
    assert report["sources"][1]["content"].startswith("PRIVATE_SOURCE_SENTINEL")
    assert payload == before


@pytest.mark.parametrize("kind", ["enquiry", "briefing", "agenda"])
def test_explicit_paragraph_role_is_retained_for_each_brief_format(kind):
    payload = project(document_type=kind, opening_paragraph="Explicit fictional purpose or introduction.")
    result = workbench.run(payload)
    assert result["document_opening"] == payload["opening_paragraph"]
    assert result["document_markdown"].count(payload["opening_paragraph"]) == 1
    assert "PRIVATE_NOTE_SENTINEL" not in result["document_markdown"]
    assert "PRIVATE_SOURCE_SENTINEL" not in result["document_markdown"]
    if kind == "agenda":
        assert "## Purpose\n\n" + payload["opening_paragraph"] in result["document_markdown"]


@pytest.mark.parametrize("kind", ["enquiry", "briefing", "agenda"])
def test_private_questions_are_not_mined_from_campaign_notes_in_any_format(kind):
    payload = project(document_type=kind, questions="", notes="PRIVATE_NOTE: should we consult our lawyer?",
                      opening_paragraph="Please help us clarify the public terms.")
    before = copy.deepcopy(payload)
    result = workbench.run(payload)
    assert result["document_questions"] == []
    assert "consult our lawyer" not in result["document_markdown"]
    assert "PRIVATE_SOURCE_SENTINEL" not in result["document_markdown"]
    assert result["sources"][0]["content"] == payload["notes"]
    assert result["sources"][1]["content"] == payload["sources"][0]["content"]
    if kind == "enquiry":
        assert {"field": "questions", "label": "Questions you want answered"} in result["missing_fields"]
        assert not result["document_ready"]
    assert payload == before


@pytest.mark.parametrize("notes", [
    "InternalNotesSentinel: water analysis.\nShould we consult our lawyer?",
    "InternalNotesSentinel: water analysis. " * 100
    + "\nShould we consult our lawyer?",
    "InternalNotesSentinel: water 分析 🐝 e\u0301. " * 100
    + "\nShould we consult our lawyer?",
    "",
])
@pytest.mark.parametrize("questions", [
    "",
    "Please confirm the water access rules.\nWho may authorise access?",
])
def test_workbench_enquiry_keeps_preparation_evidence_out_of_recipient_prose(
    monkeypatch, notes, questions,
):
    monkeypatch.setattr(evidence, "utc_now", lambda: "2026-10-16T00:00:00+00:00")
    payload = project(
        campaign_sender_review=False,
        title="Fictional water enquiry",
        notes=notes,
        questions=questions,
        opening_paragraph="Please clarify the current public terms.",
        signatory="Example coordinator",
        contact_details="coordinator@example.invalid",
        sources=[{
            "title": "Water reference",
            "content": "ReferenceBodySentinel: water access remains unapproved.",
            "url": "https://example.invalid/water",
        }],
    )
    before = copy.deepcopy(payload)
    expected_sources = evidence.collect(payload["sources"], notes)

    report = workbench.run(payload)
    document = report["document_markdown"]

    assert "InternalNotesSentinel" not in document
    assert "ReferenceBodySentinel" not in document
    assert "consult our lawyer" not in document
    assert report["document_opening"] == payload["opening_paragraph"]
    assert report["document_questions"] == (
        questions.splitlines() if questions else []
    )
    assert report["sources"] == [asdict(item) for item in expected_sources]
    assert report["excerpts"]
    assert {item["source_id"] for item in report["excerpts"]} == {
        item.id for item in expected_sources
    }
    selected = [evidence.Excerpt(**item) for item in report["excerpts"]]
    assert all(
        evidence.validate_excerpt(item, expected_sources) for item in selected
    )
    assert evidence.render_evidence(selected, expected_sources) in report["markdown"]
    missing = {"field": "questions", "label": "Questions you want answered"}
    assert (missing in report["missing_fields"]) is (not bool(questions))
    assert report["document_ready"] is bool(questions)
    assert payload == before


def test_blank_uses_existing_document_and_missing_field_shape():
    legacy = workbench.run(project())
    blank = workbench.run(project(opening_paragraph=" \n"))
    assert blank.pop("document_opening") == " \n"
    # Timestamps may cross a second; the document and evidence decisions must not.
    for key in ["document_markdown", "missing_fields", "document_ready", "document_questions"]:
        assert blank[key] == legacy[key]
    assert "document_opening" not in legacy


@pytest.mark.parametrize("value", [None, 1, [], "x" * 1201, "🐝" * 1201, "bad\0text", "bad\ud800"])
def test_invalid_opening_is_rejected_before_optional_hosted_work_and_preserves_input(value):
    payload = project(opening_paragraph=value, use_search=True, use_model=True, query="fictional")
    before = copy.deepcopy(payload)
    with pytest.raises(ValueError, match="Opening paragraph"):
        workbench.run(payload)
    assert payload == before


def test_astral_boundary_and_unsupported_workflow_are_explicit():
    value = "🐝" * 1200
    assert briefs.document_opening(project(opening_paragraph=value)) == value
    with pytest.raises(ValueError, match="briefing documents only"):
        workbench.run(project(workflow="research", opening_paragraph="Retain this input."))


def test_shared_literal_browser_renderer_regression():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for browser renderer structure checks")
    result = subprocess.run([node, "--test", "tests/literal_paragraph.mjs", "tests/brief_opening.mjs"],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_saved_report_keeps_opening_original_document_and_later_edits_distinct(tmp_path):
    payload = project(opening_paragraph="Following up on the recorded enquiry. No decision confirmed.")
    report = workbench.run(payload)
    report["input_snapshot"] = copy.deepcopy(payload)
    original = report["document_markdown"]
    report["document_edits"] = {"markdown": original + "\n\nA later human correction.",
                                "author": "user", "edited_at": "2026-10-16T00:00:00Z"}
    store = Store(tmp_path / "fictional-workspace")
    identifier = store.save_report(report)
    reopened = Store(store.directory).report(identifier)
    exported = json.loads(json.dumps(reopened, ensure_ascii=False))
    assert exported == report
    assert exported["document_opening"] == payload["opening_paragraph"]
    assert exported["input_snapshot"] == payload
    assert exported["document_markdown"] == original
    assert exported["document_edits"]["markdown"] != original



def test_request_body_cannot_enable_source_passage_enquiry_context():
    payload = project(
        campaign_sender_review=False,
        notes="InternalNotesSentinel: do not publish this analysis.",
        sources=[{
            "title": "Reference",
            "content": "ReferenceBodySentinel: retained preparation evidence.",
        }],
        enquiry_context="source_passages",
    )
    before = copy.deepcopy(payload)

    report = workbench.run(payload)

    assert "InternalNotesSentinel" not in report["document_markdown"]
    assert "ReferenceBodySentinel" not in report["document_markdown"]
    assert report["document_questions"] == [payload["questions"]]
    assert payload == before


@pytest.mark.parametrize("kind", ["briefing", "agenda"])
def test_ordinary_internal_formats_keep_notes_and_question_extraction(kind):
    notes = "Should we consult the water coordinator?"
    payload = project(
        campaign_sender_review=False,
        document_type=kind,
        notes=notes,
        questions="",
        sources=[],
    )
    before = copy.deepcopy(payload)

    report = workbench.run(payload)

    assert report["document_questions"] == [notes]
    assert notes in report["document_markdown"]
    assert report["sources"][0]["content"] == notes
    assert payload == before


@pytest.mark.parametrize("policy", ["recipient_only", "source_passages"])
@pytest.mark.parametrize("position", [0, 2])
def test_both_enquiry_policies_reject_forged_selected_passages(policy, position):
    sources = [evidence.source(
        "Original reference",
        "First exact passage.\nSecond exact passage.\nThird exact passage.",
        kind="reference_excerpt",
        retrieved_at="2026-10-16T00:00:00+00:00",
    )]
    selected = evidence.excerpts(sources)
    selected[position] = replace(
        selected[position], quote=selected[position].quote + " Forged wording."
    )
    payload = project(campaign_sender_review=False, notes="", sources=[])
    before = copy.deepcopy(payload)
    selected_before = copy.deepcopy(selected)

    with pytest.raises(ValueError, match="document passage does not match"):
        briefs.prepare_document(
            payload, sources, selected, enquiry_context=policy
        )

    assert payload == before
    assert selected == selected_before


@pytest.mark.parametrize("policy", [
    None, True, "", "source_passages ", ["source_passages"],
])
def test_invalid_producer_policy_is_rejected(policy):
    with pytest.raises(ValueError, match="recipient-only or source-passage"):
        briefs.prepare_document(project(), [], enquiry_context=policy)


def test_default_renderer_omits_reference_only_enquiry_context():
    sources = [evidence.source(
        "Original reference",
        "ReferenceBodySentinel: no water booking is approved.",
        kind="reference_excerpt",
        retrieved_at="2026-10-16T00:00:00+00:00",
    )]
    payload = project(campaign_sender_review=False, notes="", sources=[])
    selected = evidence.excerpts(sources)

    recipient = briefs.prepare_document(payload, sources, selected)
    dossier = briefs.prepare_document(
        payload, sources, selected, enquiry_context="source_passages"
    )

    assert "ReferenceBodySentinel" not in recipient["document_markdown"]
    assert "ReferenceBodySentinel" in dossier["document_markdown"]
    assert "The supplied material titled Original reference states:" in (
        dossier["document_markdown"]
    )


def test_casebook_enquiry_explicitly_preserves_attributed_source_passages():
    book = {
        "schema": "sinter-casebook/v1",
        "title": "Fictional water source dossier",
        "document_type": "enquiry",
        "questions": "What does the water notice say?",
        "documents": [{
            "title": "Water notice",
            "content": "WaterAccessSentinel: water access has not been approved.",
            "url": "https://example.invalid/water",
        }],
    }
    before = copy.deepcopy(book)

    report = casebooks.build(book)

    assert "The supplied material titled Water notice states:" in (
        report["document_markdown"]
    )
    assert "WaterAccessSentinel: water access has not been approved." in (
        report["document_markdown"]
    )
    assert report["document_questions"] == [book["questions"]]
    assert report["sources"][0]["content"] == book["documents"][0]["content"]
    assert report["excerpts"]
    assert book == before


def test_new_preparation_does_not_rewrite_a_historical_saved_letter(tmp_path):
    payload = project(
        campaign_sender_review=False,
        notes="InternalNotesSentinel: historical preparation wording.",
    )
    historical = workbench.run(payload)
    sources = [evidence.Source(**item) for item in historical["sources"]]
    selected = [evidence.Excerpt(**item) for item in historical["excerpts"]]
    historical.update(briefs.prepare_document(
        payload, sources, selected, enquiry_context="source_passages"
    ))
    historical["markdown"] = (
        "# Historical saved report\n\n" + historical["document_markdown"]
        + "\n\n" + evidence.render_evidence(selected, sources)
    )
    historical["input_snapshot"] = copy.deepcopy(payload)
    assert "InternalNotesSentinel" in historical["document_markdown"]

    store = Store(tmp_path / "fictional-history")
    identifier = store.save_report(historical)
    prepared_now = workbench.run(payload)
    reopened = Store(store.directory).report(identifier)

    assert "InternalNotesSentinel" not in prepared_now["document_markdown"]
    assert reopened == historical
    assert reopened["input_snapshot"] == payload
    assert "InternalNotesSentinel" in reopened["document_markdown"]
