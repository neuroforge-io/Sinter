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
PRESENTATION_VERSION = "sinter-handover-presentation/v2"
EVIDENCE_MODES = frozenset({"compact", "selected_appendix"})
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


def _csv_inline(value: str) -> str:
    """Protect literal CSV spacing from table trimming and inline collapse."""
    if (
        value != value.strip()
        or "  " in value
        or any(char.isspace() and char != " " for char in value)
    ):
        rendered = _literal_code(value)
        if value.endswith("\\"):
            # Separate a trailing backslash from the closing delimiter: the
            # pipe-table tokenizer treats backslash + backtick as an escape.
            fence = rendered[: len(rendered) - len(rendered.lstrip("`"))]
            return fence + " " + value + " " + fence
        return rendered
    return literal(value)


def _csv_quote(rows: list[list[str]]) -> str:
    headers, records = rows[0], rows[1:]
    if any(
        marker in cell for row in records for cell in row for marker in _LINE_BREAKS
    ):
        lines = []
        for number, record in enumerate(records, 1):
            lines.extend([f"> **Source record {number}**", ">"])
            for label, cell in zip(headers, record):
                value = _csv_inline(cell) if cell else "—"
                prefix = "> **" + _csv_inline(label) + ":**"
                if any(marker in cell for marker in _LINE_BREAKS):
                    lines.extend([prefix, ">", _literal_quote(cell)])
                else:
                    lines.append(prefix + " " + value)
                lines.append(">")
            lines.append(">")
        return "\n".join(lines)
    table = [
        "> | " + " | ".join(_csv_inline(cell) for cell in headers) + " |",
        "> | " + " | ".join("---" for _ in headers) + " |",
    ]
    table.extend(
        "> | " + " | ".join(_csv_inline(cell) if cell else "—" for cell in row) + " |"
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


def _source_caption(title: str) -> str:
    """Keep supplied titles literal and inside the quoted metadata boundary."""
    rendered = re.sub(r"\r\n|[\r\n\v\f\x85\u2028\u2029]", "\n", title)
    lines = rendered.split("\n")
    return "> Original source: " + "\n> ".join(
        _source_text_line(literal(line)) for line in lines
    )


def reference_records(sources: list[Source], selected: list[Excerpt]) -> list[dict]:
    """Name validated passages without changing canonical identities or offsets."""
    if any(
        not isinstance(source.id, str) or not source.id.strip() for source in sources
    ):
        raise ValueError("A handover source identity is missing or invalid.")
    by_source = {source.id: source for source in sources}
    if len(by_source) != len(sources):
        raise ValueError("A handover source identity is ambiguous.")
    seen = set()
    records = []
    for number, excerpt in enumerate(selected, 1):
        if (
            not isinstance(excerpt.id, str)
            or not excerpt.id.strip()
            or excerpt.id in seen
        ):
            raise ValueError("A handover passage identity is ambiguous.")
        if not isinstance(excerpt.source_id, str) or not excerpt.source_id.strip():
            raise ValueError(
                "A handover passage no longer matches its original source."
            )
        parent = by_source.get(excerpt.source_id)
        if (
            parent is None
            or type(excerpt.start) is not int
            or type(excerpt.end) is not int
            or not validate_excerpt(excerpt, [parent])
        ):
            raise ValueError(
                "A handover passage no longer matches its original source."
            )
        seen.add(excerpt.id)
        records.append(
            {
                "label": f"Passage {number}",
                "excerpt_id": excerpt.id,
                "source_id": excerpt.source_id,
                "start": excerpt.start,
                "end": excerpt.end,
            }
        )
    return records


def render(
    title: str,
    details: dict,
    sources: list[Source],
    selected: list[Excerpt],
    questions: list[dict],
    *,
    include_selected_appendix: bool = False,
) -> str:
    """Format selected wording and question-specific checks; never mark answers."""
    if type(include_selected_appendix) is not bool:
        raise ValueError(
            "Selected evidence appendix must be explicitly enabled or disabled."
        )
    records = reference_records(sources, selected)
    by_source = {source.id: source for source in sources}
    by_excerpt = {record["excerpt_id"]: record for record in records}
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
            + ", ".join(by_excerpt[identifier]["label"] for identifier in references)
            + "."
            if references
            else "No wording match was found in the admitted text. The real-world "
            "answer remains unknown; ask for clarification or add a source."
        )
    lines.extend(
        [
            "## Selected source wording",
            "Quoted notes below reproduce the included selected wording, with "
            "readable layout. They are excerpts, not every original document "
            "or its surrounding text. Ask the sender for the full originals "
            "or project backup before confirming any commitment.",
        ]
    )
    displayed = selected[:MAX_NOTES]
    if include_selected_appendix:
        # Selected excerpts are already admitted, bounded and exact. This mode
        # changes document presentation only; it never selects more evidence.
        lines[-1] = (
            "This document reproduces every selected passage, not every original "
            "source or its unselected surrounding text. Selection does not "
            "answer the questions or confirm commitments. Full originals remain "
            "in the project backup; ask the sender for those originals when "
            "surrounding context matters."
        )
        source_count = len({item.source_id for item in selected})
        lines.append(
            f"Including all {len(selected)} selected passages from "
            f"{source_count} source{'s' if source_count != 1 else ''}. "
            "This is not an exhaustive source review."
        )
    elif selected:
        source_count = len({item.source_id for item in displayed})
        lines.append(
            f"Showing {len(displayed)} of {len(selected)} selected passages from "
            f"{source_count} source{'s' if source_count != 1 else ''}. "
            + (
                "The remaining selected passages are not reproduced in this copy. "
                "Ask the sender for the full selected evidence or project backup."
                if len(selected) > len(displayed)
                else "Unselected original text is not reproduced."
            )
        )

    def quoted_passage(excerpt):
        source = by_source[excerpt.source_id]
        note = ["### " + by_excerpt[excerpt.id]["label"], _source_caption(source.title)]
        if include_selected_appendix:
            note.append(
                "> Source link (supplied): "
                + literal(source.url or "Not supplied")
                + "\n> Date label (supplied): "
                + literal(source.retrieved_at or "Unknown")
            )
        return note + [_source_quote(source, excerpt)]

    for excerpt in displayed:
        lines.extend(quoted_passage(excerpt))
    if include_selected_appendix and len(selected) > MAX_NOTES:
        lines.extend(
            [
                "## Selected evidence appendix",
                "The remaining selected passages are reproduced below for readers "
                "without Sinter's Evidence view. They remain supplied source wording, "
                "not verified answers, accepted responsibilities or confirmed dates.",
            ]
        )
        for excerpt in selected[MAX_NOTES:]:
            lines.extend(quoted_passage(excerpt))
    elif len(selected) > MAX_NOTES:
        lines.append(
            f"{len(selected) - MAX_NOTES} additional selected passages "
            "are not reproduced in this copy. This handover is not a full source "
            "review; ask the sender for the missing wording and context."
        )
    elif not selected:
        lines.append(
            "No passages were selected. Ask the sender for relevant original "
            "wording before drawing conclusions."
        )
    if records:
        lines.extend(
            [
                "## Passage reference key",
                "These short labels refer to the exact selected excerpts. Offsets "
                "count Unicode code points from zero. The start is included; the "
                "end is excluded. Selection does not establish a verified answer.",
            ]
        )
        for number, record in enumerate(records):
            source = by_source[record["source_id"]]
            scope = (
                "quoted above."
                if number < MAX_NOTES
                else "quoted in the selected evidence appendix."
                if include_selected_appendix
                else "Selected passage not reproduced in this copy. "
                "Ask the sender for its original wording and surrounding context."
            )
            # One quoted paragraph keeps each identity/range mapping together.
            # The supplied title remains inside the literal metadata boundary.
            lines.append(
                "> **"
                + record["label"]
                + "** — "
                + _source_caption(source.title)[2:]
                + "\n> Excerpt ID: "
                + _literal_code(record["excerpt_id"])
                + "; source ID: "
                + _literal_code(record["source_id"])
                + ".\n> Unicode characters: "
                + f"{record['start']}–{record['end']}; "
                + scope
            )
    return "\n\n".join(lines)
