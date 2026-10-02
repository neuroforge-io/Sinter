"""Four immutable published Linux packages to final RC4, with separate admission.

Run `outer --help` for the future installed route. It needs an already reviewed
shared native owner composition, actual final RC4 package and same-run receipt,
an existing immutable offline image, and four private exact prior asset trees.
This tool never builds/pulls an image or builds/downloads an installer.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import rc4_replacement_contract as contract  # noqa: E402
from tools import rc4_replacement_probe as probe  # noqa: E402
from tools.package_native import debian_package_version  # noqa: E402
from tools.published_rc3_fixture import prepare_fixture as prepare_e  # noqa: E402
from tools.published_rc3_fixture import seed_environment  # noqa: E402
from tools.upgrade_smoke import SEED, verify_prior_source  # noqa: E402

hashes = contract.hashes

BINARY = Path("/opt/neuroforge/sinter/Sinter")
STATUS = ["dpkg-query", "-W", "-f=${Status}\n${Version}\n", "sinter"]


def write(path, value):
    probe.write(path, value)


def command(argv, rows, role, directory, timeout=20, owned_group=False):
    """Retain full streams after reap, including failure/timeout diagnostics."""
    directory.mkdir(parents=True, exist_ok=True)
    outpath, errpath = directory / (role + ".stdout"), directory / (role + ".stderr")
    row = {
        "role": role,
        "argv": [str(value) for value in argv],
        "pid": None,
        "exit_code": None,
        "reaped": False,
        "stdout": None,
        "stderr": None,
    }
    with outpath.open("wb") as out, errpath.open("wb") as err:
        environment = seed_environment(directory)
        environment.update(
            {
                "LANG": "C.UTF-8",
                "TZ": "UTC",
                "HOME": str(directory),
                "TMPDIR": str(directory),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        process = subprocess.Popen(
            row["argv"],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=owned_group,
            env=environment,
        )
        row["pid"] = process.pid
        try:
            row["exit_code"] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if owned_group:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            row["exit_code"] = process.wait(timeout=2)
            if owned_group:
                row["forced_cleanup"] = True
        row["reaped"] = True
        if owned_group:
            remaining = probe.group_alive(process.pid)
            row.setdefault("forced_cleanup", remaining)
            if remaining:
                os.killpg(process.pid, signal.SIGKILL)
                deadline = time.monotonic() + 2
                while probe.group_alive(process.pid) and time.monotonic() < deadline:
                    time.sleep(0.02)
            row["group_remaining"] = probe.group_alive(process.pid)
    row["stdout"], row["stderr"] = (
        contract.blob(contract.regular(outpath)),
        contract.blob(contract.regular(errpath)),
    )
    rows.append(row)
    return row


def checked_package(
    argv, rows, role, directory, timeout=20, version=None, absent=False
):
    row = command(argv, rows, role, directory, timeout)
    body, diagnostics = (
        contract.raw_blob(row["stdout"]),
        contract.raw_blob(row["stderr"]),
    )
    if absent:
        contract.require(
            row["exit_code"] == 1
            and body == b""
            and diagnostics == b"dpkg-query: no packages found matching sinter\n",
            "Actual empty-container package absence differs.",
        )
    else:
        shared, _owner = contract.shared()
        contract.require(
            row["exit_code"] == 0
            and (
                diagnostics == b""
                or (
                    role == "remove"
                    and argv == ["dpkg", "-r", "sinter"]
                    and diagnostics == shared.SHARED_OPT_REMOVAL_WARNING
                )
            ),
            "Actual package transition failed: " + role,
        )
        if version:
            contract.require(
                body == ("install ok installed\n" + version + "\n").encode(),
                "Actual installed package status and Version differ: " + role,
            )
    return row


def prior_inputs(directory, version):
    prior = contract.select_prior(version, contract.PRIORS[version].source_commit)
    archive = directory / ("sinter-" + version + "-source.zip")
    installer = directory / ("Sinter-" + version + "-linux-x64.deb")
    checksum = directory / "SHA256SUMS.txt"
    contract.require(
        {path.name for path in directory.iterdir()}
        == {"source", archive.name, installer.name, checksum.name},
        "Prior mount needs exactly source, ZIP, DEB and checksum document.",
    )
    contract.require(
        contract.sha(contract.regular(archive)) == prior.source_archive_sha256
        and contract.sha(contract.regular(installer)) == prior.installer_sha256
        and contract.sha(contract.regular(checksum)) == contract.CHECKSUMS[version],
        "Prior source, installer or immutable checksum document differs.",
    )
    lines = contract.regular(checksum).decode("utf-8").splitlines()
    for path, digest in (
        (archive, prior.source_archive_sha256),
        (installer, prior.installer_sha256),
    ):
        contract.require(
            lines.count(digest + "  " + path.name) == 1,
            "Prior asset lacks its exact checksum document entry.",
        )
    if version == "0.5.4rc3":
        from tools.published_rc3_fixture import verify_inputs

        source_files = verify_inputs(directory / "source", archive, installer)
    else:
        source_files = verify_prior_source(directory / "source", archive, prior)
    return (
        {
            "version": version,
            "commit": prior.source_commit,
            "source_archive_sha256": prior.source_archive_sha256,
            "installer_sha256": prior.installer_sha256,
            "checksum_document_sha256": contract.CHECKSUMS[version],
            "source_files": source_files,
        },
        archive,
        installer,
    )


def fixture(directory, output, prior):
    """Use only byte-admitted published source in an isolated fictional seed."""
    if prior["version"] == "0.5.4rc3":
        receipt = prepare_e(
            SimpleNamespace(
                prior_source=directory / "source",
                prior_source_archive=directory / "sinter-0.5.4rc3-source.zip",
                prior_installer=directory / "Sinter-0.5.4rc3-linux-x64.deb",
                prior_version="0.5.4rc3",
                prior_commit=prior["commit"],
                replacement_profile=contract.VERSION,
                target="linux-x64",
                output=output,
            )
        )
        return (
            output / "original-E-workspace",
            output / "copied-for-eventual-replacement",
            json.loads((output / "fixture-originals.json").read_text(encoding="utf-8")),
            receipt,
        )
    output.mkdir()
    original, copied, expected_path = (
        output / "original",
        output / "replacement-copy",
        output / "expected.json",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-X",
            "utf8",
            "-c",
            SEED,
            str(directory / "source"),
            str(original),
            str(expected_path),
            prior["version"],
        ],
        stdin=subprocess.DEVNULL,
        env=seed_environment(output),
        capture_output=True,
        timeout=30,
        check=False,
    )
    (output / "seed.stdout").write_bytes(result.stdout)
    (output / "seed.stderr").write_bytes(result.stderr)
    contract.require(
        result.returncode == 0 and not result.stderr,
        "Published prior source seed failed.",
    )
    shutil.copytree(original, copied)
    expected = contract.json_value(contract.regular(expected_path))
    contract.require(
        expected["prior_version"] == prior["version"]
        and hashes(original) == hashes(copied),
        "Source fixture or its replacement copy differs.",
    )
    return (
        original,
        copied,
        expected,
        {"scope": "fictional published-source seed; no installed admission"},
    )


def empty_schema(output):
    """Create only an empty local schema from the already byte-admitted candidate."""
    directory = output / "empty-candidate-schema"
    program = (
        "import sys,socket;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
        "socket.socket.connect=lambda *a:(_ for _ in()).throw("
        "AssertionError('network'));"
        "from sinter.runtime import Application;"
        "app=Application(Path(sys.argv[2]));app.close()"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-X",
            "utf8",
            "-c",
            program,
            str(ROOT / "src"),
            str(directory),
        ],
        env=seed_environment(output),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=10,
    )
    (output / "empty-schema.stdout").write_bytes(result.stdout)
    (output / "empty-schema.stderr").write_bytes(result.stderr)
    contract.require(
        result.returncode == 0 and not result.stdout and not result.stderr,
        "Source-derived empty schema failed.",
    )
    from tools.published_rc3_fixture_seed import sqlite_snapshot

    return {
        name: sqlite_snapshot(directory / name)
        for name in ("workspace.sqlite3", "campaigns.sqlite3")
    }


def payload(installer, expected_version, output):
    """Read the actual published payload, never execute source as an installed app."""
    rows = []
    for field, value in (
        ("Package", "sinter"),
        ("Architecture", "amd64"),
        ("Version", debian_package_version(expected_version)),
    ):
        row = command(
            ["dpkg-deb", "-f", installer, field], rows, "control-" + field, output
        )
        contract.require(
            row["exit_code"] == 0
            and contract.raw_blob(row["stderr"]) == b""
            and contract.raw_blob(row["stdout"]) == (value + "\n").encode(),
            "Actual published package control differs.",
        )
    row = command(["dpkg-deb", "--fsys-tarfile", installer], rows, "payload", output)
    contract.require(
        row["exit_code"] == 0 and not contract.raw_blob(row["stderr"]),
        "Actual package payload could not be read.",
    )
    import io

    binary, entries = None, {}
    seen = set()
    with tarfile.open(
        fileobj=io.BytesIO(contract.raw_blob(row["stdout"], 128 * 1024 * 1024))
    ) as archive:
        for item in archive:
            name = item.name.removeprefix("./")
            contract.require(
                name not in seen
                and len(seen) < 10_000
                and not Path(name).is_absolute()
                and ".." not in Path(name).parts,
                "Unsafe or repeated payload member.",
            )
            seen.add(name)
            if name == "opt/neuroforge/sinter/Sinter":
                contract.require(
                    item.isfile() and item.size <= 128 * 1024 * 1024,
                    "Actual package executable is not a regular bounded member.",
                )
                binary = archive.extractfile(item).read()
            elif name in {
                "usr/share/applications/sinter.desktop",
                "usr/share/applications/sinter-native.desktop",
            }:
                contract.require(
                    item.isfile() and item.size <= 8192,
                    "Actual prior entry is not a bounded regular file.",
                )
                entries[Path(name).name] = contract.blob(
                    archive.extractfile(item).read()
                )
    contract.require(binary is not None, "Actual package executable is absent.")
    original_payload = row["stdout"]
    row["stdout"] = {
        "name": "payload.stdout",
        "bytes": original_payload["bytes"],
        "sha256": original_payload["sha256"],
    }
    contract.require(
        "sinter.desktop" in entries, "Actual prior package has no desktop entry."
    )
    return {
        "binary_sha256": contract.sha(binary),
        "binary_bytes": len(binary),
        "payload_sha256": original_payload["sha256"],
        "payload_bytes": original_payload["bytes"],
        "entries": entries,
    }, rows


FILESYSTEM_PROGRAM = (
    "import os,json,hashlib,stat;paths=['/opt/neuroforge/sinter/Sinter',"
    "'/usr/share/applications/sinter.desktop','/usr/share/applications/sinter-native.desktop'];"
    "result={};\n"
    "for path in paths:\n"
    " try:\n"
    "  info=os.lstat(path);result[path]={'exists':True,"
    "'mode':info.st_mode,'bytes':info.st_size,"
    "'sha256':hashlib.sha256(open(path,'rb').read()).hexdigest() "
    "if stat.S_ISREG(info.st_mode) else None}\n"
    " except FileNotFoundError as exc:result[path]={'exists':False,'errno':exc.errno}\n"
    "print(json.dumps(result,sort_keys=True,separators=(',',':')))"
)


def filesystem_probe(phase, receipt, output):
    row = command(
        ["python3", "-I", "-S", "-B", "-c", FILESYSTEM_PROGRAM],
        receipt["filesystem_commands"],
        phase,
        output,
    )
    contract.require(
        row["exit_code"] == 0 and not contract.raw_blob(row["stderr"]),
        "Actual installed filesystem probe failed.",
    )
    return contract.json_value(contract.raw_blob(row["stdout"]))


def inner(args):
    contract.require(
        os.geteuid() == 0
        and Path("/.dockerenv").is_file()
        and args.output == Path("/out/run")
        and args.candidate == Path("/candidate")
        and args.repository == Path("/repository")
        and ROOT == Path("/source"),
        "Actual installed route requires a disposable root Docker container.",
    )
    shared, owner = contract.shared()
    args.output.mkdir(mode=0o755, parents=True)
    receipt = {
        "schema": contract.SCHEMA,
        "failure": None,
        "cleanup_failure": None,
        "package_commands": [],
        "probes": {},
        "snapshots": {},
        "filesystem": {},
        "filesystem_commands": [],
    }
    receipt["filesystem"]["initial"] = filesystem_probe(
        "initial", receipt, args.output / "fs"
    )
    write(args.output / "replacement.json", receipt)
    installation_attempted = False
    try:
        source = owner.selected_source_identity(args, [])
        contract.require(
            source["version"] == contract.VERSION,
            "Only final 0.5.4rc4 source can run this route.",
        )
        args.installer = args.candidate / "Sinter-0.5.4rc4-linux-x64.deb"
        args.package_receipt = args.candidate / "Sinter-0.5.4rc4-linux-x64-test.json"
        contract.require(
            {path.name for path in args.candidate.iterdir()}
            == {args.installer.name, args.package_receipt.name},
            "Candidate mount has extra inputs.",
        )
        package = owner.package_preflight(args, source, [])
        prior, _archive, prior_deb = prior_inputs(Path("/prior"), args.prior_version)
        prior_payload, metadata = payload(
            prior_deb, args.prior_version, args.output / "prior-payload"
        )
        original, copied, expected, seed_receipt = fixture(
            Path("/prior"), args.output / "fixture", prior
        )
        receipt.update(
            source=source,
            package=package,
            prior=prior,
            prior_payload=prior_payload,
            prior_metadata=metadata,
            fixture=seed_receipt,
            expected=expected,
            original_hashes=hashes(original),
            empty_schema=empty_schema(args.output),
        )
        receipt["snapshots"]["before"] = contract.snapshot(copied)
        rows = receipt["package_commands"]
        checked_package(
            STATUS, rows, "initial-absence", args.output / "commands", absent=True
        )
        contract.require(
            rows[-1]["exit_code"] == 1
            and not any(v["exists"] for v in receipt["filesystem"]["initial"].values()),
            "The disposable container is not initially empty.",
        )
        installation_attempted = True
        checked_package(
            ["dpkg", "-i", prior_deb],
            rows,
            "install-prior",
            args.output / "commands",
            60,
        )
        checked_package(
            STATUS,
            rows,
            "prior-status",
            args.output / "commands",
            version=debian_package_version(prior["version"]),
        )
        receipt["filesystem"]["prior"] = filesystem_probe(
            "prior", receipt, args.output / "fs"
        )
        contract.require(
            contract.sha(contract.regular(BINARY)) == prior_payload["binary_sha256"],
            "Installed prior executable differs from its pinned package payload.",
        )
        receipt["probes"]["prior"] = probe.run(
            [str(BINARY)],
            prior["version"],
            copied,
            expected,
            args.output / "prior",
            None,
            binary_sha=prior_payload["binary_sha256"],
            runtime=Path("/out/bridge/prior"),
            phase="prior",
        )
        receipt["snapshots"]["prior"] = contract.snapshot(copied)
        protocol_before = args.output / "prior-protocol-workspace"
        shutil.copytree(copied, protocol_before)
        receipt["probes"]["prior-protocol"] = probe.run(
            [str(BINARY)],
            prior["version"],
            protocol_before,
            expected,
            args.output / "prior-protocol",
            None,
            protocol_mode=True,
            binary_sha=prior_payload["binary_sha256"],
            runtime=Path("/out/bridge/prior-protocol"),
            phase="prior-protocol",
        )
        receipt["snapshots"]["prior-protocol"] = contract.snapshot(protocol_before)
        checked_package(
            STATUS,
            rows,
            "prior-status-after",
            args.output / "commands",
            version=debian_package_version(prior["version"]),
        )
        # No removal occurs between these actual installed prior/candidate observations.
        checked_package(
            ["dpkg", "-i", args.installer],
            rows,
            "replace",
            args.output / "commands",
            60,
        )
        checked_package(
            STATUS,
            rows,
            "candidate-status",
            args.output / "commands",
            version="0.5.4~rc4",
        )
        contract.require(
            contract.sha(contract.regular(BINARY)) == package["binary_sha256"],
            "Installed RC4 executable differs from same-run package payload.",
        )
        receipt["filesystem"]["candidate"] = filesystem_probe(
            "candidate", receipt, args.output / "fs"
        )
        for phase in ("candidate", "candidate-cold"):
            receipt["probes"][phase] = probe.run(
                [str(BINARY)],
                contract.VERSION,
                copied,
                expected,
                args.output / phase,
                None,
                binary_sha=package["binary_sha256"],
                runtime=Path("/out/bridge") / phase,
                phase=phase,
            )
            receipt["snapshots"][phase] = contract.snapshot(copied)
            if phase == "candidate":
                protocol_after = args.output / "candidate-protocol-workspace"
                shutil.copytree(copied, protocol_after)
                receipt["probes"]["candidate-protocol"] = probe.run(
                    [str(BINARY)],
                    contract.VERSION,
                    protocol_after,
                    expected,
                    args.output / "candidate-protocol",
                    None,
                    protocol_mode=True,
                    binary_sha=package["binary_sha256"],
                    runtime=Path("/out/bridge/candidate-protocol"),
                    phase="candidate-protocol",
                )
                receipt["snapshots"]["candidate-protocol"] = contract.snapshot(
                    protocol_after
                )
            checked_package(
                STATUS,
                rows,
                "candidate-status-after"
                if phase == "candidate"
                else "cold-status-after",
                args.output / "commands",
                version="0.5.4~rc4",
            )
        receipt["original_hashes_after"] = hashes(original)
        receipt["prior_inputs_after"] = prior_inputs(
            Path("/prior"), args.prior_version
        )[0]
        receipt["candidate_source_after"] = owner.selected_source_identity(args, [])
    except BaseException as exc:
        receipt["failure"] = str(exc)
        raise
    finally:
        # Preserve failures before cleanup and retain actual removal observations.
        write(args.output / "replacement.json", receipt)
        try:
            if installation_attempted:
                checked_package(
                    ["dpkg", "-r", "sinter"],
                    receipt["package_commands"],
                    "remove",
                    args.output / "commands",
                    60,
                )
                command(
                    STATUS,
                    receipt["package_commands"],
                    "removed-status",
                    args.output / "commands",
                )
            receipt["filesystem"]["removed"] = filesystem_probe(
                "removed", receipt, args.output / "fs"
            )
        except BaseException as cleanup_error:
            receipt["cleanup_failure"] = str(cleanup_error)
            if receipt["failure"] is None:
                raise
        finally:
            # The enclosing host output tree remains private (0700). Make only
            # this fictional, closed inner evidence readable to its host owner.
            try:
                entries = contract.tree_entries(args.output)
                os.chmod(args.output, 0o755)
                for path, info in entries:
                    os.chmod(path, 0o755 if stat.S_ISDIR(info.st_mode) else 0o644)
            except BaseException as permission_error:
                previous = receipt["cleanup_failure"]
                receipt["cleanup_failure"] = (
                    (str(previous) + "; " if previous else "")
                    + "Evidence permission/inventory failure: "
                    + str(permission_error)
                )
                if receipt["failure"] is None:
                    raise
            finally:
                write(args.output / "replacement.json", receipt)
    return receipt


def start_with_collectors(start, folder, chromium, records, browser_tmp):
    """Attach once while the fixed host collector observes each live inner phase."""
    result, failures = [], []

    def attach():
        try:
            result.append(start())
        except BaseException as exc:
            failures.append(str(exc))

    thread = threading.Thread(target=attach, name="replacement-container-attach")
    thread.start()
    try:
        for phase in contract.RUN_ORDER:
            runtime = folder / "bridge" / phase
            deadline = time.monotonic() + 240
            while not (runtime / "state.json").exists() and time.monotonic() < deadline:
                contract.require(
                    thread.is_alive(),
                    "Installed owner ended before host phase: " + phase,
                )
                time.sleep(0.02)
            contract.require(
                (runtime / "state.json").exists(),
                "Installed owner did not publish its bounded phase.",
            )
            argv = contract.collector_argv(folder, chromium, phase, browser_tmp)
            row = command(
                argv, records, phase, folder / "host-streams", 100, owned_group=True
            )
            write(folder / (phase + "-collector-command.json"), row)
            contract.require(
                row["exit_code"] == 0
                and row["reaped"] is True
                and row["forced_cleanup"] is False
                and row["group_remaining"] is False,
                "Host collector failed; complete diagnostics retained.",
            )
    finally:
        # The attach operation has its own unchanged 240-second bound. Never
        # start a second container or collector after a lost reply/failure.
        thread.join(timeout=245)
    contract.require(
        not thread.is_alive() and not failures and len(result) == 1,
        "Installed attach failed or left its owning thread: " + str(failures),
    )
    return result[0]


def inspected_json(row):
    contract.require(
        type(row["exit_code"]) is int
        and row["exit_code"] == 0
        and row["reaped"] is True
        and type(row["pid"]) is int
        and row["pid"] > 1
        and not contract.raw_blob(row["stderr"]),
        "Actual Docker inspection command failed.",
    )
    value = contract.json_value(contract.raw_blob(row["stdout"]))
    contract.require(
        type(value) is list and len(value) == 1 and type(value[0]) is dict,
        "Actual Docker inspection is not one closed observation.",
    )
    return value[0]


def created_identifier(row):
    raw = contract.raw_blob(row["stdout"])
    contract.require(
        type(row["exit_code"]) is int
        and row["exit_code"] == 0
        and row["reaped"] is True
        and type(row["pid"]) is int
        and row["pid"] > 1
        and __import__("re").fullmatch(rb"[0-9a-f]{64}\n", raw),
        "Actual Docker create did not return its exact owned full ID.",
    )
    return raw[:-1].decode("ascii")


def retain_host_after(bundle, folder, chromium, browser_tmp, primary):
    """Independently read all after identities and retain original failure bytes."""
    after, errors, observation_error = contract.observe_host_identity(
        chromium, browser_tmp
    )
    bundle["host"]["after"], bundle["host"]["after_errors"] = after, errors
    if errors:
        previous = bundle["cleanup_failure"]
        bundle["cleanup_failure"] = (
            (str(previous) + "; " if previous else "")
            + "Host after observations failed: "
            + contract.encoded(errors)
        )
    publication = probe.EvidencePublisher(
        "OUTER-HOST",
        primary if primary is not None else observation_error,
        [contract.encoded(error) for error in errors],
    )
    publication.attempt(folder / "outer.json", bundle)
    publication.finish(folder / "outer-host-failed.json")


def outer(args):
    contract.require(
        os.name == "posix", "Actual Linux replacement needs its POSIX host owner."
    )
    shared, owner = contract.shared()
    contract.private_paths(args, ROOT)
    contract.require(
        contract.sha(contract.regular(Path(__file__))) == args.outer_owner_sha256,
        "Actual outer owner differs from its independent review pin.",
    )
    contract.require(
        not args.output.exists(), "Choose fresh output; prior failures are preserved."
    )
    source = owner.source_identity(args.repository, args.source_commit, [])
    contract.require(
        source["version"] == contract.VERSION, "Use committed final 0.5.4rc4 source."
    )
    args.installer = args.candidate / "Sinter-0.5.4rc4-linux-x64.deb"
    args.package_receipt = args.candidate / "Sinter-0.5.4rc4-linux-x64-test.json"
    package = owner.package_preflight(args, source, [])
    browser_tmp = args.owned_root / "t"
    contract.require(
        not browser_tmp.exists() and len(os.fsencode(browser_tmp)) <= 55,
        "Choose a fresh short owned browser temporary directory.",
    )
    browser_tmp.mkdir(mode=0o700)
    contract.host_identity(args.chromium, browser_tmp)
    contract.require(
        set(path.name for path in args.priors.iterdir()) == set(contract.PRIORS),
        "The replacement matrix needs exactly four prior trees.",
    )
    for version in contract.PRIORS:
        prior_inputs(args.priors / version, version)
    args.output.mkdir(mode=0o700, parents=True)
    stage = args.output / "staging"
    stage.mkdir()
    archive = subprocess.check_output(
        ["git", "-C", str(args.repository), "archive", args.source_commit], timeout=20
    )
    (stage / owner.ARCHIVE_NAME).write_bytes(archive)
    write(stage / owner.ORIGIN_NAME, owner.archive_origin(source, len(archive)))
    results = {}
    for version in contract.PRIORS:
        folder = args.output / version
        folder.mkdir()
        bridge = folder / "bridge"
        bridge.mkdir(mode=0o700)
        for phase in contract.RUN_ORDER:
            runtime = bridge / phase
            runtime.mkdir(mode=0o700)
            contract.require(
                len(os.fsencode(runtime / "relay.sock")) < 108,
                "Choose a shorter owned root for the Unix relay.",
            )
        pins = {
            "image_id": args.image_id,
            "source_commit": args.source_commit,
            "source_directory": str(ROOT),
            "repository": str(stage.resolve()),
            "prior_directory": str((args.priors / version).resolve()),
            "candidate_directory": str(args.candidate.resolve()),
            "output_directory": str(folder.resolve()),
            "prior_version": version,
        }
        # Staging and output are deliberately siblings, never ancestor aliases.
        shared.private_mounts(pins, contract.MOUNTS)
        name = "sinter-native-entry-" + uuid.uuid4().hex[:12]
        rows, identifier, inspected_owned, start_attempted = [], None, False, False
        host = {
            "schema": "sinter-rc4-host-tools/v1",
            "boundary": contract.host_tools.BOUNDARY,
            "before": contract.host_identity(args.chromium, browser_tmp),
            "after": None,
            "after_errors": [],
        }
        bundle = {
            "schema": "sinter-rc4-replacement-owner/v2",
            "owner_sha256": args.outer_owner_sha256,
            "pins": pins,
            "commands": rows,
            "failure": None,
            "cleanup_failure": None,
            "host": host,
            "collectors": [],
        }

        def invoke(argv, role, timeout=20):
            row = command(argv, [], role, folder / "outer-streams", timeout)
            # The shared seven-role schema excludes PID; full post-reap PID is retained
            # separately in the raw stream sidecar rather than broadening that contract.
            write(folder / (role + "-command.json"), row)
            rows.append({key: value for key, value in row.items() if key != "pid"})
            for key in ("stdout", "stderr"):
                raw = contract.raw_blob(rows[-1][key], 128 * 1024 * 1024)
                rows[-1][key] = {
                    **contract.blob(raw[:65_536]),
                    "bytes": len(raw),
                    "sha256": contract.sha(raw),
                    "text": raw[:65_536].decode("utf-8", errors="replace"),
                    "truncated": len(raw) > 65_536,
                }
            write(folder / "outer.json", bundle)
            return row

        try:
            image = invoke(["docker", "image", "inspect", args.image_id], "image")
            inspected_json(image)
            shared.validate_image(contract.raw_blob(image["stdout"]), pins)
            created = invoke(contract.outer_argv(pins, name), "create")
            identifier = created_identifier(created)
            contract.require(
                not contract.raw_blob(created["stderr"]),
                "Actual Docker create emitted unsupported diagnostics.",
            )
            observed = invoke(["docker", "inspect", identifier], "created")
            shared.validate_container_observation(
                inspected_json(observed),
                pins,
                contract.outer_argv,
                name,
                identifier,
                "created",
                contract.MOUNTS,
            )
            inspected_owned = True
            start_attempted = True
            started = start_with_collectors(
                lambda: invoke(["docker", "start", "-a", identifier], "start", 240),
                folder,
                args.chromium,
                bundle["collectors"],
                browser_tmp,
            )
            invoke(["docker", "inspect", identifier], "exited")
            contract.require(
                started["exit_code"] == 0,
                "Actual owning installed process failed or timed out.",
            )
        except BaseException as exc:
            bundle["failure"] = str(exc)
            raise
        finally:
            try:
                if identifier:
                    if start_attempted and not any(
                        row["role"] == "exited" for row in rows
                    ):
                        try:
                            invoke(["docker", "inspect", identifier], "exited")
                        except BaseException as status_error:
                            bundle["cleanup_failure"] = (
                                "Post-run status failed: " + str(status_error)
                            )
                    removed = invoke(["docker", "rm", identifier], "remove")
                    invoke(["docker", "inspect", identifier], "removed")
                    if removed["exit_code"] != 0 and inspected_owned:
                        cleanup = []
                        command(
                            ["docker", "rm", "-f", identifier],
                            cleanup,
                            "forced-removal",
                            folder / "cleanup",
                            8,
                        )
                        command(
                            ["docker", "inspect", identifier],
                            cleanup,
                            "forced-absence",
                            folder / "cleanup",
                            8,
                        )
                        write(folder / "forced-cleanup.json", cleanup)
                        bundle["cleanup_failure"] = (
                            "Normal removal failed; forced cleanup cannot qualify."
                        )
                    shared.validate_removal(rows[-2], rows[-1], identifier)
            except BaseException as cleanup_error:
                bundle["cleanup_failure"] = str(cleanup_error)
                if bundle["failure"] is None:
                    raise
            finally:
                retain_host_after(
                    bundle, folder, args.chromium, browser_tmp, sys.exc_info()[1]
                )
        contract.host_tools.validate_host_pair(host)
        shared.validate_lifecycle(rows, pins, contract.outer_argv, contract.MOUNTS)
        results[version] = {
            "outer": str(folder / "outer.json"),
            "inner": str(folder / "run/replacement.json"),
        }
    result = {
        "schema": contract.MATRIX_SCHEMA,
        "scope": "producer output; independent verification required",
        "source": source,
        "package": package,
        "runs": results,
    }
    write(args.output / "matrix.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("outer", "inner"):
        child = sub.add_parser(mode)
        child.add_argument("--repository", type=Path, required=True)
        child.add_argument("--source-commit", required=True)
        child.add_argument("--candidate", type=Path, required=True)
        child.add_argument("--output", type=Path, required=True)
        if mode == "outer":
            child.add_argument("--priors", type=Path, required=True)
            child.add_argument("--image-id", required=True)
            child.add_argument("--outer-owner-sha256", required=True)
            child.add_argument("--owned-root", type=Path, required=True)
            child.add_argument("--chromium", type=Path, required=True)
        else:
            child.add_argument(
                "--prior-version", choices=list(contract.PRIORS), required=True
            )
            child.add_argument("--source-route", choices=["archive"], required=True)
    args = parser.parse_args(argv)
    try:
        result = outer(args) if args.mode == "outer" else inner(args)
    except probe.EvidenceFailure as exc:
        # Full failed publication bytes remain available to the owning caller.
        sys.stderr.write(contract.encoded(exc.as_record()) + "\n")
        raise SystemExit(1) from exc
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(
            1,
            "Replacement producer refused; retained diagnostics are not a pass: "
            + str(exc)
            + "\n",
        )
    print(
        "Replacement observations retained; run the independent replacement contract."
    )
    return result


if __name__ == "__main__":
    main()
