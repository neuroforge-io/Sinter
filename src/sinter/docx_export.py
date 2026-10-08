"""Editable, local Word documents from explicitly supplied draft text.

Uses standard-library OOXML only: no HTML importer, macros, embedded files,
network requests, or lookup of saved profile and source data.
"""

from __future__ import annotations

import io
import re
import textwrap
import unicodedata
import zipfile
from copy import deepcopy
from dataclasses import dataclass, replace
from xml.etree import ElementTree as ET

from .document_markup import Block, PageBreak, Paragraph, Span, Table, parse

MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_MARKDOWN = 500_000
# Keep one bounded source note together, never an arbitrary quote dossier.
_MAX_SOURCE_NOTE_GROUP_CHARS = 2400
_MAX_SOURCE_NOTE_GROUP_LINES = 20
_MAX_SOURCE_TABLE_GROUP_CHARS = 800
_MAX_SOURCE_TABLE_GROUP_LINES = 16
_SOURCE_TABLE_DISCLAIMER = (
    "Quoted source table. Blank cells are shown as —; entries do not confirm "
    "assignments or dates."
)
_MAX_PASSAGE_NAVIGATION_RECORDS = 64
_REFERENCE_KEY_HEADING = "Passage reference key"
_REFERENCE_KEY_INTRO = (
    "These short labels refer to the exact selected excerpts. Offsets count "
    "Unicode code points from zero. The start is included; the end is excluded. "
    "Selection does not establish a verified answer."
)
_REFERENCE_SCOPES = {
    "quoted above.",
    "quoted in the selected evidence appendix.",
    "Evidence only — not reproduced in this document. "
    "Read its exact wording in Evidence.",
    "Selected passage not reproduced in this copy. "
    "Ask the sender for its original wording and surrounding context.",
}
_HANDOVER_SUMMARY_HEADING = "At a glance"
_HANDOVER_SUMMARY_INTRO = (
    "Statuses and next steps below are user-entered for review. Next steps are "
    "proposals, not accepted commitments. A retained quotation establishes "
    "supplied wording, not independent verification."
)
_HANDOVER_SUMMARY_STALE = (
    "**Review status: stale.** Review this saved record again before current use. "
    "Original evidence and historical wording remain unchanged; "
    "no current source was substituted."
)
_HANDOVER_SUMMARY_HEADERS = (
    "Item",
    "Recorded status — user-entered",
    "Next step — proposed",
    "Evidence",
)
_HANDOVER_SUMMARY_WIDTHS = (1560, 4200, 2280, 1320)
_HANDOVER_SUBTITLE = "Source-only handover checklist — review before using."
_HANDOVER_CHECKLIST_INTRO = (
    "Review each question against its related wording, then record the confirmed "
    "response and who will follow it up. A wording match is not an answer; "
    "no owner or target date is assigned by this checklist."
)
_HANDOVER_SUMMARY_COVERAGE = (
    "**Evidence coverage:** this opening uses selected wording from this saved "
    "report. The unchanged checklist and selected evidence follow. This is not "
    "full supplied history; request the matching original project backup for "
    "unselected text. Later project or campaign changes are not included."
)
_MAX_SUMMARY_QUOTE_GROUP_CHARS = 800
_MAX_SUMMARY_QUOTE_GROUP_LINES = 12
_MAX_SUMMARY_QUOTE_GROUP_COUNT = 3
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
XML = "http://www.w3.org/XML/1998/namespace"
for _prefix, _uri in (("w", W), ("r", R)):
    ET.register_namespace(_prefix, _uri)


@dataclass(frozen=True)
class WordDocument:
    filename: str
    content: bytes
    content_type: str = MIME


def _element(parent: ET.Element, tag: str, **values: object) -> ET.Element:
    return ET.SubElement(
        parent,
        f"{{{W}}}{tag}",
        {f"{{{W}}}{key}": str(value) for key, value in values.items()},
    )


def _xml(node: ET.Element) -> bytes:
    # LibreOffice's OPC package detector requires default namespaces here even
    # though an equivalent prefixed namespace parses as valid XML. Keep this
    # conversion local instead of racing on a global namespace registration.
    if node.tag in {f"{{{CT}}}Types", f"{{{REL}}}Relationships"}:
        node = deepcopy(node)
        namespace = node.tag[1:].split("}", 1)[0]
        for child in node.iter():
            child.tag = child.tag.removeprefix("{" + namespace + "}")
        node.set("xmlns", namespace)
    return ET.tostring(node, encoding="utf-8", xml_declaration=True)


def _text(value: object, name: str, limit: int, *, single_line: bool = False) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must contain between 1 and {limit:,} characters.")
    if any(
        not (
            char in "\t\n\r"
            or 0x20 <= ord(char) <= 0xD7FF
            or 0xE000 <= ord(char) <= 0xFFFD
            or 0x10000 <= ord(char) <= 0x10FFFF
        )
        for char in value
    ):
        raise ValueError(
            f"{name} contains characters that Word cannot represent. "
            "Remove the control characters and retry."
        )
    if single_line and any(char in value for char in "\r\n\t\u2028\u2029"):
        raise ValueError(f"{name} must be a single line.")
    return value


def _source_note_keep_next(blocks: tuple[Block, ...]) -> frozenset[int]:
    """Pair supplied source metadata with one small quoted paragraph only."""
    keep = set()

    def plain_quote(block):
        return (
            isinstance(block, Paragraph)
            and block.quote
            and not (block.heading or block.code or block.list_id)
        )

    def wording(block):
        return "".join(span.text for span in block.spans)

    for index, caption in enumerate(blocks):
        if not plain_quote(caption) or not wording(caption).startswith(
            "Original source: "
        ):
            continue
        end = index + 1
        if end >= len(blocks):
            continue
        metadata = blocks[end]
        if plain_quote(metadata) and wording(metadata).startswith(
            "Source link (supplied): "
        ):
            # Admit only the generated two-line metadata shape. This is a
            # layout hint, never source identity or date verification.
            lines = wording(metadata).splitlines()
            if len(lines) != 2 or not lines[1].startswith("Date label (supplied): "):
                continue
            end += 1
        if end >= len(blocks) or not plain_quote(blocks[end]):
            continue
        if wording(blocks[end]).startswith(
            ("Original source: ", "Source link (supplied): ")
        ):
            continue
        text = "\n".join(wording(block) for block in blocks[index : end + 1])
        if (
            len(text) <= _MAX_SOURCE_NOTE_GROUP_CHARS
            and len(text.splitlines()) <= _MAX_SOURCE_NOTE_GROUP_LINES
        ):
            # Stop at the note: the following passage/key cannot be chained.
            keep.update(range(index, end))
    return frozenset(keep)


def _source_table_groups(
    markdown: str, blocks: tuple[Block, ...]
) -> tuple[frozenset[int], frozenset[int]]:
    """Group one short supplied table, never verify its source or join its tail."""
    pattern = (
        r"^### (?P<label>Passage [1-9][0-9]*)\n\n"
        r"> Original source: [^\n]+\n\n"
        r"(?:> Source link \(supplied\): [^\n]+\n"
        r"> Date label \(supplied\): [^\n]+\n\n)?"
        + re.escape(_SOURCE_TABLE_DISCLAIMER)
        + r"\n\n(?:> \|[^\n]*\|\n){3,4}(?=\n|$)"
    )
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(re.finditer(pattern, normalized, re.M))
    if len(matches) > _MAX_PASSAGE_NAVIGATION_RECORDS:
        return frozenset(), frozenset()
    raw_headings: dict[str, int] = {}
    for heading in re.finditer(
        r"(?m)^[^\n]*### (Passage [1-9][0-9]*)[ \t]*$", normalized
    ):
        label = heading[1]
        raw_headings[label] = raw_headings.get(label, 0) + 1
    parsed_headings: dict[str, list[int]] = {}
    for index, block in enumerate(blocks):
        if isinstance(block, Paragraph) and block.heading == 3:
            label = "".join(span.text for span in block.spans)
            if re.fullmatch(r"Passage [1-9][0-9]*", label):
                parsed_headings.setdefault(label, []).append(index)

    def wrapped_lines(
        spans: tuple[Span, ...], width: int, *, metadata: bool = False
    ) -> int:
        text = "".join(span.text for span in spans)
        if (
            any(span.code or (span.href and len(span.href) > 96) for span in spans)
            or text != text.strip()
            or "  " in text
            or any(len(word) > 96 for word in text.split())
            or any(
                char.isspace() and char not in (" ", "\n" if metadata else " ")
                for char in text
            )
            # Wide glyphs need a different wrap estimate; preserve normal flow.
            or any(unicodedata.east_asian_width(char) in "WF" for char in text)
        ):
            return _MAX_SOURCE_TABLE_GROUP_LINES + 1
        return sum(
            max(1, len(textwrap.wrap(line, width, break_on_hyphens=False)))
            for line in text.split("\n")
        )

    keep, tables = set(), set()
    for match in matches:
        if (
            len(match[0]) > _MAX_SOURCE_TABLE_GROUP_CHARS
            or "  " in match[0]
            or raw_headings.get(match["label"]) != 1
            or len(parsed_headings.get(match["label"], ())) != 1
        ):
            continue
        group = parse(match[0])
        if not group or not isinstance(group[-1], Table):
            continue
        table = group[-1]
        if not (2 <= len(table.rows) <= 3 and 2 <= len(table.alignments) <= 5):
            continue
        width = 9360 // len(table.alignments) // 120 - 2
        lines = sum(
            wrapped_lines(block.spans, 72, metadata=len(group) == 5 and at == 2)
            for at, block in enumerate(group[:-1])
        )
        lines += sum(
            max(wrapped_lines(cell, width) for cell in row) for row in table.rows
        )
        if lines > _MAX_SOURCE_TABLE_GROUP_LINES:
            continue
        # Tables lose quote-depth provenance. Unique raw and parsed headings
        # bind this top-level shape to the same plain parsed block sequence.
        # Count nested/decorated duplicates too, rather than pairing a fenced
        # literal copy with another live heading. Never reparse long prefixes.
        start = parsed_headings[match["label"]][0]
        end = start + len(group)
        if blocks[start:end] != group:
            continue
        keep.update(range(start, end - 1))
        tables.add(end - 1)
    return frozenset(keep), frozenset(tables)


def _handover_summary_table_widths(
    markdown: str, blocks: tuple[Block, ...]
) -> dict[int, tuple[int, ...]]:
    """Scope presentation to one exact generated opening, never infer answers."""
    headings = [
        index
        for index, block in enumerate(blocks)
        if isinstance(block, Paragraph)
        and block.heading == 2
        and not (block.quote or block.code or block.list_id)
        and block.spans == (Span(_HANDOVER_SUMMARY_HEADING),)
    ]
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    raw = list(re.finditer(r"(?m)^## At a glance$", normalized))
    if len(headings) != 1 or len(raw) != 1:
        return {}
    index = headings[0]
    prefix = parse(normalized[: raw[0].end()])
    if len(prefix) != index + 1 or prefix[-1] != blocks[index]:
        return {}
    position = index + 1
    if position >= len(blocks) or blocks[position] != Paragraph(
        (Span(_HANDOVER_SUMMARY_INTRO),)
    ):
        return {}
    remaining = normalized[raw[0].end() :].lstrip("\n")
    intro = _HANDOVER_SUMMARY_INTRO + "\n\n"
    if not remaining.startswith(intro):
        return {}
    remaining = remaining[len(intro) :]
    position += 1
    stale = _HANDOVER_SUMMARY_STALE + "\n\n"
    if remaining.startswith(stale):
        if position >= len(blocks) or parse(_HANDOVER_SUMMARY_STALE) != (
            blocks[position],
        ):
            return {}
        position += 1
        remaining = remaining[len(stale) :]
    if position >= len(blocks) or not isinstance(blocks[position], Table):
        return {}
    table = blocks[position]
    raw_table = remaining.split("\n\n", 1)[0]
    if (
        len(table.alignments) != 4
        or len(table.rows) < 2
        or table.rows[0]
        != tuple((Span(header),) for header in _HANDOVER_SUMMARY_HEADERS)
        or not all(
            line.startswith("|") and line.endswith("|")
            for line in raw_table.splitlines()
        )
        or parse(raw_table) != (table,)
    ):
        return {}
    return {position: _HANDOVER_SUMMARY_WIDTHS}


def _raw_block_index(
    markdown: str, blocks: tuple[Block, ...], line: str, expected: Block
) -> tuple[int, re.Match[str]] | None:
    """Match one top-level literal block; typed layout is not verified evidence."""
    matches = list(re.finditer(r"(?m)^" + re.escape(line) + "$", markdown))
    if len(matches) != 1:
        return None
    prefix = parse(markdown[: matches[0].end()])
    index = len(prefix) - 1
    if index < 0 or index >= len(blocks) or prefix[-1] != expected:
        return None
    if blocks[index] != expected or blocks[: index + 1] != prefix:
        return None
    return index, matches[0]


def _short_summary_quote_group(blocks: tuple[Block, ...]) -> bool:
    """Bound a small layout hint, never promise that arbitrary text fits a page."""
    text = ["".join(span.text for span in block.spans) for block in blocks]
    lines = sum(
        max(1, (len(line.expandtabs(4)) + 59) // 60)
        for value in text
        for line in value.split("\n")
    )
    return (
        sum(map(len, text)) <= _MAX_SUMMARY_QUOTE_GROUP_CHARS
        and lines <= _MAX_SUMMARY_QUOTE_GROUP_LINES
    )


def _handover_summary_presentation(
    markdown: str,
    blocks: tuple[Block, ...],
    widths: dict[int, tuple[int, ...]],
) -> tuple[bool, frozenset[int], frozenset[int]]:
    """Style exact generated opening shapes only, without certifying their text.

    An exact typed copy has the same shape. No source, answer, approval or review
    state is validated by this presentation adapter; its footer stays review-only.
    """
    refused = False, frozenset(), frozenset()
    if not widths or len(blocks) < 2:
        return refused
    title = blocks[0]
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    if (
        not normalized.startswith("# ")
        or not isinstance(title, Paragraph)
        or title.heading != 1
        or title.quote
        or title.code
        or title.list_id
        or blocks[1] != Paragraph((Span(_HANDOVER_SUBTITLE),))
    ):
        return refused
    coverage = _raw_block_index(
        normalized,
        blocks,
        _HANDOVER_SUMMARY_COVERAGE,
        parse(_HANDOVER_SUMMARY_COVERAGE)[0],
    )
    checklist = _raw_block_index(
        normalized,
        blocks,
        "## Handover next steps",
        Paragraph((Span("Handover next steps"),), heading=2),
    )
    table_at = next(iter(widths))
    if (
        coverage is None
        or coverage[0] != table_at + 1
        or checklist is None
        or checklist[0] <= coverage[0]
        or checklist[0] + 1 >= len(blocks)
        or blocks[checklist[0] + 1] != Paragraph((Span(_HANDOVER_CHECKLIST_INTRO),))
    ):
        return refused
    section = normalized[coverage[1].end() : checklist[1].start()].strip("\n")
    if not section:
        return True, frozenset(), frozenset()
    heading = "### Wording selected for this summary"
    raw = [part for part in section.split("\n\n") if part]
    selected = blocks[coverage[0] + 1 : checklist[0]]
    table = blocks[table_at]
    if (
        raw[0] != heading
        or len(raw) < 3
        or len(raw) % 2 != 1
        or len(selected) != len(raw)
        or parse(section) != selected
        or selected[0]
        != Paragraph((Span("Wording selected for this summary"),), heading=3)
        or len(table.rows) > 13
    ):
        return refused
    quotes, keep, previous = set(), set(), 0
    first = coverage[0] + 1
    for offset in range(1, len(raw), 2):
        caption = re.fullmatch(
            r"\*\*Summary item ([1-9][0-9]*): (.+)\*\* — (Passage [1-9][0-9]*)",
            raw[offset],
        )
        if caption is None or len(caption[1]) > 2:
            return refused
        number = int(caption[1])
        if not previous < number < len(table.rows):
            return refused
        previous = number
        item = "".join(span.text for span in table.rows[number][0])
        if selected[offset] != Paragraph(
            (
                Span(f"Summary item {number}: {item}", bold=True),
                Span(" — " + caption[3]),
            )
        ) or table.rows[number][3] != (Span(caption[3]),):
            return refused
        lines = raw[offset + 1].split("\n")
        fence = re.fullmatch(r"> (`{3,})text", lines[0])
        if (
            fence is None
            or len(lines) < 3
            or lines[-1] != "> " + fence[1]
            or any(not line.startswith("> ") for line in lines[1:-1])
        ):
            return refused
        wording = "\n".join(line[2:] for line in lines[1:-1])
        longest = max((len(run) for run in re.findall(r"`+", wording)), default=0)
        if len(fence[1]) != max(3, longest + 1) or selected[offset + 1] != Paragraph(
            (Span(wording, code=True),), quote=True, code=True
        ):
            return refused
        quotes.add(first + offset + 1)
        if _short_summary_quote_group(selected[offset : offset + 2]):
            keep.add(first + offset)
    if len(quotes) <= _MAX_SUMMARY_QUOTE_GROUP_COUNT and _short_summary_quote_group(
        selected
    ):
        # End on the last quotation, never on the original checklist or evidence.
        keep.update(range(first, checklist[0] - 1))
    return True, frozenset(quotes), frozenset(keep)


def _reference_key_spacing(markdown: str, blocks: tuple[Block, ...]) -> frozenset[int]:
    """Admit complete generated mappings for layout, never identity validation."""

    def wording(block: Paragraph) -> str:
        return "".join(span.text for span in block.spans)

    headings = [
        index
        for index, block in enumerate(blocks)
        if isinstance(block, Paragraph)
        and block.heading == 2
        and not (block.quote or block.code or block.list_id)
        and wording(block) == _REFERENCE_KEY_HEADING
    ]
    # A single raw top-level heading also excludes flattened nested headings.
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    raw_headings = list(re.finditer(r"(?m)^## Passage reference key$", normalized))
    if len(headings) != 1 or len(raw_headings) != 1:
        return frozenset()
    index = headings[0]
    prefix = parse(normalized[: raw_headings[0].end()])
    if len(prefix) != index + 1 or prefix[-1] != blocks[index]:
        return frozenset()
    if index + 1 >= len(blocks):
        return frozenset()
    intro = blocks[index + 1]
    if not isinstance(intro, Paragraph) or intro != Paragraph(
        (Span(_REFERENCE_KEY_INTRO),)
    ):
        return frozenset()

    # Walk the raw section in the same order as its parsed mappings. Typed
    # quotes omit nesting depth; equal wording elsewhere cannot admit this row.
    remaining = normalized[raw_headings[0].end() :].lstrip("\n")
    raw_intro = _REFERENCE_KEY_INTRO + "\n\n"
    if not remaining.startswith(raw_intro):
        return frozenset()
    remaining = remaining[len(raw_intro) :].lstrip("\n")

    admitted, identities = set(), set()
    for position in range(index + 2, len(blocks)):
        block = blocks[position]
        if not isinstance(block, Paragraph) or block.heading or not block.quote:
            break
        raw_quote = re.match(r"(?:> [^\n]*(?:\n|$))+", remaining)
        if raw_quote is None or re.search(r"(?m)^> *>", raw_quote[0]):
            return frozenset()
        if parse(raw_quote[0]) != (block,):
            return frozenset()
        remaining = remaining[raw_quote.end() :].lstrip("\n")
        text = wording(block)
        lines = text.split("\n")
        number = len(admitted) + 1
        label = f"Passage {number}"
        if (
            block.code
            or block.list_id
            or len(text) > _MAX_SOURCE_NOTE_GROUP_CHARS
            or not 3 <= len(lines) <= _MAX_SOURCE_NOTE_GROUP_LINES
            or not block.spans
            or block.spans[0] != Span(label, bold=True)
            or not lines[0].startswith(label + " — Original source: ")
            or not "\n".join(lines[:-2])[len(label + " — Original source: ") :].strip()
        ):
            return frozenset()
        identity = re.fullmatch(
            r"Excerpt ID: ([^;\s]+); source ID: ([^\s]+)\.", lines[-2]
        )
        offsets = re.fullmatch(
            r"Unicode characters: (0|[1-9][0-9]{0,8})–"
            r"(0|[1-9][0-9]{0,8}); (.+)",
            lines[-1],
        )
        if (
            identity is None
            or offsets is None
            or int(offsets[1]) >= int(offsets[2])
            or offsets[3] not in _REFERENCE_SCOPES
            or identity[1] in identities
        ):
            return frozenset()
        # IDs must be literal inline-code fields, not source-title text or links.
        metadata_start = len("\n".join(lines[:-2])) + 1
        literal_fields = {
            (
                metadata_start + identity.start(group),
                metadata_start + identity.end(group),
                identity[group],
            )
            for group in (1, 2)
        }
        start = 0
        for span in block.spans:
            end = start + len(span.text)
            if span.code and not (span.bold or span.italic or span.href):
                literal_fields.discard((start, end, span.text))
            start = end
        if literal_fields:
            return frozenset()
        identities.add(identity[1])
        admitted.add(position)
    return frozenset(admitted)


def _passage_navigation(
    markdown: str, blocks: tuple[Block, ...], references: frozenset[int]
) -> tuple[dict[int, str], dict[int, tuple[tuple[int, int, str], ...]]]:
    """Link admitted literal labels, never infer or verify source identities.

    Existing source IDs, ranges and quote text stay literal. Ambiguous headings
    cannot become a quote destination; their reference entry remains available.
    Larger mappings retain all wording without this optional navigation layer.
    """
    if not references or len(references) > _MAX_PASSAGE_NAVIGATION_RECORDS:
        return {}, {}
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    bookmarks: dict[int, str] = {}
    links: dict[int, tuple[tuple[int, int, str], ...]] = {}
    destinations = {}
    for number, index in enumerate(sorted(references), 1):
        record = blocks[index]
        label = f"Passage {number}"
        reference = f"SinterReference{number}"
        bookmarks[index] = reference
        destinations[label] = reference
        lines = "".join(span.text for span in record.spans).split("\n")
        if not lines[-1].endswith(
            ("; quoted above.", "; quoted in the selected evidence appendix.")
        ):
            continue
        caption = "\n".join(lines[:-2])[len(label + " — ") :]
        headings = [
            at
            for at, block in enumerate(blocks[:index])
            if isinstance(block, Paragraph)
            and block.heading == 3
            and not (block.quote or block.code or block.list_id)
            and block.spans == (Span(label),)
        ]
        raw = list(re.finditer(r"(?m)^### " + re.escape(label) + r"$", normalized))
        if len(headings) != 1 or len(raw) != 1:
            continue
        heading = headings[0]
        # Typed blocks flatten nesting. Match the raw top-level location too.
        prefix = parse(normalized[: raw[0].end()])
        if len(prefix) != heading + 1 or prefix[-1] != blocks[heading]:
            continue
        source = blocks[heading + 1] if heading + 1 < len(blocks) else None
        if (
            not isinstance(source, Paragraph)
            or not source.quote
            or source.heading
            or source.code
            or source.list_id
            or "".join(span.text for span in source.spans) != caption
        ):
            continue
        end = next(
            (
                at
                for at in range(heading + 2, index)
                if isinstance(blocks[at], Paragraph) and blocks[at].heading
            ),
            index,
        )
        if not any(
            isinstance(block, Table)
            or (
                isinstance(block, Paragraph)
                and block.quote
                and not "".join(span.text for span in block.spans).startswith(
                    "Source link (supplied): "
                )
            )
            for block in blocks[heading + 2 : end]
        ):
            continue
        passage = f"SinterPassage{number}"
        bookmarks[heading] = passage
        destinations[label] = passage
        links[index] = ((0, len(label), passage),)
        links[heading] = ((0, len(label), reference),)

    for index, block in enumerate(blocks):
        if (
            not isinstance(block, Paragraph)
            or block.heading
            or block.quote
            or block.code
            or block.list_id
            or len(block.spans) != 1
            or block.spans[0] != Span(block.spans[0].text)
            or index == 0
        ):
            continue
        text = block.spans[0].text
        if not re.fullmatch(
            r"Related wording — review required: Passage [1-9][0-9]*"
            r"(?:, Passage [1-9][0-9]*)*\.",
            text,
        ):
            continue
        previous = blocks[index - 1]
        if (
            not isinstance(previous, Paragraph)
            or previous.heading != 3
            or previous.quote
            or previous.code
            or previous.list_id
            or not re.match(r"^[1-9][0-9]*\. ", "".join(s.text for s in previous.spans))
        ):
            continue
        labels = list(re.finditer(r"Passage [1-9][0-9]*", text))
        if all(match[0] in destinations for match in labels):
            links[index] = tuple(
                (match.start(), match.end(), destinations[match[0]]) for match in labels
            )
    return bookmarks, links


class _Package:
    def __init__(self) -> None:
        self.document = ET.Element(f"{{{W}}}document")
        self.body = _element(self.document, "body")
        self.relationships = ET.Element(f"{{{REL}}}Relationships")
        self.numbering = ET.Element(f"{{{W}}}numbering")
        self.numbers: list[ET.Element] = []
        self.lists: dict[int, int] = {}
        self.links: dict[str, str] = {}
        self.bookmark_count = 0
        for name in ("styles", "numbering"):
            ET.SubElement(
                self.relationships,
                f"{{{REL}}}Relationship",
                Id=name,
                Type=f"{R}/{name}",
                Target=f"{name}.xml",
            )

    def runs(
        self,
        parent: ET.Element,
        spans: tuple[Span, ...],
        internal_links: tuple[tuple[int, int, str], ...] = (),
        *,
        summary_quote: bool = False,
    ) -> None:
        offset = 0
        fragments = []
        for span in spans:
            end = offset + len(span.text)
            boundaries = {offset, end}
            for first, last, _ in internal_links:
                boundaries.update(at for at in (first, last) if offset < at < end)
            positions = sorted(boundaries)
            if len(positions) == 1:
                fragments.append((span, None))
            for first, last in zip(positions, positions[1:]):
                anchor = next(
                    (
                        name
                        for start, stop, name in internal_links
                        if start <= first and last <= stop
                    ),
                    None,
                )
                fragments.append(
                    (
                        replace(span, text=span.text[first - offset : last - offset]),
                        anchor,
                    )
                )
            offset = end
        for span, anchor in fragments:
            target = parent
            if anchor:
                target = _element(parent, "hyperlink", anchor=anchor)
            elif span.href:
                if span.href not in self.links:
                    identifier = "link" + str(len(self.links) + 1)
                    self.links[span.href] = identifier
                    ET.SubElement(
                        self.relationships,
                        f"{{{REL}}}Relationship",
                        Id=identifier,
                        Type=f"{R}/hyperlink",
                        Target=span.href,
                        TargetMode="External",
                    )
                target = ET.SubElement(
                    parent, f"{{{W}}}hyperlink", {f"{{{R}}}id": self.links[span.href]}
                )
            run = _element(target, "r")
            properties = _element(run, "rPr")
            if span.href or anchor:
                _element(properties, "rStyle", val="Hyperlink")
            sensitive_quote = summary_quote and (
                span.text != span.text.strip()
                or len(span.text) > _MAX_SUMMARY_QUOTE_GROUP_CHARS
                or any(
                    marker in span.text
                    for marker in ("\n", "\t", "  ", "`", "{", "}", "<", ">", "\\")
                )
            )
            if span.code and (not summary_quote or sensitive_quote):
                _element(
                    properties,
                    "rFonts",
                    ascii="Courier New",
                    hAnsi="Courier New",
                    cs="Courier New",
                )
            if span.bold:
                _element(properties, "b")
            if span.italic:
                _element(properties, "i")
            if span.code and (not summary_quote or sensitive_quote):
                _element(properties, "sz", val=22 if summary_quote else 20)
            for part in re.split(r"([\n\t])", span.text):
                if part == "\n":
                    _element(run, "br")
                elif part == "\t":
                    _element(run, "tab")
                elif part:
                    node = _element(run, "t")
                    node.set(f"{{{XML}}}space", "preserve")
                    node.text = part

    def list_number(self, paragraph: Paragraph) -> int:
        if paragraph.list_id in self.lists:
            return self.lists[paragraph.list_id]
        identifier = len(self.lists) + 1
        self.lists[paragraph.list_id] = identifier
        abstract = _element(self.numbering, "abstractNum", abstractNumId=identifier)
        _element(abstract, "multiLevelType", val="multilevel")
        for level in range(9):
            definition = _element(abstract, "lvl", ilvl=level)
            _element(definition, "start", val=1)
            _element(
                definition, "numFmt", val="decimal" if paragraph.ordered else "bullet"
            )
            _element(
                definition,
                "lvlText",
                val=f"%{level + 1}." if paragraph.ordered else "•",
            )
            _element(definition, "lvlJc", val="left")
            properties = _element(definition, "pPr")
            tabs = _element(properties, "tabs")
            _element(tabs, "tab", val="num", pos=360 * (level + 1))
            _element(properties, "ind", left=360 * (level + 1), hanging=240)
        number = ET.Element(f"{{{W}}}num", {f"{{{W}}}numId": str(identifier)})
        self.numbers.append(number)
        _element(number, "abstractNumId", val=identifier)
        override = _element(number, "lvlOverride", ilvl=paragraph.list_level)
        _element(override, "startOverride", val=paragraph.list_start)
        return identifier

    def paragraph(
        self,
        parent: ET.Element,
        paragraph: Paragraph,
        *,
        title: bool = False,
        align: str | None = None,
        keep_next: bool = False,
        compact_reference: bool = False,
        bookmark: str | None = None,
        internal_links: tuple[tuple[int, int, str], ...] = (),
        summary_quote: bool = False,
        paragraph_style: str | None = None,
    ) -> None:
        node = _element(parent, "p")
        properties = _element(node, "pPr")
        if title or paragraph.heading:
            _element(
                properties,
                "pStyle",
                val="Title" if title else f"Heading{paragraph.heading}",
            )
        elif summary_quote:
            _element(properties, "pStyle", val="SummaryQuote")
        elif paragraph.code:
            _element(properties, "pStyle", val="Code")
        elif paragraph.quote:
            _element(properties, "pStyle", val="Quote")
        elif paragraph_style:
            _element(properties, "pStyle", val=paragraph_style)
        if paragraph.quote and (
            not summary_quote or _short_summary_quote_group((paragraph,))
        ):
            # A source/reference paragraph is one unit. Keep its identity and
            # range together when it fits on a page; do not chain other notes.
            _element(properties, "keepLines")
        if keep_next:
            _element(properties, "keepNext")
        if compact_reference:
            # Leave fonts/runs and intact-record pagination unchanged. Only
            # generated reference mappings use tighter line/paragraph spacing.
            _element(
                properties, "spacing", before=0, after=80, line=240, lineRule="auto"
            )
        if paragraph.list_id:
            number = _element(properties, "numPr")
            _element(number, "ilvl", val=paragraph.list_level)
            _element(number, "numId", val=self.list_number(paragraph))
            _element(properties, "spacing", after=80)
        if align:
            _element(properties, "jc", val=align)
        if bookmark:
            identifier = self.bookmark_count
            self.bookmark_count += 1
            _element(node, "bookmarkStart", id=identifier, name=bookmark)
        self.runs(node, paragraph.spans, internal_links, summary_quote=summary_quote)
        if bookmark:
            _element(node, "bookmarkEnd", id=identifier)

    def table(
        self,
        table: Table,
        column_widths: tuple[int, ...] | None = None,
        *,
        compact_source_table: bool = False,
    ) -> None:
        node = _element(self.body, "tbl")
        properties = _element(node, "tblPr")
        if column_widths is None:
            _element(properties, "tblW", w=0, type="auto")
        else:
            _element(properties, "tblW", w=sum(column_widths), type="dxa")
            _element(properties, "tblLayout", type="fixed")
        borders = _element(properties, "tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            _element(borders, edge, val="single", sz=4, color="D1D5DB")
        margins = _element(properties, "tblCellMar")
        for edge in ("top", "left", "bottom", "right"):
            _element(margins, edge, w=60 if compact_source_table else 100, type="dxa")
        grid = _element(node, "tblGrid")
        width = 9360 // len(table.alignments)
        widths = column_widths or (width,) * len(table.alignments)
        for column_width in widths:
            _element(grid, "gridCol", w=column_width)
        for index, row in enumerate(table.rows):
            row_node = _element(node, "tr")
            row_properties = _element(row_node, "trPr")
            _element(row_properties, "cantSplit")
            if index == 0:
                _element(row_properties, "tblHeader")
            for at, spans in enumerate(row):
                cell = _element(row_node, "tc")
                cell_properties = _element(cell, "tcPr")
                _element(cell_properties, "tcW", w=widths[at], type="dxa")
                if index == 0:
                    _element(cell_properties, "shd", fill="F1F3F5", val="clear")
                    spans = tuple(
                        Span(span.text, True, span.italic, span.code, span.href)
                        for span in spans
                    )
                self.paragraph(
                    cell,
                    Paragraph(spans),
                    align=table.alignments[at],
                    keep_next=compact_source_table and index < len(table.rows) - 1,
                    paragraph_style="SourceTableCell" if compact_source_table else None,
                )
        self.paragraph(self.body, Paragraph(()))

    def page_break(self) -> None:
        """Use a native editable Word break without a section or hidden content."""
        node = _element(self.body, "p")
        properties = _element(node, "pPr")
        _element(properties, "spacing", before=0, after=0)
        _element(_element(node, "r"), "br", type="page")


def _review_page_identity(
    package: _Package, section: ET.Element, title: str
) -> dict[str, ET.Element]:
    """Repeat a bounded supplied title and review-only dynamic page identity."""
    header = ET.Element(f"{{{W}}}hdr")
    footer = ET.Element(f"{{{W}}}ftr")
    short_title = title if len(title) <= 80 else title[:79] + "…"
    for node, wording in ((header, short_title), (footer, "Review before use")):
        paragraph = _element(node, "p")
        properties = _element(paragraph, "pPr")
        if node is footer:
            tabs = _element(properties, "tabs")
            _element(tabs, "tab", val="right", pos=9360)
        _element(properties, "spacing", after=0, line=220, lineRule="auto")
        run_properties = _element(properties, "rPr")
        _element(run_properties, "color", val="475569")
        _element(run_properties, "sz", val=18)
        package.runs(paragraph, (Span(wording),))
    paragraph = footer.find(f"{{{W}}}p")
    package.runs(paragraph, (Span("\tPage "),))
    for position, field in enumerate(("PAGE", "NUMPAGES")):
        if position:
            package.runs(paragraph, (Span(" of "),))
        native = _element(paragraph, "fldSimple", instr=field, dirty="true")
        package.runs(native, (Span("1"),))
    for node in (header, footer):
        for run in node.iter(f"{{{W}}}r"):
            props = run.find(f"{{{W}}}rPr")
            _element(props, "color", val="475569")
            _element(props, "sz", val=18)
    for kind in ("header", "footer"):
        ET.SubElement(
            package.relationships,
            f"{{{REL}}}Relationship",
            Id=kind,
            Type=f"{R}/{kind}",
            Target=f"{kind}1.xml",
        )
        ET.SubElement(
            section,
            f"{{{W}}}{kind}Reference",
            {f"{{{W}}}type": "default", f"{{{R}}}id": kind},
        )
    return {"word/header1.xml": header, "word/footer1.xml": footer}


def _styles(*, summary_quotes: bool = False, source_tables: bool = False) -> ET.Element:
    styles = ET.Element(f"{{{W}}}styles")
    defaults = _element(styles, "docDefaults")
    run_defaults = _element(_element(defaults, "rPrDefault"), "rPr")
    _element(run_defaults, "rFonts", ascii="Arial", hAnsi="Arial", cs="Arial")
    _element(run_defaults, "sz", val=22)
    paragraph_defaults = _element(_element(defaults, "pPrDefault"), "pPr")
    _element(paragraph_defaults, "widowControl")
    _element(paragraph_defaults, "spacing", after=160, line=276, lineRule="auto")
    for identifier, label, size in [
        ("Normal", "Normal", 22),
        ("Title", "Title", 36),
    ] + [
        (f"Heading{level}", f"heading {level}", max(22, 34 - level * 3))
        for level in range(1, 7)
    ]:
        style = _element(styles, "style", type="paragraph", styleId=identifier)
        if identifier == "Normal":
            style.set(f"{{{W}}}default", "1")
        _element(style, "name", val=label)
        if identifier != "Normal":
            _element(style, "basedOn", val="Normal")
            _element(style, "next", val="Normal")
        _element(style, "qFormat")
        properties = _element(style, "pPr")
        if identifier != "Normal":
            _element(properties, "keepNext")
            _element(properties, "keepLines")
            _element(properties, "spacing", before=240, after=160)
            if identifier.startswith("Heading"):
                _element(properties, "outlineLvl", val=int(identifier[-1]) - 1)
        run = _element(style, "rPr")
        if identifier != "Normal":
            _element(run, "b")
        _element(run, "color", val="172C40")
        _element(run, "sz", val=size)
    for name in ("Quote", "Code"):
        style = _element(styles, "style", type="paragraph", styleId=name)
        _element(style, "name", val=name)
        _element(style, "basedOn", val="Normal")
        properties = _element(style, "pPr")
        if name == "Quote":
            borders = _element(properties, "pBdr")
            _element(borders, "left", val="single", sz=12, space=10, color="B7A774")
        else:
            _element(properties, "shd", val="clear", fill="F3F4F5")
        _element(properties, "ind", left=300, right=200)
    if summary_quotes:
        style = _element(styles, "style", type="paragraph", styleId="SummaryQuote")
        _element(style, "name", val="Summary quotation")
        _element(style, "basedOn", val="Normal")
        properties = _element(style, "pPr")
        border = _element(properties, "pBdr")
        _element(border, "left", val="single", sz=12, space=10, color="B7A774")
        _element(properties, "spacing", before=80, after=160, line=276, lineRule="auto")
        _element(properties, "ind", left=300, right=200)
        run = _element(style, "rPr")
        _element(run, "color", val="172C40")
        _element(run, "sz", val=22)
    if source_tables:
        style = _element(styles, "style", type="paragraph", styleId="SourceTableCell")
        _element(style, "name", val="Source table cell")
        _element(style, "basedOn", val="Normal")
        properties = _element(style, "pPr")
        _element(properties, "spacing", before=0, after=0, line=240, lineRule="auto")
        _element(_element(style, "rPr"), "sz", val=20)
    hyperlink = _element(styles, "style", type="character", styleId="Hyperlink")
    _element(hyperlink, "name", val="Hyperlink")
    properties = _element(hyperlink, "rPr")
    _element(properties, "color", val="245989")
    _element(properties, "u", val="single")
    return styles


def export_docx(payload: object) -> WordDocument:
    """Validate the explicit export request and return a complete OPC package."""
    if not isinstance(payload, dict) or set(payload) != {"title", "markdown"}:
        raise ValueError("A Word export needs only a title and document markdown.")
    title = _text(payload["title"], "Document title", 200, single_line=True)
    markdown = _text(payload["markdown"], "Document text", MAX_MARKDOWN)
    package = _Package()
    blocks = parse(markdown)
    summary_widths = _handover_summary_table_widths(markdown, blocks)
    qualified, summary_quotes, summary_keep = _handover_summary_presentation(
        markdown, blocks, summary_widths
    )
    source_keep, source_tables = _source_table_groups(markdown, blocks)
    keep_next = _source_note_keep_next(blocks) | summary_keep | source_keep
    compact_references = _reference_key_spacing(markdown, blocks)
    bookmarks, internal_links = _passage_navigation(
        markdown, blocks, compact_references
    )
    for index, block in enumerate(blocks):
        if isinstance(block, PageBreak):
            package.page_break()
        elif isinstance(block, Table):
            package.table(
                block,
                summary_widths.get(index),
                compact_source_table=index in source_tables,
            )
        else:
            package.paragraph(
                package.body,
                block,
                title=index == 0 and block.heading == 1,
                keep_next=index in keep_next,
                compact_reference=index in compact_references,
                bookmark=bookmarks.get(index),
                internal_links=internal_links.get(index, ()),
                summary_quote=index in summary_quotes,
            )
    package.numbering.extend(package.numbers)
    section = _element(package.body, "sectPr")
    identity_parts = _review_page_identity(package, section, title) if qualified else {}
    _element(section, "pgSz", w=11906, h=16838)
    _element(
        section,
        "pgMar",
        top=1134,
        right=1273,
        bottom=1134,
        left=1273,
        header=567,
        footer=567,
        gutter=0,
    )
    relationships = ET.Element(f"{{{REL}}}Relationships")
    ET.SubElement(
        relationships,
        f"{{{REL}}}Relationship",
        Id="document",
        Type=f"{R}/officeDocument",
        Target="word/document.xml",
    )
    ET.SubElement(
        relationships,
        f"{{{REL}}}Relationship",
        Id="properties",
        Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
        Target="docProps/core.xml",
    )
    core = ET.Element(
        "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}coreProperties"
    )
    ET.SubElement(core, "{http://purl.org/dc/elements/1.1/}title").text = title
    ET.SubElement(core, "{http://purl.org/dc/elements/1.1/}creator").text = "Sinter"
    types = ET.Element(f"{{{CT}}}Types")
    for extension, content_type in (
        ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
        ("xml", "application/xml"),
    ):
        ET.SubElement(
            types, f"{{{CT}}}Default", Extension=extension, ContentType=content_type
        )
    for part, content_type in (
        (
            "word/document.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        ),
        (
            "word/styles.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml",
        ),
        (
            "word/numbering.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml",
        ),
        (
            "docProps/core.xml",
            "application/vnd.openxmlformats-package.core-properties+xml",
        ),
    ):
        ET.SubElement(
            types, f"{{{CT}}}Override", PartName="/" + part, ContentType=content_type
        )
    for part in identity_parts:
        kind = "header" if "/header" in part else "footer"
        ET.SubElement(
            types,
            f"{{{CT}}}Override",
            PartName="/" + part,
            ContentType=(
                "application/vnd.openxmlformats-officedocument."
                f"wordprocessingml.{kind}+xml"
            ),
        )
    parts = {
        "[Content_Types].xml": types,
        "_rels/.rels": relationships,
        "word/document.xml": package.document,
        "word/styles.xml": _styles(
            summary_quotes=bool(summary_quotes), source_tables=bool(source_tables)
        ),
        "word/numbering.xml": package.numbering,
        "word/_rels/document.xml.rels": package.relationships,
        "docProps/core.xml": core,
        **identity_parts,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, node in parts.items():
            # Fixed metadata makes identical input produce identical bytes and
            # prevents the host user/path/time from leaking into the document.
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            # ZipInfo otherwise chooses its creator platform from the host.
            # Keep the original Unix metadata on every target for identical ZIPs.
            entry.create_system = 3
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, _xml(node))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", title)[:80].rstrip(". ")
    return WordDocument(f"sinter-{name or 'document'}-DRAFT.docx", output.getvalue())
