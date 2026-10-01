"""Selected-evidence handovers work outside Sinter without enlarging retrieval."""

from __future__ import annotations

import copy
import json
import threading
import urllib.request
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest
from test_handover_presentation import passage, word_text

from sinter import casebooks, client, handover
from sinter.server import make_server
from sinter.store import Store

FIXTURE = Path(__file__).parent / "fixtures/handover-appendix.json"


def project():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_nine_selected_passages_from_seven_sources_survive_word_export():
    original = project()
    before = copy.deepcopy(original)
    with patch.object(
        client, "_open", side_effect=AssertionError("Offline only")
    ) as api:
        compact = casebooks.build(original)
        full = casebooks.build({**original, "handover_evidence": "selected_appendix"})
        text, _ = word_text(full["document_markdown"])
    api.assert_not_called()
    assert len(full["excerpts"]) == 9 and len(full["sources"]) == 7
    for key in (
        "excerpts",
        "sources",
        "source_register",
        "question_index",
        "coverage",
        "document_references",
        "markdown",
        "review_status",
    ):
        assert full[key] == compact[key], key
    assert full["casebook_fingerprint"] != compact["casebook_fingerprint"]
    assert full["handover_evidence"] == "selected_appendix"
    assert "Including all 9 selected passages from 7 sources" in text
    assert "Selected evidence appendix" in text
    assert "Selected passage not reproduced" not in text
    assert "Read its exact wording in Evidence" not in text
    assert "A wording match is not an answer" in text
    assert "not an exhaustive source review" in text
    for number, excerpt in enumerate(full["excerpts"], 1):
        assert excerpt["quote"] in text
        assert text.count(excerpt["id"]) == 1
        assert f"Passage {number}" in text
        assert f"Unicode characters: {excerpt['start']}–{excerpt['end']};" in text
    assert "09:45 on 7 October; it is proposed, not confirmed" in text
    assert "current fictional scope is one small pilot" in text
    assert "IP ownership and novelty remain unverified" in text
    assert "李 😀" in text
    assert "UNSELECTED ORIGINAL CONTEXT" not in text
    assert original == before


def test_compact_default_and_explicit_compact_keep_fingerprint_and_presentation():
    original = project()
    normalized = casebooks.validate(original)
    explicit = casebooks.validate({**original, "handover_evidence": "compact"})
    assert explicit == normalized
    assert "handover_evidence" not in normalized
    with patch.object(casebooks, "utc_now", return_value="fixed test time"):
        default = casebooks.build(original)
        compact = casebooks.build({**original, "handover_evidence": "compact"})
    assert default == compact
    assert "Showing 4 of 9 selected passages" in compact["document_markdown"]
    assert compact["document_markdown"].count("Selected passage not reproduced") == 5
    assert "## Selected evidence appendix" not in compact["document_markdown"]


@pytest.mark.parametrize(
    "mode", [None, True, 1, [], {}, "all_sources", "", "SELECTED_APPENDIX"]
)
def test_unrecognised_evidence_modes_are_refused_without_mutating_sources(mode):
    book = {**project(), "handover_evidence": mode}
    before = copy.deepcopy(book)
    with pytest.raises(ValueError, match="compact handover notes"):
        casebooks.validate(book)
    assert book == before


def test_explicit_mode_persists_through_save_reopen_backup_and_separate_restore(
    tmp_path,
):
    repository = casebooks.Casebooks(Store(tmp_path))
    original = {**project(), "handover_evidence": "selected_appendix"}
    saved = repository.save(original)
    reopened = casebooks.Casebooks(Store(tmp_path)).get(saved["id"])
    assert reopened == saved
    backup = json.loads(json.dumps(reopened["document"], ensure_ascii=False))
    restored = repository.save(backup)
    assert restored["id"] != saved["id"]
    assert restored["document"]["handover_evidence"] == "selected_appendix"
    assert restored["document"]["fingerprint"] == saved["document"]["fingerprint"]
    assert repository.get(saved["id"]) == saved
    assert (
        casebooks.build(restored["document"])["handover_evidence"]
        == "selected_appendix"
    )


def test_mode_change_retires_prior_fingerprint_without_rewriting_historical_report(
    tmp_path,
):
    store = Store(tmp_path)
    repository = casebooks.Casebooks(store)
    saved = repository.save(project())
    prior_report = casebooks.build(saved["document"])
    report_id = store.save_report(prior_report)
    appendix = repository.save(
        {**saved["document"], "handover_evidence": "selected_appendix"},
        saved["id"],
        saved["revision"],
    )
    assert appendix["document"]["fingerprint"] != prior_report["casebook_fingerprint"]
    assert store.report(report_id) == prior_report
    reverted = repository.save(
        {**appendix["document"], "handover_evidence": "compact"},
        appendix["id"],
        appendix["revision"],
    )
    assert reverted["document"]["fingerprint"] == saved["document"]["fingerprint"]
    assert store.report(report_id) == prior_report


def test_http_mode_change_refuses_prior_draft_consent_before_any_request(tmp_path):
    server = make_server(port=0, directory=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path, data):
        req = urllib.request.Request(
            base + path,
            headers={
                "Content-Type": "application/json",
                "X-Sinter-Token": server.app.token,
            },
            data=json.dumps(data).encode(),
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.load(response)

    try:
        saved = request("/api/casebooks/save", {"document": project()})
        old_report = casebooks.build(saved["document"])
        changed = request(
            "/api/casebooks/save",
            {
                "document": {
                    **saved["document"],
                    "handover_evidence": "selected_appendix",
                },
                "id": saved["id"],
                "revision": saved["revision"],
            },
        )
        with patch.object(client, "chat") as generation:
            with pytest.raises(HTTPError) as refused:
                request(
                    "/api/casebooks/draft",
                    {
                        "id": changed["id"],
                        "revision": changed["revision"],
                        "consent": True,
                        "fingerprint": old_report["casebook_fingerprint"],
                    },
                )
            assert refused.value.code == 400
            assert (
                "Preview the current source-only report"
                in refused.value.read().decode()
            )
            generation.assert_not_called()
        assert server.app.casebooks.get(changed["id"]) == changed
        assert server.app.jobs.list() == []
    finally:
        server.shutdown()
        server.app.close()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize(
    "change",
    [
        {"quote": "An invented approval."},
        {"start": True},
        {"end": 5000},
        {"source_id": "Smissing"},
    ],
)
def test_appendix_still_refuses_nonfaithful_passage_identities_and_ranges(change):
    source, excerpt = passage("This source does not approve the request.")
    with pytest.raises(ValueError, match="no longer matches"):
        handover.render(
            "Handover",
            {},
            [source],
            [replace(excerpt, **change)],
            [],
            include_selected_appendix=True,
        )


def test_appendix_retains_literal_partial_csv_and_unconfirmed_table_cells():
    source, excerpt = passage(
        "task,owner,date\nAsk about access,,\nCheck IP,Unassigned,proposed\n",
        "Fictional actions.csv",
    )
    text, _ = word_text(
        handover.render(
            "Handover", {}, [source], [excerpt], [], include_selected_appendix=True
        )
    )
    assert "entries do not confirm assignments or dates" in text
    assert "Unassigned" in text and "proposed" in text
    fragment = replace(excerpt, start=5, quote=source.content[5:])
    partial, _ = word_text(
        handover.render(
            "Handover", {}, [source], [fragment], [], include_selected_appendix=True
        )
    )
    assert "Table layout could not be confirmed" in partial
    assert fragment.quote in partial


def test_appendix_remains_bounded_by_the_existing_selection_and_casebook_limits():
    book = {
        "title": "Fictional bounded selection",
        "document_type": "handover",
        "handover_evidence": "selected_appendix",
        "questions": "\n".join(f"topic{index:02}?" for index in range(20)),
        "documents": [
            {
                "title": f"Fictional {index}-{part}",
                "content": f"topic{index:02} unresolved condition {part}.",
            }
            for index in range(20)
            for part in range(3)
        ],
    }
    report = casebooks.build(book)
    assert len(report["excerpts"]) == 60
    assert len(report["document_references"]) == 60
    text, _ = word_text(report["document_markdown"])
    assert "Including all 60 selected passages" in text
    assert "Passage 60" in text
    with pytest.raises(ValueError, match="at most 20 questions"):
        casebooks.build({**book, "questions": book["questions"] + "\nextra?"})
    with pytest.raises(ValueError, match="200,000 characters"):
        casebooks.build(
            {**book, "documents": [{"title": "Large", "content": "x" * 200001}]}
        )
