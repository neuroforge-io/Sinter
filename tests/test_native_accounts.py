"""Frozen identity capability is proved separately from the dependency-free core."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sinter import desktop

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "native_packaging", ROOT / "tools" / "package_native.py"
)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def test_native_verifier_runs_real_crypto_without_provider_access(monkeypatch):
    pytest.importorskip("jwt")
    pytest.importorskip("cryptography")
    monkeypatch.setattr(
        desktop.urllib.request,
        "build_opener",
        lambda *args: pytest.fail("offline self-test contacted a provider"),
    )
    result = desktop.account_runtime_test()
    assert result["account_auth_bundled"] is True
    assert set(result["account_auth_dependencies"]) == set(package.AUTH_PACKAGES)


def test_missing_verifier_returns_explicit_unbundled_capability(monkeypatch):
    monkeypatch.setattr(desktop.importlib.util, "find_spec", lambda name: None)
    assert desktop.account_runtime_test() == {"account_auth_bundled": False}


def test_frozen_receipt_must_prove_actual_crypto_and_versions(monkeypatch):
    versions = {name: "fixture-version" for name in package.AUTH_PACKAGES}
    monkeypatch.setattr(
        package.importlib.metadata, "version", lambda name: versions[name]
    )
    receipt = {
        "account_auth_bundled": True,
        "checks": [package.ACCOUNT_CHECK],
        "account_auth_dependencies": versions,
    }
    package.verify_account_receipt(receipt)
    for changed in [
        {**receipt, "account_auth_bundled": False},
        {**receipt, "checks": []},
        {**receipt, "account_auth_dependencies": {**versions, "PyJWT": "other"}},
    ]:
        with pytest.raises(RuntimeError):
            package.verify_account_receipt(changed)
    package.verify_account_receipt({"account_auth_bundled": False}, False)
    with pytest.raises(RuntimeError, match="claimed account verification"):
        package.verify_account_receipt(
            {"account_auth_bundled": False, "checks": [package.ACCOUNT_CHECK]}, False
        )


def runtime_receipt():
    return {
        "schema": "sinter-native-test/v1",
        "version": desktop.__version__,
        "system": "Linux",
        "machine": "x86_64",
        "pointer_bits": 64,
        "python": "fixture-python",
        "frozen": True,
        "passed": True,
        "checks": ["frozen fixture checks"],
        "account_auth_bundled": False,
    }


def test_published_receipt_retains_actual_installed_checks_and_frozen_proof():
    runtime = runtime_receipt()
    receipt = {**runtime, "source_commit": "verified-source", "installer": "fixture"}
    installed = {
        **runtime,
        "checks": ["actual installed checks"],
        "source_commit": "must-not-overwrite-source",
    }
    package.record_installed_receipt(receipt, installed, False)
    assert receipt["frozen_test"] == runtime
    assert receipt["installed_test"] == installed
    assert receipt["checks"] == ["actual installed checks"]
    assert receipt["source_commit"] == "verified-source"
    assert receipt["installer"] == "fixture"


@pytest.mark.parametrize(
    "field,value",
    [
        ("passed", False),
        ("frozen", False),
        ("version", "other"),
        ("system", "other"),
        ("machine", "other"),
        ("pointer_bits", 8),
        ("python", "other"),
        ("account_auth_bundled", True),
    ],
)
def test_installed_receipt_must_match_target_and_capability(field, value):
    receipt = runtime_receipt()
    installed = {**receipt, field: value}
    with pytest.raises(RuntimeError):
        package.record_installed_receipt(receipt, installed, False)
    assert "installed_test" not in receipt


def test_core_freezer_explicitly_excludes_installed_optional_verifiers():
    arguments = package.account_bundle_arguments(False)
    for name in ("jwt", "cryptography", "cffi", "pycparser"):
        index = arguments.index(name)
        assert arguments[index - 1] == "--exclude-module"
    assert "--collect-all" not in arguments


def test_account_freezer_collects_dynamic_modules_and_version_metadata():
    arguments = package.account_bundle_arguments()
    for module in ("jwt", "cryptography", "cffi", "pycparser"):
        assert arguments[arguments.index(module) - 1] == "--collect-all"
    for name in package.AUTH_PACKAGES:
        metadata = [
            arguments[index + 1]
            for index, value in enumerate(arguments)
            if value == "--copy-metadata"
        ]
        assert name in metadata


def test_python310_dependency_is_bundled_and_explicitly_excluded_for_core(
    monkeypatch,
):
    monkeypatch.setattr(
        package, "AUTH_PACKAGES", (*package.AUTH_PACKAGES, "typing_extensions")
    )
    bundled = package.account_bundle_arguments()
    assert bundled[bundled.index("typing_extensions") - 1] == "--hidden-import"
    metadata = [
        bundled[index + 1]
        for index, value in enumerate(bundled)
        if value == "--copy-metadata"
    ]
    assert "typing_extensions" in metadata
    core = package.account_bundle_arguments(False)
    assert core[core.index("typing_extensions") - 1] == "--exclude-module"


@pytest.fixture
def licence_environment(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        (root / name).write_text("Sinter fixture notice")
    stdlib = tmp_path / "stdlib"
    stdlib.mkdir()
    (stdlib / "LICENSE.txt").write_text("Python fixture licence")
    monkeypatch.setattr(package, "ROOT", root)
    monkeypatch.setattr(package.sysconfig, "get_path", lambda name: str(stdlib))
    monkeypatch.setattr(package.sys, "base_prefix", str(stdlib))
    distributions = {}
    for name in ("pyinstaller", "certifi", *package.AUTH_PACKAGES):
        folder = tmp_path / name
        entries = ["metadata/licenses/LICENSE"]
        if name == "cryptography":
            entries += [
                "metadata/licenses/LICENSE.APACHE",
                "metadata/licenses/LICENSE.BSD",
            ]
        for entry in entries:
            path = folder / entry
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name + " " + Path(entry).name)
        distributions[name] = SimpleNamespace(
            version="fixture-version",
            files=[importlib.metadata.PackagePath(entry) for entry in entries],
            locate_file=lambda entry, folder=folder: folder / entry,
        )
    monkeypatch.setattr(
        package.importlib.metadata, "distribution", distributions.__getitem__
    )
    return tmp_path, distributions


def test_collect_licences_preserves_each_upstream_variant_and_provenance(
    licence_environment,
):
    directory, _ = licence_environment
    notices = directory / "notices"
    inventory = package.collect_licences(notices)
    crypto = next(row for row in inventory if row["name"] == "cryptography")
    assert len(crypto["licences"]) == 3
    assert len(list((notices / "cryptography").rglob("LICENSE*"))) == 3
    for row in inventory:
        for record in row["licences"]:
            assert (
                hashlib.sha256((notices / record["path"]).read_bytes()).hexdigest()
                == record["sha256"]
            )
    receipt = json.loads((notices / "bundled-dependencies.json").read_text())
    assert receipt["account_auth_bundled"] is True and receipt["packages"] == inventory


def test_core_licences_do_not_claim_unbundled_account_packages(licence_environment):
    directory, _ = licence_environment
    notices = directory / "notices"
    inventory = package.collect_licences(notices, accounts=False)
    assert {row["name"] for row in inventory} == {"pyinstaller", "certifi"}
    assert (
        json.loads((notices / "bundled-dependencies.json").read_text())[
            "account_auth_bundled"
        ]
        is False
    )


def test_missing_auth_licence_refuses_packaging(licence_environment):
    directory, distributions = licence_environment
    distributions["cryptography"].files = []
    with pytest.raises(RuntimeError, match="cryptography licence"):
        package.collect_licences(directory / "notices")


def test_portable_zipapp_opens_without_site_packages(tmp_path):
    builder_spec = importlib.util.spec_from_file_location(
        "portable_builder", ROOT / "tools" / "build_zipapp.py"
    )
    builder = importlib.util.module_from_spec(builder_spec)
    builder_spec.loader.exec_module(builder)
    archive = builder.build(tmp_path / "sinter.pyz")
    # -I isolates user imports and -S removes site-packages, including PyJWT.
    run = subprocess.run(
        [sys.executable, "-I", "-S", str(archive), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == f"sinter {desktop.__version__}"
