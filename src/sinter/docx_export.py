"""Editable, local Word documents from explicitly supplied draft text.

Uses standard-library OOXML only: no HTML importer, macros, embedded files,
network requests, or lookup of saved profile and source data.
"""

from __future__ import annotations

import io
import re
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .document_markup import Block, PageBreak, Paragraph, Span, Table, parse

MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_MARKDOWN = 500_000
# Keep one bounded source note together, never an arbitrary quote dossier.
_MAX_SOURCE_NOTE_GROUP_CHARS = 2400
_MAX_SOURCE_NOTE_GROUP_LINES = 20
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
}
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


class _Package:
    def __init__(self) -> None:
        self.document = ET.Element(f"{{{W}}}document")
        self.body = _element(self.document, "body")
        self.relationships = ET.Element(f"{{{REL}}}Relationships")
        self.numbering = ET.Element(f"{{{W}}}numbering")
        self.numbers: list[ET.Element] = []
        self.lists: dict[int, int] = {}
        self.links: dict[str, str] = {}
        for name in ("styles", "numbering"):
            ET.SubElement(
                self.relationships,
                f"{{{REL}}}Relationship",
                Id=name,
                Type=f"{R}/{name}",
                Target=f"{name}.xml",
            )

    def runs(self, parent: ET.Element, spans: tuple[Span, ...]) -> None:
        for span in spans:
            target = parent
            if span.href:
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
            if span.href:
                _element(properties, "rStyle", val="Hyperlink")
            if span.code:
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
            if span.code:
                _element(properties, "sz", val=20)
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
    ) -> None:
        node = _element(parent, "p")
        properties = _element(node, "pPr")
        if title or paragraph.heading:
            _element(
                properties,
                "pStyle",
                val="Title" if title else f"Heading{paragraph.heading}",
            )
        elif paragraph.code:
            _element(properties, "pStyle", val="Code")
        elif paragraph.quote:
            _element(properties, "pStyle", val="Quote")
        if paragraph.quote:
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
        self.runs(node, paragraph.spans)

    def table(self, table: Table) -> None:
        node = _element(self.body, "tbl")
        properties = _element(node, "tblPr")
        _element(properties, "tblW", w=0, type="auto")
        borders = _element(properties, "tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            _element(borders, edge, val="single", sz=4, color="D1D5DB")
        margins = _element(properties, "tblCellMar")
        for edge in ("top", "left", "bottom", "right"):
            _element(margins, edge, w=100, type="dxa")
        grid = _element(node, "tblGrid")
        width = 9360 // len(table.alignments)
        for _ in table.alignments:
            _element(grid, "gridCol", w=width)
        for index, row in enumerate(table.rows):
            row_node = _element(node, "tr")
            row_properties = _element(row_node, "trPr")
            _element(row_properties, "cantSplit")
            if index == 0:
                _element(row_properties, "tblHeader")
            for at, spans in enumerate(row):
                cell = _element(row_node, "tc")
                cell_properties = _element(cell, "tcPr")
                _element(cell_properties, "tcW", w=width, type="dxa")
                if index == 0:
                    _element(cell_properties, "shd", fill="F1F3F5", val="clear")
                    spans = tuple(
                        Span(span.text, True, span.italic, span.code, span.href)
                        for span in spans
                    )
                self.paragraph(cell, Paragraph(spans), align=table.alignments[at])
        self.paragraph(self.body, Paragraph(()))

    def page_break(self) -> None:
        """Use a native editable Word break without a section or hidden content."""
        node = _element(self.body, "p")
        properties = _element(node, "pPr")
        _element(properties, "spacing", before=0, after=0)
        _element(_element(node, "r"), "br", type="page")


def _styles() -> ET.Element:
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
    keep_next = _source_note_keep_next(blocks)
    compact_references = _reference_key_spacing(markdown, blocks)
    for index, block in enumerate(blocks):
        if isinstance(block, PageBreak):
            package.page_break()
        elif isinstance(block, Table):
            package.table(block)
        else:
            package.paragraph(
                package.body,
                block,
                title=index == 0 and block.heading == 1,
                keep_next=index in keep_next,
                compact_reference=index in compact_references,
            )
    package.numbering.extend(package.numbers)
    section = _element(package.body, "sectPr")
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
    parts = {
        "[Content_Types].xml": types,
        "_rels/.rels": relationships,
        "word/document.xml": package.document,
        "word/styles.xml": _styles(),
        "word/numbering.xml": package.numbering,
        "word/_rels/document.xml.rels": package.relationships,
        "docProps/core.xml": core,
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
