"""Copied-workspace qualification must reject lost data and foreign endpoints."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "upgrade_smoke", Path(__file__).parents[1] / "tools" / "upgrade_smoke.py"
)
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


def test_additive_defaults_preserve_original_unknowns_and_user_edits():
    original = {
        "id": "retained",
        "document": {
            "status": "unknown",
            "rows": [{"quote": "Original evidence — unchanged", "confirmed": False}],
            "edits": {"markdown": "# User's reviewed draft"},
        },
    }
    current = {
        **original,
        "document": {**original["document"], "new_default": "unknown"},
    }
    upgrade.assert_preserved(original, current, "fixture")
    current["document"]["rows"] = [{"quote": "Replaced evidence", "confirmed": True}]
    with pytest.raises(AssertionError, match="original value"):
        upgrade.assert_preserved(original, current, "fixture")


@pytest.mark.parametrize("changed", [[], [{}, {}], [{"confirmed": 0}]])
def test_recovery_receipt_rejects_removed_added_or_retyped_existing_rows(changed):
    with pytest.raises(AssertionError):
        upgrade.assert_preserved([{"confirmed": False}], changed, "rows")


@pytest.mark.parametrize(
    "address",
    [
        "https://127.0.0.1:1234/",
        "http://example.invalid:1234/",
        "http://localhost:1234/",
        "http://127.0.0.1/",
        "http://user:secret@127.0.0.1:1234/",
        "http://127.0.0.1:1234/api/session",
        "http://127.0.0.1:1234/?token=secret",
        "http://127.0.0.1:1234/#fragment",
    ],
)
def test_upgrade_inspection_rejects_nonlocal_or_credential_addresses(address):
    with pytest.raises(ValueError):
        upgrade.loopback_base(address)
    assert upgrade.loopback_base("http://127.0.0.1:1234/") == "http://127.0.0.1:1234"


def test_fixture_hashing_rejects_links_to_unrelated_workspaces(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text("unrelated confidential workspace")
    (fixture / "link.json").symlink_to(unrelated)
    with pytest.raises(ValueError, match="symbolic links"):
        upgrade.hashes(fixture)


def small_source(monkeypatch, tmp_path, version="0.5.4rc1"):
    """Use tiny injected bytes to exercise verification, never a published receipt."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "prior.py").write_text("# Fictional prior fixture code\n")
    archive = tmp_path / "prior-source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(source / "src" / "prior.py", "src/prior.py")
    prior = upgrade.QUALIFIED_PRIORS[version]._replace(
        source_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(upgrade, "QUALIFIED_PRIORS", MappingProxyType({version: prior}))
    monkeypatch.setitem(
        upgrade.qualified_prior.__globals__,
        "QUALIFIED_PRIORS",
        MappingProxyType({version: prior}),
    )
    return source, archive, prior


def test_only_exact_published_prior_identities_are_qualified():
    assert set(upgrade.QUALIFIED_PRIORS) == {"0.5.3", "0.5.4rc1", "0.5.4rc2"}
    assert upgrade.QUALIFIED_PRIORS["0.5.3"] == (
        "0.5.3",
        "07bf7df8f233b555218b7957060968c7cdb29d99",
        "ec4abbc0ed4e121c50a5d383296c4b84d4a2a2b2ea981688e1c80c29333f8f6d",
        "ae2d72ea31237b2297946a8ae43fe904848acd0f0b47b88c6c56791f5ed13d62",
    )
    assert upgrade.QUALIFIED_PRIORS["0.5.4rc1"] == (
        "0.5.4rc1",
        "cd928ba7561a09c477b3555e64aa6a3c4cc122b4",
        "873d539cb7d7d1de9b983283f3c5f20b28f6585b84c16b320920a236bf1dcf96",
        "31f64e2af6693a21b31c6296ee41aad68516238d6a9d4f34990e91632eb2a08d",
    )
    assert upgrade.QUALIFIED_PRIORS["0.5.4rc2"] == (
        "0.5.4rc2",
        "256d38fa4b61a4d548472ce5abfd0bf513789090",
        "d53690e159ca4a21e9ec71a0997115bc96bec2486269807f97d8ed92a7301bfc",
        "eaf318d142e68e942fa17f0881f52bf98bbf0cee30e4bb9fdb84b7002c56b7f0",
    )
    with pytest.raises(TypeError):
        upgrade.QUALIFIED_PRIORS["9.9.9"] = upgrade.QUALIFIED_PRIORS["0.5.3"]


@pytest.mark.parametrize(
    "version,commit",
    [
        ("9.9.9", "e" * 40),
        ("0.5.4rc1", "e" * 40),
        ("0.5.3", "cd928ba7561a09c477b3555e64aa6a3c4cc122b4"),
    ],
)
def test_unknown_or_crossed_prior_source_pin_is_refused(version, commit):
    with pytest.raises(ValueError, match="explicitly qualified"):
        upgrade.qualified_prior(version, commit)


@pytest.mark.parametrize(
    "version,commit",
    [
        (None, None),
        ([], None),
        (1, None),
        ("0.5.4rc1", {}),
    ],
)
def test_malformed_prior_identity_is_a_clean_refusal(version, commit):
    with pytest.raises(ValueError, match="explicitly qualified"):
        upgrade.qualified_prior(version, commit)


@pytest.mark.parametrize("version", ["0.5.3", "0.5.4rc1"])
def test_source_archive_and_every_extracted_file_must_match(
    monkeypatch,
    tmp_path,
    version,
):
    source, archive, prior = small_source(monkeypatch, tmp_path, version)
    assert upgrade.verify_prior_source(source, archive, prior) == upgrade.hashes(source)
    original = (source / "src" / "prior.py").read_bytes()
    (source / "src" / "prior.py").write_bytes(
        original.replace(b"Fictional", b"Different")
    )
    with pytest.raises(ValueError, match="Extracted prior source.*differs"):
        upgrade.verify_prior_source(source, archive, prior)


@pytest.mark.parametrize("mutation", ["extra", "missing", "link"])
def test_extracted_prior_extras_missing_files_and_links_are_refused(
    monkeypatch,
    tmp_path,
    mutation,
):
    source, archive, prior = small_source(monkeypatch, tmp_path)
    if mutation == "extra":
        (source / "rogue.py").write_text("# Extra input\n")
    elif mutation == "missing":
        (source / "src" / "prior.py").unlink()
    else:
        (source / "foreign.py").symlink_to(tmp_path / "foreign.py")
    with pytest.raises(ValueError):
        upgrade.verify_prior_source(source, archive, prior)


def test_matching_resealed_caller_source_digest_cannot_replace_published_pin(tmp_path):
    source, archive = tmp_path / "source", tmp_path / "source.zip"
    source.mkdir()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("rogue.py", "# Arbitrary fixture code\n")
    forged = upgrade.QUALIFIED_PRIORS["0.5.4rc1"]._replace(
        source_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError, match="qualified release pin"):
        upgrade.verify_prior_source(source, archive, forged)
    with pytest.raises(ValueError, match="qualified checksum"):
        upgrade.verify_prior_source(
            source, archive, upgrade.QUALIFIED_PRIORS["0.5.4rc1"]
        )


def test_failed_source_admission_does_not_create_or_replace_workspace(
    monkeypatch,
    tmp_path,
):
    source, archive, prior = small_source(monkeypatch, tmp_path)
    output = tmp_path / "output"
    archive.write_bytes(b"Not the published source ZIP")
    with pytest.raises(ValueError, match="qualified checksum"):
        upgrade.prepare_fixture(
            source, output, prior=prior, prior_source_archive=archive
        )
    assert not output.exists()
    assert (
        (source / "src" / "prior.py")
        .read_text(encoding="utf-8")
        .startswith("# Fictional")
    )


def test_oversized_prior_archive_is_refused_before_hashing_or_reading(
    monkeypatch,
    tmp_path,
):
    source, archive, prior = small_source(monkeypatch, tmp_path)
    with archive.open("r+b") as output:
        output.truncate(upgrade.MAX_PRIOR_ARCHIVE_BYTES + 1)
    monkeypatch.setattr(
        upgrade,
        "file_sha256",
        lambda path: pytest.fail("Oversized caller input reached hashing"),
    )
    with pytest.raises(ValueError, match="size bound"):
        upgrade.verify_prior_source(source, archive, prior)


@pytest.mark.parametrize("mutation", ["unexpected", "oversized", "directory"])
def test_extracted_path_and_size_admission_precedes_all_source_hashing(
    monkeypatch,
    tmp_path,
    mutation,
):
    source, archive, prior = small_source(monkeypatch, tmp_path)
    archive_hash = upgrade.file_sha256(archive)
    output = tmp_path / "new-workspace"
    if mutation == "directory":
        (source / "unqualified-directory").mkdir()
    else:
        selected = (
            source / "unexpected.py"
            if mutation == "unexpected"
            else source / "src" / "prior.py"
        )
        with selected.open("wb") as target:
            target.truncate(upgrade.MAX_PRIOR_SOURCE_BYTES + 1)
    streamed_hash = upgrade.file_sha256
    reads = []

    def hash_archive_only(path):
        reads.append(path)
        assert path == archive, "Foreign source bytes reached hashing before admission"
        return streamed_hash(path)

    monkeypatch.setattr(upgrade, "file_sha256", hash_archive_only)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: pytest.fail("Qualification used an unbounded whole-file read"),
    )
    with pytest.raises(ValueError, match="unexpected|size differs"):
        upgrade.prepare_fixture(
            source, output, prior=prior, prior_source_archive=archive
        )
    assert reads == [archive]
    assert streamed_hash(archive) == archive_hash
    assert not output.exists()


@pytest.mark.skipif(not hasattr(upgrade.os, "mkfifo"), reason="Unix FIFO admission")
def test_extracted_nonregular_entry_is_refused_without_opening_or_blocking(
    monkeypatch,
    tmp_path,
):
    source, archive, prior = small_source(monkeypatch, tmp_path)
    upgrade.os.mkfifo(source / "unexpected-pipe")
    streamed_hash = upgrade.file_sha256

    def hash_archive_only(path):
        assert path == archive, "Nonregular intake reached source hashing"
        return streamed_hash(path)

    monkeypatch.setattr(upgrade, "file_sha256", hash_archive_only)
    with pytest.raises(ValueError, match="regular files"):
        upgrade.verify_prior_source(source, archive, prior)


def test_pinned_total_source_size_is_bounded_before_source_reads(monkeypatch, tmp_path):
    source, archive, prior = small_source(monkeypatch, tmp_path)
    monkeypatch.setattr(upgrade, "MAX_PRIOR_SOURCE_BYTES", 1)
    streamed_hash = upgrade.file_sha256

    def hash_archive_only(path):
        assert path == archive, "Oversized source total reached hashing"
        return streamed_hash(path)

    monkeypatch.setattr(upgrade, "file_sha256", hash_archive_only)
    with pytest.raises(ValueError, match="content bounds"):
        upgrade.verify_prior_source(source, archive, prior)


def test_existing_receipt_or_source_nested_output_is_preserved(monkeypatch, tmp_path):
    source, archive, prior = small_source(monkeypatch, tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    receipt = output / "prior-fixture.json"
    receipt.write_text("Retained historical fixture")
    for destination in [output, source / "output"]:
        with pytest.raises(ValueError):
            upgrade.prepare_fixture(
                source, destination, prior=prior, prior_source_archive=archive
            )
    assert receipt.read_text(encoding="utf-8") == "Retained historical fixture"
    assert not (source / "output").exists()


@pytest.mark.parametrize("version", ["0.5.3", "0.5.4rc1"])
def test_seed_uses_verified_prior_version_without_environment_or_bytecode_writes(
    monkeypatch,
    tmp_path,
    version,
):
    source, archive, prior = small_source(monkeypatch, tmp_path, version)
    output = tmp_path / "fixture"
    monkeypatch.setenv("OPENAI_API_KEY", "fictional-do-not-inherit")
    monkeypatch.setenv("NEUROFORGE_MODEL", "fictional-environment-override")

    def seed(command, **kwargs):
        assert command[1:4] == ["-I", "-S", "-B"]
        assert command[-1] == version
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert "NEUROFORGE_MODEL" not in kwargs["env"]
        original = Path(command[-3])
        original.mkdir()
        (original / "preferences.json").write_text('{"model":"retained"}')
        Path(command[-2]).write_text(json.dumps({"prior_version": version}))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(upgrade.subprocess, "run", seed)
    expected, original, copied, original_hashes = upgrade.prepare_fixture(
        source, output, prior=prior, prior_source_archive=archive
    )
    assert expected["prior_version"] == version
    assert upgrade.hashes(original) == upgrade.hashes(copied) == original_hashes
    assert list((source / "src").iterdir()) == [source / "src" / "prior.py"]


@pytest.mark.parametrize("candidate", ["0.5.4rc1", "0.5.4rc2.dev0", "9.9.9"])
def test_rc1_path_cannot_qualify_an_unselected_candidate(candidate):
    args = SimpleNamespace(
        prior_version="0.5.4rc1", prior_commit=None, expected_version=candidate
    )
    with pytest.raises(ValueError, match="explicitly qualified upgrade path"):
        upgrade.prior_for_arguments(args)


def test_legacy_and_explicit_rc1_paths_choose_their_exact_registered_source():
    for version in ["0.5.3", "0.5.4rc1"]:
        args = SimpleNamespace(
            prior_version=version, prior_commit=None, expected_version="0.5.4rc2"
        )
        assert upgrade.prior_for_arguments(args) == upgrade.QUALIFIED_PRIORS[version]


@pytest.mark.parametrize(
    "version,legacy,mode_arguments",
    [
        ("0.5.3", True, []),
        ("0.5.4rc1", True, []),
        ("0.5.4rc2", True, []),
        ("0.5.4rc3", True, ["--mode", "browser"]),
        ("0.5.4rc3", False, ["--mode", "browser"]),
    ],
)
def test_installed_browser_presentation_is_independent_of_legacy_preservation(
    monkeypatch, tmp_path, version, legacy, mode_arguments
):
    """Process seams only: no frozen prior, browser, provider or release receipt."""
    workspace, output = tmp_path / "workspace", tmp_path / "output"
    workspace.mkdir()
    output.mkdir()
    preferences = b'{"model":"retained-explicit-model"}\n'
    (workspace / "preferences.json").write_bytes(preferences)
    binary = tmp_path / "fictional-binary"
    binary.write_bytes(b"Never executed fictional binary")
    label = "prior" if legacy else "candidate"
    prior_version = version if legacy else "0.5.3"
    expected = {"prior_version": prior_version, "report": {"original": "retained"}}
    calls = []
    process = SimpleNamespace(returncode=None)
    process.poll = lambda: process.returncode
    process.wait = lambda **kwargs: process.returncode
    process.terminate = lambda: pytest.fail("Normal quit reached forced termination")
    process.kill = lambda: pytest.fail("Normal quit reached forced kill")

    def binary_version(command, **kwargs):
        assert command == [str(binary.resolve()), "--version"]
        assert kwargs["check"] is True
        return subprocess.CompletedProcess(command, 0, version + "\n", "")

    def launch(command, **kwargs):
        calls.append(command)
        assert command == [str(binary.resolve()), *mode_arguments]
        assert kwargs["env"]["SINTER_DATA_DIR"] == str(workspace)
        assert kwargs["stdout"] is kwargs["stderr"]
        (output / f"{label}-loopback-url.txt").write_text(
            "http://127.0.0.1:12345", encoding="utf-8"
        )
        return process

    class API:
        def __init__(self, url):
            assert url == "http://127.0.0.1:12345"

        def request(self, path, *args):
            if path == "/api/session":
                return {"version": version, "desktop": True, "token": "fictional"}
            assert path == "/api/desktop/quit" and args == ({},)
            process.returncode = 0

    def preserve(api, retained, *, legacy):
        assert isinstance(api, API) and retained is expected
        calls.append(("preservation", legacy))
        return ["fictional preservation seam"]

    monkeypatch.setattr(upgrade.subprocess, "run", binary_version)
    monkeypatch.setattr(upgrade.subprocess, "Popen", launch)
    monkeypatch.setattr(upgrade, "LocalAPI", API)
    monkeypatch.setattr(upgrade, "check_preserved", preserve)
    actual, checks = upgrade.run_native(
        binary, workspace, expected, output, version, legacy=legacy
    )
    assert actual == version
    assert calls == [
        [str(binary.resolve()), *mode_arguments],
        ("preservation", legacy),
    ]
    assert checks == [
        "fictional preservation seam",
        "opening candidate did not rewrite the prior preferences file",
    ]
    assert (workspace / "preferences.json").read_bytes() == preferences
    assert expected == {
        "prior_version": prior_version,
        "report": {"original": "retained"},
    }
    assert (output / f"{label}-process.log").read_bytes() == b""
    assert process.returncode == 0


def test_installed_browser_version_mismatch_refuses_before_launch(
    monkeypatch, tmp_path
):
    workspace, output = tmp_path / "workspace", tmp_path / "output"
    workspace.mkdir()
    output.mkdir()
    preferences = b'{"original":"preferences"}'
    (workspace / "preferences.json").write_bytes(preferences)
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, "0.5.4rc2\n", ""
        ),
    )
    monkeypatch.setattr(
        upgrade.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("Mismatched binary reached launch"),
    )
    with pytest.raises(AssertionError, match="binary version did not match"):
        upgrade.run_native(
            tmp_path / "never-executed", workspace, {}, output, "0.5.4rc3", legacy=True
        )
    assert (workspace / "preferences.json").read_bytes() == preferences


@pytest.mark.parametrize("version", ["0.5.3", "0.5.4rc1", "0.5.4rc2"])
def test_registered_prior_presentation_does_not_relax_exact_source_selection(version):
    prior = upgrade.QUALIFIED_PRIORS[version]
    args = SimpleNamespace(
        prior_version=version,
        prior_commit=prior.source_commit,
        expected_version="0.5.4rc3",
    )
    assert upgrade.prior_for_arguments(args) is prior
    args.prior_commit = "0" * 40
    with pytest.raises(ValueError, match="qualified prior version and source"):
        upgrade.prior_for_arguments(args)


@pytest.mark.parametrize("prior", ["0.5.4rc3", "0.5.4rc3.dev0", "9.9.9", None, True])
def test_presentation_fix_does_not_admit_unknown_prior_or_future_upgrade(prior):
    args = SimpleNamespace(
        prior_version=prior, prior_commit=None, expected_version="0.5.4rc4"
    )
    with pytest.raises(ValueError, match="qualified prior version and source"):
        upgrade.prior_for_arguments(args)


@pytest.mark.parametrize("tool", ["upgrade_smoke.py", "installed_upgrade_smoke.py"])
def test_upgrade_help_is_dependency_independent_and_requires_source_archive(
    tool, tmp_path
):
    path = Path(__file__).parents[1] / "tools" / tool
    help_result = subprocess.run(
        [upgrade.sys.executable, "-I", "-S", str(path), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "--prior-source-archive" in help_result.stdout
    assert "--prior-version {0.5.3,0.5.4rc1,0.5.4rc2}" in help_result.stdout
    missing = subprocess.run(
        [upgrade.sys.executable, "-I", "-S", str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert missing.returncode == 2
    assert "--prior-source-archive" in missing.stderr
    assert "Traceback" not in missing.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "prior,candidate,admitted",
    [
        (prior, candidate, candidate in targets)
        for prior, targets in {
            "0.5.3": {"0.5.4rc1", "0.5.4rc2", "0.5.4rc3"},
            "0.5.4rc1": {"0.5.4rc2", "0.5.4rc3"},
            "0.5.4rc2": {"0.5.4rc3"},
        }.items()
        for candidate in (
            "0.5.4rc1",
            "0.5.4rc2",
            "0.5.4rc3",
            "0.5.4rc4",
            "0.5.4rc3.dev0",
            "9.9.9",
        )
    ],
)
def test_upgrade_policy_has_no_implicit_candidate_paths(prior, candidate, admitted):
    args = SimpleNamespace(
        prior_version=prior, prior_commit=None, expected_version=candidate
    )
    if admitted:
        assert upgrade.prior_for_arguments(args) == upgrade.QUALIFIED_PRIORS[prior]
    else:
        with pytest.raises(ValueError, match="explicitly qualified upgrade path"):
            upgrade.prior_for_arguments(args)


@pytest.mark.parametrize("version", ["0.5.4rc1", "0.5.4rc2"])
def test_seed_rich_prior_semantics_without_publishing_fixture_evidence(
    tmp_path, version
):
    """Execute seed logic on copied current source; never call it a prior install."""
    import shutil

    from sinter import campaigns

    source = tmp_path / "synthetic-source"
    shutil.copytree(
        Path(__file__).parents[1] / "src" / "sinter",
        source / "src" / "sinter",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (source / "src/sinter/__init__.py").write_text(f'__version__ = "{version}"\n')
    workspace, output = tmp_path / "workspace", tmp_path / "fixture.json"
    subprocess.run(
        [
            upgrade.sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            upgrade.SEED,
            str(source),
            str(workspace),
            str(output),
            version,
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    expected = json.loads(output.read_text(encoding="utf-8"))
    document = expected["campaign"]["document"]
    assert expected["prior_version"] == version
    assert len(document["sources"]) == 1 and len(document["actions"]) == 2
    assert (
        document["requirements"][0]["source_id"]
        == document["sources"][0]["id"]
        == "a" * 32
    )
    assert document["requirements"][0]["source_url"] != document["sources"][0]["url"]
    assert document["requirements"][0]["checked_at"] == "2026-09-12"
    assert document["sources"][0]["checked_at"] == "2026-09-29"
    assert [row["owner_kind"] for row in document["actions"]] == [
        "unknown",
        "unassigned",
    ]
    assert all(row["owner_confirmed"] is False for row in document["actions"])
    assert document["requirements"][0]["status"] == (
        "met" if version == "0.5.4rc2" else "unknown"
    )
    if version == "0.5.4rc2":
        result = campaigns.prepare(document)
        assert result["readiness"]["claims_without_evidence"] == 1
        assert result["readiness"]["requirements_unresolved"] == 1
    assert expected["report"]["document_edits"]["author"] == "user"
    assert expected["source_text"] == expected["report"]["excerpts"][0]["quote"]
    assert not list(source.rglob("*.pyc"))


def test_rc2_archive_pin_still_uses_complete_source_admission(monkeypatch, tmp_path):
    source, archive, prior = small_source(monkeypatch, tmp_path, "0.5.4rc2")
    assert upgrade.verify_prior_source(source, archive, prior) == upgrade.hashes(source)
    (source / "src/prior.py").write_text("Replacement source")
    with pytest.raises(ValueError, match="Extracted prior source.*differs"):
        upgrade.verify_prior_source(source, archive, prior)


def test_rich_rc2_preservation_check_uses_actual_local_routes(tmp_path, monkeypatch):
    """Exercise source APIs only; no published/native application qualification."""
    import shutil
    import threading

    from sinter import client
    from sinter.server import Application, LocalServer

    source = tmp_path / "synthetic-source"
    shutil.copytree(
        Path(__file__).parents[1] / "src" / "sinter",
        source / "src" / "sinter",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (source / "src/sinter/__init__.py").write_text('__version__ = "0.5.4rc2"\n')
    workspace, output = tmp_path / "workspace", tmp_path / "fixture.json"
    subprocess.run(
        [
            upgrade.sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            upgrade.SEED,
            str(source),
            str(workspace),
            str(output),
            "0.5.4rc2",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    expected = json.loads(output.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        client,
        "chat",
        lambda *a, **k: pytest.fail("No model call belongs in local upgrade recovery"),
    )
    app = Application(workspace)
    server = LocalServer(("127.0.0.1", 0), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    api = upgrade.LocalAPI("http://127.0.0.1:" + str(server.server_port))
    api.token = app.token
    try:
        checks = upgrade.check_preserved(api, expected)
        assert (
            "rich prior source snapshots, stale marked review "
            "and unknown/unassigned owners retained" in checks
        )
        assert app.campaigns.get(expected["campaign"]["id"]) == expected["campaign"]
        assert app.store.report(expected["report_id"]) == expected["report"]
    finally:
        server.shutdown()
        thread.join(3)
        server.server_close()
        app.close()
    assert not thread.is_alive()
