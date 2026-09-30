"""Publication must refuse missing, altered or wrong-source installer artifacts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from sinter import __version__

spec = importlib.util.spec_from_file_location(
    "release_manifest", Path(__file__).parents[1] / "tools" / "release_manifest.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def artifacts(tmp_path):
    output = tmp_path / "out"
    source = tmp_path / "source"
    output.mkdir()
    (source / "dist").mkdir(parents=True)
    (source / "verified-commit.txt").write_text("fixture-commit\n")
    (source / "sinter-source.zip").write_bytes(b"fixture archive")
    (source / "dist" / "sinter.pyz").write_bytes(b"fixture zipapp")
    for system, arch in sorted(module.EXPECTED):
        name = f"Sinter-{__version__}-{system}-{arch}.fixture"
        (output / name).write_bytes(name.encode())
        row = {
            "schema": "sinter-native-test/v1",
            "system": system,
            "machine": arch,
            "python": "fixture-python",
            "pointer_bits": 32 if arch in {"x86", "armv7"} else 64,
            "checks": ["installed fixture checks"],
            "target_arch": arch,
            "passed": True,
            "frozen": True,
            "version": __version__,
            "source_commit": "fixture-commit",
            "installer": name,
            "installer_sha256": hashlib.sha256(name.encode()).hexdigest(),
            "installer_test": "fixture test",
        }
        row["account_auth_bundled"] = (system, arch) in module.ACCOUNT_TARGETS
        if row["account_auth_bundled"]:
            row["checks"] = ["bundled ChatGPT identity verification"]
            row["account_auth_dependencies"] = {
                key: "fixture-version" for key in module.AUTH_PACKAGES
            }
            row["bundled_dependencies"] = [
                {
                    "name": key,
                    "version": "fixture-version",
                    "licences": [
                        {
                            "path": key + "/LICENSE",
                            "sha256": "a" * 64,
                        }
                    ],
                }
                for key in module.AUTH_PACKAGES
            ]
        proof = {
            key: value
            for key, value in row.items()
            if key
            not in {
                "bundled_dependencies",
                "installer",
                "installer_test",
                "installer_sha256",
                "target_arch",
                "source_commit",
            }
        }
        row["frozen_test"] = dict(proof)
        row["installed_test"] = dict(proof)
        (output / f"{system}-{arch}-test.json").write_text(json.dumps(row))
    return output, source


def test_complete_release_manifest(tmp_path):
    output, source = artifacts(tmp_path)
    module.assemble(output, source, "fixture-commit")
    result = json.loads((output / "build-manifest.json").read_text())
    assert len(result["installer_targets"]) == 9 and result["publisher_signed"] is False
    assert "build-manifest.json" in (output / "SHA256SUMS.txt").read_text()
    assert result["portable_core_account_auth_bundled"] is False
    assert len(result["account_auth_targets"]) == 6


@pytest.mark.parametrize("missing_licence", [False, True])
def test_python310_auth_dependency_requires_its_own_licence(tmp_path, missing_licence):
    output, source = artifacts(tmp_path)
    path = output / "linux-x64-test.json"
    row = json.loads(path.read_text())
    row["account_auth_dependencies"]["typing_extensions"] = "fixture-typing-version"
    for phase in ("frozen_test", "installed_test"):
        row[phase]["account_auth_dependencies"] = row["account_auth_dependencies"]
    if not missing_licence:
        row["bundled_dependencies"].append(
            {
                "name": "typing_extensions",
                "version": "fixture-typing-version",
                "licences": [{"path": "typing_extensions/LICENSE", "sha256": "b" * 64}],
            }
        )
    path.write_text(json.dumps(row))
    if missing_licence:
        with pytest.raises(ValueError, match="licence notices do not match"):
            module.assemble(output, source, "fixture-commit")
    else:
        module.assemble(output, source, "fixture-commit")


@pytest.mark.parametrize(
    "mutation",
    ["missing", "changed_package", "wrong_source", "failed", "wrong_source_archive"],
)
def test_release_rejects_invalid_receipts(tmp_path, mutation):
    output, source = artifacts(tmp_path)
    path = next(output.glob("*-test.json"))
    row = json.loads(path.read_text())
    if mutation == "missing":
        path.unlink()
    elif mutation == "changed_package":
        (output / row["installer"]).write_bytes(b"changed")
    elif mutation == "wrong_source":
        row["source_commit"] = "other"
        path.write_text(json.dumps(row))
    elif mutation == "failed":
        row["passed"] = False
        path.write_text(json.dumps(row))
    else:
        (source / "verified-commit.txt").write_text("other")
    with pytest.raises(ValueError):
        module.assemble(output, source, "fixture-commit")
    assert not (output / "build-manifest.json").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_capability",
        "wrong_capability",
        "missing_test",
        "missing_versions",
        "wrong_version",
        "missing_licence",
        "invalid_licence_digest",
        "unsafe_licence_path",
    ],
)
def test_release_rejects_unproven_account_bundle(tmp_path, mutation):
    output, source = artifacts(tmp_path)
    path = next(
        path
        for path in output.glob("*-test.json")
        if json.loads(path.read_text())["account_auth_bundled"]
    )
    row = json.loads(path.read_text())
    if mutation == "missing_capability":
        row.pop("account_auth_bundled")
    elif mutation == "wrong_capability":
        row["account_auth_bundled"] = False
    elif mutation == "missing_test":
        row["checks"] = []
    elif mutation == "missing_versions":
        row.pop("account_auth_dependencies")
    elif mutation == "wrong_version":
        row["bundled_dependencies"][0]["version"] = "different"
    elif mutation == "missing_licence":
        row["bundled_dependencies"][0]["licences"] = []
    elif mutation == "invalid_licence_digest":
        row["bundled_dependencies"][0]["licences"][0]["sha256"] = "incorrect"
    else:
        row["bundled_dependencies"][0]["licences"][0]["path"] = "../outside"
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError):
        module.assemble(output, source, "fixture-commit")
    assert not (output / "build-manifest.json").exists()


@pytest.mark.parametrize("field", ["account_auth_dependencies", "bundled_dependencies"])
def test_core_target_rejects_claims_for_excluded_account_libraries(tmp_path, field):
    output, source = artifacts(tmp_path)
    path = next(
        path
        for path in output.glob("*-test.json")
        if not json.loads(path.read_text())["account_auth_bundled"]
    )
    row = json.loads(path.read_text())
    row[field] = (
        {"cryptography": "fixture-version"}
        if field == "account_auth_dependencies"
        else [{"name": "cryptography", "version": "fixture-version"}]
    )
    if field == "account_auth_dependencies":
        for phase in ("frozen_test", "installed_test"):
            row[phase][field] = row[field]
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="excluded account dependencies"):
        module.assemble(output, source, "fixture-commit")
    assert not (output / "build-manifest.json").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_installed",
        "missing_frozen",
        "failed_installed",
        "wrong_identity",
        "wrong_published_checks",
        "wrong_frozen_account",
        "wrong_target_pointer",
    ],
)
def test_release_requires_matching_actual_installed_proof(tmp_path, mutation):
    output, source = artifacts(tmp_path)
    path = next(output.glob("*-test.json"))
    row = json.loads(path.read_text())
    if mutation == "missing_installed":
        row.pop("installed_test")
    elif mutation == "missing_frozen":
        row.pop("frozen_test")
    elif mutation == "failed_installed":
        row["installed_test"]["passed"] = False
    elif mutation == "wrong_identity":
        row["installed_test"]["pointer_bits"] = 8
    elif mutation == "wrong_published_checks":
        row["checks"] = ["summary of a different runtime"]
    elif mutation == "wrong_frozen_account":
        row["frozen_test"]["account_auth_bundled"] = not row["account_auth_bundled"]
    else:
        for phase in (row, row["installed_test"], row["frozen_test"]):
            phase["pointer_bits"] = 8
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError):
        module.assemble(output, source, "fixture-commit")
    assert not (output / "build-manifest.json").exists()
