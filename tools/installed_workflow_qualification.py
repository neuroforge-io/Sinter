"""Admit only source-bound fictional output from the installed Linux UI gate."""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import re
import struct
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree as ET

from tools.installed_workflow_contract import (
    ACTION_TASK,
    ARTIFACT_PATHS,
    COMMUNICATION,
    MAX_ARTIFACT_BYTES,
    MAX_TOTAL_BYTES,
    OPERATOR_NOTE,
    PRACTICE_FILES,
    RECEIPT_FIELDS,
    RECIPIENT,
    RESOURCE_FLAGS,
    RESTORED_CAMPAIGN_TITLE,
    RESTORED_CASEBOOK_TITLE,
    WORD_CHANGED_NOTE,
    requires_word_copy,
    workflow_artifact_paths,
    workflow_checks,
    workflow_schema,
)

WORD_PARTS = frozenset(
    {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/styles.xml",
        "word/numbering.xml",
        "word/_rels/document.xml.rels",
        "docProps/core.xml",
    }
)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
SHA = re.compile(r"[0-9a-f]{64}")


def canonical_hash(value: object) -> str:
    """Hash JSON data without wrapper entropy or ambiguous numeric values."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Installed workflow JSON contains duplicate keys.")
        result[key] = value
    return result


def json_object(content: bytes) -> dict:
    """Read bounded JSON objects without duplicate keys or nonfinite numbers."""
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("Installed workflow JSON exceeds its bound.")
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError("Installed workflow JSON contains a nonfinite number.")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Installed workflow evidence is not JSON.") from error
    if not isinstance(value, dict):
        raise ValueError("Installed workflow evidence must be a JSON object.")
    return value


def _same_json(actual: object, expected: object) -> bool:
    return json.dumps(actual, sort_keys=True, ensure_ascii=False, allow_nan=False) == (
        json.dumps(expected, sort_keys=True, ensure_ascii=False, allow_nan=False)
    )


def fictional_documents(source: dict[str, bytes]) -> tuple[dict, dict, dict, dict]:
    """Derive the only admitted backup edits from the pinned source fixtures."""
    try:
        original_book, original_campaign = (
            json_object(source[name]) for name in PRACTICE_FILES
        )
    except KeyError as error:
        raise ValueError(
            "The candidate lacks its fictional practice fixtures."
        ) from error
    if (
        original_book.get("schema") != "sinter-casebook/v1"
        or original_campaign.get("schema") != "sinter-campaign/v1"
        or not original_book.get("documents")
        or not original_campaign.get("actions")
        or not original_campaign.get("opportunities")
    ):
        raise ValueError("The pinned fictional practice fixture is incomplete.")
    book = json.loads(json.dumps(original_book))
    book.pop("fingerprint", None)
    book["recipient"] = RECIPIENT
    for key in ("signatory", "sender_role", "contact_details"):
        book.setdefault(key, "")
    campaign = json.loads(json.dumps(original_campaign))
    campaign["actions"][0]["task"] = ACTION_TASK
    campaign["communications"].append(
        {
            **COMMUNICATION,
            "opportunity": "",
            "evidence_links": [],
        }
    )
    return original_book, original_campaign, book, campaign


def validate_png(content: bytes) -> None:
    """Admit bounded browser PNG pixels without text or arbitrary metadata."""
    if len(content) > MAX_ARTIFACT_BYTES or content[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("An installed workflow screenshot is not a bounded PNG.")
    cursor, width, height, channels = 8, 0, 0, 0
    compressed = bytearray()
    ended, seen_header, seen_data = False, False, False
    metadata = set()
    while cursor < len(content):
        if cursor + 12 > len(content):
            raise ValueError("A PNG chunk is truncated.")
        size, kind = struct.unpack(">I4s", content[cursor : cursor + 8])
        stop = cursor + 12 + size
        if stop > len(content) or size > MAX_ARTIFACT_BYTES:
            raise ValueError("A PNG chunk exceeds its bound.")
        data = content[cursor + 8 : cursor + 8 + size]
        crc = struct.unpack(">I", content[cursor + 8 + size : stop])[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != crc:
            raise ValueError("A PNG chunk has invalid bytes.")
        if not seen_header and kind != b"IHDR":
            raise ValueError("A PNG must start with its image header.")
        if kind == b"IHDR":
            if seen_header or size != 13:
                raise ValueError("A PNG has a duplicate or invalid header.")
            width, height, depth, color, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", data)
            )
            if (
                not 1 <= width <= 4096
                or not 1 <= height <= 4096
                or width * height > 8_000_000
                or depth != 8
                or color not in {2, 6}
                or (compression, filtering, interlace) != (0, 0, 0)
            ):
                raise ValueError("A PNG uses an unsupported or oversized image.")
            channels, seen_header = (3 if color == 2 else 4), True
        elif kind == b"IDAT":
            if ended:
                raise ValueError("A PNG contains data after its end.")
            compressed.extend(data)
            seen_data = True
        elif kind == b"IEND":
            if size or not seen_data or stop != len(content):
                raise ValueError("A PNG has an invalid end or trailing content.")
            ended = True
        elif kind not in {b"sRGB", b"pHYs"} or seen_data:
            raise ValueError("A PNG contains unadmitted metadata or chunks.")
        else:
            if (
                kind in metadata
                or (kind == b"sRGB" and (size != 1 or data[0] > 3))
                or (kind == b"pHYs" and (size != 9 or data[-1] > 1))
            ):
                raise ValueError("A PNG has invalid or duplicate image metadata.")
            metadata.add(kind)
        cursor = stop
    if not ended:
        raise ValueError("A PNG image has no end.")
    bound = (width * channels + 1) * height
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(compressed, bound + 1)
    except zlib.error as error:
        raise ValueError("A PNG has invalid compressed pixels.") from error
    if (
        len(pixels) != bound
        or not decoder.eof
        or decoder.unused_data
        or decoder.unconsumed_tail
        or any(pixels[row * (width * channels + 1)] > 4 for row in range(height))
    ):
        raise ValueError("A PNG decoded image differs from its bounded header.")


def _word_paragraphs(content: bytes) -> tuple[list[str], dict[str, ET.Element]]:
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("The installed Word download exceeds its bound.")
    parsed, seen, total = {}, set(), 0
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for member in archive.infolist():
                name = member.filename
                total += member.file_size
                if (
                    name not in WORD_PARTS
                    or name in seen
                    or member.is_dir()
                    or member.flag_bits & 1
                    or (member.external_attr >> 16) & 0o170000 not in {0, 0o100000}
                    or member.file_size > MAX_ARTIFACT_BYTES
                    or total > 4 * MAX_ARTIFACT_BYTES
                ):
                    raise ValueError("The Word download contains unadmitted members.")
                seen.add(name)
                data = archive.read(member)
                if re.search(rb"<!\s*(?:DOCTYPE|ENTITY|--)", data, re.I):
                    raise ValueError(
                        "The Word download contains unsafe XML declarations."
                    )
                parsed[name] = ET.fromstring(data)
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError) as error:
        raise ValueError("The installed Word download is not valid OOXML.") from error
    if seen != WORD_PARTS:
        raise ValueError("The Word download omits required OOXML parts.")
    for name, expected in (
        ("_rels/.rels", {"word/document.xml", "docProps/core.xml"}),
        ("word/_rels/document.xml.rels", {"styles.xml", "numbering.xml"}),
    ):
        if parsed[name].tag != REL + "Relationships":
            raise ValueError("The Word relationship root is invalid.")
        if len(parsed[name]) != len(expected):
            raise ValueError("The Word relationship inventory differs.")
        for node in parsed[name]:
            if (
                node.tag != REL + "Relationship"
                or node.get("TargetMode")
                or set(node.attrib) != {"Id", "Type", "Target"}
                or node.get("Target") not in expected
            ):
                raise ValueError("The Word download contains unadmitted relationships.")
        if {node.get("Target") for node in parsed[name]} != expected:
            raise ValueError("The Word relationships are missing or duplicated.")
    document = parsed["word/document.xml"]
    if document.tag != W + "document":
        raise ValueError("The Word download has no Word document root.")
    paragraphs = []
    for paragraph in document.iter(W + "p"):
        text = "".join(
            (node.text or "")
            if node.tag == W + "t"
            else "\n"
            if node.tag == W + "br"
            else "\t"
            if node.tag == W + "tab"
            else ""
            for node in paragraph.iter()
        )
        paragraphs.append(text)
    return paragraphs, parsed


def validate_word(content: bytes, book: dict) -> None:
    """Check the fictional handover's words, exact key and appended operator note."""
    paragraphs, parsed = _word_paragraphs(content)
    text = "\n".join(paragraphs)
    core = parsed["docProps/core.xml"]
    if (
        core.findtext("{http://purl.org/dc/elements/1.1/}title") != book["title"]
        or core.findtext("{http://purl.org/dc/elements/1.1/}creator") != "Sinter"
    ):
        raise ValueError("The Word download is not the fictional handover.")
    for required in (
        "Source-only handover checklist",
        "The real-world answer remains unknown",
        "The equipment quote has not been received.",
        "No person has accepted the actions.",
        "not a confirmed deadline or grant closing date",
        "Passage reference key",
        OPERATOR_NOTE.split("\n\n")[-1],
    ):
        if required not in text:
            raise ValueError(
                "The Word download loses fictional qualifications or edits."
            )
    # Full fixture passages are shorter than the indexed chunk bound. Every exact
    # source/excerpt/range must occur together once in the exported reference key.
    for source in book["documents"]:
        end = len(source["content"])
        identifier = (
            "E" + hashlib.sha256(f"{source['id']}:0:{end}".encode()).hexdigest()[:24]
        )
        matching = [row for row in paragraphs if identifier in row]
        if (
            len(matching) != 1
            or source["id"] not in matching[0]
            or f"0–{end}; quoted above." not in matching[0]
            or source["title"] not in matching[0]
        ):
            raise ValueError("The Word download has no complete exact passage key.")
    if parsed["word/document.xml"].find(".//" + W + "tbl") is None:
        raise ValueError("The fictional source table is missing from Word.")
    _known_word_paragraphs(paragraphs, book)


def _known_word_paragraphs(paragraphs: list[str], book: dict) -> None:
    # A closed text vocabulary prevents a resealed file from carrying unrelated
    # private prose alongside valid fixture phrases. Styling remains reviewable.
    allowed = {
        "",
        book["title"],
        book["organisation"],
        "Prepared for: " + RECIPIENT,
        "Source-only handover checklist — review before using.",
        "Handover next steps",
        "Selected source wording",
        "Passage reference key",
        "Fictional operator note",
        OPERATOR_NOTE.split("\n\n")[-1],
        "Review each question against its related wording, then record the confirmed "
        "response and who will follow it up. A wording match is not an answer; no "
        "owner or target date is assigned by this checklist.",
        "No wording match was found in the admitted text. The real-world answer "
        "remains unknown; ask for clarification or add a source.",
        "Quoted source notes below preserve the supplied words, with readable "
        "layout. Read the exact originals and surrounding context in Evidence "
        "before confirming any commitment.",
        "Showing 4 of 4 selected passages from 4 sources. All selected passages "
        "remain available in Evidence.",
        "Quoted source table. Blank cells are shown as —; entries do not confirm "
        "assignments or dates.",
        "These short labels refer to the exact selected excerpts. Offsets count "
        "Unicode code points from zero. The start is included; the end is excluded. "
        "Selection does not establish a verified answer.",
    }
    for number, question in enumerate(book["questions"].splitlines(), 1):
        allowed.add(f"{number}. {question}")
    for source in book["documents"]:
        allowed.add("Original source: " + source["title"])
        for line in source["content"].splitlines():
            allowed.add(re.sub(r"^\s*(?:#{1,6}|>|-)\s+", "", line))
        if source["content"].startswith("Action,Scope,"):
            for row in csv.reader(io.StringIO(source["content"], newline="")):
                allowed.update(cell or "—" for cell in row)
        identifier = (
            "E"
            + hashlib.sha256(
                f"{source['id']}:0:{len(source['content'])}".encode()
            ).hexdigest()[:24]
        )
        for number in range(1, 5):
            allowed.add(f"Passage {number}")
            allowed.add(
                f"Passage {number} — Original source: {source['title']}\n"
                f"Excerpt ID: {identifier}; source ID: {source['id']}.\n"
                f"Unicode characters: 0–{len(source['content'])}; quoted above."
            )

    def normalize(value: str) -> str:
        return " ".join(value.split())

    allowed = {normalize(value) for value in allowed}
    related = re.compile(
        r"Related wording — review required: Passage [1-4]"
        r"(?:, Passage [1-4])*\."
    )
    for paragraph in paragraphs:
        value = normalize(paragraph)
        if value not in allowed and not related.fullmatch(value):
            raise ValueError("The Word download contains unrelated or private wording.")


def verify_installed_workflow(
    folder: Path,
    version: str,
    commit: str,
    sums: dict[str, str],
    source: dict[str, bytes],
    native_receipt: dict,
    binary_sha256: str,
) -> None:
    """Require exact installed/offline identity, retained bytes and fictional data."""
    path = folder / "installed-workflow-browser.json"
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("The installed workflow receipt exceeds its bound.")
    receipt = json_object(path.read_bytes())
    if set(receipt) != RECEIPT_FIELDS:
        raise ValueError(
            "The installed workflow receipt has missing or unknown fields."
        )
    roles = workflow_artifact_paths(source)
    fixed = {
        "schema": workflow_schema(source),
        "passed": True,
        "version": version,
        "source_commit": commit,
        "system": "Linux",
        "target_arch": "x64",
        "machine": "x86_64",
        "pointer_bits": 64,
        "frozen": True,
        "desktop": True,
        "installed_executable": "/opt/neuroforge/sinter/Sinter",
        "installer_sha256": native_receipt["installer_sha256"],
        "source_archive_sha256": sums[f"sinter-{version}-source.zip"],
        "native_receipt_sha256": sums[f"Sinter-{version}-linux-x64-test.json"],
        "installed_binary_sha256": binary_sha256,
        "container": "ubuntu:22.04",
        "network": "disabled container; loopback only",
        "network_mode": "none",
        "host_installation": False,
        "libc": ["glibc", "2.35"],
        "os_release": {"ID": "ubuntu", "VERSION_ID": "22.04"},
        "external_requests": 0,
        "page_errors": 0,
        "model_calls": 0,
        "checks": list(workflow_checks(source)),
        "resources": dict.fromkeys(RESOURCE_FLAGS, True),
    }
    for key, value in fixed.items():
        if type(receipt[key]) is not type(value) or not _same_json(receipt[key], value):
            raise ValueError(
                "The installed workflow identity, checks or scope differs."
            )
    if not isinstance(receipt["image_id"], str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", receipt["image_id"]
    ):
        raise ValueError(
            "The installed workflow has no exact container image identity."
        )
    web = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in source.items()
        if name.startswith("src/sinter/web/")
    }
    practice = {
        name: hashlib.sha256(source[name]).hexdigest()
        for name in PRACTICE_FILES
        if name in source
    }
    if (
        not _same_json(receipt["web_assets_sha256"], web)
        or not _same_json(receipt["practice_fixture_sha256"], practice)
        or len(practice) != len(PRACTICE_FILES)
    ):
        raise ValueError("Installed workflow static and fictional inputs differ.")
    artifacts = receipt["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != len(roles):
        raise ValueError("The installed workflow artifact inventory is incomplete.")
    seen, total, retained = set(), 0, {}
    for row in artifacts:
        if (
            not isinstance(row, dict)
            or set(row) != {"role", "path", "sha256", "bytes"}
            or not isinstance(row["role"], str)
            or row["role"] not in roles
            or row["role"] in seen
            or row["path"] != roles[row["role"]]
            or not isinstance(row["sha256"], str)
            or not SHA.fullmatch(row["sha256"])
            or type(row["bytes"]) is not int
            or not 1 <= row["bytes"] <= MAX_ARTIFACT_BYTES
        ):
            raise ValueError(
                "An installed workflow artifact role is invalid or duplicated."
            )
        artifact = folder / row["path"]
        if (
            artifact.is_symlink()
            or not artifact.is_file()
            or artifact.stat().st_size != row["bytes"]
        ):
            raise ValueError("An installed workflow artifact is absent or changed.")
        data = artifact.read_bytes()
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("An installed workflow artifact differs from its hash.")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ValueError(
                "Installed workflow artifacts exceed their combined bound."
            )
        seen.add(row["role"])
        retained[row["role"]] = data
    original_book, original_campaign, book, campaign = fictional_documents(source)
    if not _same_json(json_object(retained["casebook_backup"]), book) or not _same_json(
        json_object(retained["campaign_backup"]), campaign
    ):
        raise ValueError("Installed backups differ from the fixed fictional edits.")
    for role, data in retained.items():
        if role not in ARTIFACT_PATHS or role.endswith("backup"):
            continue
        if role == "handover_word":
            validate_word(data, book)
        else:
            validate_png(data)
    if requires_word_copy(source):
        validate_operations_catalog(
            json_object(retained["operations_catalog"]), source, version
        )
        validate_word_copy_recovery(retained, source, book, receipt)
    _verify_result_hashes(
        receipt, original_book, original_campaign, book, campaign, web
    )


def _verify_result_hashes(
    receipt: dict,
    original_book: dict,
    original_campaign: dict,
    book: dict,
    campaign: dict,
    web: dict,
) -> None:
    inputs = {
        "garden_casebook": canonical_hash(original_book),
        "garden_campaign": canonical_hash(original_campaign),
        "static_assets": canonical_hash(web),
    }
    if not _same_json(receipt["input_hashes"], inputs):
        raise ValueError(
            "The installed workflow input hashes differ from source fixtures."
        )
    normalized = dict(book)
    normalized["fingerprint"] = hashlib.sha256(
        json.dumps(
            book,
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    restored_book = {**book, "title": RESTORED_CASEBOOK_TITLE}
    restored_book["fingerprint"] = hashlib.sha256(
        json.dumps(restored_book, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    restored_campaign = {**campaign, "title": RESTORED_CAMPAIGN_TITLE}
    results = receipt["result_hashes"]
    expected = {
        "saved_casebook": canonical_hash(normalized),
        "restored_casebook": canonical_hash(restored_book),
        "saved_campaign": canonical_hash(campaign),
        "restored_campaign": canonical_hash(restored_campaign),
    }
    if (
        not isinstance(results, dict)
        or set(results) != {*expected, "saved_report"}
        or any(results.get(key) != value for key, value in expected.items())
        or not isinstance(results["saved_report"], str)
        or not SHA.fullmatch(results["saved_report"])
    ):
        raise ValueError(
            "The installed workflow result hashes do not bind retained data."
        )


def source_operations(source: dict[str, bytes]) -> list[dict]:
    """Read the closed literal catalogue; never execute candidate source."""
    try:
        tree = ast.parse(source["src/sinter/runtime.py"])
        entries = next(
            node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_OPERATIONS"
                for target in node.targets
            )
        )
        result = []
        for entry in entries.elts:
            if (
                not isinstance(entry, ast.Call)
                or not isinstance(entry.func, ast.Name)
                or entry.func.id != "Operation"
                or entry.keywords
                or not 4 <= len(entry.args) <= 6
            ):
                raise ValueError(
                    "The candidate catalogue is not a closed literal contract."
                )
            values = [ast.literal_eval(argument) for argument in entry.args]
            values += [
                "JSON object; omitted fields retain the existing API defaults.",
                "local",
            ][len(values) - 4 :]
            if any(not isinstance(value, str) for value in values):
                raise ValueError("The candidate catalogue contains non-text fields.")
            result.append(
                dict(
                    zip(("id", "method", "route", "summary", "input", "effect"), values)
                )
            )
    except (KeyError, StopIteration, SyntaxError, AttributeError, TypeError) as error:
        raise ValueError(
            "The candidate has no admitted operation catalogue."
        ) from error
    if len(result) != 53 or len({entry["id"] for entry in result}) != 53:
        raise ValueError(
            "The current installed workflow requires exactly 53 operations."
        )
    save = next((entry for entry in result if entry["id"] == "documents.docx.save"), {})
    if (save.get("method"), save.get("route"), save.get("effect")) != (
        "POST",
        "/api/documents/docx/save",
        "write",
    ):
        raise ValueError(
            "The current catalogue lacks the explicit Word-copy write contract."
        )
    return result


def validate_operations_catalog(
    value: dict, source: dict[str, bytes], version: str
) -> None:
    """Bind the complete CLI success envelope and source-declared catalogue."""
    catalogue = {
        "schema": "sinter-operations/v1",
        "version": version,
        "operations": source_operations(source),
        "excluded": [
            "account setup",
            "credentials",
            "settings mutations",
            "HTTP session/security controls",
            "desktop lifecycle",
        ],
        "jobs": "Temporary within one Runtime; CLI waits and never starts a daemon."
        " Save/export useful results explicitly.",
    }
    expected = {
        "schema": "sinter-operation-result/v1",
        "version": version,
        "operation": "operations",
        "ok": True,
        "result": catalogue,
    }
    if not _same_json(value, expected):
        raise ValueError(
            "Installed capabilities differ from the exact 53-operation source contract."
        )


def _word_copy_zip_envelope(content: bytes, archive: zipfile.ZipFile) -> None:
    """Admit only ordinary compiler ZIP records, without hidden extra data."""
    if len(content) < 22:
        raise ValueError("Saved Word ZIP footer is incomplete.")
    footer = struct.unpack("<4s4H2LH", content[-22:])
    if (
        footer[:5] != (b"PK\x05\x06", 0, 0, len(WORD_PARTS), len(WORD_PARTS))
        or footer[5] + footer[6] != len(content) - 22
        or footer[7] != 0
        or archive.comment
    ):
        raise ValueError("Saved Word ZIP contains unsupported footer or trailing data.")
    position = 0
    for member in sorted(archive.infolist(), key=lambda entry: entry.header_offset):
        if (
            member.header_offset != position
            or member.comment
            or member.extra
            or member.flag_bits != 0
            or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            or position + 30 > footer[6]
        ):
            raise ValueError("Saved Word ZIP contains unsupported member metadata.")
        header = struct.unpack("<4s5H3L2H", content[position : position + 30])
        name = member.filename.encode("ascii")
        if (
            header[0] != b"PK\x03\x04"
            or header[1:4]
            != (member.extract_version, member.flag_bits, member.compress_type)
            or header[6:]
            != (member.CRC, member.compress_size, member.file_size, len(name), 0)
            or content[position + 30 : position + 30 + len(name)] != name
        ):
            raise ValueError("Saved Word ZIP local header differs from its directory.")
        position += 30 + len(name)
        compressed = content[position : position + member.compress_size]
        if member.compress_type == zipfile.ZIP_DEFLATED:
            decoder = zlib.decompressobj(-15)
            try:
                decoder.decompress(compressed)
            except zlib.error as error:
                raise ValueError("Saved Word ZIP compression is invalid.") from error
            if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError("Saved Word ZIP contains hidden compressed data.")
        elif len(compressed) != member.file_size:
            raise ValueError("Saved Word ZIP stored member length differs.")
        position += member.compress_size
    if position != footer[6]:
        raise ValueError("Saved Word ZIP contains data outside its members.")


def validate_word_copy_recovery(
    retained: dict[str, bytes], source: dict[str, bytes], book: dict, receipt: dict
) -> None:
    """A response alone cannot replace saved bytes, snapshots and conservation."""
    # Bind all transitive local rendering code before calling the verifier's
    # compiler. Policy tooling may differ; admitted application Python may not.
    root = Path(__file__).resolve().parents[1]
    expected_python = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in (root / "src/sinter").rglob("*.py")
    }
    actual_python = {
        name: content
        for name, content in source.items()
        if name.startswith("src/sinter/") and name.endswith(".py")
    }
    if actual_python != expected_python:
        raise ValueError(
            "Word verification needs the exact candidate Python rendering code."
        )
    from sinter import casebooks, docx_export

    proof = json_object(retained["word_copy_recovery"])
    fields = {
        "schema",
        "snapshots",
        "pending",
        "uncertain",
        "before",
        "after",
        "saved_report",
        "synthetic_download_denials",
    }
    if set(proof) != fields or proof["schema"] != "sinter-installed-word-copy/v1":
        raise ValueError("Word recovery evidence has missing or unknown fields.")
    original = {
        "title": book["title"],
        "markdown": casebooks.build(book)["document_markdown"] + OPERATOR_NOTE,
    }
    changed = {**original, "markdown": original["markdown"] + WORD_CHANGED_NOTE}
    rows = proof["snapshots"]
    if not isinstance(rows, list) or len(rows) != 3:
        raise ValueError("Word recovery requires three actual distinct local copies.")
    paths = set()
    for row, payload, role in zip(
        rows,
        (original, changed, changed),
        ("word_copy_applied", "word_copy_changed", "word_copy_unconfirmed"),
    ):
        if not isinstance(row, dict) or set(row) != {
            "payload",
            "response",
            "file_mode",
            "file_links",
        }:
            raise ValueError("A Word snapshot observation has unsupported fields.")
        response = row["response"]
        if (
            not _same_json(row["payload"], payload)
            or not isinstance(response, dict)
            or set(response)
            != {
                "path",
                "filename",
                "bytes",
                "sha256",
                "content_type",
                "verification",
                "title",
                "markdown_sha256",
                "snapshot_sha256",
            }
        ):
            raise ValueError("Word recovery did not retain the exact applied snapshot.")
        name = response["filename"]
        if (
            not isinstance(name, str)
            or not name.endswith(".docx")
            or len(name.encode("utf-8")) > 150
            or re.search(r"[\\/\x00-\x1f]", name)
            or response["path"] != "/proof/data/exports/" + name
            or response["path"] in paths
        ):
            raise ValueError(
                "Word copy paths are unsafe, duplicated "
                "or outside the fictional workspace."
            )
        content = retained[role]
        expected_content = docx_export.export_docx(payload).content
        _word_paragraphs(content)
        with (
            zipfile.ZipFile(io.BytesIO(content)) as actual_word,
            zipfile.ZipFile(io.BytesIO(expected_content)) as expected_word,
        ):
            _word_copy_zip_envelope(content, actual_word)
            # ZIP compression can differ between frozen/host zlib versions.
            # Every actual ZIP byte is hashed below; every uncompressed OOXML
            # part must still equal the exact same-source compiler output.
            if any(
                actual_word.read(name) != expected_word.read(name)
                for name in WORD_PARTS
            ):
                raise ValueError(
                    "Actual saved Word content differs from the supplied snapshot."
                )
        expected = {
            "path": response["path"],
            "filename": name,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "content_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            "verification": "Word ZIP integrity and exact byte readback",
            "title": payload["title"],
            "markdown_sha256": hashlib.sha256(payload["markdown"].encode()).hexdigest(),
            "snapshot_sha256": canonical_hash(payload),
        }
        if (
            not _same_json(response, expected)
            or type(row["file_mode"]) is not int
            or row["file_mode"] != 0o600
            or type(row["file_links"]) is not int
            or row["file_links"] != 1
        ):
            raise ValueError(
                "Actual local Word file metadata or snapshot hashes differ."
            )
        paths.add(response["path"])
    if not isinstance(proof["saved_report"], dict) or not isinstance(
        proof["saved_report"].get("document_edits"), dict
    ):
        raise ValueError("Word preservation must retain the saved original draft.")
    if (
        proof["saved_report"].get("document_edits", {}).get("markdown")
        != original["markdown"]
        or (
            proof["saved_report"].get("document_title")
            or proof["saved_report"].get("title")
        )
        != original["title"]
    ):
        raise ValueError(
            "The applied Word snapshot differs from the saved original draft."
        )
    if retained["word_copy_applied"] != retained["handover_word"]:
        raise ValueError(
            "Ordinary Word download differs from the locally saved applied copy."
        )
    if not _same_json(
        proof["pending"],
        {"requests_before": 1, "requests_after": 1, "editor_text": changed["markdown"]},
    ):
        raise ValueError("Pending edits were exported or lost instead of protected.")
    if not _same_json(
        proof["uncertain"],
        {
            "requests_after_failure": 3,
            "requests_after_idle": 3,
            "displayed_path": rows[1]["response"]["path"],
            "displayed_notice": "Previously confirmed copy",
            "editor_text": changed["markdown"],
        },
    ):
        raise ValueError(
            "Uncertain Word save lost the previous path or automatically replayed."
        )
    if (
        type(proof["synthetic_download_denials"]) is not int
        or proof["synthetic_download_denials"] != 1
    ):
        raise ValueError(
            "The intentional download denial was not observed exactly once."
        )
    before = proof["before"]
    if not isinstance(before, dict) or set(before) != {
        "tables",
        "preferences_file",
        "settings_sha256",
    }:
        raise ValueError("Word conservation evidence is incomplete.")
    tables = before["tables"]
    names = {
        "workspace.sqlite3/reports",
        "workspace.sqlite3/watches",
        "workspace.sqlite3/casebooks",
        "workspace.sqlite3/casebooks_scoped_v2",
        "campaigns.sqlite3/campaigns",
    }
    if not isinstance(tables, dict) or set(tables) != names:
        raise ValueError("Word conservation does not cover all five original tables.")
    for value in tables.values():
        if (
            not isinstance(value, dict)
            or set(value) != {"definition_sha256", "rows_sha256", "rows"}
            or type(value["rows"]) is not int
            or value["rows"] < 0
            or any(
                not isinstance(value[key], str) or not SHA.fullmatch(value[key])
                for key in ("definition_sha256", "rows_sha256")
            )
        ):
            raise ValueError("Word conservation contains unbound table observations.")
    if any(
        tables[name].get("rows") != 1
        for name in (
            "workspace.sqlite3/reports",
            "workspace.sqlite3/casebooks",
            "campaigns.sqlite3/campaigns",
        )
    ):
        raise ValueError(
            "Word preservation must include the actual saved "
            "project, campaign and report."
        )
    if (
        not isinstance(before["settings_sha256"], str)
        or not SHA.fullmatch(before["settings_sha256"])
        or before["preferences_file"] is not None
        and (
            not isinstance(before["preferences_file"], str)
            or not SHA.fullmatch(before["preferences_file"])
        )
        or not _same_json(proof["after"], before)
        or canonical_hash(proof["saved_report"])
        != receipt["result_hashes"]["saved_report"]
    ):
        raise ValueError("Word recovery changed original reports, rows or preferences.")
