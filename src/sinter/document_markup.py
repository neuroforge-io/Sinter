"""Small, literal-safe document markup adapter shared by file exporters.

HTML and images are text, never instructions. Unsupported syntax stays visible.
The supported subset mirrors the writing surface: paragraphs, inline emphasis,
code, HTTP links, headings, quotes, nested lists and pipe tables.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Span:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    href: str | None = None


@dataclass(frozen=True)
class Paragraph:
    spans: tuple[Span, ...]
    heading: int = 0
    quote: bool = False
    code: bool = False
    list_id: int = 0
    list_level: int = 0
    list_start: int = 1
    ordered: bool = False


@dataclass(frozen=True)
class Table:
    rows: tuple[tuple[tuple[Span, ...], ...], ...]
    alignments: tuple[str, ...]


Block = Paragraph | Table
_INLINE = re.compile(
    r"\\[\\`*_{}\[\]#!|>]|\*\*([^\n]+?)\*\*|(?<!\w)__([^\n]+?)__(?!\w)"
    r"|(?<!`)(`+)(?!`)([^\n]*?)(?<!`)\3(?!`)"
    r"|(?<!!)\[([^\[\]\n]+)\]\((<[^<>\s]+>|(?:\\.|[^\s()\\]|\((?:\\.|[^\s()\\])*\))+)\)"
    r"|\*([^*\n]+)\*|(?<!\w)_([^_\n]+)_(?!\w)"
)
_ITEM = re.compile(r"^( *)([-+*]|\d{1,9}[.)])( +)(.*)$")
_BLOCK = re.compile(
    r"^(?: {0,3}#{1,6} | {0,3}>|\s*[-+*] |\s*\d{1,9}[.)] "
    r"| {0,3}`{3,}| {0,3}~{3,}|---+$|\*\*\*+$|___+$)"
)


def literal(value: str) -> str:
    value = re.sub(r"\\([\\`*_{}\[\]#!|>])", r"\1", value)
    return value.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def safe_href(value: str) -> str | None:
    """Validate a click target without opening it or resolving its hostname."""
    if not re.match(r"^https?://", value, re.I) or any(
        char == "\\" or char.isspace() or unicodedata.category(char) in {"Cc", "Cf"}
        for char in value
    ):
        return None
    try:
        parsed = urlsplit(value)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port == 0
        ):
            return None
    except ValueError:
        return None
    return value


def inline(value: str, depth: int = 0) -> tuple[Span, ...]:
    if depth > 6:
        return (Span(literal(value)),)
    result: list[Span] = []
    start = 0
    for match in _INLINE.finditer(value):
        if match.start() > start:
            result.append(Span(literal(value[start : match.start()])))
        if match[1] is not None or match[2] is not None:
            result.extend(
                replace(span, bold=True)
                for span in inline(match[1] or match[2], depth + 1)
            )
        elif match[3] is not None:
            content = match[4]
            if content.startswith(" ") and content.endswith(" ") and content.strip():
                content = content[1:-1]
            result.append(Span(content, code=True))
        elif match[5] is not None:
            target = literal(re.sub(r"\\([()\\])", r"\1", match[6]))
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            href = safe_href(target)
            result.append(
                Span(literal(match[5]), href=href) if href else Span(literal(match[0]))
            )
        elif match[7] is not None or match[8] is not None:
            result.extend(
                replace(span, italic=True)
                for span in inline(match[7] or match[8], depth + 1)
            )
        else:
            result.append(Span(literal(match[0])))
        start = match.end()
    if start < len(value):
        result.append(Span(literal(value[start:])))
    return tuple(result)


def cells(line: str) -> list[str]:
    values: list[str] = []
    value, ticks = "", 0
    for token in re.findall(r"\\.|`+|[^\\`|]+|\||\\", line.strip()):
        if re.fullmatch(r"`+", token):
            ticks = 0 if ticks == len(token) else ticks or len(token)
        if token == "|" and not ticks:
            values.append(value.strip())
            value = ""
        else:
            value += token
    values.append(value.strip())
    if len(values) > 1 and not values[0]:
        values.pop(0)
    if len(values) > 1 and not values[-1]:
        values.pop()
    return values


def _table_rule(line: str) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", value) for value in cells(line))


def parse(markdown: str) -> tuple[Block, ...]:
    """Return typed blocks without interpreting HTML or loading remote assets."""
    sequence = 0

    def blocks(lines: list[str], depth: int = 0, quote: bool = False) -> list[Block]:
        nonlocal sequence
        if depth > 8:
            return [Paragraph((Span(literal("\n".join(lines))),), quote=quote)]
        result: list[Block] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            fence = re.fullmatch(r"\s*(`{3,}|~{3,})([^\s]*)\s*", line)
            if fence:
                content: list[str] = []
                close = re.compile(
                    r"\s*"
                    + re.escape(fence[1][0])
                    + "{"
                    + str(len(fence[1]))
                    + r",}\s*"
                )
                i += 1
                while i < len(lines) and not close.fullmatch(lines[i]):
                    content.append(lines[i])
                    i += 1
                if i < len(lines):
                    i += 1
                result.append(
                    Paragraph(
                        (Span("\n".join(content), code=True),), quote=quote, code=True
                    )
                )
                continue
            heading = re.fullmatch(r" {0,3}(#{1,6}) (.+)", line)
            if heading:
                result.append(
                    Paragraph(inline(heading[2]), heading=len(heading[1]), quote=quote)
                )
                i += 1
                continue
            if re.fullmatch(r" {0,3}(?:-{3,}|\*{3,}|_{3,})\s*", line):
                result.append(Paragraph((Span("—"),), quote=quote))
                i += 1
                continue
            if (
                "|" in line
                and i + 1 < len(lines)
                and _table_rule(lines[i + 1])
                and len(cells(line)) == len(cells(lines[i + 1]))
            ):
                rows, rules = [cells(line)], cells(lines[i + 1])
                i += 2
                while (
                    i < len(lines)
                    and lines[i].strip()
                    and "|" in lines[i]
                    and not _BLOCK.match(lines[i])
                ):
                    rows.append(cells(lines[i]))
                    i += 1
                width = max(map(len, rows))
                if width > 63:
                    raise ValueError(
                        "A Word table can have at most 63 columns. "
                        "Split this table before exporting."
                    )
                alignments = tuple(
                    "center"
                    if rule.startswith(":") and rule.endswith(":")
                    else "right"
                    if rule.endswith(":")
                    else "left"
                    for rule in rules
                )
                result.append(
                    Table(
                        tuple(
                            tuple(
                                inline(value)
                                for value in row + [""] * (width - len(row))
                            )
                            for row in rows
                        ),
                        alignments + ("left",) * (width - len(rules)),
                    )
                )
                continue
            if re.match(r" {0,3}>", line):
                quoted: list[str] = []
                while i < len(lines) and re.match(r" {0,3}>", lines[i]):
                    quoted.append(re.sub(r"^ {0,3}> ?", "", lines[i]))
                    i += 1
                result.extend(blocks(quoted, depth + 1, True))
                continue
            item = _ITEM.match(line)
            if item:
                ordered, indent = item[2][0].isdigit(), len(item[1])
                sequence += 1
                identifier = sequence
                beginning = int(item[2][:-1]) if ordered else 1
                while i < len(lines):
                    next_item = _ITEM.match(lines[i])
                    if (
                        not next_item
                        or len(next_item[1]) != indent
                        or next_item[2][0].isdigit() != ordered
                    ):
                        break
                    content = [next_item[4]]
                    content_indent = indent + len(next_item[2]) + len(next_item[3])
                    i += 1
                    while i < len(lines):
                        if not lines[i].strip():
                            after = i + 1
                            while after < len(lines) and not lines[after].strip():
                                after += 1
                            upcoming = (
                                _ITEM.match(lines[after])
                                if after < len(lines)
                                else None
                            )
                            if (
                                upcoming
                                and len(upcoming[1]) == indent
                                and upcoming[2][0].isdigit() == ordered
                            ):
                                i = after
                                break
                            if (
                                after == len(lines)
                                or len(lines[after]) - len(lines[after].lstrip())
                                <= indent
                            ):
                                break
                            content.append("")
                            i += 1
                            continue
                        spaces = len(lines[i]) - len(lines[i].lstrip())
                        if spaces <= indent:
                            break
                        content.append(lines[i][min(content_indent, spaces) :])
                        i += 1
                    children = blocks(content, depth + 1, quote)
                    if not children or isinstance(children[0], Table):
                        children.insert(0, Paragraph(()))
                    children[0] = replace(
                        children[0],
                        list_id=identifier,
                        list_level=min(depth, 8),
                        list_start=beginning,
                        ordered=ordered,
                    )
                    result.extend(children)
                continue
            paragraph = [line]
            i += 1
            while (
                i < len(lines)
                and lines[i].strip()
                and not _BLOCK.match(lines[i])
                and not (
                    "|" in lines[i] and i + 1 < len(lines) and _table_rule(lines[i + 1])
                )
            ):
                paragraph.append(lines[i])
                i += 1
            spans: list[Span] = []
            for at, value in enumerate(paragraph):
                ending = re.search(r"\\+$", value)
                if at < len(paragraph) - 1 and ending and len(ending[0]) % 2:
                    value = value[:-1]
                else:
                    value = re.sub(r" {2,}$", "", value)
                spans.extend(inline(value))
                if at < len(paragraph) - 1:
                    spans.append(Span("\n"))
            result.append(Paragraph(tuple(spans), quote=quote))
        return result

    return tuple(blocks(markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")))
