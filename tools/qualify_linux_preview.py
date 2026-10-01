"""Run existing offline installed RC3 producers; never stage or publish a release.

The fetch operation downloads only checksum-pinned public prior release assets.
The run operation uses an existing image and the same-run frozen build. Its
receipt remains partial qualification pending independent Python-free install
and the unchanged final canonical candidate gate.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.candidate_qualification import (  # noqa: E402
    _native_payload,
    _source,
    digest,
)
from tools.installed_recovery_contract import verify_installed_recovery  # noqa: E402
from tools.installed_workflow_qualification import (  # noqa: E402
    verify_installed_workflow,
)
from tools.qualified_priors import (  # noqa: E402
    QUALIFIED_CHECKSUM_DOCUMENTS,
    QUALIFIED_PRIORS,
)
from tools.upgrade_smoke import verify_prior_source  # noqa: E402

VERSION = "0.5.4rc3"
MAX_DOWNLOAD = 64 * 1024 * 1024
BINARY = "/opt/neuroforge/sinter/Sinter"
PRODUCER_ENTRY = """import runpy, signal, sys
def interrupted(signum, frame):
    raise KeyboardInterrupt('qualification deadline reached')
signal.signal(signal.SIGTERM, interrupted)
producer = sys.argv.pop(1)
sys.argv[0] = producer
runpy.run_path(producer, run_name='__main__')
"""


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], *, timeout: int = 180, log: Path | None = None) -> str:
    """Bound a single producer; retain its exact output without dumping artifacts."""
    stream = log.open("w", encoding="utf-8") if log else None
    process = None
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            text=True,
            stdout=stream or subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=os.name == "posix",
        )
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # The producer bootstrap raises KeyboardInterrupt, letting its existing
            # finally blocks close browsers, remove packages and retain partial proof.
            process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
            raise
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command, output)
        return (output or "").strip()
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process is not None and os.name == "posix":
            for stop in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(process.pid, stop)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
        if stream:
            stream.close()


def fetch_priors(output: Path) -> None:
    """Get public bytes without cookies, auth, ambient proxies, retries or models."""
    output.mkdir(mode=0o700)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for prior in QUALIFIED_PRIORS.values():
        folder = output / prior.version
        folder.mkdir()
        assets = {
            f"sinter-{prior.version}-source.zip": prior.source_archive_sha256,
            f"Sinter-{prior.version}-linux-x64.deb": prior.installer_sha256,
            "SHA256SUMS.txt": QUALIFIED_CHECKSUM_DOCUMENTS.get(prior.version),
        }
        for name, expected in assets.items():
            url = (
                "https://github.com/neuroforge-io/Sinter/releases/download/"
                f"v{prior.version}/{name}"
            )
            temporary = folder / (name + ".partial")
            try:
                with (
                    opener.open(url, timeout=60) as response,
                    temporary.open("xb") as sink,
                ):
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_DOWNLOAD:
                            raise ValueError("Published prior asset exceeds its bound.")
                        sink.write(chunk)
                if expected and digest(temporary) != expected:
                    raise ValueError(
                        "Published prior asset differs from its immutable pin."
                    )
                temporary.rename(folder / name)
            finally:
                temporary.unlink(missing_ok=True)
        sums = (folder / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines()
        for name, expected in list(assets.items())[:2]:
            if f"{expected}  {name}" not in sums:
                raise ValueError(
                    "Published checksums omit a pinned source or installer."
                )
        source = folder / "source"
        source.mkdir()
        # Extraction is admitted only after the entire archive matched its reviewed pin.
        archive = folder / f"sinter-{prior.version}-source.zip"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(source)
        files = verify_prior_source(source, archive, prior)
        tracked = subprocess.check_output(
            ["git", "archive", "--format=zip", prior.source_commit],
            cwd=ROOT,
            timeout=30,
        )
        with zipfile.ZipFile(io.BytesIO(tracked)) as bundle:
            committed = {
                row.filename: hashlib.sha256(bundle.read(row)).hexdigest()
                for row in bundle.infolist()
                if not row.is_dir()
            }
        if committed != files:
            raise ValueError(
                "Published prior source differs from its pinned Git commit."
            )
        write_json(
            folder / "source-verification.json",
            {
                "schema": "sinter-prior-release-source/v1",
                "version": prior.version,
                "source_commit": prior.source_commit,
                "archive": archive.name,
                "archive_sha256": prior.source_archive_sha256,
                "sha256sums_verified": True,
                "tracked_archive_and_local_commit_files_match": True,
                "source_files": len(files),
            },
        )


def candidate_inputs(candidate: Path, commit: str) -> tuple[dict, dict, str]:
    """Refuse mismatched build/source identities before creating a container."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Provide the exact full tested source commit.")
    if run(["git", "rev-parse", "HEAD"]) != commit:
        raise ValueError("The checkout differs from the tested source commit.")
    receipt = candidate / f"Sinter-{VERSION}-linux-x64-test.json"
    if (
        receipt.is_symlink()
        or not receipt.is_file()
        or receipt.stat().st_size > 1_000_000
    ):
        raise ValueError("Provide the bounded same-run native build receipt.")
    native = json.loads(receipt.read_text(encoding="utf-8"))
    if not isinstance(native, dict):
        raise ValueError("The native build receipt must be a JSON object.")
    expected = {
        "schema": "sinter-native-test/v1",
        "version": VERSION,
        "source_commit": commit,
        "system": "Linux",
        "target_arch": "x64",
        "passed": True,
        "frozen": True,
        "package_version": "0.5.4~rc3",
        "installer": f"Sinter-{VERSION}-linux-x64.deb",
    }
    if any(
        type(native.get(k)) is not type(v) or native[k] != v
        for k, v in expected.items()
    ):
        raise ValueError("The native artifact has another source, version or target.")
    installer = candidate / native["installer"]
    if digest(installer) != native.get("installer_sha256"):
        raise ValueError("The native installer differs from its build receipt.")
    source = _source(candidate, VERSION, commit, ROOT)
    binary_sha = _native_payload(candidate, VERSION, source, native)
    return source, native, binary_sha


def _container_upgrades(
    candidate: Path, priors: Path, output: Path, commit: str
) -> None:
    """Invoke the unchanged producers against the actually installed package."""
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or not Path("/.dockerenv").is_file()
    ):
        raise ValueError("Run installer operations only in the disposable container.")
    output.mkdir()
    installer = candidate / f"Sinter-{VERSION}-linux-x64.deb"
    run(["dpkg", "-i", str(installer)], timeout=60)
    try:
        for prior in QUALIFIED_PRIORS.values():
            folder = priors / prior.version
            run(
                [
                    sys.executable,
                    "-B",
                    "tools/upgrade_smoke.py",
                    "--prior-source",
                    str(folder / "source"),
                    "--prior-source-archive",
                    str(folder / f"sinter-{prior.version}-source.zip"),
                    "--prior-version",
                    prior.version,
                    "--prior-commit",
                    prior.source_commit,
                    "--candidate-binary",
                    BINARY,
                    "--source-commit",
                    commit,
                    "--expected-version",
                    VERSION,
                    "--output",
                    str(output / ("copied-" + prior.version)),
                ],
                log=output / ("copied-" + prior.version + ".log"),
            )
    finally:
        run(["dpkg", "-r", "sinter"], timeout=60)
    for prior in QUALIFIED_PRIORS.values():
        folder = priors / prior.version
        run(
            [
                sys.executable,
                "-B",
                "tools/installed_upgrade_smoke.py",
                "--prior-source",
                str(folder / "source"),
                "--prior-source-archive",
                str(folder / f"sinter-{prior.version}-source.zip"),
                "--prior-version",
                prior.version,
                "--prior-commit",
                prior.source_commit,
                "--prior-installer",
                str(folder / f"Sinter-{prior.version}-linux-x64.deb"),
                "--prior-sha256",
                prior.installer_sha256,
                "--candidate-installer",
                str(installer),
                "--source-commit",
                commit,
                "--expected-version",
                VERSION,
                "--output",
                str(output / ("installed-" + prior.version)),
            ],
            log=output / ("installed-" + prior.version + ".log"),
        )
    if Path(BINARY).exists():
        raise ValueError("The owned installed executable remains after cleanup.")


def container_upgrades(
    candidate: Path, priors: Path, output: Path, commit: str
) -> None:
    """Return generated evidence to the host owner without widening file modes."""
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or not Path("/.dockerenv").is_file()
    ):
        raise ValueError("Run installer operations only in the disposable container.")
    if output.exists() or output.is_symlink():
        raise ValueError(
            "Choose fresh container evidence; existing output is protected."
        )
    ids = [os.environ.get(name, "") for name in ("SINTER_TEST_UID", "SINTER_TEST_GID")]
    if any(not re.fullmatch(r"\d+", value) for value in ids):
        raise ValueError("Provide numeric host ownership for the generated proof.")
    uid, gid = map(int, ids)
    try:
        _container_upgrades(candidate, priors, output, commit)
    finally:
        if output.exists():
            for path in [output, *output.rglob("*")]:
                os.chown(path, uid, gid, follow_symlinks=False)


def remove_owned_containers(owner: str) -> None:
    """Remove only containers bearing this task's unique ownership label."""
    query = [
        "docker",
        "ps",
        "--all",
        "--quiet",
        "--filter",
        f"label=sinter.qualification.owner={owner}",
    ]
    ids = run(query).split()
    if any(not re.fullmatch(r"[0-9a-f]{12,64}", value) for value in ids):
        raise ValueError("The owned container lookup returned an invalid identity.")
    if ids:
        run(["docker", "rm", "--force", *ids], timeout=30)
    if run(query):
        raise ValueError("An owned qualification container remains after cleanup.")


def qualify(
    candidate: Path, priors: Path, output: Path, commit: str, image: str
) -> dict:
    """Retain observed installed gates; independent final qualification stays open."""
    if sys.platform != "linux":
        raise ValueError("Run the installed Linux gates on a Linux host.")
    if output.exists() or output.is_symlink():
        raise ValueError(
            "Choose a fresh output directory; existing evidence is protected."
        )
    if any(
        c in str(p.resolve())
        for p in (ROOT, candidate, priors, output)
        for c in (",", "\n", "\r")
    ):
        raise ValueError("Qualification mount paths contain unsupported characters.")
    source, native, binary_sha = candidate_inputs(candidate, commit)
    image_id = run(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("The existing qualification image has no exact identity.")
    output.mkdir(mode=0o700)
    owner = uuid.uuid4().hex
    state = {
        "schema": "sinter-linux-installed-gates/v1",
        "version": VERSION,
        "source_commit": commit,
        "installer_sha256": native["installer_sha256"],
        "binary_sha256": binary_sha,
        "image_id": image_id,
        "passed": False,
        "publication_executed": False,
        "independent_clean_install": False,
        "final_candidate_gate": False,
        "copied_and_installed_priors": [],
        "installed_workflow": False,
        "installed_recovery": False,
        "timings_seconds": {},
        "owned_upgrade_container_removed": False,
        "owned_containers_removed": False,
        "owner": owner,
    }
    name = "sinter-qualification-upgrades-" + uuid.uuid4().hex
    receipt_path = output / "installed-gates.json"
    write_json(receipt_path, state)
    try:
        started = time.monotonic()
        command = [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--memory=768m",
            "--cpus=1",
            "--pids-limit=128",
            "--name",
            name,
            "--label",
            f"sinter.qualification.owner={owner}",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            f"SINTER_TEST_UID={os.getuid()}",
            "--env",
            f"SINTER_TEST_GID={os.getgid()}",
            "--mount",
            f"type=bind,src={ROOT},dst=/work,readonly",
            "--mount",
            f"type=bind,src={candidate.resolve()},dst=/candidate,readonly",
            "--mount",
            f"type=bind,src={priors.resolve()},dst=/priors,readonly",
            "--mount",
            f"type=bind,src={output.resolve()},dst=/proof",
            image_id,
            "/usr/bin/python3",
            "-B",
            "tools/qualify_linux_preview.py",
            "container",
            "--candidate",
            "/candidate",
            "--priors",
            "/priors",
            "--output",
            "/proof/upgrades",
            "--source-commit",
            commit,
        ]
        try:
            run(command, timeout=300, log=output / "upgrades.log")
        finally:
            # A timed-out Docker client can leave its container running.
            subprocess.run(
                ["docker", "rm", "--force", name],
                capture_output=True,
                timeout=30,
                check=False,
            )
            remaining = run(
                ["docker", "ps", "--all", "--quiet", "--filter", f"name=^{name}$"]
            )
            state["owned_upgrade_container_removed"] = not remaining
        state["timings_seconds"]["upgrades"] = round(time.monotonic() - started, 3)
        state["copied_and_installed_priors"] = list(QUALIFIED_PRIORS)
        args = [
            "--installer",
            str(candidate / native["installer"]),
            "--source-archive",
            str(candidate / f"sinter-{VERSION}-source.zip"),
            "--native-receipt",
            str(candidate / f"Sinter-{VERSION}-linux-x64-test.json"),
            "--installer-sha256",
            native["installer_sha256"],
            "--source-sha256",
            digest(candidate / f"sinter-{VERSION}-source.zip"),
            "--source-commit",
            commit,
            "--version",
            VERSION,
            "--image",
            image_id,
        ]
        for phase, producer in (
            ("workflow", "tools/installed_workflow_browser.py"),
            ("recovery", "tools/installed_recovery_browser.py"),
        ):
            command = [
                sys.executable,
                "-B",
                "-c",
                PRODUCER_ENTRY,
                producer,
                *args,
                "--output",
                str(output / phase),
            ]
            if phase == "recovery":
                workflow = output / "workflow/installed-workflow-browser.json"
                command.extend(
                    [
                        "--installed-workflow-receipt",
                        str(workflow),
                        "--workflow-sha256",
                        digest(workflow),
                    ]
                )
            started = time.monotonic()
            previous = os.environ.get("SINTER_QUALIFICATION_OWNER")
            os.environ["SINTER_QUALIFICATION_OWNER"] = owner
            try:
                run(command, timeout=180, log=output / (phase + ".log"))
            finally:
                if previous is None:
                    os.environ.pop("SINTER_QUALIFICATION_OWNER", None)
                else:
                    os.environ["SINTER_QUALIFICATION_OWNER"] = previous
            state["timings_seconds"][phase] = round(time.monotonic() - started, 3)
            state["installed_" + phase] = True
            write_json(receipt_path, state)
        evidence = output / "evidence"
        shutil.copytree(output / "workflow", evidence)
        shutil.copytree(output / "recovery", evidence, dirs_exist_ok=True)
        for name in (
            f"sinter-{VERSION}-source.zip",
            f"Sinter-{VERSION}-linux-x64-test.json",
        ):
            shutil.copyfile(candidate / name, evidence / name)
        sums = {
            p.relative_to(evidence).as_posix(): digest(p)
            for p in evidence.rglob("*")
            if p.is_file()
        }
        verify_installed_workflow(
            evidence, VERSION, commit, sums, source, native, binary_sha
        )
        verify_installed_recovery(
            evidence, VERSION, commit, sums, source, native, binary_sha
        )
        if not state["owned_upgrade_container_removed"]:
            raise ValueError("The owned upgrade container was not removed.")
        state["passed"] = True
        return state
    finally:
        try:
            remove_owned_containers(owner)
            state["owned_containers_removed"] = True
        except (OSError, ValueError, subprocess.SubprocessError):
            state["passed"] = False
            raise
        finally:
            write_json(receipt_path, state)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    fetch = commands.add_parser(
        "fetch", help="Download only pinned public prior artifacts"
    )
    fetch.add_argument("--output", type=Path, required=True)
    for operation in ("run", "container"):
        command = commands.add_parser(operation)
        for name in ("candidate", "priors", "output"):
            command.add_argument("--" + name, type=Path, required=True)
        command.add_argument("--source-commit", required=True)
        if operation == "run":
            command.add_argument("--image", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "fetch":
            fetch_priors(args.output)
        elif args.operation == "container":
            container_upgrades(
                args.candidate, args.priors, args.output, args.source_commit
            )
        else:
            qualify(
                args.candidate, args.priors, args.output, args.source_commit, args.image
            )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Installed RC3 gates failed; no final qualification: {error}\n")


if __name__ == "__main__":
    if os.name == "posix":

        def interrupted(signum, frame):
            raise KeyboardInterrupt(
                "qualification stopped; preserving partial evidence"
            )

        signal.signal(signal.SIGTERM, interrupted)
    main()
