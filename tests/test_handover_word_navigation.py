"""Native Word navigation is presentation of known labels, never new evidence."""

from __future__ import annotations

import copy
import io
import json
import re
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from sinter import casebooks, client, evidence, handover
from sinter.document_markup import safe_href
from sinter.docx_export import REL, R, W, export_docx

NS = {"w": W, "r": R, "rel": REL}
FIXTURE = Path(__file__).parent / "fixtures/handover-appendix.json"


def rendered(appendix=True):
    original = json.loads(FIXTURE.read_text())
    if appendix:
        original["handover_evidence"] = "selected_appendix"
    before = copy.deepcopy(original)
    with patch.object(client, "_open", side_effect=AssertionError("Offline only")):
        report = casebooks.build(original)
    assert original == before
    return report


def word(markdown):
    payload = {"title": "Fictional selected handover", "markdown": markdown}
    before = copy.deepcopy(payload)
    result = export_docx(payload)
    assert payload == before
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert archive.testzip() is None
        parts = {name: ET.fromstring(archive.read(name)) for name in archive.namelist()}
    return result, parts


def text(node):
    return "".join(
        (child.text or "")
        if child.tag == f"{{{W}}}t"
        else "\n"
        if child.tag == f"{{{W}}}br"
        else "\t"
        if child.tag == f"{{{W}}}tab"
        else ""
        for child in node.iter()
    )


def anchor_text(paragraph):
    return [
        (text(link), link.get(f"{{{W}}}anchor"))
        for link in paragraph.findall("w:hyperlink", NS)
    ]


@pytest.mark.parametrize("appendix", [False, True])
def test_native_links_resolve_to_included_quote_or_explicit_omitted_reference(appendix):
    report = rendered(appendix)
    result, parts = word(report["document_markdown"])
    document = parts["word/document.xml"]
    starts = document.findall(".//w:bookmarkStart", NS)
    ends = document.findall(".//w:bookmarkEnd", NS)
    included = 9 if appendix else 4
    names = {node.get(f"{{{W}}}name") for node in starts}
    assert names == {f"SinterReference{n}" for n in range(1, 10)} | {
        f"SinterPassage{n}" for n in range(1, included + 1)
    }
    assert len(starts) == len(names) == 9 + included
    start_ids = [node.get(f"{{{W}}}id") for node in starts]
    assert len(set(start_ids)) == len(start_ids)
    assert sorted(start_ids) == sorted(node.get(f"{{{W}}}id") for node in ends)
    assert all(re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,39}", name) for name in names)
    links = document.findall(".//w:hyperlink", NS)
    assert links and all(node.get(f"{{{W}}}anchor") in names for node in links)
    assert all(node.get(f"{{{R}}}id") is None for node in links)
    assert all(text(link).startswith("Passage ") for link in links)
    assert not any(
        node.get("Type") == f"{R}/hyperlink"
        for node in parts["word/_rels/document.xml.rels"]
    )
    assert len(parts) == 7
    paragraphs = document.findall("w:body/w:p", NS)
    for number, reference in enumerate(report["document_references"], 1):
        key = next(
            p
            for p in paragraphs
            if text(p).startswith(f"Passage {number} — Original source: ")
        )
        assert (
            f"Excerpt ID: {reference['excerpt_id']}; source ID: {reference['source_id']}."
            in text(key)
        )
        assert f"Unicode characters: {reference['start']}–{reference['end']};" in text(
            key
        )
        assert key.find("w:pPr/w:keepLines", NS) is not None
        if number <= included:
            heading = next(p for p in paragraphs if text(p) == f"Passage {number}")
            assert anchor_text(key) == [(f"Passage {number}", f"SinterPassage{number}")]
            assert anchor_text(heading) == [
                (f"Passage {number}", f"SinterReference{number}")
            ]
            assert heading.find("w:pPr/w:pStyle", NS).get(f"{{{W}}}val") == "Heading3"
        else:
            assert anchor_text(key) == []
            assert "Selected passage not reproduced in this copy." in text(key)
    question_links = [
        (text(p), anchor_text(p))
        for p in paragraphs
        if text(p).startswith("Related wording — review required:")
    ]
    for question, linked in question_links:
        assert [label for label, _ in linked] == re.findall(
            r"Passage [1-9][0-9]*", question
        )
        for label, anchor in linked:
            number = int(label.split()[1])
            assert (
                anchor
                == f"Sinter{'Passage' if number <= included else 'Reference'}{number}"
            )
    assert (
        result.content
        == export_docx(
            {
                "title": "Fictional selected handover",
                "markdown": report["document_markdown"],
            }
        ).content
    )


def test_recipient_guidance_does_not_require_the_application_and_keeps_original_qualifiers():
    for appendix in (False, True):
        report = rendered(appendix)
        document = report["document_markdown"]
        assert "Read its exact wording in Evidence" not in document
        assert "remain available in Evidence" not in document
        assert "ask the sender" in document.lower()
        assert "A wording match is not an answer" in document
        assert "no owner or target date is assigned" in document
        assert "Selection does not establish a verified answer" in document
        if appendix:
            assert (
                "not every original source or its unselected surrounding text"
                in document
            )
        else:
            assert "not reproduced in this copy" in document
        _, parts = word(document)
        visible = text(parts["word/document.xml"])
        if appendix:
            assert "09:45 on 7 October; it is proposed, not confirmed" in visible
            assert "current fictional scope is one small pilot" in visible
            assert "IP ownership and novelty remain unverified" in visible


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "deleted",
        "caption",
        "quoted",
        "list",
        "code",
        "missing_quote",
        "omitted_scope",
    ],
)
def test_ambiguous_or_absent_quote_never_receives_a_stale_anchor(change):
    report = rendered()
    markdown = report["document_markdown"]
    if change == "duplicate":
        markdown = markdown.replace(
            "## Passage reference key",
            "### Passage 1\n\n> Original source: Duplicate\n\n> An unconfirmed extra note.\n\n## Passage reference key",
        )
    elif change == "deleted":
        markdown = markdown.replace("### Passage 1", "### Renamed selected note", 1)
    elif change == "caption":
        start = markdown.index("### Passage 1")
        first = markdown.index("> Original source: ", start)
        markdown = markdown[:first] + markdown[first:].replace(
            "> Original source: ", "> Altered caption: ", 1
        )
    elif change in {"quoted", "list", "code"}:
        heading = {
            "quoted": "> ### Passage 1",
            "list": "- ### Passage 1",
            "code": "```text\n### Passage 1\n```",
        }[change]
        markdown = markdown.replace("### Passage 1", heading, 1)
    elif change == "missing_quote":
        start = markdown.index("### Passage 1")
        end = markdown.index("### Passage 2", start)
        caption_end = markdown.index(
            "\n\n", markdown.index("> Original source: ", start)
        )
        markdown = markdown[:caption_end] + "\n\n" + markdown[end:]
    else:
        key = markdown.index("## Passage reference key")
        markdown = markdown[:key] + markdown[key:].replace(
            "quoted above.",
            "Selected passage not reproduced in this copy. Ask the sender for its original wording and surrounding context.",
            1,
        )
    _, parts = word(markdown)
    document = parts["word/document.xml"]
    names = {
        node.get(f"{{{W}}}name") for node in document.findall(".//w:bookmarkStart", NS)
    }
    assert "SinterPassage1" not in names
    assert "SinterReference1" in names
    assert not document.findall('.//w:hyperlink[@w:anchor="SinterPassage1"]', NS)
    assert all(
        link.get(f"{{{W}}}anchor") in names
        for link in document.findall(".//w:hyperlink", NS)
    )
    for reference in report["document_references"]:
        assert reference["excerpt_id"] in text(document)


@pytest.mark.parametrize(
    "change", ["duplicate_id", "missing_code", "nested_key", "missing_key_intro"]
)
def test_unadmitted_reference_key_stays_literal_without_navigation(change):
    report = rendered()
    markdown = report["document_markdown"]
    first, second = report["document_references"][:2]
    if change == "duplicate_id":
        markdown = markdown.replace(second["excerpt_id"], first["excerpt_id"])
    elif change == "missing_code":
        markdown = markdown.replace(
            "`" + first["excerpt_id"] + "`", first["excerpt_id"]
        )
    elif change == "nested_key":
        markdown = markdown.replace(
            "## Passage reference key", "> ## Passage reference key"
        )
    else:
        markdown = markdown.replace(
            "These short labels refer to the exact selected excerpts.",
            "A user-edited reference note.",
        )
    _, parts = word(markdown)
    document = parts["word/document.xml"]
    assert not document.findall(".//w:bookmarkStart", NS)
    assert not document.findall(".//w:hyperlink", NS)
    assert first["excerpt_id"] in text(document)


def test_arbitrary_fragments_and_quoted_passage_labels_are_literal_not_navigation():
    assert safe_href("#SinterPassage1") is None
    markdown = rendered()["document_markdown"]
    markdown += "\n\n[Unknown](#SinterPassage1)\n\n> Related wording — review required: Passage 1.\n\n```text\nRelated wording — review required: Passage 1.\n```"
    _, parts = word(markdown)
    document = parts["word/document.xml"]
    assert "[Unknown](#SinterPassage1)" in text(document)
    paragraphs = document.findall("w:body/w:p", NS)
    trailing = paragraphs[-3:]
    assert all(not p.findall("w:hyperlink", NS) for p in trailing)
    assert not any(
        node.get("Type") == f"{R}/hyperlink"
        for node in parts["word/_rels/document.xml.rels"]
    )


def test_supplied_wording_about_evidence_and_noncanonical_ids_is_never_rewritten():
    original = (
        "Read its exact wording in Evidence. No owner or amount is confirmed. 前😀"
    )
    source = evidence.source("Same title with Passage 1", original)
    excerpt = evidence.Excerpt("E[original]", source.id, 0, len(original), original)
    markdown = handover.render(
        "Fictional",
        {},
        [source],
        [excerpt],
        [{"question": "What is confirmed?", "excerpt_ids": [excerpt.id]}],
    )
    _, parts = word(markdown)
    document = parts["word/document.xml"]
    assert original in text(document)
    assert text(document).count(excerpt.id) == 1
    assert "SinterPassage1" in {
        n.get(f"{{{W}}}name") for n in document.findall(".//w:bookmarkStart", NS)
    }
    assert source.content == original


def test_larger_reference_maps_keep_all_quotes_and_ids_without_optional_navigation():
    sources, excerpts = [], []
    for number in range(65):
        source = evidence.source(
            f"Fictional source {number}", f"Unique condition {number}: NOT approved."
        )
        sources.append(source)
        excerpts.append(
            evidence.Excerpt(
                f"E{number}", source.id, 0, len(source.content), source.content
            )
        )
    markdown = handover.render(
        "Fictional", {}, sources, excerpts, [], include_selected_appendix=True
    )
    _, parts = word(markdown)
    document = parts["word/document.xml"]
    assert not document.findall(".//w:bookmarkStart", NS)
    for excerpt in excerpts:
        assert excerpt.quote in text(document)
        assert f"Excerpt ID: {excerpt.id};" in text(document)


def test_same_titles_multiple_ranges_and_unicode_ids_do_not_alias_navigation():
    first = evidence.source("Repeated supplied title", "Before😀 NOT approved. After")
    second = evidence.source(
        "Repeated supplied title", "No owner or date is confirmed — 李."
    )
    selected = [
        evidence.Excerpt("Efirst", first.id, 8, 21, first.content[8:21]),
        evidence.Excerpt("Eprefix", first.id, 0, 7, first.content[:7]),
        evidence.Excerpt("Esecond", second.id, 0, len(second.content), second.content),
    ]
    questions = [
        {
            "question": "What is approved?",
            "excerpt_ids": [selected[2].id, selected[0].id],
        }
    ]
    before = copy.deepcopy((first, second, selected, questions))
    markdown = handover.render("Fictional", {}, [first, second], selected, questions)
    _, parts = word(markdown)
    paragraphs = parts["word/document.xml"].findall("w:body/w:p", NS)
    related = next(
        p
        for p in paragraphs
        if text(p).startswith("Related wording — review required:")
    )
    assert anchor_text(related) == [
        ("Passage 3", "SinterPassage3"),
        ("Passage 1", "SinterPassage1"),
    ]
    for number, excerpt in enumerate(selected, 1):
        key = next(
            p
            for p in paragraphs
            if text(p).startswith(f"Passage {number} — Original source: ")
        )
        assert excerpt.id in text(key) and excerpt.source_id in text(key)
        assert f"Unicode characters: {excerpt.start}–{excerpt.end};" in text(key)
    assert (first, second, selected, questions) == before


def test_moved_unique_quote_recomputes_destination_and_unknown_question_label_is_literal():
    report = rendered()
    markdown = report["document_markdown"]
    begin = markdown.index("### Passage 1")
    end = markdown.index("### Passage 2", begin)
    segment = markdown[begin:end]
    markdown = markdown[:begin] + markdown[end:]
    markdown = markdown.replace(
        "## Passage reference key", segment + "## Passage reference key"
    )
    _, parts = word(markdown)
    paragraphs = parts["word/document.xml"].findall("w:body/w:p", NS)
    heading = next(p for p in paragraphs if text(p) == "Passage 1")
    assert heading.find("w:bookmarkStart", NS).get(f"{{{W}}}name") == "SinterPassage1"
    assert anchor_text(heading) == [("Passage 1", "SinterReference1")]
    changed = report["document_markdown"].replace(
        "Related wording — review required: Passage 1",
        "Related wording — review required: Passage 999",
        1,
    )
    _, parts = word(changed)
    unknown = next(
        p
        for p in parts["word/document.xml"].findall("w:body/w:p", NS)
        if text(p).startswith("Related wording — review required: Passage 999")
    )
    assert not unknown.findall("w:hyperlink", NS)


def test_historical_supplied_reference_scope_is_exported_verbatim_without_migration():
    report = rendered(False)
    new_scope = "Selected passage not reproduced in this copy. Ask the sender for its original wording and surrounding context."
    old_scope = "Evidence only — not reproduced in this document. Read its exact wording in Evidence."
    markdown = report["document_markdown"].replace(new_scope, old_scope)
    original = markdown
    _, parts = word(markdown)
    document = parts["word/document.xml"]
    assert markdown == original
    assert old_scope in text(document)
    assert not document.findall('.//w:hyperlink[@w:anchor="SinterPassage5"]', NS)
    assert "SinterReference5" in {
        n.get(f"{{{W}}}name") for n in document.findall(".//w:bookmarkStart", NS)
    }
