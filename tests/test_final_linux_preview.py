"""Adversarial pure-data admission checks; actual installed proof belongs to CI."""

import hashlib
import json
import shutil
import subprocess
import zipfile

import pytest

from tools import finalize_linux_preview as final

BINARY = "a" * 64


def proof(tmp_path):
    values = {
        "preflight.json": {
            "schema": "sinter-clean-preflight/v1",
            "python_packages": 0,
            "python_files": 0,
            "account_packages": 0,
            "candidate_preinstalled": False,
        },
        "clean-ubuntu-installed-test.json": {
            "frozen": True,
            "passed": True,
            "version": "0.5.4rc3",
        },
        "removal.json": {"installed_selftest_completed": True, "package_removed": True},
    }
    for name, value in values.items():
        (tmp_path / name).write_text(json.dumps(value))
    (tmp_path / "preinstalled-packages.txt").write_text("libc6:amd64 ii \n")
    (tmp_path / "preinstalled-python-files.txt").write_text("")
    (tmp_path / "preinstalled-account-files.txt").write_text("")
    (tmp_path / "os-release.txt").write_text('VERSION_ID="22.04"\n')
    (tmp_path / "libc.txt").write_text("glibc 2.35\n")
    (tmp_path / "installed-binary.sha256").write_text(
        BINARY + "  /opt/neuroforge/sinter/Sinter\n"
    )
    return {"installed_test": values["clean-ubuntu-installed-test.json"]}


def test_actual_package_and_filesystem_proof_matches(tmp_path):
    native = proof(tmp_path)
    assert final.validate_clean(tmp_path, native, BINARY) == native["installed_test"]


@pytest.mark.parametrize(
    "name,content",
    [
        ("preinstalled-python-files.txt", "/usr/local/bin/python3\n"),
        ("preinstalled-account-files.txt", "/opt/lib/site-packages/jwt\n"),
        ("preinstalled-packages.txt", "python3-minimal ii \n"),
        ("os-release.txt", 'VERSION_ID="24.04"\n'),
        ("libc.txt", "glibc 2.39\n"),
        ("clean-ubuntu-installed-test.json", '{"frozen":false}'),
        ("installed-binary.sha256", "changed  /opt/neuroforge/sinter/Sinter\n"),
        (
            "removal.json",
            '{"installed_selftest_completed":true,"package_removed":false}',
        ),
        ("preflight.json", '{"python_files":0}'),
    ],
)
def test_absence_claim_or_hidden_path_cannot_replace_independent_proof(
    tmp_path, name, content
):
    native = proof(tmp_path)
    (tmp_path / name).write_text(content)
    with pytest.raises(ValueError):
        final.validate_clean(tmp_path, native, BINARY)


@pytest.mark.parametrize("path", ["../escape", "/escape", "a\\b", "a:b"])
def test_archive_rejects_unsafe_paths_even_after_digest_admission(
    tmp_path, monkeypatch, path
):
    target = tmp_path / "toy.zip"
    with zipfile.ZipFile(target, "w") as bundle:
        bundle.writestr(path, b"fictional")
    monkeypatch.setattr(
        final, "ARTIFACT_SHA", hashlib.sha256(target.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError):
        final.admit_archive(target)


def test_archive_requires_exact_original_bytes(tmp_path):
    target = tmp_path / "changed.zip"
    target.write_bytes(b"fictional corruption")
    with pytest.raises(ValueError, match="unchanged original"):
        final.admit_archive(target)


def test_legacy_gate_keeps_terminal_exclusion_and_rc3_requires_actual_notices():
    from tools.candidate_qualification import independent_review_checks

    for version in ("0.5.4rc1", "0.5.4rc2"):
        assert "readline_and_tinfo_excluded" in independent_review_checks(version)
        assert "terminal_library_notices_verified" not in independent_review_checks(
            version
        )
    rc3 = independent_review_checks("0.5.4rc3")
    assert "readline_and_tinfo_excluded" not in rc3
    assert {"readline_excluded", "terminal_library_notices_verified"} <= set(rc3)


@pytest.mark.parametrize(
    "field,value",
    [("python_files", False), ("python_packages", False), ("account_packages", False)],
)
def test_false_does_not_substitute_for_measured_zero(tmp_path, field, value):
    native = proof(tmp_path)
    path = tmp_path / "preflight.json"
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        final.validate_clean(tmp_path, native, BINARY)


def test_clean_image_has_no_python_tooling_and_app_is_not_source_mode():
    image = (final.ROOT / "tools/clean-qualification-image.Dockerfile").read_text()
    assert "python" not in image.lower()
    assert "/opt/neuroforge/sinter/Sinter" in final.CLEAN_SCRIPT
    assert "--self-test /proof/clean-ubuntu-installed-test.json" in final.CLEAN_SCRIPT
    assert "dpkg -i /candidate/" in final.CLEAN_SCRIPT
    assert "find / -xdev" in final.CLEAN_SCRIPT
    assert "env -i PATH=/usr/bin:/bin" in final.CLEAN_SCRIPT
    assert "dpkg -r sinter" in final.CLEAN_SCRIPT
    workflow = (final.ROOT / ".github/workflows/native.yml").read_text()
    job = workflow.split("  final_rc3:", 1)[1].split("  desktop:", 1)[0]
    assert "actions: read" in job and "write" not in job
    assert "persist-credentials: false" in job
    assert "github.event.pull_request.head.repo.full_name == github.repository" in job
    assert "gh release" not in job
    assert final.COMMIT == "d9b36a6853bab0d715dc91e726f984a8ab16a747"


@pytest.mark.parametrize(
    "mutation", ["none", "changed_notice", "missing_notice", "readline"]
)
def test_rc3_terminal_dependency_requires_actual_installer_notice_bytes(
    tmp_path, mutation
):
    from tools.candidate_qualification import verify_rc3_terminal_notices

    if not shutil.which("dpkg-deb"):
        pytest.skip("Actual synthetic Debian notice test requires dpkg-deb.")
    package = tmp_path / "package"
    control = package / "DEBIAN/control"
    control.parent.mkdir(parents=True)
    control.write_text(
        "Package: sinter\nVersion: 0.5.4~rc3\nArchitecture: amd64\n"
        "Maintainer: Fictional <test@example.invalid>\n"
        "Description: Synthetic notice test\n"
    )
    name = "libreadline.so.8" if mutation == "readline" else "libtinfo.so.6"
    library = package / "opt/neuroforge/sinter/_internal" / name
    library.parent.mkdir(parents=True)
    library.write_bytes(b"fictional library, never loaded")
    licence = package / "opt/neuroforge/sinter/licenses/system/libfixture/copyright"
    licence.parent.mkdir(parents=True)
    licence.write_bytes(b"Original fictional authors and notice bytes")
    inventory = [
        {
            "name": "Debian-libfixture",
            "version": "fixture1",
            "purpose": "bundled_shared_library",
            "libraries": [
                {
                    "path": "_internal/" + name,
                    "sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
                }
            ],
            "licences": [
                {
                    "path": "system/libfixture/copyright",
                    "sha256": hashlib.sha256(licence.read_bytes()).hexdigest(),
                }
            ],
        }
    ]
    if mutation == "changed_notice":
        licence.write_bytes(b"changed after inventory creation")
    elif mutation == "missing_notice":
        licence.unlink()
    installer = tmp_path / "fictional.deb"
    subprocess.run(
        ["dpkg-deb", "--build", "--root-owner-group", str(package), str(installer)],
        check=True,
        capture_output=True,
    )
    receipt = {"installer": installer.name, "bundled_dependencies": inventory}
    if mutation == "none":
        verify_rc3_terminal_notices(tmp_path, receipt)
    else:
        with pytest.raises((RuntimeError, ValueError)):
            verify_rc3_terminal_notices(tmp_path, receipt)
