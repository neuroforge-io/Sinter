"""Audit the retained D9 artifact; never stage, publish or qualify current E."""

from __future__ import annotations

import argparse
import json
import shutil
import signal
import sys
import tarfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from tools.candidate_qualification import (  # noqa: E402
    _native_payload,
    _source,
    digest,
    prior_roles,
    verify_rc3_terminal_notices,
)
from tools.qualified_priors import QUALIFIED_PRIORS  # noqa: E402
from tools.qualify_linux_preview import run as run_owned  # noqa: E402
from tools.release_manifest import assemble  # noqa: E402

VERSION = "0.5.4rc3"
COMMIT = "d9b36a6853bab0d715dc91e726f984a8ab16a747"
ARTIFACT_SHA = "ef70ac114f3de900431f2115b93116d5d8b692b80cc07312fb8a873a58192661"
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
STAGING_REFUSED_EXIT = 3


class HistoricalStagingRefused(ValueError):
    """The retained audit completed; publication staging is unsupported."""


CLEAN_SCRIPT = r"""#!/bin/sh
set -eu
test "$(id -u)" = 0
grep -q '^VERSION_ID="22.04"$' /etc/os-release
cat /etc/os-release > /proof/os-release.txt
getconf GNU_LIBC_VERSION > /proof/libc.txt
cat /proof/os-release.txt /proof/libc.txt
# Check installed packages and actual filesystem, not just PATH discovery.
dpkg-query -W -f='${binary:Package} ${db:Status-Abbrev}\n' \
  > /proof/preinstalled-packages.txt
if grep -E '^(python|libpython|pypy)[^ ]* ii' \
  /proof/preinstalled-packages.txt; then exit 31; fi
find / -xdev -type f \
  \( -iname '*python*' -o -iname '*pypy*' -o -iname '*pyjwt*' \) \
  > /proof/preinstalled-python-files.txt
find / -xdev -type d \( -name site-packages -o -name dist-packages \
  -o -name jwt -o -name cryptography -o -name cffi -o -name pycparser \) \
  > /proof/preinstalled-account-files.txt
test ! -s /proof/preinstalled-python-files.txt
test ! -s /proof/preinstalled-account-files.txt
test ! -e /opt/neuroforge/sinter/Sinter
printf '%s\n' 'Actual preinstall package inventory:'
cat /proof/preinstalled-packages.txt
printf '%s\n' 'Python/account filesystem inventories are empty; candidate absent.'
printf '%s\n' '{"schema":"sinter-clean-preflight/v1",' \
  '"python_packages":0,"python_files":0,"account_packages":0,' \
  '"candidate_preinstalled":false}' > /proof/preflight.json
cat /proof/preflight.json
dpkg -i /candidate/Sinter-0.5.4rc3-linux-x64.deb
dpkg-query -W -f='${binary:Package} ${Version} ${db:Status-Abbrev}\n' sinter
sha256sum /opt/neuroforge/sinter/Sinter > /proof/installed-binary.sha256
cat /proof/installed-binary.sha256
mkdir -p /tmp/sinter-clean-home /tmp/sinter-clean-data
chmod 700 /tmp/sinter-clean-home /tmp/sinter-clean-data
env -i PATH=/usr/bin:/bin LANG=C.UTF-8 TZ=UTC HOME=/tmp/sinter-clean-home \
  XDG_DATA_HOME=/tmp/sinter-clean-data /opt/neuroforge/sinter/Sinter \
  --self-test /proof/clean-ubuntu-installed-test.json
cat /proof/clean-ubuntu-installed-test.json
dpkg -r sinter
test ! -e /opt/neuroforge/sinter/Sinter
printf '%s\n' '{"installed_selftest_completed":true,"package_removed":true}' \
  > /proof/removal.json
cat /proof/removal.json
"""


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def command(args: list[str], *, timeout=120, log: Path | None = None) -> str:
    return run_owned(args, timeout=timeout, log=log)


def cleanup_owned(owner: str) -> None:
    """Remove only resources bearing this invocation's unique ownership label."""
    selector = "label=sinter.qualification.owner=" + owner
    containers = command(
        ["docker", "ps", "--all", "--no-trunc", "--quiet", "--filter", selector]
    ).splitlines()
    for identity in containers:
        if len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("Invalid owned container identity during cleanup.")
        command(["docker", "rm", "--force", identity], timeout=30)
    images = command(
        ["docker", "image", "ls", "--no-trunc", "--quiet", "--filter", selector]
    ).splitlines()
    for identity in set(images):
        if (
            not identity.startswith("sha256:")
            or len(identity) != 71
            or any(c not in "0123456789abcdef" for c in identity[7:])
        ):
            raise ValueError("Invalid owned image identity during cleanup.")
        command(["docker", "image", "rm", identity], timeout=30)
    if command(["docker", "ps", "--all", "--quiet", "--filter", selector]) or command(
        ["docker", "image", "ls", "--quiet", "--filter", selector]
    ):
        raise ValueError("Owned clean-install resource remains.")


def admit_archive(path: Path) -> None:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_TOTAL
        or digest(path) != ARTIFACT_SHA
    ):
        raise ValueError("Use the unchanged original installed-gates artifact.")
    with zipfile.ZipFile(path) as archive:
        seen, total = set(), 0
        for row in archive.infolist():
            # ZipInfo normalises the host separator while reading on Windows.
            # Admission must inspect the original stored name before that rewrite
            # (and before the constructor truncates a NUL-containing filename).
            name = row.orig_filename
            archive_path = PurePosixPath(name)
            parts = archive_path.parts
            total += row.file_size
            if (
                name in seen
                or not parts
                or archive_path.is_absolute()
                or ".." in parts
                or "\\" in name
                or ":" in name
                or "\x00" in name
                or row.file_size > MAX_FILE
                or total > MAX_TOTAL
                or (row.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("Unsafe or oversized original evidence archive.")
            seen.add(name)


def validate_clean(proof: Path, native: dict, binary: str) -> dict:
    preflight = json.loads((proof / "preflight.json").read_bytes())
    expected = {
        "schema": "sinter-clean-preflight/v1",
        "python_packages": 0,
        "python_files": 0,
        "account_packages": 0,
        "candidate_preinstalled": False,
    }
    if (
        json.dumps(preflight, sort_keys=True) != json.dumps(expected, sort_keys=True)
        or (proof / "preinstalled-python-files.txt").read_bytes()
        or (proof / "preinstalled-account-files.txt").read_bytes()
    ):
        raise ValueError("Independent filesystem/package preflight is incomplete.")
    packages = (proof / "preinstalled-packages.txt").read_text()
    for line in packages.splitlines():
        name, status = line.split(maxsplit=1)
        if name.startswith(("python", "libpython", "pypy")) and status.startswith("ii"):
            raise ValueError("A system Python package was preinstalled.")
    if (proof / "installed-binary.sha256").read_text().strip() != (
        binary + "  /opt/neuroforge/sinter/Sinter"
    ):
        raise ValueError(
            "Actually installed executable differs from the original binary."
        )
    clean = json.loads((proof / "clean-ubuntu-installed-test.json").read_bytes())
    if json.dumps(clean, sort_keys=True) != json.dumps(
        native["installed_test"], sort_keys=True
    ):
        raise ValueError("Clean installed self-test differs from the original receipt.")
    if json.loads((proof / "removal.json").read_bytes()) != {
        "installed_selftest_completed": True,
        "package_removed": True,
    }:
        raise ValueError("Actual package removal is unproven.")
    if (
        'VERSION_ID="22.04"' not in (proof / "os-release.txt").read_text()
        or (proof / "libc.txt").read_text().strip() != "glibc 2.35"
    ):
        raise ValueError("Clean runtime has another OS/libc baseline.")
    return clean


def clean_install(candidate: Path, proof: Path, native: dict, binary: str) -> dict:
    proof.mkdir()
    runner = proof / "clean-install.sh"
    runner.write_text(CLEAN_SCRIPT)
    owner = uuid.uuid4().hex
    image = "sinter-rc3-clean:" + owner
    try:
        command(
            [
                "docker",
                "build",
                "--tag",
                image,
                "--label",
                "sinter.qualification.owner=" + owner,
                "--file",
                str(ROOT / "tools/clean-qualification-image.Dockerfile"),
                str(ROOT / "tools"),
            ],
            log=proof / "image-build.log",
        )
        image_id = command(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
        name = "sinter-rc3-clean-" + owner
        container = command(
            [
                "docker",
                "create",
                "--name",
                name,
                "--pull",
                "never",
                "--network",
                "none",
                "--memory",
                "384m",
                "--cpus",
                "1",
                "--pids-limit",
                "128",
                "--label",
                "sinter.qualification.owner=" + owner,
                "--mount",
                f"type=bind,src={candidate.resolve()},dst=/candidate,readonly",
                "--mount",
                f"type=bind,src={proof.resolve()},dst=/proof",
                image_id,
                "/bin/sh",
                "/proof/clean-install.sh",
            ]
        )
        if len(container) != 64 or any(c not in "0123456789abcdef" for c in container):
            raise ValueError("No owned container identity.")
        observed = json.loads(command(["docker", "inspect", container]))[0]
        if (
            observed["HostConfig"]["NetworkMode"] != "none"
            or observed["Image"] != image_id
        ):
            raise ValueError("Independent container identity or offline scope differs.")
        command(
            ["docker", "start", "--attach", container],
            log=proof / "clean-ubuntu-installed-test.log",
        )
        result = validate_clean(proof, native, binary)
    finally:
        cleanup_owned(owner)
        write(
            proof / "cleanup.json", {"container_removed": True, "image_removed": True}
        )
    write(
        proof / "container.json",
        {
            "image_id": image_id,
            "image_recipe_sha256": digest(
                ROOT / "tools/clean-qualification-image.Dockerfile"
            ),
            "base_image": (ROOT / "tools/clean-qualification-image.Dockerfile")
            .read_text()
            .splitlines()[0]
            .removeprefix("FROM "),
            "container_id": container,
            "network": observed["HostConfig"]["NetworkMode"],
            "container_removed": True,
            "image_removed": True,
            "memory_mib": 384,
            "cpu_limit": 1,
            "private_workspace_used": False,
        },
    )
    return result


def canonical(raw: Path, folder: Path) -> dict:
    folder.mkdir()
    candidate = raw / "candidate"
    for name in (
        f"Sinter-{VERSION}-linux-x64.deb",
        f"Sinter-{VERSION}-linux-x64.tar.gz",
        f"Sinter-{VERSION}-linux-x64-test.json",
        f"sinter-{VERSION}-source.zip",
        f"sinter-{VERSION}.pyz",
    ):
        shutil.copyfile(candidate / name, folder / name)
    native = json.loads((folder / f"Sinter-{VERSION}-linux-x64-test.json").read_bytes())
    gates = json.loads(
        (raw / "installed-qualification/installed-gates.json").read_bytes()
    )
    if (
        gates["source_commit"] != COMMIT
        or not gates["passed"]
        or native["source_commit"] != COMMIT
    ):
        raise ValueError("Original installed evidence has another build identity.")
    for prior in QUALIFIED_PRIORS.values():
        source_name, sums_name, copied_name, replacement_name = prior_roles(prior)
        shutil.copyfile(
            raw / f"priors/{prior.version}/source-verification.json",
            folder / source_name,
        )
        shutil.copyfile(
            raw / f"priors/{prior.version}/SHA256SUMS.txt", folder / sums_name
        )
        for mode, source, target in (
            ("copied", "upgrade-test.json", copied_name),
            ("installed", "installer-upgrade-test.json", replacement_name),
        ):
            shutil.copyfile(
                raw
                / f"installed-qualification/upgrades/{mode}-{prior.version}/{source}",
                folder / target,
            )
    evidence = raw / "installed-qualification/evidence"
    for path in evidence.rglob("*"):
        if path.is_file():
            target = folder / path.relative_to(evidence)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    with tarfile.open(folder / f"Sinter-{VERSION}-linux-x64.tar.gz") as runtime:
        for member in runtime:
            if member.isfile() and member.name.startswith("Sinter/licenses/"):
                relative = member.name.removeprefix("Sinter/")
                if ".." in Path(relative).parts or member.size > MAX_FILE:
                    raise ValueError("Unsafe exported notice.")
                target = folder / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with runtime.extractfile(member) as stream, target.open("wb") as sink:
                    shutil.copyfileobj(stream, sink)
    verify_rc3_terminal_notices(folder, native)
    (folder / "SOURCE-COMMIT.txt").write_text(COMMIT + "\n")
    with zipfile.ZipFile(folder / f"sinter-{VERSION}-source.zip") as original:
        (folder / "qualification-Dockerfile").write_bytes(
            original.read("tools/qualification-image.Dockerfile")
        )
        workflow = original.read(".github/workflows/native.yml").decode("utf-8")
        step = workflow.split(
            "      - name: Run existing pinned upgrades and installed "
            "workflow/recovery",
            1,
        )[1]
        lines = (
            step.split("        run: |\n", 1)[1]
            .split("      - name:", 1)[0]
            .splitlines()
        )
        recorded = "\n".join(
            line[10:] for line in lines if line.startswith("          ")
        )
        (folder / "qualification-runner.sh").write_text(
            "#!/bin/sh\n# Original hosted gate command; "
            "run from the pinned source checkout.\n" + recorded + "\n"
        )
    shutil.copyfile(
        raw / "installed-qualification-setup/image-build.log",
        folder / "qualification-build.log",
    )
    shutil.copyfile(
        raw / "installed-qualification-setup/image.json",
        folder / "qualification-image.json",
    )
    return native


def publisher_negative(candidate: Path) -> dict:
    """Exercise the unchanged all-target gate with one genuine target input."""
    if len(list(candidate.glob("*-test.json"))) != 1:
        raise ValueError("Publisher input is not a single Linux architecture.")
    try:
        assemble(candidate, ROOT, COMMIT)
    except ValueError as error:
        if str(error) != "A required architecture receipt is missing or duplicated.":
            raise
        return {
            "schema": "sinter-preview-publisher-gate/v1",
            "linux_only_promotion_refused": True,
            "returncode": 1,
            "architecture_receipts": 1,
            "message": str(error),
        }
    raise ValueError("All-platform publisher accepted Linux-only evidence.")


def finalize(artifact: Path, output: Path) -> None:
    admit_archive(artifact)
    output.mkdir()
    raw, folder, proof = (output / name for name in ("raw", "canonical", "clean-proof"))
    with zipfile.ZipFile(artifact) as archive:
        archive.extractall(raw)
    native = canonical(raw, folder)
    source = _source(folder, VERSION, COMMIT, ROOT)
    binary = _native_payload(folder, VERSION, source, native)
    started = time.monotonic()
    clean_install(folder, proof, native, binary)
    clean_seconds = round(time.monotonic() - started, 3)
    # The fixed artifact is historical workflow/v1. Current RC3 publication
    # notes describe E's workflow/v2 and Word recovery, so this retained audit
    # must never manufacture a current candidate or independent-review receipt.
    write(
        output / "final-qualification.json",
        {
            "schema": "sinter-rc3-retained-artifact-audit/v1",
            "source_commit": COMMIT,
            "qualification_policy_commit": command(["git", "rev-parse", "HEAD"]),
            "qualification_tool_sha256": digest(Path(__file__)),
            "original_artifact_sha256": ARTIFACT_SHA,
            "binary_sha256": binary,
            "clean_install_selftest_and_remove": True,
            "clean_seconds": clean_seconds,
            "python_account_free_preflight": True,
            "x11_xcb_free_preflight": False,
            "historical_only": True,
            "current_release_qualification": False,
            "canonical_candidate_gate": False,
            "independent_final_artifact_review_produced": False,
            "prepare_and_verify": False,
            "publication_supported": False,
            "all_platform_release_qualified": False,
            "publication_executed": False,
            "status": "historical_audit_complete_staging_refused",
        },
    )
    raise HistoricalStagingRefused(
        "Historical D9 audit completed; staging refused. "
        "Published E requires its separate exact qualification."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    def interrupted(signum, frame):
        raise KeyboardInterrupt("qualification interrupted")

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        finalize(args.artifact, args.output)
    except HistoricalStagingRefused as error:
        print(str(error), file=sys.stderr)
        return STAGING_REFUSED_EXIT
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
