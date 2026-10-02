"""Own the unchanged installed garden UI journey with retained RC4 lifetimes.

The run command installs only in an existing restricted, disposable container.
It is not a Python-free cold-install gate or release authorisation. No download,
account profile, model call, source fixture or DEV evidence can qualify this route.
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import platform
import re
import secrets
import socket
import stat
import subprocess
import sys
import threading
import time
import traceback
import zipfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from tools import rc4_installed_workflow_contract as contract  # noqa: E402
from tools import rc4_replacement_probe as evidence  # noqa: E402


class Attempts:
    """Keep the first actual exception and attempt every independent cleanup."""

    def __init__(self, primary=None):
        self.first = primary
        self.errors, self.rows = [], []

    def call(self, label, action):
        row = {"resource": label, "succeeded": False}
        self.rows.append(row)
        try:
            value = action()
            row["succeeded"] = True
            return value
        except BaseException as error:
            self.first = self.first or error
            detail = {
                "resource": label,
                "type": type(error).__name__,
                "message": str(error)[:4096],
            }
            row["error"] = detail
            self.errors.append(detail)
            return None

    def raise_first(self):
        if self.first is not None:
            if self.errors:
                print(
                    contract.recovery.canonical({"cleanup_errors": self.errors}),
                    file=sys.stderr,
                )
            raise self.first


def write_json(path, value):
    """Preserve failed temporary bytes if final evidence delivery fails."""
    path = Path(path)
    raw = (contract.recovery.canonical(value) + "\n").encode("utf-8")
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("xb") as stream:
        stream.write(raw)
    temporary.replace(path)


def serialized_receipt(value):
    # Valid Unicode matches the unchanged writer; surrogates remain reversible.
    return (contract.recovery.canonical(value) + "\n").encode(
        "utf-8", "backslashreplace"
    )


def diagnostic_failures(error):
    """Retain compound faults only within this source-fixed writer activation."""
    failures, seen = [error], {id(error)}
    code = getattr(write_json, "__code__", None)
    trace, active, frames = error.__traceback__, False, set()
    while trace is not None:
        active |= trace.tb_frame.f_code is code
        if active:
            frames.add(trace.tb_frame)
        trace = trace.tb_next
    candidate = error.__context__
    while candidate is not None and id(candidate) not in seen:
        trace, owned = candidate.__traceback__, False
        while trace is not None:
            owned |= trace.tb_frame in frames
            trace = trace.tb_next
        if not owned:
            break
        failures.append(candidate)
        seen.add(id(candidate))
        candidate = candidate.__context__
    return tuple(reversed(failures))


def publish_receipt(role, path, value, primary=None):
    """Retain exact failed bytes; successful delivery preserves body exceptions."""
    publication = evidence.EvidencePublisher(
        role,
        primary,
        [],
        writer=write_json,
        serializer=serialized_receipt,
        failure_schema="sinter-rc4-workflow-failed-evidence/v1",
        unwrap_primary=True,
        failure_observer=diagnostic_failures,
    )
    publication.attempt(path, value)
    if publication.errors:
        publication.finish(Path(path).with_name(Path(path).name + ".failed.json"))


def read_json(path, limit=16 * 1024 * 1024):
    return contract.read_json(contract.regular(Path(path), limit))


def wait(path, predicate=lambda value: True, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            value = read_json(path)
            if value.get("phase") == "failed":
                raise ValueError("Owned peer failed: " + str(value.get("failure")))
            if predicate(value):
                return value
        time.sleep(0.02)
    raise TimeoutError("Owned workflow peer did not complete; nothing is replayed.")


def closed_port(port):
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def validate_zip(raw, commit, qa):
    """Require exact Git ZIP origin and complete bytes, not a version projection."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        contract.require(
            archive.comment == commit.encode("ascii"), "Source ZIP Git origin differs."
        )
        files, seen, total = {}, set(), 0
        for row in archive.infolist():
            name = row.filename.rstrip("/") if row.is_dir() else row.filename
            from pathlib import PurePosixPath

            logical = PurePosixPath(name)
            contract.require(
                name
                and name not in seen
                and not logical.is_absolute()
                and ".." not in logical.parts
                and str(logical) == name
                and "\\" not in name
                and len(seen) < 8192,
                "Source ZIP role/path differs.",
            )
            seen.add(name)
            mode = row.external_attr >> 16
            contract.require(
                not row.flag_bits & 1
                and mode in (0, 0o100644, 0o100755, 0o40775)
                and (not mode or stat.S_ISDIR(mode) == row.is_dir()),
                "Encrypted or non-regular source ZIP member refuses.",
            )
            if row.is_dir():
                contract.require(row.file_size == 0, "Source ZIP directory has bytes.")
                continue
            total += row.file_size
            contract.require(
                row.file_size <= contract.MAX_FILE and total <= contract.MAX_TOTAL,
                "Source ZIP exceeds its finite bound.",
            )
            files[name] = contract.record(archive.read(row))
        contract.require(contract.equal(files, qa), "Complete source ZIP bytes differ.")
        parents = {
            parent.as_posix()
            for name in files
            for parent in Path(name).parents
            if str(parent) != "."
        }
        contract.require(
            seen - set(files) == parents, "Source ZIP directory closure differs."
        )


def prepare(args):
    from tools import installed_native_menu as menu
    from tools import rc4_installed_recovery as recovery

    contract.require(
        platform.system() == "Linux", "This actual installed route supports Linux only."
    )
    contract.require(
        0 < os.geteuid() <= 2**31 - 1,
        "Prepare this workflow as an observed nonprivileged user; UID 0 is unsupported.",
    )
    qa = recovery.source_records(ROOT)
    contract.qa_inventory(qa)
    contract.require(
        qa[contract.SOURCE_FILE]["sha256"] == args.owner_sha256,
        "Independently reviewed workflow owner pin differs.",
    )
    root = args.output.resolve()
    contract.require(
        not os.path.lexists(root)
        and root.parent.stat().st_uid == os.geteuid()
        and not root.parent.stat().st_mode & 0o022
        and len(os.fsencode(root / "t")) <= 55,
        "Choose a fresh short owned private home output.",
    )
    for origin in (
        ROOT,
        args.repository.resolve(),
        args.installer.resolve(),
        args.package_receipt.resolve(),
    ):
        contract.require(
            not root.is_relative_to(origin) and not origin.is_relative_to(root),
            "Owned workflow output must be disjoint from every original input.",
        )
    contract.require(
        type(args.source_commit) is str
        and re.fullmatch("[0-9a-f]{40}", args.source_commit),
        "Full source commit required.",
    )
    browser = recovery.browser_identity(str(args.chromium))
    root.mkdir(mode=0o700)
    for name in (
        "source",
        "repository",
        "candidate",
        "out",
        "runtime",
        "raw",
        "client",
        "t",
    ):
        (root / name).mkdir(
            mode=0o755 if name in {"source", "repository", "candidate"} else 0o700
        )
    (root / "out").chmod(0o777)
    (root / "runtime").chmod(0o777)
    for name in ("home", "data", "process"):
        (root / "runtime" / name).mkdir(mode=0o700)
    (root / "client/.docker").mkdir(mode=0o700)
    env = {
        "PATH": os.defpath,
        "HOME": str(root / "client"),
        "DOCKER_CONFIG": str(root / "client/.docker"),
        "TMPDIR": str(root / "t"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    source_commands = []
    for fmt, name in (
        ("tar", "committed-source.tar"),
        ("zip", f"sinter-{contract.VERSION}-source.zip"),
    ):
        primary = None
        try:
            code, raw = menu.command(
                [
                    "git",
                    "-C",
                    str(args.repository.resolve()),
                    "archive",
                    "--format=" + fmt,
                    args.source_commit,
                ],
                source_commands,
                env=env,
                timeout=30,
                limit=contract.MAX_TOTAL,
                save_streams={
                    key: root / "raw" / ("source-" + fmt + "." + key)
                    for key in ("stdout", "stderr")
                },
            )
        except BaseException as error:
            primary = error
            raise
        finally:
            publish_receipt(
                "preparation",
                root / "raw/source-commands.json",
                {"commands": source_commands},
                primary,
            )
        contract.require(
            code == 0
            and contract.native.stream_bytes(source_commands[-1]["stderr"]) == b"",
            "Actual Git archive failed.",
        )
        (root / "repository" / name).write_bytes(raw)
        if fmt == "tar":
            binding = recovery.source_binding(raw, args.source_commit, qa, "candidate")
        else:
            validate_zip(raw, args.source_commit, qa)
    for name in qa:
        target = root / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contract.regular(ROOT / name, contract.MAX_FILE))
    for path in (args.installer, args.package_receipt):
        (root / "candidate" / path.name).write_bytes(
            contract.regular(path, contract.MAX_FILE)
        )
    inputs = contract.config(
        {
            "schema": contract.CONFIG,
            "source_commit": args.source_commit,
            "version": binding["version"],
            "qa_files": qa,
            "owner_sha256": args.owner_sha256,
            "installer_name": args.installer.name,
            "package_receipt_name": args.package_receipt.name,
            "installer_sha256": contract.sha(
                contract.regular(args.installer, contract.MAX_FILE)
            ),
            "package_receipt_sha256": contract.sha(
                contract.regular(args.package_receipt, 2 * 1024 * 1024)
            ),
            "uid": os.geteuid(),
            "gid": os.getegid(),
            "browser": browser,
            "repository": str(args.repository.resolve()),
        }
    )
    write_json(root / "candidate/workflow-input.json", inputs)
    for name in ("source", "repository", "candidate"):
        for path in (root / name).rglob("*"):
            path.chmod(0o555 if path.is_dir() else 0o444)
        (root / name).chmod(0o555)
    return root, env, qa, binding, inputs


def app_environment():
    return {
        "PATH": os.defpath,
        "HOME": "/proof/home",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "BROWSER": "/proof/capture-browser",
    }


class Controller:
    """Two normal UI quits, one actual restart; every stop retains full streams."""

    def __init__(self, runtime, identity):
        from tools.rc4_installed_recovery import owned_inner_relay

        self.runtime, self.identity = runtime, identity
        self.inner = owned_inner_relay(runtime)
        self.thread = threading.Thread(target=self.inner.serve_forever, daemon=True)
        self.process, self.rows, self.streams, self.paths = None, [], {}, {}
        self.failure = None
        self.acquisition_cleanup = []

    def launch(self, run):
        from tools.installed_workflow_browser import inner_address

        capture = self.runtime / "launch-url.txt"
        capture.unlink(missing_ok=True)
        output = self.runtime / "process" / f"run-{run}"
        output.mkdir(mode=0o700)
        self.process = None
        self.paths = {name: output / name for name in ("stdout", "stderr")}
        self.streams = {}
        try:
            for name, path in self.paths.items():
                self.streams[name] = path.open("xb")
        except BaseException as error:
            attempts = Attempts(error)
            for name, stream in self.streams.items():
                attempts.call(name + " acquisition close", stream.close)
            self.acquisition_cleanup.extend(attempts.rows)
            attempts.raise_first()
        argv = [
            contract.BINARY,
            "app",
            "--mode",
            "browser",
            "--directory",
            "/proof/data",
        ]
        try:
            self.process = subprocess.Popen(
                argv,
                env=app_environment(),
                stdin=subprocess.DEVNULL,
                stdout=self.streams["stdout"],
                stderr=self.streams["stderr"],
                start_new_session=True,
            )
        except BaseException as error:
            attempts = Attempts(error)
            for name, stream in self.streams.items():
                attempts.call(name + " acquisition close", stream.close)
            self.acquisition_cleanup.extend(attempts.rows)
            attempts.raise_first()
        row = {
            "run": run,
            "pid": self.process.pid,
            "argv": argv,
            "stop_method": "interface_quit",
            "forced_cleanup": False,
            "sigterm_sent": False,
        }
        self.rows.append(row)
        row["cmdline"] = contract.full_record(
            contract.regular(Path(f"/proc/{self.process.pid}/cmdline"), 4096)
        )
        deadline = time.monotonic() + 25
        while not capture.exists():
            contract.require(
                self.process.poll() is None and time.monotonic() < deadline,
                "Installed app failed before fixed opener capture.",
            )
            time.sleep(0.02)
        raw = contract.regular(capture, 1024)
        _, self.inner.port = inner_address(raw.decode("ascii"))
        row.update(opener=contract.full_record(raw), port=self.inner.port)
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

    def reap(self):
        from tools import native_window_smoke as native
        from tools.installed_native_menu import stream_record

        row = self.rows[-1]
        attempts = Attempts()
        attempts.call("app stop", lambda: native.stop_process(self.process, row))
        for name, stream in self.streams.items():
            attempts.call(name + " close", stream.close)
        for name, path in self.paths.items():

            def capture(p=path, n=name):
                with p.open("rb") as stream:
                    row[n] = stream_record(stream)

            attempts.call(name + " retention", capture)
        row["streams_complete"] = (
            self.process.poll() is not None
            and row.get("owned_group_remaining") is False
        )
        row["port_closed"] = (
            attempts.call("listener observation", lambda: closed_port(self.inner.port))
            is True
        )
        row["returncode"] = self.process.poll()
        row["cleanup_observation"] = {
            "errors": list(attempts.errors),
            "attempts": list(attempts.rows),
        }
        attempts.call(
            "app observation retention",
            lambda: write_json(
                self.runtime / "process" / f"run-{row['run']}" / "observation.json", row
            ),
        )
        attempts.raise_first()
        contract.command(row, row["argv"])
        contract.require(
            row["sigterm_sent"] is False and row["port_closed"] is True,
            "Only an observed normal interface quit may qualify.",
        )
        notice = base64.b64decode(self.identity["notice_base64"])
        expected_stdout = contract.browser_stdout(
            contract.full(row["opener"], 1024).decode("ascii"), row["port"]
        )
        contract.require(
            row["port"] == self.inner.port,
            "App listener differs from its actual relay admission.",
        )
        contract.require(
            contract.regular(self.paths["stdout"], contract.MAX_FILE) == expected_stdout
            and contract.regular(self.paths["stderr"], contract.MAX_FILE) == notice,
            "Actual app diagnostics differ; retained streams are not a pass.",
        )
        write_json(
            self.runtime / "state.json",
            {
                **self.identity,
                "phase": "stopped",
                "run": row["run"],
                "exit_code": row["exit_code"],
                "port_closed": True,
            },
        )

    def run(self):
        primary, run, reaped = None, 1, False
        started = False
        cmdline = None
        try:
            cmdline = contract.full_record(
                contract.regular(Path("/proc/self/cmdline"), 4096)
            )
            self.thread.start()
            started = True
            self.launch(run)
            deadline = time.monotonic() + 400
            while time.monotonic() < deadline:
                if self.process.poll() is not None and not reaped:
                    self.reap()
                    reaped = True
                control = self.runtime / "control.json"
                if control.exists():
                    value = read_json(control, 1024)
                    control.unlink()
                    contract.require(
                        type(value) is dict and set(value) == {"action"},
                        "Unknown controller fields refuse.",
                    )
                    if value["action"] == "restart" and reaped and run == 1:
                        run, reaped = 2, False
                        self.launch(run)
                    elif value["action"] == "cleanup" and reaped and run == 2:
                        break
                    else:
                        raise ValueError(
                            "Invalid fixed workflow controller transition."
                        )
                time.sleep(0.02)
            else:
                raise TimeoutError(
                    "Installed UI journey timed out; no automatic retry."
                )
        except BaseException as error:
            primary = error
            self.failure = {"type": type(error).__name__, "message": str(error)[:4096]}
            write_json(
                self.runtime / "state.json",
                {"phase": "failed", "failure": self.failure},
            )
        finally:
            attempts = Attempts(primary)
            attempts.call(
                "app final reap",
                lambda: (
                    self.reap() if self.process is not None and not reaped else None
                ),
            )
            attempts.call(
                "relay shutdown", lambda: self.inner.shutdown() if started else None
            )
            attempts.call("relay close", self.inner.server_close)
            attempts.call(
                "relay join", lambda: self.thread.join(timeout=5) if started else None
            )

            def remove_socket():
                contract.require(
                    not self.thread.is_alive() and self.inner.idle(),
                    "Inner relay still owns work.",
                )
                (self.runtime / "relay.sock").unlink(missing_ok=True)

            attempts.call("relay socket removal", remove_socket)
            resources = {}

            def observe():
                from tools.native_window_smoke import group_alive

                resources.update(
                    inner_thread_closed=not self.thread.is_alive(),
                    inner_requests_closed=self.inner.idle(),
                    inner_socket_absent=not os.path.lexists(
                        self.runtime / "relay.sock"
                    ),
                    app_groups_absent=all(
                        not group_alive(row["pid"]) for row in self.rows
                    ),
                )
                contract.require(
                    all(resources.values()), "Installed controller resources survive."
                )

            attempts.call("controller final observation", observe)
            value = {
                "schema": contract.CONTROLLER,
                "uid": os.geteuid(),
                "gid": os.getegid(),
                "pid": os.getpid(),
                "argv": [
                    "python3",
                    "-B",
                    "/source/" + contract.SOURCE_FILE,
                    "controller",
                ],
                "cmdline": cmdline,
                "rows": self.rows,
                "resources": resources,
                "failure": self.failure,
                "acquisition_cleanup": self.acquisition_cleanup,
                "cleanup_errors": list(attempts.errors),
                "cleanup_attempts": list(attempts.rows),
            }
            attempts.call(
                "controller receipt retention",
                lambda: write_json(self.runtime / "controller.json", value),
            )
            attempts.raise_first()
        return 0


def controller():
    inputs = contract.config(read_json(Path("/candidate/workflow-input.json")))
    contract.require(
        os.geteuid() == inputs["uid"]
        and os.getegid() == inputs["gid"]
        and Path("/.dockerenv").is_file(),
        "Use only the fixed observed user controller.",
    )
    identity = wait(Path("/proof/ready.json"))
    script = Path("/proof/capture-browser")
    script.write_text(
        "#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\n"
        "Path('/proof/launch-url.txt').write_text(sys.argv[1], encoding='ascii')\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    return Controller(Path("/proof"), identity).run()


def package_inputs(inputs, source, output, rows):
    """Capture each actual control and the full payload before deriving identities."""
    from tools import installed_native_menu as menu
    from tools.package_native import debian_package_version, linux_desktop_entries

    installer = Path("/candidate") / inputs["installer_name"]
    receipt_path = Path("/candidate") / inputs["package_receipt_name"]
    expected = read_json(receipt_path, 2 * 1024 * 1024)
    contract.require(
        contract.sha(contract.regular(installer, contract.MAX_FILE))
        == inputs["installer_sha256"]
        and contract.sha(contract.regular(receipt_path, contract.MAX_FILE))
        == inputs["package_receipt_sha256"]
        and expected["passed"] is True
        and expected["frozen"] is True
        and expected["version"] == contract.VERSION
        and expected["source_commit"] == source["commit"]
        and expected["installer_sha256"] == inputs["installer_sha256"],
        "Same-run frozen build/package/source identity differs.",
    )
    indexes = []
    for field, value in (
        ("Package", "sinter"),
        ("Architecture", "amd64"),
        ("Version", debian_package_version(contract.VERSION)),
    ):
        indexes.append(len(rows))
        code, raw = menu.command(["dpkg-deb", "-f", installer, field], rows)
        contract.require(
            code == 0
            and raw == (value + "\n").encode()
            and contract.native.stream_bytes(rows[-1]["stderr"]) == b"",
            "Actual package control differs.",
        )
    index = len(rows)
    code, payload = menu.command(
        ["dpkg-deb", "--fsys-tarfile", installer],
        rows,
        limit=contract.MAX_TOTAL,
        save_streams={
            name: output / ("package." + name) for name in ("stdout", "stderr")
        },
    )
    contract.require(code == 0, "Actual package payload failed.")
    members = menu.package_members(payload)
    binary = members["opt/neuroforge/sinter/Sinter"]
    binary_sha = contract.sha(binary)
    contract.require(
        expected["frozen_cli_test"]["passed"] is True
        and expected["frozen_cli_test"]["binary_sha256"] == binary_sha,
        "Actual payload differs from same-build frozen CLI.",
    )
    entries = {}
    for name, text in linux_desktop_entries(True).items():
        raw = members["usr/share/applications/" + name]
        contract.require(
            raw == text.encode("utf-8"), "Exact source/menu payload differs."
        )
        entries[name] = contract.full_record(raw)
    return (
        {
            "installer_sha256": inputs["installer_sha256"],
            "receipt_sha256": inputs["package_receipt_sha256"],
            "binary_sha256": binary_sha,
            "binary_bytes": len(binary),
            "payload_tar_sha256": contract.sha(payload),
            "payload_tar_bytes": len(payload),
            "package_version": debian_package_version(contract.VERSION),
            "entries": entries,
        },
        indexes,
        index,
    )


def retain_commands(output, rows):
    """Small complete commands retain decoded originals; payload already has sidecars."""
    for index, row in enumerate(rows):
        for name in ("stdout", "stderr"):
            if row[name].get("truncated") is True:
                contract.require(
                    row["argv"][:2] == ["dpkg-deb", "--fsys-tarfile"],
                    "Unexpected command truncation refuses evidence.",
                )
                continue
            raw = contract.native.stream_bytes(row[name])
            destination = output / f"command-{index:02d}.{name}"
            if destination.exists():
                contract.require(
                    contract.regular(destination, contract.MAX_FILE) == raw,
                    "Retained command changed; do not overwrite it.",
                )
            else:
                destination.write_bytes(raw)


def inner():
    from tools import installed_native_menu as menu
    from tools import native_window_smoke as native
    from tools import rc4_installed_recovery as recovery
    from tools.installed_menu_browser import browser_notice

    inputs = contract.config(read_json(Path("/candidate/workflow-input.json")))
    contract.require(
        os.geteuid() == 0
        and os.getpid() == 1
        and Path("/.dockerenv").is_file()
        and {path.name for path in Path("/sys/class/net").iterdir()} == {"lo"}
        and not os.environ.get("DISPLAY"),
        "Use only isolated disposable PID1/root.",
    )
    source = recovery.source_binding(
        contract.regular(Path("/repository/committed-source.tar"), contract.MAX_TOTAL),
        inputs["source_commit"],
        recovery.source_records(ROOT),
        "candidate",
    )
    output = Path("/out/evidence")
    output.mkdir(mode=0o755)
    value = {
        "schema": contract.INNER,
        "source": source,
        "commands": [],
        "failure": None,
        "cleanup_errors": [],
        "passed": False,
        "container": {
            "effective_uid": os.geteuid(),
            "pid": os.getpid(),
            "interfaces": sorted(p.name for p in Path("/sys/class/net").iterdir()),
            "inherited_display": bool(os.environ.get("DISPLAY")),
        },
    }
    rows, attempted, primary = value["commands"], False, None
    try:
        contract.require(
            menu.package_state(rows) == "absent"
            and not any(os.path.lexists(path) for path in contract.INSTALLED_PATHS),
            "Existing package paths refuse a clean workflow install.",
        )
        package, indexes, payload_index = package_inputs(inputs, source, output, rows)
        value.update(
            package=package,
            package_control_indexes=indexes,
            package_payload_command_index=payload_index,
        )
        attempted = True
        code, _raw = menu.command(
            ["dpkg", "-i", "/candidate/" + inputs["installer_name"]], rows, timeout=60
        )
        contract.require(code == 0, "Actual package installation failed.")
        value["installed_entries"], value["installed_binary"] = {}, {}
        menu.installed_identity(
            package,
            observations=value["installed_entries"],
            binary_observation=value["installed_binary"],
        )
        value["installed_package"] = menu.installed_package_version(
            package["package_version"], rows
        )
        home = Path("/out/diagnostic-home")
        # The containing proof root is private. Read permission lets the
        # independent host inventory actually inspect this root-owned empty home.
        home.mkdir(mode=0o755)
        environment = {"PATH": os.defpath, "HOME": str(home), "LC_ALL": "C.UTF-8"}
        diag_row, diag_obs = {}, {}
        try:
            value["diagnostic"] = native.diagnose(
                Path(contract.BINARY), environment, diag_row, observation=diag_obs
            )
        finally:
            value.update(diagnostic_process=diag_row, diagnostic_observation=diag_obs)
            for name in ("stdout", "stderr"):
                if name in diag_obs:
                    (output / ("diagnose." + name)).write_bytes(
                        contract.native.stream_bytes(diag_obs[name]["record"])
                    )
        selftest = output / "selftest.json"
        code, _raw = menu.command(
            [contract.BINARY, "--self-test", selftest],
            rows,
            env=environment,
            timeout=60,
        )
        value["selftest_command"] = rows[-1]
        value["selftest"] = read_json(selftest)
        expected = read_json(Path("/candidate") / inputs["package_receipt_name"])
        contract.require(
            code == 0 and contract.equal(value["selftest"], expected["installed_test"]),
            "Actual installed frozen self-test differs.",
        )
        operations_path = output / "operations.json"
        code, raw = menu.command(
            [contract.BINARY, "operations", "--format", "json"],
            rows,
            env=environment,
            save_streams={
                name: output / ("operations." + name) for name in ("stdout", "stderr")
            },
        )
        contract.require(code == 0, "Actual installed operation catalogue failed.")
        operations_path.write_bytes(raw)
        import platform as runtime_platform

        ready = {
            "phase": "ready",
            "package": "sinter",
            "architecture": "amd64",
            "version": contract.VERSION,
            "package_version": package["package_version"],
            "installed_package_version": package["package_version"],
            "binary_sha256": package["binary_sha256"],
            "web": {
                name: info["sha256"]
                for name, info in source["files"].items()
                if name.startswith("src/sinter/web/")
            },
            "os_release": {"ID": "ubuntu", "VERSION_ID": "22.04"},
            "libc": list(runtime_platform.libc_ver()),
            "frozen_test": value["selftest"],
            "operations_catalog": read_json(operations_path),
            "notice_base64": base64.b64encode(
                browser_notice((ROOT / "src/sinter/desktop.py").read_bytes())
            ).decode("ascii"),
        }
        actual_release = dict(
            line.split("=", 1)
            for line in Path("/etc/os-release").read_text().splitlines()
            if "=" in line
        )
        contract.require(
            actual_release["ID"].strip('"') == "ubuntu"
            and actual_release["VERSION_ID"].strip('"') == "22.04"
            and ready["libc"] == ["glibc", "2.35"],
            "Actual runtime baseline differs.",
        )
        value["runtime"] = {
            "os_release": Path("/etc/os-release").read_text(),
            "libc": ready["libc"],
        }
        write_json(Path("/proof/ready.json"), ready)
        # Only the outer owner signals removal after the exact exec client and host
        # collector have both reaped. A controller-written success is insufficient.
        finished = wait(Path("/proof/remove.json"), timeout=500)
        contract.require(
            finished == {"action": "remove", "exec_reaped": True, "host_reaped": True},
            "Exact post-reap removal acknowledgement required.",
        )
        value["installed_entries_after"], value["installed_binary_after"] = {}, {}
        menu.installed_identity(
            package,
            observations=value["installed_entries_after"],
            binary_observation=value["installed_binary_after"],
        )
        value["passed"] = True
    except BaseException as error:
        primary = error
        value["failure"] = {"type": type(error).__name__, "message": str(error)[:4096]}
        (output / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        attempts = Attempts(primary)
        if attempted:

            def remove():
                try:
                    return menu.command(["dpkg", "-r", "sinter"], rows, timeout=60)[0]
                finally:
                    if rows and rows[-1].get("argv") == ["dpkg", "-r", "sinter"]:
                        value["removal_command"] = rows[-1]

            code = attempts.call("package removal", remove)
            state = attempts.call("package state", lambda: menu.removal_state(rows))
            if state is not None:
                value["removal"] = state
            absence = attempts.call(
                "independent path absence",
                lambda: menu.observed_absence(contract.INSTALLED_PATHS, rows),
            )
            if absence is not None:
                value["absence"] = absence
            if code is not None and state is not None:
                attempts.call(
                    "removal admission",
                    lambda: contract.recovery.validate_package_removal(
                        code, value["removal_command"], state, rows
                    ),
                )
        value["qa_files_after"] = attempts.call(
            "source conservation", lambda: recovery.source_records(ROOT)
        )
        attempts.call(
            "all command stream retention", lambda: retain_commands(output, rows)
        )
        value["cleanup_errors"] = attempts.errors
        if attempts.first is not None:
            value["passed"] = False
        attempts.call(
            "installed receipt retention",
            lambda: write_json(output / "inner.json", value),
        )
        attempts.raise_first()
    return 0


def chrome_argv(home, executable):
    return [
        str(executable),
        "--headless=new",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--metrics-recording-only",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=0",
        "--user-data-dir=" + str(home / "profile"),
        "about:blank",
    ]


def captured_session_class():
    """Extend the accepted factory with a separately owned, fully captured Chrome.

    The supplied factory still delegates all context/browser/driver cleanup to the
    accepted OwnedBrowserSession. Its fixed chromium.launch adapter connects that
    API to the explicit private Chrome process rather than an uncaptured child.
    """
    from tools.rc4_installed_recovery import OwnedBrowserSession

    class CapturedSession(OwnedBrowserSession):
        def __init__(self, root, executable):
            super().__init__("core-workflow")
            self.root, self.executable = root, executable
            self.chrome_process, self.chrome, self.cdp = None, None, None
            self.chrome_streams, self.browser_pids, self.driver_observation = (
                {},
                set(),
                {},
            )
            self.chrome_row = {}

        def __enter__(self):
            from tools import rc4_native_handoff as handoff

            previous = handoff.children()
            raw_driver = super().__enter__()
            try:
                driver_pids = handoff.children() - previous
                self.driver_observation = {"candidates": sorted(driver_pids)}
                contract.require(
                    len(driver_pids) == 1,
                    "One actual continuing managed Node driver required.",
                )
                pid = next(iter(driver_pids))
                import playwright

                path = Path(os.readlink(f"/proc/{pid}/exe"))
                expected = Path(playwright.__file__).resolve().parent / "driver/node"
                contract.require(
                    path == expected, "Actual managed Node executable differs."
                )
                self.driver_observation = {
                    "pid": pid,
                    "path": str(path),
                    "sha256": contract.sha(contract.regular(path, 512 * 1024 * 1024)),
                    "cmdline": contract.full_record(
                        contract.regular(Path(f"/proc/{pid}/cmdline"), 4096)
                    ),
                    "gone": False,
                }
                session = self

                class Chromium:
                    def launch(self, *, headless, executable_path):
                        contract.require(
                            headless is True
                            and Path(executable_path) == session.executable,
                            "Only explicitly pinned headless Chromium may be launched.",
                        )
                        return session.start_chrome(raw_driver)

                class Driver:
                    chromium = Chromium()

                    def __getattr__(self, name):
                        return getattr(raw_driver, name)

                self.driver = Driver()
                return self.driver
            except BaseException:
                kind, error, trace = sys.exc_info()
                # Python does not invoke __exit__ when __enter__ fails.
                closed = self.observe_close(
                    "driver", lambda: self.manager.__exit__(kind, error, trace)
                )
                self.driver_closed = closed is None
                raise

        def observe_pids(self):
            values = self.cdp.send("SystemInfo.getProcessInfo")["processInfo"]
            self.browser_pids.update(int(row["id"]) for row in values)

        def start_chrome(self, driver):
            home = self.root / "client/browser-home"
            home.mkdir(mode=0o700)
            for name in ("stdout", "stderr"):
                self.chrome_streams[name] = (self.root / "out/chrome" / name).open("xb")
            environment = {
                "PATH": os.defpath,
                "HOME": str(home),
                "TMPDIR": str(self.root / "t"),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            }
            self.chrome_row = {
                "argv": chrome_argv(home, self.executable),
                "sigterm_sent": False,
                "forced_cleanup": False,
                "debug_port_closed": False,
            }
            self.chrome_process = subprocess.Popen(
                self.chrome_row["argv"],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=self.chrome_streams["stdout"],
                stderr=self.chrome_streams["stderr"],
                start_new_session=True,
            )
            self.chrome_row["pid"] = self.chrome_process.pid
            self.chrome_row["cmdline"] = contract.full_record(
                contract.regular(Path(f"/proc/{self.chrome_process.pid}/cmdline"), 8192)
            )
            active = home / "profile/DevToolsActivePort"
            deadline = time.monotonic() + 15
            while not active.exists():
                contract.require(
                    self.chrome_process.poll() is None and time.monotonic() < deadline,
                    "Private Chromium debugger failed to start.",
                )
                time.sleep(0.025)
            lines = contract.regular(active, 1024).decode("ascii").splitlines()
            contract.require(
                len(lines) == 2
                and re.fullmatch("[0-9]{1,5}", lines[0])
                and re.fullmatch("/devtools/browser/[0-9a-f-]+", lines[1]),
                "Private debugger endpoint differs.",
            )
            self.chrome_row["debug_port"] = int(lines[0])
            contract.require(
                0 < self.chrome_row["debug_port"] <= 65535,
                "Debugger port outside range.",
            )
            self.chrome = driver.chromium.connect_over_cdp(
                f"http://127.0.0.1:{lines[0]}"
            )
            self.cdp = self.chrome.new_browser_cdp_session()
            self.observe_pids()
            session, raw = self, self.chrome

            class Browser:
                def __getattr__(self, name):
                    return getattr(raw, name)

                def new_context(self, **kwargs):
                    context = raw.new_context(**kwargs)
                    context.on(
                        "page",
                        lambda page: page.on(
                            "domcontentloaded", lambda *_args: session.observe_pids()
                        ),
                    )
                    return context

                def close(self):
                    if session.chrome_process.poll() is None:
                        session.observe_pids()
                        session.cdp.send("Browser.close")
                        session.chrome_process.wait(timeout=5)
                    raw.close()

            return Browser()

    return CapturedSession


def fixture(source):
    from tools.installed_workflow_contract import PRACTICE_FILES
    from tools.installed_workflow_qualification import source_operations

    result = {
        kind: contract.read_json(source[f"src/sinter/web/offline-garden-{kind}.json"])
        for kind in ("casebook", "campaign")
    }
    result.update(
        source=source,
        practice_hashes={name: contract.sha(source[name]) for name in PRACTICE_FILES},
        web={
            name: contract.sha(raw)
            for name, raw in source.items()
            if name.startswith("src/sinter/web/")
        },
    )
    source_operations(source)
    return result


def receipt(inputs, source, ready, source_zip, receipt_path):
    from tools.installed_workflow_browser import object_digest
    from tools.installed_workflow_contract import RESOURCE_FLAGS, workflow_schema

    expected = read_json(receipt_path)
    contract.require(
        expected["installed_test"] == ready["frozen_test"],
        "Actual installed identity differs.",
    )
    return {
        "schema": workflow_schema(source),
        "passed": False,
        "version": contract.VERSION,
        "source_commit": inputs["source_commit"],
        "system": "Linux",
        "target_arch": "x64",
        "machine": ready["frozen_test"]["machine"],
        "pointer_bits": ready["frozen_test"]["pointer_bits"],
        "frozen": ready["frozen_test"]["frozen"],
        "desktop": True,
        "installed_executable": contract.BINARY,
        "installer_sha256": inputs["installer_sha256"],
        "source_archive_sha256": contract.sha(
            contract.regular(source_zip, contract.MAX_FILE)
        ),
        "native_receipt_sha256": contract.sha(
            contract.regular(receipt_path, contract.MAX_FILE)
        ),
        "installed_binary_sha256": ready["binary_sha256"],
        "web_assets_sha256": ready["web"],
        "practice_fixture_sha256": fixture(source)["practice_hashes"],
        "image_id": contract.IMAGE,
        "container": "ubuntu:22.04",
        "os_release": ready["os_release"],
        "libc": ready["libc"],
        "network": "disabled container; loopback only",
        "network_mode": "none",
        "host_installation": False,
        "external_requests": 0,
        "page_errors": 0,
        "model_calls": 0,
        "resources": dict.fromkeys(RESOURCE_FLAGS, False),
        "checks": [],
        "input_hashes": {
            "garden_casebook": object_digest(fixture(source)["casebook"]),
            "garden_campaign": object_digest(fixture(source)["campaign"]),
            "static_assets": object_digest(ready["web"]),
        },
        "result_hashes": {},
        "artifacts": [],
    }


def host(root, chromium):
    from tools import installed_native_menu as menu
    from tools import installed_workflow_browser as workflow
    from tools import native_window_smoke as native
    from tools import rc4_installed_recovery as recovery
    from tools import rc4_native_handoff as handoff
    from tools.installed_workflow_contract import CHECKS

    inputs = contract.config(read_json(root / "candidate/workflow-input.json"))
    contract.require(
        ROOT == root / "source"
        and Path(chromium) == Path(inputs["browser"]["path"])
        and recovery.source_records(ROOT) == inputs["qa_files"]
        and os.environ.get("TMPDIR") == str(root / "t"),
        "Fixed staged collector environment/source differs.",
    )
    source = {
        name: contract.regular(ROOT / name, contract.MAX_FILE)
        for name in inputs["qa_files"]
    }
    ready = wait(root / "runtime/ready.json")
    output = root / "out/workflow"
    output.mkdir(mode=0o700)
    (output / "installed-workflow").mkdir(mode=0o700)
    (root / "out/chrome").mkdir(mode=0o700)
    source_zip = root / "repository" / f"sinter-{contract.VERSION}-source.zip"
    report = receipt(
        inputs,
        source,
        ready,
        source_zip,
        root / "candidate" / inputs["package_receipt_name"],
    )
    from tools.installed_workflow_qualification import validate_operations_catalog

    validate_operations_catalog(ready["operations_catalog"], source, contract.VERSION)
    write_json(
        output / "installed-workflow/operations-catalog.json",
        ready["operations_catalog"],
    )
    report["checks"] = list(CHECKS[:2])
    session = captured_session_class()(root, Path(chromium))
    relay, thread, primary = workflow.Relay(root / "runtime"), None, None
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    started = False
    observation = {
        "schema": contract.HOST,
        "failure": None,
        "cleanup_errors": [],
        "cleanup_attempts": [],
        "session": {},
        "relay": {},
        "chrome": {},
        "driver": {},
        "browser_pids": [],
        "owned_pids_gone": False,
    }
    try:
        thread.start()
        started = True
        workflow.wait_state(root / "runtime", "running", 1)
        args = SimpleNamespace(
            output=output, chromium=chromium, version=contract.VERSION
        )
        values, errors, external = workflow.browser_workflow(
            args,
            root / "runtime",
            relay,
            fixture(source),
            report["checks"],
            browser_session=session,
        )
        report.update(
            result_hashes=values,
            page_errors=errors,
            external_requests=external,
            artifacts=workflow.artifact_inventory(output, source),
        )
    except BaseException as error:
        primary = error
        observation["failure"] = {
            "type": type(error).__name__,
            "message": str(error)[:4096],
        }
        (root / "out/host-failure.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
    finally:
        attempts = Attempts(primary)

        def close_browser():
            if (
                session.chrome_process is not None
                and session.chrome_process.poll() is None
            ):
                session.cdp.send("Browser.close")
                session.chrome_process.wait(timeout=5)

        attempts.call("browser close request", close_browser)
        attempts.call(
            "chrome reap",
            lambda: (
                native.stop_process(session.chrome_process, session.chrome_row)
                if session.chrome_process is not None
                else None
            ),
        )
        for name in ("stdout", "stderr"):

            def capture(n=name):
                path = root / "out/chrome" / n
                session.chrome_streams[n].flush()
                with path.open("rb") as stream:
                    session.chrome_row[n] = menu.stream_record(stream)

            attempts.call("chrome " + name, capture)
        for name in ("stdout", "stderr"):
            attempts.call(
                "chrome " + name + " close",
                lambda n=name: session.chrome_streams[n].close(),
            )
        attempts.call("relay shutdown", lambda: relay.shutdown() if started else None)
        attempts.call("relay close", relay.server_close)
        attempts.call("relay join", lambda: thread.join(timeout=5) if started else None)

        def observe():
            # Preserve every available original observation even if a later
            # browser identity/read fails during partial acquisition.
            observation.update(
                session=session.observations(),
                chrome=session.chrome_row,
                driver=session.driver_observation,
                browser_pids=sorted(session.browser_pids),
                relay={
                    "stopped": not thread.is_alive(),
                    "idle": relay.idle(),
                    "port_closed": closed_port(relay.server_address[1]),
                    "model_routes": relay.model_requests,
                    "errors": relay.errors,
                },
            )
            deadline = time.monotonic() + 5
            owned = set(session.browser_pids)
            if (
                type(session.driver_observation.get("pid")) is int
                and session.driver_observation["pid"] > 1
            ):
                owned.add(session.driver_observation["pid"])
            while (
                any(handoff.alive(pid) for pid in owned) and time.monotonic() < deadline
            ):
                time.sleep(0.02)
            observation["session"] = session.observations()
            session.chrome_row["streams_complete"] = (
                session.chrome_process is not None
                and session.chrome_process.poll() is not None
                and session.chrome_row.get("owned_group_remaining") is False
            )
            session.chrome_row["debug_port_closed"] = closed_port(
                session.chrome_row["debug_port"]
            )
            session.driver_observation["gone"] = not handoff.alive(
                session.driver_observation["pid"]
            )
            observation.update(
                chrome=session.chrome_row,
                driver=session.driver_observation,
                browser_pids=sorted(session.browser_pids),
                owned_pids_gone=all(
                    not handoff.alive(pid) for pid in session.browser_pids
                ),
                relay={
                    "stopped": not thread.is_alive(),
                    "idle": relay.idle(),
                    "port_closed": closed_port(relay.server_address[1]),
                    "model_routes": relay.model_requests,
                    "errors": relay.errors,
                },
            )
            contract.require(
                all(
                    observation["relay"][key]
                    for key in ("stopped", "idle", "port_closed")
                ),
                "Host relay survives.",
            )

        attempts.call("host resource observation", observe)
        attempts.call(
            "installed cleanup request",
            lambda: write_json(root / "runtime/control.json", {"action": "cleanup"}),
        )
        observation["cleanup_errors"], observation["cleanup_attempts"] = (
            list(attempts.errors),
            list(attempts.rows),
        )
        report["resources"].update(
            browser_closed=observation.get("session", {}).get("browser_closed", False),
            relay_closed=all(
                observation.get("relay", {}).get(k) is True
                for k in ("stopped", "idle", "port_closed")
            ),
            installed_process_stopped=primary is None,
        )
        attempts.call(
            "host observation retention",
            lambda: write_json(root / "out/host.json", observation),
        )
        attempts.call(
            "unfinished workflow retention",
            lambda: write_json(
                output / "installed-workflow-browser.pending.json", report
            ),
        )
        attempts.raise_first()
    return 0


def validate_inventory(root, inputs):
    """Close fixed evidence roles and bound only fresh fictional/private runtime data."""
    from tools.installed_workflow_contract import workflow_artifact_paths

    source = {
        name: contract.regular(root / "source" / name, contract.MAX_FILE)
        for name in inputs["qa_files"]
    }
    fixed = {
        "workflow-owner.json",
        "candidate/workflow-input.json",
        "candidate/" + inputs["installer_name"],
        "candidate/" + inputs["package_receipt_name"],
        "repository/committed-source.tar",
        "repository/sinter-" + contract.VERSION + "-source.zip",
        "out/evidence/inner.json",
        "out/evidence/selftest.json",
        "out/evidence/operations.json",
        "out/evidence/operations.stdout",
        "out/evidence/operations.stderr",
        "out/evidence/diagnose.stdout",
        "out/evidence/diagnose.stderr",
        "out/evidence/package.stdout",
        "out/evidence/package.stderr",
        "out/host.json",
        "out/chrome/stdout",
        "out/chrome/stderr",
        "out/workflow/installed-workflow-browser.json",
        "out/workflow/installed-workflow-browser.pending.json",
        "runtime/ready.json",
        "runtime/state.json",
        "runtime/controller.json",
        "runtime/remove.json",
        "runtime/capture-browser",
        "runtime/launch-url.txt",
        "raw/source-tar.stdout",
        "raw/source-tar.stderr",
        "raw/source-zip.stdout",
        "raw/source-zip.stderr",
        "raw/source-commands.json",
    }
    fixed.update("source/" + name for name in inputs["qa_files"])
    fixed.update(
        "out/workflow/" + name for name in workflow_artifact_paths(source).values()
    )
    inner_value = read_json(root / "out/evidence/inner.json")
    fixed.update(
        f"out/evidence/command-{index:02d}.{name}"
        for index, row in enumerate(inner_value["commands"])
        for name in ("stdout", "stderr")
        if row[name].get("truncated") is not True
    )
    fixed.update(
        "raw/" + role + "." + name
        for role in (*contract.native.ROLES, "client-version", "controller", "host")
        for name in ("stdout", "stderr")
    )
    fixed.update(
        f"runtime/process/run-{run}/{name}"
        for run in (1, 2)
        for name in ("stdout", "stderr", "observation.json")
    )
    permitted_empty = {"t", "client/.docker", "out/diagnostic-home", "runtime/home"}
    files, directories, total = set(), set(), 0
    variable_roots = ("client/browser-home/", "runtime/data/")
    pending = [root]
    while pending:
        # iterdir raises on an unreadable directory; rglob may silently omit it.
        for path in pending.pop().iterdir():
            name = path.relative_to(root).as_posix()
            info = path.lstat()
            contract.require(
                len(name.split("/")) <= 16
                and len(files) + len(directories) < 8192
                and not path.is_symlink()
                and (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)),
                "Unknown link/special/deep evidence entry refuses before reads.",
            )
            if stat.S_ISDIR(info.st_mode):
                directories.add(name)
                pending.append(path)
            else:
                contract.require(
                    name in fixed or name.startswith(variable_roots),
                    "Unknown fixed evidence file role.",
                )
                total += info.st_size
                contract.require(
                    info.st_size <= contract.MAX_FILE and total <= contract.MAX_TOTAL,
                    "Evidence tree exceeds unchanged public bounds.",
                )
                files.add(name)
    contract.require(fixed.issubset(files), "Required raw evidence role is missing.")
    parents = {
        parent.as_posix()
        for name in files
        for parent in Path(name).parents
        if str(parent) != "."
    }
    contract.require(
        all(
            name in parents
            or name in permitted_empty
            or name.startswith("client/browser-home/")
            for name in directories
        ),
        "Unlisted empty evidence directory refuses.",
    )
    data_files = {
        name.removeprefix("runtime/data/")
        for name in files
        if name.startswith("runtime/data/")
    }
    contract.require(
        {"workspace.sqlite3", "campaigns.sqlite3"}.issubset(data_files)
        and all(
            name in {"workspace.sqlite3", "campaigns.sqlite3", "preferences.json"}
            or name.startswith("exports/")
            and name.endswith(".docx")
            for name in data_files
        ),
        "Unexpected fictional workspace storage entry refuses.",
    )
    contract.require(
        not any((root / "runtime/home").iterdir()),
        "Fictional account-free app home is not empty.",
    )
    return {"files": len(files), "directories": len(directories), "bytes": total}


def finalize_workflow(root, inputs, outer):
    """Complete the retained draft only after independent package/container closure."""
    from tools import rc4_installed_recovery as recovery
    from tools.installed_workflow_contract import CHECKS, workflow_checks

    inner_value = read_json(root / "out/evidence/inner.json")
    contract.require(
        inner_value["passed"] is True and inner_value["failure"] is None,
        "Actual install owner did not finish.",
    )
    controller_value = read_json(root / "runtime/controller.json")
    contract.require(
        controller_value["failure"] is None
        and len(controller_value["rows"]) == 2
        and all(
            row["exit_code"] == 0 and not row.get("sigterm_sent")
            for row in controller_value["rows"]
        ),
        "Installed UI lifetimes did not quit normally.",
    )
    pins = outer["pins"]
    contract.native.validate_lifecycle(
        outer["commands"], pins, contract.outer_argv, contract.MOUNTS
    )
    value = read_json(root / "out/workflow/installed-workflow-browser.pending.json")
    source = {
        name: contract.regular(root / "source" / name, contract.MAX_FILE)
        for name in inputs["qa_files"]
    }
    value["resources"].update(
        package_removed=inner_value["removal"]["passed"], container_removed=True
    )
    contract.require(
        all(value["resources"].values()),
        "Actual workflow resources were not all observed.",
    )
    value["checks"].append(CHECKS[-1])
    contract.require(
        tuple(value["checks"]) == workflow_checks(source),
        "Exact 22 installed checks required.",
    )
    value["passed"] = True
    write_json(root / "out/workflow/installed-workflow-browser.json", value)
    contract.require(
        recovery.source_records(ROOT) == inputs["qa_files"],
        "Source changed before final UI admission.",
    )


def run(args):
    from tools import installed_native_container as owner
    from tools import installed_native_menu as menu
    from tools import rc4_installed_recovery as recovery

    root, env, qa, binding, inputs = prepare(args)
    pins = owner.pins_for(
        root,
        args.owner_sha256,
        args.source_commit,
        args.installer.name,
        args.package_receipt.name,
    )
    pins["workflow_directory"] = str(root / "runtime")
    commands, client_rows, cleanup = [], [], []
    value = {
        "schema": contract.SCHEMA,
        "owner_sha256": args.owner_sha256,
        "source": binding,
        "pins": pins,
        "commands": commands,
        "client_commands": client_rows,
        "host_python": sys.executable,
        "failure": None,
        "cleanup_errors": [],
        "cleanup": cleanup,
        "parallel_failures": [],
        "cleanup_attempts": [],
        "browser": {
            **inputs["browser"],
            "sha256_after": None,
            "temporary_directory": str(root / "t"),
            "temporary_empty_before": not any((root / "t").iterdir()),
            "temporary_empty_after": None,
        },
        "passed": False,
    }
    identifier, exited, primary = None, False, None
    start_thread, exec_thread = None, None
    start_errors, exec_errors, exec_rows = [], [], []
    failure_lock = threading.Lock()
    actual_failures = []

    def failed(role, error):
        with failure_lock:
            actual_failures.append(error)
            value["parallel_failures"].append(
                {
                    "role": role,
                    "type": type(error).__name__,
                    "message": str(error)[:4096],
                }
            )

    try:
        value["docker_client"] = owner.client_identity(root, env, client_rows)
        code, raw = owner.docker_row(
            "image",
            ["docker", "image", "inspect", contract.IMAGE],
            root,
            env,
            commands,
            client_rows,
        )
        contract.require(
            code == 0, "Exact retained local image unavailable; never download."
        )
        contract.native.validate_image(raw, pins)
        name = "sinter-native-entry-" + secrets.token_hex(6)
        argv = contract.outer_argv(pins, name)
        code, raw = owner.docker_row("create", argv, root, env, commands, client_rows)
        identifier = contract.recovery.admitted_create(commands[-1], raw)
        code, raw = owner.docker_row(
            "created",
            ["docker", "inspect", identifier],
            root,
            env,
            commands,
            client_rows,
        )
        contract.require(code == 0, "Created container inspection failed.")
        contract.native.validate_container_observation(
            contract.read_json_list(raw)[0],
            pins,
            contract.outer_argv,
            name,
            identifier,
            "created",
            contract.MOUNTS,
        )

        def start():
            try:
                code, _raw = owner.docker_row(
                    "start",
                    ["docker", "start", "-a", identifier],
                    root,
                    env,
                    commands,
                    client_rows,
                    timeout=600,
                )
                contract.require(code == 0, "Actual installed owner failed.")
            except BaseException as error:
                start_errors.append(error)
                failed("installed owner", error)

        start_thread = threading.Thread(target=start, daemon=True)
        start_thread.start()
        wait(root / "runtime/ready.json")

        def execute_controller():
            try:
                code, _raw = menu.command(
                    contract.exec_argv(identifier, inputs),
                    exec_rows,
                    env=env,
                    timeout=500,
                    save_streams={
                        name: root / "raw" / ("controller." + name)
                        for name in ("stdout", "stderr")
                    },
                )
                contract.require(code == 0, "Actual user controller failed.")
            except BaseException as error:
                exec_errors.append(error)
                failed("controller", error)

        exec_thread = threading.Thread(target=execute_controller, daemon=True)
        exec_thread.start()
        host_rows = []
        try:
            code, _raw = menu.command(
                contract.host_argv(root, inputs, sys.executable),
                host_rows,
                env=env,
                timeout=450,
                save_streams={
                    name: root / "raw" / ("host." + name)
                    for name in ("stdout", "stderr")
                },
            )
            contract.require(code == 0, "Actual browser collector failed.")
        finally:
            if host_rows:
                value["host_command"] = host_rows[-1]
        exec_thread.join(timeout=30)
        contract.require(
            not exec_thread.is_alive() and not exec_errors and exec_rows,
            "Exact controller exec did not finish normally.",
        )
        value["exec_command"] = exec_rows[-1]
        write_json(
            root / "runtime/remove.json",
            {"action": "remove", "exec_reaped": True, "host_reaped": True},
        )
        start_thread.join(timeout=90)
        contract.require(
            not start_thread.is_alive() and not start_errors,
            "Installed owner did not finish normally.",
        )
        code, raw = owner.docker_row(
            "exited",
            ["docker", "inspect", identifier],
            root,
            env,
            commands,
            client_rows,
        )
        state = contract.read_json_list(raw)[0]["State"]
        exited = code == 0 and state["Running"] is False and state["Status"] == "exited"
        contract.require(exited, "Actual container exit unobserved.")
    except BaseException as error:
        failed("outer body", error)
        primary = actual_failures[0]
        value["failure"] = {
            "type": type(primary).__name__,
            "message": str(primary)[:4096],
        }
    finally:
        attempts = Attempts(primary)
        if identifier is not None:
            if not exited:
                for role, argv in (
                    (
                        "cleanup-term",
                        ["docker", "kill", "--signal", "SIGTERM", identifier],
                    ),
                    ("cleanup-wait", ["docker", "wait", identifier]),
                ):
                    attempts.call(
                        role,
                        lambda r=role, a=argv: owner.capture(
                            r, a, root, env, cleanup, timeout=8
                        ),
                    )

            def remove():
                code, _raw = owner.docker_row(
                    "remove",
                    ["docker", "rm", *([] if exited else ["-f"]), identifier],
                    root,
                    env,
                    commands,
                    client_rows,
                )
                contract.require(code == 0, "Container removal failed.")

            attempts.call("container removal", remove)

            def absence():
                code, _raw = owner.docker_row(
                    "removed",
                    ["docker", "inspect", identifier],
                    root,
                    env,
                    commands,
                    client_rows,
                )
                contract.require(code == 1, "Independent container absence unobserved.")
                contract.native.validate_removal(commands[-2], commands[-1], identifier)

            attempts.call("independent container absence", absence)
        for label, thread in (
            ("attach thread", start_thread),
            ("controller thread", exec_thread),
        ):
            if thread is not None:

                def join(t=thread):
                    t.join(timeout=20)
                    contract.require(not t.is_alive(), "Owned client thread survives.")

                attempts.call(label, join)
        if exec_rows:
            value["exec_command"] = exec_rows[-1]
        if "docker_client" in value:
            attempts.call(
                "Docker identity",
                lambda: value["docker_client"].update(
                    sha256_after=contract.sha(
                        contract.regular(
                            Path(value["docker_client"]["path"]), contract.MAX_FILE
                        )
                    )
                ),
            )
        attempts.call(
            "browser identity",
            lambda: value["browser"].update(
                sha256_after=recovery.browser_identity(inputs["browser"]["path"])[
                    "sha256"
                ]
            ),
        )
        host_command = value.get("host_command", {})
        host_exit = host_command.get("exit_code")
        # A completed failed collector permits cleanup only after the original
        # body failure is retained. It never qualifies that failed workflow.
        expected_host_exit = (
            1
            if primary is not None and type(host_exit) is int and host_exit == 1
            else 0
        )
        attempts.call(
            "post-reap browser cache",
            lambda: value["browser"].update(
                cleanup=recovery.clean_browser_temp(
                    root,
                    host_command,
                    value["browser"],
                    expected_exit=expected_host_exit,
                )
            ),
        )
        attempts.call(
            "browser temp observation",
            lambda: value["browser"].update(
                temporary_empty_after=not any((root / "t").iterdir())
            ),
        )
        value["qa_files_after"] = attempts.call(
            "source conservation", lambda: recovery.source_records(ROOT)
        )
        value["cleanup_errors"] = list(attempts.errors)
        value["cleanup_attempts"] = list(attempts.rows)
        if attempts.first is not None:
            value["failure"] = {
                "type": type(attempts.first).__name__,
                "message": str(attempts.first)[:4096],
            }
        attempts.call(
            "outer receipt retention",
            lambda: write_json(root / "workflow-owner.json", value),
        )
        attempts.raise_first()
    proof_args = SimpleNamespace(
        proof_root=root,
        source_commit=args.source_commit,
        owner_sha256=args.owner_sha256,
        installer_sha256=inputs["installer_sha256"],
        package_receipt_sha256=inputs["package_receipt_sha256"],
    )
    try:
        finalize_workflow(root, inputs, value)
        value["verification"] = contract.verify_original(proof_args, pending=True)
        value["passed"] = True
    except BaseException as error:
        value["failure"] = {"type": type(error).__name__, "message": str(error)[:4096]}
        publish_receipt("qualification", root / "workflow-owner.json", value, error)
        raise
    publish_receipt("qualification", root / "workflow-owner.json", value)
    return 0


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("inner", "controller"):
        sub.add_parser(name, help=argparse.SUPPRESS)
    host_parser = sub.add_parser("host", help=argparse.SUPPRESS)
    host_parser.add_argument("--proof-root", type=Path, required=True)
    host_parser.add_argument("--chromium", required=True)
    run_parser = sub.add_parser("run")
    for name in ("repository", "installer", "package-receipt", "output", "chromium"):
        run_parser.add_argument("--" + name, type=Path, required=True)
    for name in ("source-commit", "owner-sha256"):
        run_parser.add_argument("--" + name, required=True)
    verify_parser = sub.add_parser(
        "verify", help="Original-tree semantic review; no install/browser."
    )
    verify_parser.add_argument("--proof-root", type=Path, required=True)
    for name in (
        "source-commit",
        "owner-sha256",
        "installer-sha256",
        "package-receipt-sha256",
    ):
        verify_parser.add_argument("--" + name, required=True)
    return parser, parser.parse_args(argv)


def main(argv=None):
    import signal

    parser, args = arguments(argv)
    if sys.flags.optimize:
        parser.exit(1, "Run qualification without Python optimisation.\n")
    previous = signal.getsignal(signal.SIGTERM)

    def interrupted(*_args):
        raise KeyboardInterrupt("Owned workflow interrupted; no automatic replay.")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.mode == "inner":
            return inner()
        if args.mode == "controller":
            return controller()
        if args.mode == "host":
            return host(args.proof_root.resolve(strict=True), args.chromium)
        if args.mode == "verify":
            print(contract.recovery.canonical(contract.verify_original(args)))
            return 0
        return run(args)
    except evidence.EvidenceFailure as error:
        evidence.emit_failure(error)
        raise SystemExit(1) from error
    except Exception as error:
        parser.exit(1, type(error).__name__ + ": " + str(error) + "\n")
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
