"""Readable handovers retain source qualifiers and never answer lexical matches."""

from __future__ import annotations

import copy
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from sinter import casebooks, client, evidence, handover
from sinter.document_markup import Table, inline, parse
from sinter.docx_export import W, export_docx


def garden():
    path = Path(__file__).resolve().parents[1] / "examples/offline-garden/casebook.json"
    return json.loads(path.read_text(encoding="utf-8"))


def passage(content, title="Supplied note", start=0, end=None):
    source = evidence.source(title, content)
    end = len(content) if end is None else end
    excerpt = evidence.Excerpt("Eexample", source.id, start, end, content[start:end])
    return source, excerpt


def render(content, title="Supplied note", question="What is confirmed?"):
    source, excerpt = passage(content, title)
    return handover.render(
        "Handover",
        {},
        [source],
        [excerpt],
        [{"question": question, "excerpt_ids": [excerpt.id]}],
    )


def word_text(markdown):
    document = export_docx({"title": "Source-only handover", "markdown": markdown})
    with zipfile.ZipFile(io.BytesIO(document.content)) as archive:
        assert archive.testzip() is None
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter(f"{{{W}}}p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{{{W}}}t":
                parts.append(node.text or "")
            elif node.tag == f"{{{W}}}br":
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs), root


def test_garden_puts_unanswered_checks_before_readable_attributed_source_wording():
    payload = garden()
    before = copy.deepcopy(payload)
    with patch.object(
        client, "_open", side_effect=AssertionError("Offline only")
    ) as api:
        report = casebooks.build(payload)
        _, root = word_text(report["document_markdown"])
    api.assert_not_called()
    document = report["document_markdown"]
    assert document.index("## Handover next steps") < document.index(
        "## Selected source wording"
    )
    assert "Source-only handover checklist" in document
    assert "A wording match is not an answer" in document
    assert "no owner or target date is assigned" in document
    assert document.count("Related wording — review required:") == 5
    assert "### 6. What insurance excess applies?" in document
    assert "The real-world answer remains unknown" in document
    assert "Quoted source table" in document
    assert "Proposed target date (unconfirmed)" in document
    assert "Check current funder guidelines | — | — | — | not\\_started" in document
    assert "Fictional treasurer | 2026-10-09 | in\\_progress" in document
    assert "The equipment quote has not been received." in document
    assert "No person has accepted the actions." in document
    assert "not a confirmed deadline or grant closing date" in document
    assert "Requirements have not been checked for this source yet." in document
    assert "> **Example school garden funding**" in document
    assert "> \\# Example school garden funding" not in document
    assert root.find(f".//{{{W}}}tbl") is not None
    assert payload == before
    sources = {item["id"]: item for item in report["sources"]}
    for excerpt in report["excerpts"]:
        assert (
            sources[excerpt["source_id"]]["content"][excerpt["start"] : excerpt["end"]]
            == excerpt["quote"]
        )


def test_presentation_changes_only_document_not_existing_audit_or_metadata():
    payload = garden()
    report = casebooks.build(payload)
    with patch.object(casebooks, "render_handover", return_value="Legacy presentation"):
        control = casebooks.build(payload)
    for key in control.keys() - {"created_at", "document_markdown"}:
        assert report[key] == control[key], key
    brief = casebooks.build(payload, "brief")
    expected_audit = (
        brief["markdown"]
        .replace(
            "Briefing note - DRAFT / HUMAN REVIEW REQUIRED",
            "Volunteer handover - DRAFT / HUMAN REVIEW REQUIRED",
        )
        .replace("## Recommended next steps", "## Handover next steps")
    )
    assert report["markdown"] == expected_audit
    assert "\\# Example school garden funding" in report["markdown"]
    assert payload["documents"][2]["content"] in control["sources"][2]["content"]


def test_other_document_types_do_not_use_the_handover_adapter():
    with patch.object(
        casebooks, "render_handover", side_effect=AssertionError("Handover only")
    ):
        for kind in ("brief", "agenda", "enquiry"):
            report = casebooks.build(garden(), kind)
            assert report["document_type"] == kind


def test_supplied_sender_role_organisation_and_multiline_contact_survive_word_export():
    payload = {
        **garden(),
        "signatory": "Alex Morgan",
        "sender_role": "Secretary",
        "organisation": "Fictional Community Association",
        "contact_details": "alex@example.invalid\n+61 7 5550 1234",
    }
    report = casebooks.build(payload)
    document = report["document_markdown"]
    text, _ = word_text(document)
    for wording in (
        "Prepared by: Alex Morgan",
        "Role: Secretary",
        "Fictional Community Association",
        "alex@example.invalid",
        "+61 7 5550 1234",
        "Prepared for: Incoming fictional committee",
    ):
        assert wording in document and wording in text
    assert "[name]" not in document


def test_emphasised_source_heading_is_one_readable_quote_without_double_markers():
    document = render(
        "# **NOT approved** unless *permission* is confirmed.\nKeep conditions."
    )
    assert "> **NOT approved unless permission is confirmed.**" in document
    text, _ = word_text(document)
    assert "NOT approved unless permission is confirmed." in text
    assert "****" not in document


def test_multiple_passages_from_one_source_have_distinct_titles_and_scope():
    source = evidence.source("Long source", "Not approved.\nAsk Jo before confirming.")
    first = evidence.Excerpt("Efirst", source.id, 0, 13, source.content[:13])
    second = evidence.Excerpt(
        "Esecond", source.id, 14, len(source.content), source.content[14:]
    )
    document = handover.render("Handover", {}, [source], [first, second], [])
    assert "Showing 2 of 2 selected passages from 1 source." in document
    assert "### Passage 1" in document
    assert "### Passage 2" in document
    assert document.count("Original source: Long source") == 4
    assert "Not approved." in document and "Ask Jo before confirming." in document


def test_csv_quotes_commas_pipes_formulas_and_all_cells_without_interpretation():
    content = (
        'Item,Quantity,Notes\r\n"Seeds, beans",2,"not approved | ask Jo"\r\n'
        '"=SUM(1,2)",0,"Do NOT purchase unless permission is confirmed."\r\n'
    )
    source, excerpt = passage(content, "inventory.csv")
    document = render(content, "inventory.csv")
    tables = [block for block in parse(document) if isinstance(block, Table)]
    assert len(tables) == 1
    cells = [
        ["".join(span.text for span in cell) for cell in row] for row in tables[0].rows
    ]
    assert cells == [
        ["Item", "Quantity", "Notes"],
        ["Seeds, beans", "2", "not approved | ask Jo"],
        ["=SUM(1,2)", "0", "Do NOT purchase unless permission is confirmed."],
    ]
    text, root = word_text(document)
    for row in cells:
        for cell in row:
            assert cell in text
    assert root.find(f".//{{{W}}}instrText") is None
    assert excerpt.quote == source.content == content


def test_multiline_csv_is_complete_labelled_source_records_not_broken_rows():
    content = (
        'Action,Owner,Notes\n"Ask coordinator","","Do not approve until\n'
        'a named volunteer accepts.\nKeep every condition."\n'
        '"Record decision","Suggested role only","Not a commitment."\n'
    )
    document = render(content, "tasks.csv")
    assert "**Source record 1**" in document and "**Source record 2**" in document
    assert not any(isinstance(block, Table) for block in parse(document))
    text, _ = word_text(document)
    for wording in (
        "Ask coordinator",
        "Owner:",
        "Do not approve until",
        "a named volunteer accepts.",
        "Keep every condition.",
        "Suggested role only",
        "Not a commitment.",
    ):
        assert wording in text
    assert "Blank cells are shown as —" in document


@pytest.mark.parametrize(
    "content",
    [
        "Action,Owner\nCheck guidance,Jo,not confirmed\n",
        "Action,Owner,Status\nCheck guidance,Jo\n",
        'Action,Owner\n"Unclosed wording,Jo\n',
        "Action,Action\nCheck guidance,not confirmed\n",
        "Action, OWNER ,owner\nCheck guidance,Jo,role only\n",
        "Action,,Owner\nCheck guidance,,Jo\n",
        '"Action\nlabel",Owner\nCheck guidance,Jo\n',
        "1,2\n3,4\n",
        "Apple,Pear\nOrange,Peach\n",
        "Action,Owner\n",
        "Action,Owner\nCheck guidance,Jo\n\nRecord reply,unassigned\n",
    ],
)
def test_ambiguous_or_malformed_csv_keeps_complete_literal_source(content):
    source, excerpt = passage(content, "supplied.csv")
    assert handover._csv_rows(source, excerpt) is None
    document = render(content, "supplied.csv")
    assert "Table layout could not be confirmed" in document
    assert handover._literal_quote(content) in document
    assert not any(isinstance(block, Table) for block in parse(document))
    assert excerpt.quote == source.content == content


@pytest.mark.parametrize(
    "header",
    [
        "Action\n",
        "\nAction",
        "Action\r",
        "\rAction",
        "Action\r\n",
        "Action\v",
        "Action\f",
        "Action\x85",
        "Action\u2028",
        "Action\u2029",
    ],
)
def test_header_line_breaks_are_rejected_before_label_whitespace_is_stripped(header):
    content = f'"{header}",Owner\nReview,Unassigned\n'
    source, excerpt = passage(content, "actions.csv")
    assert handover._csv_rows(source, excerpt) is None
    document = render(content, "actions.csv")
    assert "Table layout could not be confirmed" in document
    assert handover._literal_quote(content) in document


@pytest.mark.parametrize("separator", ["\r", "\r\n", "\x85", "\u2028", "\u2029"])
def test_csv_cell_line_separators_use_complete_labelled_records(separator):
    content = (
        f'Action,Owner,Notes\nReview,Unassigned,"Not confirmed{separator}ask Jo"\n'
    )
    document = render(content, "actions.csv")
    assert "**Source record 1**" in document
    assert "Not confirmed\n> ask Jo" in document
    assert not any(isinstance(block, Table) for block in parse(document))
    text, _ = word_text(document)
    assert "Not confirmed\nask Jo" in text


@pytest.mark.parametrize(
    "cell",
    [
        "NOT approved\n1. Not eligible\n9. Funding unknown",
        "NOT approved\n---\nunless committee confirms",
        "NOT approved\n- Do not proceed\n+ Ask Jo first",
        "NOT approved\n# Condition remains unconfirmed\n> Not a commitment",
        "NOT approved\n```\nKeep every delimiter.\n````\nDo not publish",
    ],
)
def test_multiline_cells_export_exact_values_without_reinterpreting_block_markup(cell):
    output = io.StringIO(newline="")
    import csv

    writer = csv.writer(output)
    writer.writerow(["Action", "Owner", "Notes"])
    writer.writerow(["Review", "Unassigned", cell])
    document = render(output.getvalue(), "actions.csv")
    text, root = word_text(document)
    assert cell in text
    assert root.find(f".//{{{W}}}numPr") is None


def test_malformed_fallback_exports_literal_lists_rules_fences_and_html_completely():
    content = (
        "Action,Owner\nReview,Jo,extra field\n---\n1. Not eligible\n"
        "9. Funding unknown\n```\n<script>Not approved</script>\n````"
    )
    document = render(content, "actions.csv")
    text, root = word_text(document)
    assert content in text
    assert "Table layout could not be confirmed" in document
    assert root.find(f".//{{{W}}}numPr") is None
    assert root.find(f".//{{{W}}}drawing") is None


@pytest.mark.parametrize(
    "content",
    [
        "Action,Owner\n"
        + "Check guidance,unassigned\n" * (handover.MAX_TABLE_ROWS + 1),
        "Action,Owner,"
        + ",".join(f"Column{i}" for i in range(11))
        + "\n"
        + ",".join("do not confirm" for _ in range(13))
        + "\n",
    ],
)
def test_table_layout_limits_fall_back_without_truncating_rows_or_cells(content):
    source, excerpt = passage(content, "large.csv")
    assert handover._csv_rows(source, excerpt) is None
    document = render(content, "large.csv")
    assert handover._literal_quote(content) in document
    assert document.count("unassigned") == content.count("unassigned")
    assert document.count("do not confirm") == content.count("do not confirm")


@pytest.mark.parametrize("start,end", [(0, 24), (13, None)])
def test_partial_csv_passage_cannot_assert_headers_or_drop_fragment(start, end):
    content = "Action,Owner\nCheck guidance,unassigned\nRecord reply,role only\n"
    source, excerpt = passage(content, "partial.csv", start, end)
    document = handover.render("Handover", {}, [source], [excerpt], [])
    assert "Table layout could not be confirmed" in document
    assert handover._literal_quote(excerpt.quote) in document
    assert source.content == content
    assert not any(isinstance(block, Table) for block in parse(document))


def test_comma_containing_correspondence_is_not_assumed_to_be_csv():
    content = "Hello, Sam\nNo, the booking is not confirmed.\nThanks, Pat"
    document = render(content)
    assert "Quoted source table" not in document
    assert not any(isinstance(block, Table) for block in parse(document))
    text, _ = word_text(document)
    assert "No, the booking is not confirmed." in text


def test_markdown_layout_preserves_negation_conditions_urls_and_literal_hostile_text():
    content = (
        "# Provisional access\n\n**NOT confirmed**. "
        "Do not advertise unless approved.\n\n"
        "- Owner: *suggested role only*; nobody has accepted.\n"
        "- Read [current wording](https://example.invalid/guidance).\n\n"
        '<script>alert("approval")</script>\n'
        "![approval](https://example.invalid/track.png)\n"
        "[run](javascript:alert(1))\n"
    )
    document = render(content)
    assert "> **Provisional access**" in document
    assert "> **NOT confirmed**" in document
    text, root = word_text(document)
    for wording in (
        "NOT confirmed",
        "Do not advertise unless approved.",
        "suggested role only",
        "nobody has accepted.",
        "current wording (https://example.invalid/guidance)",
        '<script>alert("approval")</script>',
        "![approval](https://example.invalid/track.png)",
        "[run](javascript:alert(1))",
    ):
        assert wording in text
    assert root.find(f".//{{{W}}}drawing") is None
    assert "no owner or target date is assigned" in document


def test_fenced_code_is_quoted_literal_without_reinterpreting_headers_or_instructions():
    content = "```text\n# Do not publish\nAction,Owner\nNOT approved,unassigned\n```"
    document = render(content)
    assert handover._literal_quote(content) in document
    assert "**Do not publish**" not in document
    text, _ = word_text(document)
    assert "# Do not publish" in text
    assert "NOT approved,unassigned" in text


@pytest.mark.parametrize(
    "content",
    [
        "1. Not eligible\n9. Funding unknown\n---",
        "4) Not approved\n   8. Ask Jo first\n------",
        "3. NOT **approved**\n7. Do not proceed unless *permission* is confirmed.\n---",
    ],
)
def test_ordinary_source_numbers_and_rule_markers_remain_literal_in_word(content):
    document = render(content)
    text, root = word_text(document)
    for line in content.splitlines():
        words = line.strip().replace("**", "").replace("*", "")
        assert words in text
    assert root.find(f".//{{{W}}}numPr") is None
    assert "\n—\n" not in text
    assert all(
        block.ordered is False for block in parse(document) if hasattr(block, "ordered")
    )


def test_regular_source_bullets_remain_readable_without_numeric_marker_loss():
    document = render(
        "- Scope is not specified.\n- Owner has not accepted.\n1. Ask Jo."
    )
    text, root = word_text(document)
    assert "Scope is not specified." in text and "Owner has not accepted." in text
    assert "1. Ask Jo." in text
    numbered = root.findall(f".//{{{W}}}numPr")
    assert len(numbered) == 2  # The two supplied bullet items only.


def test_nested_source_quote_cannot_renumber_identifiers_or_replace_rule_wording():
    document = render("> 1. Not eligible\n> 9. Funding unknown\n> ---")
    text, root = word_text(document)
    for wording in ("1. Not eligible", "9. Funding unknown", "---"):
        assert wording in text
    assert root.find(f".//{{{W}}}numPr") is None


@pytest.mark.parametrize(
    "content",
    [
        "`1. Not eligible`\n`9. Funding unknown`\n`---`",
        "> `1. Not eligible`\n> `9. Funding unknown`\n> `---`",
        "[1. Not eligible](https://example.invalid/one)\n"
        "[9. Funding unknown](https://example.invalid/nine)",
    ],
)
def test_inline_presentation_cannot_introduce_automatic_numbering_or_rules(content):
    document = render(content)
    text, root = word_text(document)
    assert "1. Not eligible" in text
    assert "9. Funding unknown" in text
    if "---" in content:
        assert "---" in text
    assert root.find(f".//{{{W}}}numPr") is None
    assert "\n—\n" not in text


@pytest.mark.parametrize(
    "value",
    [
        "snake_case_identifier",
        "A|B",
        r"a\b",
        "<script>Do NOT approve</script>",
        "`embedded`",
        "`starts",
        "ends`",
        " keep both spaces ",
        " leading only",
        "trailing only ",
        "  ",
        "1. Not eligible",
        "---",
    ],
)
def test_literal_inline_code_roundtrips_exact_values_including_spacing(value):
    markup = handover._literal_code(value)
    parsed = inline(markup)
    assert len(parsed) == 1
    assert parsed[0].code and parsed[0].text == value
    transformed = handover._source_inline(markup)
    reparsed = inline(transformed)
    assert len(reparsed) == 1
    assert reparsed[0].code and reparsed[0].text == value
    text, root = word_text(render(markup))
    assert value in text
    assert root.find(f".//{{{W}}}numPr") is None
    assert root.find(f".//{{{W}}}drawing") is None


def test_bullet_continuation_rule_is_not_reinterpreted_after_indentation_removal():
    document = render("- Note:\n\n    ---\n\n    Not approved")
    text, _ = word_text(document)
    assert "---" in text and "Not approved" in text
    assert "\n—\n" not in text


def test_disagreements_remain_separate_sources_without_a_resolved_answer():
    payload = {
        "title": "Venue access",
        "questions": "Is venue access confirmed?\nWhat insurance excess applies?",
        "document_type": "handover",
        "documents": [
            {
                "title": "Earlier reply",
                "content": "Venue access is confirmed.",
                "date": "2026-09-01",
            },
            {
                "title": "Later reply",
                "content": "Venue access is NOT confirmed; ask Jo.",
                "date": "2026-09-30",
            },
        ],
    }
    report = casebooks.build(payload)
    document = report["document_markdown"]
    assert "Earlier reply" in document and "Later reply" in document
    assert "Venue access is confirmed." in document
    assert "Venue access is NOT confirmed; ask Jo." in document
    assert report["question_index"][0]["status"] == "related_wording"
    assert "Related wording — review required:" in document
    assert "The real-world answer remains unknown" in document
    assert "resolved" not in document.lower()


def test_no_selected_wording_does_not_substitute_irrelevant_background_as_an_answer():
    payload = {
        "title": "Insurance",
        "questions": "Insurance excess?",
        "document_type": "handover",
        "documents": [
            {"title": "Menu", "content": "Bring fruit and water."},
        ],
    }
    report = casebooks.build(payload)
    assert not report["excerpts"]
    assert "Bring fruit" not in report["document_markdown"]
    assert "The real-world answer remains unknown" in report["document_markdown"]
    assert "No passages were selected" in report["document_markdown"]
    assert report["coverage"]["unrepresented_documents"] == ["Menu"]


def test_extra_selected_passages_remain_exact_and_explicitly_omitted_from_copy():
    labels = ("azalea", "banksia", "clover", "dahlia", "eucalyptus", "freesia")
    payload = {
        "title": "Access",
        "questions": "Access permission?",
        "document_type": "handover",
        "documents": [
            {
                "title": f"Reply {number}",
                "content": f"Access permission for {label} is not confirmed.",
            }
            for number, label in enumerate(labels)
        ],
    }
    # Multiple independent questions can select more than four passages.
    payload["questions"] = "\n".join(f"{label}?" for label in labels)
    report = casebooks.build(payload)
    assert len(report["excerpts"]) > handover.MAX_NOTES
    extra = len(report["excerpts"]) - handover.MAX_NOTES
    assert (
        f"{extra} additional selected passages are not reproduced in this copy"
        in report["document_markdown"]
    )
    for item in report["excerpts"]:
        assert evidence.literal(item["quote"]) in report["markdown"]


def test_forged_quote_and_unknown_question_reference_are_rejected():
    source, excerpt = passage("An action is not accepted.")
    with pytest.raises(ValueError, match="no longer matches"):
        handover.render(
            "Handover", {}, [source], [replace(excerpt, quote="Approved")], []
        )
    with pytest.raises(ValueError, match="unavailable evidence"):
        handover.render(
            "Handover",
            {},
            [source],
            [excerpt],
            [
                {"question": "Approved?", "excerpt_ids": ["Eforged"]},
            ],
        )
