"""Summary-only Word widths preserve content and fail closed outside its shape."""

from __future__ import annotations

import io
from copy import deepcopy
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from sinter.document_markup import parse
from sinter.docx_export import W, _handover_summary_table_widths, export_docx

NS = {"w": W}
INTRO = (
    "Statuses and next steps below are user-entered for review. Next steps are "
    "proposals, not accepted commitments. A retained quotation establishes "
    "supplied wording, not independent verification."
)
STALE = (
    "**Review status: stale.** Review this saved record again before current use. "
    "Original evidence and historical wording remain unchanged; "
    "no current source was substituted."
)
HEADER = "| Item | Recorded status — user-entered | Next step — proposed | Evidence |"
TABLE = (
    HEADER + "\n| --- | --- | --- | --- |\n"
    "| Equipment café 🌿 | As recorded: quote unknown; owner: Unassigned; "
    "target: 9 October (unconfirmed proposal, not a funder deadline) | "
    "Ask for a quote; no order approved. | Passage 1 |\n"
    "| Insurance | Historical wording: answer not recorded; owner: Unknown | "
    "Ask; role: treasurer — acceptance unconfirmed. | "
    "No retained quotation selected; missing answer. |"
)
OPENING = "## At a glance\n\n" + INTRO + "\n\n" + TABLE
APPENDIX = (
    "\n\n## Selected source wording\n\n### Passage 1\n\n"
    "> Original source: Fictional café source\n\n"
    "> Exact café 🌿 é | words remain as supplied.\n\n"
    "> | Task | Owner |\n> | --- | --- |\n> | Keep full wording | Unknown |\n\n"
    "## Passage reference key\n\n"
    "These short labels refer to the exact selected excerpts. Offsets count "
    "Unicode code points from zero. The start is included; the end is excluded. "
    "Selection does not establish a verified answer.\n\n"
    "> **Passage 1** — Original source: Fictional café source\n"
    "> Excerpt ID: `Eaaaaaaaaaaaaaaaa`; source ID: `Saaaaaaaaaaaaaaaa`.\n"
    "> Unicode characters: 0–44; quoted above.\n\n"
    "[Original supplied link](https://example.invalid/note?x=1&y=2)"
)
DOCUMENT = "# Fictional handover\n\n" + OPENING + APPENDIX


def parts(markdown=DOCUMENT, *, generic=False):
    if generic:
        with patch(
            "sinter.docx_export._handover_summary_table_widths", return_value={}
        ):
            data = export_docx(
                {"title": "Fictional handover", "markdown": markdown}
            ).content
    else:
        data = export_docx(
            {"title": "Fictional handover", "markdown": markdown}
        ).content
    with ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def document(parts):
    return ET.fromstring(parts["word/document.xml"])


def without_widths(node):
    node = deepcopy(node)
    for table in node.findall(".//w:tbl", NS):
        properties = table.find("w:tblPr", NS)
        for tag in ("tblW", "tblLayout"):
            for child in list(properties.findall("w:" + tag, NS)):
                properties.remove(child)
        grid = table.find("w:tblGrid", NS)
        table.remove(grid)
        for cell in table.findall("w:tr/w:tc", NS):
            cell_properties = cell.find("w:tcPr", NS)
            cell_properties.remove(cell_properties.find("w:tcW", NS))
    return ET.tostring(node)


def test_generated_summary_uses_only_its_fixed_widths_and_keeps_editable_rows():
    output = document(parts())
    tables = output.findall("w:body/w:tbl", NS)
    assert len(tables) == 2
    summary = tables[0]
    assert summary.find("w:tblPr/w:tblW", NS).attrib == {
        f"{{{W}}}w": "9360",
        f"{{{W}}}type": "dxa",
    }
    assert summary.find("w:tblPr/w:tblLayout", NS).get(f"{{{W}}}type") == "fixed"
    assert [
        int(node.get(f"{{{W}}}w"))
        for node in summary.findall("w:tblGrid/w:gridCol", NS)
    ] == [1560, 4200, 2280, 1320]
    for index, row in enumerate(summary.findall("w:tr", NS)):
        assert row.find("w:trPr/w:cantSplit", NS) is not None
        assert (row.find("w:trPr/w:tblHeader", NS) is not None) == (index == 0)
        assert [
            int(node.get(f"{{{W}}}w")) for node in row.findall("w:tc/w:tcPr/w:tcW", NS)
        ] == [1560, 4200, 2280, 1320]
        assert not row.findall(".//w:keepNext", NS)
    assert tables[1].find("w:tblPr/w:tblLayout", NS) is None
    assert [
        int(node.get(f"{{{W}}}w"))
        for node in tables[1].findall("w:tblGrid/w:gridCol", NS)
    ] == [4680, 4680]


def test_full_content_fonts_links_unicode_bookmarks_and_other_parts_are_unchanged():
    before, after = parts(generic=True), parts()
    assert set(before) == set(after)
    for name in before.keys() - {"word/document.xml"}:
        assert before[name] == after[name]
    old, new = document(before), document(after)
    assert without_widths(old) == without_widths(new)
    assert ET.tostring(old.findall("w:body/w:tbl", NS)[1]) == ET.tostring(
        new.findall("w:body/w:tbl", NS)[1]
    )
    assert len(new.findall(".//w:bookmarkStart", NS)) == 2
    assert new.findall(".//w:hyperlink[@w:anchor]", NS)
    wording = "".join(node.text or "" for node in new.findall(".//w:t", NS))
    for exact in [
        "Unknown",
        "Unassigned",
        "Historical wording",
        "acceptance unconfirmed",
        "not a funder deadline",
        "No retained quotation selected; missing answer.",
        "café 🌿 é",
        "Eaaaaaaaaaaaaaaaa",
        "Saaaaaaaaaaaaaaaa",
        "Unicode characters: 0–44",
    ]:
        assert exact in wording


@pytest.mark.parametrize("stale", [False, True])
def test_exact_optional_stale_notice_and_windows_newlines_keep_scoped_layout(stale):
    body = DOCUMENT.replace(
        INTRO + "\n\n", INTRO + "\n\n" + (STALE + "\n\n" if stale else ""), 1
    ).replace("\n", "\r\n")
    widths = _handover_summary_table_widths(body, parse(body))
    assert list(widths.values()) == [(1560, 4200, 2280, 1320)]
    assert without_widths(document(parts(body))) == without_widths(
        document(parts(body, generic=True))
    )


@pytest.mark.parametrize(
    "body",
    [
        "\n".join("> " + line for line in OPENING.splitlines()),
        "\n".join("> > " + line for line in OPENING.splitlines()),
        "- Nested material\n\n"
        + "\n".join("  " + line for line in OPENING.splitlines()),
        "```text\n" + OPENING + "\n```",
        OPENING + "\n\n" + OPENING,
        OPENING.replace(INTRO, "Changed introductory claim"),
        OPENING.replace("## At a glance", "### At a glance"),
        OPENING.replace("Recorded status — user-entered", "Status"),
        OPENING.replace(
            HEADER,
            "| Evidence | Item | Recorded status — user-entered | Next step — proposed |",
        ),
        OPENING.replace("Evidence |", "Evidence | Extra |", 1),
        OPENING.replace(INTRO + "\n\n", INTRO + "\n\nAn intervening paragraph.\n\n"),
        OPENING.replace(
            INTRO + "\n\n",
            INTRO
            + "\n\n"
            + STALE.replace("no current source", "a current source")
            + "\n\n",
        ),
        OPENING.replace("| --- | --- | --- | --- |", "not a table separator"),
        OPENING.replace(INTRO, "**" + INTRO + "**"),
    ],
)
def test_changed_quoted_nested_or_ambiguous_openings_retain_exact_generic_output(body):
    assert _handover_summary_table_widths(body, parse(body)) == {}
    assert parts(body) == parts(body, generic=True)


def test_large_user_wording_and_many_rows_are_complete_without_page_fit_guarantee():
    wording = ("Long supplied café 🌿 é and escaped \\| pipe — " * 20).rstrip()
    rows = "\n".join(
        f"| Item {number} | {wording} | Proposed action — no accepted commitment | Missing answer; no quotation |"
        for number in range(12)
    )
    body = (
        "# Fictional long handover\n\n## At a glance\n\n"
        + INTRO
        + "\n\n"
        + HEADER
        + "\n| --- | --- | --- | --- |\n"
        + rows
    )
    output = document(parts(body))
    table = output.find("w:body/w:tbl", NS)
    assert len(table.findall("w:tr", NS)) == 13
    assert without_widths(output) == without_widths(document(parts(body, generic=True)))
    assert sum(len(node.text or "") for node in table.findall(".//w:t", NS)) > 9_000
    assert all(
        row.find("w:trPr/w:cantSplit", NS) is not None
        for row in table.findall("w:tr", NS)
    )
