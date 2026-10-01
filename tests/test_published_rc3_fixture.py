"""Separate E fixture preparation must not broaden any release admission."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = load("published_rc3_fixture")
worker = load("published_rc3_fixture_seed")


def arguments(source, archive, installer, output):
    return SimpleNamespace(
        prior_source=source,
        prior_source_archive=archive,
        prior_installer=installer,
        prior_version=fixture.PUBLISHED_E.version,
        prior_commit=fixture.PUBLISHED_E.source_commit,
        replacement_profile=fixture.REPLACEMENT_PROFILE,
        target=fixture.TARGET,
        output=output,
    )


def small_inputs(monkeypatch, tmp_path):
    """Inject tiny test inputs only; they cannot satisfy production E pins."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "prior.py").write_bytes(b"# Fictional prior code\n")
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(source / "src" / "prior.py", "src/prior.py")
    installer = tmp_path / "fictional.deb"
    installer.write_bytes(b"Never executed or installed; test fixture only.")
    monkeypatch.setattr(
        fixture,
        "PUBLISHED_E",
        fixture.PUBLISHED_E._replace(
            source_archive_sha256=fixture.file_sha256(archive),
            installer_sha256=fixture.file_sha256(installer),
        ),
    )
    monkeypatch.setattr(
        fixture.subprocess,
        "check_output",
        lambda *args, **kw: (
            "Package: sinter\nVersion: 0.5.4~rc3\nArchitecture: amd64\n"
        ),
    )
    return source, archive, installer


def test_exact_e_profile_is_separate_from_historical_priors():
    from tools.qualified_priors import QUALIFIED_PRIORS, qualified_prior

    assert set(QUALIFIED_PRIORS) == {"0.5.3", "0.5.4rc1", "0.5.4rc2"}
    before = dict(QUALIFIED_PRIORS)
    prior = fixture.select_fixture_profile(
        "0.5.4rc3",
        "246b91e0ee432cb1f6f6fcd17425f55cd7a4cabe",
        "0.5.4rc4",
        "linux-x64",
    )
    assert (
        prior.source_archive_sha256
        == "6d2a4ec4c6342d1243507169d877d2d266230469b01dbc00cbe031c53328f22a"
    )
    assert (
        prior.installer_sha256
        == "bb7133d70d3abfc3a0f825d57968d75629e00dc21af8d33030870e68c8c99dae"
    )
    with pytest.raises(ValueError):
        qualified_prior(prior.version, prior.source_commit)
    assert dict(QUALIFIED_PRIORS) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("prior_version", "0.5.4rc2"),
        ("prior_version", "0.5.4rc3.dev0"),
        ("prior_commit", "1b3189c5fbfe8c526d6681b303d5548eff86d7d0"),
        ("replacement_profile", "0.5.4rc4.dev0"),
        ("replacement_profile", "0.5.5"),
        ("target", "windows-x64"),
        ("target", "linux-arm64"),
        ("target", None),
    ],
)
def test_unknown_profile_refuses_before_read_or_write(
    monkeypatch, tmp_path, field, value
):
    args = arguments(
        tmp_path / "not-read",
        tmp_path / "not-read.zip",
        tmp_path / "not-read.deb",
        tmp_path / "output",
    )
    setattr(args, field, value)
    monkeypatch.setattr(
        fixture, "verify_inputs", lambda *args: pytest.fail("Read before admission")
    )
    with pytest.raises(ValueError, match="exact published E"):
        fixture.prepare_fixture(args)
    assert not args.output.exists()


@pytest.mark.parametrize("entry", ["source", "archive", "installer"])
def test_changed_inputs_refuse_before_worker(monkeypatch, tmp_path, entry):
    source, archive, installer = small_inputs(monkeypatch, tmp_path)
    selected = {
        "source": source / "src/prior.py",
        "archive": archive,
        "installer": installer,
    }[entry]
    selected.write_bytes(b"Changed fictional bytes\n")
    monkeypatch.setattr(
        fixture.subprocess, "run", lambda *args, **kw: pytest.fail("Unverified seed")
    )
    with pytest.raises(ValueError):
        fixture.prepare_fixture(
            arguments(source, archive, installer, tmp_path / "output")
        )
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("change", ["missing", "foreign", "directory", "same_size"])
def test_extracted_source_requires_complete_archive_identity(
    monkeypatch, tmp_path, change
):
    source, archive, installer = small_inputs(monkeypatch, tmp_path)
    if change == "missing":
        (source / "src/prior.py").unlink()
    elif change == "foreign":
        (source / "unlisted.txt").write_bytes(b"foreign")
    elif change == "directory":
        (source / "unlisted").mkdir()
    else:
        path = source / "src/prior.py"
        path.write_bytes(b"!" * path.stat().st_size)
    with pytest.raises(ValueError):
        fixture.verify_inputs(source, archive, installer)


@pytest.mark.parametrize(
    "metadata",
    [
        "Package: sinter\nVersion: 0.5.4~rc4\nArchitecture: amd64\n",
        "Package: sinter\nVersion: 0.5.4~rc3\nArchitecture: arm64\n",
    ],
)
def test_linux_package_metadata_does_not_admit_another_candidate(
    monkeypatch, tmp_path, metadata
):
    source, archive, installer = small_inputs(monkeypatch, tmp_path)
    monkeypatch.setattr(
        fixture.subprocess, "check_output", lambda *args, **kw: metadata
    )
    with pytest.raises(ValueError, match="package metadata"):
        fixture.verify_inputs(source, archive, installer)


@pytest.mark.parametrize("location", ["existing", "under-source", "above-source"])
def test_output_cannot_overwrite_or_contain_prior_source(
    monkeypatch, tmp_path, location
):
    source, archive, installer = small_inputs(monkeypatch, tmp_path)
    output = {
        "existing": tmp_path / "existing",
        "under-source": source / "output",
        "above-source": tmp_path,
    }[location]
    if location == "existing":
        output.mkdir()
        (output / "original").write_bytes(b"Retain me.")
    before = fixture.hashes(source)
    monkeypatch.setattr(
        fixture.subprocess, "run", lambda *args, **kw: pytest.fail("Unsafe output seed")
    )
    with pytest.raises(ValueError, match="fresh fixture output"):
        fixture.prepare_fixture(arguments(source, archive, installer, output))
    assert fixture.hashes(source) == before
    if location == "existing":
        assert (output / "original").read_bytes() == b"Retain me."


@pytest.mark.parametrize("result", ["failure", "stderr", "timeout"])
def test_seed_failure_retains_diagnostics_without_fixture_receipt(
    monkeypatch, tmp_path, result
):
    source, archive, installer = small_inputs(monkeypatch, tmp_path)
    output = tmp_path / "output"

    def failed(*args, **kwargs):
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["env"] == fixture.seed_environment(output)
        assert kwargs["timeout"] == 40
        assert args[0][1:4] == ["-I", "-S", "-B"]
        if result == "timeout":
            raise subprocess.TimeoutExpired(
                args[0], 40, output=b"partial\xff", stderr=b"diagnostic\xfe"
            )
        return subprocess.CompletedProcess(
            args[0], 1 if result == "failure" else 0, b"partial\xff", b"diagnostic\xfe"
        )

    monkeypatch.setattr(fixture.subprocess, "run", failed)
    with pytest.raises(ValueError, match="not a pass"):
        fixture.prepare_fixture(arguments(source, archive, installer, output))
    assert (output / "seed.stdout").read_bytes() == b"partial\xff"
    assert (output / "seed.stderr").read_bytes() == b"diagnostic\xfe"
    assert not (output / "fixture-preparation.json").exists()
    assert not (output / "copied-for-eventual-replacement").exists()


@pytest.mark.parametrize("before,after", [(True, 1), (1, 1.0), (False, 0)])
def test_typed_original_values_do_not_compare_equal_after_retyping(before, after):
    assert not worker.same_json({"original": before}, {"original": after})


@pytest.mark.parametrize(
    "pragma,value", [("user_version", 9), ("application_id", 42), ("page_size", 8192)]
)
def test_live_sqlite_metadata_mutation_is_observed_without_reopening_runtime(
    tmp_path, pragma, value
):
    path = tmp_path / "fictional.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE originals (value TEXT)")
        db.execute("INSERT INTO originals VALUES ('Preserve exact é 🐝')")
    before = worker.sqlite_snapshot(path)
    with sqlite3.connect(path) as db:
        db.execute(f"PRAGMA {pragma}={value}")
        if pragma == "page_size":
            db.execute("VACUUM")
    after = worker.sqlite_snapshot(path)
    assert after["tables"] == before["tables"]
    assert after["metadata"][pragma] == value
    assert not worker.same_json(before, after)


def test_fixture_seed_creates_rich_work_and_per_request_capability_proofs(tmp_path):
    # Current-source compatibility control only. This does not stand in for E's
    # actual immutable source pin; the outer producer refuses these bytes.
    source = tmp_path / "synthetic-source"
    shutil.copytree(ROOT / "src", source / "src")
    version = source / "src/sinter/__init__.py"
    version.write_text('__version__ = "0.5.4rc3"\n', encoding="utf-8")
    before_source = fixture.hashes(source)
    workspace, expected_path = tmp_path / "workspace", tmp_path / "originals.json"
    command = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(ROOT / "tools/published_rc3_fixture_seed.py"),
        str(source),
        str(workspace),
        str(expected_path),
    ]
    result = subprocess.run(
        command,
        env=fixture.seed_environment(tmp_path),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=40,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert result.stderr == b""
    value = json.loads(expected_path.read_text(encoding="utf-8"))
    assert value["provider_calls"] == value["external_connections"] == 0
    assert value["settings"]["model"] == "fictional-upgrade-model"
    assert value["connection"]["inherit_key"] is False
    assert value["public_settings"]["has_session_key"] is False
    assert value["public_settings"]["environment_override"] is False
    campaign = value["campaign"]["document"]
    assert campaign["requirements"][0]["status"] == "met"
    assert campaign["requirements"][0]["source_url"] != campaign["sources"][0]["url"]
    assert [
        (row["owner_kind"], row["owner_confirmed"], row["due"])
        for row in campaign["actions"]
    ] == [
        ("unknown", False, "2026-10-09"),
        ("unassigned", False, ""),
    ]
    assert campaign["answers"][0]["status"] == "reviewed"
    assert [row["unit_cost"] for row in campaign["budget"]] == [
        "110.00",
        "100.00",
        None,
    ]
    assert "including GST" in campaign["budget"][0]["quote_reference"]
    assert "excluding GST" in campaign["budget"][1]["quote_reference"]
    assert value["watch"]["enabled"] == 0
    historical, scoped = value["historical_casebook"], value["scoped_casebook"]
    assert historical["id"] == scoped["id"] and (
        historical["revision"],
        scoped["revision"],
    ) == (1, 2)
    assert historical["document"]["schema"] == "sinter-casebook/v1"
    assert scoped["document"]["schema"] == worker.SCHEMA
    assert historical["document"]["documents"] == scoped["document"]["documents"]
    assert scoped["document"]["question_scopes"][1]["source_ids"] == []
    assert scoped["document"]["documents"][2]["date"] == ""
    assert all("id" not in row["stored_report"] for row in value["raw_reports"])
    retained = next(
        row["stored_report"]
        for row in value["raw_reports"]
        if row["report_id"] == value["historical_report_id"]
    )
    assert retained["document_edits"]["author"] == "user"
    assert "é 🐝" in retained["document_edits"]["markdown"]
    assert retained["review_status"] == "draft"
    protocol = value["source_protocol_checks"]
    for name in (
        "v2_read_without_capability_refused",
        "v2_backup_without_capability_refused",
        "older_reader_resave_refused",
        "v2_build_without_capability_refused",
        "v2_draft_without_capability_refused",
        "v2_draft_without_consent_refused",
    ):
        assert protocol[name]["status"] == 400
    assert protocol["v1_read_without_capability"]["capability_present"] is False
    assert protocol["v2_read_with_capability"]["capability_present"] is True
    assert protocol["selected_empty_and_default_all_choices_preserved"] is True
    assert protocol["persistent_originals_and_settings_unchanged"] is True
    assert protocol["owned_listener_closed"] is True
    assert worker.same_json(
        value["persistent_snapshot"], worker.workspace_snapshot(workspace)
    )
    assert fixture.hashes(source) == before_source
    for name, book in (
        ("plain-v1", value["plain_casebook"]),
        ("historical-v1", historical),
        ("scoped-v2", scoped),
    ):
        backup = json.loads(
            (workspace / "fixture-backups" / (name + ".json")).read_text(
                encoding="utf-8"
            )
        )
        assert worker.same_json(backup, book["document"])
    # Changing a quoted original or edit is detected; snapshots never normalize it.
    changed = copy.deepcopy(value["persistent_snapshot"])
    changed["preferences"]["model"] = "replacement-model"
    assert not worker.same_json(value["persistent_snapshot"], changed)


def test_success_retains_exact_copy_without_candidate_or_installed_pass(
    monkeypatch, tmp_path
):
    source, archive, installer = small_inputs(monkeypatch, tmp_path)
    output = tmp_path / "output"

    def fake_seed(command, **kwargs):
        # Ordinary worker orchestration control, not an actual E evidence fixture.
        original, expected = map(Path, command[-2:])
        original.mkdir()
        (original / "original.json").write_bytes(
            b'{"unknown":null,"confirmed":false}\n'
        )
        expected.write_text(
            json.dumps({"prior_version": "0.5.4rc3", "source_protocol_checks": {}}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(fixture.subprocess, "run", fake_seed)
    receipt = fixture.prepare_fixture(arguments(source, archive, installer, output))
    assert receipt["fixture_created"] is True
    assert "passed" not in receipt
    assert all(
        receipt[name] is False
        for name in (
            "candidate_admitted",
            "candidate_tested",
            "prior_binary_tested",
            "package_replacement_tested",
        )
    )
    assert receipt["original_fixture_hashes"] == receipt["copied_fixture_hashes"]
    assert (output / "original-E-workspace/original.json").read_bytes() == (
        output / "copied-for-eventual-replacement/original.json"
    ).read_bytes()
    assert receipt["fixture_originals_sha256"] == fixture.file_sha256(
        output / "fixture-originals.json"
    )
    original = (output / "original-E-workspace/original.json").read_bytes()
    (output / "copied-for-eventual-replacement/original.json").write_bytes(
        b'{"unknown":true}'
    )
    assert (output / "original-E-workspace/original.json").read_bytes() == original


def test_source_changed_during_seed_cannot_emit_preparation_receipt(
    monkeypatch, tmp_path
):
    source, archive, installer = small_inputs(monkeypatch, tmp_path)
    output = tmp_path / "output"

    def changed(command, **kwargs):
        original, expected = map(Path, command[-2:])
        original.mkdir()
        expected.write_text(
            json.dumps({"prior_version": "0.5.4rc3", "source_protocol_checks": {}}),
            encoding="utf-8",
        )
        (source / "src/prior.py").write_bytes(b"Changed during worker execution")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(fixture.subprocess, "run", changed)
    with pytest.raises(ValueError):
        fixture.prepare_fixture(arguments(source, archive, installer, output))
    assert not (output / "fixture-preparation.json").exists()
    assert not (output / "copied-for-eventual-replacement").exists()


def test_encoding_is_retained_as_live_persistent_metadata(tmp_path):
    paths = [tmp_path / "utf8.sqlite3", tmp_path / "utf16.sqlite3"]
    snapshots = []
    for path, encoding in zip(paths, ("UTF-8", "UTF-16le")):
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA encoding='" + encoding + "'")
            db.execute("CREATE TABLE originals (value TEXT)")
            db.execute("INSERT INTO originals VALUES ('Preserve exact é 🐝')")
        snapshots.append(worker.sqlite_snapshot(path))
    assert snapshots[0]["tables"] == snapshots[1]["tables"]
    assert snapshots[0]["metadata"]["encoding"] == "UTF-8"
    assert snapshots[1]["metadata"]["encoding"] == "UTF-16le"
    assert not worker.same_json(*snapshots)


@pytest.mark.parametrize("index", range(4))
def test_python_profile_call_requires_literal_builtin_strings(index):
    class Text(str):
        pass

    values = ["0.5.4rc3", fixture.PUBLISHED_E.source_commit, "0.5.4rc4", "linux-x64"]
    values[index] = Text(values[index])
    with pytest.raises(ValueError, match="exact published E"):
        fixture.select_fixture_profile(*values)


@pytest.mark.parametrize("system_key", ["SystemRoot", "SYSTEMROOT"])
def test_windows_seed_environment_has_bootstrap_and_fictional_home_only(
    monkeypatch, tmp_path, system_key
):
    inherited = {
        system_key: "C:\\Windows",
        "USERPROFILE": "C:\\Users\\FictionalCaller",
        "HOME": "C:\\Users\\FictionalCaller",
        "NEUROFORGE_BASE_URL": "https://example.invalid/private",
        "NEUROFORGE_API_KEY": "fictional-key-do-not-inherit",
        "PYTHONPATH": "fictional-foreign-imports",
    }
    original = dict(inherited)
    monkeypatch.setattr(
        fixture,
        "os",
        SimpleNamespace(name="nt", defpath="fixed-path", environ=inherited),
    )
    assert fixture.seed_environment(tmp_path) == {
        "PATH": "fixed-path",
        "SystemRoot": "C:\\Windows",
        "USERPROFILE": str(tmp_path.resolve()),
    }
    assert inherited == original


@pytest.mark.parametrize("system_root", [None, "", "invalid\x00path", 17])
def test_windows_seed_environment_refuses_missing_or_invalid_bootstrap(
    monkeypatch, tmp_path, system_root
):
    monkeypatch.setattr(
        fixture,
        "os",
        SimpleNamespace(
            name="nt", defpath="fixed-path", environ={"SystemRoot": system_root}
        ),
    )
    with pytest.raises(ValueError, match="valid SystemRoot"):
        fixture.seed_environment(tmp_path)


def test_posix_seed_environment_does_not_inherit_windows_or_provider_settings(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        fixture,
        "os",
        SimpleNamespace(
            name="posix",
            defpath="fixed-path",
            environ={
                "SystemRoot": "fictional-system",
                "USERPROFILE": "fictional-profile",
                "NEUROFORGE_BASE_URL": "https://example.invalid/private",
            },
        ),
    )
    assert fixture.seed_environment(tmp_path) == {"PATH": "fixed-path"}
