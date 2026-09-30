"""Exercise an installed Linux desktop in a disposable offline Ubuntu container.

Requires an existing qualification image, pinned source ZIP/build receipt and the
actual .deb. No image pulls, builds, source server or model mocks are used. Run
--help before installing optional host Playwright/Chromium tooling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path("/opt/neuroforge/sinter/Sinter")
MAX_REQUEST = 16_000_000
MAX_HEADER = 65_536
MAX_ARTIFACT = 2_000_000
if sys.argv[1:] != ["--container"]:
    # Internal mode is copied alone into the disposable container. Its relay
    # never imports the repository or runs the source application.
    sys.path.insert(0, str(ROOT))
    from tools.installed_workflow_contract import (
        ACTION_TASK,
        ARTIFACT_PATHS,
        CHECKS,
        COMMUNICATION,
        MAX_ARTIFACT_BYTES,
        MAX_TOTAL_BYTES,
        OPERATOR_NOTE,
        RECIPIENT,
        RESOURCE_FLAGS,
        RESTORED_CAMPAIGN_TITLE,
        RESTORED_CASEBOOK_TITLE,
        SCHEMA,
    )

    ARTIFACTS = {role: Path(path).name for role, path in ARTIFACT_PATHS.items()}
    MAX_ARTIFACT = MAX_ARTIFACT_BYTES

SAVED_CAMPAIGN = (
    "Campaign saved. Answers, costs, checks and actions will be here when you return."
)


def digest(path: Path) -> str:
    """Hash an exact retained file without printing its contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_digest(value: object) -> str:
    """Hash deterministic Unicode JSON snapshots."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def command(*args: str, timeout: int = 30) -> str:
    """Run bounded test tooling; output never contains request/session payloads."""
    result = subprocess.run(
        args, capture_output=True, text=True, check=True, timeout=timeout
    )
    return result.stdout.strip()


def inner_address(value: str) -> tuple[str, int]:
    """Accept only a credential-free, exact IPv4 loopback browser launch URL."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not parsed.port
        or value != f"http://127.0.0.1:{parsed.port}"
    ):
        raise ValueError("The native launch address is not an exact local URL.")
    return parsed.hostname, parsed.port


def rewrite_headers(raw: bytes, outer: str, inner: str) -> bytes:
    """Change only destination-bound Host/Origin; retain all other exact bytes."""
    if len(raw) > MAX_HEADER or not raw.endswith(b"\r\n\r\n"):
        raise ValueError("Invalid or oversized relay request headers.")
    lines = raw[:-4].split(b"\r\n")
    parts = lines[0].split(b" ")
    if (
        len(parts) != 3
        or parts[0] not in {b"GET", b"HEAD", b"POST", b"OPTIONS"}
        or not parts[1].startswith(b"/")
        or parts[1].startswith(b"//")
        or parts[2] not in {b"HTTP/1.0", b"HTTP/1.1"}
    ):
        raise ValueError("Only local origin-form HTTP requests are relayed.")
    counts: dict[bytes, int] = {}
    rewritten = [lines[0]]
    for line in lines[1:]:
        if not line or line[:1] in {b" ", b"\t"} or b":" not in line:
            raise ValueError("Malformed relay header.")
        key, value = line.split(b":", 1)
        name = key.lower()
        counts[name] = counts.get(name, 0) + 1
        if name in {b"transfer-encoding", b"upgrade", b"trailer"}:
            raise ValueError("Unsupported relay request framing.")
        if name in {b"host", b"origin", b"content-length"} and counts[name] > 1:
            raise ValueError("Ambiguous relay request framing.")
        if name == b"host":
            if value.strip() != outer.encode("ascii"):
                raise ValueError("Unexpected outer Host.")
            line = key + b": " + inner.encode("ascii")
        elif name == b"origin":
            if value.strip() != ("http://" + outer).encode("ascii"):
                raise ValueError("Unexpected outer Origin.")
            line = key + b": http://" + inner.encode("ascii")
        elif name == b"content-length":
            if not re.fullmatch(rb"[0-9]+", value.strip()):
                raise ValueError("Invalid request length.")
            if int(value) > MAX_REQUEST:
                raise ValueError("Oversized relay request.")
        rewritten.append(line)
    if counts.get(b"host") != 1:
        raise ValueError("A relay request needs one exact Host.")
    return b"\r\n".join(rewritten) + b"\r\n\r\n"


class Relay(socketserver.ThreadingTCPServer):
    """Loopback-only raw HTTP relay; responses are never parsed or rewritten."""

    daemon_threads = True

    def __init__(self, runtime: Path):
        self.runtime = runtime
        self.errors = 0
        self.model_requests = 0
        self.lock = threading.Lock()
        self.connections: set[socket.socket] = set()
        super().__init__(("127.0.0.1", 0), RelayRequest)

    def server_close(self) -> None:
        with self.lock:
            for connection in self.connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        super().server_close()

    def idle(self) -> bool:
        """Confirm request handlers have finished, including idle preconnects."""
        with self.lock:
            return not self.connections


class RelayRequest(socketserver.BaseRequestHandler):
    def setup(self) -> None:
        with self.server.lock:
            self.server.connections.add(self.request)

    def finish(self) -> None:
        with self.server.lock:
            self.server.connections.discard(self.request)

    def handle(self) -> None:
        self.request.settimeout(20)
        try:
            received = bytearray()
            while b"\r\n\r\n" not in received:
                chunk = self.request.recv(4096)
                if not chunk:
                    if not received:
                        return
                    raise ValueError("Relay headers were incomplete.")
                received.extend(chunk)
                if len(received) > MAX_HEADER:
                    raise ValueError("Relay headers were incomplete.")
            head, body = bytes(received).split(b"\r\n\r\n", 1)
            state = json.loads((self.server.runtime / "state.json").read_text())
            inner = f"127.0.0.1:{state['port']}"
            outer = f"127.0.0.1:{self.server.server_address[1]}"
            headers = rewrite_headers(head + b"\r\n\r\n", outer, inner)
            path = head.split(b" ")[1].split(b"?")[0]
            if path.startswith(
                (
                    b"/api/chat",
                    b"/api/template/",
                    b"/api/assistant/",
                    b"/api/casebooks/draft",
                    b"/api/atlas/answer",
                    b"/api/models",
                    b"/api/health",
                )
            ):
                self.server.model_requests += 1
            match = re.search(rb"(?im)^content-length:\s*([0-9]+)\r?$", head)
            size = int(match[1]) if match else 0
            while len(body) < size:
                chunk = self.request.recv(min(65_536, size - len(body)))
                if not chunk:
                    raise ValueError("Relay request body was incomplete.")
                body += chunk
            if len(body) != size:
                raise ValueError("Relay request contains unexpected extra bytes.")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                channel.settimeout(20)
                channel.connect(str(self.server.runtime / "relay.sock"))
                channel.sendall(headers + body)
                channel.shutdown(socket.SHUT_WR)
                total = 0
                while chunk := channel.recv(65_536):
                    total += len(chunk)
                    if total > 32_000_000:
                        raise ValueError("Relay response exceeded its bound.")
                    self.request.sendall(chunk)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            self.server.errors += 1
            # Fail closed. Do not synthesize a successful product response.


class InnerRelay(
    getattr(socketserver, "ThreadingUnixStreamServer", socketserver.ThreadingTCPServer)
):
    daemon_threads = True

    def __init__(self, root: Path):
        if not hasattr(socket, "AF_UNIX"):
            raise ValueError("Installed Linux qualification needs Unix sockets.")
        self.root = root
        self.port = 0
        super().__init__(str(root / "relay.sock"), InnerRequest)
        os.chmod(root / "relay.sock", 0o666)


class InnerRequest(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(20)
        try:
            request = bytearray()
            while chunk := self.request.recv(65_536):
                request.extend(chunk)
                if len(request) > MAX_REQUEST + MAX_HEADER:
                    raise ValueError("Oversized inner relay request.")
            # The container has no network interface except loopback. Never
            # derive a target from the client's Host or any request payload.
            with socket.create_connection(("127.0.0.1", self.server.port), 20) as app:
                app.sendall(request)
                app.shutdown(socket.SHUT_WR)
                while chunk := app.recv(65_536):
                    self.request.sendall(chunk)
        except (OSError, ValueError):
            pass


def write_json(path: Path, value: object) -> None:
    """Atomically publish bounded test state or a structured proof receipt."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def container_main() -> None:
    """Install/launch/remove only inside the disposable test container."""
    if getattr(os, "geteuid", lambda: -1)() != 0 or not Path("/.dockerenv").is_file():
        raise ValueError("Internal mode requires a disposable root Docker container.")
    root = Path("/proof")
    root.joinpath("data").mkdir(mode=0o700, exist_ok=True)
    info = {
        "package": command("dpkg-deb", "-f", "/candidate.deb", "Package"),
        "package_version": command("dpkg-deb", "-f", "/candidate.deb", "Version"),
        "architecture": command("dpkg-deb", "-f", "/candidate.deb", "Architecture"),
    }
    process = None
    relay = None
    relay_thread = None
    try:
        existing = subprocess.run(
            ["dpkg-query", "-W", "sinter"], capture_output=True, check=False
        )
        if existing.returncode == 0 or info["package"] != "sinter":
            raise ValueError("Qualification needs a fresh actual Sinter installer.")
        command("dpkg", "-i", "/candidate.deb", timeout=60)
        info["installed_package_version"] = command(
            "dpkg-query", "-W", "-f=${Version}", "sinter"
        )
        info["version"] = command(str(BINARY), "--version")
        info["binary_sha256"] = digest(BINARY)
        web = BINARY.parent / "_internal/sinter/web"
        info["web"] = {
            "src/sinter/web/" + path.name: digest(path)
            for path in sorted(web.iterdir())
            if path.is_file()
        }
        release = dict(
            line.split("=", 1)
            for line in Path("/etc/os-release").read_text().splitlines()
            if "=" in line
        )
        info["runtime"] = {
            "os_id": release["ID"].strip('"'),
            "os_version": release["VERSION_ID"].strip('"'),
            "machine": os.uname().machine,
            "pointer_bits": struct.calcsize("P") * 8,
            "tooling_python": sys.version.split()[0],
        }
        info["os_release"] = {
            key: release[key].strip('"') for key in ("ID", "VERSION_ID")
        }
        info["libc"] = list(platform.libc_ver())
        command(str(BINARY), "--self-test", str(root / "frozen.json"), timeout=60)
        info["frozen_test"] = json.loads((root / "frozen.json").read_text())
        relay = InnerRelay(root)
        relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
        relay_thread.start()
        run = 0
        while True:
            if process is None:
                run += 1
                capture = root / "launch-url.txt"
                capture.unlink(missing_ok=True)
                browser = root / "capture.py"
                browser.write_text(
                    "import sys\nfrom pathlib import Path\n"
                    "Path('/proof/launch-url.txt').write_text(sys.argv[1])\n"
                )
                env = {
                    "PATH": "/usr/bin:/bin",
                    "HOME": str(root / "home"),
                    "SINTER_DATA_DIR": str(root / "data"),
                    "BROWSER": "/usr/bin/python3 /proof/capture.py %s",
                }
                process = subprocess.Popen(
                    [str(BINARY)],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                deadline = time.monotonic() + 20
                while not capture.exists() and time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise ValueError("The native desktop stopped before launch.")
                    time.sleep(0.05)
                _, relay.port = inner_address(capture.read_text())
                write_json(
                    root / "state.json",
                    {
                        **info,
                        "phase": "running",
                        "run": run,
                        "port": relay.port,
                    },
                )
            if process.poll() is not None:
                with socket.socket() as probe:
                    closed = probe.connect_ex(("127.0.0.1", relay.port)) != 0
                write_json(
                    root / "state.json",
                    {
                        **info,
                        "phase": "stopped",
                        "run": run,
                        "exit_code": process.returncode,
                        "port_closed": closed,
                    },
                )
            control = root / "control.json"
            if control.exists():
                action = json.loads(control.read_text())["action"]
                control.unlink()
                if action == "restart" and process.poll() is not None:
                    process = None
                elif action == "cleanup":
                    break
                else:
                    raise ValueError("Invalid native lifecycle test command.")
            time.sleep(0.05)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        write_json(
            root / "state.json",
            {
                "phase": "failed",
                "error_type": type(error).__name__,
            },
        )
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if relay is not None:
            relay.shutdown()
            relay.server_close()
            relay_thread.join(timeout=5)
        command("dpkg", "-r", "sinter", timeout=60)
        if BINARY.exists():
            raise ValueError("The installed executable remains after removal.")
        write_json(root / "removed.json", {"package_removed": True})
        uid, gid = (
            int(os.environ["SINTER_TEST_UID"]),
            int(os.environ["SINTER_TEST_GID"]),
        )
        for directory, directories, files in os.walk(root):
            for name in directories + files:
                os.chown(Path(directory) / name, uid, gid)


def wait_state(runtime: Path, phase: str, run: int, timeout: int = 30) -> dict:
    """Observe the actual native process, never a browser-only reload."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (runtime / "state.json").is_file():
            state = json.loads((runtime / "state.json").read_text())
            if state.get("phase") == "failed":
                raise ValueError("The disposable installed process failed.")
            if state.get("phase") == phase and state.get("run") == run:
                return state
        time.sleep(0.05)
    raise ValueError("The installed lifecycle test exceeded its time bound.")


def validate_inputs(args: argparse.Namespace) -> tuple[dict, dict]:
    """Bind all installation inputs before creating any output/container."""
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("Choose a new proof directory; existing output is protected.")
    for name in ("installer_sha256", "source_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", getattr(args, name)):
            raise ValueError("Provide complete lowercase SHA-256 identities.")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise ValueError("Provide the complete lowercase source commit.")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:rc[1-9]\d*)?", args.version):
        raise ValueError("Provide an explicit supported release version.")
    for path in (args.installer, args.source_archive, args.native_receipt):
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 150_000_000:
            raise ValueError("Provide bounded regular candidate input files.")
        if any(character in str(path.resolve()) for character in (",", "\n", "\r")):
            raise ValueError("Candidate paths contain unsupported mount characters.")
    if digest(args.installer) != args.installer_sha256:
        raise ValueError("The installer checksum differs from the pinned input.")
    if digest(args.source_archive) != args.source_sha256:
        raise ValueError("The source checksum differs from the pinned input.")
    expected = subprocess.check_output(
        ["git", "archive", "--format=zip", args.source_commit], cwd=ROOT, timeout=30
    )
    if hashlib.sha256(expected).hexdigest() != args.source_sha256:
        raise ValueError("The source ZIP differs from the exact pinned Git archive.")
    with zipfile.ZipFile(args.source_archive) as archive:
        names = archive.namelist()
        if (
            len(names) != len(set(names))
            or archive.comment.decode() != args.source_commit
        ):
            raise ValueError("The source archive has ambiguous commit/file identities.")
        init = archive.read("src/sinter/__init__.py")
        match = re.search(rb'__version__\s*=\s*["\']([^"\']+)["\']', init)
        if not match or match[1].decode() != args.version:
            raise ValueError("The source archive declares another version.")
        fixture = {
            kind: json.loads(archive.read(f"src/sinter/web/offline-garden-{kind}.json"))
            for kind in ("casebook", "campaign")
        }
        fixture["practice_hashes"] = {
            f"src/sinter/web/offline-garden-{kind}.json": hashlib.sha256(
                archive.read(f"src/sinter/web/offline-garden-{kind}.json")
            ).hexdigest()
            for kind in ("casebook", "campaign")
        }
        fixture["web"] = {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in names
            if name.startswith("src/sinter/web/") and not name.endswith("/")
        }
    native = json.loads(args.native_receipt.read_text())
    package = args.version.replace("rc", "~rc")
    if (
        native.get("schema") != "sinter-native-test/v1"
        or native.get("passed") is not True
        or native.get("frozen") is not True
        or native.get("system") != "Linux"
        or native.get("target_arch") != "x64"
        or native.get("version") != args.version
        or native.get("source_commit") != args.source_commit
        or native.get("installer_sha256") != args.installer_sha256
        or native.get("package_version") != package
    ):
        raise ValueError("The native build receipt does not bind these exact inputs.")
    return fixture, native


def artifact_inventory(output: Path) -> list[dict]:
    """Retain exactly the declared eight bounded fictional proof artifacts."""
    directory = output / "installed-workflow"
    if {path.name for path in directory.iterdir()} != set(ARTIFACTS.values()):
        raise ValueError("The installed workflow evidence roles differ.")
    records = []
    for role, name in ARTIFACTS.items():
        path = directory / name
        if (
            not path.is_file()
            or path.is_symlink()
            or not 0 < path.stat().st_size <= MAX_ARTIFACT
        ):
            raise ValueError("An installed workflow artifact is missing or oversized.")
        if name.endswith(".png") and not path.read_bytes().startswith(
            b"\x89PNG\r\n\x1a\n"
        ):
            raise ValueError("A screenshot does not contain PNG bytes.")
        if name.endswith(".json") and not isinstance(
            json.loads(path.read_text()), dict
        ):
            raise ValueError("A backup does not contain a JSON object.")
        records.append(
            {
                "role": role,
                "path": "installed-workflow/" + name,
                "sha256": digest(path),
                "bytes": path.stat().st_size,
            }
        )
    if sum(row["bytes"] for row in records) > MAX_TOTAL_BYTES:
        raise ValueError("Installed workflow evidence exceeds its aggregate bound.")
    return records


def word_check(path: Path, source_ids: list[str]) -> None:
    """Check the actual downloaded safe OOXML and retained source identities."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) > 40 or len(names) != len(set(names)):
            raise ValueError("Ambiguous or excessive Word package members.")
        if sum(row.file_size for row in archive.infolist()) > 8_000_000:
            raise ValueError("Word package expansion exceeds its bound.")
        for name in names:
            if (
                PurePosixPath(name).is_absolute()
                or ".." in PurePosixPath(name).parts
                or not name.endswith((".xml", ".rels"))
                or "media/" in name
            ):
                raise ValueError("Unexpected Word payload.")
            root = ElementTree.fromstring(archive.read(name))
            if any(row.get("TargetMode") == "External" for row in root.iter()):
                raise ValueError("Word contains an external relationship.")
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        text = " ".join(row.text or "" for row in root.iter() if row.tag.endswith("}t"))
        for identifier in source_ids:
            assert text.count(identifier) == 1
        assert "No order or enquiry has been sent." in text
        assert "The real-world answer remains unknown" in text


def browser_workflow(
    args: argparse.Namespace,
    runtime: Path,
    relay: Relay,
    fixture: dict,
    checks: list[str],
) -> tuple[dict, int, int]:
    """Operate the frozen app through its real UI and explicit local saves."""
    from playwright.sync_api import expect, sync_playwright

    sys.path.insert(0, str(ROOT))
    from tools._support import launch_chromium

    output = args.output / "installed-workflow"
    origin = f"http://127.0.0.1:{relay.server_address[1]}"
    errors, external = [], []
    snapshots = {}
    with sync_playwright() as driver:
        browser = launch_chromium(driver, args.chromium)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                accept_downloads=True,
                reduced_motion="reduce",
                service_workers="block",
            )
            context.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if urlsplit(route.request.url).netloc == urlsplit(origin).netloc
                    and urlsplit(route.request.url).scheme == "http"
                    else (external.append(True), route.abort())
                ),
            )
            context.route_web_socket(
                "**/*", lambda route: (external.append(True), route.close())
            )
            page = context.new_page()
            page.set_default_timeout(10_000)
            page.on("pageerror", lambda error: errors.append(type(error).__name__))
            page.on("dialog", lambda dialog: dialog.accept())

            def read(path: str) -> dict:
                return page.evaluate(
                    "path => fetch(path).then(r => {"
                    "if (!r.ok) throw Error('Read failed'); return r.json();})",
                    path,
                )

            def screenshot(role: str) -> None:
                page.screenshot(path=str(output / ARTIFACTS[role]))

            def sources() -> None:
                entries = page.locator(".casebook-editor details.source")
                expect(entries).to_have_count(len(fixture["casebook"]["documents"]))
                for index, original in enumerate(fixture["casebook"]["documents"]):
                    if entries.nth(index).get_attribute("open") is None:
                        entries.nth(index).locator("summary").click()
                    assert (
                        entries.nth(index).locator("pre").inner_text()
                        == original["content"]
                    )

            def quit_app(run: int) -> None:
                page.get_by_role("button", name="Quit Sinter", exact=True).click()
                state = wait_state(runtime, "stopped", run)
                assert state["exit_code"] == 0 and state["port_closed"] is True

            page.goto(origin + "/#home")
            identity = page.evaluate(
                "() => fetch('/api/session').then(r => r.json())"
                ".then(({version,desktop}) => ({version,desktop}))"
            )
            assert identity == {"version": args.version, "desktop": True}
            card = page.get_by_role("region", name="Fictional garden practice project")
            expect(card).to_contain_text("No account or internet needed")
            screenshot("overview")
            checks.append(CHECKS[2])
            card.get_by_role("button", name="Open garden handover", exact=True).click()
            expect(page.get_by_label("Project name", exact=True)).to_have_value(
                fixture["casebook"]["title"]
            )
            sources()
            checks.append(CHECKS[3])
            page.get_by_label("Recipient or audience", exact=True).fill(RECIPIENT)
            page.get_by_role(
                "button", name="Prepare source-only report", exact=True
            ).click()
            report = page.get_by_role("region", name="Your draft report")
            document = report.get_by_role("tabpanel", name="Document", exact=True)
            expect(document).to_contain_text("Source-only handover checklist")
            expect(document.get_by_role("table")).to_have_count(1)
            screenshot("prepared_handover")
            report.get_by_text("More options", exact=True).click()
            report.get_by_role("button", name="Edit draft", exact=True).click()
            editor = report.get_by_label("Edit your draft", exact=True)
            editor.fill(editor.input_value() + OPERATOR_NOTE)
            report.get_by_role("button", name="Apply edits", exact=True).click()
            report.get_by_role(
                "button", name="Save to this computer", exact=True
            ).click()
            expect(
                report.get_by_text(
                    "Saved in My workspace, including your edits "
                    "and original evidence.",
                    exact=True,
                )
            ).to_be_visible()
            page.get_by_role("button", name="Save project", exact=True).click()
            expect(page.get_by_text("Saved revision 2.", exact=False)).to_be_visible()
            books = read("/api/casebooks")["casebooks"]
            assert len(books) == 1
            snapshots["saved_casebook"] = read("/api/casebooks/" + books[0]["id"])
            reports = read("/api/reports")["reports"]
            assert len(reports) == 1
            snapshots["saved_report"] = read("/api/reports/" + reports[0]["id"])
            checks.append(CHECKS[4])

            page.get_by_role("region", name="Garden practice steps").get_by_role(
                "button", name="Open garden campaign"
            ).click()
            page.get_by_role("tab", name="Next actions", exact=True).click()
            action = page.get_by_role(
                "article", name="Campaign action", exact=True
            ).nth(0)
            if action.locator("details").get_attribute("open") is None:
                action.locator("summary").click()
            action.locator('[data-campaign-field="task"]').fill(ACTION_TASK)
            screenshot("campaign_action")
            page.get_by_role("tab", name="Communications", exact=True).click()
            page.get_by_role("button", name="Add communication", exact=True).click()
            communication = page.get_by_role(
                "article", name="Campaign communication", exact=True
            )
            communication.get_by_label("Subject or short title", exact=True).fill(
                COMMUNICATION["subject"]
            )
            communication.get_by_label(
                "Communication date (user-entered)", exact=True
            ).fill(COMMUNICATION["date"])
            communication.get_by_label("Person or organisation", exact=True).fill(
                COMMUNICATION["counterparty"]
            )
            communication.get_by_label("Message text or summary", exact=True).fill(
                COMMUNICATION["content"]
            )
            expect(communication).to_contain_text("Draft · not sent")
            page.get_by_role("button", name="Save campaign", exact=True).click()
            expect(
                page.get_by_text(
                    SAVED_CAMPAIGN,
                    exact=True,
                )
            ).to_be_visible()
            campaigns = read("/api/campaigns")["campaigns"]
            assert len(campaigns) == 1
            snapshots["saved_campaign"] = read("/api/campaigns/" + campaigns[0]["id"])
            checks.append(CHECKS[5])
            quit_app(1)
            checks.append(CHECKS[6])
            write_json(runtime / "control.json", {"action": "restart"})
            restarted = wait_state(runtime, "running", 2)
            assert restarted["version"] == args.version
            checks.append(CHECKS[7])
            context.clear_cookies()
            page.close()
            page = context.new_page()
            page.set_default_timeout(10_000)
            page.on("pageerror", lambda error: errors.append(type(error).__name__))
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(origin + "/#campaigns")
            page.get_by_role("tab", name="Next actions", exact=True).click()
            action = page.get_by_role(
                "article", name="Campaign action", exact=True
            ).nth(0)
            if action.locator("details").get_attribute("open") is None:
                action.locator("summary").click()
            expect(action.locator('[data-campaign-field="task"]')).to_have_value(
                ACTION_TASK
            )
            page.get_by_role("tab", name="Communications", exact=True).click()
            expect(
                page.get_by_role("article", name="Campaign communication", exact=True)
            ).to_contain_text(COMMUNICATION["subject"])
            page.get_by_role("link", name="My workspace", exact=True).click()
            page.get_by_role("button", name="Open draft", exact=True).click()
            report = page.get_by_role("region", name="Your draft report")
            expect(
                report.get_by_role("tabpanel", name="Document", exact=True)
            ).to_contain_text("No order or enquiry has been sent.")
            screenshot("reopened_handover")
            checks.append(CHECKS[8])
            with page.expect_download() as downloaded:
                report.get_by_role(
                    "button", name="Download Word (.docx)", exact=True
                ).click()
            downloaded.value.save_as(output / ARTIFACTS["handover_word"])
            word_check(
                output / ARTIFACTS["handover_word"],
                [row["id"] for row in snapshots["saved_report"]["excerpts"]],
            )
            checks.append(CHECKS[9])
            page.get_by_role("link", name="Community casebooks", exact=True).click()
            page.get_by_role("button", name="Open project", exact=True).click()
            expect(
                page.get_by_label("Recipient or audience", exact=True)
            ).to_have_value(RECIPIENT)
            sources()
            with page.expect_download() as downloaded:
                page.get_by_role(
                    "button", name="Export project backup", exact=True
                ).click()
            downloaded.value.save_as(output / ARTIFACTS["casebook_backup"])
            page.get_by_role("link", name="Funding campaigns", exact=True).click()
            page.get_by_text("Import or back up a campaign", exact=True).click()
            with page.expect_download() as downloaded:
                page.get_by_role(
                    "button", name="Export campaign backup", exact=True
                ).click()
            downloaded.value.save_as(output / ARTIFACTS["campaign_backup"])
            checks.append(CHECKS[10])
            page.get_by_label("Import campaign backup", exact=True).set_input_files(
                output / ARTIFACTS["campaign_backup"]
            )
            expect(page.locator('[data-campaign-field="title"]')).to_have_value(
                fixture["campaign"]["title"]
            )
            if not page.locator('[data-campaign-field="title"]').is_visible():
                page.get_by_text("Campaign details", exact=True).click()
            page.locator('[data-campaign-field="title"]').fill(RESTORED_CAMPAIGN_TITLE)
            page.get_by_role("button", name="Save campaign", exact=True).click()
            expect(
                page.get_by_text(
                    SAVED_CAMPAIGN,
                    exact=True,
                )
            ).to_be_visible()
            campaigns = read("/api/campaigns")["campaigns"]
            assert len(campaigns) == 2
            copied = next(
                row
                for row in campaigns
                if row["id"] != snapshots["saved_campaign"]["id"]
            )
            snapshots["restored_campaign"] = read("/api/campaigns/" + copied["id"])
            page.get_by_role("tab", name="Communications", exact=True).click()
            communication = page.get_by_role(
                "article", name="Campaign communication", exact=True
            )
            if communication.locator("details").first.get_attribute("open") is None:
                communication.locator("summary").first.click()
            expect(communication).to_contain_text("Draft · not sent")
            expect(
                communication.get_by_label("Message text or summary", exact=True)
            ).to_have_value(COMMUNICATION["content"])
            page.get_by_role("link", name="Community casebooks", exact=True).click()
            page.get_by_text("Backups and project removal", exact=True).click()
            page.get_by_label("Restore a casebook backup", exact=True).set_input_files(
                output / ARTIFACTS["casebook_backup"]
            )
            expect(
                page.get_by_text("Backup opened as a new unsaved project.", exact=True)
            ).to_be_visible()
            sources()
            page.get_by_label("Project name", exact=True).fill(RESTORED_CASEBOOK_TITLE)
            page.get_by_role("button", name="Save project", exact=True).click()
            expect(page.get_by_text("Saved revision 1.", exact=False)).to_be_visible()
            books = read("/api/casebooks")["casebooks"]
            assert len(books) == 2
            copied = next(
                row for row in books if row["id"] != snapshots["saved_casebook"]["id"]
            )
            snapshots["restored_casebook"] = read("/api/casebooks/" + copied["id"])
            screenshot("restored_workspace")
            checks.append(CHECKS[11])
            original_book = snapshots["saved_casebook"]
            original_campaign = snapshots["saved_campaign"]
            assert read("/api/casebooks/" + original_book["id"]) == original_book
            assert (
                read("/api/campaigns/" + original_campaign["id"]) == original_campaign
            )
            assert read("/api/reports/" + reports[0]["id"]) == snapshots["saved_report"]
            assert (
                original_book["document"]["documents"]
                == fixture["casebook"]["documents"]
            )
            assert (
                snapshots["restored_casebook"]["document"]["documents"]
                == fixture["casebook"]["documents"]
            )
            assert (
                snapshots["restored_campaign"]["document"]["communications"]
                == original_campaign["document"]["communications"]
            )
            assert (
                original_campaign["document"]["communications"][0]["content"]
                == COMMUNICATION["content"]
            )
            assert (
                original_campaign["document"]["communications"][0]["status"] == "draft"
            )
            for key in ("answers", "requirements", "sources"):
                assert original_campaign["document"][key] == fixture["campaign"][key]
                assert (
                    snapshots["restored_campaign"]["document"][key]
                    == original_campaign["document"][key]
                )
            checks.append(CHECKS[12])
            quit_app(2)
            checks.append(CHECKS[13])
            context.close()
        finally:
            browser.close()
    assert not errors and not external
    return (
        {
            key: object_digest(value.get("document", value))
            for key, value in snapshots.items()
        },
        len(errors),
        len(external),
    )


def qualify(args: argparse.Namespace, fixture: dict) -> dict:
    """Run the real installer and retain no secret/runtime transport artifacts."""
    if sys.platform != "linux":
        raise ValueError("Run this installed Linux workflow on a Linux host.")
    image = command("docker", "image", "inspect", args.image, "--format", "{{.Id}}")
    args.output.mkdir(mode=0o700)
    (args.output / "installed-workflow").mkdir()
    receipt = {
        "schema": SCHEMA,
        "passed": False,
        "version": args.version,
        "source_commit": args.source_commit,
        "source_archive_sha256": args.source_sha256,
        "installer_sha256": args.installer_sha256,
        "native_receipt_sha256": digest(args.native_receipt),
        "system": "Linux",
        "target_arch": "x64",
        "machine": "x86_64",
        "pointer_bits": 64,
        "frozen": False,
        "desktop": False,
        "installed_executable": str(BINARY),
        "installed_binary_sha256": "",
        "web_assets_sha256": fixture["web"],
        "practice_fixture_sha256": fixture["practice_hashes"],
        "image_id": image,
        "container": "ubuntu:22.04",
        "os_release": {},
        "libc": [],
        "network": "disabled container; loopback only",
        "network_mode": "",
        "host_installation": False,
        "resources": {name: False for name in RESOURCE_FLAGS},
        "external_requests": 0,
        "page_errors": 0,
        "model_calls": 0,
        "checks": [],
        "input_hashes": {
            "garden_casebook": object_digest(fixture["casebook"]),
            "garden_campaign": object_digest(fixture["campaign"]),
            "static_assets": object_digest(fixture["web"]),
        },
        "result_hashes": {},
        "artifacts": [],
    }
    path = args.output / "installed-workflow-browser.json"
    write_json(path, receipt)
    name = "sinter-installed-ui-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="sinter-installed-private-") as temporary:
        runtime = Path(temporary)
        (runtime / "data").mkdir(mode=0o700)
        shutil.copyfile(Path(__file__), runtime / "helper.py")
        relay = None
        relay_thread = None
        created = False
        try:
            command(
                "docker",
                "create",
                "--pull=never",
                "--network=none",
                "--name",
                name,
                "--env",
                f"SINTER_TEST_UID={os.getuid()}",
                "--env",
                f"SINTER_TEST_GID={os.getgid()}",
                "--mount",
                f"type=bind,src={runtime},dst=/proof",
                "--mount",
                f"type=bind,src={args.installer.resolve()},dst=/candidate.deb,readonly",
                image,
                "/usr/bin/python3",
                "/proof/helper.py",
                "--container",
            )
            created = True
            command("docker", "start", name)
            receipt["network_mode"] = command(
                "docker", "inspect", name, "--format", "{{.HostConfig.NetworkMode}}"
            )
            assert receipt["network_mode"] == "none"
            state = wait_state(runtime, "running", 1, 100)
            assert state["package"] == "sinter" and state["architecture"] == "amd64"
            assert (
                state["package_version"]
                == state["installed_package_version"]
                == args.version.replace("rc", "~rc")
            )
            assert state["version"] == args.version and state["web"] == fixture["web"]
            assert (
                state["runtime"]["os_id"] == "ubuntu"
                and state["runtime"]["os_version"] == "22.04"
            )
            assert (
                state["runtime"]["machine"] == "x86_64"
                and state["runtime"]["pointer_bits"] == 64
            )
            receipt["installed_binary_sha256"] = state["binary_sha256"]
            receipt["os_release"] = state["os_release"]
            receipt["libc"] = state["libc"]
            assert state["libc"] == ["glibc", "2.35"]
            receipt["checks"].append(CHECKS[0])
            frozen = state["frozen_test"]
            assert frozen["passed"] is True and frozen["frozen"] is True
            assert frozen["version"] == args.version and frozen["system"] == "Linux"
            assert frozen["machine"] == "x86_64" and frozen["pointer_bits"] == 64
            receipt["machine"] = frozen["machine"]
            receipt["pointer_bits"] = frozen["pointer_bits"]
            receipt["system"] = frozen["system"]
            receipt["frozen"] = True
            receipt["desktop"] = True
            receipt["checks"].append(CHECKS[1])
            relay = Relay(runtime)
            relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
            relay_thread.start()
            results, errors, external = browser_workflow(
                args, runtime, relay, fixture, receipt["checks"]
            )
            assert relay.errors == 0
            assert relay.model_requests == 0
            receipt["result_hashes"] = results
            receipt["page_errors"], receipt["external_requests"] = errors, external
            receipt["resources"]["browser_closed"] = True
            receipt["resources"]["installed_process_stopped"] = True
            receipt["artifacts"] = artifact_inventory(args.output)
        finally:
            if relay is not None:
                relay.shutdown()
                relay.server_close()
                relay_thread.join(timeout=5)
                deadline = time.monotonic() + 2
                while not relay.idle() and time.monotonic() < deadline:
                    time.sleep(0.01)
                receipt["resources"]["relay_closed"] = (
                    not relay_thread.is_alive() and relay.idle()
                )
            if created:
                write_json(runtime / "control.json", {"action": "cleanup"})
                deadline = time.monotonic() + 20
                while (
                    not (runtime / "removed.json").exists()
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.05)
                removed = (runtime / "removed.json").exists()
                command("docker", "rm", "--force", name)
                receipt["resources"]["package_removed"] = removed
                receipt["resources"]["container_removed"] = True
            if all(receipt["resources"].values()):
                receipt["checks"].append(CHECKS[14])
            write_json(path, receipt)
    if tuple(receipt["checks"]) != CHECKS or not all(receipt["resources"].values()):
        raise ValueError("The installed workflow did not complete every proof check.")
    receipt["passed"] = True
    write_json(path, receipt)
    return receipt


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse help/strict identities without importing browser tooling or Docker."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("installer", "source-archive", "native-receipt", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("installer-sha256", "source-sha256", "source-commit", "version"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--image", default="sinter-candidate-qualification:ubuntu2204")
    parser.add_argument("--chromium", default=os.environ.get("SINTER_CHROMIUM"))
    args = parser.parse_args(argv)
    try:
        args.fixture, _ = validate_inputs(args)
        if args.chromium and (
            not Path(args.chromium).is_file() or not os.access(args.chromium, os.X_OK)
        ):
            raise ValueError("Choose an executable host Chromium path.")
        if any(
            character in str(args.output.resolve()) for character in (",", "\n", "\r")
        ):
            raise ValueError("The proof path contains unsupported characters.")
    except (
        OSError,
        ValueError,
        KeyError,
        zipfile.BadZipFile,
        subprocess.SubprocessError,
    ) as error:
        parser.error(str(error))
    return args


def main(argv: list[str] | None = None) -> None:
    if (sys.argv[1:] if argv is None else argv) == ["--container"]:
        container_main()
        return
    args = arguments(argv)
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Host Playwright is required: install .[browser] and Chromium."
        ) from None
    try:
        qualify(args, args.fixture)
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError):
        raise SystemExit(
            "Installed workflow failed; incomplete receipt retained. "
            "No check was skipped."
        ) from None
    print(
        "PASS: installed offline UI, actual restart, Word/backups/restores and cleanup."
    )


if __name__ == "__main__":
    main()
