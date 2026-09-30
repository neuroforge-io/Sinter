"""Fail a release unless all nine installed-app receipts match this checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from sinter import __version__  # noqa: E402
from tools.native_licences import library_records, verify_debian_archive  # noqa: E402

EXPECTED = (
    {("windows", arch) for arch in ("x64", "x86", "arm64")}
    | {("darwin", arch) for arch in ("x64", "arm64")}
    | {("linux", arch) for arch in ("x64", "x86", "arm64", "armv7")}
)
ACCOUNT_TARGETS = {("windows", "x64"), ("darwin", "arm64")} | {
    ("linux", arch) for arch in ("x64", "x86", "arm64", "armv7")
}
AUTH_PACKAGES = {"PyJWT", "cryptography", "cffi", "pycparser"}
ALLOWED_AUTH_PACKAGES = AUTH_PACKAGES | {"typing_extensions"}


def verify_installed_receipt(row):
    """Reject summaries without the actual matching installed-app evidence."""
    identity = ("schema", "version", "system", "machine", "pointer_bits", "python")
    runtime_fields = (
        *identity,
        "checks",
        "account_auth_bundled",
        "account_auth_dependencies",
    )
    phase_identity = (*identity, "account_auth_bundled", "account_auth_dependencies")
    for name in ("frozen_test", "installed_test"):
        test = row.get(name)
        if (
            not isinstance(test, dict)
            or test.get("passed") is not True
            or test.get("frozen") is not True
            or test.get("schema") != "sinter-native-test/v1"
            or not isinstance(test.get("checks"), list)
            or any(field not in test for field in identity)
            or any(test.get(field) != row.get(field) for field in phase_identity)
            or (
                row.get("account_auth_bundled") is True
                and "bundled ChatGPT identity verification" not in test["checks"]
            )
        ):
            raise ValueError(
                "Matching frozen and installed runtime evidence is missing."
            )
    installed = row["installed_test"]
    if any(installed.get(field) != row.get(field) for field in runtime_fields):
        raise ValueError(
            "Published runtime checks do not match the installed evidence."
        )


def verify_account_capability(row, target):
    """Publish only capabilities proven inside that target's installed binary."""
    expected = target in ACCOUNT_TARGETS
    if row.get("account_auth_bundled") is not expected:
        raise ValueError("An installer account capability does not match its target.")
    if not expected:
        dependencies = row.get("bundled_dependencies", [])
        if not isinstance(dependencies, list):
            raise ValueError("Bundled dependency inventory is invalid.")
        if (
            row.get("account_auth_dependencies")
            or "bundled ChatGPT identity verification" in row.get("checks", [])
            or any(
                isinstance(dependency, dict)
                and isinstance(dependency.get("name"), str)
                and dependency.get("name") in ALLOWED_AUTH_PACKAGES
                for dependency in dependencies
            )
        ):
            raise ValueError("An installer claimed excluded account dependencies.")
        return
    if "bundled ChatGPT identity verification" not in row.get("checks", []):
        raise ValueError("Installed ChatGPT identity verification is missing.")
    versions = row.get("account_auth_dependencies")
    if (
        not isinstance(versions, dict)
        or not AUTH_PACKAGES <= set(versions) <= ALLOWED_AUTH_PACKAGES
        or any(not isinstance(value, str) or not value for value in versions.values())
    ):
        raise ValueError("Installed account dependency versions are missing.")
    dependencies = row.get("bundled_dependencies")
    if not isinstance(dependencies, list):
        raise ValueError("Bundled account licence inventory is missing.")
    names = {}
    for dependency in dependencies:
        if (
            not isinstance(dependency, dict)
            or not isinstance(dependency.get("name"), str)
            or not dependency["name"]
            or dependency["name"] in names
        ):
            raise ValueError("Bundled dependency inventory is invalid or duplicated.")
        names[dependency.get("name")] = dependency
    for name in versions:
        dependency = names.get(name, {})
        licences = dependency.get("licences")
        if (
            dependency.get("version") != versions[name]
            or not isinstance(licences, list)
            or not licences
        ):
            raise ValueError(
                "Bundled account versions or licence notices do not match."
            )
        for licence in licences:
            if (
                not isinstance(licence, dict)
                or not isinstance(licence.get("path"), str)
                or not licence["path"]
                or "\\" in licence["path"]
                or ":" in licence["path"]
                or Path(licence["path"]).is_absolute()
                or ".." in Path(licence["path"]).parts
                or not isinstance(licence.get("sha256"), str)
                or not re.fullmatch("[0-9a-f]{64}", licence.get("sha256", ""))
            ):
                raise ValueError("Bundled account licence provenance is invalid.")


def assemble(output: Path, source: Path, commit: str):
    receipts = sorted(output.glob("*-test.json"))
    if len(receipts) != len(EXPECTED):
        raise ValueError("A required architecture receipt is missing or duplicated.")
    targets = set()
    records = []
    for path in receipts:
        row = json.loads(path.read_text(encoding="utf-8"))
        system = row["system"].lower()
        arch = row["target_arch"]
        key = (system, arch)
        if key not in EXPECTED or key in targets:
            raise ValueError("Unexpected or duplicate installer target.")
        if row.get("pointer_bits") != (32 if arch in {"x86", "armv7"} else 64):
            raise ValueError("An installer runtime has the wrong pointer size.")
        targets.add(key)
        if (
            row.get("passed") is not True
            or row.get("frozen") is not True
            or row.get("version") != __version__
            or row.get("source_commit") != commit
        ):
            raise ValueError("An installer receipt does not match the release source.")
        name = row["installer"]
        if Path(name).name != name or not name.startswith(f"Sinter-{__version__}-"):
            raise ValueError("Invalid installer filename.")
        package = output / name
        if hashlib.sha256(package.read_bytes()).hexdigest() != row["installer_sha256"]:
            raise ValueError("An installer digest does not match its test receipt.")
        if not row.get("installer_test"):
            raise ValueError("Installed-app validation is missing.")
        verify_installed_receipt(row)
        verify_account_capability(row, key)
        if system == "linux":
            if row.get("linux_shared_library_notices_verified") is not True:
                raise ValueError("Bundled Linux library notices were not verified.")
            try:
                declared = library_records(row.get("bundled_dependencies", []))
            except RuntimeError as error:
                raise ValueError(str(error)) from error
            if row.get("native_shared_library_files") != declared:
                raise ValueError(
                    "Bundled Linux library notice coverage does not match."
                )
            try:
                verify_debian_archive(package, row["bundled_dependencies"])
            except RuntimeError as error:
                raise ValueError(str(error)) from error
        records.append(row)
    if targets != EXPECTED:
        raise ValueError("Not all required installer targets passed.")
    if (source / "verified-commit.txt").read_text(encoding="utf-8").strip() != commit:
        raise ValueError("Source archive was tested at a different commit.")
    shutil.copy2(
        source / "sinter-source.zip", output / f"sinter-{__version__}-source.zip"
    )
    shutil.copy2(source / "dist" / "sinter.pyz", output / f"sinter-{__version__}.pyz")
    (output / "build-manifest.json").write_text(
        json.dumps(
            {
                "schema": "sinter-release/v1",
                "version": __version__,
                "source_commit": commit,
                "installer_targets": records,
                "publisher_signed": False,
                "speech_bundled": False,
                "rkc_bundled": False,
                "account_auth_targets": [
                    list(target) for target in sorted(ACCOUNT_TARGETS)
                ],
                "portable_core_account_auth_bundled": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    checksums = []
    for path in sorted(output.iterdir()):
        if (
            path.is_file()
            and not path.name.endswith(".sha256")
            and path.name != "SHA256SUMS.txt"
        ):
            checksums.append(
                hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name
            )
    (output / "SHA256SUMS.txt").write_text(
        "\n".join(checksums) + "\n", encoding="ascii"
    )
    print(f"Verified {len(records)} installed targets and source at {commit}")


def main(argv: list[str] | None = None) -> None:
    """Validate release inputs before assembling the required target receipts."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="GITHUB_SHA must contain the full source commit tested by CI.",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Directory containing all nine installers and test receipts.",
    )
    parser.add_argument(
        "source",
        type=Path,
        help=(
            "Tested source package with verified-commit.txt, "
            "sinter-source.zip and dist/sinter.pyz."
        ),
    )
    args = parser.parse_args(argv)
    commit = os.environ.get("GITHUB_SHA", "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        parser.error(
            "Set GITHUB_SHA to the full 40-character source commit tested by CI. "
            "Release provenance is required."
        )
    for name, folder in [("output", args.output), ("source", args.source)]:
        if not folder.is_dir():
            parser.error(f"The {name} directory does not exist: {folder}")
    try:
        assemble(args.output, args.source, commit)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"{parser.prog}: release validation failed: {exc}\n")


if __name__ == "__main__":
    main()
