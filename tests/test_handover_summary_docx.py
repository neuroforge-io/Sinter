"""Summary-only Word widths preserve content and fail closed outside its shape."""

from __future__ import annotations

import io
import re
from copy import deepcopy
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from sinter.document_markup import parse
from sinter.docx_export import (
    MAX_MARKDOWN,
    REL,
    R,
    W,
    _handover_summary_table_widths,
    export_docx,
)

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
            "| Evidence | Item | Recorded status — user-entered | "
            "Next step — proposed |",
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
        f"| Item {number} | {wording} | Proposed action — no accepted commitment "
        "| Missing answer; no quotation |"
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


COVERAGE = (
    "**Evidence coverage:** this opening uses selected wording from this saved "
    "report. The unchanged checklist and selected evidence follow. This is not "
    "full supplied history; request the matching original project backup for "
    "unselected text. Later project or campaign changes are not included."
)
CHECKLIST = (
    "## Handover next steps\n\n"
    "Review each question against its related wording, then record the confirmed "
    "response and who will follow it up. A wording match is not an answer; "
    "no owner or target date is assigned by this checklist."
)


def qualified_body(quotes=("The quote has not arrived. café 🌿", "Answer unknown.")):
    """A literal generated shape is layout input, never verified source evidence."""
    rows, pairs = [], []
    for number, quote in enumerate(quotes, 1):
        rows.append(
            f"| Item {number} | As recorded: unknown.; Unassigned; target not supplied "
            "| Ask, without committing. | Passage 1 |"
        )
        longest = max((len(run) for run in re.findall(r"`+", quote)), default=0)
        fence = "`" * max(3, longest + 1)
        pairs.append(
            f"**Summary item {number}: Item {number}** — Passage 1\n\n"
            f"> {fence}text\n> " + quote.replace("\n", "\n> ") + f"\n> {fence}"
        )
    return (
        "# Fictional handover\n\n"
        "Source-only handover checklist — review before using.\n\n"
        "## At a glance\n\n"
        + INTRO
        + "\n\n"
        + HEADER
        + "\n| --- | --- | --- | --- |\n"
        + "\n".join(rows)
        + "\n\n"
        + COVERAGE
        + "\n\n### Wording selected for this summary\n\n"
        + "\n\n".join(pairs)
        + "\n\n"
        + CHECKLIST
        + APPENDIX
    )


def unpolished_parts(body):
    with patch(
        "sinter.docx_export._handover_summary_presentation",
        return_value=(False, frozenset(), frozenset()),
    ):
        return parts(body)


def wording(node):
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


def test_short_summary_quote_section_stays_together_without_chaining_the_checklist():
    body = qualified_body()
    before, after = unpolished_parts(body), parts(body)
    old, new = document(before), document(after)
    assert [wording(p) for p in old.findall(".//w:p", NS)] == [
        wording(p) for p in new.findall(".//w:p", NS)
    ]
    # Stored historical edited punctuation is literal; the exporter cannot fix it.
    assert wording(new).count("unknown.;") == 2
    paragraphs = new.findall("w:body/w:p", NS)
    start = next(
        i
        for i, p in enumerate(paragraphs)
        if wording(p) == "Wording selected for this summary"
    )
    group = paragraphs[start : start + 5]
    assert all(p.find("w:pPr/w:keepNext", NS) is not None for p in group[:-1])
    assert group[-1].find("w:pPr/w:keepNext", NS) is None
    for quote in (group[2], group[4]):
        assert quote.find("w:pPr/w:pStyle", NS).get(f"{{{W}}}val") == "SummaryQuote"
        assert quote.find("w:pPr/w:keepLines", NS) is not None
        assert quote.find("w:r/w:rPr/w:rFonts", NS) is None
    old_tail = list(old.find("w:body", NS))
    new_tail = list(new.find("w:body", NS))
    first = next(
        i for i, block in enumerate(new_tail) if wording(block) == "Handover next steps"
    )
    assert [ET.tostring(block) for block in old_tail[first:-1]] == [
        ET.tostring(block) for block in new_tail[first:-1]
    ]
    assert ET.tostring(old.findall("w:body/w:tbl", NS)[0]) == ET.tostring(
        new.findall("w:body/w:tbl", NS)[0]
    )
    styles = ET.fromstring(after["word/styles.xml"])
    summary_style = styles.find("w:style[@w:styleId='SummaryQuote']", NS)
    assert summary_style.find("w:rPr/w:sz", NS).get(f"{{{W}}}val") == "22"
    assert summary_style.find("w:rPr/w:color", NS).get(f"{{{W}}}val") == "172C40"
    assert summary_style.find("w:pPr/w:shd", NS) is None


@pytest.mark.parametrize(
    "quote",
    [
        "  retained leading and repeated  spaces  ",
        "return `café|🐝` if <flag> else {value} \\",
        "\tif <flag>:\n    return `café|🐝`  # **literal**\n\nlast line",
    ],
)
def test_sensitive_summary_quotes_keep_literal_code_whitespace_and_generic_code(quote):
    body = qualified_body((quote,)) + "\n\n```python\n  raw_code()\n```"
    old, new = document(unpolished_parts(body)), document(parts(body))
    assert wording(old) == wording(new)
    paragraph = next(p for p in new.findall("w:body/w:p", NS) if wording(p) == quote)
    assert (
        paragraph.find("w:r/w:rPr/w:rFonts", NS).get(f"{{{W}}}ascii") == "Courier New"
    )
    assert paragraph.find("w:r/w:rPr/w:sz", NS).get(f"{{{W}}}val") == "22"
    raw_before = next(
        p for p in old.findall("w:body/w:p", NS) if wording(p) == "  raw_code()"
    )
    raw_after = next(
        p for p in new.findall("w:body/w:p", NS) if wording(p) == "  raw_code()"
    )
    assert ET.tostring(raw_before) == ET.tostring(raw_after)


@pytest.mark.parametrize(
    "quotes",
    [
        ("x" * 801,),
        ("\n".join("line" for _ in range(13)),),
        tuple("Long literal quote. " * 100 for _ in range(8)),
    ],
)
def test_large_summary_quotes_flow_without_unbounded_keep_groups(quotes):
    output = document(parts(qualified_body(quotes)))
    paragraphs = output.findall("w:body/w:p", NS)
    for quote in quotes:
        found = [p for p in paragraphs if wording(p) == quote]
        assert found
        assert all(p.find("w:pPr/w:keepLines", NS) is None for p in found)
        assert all(p.find("w:pPr/w:keepNext", NS) is None for p in found)
    captions = [p for p in paragraphs if wording(p).startswith("Summary item ")]
    assert all(p.find("w:pPr/w:keepNext", NS) is None for p in captions)


def test_more_than_three_short_quotes_stop_each_keep_group_at_its_quote():
    quotes = tuple(f"Short wording {number}." for number in range(4))
    output = document(parts(qualified_body(quotes)))
    paragraphs = output.findall("w:body/w:p", NS)
    for quote in quotes:
        position = next(i for i, p in enumerate(paragraphs) if wording(p) == quote)
        assert paragraphs[position - 1].find("w:pPr/w:keepNext", NS) is not None
        assert paragraphs[position].find("w:pPr/w:keepNext", NS) is None
    checklist = next(p for p in paragraphs if wording(p) == "Handover next steps")
    assert checklist.find("w:pPr/w:pageBreakBefore", NS) is None


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b.replace(
            "Source-only handover checklist — review before using.", "Dear committee,"
        ),
        lambda b: b.replace(COVERAGE, "An edited coverage claim."),
        lambda b: b.replace(CHECKLIST, CHECKLIST + "\n\n" + CHECKLIST),
        lambda b: b.replace("### Wording selected", "### Edited wording selected"),
        lambda b: b.replace(
            "**Summary item 1: Item 1** — Passage 1",
            "**Summary item 1: Item 1** — Passage 2",
        ),
        lambda b: b.replace("> ```text", "> ```python", 1),
        lambda b: b.replace(
            "### Wording selected for this summary",
            "Unrelated paragraph.\n\n### Wording selected for this summary",
        ),
        lambda b: "\n".join("> " + line for line in b.splitlines()),
        lambda b: "```text\n" + b + "\n```",
    ],
)
def test_edited_nested_ambiguous_or_code_lookalikes_keep_the_generic_export(change):
    body = change(qualified_body())
    assert parts(body) == unpolished_parts(body)


def test_review_only_running_identity_has_native_fields_valid_parts_and_bounded_title():
    title = "Fictional café 🐝 " * 10
    payload = {"title": title, "markdown": qualified_body()}
    original = deepcopy(payload)
    result = export_docx(payload)
    assert payload == original
    assert result.content == export_docx(payload).content
    with ZipFile(io.BytesIO(result.content)) as archive:
        output = {
            name: ET.fromstring(archive.read(name)) for name in archive.namelist()
        }
    assert len(wording(output["word/header1.xml"])) == 80
    assert wording(output["word/header1.xml"]).endswith("…")
    assert "Review before use" in wording(output["word/footer1.xml"])
    assert [
        node.get(f"{{{W}}}instr")
        for node in output["word/footer1.xml"].iter(f"{{{W}}}fldSimple")
    ] == ["PAGE", "NUMPAGES"]
    assert all(
        node.get(f"{{{W}}}dirty") == "true"
        for node in output["word/footer1.xml"].iter(f"{{{W}}}fldSimple")
    )
    relationships = output["word/_rels/document.xml.rels"]
    for kind in ("header", "footer"):
        relation = next(
            item for item in relationships if item.get("Type") == f"{R}/{kind}"
        )
        assert relation.get("Target") == f"{kind}1.xml"
        assert relation.get("TargetMode") is None
    section = output["word/document.xml"].find("w:body/w:sectPr", NS)
    assert [node.tag for node in list(section)[:2]] == [
        f"{{{W}}}headerReference",
        f"{{{W}}}footerReference",
    ]
    assert REL in ET.tostring(relationships).decode()


def test_polish_keeps_stale_notice_line_endings_and_full_500k_boundary():
    body = qualified_body().replace(INTRO, INTRO + "\n\n" + STALE)
    before, after = document(unpolished_parts(body)), document(parts(body))
    assert wording(before) == wording(after)
    assert "Review status: stale." in wording(after)
    assert wording(document(parts(body.replace("\n", "\r\n")))) == wording(after)
    exact = body + "\n\n" + "x" * (MAX_MARKDOWN - len(body) - 2)
    payload = {"title": "Fictional handover", "markdown": exact}
    original = deepcopy(payload)
    assert len(exact) == MAX_MARKDOWN
    output = export_docx(payload)
    assert output.content and payload == original
    with ZipFile(io.BytesIO(output.content)) as archive:
        full = ET.fromstring(archive.read("word/document.xml"))
    tail = full.findall("w:body/w:p", NS)[-1]
    assert wording(tail) == "x" * (MAX_MARKDOWN - len(body) - 2)
    assert tail.find("w:pPr/w:keepNext", NS) is None
    assert tail.find("w:pPr/w:keepLines", NS) is None
    assert tail.find("w:pPr/w:pageBreakBefore", NS) is None
    assert tail.find(".//w:br[@w:type='page']", NS) is None
    with pytest.raises(ValueError, match="500,000"):
        export_docx({**payload, "markdown": exact + "x"})
    assert payload == original
