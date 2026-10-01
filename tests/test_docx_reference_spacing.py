"""Compact complete reference mappings without changing words or other exports."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from sinter import docx_export, evidence, handover
from sinter.document_markup import PAGE_BREAK_MARKER

NS = {"w": docx_export.W}
INTRO = (
    "These short labels refer to the exact selected excerpts. Offsets count "
    "Unicode code points from zero. The start is included; the end is excluded. "
    "Selection does not establish a verified answer."
)
RECORD = (
    "> **Passage 1** — Original source: Fictional 🌱 e\u0301 note\n"
    "> Excerpt ID: `Efirst`; source ID: `Soriginal`.\n"
    "> Unicode characters: 1–8; quoted above."
)
KEY = "## Passage reference key\n\n" + INTRO + "\n\n" + RECORD
ORDINARY = (
    "# Fictional ordinary draft\n\nNo consent or owner is confirmed. 🐝 e\u0301\n\n"
    "> Original source: Fictional note\n\n> Words retain ordinary quote spacing.\n\n"
    "| Action | Owner |\n| --- | --- |\n| Ask | Unassigned |\n\n"
    "```text\n## Passage reference key\n> This is literal code.\n```\n\n"
    + PAGE_BREAK_MARKER
    + "\n\n## Following page\n\nNothing has been sent."
)


def exported(markdown: str, *, baseline: bool = False) -> tuple[bytes, dict]:
    """The baseline keeps the prior export path with no reference layout hint."""
    payload = {"title": "Fictional source-only handover", "markdown": markdown}
    # Isolate spacing from the separately tested optional navigation layer.
    with patch.object(docx_export, "_passage_navigation", return_value=({}, {})):
        if baseline:
            with patch.object(
                docx_export, "_reference_key_spacing", return_value=frozenset()
            ):
                data = docx_export.export_docx(payload).content
        else:
            data = docx_export.export_docx(payload).content
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        return data, {name: archive.read(name) for name in archive.namelist()}


def paragraphs(parts: dict) -> list[ET.Element]:
    return ET.fromstring(parts["word/document.xml"]).findall("w:body/w:p", NS)


def words(node: ET.Element) -> str:
    result = []
    for item in node.iter():
        if item.tag == f"{{{docx_export.W}}}t":
            result.append(item.text or "")
        elif item.tag == f"{{{docx_export.W}}}br":
            result.append("\n")
    return "".join(result)


def compact(node: ET.Element) -> bool:
    spacing = node.find("w:pPr/w:spacing", NS)
    return (
        spacing is not None and spacing.attrib.get(f"{{{docx_export.W}}}line") == "240"
    )


@pytest.mark.parametrize("count", [1, 5, 12])
@pytest.mark.parametrize("appendix", [False, True])
def test_complete_generated_keys_only_adjust_spacing_with_exact_words_and_offsets(
    count, appendix
):
    content = "a🐝e\u0301" * count
    source = evidence.source("Fictional original 🌱 e\u0301", content)
    selected = [
        evidence.Excerpt(
            f"Epart{at}", source.id, at * 4, at * 4 + 4, content[at * 4 : at * 4 + 4]
        )
        for at in range(count)
    ]
    markdown = handover.render(
        "Fictional handover",
        {},
        [source],
        selected,
        [],
        include_selected_appendix=appendix,
    )
    _, current = exported(markdown)
    _, previous = exported(markdown, baseline=True)
    assert set(current) == set(previous)
    assert all(
        current[name] == previous[name]
        for name in current
        if name != "word/document.xml"
    )
    before, after = paragraphs(previous), paragraphs(current)
    assert len(before) == len(after)
    mappings = []
    for old, new in zip(before, after):
        assert words(old) == words(new)
        assert [ET.tostring(run) for run in old.findall("w:r", NS)] == [
            ET.tostring(run) for run in new.findall("w:r", NS)
        ], "Fonts, code identities and all original runs must remain exact."
        if compact(new):
            mappings.append(new)
            assert new.find("w:pPr/w:keepLines", NS) is not None
            assert new.find("w:pPr/w:keepNext", NS) is None
            spacing = new.find("w:pPr/w:spacing", NS)
            assert spacing.attrib == {
                f"{{{docx_export.W}}}before": "0",
                f"{{{docx_export.W}}}after": "80",
                f"{{{docx_export.W}}}line": "240",
                f"{{{docx_export.W}}}lineRule": "auto",
            }
            new.find("w:pPr", NS).remove(spacing)
        assert ET.tostring(old) == ET.tostring(new), "Non-spacing XML stays exact."
    assert len(mappings) == count
    for number, (node, excerpt) in enumerate(zip(mappings, selected), 1):
        text = words(node)
        assert text.startswith(f"Passage {number} — Original source: ")
        assert f"Excerpt ID: {excerpt.id}; source ID: {source.id}." in text
        assert f"Unicode characters: {excerpt.start}–{excerpt.end};" in text
        assert source.content[excerpt.start : excerpt.end] == excerpt.quote
        if number > 4:
            assert (
                "quoted in the selected evidence appendix."
                if appendix
                else "Selected passage not reproduced in this copy. "
                "Ask the sender for its original wording and surrounding context."
            ) in text


def test_multiline_literal_source_titles_and_unicode_offsets_do_not_change():
    source = evidence.source(
        "First 🌱 e\u0301 line\n[Passage 7] <literal>\n1. --- `a_b`",
        "🐝 e\u0301 Unknown, not approved.",
    )
    excerpt = evidence.Excerpt("Eunicode", source.id, 2, 4, source.content[2:4])
    markdown = handover.render("Fictional handover", {}, [source], [excerpt], [])
    _, parts = exported(markdown)
    mapping = next(node for node in paragraphs(parts) if compact(node))
    assert "First 🌱 e\u0301 line\n[Passage 7] <literal>\n1. --- `a_b`" in words(
        mapping
    )
    assert "Unicode characters: 2–4; quoted above." in words(mapping)
    assert len(mapping.findall(".//w:br", NS)) == 4
    assert mapping.find("w:pPr/w:numPr", NS) is None


@pytest.mark.parametrize("host", ["linux", "win32"])
def test_ordinary_document_is_exact_prior_package_bytes(host):
    with patch.object(zipfile.sys, "platform", host):
        current, _ = exported(ORDINARY)
        previous, _ = exported(ORDINARY, baseline=True)
    assert current == previous
    # Captured from the prior exporter, including deterministic ZIP metadata.
    assert (
        hashlib.sha256(current).hexdigest()
        == "07049b683fe726b8a8f2306d00cea3ded022bb70b8aa3fd3a71d50f433d9ac25"
    )


@pytest.mark.parametrize(
    "markdown",
    [
        RECORD,
        "### Passage reference key\n\n" + INTRO + "\n\n" + RECORD,
        "> ## Passage reference key\n>\n> " + INTRO + "\n>\n" + RECORD,
        "- Heading\n  ## Passage reference key\n\n  "
        + INTRO
        + "\n\n"
        + "\n".join("  " + line for line in RECORD.splitlines()),
        "```text\n" + KEY + "\n```",
        KEY.replace(
            "\n\n" + RECORD,
            "\n\n" + "\n".join("> " + line for line in RECORD.splitlines()),
        ),
        KEY.replace("**Passage 1**", "Passage 1"),
        KEY.replace("**Passage 1**", "**Passage 2**"),
        KEY.replace("`Efirst`", "Efirst"),
        KEY.replace("`Soriginal`", "[Soriginal](https://example.invalid/source)"),
        KEY.replace("Excerpt ID:", "Excerpt:"),
        KEY.replace("1–8", "8–1"),
        KEY.replace("1–8", "1–1"),
        KEY.replace("1–8", "01–8"),
        KEY.replace("quoted above.", "verified answer."),
        KEY.replace(INTRO, "A different user-written introduction."),
        KEY + "\n\n" + RECORD,
        KEY + "\n\n## Passage reference key\n\n" + INTRO + "\n\n" + RECORD,
        KEY + "\n\n> Unrelated user quote within this section.",
        KEY.replace("Fictional 🌱 e\u0301 note", "\n> "),
        KEY.replace("Fictional 🌱 e\u0301 note", "x" * 2500),
        KEY.replace("Fictional 🌱 e\u0301 note", "\n> ".join(["line"] * 20)),
    ],
)
def test_ambiguous_nested_fenced_or_incomplete_key_lookalikes_keep_exact_prior_bytes(
    markdown,
):
    current, parts = exported(markdown)
    previous, _ = exported(markdown, baseline=True)
    assert current == previous
    assert not any(compact(node) for node in paragraphs(parts))


@pytest.mark.parametrize(
    "prefix", ["> > ", ">  > ", ">   > ", ">    > ", ">  >> ", ">   >>> "]
)
def test_nested_quote_spacing_forms_never_promote_source_mapping_lookalikes(prefix):
    nested = "\n".join(prefix + line[2:] for line in RECORD.splitlines())
    markdown = KEY.replace(RECORD, nested)
    current, parts = exported(markdown)
    previous, _ = exported(markdown, baseline=True)
    assert current == previous
    assert not any(compact(node) for node in paragraphs(parts))


@pytest.mark.parametrize("witness_before", [False, True])
def test_nested_mapping_cannot_borrow_an_equal_plain_quote_outside_its_section(
    witness_before,
):
    nested = "\n".join("> " + line for line in RECORD.splitlines())
    key = KEY.replace(RECORD, nested)
    witness = "## Unrelated section\n\n" + RECORD
    markdown = witness + "\n\n" + key if witness_before else key + "\n\n" + witness
    current, parts = exported(markdown)
    previous, _ = exported(markdown, baseline=True)
    assert current == previous
    assert not any(compact(node) for node in paragraphs(parts))


@pytest.mark.parametrize("witness_before", [False, True])
def test_valid_mapping_uses_its_own_source_position_despite_equal_quote_elsewhere(
    witness_before,
):
    witness = "## Unrelated section\n\n" + RECORD
    markdown = witness + "\n\n" + KEY if witness_before else KEY + "\n\n" + witness
    _, parts = exported(markdown)
    mapping = [node for node in paragraphs(parts) if "Excerpt ID:" in words(node)]
    assert len(mapping) == 2
    assert [compact(node) for node in mapping] == (
        [False, True] if witness_before else [True, False]
    )


@pytest.mark.parametrize(
    "boundary",
    [
        "## Following section",
        PAGE_BREAK_MARKER,
        "| Key | Value |\n| --- | --- |\n| Source | Unknown |",
    ],
)
def test_reference_spacing_stops_at_structural_section_boundary(boundary):
    second = RECORD.replace("**Passage 1**", "**Passage 2**").replace(
        "Efirst", "Esecond"
    )
    markdown = KEY + "\n\n" + boundary + "\n\n" + second
    _, parts = exported(markdown)
    mapping = [node for node in paragraphs(parts) if "Excerpt ID:" in words(node)]
    assert len(mapping) == 2
    assert compact(mapping[0])
    assert not compact(mapping[1])


def test_literal_mapping_ids_are_not_assumed_to_have_a_particular_hash_length():
    record = RECORD.replace("Efirst", "E1234567890abcdef").replace(
        "Soriginal", "S0123456789abcdef01234567"
    )
    _, parts = exported(KEY.replace(RECORD, record))
    assert len([node for node in paragraphs(parts) if compact(node)]) == 1
    assert re.search(
        "Excerpt ID: E1234567890abcdef; source ID: S0123456789abcdef01234567",
        words(ET.fromstring(parts["word/document.xml"])),
    )
