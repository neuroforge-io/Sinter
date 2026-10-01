"""Guard the recovery producer's side effects, identities and bounded artifacts."""

from __future__ import annotations

import argparse
import builtins
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools import installed_recovery_browser as recovery
from tools.installed_recovery_contract import ARTIFACT_PATHS, CAMPAIGN_SOURCE


def source_args(tmp_path):
    return argparse.Namespace(
        output=tmp_path / "new-proof",
        source_fixture=True,
        chromium=None,
        installer=None,
        installer_sha256=None,
        source_archive=None,
        source_sha256=None,
        native_receipt=None,
        installed_workflow_receipt=None,
        workflow_sha256=None,
        version=None,
        source_commit=None,
        image="not-used-in-source-mode",
    )


@pytest.mark.parametrize("arguments,code", [(["--help"], 0), ([], 2)])
def test_help_and_missing_arguments_need_no_optional_tooling(arguments, code):
    result = subprocess.run(
        [
            sys.executable,
            str(recovery.ROOT / "tools/installed_recovery_browser.py"),
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == code
    assert "usage:" in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert "ModuleNotFoundError" not in result.stdout + result.stderr


def test_missing_browser_dependency_fails_before_creating_any_output(
    tmp_path, monkeypatch
):
    original = builtins.__import__

    def missing(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("explicit missing-extra regression")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    monkeypatch.setattr(recovery.transport, "command", lambda *args: "a" * 40)
    output = tmp_path / "new-proof"
    with pytest.raises(SystemExit, match="Host Playwright is required"):
        recovery.main(["--source-fixture", "--output", str(output)])
    assert not output.exists()


def test_source_fixture_is_explicit_and_does_not_create_output(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery.transport, "command", lambda *args: "a" * 40)
    args = source_args(tmp_path)
    inputs = recovery.validate_inputs(args)
    assert inputs["workflow"] is None
    assert (
        inputs["source"][CAMPAIGN_SOURCE]
        == (recovery.ROOT / CAMPAIGN_SOURCE).read_bytes()
    )
    assert args.version and len(args.source_commit) == 40
    assert not args.output.exists()


def test_source_fixture_without_git_identity_is_refused_before_output(
    tmp_path, monkeypatch
):
    def no_identity(*args):
        raise subprocess.CalledProcessError(128, args)

    monkeypatch.setattr(recovery.transport, "command", no_identity)
    args = source_args(tmp_path)
    with pytest.raises(subprocess.CalledProcessError):
        recovery.validate_inputs(args)
    assert not args.output.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("installer", Path("candidate.deb")),
        ("installer_sha256", "a" * 64),
        ("native_receipt", Path("candidate.json")),
        ("version", "0.5.4rc3"),
        ("source_commit", "a" * 40),
        ("workflow_sha256", "a" * 64),
    ],
)
def test_source_run_cannot_masquerade_as_installed_receipt(tmp_path, field, value):
    args = source_args(tmp_path)
    setattr(args, field, value)
    with pytest.raises(ValueError, match="cannot accept installed"):
        recovery.validate_inputs(args)
    assert not args.output.exists()


def test_existing_output_and_symlink_target_are_protected(tmp_path):
    args = source_args(tmp_path)
    args.output.mkdir()
    retained = args.output / "previous-proof.json"
    retained.write_text('{"historical":"unchanged"}')
    before = retained.read_bytes()
    with pytest.raises(ValueError, match="existing output is protected"):
        recovery.validate_inputs(args)
    assert retained.read_bytes() == before
    args.output = tmp_path / "linked-output"
    args.output.symlink_to(retained.parent)
    with pytest.raises(ValueError, match="existing output is protected"):
        recovery.validate_inputs(args)
    assert retained.read_bytes() == before


def test_installed_inputs_are_mandatory_before_process_or_docker(tmp_path):
    args = source_args(tmp_path)
    args.source_fixture = False
    with pytest.raises(ValueError, match="every pinned"):
        recovery.validate_inputs(args)
    assert not args.output.exists()


def test_stop_targets_only_the_owned_process():
    command = [sys.executable, "-c", "import time;time.sleep(30)"]
    owned, unrelated = subprocess.Popen(command), subprocess.Popen(command)
    try:
        recovery.stop_owned(owned)
        assert owned.poll() is not None
        assert unrelated.poll() is None
        recovery.stop_owned(owned)  # Completed process cleanup is safe to repeat.
        assert unrelated.poll() is None
    finally:
        recovery.stop_owned(owned)
        unrelated.terminate()
        unrelated.wait(timeout=5)


def artifact_files(tmp_path):
    directory = tmp_path / "installed-recovery"
    directory.mkdir()
    for role, name in ARTIFACT_PATHS.items():
        path = tmp_path / name
        path.write_bytes(b"not-a-real-PNG" if role.endswith("_screen") else b"{}")
    return directory


def test_incomplete_inventory_and_extra_runtime_material_fail_closed(tmp_path):
    directory = artifact_files(tmp_path)
    (directory / "launch-url.txt").write_text("runtime material must not be retained")
    with pytest.raises(ValueError, match="inventory differs"):
        recovery.inventory(tmp_path)
    (directory / "launch-url.txt").unlink()
    (tmp_path / ARTIFACT_PATHS["held_csv"]).unlink()
    with pytest.raises(ValueError, match="inventory differs"):
        recovery.inventory(tmp_path)


def test_fake_screenshot_extension_is_not_accepted(tmp_path):
    artifact_files(tmp_path)
    with pytest.raises(ValueError, match="PNG"):
        recovery.inventory(tmp_path)


def test_oversized_sparse_artifact_is_refused_before_any_content_read(
    tmp_path, monkeypatch
):
    from tools.installed_recovery_contract import MAX_ARTIFACT_BYTES

    artifact_files(tmp_path)
    phases = tmp_path / ARTIFACT_PATHS["phases"]
    with phases.open("wb") as stream:
        stream.truncate(MAX_ARTIFACT_BYTES + 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("Content was read before stat-size admission.")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(ValueError, match="size exceeds"):
        recovery.inventory(tmp_path)


def test_workspace_hashes_detect_any_saved_data_change(tmp_path):
    saved = tmp_path / "campaigns"
    saved.mkdir()
    path = saved / "fictional.json"
    path.write_text(json.dumps({"id": "a" * 32, "revision": 1}))
    before = recovery.workspace_hashes(tmp_path)
    path.write_text(json.dumps({"id": "a" * 32, "revision": 2}))
    assert recovery.workspace_hashes(tmp_path) != before


class _WindowsRelativePath:
    """Real test bytes with Windows path spelling on any executor."""

    def __init__(self, path):
        self.path = path

    def __truediv__(self, part):
        return type(self)(self.path / part)

    def __str__(self):
        return str(self.path)

    def __lt__(self, other):
        return self.path < other.path

    def relative_to(self, root):
        from pathlib import PureWindowsPath

        return PureWindowsPath(*self.path.relative_to(root.path).parts)

    def iterdir(self):
        return (type(self)(path) for path in self.path.iterdir())

    def rglob(self, pattern):
        return (type(self)(path) for path in self.path.rglob(pattern))

    def is_file(self):
        return self.path.is_file()

    def read_bytes(self):
        return self.path.read_bytes()

    def read_text(self):
        return self.path.read_text(encoding="utf-8")


def test_source_fixture_uses_portable_contract_keys_for_windows_paths(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(recovery, "ROOT", _WindowsRelativePath(recovery.ROOT))
    monkeypatch.setattr(recovery.transport, "command", lambda *args: "a" * 40)
    args = source_args(tmp_path)
    inputs = recovery.validate_inputs(args)
    assert CAMPAIGN_SOURCE in inputs["source"]
    assert "\\" not in "".join(inputs["source"])
    assert (
        inputs["source"][CAMPAIGN_SOURCE]
        == (recovery.ROOT / CAMPAIGN_SOURCE).read_bytes()
    )
    assert not args.output.exists()


def test_workspace_hash_keys_are_portable_for_windows_relative_paths(
    tmp_path, monkeypatch
):
    source = tmp_path / "folder" / "fictional.json"
    source.parent.mkdir()
    source.write_bytes(b'{"fictional":"unchanged"}')
    monkeypatch.setattr(recovery.transport, "digest", lambda path: "a" * 64)
    assert recovery.workspace_hashes(_WindowsRelativePath(tmp_path)) == {
        "folder/fictional.json": "a" * 64
    }
    assert source.read_bytes() == b'{"fictional":"unchanged"}'
