"""New report presentation and qualification leave historical identities intact."""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from sinter import casebooks, docx_export
from sinter.store import Store
from tools import historical_handover_fixture as oracle
from tools import installed_workflow_browser as browser
from tools import installed_workflow_contract as contract
from tools import installed_workflow_qualification as qualification

ROOT = Path(__file__).resolve().parents[1]
W = qualification.W


def current_source():
    return {
        path.relative_to(ROOT).as_posix(): path.read_bytes()
        for path in (ROOT / "src/sinter").rglob("*.py")
    }


def current_word():
    fixture = oracle.historical_handover("installed_garden")
    report = casebooks.build(fixture["input"])
    content = docx_export.export_docx(
        {
            "title": fixture["input"]["title"],
            "markdown": report["document_markdown"] + contract.OPERATOR_NOTE,
        }
    ).content
    return fixture["input"], content


def changed_document(content, change):
    result = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as original:
        document = ET.fromstring(original.read("word/document.xml"))
        change(document)
        with zipfile.ZipFile(result, "w") as revised:
            for entry in original.infolist():
                revised.writestr(
                    entry,
                    ET.tostring(document)
                    if entry.filename == "word/document.xml"
                    else original.read(entry),
                )
    return result.getvalue()


def test_historical_oracle_is_exact_distinct_data_and_not_a_current_generator():
    assert (
        hashlib.sha256(oracle.ORACLE_PATH.read_bytes()).hexdigest()
        == oracle.ORACLE_SHA256
    )
    original = oracle.historical_handover("unscoped_golden")
    assert hashlib.sha256(
        json.dumps(original["report"], ensure_ascii=False).encode()
    ).hexdigest() == (
        "c793b8d5b4df96b6dd7eb17cdd8551cc4ed840cc701e8af3521c80d2d5bdf529"
    )
    assert "handover_presentation" not in original["report"]
    changed = oracle.historical_handover("unscoped_golden")
    changed["report"]["document_markdown"] = "Fictional edited copy"
    assert oracle.historical_handover("unscoped_golden") == original


def test_changed_oracle_bytes_are_refused(tmp_path, monkeypatch):
    path = tmp_path / "oracle.json"
    path.write_bytes(oracle.ORACLE_PATH.read_bytes() + b"\n")
    monkeypatch.setattr(oracle, "ORACLE_PATH", path)
    with pytest.raises(ValueError, match="bytes changed"):
        oracle.historical_handover("installed_garden")


def test_input_fingerprint_audit_and_history_are_not_a_presentation_migration(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(casebooks, "utc_now", lambda: "2026-10-01T00:00:00Z")
    fixture = oracle.historical_handover("unscoped_golden")
    old = fixture["report"]
    payload = fixture["input"]
    normalized = casebooks.validate(payload)
    current = casebooks.build(payload)
    assert normalized["fingerprint"] == old["casebook_fingerprint"]
    assert current["casebook_fingerprint"] == old["casebook_fingerprint"]
    projection = copy.deepcopy(current)
    assert projection.pop("handover_presentation") == contract.RECIPIENT_PRESENTATION
    projection["document_markdown"] = old["document_markdown"]
    assert projection == old
    # Presentation belongs to the derived report; it is never normalized into
    # saved project inputs or their fingerprint, even if a caller adds it.
    assert (
        casebooks.validate(
            {**payload, "handover_presentation": contract.RECIPIENT_PRESENTATION}
        )
        == normalized
    )
    old["document_edits"] = {
        "markdown": "Fictional exact earlier user edit — 前😀",
        "author": "user",
    }
    store = Store(tmp_path)
    identifier = store.save_report(old)
    before = store.report(identifier)
    store.save_report(current)
    assert Store(tmp_path).report(identifier) == before
    for kind in ("brief", "agenda", "enquiry"):
        assert "handover_presentation" not in casebooks.build(
            {**payload, "document_type": kind}
        )


def test_source_selects_a_separate_closed_revision_without_changing_historical_roles():
    assert contract.workflow_schema({}) == contract.SCHEMA
    legacy_word_source = {"src/sinter/document_copies.py": b""}
    assert contract.workflow_schema(legacy_word_source) == contract.LATEST_SCHEMA
    assert contract.workflow_checks(legacy_word_source) == (
        *contract.CHECKS[:-1],
        *contract.WORD_CHECKS,
        contract.CHECKS[-1],
    )
    source = current_source()
    assert contract.source_presentation(source) == contract.RECIPIENT_PRESENTATION
    assert contract.workflow_schema(source) == contract.NAVIGATION_SCHEMA
    assert len(contract.workflow_checks(source)) == 22
    assert contract.workflow_artifact_paths(source) == contract.LATEST_ARTIFACT_PATHS
    assert len(contract.workflow_artifact_paths(source)) == 13


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_marker",
        "wrong_marker",
        "duplicate_marker",
        "expression",
        "missing_helper",
        "missing_word_copy",
    ],
)
def test_incomplete_or_unrecognized_presentation_cannot_downgrade_to_old_revision(
    mutation,
):
    source = current_source()
    if mutation == "missing_marker":
        source["src/sinter/handover.py"] = source["src/sinter/handover.py"].replace(
            b'PRESENTATION_VERSION = "sinter-handover-presentation/v2"', b""
        )
    elif mutation == "wrong_marker":
        source["src/sinter/handover.py"] = source["src/sinter/handover.py"].replace(
            b"sinter-handover-presentation/v2", b"sinter-handover-presentation/v999"
        )
    elif mutation == "duplicate_marker":
        source["src/sinter/handover.py"] += (
            b'\nPRESENTATION_VERSION = "sinter-handover-presentation/v2"\n'
        )
    elif mutation == "expression":
        source["src/sinter/handover.py"] = source["src/sinter/handover.py"].replace(
            b'PRESENTATION_VERSION = "sinter-handover-presentation/v2"',
            b'PRESENTATION_VERSION = str("sinter-handover-presentation/v2")',
        )
    elif mutation == "missing_helper":
        source["src/sinter/docx_export.py"] = source[
            "src/sinter/docx_export.py"
        ].replace(b"def _passage_navigation(", b"def _unknown_navigation(")
    else:
        source.pop("src/sinter/document_copies.py")
        source["src/sinter/runtime.py"] = b""
    with pytest.raises(ValueError):
        contract.workflow_schema(source)


def test_old_and_new_guidance_are_selected_separately_never_unioned(tmp_path):
    fixture = oracle.historical_handover("installed_garden")
    historical = base64.b64decode(fixture["word_base64"], validate=True)
    qualification.validate_word(historical, fixture["input"])
    book, current = current_word()
    qualification.validate_word(
        current, book, presentation=contract.RECIPIENT_PRESENTATION
    )
    with pytest.raises(ValueError, match="unrelated or private"):
        qualification.validate_word(current, book)
    with pytest.raises(ValueError, match="unrelated or private"):
        qualification.validate_word(
            historical, book, presentation=contract.RECIPIENT_PRESENTATION
        )
    path = tmp_path / "actual-download.docx"
    path.write_bytes(current)
    assert browser.verify_recipient_download(
        path, {"source": current_source(), "casebook": book}
    )
    path.write_bytes(historical)
    with pytest.raises(ValueError):
        browser.verify_recipient_download(
            path, {"source": current_source(), "casebook": book}
        )
    assert not browser.verify_recipient_download(path, {"source": {}, "casebook": book})


@pytest.mark.parametrize(
    "mutation",
    ["missing", "wrong_target", "external", "nested", "orphan", "wrong_close"],
)
def test_current_word_gate_requires_real_matching_local_navigation(mutation):
    book, original = current_word()

    def change(document):
        paragraph = next(
            row
            for row in document.iter(W + "p")
            if row.find(W + "bookmarkStart") is not None
        )
        link = paragraph.find(W + "hyperlink")
        if mutation == "missing":
            for child in list(link):
                paragraph.append(child)
            paragraph.remove(link)
        elif mutation == "wrong_target":
            link.set(W + "anchor", "SinterReference4")
        elif mutation == "external":
            link.set(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id",
                "rId1",
            )
        elif mutation == "nested":
            paragraph.remove(link)
            ET.SubElement(paragraph, W + "r").append(link)
        elif mutation == "orphan":
            for row in document.iter(W + "p"):
                for node in list(row):
                    if node.tag in (W + "bookmarkStart", W + "bookmarkEnd"):
                        row.remove(node)
                        document.find(W + "body").append(node)
                    elif node.tag == W + "hyperlink":
                        for child in list(node):
                            row.append(child)
                        row.remove(node)
        else:
            paragraph.find(W + "bookmarkEnd").set(W + "id", "999")

    with pytest.raises(ValueError):
        qualification.validate_word(
            changed_document(original, change),
            book,
            presentation=contract.RECIPIENT_PRESENTATION,
        )


@pytest.mark.parametrize(
    "addition,without_helper",
    [
        ('PRESENTATION_VERSION: str = "sinter-handover-presentation/v999"', False),
        ("del PRESENTATION_VERSION", False),
        (
            'if True:\n    PRESENTATION_VERSION = "sinter-handover-presentation/v999"',
            False,
        ),
        ('PRESENTATION_VERSION: str = "sinter-handover-presentation/v999"', True),
        ('PRESENTATION_VERSION += "unknown"', False),
        ("other = PRESENTATION_VERSION", False),
        ("from elsewhere import PRESENTATION_VERSION", False),
        ("import elsewhere as PRESENTATION_VERSION", False),
        ("def PRESENTATION_VERSION():\n    pass", False),
        ("class PRESENTATION_VERSION:\n    pass", False),
        ("def other(PRESENTATION_VERSION):\n    pass", False),
        ('match {}:\n    case {"value": PRESENTATION_VERSION}:\n        pass', False),
    ],
)
def test_reserved_identity_declarations_and_uses_cannot_hide_overrides(
    addition, without_helper
):
    source = current_source()
    if without_helper:
        source["src/sinter/handover.py"] = addition.encode()
        source["src/sinter/docx_export.py"] = b""
    else:
        source["src/sinter/handover.py"] += ("\n" + addition + "\n").encode()
    with pytest.raises(ValueError, match="closed handover presentation"):
        contract.workflow_schema(source)


@pytest.mark.parametrize(
    "addition",
    [
        "def _passage_navigation():\n    pass",
        "del _passage_navigation",
        "_passage_navigation = None",
        "if True:\n    def _passage_navigation():\n        pass",
    ],
)
def test_navigation_helper_cannot_be_redeclared_or_removed(addition):
    source = current_source()
    source["src/sinter/docx_export.py"] += ("\n" + addition + "\n").encode()
    with pytest.raises(ValueError, match="closed handover presentation"):
        contract.workflow_schema(source)


def test_legacy_comments_and_string_prose_are_not_an_identity_declaration():
    source = {
        "src/sinter/document_copies.py": b"",
        "src/sinter/handover.py": b'# PRESENTATION_VERSION\n"PRESENTATION_VERSION"\n',
        "src/sinter/docx_export.py": b'# _passage_navigation\n"_passage_navigation"\n',
    }
    assert contract.workflow_schema(source) == contract.LATEST_SCHEMA


@pytest.mark.parametrize("swap_quote_captions", [False, True])
def test_numbered_key_is_bound_to_the_exact_supplied_source_caption_and_id(
    swap_quote_captions,
):
    book, original = current_word()

    def words(node):
        return "".join(item.text or "" for item in node.iter(W + "t"))

    def change(document):
        # The independent V1 witness keeps the source/ID/range triples intact
        # while swapping labels, bookmark names and reciprocal targets.
        rows = [row for row in document.iter(W + "p") if "Excerpt ID:" in words(row)]
        for row in rows[:2]:
            number = 1 if words(row).startswith("Passage 1 ") else 2
            for node in row.iter(W + "t"):
                if node.text == f"Passage {number}":
                    node.text = f"Passage {3 - number}"
            row.find(W + "bookmarkStart").set(
                W + "name", f"SinterReference{3 - number}"
            )
            row.find(W + "hyperlink").set(W + "anchor", f"SinterPassage{3 - number}")
        if swap_quote_captions:
            captions = [
                row
                for row in document.iter(W + "p")
                if words(row).startswith("Original source: ")
            ]
            first, second = [list(row.iter(W + "t")) for row in captions[:2]]
            assert len(first) == len(second) == 1
            first[0].text, second[0].text = second[0].text, first[0].text

    with pytest.raises(ValueError, match="source|reference|caption"):
        qualification.validate_word(
            changed_document(original, change),
            book,
            presentation=contract.RECIPIENT_PRESENTATION,
        )


def test_quote_destination_caption_must_match_the_reference_source():
    book, original = current_word()

    def change(document):
        captions = [
            row
            for row in document.iter(W + "p")
            if "".join(item.text or "" for item in row.iter(W + "t")).startswith(
                "Original source: "
            )
        ]
        first, second = [list(row.iter(W + "t")) for row in captions[:2]]
        assert len(first) == len(second) == 1
        first[0].text, second[0].text = second[0].text, first[0].text

    with pytest.raises(ValueError, match="source|reference|caption"):
        qualification.validate_word(
            changed_document(original, change),
            book,
            presentation=contract.RECIPIENT_PRESENTATION,
        )
