"""Focused source-only scope preservation, reader refusal and closed evidence."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from sinter.casebooks import Casebooks, validate
from sinter.server import make_server
from sinter.store import Store
from tools import published_rc3_fixture as published_fixture
from tools import rc4_recovery_source as base
from tools import rc4_scoped_recovery_contract as contract
from tools import rc4_scoped_recovery_source as producer
from tools import rc4_scoped_recovery_worker as worker
from tools.rc4_recovery_worker import canonical, protected, seed, snapshot


def scoped_fixture():
    book = validate(contract.fixture())
    ids = [row["id"] for row in book["documents"]]
    return validate(
        {
            **book,
            "schema": "sinter-casebook/v2",
            "question_scopes": [
                {
                    "question_index": 0,
                    "question": contract.QUESTIONS[0],
                    "source_ids": [ids[0]],
                },
                {
                    "question_index": 1,
                    "question": contract.QUESTIONS[1],
                    "source_ids": [],
                },
            ],
        }
    )


@pytest.fixture
def seeded(tmp_path):
    data = tmp_path / "data"
    initial = seed(data)
    saved = Casebooks(Store(data)).save(scoped_fixture())
    (tmp_path / "process").mkdir()
    producer.write_json(tmp_path / "seed-control.json", {"seed": initial})
    return data, initial, saved


def test_help_has_no_installed_or_bypass_mode():
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(producer.ROOT / "tools/rc4_scoped_recovery_source.py"),
            "--help",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0 and not result.stderr
    assert (
        "--source-manifest-sha256" in result.stdout
        and "--source-commit" in result.stdout
    )
    assert "--installed" not in result.stdout and "--skip" not in result.stdout


def test_coordinator_defaults_keep_original_profile(tmp_path):
    obj = base.SourceLifecycle(tmp_path, tmp_path, {"notice": b"notice"}, {})
    assert obj.preserve is protected
    assert obj.worker == base.ROOT / "tools/rc4_recovery_worker.py"
    assert obj.command(tmp_path / "control")[-2:] == [
        "--control",
        str(tmp_path / "control"),
    ]


def test_actual_matrix_all_headers_refuse_before_jobs_or_writes(
    seeded, tmp_path, monkeypatch
):
    data, initial, saved = seeded
    server = make_server("127.0.0.1", 0, directory=data)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()

    def forbidden(*a, **kw):
        raise AssertionError("Unadmitted request reached queue or provider")

    try:
        monkeypatch.setattr(server.app.jobs, "submit", forbidden)
        monkeypatch.setattr(server.app, "connection", forbidden)
        producer.write_json(tmp_path / "state.json", {"port": server.server_port})
        result = producer.protocol(tmp_path, tmp_path, saved)
        assert len(result["matrix"]) == 30
        assert canonical(result["snapshot_before"]) == canonical(
            result["snapshot_after"]
        )
        assert result["jobs_before"] == result["jobs_after"]
    finally:
        server.shutdown()
        server.server_close()
        server.app.close()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert contract.equal(
        contract.seed_projection(snapshot(data), initial["snapshot"]),
        initial["snapshot"],
    )


def test_current_native_and_python_refuse_cli_preserves(seeded, tmp_path):
    data, initial, saved = seeded
    args = SimpleNamespace(
        data=data, source=producer.ROOT, control=tmp_path / "process/run-1.json"
    )
    # Native/Runtime are real current seams; CLI is four real isolated children.
    results = worker.after_stop(args)
    assert set(results["native"]) == {
        "open",
        "import",
        "resave",
        "build",
        "export_scoped_local",
        "add_text_scoped_local",
        "resave_scoped_local",
        "build_scoped_local",
    }
    assert len(results["runtime"]) == 6 and results["jobs_unchanged"] is True
    assert set(results["cli"]) == {
        "casebooks.get",
        "casebooks.validate",
        "casebooks.build",
        "export",
    }
    assert contract.equal(results["snapshot_before"], results["snapshot_after"])
    assert results["stored"] == saved
    assert contract.equal(
        json.loads(
            (tmp_path / "process/run-1.cli-export.json").read_text(encoding="utf-8")
        ),
        saved["document"],
    )
    assert contract.equal(
        contract.seed_projection(snapshot(data), initial["snapshot"]),
        initial["snapshot"],
    )


def test_scoped_cli_reader_environment_keeps_only_windows_bootstrap(
    tmp_path, monkeypatch
):
    fictional_home = tmp_path / "fictional-home"
    monkeypatch.setattr(
        published_fixture,
        "os",
        SimpleNamespace(
            name="nt",
            defpath="fixed-python-path",
            environ={
                "SYSTEMROOT": "/fictional/windows",
                "HOME": "/caller/home",
                "USERPROFILE": "/caller/profile",
                "OPENAI_API_KEY": "fictional-excluded",
                "NEUROFORGE_BASE_URL": "https://excluded.invalid",
            },
        ),
    )
    assert worker.cli_reader_environment(fictional_home) == {
        "PATH": "fixed-python-path",
        "SystemRoot": "/fictional/windows",
        "USERPROFILE": str(fictional_home.resolve()),
        "HOME": str(fictional_home),
    }


def test_scoped_actual_cli_readers_use_explicit_utf8_and_isolated_home(
    seeded, tmp_path, monkeypatch
):
    data, _, _ = seeded
    original_run = subprocess.run
    observations = []
    control = tmp_path / "process 🐝 é" / "run-1.json"
    control.parent.mkdir()

    def observed_run(command, **kwargs):
        assert command[1:8] == [
            "-I",
            "-S",
            "-B",
            "-X",
            "utf8",
            str(worker.__file__),
            "--cli-child",
        ]
        assert kwargs["env"] == worker.cli_reader_environment(tmp_path / "home")
        assert not any("KEY" in key for key in kwargs["env"])
        result = original_run(command, **kwargs)
        observations.append(result)
        return result

    monkeypatch.setattr(worker.subprocess, "run", observed_run)
    worker.after_stop(SimpleNamespace(data=data, source=producer.ROOT, control=control))
    assert len(observations) == 4
    assert all(result.returncode == 0 for result in observations)
    assert [result.stderr for result in observations] == [
        b"",
        b"",
        b"Ready for review\n",
        ("Saved: " + str(control.with_suffix(".cli-export.json")) + "\n").encode(
            "utf-8"
        ),
    ]
    envelopes = [json.loads(result.stdout.decode("utf-8")) for result in observations]
    assert all("🐝" in json.dumps(row, ensure_ascii=False) for row in envelopes[:3])
    assert "🐝" in json.dumps(
        json.loads(control.with_suffix(".cli-export.json").read_text(encoding="utf-8")),
        ensure_ascii=False,
    )


@pytest.mark.parametrize(
    "kind",
    (
        "missing_row",
        "original_raw_json",
        "original_integer_type",
        "preferences",
        "preference_type",
        "metadata",
        "schema",
        "columns",
    ),
)
def test_seed_projection_never_hides_original_changes(seeded, kind):
    data, initial, _ = seeded
    original = initial["snapshot"]
    changed = snapshot(data)
    table = changed["databases"]["workspace.sqlite3"]["tables"]["casebooks"]
    if kind == "missing_row":
        table["rows"] = []
    elif kind == "original_raw_json":
        table["rows"][0][-1] += " "
    elif kind == "original_integer_type":
        table["rows"][0][1] = True
    elif kind == "preferences":
        changed["preferences_sha256"] = "0" * 64
    elif kind == "preference_type":
        changed["preferences"]["max_tokens"] = 512.0
    elif kind == "metadata":
        changed["databases"]["workspace.sqlite3"]["metadata"]["application_id"] += 1
    elif kind == "schema":
        table["sql"] += " "
    elif kind == "columns":
        table["columns"].append("ignored")
    try:
        projected = contract.seed_projection(changed, original)
    except ValueError:
        assert kind in ("schema", "columns")
    else:
        assert not contract.equal(projected, original)


def test_reader_added_scoped_rows_do_not_change_seed_protection(seeded):
    data, initial, saved = seeded
    assert contract.equal(
        contract.seed_projection(snapshot(data), initial["snapshot"]),
        initial["snapshot"],
    )
    assert len(contract.wrappers(snapshot(data), "casebooks_scoped_v2")) == 1
    assert contract.wrappers(snapshot(data), "casebooks_scoped_v2")[0] == saved


@pytest.mark.parametrize(
    "pragma,value", (("user_version", 0), ("application_id", 0), ("page_size", 8192))
)
def test_same_live_metadata_observed_before_repair(seeded, pragma, value):
    data, initial, _ = seeded
    with sqlite3.connect(data / "workspace.sqlite3") as db:
        db.execute("PRAGMA " + pragma + "=" + str(value))
        if pragma == "page_size":
            db.execute("VACUUM")
    actual = snapshot(data)
    assert actual["databases"]["workspace.sqlite3"]["metadata"][pragma] == value
    assert not contract.equal(
        contract.seed_projection(actual, initial["snapshot"]), initial["snapshot"]
    )


def test_json_writer_preserves_unicode_and_types(tmp_path):
    path = tmp_path / "value.json"
    value = {"original": "🐝 e\u0301", "flag": False, "count": 1, "float": 1.0}
    producer.write_json(path, value)
    assert path.read_bytes() == json.dumps(
        value, ensure_ascii=False, indent=2, allow_nan=False
    ).encode("utf-8")
    assert contract.equal(json.loads(path.read_bytes()), value)
    assert not path.with_suffix(".tmp").exists()


def test_fictional_scopes_selected_empty_and_default_all():
    original = scoped_fixture()
    assert original["documents"][0]["content"].endswith("no commitment was made.")
    assert all(row["date"] == "" for row in original["documents"])
    assert original["question_scopes"][0]["source_ids"] == [
        original["documents"][0]["id"]
    ]
    assert original["question_scopes"][1]["source_ids"] == []
    assert 2 not in [row["question_index"] for row in original["question_scopes"]]


@pytest.mark.parametrize(
    "name",
    (
        "candidate_admitted",
        "installed_tested",
        "native_tested",
        "prior_replacement_tested",
        "release_qualified",
        "source_files_conserved",
        "source_rehearsal_passed",
    ),
)
def test_closed_receipt_never_promotes_missing_evidence(tmp_path, name):
    # Wrong flags must be refused before a missing-artifact path could matter.
    version = (producer.ROOT / "src/sinter/__init__.py").read_text(encoding="utf-8")
    import re

    observed = re.search(r'__version__\s*=\s*["\']([^"\']+)', version)[1]
    value = {key: None for key in contract.FIELDS}
    value.update(
        schema=contract.SCHEMA,
        execution="source",
        source_base_commit="a" * 40,
        source_manifest_sha256="b" * 64,
        source_files_sha256={"src/a": "c" * 64},
        observed_version=observed,
        candidate_admitted=False,
        installed_tested=False,
        native_tested=False,
        prior_replacement_tested=False,
        release_qualified=False,
        source_rehearsal_passed=True,
        source_files_conserved=True,
        resources={
            "browser_closed": True,
            "outer_relay_closed": True,
            "inner_relay_closed": True,
            "source_processes_stopped": True,
        },
        failure=None,
        artifacts={},
    )
    value[name] = not value[name]
    producer.write_json(tmp_path / contract.RECEIPT, value)
    with pytest.raises(ValueError, match="flags, identity or cleanup"):
        contract.validate_rehearsal(tmp_path, {"src/a": "c" * 64}, "a" * 40, "b" * 64)


@pytest.mark.parametrize(
    "change",
    (
        "full_original",
        "source_id",
        "passage_id",
        "quote",
        "range",
        "reference",
        "empty_scope",
        "all_scope",
        "human_text",
        "review_status",
        "edit_author",
        "extra_edit_field",
        "word_text",
    ),
)
def test_source_report_and_word_refuse_semantic_changes(change):
    from sinter.casebooks import build
    from sinter.docx_export import export_docx

    original = scoped_fixture()
    report = build(original, "handover")
    report["document_edits"] = {
        "markdown": report["document_markdown"] + contract.NOTE,
        "edited_at": "2026-10-02T12:00:00Z",
        "author": "user",
    }
    payload = {
        "title": report.get("document_title") or report["title"],
        "markdown": report["document_edits"]["markdown"],
    }
    word = export_docx(payload).content
    contract.validate_report(report, original, word)
    if change == "full_original":
        report["sources"][0]["content"] += " changed"
    elif change == "source_id":
        report["source_register"][0]["id"] = "S" + "0" * 24
    elif change == "passage_id":
        report["excerpts"][0]["id"] = "made-up"
    elif change == "quote":
        report["excerpts"][0]["quote"] = "A confirmed answer"
    elif change == "range":
        report["excerpts"][0]["start"] += 1
    elif change == "reference":
        report["document_references"][0]["source_id"] = "S" + "0" * 24
    elif change == "empty_scope":
        report["question_scopes"][1]["source_ids"] = [original["documents"][1]["id"]]
    elif change == "all_scope":
        report["question_index"][2]["source_scope"]["mode"] = "selected"
    elif change == "human_text":
        report["document_edits"]["markdown"] += " Unapplied wording"
    elif change == "review_status":
        report["review_status"] = "reviewed"
    elif change == "edit_author":
        report["document_edits"]["author"] = "model"
    elif change == "extra_edit_field":
        report["document_edits"]["hidden"] = "unreviewed text"
    elif change == "word_text":
        word = export_docx(
            {**payload, "markdown": payload["markdown"] + " Not the applied wording"}
        ).content
    with pytest.raises(ValueError):
        contract.validate_report(report, original, word)


def test_reader_artifacts_match_closed_current_inventory(seeded, tmp_path):
    data, _, _ = seeded
    worker.after_stop(
        SimpleNamespace(
            data=data, source=producer.ROOT, control=tmp_path / "process/run-1.json"
        )
    )
    actual = {
        "process/" + p.name for p in (tmp_path / "process").iterdir() if p.is_file()
    }
    assert actual <= contract.CORE
    assert "process/run-1.native-text.txt" in actual


def test_closed_profile_cannot_skip_required_v1_evidence(tmp_path):
    with pytest.raises(TypeError):
        producer.rehearse(
            SimpleNamespace(output=tmp_path / "proof"), {}, compatibility=False
        )
    assert not (tmp_path / "proof").exists()
    with pytest.raises(TypeError):
        contract.validate_rehearsal(
            tmp_path, {}, "a" * 40, "b" * 64, require_compatibility=False
        )


@pytest.mark.parametrize("change", ("metadata", "schema", "original", "preferences"))
def test_reader_guard_retains_raw_fixture_before_any_reopen(
    seeded, tmp_path, monkeypatch, change
):
    data, _, _ = seeded
    if change == "preferences":
        path = data / "preferences.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["model"] = "Fictional changed model before reader admission"
        producer.write_json(path, value)
    else:
        with sqlite3.connect(data / "workspace.sqlite3") as db:
            if change == "metadata":
                db.execute("PRAGMA user_version=0")
            elif change == "schema":
                db.execute("CREATE TABLE fictional_extra(value TEXT)")
            else:
                db.execute(
                    "UPDATE reports SET title='Fictional changed original title'"
                )
    before = snapshot(data)

    def forbidden(*args, **kwargs):
        raise AssertionError("Changed fixture reached Runtime initialization")

    monkeypatch.setattr("sinter.runtime.Runtime", forbidden)
    with pytest.raises(ValueError, match="Original schema|Stopped fixture changed"):
        worker.after_stop(
            SimpleNamespace(
                data=data, source=producer.ROOT, control=tmp_path / "process/run-1.json"
            )
        )
    retained = json.loads(
        (tmp_path / "process/run-1.reader-before.json").read_text(encoding="utf-8")
    )
    assert canonical(retained) == canonical(before) == canonical(snapshot(data))


def semantic_data_before_protocol(initial):
    """Valid source/Word/backup evidence; no process or passing receipt invented."""
    from sinter.campaigns import validate as validate_campaign
    from sinter.casebooks import build
    from sinter.docx_export import export_docx

    expected = scoped_fixture()
    saved = {"id": "a" * 32, "revision": 3, "document": expected}
    stale = {key: value for key, value in expected.items() if key != "fingerprint"}
    stale["questions"] = (
        contract.QUESTIONS[0]
        + " Revised wording?\n"
        + "\n".join(contract.QUESTIONS[1:])
    )
    control = validate({**expected, "title": contract.TITLE + " — conflict control"})
    working = {key: value for key, value in control.items() if key != "fingerprint"}
    working["recipient"] = "Fictional local unsaved conflict 🐝"
    report = build(expected, "handover")
    report["document_edits"] = {
        "markdown": report["document_markdown"] + contract.NOTE,
        "edited_at": "2026-10-02T12:00:00Z",
        "author": "user",
    }
    campaign = validate_campaign(
        json.loads(
            (producer.ROOT / "src/sinter/web/offline-garden-campaign.json").read_text(
                encoding="utf-8"
            )
        )
    )
    campaign["actions"][0]["task"] = contract.ACTION
    observation = {
        "phases": [
            {"name": name, "snapshot": initial["snapshot"]}
            for name in (
                "saved-use",
                "stopped-1",
                "reopened-use",
                "stopped-2",
                "stopped-3",
                "restored-both",
                "stopped-4",
            )
        ],
        "errors": [],
        "external": [],
        "dialogs": [],
        "warnings": [contract.WARNING],
        "scoped": saved,
        "report_id": "e" * 32,
        "report": report,
        "campaign": {"document": campaign},
        "offline": {},
        "stale_scope": {
            "working": stale,
            "stored": {**saved, "revision": 2},
            "posts": 0,
            "warning": (
                "Questions changed or moved. Review their source choices before saving."
            ),
        },
        "conflict": {
            "initial": {"id": "b" * 32, "revision": 1, "document": control},
            "saved": {
                "id": "b" * 32,
                "revision": 2,
                "document": validate(
                    {**control, "recipient": "Fictional other-window saved wording"}
                ),
            },
            "working": working,
            "posts": 1,
            "automatic_replays": 0,
            "snapshot_before": {},
            "snapshot_after": {},
            "warning": "This casebook changed in another window.",
        },
    }
    raw = {
        "seed-control.json": canonical({"seed": initial}).encode("utf-8"),
        "fixture.json": canonical(contract.fixture()).encode("utf-8"),
        "reopened.json": canonical(
            {key: value for key, value in expected.items() if key != "fingerprint"}
        ).encode("utf-8"),
        "stale-scope.json": canonical(stale).encode("utf-8"),
        "scoped-conflict.json": canonical(working).encode("utf-8"),
        "control-import.json": canonical(expected).encode("utf-8"),
        "handover.docx": export_docx(
            {
                "title": report.get("document_title") or report["title"],
                "markdown": report["document_edits"]["markdown"],
            }
        ).content,
    }
    for branch, identifier in (("clipboard", "c" * 32), ("manual", "d" * 32)):
        document = {
            key: value for key, value in expected.items() if key != "fingerprint"
        }
        document["recipient"] = "Fictional " + branch + " recovery 🐝 e\u0301"
        raw[branch + ".json"] = canonical(document).encode("utf-8")
        raw[branch + "-reference.json"] = raw[branch + ".json"]
        observation["offline"][branch] = {
            "document": document,
            "selection": [0, len(canonical(document).encode("utf-16-le")) // 2],
            "clipboard": {"attempts": 1, "successes": int(branch == "clipboard")},
            "snapshot_before": {},
            "snapshot_after": {},
        }
        observation[branch + "_restored"] = {
            "id": identifier,
            "revision": 1,
            "document": validate(
                {**document, "title": contract.TITLE + " — " + branch + " restored"}
            ),
        }
    return raw, observation


class ProtocolBoundary(Exception):
    """A finite unit probe reached protocol checks; not a full admission."""


def stop_before_protocol(raw, monkeypatch):
    sentinel = b"finite-unit-protocol-boundary"
    original = contract.json_object

    def read(value):
        if value is sentinel:
            raise ProtocolBoundary
        return original(value)

    raw["protocol.json"] = sentinel
    monkeypatch.setattr(contract, "json_object", read)


@pytest.mark.parametrize(
    "field,value",
    (
        ("stale_posts", False),
        ("stale_posts", 0.0),
        ("initial_revision", True),
        ("initial_revision", 1.0),
    ),
)
def test_actual_semantic_path_refuses_noninteger_observation(
    seeded, monkeypatch, field, value
):
    _, initial, _ = seeded
    raw, observation = semantic_data_before_protocol(initial)
    stop_before_protocol(raw, monkeypatch)
    raw["observations.json"] = canonical(observation).encode("utf-8")
    with pytest.raises(ProtocolBoundary):
        contract.validate_semantics(raw)
    if field == "stale_posts":
        observation["stale_scope"]["posts"] = value
    else:
        observation["conflict"]["initial"]["revision"] = value
    raw["observations.json"] = canonical(observation).encode("utf-8")
    try:
        contract.validate_semantics(raw)
    except ValueError as error:
        reason = str(error)
    except ProtocolBoundary:
        reason = None
    assert reason is not None, "Noninteger count/revision was admitted"
    assert (
        "not blocked locally" if field == "stale_posts" else "saved wrong wording"
    ) in reason


@pytest.mark.parametrize("branch", ("clipboard", "manual"))
@pytest.mark.parametrize("change", ("bool_start", "float_start", "float_end"))
def test_actual_backup_selection_requires_complete_integer_bounds(
    seeded, monkeypatch, branch, change
):
    _, initial, _ = seeded
    raw, observation = semantic_data_before_protocol(initial)
    stop_before_protocol(raw, monkeypatch)
    raw["observations.json"] = canonical(observation).encode("utf-8")
    with pytest.raises(ProtocolBoundary):
        contract.validate_semantics(raw)
    selection = observation["offline"][branch]["selection"]
    if change == "float_end":
        selection[1] = float(selection[1])
    else:
        selection[0] = False if change == "bool_start" else 0.0
    raw["observations.json"] = canonical(observation).encode("utf-8")
    try:
        contract.validate_semantics(raw)
    except ValueError as error:
        reason = str(error)
    except ProtocolBoundary:
        reason = None
    assert reason is not None, "Noninteger full-backup selection was admitted"
    assert "truncated manual selection" in reason
