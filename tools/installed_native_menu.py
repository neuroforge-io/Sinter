"""Own a Linux container install, native-entry Tk save/reopen, and removal check.

This new proof is separate from the unchanged mapped-window v1 receipt. It
invokes the byte-admitted entry command, not a physical menu. It does not prove
browser ownership, full native editing, an installer upgrade or RC4 readiness.
Never run this on a host or an existing installation.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import io
import json
import os
import platform
import re
import secrets
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from sinter.casebooks import validate  # noqa: E402
from tools import native_window_smoke as native  # noqa: E402
from tools.installed_menu_browser import menu_command  # noqa: E402
from tools.installed_native_tk import FIXTURE  # noqa: E402
from tools.package_native import (  # noqa: E402
    debian_package_version,
    linux_desktop_entries,
)

BINARY = Path("/opt/neuroforge/sinter/Sinter")
ENTRY_DIR = Path("/usr/share/applications")
OWN_PATHS = (
    "tools/installed_native_menu.py",
    "tools/installed_native_tk.py",
    "tools/native_window_smoke.py",
    "tools/installed_native_entry_contract.py",
)
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_MEMBER = 128 * 1024 * 1024
MAX_ENTRIES = 4000
FILESYSTEM_PROBE = "import json,os,sys;print(json.dumps([{'path':p,'lexists':os.path.lexists(p)} for p in sys.argv[1:]],sort_keys=True))"


def observed_absence(paths, commands):
    """Retain a separately reaped filesystem probe, not an asserted cleanup flag."""
    paths = list(map(str, paths))
    code, raw = command(
        [sys.executable, "-B", "-c", FILESYSTEM_PROBE, *paths], commands
    )
    if (
        code
        or commands[-1]["stderr"]["bytes"]
        or not native.same_json(
            json.loads(raw), [{"path": path, "lexists": False} for path in paths]
        )
    ):
        raise ValueError("Owned path absence was not observed by the actual probe.")
    return {"paths": paths, "command_index": len(commands) - 1}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def exact_text(value, pattern, name):
    if type(value) is not str or not re.fullmatch(pattern, value):
        raise ValueError("Use an exact " + name + " identity.")
    return value


def stream_record(stream):
    row = {}
    native.capture_stderr(stream, row)
    return {
        key.removeprefix("stderr").lstrip("_") or "text": value
        for key, value in row.items()
    }


def command(
    argv, rows, *, env=None, timeout=20, limit=65536, redact=(), save_streams=None
):
    """Bound children; body errors outrank cleanup, then capture errors."""
    arguments = list(map(str, argv))
    observed = arguments.copy()
    for index in redact:
        observed[index] = "<private owned X authorization>"
    row = {"argv": observed, "passed": False}
    rows.append(row)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(
            arguments,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        row["pid"] = process.pid
        body_error = cleanup_error = capture_error = None
        try:
            process.wait(timeout=timeout)
        except BaseException as error:
            body_error = error
            if redact and isinstance(error, subprocess.TimeoutExpired):
                error.cmd = observed.copy()
            row["body_error_type"] = type(error).__name__
        try:
            native.stop_process(process, row)
        except BaseException as error:
            cleanup_error = error
            row["cleanup_error_type"] = type(error).__name__
        row["streams_complete"] = (
            getattr(process, "poll", lambda: None)() is not None
            and row.get("owned_group_remaining") is False
        )
        for name, stream in (("stdout", out), ("stderr", err)):
            try:
                row[name] = stream_record(stream)
                if save_streams is not None:
                    stream.seek(0)
                    with Path(save_streams[name]).open("xb") as sink:
                        while block := stream.read(65536):
                            sink.write(block)
                    row[name + "_file"] = str(save_streams[name])
            except BaseException as error:
                if capture_error is None:
                    capture_error = error
                row[name + "_capture_error_type"] = type(error).__name__
        if body_error or cleanup_error or capture_error:
            raise body_error or cleanup_error or capture_error
        if row.get("forced_cleanup") or row.get("owned_group_remaining"):
            raise RuntimeError("An owned qualification command needed forced cleanup.")
        out.seek(0)
        raw = out.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Qualification command output exceeds its bound.")
        row["passed"] = row["exit_code"] == 0
        return row["exit_code"], raw


def source_identity(repository, commit, commands):
    exact_text(commit, r"[0-9a-f]{40}", "source")
    code, archive = command(
        ["git", "-C", repository, "archive", commit], commands, limit=MAX_ARCHIVE
    )
    if code:
        raise ValueError("The exact source archive cannot be read.")
    return archive_identity(archive, commit)


def archive_identity(archive, commit):
    records = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        for item in bundle:
            if item.isdir():
                continue
            if (
                not item.isfile()
                or item.name in records
                or len(records) >= MAX_ENTRIES
                or item.size > MAX_MEMBER
            ):
                raise ValueError(
                    "Source archive contains an unsupported or repeated member."
                )
            path = Path(item.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Source archive member is unsafe.")
            raw = bundle.extractfile(item).read()
            if regular_bytes(ROOT / path, MAX_MEMBER) != raw:
                raise ValueError("Candidate source differs at " + item.name)
            records[item.name] = {"bytes": len(raw), "sha256": digest(raw)}
    if not set(OWN_PATHS).issubset(records):
        raise ValueError(
            "This source does not contain the installed native-entry producer."
        )
    actual_paths = {
        str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if not path.is_dir()
    }
    if actual_paths != set(records):
        raise ValueError(
            "Execute only the complete exact source archive, without extra files."
        )
    tree = ast.parse((ROOT / "src/sinter/__init__.py").read_text(encoding="utf-8"))
    versions = [
        n.value.value
        for n in tree.body
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "__version__"
        and isinstance(n.value, ast.Constant)
        and type(n.value.value) is str
    ]
    if len(versions) != 1:
        raise ValueError("Candidate source version is unavailable or ambiguous.")
    return {
        "commit": commit,
        "version": versions[0],
        "archive_sha256": digest(archive),
        "files": records,
        "producer_sha256": records[OWN_PATHS[0]]["sha256"],
        "driver_sha256": records[OWN_PATHS[1]]["sha256"],
        "checker_sha256": records[OWN_PATHS[2]]["sha256"],
    }


ARCHIVE_NAME = "committed-source.tar"
ORIGIN_NAME = "committed-source.json"
ARCHIVE_READ = (
    "import pathlib,sys;sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())"
)
ARCHIVE_INNER_SCHEMA = "sinter-installed-native-entry-archive-test/v1"


def strict_archive(archive, commit):
    """Accept only bounded exact Git tar members and the bound full revision."""
    exact_text(commit, r"[0-9a-f]{40}", "source")
    if type(archive) is not bytes or len(archive) > MAX_ARCHIVE:
        raise ValueError("Source archive exceeds its closed byte bound.")
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        if bundle.pax_headers != {"comment": commit}:
            raise ValueError(
                "Source archive origin/revision differs from the actual Git commit."
            )
        for item in bundle:
            name = item.name.rstrip("/") if item.isdir() else item.name
            path = Path(name)
            if (
                not name
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or str(path) != name
                or name in seen
                or len(seen) >= MAX_ENTRIES
                or "__pycache__" in path.parts
                or path.suffix == ".pyc"
                or item.pax_headers != {"comment": commit}
            ):
                raise ValueError(
                    "Source archive has redirected, duplicate, extra/cache or noncanonical members."
                )
            seen.add(name)
            target = ROOT / name
            if not target.exists() or target.is_symlink():
                raise ValueError("Source archive has extra or redirected members.")
            if item.isdir():
                if not target.is_dir():
                    raise ValueError("Source directory member type differs.")
                if item.size != 0:
                    raise ValueError("Source directory has an invalid size.")
            elif item.isfile():
                if not 0 <= item.size <= MAX_MEMBER:
                    raise ValueError("Source member exceeds its closed size bound.")
                raw = bundle.extractfile(item).read(MAX_MEMBER + 1)
                if len(raw) != item.size:
                    raise ValueError(
                        "Source member type/size differs from its original bytes."
                    )
            else:
                raise ValueError(
                    "Source archive links/special member types are refused."
                )
    if seen != {str(path.relative_to(ROOT)) for path in ROOT.rglob("*")}:
        raise ValueError("Source archive complete member set differs.")
    return archive_identity(archive, commit)


def archive_origin(source, archive_bytes):
    return {
        "schema": "sinter-bound-git-source-archive/v1",
        "source": source,
        "archive": {"bytes": archive_bytes, "sha256": source["archive_sha256"]},
    }


def unique_origin(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate source origin key.")
        value[key] = item
    return value


def archive_source_identity(repository, commit, commands, observations=None):
    """Read only the fixed source files; host verification re-archives real Git."""
    if observations is not None and (type(observations) is not dict or observations):
        raise ValueError("Use a fresh archive source observation.")
    repository = Path(repository)
    if repository.resolve(strict=True) != repository:
        raise ValueError("Source archive repository must not redirect.")
    path = repository / ARCHIVE_NAME
    original = regular_bytes(path, MAX_ARCHIVE)
    code, archive = command(
        [sys.executable, "-B", "-c", ARCHIVE_READ, path], commands, limit=MAX_ARCHIVE
    )
    if code or archive != original or commands[-1]["stderr"]["bytes"]:
        raise ValueError("Original source archive could not be read exactly.")
    source = strict_archive(archive, commit)
    raw = regular_bytes(repository / ORIGIN_NAME, 2 * 1024 * 1024)
    origin = json.loads(raw, object_pairs_hook=unique_origin)
    if not native.same_json(origin, archive_origin(source, len(archive))):
        raise ValueError("Source archive manifest/origin/revision differs.")
    if observations is not None:
        observations.update(
            {
                "schema": "sinter-bound-git-source-archive-observed/v1",
                "archive_name": ARCHIVE_NAME,
                "origin_name": ORIGIN_NAME,
                "origin": {
                    "bytes": len(raw),
                    "sha256": digest(raw),
                    "base64": base64.b64encode(raw).decode("ascii"),
                },
            }
        )
    return source


def selected_source_identity(args, commands, observations=None):
    route = getattr(args, "source_route", "git")
    if route == "git":
        return source_identity(args.repository, args.source_commit, commands)
    if route == "archive":
        return archive_source_identity(
            args.repository, args.source_commit, commands, observations
        )
    raise ValueError("Unsupported source producer/route override.")


def regular_bytes(path, limit):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError("Use a bounded regular non-symlink file: " + str(path))
    with path.open("rb") as stream:
        actual = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (
            actual.st_dev,
            actual.st_ino,
        ) or not stat.S_ISREG(actual.st_mode):
            raise ValueError("The qualification file changed while opening.")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("The qualification file exceeds its bound.")
    return raw


def package_members(raw):
    required = {
        "opt/neuroforge/sinter/Sinter": None,
        "usr/share/applications/sinter.desktop": None,
        "usr/share/applications/sinter-native.desktop": None,
    }
    seen, count = set(), 0
    with tarfile.open(fileobj=io.BytesIO(raw)) as bundle:
        for item in bundle:
            count += 1
            name = item.name.removeprefix("./")
            if count > MAX_ENTRIES or name in seen:
                raise ValueError("The installer has repeated or too many members.")
            seen.add(name)
            if name not in required:
                continue
            limit = MAX_MEMBER if name.startswith("opt/") else 8192
            if not item.isfile() or item.size > limit:
                raise ValueError(
                    "Required installer member is not a bounded regular file."
                )
            required[name] = bundle.extractfile(item).read()
    if any(value is None for value in required.values()):
        raise ValueError("The installer omits the executable or a desktop entry.")
    return required


def package_preflight(args, source, commands):
    raw = regular_bytes(args.installer, MAX_ARCHIVE)
    expected = json.loads(regular_bytes(args.package_receipt, 2 * 1024 * 1024))
    installer_sha = digest(raw)
    if (
        type(expected) is not dict
        or expected.get("passed") is not True
        or type(expected.get("source_commit")) is not str
        or expected["source_commit"] != source["commit"]
        or type(expected.get("version")) is not str
        or expected["version"] != source["version"]
        or expected.get("installer_sha256") != installer_sha
    ):
        raise ValueError(
            "Bind the same-run package receipt to source, version and installer."
        )
    for field, value in (
        ("Package", "sinter"),
        ("Architecture", "amd64"),
        ("Version", debian_package_version(source["version"])),
    ):
        code, body = command(["dpkg-deb", "-f", args.installer, field], commands)
        if code or body.decode("utf-8").strip() != value:
            raise ValueError("Installer control identity differs: " + field)
    code, body = command(
        ["dpkg-deb", "--fsys-tarfile", args.installer], commands, limit=MAX_ARCHIVE
    )
    if code:
        raise ValueError("The actual installer payload cannot be read.")
    members = package_members(body)
    binary_sha = digest(members["opt/neuroforge/sinter/Sinter"])
    cli = expected.get("frozen_cli_test")
    if (
        type(cli) is not dict
        or cli.get("passed") is not True
        or cli.get("binary_sha256") != binary_sha
    ):
        raise ValueError("Same-run frozen CLI identity differs from the installer.")
    generated = linux_desktop_entries(True)
    entries = {}
    for name, text in generated.items():
        raw = members["usr/share/applications/" + name]
        if raw != text.encode("utf-8"):
            raise ValueError("Full installer entry differs from source: " + name)
        entries[name] = {
            "bytes": len(raw),
            "sha256": digest(raw),
            "base64": base64.b64encode(raw).decode("ascii"),
        }
    return {
        "installer_sha256": installer_sha,
        "binary_sha256": binary_sha,
        "binary_bytes": len(members["opt/neuroforge/sinter/Sinter"]),
        "payload_tar_sha256": digest(body),
        "payload_tar_bytes": len(body),
        "receipt_sha256": native.binary_digest(args.package_receipt),
        "package_version": debian_package_version(source["version"]),
        "entries": entries,
    }


def installed_identity(package, *, observations=None, binary_observation=None):
    if observations is not None and (type(observations) is not dict or observations):
        raise ValueError("Provide a fresh full installed-entry observation.")
    if binary_observation is not None and (
        type(binary_observation) is not dict or binary_observation
    ):
        raise ValueError("Provide a fresh installed executable observation.")
    records = {}
    if (
        BINARY.resolve(strict=True) != BINARY
        or ENTRY_DIR.resolve(strict=True) != ENTRY_DIR
    ):
        raise ValueError("Installed locations must not redirect through symlinks.")
    binary = regular_bytes(BINARY, MAX_MEMBER)
    executable = os.access(BINARY, os.X_OK)
    if binary_observation is not None:
        binary_observation.update(
            bytes=len(binary), sha256=digest(binary), executable=executable
        )
    if digest(binary) != package["binary_sha256"] or not executable:
        raise ValueError("Installed executable differs from the actual package.")
    for name, expected in package["entries"].items():
        raw = regular_bytes(ENTRY_DIR / name, 8192)
        records[name] = {
            "bytes": len(raw),
            "sha256": digest(raw),
            "base64": base64.b64encode(raw).decode("ascii"),
        }
        if records[name] != expected or raw != base64.b64decode(
            expected["base64"], validate=True
        ):
            raise ValueError(
                "Full installed entry differs from source/package: " + name
            )
    if observations is not None:
        observations.update(records)
    # Parsing follows full-byte admission; it cannot normalize away differences.
    return tuple(menu_command(ENTRY_DIR / "sinter-native.desktop", native=True))


def package_state(commands):
    code, raw = command(
        ["dpkg-query", "-W", "-f=${Status}", "sinter"],
        commands,
        env={"PATH": os.defpath, "LC_ALL": "C.UTF-8"},
    )
    diagnostics = commands[-1]["stderr"]
    absent = b"dpkg-query: no packages found matching sinter\n"
    if code == 1:
        if (
            raw
            or diagnostics["bytes"] != len(absent)
            or diagnostics["sha256"] != digest(absent)
            or diagnostics["base64"] != base64.b64encode(absent).decode("ascii")
            or diagnostics["truncated"] is not False
        ):
            raise ValueError(
                "Package absence could not be distinguished from a query failure."
            )
        commands[-1]["expected_absence"] = True
        return "absent"
    if code != 0 or diagnostics["bytes"]:
        raise ValueError("Package state could not be inspected.")
    value = raw.decode("ascii").strip()
    if value not in {"install ok installed", "deinstall ok config-files"}:
        raise ValueError("Package state is incomplete or unexpected: " + value)
    return value


def removal_state(commands):
    state = package_state(commands)
    remaining = [
        str(path)
        for path in (
            BINARY,
            ENTRY_DIR / "sinter.desktop",
            ENTRY_DIR / "sinter-native.desktop",
        )
        if os.path.lexists(path)
    ]
    return {
        "package_state": state,
        "remaining_paths": remaining,
        "passed": state in {"absent", "deinstall ok config-files"} and not remaining,
    }


def installed_package_version(expected, commands):
    """Observe the actual dpkg database, not only the input DEB control field."""
    code, raw = command(
        ["dpkg-query", "-W", "-f=${Status}\n${Version}\n", "sinter"],
        commands,
        env={"PATH": os.defpath, "LC_ALL": "C.UTF-8"},
    )
    if (
        code != 0
        or commands[-1]["stderr"]["bytes"] != 0
        or raw != ("install ok installed\n" + expected + "\n").encode("ascii")
    ):
        raise ValueError("Actual installed package status or version differs.")
    return {
        "status": "install ok installed",
        "version": expected,
        "command_index": len(commands) - 1,
    }


@contextmanager
def display(home, receipt):
    """Own fresh authenticated Xvfb, never inherit the customer's display."""
    if any(os.path.lexists(path) for path in ("/tmp/.X11-unix/X97", "/tmp/.X97-lock")):
        raise ValueError("Refuse a display owned by another process.")
    authority = home / "xauthority"
    authority.touch(mode=0o600)
    old = {key: os.environ.get(key) for key in ("DISPLAY", "XAUTHORITY")}
    process = None
    body_failed = False
    receipt["display"] = {"passed": False}
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            code, _ = command(
                ["xauth", "-f", authority, "add", ":97", ".", secrets.token_hex(16)],
                receipt["commands"],
                redact=(-1,),
            )
            if code:
                raise ValueError("Private X authorization could not be created.")
            row = receipt["display"] = {"passed": False}
            process = subprocess.Popen(
                [
                    "Xvfb",
                    ":97",
                    "-screen",
                    "0",
                    "1280x900x24",
                    "-nolisten",
                    "tcp",
                    "-auth",
                    str(authority),
                ],
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
            row["pid"] = process.pid
            os.environ.update(DISPLAY=":97", XAUTHORITY=str(authority))
            deadline = time.monotonic() + 5
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Owned Xvfb exited before readiness.")
                try:
                    observer = native.X11Observer(":97")
                    observer.close()
                    if regular_bytes(Path("/tmp/.X97-lock"), 64).strip() != str(
                        process.pid
                    ).encode("ascii"):
                        raise ValueError(
                            "The display lock does not identify the owned Xvfb process."
                        )
                    break
                except RuntimeError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.05)
            yield ":97", str(authority)
        except BaseException:
            body_failed = True
            raise
        finally:
            cleanup_error = capture_error = None
            try:
                if process is not None:
                    native.stop_process(process, receipt["display"])
            except BaseException as error:
                cleanup_error = error
                receipt["display"]["cleanup_error_type"] = type(error).__name__
            for name, stream in (("stderr", err), ("stdout", out)):
                try:
                    if name == "stderr":
                        native.capture_stderr(stream, receipt["display"])
                    else:
                        receipt["display"]["stdout_observed"] = (
                            native.stdout_observation(
                                stream, process, receipt["display"]
                            )
                            if process is not None
                            else {"complete": False}
                        )
                except BaseException as error:
                    capture_error = capture_error or error
                    receipt["display"][name + "_capture_error_type"] = type(
                        error
                    ).__name__
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            authority.unlink(missing_ok=True)
            row = receipt["display"]
            row["remaining_display_paths"] = [
                path
                for path in ("/tmp/.X11-unix/X97", "/tmp/.X97-lock")
                if os.path.lexists(path)
            ]
            row["authority_remaining"] = os.path.lexists(authority)
            row["passed"] = (
                cleanup_error is None
                and capture_error is None
                and row.get("exit_code") == 0
                and row.get("sigterm_sent") is True
                and not row.get("forced_cleanup")
                and not row.get("owned_group_remaining")
                and row.get("stderr_bytes") == 0
                and row.get("stdout_observed", {}).get("complete") is True
                and row["stdout_observed"]["record"]["bytes"] == 0
                and not row["remaining_display_paths"]
                and row["authority_remaining"] is False
            )
            if not body_failed:
                if cleanup_error or capture_error:
                    raise cleanup_error or capture_error
                if not row["passed"]:
                    raise RuntimeError("Owned display cleanup or diagnostics failed.")


def ui_launch(command_prefix, home, workspace, environment, observer, phase, receipt):
    native.native_entry_arguments(BINARY, command_prefix)
    if type(phase) is not str or phase not in {"create", "reopen"}:
        raise ValueError("Use one fixed Tk phase.")
    row = {
        "phase": phase,
        "argv": [*command_prefix, "--directory", str(workspace)],
        "passed": False,
    }
    receipt["tk_launches"].append(row)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(
            row["argv"],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        row["pid"] = process.pid
        body_failed = False
        try:
            deadline = time.monotonic() + native.START_SECONDS
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        "Installed native entry stopped before Tk appeared."
                    )
                windows = observer.windows(process.pid, mapped_only=True)
                if windows:
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError("No process-owned mapped installed Tk window.")
            row["mapped_windows"] = windows
            request = home / (phase + "-tk-request.json")
            request.write_text(
                json.dumps(
                    {
                        "phase": phase,
                        "pid": process.pid,
                        "window_ids": [w["window_id"] for w in windows],
                    }
                ),
                encoding="utf-8",
            )
            code, raw = command(
                [
                    sys.executable,
                    "-B",
                    ROOT / "tools/installed_native_tk.py",
                    "--request",
                    request,
                ],
                receipt["commands"],
                env=environment,
                timeout=15,
            )
            row["driver_command_index"] = len(receipt["commands"]) - 1
            if code or receipt["commands"][-1]["stderr"]["bytes"]:
                raise RuntimeError(
                    "Bounded actual Tk driver failed; see retained bytes."
                )
            result = json.loads(raw)
            if (
                type(result) is not dict
                or set(result)
                != {
                    "schema",
                    "phase",
                    "project_id",
                    "window_id",
                    "fields_exact",
                    "save_button_invoked",
                    "wm_close_invoked",
                }
                or result["schema"] != "sinter-installed-native-tk-action/v1"
                or result["phase"] != phase
                or result["fields_exact"] is not True
                or result["wm_close_invoked"] is not True
                or result["save_button_invoked"] is not (phase == "create")
                or type(result["project_id"]) is not str
                or not re.fullmatch(r"[0-9a-f]{32}", result["project_id"])
                or result["window_id"] not in [w["window_id"] for w in windows]
            ):
                raise ValueError("Actual Tk action identity or result is incomplete.")
            row["action"] = result
            row["exit_code"] = process.wait(timeout=8)
        except BaseException:
            body_failed = True
            raise
        finally:
            cleanup_error = capture_error = None
            try:
                native.stop_process(process, row)
                row["owned_windows_remaining"] = observer.windows(process.pid)
            except BaseException as error:
                cleanup_error = error
                row["cleanup_error_type"] = type(error).__name__
            for name, stream in (("stderr", err), ("stdout", out)):
                try:
                    if name == "stderr":
                        native.capture_stderr(stream, row)
                    else:
                        observed = native.stdout_observation(stream, process, row)
                        row[name] = observed["record"]
                        row["stdout_complete"] = observed["complete"]
                except BaseException as error:
                    capture_error = capture_error or error
                    row[name + "_capture_error_type"] = type(error).__name__
            if not body_failed and (cleanup_error or capture_error):
                raise cleanup_error or capture_error
        if (
            row["exit_code"] != 0
            or row.get("sigterm_sent")
            or row.get("forced_cleanup")
            or row["owned_group_remaining"]
            or row["owned_windows_remaining"]
            or row["stderr_bytes"]
            or row.get("stdout_complete") is not True
            or row["stdout"]["bytes"] != 0
        ):
            raise RuntimeError(
                "Installed native WM quit/cleanup emitted errors or needed a signal."
            )
        row["passed"] = True
        return row["action"]["project_id"]


def admit_invocations(proof, observations, command_prefix, package):
    if (
        type(proof) is not dict
        or proof.get("schema") != "sinter-frozen-native-window-test/v1"
        or proof.get("passed") is not True
        or proof.get("binary_sha256") != package["binary_sha256"]
        or proof.get("binary_sha256_after") != package["binary_sha256"]
        or proof.get("binary_unchanged") is not True
        or type(observations) is not list
        or len(observations) != 2
        or type(proof.get("launches")) is not list
        or len(proof["launches"]) != 2
    ):
        raise ValueError(
            "Require fresh unchanged native proof and two actual entry invocations."
        )
    directories, pids = set(), set()
    for observation, row in zip(observations, proof["launches"]):
        if (
            type(observation) is not dict
            or set(observation) != {"argv", "started", "pid"}
            or observation["started"] is not True
            or type(observation["pid"]) is not int
            or observation["pid"] <= 0
            or observation["pid"] != row.get("pid")
            or type(row.get("pid")) is not int
            or type(observation["argv"]) is not list
            or len(observation["argv"]) != 6
            or any(type(a) is not str for a in observation["argv"])
            or observation["argv"][:4] != list(command_prefix)
            or observation["argv"][4] != "--directory"
            or row.get("passed") is not True
            or row.get("sigterm_sent") is not True
            or row.get("forced_cleanup") is not False
            or row.get("owned_group_remaining") is not False
            or row.get("owned_windows_remaining") != []
            or type(row.get("stderr_bytes")) is not int
            or row["stderr_bytes"] != 0
            or type(row.get("exit_code")) is not int
            or row["exit_code"] != 0
            or not row.get("mapped_windows")
        ):
            raise ValueError(
                "Native entry invocation does not match its strict mapped launch."
            )
        windows = row["mapped_windows"]
        if (
            type(windows) is not list
            or not 0 < len(windows) < 5
            or any(
                type(w) is not dict
                or type(w.get("pid")) is not int
                or w["pid"] != row["pid"]
                or w.get("mapped") is not True
                or type(w.get("window_id")) is not str
                or not re.fullmatch(r"0x[0-9a-f]+", w["window_id"])
                or w.get("title") != native.TITLE
                or any(
                    type(w.get(k)) is not int or w[k] <= 0 for k in ("width", "height")
                )
                for w in windows
            )
        ):
            raise ValueError(
                "Mapped native windows must match the actual invoked PID and title."
            )
        if not Path(observation["argv"][-1]).is_absolute():
            raise ValueError("Use an absolute owned fictional workspace.")
        directories.add(observation["argv"][-1])
        pids.add(observation["pid"])
    if len(directories) != 1 or len(pids) != 2:
        raise ValueError(
            "Native launches must be fresh PIDs using the same fictional directory."
        )


def run(args):
    receipt = {
        "schema": ARCHIVE_INNER_SCHEMA
        if getattr(args, "source_route", "git") == "archive"
        else "sinter-installed-native-entry-test/v2",
        "passed": False,
        "commands": [],
        "tk_launches": [],
        "invocations": [],
        "tk_workspaces": [],
        "mapped_observations": {},
        "boundary": "Installed Linux X11 native-entry command, fictional Tk create/save/reopen/WM quit, repeated SIGTERM and owned package removal; not physical menu, full editing/browser handoff, upgrade or RC4 release qualification.",
    }
    attempted = False
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        if (
            platform.system() != "Linux"
            or os.geteuid() != 0
            or not Path("/.dockerenv").is_file()
            or {p.name for p in Path("/sys/class/net").iterdir()} != {"lo"}
            or os.environ.get("DISPLAY")
        ):
            raise ValueError(
                "Use a fresh root disposable network-none container without a display."
            )
        if package_state(receipt["commands"]) != "absent" or any(
            os.path.lexists(p)
            for p in (
                BINARY,
                ENTRY_DIR / "sinter.desktop",
                ENTRY_DIR / "sinter-native.desktop",
            )
        ):
            raise ValueError("Refuse an existing package or residual installed path.")
        receipt["container"] = {
            "effective_uid": os.geteuid(),
            "interfaces": sorted(p.name for p in Path("/sys/class/net").iterdir()),
            "inherited_display": False,
            "docker_marker_present": True,
        }
        archive_route = getattr(args, "source_route", "git") == "archive"
        origin = {} if archive_route else None
        source = receipt["source"] = selected_source_identity(
            args, receipt["commands"], origin
        )
        if archive_route:
            receipt["source_origin"] = origin
        package = receipt["package"] = package_preflight(
            args, source, receipt["commands"]
        )
        if native.binary_digest(args.installer) != package["installer_sha256"]:
            raise ValueError("The installer changed before its explicit installation.")
        attempted = True
        code, _ = command(
            ["dpkg", "-i", args.installer], receipt["commands"], timeout=60
        )
        if code or package_state(receipt["commands"]) != "install ok installed":
            raise RuntimeError("Owned candidate installation failed.")
        receipt["installed_entries"] = {}
        receipt["installed_binary"] = {}
        prefix = installed_identity(
            package,
            observations=receipt["installed_entries"],
            binary_observation=receipt["installed_binary"],
        )
        receipt["native_command"] = list(prefix)
        receipt["installed_package"] = installed_package_version(
            debian_package_version(source["version"]), receipt["commands"]
        )
        with tempfile.TemporaryDirectory(
            prefix="sinter-native-entry-", dir=args.output
        ) as temp:
            home = Path(temp)
            receipt["owned_home"] = str(home)
            with display(home, receipt) as (name, authority):
                environment = native.clean_environment(home, name, authority)
                receipt["diagnostic_process"] = {}
                receipt["diagnostic_observation"] = {}
                diag = receipt["frozen_diagnostics"] = native.diagnose(
                    BINARY,
                    environment,
                    receipt["diagnostic_process"],
                    observation=receipt["diagnostic_observation"],
                )
                if diag["version"] != source["version"]:
                    raise ValueError(
                        "Installed frozen version differs from source/package."
                    )
                workspace = home / "workspace"
                workspace.mkdir(mode=0o700)
                (workspace / "preferences.json").write_text(
                    json.dumps(native.FICTIONAL_PREFERENCES, ensure_ascii=False),
                    encoding="utf-8",
                )
                receipt["offline_commands"] = []
                receipt["offline_observations"] = []
                expected = validate(FIXTURE)
                observer = native.X11Observer(name)
                saved = None
                try:
                    for phase in ("create", "reopen"):
                        identifier = ui_launch(
                            prefix,
                            home,
                            workspace,
                            environment,
                            observer,
                            phase,
                            receipt,
                        )
                        before = native.workspace_snapshot(workspace)
                        actual = native.local_operation(
                            BINARY,
                            workspace,
                            environment,
                            "casebooks.get",
                            {"id": identifier},
                            receipt,
                            **native.operation_observation_argument(
                                receipt["offline_observations"]
                            ),
                        )
                        if (
                            type(actual.get("id")) is not str
                            or actual["id"] != identifier
                            or type(actual.get("revision")) is not int
                            or actual["revision"] != 1
                            or not native.same_json(actual.get("document"), expected)
                            or saved is not None
                            and not native.same_json(actual, saved)
                            or native.workspace_snapshot(workspace) != before
                        ):
                            raise ValueError(
                                "Actual installed Tk save/reopen did not retain exact fictional work."
                            )
                        if before["preferences_sha256"] != digest(
                            json.dumps(
                                native.FICTIONAL_PREFERENCES, ensure_ascii=False
                            ).encode("utf-8")
                        ):
                            raise ValueError(
                                "Tk changed the explicit saved preferences."
                            )
                        if saved is None:
                            receipt["fictional_workspace"] = {"original": before}
                        receipt["tk_launches"][-1]["passed"] = False
                        native.verify_fictional_workspace(
                            BINARY,
                            workspace,
                            environment,
                            saved or actual,
                            receipt,
                            receipt["tk_launches"][-1],
                            operation_observations=receipt["offline_observations"],
                        )
                        receipt["tk_launches"][-1]["passed"] = True
                        saved = actual
                        receipt["tk_launches"][-1]["saved_snapshot"] = before
                        receipt["tk_launches"][-1]["saved_document_sha256"] = digest(
                            json.dumps(
                                actual, sort_keys=True, ensure_ascii=False
                            ).encode("utf-8")
                        )
                        receipt["tk_workspaces"].append(
                            {
                                "phase": phase,
                                "snapshot": native.retained_workspace_snapshot(
                                    workspace
                                ),
                            }
                        )
                finally:
                    observer.close()
                receipt["mapped_native_proof"] = native.smoke(
                    BINARY,
                    native_entry_command=prefix,
                    invocation_log=receipt["invocations"],
                    entry_observations=receipt["mapped_observations"],
                )
                admit_invocations(
                    receipt["mapped_native_proof"],
                    receipt["invocations"],
                    prefix,
                    package,
                )
                streams = receipt["mapped_observations"].get("streams", [])
                if len(streams) != 2 or any(
                    row.get("stdout", {}).get("complete") is not True
                    or row["stdout"]["record"]["bytes"] != 0
                    for row in streams
                ):
                    raise ValueError(
                        "Require complete clean post-reap mapped stdout observations."
                    )
                all_pids = [r["pid"] for r in receipt["tk_launches"]] + [
                    r["pid"] for r in receipt["invocations"]
                ]
                if len(set(all_pids)) != 4:
                    raise ValueError(
                        "Every actual entry invocation requires a separate process."
                    )
                receipt["installed_package_recheck"] = installed_package_version(
                    debian_package_version(source["version"]), receipt["commands"]
                )
                receipt["installed_entries_after"] = {}
                receipt["installed_binary_after"] = {}
                if (
                    installed_identity(
                        package,
                        observations=receipt["installed_entries_after"],
                        binary_observation=receipt["installed_binary_after"],
                    )
                    != prefix
                    or native.binary_digest(args.installer)
                    != package["installer_sha256"]
                ):
                    raise ValueError(
                        "Source-bound installed/package bytes changed during proof."
                    )
        receipt["fictional_workspace_removed"] = not home.exists()
        receipt["workspace_cleanup_probe"] = observed_absence(
            [
                home,
                Path(receipt["mapped_observations"]["workspace_path"]).parent,
                "/tmp/.X11-unix/X97",
                "/tmp/.X97-lock",
                home / "xauthority",
            ],
            receipt["commands"],
        )
        origin_after = {} if archive_route else None
        source_after = selected_source_identity(args, receipt["commands"], origin_after)
        if archive_route:
            receipt["source_origin_after"] = origin_after
            if not native.same_json(origin, origin_after):
                raise ValueError(
                    "Original source archive manifest changed during proof."
                )
        if not receipt["fictional_workspace_removed"] or not native.same_json(
            source_after, source
        ):
            raise ValueError(
                "Source bytes or fictional workspace cleanup changed during proof."
            )
        receipt["workflow_passed"] = True
    except BaseException as error:
        receipt.update(error_type=type(error).__name__, error=str(error)[:4096])
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        try:
            if attempted:
                code, _ = command(
                    ["dpkg", "-r", "sinter"], receipt["commands"], timeout=60
                )
                receipt["removal"] = removal_state(receipt["commands"])
                receipt["removal"]["command_exit"] = code
                receipt["removal"]["passed"] = (
                    code == 0 and receipt["removal"]["passed"]
                )
                if (
                    receipt["removal"]["passed"]
                    and receipt.get("workflow_passed") is True
                ):
                    receipt["removal_cleanup_probe"] = observed_absence(
                        [
                            BINARY,
                            ENTRY_DIR / "sinter.desktop",
                            ENTRY_DIR / "sinter-native.desktop",
                        ],
                        receipt["commands"],
                    )
            else:
                receipt["removal"] = {"passed": False, "attempted": False}
        except BaseException as error:
            receipt.update(
                cleanup_error_type=type(error).__name__, cleanup_error=str(error)[:4096]
            )
        receipt["passed"] = (
            receipt.get("workflow_passed") is True
            and receipt.get("removal", {}).get("passed") is True
            and "error_type" not in receipt
            and "cleanup_error_type" not in receipt
        )
        (args.output / "installed-native-entry-test.json").write_text(
            json.dumps(receipt, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-route", choices=("git", "archive"), default="git")
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--package-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    previous = signal.getsignal(signal.SIGTERM)

    def cancelled(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, cancelled)
    try:
        result = run(args)
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
