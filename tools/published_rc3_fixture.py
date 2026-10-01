"""Prepare an exact published-E fictional fixture; never install or qualify RC4.

This separate route does not change historical qualified priors or receipts.
Only fixture creation is supported. Actual binary launch, package replacement,
native controls, independent admission and publication remain separate gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.qualified_priors import PriorRelease  # noqa: E402
from tools.upgrade_smoke import (  # noqa: E402
    MAX_PRIOR_ARCHIVE_BYTES,
    admitted_source_files,
    file_sha256,
    hashes,
)

PUBLISHED_E = PriorRelease(
    "0.5.4rc3",
    "246b91e0ee432cb1f6f6fcd17425f55cd7a4cabe",
    "6d2a4ec4c6342d1243507169d877d2d266230469b01dbc00cbe031c53328f22a",
    "bb7133d70d3abfc3a0f825d57968d75629e00dc21af8d33030870e68c8c99dae",
)
REPLACEMENT_PROFILE = "0.5.4rc4"
TARGET = "linux-x64"


def seed_environment(directory: Path) -> dict[str, str]:
    """Exclude caller accounts while retaining Windows interpreter bootstrap."""
    environment = {"PATH": os.defpath}
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
        if type(system_root) is not str or not system_root or "\x00" in system_root:
            raise ValueError("Windows fixture Python requires a valid SystemRoot.")
        # Python's Windows bootstrap needs SystemRoot; pathlib needs a home.
        # Point the latter at fictional data, never the caller's account profile.
        environment.update(SystemRoot=system_root, USERPROFILE=str(directory.resolve()))
    return environment


def select_fixture_profile(version, commit, replacement, target) -> PriorRelease:
    """Admit exact E fixture inputs, not a candidate or release qualification."""
    if any(type(value) is not str for value in (version, commit, replacement, target)):
        raise ValueError("Choose the exact published E fixture profile.")
    if (version, commit, replacement, target) != (
        PUBLISHED_E.version,
        PUBLISHED_E.source_commit,
        REPLACEMENT_PROFILE,
        TARGET,
    ):
        raise ValueError(
            "Choose the exact published E fixture profile; "
            "development versions are refused."
        )
    return PUBLISHED_E


def verify_inputs(source: Path, archive: Path, installer: Path) -> dict[str, str]:
    """Verify all prior source bytes and the exact E installer before writing."""
    for path, expected in (
        (archive, PUBLISHED_E.source_archive_sha256),
        (installer, PUBLISHED_E.installer_sha256),
    ):
        if not path.is_file() or path.is_symlink():
            raise ValueError("Use the regular published E source ZIP and DEB.")
        if path.stat().st_size > MAX_PRIOR_ARCHIVE_BYTES:
            raise ValueError("Published E input exceeds the fixture size bound.")
        if file_sha256(path) != expected:
            raise ValueError("Published E input differs from its immutable checksum.")
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Use the complete extracted published E source.")
    # The exact archive pin is checked first. Do not import current-source
    # modules, accept a caller checksum, or modify QUALIFIED_PRIORS to use E.
    with zipfile.ZipFile(archive) as bundle:
        sizes = {
            row.filename: row.file_size for row in bundle.infolist() if not row.is_dir()
        }
        directories = {
            parent.as_posix()
            for name in sizes
            for parent in PurePosixPath(name).parents
            if parent != PurePosixPath(".")
        }
        files = admitted_source_files(source, sizes, directories)
        expected_hashes = {}
        for name, path in files.items():
            expected_hashes[name] = hashlib.sha256(bundle.read(name)).hexdigest()
            if file_sha256(path) != expected_hashes[name]:
                raise ValueError("Extracted E source differs from the pinned archive.")
    metadata = subprocess.check_output(
        ["dpkg-deb", "-f", str(installer), "Package", "Version", "Architecture"],
        text=True,
        timeout=20,
    ).splitlines()
    if metadata != ["Package: sinter", "Version: 0.5.4~rc3", "Architecture: amd64"]:
        raise ValueError("Use the exact Linux x64 published E package metadata.")
    return expected_hashes


def prepare_fixture(args) -> dict:
    """Create source-only prior/copy data after closed identity admission."""
    prior = select_fixture_profile(
        args.prior_version,
        args.prior_commit,
        args.replacement_profile,
        args.target,
    )
    source_hashes = verify_inputs(
        args.prior_source, args.prior_source_archive, args.prior_installer
    )
    output, source = args.output.resolve(), args.prior_source.resolve()
    if (
        output.exists()
        or output.is_relative_to(source)
        or source.is_relative_to(output)
    ):
        raise ValueError("Choose a fresh fixture output outside the prior source.")
    output.mkdir(mode=0o700, parents=True)
    original = output / "original-E-workspace"
    copied = output / "copied-for-eventual-replacement"
    expected_path = output / "fixture-originals.json"
    seed = Path(__file__).with_name("published_rc3_fixture_seed.py")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(seed),
                str(source),
                str(original),
                str(expected_path),
            ],
            # No inherited connection/model/key override enters the source fixture.
            env=seed_environment(output),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=40,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        (output / "seed.stdout").write_bytes(exc.stdout or b"")
        (output / "seed.stderr").write_bytes(exc.stderr or b"")
        raise ValueError(
            "Published E seed timed out; retained partial output is not a pass."
        ) from exc
    (output / "seed.stdout").write_bytes(result.stdout)
    (output / "seed.stderr").write_bytes(result.stderr)
    if result.returncode != 0 or result.stderr:
        raise ValueError(
            "Published E source fixture failed; "
            "retained seed diagnostics are not a pass."
        )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    if expected["prior_version"] != prior.version:
        raise ValueError("The fixture did not use the exact prior version.")
    if (
        verify_inputs(source, args.prior_source_archive, args.prior_installer)
        != source_hashes
    ):
        raise ValueError("Prior source inputs changed during fixture creation.")
    original_hashes = hashes(original)
    shutil.copytree(original, copied)
    if hashes(copied) != original_hashes:
        raise ValueError("The replacement copy differs from the original fixture.")
    receipt = {
        "schema": "sinter-published-rc3-fixture/v1",
        "fixture_created": True,
        "scope": (
            "Fictional source-created E fixture; "
            "no binary launch or package replacement."
        ),
        "prior_version": prior.version,
        "prior_source_commit": prior.source_commit,
        "prior_source_archive_sha256": prior.source_archive_sha256,
        "prior_installer_sha256": prior.installer_sha256,
        "prior_source_hashes": source_hashes,
        "replacement_fixture_profile": REPLACEMENT_PROFILE,
        "target": TARGET,
        "candidate_admitted": False,
        "candidate_tested": False,
        "prior_binary_tested": False,
        "package_replacement_tested": False,
        "original_fixture_hashes": original_hashes,
        "copied_fixture_hashes": hashes(copied),
        "fixture_originals_sha256": file_sha256(expected_path),
        "source_protocol_checks": expected["source_protocol_checks"],
        "producer_sha256": file_sha256(Path(__file__)),
        "seed_sha256": file_sha256(seed),
    }
    (output / "fixture-preparation.json").write_text(
        json.dumps(receipt, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-source", type=Path, required=True)
    parser.add_argument("--prior-source-archive", type=Path, required=True)
    parser.add_argument("--prior-installer", type=Path, required=True)
    parser.add_argument("--prior-version", default=PUBLISHED_E.version)
    parser.add_argument("--prior-commit", default=PUBLISHED_E.source_commit)
    parser.add_argument("--replacement-profile", default=REPLACEMENT_PROFILE)
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        prepare_fixture(args)
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Published E fixture preparation refused: {exc}\n")
    print(
        "Fixture prepared from exact published E source; "
        "no installed or replacement pass."
    )


if __name__ == "__main__":
    main()
