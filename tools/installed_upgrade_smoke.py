"""Replace a published native installer inside a disposable offline container."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.package_native import debian_package_version  # noqa: E402
from tools.upgrade_smoke import (  # noqa: E402
    PRIOR_COMMIT,
    hashes,
    prepare_fixture,
    run_native,
)

BINARY = Path("/opt/neuroforge/sinter/Sinter")


def package_field(installer: Path, field: str) -> str:
    return subprocess.check_output(
        ["dpkg-deb", "-f", str(installer), field], text=True, timeout=20
    ).strip()


def installed_version() -> str:
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=" + "$" + "{Status} " + "$" + "{Version}", "sinter"],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    prefix = "install ok installed "
    return (
        result.stdout.removeprefix(prefix).strip()
        if (result.returncode == 0 and result.stdout.startswith(prefix))
        else ""
    )


def qualify(args) -> dict:
    if os.geteuid() != 0 or not Path("/.dockerenv").is_file():
        raise ValueError(
            "Installer replacement requires a disposable Docker container."
        )
    if installed_version():
        raise ValueError("The disposable container already has Sinter installed.")
    prior_sha = hashlib.sha256(args.prior_installer.read_bytes()).hexdigest()
    candidate_sha = hashlib.sha256(args.candidate_installer.read_bytes()).hexdigest()
    if prior_sha != args.prior_sha256:
        raise ValueError("Prior native installer differs from its published checksum.")
    for installer in (args.prior_installer, args.candidate_installer):
        if package_field(installer, "Package") != "sinter":
            raise ValueError("Use actual Sinter Debian installers.")
    if package_field(args.prior_installer, "Version") != "0.5.3":
        raise ValueError("Use the published v0.5.3 prior native installer.")
    expected_package = debian_package_version(args.expected_version)
    if package_field(args.candidate_installer, "Version") != expected_package:
        raise ValueError("Candidate native installer version does not match.")
    expected, original, copied, original_hashes = prepare_fixture(
        args.prior_source, args.output
    )
    checks = []
    try:
        subprocess.run(
            ["dpkg", "-i", str(args.prior_installer)], check=True, timeout=60
        )
        assert installed_version() == "0.5.3"
        prior_version, prior_checks = run_native(
            BINARY, copied, expected, args.output, "0.5.3", legacy=True
        )
        assert installed_version() == "0.5.3"
        # Deliberately retain the installed prior package while applying its update.
        subprocess.run(
            ["dpkg", "-i", str(args.candidate_installer)], check=True, timeout=60
        )
        assert installed_version() == expected_package
        candidate_version, candidate_checks = run_native(
            BINARY, copied, expected, args.output, args.expected_version
        )
        binary_sha = hashlib.sha256(BINARY.read_bytes()).hexdigest()
        assert hashes(original) == original_hashes
        checks.extend(
            [
                "checksum-verified published v0.5.3 installer installed and launched",
                "copied fictional workspace used by actual prior native application",
                "candidate installer replaced prior package without prior uninstall",
                "candidate reopened retained data and ran source-only workflow",
                "original prior fixture file digests remain unchanged",
            ]
        )
    finally:
        if installed_version():
            subprocess.run(["dpkg", "-r", "sinter"], check=True, timeout=60)
    assert not BINARY.exists()
    checks.append("replacement candidate removed and installed executable absent")
    return {
        "schema": "sinter-native-installer-upgrade/v1",
        "passed": True,
        "fixture_notice": (
            "Fictional source-created workspace; actual native package replacement."
        ),
        "prior_source_commit": PRIOR_COMMIT,
        "prior_app_version": prior_version,
        "prior_installer_sha256": prior_sha,
        "candidate_source_commit": args.source_commit,
        "candidate_app_version": candidate_version,
        "candidate_package_version": expected_package,
        "candidate_installer_sha256": candidate_sha,
        "candidate_binary_sha256": binary_sha,
        "original_fixture_hashes": original_hashes,
        "prior_native_checks": prior_checks,
        "candidate_native_checks": candidate_checks,
        "checks": checks,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-source", type=Path, required=True)
    parser.add_argument("--prior-installer", type=Path, required=True)
    parser.add_argument("--prior-sha256", required=True)
    parser.add_argument("--candidate-installer", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-version", default="0.5.4rc1")
    args = parser.parse_args(argv)
    if not re.fullmatch("[0-9a-f]{40}", args.source_commit) or not re.fullmatch(
        "[0-9a-f]{64}", args.prior_sha256
    ):
        parser.error("Use full verified source and prior-installer identities.")
    if not (args.prior_source / "src/sinter/__init__.py").is_file() or any(
        not path.is_file() for path in (args.prior_installer, args.candidate_installer)
    ):
        parser.error("Provide the extracted prior source and both actual installers.")
    try:
        receipt = qualify(args)
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Native installer upgrade qualification failed: {error}\n")
    (args.output / "installer-upgrade-test.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print("PASS: published native installer replaced; copied fictional work retained.")


if __name__ == "__main__":
    main()
