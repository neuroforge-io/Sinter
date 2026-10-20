"""New editable handover sections preserve literal fields and original destinations."""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from sinter.docx_export import W, export_docx
from test_handover_summary import node
from test_runtime import server  # noqa: F401

NS = {"w": W}
LABELS = ("Next step — proposed", "Evidence", "Recorded status — user-entered",
          "Wording period", "Responsibility", "Timing")


@pytest.fixture(scope="module")
def generated():
    return json.loads(node("tests/handover_summary.mjs", "--sample-json"))


def literal(value):
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"[\\\x60*_{}\[\]#!|]", lambda match: "\\" + match[0], value)


def exported(markdown):
    value = export_docx({"title": "Fictional retained handover", "markdown": markdown})
    with zipfile.ZipFile(io.BytesIO(value.content)) as archive:
        assert archive.testzip() is None
        parts = {name: archive.read(name) for name in archive.namelist()}
    return ET.fromstring(parts["word/document.xml"]), parts


def wording(element):
    return "".join(node.text or "" for node in element.iter(f"{{{W}}}t"))


def summary_groups(document):
    paragraphs = document.find("w:body", NS).findall("w:p", NS)
    groups = []
    for index, paragraph in enumerate(paragraphs):
        style = paragraph.find("w:pPr/w:pStyle", NS)
        if (style is not None and style.get(f"{{{W}}}val") == "Heading3"
                and wording(paragraph).startswith("Summary item ")):
            groups.append(paragraphs[index:index + 7])
    return groups


def test_actual_compiler_preserves_original_table_and_native_evidence_destinations(generated):
    report = generated["applied"]
    markdown = report["document_edits"]["markdown"]
    document, parts = exported(markdown)
    original, _ = exported(generated["original"]["document_markdown"])
    assert [ET.tostring(table) for table in document.iter(f"{{{W}}}tbl")] == [
        ET.tostring(table) for table in original.iter(f"{{{W}}}tbl")
    ]
    groups = summary_groups(document)
    assert len(groups) == 6
    bookmarks = {node.get(f"{{{W}}}name") for node in document.iter(f"{{{W}}}bookmarkStart")}
    assert len(bookmarks) == 8
    assert {"word/header1.xml", "word/footer1.xml"} <= parts.keys()
    for index, group in enumerate(groups):
        assert len(group) == 7
        assert all(wording(group[field + 1]).startswith(label + ": ")
                   for field, label in enumerate(LABELS))
        links = group[2].findall("w:hyperlink", NS)
        if index < 5:
            expected = generated["quotations"][index]["label"]
            assert len(links) == 1 and wording(links[0]) == expected
            anchor = links[0].get(f"{{{W}}}anchor")
            assert anchor == "SinterPassage" + expected.split()[1]
            assert anchor in bookmarks
            assert set(links[0].attrib) == {f"{{{W}}}anchor"}
        else:
            assert not links
    assert wording(groups[1][5]) == "Responsibility: Unassigned; no owner has been recorded"
    assert wording(groups[0][5]) == "Responsibility: Owner type unknown; acceptance unconfirmed"
    assert wording(groups[4][4]) == "Wording period: Historical wording"


def test_literal_unicode_entities_and_edge_spacing_survive_export_and_anchor_mapping(generated):
    markdown = generated["applied"]["document_edits"]["markdown"]
    item = "  Equipment  café 🐝 ; : &lt; [keep]| *  "
    status = "  Missing  &amp; &lt; e\u0301 🐝 \x60*\\  "
    action = "  Ask  about <&>| and literal punctuation.  "
    owner = "Named person: Example: family; role  retained  ; acceptance unconfirmed"
    markdown = markdown.replace("### Summary item 1: Equipment quote",
                                "### Summary item 1: " + literal(item))
    markdown = markdown.replace("**Summary item 1: Equipment quote**",
                                "**Summary item 1: " + literal(item) + "**")
    markdown = markdown.replace("**Recorded status — user-entered:** Not received",
                                "**Recorded status — user-entered:** " + literal(status), 1)
    markdown = markdown.replace(
        "**Next step — proposed:** Obtain an itemised quote and confirm a named owner",
        "**Next step — proposed:** " + literal(action), 1)
    markdown = markdown.replace(
        "**Responsibility:** Owner type unknown; acceptance unconfirmed",
        "**Responsibility:** " + literal(owner), 1)
    document, _ = exported(markdown)
    first = summary_groups(document)[0]
    assert wording(first[0]) == "Summary item 1: " + item
    assert wording(first[1]) == LABELS[0] + ": " + action
    assert wording(first[3]) == LABELS[2] + ": " + status
    assert wording(first[5]) == "Responsibility: " + owner
    assert all(node.get("{http://www.w3.org/XML/1998/namespace}space") == "preserve"
               for node in first[3].iter(f"{{{W}}}t"))
    assert first[2].find("w:hyperlink", NS).get(f"{{{W}}}anchor") == "SinterPassage1"


@pytest.mark.parametrize("change", [
    lambda text: text.replace("### Summary item 2:", "### Summary item 1:"),
    lambda text: text.replace("### Summary item 2:", "### Summary item 3:"),
    lambda text: text.replace("**Timing:** Proposed target not supplied",
                              "**Timing:** Confirmed deadline tomorrow", 1),
    lambda text: text.replace("**Responsibility:** Owner type unknown; acceptance unconfirmed",
                              "**Responsibility:** Jane confirmed", 1),
    lambda text: text.replace("**Recorded status — user-entered:** Not received",
                              "**Recorded status — user-entered:** **Not received**", 1),
    lambda text: text.replace("**Summary item 1: Equipment quote** — Passage 1",
                              "**Summary item 1: Equipment quote** — Passage 2"),
    lambda text: text.replace("**Evidence coverage:**", "**Edited coverage:**"),
    lambda text: text.replace("**Evidence:** Passage 1",
                              "**Evidence:** Passage 1\n\nExtra literal human note.", 1),
])
def test_later_malformed_fields_or_caption_disable_all_optional_opening_polish(generated, change):
    markdown = change(generated["applied"]["document_edits"]["markdown"])
    document, parts = exported(markdown)
    assert "word/header1.xml" not in parts and "word/footer1.xml" not in parts
    for group in summary_groups(document):
        assert not group[2].findall("w:hyperlink", NS)
    styles = ET.fromstring(parts["word/styles.xml"])
    assert not any(style.get(f"{{{W}}}styleId") == "SummaryQuote"
                   for style in styles.findall("w:style", NS))
    assert "Handover next steps" in wording(document)
    assert "Passage reference key" in wording(document)


@pytest.mark.parametrize("change", [
    lambda text: text.replace("## Passage reference key", "### Passage reference key"),
    lambda text: re.sub(r"Unicode characters: \d+–\d+;", "Unicode characters: 0–0;", text),
])
def test_unadmitted_reference_key_cannot_gain_new_summary_navigation(generated, change):
    document, _ = exported(change(generated["applied"]["document_edits"]["markdown"]))
    for group in summary_groups(document):
        assert not group[2].findall("w:hyperlink", NS)


def test_duplicate_passage_heading_uses_only_the_existing_reference_fallback(generated):
    markdown = generated["applied"]["document_edits"]["markdown"]
    markdown += "\n\n### Passage 1\n\nHuman-added duplicate; no original quote destination."
    document, _ = exported(markdown)
    for group in summary_groups(document)[:5]:
        link = group[2].find("w:hyperlink", NS)
        assert link is not None
        assert link.get(f"{{{W}}}anchor") == "SinterReference1"
    assert all(node.get(f"{{{W}}}name") != "SinterPassage1"
               for node in document.iter(f"{{{W}}}bookmarkStart"))


def test_long_fields_flow_without_chaining_status_owner_or_the_next_item(generated):
    markdown = generated["applied"]["document_edits"]["markdown"]
    status = "x" * 1000
    markdown = markdown.replace("**Recorded status — user-entered:** Not received",
                                "**Recorded status — user-entered:** " + status, 1)
    document, _ = exported(markdown)
    group = summary_groups(document)[0]
    assert wording(group[3]) == LABELS[2] + ": " + status
    for paragraph in group[2:]:
        assert paragraph.find("w:pPr/w:keepNext", NS) is None
        assert paragraph.find("w:pPr/w:keepLines", NS) is None


def test_new_module_is_served_as_a_local_asset(server):
    from test_runtime import request
    status, headers, body = request(server, "/static/handover-opening-format.js")
    assert status == 200
    assert "javascript" in headers["Content-Type"]
    assert body == (Path(__file__).resolve().parents[1] / "src/sinter/web/handover-opening-format.js").read_bytes()
    assert b"parseHandoverOpening" in body


@pytest.mark.parametrize("value, accepted", [
    ("🐝" * 500, True), ("🐝" * 501, False), ("x" * 1001, False),
])
def test_word_admission_matches_javascript_utf16_field_boundaries(generated, value, accepted):
    markdown = generated["applied"]["document_edits"]["markdown"].replace(
        "**Recorded status — user-entered:** Not received",
        "**Recorded status — user-entered:** " + literal(value), 1)
    document, parts = exported(markdown)
    assert ("word/header1.xml" in parts) is accepted
    assert wording(summary_groups(document)[0][3]) == LABELS[2] + ": " + value


def test_repeated_passage_selection_keeps_both_item_bindings_and_original_destination():
    value = json.loads(node("tests/handover_summary.mjs", "--sample-json", "--repeated-passage"))
    document, parts = exported(value["applied"]["document_edits"]["markdown"])
    assert "word/header1.xml" in parts
    assert [entry["label"] for entry in value["quotations"][:2]] == ["Passage 1", "Passage 1"]
    assert value["quotations"][0]["quote"] == value["quotations"][1]["quote"]
    groups = summary_groups(document)
    for group in groups[:2]:
        links = group[2].findall("w:hyperlink", NS)
        assert len(links) == 1 and links[0].get(f"{{{W}}}anchor") == "SinterPassage1"
    assert "Summary item 2: Funding checks — Passage 1" in wording(document)


@pytest.mark.parametrize("before, after", [
    ("**Recorded status — user-entered:** Not received",
     "**Recorded status — user-entered:** \ufeff \ufeff"),
    ("**Responsibility:** Owner type unknown; acceptance unconfirmed",
     "**Responsibility:** Named person: \ufeff \ufeff; acceptance unconfirmed"),
    ("**Responsibility:** Owner type unknown; acceptance unconfirmed",
     "**Responsibility:** Suggested role: \ufeff \ufeff; acceptance unconfirmed"),
])
def test_blank_looking_bom_only_fields_keep_generic_word_fallback(generated, before, after):
    markdown = generated["applied"]["document_edits"]["markdown"].replace(before, after, 1)
    document, parts = exported(markdown)
    assert "word/header1.xml" not in parts
    assert all(not group[2].findall("w:hyperlink", NS) for group in summary_groups(document))


def test_empty_selected_quote_refuses_only_new_opening_polish(generated):
    quote = generated["quotations"][0]["quote"]
    markdown = generated["applied"]["document_edits"]["markdown"].replace(
        "> " + quote, "> ", 1)
    document, parts = exported(markdown)
    assert "word/header1.xml" not in parts
    assert all(not group[2].findall("w:hyperlink", NS) for group in summary_groups(document))


def test_zipapp_carries_the_exact_new_local_module(tmp_path):
    from tools.build_zipapp import build

    root = Path(__file__).resolve().parents[1]
    output = build(tmp_path / "sinter.pyz")
    with zipfile.ZipFile(output) as archive:
        assert archive.read("sinter/web/handover-opening-format.js") == (
            root / "src/sinter/web/handover-opening-format.js").read_bytes()
