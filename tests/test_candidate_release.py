"""Scoped publication verifies exact artifacts and cannot inherit a full release pass.

The small local Git/Debian fixtures model qualification documents; they do not
claim that the fixture executable ran or that a product platform was qualified.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
import zipfile

import pytest

from tools import candidate_qualification as qualification
from tools import candidate_release as candidate
from tools import release_manifest, release_tag

VERSION = "0.5.4rc1"
PRIOR = qualification.QUALIFIED_PRIOR_COMMIT
PUBLISHED_RC2_CHECKSUM_DOCUMENT = (
    "dad6fc834090a2a0692672abcd4e9b5364444dcfb41d87869c6144b7e1081c8d"
    "  RELEASE-NOTES.md\n"
    "eaf318d142e68e942fa17f0881f52bf98bbf0cee30e4bb9fdb84b7002c56b7f0"
    "  Sinter-0.5.4rc2-linux-x64.deb\n"
    "1f787528f9df4ec97b1a469fb877a8f04d0f8087aaf65c979a0be65f656265f4"
    "  Sinter-0.5.4rc2-linux-x64.tar.gz\n"
    "5d173a7cb3a2fbba5ffb5fa390241713dcc6e9fcd3ba6bffbce7dd6031a3a31c"
    "  candidate-release-manifest.json\n"
    "ab3d3464b834276679a39ed2989509ac636e914ffa832a0b02ead4c058fa549d"
    "  sinter-0.5.4rc2-qualification.zip\n"
    "d53690e159ca4a21e9ec71a0997115bc96bec2486269807f97d8ed92a7301bfc"
    "  sinter-0.5.4rc2-source.zip\n"
    "f2d8ccdc3421ee899241eb6f48da4a136684f757dc129df8aea86de277c0b7c9"
    "  sinter-0.5.4rc2.pyz\n"
)
UPGRADE_CHECKS = [
    "prior profile and appearance preferences retained",
    "explicit legacy model selection retained with compatible provider",
    "campaign and casebook identities, revisions and original data retained",
    "saved report, source evidence and user edits retained",
    "disabled watch retained without a search request",
    "retained source-only casebook completed through installed API",
    "opening candidate did not rewrite the prior preferences file",
]
NATIVE_CHECKS = [
    "checksum-verified published v0.5.3 installer installed and launched",
    "copied fictional workspace used by actual prior native application",
    "candidate installer replaced prior package without prior uninstall",
    "candidate reopened retained data and ran source-only workflow",
    "original prior fixture file digests remain unchanged",
    "replacement candidate removed and installed executable absent",
]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def seal(folder):
    """Update fixture bookkeeping so mutations must fail substantive gates."""
    path = folder / "candidate-qualification.json"
    row = json.loads(path.read_text())
    row["artifacts"] = [
        {"path": name, "sha256": candidate.digest(path), "bytes": path.stat().st_size}
        for name, path in sorted(candidate._files(folder).items())
        if name not in {"candidate-qualification.json", "SHA256SUMS.txt"}
    ]
    write_json(path, row)
    candidate._write_checksums(folder)


@pytest.fixture
def bundle(tmp_path, request):
    version = getattr(request, "param", VERSION)
    if not shutil.which("dpkg-deb"):
        pytest.skip("Actual Debian artifact fixtures require dpkg-deb.")
    repository = tmp_path / "repo"
    repository.mkdir()
    files = {
        "src/sinter/__init__.py": f'__version__ = "{version}"\n',
        "src/sinter/cli.py": "def launch():\n    pass\n",
        "src/sinter/web/app.js": "// Fictional fixture only.\n",
        "LICENSE": "Fixture licence\n",
        "NOTICE": "Fixture notice\n",
    }
    if version in {"0.5.4rc2", "0.5.4rc3"}:
        for name in ("offline-garden-casebook.json", "offline-garden-campaign.json"):
            files["src/sinter/web/" + name] = (
                qualification.ROOT / "src/sinter/web" / name
            ).read_text()
    for name, value in files.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    for args in (
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Fixture",
            "--no-gpg-sign",
        ],
    ):
        subprocess.run(["git", *args], cwd=repository, check=True, capture_output=True)
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    folder, review, package = (
        tmp_path / name for name in ("candidate", "review", "package")
    )
    folder.mkdir()
    review.mkdir()
    runtime = package / "opt/neuroforge/sinter"
    (runtime / "_internal/sinter/web").mkdir(parents=True)
    for name, value in files.items():
        if name.startswith("src/sinter/web/"):
            (runtime / "_internal" / name.removeprefix("src/")).write_text(value)
    (runtime / "Sinter").write_bytes(b"fixture executable, never executed")
    (runtime / "Sinter").chmod(0o755)
    dependencies = []
    for name in sorted(release_manifest.AUTH_PACKAGES):
        path = f"{name}/LICENSE"
        text = f"Fixture notice for {name}".encode()
        (runtime / "licenses" / name).mkdir(parents=True)
        (runtime / "licenses" / path).write_bytes(text)
        dependencies.append(
            {
                "name": name,
                "version": "fixture-version",
                "licences": [
                    {"path": path, "sha256": hashlib.sha256(text).hexdigest()}
                ],
            }
        )
    library = runtime / "_internal/libfixture.so.1"
    library.write_bytes(b"fixture library, never loaded")
    library_sha = candidate.digest(library)
    copyright_path = runtime / "licenses/system/libfixture1/copyright"
    copyright_path.parent.mkdir(parents=True)
    copyright_path.write_text("Fixture library licence notice.\n")
    dependencies.append(
        {
            "name": "Debian-libfixture1",
            "version": "1.2-3",
            "purpose": "bundled_shared_library",
            "libraries": [{"path": "_internal/libfixture.so.1", "sha256": library_sha}],
            "licences": [
                {
                    "path": "system/libfixture1/copyright",
                    "sha256": candidate.digest(copyright_path),
                }
            ],
        }
    )
    for name, value in {
        "LICENSE": files["LICENSE"],
        "NOTICE": files["NOTICE"],
        "Python-LICENSE.txt": "Fixture Python notice.\n",
        "THIRD_PARTY_NOTICES.md": "Fixture inventory narrative.\n",
    }.items():
        (runtime / "licenses" / name).write_text(value)
    write_json(
        runtime / "licenses/bundled-dependencies.json",
        {
            "schema": "sinter-native-dependencies/v1",
            "packages": dependencies,
            "account_auth_bundled": True,
            "linux_shared_library_notices_verified": True,
        },
    )
    shutil.copytree(runtime / "licenses", folder / "licenses")
    for name in (
        "full-publisher-gate.json",
        "qualification-Dockerfile",
        "qualification-build.log",
        "qualification-image.json",
        "qualification-runner.sh",
        "qualification-runtime.json",
    ):
        (folder / name).write_text("Fictional evidence-name fixture only.\n")
    (folder / "prior-release-SHA256SUMS.txt").write_text(
        f"{qualification.QUALIFIED_PRIOR_INSTALLER_SHA}  Sinter-0.5.3-linux-x64.deb\n"
        f"{qualification.QUALIFIED_PRIOR_SOURCE_SHA}  sinter-0.5.3-source.zip\n"
    )
    write_json(
        folder / "prior-source-verification.json",
        {
            "schema": "sinter-prior-release-source/v1",
            "version": "0.5.3",
            "source_commit": PRIOR,
            "archive": "sinter-0.5.3-source.zip",
            "archive_sha256": qualification.QUALIFIED_PRIOR_SOURCE_SHA,
            "sha256sums_verified": True,
            "tracked_archive_and_local_commit_files_match": True,
        },
    )
    (package / "DEBIAN").mkdir()
    (package / "DEBIAN/control").write_text(
        f"Package: sinter\nVersion: {version.replace('rc', '~rc')}\n"
        "Architecture: amd64\n"
        "Maintainer: Fixture <fixture@example.invalid>\n"
        "Depends: libc6 (>= 2.35), zlib1g\n"
        "Description: Fictional verification fixture\n"
    )
    installer = folder / f"Sinter-{version}-linux-x64.deb"
    subprocess.run(
        ["dpkg-deb", "--build", "--root-owner-group", str(package), str(installer)],
        check=True,
        capture_output=True,
    )
    native = folder / f"Sinter-{version}-linux-x64.tar.gz"
    with tarfile.open(native, "w:gz") as archive:
        archive.add(runtime, arcname="Sinter")
    archive = folder / f"sinter-{version}-source.zip"
    archive.write_bytes(
        subprocess.check_output(
            ["git", "archive", "--format=zip", commit], cwd=repository
        )
    )
    with zipfile.ZipFile(folder / f"sinter-{version}.pyz", "w") as portable:
        for name, content in files.items():
            portable.writestr(name.removeprefix("src/"), content)
        portable.writestr(
            "__main__.py",
            "# -*- coding: utf-8 -*-\nimport sinter.cli\nsinter.cli.launch()\n",
        )
    (folder / "SOURCE-COMMIT.txt").write_text(commit + "\n")
    installed = {
        "schema": "sinter-native-test/v1",
        "version": version,
        "system": "Linux",
        "machine": "x86_64",
        "pointer_bits": 64,
        "python": "3.10.12",
        "frozen": True,
        "passed": True,
        "checks": [
            "bundled ChatGPT identity verification",
            "fixture static and workflow checks",
        ],
        "account_auth_bundled": True,
        "account_auth_dependencies": {
            name: "fixture-version" for name in release_manifest.AUTH_PACKAGES
        },
    }
    receipt = {
        **installed,
        "source_commit": commit,
        "target_arch": "x64",
        "execution": "native",
        "signed_by_publisher": False,
        "package_version": version.replace("rc", "~rc"),
        "glibc_minimum": "2.35",
        "bundled_dependencies": dependencies,
        "linux_shared_library_notices_verified": True,
        "native_shared_library_files": {"_internal/libfixture.so.1": library_sha},
        "installer": installer.name,
        "installer_sha256": candidate.digest(installer),
        "installer_test": "fixture installed evidence",
        "frozen_test": installed,
        "installed_test": installed,
    }
    write_json(folder / f"Sinter-{version}-linux-x64-test.json", receipt)
    upgrade = {
        "passed": True,
        "prior_source_commit": PRIOR,
        "candidate_source_commit": commit,
        "original_fixture_hashes": {
            name: "a" * 64
            for name in ("campaigns.sqlite3", "preferences.json", "workspace.sqlite3")
        },
    }
    write_json(
        folder / "copied-upgrade-test.json",
        {
            **upgrade,
            "schema": "sinter-copied-upgrade-test/v1",
            "prior_version": "0.5.3",
            "candidate_version": version,
            "checks": UPGRADE_CHECKS,
        },
    )
    write_json(
        folder / "native-installer-upgrade-test.json",
        {
            **upgrade,
            "schema": "sinter-native-installer-upgrade/v1",
            "prior_app_version": "0.5.3",
            "candidate_app_version": version,
            "candidate_package_version": version.replace("rc", "~rc"),
            "candidate_installer_sha256": candidate.digest(installer),
            "prior_installer_sha256": qualification.QUALIFIED_PRIOR_INSTALLER_SHA,
            "candidate_native_checks": UPGRADE_CHECKS,
            "checks": NATIVE_CHECKS,
        },
    )
    write_json(
        folder / "candidate-qualification.json",
        {
            "schema": "sinter-preview-qualification/v1",
            "version": version,
            "source_commit": commit,
            "prior_source_commit": PRIOR,
            "prior_native_installer_sha256": (
                qualification.QUALIFIED_PRIOR_INSTALLER_SHA
            ),
            "prerelease": True,
            "all_platform_release_qualified": False,
            "publisher_signed": False,
            "notarised": False,
            "unqualified_targets": candidate.UNQUALIFIED,
            "qualified_targets": [
                {
                    "system": "linux",
                    "arch": "x64",
                    "execution": "native",
                    "installed_test": True,
                    "copied_prior_release_upgrade_test": True,
                    "published_native_installer_replacement_test": True,
                    "shared_library_notices_verified": True,
                }
            ],
            "normal_package_upgrade_order_verified": True,
            "installed_runtime_and_copied_upgrade_passed": True,
            "published_native_installer_replacement_passed": True,
            "actual_debian_archive_notice_bytes_verified": True,
            "linux_shared_library_notices_verified": True,
            "runtime_baseline": {
                **{
                    key: installed[key]
                    for key in ("system", "machine", "pointer_bits", "python")
                },
                "libc": ["glibc", "2.35"],
                "os_release": 'VERSION_ID="22.04"\n',
                "network": "disabled container; loopback only",
                "host_installation": False,
            },
        },
    )
    if version in {"0.5.4rc2", "0.5.4rc3"}:
        for prior in qualification.candidate_priors(version):
            source_name, sums_name, copied_name, native_name = (
                qualification.prior_roles(prior)
            )
            write_json(
                folder / source_name,
                {
                    "schema": "sinter-prior-release-source/v1",
                    "version": prior.version,
                    "source_commit": prior.source_commit,
                    "archive": f"sinter-{prior.version}-source.zip",
                    "archive_sha256": prior.source_archive_sha256,
                    "sha256sums_verified": True,
                    "tracked_archive_and_local_commit_files_match": True,
                },
            )
            (folder / sums_name).write_text(
                f"{prior.installer_sha256}  Sinter-{prior.version}-linux-x64.deb\n"
                f"{prior.source_archive_sha256}  sinter-{prior.version}-source.zip\n"
            )
            if prior.version == "0.5.4rc2":
                (folder / sums_name).write_bytes(
                    PUBLISHED_RC2_CHECKSUM_DOCUMENT.encode()
                )
            base = {
                **upgrade,
                "prior_source_commit": prior.source_commit,
                "prior_source_archive_sha256": prior.source_archive_sha256,
                "candidate_binary_sha256": candidate.digest(runtime / "Sinter"),
            }
            rich = (
                [
                    "rich prior source snapshots, stale marked review "
                    "and unknown/unassigned owners retained"
                ]
                if prior.version == "0.5.4rc2"
                else []
            )
            write_json(
                folder / copied_name,
                {
                    **base,
                    "schema": "sinter-copied-upgrade-test/v1",
                    "prior_version": prior.version,
                    "candidate_version": version,
                    "checks": [
                        *UPGRADE_CHECKS,
                        "untouched prior workspace retains every original file digest",
                        *rich,
                    ],
                    **(
                        {
                            "fixture_notice": (
                                "Fictional workspace only. No live model access "
                                "or real account proof."
                            )
                        }
                        if prior.version == "0.5.4rc2"
                        else {}
                    ),
                },
            )
            native_checks = [*NATIVE_CHECKS]
            native_checks[0] = (
                f"checksum-verified published v{prior.version} installer "
                "installed and launched"
            )
            write_json(
                folder / native_name,
                {
                    **base,
                    "schema": "sinter-native-installer-upgrade/v1",
                    "prior_app_version": prior.version,
                    "prior_package_version": prior.version.replace("rc", "~rc"),
                    "candidate_app_version": version,
                    "candidate_package_version": version.replace("rc", "~rc"),
                    "candidate_installer_sha256": candidate.digest(installer),
                    "prior_installer_sha256": prior.installer_sha256,
                    "candidate_native_checks": [*UPGRADE_CHECKS, *rich],
                    "checks": native_checks,
                    **(
                        {
                            "fixture_notice": (
                                "Fictional source-created workspace; actual native "
                                "package replacement."
                            ),
                            "prior_native_checks": [
                                check.replace(
                                    " with compatible provider", " by prior application"
                                )
                                for check in [*UPGRADE_CHECKS, *rich]
                            ],
                        }
                        if prior.version == "0.5.4rc2"
                        else {}
                    ),
                },
            )
    seal(folder)
    checks = {
        name: True
        for name in (
            "source_commit_matches_with_declared_windows_CRLF",
            "portable_source_bytes_match",
            "packaged_static_source_bytes_match",
            "actual_debian_notice_and_referenced_text_gate",
            "readline_and_tinfo_excluded",
            "frozen_and_installed_receipts_match",
            "github_prior_asset_digest_independently_matches",
            "original_copied_and_replacement_fixture_hashes_match",
            "prior_database_rows_and_preferences_preserved",
            "nine_target_publisher_refuses_linux_only",
            "clean_offline_Ubuntu22_install_self_test_remove",
        )
    }
    write_json(
        review / "final-artifact-review.json",
        {
            "schema": "sinter-independent-final-artifact-review/v1",
            "version": version,
            "source_commit": commit,
            "checks": checks,
            "installer_sha256": candidate.digest(installer),
            "native_archive_sha256": candidate.digest(native),
            "source_archive_sha256": candidate.digest(archive),
            "portable_sha256": candidate.digest(folder / f"sinter-{version}.pyz"),
        },
    )
    write_json(review / "clean-ubuntu-installed-test.json", installed)
    write_json(
        review / "qualification-context.json",
        {
            "source_commit": commit,
            "version": version,
            "installer_sha256": candidate.digest(installer),
            "container": "ubuntu:22.04",
            "network": "disabled",
            "host_installation": False,
            "product_edits": False,
            "preinstalled_python": False,
            "preinstalled_account_packages": False,
        },
    )
    (review / "clean-ubuntu-installed-test.log").write_text(
        "Fixture log, no actual installation claim.\n"
    )
    return folder, review, repository, commit


def test_scoped_stage_keeps_canonical_bundle_immutable_and_full_gate_closed(
    bundle, tmp_path, monkeypatch
):
    folder, review, repository, commit = bundle
    before = {
        name: candidate.digest(path) for name, path in candidate._files(folder).items()
    }
    manifest = candidate.prepare(
        folder, review, tmp_path / "stage", VERSION, commit, repository
    )
    plan = candidate.verify_plan(manifest, repository)
    assert plan["prerelease"] is True and plan["latest"] is False
    assert plan["qualified_targets"] == ["linux-x64"]
    assert plan["unqualified_targets"] == candidate.UNQUALIFIED
    assert plan["publication_executed"] is False
    assert before == {
        name: candidate.digest(path) for name, path in candidate._files(folder).items()
    }
    with pytest.raises(ValueError, match="required architecture"):
        release_manifest.assemble(folder, repository, commit)
    monkeypatch.setattr(candidate, "ROOT", repository)
    monkeypatch.setattr(candidate, "verify_plan", lambda path: plan)
    commands = candidate.publication_commands(manifest)
    assert (
        "--candidate-manifest" in commands and "--prerelease --latest=false" in commands
    )
    assert "--verify-tag" in commands and "upload" not in commands


@pytest.mark.parametrize(
    "filename,field,value",
    [
        ("candidate-qualification.json", "prerelease", False),
        ("candidate-qualification.json", "all_platform_release_qualified", True),
        ("candidate-qualification.json", "source_commit", "d" * 40),
        ("candidate-qualification.json", "unqualified_targets", []),
        (
            "candidate-qualification.json",
            "published_native_installer_replacement_passed",
            1,
        ),
        ("candidate-qualification.json", "publisher_signed", True),
        ("copied-upgrade-test.json", "checks", ["save succeeded"]),
        (
            "copied-upgrade-test.json",
            "original_fixture_hashes",
            {"workspace.sqlite3": "a" * 64},
        ),
        ("native-installer-upgrade-test.json", "candidate_installer_sha256", "d" * 64),
        ("native-installer-upgrade-test.json", "checks", ["new install succeeded"]),
        (
            "native-installer-upgrade-test.json",
            "candidate_native_checks",
            ["save succeeded"],
        ),
    ],
)
def test_resealed_receipt_forgery_cannot_admit_candidate(
    bundle, filename, field, value
):
    folder, review, repository, commit = bundle
    path = folder / filename
    row = json.loads(path.read_text())
    row[field] = value
    write_json(path, row)
    seal(folder)
    with pytest.raises(ValueError):
        candidate.verify_candidate(folder, review, VERSION, commit, repository)


@pytest.mark.parametrize(
    "mutation",
    [
        "questionable_baseline",
        "extra_target",
        "integer_target_flag",
        "changed_source",
        "changed_pyz",
        "extra_tar_member",
        "missing_notice",
        "unmatched_upgrade_source",
    ],
)
def test_exact_source_payload_notices_and_scope_are_required(bundle, mutation):
    folder, review, repository, commit = bundle
    qualification_path = folder / "candidate-qualification.json"
    row = json.loads(qualification_path.read_text())
    if mutation == "questionable_baseline":
        row["runtime_baseline"]["libc"] = ["glibc", "2.41"]
    elif mutation == "extra_target":
        row["qualified_targets"].append({"system": "windows", "arch": "x64"})
    elif mutation == "integer_target_flag":
        row["qualified_targets"][0]["installed_test"] = 1
    elif mutation in {"changed_source", "changed_pyz"}:
        name = (
            f"sinter-{VERSION}-source.zip"
            if mutation == "changed_source"
            else f"sinter-{VERSION}.pyz"
        )
        with zipfile.ZipFile(folder / name, "a") as archive:
            archive.writestr("additional-unqualified.py", "print('forged')")
    elif mutation == "extra_tar_member":
        path = folder / f"Sinter-{VERSION}-linux-x64.tar.gz"
        with tarfile.open(path) as archive:
            original = [
                (
                    member,
                    archive.extractfile(member).read() if member.isfile() else None,
                )
                for member in archive
            ]
        import io

        with tarfile.open(path, "w:gz") as archive:
            for member, content in original:
                archive.addfile(
                    member, io.BytesIO(content) if content is not None else None
                )
            extra = tarfile.TarInfo("unqualified-other-app")
            extra.size = 6
            archive.addfile(extra, io.BytesIO(b"forged"))
    elif mutation == "missing_notice":
        path = folder / f"Sinter-{VERSION}-linux-x64-test.json"
        receipt = json.loads(path.read_text())
        receipt["bundled_dependencies"][-1]["licences"] = []
        write_json(path, receipt)
    else:
        path = folder / "native-installer-upgrade-test.json"
        upgrade = json.loads(path.read_text())
        upgrade["prior_source_commit"] = "f" * 40
        write_json(path, upgrade)
    write_json(qualification_path, row)
    seal(folder)
    with pytest.raises(ValueError):
        candidate.verify_candidate(folder, review, VERSION, commit, repository)


@pytest.mark.parametrize(
    "mutation",
    [
        "another_asset",
        "failed_clean_install",
        "online",
        "different_installed",
        "missing_clean_log",
    ],
)
def test_independent_installed_evidence_must_match_exact_assets_and_scope(
    bundle, mutation
):
    folder, review, repository, commit = bundle
    path = review / "final-artifact-review.json"
    row = json.loads(path.read_text())
    if mutation == "another_asset":
        row["installer_sha256"] = "f" * 64
    elif mutation == "failed_clean_install":
        row["checks"]["clean_offline_Ubuntu22_install_self_test_remove"] = False
    elif mutation == "online":
        path = review / "qualification-context.json"
        row = json.loads(path.read_text())
        row["network"] = "enabled"
    elif mutation == "different_installed":
        path = review / "clean-ubuntu-installed-test.json"
        row = json.loads(path.read_text())
        row["checks"] = ["some other runtime"]
    else:
        (review / "clean-ubuntu-installed-test.log").unlink()
    if mutation != "missing_clean_log":
        write_json(path, row)
    with pytest.raises((ValueError, OSError)):
        candidate.prepare(
            folder, review, folder.parent / "stage", VERSION, commit, repository
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "latest",
        "stable",
        "no_approval",
        "extra_public_platform",
        "changed_public_source",
        "false_notes",
    ],
)
def test_resealed_publication_plan_rejects_promotion_extra_assets_and_changed_downloads(
    bundle, tmp_path, mutation
):
    folder, review, repository, commit = bundle
    manifest = candidate.prepare(
        folder, review, tmp_path / "stage", VERSION, commit, repository
    )
    plan = json.loads(manifest.read_text())
    if mutation == "latest":
        plan["latest"] = True
    elif mutation == "stable":
        plan["prerelease"] = False
    elif mutation == "no_approval":
        plan["human_approval_required"] = False
    elif mutation == "false_notes":
        path = manifest.parent / "RELEASE-NOTES.md"
        path.write_text("All Windows and macOS targets passed; this is stable.\n")
        for row in plan["assets"]:
            if row["path"] == path.name:
                row.update(sha256=candidate.digest(path), bytes=path.stat().st_size)
    else:
        path = manifest.parent / (
            "Sinter-0.5.4rc1-windows-x64.exe"
            if mutation == "extra_public_platform"
            else f"sinter-{VERSION}-source.zip"
        )
        path.write_bytes(b"unqualified")
        plan["assets"] = [row for row in plan["assets"] if row["path"] != path.name]
        plan["assets"].append(
            {
                "path": path.name,
                "sha256": candidate.digest(path),
                "bytes": path.stat().st_size,
            }
        )
    write_json(manifest, plan)
    candidate._write_checksums(manifest.parent)
    with pytest.raises(ValueError):
        candidate.verify_plan(manifest, repository)


def test_canonical_directory_is_never_overwritten_or_used_as_stage(bundle):
    folder, review, repository, commit = bundle
    original = (folder / "SOURCE-COMMIT.txt").read_bytes()
    for output in (folder, folder / "nested-stage", review / "nested-stage"):
        with pytest.raises(ValueError, match="never overwritten"):
            candidate.prepare(folder, review, output, VERSION, commit, repository)
    assert (folder / "SOURCE-COMMIT.txt").read_bytes() == original


def test_newer_working_tree_version_never_changes_frozen_candidate_identity(bundle):
    folder, review, repository, commit = bundle
    (repository / "src/sinter/__init__.py").write_text(
        '__version__ = "0.5.4rc2.dev0"\n'
    )
    result = candidate.verify_candidate(folder, review, VERSION, commit, repository)
    assert result["native_target"] == "linux-x64"


def test_published_rc1_notes_remain_byte_identical():
    notes = candidate.release_notes(
        "0.5.4rc1", "cd928ba7561a09c477b3555e64aa6a3c4cc122b4"
    )
    assert hashlib.sha256(notes.encode()).hexdigest() == (
        "163b5afd0b2f777022f44e453660a678fe68d3bcbc2cc35f34f2fcfa4dc95708"
    )


def test_rc1_cannot_admit_new_candidate_roles(bundle):
    folder, review, repository, commit = bundle
    write_json(folder / "installed-workflow-browser.json", {"passed": True})
    seal(folder)
    with pytest.raises(ValueError, match="unexpected artifact roles"):
        candidate.verify_candidate(folder, review, VERSION, commit, repository)


@pytest.mark.parametrize(
    "extra",
    [
        "Sinter-0.5.4rc1-windows-x64.exe",
        "licenses/unqualified.exe",
        "extra/unqualified.exe",
    ],
)
def test_resealed_canonical_inventory_cannot_smuggle_nested_unqualified_assets(
    bundle, tmp_path, extra
):
    folder, review, repository, commit = bundle
    path = folder / extra
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ unqualified executable")
    seal(folder)
    with pytest.raises(ValueError, match="unexpected artifact roles"):
        candidate.prepare(
            folder, review, tmp_path / "stage", VERSION, commit, repository
        )
    assert not (tmp_path / "stage").exists()


@pytest.mark.parametrize(
    "mutation", ["unsafe_directory", "directory_mode", "duplicate_directory"]
)
def test_resealed_native_tar_checks_directory_paths_permissions_and_duplicates(
    bundle, mutation
):
    import io

    folder, review, repository, commit = bundle
    path = folder / f"Sinter-{VERSION}-linux-x64.tar.gz"
    with tarfile.open(path) as archive:
        original = [
            (member, archive.extractfile(member).read() if member.isfile() else None)
            for member in archive
        ]
    with tarfile.open(path, "w:gz") as archive:
        for member, content in original:
            if mutation == "directory_mode" and member.name == "Sinter/_internal":
                member.mode = 0
            archive.addfile(
                member, io.BytesIO(content) if content is not None else None
            )
        if mutation != "directory_mode":
            bad = tarfile.TarInfo(
                "Sinter/../../outside"
                if mutation == "unsafe_directory"
                else "Sinter/_internal"
            )
            bad.type = tarfile.DIRTYPE
            archive.addfile(bad)
    seal(folder)
    independent_path = review / "final-artifact-review.json"
    independent = json.loads(independent_path.read_text())
    independent["native_archive_sha256"] = candidate.digest(path)
    write_json(independent_path, independent)
    with pytest.raises(ValueError, match="unsafe|duplicate|differs"):
        candidate.verify_candidate(folder, review, VERSION, commit, repository)


@pytest.mark.parametrize(
    "mutation",
    [
        "matched_fake_upgrade",
        "fake_all_prior_documents",
        "wrong_prior_version",
        "changed_preserved_checksums",
        "changed_preserved_source",
    ],
)
def test_prior_upgrade_identity_is_bound_to_preserved_and_explicitly_qualified_release(
    bundle, mutation
):
    folder, review, repository, commit = bundle
    if mutation in {"matched_fake_upgrade", "fake_all_prior_documents"}:
        path = folder / "candidate-qualification.json"
        row = json.loads(path.read_text())
        row.update(prior_source_commit="e" * 40, prior_native_installer_sha256="f" * 64)
        write_json(path, row)
        for name in ("copied-upgrade-test.json", "native-installer-upgrade-test.json"):
            path = folder / name
            row = json.loads(path.read_text())
            row["prior_source_commit"] = "e" * 40
            if name.startswith("native-"):
                row.update(prior_installer_sha256="f" * 64, prior_app_version="9.9.9")
            else:
                row["prior_version"] = "9.9.9"
            write_json(path, row)
    if mutation in {"fake_all_prior_documents", "changed_preserved_source"}:
        path = folder / "prior-source-verification.json"
        row = json.loads(path.read_text())
        row.update(version="9.9.9", source_commit="e" * 40, archive_sha256="f" * 64)
        write_json(path, row)
    if mutation in {"fake_all_prior_documents", "changed_preserved_checksums"}:
        (folder / "prior-release-SHA256SUMS.txt").write_text(
            f"{'f' * 64}  Sinter-0.5.3-linux-x64.deb\n"
            f"{'f' * 64}  sinter-0.5.3-source.zip\n"
        )
    if mutation == "wrong_prior_version":
        path = folder / "native-installer-upgrade-test.json"
        row = json.loads(path.read_text())
        row["prior_app_version"] = "9.9.9"
        write_json(path, row)
    seal(folder)
    with pytest.raises(ValueError, match="prior|upgrade"):
        candidate.verify_candidate(folder, review, VERSION, commit, repository)


def test_rc_tag_requires_fully_verified_matching_plan_before_github(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setattr(release_tag, "_api", lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="verified scoped"):
        release_tag.ensure_release_tag(candidate.REPOSITORY, "v0.5.4rc1", "a" * 40)
    monkeypatch.setattr(
        candidate,
        "verify_plan",
        lambda path: {
            "repository": candidate.REPOSITORY,
            "tag": "v0.5.4rc1",
            "source_commit": "b" * 40,
        },
    )
    with pytest.raises(ValueError, match="another release identity"):
        release_tag.ensure_release_tag(
            candidate.REPOSITORY, "v0.5.4rc1", "a" * 40, tmp_path / "manifest.json"
        )
    assert calls == []


def test_verified_rc_tag_uses_create_only_identity_bound_path(monkeypatch, tmp_path):
    commit, tag = "a" * 40, "v0.5.4rc1"
    monkeypatch.setattr(
        candidate,
        "verify_plan",
        lambda path: {
            "repository": candidate.REPOSITORY,
            "tag": tag,
            "source_commit": commit,
        },
    )
    calls = []

    def api(repository, method, endpoint, payload=None):
        calls.append(method)
        if method == "GET":
            return 404, {"message": "Not Found"}
        assert method == "POST" and payload == {
            "ref": f"refs/tags/{tag}",
            "sha": commit,
        }
        return 201, {
            "ref": f"refs/tags/{tag}",
            "object": {"type": "commit", "sha": commit},
        }

    monkeypatch.setattr(release_tag, "_api", api)
    release_tag.ensure_release_tag(
        candidate.REPOSITORY, tag, commit, tmp_path / "manifest.json"
    )
    assert calls == ["GET", "POST"]


def test_scoped_plan_cannot_authorise_stable_tag(monkeypatch, tmp_path):
    monkeypatch.setattr(
        release_tag, "_api", lambda *args: pytest.fail("Stable tag reached GitHub")
    )
    with pytest.raises(ValueError, match="stable release tag"):
        release_tag.ensure_release_tag(
            candidate.REPOSITORY, "v0.5.3", "a" * 40, tmp_path / "manifest.json"
        )


@pytest.mark.parametrize(
    "kind", [0o120000, 0o010000, 0o020000, 0o040000, 0o060000, 0o140000]
)
def test_resealed_qualification_zip_refuses_nonregular_member_types(
    bundle, tmp_path, kind
):
    folder, review, repository, commit = bundle
    manifest = candidate.prepare(
        folder, review, tmp_path / "stage", VERSION, commit, repository
    )
    archive_path = manifest.parent / f"sinter-{VERSION}-qualification.zip"
    with zipfile.ZipFile(archive_path) as archive:
        members = [(item, archive.read(item)) for item in archive.infolist()]
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for item, data in members:
            if item.filename == "canonical/prior-source-verification.json":
                item.create_system = 3
                item.external_attr = (kind | 0o600) << 16
            archive.writestr(item, data)
    plan = json.loads(manifest.read_text())
    for row in plan["assets"]:
        if row["path"] == archive_path.name:
            row.update(
                sha256=candidate.digest(archive_path), bytes=archive_path.stat().st_size
            )
    write_json(manifest, plan)
    candidate._write_checksums(manifest.parent)
    with pytest.raises(ValueError, match="entry types"):
        candidate.verify_plan(manifest, repository)
