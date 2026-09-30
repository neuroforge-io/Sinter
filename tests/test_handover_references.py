"""Readable local references remain bound to exact, unchanged source passages."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import replace
from unittest.mock import patch

import pytest
from test_handover_presentation import garden, passage, word_text

from sinter import casebooks, client, evidence, handover
from sinter.document_markup import Paragraph, parse
from sinter.docx_export import W
from sinter.store import Store


def test_garden_questions_and_notes_use_labels_with_exact_identity_key_once():
    original = garden()
    before = copy.deepcopy(original)
    with patch.object(
        client, "_open", side_effect=AssertionError("Offline only")
    ) as api:
        report = casebooks.build(original)
    api.assert_not_called()
    document = report["document_markdown"]
    prose, key = document.split("## Passage reference key", 1)
    assert not re.search(r"[ES][0-9a-f]{24}", prose)
    assert "Related wording — review required: Passage 1" in prose
    assert "### Passage 1" in prose
    assert "The real-world answer remains unknown" in prose
    assert "Offsets count Unicode code points from zero" in key
    assert "The start is included; the end is excluded" in key
    assert "Selection does not establish a verified answer" in key
    assert len(report["document_references"]) == len(report["excerpts"])
    sources = {item["id"]: item for item in report["sources"]}
    for number, (reference, excerpt) in enumerate(
        zip(report["document_references"], report["excerpts"]), 1
    ):
        assert reference == {
            "label": f"Passage {number}",
            "excerpt_id": excerpt["id"],
            "source_id": excerpt["source_id"],
            "start": excerpt["start"],
            "end": excerpt["end"],
        }
        assert document.count(excerpt["id"]) == 1
        assert "`" + excerpt["id"] + "`" in key
        assert "`" + excerpt["source_id"] + "`" in key
        assert (
            sources[excerpt["source_id"]]["content"][
                reference["start"] : reference["end"]
            ]
            == excerpt["quote"]
        )
    text, _ = word_text(document)
    for reference in report["document_references"]:
        assert reference["label"] in text
        assert text.count(reference["excerpt_id"]) == 1
    assert original == before


def test_questions_reference_passages_in_their_original_order_without_answers():
    first, one = passage("Access is not confirmed.", "Earlier reply")
    second, two = passage("Access may be possible; ask Jo.", "Later reply")
    two = replace(two, id="Esecond")
    questions = [
        {"question": "Is access confirmed?", "excerpt_ids": [two.id, one.id]},
        {"question": "What insurance excess applies?", "excerpt_ids": []},
    ]
    before = copy.deepcopy(questions)
    document = handover.render("Handover", {}, [first, second], [one, two], questions)
    assert "Related wording — review required: Passage 2, Passage 1." in document
    assert "The real-world answer remains unknown" in document
    assert "A wording match is not an answer" in document
    assert "no owner or target date is assigned" in document
    assert questions == before


def test_duplicate_source_titles_and_multiple_passages_do_not_alias_by_title():
    first = evidence.source("Same title", "Not approved. Ask before confirming.")
    second = evidence.source(
        "Same title", "Earlier account is superseded; do not reuse."
    )
    selected = [
        evidence.Excerpt("Efirst", first.id, 0, 13, first.content[:13]),
        evidence.Excerpt(
            "Esecond", first.id, 14, len(first.content), first.content[14:]
        ),
        evidence.Excerpt("Ethird", second.id, 0, len(second.content), second.content),
    ]
    references = handover.reference_records([first, second], selected)
    assert [item["label"] for item in references] == [
        "Passage 1",
        "Passage 2",
        "Passage 3",
    ]
    assert references[0]["source_id"] == references[1]["source_id"] == first.id
    assert references[2]["source_id"] == second.id
    assert first.id != second.id
    document = handover.render("Handover", {}, [first, second], selected, [])
    assert document.count("Excerpt ID:") == 3
    for selected_passage in selected:
        assert document.count(selected_passage.id) == 1
    assert f"Unicode characters: 14–{len(first.content)};" in document


def test_evidence_only_passages_have_a_complete_key_without_reproducing_text():
    sources, selected = [], []
    for number in range(7):
        source, excerpt = passage(
            f"Unique condition {number}: not approved.", f"Original source {number}"
        )
        sources.append(source)
        selected.append(replace(excerpt, id=f"Epassage{number}"))
    questions = [
        {
            "question": "Has the last condition been approved?",
            "excerpt_ids": [selected[-1].id],
        }
    ]
    document = handover.render("Handover", {}, sources, selected, questions)
    prose, key = document.split("## Passage reference key", 1)
    assert "Related wording — review required: Passage 7." in prose
    assert "Showing 4 of 7 selected passages from 4 sources" in prose
    assert key.count("Evidence only — not reproduced in this document") == 3
    assert key.count("quoted above.") == 4
    for index, excerpt in enumerate(selected):
        assert document.count(excerpt.id) == 1
        assert f"> **Passage {index + 1}**" in key
        if index >= handover.MAX_NOTES:
            assert excerpt.quote not in document
        else:
            assert excerpt.quote in prose
    text, _ = word_text(document)
    assert "Evidence only — not reproduced in this document" in text
    assert selected[-1].id in text


def test_unicode_offsets_count_python_code_points_without_changing_original_text():
    prefix = "前😀e\u0301\r\n"
    quote = "NOT approved — ask 李."
    content = prefix + quote + "\n後"
    source = evidence.source("Unicode source", content)
    selected = evidence.Excerpt(
        "Eunicode", source.id, len(prefix), len(prefix) + len(quote), quote
    )
    assert len(prefix) != len(prefix.encode("utf-16-le")) // 2
    assert len(prefix) != len(prefix.encode("utf-8"))
    records = handover.reference_records([source], [selected])
    assert records[0]["start"] == 6
    assert records[0]["end"] == 6 + len(quote)
    assert source.content[records[0]["start"] : records[0]["end"]] == quote
    document = handover.render("Handover", {}, [source], [selected], [])
    assert f"Unicode characters: 6–{6 + len(quote)};" in document
    text, _ = word_text(document)
    assert quote in text and selected.id in text
    assert source.content == content


@pytest.mark.parametrize(
    "title",
    [
        "Passage 1 names a source; it is not a reference",
        "[Passage 1] | **supplied title**",
        "Source title\n9. Passage 1 remains unconfirmed\n---",
        "<script>Passage 1</script>",
    ],
)
def test_supplied_source_titles_are_literal_quoted_metadata_not_alias_headings(title):
    source, selected = passage("No person has accepted the task.", title)
    document = handover.render("Handover", {}, [source], [selected], [])
    blocks = parse(document)
    title_paragraphs = [
        block
        for block in blocks
        if isinstance(block, Paragraph)
        and "Original source:" in "".join(span.text for span in block.spans)
    ]
    assert len(title_paragraphs) == 2
    assert all(block.quote for block in title_paragraphs)
    headings = [
        block for block in blocks if isinstance(block, Paragraph) and block.heading
    ]
    assert [
        "".join(span.text for span in block.spans)
        for block in headings
        if block.heading == 3
    ] == ["Passage 1"]
    text, _ = word_text(document)
    assert title in text


def test_canonical_identifiers_in_reference_key_remain_literal_code_spans():
    source, selected = passage("Not approved.")
    document = handover.render("Handover", {}, [source], [selected], [])
    identifiers = {source.id, selected.id}
    found = [
        span
        for block in parse(document)
        if isinstance(block, Paragraph)
        for span in block.spans
        if span.text in identifiers
    ]
    assert len(found) == 2
    assert all(span.code for span in found)


def test_each_reference_key_record_is_one_quoted_paragraph_including_word_export():
    report = casebooks.build(garden())
    _, key = report["document_markdown"].split("## Passage reference key", 1)
    records = [
        block
        for block in parse(key)
        if isinstance(block, Paragraph) and block.quote
    ]
    assert len(records) == len(report["document_references"])
    _, word = word_text(report["document_markdown"])
    word_records = [
        paragraph
        for paragraph in word.iter(f"{{{W}}}p")
        if "Excerpt ID:" in "".join(paragraph.itertext())
    ]
    assert len(word_records) == len(records)
    sources = {source["id"]: source for source in report["sources"]}
    for reference, paragraph, word_paragraph in zip(
        report["document_references"], records, word_records
    ):
        text = "".join(span.text for span in paragraph.spans)
        word_words = "".join(word_paragraph.itertext())
        for expected in (
            reference["label"],
            sources[reference["source_id"]]["title"],
            reference["excerpt_id"],
            reference["source_id"],
            f"Unicode characters: {reference['start']}–{reference['end']};",
            "quoted above.",
        ):
            assert expected in text
            assert expected in word_words
        assert text.count("\n") == 2
        assert len(list(word_paragraph.iter(f"{{{W}}}br"))) == 2
        assert not paragraph.heading and not paragraph.list_id


def test_evidence_only_scope_stays_with_its_identity_and_range_in_word():
    source = evidence.source("One exact original", "abcde")
    selected = [
        evidence.Excerpt(f"Epart{index}", source.id, index, index + 1, character)
        for index, character in enumerate(source.content)
    ]
    document = handover.render("Handover", {}, [source], selected, [])
    _, word = word_text(document)
    matching = [
        "".join(paragraph.itertext())
        for paragraph in word.iter(f"{{{W}}}p")
        if "Epart4" in "".join(paragraph.itertext())
    ]
    assert len(matching) == 1
    assert "Passage 5" in matching[0] and source.id in matching[0]
    assert "Unicode characters: 4–5;" in matching[0]
    assert "Evidence only — not reproduced in this document." in matching[0]
    assert "Read its exact wording in Evidence." in matching[0]


def test_repeated_builds_and_json_roundtrip_keep_labels_and_canonical_metadata(
    tmp_path,
):
    original = garden()
    first = casebooks.build(original)
    second = casebooks.build(copy.deepcopy(original))
    for key in (
        "document_markdown",
        "document_references",
        "excerpts",
        "sources",
        "source_register",
        "question_index",
        "coverage",
        "markdown",
    ):
        assert first[key] == second[key], key
    repository = Store(tmp_path)
    identifier = repository.save_report(first)
    reopened = repository.report(identifier)
    assert reopened == first
    restored = json.loads(json.dumps(reopened, ensure_ascii=False))
    assert restored["document_references"] == first["document_references"]
    text, _ = word_text(restored["document_markdown"])
    for reference in restored["document_references"]:
        assert reference["label"] in text
        assert text.count(reference["excerpt_id"]) == 1
        assert reference["source_id"] in text


def test_report_reference_metadata_is_additive_and_audit_metadata_is_unchanged():
    original = garden()
    report = casebooks.build(original)
    with (
        patch.object(casebooks, "render_handover", return_value="Old document"),
        patch.object(casebooks, "handover_references", return_value=[]),
    ):
        baseline = casebooks.build(original)
    for key in baseline.keys() - {
        "document_markdown",
        "document_references",
        "created_at",
    }:
        assert report[key] == baseline[key], key
    for kind in ("brief", "agenda", "enquiry"):
        assert "document_references" not in casebooks.build(original, kind)


def test_no_evidence_produces_no_reference_key_or_fabricated_label():
    original = {
        "title": "Insurance",
        "questions": "Insurance excess?",
        "document_type": "handover",
        "documents": [
            {"title": "Menu", "content": "Bring fruit and water."},
        ],
    }
    report = casebooks.build(original)
    assert report["document_references"] == []
    assert report["excerpts"] == []
    assert "## Passage reference key" not in report["document_markdown"]
    assert "Passage 1" not in report["document_markdown"]
    assert "The real-world answer remains unknown" in report["document_markdown"]
    assert report["question_index"][0]["status"] == "no_wording_match"


def test_historical_saved_report_is_not_rewritten_or_assigned_new_labels(tmp_path):
    legacy = casebooks.build(garden())
    del legacy["document_references"]
    legacy["document_markdown"] = (
        "Historical handover: [" + legacy["excerpts"][0]["id"] + "]"
    )
    repository = Store(tmp_path)
    identifier = repository.save_report(legacy)
    with repository.connect() as db:
        before = db.execute(
            "SELECT document FROM reports WHERE id=?", (identifier,)
        ).fetchone()[0]
    reopened = repository.report(identifier)
    assert reopened == legacy
    assert "document_references" not in reopened
    with repository.connect() as db:
        after = db.execute(
            "SELECT document FROM reports WHERE id=?", (identifier,)
        ).fetchone()[0]
    assert after == before


@pytest.mark.parametrize(
    "change",
    [
        {"quote": "Approved."},
        {"source_id": "Smissing"},
        {"start": -1},
        {"start": True},
        {"end": 1.5},
        {"end": 1000},
        {"start": 0, "end": 0},
    ],
)
def test_invalid_original_passage_cannot_create_an_alias(change):
    source, selected = passage("Not approved.")
    with pytest.raises(ValueError, match="no longer matches"):
        handover.reference_records([source], [replace(selected, **change)])


def test_ambiguous_original_identities_cannot_create_competing_aliases():
    source, selected = passage("Not approved.")
    with pytest.raises(ValueError, match="source identity is ambiguous"):
        handover.reference_records([source, source], [selected])
    with pytest.raises(ValueError, match="passage identity is ambiguous"):
        handover.reference_records([source], [selected, selected])


@pytest.mark.parametrize("identifier", ["", " ", "\t\n", None, []])
def test_missing_retained_source_identity_cannot_create_a_reference(identifier):
    source, selected = passage("Not approved.")
    with pytest.raises(ValueError, match="source identity is missing or invalid"):
        handover.reference_records(
            [replace(source, id=identifier)], [replace(selected, source_id=identifier)]
        )
    with pytest.raises(ValueError, match="source identity is missing or invalid"):
        handover.render(
            "Handover",
            {},
            [replace(source, id=identifier)],
            [replace(selected, source_id=identifier)],
            [],
        )


@pytest.mark.parametrize("identifier", ["", " ", "\t\n", None, []])
def test_missing_passage_identity_cannot_create_a_reference(identifier):
    source, selected = passage("Not approved.")
    with pytest.raises(ValueError, match="passage identity is ambiguous"):
        handover.reference_records([source], [replace(selected, id=identifier)])


def test_unknown_question_reference_is_rejected_without_mutating_supplied_values():
    source, selected = passage("Not approved.")
    questions = [{"question": "Approved?", "excerpt_ids": ["Eunknown"]}]
    before = copy.deepcopy(questions)
    with pytest.raises(ValueError, match="unavailable evidence"):
        handover.render("Handover", {}, [source], [selected], questions)
    assert questions == before
