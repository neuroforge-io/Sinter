"""Word exports retain usable text and native formatting without remote assets."""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest
from test_runtime import post, request, server  # noqa: F401

from sinter import client, evidence
from sinter.document_markup import Paragraph, Table, inline, parse, safe_href
from sinter.docx_export import MAX_MARKDOWN, MIME, REL, R, W, export_docx

NS = {"w": W, "r": R, "rel": REL}
FIXTURE = (
    "# Fictional garden access letter\n\nDear **Jordan**,\n\n"
    "Please keep *all* conditions and snake_case_identifier.\n\n"
    "## Actions\n\n4. Confirm access.\n   1. Ask the coordinator.\n"
    "   2. Record the response.\n5. Share the agreed plan.\n\n"
    "- Bring water.\n- Keep the gate clear.\n\n"
    "| Task | Owner |\n| :---: | ---: |\n"
    "| Keep `a|b` | Sam \\| Jo |\n| Extra | Supplied | Keep this cell |\n\n"
    "Kind regards,\nMaya Chen\nCommunity coordinator\n\n"
    "[Read guidance](https://example.invalid/wiki/Water_(policy)?x=1&amp;y=2)\n\n"
    "```text\n  first line\n\n\n```not-a-closing-fence\nlast line\n```"
)


def package(markdown=FIXTURE, title="Fictional garden access letter"):
    result = export_docx({"title": title, "markdown": markdown})
    archive = zipfile.ZipFile(io.BytesIO(result.content))
    assert archive.testzip() is None
    return result, {
        name: ET.fromstring(archive.read(name)) for name in archive.namelist()
    }


def text(node):
    parts = []
    for item in node.iter():
        if item.tag == f"{{{W}}}t":
            parts.append(item.text or "")
        elif item.tag == f"{{{W}}}br":
            parts.append("\n")
        elif item.tag == f"{{{W}}}tab":
            parts.append("\t")
    return "".join(parts)


def test_native_word_package_opens_has_required_relationships_and_deterministic_bytes():
    result, parts = package()
    assert result.content_type == MIME and result.filename.endswith("-DRAFT.docx")
    assert (
        result.content
        == export_docx(
            {"title": "Fictional garden access letter", "markdown": FIXTURE}
        ).content
    )
    assert set(parts) == {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/styles.xml",
        "word/numbering.xml",
        "word/_rels/document.xml.rels",
        "docProps/core.xml",
    }
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert b'<Types xmlns="' in archive.read("[Content_Types].xml")
        assert b'<Relationships xmlns="' in archive.read("_rels/.rels")
    relationships = parts["_rels/.rels"]
    main = next(
        item for item in relationships if item.attrib["Type"] == f"{R}/officeDocument"
    )
    assert main.attrib["Target"] == "word/document.xml"
    document = parts["word/document.xml"]
    assert document.find("w:body/w:sectPr/w:pgSz", NS) is not None
    assert list(document.find("w:body", NS))[-1].tag == f"{{{W}}}sectPr"
    for element in document.iter():
        assert element.tag not in {
            f"{{{W}}}altChunk",
            f"{{{W}}}object",
            f"{{{W}}}instrText",
            f"{{{W}}}fldSimple",
        }


def test_paragraphs_headings_emphasis_signatures_and_verbatim_code():
    _, parts = package()
    document = parts["word/document.xml"]
    paragraphs = document.findall("w:body/w:p", NS)
    assert paragraphs[0].find("w:pPr/w:pStyle", NS).attrib[f"{{{W}}}val"] == "Title"
    actions = next(item for item in paragraphs if text(item) == "Actions")
    assert actions.find("w:pPr/w:pStyle", NS).attrib[f"{{{W}}}val"] == "Heading2"
    greeting = next(item for item in paragraphs if text(item) == "Dear Jordan,")
    assert (
        text(
            next(
                run
                for run in greeting.findall("w:r", NS)
                if run.find("w:rPr/w:b", NS) is not None
            )
        )
        == "Jordan"
    )
    prose = next(item for item in paragraphs if "snake_case_identifier" in text(item))
    assert (
        text(
            next(
                run
                for run in prose.findall("w:r", NS)
                if run.find("w:rPr/w:i", NS) is not None
            )
        )
        == "all"
    )
    signature = next(
        item for item in paragraphs if text(item).startswith("Kind regards")
    )
    assert text(signature) == "Kind regards,\nMaya Chen\nCommunity coordinator"
    code = next(
        item
        for item in paragraphs
        if item.find("w:pPr/w:pStyle[@w:val='Code']", NS) is not None
    )
    assert text(code) == "  first line\n\n\n```not-a-closing-fence\nlast line"
    assert code.find("w:r/w:rPr/w:rFonts", NS).attrib[f"{{{W}}}ascii"] == "Courier New"


def test_real_ordered_nested_and_bullet_list_definitions_preserve_start_and_levels():
    _, parts = package()
    paragraphs = parts["word/document.xml"].findall("w:body/w:p", NS)
    listed = {
        text(item): item.find("w:pPr/w:numPr", NS)
        for item in paragraphs
        if item.find("w:pPr/w:numPr", NS) is not None
    }
    numbering = parts["word/numbering.xml"]

    def properties(label):
        number = listed[label].find("w:numId", NS).attrib[f"{{{W}}}val"]
        level = listed[label].find("w:ilvl", NS).attrib[f"{{{W}}}val"]
        definition = numbering.find(f"w:num[@w:numId='{number}']", NS)
        abstract_id = definition.find("w:abstractNumId", NS).attrib[f"{{{W}}}val"]
        abstract = numbering.find(
            f"w:abstractNum[@w:abstractNumId='{abstract_id}']", NS
        )
        return number, level, definition, abstract

    number, level, definition, abstract = properties("Confirm access.")
    assert (
        level == "0"
        and definition.find("w:lvlOverride/w:startOverride", NS).attrib[f"{{{W}}}val"]
        == "4"
    )
    assert properties("Share the agreed plan.")[0] == number
    assert abstract.find("w:lvl/w:numFmt", NS).attrib[f"{{{W}}}val"] == "decimal"
    assert properties("Ask the coordinator.")[1] == "1"
    assert (
        properties("Ask the coordinator.")[0] == properties("Record the response.")[0]
    )
    assert (
        properties("Bring water.")[3].find("w:lvl/w:numFmt", NS).attrib[f"{{{W}}}val"]
        == "bullet"
    )
    # OPC schema requires all abstract definitions before concrete numbering.
    tags = [item.tag.rsplit("}", 1)[-1] for item in numbering]
    assert tags == sorted(tags, key=lambda name: name != "abstractNum")


def test_tables_are_editable_keep_all_cells_and_repeat_header():
    _, parts = package()
    table = parts["word/document.xml"].find("w:body/w:tbl", NS)
    rows = table.findall("w:tr", NS)
    assert [[text(cell) for cell in row.findall("w:tc", NS)] for row in rows] == [
        ["Task", "Owner", ""],
        ["Keep a|b", "Sam | Jo", ""],
        ["Extra", "Supplied", "Keep this cell"],
    ]
    assert rows[0].find("w:trPr/w:tblHeader", NS) is not None
    assert all(row.find("w:trPr/w:cantSplit", NS) is not None for row in rows)
    assert [
        cell.find("w:p/w:pPr/w:jc", NS).attrib[f"{{{W}}}val"]
        for cell in rows[0].findall("w:tc", NS)
    ] == ["center", "right", "left"]


def test_links_are_click_targets_only_and_dangerous_markup_is_literal():
    hostile = (
        '<script>alert("bad")</script>\n'
        "![remote image](https://example.invalid/never-fetch.png)\n"
        "[bad](javascript:alert(1)) [private](https://user:pass@example.invalid)"
    )
    with (
        patch.object(client, "_get", side_effect=AssertionError("No remote load")),
        patch.object(client, "_post", side_effect=AssertionError("No model call")),
    ):
        _, parts = package(FIXTURE + "\n\n" + hostile)
    document = parts["word/document.xml"]
    assert '<script>alert("bad")</script>' in text(document)
    assert "![remote image](https://example.invalid/never-fetch.png)" in text(document)
    assert "[bad](javascript:alert(1))" in text(document)
    assert "[private](https://user:pass@example.invalid)" in text(document)
    rels = [
        item
        for item in parts["word/_rels/document.xml.rels"]
        if item.attrib.get("TargetMode") == "External"
    ]
    assert all(item.attrib["Type"] == f"{R}/hyperlink" for item in rels)
    assert any(
        item.attrib["Target"] == "https://example.invalid/wiki/Water_(policy)?x=1&y=2"
        for item in rels
    )
    assert all("never-fetch" not in item.attrib["Target"] for item in rels)
    assert document.find(".//w:drawing", NS) is None


def test_quoted_source_unicode_and_metadata_are_exact_and_only_explicit():
    source = "**literal** and `code` <tag> & entities &lt; — café_name_label 🌿."
    _, parts = package("> " + evidence.literal(source), title='Fictional "title" <tag>')
    assert text(parts["word/document.xml"]) == source
    assert parts["word/document.xml"].find(".//w:b", NS) is None
    core = ET.tostring(parts["docProps/core.xml"], encoding="unicode")
    assert "Sinter" in core and "&lt;tag&gt;" in core
    assert "lastModifiedBy" not in core and "created" not in core


def test_angle_delimited_campaign_links_preserve_nested_parentheses_and_safety():
    _, parts = package(
        "[Programme details](<https://example.invalid/fund_(round_(one))?a=1&amp;b=2>)\n\n[Unsafe](<javascript:alert(1)>)"
    )
    rels = [
        item
        for item in parts["word/_rels/document.xml.rels"]
        if item.attrib.get("TargetMode") == "External"
    ]
    assert [item.attrib["Target"] for item in rels] == [
        "https://example.invalid/fund_(round_(one))?a=1&b=2"
    ]
    assert (
        text(parts["word/document.xml"])
        == "Programme details[Unsafe](<javascript:alert(1)>)"
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"title": "X"},
        {"title": "X", "markdown": "Y", "profile": {}},
        {"title": "", "markdown": "Y"},
        {"title": "X" * 201, "markdown": "Y"},
        {"title": "X\nY", "markdown": "Z"},
        {"title": "X", "markdown": " "},
        {"title": "X", "markdown": "Y" * (MAX_MARKDOWN + 1)},
        {"title": "X", "markdown": "Y\x00Z"},
        {"title": "X", "markdown": "\ud800"},
    ],
)
def test_bad_exports_fail_clearly_before_creating_a_document(payload):
    with pytest.raises(ValueError):
        export_docx(payload)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https:example.invalid",
        "//example.invalid",
        "https://example.invalid:0",
        "https://user:pass@example.invalid",
        "https://example.invalid/with space",
        "https://example.invalid/\u202ehidden",
        "https://example.invalid/\\bad",
    ],
)
def test_href_validation_never_interprets_unsafe_target(url):
    assert safe_href(url) is None


def test_parser_has_bounded_nested_markup_and_preserves_malformed_text():
    assert "".join(span.text for span in inline("[" * 50000)) == "[" * 50000
    blocks = parse(
        "- Parent\n  - Child\n\n    Continued child paragraph.\n\n- Next\n\nTail"
    )
    assert all(isinstance(item, Paragraph) for item in blocks)
    assert "Continued child paragraph." in "\n".join(
        span.text for item in blocks for span in item.spans
    )
    assert parse("| One |\n| --- |\n| Two |")[0].rows[1][0][0].text == "Two"
    assert isinstance(parse("| One |\n| --- |\n| Two |")[0], Table)


def test_real_http_download_is_authenticated_local_and_retains_explicit_text(server):  # noqa: F811
    payload = {"title": "Fictional café letter", "markdown": FIXTURE}
    assert post(server, "/api/documents/docx", payload, token=False)[0] == 403
    with (
        patch.object(client, "chat", side_effect=AssertionError("No model call")),
        patch.object(client, "search", side_effect=AssertionError("No search")),
    ):
        code, headers, raw = post(server, "/api/documents/docx", payload)
    assert code == 200 and headers["Content-Type"] == MIME
    assert headers["Content-Disposition"].startswith(
        "attachment; filename*=UTF-8''sinter-Fictional%20caf%C3%A9"
    )
    assert headers["Cache-Control"] == "no-store"
    assert zipfile.ZipFile(io.BytesIO(raw)).testzip() is None
    assert server.app.store.reports() == []
    code, _, body = post(server, "/api/documents/docx", {"title": "X", "markdown": ""})
    assert code == 400 and "Document text" in json.loads(body)["error"]
    headers = {
        "Content-Type": "application/json",
        "X-Sinter-Token": server.app.token,
        "Origin": "https://evil.example",
    }
    assert (
        request(server, "/api/documents/docx", "POST", json.dumps(payload), headers)[0]
        == 403
    )
