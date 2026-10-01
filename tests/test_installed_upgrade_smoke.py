"""Only published prior identities may reach disposable package replacement."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "installed_upgrade_smoke",
    Path(__file__).parents[1] / "tools" / "installed_upgrade_smoke.py",
)
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


def arguments(tmp_path, version="0.5.4rc1"):
    prior = upgrade.QUALIFIED_PRIORS[version]
    source = tmp_path / "prior-source"
    source.mkdir()
    prior_installer = tmp_path / "prior.deb"
    prior_installer.write_bytes(b"Fictional prior installer bytes")
    candidate = tmp_path / "candidate.deb"
    candidate.write_bytes(b"Fictional candidate installer bytes")
    return SimpleNamespace(
        prior_version=version,
        prior_commit=prior.source_commit,
        prior_source=source,
        prior_source_archive=tmp_path / "prior-source.zip",
        prior_installer=prior_installer,
        prior_sha256=prior.installer_sha256,
        candidate_installer=candidate,
        source_commit="c" * 40,
        expected_version="0.5.4rc3" if version == "0.5.4rc2" else "0.5.4rc2",
        output=tmp_path / "proof",
    )


def permit_disposable_fixture(monkeypatch):
    """Simulate the sandbox guard without ever invoking an installer."""
    monkeypatch.setattr(upgrade.os, "geteuid", lambda: 0)
    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: True if str(path) == "/.dockerenv" else original_is_file(path),
    )
    monkeypatch.setattr(upgrade, "installed_version", lambda: "")


@pytest.mark.parametrize("version", ["0.5.3", "0.5.4rc1", "0.5.4rc2"])
@pytest.mark.parametrize("caller_matches_forged_bytes", [False, True])
def test_caller_digest_cannot_reseal_an_unqualified_installer(
    monkeypatch,
    tmp_path,
    version,
    caller_matches_forged_bytes,
):
    args = arguments(tmp_path, version)
    if caller_matches_forged_bytes:
        args.prior_sha256 = hashlib.sha256(
            args.prior_installer.read_bytes()
        ).hexdigest()
    permit_disposable_fixture(monkeypatch)
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("Unqualified package reached dpkg"),
    )
    with pytest.raises(ValueError, match="published checksum"):
        upgrade.qualify(args)
    assert not args.output.exists()
    assert args.prior_installer.read_bytes() == b"Fictional prior installer bytes"


def simulated_replacement(monkeypatch, tmp_path, version):
    """Exercise receipt and replacement ordering with no host package operations."""
    args = arguments(tmp_path, version)
    prior = upgrade.QUALIFIED_PRIORS[version]._replace(
        installer_sha256=hashlib.sha256(args.prior_installer.read_bytes()).hexdigest()
    )
    args.prior_sha256 = prior.installer_sha256
    monkeypatch.setattr(upgrade, "prior_for_arguments", lambda args: prior)
    permit_disposable_fixture(monkeypatch)
    binary = tmp_path / "installed-binary"
    monkeypatch.setattr(upgrade, "BINARY", binary)
    package_versions = {
        args.prior_installer: upgrade.debian_package_version(version),
        args.candidate_installer: upgrade.debian_package_version(args.expected_version),
    }
    monkeypatch.setattr(
        upgrade,
        "package_field",
        lambda path, key: {
            "Package": "sinter",
            "Architecture": "amd64",
            "Version": package_versions[path],
        }[key],
    )
    state = {"installed": ""}
    operations = []

    def package_operation(command, **kwargs):
        operations.append(command)
        if command[1] == "--compare-versions":
            assert command[2:] == [
                package_versions[args.prior_installer],
                "lt",
                upgrade.debian_package_version(args.expected_version),
            ]
        elif command[1] == "-i":
            installer = Path(command[2])
            if installer == args.candidate_installer:
                assert state["installed"] == package_versions[args.prior_installer]
            state["installed"] = package_versions[installer]
            binary.write_bytes(b"Fictional installed binary")
        else:
            assert command == ["dpkg", "-r", "sinter"]
            state["installed"] = ""
            binary.unlink()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(upgrade.subprocess, "run", package_operation)
    monkeypatch.setattr(upgrade, "installed_version", lambda: state["installed"])

    def fixture(source, output, **kwargs):
        assert kwargs == {
            "prior": prior,
            "prior_source_archive": args.prior_source_archive,
        }
        output.mkdir()
        original = output / "prior-workspace"
        original.mkdir()
        (original / "preferences.json").write_text('{"model":"retained"}')
        copied = output / "candidate-workspace"
        copied.mkdir()
        return {"prior_version": version}, original, copied, upgrade.hashes(original)

    monkeypatch.setattr(upgrade, "prepare_fixture", fixture)
    launches = []

    def launch(binary_arg, copied, expected, output, selected_version, **kwargs):
        launches.append((selected_version, kwargs))
        assert binary_arg == binary and binary.is_file()
        return selected_version, ["Fictional retained work inspected"]

    monkeypatch.setattr(upgrade, "run_native", launch)
    return args, prior, operations, launches, state, binary


@pytest.mark.parametrize("version", ["0.5.3", "0.5.4rc1", "0.5.4rc2"])
def test_both_priors_are_replaced_without_uninstall_and_receipt_uses_exact_prior(
    monkeypatch,
    tmp_path,
    version,
):
    args, prior, operations, launches, state, binary = simulated_replacement(
        monkeypatch, tmp_path, version
    )
    receipt = upgrade.qualify(args)
    assert launches == [(version, {"legacy": True}), (args.expected_version, {})]
    assert [command[:2] for command in operations] == [
        ["dpkg", "--compare-versions"],
        ["dpkg", "-i"],
        ["dpkg", "-i"],
        ["dpkg", "-r"],
    ]
    assert not binary.exists() and state["installed"] == ""
    assert receipt["prior_source_commit"] == prior.source_commit
    assert receipt["prior_source_archive_sha256"] == prior.source_archive_sha256
    assert receipt["prior_installer_sha256"] == prior.installer_sha256
    assert receipt["prior_app_version"] == version
    assert receipt["prior_package_version"] == upgrade.debian_package_version(version)
    assert receipt["candidate_app_version"] == args.expected_version
    assert receipt["candidate_package_version"] == upgrade.debian_package_version(
        args.expected_version
    )
    assert f"published v{version} installer" in receipt["checks"][0]
    assert receipt["original_fixture_hashes"] == upgrade.hashes(
        args.output / "prior-workspace"
    )
    json.dumps(receipt)


@pytest.mark.parametrize(
    "field,wrong",
    [
        ("Architecture", "arm64"),
        ("Package", "unrelated"),
        ("Version", "9.9.9"),
    ],
)
def test_prior_control_identity_must_match_before_fixture_or_install(
    monkeypatch,
    tmp_path,
    field,
    wrong,
):
    args, _, operations, _, _, _ = simulated_replacement(
        monkeypatch, tmp_path, "0.5.4rc1"
    )
    original_field = upgrade.package_field
    monkeypatch.setattr(
        upgrade,
        "package_field",
        lambda path, key: (
            wrong
            if path == args.prior_installer and key == field
            else original_field(path, key)
        ),
    )
    with pytest.raises(ValueError):
        upgrade.qualify(args)
    assert not operations and not args.output.exists()


def test_invalid_package_upgrade_order_cannot_create_a_receipt(monkeypatch, tmp_path):
    args, _, _, _, _, _ = simulated_replacement(monkeypatch, tmp_path, "0.5.4rc1")
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1),
    )
    with pytest.raises(ValueError, match="upgrade order"):
        upgrade.qualify(args)
    assert not args.output.exists()
