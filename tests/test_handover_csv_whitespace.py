"""CSV presentation preserves literal cell boundaries in typed and Word tables."""

from __future__ import annotations

import csv
import io
import zipfile
from xml.etree import ElementTree as ET

import pytest

from sinter import evidence, handover
from sinter.document_markup import Paragraph, Table, parse
from sinter.docx_export import W, export_docx


def csv_content(rows: list[list[str]]) -> str:
    output = io.StringIO(newline="")
    csv.writer(output).writerows(rows)
    return output.getvalue()


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(
        node.text or ""
        if node.tag == f"{{{W}}}t"
        else "\t"
        if node.tag == f"{{{W}}}tab"
        else "\n"
        if node.tag == f"{{{W}}}br"
        else ""
        for node in paragraph.iter()
    )


@pytest.mark.parametrize(
    "headers,record",
    [
        (["Action", "Owner", "Notes"], ["Review", "  Casey  ", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", "Casey  ", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", "  Casey", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", "   ", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", "\t", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", "Casey\tLee", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", "\tCasey\t", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", " Casey | Lee ", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", "  ``Casey|Lee``  ", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", " `Casey` ", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", " Casey\\|`Lee` ", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", "\u00a0Casey\u00a0", "Unknown"]),
        (["Action", "Owner", "Notes"], ["Review", "Casey  Lee", "Unknown"]),
        pytest.param(
            ["Action", "Owner", "Notes"],
            ["Review", " Casey\\", "Unknown"],
            id="trailing-backslash",
        ),
        pytest.param(
            ["Action", "Owner", "Notes"],
            ["Review", "\t`Casey|Lee`\\", "Unknown"],
            id="trailing-backslash-with-tab-pipe-ticks",
        ),
        (["  Action  ", "\tOwner\t", " Notes "], ["Review", "", "Unknown"]),
        (["Action", "Owner", "  Notes|`literal`  "], ["Review", "", "Unknown"]),
        (["Action", "Owner", " Notes\\"], ["Review", "", "Unknown"]),
    ],
)
def test_csv_whitespace_cells_survive_render_parse_and_word(
    headers: list[str], record: list[str]
) -> None:
    content = csv_content([headers, record])
    source = evidence.source("actions.csv", content)
    excerpt = evidence.Excerpt("Ewhitespace", source.id, 0, len(content), content)
    original = (source, excerpt)
    document = handover.render(
        "Unconfirmed handover",
        {},
        [source],
        [excerpt],
        [{"question": "Who has accepted?", "excerpt_ids": [excerpt.id]}],
    )
    expected = [headers, [cell if cell else "—" for cell in record]]
    tables = [block for block in parse(document) if isinstance(block, Table)]
    assert len(tables) == 1
    assert [
        ["".join(span.text for span in cell) for cell in row] for row in tables[0].rows
    ] == expected
    word = export_docx({"title": "Unconfirmed handover", "markdown": document})
    with zipfile.ZipFile(io.BytesIO(word.content)) as archive:
        assert archive.testzip() is None
        root = ET.fromstring(archive.read("word/document.xml"))
    word_tables = root.findall(f".//{{{W}}}tbl")
    assert len(word_tables) == 1
    assert [
        [
            "".join(paragraph_text(p) for p in cell.findall(f"{{{W}}}p"))
            for cell in row.findall(f"{{{W}}}tc")
        ]
        for row in word_tables[0].findall(f"{{{W}}}tr")
    ] == expected
    assert (source, excerpt) == original
    assert source.content == excerpt.quote == content
    assert evidence.validate_excerpt(excerpt, [source])
    assert f"source ID: `{source.id}`" in document
    assert f"Excerpt ID: `{excerpt.id}`" in document
    assert f"Unicode characters: 0–{len(content)};" in document
    assert "A wording match is not an answer" in document
    assert "entries do not confirm assignments or dates" in document


@pytest.mark.parametrize(
    "label,value",
    [
        ("  Owner  ", "  Casey  "),
        ("Owner", "   "),
        ("Owner", "\tCasey|``Lee``\t"),
        ("Owner", " Casey\\"),
        ("  Owner|`literal`  ", "  Casey  "),
    ],
)
def test_multiline_records_keep_other_literal_single_line_fields(
    label: str, value: str
) -> None:
    content = csv_content(
        [["Action", label, "Notes"], ["Review", value, "Not approved\nNo one accepted"]]
    )
    source = evidence.source("actions.csv", content)
    excerpt = evidence.Excerpt("Emultiline", source.id, 0, len(content), content)
    document = handover.render("Unconfirmed handover", {}, [source], [excerpt], [])
    assert not any(isinstance(block, Table) for block in parse(document))
    expected = f"{label}: {value}"
    assert any(
        "".join(span.text for span in block.spans) == expected
        for block in parse(document)
        if isinstance(block, Paragraph)
    )
    word = export_docx({"title": "Unconfirmed handover", "markdown": document})
    with zipfile.ZipFile(io.BytesIO(word.content)) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    assert expected in [paragraph_text(p) for p in root.iter(f"{{{W}}}p")]
    assert "Not approved\nNo one accepted" in [
        paragraph_text(p) for p in root.iter(f"{{{W}}}p")
    ]
    assert source.content == excerpt.quote == content
    assert evidence.validate_excerpt(excerpt, [source])


@pytest.mark.parametrize("blank_header", ["   ", "\t"])
def test_whitespace_only_header_keeps_complete_literal_csv(blank_header: str) -> None:
    content = csv_content([["Action", "Owner", blank_header], ["Review", "Casey", " "]])
    source = evidence.source("actions.csv", content)
    excerpt = evidence.Excerpt("Eunlabelled", source.id, 0, len(content), content)
    assert handover._csv_rows(source, excerpt) is None
    document = handover.render("Unconfirmed handover", {}, [source], [excerpt], [])
    blocks = parse(document)
    assert not any(isinstance(block, Table) for block in blocks)
    normalized = content.replace("\r\n", "\n")
    assert any(
        block.code and "".join(span.text for span in block.spans) == normalized
        for block in blocks
        if isinstance(block, Paragraph)
    )
    word = export_docx({"title": "Unconfirmed handover", "markdown": document})
    with zipfile.ZipFile(io.BytesIO(word.content)) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    assert normalized in [paragraph_text(p) for p in root.iter(f"{{{W}}}p")]
    assert source.content == excerpt.quote == content
    assert evidence.validate_excerpt(excerpt, [source])


def test_ordinary_csv_cells_keep_existing_literal_table_markup() -> None:
    rows = [
        ["Action", "Owner", "Notes"],
        ["Review", "Unassigned", "not_started"],
        ["Ask | Jo", "`raw`", "No formula =1+1"],
    ]
    assert handover._csv_quote(rows) == (
        "> | Action | Owner | Notes |\n"
        "> | --- | --- | --- |\n"
        "> | Review | Unassigned | not\\_started |\n"
        "> | Ask \\| Jo | \\`raw\\` | No formula =1+1 |"
    )
