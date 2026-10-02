"""Recipient-first source-only edits reuse local storage and Word export."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from sinter.docx_export import W, export_docx
from sinter.store import Store

ROOT = Path(__file__).resolve().parents[1]


def node(*arguments):
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("Node.js is required for browser-module source checks")
    result = subprocess.run(
        [executable, *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_reviewed_summary_compiler_and_replacement_boundaries():
    node("--test", "tests/handover_summary.mjs")


@pytest.fixture(scope="module")
def sample():
    return json.loads(node("tests/handover_summary.mjs", "--sample-json"))


def test_local_save_close_reopen_restore_keeps_summary_and_exact_evidence(
    sample, tmp_path
):
    original, report = sample["original"], sample["applied"]
    store = Store(tmp_path / "fictional-workspace")
    identifier = store.save_report(report)
    reopened = Store(tmp_path / "fictional-workspace").report(identifier)
    assert reopened == report
    for key in (
        "markdown",
        "document_markdown",
        "sources",
        "excerpts",
        "source_register",
        "document_references",
        "casebook_fingerprint",
        "review_status",
    ):
        assert reopened[key] == original[key]
    restored = json.loads(json.dumps(reopened, ensure_ascii=False))
    restored_id = store.save_report(restored)
    assert restored_id != identifier
    assert store.report(identifier) == store.report(restored_id) == report
    assert "handover_summary" not in reopened


def test_word_contains_useful_opening_before_questions_and_original_navigation(sample):
    report = sample["applied"]
    document = export_docx(
        {
            "title": report["document_title"],
            "markdown": report["document_edits"]["markdown"],
        }
    )
    with zipfile.ZipFile(io.BytesIO(document.content)) as package:
        assert package.testzip() is None
        body = ET.fromstring(package.read("word/document.xml"))
    text = " ".join(
        "".join(node.text or "" for node in paragraph.iter(f"{{{W}}}t"))
        for paragraph in body.iter(f"{{{W}}}p")
    )
    assert text.index("At a glance") < text.index("Handover next steps")
    for wording in (
        "Not received",
        "Unassigned; no owner has been recorded",
        "Owner type unknown; acceptance unconfirmed",
        "Suggested role: Volunteer coordinator",
        "2026-10-09 (unconfirmed; not a funder deadline)",
        "Historical wording: Recorded closed",
        "Missing supporting record; answer remains unknown",
        "not full supplied history",
        "in_progress",
        "Passage reference key",
    ):
        assert wording in text
    tables = list(body.iter(f"{{{W}}}tbl"))
    assert len(tables) == 2  # reviewed summary plus the original quoted action table
    assert len(list(tables[0].iter(f"{{{W}}}tr"))) == 7
    assert len(list(body.iter(f"{{{W}}}bookmarkStart"))) == 8
    assert len(list(body.iter(f"{{{W}}}hyperlink"))) >= 22


def test_stale_record_notice_survives_word_export_without_changing_original_fields():
    stale = json.loads(node("tests/handover_summary.mjs", "--sample-json", "--stale"))
    original, report = stale["original"], stale["applied"]
    assert original["review_status"] == report["review_status"] == "stale"
    assert {
        key: value for key, value in report.items() if key != "document_edits"
    } == original
    package = export_docx(
        {
            "title": report["document_title"],
            "markdown": report["document_edits"]["markdown"],
        }
    )
    with zipfile.ZipFile(io.BytesIO(package.content)) as document:
        body = ET.fromstring(document.read("word/document.xml"))
    text = " ".join(
        "".join(n.text or "" for n in p.iter(f"{{{W}}}t"))
        for p in body.iter(f"{{{W}}}p")
    )
    assert text.index("Review status: stale") < text.index("Handover next steps")
    assert "Original evidence and historical wording remain unchanged" in text
