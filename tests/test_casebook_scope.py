"""Question scopes preserve originals and fail closed at changed anchors/identities."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import casebooks, client
from sinter.casebook_scope import EMPTY_ANSWER, draft_context, scoped_draft
from sinter.preferences import Preferences
from sinter.store import Store
from tools.historical_handover_fixture import historical_handover

ROOT = Path(__file__).resolve().parents[1]
LEGACY_PATH = ROOT / "tests/fixtures/casebooks_pre_scope_v1.py"
LEGACY_IDENTITY = ROOT / "tests/fixtures/casebooks_pre_scope_v1.identity.json"


def serialized_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def legacy_identity():
    assert hashlib.sha256(LEGACY_IDENTITY.read_bytes()).hexdigest() == (
        "d75e7347998e0cbc3c563b3943f561d1a9b0cb88489f2ec727221dd0b97c6f02"
    )
    identity = json.loads(LEGACY_IDENTITY.read_bytes())
    assert (
        hashlib.sha256(LEGACY_PATH.read_bytes()).hexdigest()
        == (identity["reader_fixture_sha256"])
    )
    assert identity["source_commit"] == "a0fcdbf14da1e31e65632fe144e7a4fbcaea9154"
    assert identity["original_source_sha256"] == (
        "7dd36048872907794c61a8affbf8d582a73078c4b912367cb9a199d85e9d77bc"
    )
    return identity


def legacy_module():
    # Exact old validator/storage excerpts; works without Git in a source archive.
    legacy_identity()
    spec = importlib.util.spec_from_file_location("sinter.scope_legacy", LEGACY_PATH)
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    return legacy


def project():
    return {
        "title": "Fictional supplier and governing rules",
        "questions": "Which applicants are eligible?\n"
        "What production costs need checking?",
        "documents": [
            {
                "title": f"Fictional supplier enquiry {index}",
                "content": "Eligible applicants ask production costs. "
                "No supplier quote, "
                "approval or availability was received. 🐝",
            }
            for index in range(3)
        ]
        + [
            {
                "title": "Fictional governing rule",
                "content": "Eligible applicants must check the current governing rule. "
                "Eligibility is not confirmed. Costs are not supplied.",
            }
        ],
    }


def scoped(source_ids=None):
    book = casebooks.validate(project())
    return {
        **book,
        "schema": "sinter-casebook/v2",
        "question_scopes": [
            {
                "question_index": 0,
                "question": "Which applicants are eligible?",
                "source_ids": source_ids
                if source_ids is not None
                else [book["documents"][3]["id"]],
            },
        ],
    }


def test_explicit_choice_limits_only_that_question_and_retains_all_originals():
    original = project()
    book = scoped()
    before = copy.deepcopy(book)
    report = casebooks.build(book)
    hits = {row["id"]: row for row in report["excerpts"]}
    assert {
        hits[identity]["source_id"]
        for identity in report["question_index"][0]["excerpt_ids"]
    } == {book["documents"][3]["id"]}
    assert report["question_index"][0]["status"] == "related_wording"
    assert report["question_index"][0]["source_scope"]["sources_searched"] == 1
    assert report["question_index"][1]["source_scope"]["mode"] == "all"
    assert report["question_index"][1]["source_scope"]["sources_searched"] == 4
    assert (
        casebooks.validate(book)["documents"]
        == casebooks.validate(original)["documents"]
    )
    assert book == before
    assert len(report["source_register"]) == 4
    assert report["coverage"]["exhaustive_review"] is False
    by_id = {row["id"]: row for row in book["documents"]}
    for row in report["excerpts"]:
        assert (
            by_id[row["source_id"]]["content"][row["start"] : row["end"]]
            == row["quote"]
        )


@pytest.mark.parametrize("kind", ["brief", "enquiry", "agenda", "handover"])
def test_explicit_zero_never_falls_back_to_unselected_source_text(kind):
    book = scoped([])
    book["questions"] = "Which applicants are eligible?"
    book["document_type"] = kind
    report = casebooks.build(book)
    assert report["excerpts"] == []
    assert report["sources"] == []
    assert report["question_index"][0]["status"] == "no_wording_match"
    assert report["question_index"][0]["source_scope"]["sources_searched"] == 0
    assert "No sources were selected for this question" in report["document_markdown"]
    assert "No supplier quote" not in report["document_markdown"]
    with patch.object(client, "chat") as remote:
        with pytest.raises(ValueError, match="No evidence was selected"):
            casebooks.draft(report, True)
        remote.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"question_index": True},
        {"question_index": -1},
        {"question_index": 2},
        {"question": "A moved or changed question"},
        {"question": False},
        {"source_ids": ["S" + "0" * 24]},
        {"source_ids": [True]},
        {"source_ids": "all"},
        {"source_ids": None},
        {"allow_all": True},
    ],
)
def test_bad_scope_values_do_not_broaden_a_search(change):
    book = scoped()
    book["question_scopes"][0].update(change)
    with pytest.raises(ValueError):
        casebooks.validate(book)


def test_duplicate_sources_positions_reordered_questions_and_removal_are_refused():
    book = scoped()
    source = book["question_scopes"][0]["source_ids"][0]
    for rows in (
        [{**book["question_scopes"][0], "source_ids": [source, source]}],
        book["question_scopes"] * 2,
        [
            {
                "question_index": 1,
                "question": "What production costs need checking?",
                "source_ids": [source],
            },
            book["question_scopes"][0],
        ],
    ):
        with pytest.raises(ValueError):
            casebooks.validate({**book, "question_scopes": rows})
    with pytest.raises(ValueError, match="changed or moved"):
        casebooks.validate(
            {
                **book,
                "questions": "What production costs need checking?\n"
                "Which applicants are eligible?",
            }
        )
    with pytest.raises(ValueError, match="existing sources"):
        casebooks.validate({**book, "documents": book["documents"][:3]})


def test_v2_is_required_so_old_previews_cannot_silently_discard_choices():
    book = scoped()
    with pytest.raises(ValueError, match="v2"):
        casebooks.validate({**book, "schema": "sinter-casebook/v1"})
    for value in (True, False, None, {}, "all"):
        with pytest.raises(ValueError):
            casebooks.validate({**project(), "question_scopes": value})
    legacy = legacy_module()
    with pytest.raises(ValueError):
        legacy.validate(book)


def test_unscoped_legacy_identity_and_presentation_change_are_separate(
    monkeypatch,
):
    legacy = legacy_module()
    identity = legacy_identity()
    assert serialized_digest(project()) == identity["fictional_input_sha256"]
    monkeypatch.setattr(casebooks, "utc_now", lambda: "2026-10-01T00:00:00Z")
    for kind in ("brief", "enquiry", "agenda", "handover"):
        book = {**project(), "document_type": kind}
        assert casebooks.validate(book) == legacy.validate(book)
        assert casebooks.validate({**book, "question_scopes": []}) == legacy.validate(
            book
        )
        actual = casebooks.build(book)
        current = actual
        golden = identity["formats"][kind]
        assert (
            serialized_digest(casebooks.validate(book)) == golden["normalized_sha256"]
        )
        if kind == "handover":
            captured = historical_handover("unscoped_golden")
            assert captured["input"] == book
            actual = captured["report"]
            projected = dict(current)
            assert projected.pop("handover_presentation") == (
                "sinter-handover-presentation/v2"
            )
            assert current["document_markdown"] != actual["document_markdown"]
            projected["document_markdown"] = actual["document_markdown"]
            assert projected == actual
            assert draft_context(current) == draft_context(actual)
        assert serialized_digest(actual) == golden["report_sha256"]
        assert serialized_digest(draft_context(actual)) == golden["packet_sha256"]
        response = client.ChatResult(
            "Please clarify [" + actual["excerpts"][0]["id"] + "]",
            finish_reason="stop",
        )
        with patch.object(client, "chat", return_value=response) as remote:
            actual_draft = casebooks.draft(actual, True)
            request = {
                "messages": [asdict(row) for row in remote.call_args.args[0]],
                "options": remote.call_args.kwargs,
            }
        assert serialized_digest(actual_draft) == golden["draft_sha256"]
        assert serialized_digest(request) == golden["request_sha256"]
        if kind == "handover":
            with patch.object(client, "chat", return_value=response) as remote:
                current_draft = casebooks.draft(current, True)
            assert {
                "messages": [asdict(row) for row in remote.call_args.args[0]],
                "options": remote.call_args.kwargs,
            } == request
            assert current_draft.pop("handover_presentation") == (
                "sinter-handover-presentation/v2"
            )
            assert (
                current_draft["source_document_markdown"]
                == current["document_markdown"]
            )
            current_draft["source_document_markdown"] = actual["document_markdown"]
            assert serialized_digest(current_draft) == golden["draft_sha256"]


def test_scopes_change_fingerprint_and_survive_save_reopen_distinct_restore(tmp_path):
    repository = casebooks.Casebooks(Store(tmp_path))
    original = repository.save(project())
    chosen = repository.save(scoped(), original["id"], original["revision"])
    assert original["document"]["fingerprint"] != chosen["document"]["fingerprint"]
    reopened = repository.get(chosen["id"])
    assert reopened == chosen
    copied = repository.save(json.loads(json.dumps(reopened["document"])))
    assert copied["id"] != chosen["id"]
    assert copied["document"] == chosen["document"]
    assert repository.get(chosen["id"]) == reopened
    assert copied["document"]["documents"] == original["document"]["documents"]


def test_old_reader_cannot_see_or_resave_scoped_project_on_a_copied_workspace(
    tmp_path,
):
    directory = tmp_path / "original"
    store = Store(directory)
    current = casebooks.Casebooks(store)
    ordinary = current.save({**project(), "title": "Fictional unchanged v1 project"})
    prior = current.save(project())
    historical = casebooks.build(prior["document"])
    report_id = store.save_report(historical)
    preferences = Preferences(directory)
    preferences.update(
        {"api_url": "https://example.invalid/v1", "model": "explicit-fictional-model"},
        confirm_endpoint=True,
    )
    preferences_before = preferences.path.read_bytes()
    v2 = current.save(scoped(), prior["id"], prior["revision"])
    assert v2["id"] == prior["id"] and v2["revision"] == 2
    assert v2["document"]["documents"] == prior["document"]["documents"]
    assert current.get(ordinary["id"]) == ordinary
    assert {row["id"] for row in current.list()} == {ordinary["id"], v2["id"]}
    with store.connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM casebooks WHERE id=?", (v2["id"],)
            ).fetchone()[0]
            == 0
        )
        encoded_history = db.execute(
            "SELECT document FROM reports WHERE id=?", (report_id,)
        ).fetchone()[0]
    assert json.loads(encoded_history) == historical
    assert preferences.path.read_bytes() == preferences_before

    copied_directory = tmp_path / "copied-for-old-reader"
    shutil.copytree(directory, copied_directory)
    copied_store = Store(copied_directory)
    old = legacy_module().Casebooks(copied_store)
    before_attempts = copied_store.path.read_bytes()
    assert {row["id"] for row in old.list()} == {ordinary["id"]}
    assert old.get(ordinary["id"]) == ordinary
    with pytest.raises(KeyError, match="not found"):
        old.get(v2["id"])
    # Even an old window opened before the explicit scope change cannot resave.
    with pytest.raises(ValueError, match="changed in another window"):
        old.save(prior["document"], prior["id"], prior["revision"])
    with pytest.raises(ValueError):
        old.save(v2["document"])
    assert copied_store.path.read_bytes() == before_attempts
    returned = casebooks.Casebooks(copied_store)
    assert returned.get(v2["id"]) == v2
    assert returned.get(ordinary["id"]) == ordinary
    assert copied_store.report(report_id) == historical
    assert (copied_directory / "preferences.json").read_bytes() == preferences_before


def test_scoped_namespace_roundtrip_is_only_an_explicit_saved_schema_change(tmp_path):
    store = Store(tmp_path)
    repository = casebooks.Casebooks(store)
    saved = repository.save(scoped())
    before = saved["document"]
    with pytest.raises(ValueError, match="v2"):
        repository.save(
            {**before, "schema": "sinter-casebook/v1"}, saved["id"], saved["revision"]
        )
    assert repository.get(saved["id"]) == saved
    all_sources = {
        key: value
        for key, value in before.items()
        if key not in {"question_scopes", "fingerprint"}
    }
    all_sources["schema"] = "sinter-casebook/v1"
    all_sources["question_scopes"] = []
    explicit = repository.save(all_sources, saved["id"], saved["revision"])
    assert explicit["id"] == saved["id"] and explicit["revision"] == 2
    assert explicit["document"]["documents"] == before["documents"]
    old = legacy_module().Casebooks(store)
    assert old.get(explicit["id"]) == explicit
    again = repository.save(before, explicit["id"], explicit["revision"])
    assert again["id"] == saved["id"] and again["revision"] == 3
    assert again["document"] == before
    assert old.list() == []
    with pytest.raises(ValueError):
        repository.delete(again["id"], 2)
    assert repository.get(again["id"]) == again
    repository.delete(again["id"], 3)
    assert repository.list() == []


def test_casebook_limit_counts_both_namespaces_and_ambiguous_ids_fail_closed(tmp_path):
    store = Store(tmp_path)
    repository = casebooks.Casebooks(store)
    scoped_record = repository.save(scoped())
    for index in range(49):
        repository.save({**project(), "title": f"Fictional v1 {index}"})
    assert len(repository.list()) == 50
    with pytest.raises(ValueError, match="50 casebooks"):
        repository.save(project())
    with pytest.raises(ValueError, match="50 casebooks"):
        repository.save(scoped())
    repository.save(scoped_record["document"], scoped_record["id"], 1)
    with store.connect() as db:
        row = db.execute(
            "SELECT * FROM casebooks_scoped_v2 WHERE id=?", (scoped_record["id"],)
        ).fetchone()
        db.execute("INSERT INTO casebooks VALUES (?,?,?,?,?)", tuple(row))
    before = store.path.read_bytes()
    for operation in (
        lambda: repository.get(scoped_record["id"]),
        lambda: repository.save(project(), scoped_record["id"], 2),
        lambda: repository.delete(scoped_record["id"], 2),
    ):
        with pytest.raises(ValueError, match="conflicting local records"):
            operation()
        assert store.path.read_bytes() == before


@pytest.mark.parametrize("failed_step", ["insert_target", "delete_original"])
def test_explicit_v1_to_v2_move_rolls_back_whole_record_on_storage_failure(
    tmp_path,
    failed_step,
):
    store = Store(tmp_path)
    repository = casebooks.Casebooks(store)
    original = repository.save(project())
    event, table = (
        ("INSERT", "casebooks_scoped_v2")
        if failed_step == "insert_target"
        else ("DELETE", "casebooks")
    )
    with store.connect() as db:
        db.execute(
            "CREATE TRIGGER fictional_move_failure BEFORE "
            + event
            + " ON "
            + table
            + " BEGIN SELECT RAISE(ABORT, 'fictional failure'); END"
        )
    before = store.path.read_bytes()
    with pytest.raises(sqlite3.IntegrityError, match="fictional failure"):
        repository.save(scoped(), original["id"], original["revision"])
    assert store.path.read_bytes() == before
    assert repository.get(original["id"]) == original
    assert {row["id"] for row in repository.list()} == {original["id"]}
    assert legacy_module().Casebooks(store).get(original["id"]) == original


@pytest.mark.parametrize("direction", ["v1_to_v2", "v2_to_v1"])
def test_get_keeps_one_actual_sqlite_snapshot_during_concurrent_scope_move(
    tmp_path,
    direction,
):
    writer_store = Store(tmp_path)
    writer = casebooks.Casebooks(writer_store)
    reader_store = Store(tmp_path)
    reader = casebooks.Casebooks(reader_store)
    with writer_store.connect() as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    initial = writer.save(scoped() if direction == "v2_to_v1" else project())
    target = (
        {**project(), "question_scopes": []} if direction == "v2_to_v1" else scoped()
    )
    real_connect, committed = reader_store.connect, []

    class InterleavingConnection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, arguments=()):
            cursor = self.db.execute(sql, arguments)
            if not committed and sql.startswith("SELECT revision"):
                # SQLite has stepped into the first actual SELECT result, but
                # get() has not fetched the remaining namespace/record yet.
                # A different connection commits a real atomic schema move.
                committed.append(writer.save(target, initial["id"], 1))
            return cursor

    @contextmanager
    def concurrent_connect():
        with real_connect() as db:
            yield InterleavingConnection(db)

    reader_store.connect = concurrent_connect
    assert reader.get(initial["id"]) == initial
    assert len(committed) == 1 and committed[0]["revision"] == 2
    assert reader.get(initial["id"]) == committed[0]
    assert writer.get(initial["id"]) == committed[0]
    assert len(writer.list()) == 1


def test_ai_packet_has_only_each_questions_allowed_hits_and_rejects_tampering():
    report = casebooks.build(scoped())
    packet = draft_context(report)
    selected = {row["id"]: row for row in packet["excerpts"]}
    for row in packet["questions"]:
        assert all(
            selected[identity]["source_id"] in row["source_ids"]
            for identity in row["excerpt_ids"]
        )
    assert (
        packet["questions"][0]["source_ids"]
        == report["question_scopes"][0]["source_ids"]
    )
    response = json.dumps(
        {
            "sections": [
                {
                    "question_index": index,
                    "question": row["question"],
                    "text": f"Clarify [{row['excerpt_ids'][0]}]"
                    if row["excerpt_ids"]
                    else "",
                }
                for index, row in enumerate(packet["questions"])
            ]
        }
    )
    with patch.object(
        client, "chat", return_value=client.ChatResult(response)
    ) as remote:
        casebooks.draft(report, True)
    sent = json.loads(remote.call_args.args[0][1].content)
    assert sent == packet
    assert (
        "Never use another question's excerpts" in remote.call_args.args[0][0].content
    )
    altered = copy.deepcopy(report)
    other = next(
        row["id"]
        for row in altered["excerpts"]
        if row["source_id"] not in altered["question_scopes"][0]["source_ids"]
    )
    altered["question_index"][0]["excerpt_ids"] = [other]
    with patch.object(client, "chat") as remote:
        with pytest.raises(ValueError, match="outside"):
            casebooks.draft(altered, True)
        remote.assert_not_called()


def response_rows(packet):
    return [
        {
            "question_index": index,
            "question": row["question"],
            "text": f"Clarify [{row['excerpt_ids'][0]}]" if row["excerpt_ids"] else "",
        }
        for index, row in enumerate(packet["questions"])
    ]


@pytest.mark.parametrize(
    "fault",
    [
        "cross_question",
        "bare_cross_question",
        "source_reference",
        "unknown",
        "wrong_anchor",
        "wrong_index",
        "bool_index",
        "duplicate_section",
        "reordered",
        "missing_section",
        "extra_section",
        "extra_field",
        "extra_root",
        "nontext",
        "empty",
        "placeholder",
        "binary",
        "surrogate",
        "duplicate_json_key",
        "nonfinite",
        "exponent_infinity",
        "fenced",
        "length",
    ],
)
def test_scoped_invalid_received_text_is_retained_once_without_answer_admission(fault):
    report = casebooks.build(scoped())
    before = copy.deepcopy(report)
    packet = draft_context(report)
    rows = response_rows(packet)
    other = next(
        identity
        for identity in packet["questions"][1]["excerpt_ids"]
        if identity not in packet["questions"][0]["excerpt_ids"]
    )
    valid = rows[0]["text"]
    changes = {
        "cross_question": {"text": f"Clarify [{other}]"},
        "bare_cross_question": {"text": valid + " " + other},
        "source_reference": {
            "text": valid + " [" + packet["questions"][0]["source_ids"][0] + "]"
        },
        "unknown": {"text": "Clarify [E" + "0" * 24 + "]"},
        "wrong_anchor": {"question": "Different question"},
        "wrong_index": {"question_index": 1},
        "bool_index": {"question_index": False},
        "extra_field": {"answer_approved": True},
        "nontext": {"text": True},
        "empty": {"text": ""},
        "placeholder": {"text": valid + " [Insert recipient]"},
        "binary": {"text": valid + "\x00"},
        "surrogate": {"text": valid + "\ud800"},
    }
    rows[0].update(changes.get(fault, {}))
    if fault == "duplicate_section":
        rows[1] = copy.deepcopy(rows[0])
    elif fault == "reordered":
        rows.reverse()
    elif fault == "missing_section":
        rows.pop()
    elif fault == "extra_section":
        rows.append(copy.deepcopy(rows[0]))
    data = {"sections": rows}
    if fault == "extra_root":
        data["approved"] = True
    raw = json.dumps(data)
    if fault == "duplicate_json_key":
        raw = '{"sections": [], "sections": ' + json.dumps(rows) + "}"
    elif fault in {"nonfinite", "exponent_infinity"}:
        raw = raw.replace(
            '"question_index": 0',
            '"question_index": ' + ("NaN" if fault == "nonfinite" else "1e999"),
        )
    elif fault == "fenced":
        raw = "```json\n" + raw + "\n```"
    received = client.ChatResult(
        raw, finish_reason="length" if fault == "length" else "stop"
    )
    with patch.object(client, "chat", return_value=received) as remote:
        with pytest.raises(client.APIError) as failure:
            casebooks.draft(report, True)
        assert remote.call_count == 1
    partial = failure.value.partial_result
    assert partial["incomplete"] is True
    assert partial["model_draft"] is True
    assert partial["scoped_model_response"]["content"] == raw
    assert raw in partial["document_markdown"]
    assert partial["source_document_markdown"] == report["document_markdown"]
    assert partial["markdown"].endswith(report["markdown"])
    assert partial["excerpts"] == report["excerpts"]
    assert partial["source_register"] == report["source_register"]
    assert "No request was replayed" in partial["document_markdown"]
    assert report == before


def test_zero_evidence_question_has_fixed_unanswered_text_and_cannot_borrow():
    report = casebooks.build(scoped([]))
    packet = draft_context(report)
    rows = response_rows(packet)
    assert packet["questions"][0]["excerpt_ids"] == []
    rendered = scoped_draft(json.dumps({"sections": rows}), packet)
    assert EMPTY_ANSWER in rendered
    other = packet["questions"][1]["excerpt_ids"][0]
    rows[0]["text"] = f"Made up answer [{other}]"
    with pytest.raises(ValueError, match="remain unanswered"):
        scoped_draft(json.dumps({"sections": rows}), packet)


@pytest.mark.parametrize(
    "failure",
    [
        client.APIError(
            "The API connection was interrupted; no request was replayed.", 504
        ),
        ValueError("This task does not fit the native contract; no request was sent."),
    ],
)
def test_no_response_does_not_crash_invent_content_or_automatically_retry(failure):
    report = casebooks.build(scoped())
    before = copy.deepcopy(report)
    with patch.object(client, "chat", side_effect=failure) as remote:
        with pytest.raises(type(failure)) as raised:
            casebooks.draft(report, True)
        assert remote.call_count == 1
    partial = raised.value.partial_result
    assert partial["scoped_model_response"] is None
    assert "No response text was made available" in partial["document_markdown"]
    assert "If contact was interrupted" in partial["document_markdown"]
    assert partial["source_document_markdown"] == report["document_markdown"]
    assert partial["excerpts"] == report["excerpts"]
    assert report == before


def test_client_partial_exception_is_preserved_as_exact_incomplete_scoped_report():
    report = casebooks.build(scoped())
    raw = "Received partial ``` JSON 🐝 e\u0301"
    original = client.IncompleteGeneration(
        client.ChatResult(raw, finish_reason="incomplete"), 1024
    )
    with patch.object(client, "chat", side_effect=original) as remote:
        with pytest.raises(client.IncompleteGeneration) as raised:
            casebooks.draft(report, True)
        assert remote.call_count == 1
    assert raised.value is original
    assert raised.value.partial_result["scoped_model_response"]["content"] == raw
    assert raw in raised.value.partial_result["document_markdown"]


def test_scoped_native_preflight_keeps_work_and_task_guard(monkeypatch):
    report = casebooks.build(scoped())
    monkeypatch.setenv("NEUROFORGE_MODEL", client.NATIVE_MODEL)
    with patch.object(
        client, "_open", side_effect=AssertionError("No hosted calls")
    ) as remote:
        with pytest.raises(ValueError) as failure:
            casebooks.draft(report, True)
        remote.assert_not_called()
    assert failure.value.partial_result["scoped_model_response"] is None
    assert failure.value.partial_result["source_register"] == report["source_register"]
