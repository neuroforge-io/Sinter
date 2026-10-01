"""Review/stage the original RC3 artifact; never publish or change its identity."""

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
    UNQUALIFIED,
    _canonical_roles,
    _native_payload,
    _source,
    digest,
    independent_review_checks,
    prior_roles,
    verify_rc3_terminal_notices,
)
from tools.candidate_release import prepare, verify_plan  # noqa: E402
from tools.qualified_priors import QUALIFIED_PRIORS  # noqa: E402
from tools.qualify_linux_preview import run as run_owned  # noqa: E402
from tools.release_manifest import assemble  # noqa: E402

VERSION = "0.5.4rc3"
COMMIT = "d9b36a6853bab0d715dc91e726f984a8ab16a747"
ARTIFACT_SHA = "ef70ac114f3de900431f2115b93116d5d8b692b80cc07312fb8a873a58192661"
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
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
    raw, folder, review, proof = (
        output / name
        for name in ("raw", "canonical", "independent-review", "clean-proof")
    )
    with zipfile.ZipFile(artifact) as archive:
        archive.extractall(raw)
    native = canonical(raw, folder)
    source = _source(folder, VERSION, COMMIT, ROOT)
    binary = _native_payload(folder, VERSION, source, native)
    started = time.monotonic()
    clean_install(folder, proof, native, binary)
    clean_seconds = round(time.monotonic() - started, 3)
    # The original candidate contains exactly one architecture receipt. Upgrade
    # receipts in the canonical folder must not contaminate this negative test.
    write(folder / "full-publisher-gate.json", publisher_negative(raw / "candidate"))
    os_release = (proof / "os-release.txt").read_text()
    baseline = {
        key: native[key] for key in ("system", "machine", "pointer_bits", "python")
    }
    baseline.update(
        libc=["glibc", "2.35"],
        os_release=os_release,
        network="disabled container; loopback only",
        host_installation=False,
    )
    write(folder / "qualification-runtime.json", baseline)
    manifest = {
        "schema": "sinter-preview-qualification/v1",
        "version": VERSION,
        "source_commit": COMMIT,
        "prior_source_commit": QUALIFIED_PRIORS["0.5.3"].source_commit,
        "prior_native_installer_sha256": QUALIFIED_PRIORS["0.5.3"].installer_sha256,
        "prerelease": True,
        "all_platform_release_qualified": False,
        "normal_package_upgrade_order_verified": True,
        "installed_runtime_and_copied_upgrade_passed": True,
        "published_native_installer_replacement_passed": True,
        "actual_debian_archive_notice_bytes_verified": True,
        "linux_shared_library_notices_verified": True,
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
        "unqualified_targets": UNQUALIFIED,
        "runtime_baseline": baseline,
        "publisher_signed": False,
        "notarised": False,
    }
    for old, new in [
        ("0.5.3", "0.5.4~rc1"),
        ("0.5.4~rc1", "0.5.4~rc2"),
        ("0.5.4~rc2", "0.5.4~rc3"),
        ("0.5.4~rc3", "0.5.4"),
    ]:
        command(["dpkg", "--compare-versions", old, "lt", new])
    manifest["artifacts"] = [
        {
            "path": p.relative_to(folder).as_posix(),
            "sha256": digest(p),
            "bytes": p.stat().st_size,
        }
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    ]
    write(folder / "candidate-qualification.json", manifest)
    (folder / "SHA256SUMS.txt").write_text(
        "".join(
            f"{digest(p)}  {p.relative_to(folder).as_posix()}\n"
            for p in sorted(folder.rglob("*"))
            if p.is_file() and p.name != "SHA256SUMS.txt"
        )
    )
    _canonical_roles(folder, VERSION, native)
    review.mkdir()
    for filename in (
        "clean-ubuntu-installed-test.json",
        "clean-ubuntu-installed-test.log",
    ):
        shutil.copyfile(proof / filename, review / filename)
    write(
        review / "qualification-context.json",
        {
            "qualification_policy_commit": command(["git", "rev-parse", "HEAD"]),
            "version": VERSION,
            "source_commit": COMMIT,
            "installer_sha256": native["installer_sha256"],
            "container": "ubuntu:22.04",
            "network": "disabled",
            "host_installation": False,
            "product_edits": False,
            "preinstalled_python": False,
            "preinstalled_account_packages": False,
            "clean_container": json.loads((proof / "container.json").read_bytes()),
        },
    )
    checks = independent_review_checks(VERSION)
    independent = {
        "qualification_policy_commit": command(["git", "rev-parse", "HEAD"]),
        "schema": "sinter-independent-final-artifact-review/v1",
        "version": VERSION,
        "source_commit": COMMIT,
        "checks": dict.fromkeys(checks, True),
        "installer_sha256": digest(folder / native["installer"]),
        "native_archive_sha256": digest(folder / f"Sinter-{VERSION}-linux-x64.tar.gz"),
        "source_archive_sha256": digest(folder / f"sinter-{VERSION}-source.zip"),
        "portable_sha256": digest(folder / f"sinter-{VERSION}.pyz"),
    }
    write(review / "final-artifact-review.json", independent)
    plan = prepare(folder, review, output / "stage", VERSION, COMMIT)
    verified = verify_plan(plan)
    write(
        output / "final-qualification.json",
        {
            "schema": "sinter-rc3-final-qualification/v1",
            "source_commit": COMMIT,
            "original_artifact_sha256": ARTIFACT_SHA,
            "binary_sha256": binary,
            "independent_clean_install": True,
            "clean_seconds": clean_seconds,
            "canonical_candidate_gate": True,
            "prepare_and_verify": True,
            "all_platform_release_qualified": False,
            "publication_executed": False,
            "manifest_sha256": digest(plan),
            "verification": verified["verification"],
        },
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    def interrupted(signum, frame):
        raise KeyboardInterrupt("qualification interrupted")

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        finalize(args.artifact, args.output)
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    main()
