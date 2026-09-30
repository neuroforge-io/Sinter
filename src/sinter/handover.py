"""Readable source-only handovers, without answering questions or inferring actions.

This is a presentation adapter. Evidence selection and exact originals belong to
the casebook; unsupported or ambiguous layouts remain quoted literal text.
"""

from __future__ import annotations

import csv
import io
import re

from .document_markup import inline
from .evidence import Excerpt, Source, literal, validate_excerpt

MAX_NOTES = 4
MAX_TABLE_ROWS = 40
MAX_TABLE_COLUMNS = 12
_LINE_BREAKS = "\r\n\v\f\x85\u2028\u2029"
_FIELDS = frozenset(
    {
        "action",
        "task",
        "scope",
        "owner",
        "status",
        "date",
        "deadline",
        "item",
        "quantity",
        "amount",
        "cost",
        "name",
        "role",
        "notes",
        "description",
    }
)


def _literal_code(value: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * max(1, longest + 1)
    padding = (
        value.startswith("`")
        or value.endswith("`")
        or (value.startswith(" ") and value.endswith(" ") and bool(value.strip()))
    )
    return fence + (" " + value + " " if padding else value) + fence


def _source_inline(value: str, emphasis: bool = True) -> str:
    """Promote supported emphasis only; source links remain visible wording."""
    parts = []
    for span in inline(value):
        if span.code:
            parts.append(_literal_code(span.text))
            continue
        rendered = literal(span.text)
        if emphasis and span.bold and not span.code:
            rendered = "**" + rendered + "**"
        if emphasis and span.italic and not span.code:
            rendered = "*" + rendered + "*"
        if span.href:
            rendered += " (" + literal(span.href) + ")"
        parts.append(rendered)
    return "".join(parts)


def _literal_quote(value: str) -> str:
    # Literal multiline text must not become a list or horizontal rule when an
    # exporter parses the quoted block. Choose a fence absent from the original.
    rendered = re.sub(r"\r\n|[\r\n\v\f\x85\u2028\u2029]", "\n", value)
    longest = max((len(run) for run in re.findall(r"`+", rendered)), default=0)
    fence = "`" * max(3, longest + 1)
    return "> " + fence + "text\n> " + rendered.replace("\n", "\n> ") + "\n> " + fence


def _csv_rows(source: Source, excerpt: Excerpt):
    # A fragment cannot establish column labels or a complete multiline record.
    if excerpt.start != 0 or excerpt.end != len(source.content):
        return None
    try:
        rows = list(csv.reader(io.StringIO(excerpt.quote, newline=""), strict=True))
    except csv.Error:
        return None
    if not 2 <= len(rows) <= MAX_TABLE_ROWS + 1:
        return None
    headers = rows[0]
    if not 2 <= len(headers) <= MAX_TABLE_COLUMNS:
        return None
    labels = [value.strip().casefold() for value in headers]
    if (
        any(not value for value in labels)
        or any(marker in value for value in headers for marker in _LINE_BREAKS)
        or len(set(labels)) != len(labels)
        or any(len(row) != len(headers) for row in rows[1:])
    ):
        return None
    # A filename does not establish that row one contains headers. Require
    # recognisable labels before promoting it to column headings.
    if len(set(labels) & _FIELDS) < 2:
        return None
    return rows


def _csv_quote(rows: list[list[str]]) -> str:
    headers, records = rows[0], rows[1:]
    if any(
        marker in cell for row in records for cell in row for marker in _LINE_BREAKS
    ):
        lines = []
        for number, record in enumerate(records, 1):
            lines.extend([f"> **Source record {number}**", ">"])
            for label, cell in zip(headers, record):
                value = literal(cell) if cell else "—"
                prefix = "> **" + literal(label) + ":**"
                if any(marker in cell for marker in _LINE_BREAKS):
                    lines.extend([prefix, ">", _literal_quote(cell)])
                else:
                    lines.append(prefix + " " + value)
                lines.append(">")
            lines.append(">")
        return "\n".join(lines)
    table = [
        "> | " + " | ".join(literal(cell) for cell in headers) + " |",
        "> | " + " | ".join("---" for _ in headers) + " |",
    ]
    table.extend(
        "> | " + " | ".join(literal(cell) if cell else "—" for cell in row) + " |"
        for row in records
    )
    return "\n".join(table)


def _source_text_line(value: str) -> str:
    """Keep source numbering and rule markers out of generated block syntax."""
    rendered = _source_inline(value)
    numbered = re.match(r"^( *)(\d{1,9}[.)]) (.*)$", rendered)
    if numbered:
        return numbered[1] + "**" + numbered[2] + "** " + numbered[3]
    if re.fullmatch(r"\s*-{3,}\s*", rendered):
        return _literal_code(rendered)
    return rendered


def _source_quote(source: Source, excerpt: Excerpt) -> str:
    rows = _csv_rows(source, excerpt)
    if rows is not None:
        return (
            "Quoted source table. Blank cells are shown as —; entries do not "
            "confirm assignments or dates.\n\n" + _csv_quote(rows)
        )
    lines = excerpt.quote.splitlines()
    # Failed or partial CSV stays literal, including every row and cell.
    if source.title.lower().endswith(".csv") or (
        lines
        and len({cell.strip().casefold() for cell in lines[0].split(",")} & _FIELDS)
        >= 2
    ):
        return (
            "Quoted source wording. Table layout could not be confirmed; "
            "the original text is retained.\n\n" + _literal_quote(excerpt.quote)
        )
    if any(re.match(r"^\s*(?:`{3,}|~{3,})", line) for line in lines):
        return _literal_quote(excerpt.quote)
    formatted = []
    for line in lines:
        heading = re.match(r"^ {0,3}#{1,6} (.+)$", line)
        item = re.match(r"^( *)([-+*]|\d{1,9}[.)]) (.*)$", line)
        quote = re.match(r"^ {0,3}> ?(.*)$", line)
        if heading:
            rendered = "**" + _source_inline(heading[1], emphasis=False) + "**"
        elif item and item[2][0].isdigit():
            # Source numbers can identify nonsequential items. An exported
            # ordered list would silently renumber them, so keep the marker.
            rendered = _source_text_line(line)
        elif item:
            rendered = item[1] + item[2] + " " + _source_inline(item[3])
        elif quote:
            rendered = "> " + _source_text_line(quote[1])
        else:
            rendered = _source_text_line(line)
        formatted.append("> " + rendered)
    return "\n".join(formatted)


def render(
    title: str,
    details: dict,
    sources: list[Source],
    selected: list[Excerpt],
    questions: list[dict],
) -> str:
    """Format selected wording and question-specific checks; never mark answers."""
    by_source = {source.id: source for source in sources}
    by_excerpt = {excerpt.id: excerpt for excerpt in selected}
    if any(not validate_excerpt(excerpt, sources) for excerpt in selected):
        raise ValueError("A handover passage no longer matches its original source.")
    lines = [
        "# " + literal(title),
        "Source-only handover checklist — review before using.",
    ]
    for key, label in (("recipient", "Prepared for"), ("signatory", "Prepared by")):
        if details.get(key):
            lines.append(label + ": " + literal(details[key]))
    if details.get("sender_role"):
        lines.append("Role: " + literal(details["sender_role"]))
    if details.get("organisation"):
        lines.append(literal(details["organisation"]))
    if details.get("contact_details"):
        lines.append("Contact details: " + literal(details["contact_details"]))
    lines.extend(
        [
            "## Handover next steps",
            "Review each question against its related wording, then record the "
            "confirmed response and who will follow it up. A wording match is not "
            "an answer; no owner or target date is assigned by this checklist.",
        ]
    )
    for number, row in enumerate(questions, 1):
        references = row["excerpt_ids"]
        if any(identifier not in by_excerpt for identifier in references):
            raise ValueError("A handover question refers to unavailable evidence.")
        lines.append(f"### {number}. {literal(row['question'])}")
        lines.append(
            "Related wording — review required: "
            + ", ".join("[" + identifier + "]" for identifier in references)
            + "."
            if references
            else "No wording match was found in the admitted text. The real-world "
            "answer remains unknown; ask for clarification or add a source."
        )
    lines.extend(
        [
            "## Selected source wording",
            "Quoted source notes below preserve the supplied words, with "
            "readable layout. Read the exact originals and surrounding "
            "context in Evidence before confirming any commitment.",
        ]
    )
    displayed = selected[:MAX_NOTES]
    if selected:
        source_count = len({item.source_id for item in displayed})
        lines.append(
            f"Showing {len(displayed)} of {len(selected)} selected passages from "
            f"{source_count} source{'s' if source_count != 1 else ''}. All selected "
            "passages remain available in Evidence."
        )
    for number, excerpt in enumerate(displayed, 1):
        source = by_source[excerpt.source_id]
        lines.extend(
            [
                "### "
                + literal(source.title)
                + f" — passage {number} "
                + "["
                + excerpt.id
                + "]",
                _source_quote(source, excerpt),
            ]
        )
    if len(selected) > MAX_NOTES:
        lines.append(
            f"{len(selected) - MAX_NOTES} additional selected passages "
            "remain in Evidence. This handover is not a full source review."
        )
    elif not selected:
        lines.append(
            "No passages were selected. The original documents remain "
            "in the casebook; add relevant wording before drawing conclusions."
        )
    return "\n\n".join(lines)
