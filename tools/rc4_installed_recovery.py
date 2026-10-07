"""Own an offline installed Linux recovery rehearsal with private host Chromium.

Both campaign and scoped recovery profiles are mandatory. This new route never
builds/pulls an image, opens a physical browser, admits a prior or qualifies a
release. The explicit development route separately binds QA and candidate bytes.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import platform
import re
import secrets
import socket
import stat
import subprocess
import sys
import tarfile
import threading
import time
import traceback
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tools import rc4_installed_recovery_contract as contract  # noqa: E402

BINARY = PurePosixPath("/opt/neuroforge/sinter/Sinter")
IMAGE = "sha256:a6abf8768b5d981009b5fd68c7663ed14f87ade82ba8e5aa9be7f856f9313268"
SOURCE_FILE = "tools/rc4_installed_recovery.py"
PROFILES = ("campaign", "scoped")
MAX_RPC = 4 * 1024 * 1024
RPC_LIMIT = 64
CLI_EXPORT_PRIVATE = Path(contract.EXPORT_PRIVATE)


def write_json(path, value):
    raw = contract.canonical(value).encode("utf-8")
    temporary = path.with_suffix(".tmp")
    with temporary.open("xb") as stream:
        stream.write(raw)
    temporary.replace(path)


def prepare_cli_export_directory() -> None:
    """Create the one fixed, unmounted private directory; existing entries refuse."""
    CLI_EXPORT_PRIVATE.mkdir(mode=0o700)
    info = CLI_EXPORT_PRIVATE.lstat()
    contract.require(
        stat.S_ISDIR(info.st_mode)
        and stat.S_IMODE(info.st_mode) == 0o700
        and info.st_uid == os.geteuid()
        and info.st_gid == os.getegid(),
        "CLI export private directory differs.",
    )


def cli_export_paths(run: int, output: Path) -> tuple[Path, Path]:
    """Only the four scoped original exports and their existing proof roles."""
    contract.require(
        type(run) is int and run in range(1, 5), "Unknown CLI export run refuses."
    )
    return (
        CLI_EXPORT_PRIVATE / f"run-{run}.cli-export.json",
        output / f"process/run-{run}.cli-export.json",
    )


def export_directory(
    resources: contract.ExportDescriptors, path: Path, *, private: bool
) -> int:
    """Anchor owned directories without following redirects."""
    before = contract.export_metadata(path.lstat())
    contract.require(
        stat.S_ISDIR(before["st_mode"])
        and before["st_uid"] == os.geteuid()
        and before["st_gid"] == os.getegid()
        and (not private or stat.S_IMODE(before["st_mode"]) == 0o700),
        "CLI export directory ownership or mode differs.",
    )
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    resources.callback(os.close, fd)
    contract.require(
        contract.export_metadata(os.fstat(fd)) == before,
        "CLI export directory changed while opening.",
    )
    return fd


def fresh_cli_export(
    run: int, output: Path, *, cleanup: list[dict] | None = None
) -> None:
    """Refuse any pre-existing private original or proof before the CLI starts."""
    source, proof = cli_export_paths(run, output)
    with contract.ExportDescriptors(cleanup) as resources:
        for path, private in ((source, True), (proof, False)):
            fd = export_directory(resources, path.parent, private=private)
            try:
                os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise ValueError("CLI export original and proof must both be fresh.")


def publish_cli_export(
    run: int, output: Path, document: dict, *, cleanup: list[dict] | None = None
) -> dict:
    """Retain private source bytes and publish a distinct, read-only proof copy."""
    source, proof = cli_export_paths(run, output)
    with contract.ExportDescriptors(cleanup) as resources:
        source_dir = export_directory(resources, source.parent, private=True)
        proof_dir = export_directory(resources, proof.parent, private=False)
        directories = [(source.parent, source_dir), (proof.parent, proof_dir)]
        identities = [os.fstat(fd) for _, fd in directories]
        before = contract.export_metadata(
            os.stat(source.name, dir_fd=source_dir, follow_symlinks=False)
        )
        contract.require(
            before["st_mode"] == stat.S_IFREG | 0o600
            and before["st_uid"] == os.geteuid()
            and before["st_gid"] == os.getegid()
            and before["st_nlink"] == 1
            and 0 < before["st_size"] <= MAX_RPC,
            "CLI private export ownership, mode or bound differs.",
        )
        source_fd = os.open(
            source.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source_dir
        )
        resources.callback(os.close, source_fd)

        def conserved_source() -> None:
            contract.require(
                contract.export_metadata(os.fstat(source_fd)) == before
                and contract.export_metadata(
                    os.stat(source.name, dir_fd=source_dir, follow_symlinks=False)
                )
                == before,
                "CLI private original changed during proof publication.",
            )

        conserved_source()
        with os.fdopen(source_fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_RPC + 1)
        conserved_source()
        contract.require(
            len(raw) == before["st_size"]
            and contract.equal(contract.json_object(raw), document),
            "CLI private export does not preserve full original input.",
        )
        proof_fd = os.open(
            proof.name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o444,
            dir_fd=proof_dir,
        )
        resources.callback(os.close, proof_fd)
        # Only the new proof copy is made readable; the private original is untouched.
        os.fchmod(proof_fd, 0o444)
        remaining = memoryview(raw)
        while remaining:
            written = os.write(proof_fd, remaining)
            contract.require(written > 0, "CLI proof write did not complete.")
            remaining = remaining[written:]
        os.fsync(proof_fd)
        os.lseek(proof_fd, 0, os.SEEK_SET)
        with os.fdopen(proof_fd, "rb", closefd=False) as stream:
            copied = stream.read(MAX_RPC + 1)
        metadata = contract.export_metadata(os.fstat(proof_fd))
        contract.require(
            copied == raw
            and metadata["st_mode"] == stat.S_IFREG | 0o444
            and metadata["st_uid"] == os.geteuid()
            and metadata["st_gid"] == os.getegid()
            and metadata["st_nlink"] == 1
            and (metadata["st_dev"], metadata["st_ino"])
            != (before["st_dev"], before["st_ino"])
            and contract.export_metadata(
                os.stat(proof.name, dir_fd=proof_dir, follow_symlinks=False)
            )
            == metadata,
            "CLI proof copy bytes, permissions or identity differ.",
        )
        conserved_source()
        os.lseek(source_fd, 0, os.SEEK_SET)
        with os.fdopen(source_fd, "rb", closefd=False) as stream:
            contract.require(
                stream.read(MAX_RPC + 1) == raw,
                "CLI private original bytes changed after copying.",
            )
        conserved_source()
        for (path, fd), original in zip(directories, identities):
            current = path.lstat()
            contract.require(
                all(
                    getattr(current, k)
                    == getattr(original, k)
                    == getattr(os.fstat(fd), k)
                    for k in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")
                ),
                "CLI export directory identity changed during publication.",
            )
        os.fsync(proof_dir)
        return {
            "schema": contract.EXPORT_PROOF_SCHEMA,
            "source_path": str(source),
            "proof_path": str(proof),
            "source_before": before,
            "source_after": contract.export_metadata(os.fstat(source_fd)),
            "proof_metadata": metadata,
            "bytes": len(raw),
            "sha256": contract.sha(raw),
        }


def read_json(path, limit=MAX_RPC):
    return contract.json_object(contract.regular(path, limit))


def source_records(root):
    records = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or "__pycache__" in path.parts or path.suffix == ".pyc":
            raise ValueError("Use complete source without redirects or import caches.")
        contract.require(
            path.is_file() or path.is_dir(), "Special source entries refuse."
        )
        if path.is_file():
            raw = contract.regular(path, 128 * 1024 * 1024)
            records[path.relative_to(root).as_posix()] = contract.record(raw)
    return records


def source_binding(archive, commit, qa, mode):
    """Bind actual Git tar bytes before using any candidate Sinter compiler."""
    contract.require(
        type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit),
        "Use one full candidate commit.",
    )
    contract.require(
        type(archive) is bytes and len(archive) <= 128 * 1024 * 1024,
        "Use a bounded source archive.",
    )
    files, version = {}, None
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        contract.require(
            bundle.pax_headers == {"comment": commit}, "Git origin differs."
        )
        seen = set()
        for item in bundle:
            name = item.name.rstrip("/") if item.isdir() else item.name
            path = PurePosixPath(name)
            contract.require(
                name
                and not path.is_absolute()
                and ".." not in path.parts
                and "\\" not in name
                and str(path) == name
                and name not in seen
                and len(seen) < 4000
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
                and item.pax_headers == {"comment": commit},
                "Source archive member/origin differs.",
            )
            seen.add(name)
            if item.isdir():
                contract.require(item.size == 0, "Directory member has content.")
                continue
            contract.require(
                item.isfile() and item.size <= 128 * 1024 * 1024,
                "Links and special source members refuse.",
            )
            raw = bundle.extractfile(item).read(item.size + 1)
            contract.require(len(raw) == item.size, "Source member size differs.")
            files[name] = contract.record(raw)
            if name == "src/sinter/__init__.py":
                matches = re.findall(
                    r"^__version__ = [\"\']([^\"\']+)[\"\']$", raw.decode(), re.M
                )
                contract.require(len(matches) == 1, "Candidate version is ambiguous.")
                version = matches[0]
    contract.require(
        mode in ("development", "candidate"), "Unknown execution boundary."
    )
    production = {n: r for n, r in files.items() if n.startswith("src/")}
    contract.require(
        production
        and contract.equal(
            production, {n: r for n, r in qa.items() if n.startswith("src/")}
        ),
        "Every production byte must match the actual candidate archive.",
    )
    if mode == "candidate":
        contract.require(
            version == "0.5.4rc4" and contract.equal(qa, files),
            "Final RC4 requires one exact candidate and QA identity.",
        )
    else:
        contract.require(
            version == "0.5.4rc4.dev0", "Development is not a tag admission."
        )
    return {
        "commit": commit,
        "version": version,
        "archive_sha256": contract.sha(archive),
        "files": files,
        "qa_files": qa,
        "mode": mode,
    }


def outer_argv(pins, name):
    from tools.installed_native_entry_contract import outer_argv as native_argv

    argv = native_argv(pins, name)
    index = argv.index(pins["image_id"])
    return argv[: index + 1] + ["python3", "-B", "/source/" + SOURCE_FILE, "inner"]


def process_argv(data):
    return [str(BINARY), "app", "--mode", "browser", "--directory", str(data)]


def environment(home, capture):
    return {
        "PATH": os.defpath,
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "BROWSER": str(capture),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


class ObservationClient:
    """One fixed profile, sequential bounded requests; never paths/SQL/commands."""

    def __init__(self, runtime, profile, nonce, output, timeout=20):
        contract.require(profile in PROFILES, "Unknown observation profile.")
        contract.require(
            type(nonce) is str and re.fullmatch(r"[0-9a-f]{32}", nonce),
            "Use the owned session identity.",
        )
        self.runtime, self.profile, self.nonce = runtime, profile, nonce
        self.output, self.timeout, self.sequence = output, timeout, 0
        self.lock = threading.Lock()

    def call(self, operation):
        contract.require(
            operation in contract.OPERATIONS[self.profile],
            "Unknown fixed observation operation.",
        )
        with self.lock:
            self.sequence += 1
            contract.require(
                self.sequence <= RPC_LIMIT, "Observation count exceeds bound."
            )
            request = {
                "schema": contract.RPC_REQUEST,
                "profile": self.profile,
                "session": self.nonce,
                "sequence": self.sequence,
                "operation": operation,
            }
            rpc = self.runtime / "rpc"
            response = rpc / "response.json"
            response.unlink(missing_ok=True)
            write_json(rpc / "request.json", request)
            write_json(self.output / f"rpc/{self.sequence:02d}.request.json", request)
            deadline = time.monotonic() + self.timeout
            while not response.exists():
                if time.monotonic() >= deadline:
                    raise ValueError("Installed observation timed out; no pass.")
                time.sleep(0.01)
            raw = contract.regular(response, MAX_RPC)
            (self.output / f"rpc/{self.sequence:02d}.response.json").write_bytes(raw)
            result = contract.json_object(raw)
            contract.validate_rpc(request, result)
            if result["error"] is not None:
                raise ValueError("Installed observation refused: " + result["error"])
            return result["result"]

    def snapshot(self, path):
        contract.require(
            Path(path) == self.runtime / "data",
            "Only the fixed current profile workspace is observable.",
        )
        return self.call("snapshot")

    def protocol(self, runtime, output, saved):
        contract.require(
            Path(runtime) == self.runtime and Path(output) == self.output,
            "Protocol maps only the owned scoped profile.",
        )
        value = self.call("protocol")
        contract.require(
            contract.equal(value["capable_get"], saved),
            "Protocol did not select the saved current scoped project.",
        )
        write_json(output / "protocol.json", value)


class ObservationServer:
    """Read-only fixed operations in the inner owner's known workspace."""

    def __init__(self, runtime, profile, nonce, output, snapshotter, protocol_probe):
        self.runtime, self.profile, self.nonce = runtime, profile, nonce
        self.output, self.snapshotter, self.protocol_probe = (
            output,
            snapshotter,
            protocol_probe,
        )
        self.sequence, self.rows = 0, []

    def service(self):
        path = self.runtime / "rpc/request.json"
        if not path.exists():
            return
        raw = contract.regular(path, 1024)
        (self.output / f"inner-rpc/{self.sequence + 1:02d}.request.json").write_bytes(
            raw
        )
        request = contract.json_object(raw)
        contract.validate_request(request, self.profile, self.nonce, self.sequence + 1)
        path.unlink()
        self.sequence += 1
        error, result = None, None
        try:
            if request["operation"] == "snapshot":
                result = self.snapshotter(self.runtime / "data")
            else:
                result = self.protocol_probe()
        except BaseException as exc:
            error = type(exc).__name__ + ": " + str(exc)[:512]
        response = {
            **request,
            "schema": contract.RPC_RESPONSE,
            "result": result,
            "error": error,
        }
        try:
            raw_response = contract.canonical(response).encode("utf-8")
            contract.require(
                len(raw_response) <= MAX_RPC, "Observation exceeded finite bound."
            )
        except (ValueError, TypeError) as exc:
            response["result"] = None
            response["error"] = type(exc).__name__ + ": " + str(exc)[:512]
        self.rows.append({"request": request, "response": response})
        write_json(self.output / f"inner-rpc/{self.sequence:02d}.request.json", request)
        write_json(
            self.output / f"inner-rpc/{self.sequence:02d}.response.json", response
        )
        write_json(self.runtime / "rpc/response.json", response)


def fixed_snapshot(directory):
    """Read bounded original bytes/typed rows only from the fixed unlinked data path."""
    from tools.rc4_recovery_worker import snapshot

    directory = Path(directory)
    contract.require(
        directory.name == "data"
        and directory.is_dir()
        and not directory.is_symlink()
        and directory.resolve() == directory.absolute(),
        "Fixed workspace observation path is redirected.",
    )
    require_names = {"workspace.sqlite3", "campaigns.sqlite3"}
    contract.require(
        {p.name for p in directory.glob("*.sqlite3")} == require_names,
        "Fixed workspace database inventory differs.",
    )
    files = [
        directory / "preferences.json",
        *(directory / n for n in sorted(require_names)),
    ]
    files += [
        directory / (n + suffix)
        for n in sorted(require_names)
        for suffix in ("-wal", "-shm")
        if (directory / (n + suffix)).exists()
    ]
    for path in files:
        contract.regular(path, 8 * 1024 * 1024)
    result = snapshot(directory)
    contract.require(
        len(contract.canonical(result).encode("utf-8")) <= MAX_RPC,
        "Complete raw workspace observation exceeded its bound.",
    )
    return result


class OwnedBrowserSession:
    """Attempt each close independently; UI failure outranks cleanup failures."""

    def __init__(self, phase):
        self.phase = phase
        self.contexts, self.browsers, self.errors, self.attempts = [], [], [], []
        self.driver_closed = False

    def __call__(self):
        return self

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self.manager = sync_playwright()
        try:
            self.driver = self.manager.__enter__()
        except BaseException:
            kind, primary, trace = sys.exc_info()
            error = self.observe_close(
                "driver", lambda: self.manager.__exit__(kind, primary, trace)
            )
            self.driver_closed = error is None
            raise
        return self.driver

    def observe_close(self, label, action):
        row = {"resource": label, "succeeded": False}
        self.attempts.append(row)
        try:
            action()
            row["succeeded"] = True
            return None
        except BaseException as error:
            diagnostic = {
                "resource": label,
                "type": type(error).__name__,
                "message": str(error)[:1024],
            }
            self.errors.append(diagnostic)
            row["error"] = diagnostic
            return error

    def launch(self, driver, chromium):
        from tools._support import launch_chromium

        contract.require(
            driver is self.driver, "Browser driver belongs to another session."
        )
        raw, session = launch_chromium(driver, chromium), self

        class Browser:
            closed = False

            def __init__(self):
                self.contexts = []

            def __getattr__(self, name):
                return getattr(raw, name)

            def new_context(self, **kwargs):
                context = raw.new_context(**kwargs)

                class Context:
                    closed = False

                    def __getattr__(self, name):
                        return getattr(context, name)

                    def close(self):
                        if self.closed:
                            return
                        primary = sys.exc_info()[1]
                        error = session.observe_close("context", context.close)
                        self.closed = error is None
                        if error is not None and primary is None:
                            raise error

                wrapped = Context()
                self.contexts.append(wrapped)
                session.contexts.append(wrapped)
                return wrapped

            def close(self):
                primary, first = sys.exc_info()[1], None
                for context in self.contexts:
                    if not context.closed:
                        error = session.observe_close("context retry", context.close)
                        first = first or error
                if not self.closed:
                    error = session.observe_close("browser", raw.close)
                    self.closed = error is None
                    first = first or error
                if first is not None and primary is None:
                    raise first

        browser = Browser()
        self.browsers.append(browser)
        return browser

    def __exit__(self, kind, primary, trace):
        first = None
        for browser in self.browsers:
            error = self.observe_close("browser final", browser.close)
            first = first or error
        error = self.observe_close(
            "driver", lambda: self.manager.__exit__(kind, primary, trace)
        )
        self.driver_closed = error is None
        first = first or error
        if primary is None and first is not None:
            raise first
        return False

    def observations(self):
        return {
            "phase": self.phase,
            "driver_closed": self.driver_closed,
            "browser_closed": all(b.closed for b in self.browsers),
            "contexts_closed": all(c.closed for c in self.contexts),
            "cleanup_errors": self.errors,
            "cleanup_attempts": self.attempts,
        }


def owned_inner_relay(runtime):
    """Keep the unchanged transport while observing each admitted request worker."""
    from tools import installed_workflow_browser as transport

    class ObservedInnerRelay(transport.InnerRelay):
        def __init__(self, path):
            self.request_lock = threading.Lock()
            self.requests = set()
            super().__init__(path)

        def get_request(self):
            request, address = super().get_request()
            with self.request_lock:
                self.requests.add(request)
            return request, address

        def process_request_thread(self, request, address):
            try:
                super().process_request_thread(request, address)
            finally:
                with self.request_lock:
                    self.requests.discard(request)

        def server_close(self):
            with self.request_lock:
                for request in self.requests:
                    try:
                        request.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
            super().server_close()

        def idle(self):
            with self.request_lock:
                return not self.requests

    return ObservedInnerRelay(runtime)


class InstalledLifecycle:
    """Launch the actual immutable binary; capture streams even on cleanup faults."""

    def __init__(self, runtime, output, identity, baseline, profile, nonce):
        snapshot = fixed_snapshot

        self.runtime, self.output, self.identity = runtime, output, identity
        self.profile, self.baseline = profile, baseline
        self.process, self.rows, self.failure, self.closed = None, [], None, False
        self.inner = owned_inner_relay(runtime)
        self.thread = threading.Thread(target=self.inner.serve_forever, daemon=True)
        self.rpc = ObservationServer(
            runtime, profile, nonce, output, snapshot, self.protocol
        )
        self.notice = base64.b64decode(identity["notice_base64"])

    def preserved(self, value):
        from tools.rc4_recovery_worker import protected
        from tools.rc4_scoped_recovery_contract import seed_projection

        return (
            protected(value)
            if self.profile == "campaign"
            else seed_projection(value, self.baseline)
        )

    def admission(self, name):
        snapshot = fixed_snapshot

        before = snapshot(self.runtime / "data")
        write_json(self.output / ("process/" + name + ".before-reader.json"), before)
        contract.require(
            contract.equal(self.preserved(before), self.preserved(self.baseline)),
            "Fixture changed before installed reader/reopen admission.",
        )
        return before

    def protocol(self):
        from tools import rc4_scoped_recovery_source as scoped

        snapshot = fixed_snapshot
        from tools.rc4_scoped_recovery_contract import TITLE, wrappers

        before = snapshot(self.runtime / "data")
        rows = [
            r
            for r in wrappers(before, "casebooks_scoped_v2")
            if r["document"]["title"] == TITLE
        ]
        contract.require(
            len(rows) == 1 and self.process.poll() is None,
            "Fixed scoped protocol requires the current live original.",
        )
        scoped.protocol(self.runtime, self.output, rows[0])
        return read_json(self.output / "protocol.json")

    def launch(self, run):
        from tools import installed_workflow_browser as transport

        self.admission(f"run-{run}")
        capture = self.runtime / "launch-url.txt"
        capture.unlink(missing_ok=True)
        stdout, stderr = [
            self.output / f"process/run-{run}.{n}" for n in ("stdout", "stderr")
        ]
        self.paths = {"stdout": stdout, "stderr": stderr}
        self.streams = [stdout.open("wb"), stderr.open("wb")]
        argv = process_argv(self.runtime / "data")
        self.process = subprocess.Popen(
            argv,
            env=environment(self.runtime / "home", self.runtime / "capture-browser"),
            stdin=subprocess.DEVNULL,
            stdout=self.streams[0],
            stderr=self.streams[1],
            start_new_session=True,
        )
        row = {
            "run": run,
            "pid": self.process.pid,
            "argv": argv,
            "binary_sha256": contract.sha(contract.regular(BINARY, 128 * 1024 * 1024)),
            "workspace": str(self.runtime / "data"),
            "stop_method": "interface_quit",
            "forced_cleanup": False,
            "sigterm_sent": False,
        }
        self.rows.append(row)
        deadline = time.monotonic() + 25
        while not capture.exists():
            contract.require(
                self.process.poll() is None, "Installed process stopped before capture."
            )
            contract.require(
                time.monotonic() < deadline, "Installed opener capture timed out."
            )
            time.sleep(0.02)
        raw = contract.regular(capture, 1024)
        _, self.inner.port = transport.inner_address(raw.decode("utf-8"))
        row["opener"] = contract.record_full(raw)
        row["cmdline"] = contract.record_full(
            contract.regular(Path(f"/proc/{self.process.pid}/cmdline"), 4096)
        )
        row["port"] = self.inner.port
        write_json(
            self.runtime / "state.json",
            {
                **self.identity,
                "phase": "running",
                "run": run,
                "pid": self.process.pid,
                "port": self.inner.port,
            },
        )

    def reap(self, run, *, observe=True):
        from tools import native_window_smoke as native
        from tools.rc4_recovery_source import capture_stream

        snapshot = fixed_snapshot

        row = self.rows[-1]
        errors = []
        try:
            native.stop_process(self.process, row)
        except Exception as exc:
            errors.append("stop: " + str(exc))
        for stream in self.streams:
            try:
                stream.close()
            except Exception as exc:
                errors.append("stream close: " + str(exc))
        # Independent capture precedes every optional snapshot/cleanup observation.
        for name in ("stderr", "stdout"):
            try:
                row[name] = capture_stream(self.paths[name])
            except Exception as exc:
                errors.append(name + " capture: " + str(exc))
        row["returncode"] = self.process.poll()
        row["port_closed"] = False
        try:
            with socket.socket() as probe:
                probe.settimeout(1)
                row["port_closed"] = (
                    probe.connect_ex(("127.0.0.1", self.inner.port)) != 0
                )
            if observe:
                row["persistent_snapshot"] = snapshot(self.runtime / "data")
                write_json(
                    self.output / f"process/run-{run}.snapshot.json",
                    row["persistent_snapshot"],
                )
                before = self.admission(f"stopped-{run}")
                if self.profile == "scoped":
                    # A readable proof copy is permitted only after the app's
                    # original stop, streams, port and snapshot are admitted.
                    contract.require(
                        not errors
                        and type(row["returncode"]) is int
                        and row["returncode"] == 0
                        and row["port_closed"] is True
                        and row.get("forced_cleanup") is False
                        and row.get("owned_group_remaining") is False
                        and contract.regular(self.paths["stderr"], 65536)
                        == self.notice,
                        "Scoped CLI export requires a known-normal stopped app.",
                    )
                    self.cli_readers(run, before)
        except Exception as exc:
            errors.append("observation: " + str(exc))
        suffix = "" if observe else ".cleanup"
        write_json(self.output / f"process/run-{run}{suffix}.json", row)
        contract.require(not errors, "; ".join(errors))
        contract.require(
            row["returncode"] == 0
            and row["port_closed"] is True
            and not row.get("forced_cleanup")
            and not row.get("owned_group_remaining")
            and contract.regular(self.paths["stderr"], 65536) == self.notice,
            "Installed process exit/diagnostics/ownership refused.",
        )
        if not observe:
            return
        write_json(
            self.runtime / "state.json",
            {
                **self.identity,
                "phase": "stopped",
                "run": run,
                "pid": self.process.pid,
                "port": self.inner.port,
                "exit_code": row["returncode"],
                "stop_method": row["stop_method"],
                "port_closed": row["port_closed"],
            },
        )

    def cli_readers(self, run, before):
        """Admit each actual frozen CLI after typed raw conservation checks."""
        from tools import installed_native_entry_contract as native
        from tools import installed_native_menu as menu

        snapshot = fixed_snapshot
        from tools.rc4_scoped_recovery_contract import TITLE, wrappers

        originals = [
            r
            for r in wrappers(before, "casebooks_scoped_v2")
            if r["document"]["title"] == TITLE
        ]
        contract.require(
            len(originals) == 1, "Stopped fixture has no unique scoped original."
        )
        saved = originals[0]
        result = {
            "before": before,
            "after": None,
            "operations": {},
            "reader_snapshots": {},
            "export_proof": None,
            "export_cleanup": {"fresh": [], "publish": []},
        }
        exported, _ = cli_export_paths(run, self.output)
        env = environment(self.runtime / "home", self.runtime / "capture-browser")
        try:
            for operation in (
                "casebooks.get",
                "casebooks.validate",
                "casebooks.build",
                "export",
            ):
                suffix = operation.replace(".", "-")
                before_op = self.admission(f"run-{run}.{suffix}")
                result["reader_snapshots"][operation] = {
                    "before": before_op,
                    "after": None,
                }
                contract.require(
                    contract.equal(before_op, before),
                    "Supporting CLI admission changed typed originals/settings.",
                )
                payload = self.output / f"process/run-{run}.{suffix}.input.json"
                body = (
                    {"document": saved["document"]}
                    if operation == "casebooks.validate"
                    else {"id": saved["id"]}
                )
                if operation == "casebooks.build":
                    body["revision"] = saved["revision"]
                write_json(payload, body)
                argv = (
                    [
                        BINARY,
                        "export",
                        "casebook",
                        saved["id"],
                        "--directory",
                        self.runtime / "data",
                        "-o",
                        exported,
                        "--machine",
                    ]
                    if operation == "export"
                    else [
                        BINARY,
                        "run",
                        operation,
                        "--input",
                        payload,
                        "--directory",
                        self.runtime / "data",
                        "--format",
                        "json",
                    ]
                )
                rows = []
                try:
                    if operation == "export":
                        fresh_cli_export(
                            run, self.output, cleanup=result["export_cleanup"]["fresh"]
                        )
                    code, raw = menu.command(
                        argv,
                        rows,
                        env=env,
                        timeout=20,
                        limit=MAX_RPC,
                        save_streams={
                            n: self.output / f"process/run-{run}.{suffix}.{n}"
                            for n in ("stdout", "stderr")
                        },
                    )
                    envelope = contract.json_object(raw)
                    native.stopped(rows[-1])
                    diagnostics = contract.regular(
                        self.output / f"process/run-{run}.{suffix}.stderr", MAX_RPC
                    )
                    contract.validate_cli_stderr(operation, diagnostics, str(exported))
                    contract.require(
                        type(code) is int
                        and code == 0
                        and rows[-1]["streams_complete"] is True
                        and native.stream_bytes(rows[-1]["stderr"]) == diagnostics
                        and rows[-1]["stdout"]["bytes"] == len(raw)
                        and rows[-1]["stdout"]["sha256"] == contract.sha(raw)
                        and envelope["ok"] is True
                        and envelope["schema"] == "sinter-operation-result/v1"
                        and envelope["operation"]
                        == ("casebooks.get" if operation == "export" else operation)
                        and envelope["version"] == self.identity["version"],
                        "Actual installed scoped CLI refused.",
                    )
                finally:
                    # Retain actual subprocess metadata even if cleanup/capture failed.
                    if rows:
                        result["operations"][operation] = rows[-1]
                    write_json(self.output / f"process/run-{run}.cli.json", result)
                after_op = snapshot(self.runtime / "data")
                result["reader_snapshots"][operation]["after"] = after_op
                write_json(
                    self.output / f"process/run-{run}.{suffix}.after-reader.json",
                    after_op,
                )
                write_json(self.output / f"process/run-{run}.cli.json", result)
                contract.require(
                    contract.equal(before_op, after_op),
                    "Supporting installed CLI changed typed originals/settings.",
                )
                if operation == "export":
                    result["export_proof"] = publish_cli_export(
                        run,
                        self.output,
                        saved["document"],
                        cleanup=result["export_cleanup"]["publish"],
                    )
                    write_json(self.output / f"process/run-{run}.cli.json", result)
            result["after"] = snapshot(self.runtime / "data")
            contract.require(
                contract.equal(before, result["after"]),
                "Supporting installed CLI changed typed originals/settings.",
            )
        finally:
            write_json(self.output / f"process/run-{run}.cli.json", result)

    def run(self):
        from tools import native_window_smoke as native

        self.thread.start()
        run, reaped = 1, False
        try:
            self.launch(run)
            while True:
                self.rpc.service()
                if self.process.poll() is not None and not reaped:
                    self.reap(run)
                    reaped = True
                path = self.runtime / "control.json"
                if path.exists():
                    control = read_json(path, 1024)
                    path.unlink()
                    contract.require(
                        set(control) == {"action"}, "Unknown lifecycle control fields."
                    )
                    action = control["action"]
                    if action == "stop" and self.process.poll() is None:
                        self.rows[-1]["stop_method"] = "terminate"
                        native.stop_process(self.process, self.rows[-1])
                    elif action == "restart" and reaped:
                        run += 1
                        contract.require(
                            run <= (6 if self.profile == "campaign" else 4),
                            "Unexpected installed process lifetime.",
                        )
                        self.launch(run)
                        reaped = False
                    elif action == "cleanup" and reaped:
                        break
                    else:
                        raise ValueError("Invalid installed lifecycle transition.")
                time.sleep(0.01)
        except Exception as exc:
            self.failure = type(exc).__name__ + ": " + str(exc)
            write_json(
                self.runtime / "state.json",
                {"phase": "failed", "failure": self.failure},
            )
        finally:
            if self.process is not None and not reaped:
                try:
                    if self.process.poll() is None:
                        self.rows[-1]["stop_method"] = "cleanup"
                    self.reap(run, observe=False)
                except Exception as exc:
                    self.failure = (self.failure or "") + "; cleanup: " + str(exc)
            for action in (self.inner.shutdown, self.inner.server_close):
                try:
                    action()
                except Exception as exc:
                    self.failure = (self.failure or "") + "; relay cleanup: " + str(exc)
            self.thread.join(timeout=5)
            deadline = time.monotonic() + 5
            while not self.inner.idle() and time.monotonic() < deadline:
                time.sleep(0.01)
            socket_path = self.runtime / "relay.sock"
            if not self.thread.is_alive() and self.inner.idle():
                socket_path.unlink(missing_ok=True)
            resources = {
                "inner_thread_closed": not self.thread.is_alive(),
                "inner_requests_closed": self.inner.idle(),
                "inner_socket_absent": not os.path.lexists(socket_path),
            }
            self.closed = (
                all(resources.values())
                and self.process is not None
                and self.process.poll() is not None
            )
            if not self.closed:
                self.failure = (
                    self.failure or ""
                ) + "; installed ownership cleanup incomplete"
            write_json(
                self.output / "processes.json",
                {
                    "rows": self.rows,
                    "failure": self.failure,
                    "closed": self.closed,
                    "resources": resources,
                },
            )


def seed_profile(runtime, output, source):
    """Source prepares fictional seed only; actual execution uses the frozen binary."""
    from tools.rc4_recovery_worker import seed

    # source_binding already compared every production module before this import/use.
    sys.path.insert(0, str(ROOT / "src"))
    value = seed(runtime / "data")
    write_json(
        output / "seed.json",
        {
            "schema": contract.SEED,
            "source_commit": source["commit"],
            "source_files": {
                n: r for n, r in source["files"].items() if n.startswith("src/")
            },
            "seed": value,
            "instrumentation": (
                "source-prepared fictional disabled watch; scheduler unchanged"
            ),
        },
    )
    capture = runtime / "capture-browser"
    capture.write_text(
        '#!/bin/sh\nprintf "%s" "$1" > "' + str(runtime / "launch-url.txt") + '"\n',
        encoding="utf-8",
    )
    capture.chmod(0o755)
    return value["snapshot"]


def run_inner():
    contract.require(
        platform.system() == "Linux"
        and os.geteuid() == 0
        and os.getpid() == 1
        and Path("/.dockerenv").is_file()
        and {p.name for p in Path("/sys/class/net").iterdir()} == {"lo"}
        and not os.environ.get("DISPLAY"),
        "Use only the owned offline root container.",
    )
    config = read_json(Path("/candidate/recovery-input.json"))
    contract.validate_config(config)
    archive = contract.regular(
        Path("/repository/committed-source.tar"), 128 * 1024 * 1024
    )
    source = source_binding(
        archive, config["source_commit"], source_records(ROOT), config["mode"]
    )
    from tools import installed_native_menu as menu
    from tools import native_window_smoke as native
    from tools.installed_menu_browser import browser_notice

    output = Path("/out/evidence")
    output.mkdir(mode=0o755)
    receipt = {
        "schema": contract.INNER,
        "source": source,
        "commands": [],
        "failure": None,
        "profiles": {},
        "provider_attempts": "unmeasured",
        "passed": False,
    }
    attempted = False
    try:
        contract.require(
            menu.package_state(receipt["commands"]) == "absent"
            and not any(os.path.lexists(p) for p in contract.INSTALLED_PATHS),
            "Existing package or residual Sinter paths refuse.",
        )
        args = SimpleNamespace(
            installer=Path("/candidate") / config["installer_name"],
            package_receipt=Path("/candidate") / config["package_receipt_name"],
        )
        package = receipt["package"] = menu.package_preflight(
            args, source, receipt["commands"]
        )
        receipt["package_control_indexes"] = list(
            range(len(receipt["commands"]) - 4, len(receipt["commands"]) - 1)
        )
        receipt["package_payload_command_index"] = len(receipt["commands"])
        code, payload = menu.command(
            ["dpkg-deb", "--fsys-tarfile", args.installer],
            receipt["commands"],
            limit=128 * 1024 * 1024,
            save_streams={n: output / ("package." + n) for n in ("stdout", "stderr")},
        )
        contract.require(
            code == 0
            and contract.sha(payload) == package["payload_tar_sha256"]
            and len(payload) == package["payload_tar_bytes"],
            "Actual retained package payload differs from preflight.",
        )
        contract.require(
            package["installer_sha256"] == config["installer_sha256"]
            and package["receipt_sha256"] == config["package_receipt_sha256"],
            "Package differs from external input pins.",
        )
        attempted = True
        code, _ = menu.command(
            ["dpkg", "-i", args.installer], receipt["commands"], timeout=60
        )
        contract.require(code == 0, "Owned installation failed.")
        receipt["installed_entries"], receipt["installed_binary"] = {}, {}
        menu.installed_identity(
            package,
            observations=receipt["installed_entries"],
            binary_observation=receipt["installed_binary"],
        )
        receipt["installed_package"] = menu.installed_package_version(
            package["package_version"], receipt["commands"]
        )
        home = Path("/out/diagnostic-home")
        home.mkdir(mode=0o700)
        env = {"PATH": os.defpath, "HOME": str(home), "LC_ALL": "C.UTF-8"}
        diag_row, diag_obs = {}, {}
        receipt["diagnostic"] = native.diagnose(
            BINARY, env, diag_row, observation=diag_obs
        )
        receipt["diagnostic_process"], receipt["diagnostic_observation"] = (
            diag_row,
            diag_obs,
        )
        contract.require(
            receipt["diagnostic"]["version"] == source["version"],
            "Frozen diagnostic version differs.",
        )
        expected = read_json(args.package_receipt, 2 * 1024 * 1024)
        selftest = output / "selftest.json"
        code, _ = menu.command(
            [BINARY, "--self-test", selftest], receipt["commands"], env=env, timeout=60
        )
        receipt["selftest_command"] = receipt["commands"][-1]
        receipt["selftest"] = read_json(selftest)
        contract.require(
            code == 0
            and receipt["commands"][-1]["stderr"]["bytes"] == 0
            and contract.equal(receipt["selftest"], expected["installed_test"])
            and receipt["selftest"]["frozen"] is True,
            "Actual installed selftest differs.",
        )
        identity = {
            "version": source["version"],
            "binary_sha256": package["binary_sha256"],
            "web": {
                n: r["sha256"]
                for n, r in source["files"].items()
                if n.startswith("src/sinter/web/")
            },
            "notice_base64": base64.b64encode(
                browser_notice((ROOT / "src/sinter/desktop.py").read_bytes())
            ).decode(),
        }
        prepare_cli_export_directory()
        for profile in PROFILES:
            runtime, proof = Path("/out/runtime") / profile, output / profile
            runtime.mkdir(parents=True, mode=0o777)
            runtime.chmod(0o777)
            proof.mkdir(mode=0o777)
            proof.chmod(0o777)
            for n in ("home", "rpc"):
                (runtime / n).mkdir(mode=0o777 if n == "rpc" else 0o700)
            # Host-owned ancestors remain 0700; the fictional exchange is writable.
            (runtime / "rpc").chmod(0o777)
            for n in ("process", "rpc", "inner-rpc", "installed-recovery", "advanced"):
                (proof / n).mkdir(mode=0o777)
                (proof / n).chmod(0o777)
            baseline = seed_profile(runtime, proof, source)
            lifecycle = InstalledLifecycle(
                runtime, proof, identity, baseline, profile, config["session"]
            )
            write_json(
                Path("/out/profile.json"),
                {"profile": profile, "session": config["session"]},
            )
            lifecycle.run()
            receipt["profiles"][profile] = {
                "closed": lifecycle.closed,
                "failure": lifecycle.failure,
                "lifetimes": len(lifecycle.rows),
            }
            contract.require(
                lifecycle.closed and lifecycle.failure is None,
                "Installed profile failed; retain raw evidence.",
            )
        receipt["passed"] = True
    except Exception as exc:
        receipt["failure"] = type(exc).__name__ + ": " + str(exc)
        (output / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        receipt["cleanup_errors"] = []

        def observe(label, action):
            try:
                return action()
            except BaseException as error:
                receipt["passed"] = False
                receipt["cleanup_errors"].append(
                    {
                        "resource": label,
                        "type": type(error).__name__,
                        "message": str(error)[:1024],
                    }
                )
                receipt["failure"] = (
                    (receipt["failure"] or "") + "; " + label + ": " + str(error)[:1024]
                )
                return None

        if attempted:

            def remove():
                try:
                    return menu.command(
                        ["dpkg", "-r", "sinter"], receipt["commands"], timeout=60
                    )[0]
                finally:
                    if receipt["commands"] and receipt["commands"][-1].get("argv") == [
                        "dpkg",
                        "-r",
                        "sinter",
                    ]:
                        receipt["removal_command"] = receipt["commands"][-1]

            code = observe("package removal", remove)
            state = observe(
                "package removal state", lambda: menu.removal_state(receipt["commands"])
            )
            if state is not None:
                receipt["removal"] = state
            absence = observe(
                "independent path absence",
                lambda: menu.observed_absence(
                    contract.INSTALLED_PATHS, receipt["commands"]
                ),
            )
            if absence is not None:
                receipt["absence"] = absence
            if code is not None and state is not None:
                observe(
                    "removal admission",
                    lambda: contract.validate_package_removal(
                        code,
                        receipt["removal_command"],
                        state,
                        receipt["commands"],
                    ),
                )
        qa = observe("QA source identity", lambda: source_records(ROOT))
        if qa is not None:
            receipt["qa_files_after"] = qa
        write_json(output / "inner.json", receipt)
    return 0 if receipt["passed"] and receipt["failure"] is None else 1


def close_host_profile(runtime, output, relay, thread, client, sessions, primary):
    """Always retain the primary failure and every independently attempted cleanup."""
    errors, attempts = [], []
    first = primary
    for label, action in (
        (
            "installed cleanup request",
            lambda: write_json(runtime / "control.json", {"action": "cleanup"}),
        ),
        ("relay shutdown", relay.shutdown),
        ("relay close", relay.server_close),
        ("relay join", lambda: thread.join(timeout=5)),
    ):
        row = {"resource": label, "succeeded": False}
        attempts.append(row)
        try:
            action()
            row["succeeded"] = True
        except BaseException as error:
            first = first or error
            diagnostic = {
                "resource": label,
                "type": type(error).__name__,
                "message": str(error)[:1024],
            }
            errors.append(diagnostic)
            row["error"] = diagnostic
    closed = False
    try:
        closed = not thread.is_alive() and relay.idle()
    except BaseException as error:
        first = first or error
        errors.append(
            {
                "resource": "relay observation",
                "type": type(error).__name__,
                "message": str(error)[:1024],
            }
        )
    result = {
        "relay_closed": closed,
        "model_route_requests": relay.model_requests,
        "relay_errors": relay.errors,
        "observation_requests": client.sequence,
        "body_failure": None
        if primary is None
        else {"type": type(primary).__name__, "message": str(primary)[:1024]},
        "cleanup_errors": errors,
        "cleanup_attempts": attempts,
        "browser_sessions": [session.observations() for session in sessions],
    }
    # Even failed profiles retain their final response; never replay a profile.
    try:
        write_json(output / "host-observations.json", result)
    except BaseException as error:
        first = first or error
        diagnostic = {
            "resource": "host response retention",
            "type": type(error).__name__,
            "message": str(error)[:1024],
        }
        errors.append(diagnostic)
        print(contract.canonical(diagnostic), file=sys.stderr)
    return result, first


def host_profiles(root, config, chromium):
    """Actual host browser, fixed UNIX transport and authoritative inner RPC."""
    from tools import installed_recovery_browser as legacy
    from tools import installed_workflow_browser as transport
    from tools import rc4_recovery_source as campaign
    from tools import rc4_scoped_recovery_source as scoped

    source = {
        p.relative_to(ROOT).as_posix(): p.read_bytes()
        for p in (ROOT / "src/sinter/web").iterdir()
        if p.is_file()
    }
    evidence, resources = root / "out/evidence", {}
    try:
        for profile in PROFILES:
            deadline = time.monotonic() + 120
            while True:
                path = root / "out/profile.json"
                if path.exists() and read_json(path)["profile"] == profile:
                    break
                contract.require(
                    time.monotonic() < deadline,
                    "Installed profile readiness timed out.",
                )
                time.sleep(0.05)
            runtime, output = root / "out/runtime" / profile, evidence / profile
            transport.wait_state(runtime, "running", 1)
            client = ObservationClient(runtime, profile, config["session"], output)
            relay = transport.Relay(runtime)
            thread = threading.Thread(target=relay.serve_forever, daemon=True)
            thread.start()
            failed, sessions = None, []
            try:
                args = SimpleNamespace(
                    output=output,
                    chromium=chromium,
                    version=config["version"],
                    source_fixture=False,
                )
                session = OwnedBrowserSession(profile + "-base")
                sessions.append(session)
                if profile == "campaign":
                    observed = legacy.browser_workflow(
                        args,
                        runtime,
                        relay,
                        source,
                        workspace_observer=client.snapshot,
                        browser_session=session,
                    )
                    write_json(output / "base-observations.json", observed)
                    phases = read_json(
                        output / "installed-recovery/campaign-phases.json"
                    )
                    session = OwnedBrowserSession("campaign-advanced")
                    sessions.append(session)
                    campaign.advanced_workflow(
                        args, runtime, relay, phases, browser_session=session
                    )
                else:
                    scoped.browser_workflow(
                        args,
                        runtime,
                        relay,
                        snapshot_observer=client.snapshot,
                        protocol_observer=client.protocol,
                        browser_session=session,
                    )
                contract.require(
                    relay.model_requests == 0 and relay.errors == 0,
                    "Relay observed model routes or transport errors.",
                )
            except BaseException as exc:
                failed = exc
            finally:
                resources[profile], failed = close_host_profile(
                    runtime, output, relay, thread, client, sessions, failed
                )
            if failed:
                raise failed
        return resources
    finally:
        primary = sys.exc_info()[1]
        try:
            write_json(root / "out/host-resources.json", resources)
        except BaseException as error:
            if primary is None:
                raise
            print(
                contract.canonical(
                    {
                        "resource": "host aggregate retention",
                        "type": type(error).__name__,
                        "message": str(error)[:1024],
                    }
                ),
                file=sys.stderr,
            )


def verify(args):
    """Read-only re-review with explicit external candidate/package/QA pins."""
    from tools import installed_native_container as owner

    root = args.proof_root.resolve(strict=True)
    config = read_json(root / "candidate/recovery-input.json")
    contract.validate_config(config)
    qa = source_records(ROOT)
    contract.require(
        qa[SOURCE_FILE]["sha256"] == args.owner_sha256
        and contract.equal(qa, config["qa_files"])
        and config["source_commit"] == args.source_commit
        and config["installer_sha256"] == args.installer_sha256
        and config["package_receipt_sha256"] == args.package_receipt_sha256,
        "External reviewed QA/candidate/package pins differ.",
    )
    pins = owner.pins_for(
        root,
        args.owner_sha256,
        args.source_commit,
        config["installer_name"],
        config["package_receipt_name"],
    )
    return contract.validate(
        root,
        read_json(root / "installed-recovery.json", 16 * 1024 * 1024),
        pins,
        config,
    )


def browser_identity(path):
    """Bind the selected headless launch file; bundling is not proved."""
    contract.require(
        type(path) is str and path, "Select an existing headless Chromium launch file."
    )
    selected = Path(path).resolve(strict=True)
    contract.require(
        selected.is_absolute() and os.access(selected, os.X_OK),
        "The selected Chromium launch file is not executable.",
    )
    return {
        "path": str(selected),
        "sha256": contract.sha(contract.regular(selected, 512 * 1024 * 1024)),
    }


CACHE_NAME = "fbdd96f424c67bd94b857b415c88a5711d0711f4d7a62d733ee650e5afe87766"
CACHE_DIRECTORY = r"com\.google\.Chrome\.chrome_chrome_url_fetcher_\.[A-Za-z0-9]{6}"
OWNED_TEMP_FILE = r"\.org\.chromium\.Chromium\.[A-Za-z0-9]{6}"
OWNED_TEMP_LIMIT = 524_288


def browser_temp_metadata(info: os.stat_result) -> dict[str, int]:
    """Retain stable metadata; reading itself may change access time."""
    return {
        name: getattr(info, "st_" + name)
        for name in (
            "dev",
            "ino",
            "mode",
            "uid",
            "gid",
            "nlink",
            "size",
            "mtime_ns",
            "ctime_ns",
        )
    }


def owned_browser_temp_bytes(path: Path, before: os.stat_result) -> bytes:
    """Read one bounded private shape, without claiming filename provenance."""
    expected = browser_temp_metadata(before)
    contract.require(
        stat.S_ISREG(before.st_mode)
        and stat.S_IMODE(before.st_mode) == 0o600
        and before.st_uid == (os.getuid() if hasattr(os, "getuid") else 0)
        and before.st_gid == (os.getgid() if hasattr(os, "getgid") else 0)
        and before.st_nlink == 1
        and before.st_size <= OWNED_TEMP_LIMIT,
        "Bounded private single-link browser temporary file required.",
    )
    raw = contract.regular(path, OWNED_TEMP_LIMIT)
    contract.require(
        browser_temp_metadata(path.lstat()) == expected and len(raw) == before.st_size,
        "Browser temporary file metadata changed while reading.",
    )
    return raw


def cleanup_browser_after_host(root, host, browser, *, failed):
    """A held failure may clean a completely captured normal exit of one."""
    expected = (
        1
        if failed is True
        and type(host.get("exit_code")) is int
        and host["exit_code"] == 1
        and host.get("passed") is False
        else 0
    )
    return clean_browser_temp(root, host, browser, expected_exit=expected)


def clean_browser_temp(root, host, browser, *, expected_exit: int = 0):
    """Clean owned caches after an exactly observed exit; never qualify failure."""
    from tools import installed_native_entry_contract as native

    directory = root / "t"
    observation = {
        "attempted": False,
        "inventory": {},
        "outcomes": [],
        "complete": False,
        "failure": None,
    }
    browser["temporary_cleanup"] = observation
    try:
        contract.require(
            directory.is_dir()
            and not directory.is_symlink()
            and browser["temporary_directory"] == str(directory),
            "Fixed browser temporary directory differs.",
        )
        contract.require(
            type(expected_exit) is int and expected_exit in (0, 1),
            "Only an explicit completed collector exit of zero or one is supported.",
        )
        native.stopped(host, expected_exit=expected_exit)
        contract.require(
            host["streams_complete"] is True,
            "Collector capture must finish before cache cleanup.",
        )
        if expected_exit == 1:
            native.exact(host.get("passed"), False, "Failed collector status differs.")
            for name in ("stdout", "stderr"):
                native.stream_bytes(host.get(name))
        observation["attempted"] = True
        files, folders, owned_files = [], [], {}
        temporary_info = directory.lstat()
        # Bound enumeration before reading or deleting any cache entry.
        entries = []
        for folder in directory.iterdir():
            entries.append(folder)
            contract.require(
                len(entries) <= 64, "Browser cache inventory exceeds bound."
            )
            if (
                folder.is_dir()
                and not folder.is_symlink()
                and re.fullmatch(CACHE_DIRECTORY, folder.name)
            ):
                for child in folder.iterdir():
                    entries.append(child)
                    contract.require(
                        len(entries) <= 64, "Browser cache inventory exceeds bound."
                    )
        for path in sorted(entries):
            relative = path.relative_to(directory).as_posix()
            info = path.lstat()
            row = {
                "type": "directory"
                if stat.S_ISDIR(info.st_mode)
                else "file"
                if stat.S_ISREG(info.st_mode)
                else "special",
                "bytes": info.st_size,
            }
            observation["inventory"][relative] = row
            contract.require(
                info.st_uid == (os.getuid() if hasattr(os, "getuid") else 0)
                and not path.is_symlink(),
                "Foreign/linked browser cache refused.",
            )
            if row["type"] == "directory":
                contract.require(
                    len(path.relative_to(directory).parts) == 1
                    and re.fullmatch(CACHE_DIRECTORY, path.name),
                    "Unknown browser temporary directory.",
                )
                folders.append((path, info))
            else:
                if (
                    row["type"] == "file"
                    and len(path.relative_to(directory).parts) == 1
                    and re.fullmatch(OWNED_TEMP_FILE, path.name)
                ):
                    contract.require(
                        temporary_info.st_uid == info.st_uid
                        and temporary_info.st_gid == info.st_gid
                        and stat.S_IMODE(temporary_info.st_mode) == 0o700,
                        "Owned private browser temporary directory required.",
                    )
                    for name in ("stdout", "stderr"):
                        native.stream_bytes(host.get(name))
                    row["metadata"] = browser_temp_metadata(info)
                    row.update(contract.record(owned_browser_temp_bytes(path, info)))
                    owned_files[path] = row
                    files.append((path, info))
                    continue
                contract.require(
                    row["type"] == "file"
                    and info.st_nlink == 1
                    and len(path.relative_to(directory).parts) == 2
                    and re.fullmatch(CACHE_DIRECTORY, path.parent.name)
                    and path.name == CACHE_NAME,
                    "Unknown or special browser cache entry.",
                )
                raw = contract.regular(path, 32768)
                row.update(contract.record(raw))
                files.append((path, info))
        first = None
        for path, before in [*files, *sorted(folders, reverse=True)]:
            outcome = {"path": path.relative_to(directory).as_posix(), "removed": False}
            observation["outcomes"].append(outcome)
            try:
                after = path.lstat()
                if path in owned_files:
                    current_directory = directory.lstat()
                    contract.require(
                        (temporary_info.st_dev, temporary_info.st_ino)
                        == (current_directory.st_dev, current_directory.st_ino)
                        and current_directory.st_uid == temporary_info.st_uid
                        and current_directory.st_gid == temporary_info.st_gid
                        and stat.S_IMODE(current_directory.st_mode) == 0o700,
                        "Browser temporary directory changed before cleanup.",
                    )
                    raw = owned_browser_temp_bytes(path, before)
                    contract.require(
                        contract.record(raw)
                        == {
                            "bytes": owned_files[path]["bytes"],
                            "sha256": owned_files[path]["sha256"],
                        },
                        "Browser temporary bytes changed before cleanup.",
                    )
                contract.require(
                    (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
                    "Browser cache identity changed before cleanup.",
                )
                if path.is_dir():
                    path.rmdir()
                else:
                    contract.require(
                        (before.st_size, before.st_mtime_ns)
                        == (after.st_size, after.st_mtime_ns),
                        "Browser cache changed before cleanup.",
                    )
                    path.unlink()
                outcome["removed"] = True
            except BaseException as error:
                outcome["error"] = {
                    "type": type(error).__name__,
                    "message": str(error)[:1024],
                }
                first = first or error
        if first is not None:
            raise first
        contract.require(
            not any(directory.iterdir()), "Owned browser temporary files remain."
        )
        observation["complete"] = True
    except BaseException as error:
        observation["failure"] = {
            "type": type(error).__name__,
            "message": str(error)[:1024],
        }
        raise


def prepare(args):
    """Stage fresh private siblings without inherited account resources."""
    contract.require(
        platform.system() == "Linux", "Installed recovery supports Linux only."
    )
    qa = source_records(ROOT)
    contract.require(
        qa[SOURCE_FILE]["sha256"] == args.owner_sha256, "Reviewed producer pin differs."
    )
    output = args.output.resolve()
    contract.require(
        not os.path.lexists(output)
        and output.parent.stat().st_uid == os.geteuid()
        and not output.parent.stat().st_mode & 0o022,
        "Use a fresh owned private home output.",
    )
    inputs = (
        ROOT,
        args.repository.resolve(),
        args.installer.resolve(),
        args.package_receipt.resolve(),
    )
    contract.require(
        all(
            not output.is_relative_to(p) and not p.is_relative_to(output)
            for p in inputs
        ),
        "Output must be disjoint from inputs.",
    )
    contract.require(
        len(str(output / "t").encode()) <= 55,
        "Use a short owned output so Chromium socket paths remain bounded.",
    )
    browser = browser_identity(args.chromium)
    output.mkdir(mode=0o700)
    for n in ("source", "repository", "candidate", "out", "raw", "client", "t"):
        (output / n).mkdir(
            mode=0o755 if n in ("source", "repository", "candidate") else 0o700
        )
    (output / "out").chmod(0o777)
    (output / "client/.docker").mkdir(mode=0o700)
    env = {
        "PATH": os.defpath,
        "HOME": str(output / "client"),
        "DOCKER_CONFIG": str(output / "client/.docker"),
        "TMPDIR": str(output / "t"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    # Exact full commit is checked before argv construction; no arbitrary ref/command.
    contract.require(
        type(args.source_commit) is str
        and re.fullmatch(r"[0-9a-f]{40}", args.source_commit),
        "Use full commit.",
    )
    process = subprocess.run(
        ["git", "-C", str(args.repository), "archive", args.source_commit],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )
    (output / "raw/source-archive.stdout").write_bytes(process.stdout)
    (output / "raw/source-archive.stderr").write_bytes(process.stderr)
    contract.require(
        process.returncode == 0 and not process.stderr, "Actual Git archive failed."
    )
    binding = source_binding(process.stdout, args.source_commit, qa, args.boundary)
    (output / "repository/committed-source.tar").write_bytes(process.stdout)
    for n in qa:
        target = output / "source" / n
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contract.regular(ROOT / n, 128 * 1024 * 1024))
    for p in (args.installer, args.package_receipt):
        (output / "candidate" / p.name).write_bytes(
            contract.regular(p, 128 * 1024 * 1024)
        )
    config = {
        "source_commit": args.source_commit,
        "version": binding["version"],
        "mode": args.boundary,
        "installer_name": args.installer.name,
        "package_receipt_name": args.package_receipt.name,
        "installer_sha256": contract.sha(
            contract.regular(args.installer, 128 * 1024 * 1024)
        ),
        "package_receipt_sha256": contract.sha(
            contract.regular(args.package_receipt, 2 * 1024 * 1024)
        ),
        "session": secrets.token_hex(16),
        "qa_files": qa,
        "browser": browser,
    }
    write_json(output / "candidate/recovery-input.json", config)
    for tree in ("source", "repository", "candidate"):
        for p in (output / tree).rglob("*"):
            p.chmod(0o555 if p.is_dir() else 0o444)
        (output / tree).chmod(0o555)
    return output, env, qa, binding, config


def run(args):
    root, env, qa, binding, config = prepare(args)
    from tools import installed_native_container as owner
    from tools import installed_native_entry_contract as native

    pins = owner.pins_for(
        root,
        args.owner_sha256,
        args.source_commit,
        args.installer.name,
        args.package_receipt.name,
    )
    commands, rows, cleanup = [], [], []
    identifier, exited, error = None, False, None
    thread = None
    receipt = {
        "schema": contract.OUTER,
        "source": binding,
        "owner_sha256": args.owner_sha256,
        "commands": commands,
        "resources": {},
        "failure": None,
        "installed_rehearsal_passed": False,
        "release_qualified": False,
        "prior_replacement_tested": False,
        "native_tested": False,
        "browser": {
            **config["browser"],
            "sha256_after": None,
            "temporary_directory": str(root / "t"),
            "temporary_empty_before": not any((root / "t").iterdir()),
            "temporary_empty_after": None,
        },
    }
    try:
        receipt["docker_client"] = owner.client_identity(root, env, rows)
        code, raw = owner.docker_row(
            "image", ["docker", "image", "inspect", IMAGE], root, env, commands, rows
        )
        contract.require(code == 0, "Retained image unavailable; never pull.")
        native.validate_image(raw, pins)
        name = "sinter-native-entry-" + secrets.token_hex(6)
        argv = outer_argv(pins, name)
        code, raw = owner.docker_row("create", argv, root, env, commands, rows)
        candidate_id = contract.admitted_create(commands[-1], raw)
        identifier = candidate_id
        code, raw = owner.docker_row(
            "created", ["docker", "inspect", identifier], root, env, commands, rows
        )
        contract.require(code == 0, "Created inspect failed.")
        native.validate_container_observation(
            json.loads(raw)[0], pins, outer_argv, name, identifier, "created"
        )
        start_error = []

        def start():
            try:
                code, _ = owner.docker_row(
                    "start",
                    ["docker", "start", "-a", identifier],
                    root,
                    env,
                    commands,
                    rows,
                    timeout=600,
                )
                contract.require(code == 0, "Installed inner process failed.")
            except Exception as exc:
                start_error.append(exc)

        thread = threading.Thread(target=start, daemon=True)
        thread.start()
        from tools import installed_native_menu as menu

        host_argv = [
            sys.executable,
            "-B",
            str(root / "source" / SOURCE_FILE),
            "host",
            "--proof-root",
            str(root),
        ]
        host_argv += ["--chromium", config["browser"]["path"]]
        host_rows = []
        try:
            code, _ = menu.command(
                host_argv,
                host_rows,
                env=env,
                timeout=500,
                save_streams={
                    n: root / "raw" / ("host." + n) for n in ("stdout", "stderr")
                },
            )
            contract.require(code == 0, "Actual owned browser collector failed.")
        finally:
            if host_rows:
                receipt["host_process"] = host_rows[-1]
        receipt["resources"] = read_json(root / "out/host-resources.json")
        thread.join(timeout=120)
        contract.require(
            not thread.is_alive() and not start_error,
            "Owned inner did not finish cleanly.",
        )
        code, raw = owner.docker_row(
            "exited", ["docker", "inspect", identifier], root, env, commands, rows
        )
        state = json.loads(raw)[0]["State"]
        exited = state["Running"] is False and state["Status"] == "exited"
        contract.require(code == 0 and exited, "Container exit not observed.")
    except Exception as exc:
        error = exc
        receipt["failure"] = type(exc).__name__ + ": " + str(exc)
    finally:
        receipt["cleanup_errors"] = []

        def cleanup_observe(label, action):
            nonlocal error
            try:
                return action()
            except BaseException as exc:
                error = error or exc
                receipt["cleanup_errors"].append(
                    {
                        "resource": label,
                        "type": type(exc).__name__,
                        "message": str(exc)[:1024],
                    }
                )
                receipt["failure"] = (
                    (receipt["failure"] or "") + "; " + label + ": " + str(exc)[:1024]
                )
                return None

        if identifier:
            if not exited and not any(r["role"] == "exited" for r in commands):

                def observe_exit():
                    code, raw = owner.docker_row(
                        "exited",
                        ["docker", "inspect", identifier],
                        root,
                        env,
                        commands,
                        rows,
                    )
                    contract.require(code == 0, "Post-run inspect failed.")
                    state = json.loads(raw)[0]["State"]
                    return state["Running"] is False and state["Status"] == "exited"

                exited = cleanup_observe("post-run exit", observe_exit) is True
            if not exited:
                for role, argv in (
                    (
                        "cleanup-term",
                        ["docker", "kill", "--signal", "SIGTERM", identifier],
                    ),
                    ("cleanup-wait", ["docker", "wait", identifier]),
                ):
                    cleanup_observe(
                        role,
                        lambda role=role, argv=argv: owner.capture(
                            role, argv, root, env, cleanup, timeout=8
                        ),
                    )

            def remove_container():
                code, _ = owner.docker_row(
                    "remove",
                    ["docker", "rm", *([] if exited else ["-f"]), identifier],
                    root,
                    env,
                    commands,
                    rows,
                )
                contract.require(code == 0, "Owned container removal failed.")

            cleanup_observe("container remove", remove_container)

            def observe_removed():
                code, _ = owner.docker_row(
                    "removed",
                    ["docker", "inspect", identifier],
                    root,
                    env,
                    commands,
                    rows,
                )
                contract.require(code == 1, "Owned absence not observed.")
                native.validate_removal(commands[-2], commands[-1], identifier)

            cleanup_observe("container absence", observe_removed)
        if thread is not None:
            thread.join(timeout=20)
            if thread.is_alive():
                error = error or ValueError("Owned attach client thread remains.")
                receipt["failure"] = (
                    receipt["failure"] or ""
                ) + "; owned attach thread remains"
        # Receipt preservation must survive a final identity/read observation fault.
        observations = []
        if "docker_client" in receipt:
            client = receipt["docker_client"]
            observations.append(
                (
                    "Docker client identity",
                    lambda: client.update(
                        sha256_after=contract.sha(
                            contract.regular(Path(client["path"]), 128 * 1024 * 1024)
                        )
                    ),
                )
            )
        observations += [
            (
                "browser identity",
                lambda: receipt["browser"].update(
                    sha256_after=browser_identity(config["browser"]["path"])["sha256"]
                ),
            ),
            (
                "browser cache cleanup",
                lambda: cleanup_browser_after_host(
                    root,
                    receipt.get("host_process", {}),
                    receipt["browser"],
                    failed=error is not None,
                ),
            ),
            (
                "browser temporary cleanup",
                lambda: receipt["browser"].update(
                    temporary_empty_after=not any((root / "t").iterdir())
                ),
            ),
            (
                "QA source identity",
                lambda: receipt.update(qa_files_after=source_records(ROOT)),
            ),
        ]
        for label, observe in observations:
            try:
                observe()
            except Exception as exc:
                error = error or exc
                receipt["failure"] = (
                    (receipt["failure"] or "") + "; " + label + ": " + str(exc)
                )
        receipt["cleanup"] = cleanup
        write_json(root / "installed-recovery.json", receipt)
    if error:
        raise error
    try:
        native.validate_lifecycle(commands, pins, outer_argv)
        result = contract.validate(root, receipt, pins, config, _pending=True)
    except Exception as exc:
        receipt["failure"] = "verification: " + type(exc).__name__ + ": " + str(exc)
        if "cli_export_close_outcomes" in exc.__dict__:
            receipt["proof_exchange_close_outcomes"] = exc.__dict__[
                "cli_export_close_outcomes"
            ]
        write_json(root / "installed-recovery.json", receipt)
        raise
    receipt["installed_rehearsal_passed"] = True
    receipt["verification"] = result
    write_json(root / "installed-recovery.json", receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("inner")
    verify_parser = sub.add_parser(
        "verify", help="Read-only artifact verification; never launches Docker."
    )
    verify_parser.add_argument("--proof-root", type=Path, required=True)
    for name in (
        "owner-sha256",
        "source-commit",
        "installer-sha256",
        "package-receipt-sha256",
    ):
        verify_parser.add_argument("--" + name, required=True)
    host_parser = sub.add_parser("host", help=argparse.SUPPRESS)
    host_parser.add_argument("--proof-root", type=Path, required=True)
    host_parser.add_argument("--chromium")
    run_parser = sub.add_parser("run")
    run_parser.add_argument(
        "--boundary", choices=("development", "candidate"), required=True
    )
    run_parser.add_argument("--repository", type=Path, required=True)
    run_parser.add_argument("--source-commit", required=True)
    run_parser.add_argument("--installer", type=Path, required=True)
    run_parser.add_argument("--package-receipt", type=Path, required=True)
    run_parser.add_argument("--owner-sha256", required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--chromium", default=os.environ.get("SINTER_CHROMIUM"))
    args = parser.parse_args(argv)
    if sys.flags.optimize:
        parser.exit(1, "Run without Python optimisation.\n")
    try:
        if args.mode == "inner":
            return run_inner()
        if args.mode == "verify":
            verify(args)
            print("Installed recovery artifacts verified; no release qualification.")
            return 0
        if args.mode == "host":
            root = args.proof_root.resolve(strict=True)
            contract.require(
                ROOT == root / "source",
                "The host collector must use its owned staged source.",
            )
            config = read_json(root / "candidate/recovery-input.json")
            contract.require(
                contract.equal(source_records(ROOT), config["qa_files"]),
                "Host collector source differs from the pinned QA origin.",
            )
            contract.require(
                contract.equal(browser_identity(args.chromium), config["browser"])
                and os.environ.get("TMPDIR") == str(root / "t")
                and not any((root / "t").iterdir()),
                "Host browser identity/temporary directory differs.",
            )
            result = host_profiles(root, config, args.chromium)
            contract.require(
                contract.equal(browser_identity(args.chromium), config["browser"]),
                "Host browser identity changed.",
            )
            # The outer owner inventories and cleans this fixed temporary tree
            # only after this collector is reaped and its full streams retained.
            write_json(root / "out/host-resources.json", result)
            return 0
        return run(args) and 0
    except Exception as exc:
        details = ""
        if "cli_export_close_outcomes" in exc.__dict__:
            details = (
                "CLI proof descriptor outcomes: "
                + contract.canonical(exc.__dict__["cli_export_close_outcomes"])
                + "\n"
            )
        parser.exit(1, type(exc).__name__ + ": " + str(exc) + "\n" + details)


if __name__ == "__main__":
    raise SystemExit(main())
