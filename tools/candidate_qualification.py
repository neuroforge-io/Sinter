"""Verify immutable candidate artifacts and installed-platform qualification."""

from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from tools.qualified_priors import (  # noqa: E402
    QUALIFIED_CHECKSUM_DOCUMENTS,
    QUALIFIED_PRIORS,
    PriorRelease,
)
from tools.release_manifest import EXPECTED, verify_target_receipt  # noqa: E402

SCHEMA = "sinter-scoped-candidate-release/v1"
REPOSITORY = "neuroforge-io/Sinter"
TARGET = "linux-x64"
UNQUALIFIED = sorted(
    f"{system}-{arch}" for system, arch in EXPECTED - {("linux", "x64")}
)
MAX_FILE = 64 * 1024 * 1024
MAX_BUNDLE = 256 * 1024 * 1024
REVIEW_FILES = (
    "final-artifact-review.json",
    "clean-ubuntu-installed-test.json",
    "qualification-context.json",
    "clean-ubuntu-installed-test.log",
)
QUALIFIED_PRIOR_VERSION = "0.5.3"
QUALIFIED_PRIOR_COMMIT = "07bf7df8f233b555218b7957060968c7cdb29d99"
QUALIFIED_PRIOR_INSTALLER_SHA = (
    "ae2d72ea31237b2297946a8ae43fe904848acd0f0b47b88c6c56791f5ed13d62"
)
QUALIFIED_PRIOR_SOURCE_SHA = (
    "ec4abbc0ed4e121c50a5d383296c4b84d4a2a2b2ea981688e1c80c29333f8f6d"
)
CANDIDATE_PRIORS = MappingProxyType(
    {
        "0.5.4rc1": (QUALIFIED_PRIORS["0.5.3"],),
        "0.5.4rc2": (QUALIFIED_PRIORS["0.5.3"], QUALIFIED_PRIORS["0.5.4rc1"]),
        "0.5.4rc3": (
            QUALIFIED_PRIORS["0.5.3"],
            QUALIFIED_PRIORS["0.5.4rc1"],
            QUALIFIED_PRIORS["0.5.4rc2"],
        ),
    }
)


def candidate_priors(version: str) -> tuple[PriorRelease, ...]:
    """Select reviewed requirements from policy, never from supplied receipts."""
    if version not in CANDIDATE_PRIORS:
        raise ValueError("This candidate version has no explicit qualification policy.")
    return CANDIDATE_PRIORS[version]


def prior_roles(prior: PriorRelease) -> tuple[str, str, str, str]:
    """Name the closed source/checksum/copied/native roles for a pinned prior."""
    if QUALIFIED_PRIORS.get(prior.version) != prior:
        raise ValueError("Upgrade roles require an exact qualified prior identity.")
    if prior.version == "0.5.3":
        return (
            "prior-source-verification.json",
            "prior-release-SHA256SUMS.txt",
            "copied-upgrade-test.json",
            "native-installer-upgrade-test.json",
        )
    if prior.version in {"0.5.4rc1", "0.5.4rc2"}:
        prefix = "published-" + prior.version.removeprefix("0.5.4")
        return (
            prefix + "-source-verification.json",
            prefix + "-SHA256SUMS.txt",
            prefix + "-copied-upgrade-test.json",
            prefix + "-native-installer-upgrade-test.json",
        )
    raise ValueError("Upgrade roles require an exact qualified prior identity.")


def digest(path: Path) -> str:
    """Hash an artifact without loading the complete file into memory."""
    with path.open("rb") as source:
        return (
            hashlib.file_digest(source, "sha256").hexdigest()
            if hasattr(hashlib, "file_digest")
            else _stream_digest(source)
        )


def _stream_digest(source) -> str:
    result = hashlib.sha256()
    while chunk := source.read(1024 * 1024):
        result.update(chunk)
    return result.hexdigest()


def _safe_name(name: str) -> str:
    parts = PurePosixPath(name).parts
    if (
        not name
        or "\\" in name
        or ":" in name
        or "\x00" in name
        or PurePosixPath(name).is_absolute()
        or ".." in parts
        or PurePosixPath(name).as_posix() != name
    ):
        raise ValueError("An artifact has an unsafe or noncanonical path.")
    return name


def _json(path: Path) -> dict:
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("An evidence document exceeds its bound.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("An evidence document is not an object.")
    return value


def _files(folder: Path) -> dict[str, Path]:
    result = {}
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise ValueError("Artifact directories must not contain symlinks.")
        if path.is_file():
            result[_safe_name(path.relative_to(folder).as_posix())] = path
    return result


def _checksum_entries(path: Path) -> dict[str, str]:
    declared = {}
    for line in path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match or match[2] in declared:
            raise ValueError("Checksums are invalid or duplicated.")
        declared[_safe_name(match[2])] = match[1]
    return declared


def _checksums(folder: Path) -> dict[str, str]:
    declared = _checksum_entries(folder / "SHA256SUMS.txt")
    actual = _files(folder)
    actual.pop("SHA256SUMS.txt", None)
    if set(declared) != set(actual):
        raise ValueError("Checksums do not cover the exact artifact directory.")
    if any(digest(actual[name]) != sha for name, sha in declared.items()):
        raise ValueError("An artifact does not match its checksum.")
    return declared


def _identity(version: str, commit: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+rc[1-9]\d*", version):
        raise ValueError("Scoped candidates require an explicit rc version.")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Use the full lowercase candidate source commit.")
    candidate_priors(version)


def _source(folder: Path, version: str, commit: str, repository: Path) -> dict:
    archive = folder / f"sinter-{version}-source.zip"
    expected = subprocess.run(
        ["git", "archive", "--format=zip", commit],
        cwd=repository,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    if len(expected) > MAX_BUNDLE or hashlib.sha256(expected).hexdigest() != digest(
        archive
    ):
        raise ValueError("The source ZIP is not the exact pinned Git archive.")
    with zipfile.ZipFile(io.BytesIO(expected)) as source:
        files = {
            row.filename: source.read(row)
            for row in source.infolist()
            if not row.is_dir()
        }
    match = re.search(
        rb'__version__\s*=\s*["\']([^"\']+)["\']', files["src/sinter/__init__.py"]
    )
    if not match or match[1].decode("ascii") != version:
        raise ValueError("The pinned source declares another app version.")
    with zipfile.ZipFile(folder / f"sinter-{version}.pyz") as portable:
        names = [row.filename for row in portable.infolist() if not row.is_dir()]
        expected_names = {
            name.removeprefix("src/")
            for name in files
            if name.startswith("src/sinter/")
        }
        expected_names |= {"LICENSE", "NOTICE", "__main__.py"}
        if len(names) != len(set(names)) or set(names) != expected_names:
            raise ValueError("The portable app contains missing or unexpected files.")
        for name in expected_names - {"__main__.py"}:
            original = "src/" + name if name.startswith("sinter/") else name
            if portable.read(name) != files[original]:
                raise ValueError("The portable app does not match the pinned source.")
        if portable.read("__main__.py") != (
            b"# -*- coding: utf-8 -*-\nimport sinter.cli\nsinter.cli.launch()\n"
        ):
            raise ValueError("The portable entry point differs from the qualified app.")
    return files


def _runtime_members(
    archive: tarfile.TarFile, prefix: str, *, strict_root: bool = False
) -> dict:
    result, total = {}, 0
    for member in archive:
        name = member.name.removeprefix("./").rstrip("/")
        root = prefix.rstrip("/")
        if strict_root and name != root and not name.startswith(prefix):
            raise ValueError("The native archive contains a path outside its runtime.")
        if name != root and not name.startswith(prefix):
            continue
        relative = "." if name == root else _safe_name(name.removeprefix(prefix))
        if relative in result:
            raise ValueError("The native runtime contains duplicate paths.")
        if member.isdir():
            value, kind = "", "directory"
        elif member.isfile():
            total += member.size
            if member.size > MAX_FILE or total > MAX_BUNDLE:
                raise ValueError("The native runtime exceeds its archive bounds.")
            value = _stream_digest(archive.extractfile(member))
            kind = "file"
        elif member.issym():
            value, kind = _safe_name(member.linkname), "symlink"
        else:
            raise ValueError("The native runtime contains unsupported archive members.")
        result[relative] = (kind, value, member.mode & 0o7777)
    return result


def _native_payload(folder: Path, version: str, files: dict, receipt: dict) -> str:
    installer = folder / receipt["installer"]
    fields = subprocess.run(
        [
            "dpkg-deb",
            "--field",
            str(installer),
            "Package",
            "Version",
            "Architecture",
            "Depends",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.splitlines()
    debian_version = version.replace("rc", "~rc")
    if (
        fields
        != [
            "Package: sinter",
            f"Version: {debian_version}",
            "Architecture: amd64",
            "Depends: libc6 (>= 2.35), zlib1g",
        ]
        or receipt.get("package_version") != debian_version
        or receipt.get("glibc_minimum") != "2.35"
    ):
        raise ValueError("The actual Debian package identity or baseline differs.")
    payload = subprocess.run(
        ["dpkg-deb", "--fsys-tarfile", str(installer)],
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    if len(payload) > MAX_BUNDLE:
        raise ValueError("The Debian payload exceeds its bound.")
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        debian = _runtime_members(archive, "opt/neuroforge/sinter/")
    with tarfile.open(folder / f"Sinter-{version}-linux-x64.tar.gz") as archive:
        portable = _runtime_members(archive, "Sinter/", strict_root=True)
    if not debian or debian != portable:
        raise ValueError(
            "The native archive differs from the installed Debian runtime."
        )
    for name, content in files.items():
        if name.startswith("src/sinter/web/"):
            relative = "_internal/" + name.removeprefix("src/")
            if debian.get(relative, ())[:2] != (
                "file",
                hashlib.sha256(content).hexdigest(),
            ):
                raise ValueError("A packaged web asset differs from the pinned source.")
    for name, path in _files(folder).items():
        if name.startswith("licenses/") and debian.get(name, ())[:2] != (
            "file",
            digest(path),
        ):
            raise ValueError("An exported notice differs from the actual installer.")
    executable = debian.get("Sinter", ())
    if len(executable) != 3 or executable[0] != "file" or not executable[2] & 0o111:
        raise ValueError("The native package has no executable Sinter binary.")
    return executable[1]


def _canonical_roles(folder: Path, version: str, receipt: dict) -> None:
    """Admit only the tested product and named evidence, including nested notices."""
    expected = {
        "SHA256SUMS.txt",
        "SOURCE-COMMIT.txt",
        "candidate-qualification.json",
        f"Sinter-{version}-linux-x64-test.json",
        f"Sinter-{version}-linux-x64.deb",
        f"Sinter-{version}-linux-x64.tar.gz",
        f"sinter-{version}-source.zip",
        f"sinter-{version}.pyz",
        "copied-upgrade-test.json",
        "full-publisher-gate.json",
        "native-installer-upgrade-test.json",
        "prior-release-SHA256SUMS.txt",
        "prior-source-verification.json",
        "qualification-Dockerfile",
        "qualification-build.log",
        "qualification-image.json",
        "qualification-runner.sh",
        "qualification-runtime.json",
        "licenses/LICENSE",
        "licenses/NOTICE",
        "licenses/Python-LICENSE.txt",
        "licenses/THIRD_PARTY_NOTICES.md",
        "licenses/bundled-dependencies.json",
    }
    for dependency in receipt["bundled_dependencies"]:
        for notice in dependency.get("licences", []):
            expected.add("licenses/" + _safe_name(notice["path"]))
    if version in {"0.5.4rc2", "0.5.4rc3"}:
        from tools.installed_workflow_contract import ARTIFACT_PATHS

        expected.update(prior_roles(QUALIFIED_PRIORS["0.5.4rc1"]))
        expected.add("installed-workflow-browser.json")
        expected.update(ARTIFACT_PATHS.values())
    if version == "0.5.4rc3":
        from tools.installed_recovery_contract import (
            ARTIFACT_PATHS as RECOVERY_PATHS,
        )
        from tools.installed_recovery_contract import (
            RECEIPT_PATH,
        )

        expected.update(prior_roles(QUALIFIED_PRIORS["0.5.4rc2"]))
        expected.add(RECEIPT_PATH)
        expected.update(RECOVERY_PATHS.values())
    if set(_files(folder)) != expected:
        raise ValueError(
            "The canonical bundle contains missing or unexpected artifact roles."
        )
    inventory = _json(folder / "licenses/bundled-dependencies.json")
    if (
        inventory.get("schema") != "sinter-native-dependencies/v1"
        or inventory.get("packages") != receipt["bundled_dependencies"]
        or inventory.get("account_auth_bundled") is not True
        or inventory.get("linux_shared_library_notices_verified") is not True
    ):
        raise ValueError(
            "The exported notice inventory differs from the installed evidence."
        )


def _prior_identity(folder: Path, qualification: dict) -> str:
    """Bind upgrade proof to the independently reviewed published prior release."""
    if (
        qualification.get("prior_source_commit") != QUALIFIED_PRIOR_COMMIT
        or qualification.get("prior_native_installer_sha256")
        != QUALIFIED_PRIOR_INSTALLER_SHA
    ):
        raise ValueError(
            "The prior release differs from the explicitly qualified upgrade pin."
        )
    _prior_source_records(folder, QUALIFIED_PRIORS["0.5.3"])
    return QUALIFIED_PRIOR_COMMIT


def _prior_source_records(folder: Path, prior: PriorRelease) -> None:
    source_name, checksum_name, _, _ = prior_roles(prior)
    source = _json(folder / source_name)
    if prior.version == "0.5.4rc2":
        from tools.installed_workflow_qualification import json_object

        # This new role has no arbitrary attachments or duplicated JSON fields.
        # The optional count is the file count in the checksum-pinned public ZIP.
        source = json_object((folder / source_name).read_bytes())
        fields = {
            "schema",
            "version",
            "source_commit",
            "archive",
            "archive_sha256",
            "sha256sums_verified",
            "tracked_archive_and_local_commit_files_match",
        }
        if set(source) not in (fields, fields | {"source_files"}) or (
            "source_files" in source
            and (
                type(source["source_files"]) is not int or source["source_files"] != 251
            )
        ):
            raise ValueError("The published RC2 source verification has unknown data.")
    if (
        source.get("schema") != "sinter-prior-release-source/v1"
        or source.get("version") != prior.version
        or source.get("source_commit") != prior.source_commit
        or source.get("archive") != f"sinter-{prior.version}-source.zip"
        or source.get("archive_sha256") != prior.source_archive_sha256
        or source.get("sha256sums_verified") is not True
        or source.get("tracked_archive_and_local_commit_files_match") is not True
    ):
        raise ValueError(
            "Preserved prior source verification does not match the qualified release."
        )
    if (
        prior.version == "0.5.4rc2"
        and digest(folder / checksum_name)
        != (QUALIFIED_CHECKSUM_DOCUMENTS[prior.version])
    ):
        raise ValueError(
            "The published RC2 checksum document differs from reviewed bytes."
        )
    checksums = _checksum_entries(folder / checksum_name)
    if (
        checksums.get(f"Sinter-{prior.version}-linux-x64.deb") != prior.installer_sha256
        or checksums.get(f"sinter-{prior.version}-source.zip")
        != prior.source_archive_sha256
    ):
        raise ValueError(
            "Preserved prior checksums do not identify the reviewed "
            "source and installer."
        )


def _has_checks(value: object, required: set[str]) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and required <= set(value)
    )


def _upgrade_records(
    folder: Path,
    prior: PriorRelease,
    version: str,
    commit: str,
    receipt: dict,
    binary_sha256: str,
) -> None:
    """Bind each independent copied/native run to its exact published prior."""
    _, _, copied_name, native_name = prior_roles(prior)
    for filename, native in ((copied_name, False), (native_name, True)):
        upgrade = _json(folder / filename)
        closed_rc2 = version == "0.5.4rc3" and prior.version == "0.5.4rc2"
        if closed_rc2:
            from tools.installed_workflow_qualification import json_object

            upgrade = json_object((folder / filename).read_bytes())
            fields = {
                "schema",
                "passed",
                "fixture_notice",
                "prior_source_commit",
                "prior_source_archive_sha256",
                "candidate_source_commit",
                "candidate_binary_sha256",
                "original_fixture_hashes",
                "checks",
            }
            fields |= (
                {
                    "prior_app_version",
                    "prior_package_version",
                    "prior_installer_sha256",
                    "candidate_app_version",
                    "candidate_package_version",
                    "candidate_installer_sha256",
                    "prior_native_checks",
                    "candidate_native_checks",
                }
                if native
                else {"prior_version", "candidate_version"}
            )
            notice = (
                "Fictional source-created workspace; actual native package replacement."
                if native
                else "Fictional workspace only. No live model access "
                "or real account proof."
            )
            if set(upgrade) != fields or upgrade["fixture_notice"] != notice:
                raise ValueError("The published RC2 upgrade contains unknown data.")
        schema = (
            "sinter-native-installer-upgrade/v1"
            if native
            else "sinter-copied-upgrade-test/v1"
        )
        candidate_field = "candidate_app_version" if native else "candidate_version"
        prior_field = "prior_app_version" if native else "prior_version"
        if (
            upgrade.get("schema") != schema
            or upgrade.get("passed") is not True
            or upgrade.get("candidate_source_commit") != commit
            or upgrade.get(candidate_field) != version
            or upgrade.get("prior_source_commit") != prior.source_commit
            or upgrade.get(prior_field) != prior.version
            or not upgrade.get("original_fixture_hashes")
            or not upgrade.get("checks")
        ):
            raise ValueError(
                "Matching original-preserving upgrade evidence is missing."
            )
        if native and (
            upgrade.get("candidate_installer_sha256") != receipt["installer_sha256"]
            or upgrade.get("prior_installer_sha256") != prior.installer_sha256
            or upgrade.get("candidate_package_version") != version.replace("rc", "~rc")
        ):
            raise ValueError("The native replacement did not test this installer.")
        if version in {"0.5.4rc2", "0.5.4rc3"} and (
            upgrade.get("prior_source_archive_sha256") != prior.source_archive_sha256
            or upgrade.get("candidate_binary_sha256") != binary_sha256
            or (
                native
                and upgrade.get("prior_package_version")
                != prior.version.replace("rc", "~rc")
            )
        ):
            raise ValueError(
                "The upgrade does not bind its source and installed binary."
            )
        hashes = upgrade["original_fixture_hashes"]
        if (
            not isinstance(hashes, dict)
            or set(hashes)
            != {"campaigns.sqlite3", "preferences.json", "workspace.sqlite3"}
            or any(
                not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha)
                for sha in hashes.values()
            )
        ):
            raise ValueError(
                "The upgrade does not identify its original fictional workspace."
            )
        required = {
            "prior profile and appearance preferences retained",
            "explicit legacy model selection retained with compatible provider",
            "campaign and casebook identities, revisions and original data retained",
            "saved report, source evidence and user edits retained",
            "disabled watch retained without a search request",
            "retained source-only casebook completed through installed API",
            "opening candidate did not rewrite the prior preferences file",
        }
        if version in {"0.5.4rc2", "0.5.4rc3"} and not native:
            required.add("untouched prior workspace retains every original file digest")
        if version == "0.5.4rc3" and prior.version == "0.5.4rc2":
            required.add(
                "rich prior source snapshots, stale marked review "
                "and unknown/unassigned owners retained"
            )
        observed = (
            upgrade.get("candidate_native_checks", []) if native else upgrade["checks"]
        )
        if not _has_checks(observed, required):
            raise ValueError(
                "The upgrade is missing required work, preferences "
                "or source preservation."
            )
        native_required = {
            f"checksum-verified published v{prior.version} installer "
            "installed and launched",
            "copied fictional workspace used by actual prior native application",
            "candidate installer replaced prior package without prior uninstall",
            "candidate reopened retained data and ran source-only workflow",
            "original prior fixture file digests remain unchanged",
            "replacement candidate removed and installed executable absent",
        }
        if native and not _has_checks(upgrade["checks"], native_required):
            raise ValueError(
                "The actual published-package replacement sequence is incomplete."
            )
        if closed_rc2:
            candidate_required = required - {
                "untouched prior workspace retains every original file digest"
            }
            if (
                set(observed) != required
                or len(observed) != len(required)
                or (
                    native
                    and (
                        set(upgrade["checks"]) != native_required
                        or len(upgrade["checks"]) != len(native_required)
                    )
                )
            ):
                raise ValueError(
                    "The published RC2 upgrade has unqualified check text."
                )
            if native:
                prior_required = (
                    candidate_required
                    - {
                        "explicit legacy model selection retained "
                        "with compatible provider"
                    }
                ) | {"explicit legacy model selection retained by prior application"}
                prior_checks = upgrade["prior_native_checks"]
                if not _has_checks(prior_checks, prior_required) or len(
                    prior_checks
                ) != len(prior_required):
                    raise ValueError(
                        "The published RC2 prior has unqualified check text."
                    )


def independent_review_checks(version: str) -> tuple[str, ...]:
    """Preserve legacy exclusions; RC3 permits only fully noticed terminal libs."""
    terminal_checks = (
        ("readline_excluded", "terminal_library_notices_verified")
        if version == "0.5.4rc3"
        else ("readline_and_tinfo_excluded",)
    )
    return (
        "source_commit_matches_with_declared_windows_CRLF",
        "portable_source_bytes_match",
        "packaged_static_source_bytes_match",
        "actual_debian_notice_and_referenced_text_gate",
        *terminal_checks,
        "frozen_and_installed_receipts_match",
        "github_prior_asset_digest_independently_matches",
        "original_copied_and_replacement_fixture_hashes_match",
        "prior_database_rows_and_preferences_preserved",
        "nine_target_publisher_refuses_linux_only",
        "clean_offline_Ubuntu22_install_self_test_remove",
    )


def verify_rc3_terminal_notices(folder: Path, receipt: dict) -> None:
    """RC3 retained libraries require actual installer notice/reference bytes."""
    from tools.native_licences import library_records, verify_debian_archive

    inventory = receipt["bundled_dependencies"]
    if any("readline" in name for name in library_records(inventory)):
        raise ValueError("Readline is excluded from this scoped RC3 candidate.")
    verify_debian_archive(folder / receipt["installer"], inventory)


def verify_candidate(
    folder: Path, review: Path, version: str, commit: str, repository: Path = ROOT
) -> dict:
    """Recheck original artifacts and independent proof without changing them."""
    _identity(version, commit)
    sums = _checksums(folder)
    if (folder / "SOURCE-COMMIT.txt").read_text().strip() != commit:
        raise ValueError("The candidate source pin differs.")
    qualification = _json(folder / "candidate-qualification.json")
    if (
        qualification.get("schema") != "sinter-preview-qualification/v1"
        or qualification.get("version") != version
        or qualification.get("source_commit") != commit
        or qualification.get("prerelease") is not True
        or qualification.get("all_platform_release_qualified") is not False
        or sorted(qualification.get("unqualified_targets", [])) != UNQUALIFIED
    ):
        raise ValueError(
            "The candidate qualification identity or target scope differs."
        )
    for flag in (
        "normal_package_upgrade_order_verified",
        "installed_runtime_and_copied_upgrade_passed",
        "published_native_installer_replacement_passed",
        "actual_debian_archive_notice_bytes_verified",
        "linux_shared_library_notices_verified",
    ):
        if qualification.get(flag) is not True:
            raise ValueError("A required native qualification gate did not pass.")
    expected_target = {
        "system": "linux",
        "arch": "x64",
        "execution": "native",
        "installed_test": True,
        "copied_prior_release_upgrade_test": True,
        "published_native_installer_replacement_test": True,
        "shared_library_notices_verified": True,
    }
    targets = qualification.get("qualified_targets")
    if targets != [expected_target] or any(
        type(targets[0][key]) is not type(value)
        for key, value in expected_target.items()
    ):
        raise ValueError(
            "This scoped policy only qualifies Linux x64 native execution."
        )
    assets = qualification.get("artifacts")
    if not isinstance(assets, list) or any(not isinstance(row, dict) for row in assets):
        raise ValueError("The candidate inventory is invalid.")
    inventory = {row["path"]: row for row in assets}
    if len(inventory) != len(assets) or set(inventory) != set(sums) - {
        "candidate-qualification.json"
    }:
        raise ValueError("The candidate inventory omits or duplicates artifacts.")
    for name, row in inventory.items():
        if (
            row.get("sha256") != sums[name]
            or type(row.get("bytes")) is not int
            or row["bytes"] != (folder / name).stat().st_size
        ):
            raise ValueError("The candidate inventory differs from the actual files.")
    receipt = verify_target_receipt(
        folder / f"Sinter-{version}-linux-x64-test.json", folder, commit, version
    )
    _canonical_roles(folder, version, receipt)
    if receipt.get("execution") != "native" or (
        receipt["system"].lower(),
        receipt["target_arch"],
    ) != ("linux", "x64"):
        raise ValueError("The receipt does not prove native Linux x64 execution.")
    if (
        receipt.get("machine") != "x86_64"
        or type(receipt.get("pointer_bits")) is not int
    ):
        raise ValueError("The installed machine identity does not match Linux x64.")
    if (
        receipt.get("signed_by_publisher") is not False
        or qualification.get("publisher_signed") is not False
        or qualification.get("notarised") is not False
    ):
        raise ValueError("This candidate must accurately declare its unsigned status.")
    baseline = qualification.get("runtime_baseline", {})
    if (
        any(
            baseline.get(key) != receipt.get(key)
            for key in ("system", "machine", "pointer_bits", "python")
        )
        or baseline.get("libc") != ["glibc", "2.35"]
        or 'VERSION_ID="22.04"' not in baseline.get("os_release", "")
        or baseline.get("network") != "disabled container; loopback only"
        or baseline.get("host_installation") is not False
    ):
        raise ValueError(
            "The qualification runtime baseline differs from its installed proof."
        )
    source = _source(folder, version, commit, repository)
    binary_sha256 = _native_payload(folder, version, source, receipt)
    if version == "0.5.4rc3":
        verify_rc3_terminal_notices(folder, receipt)
    _prior_identity(folder, qualification)
    for prior in candidate_priors(version):
        if prior.version != QUALIFIED_PRIOR_VERSION:
            _prior_source_records(folder, prior)
        _upgrade_records(folder, prior, version, commit, receipt, binary_sha256)
    if version in {"0.5.4rc2", "0.5.4rc3"}:
        from tools.installed_workflow_qualification import verify_installed_workflow

        verify_installed_workflow(
            folder, version, commit, sums, source, receipt, binary_sha256
        )
    if version == "0.5.4rc3":
        from tools.installed_recovery_contract import verify_installed_recovery

        verify_installed_recovery(
            folder, version, commit, sums, source, receipt, binary_sha256
        )
    independent = _json(review / "final-artifact-review.json")
    required_checks = independent_review_checks(version)
    if (
        independent.get("schema") != "sinter-independent-final-artifact-review/v1"
        or independent.get("source_commit") != commit
        or independent.get("version") != version
        or any(
            independent.get("checks", {}).get(name) is not True
            for name in required_checks
        )
    ):
        raise ValueError(
            "The independent installed-artifact review is missing or incomplete."
        )
    for key, filename in (
        ("installer_sha256", receipt["installer"]),
        ("native_archive_sha256", f"Sinter-{version}-linux-x64.tar.gz"),
        ("source_archive_sha256", f"sinter-{version}-source.zip"),
        ("portable_sha256", f"sinter-{version}.pyz"),
    ):
        if independent.get(key) != sums[filename]:
            raise ValueError("The independent review tested another artifact.")
    clean = _json(review / "clean-ubuntu-installed-test.json")
    if clean != receipt["installed_test"]:
        raise ValueError("The independent installed runtime evidence differs.")
    context = _json(review / "qualification-context.json")
    if (
        context.get("source_commit") != commit
        or context.get("version") != version
        or context.get("installer_sha256") != receipt["installer_sha256"]
        or context.get("container") != "ubuntu:22.04"
        or context.get("network") != "disabled"
        or context.get("host_installation") is not False
        or context.get("product_edits") is not False
        or context.get("preinstalled_python") is not False
        or context.get("preinstalled_account_packages") is not False
    ):
        raise ValueError("The independent clean-install scope is unproven.")
    return {
        "canonical_checksum_entries": len(sums),
        "source_files": len(source),
        "native_target": TARGET,
        "installed_and_upgrade_evidence": True,
        "actual_package_and_notices": True,
        "independent_clean_install": True,
    }
