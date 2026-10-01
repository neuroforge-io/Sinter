"""Qualification orchestration must fail before side effects on mixed provenance."""

from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path

import pytest

from tools import qualify_linux_preview as gates

COMMIT = "a" * 40


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(gates.sys, "platform", "linux")
    monkeypatch.setattr(gates.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(gates.os, "getgid", lambda: 1000, raising=False)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    installer = candidate / f"Sinter-{gates.VERSION}-linux-x64.deb"
    installer.write_bytes(b"fictional installer input; never executed")
    native = {
        "schema": "sinter-native-test/v1",
        "version": gates.VERSION,
        "source_commit": COMMIT,
        "system": "Linux",
        "target_arch": "x64",
        "passed": True,
        "frozen": True,
        "package_version": "0.5.4~rc3",
        "installer": installer.name,
        "installer_sha256": gates.digest(installer),
    }
    receipt = candidate / f"Sinter-{gates.VERSION}-linux-x64-test.json"
    receipt.write_text(json.dumps(native), encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        gates, "run", lambda command, **kw: calls.append(command) or COMMIT
    )
    # Existing artifact validators have their own actual archive regressions.
    # These seams let the wrapper's admission boundary be exercised independently.
    monkeypatch.setattr(gates, "_source", lambda *a: {"fictional": b"source"})
    monkeypatch.setattr(gates, "_native_payload", lambda *a: "b" * 64)
    return candidate, receipt, native, calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_commit", "c" * 40),
        ("version", "0.5.4rc3.dev0"),
        ("system", "Windows"),
        ("target_arch", "arm64"),
        ("passed", False),
        ("frozen", False),
        ("passed", 1),
        ("package_version", "0.5.4"),
        ("installer", "../foreign.deb"),
        ("installer_sha256", "d" * 64),
    ],
)
def test_mixed_build_identity_cannot_start_docker(tmp_path, monkeypatch, field, value):
    candidate, receipt, native, calls = fixture(tmp_path, monkeypatch)
    native[field] = value
    receipt.write_text(json.dumps(native), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in candidate.iterdir()}
    output = tmp_path / "proof"
    with pytest.raises(ValueError):
        gates.qualify(candidate, tmp_path / "priors", output, COMMIT, "unused")
    assert not output.exists()
    assert calls == [["git", "rev-parse", "HEAD"]]
    assert before == {p.name: p.read_bytes() for p in candidate.iterdir()}


def test_different_checkout_is_not_relabelled_as_build(tmp_path, monkeypatch):
    candidate, _, _, _ = fixture(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(
        gates, "run", lambda command, **kw: calls.append(command) or "c" * 40
    )
    with pytest.raises(ValueError, match="checkout"):
        gates.qualify(
            candidate, tmp_path / "priors", tmp_path / "proof", COMMIT, "unused"
        )
    assert calls == [["git", "rev-parse", "HEAD"]]
    assert not (tmp_path / "proof").exists()


def test_existing_gate_refusal_is_preserved_before_container(tmp_path, monkeypatch):
    candidate, _, _, calls = fixture(tmp_path, monkeypatch)

    def refuse(*args):
        raise ValueError("exact source archive differs")

    monkeypatch.setattr(gates, "_source", refuse)
    with pytest.raises(ValueError, match="exact source archive"):
        gates.qualify(
            candidate, tmp_path / "priors", tmp_path / "proof", COMMIT, "unused"
        )
    assert calls == [["git", "rev-parse", "HEAD"]]
    assert not (tmp_path / "proof").exists()


@pytest.mark.parametrize("name", ["existing", "invalid,mount"])
def test_existing_evidence_and_ambiguous_mounts_are_protected(
    tmp_path, monkeypatch, name
):
    output = tmp_path / name
    if name == "existing":
        output.mkdir()
        (output / "kept.txt").write_bytes(b"retained fictional proof")
    monkeypatch.setattr(
        gates, "candidate_inputs", lambda *a: pytest.fail("admission proceeded")
    )
    with pytest.raises(ValueError):
        gates.qualify(tmp_path, tmp_path, output, COMMIT, "unused")
    if name == "existing":
        assert (output / "kept.txt").read_bytes() == b"retained fictional proof"
    else:
        assert not output.exists()


def test_failed_upgrades_keep_partial_receipt_and_remove_only_owned_container(
    tmp_path, monkeypatch
):
    candidate, _, native, _ = fixture(tmp_path, monkeypatch)
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return COMMIT
        if command[:3] == ["docker", "image", "inspect"]:
            return "sha256:" + "e" * 64
        if command[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(command, 300)
        if command[:3] == ["docker", "ps", "--all"]:
            return ""
        pytest.fail(f"Unexpected execution {command}")

    removed = []
    monkeypatch.setattr(gates, "run", execute)
    monkeypatch.setattr(
        gates.subprocess, "run", lambda command, **kw: removed.append(command)
    )
    output = tmp_path / "proof"
    with pytest.raises(subprocess.TimeoutExpired):
        gates.qualify(candidate, tmp_path / "priors", output, COMMIT, "image")
    state = json.loads((output / "installed-gates.json").read_text())
    assert state["passed"] is False
    assert state["independent_clean_install"] is False
    assert state["final_candidate_gate"] is False
    assert state["publication_executed"] is False
    assert state["copied_and_installed_priors"] == []
    assert state["owned_upgrade_container_removed"] is True
    assert state["owned_containers_removed"] is True
    assert state["installer_sha256"] == native["installer_sha256"]
    launched = next(c for c in calls if c[:2] == ["docker", "run"])
    name = launched[launched.index("--name") + 1]
    assert removed == [["docker", "rm", "--force", name]]
    assert "--pull=never" in launched and "--network=none" in launched
    assert "--memory=768m" in launched and "--cpus=1" in launched
    assert launched[-1] == COMMIT
    labels = [c for c in calls if "--filter" in c]
    assert any(
        f"label=sinter.qualification.owner={state['owner']}" in c for c in labels
    )


@pytest.mark.parametrize("oversized", [False, True])
def test_corrupt_or_oversized_download_is_never_admitted(
    tmp_path, monkeypatch, oversized
):
    requests = []

    class PublicBytes:
        def open(self, url, timeout):
            requests.append(url)
            return io.BytesIO(b"invalid fictional asset")

    monkeypatch.setattr(gates.urllib.request, "build_opener", lambda *a: PublicBytes())
    if oversized:
        monkeypatch.setattr(gates, "MAX_DOWNLOAD", 2)
    output = tmp_path / "priors"
    with pytest.raises(ValueError):
        gates.fetch_priors(output)
    assert requests == [
        "https://github.com/neuroforge-io/Sinter/releases/download/v0.5.3/sinter-0.5.3-source.zip"
    ]
    assert not list(output.rglob("*.partial"))
    assert not list(output.rglob("*.zip"))


@pytest.mark.skipif(os.name != "posix", reason="Linux proof ownership and file modes")
def test_container_ownership_cleanup_preserves_modes_on_failure(tmp_path, monkeypatch):
    output = tmp_path / "proof"
    monkeypatch.setenv("SINTER_TEST_UID", "1234")
    monkeypatch.setenv("SINTER_TEST_GID", "5678")
    monkeypatch.setattr(gates.sys, "platform", "linux")
    monkeypatch.setattr(gates.os, "geteuid", lambda: 0, raising=False)
    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda p: True if str(p) == "/.dockerenv" else original_is_file(p),
    )

    def fail(*args):
        output.mkdir(mode=0o700)
        (output / "fictional.sqlite").write_bytes(b"retained partial proof")
        (output / "fictional.sqlite").chmod(0o600)
        raise ValueError("fictional producer failure")

    observed = []
    monkeypatch.setattr(gates, "_container_upgrades", fail)
    monkeypatch.setattr(
        gates.os,
        "chown",
        lambda p, uid, gid, **kw: observed.append((p, uid, gid, kw)),
        raising=False,
    )
    with pytest.raises(ValueError, match="fictional producer"):
        gates.container_upgrades(tmp_path, tmp_path, output, COMMIT)
    assert {row[0] for row in observed} == {output, output / "fictional.sqlite"}
    assert all(row[1:] == (1234, 5678, {"follow_symlinks": False}) for row in observed)
    assert (output.stat().st_mode & 0o777) == 0o700
    assert ((output / "fictional.sqlite").stat().st_mode & 0o777) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="Linux producer supervisor")
def test_actual_timeout_allows_producer_finally_and_reaps_process(tmp_path):
    script = tmp_path / "fictional-producer.py"
    marker = tmp_path / "finally.txt"
    script.write_text(
        "import time\nfrom pathlib import Path\ntry:\n"
        "    time.sleep(30)\nfinally:\n"
        f"    Path({str(marker)!r}).write_text('closed')\n",
        encoding="utf-8",
    )
    with pytest.raises(subprocess.TimeoutExpired):
        gates.run(
            [gates.sys.executable, "-B", "-c", gates.PRODUCER_ENTRY, str(script)],
            timeout=0.5,
            log=tmp_path / "producer.log",
        )
    assert marker.read_text() == "closed"


def test_hosted_gate_is_same_run_linux_only_and_nonpublishing():
    workflow = (Path(__file__).parents[1] / ".github/workflows/native.yml").read_text()
    job = workflow.split("  installed_rc3:\n", 1)[1].split("  linux32:\n", 1)[0]
    assert "needs: desktop" in job and "name: native-Linux-x64" in job
    assert "workflow_run" not in job and "run-id:" not in job
    assert "persist-credentials: false" in job and "fetch-depth: 0" in job
    assert "github.event.pull_request.head.repo.full_name == github.repository" in job
    assert "github.head_ref == 'qualification/linux-rc3-20261001'" in job
    assert '"$GITHUB_SHA"' in job and "contents: write" not in job
    assert "gh release" not in job and "release_tag.py" not in job
