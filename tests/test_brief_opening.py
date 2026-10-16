"""Recipient prose remains explicit, literal and separate from campaign evidence."""
import copy
import io
import json
import zipfile
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from sinter import briefs, client, workbench
from sinter.document_markup import Paragraph, parse
from sinter.docx_export import W, export_docx
from sinter.evidence import literal_paragraph
from sinter.store import Store

FIXTURE = json.loads((Path(__file__).parent / "fixtures/literal_paragraph.v1.json").read_text())


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


def test_non_campaign_notes_keep_existing_question_and_background_behavior():
    payload = project(campaign_sender_review=False, questions="", notes="Should we consult the coordinator?")
    report = workbench.run(payload)
    assert report["document_questions"] == [payload["notes"]]
    assert payload["notes"] in report["document_markdown"]


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
