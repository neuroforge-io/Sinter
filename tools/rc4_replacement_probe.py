"""Bounded owned browser/API observations for the separate RC4 replacement route."""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import select
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.installed_workflow_browser import (  # noqa: E402
    InnerRelay,
    Relay,
    RelayRequest,
    browser_launch_command,
)
from tools.rc4_replacement_contract import (  # noqa: E402
    blob,
    encoded,
    equal,
    json_value,
    regular,
    rendered_words,
    require,
    sha,
)

SCOPED = "sinter-casebook/v2"


class ClosingRequest:
    """Make client reads cancellable without changing raw framing or deadlines."""

    def __init__(self, channel, closing):
        self.channel, self.closing = channel, closing

    def __getattr__(self, name):
        return getattr(self.channel, name)

    def recv(self, size, flags=0):
        timeout = self.channel.gettimeout()
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self.closing.is_set():
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise TimeoutError("Relay client read timed out.")
            ready, _, _ = select.select(
                [self.channel],
                [],
                [],
                0.1 if remaining is None else min(0.1, remaining),
            )
            if ready and not self.closing.is_set():
                return self.channel.recv(size, flags)
        # Empty preconnects close cleanly. The unchanged parser rejects a
        # partial header/body as incomplete and keeps its actual error count.
        return b""


class ClosingRelayRequest(RelayRequest):
    def handle(self):
        channel = self.request
        self.request = ClosingRequest(channel, self.server.closing)
        try:
            super().handle()
        finally:
            # setup/finish and owned-socket observations retain the real socket.
            self.request = channel


class TrackedRequests:
    """Add bounded actual worker/socket ownership to the unchanged raw transport."""

    def __init__(self, runtime):
        self.owned_lock = threading.Lock()
        self.owned_workers, self.owned_sockets = set(), set()
        self.close_failures = []
        self.closing = threading.Event()
        super().__init__(runtime)

    def process_request_thread(self, request, client_address):
        worker = threading.current_thread()
        with self.owned_lock:
            self.owned_workers.add(worker)
            self.owned_sockets.add(request)
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.owned_lock:
                self.owned_workers.discard(worker)
                self.owned_sockets.discard(request)

    def process_request(self, request, client_address):
        with self.owned_lock:
            self.owned_sockets.add(request)
        super().process_request(request, client_address)

    def close_owned(self):
        self.closing.set()
        with self.owned_lock:
            sockets, workers = list(self.owned_sockets), list(self.owned_workers)
        for channel in sockets:
            try:
                channel.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            except BaseException as exc:
                self.close_failures.append("socket-shutdown: " + str(exc))
        try:
            self.server_close()
        except BaseException as exc:
            self.close_failures.append("server-close: " + str(exc))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            for worker in workers:
                try:
                    worker.join(timeout=max(0, deadline - time.monotonic()))
                except BaseException as exc:
                    self.close_failures.append("worker-join: " + str(exc))
            with self.owned_lock:
                workers = list(self.owned_workers)
                if not self.owned_sockets and not workers:
                    break
            time.sleep(0.02)
        with self.owned_lock:
            return len(self.owned_workers), len(self.owned_sockets)


class HostRelay(TrackedRequests, Relay):
    def __init__(self, runtime):
        super().__init__(runtime)
        self.RequestHandlerClass = ClosingRelayRequest


class InstalledRelay(TrackedRequests, InnerRelay):
    pass


def write(path, value):
    """Publish complete UTF-8 bridge messages atomically, never legacy receipts."""
    temporary = path.with_name(path.name + ".temporary")
    temporary.write_text(encoded(value) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


class EvidenceFailure(ValueError):
    """Keep the first exception and full unpublished bytes when disk evidence fails."""

    def __init__(self, publisher):
        self.primary_exception = publisher.primary
        self.cleanup_errors = tuple(publisher.cleanup)
        self.publication_errors = tuple(publisher.errors)
        self.unpublished_bytes = dict(publisher.unpublished)
        self.published_paths = tuple(publisher.published)
        self.schema = publisher.failure_schema
        super().__init__(publisher.message())

    def as_record(self):
        return {
            "schema": self.schema,
            "first_failure": str(self.primary_exception)
            if self.primary_exception is not None
            else None,
            "cleanup_errors": list(self.cleanup_errors),
            "publication_errors": list(self.publication_errors),
            "published_paths": list(self.published_paths),
            "unpublished_bytes": {
                path: {
                    "bytes": len(raw),
                    "sha256": sha(raw),
                    "data_base64": base64.b64encode(raw).decode("ascii"),
                }
                for path, raw in self.unpublished_bytes.items()
            },
        }


class EvidencePublisher:
    """Attempt each owned publication once; never acknowledge an unsuccessful write."""

    def __init__(
        self,
        role,
        primary,
        cleanup,
        *,
        writer=None,
        serializer=None,
        failure_schema="sinter-rc4-replacement-failed-evidence/v1",
        unwrap_primary=False,
        failure_observer=None,
    ):
        self.role, self.primary, self.cleanup = role, primary, cleanup
        self.writer = write if writer is None else writer
        self.serializer = (
            (lambda value: (encoded(value) + "\n").encode("utf-8"))
            if serializer is None
            else serializer
        )
        self.failure_schema = failure_schema
        self.failure_observer = failure_observer
        self.unwrap_primary = unwrap_primary
        self.inherited_cleanup = []
        self.errors, self.exceptions, self.published, self.unpublished = [], [], [], {}
        if isinstance(primary, EvidenceFailure):
            self.errors.extend(primary.publication_errors)
            self.unpublished.update(primary.unpublished_bytes)
            if unwrap_primary:
                self.published.extend(primary.published_paths)
                self.inherited_cleanup.extend(primary.cleanup_errors)
                self.cleanup = self.inherited_cleanup + list(cleanup)
                while isinstance(self.primary, EvidenceFailure):
                    wrapped = self.primary
                    self.primary = (
                        wrapped.primary_exception
                        if wrapped.primary_exception is not None
                        else wrapped.__cause__
                    )

    def attempt(self, path, value):
        raw = self.serializer(value)
        try:
            self.writer(path, value)
        except BaseException as exc:
            failures = (
                (exc,) if self.failure_observer is None else self.failure_observer(exc)
            )
            for failure in failures:
                self.errors.append(
                    {
                        "path": str(path),
                        "error_type": type(failure).__name__,
                        "error": str(failure),
                    }
                )
                self.exceptions.append(failure)
            self.unpublished[str(path)] = raw
            return False
        self.published.append(str(path))
        return True

    def message(self):
        details = [self.role + " phase failed", "first failure: " + str(self.primary)]
        if self.cleanup:
            details.append("cleanup errors: " + "; ".join(self.cleanup))
        if self.errors:
            details.append(
                "publication errors: "
                + "; ".join(row["path"] + ": " + row["error"] for row in self.errors)
            )
        return "; ".join(details)

    def finish(self, fallback):
        if self.primary is None and not self.cleanup and not self.errors:
            return
        if self.unwrap_primary and self.primary is None and self.exceptions:
            self.primary = self.exceptions[0]
        self.attempt(
            fallback,
            {
                "schema": self.failure_schema,
                "role": self.role,
                "first_failure": str(self.primary)
                if self.primary is not None
                else None,
                "cleanup_errors": list(self.cleanup),
                "publication_errors": list(self.errors),
                "published_paths": list(self.published),
                "unpublished_bytes": {
                    path: {
                        "bytes": len(raw),
                        "sha256": sha(raw),
                        "data_base64": base64.b64encode(raw).decode("ascii"),
                    }
                    for path, raw in self.unpublished.items()
                },
            },
        )
        cause = (
            self.primary
            if self.primary is not None
            else (self.exceptions[0] if self.exceptions else None)
        )
        raise EvidenceFailure(self) from cause


def emit_failure(exc, stream=None):
    """Emit full failed bytes, retaining stderr's own failed publication in memory."""
    try:
        # JSON escapes preserve filesystem surrogates; valid Unicode is unchanged.
        raw = (encoded(exc.as_record()) + "\n").encode("utf-8", "backslashreplace")
    except BaseException as rendering_error:
        exc.publication_errors += (
            {
                "path": "<stderr-render>",
                "error_type": type(rendering_error).__name__,
                "error": str(rendering_error),
            },
        )
        try:
            raw = (
                json.dumps(
                    exc.as_record(),
                    sort_keys=True,
                    ensure_ascii=True,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("ascii")
        except BaseException as fallback_error:
            exc.publication_errors += (
                {
                    "path": "<stderr-render-fallback>",
                    "error_type": type(fallback_error).__name__,
                    "error": str(fallback_error),
                },
            )
            return None
    try:
        target = sys.stderr.buffer if stream is None else stream
        written = target.write(raw)
        if written != len(raw):
            raise OSError("Failed evidence stderr write was incomplete.")
        target.flush()
    except BaseException as publication_error:
        exc.publication_errors += (
            {
                "path": "<stderr>",
                "error_type": type(publication_error).__name__,
                "error": str(publication_error),
            },
        )
        exc.unpublished_bytes["<stderr>"] = raw
    return raw


def bridge_request(value, phase, expected_raw):
    require(
        type(value) is dict
        and set(value)
        == {
            "schema",
            "phase",
            "version",
            "pid",
            "port",
            "workspace",
            "binary_sha256",
            "expected_sha256",
            "collector_source_sha256",
        },
        "Closed phase bridge request required.",
    )
    require(
        value["schema"] == "sinter-rc4-replacement-bridge/v1"
        and value["phase"] == phase
        and phase
        in {
            "prior",
            "candidate",
            "candidate-cold",
            "prior-protocol",
            "candidate-protocol",
        }
        and type(value["pid"]) is int
        and value["pid"] > 1
        and type(value["port"]) is int
        and 1 <= value["port"] <= 65535
        and type(value["workspace"]) is str
        and PurePosixPath(value["workspace"]).is_absolute()
        and ".." not in PurePosixPath(value["workspace"]).parts
        and "\\" not in value["workspace"]
        and value["expected_sha256"] == sha(expected_raw)
        and value["collector_source_sha256"] == sha(regular(Path(__file__)))
        and type(value["binary_sha256"]) is str
        and len(value["binary_sha256"]) == 64,
        "Actual installed phase bridge identity differs.",
    )
    expected = json_value(expected_raw)
    version = expected["prior_version"] if phase.startswith("prior") else "0.5.4rc4"
    require(value["version"] == version, "Bridge version differs from its fixed phase.")
    return expected


def closed_port(port):
    with socket.socket() as listener:
        listener.settimeout(0.2)
        return listener.connect_ex(("127.0.0.1", port))


def collect(runtime, chromium, phase, browser_tmp):
    """Host-only collector for one fixed owned phase; never starts the app."""
    request = json_value(regular(runtime / "state.json", 2_000_000))
    expected = bridge_request(
        request, phase, regular(runtime / "expected.json", 2_000_000)
    )
    require((runtime / "relay.sock").is_socket(), "Owned inner relay socket is absent.")
    require(
        not (runtime / "response.json").exists(), "A phase response cannot be replayed."
    )
    require(
        browser_tmp.is_absolute()
        and browser_tmp == browser_tmp.resolve()
        and browser_tmp.is_dir()
        and not any(browser_tmp.iterdir())
        and len(os.fsencode(browser_tmp)) <= 55,
        "Use a fresh short owned browser temp directory.",
    )
    os.environ["TMPDIR"] = str(browser_tmp)
    tempfile.tempdir = str(browser_tmp)
    relay = HostRelay(runtime)
    thread = threading.Thread(target=relay.serve_forever, name="replacement-host-relay")
    thread.start()
    port = relay.server_address[1]
    response = {"request": request, "ui": None, "failure": None, "resources": None}
    cleanup = []
    primary_exception = None

    def attempt(name, action, fallback=None):
        try:
            return action()
        except BaseException as exc:
            cleanup.append(name + ": " + str(exc))
            return fallback

    try:
        response["ui"] = ui(
            "http://127.0.0.1:" + str(port),
            expected,
            runtime,
            chromium,
            request["version"],
        )
    except BaseException as exc:
        response["failure"], primary_exception = str(exc), exc
    finally:
        attempt("relay-shutdown", relay.shutdown)
        attempt("relay-thread-join", lambda: thread.join(timeout=5))
        closed = attempt(
            "relay-owned-close",
            relay.close_owned
            if hasattr(relay, "close_owned")
            else lambda: (_ for _ in ()).throw(
                ValueError("Owned relay close unavailable")
            ),
        )
        workers, sockets = closed if closed is not None else (None, None)
        cleanup.extend(getattr(relay, "close_failures", []))
        response["resources"] = {
            "host_port": port,
            "host_connect_errno": attempt("host-port-check", lambda: closed_port(port)),
            "thread_alive": thread.is_alive(),
            "connections_remaining": attempt("relay-idle", lambda: not relay.idle()),
            "relay_errors": getattr(relay, "errors", None),
            "model_route_requests": getattr(relay, "model_requests", None),
            "workers_remaining": workers,
            "sockets_remaining": sockets,
            "browser_temp_remaining": attempt(
                "browser-temp-check",
                lambda: sorted(path.name for path in browser_tmp.iterdir()),
            ),
        }
        primary = response["failure"]
        if cleanup and primary is None:
            response["failure"] = "Host cleanup failed: " + "; ".join(cleanup)
        publication = EvidencePublisher("HOST", primary_exception, cleanup)
        publication.attempt(
            runtime / "host-diagnostics.json",
            {
                "failure": primary,
                "cleanup_failures": cleanup,
                "resources": response["resources"],
            },
        )
        if publication.errors:
            response["failure"] = publication.message()
        publication.attempt(runtime / "response.json", response)
    publication.finish(runtime / "host-failed-response.json")
    resources = response["resources"]
    require(
        response["failure"] is None
        and not cleanup
        and resources["thread_alive"] is False
        and resources["connections_remaining"] is False
        and type(resources["host_connect_errno"]) is int
        and resources["host_connect_errno"] != 0
        and resources["relay_errors"] == 0
        and resources["model_route_requests"] == 0
        and workers == sockets == 0,
        "Host browser or relay resource observations failed: "
        + str(response["failure"]),
    )
    require(
        not resources["browser_temp_remaining"],
        "Host browser left temporary resources.",
    )
    return response


def hosted_ui(
    api, expected, output, runtime, phase, version, pid, workspace, binary_sha
):
    """Inner owner waits for the independent host to render this actual listener."""
    require(
        runtime.is_dir() and not any(runtime.iterdir()),
        "Use a fresh host-owned bridge directory.",
    )
    require(
        len(os.fsencode(runtime / "relay.sock")) < 108,
        "Owned Unix relay path is too long.",
    )
    request = {
        "schema": "sinter-rc4-replacement-bridge/v1",
        "phase": phase,
        "version": version,
        "pid": pid,
        "port": api.port,
        "workspace": str(workspace),
        "binary_sha256": binary_sha,
        "expected_sha256": sha(encoded(expected).encode()),
        "collector_source_sha256": sha(regular(Path(__file__))),
    }
    bridge_request(request, phase, encoded(expected).encode())
    relay = InstalledRelay(runtime)
    relay.port = api.port
    thread = threading.Thread(
        target=relay.serve_forever, name="replacement-inner-relay"
    )
    thread.start()
    response, failure, primary_exception = None, None, None
    try:
        write(runtime / "expected.json", expected)
        # Bind the digest to actual serialized bytes, including its stable newline.
        request["expected_sha256"] = sha(regular(runtime / "expected.json"))
        write(runtime / "state.json", request)
        deadline = time.monotonic() + 90
        while not (runtime / "response.json").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        require(
            (runtime / "response.json").exists(),
            "Host collector did not finish its bounded phase.",
        )
        response = json_value(regular(runtime / "response.json", 2_000_000))
        require(
            type(response) is dict
            and set(response) == {"request", "ui", "failure", "resources"}
            and equal(response["request"], request)
            and response["failure"] is None,
            "Host response does not match this exact actual installed phase: "
            + str(response.get("failure") if type(response) is dict else response),
        )
        for image in response["ui"]["screenshots"]:
            name = image["name"]
            require(
                Path(name).name == name and name.endswith(".png"),
                "Invalid screenshot artifact name.",
            )
            (output / name).write_bytes(regular(runtime / name, 2_000_000))
    except BaseException as exc:
        failure, primary_exception = str(exc), exc
    finally:
        cleanup = []

        def attempt(name, action, fallback=None):
            try:
                return action()
            except BaseException as exc:
                cleanup.append(name + ": " + str(exc))
                return fallback

        attempt("relay-shutdown", relay.shutdown)
        attempt("relay-thread-join", lambda: thread.join(timeout=5))
        closed = attempt("relay-owned-close", relay.close_owned)
        workers, sockets = closed if closed is not None else (None, None)
        cleanup.extend(getattr(relay, "close_failures", []))
        attempt("relay-socket-unlink", lambda: (runtime / "relay.sock").unlink())
        primary = failure
        if cleanup and failure is None:
            failure = "Inner cleanup failed: " + "; ".join(cleanup)
        ownership = {
            "request": request,
            "response": response,
            "failure": failure,
            "inner_thread_alive": thread.is_alive(),
            "inner_socket_remaining": (runtime / "relay.sock").exists(),
            "inner_workers_remaining": workers,
            "inner_connections_remaining": sockets,
        }
        publication = EvidencePublisher("INNER", primary_exception, cleanup)
        publication.attempt(
            output / "inner-diagnostics.json",
            {"failure": primary, "cleanup_failures": cleanup, "resources": ownership},
        )
        if publication.errors:
            ownership["failure"] = publication.message()
        publication.attempt(output / "bridge.json", ownership)
    publication.finish(output / "inner-failed-response.json")
    require(
        failure is None
        and not cleanup
        and not thread.is_alive()
        and workers == sockets == 0,
        "Inner relay phase failed: " + str(failure),
    )
    return response["ui"], ownership


class API:
    def __init__(self, base):
        parsed = urlsplit(base)
        require(
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and parsed.port
            and not parsed.username
            and not parsed.password
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment,
            "Only the owned numeric loopback listener is supported.",
        )
        self.port, self.token, self.rows = parsed.port, "", []

    def request(self, name, path, body=None, capabilities=()):
        require(
            path.startswith("/api/") and ".." not in path, "Use only local API paths."
        )
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        raw = b"" if body is None else encoded(body).encode("utf-8")
        method = "GET" if body is None else "POST"
        try:
            connection.putrequest(method, path)
            connection.putheader("X-Sinter-Token", self.token)
            for capability in capabilities:
                connection.putheader("X-Sinter-Casebook-Schema", capability)
            if body is not None:
                connection.putheader("Content-Type", "application/json")
                connection.putheader("Content-Length", str(len(raw)))
            connection.endheaders(raw or None)
            response = connection.getresponse()
            content = response.read(2_000_001)
            require(len(content) <= 2_000_000, "Local response exceeds its bound.")
            value = json.loads(content)
            self.rows.append(
                {
                    "name": name,
                    "method": method,
                    "path": path,
                    "capabilities": list(capabilities),
                    "body": blob(raw),
                    "status": response.status,
                    "response": blob(content),
                }
            )
            return response.status, value
        finally:
            connection.close()

    def expect(self, name, path, body=None, capabilities=(), status=200):
        code, value = self.request(name, path, body, capabilities)
        require(code == status, "Unexpected actual local response: " + name)
        if code == 400:
            require(
                type(value) is dict
                and type(value.get("error")) is str
                and value["error"],
                "Refusal lacks its actual explanation.",
            )
        return value


def inspect(api, expected):
    session = api.expect("session", "/api/session")
    api.token = session["token"]
    api.expect("settings", "/api/settings")
    api.expect("campaign", "/api/campaigns/" + expected["campaign"]["id"])
    # The historical v1 project has the same ID as its later scoped revision;
    # its immutable backup and saved report are history, not a second live row.
    books = (
        [("plain", expected["plain_casebook"]), ("scoped", expected["scoped_casebook"])]
        if "scoped_casebook" in expected
        else [("plain", expected["casebook"])]
    )
    for name, book in books:
        api.expect(
            name,
            "/api/casebooks/" + book["id"],
            capabilities=(SCOPED,) if book["document"].get("schema") == SCOPED else (),
        )
    reports = (
        [(row["report_id"], row["stored_report"]) for row in expected["raw_reports"]]
        if "raw_reports" in expected
        else [(expected["report_id"], expected["report"])]
    )
    for index, (identifier, _report) in enumerate(reports):
        api.expect("report-" + str(index), "/api/reports/" + identifier)
    api.expect("reports", "/api/reports")
    api.expect("watches", "/api/watches")
    api.expect("jobs", "/api/jobs")
    return session


def protocol(api, expected):
    """An installed current E/RC4 reader gets no capability by default."""
    before = api.expect("jobs-before", "/api/jobs")
    if "scoped_casebook" in expected:
        book = expected["scoped_casebook"]
        path = "/api/casebooks/" + book["id"]
        work = {"id": book["id"], "revision": book["revision"]}
        for name, capabilities in (
            ("missing", ()),
            ("wrong", ("sinter-casebook/v1",)),
            ("duplicate", (SCOPED, SCOPED)),
        ):
            api.expect("read-" + name, path, capabilities=capabilities, status=400)
        api.expect("read-capable", path, capabilities=(SCOPED,))
        api.expect(
            "validate-missing",
            "/api/casebooks/validate",
            {"document": book["document"]},
            status=400,
        )
        api.expect(
            "validate-capable",
            "/api/casebooks/validate",
            {"document": book["document"]},
            capabilities=(SCOPED,),
        )
        broad = {
            key: value
            for key, value in book["document"].items()
            if key not in {"question_scopes", "fingerprint"}
        }
        broad["schema"] = "sinter-casebook/v1"
        api.expect(
            "old-reader-save",
            "/api/casebooks/save",
            {**work, "document": broad},
            status=400,
        )
        for name, route, capability in (
            ("build-missing", "build", ()),
            ("draft-missing", "draft", ()),
            ("draft-without-consent", "draft", (SCOPED,)),
        ):
            api.expect(
                name,
                "/api/casebooks/" + route,
                work,
                capabilities=capability,
                status=400,
            )
        require(
            equal(api.expect("jobs-after-refusals", "/api/jobs"), before),
            "Refused requests queued work.",
        )
        queued = api.expect(
            "source-build",
            "/api/casebooks/build",
            work,
            capabilities=(SCOPED,),
            status=202,
        )
    else:
        book = expected["casebook"]
        queued = api.expect(
            "source-build",
            "/api/casebooks/build",
            {"id": book["id"], "revision": book["revision"]},
            status=202,
        )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = api.expect("source-job", "/api/jobs/" + queued["id"])
        if job["status"] in {"done", "failed", "cancelled"}:
            break
        time.sleep(0.05)
    else:
        raise ValueError("Source-only installed work did not finish in twenty seconds.")
    require(job["status"] == "done", "Source-only installed work failed.")
    api.expect(
        "read-after-protocol",
        "/api/casebooks/" + book["id"],
        capabilities=(SCOPED,) if "scoped_casebook" in expected else (),
    )


def ui(base, expected, output, chromium, version):
    from playwright.sync_api import expect, sync_playwright

    errors, external, images, visible = [], [], [], {}
    output.mkdir(parents=True, exist_ok=True)
    manager = sync_playwright()
    browser, context, primary, cleanup = None, None, None, []
    primary_exception = None
    resources = {
        "context_pages_after_close": None,
        "browser_connected_after_close": None,
    }
    try:
        playwright = manager.__enter__()
        browser = playwright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(viewport={"width": 1280, "height": 960})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def guard(route):
            if urlsplit(route.request.url).netloc != urlsplit(base).netloc:
                external.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        context.route("**/*", guard)
        page.goto(base + "/#library", wait_until="networkidle", timeout=20_000)
        reports = (
            [row["stored_report"] for row in expected["raw_reports"]]
            if "raw_reports" in expected
            else [expected["report"]]
        )
        identifiers = (
            [row["report_id"] for row in expected["raw_reports"]]
            if "raw_reports" in expected
            else [expected["report_id"]]
        )
        listing = page.request.get(base + "/api/reports").json()["reports"]
        visible["report_bodies"] = []
        for index, report in enumerate(reports):
            article = page.locator("article.card").filter(
                has=page.get_by_role("heading", name=report["title"], exact=True)
            )
            same_title = [
                row["id"] for row in listing if row["title"] == report["title"]
            ]
            article = article.nth(same_title.index(identifiers[index]))
            with page.expect_response(
                lambda response: (
                    urlsplit(response.url).path == "/api/reports/" + identifiers[index]
                ),
                timeout=20_000,
            ) as opened:
                article.get_by_role("button", name="Open draft", exact=True).click()
            require(opened.value.status == 200, "Saved report reader failed.")
            paper = page.locator(".document-paper")
            expect(paper).to_be_visible()
            original = report.get("document_edits", {}).get(
                "markdown", report.get("document_markdown", report.get("markdown", ""))
            )
            page.wait_for_function(
                r"""segments => {
                    const paper = document.querySelector('.document-paper');
                    if (!paper) return false;
                    const text = paper.innerText.replace(/\s+/g, ' ').trim();
                    let cursor = 0;
                    for (const segment of segments) {
                        let at = text.indexOf(segment, cursor);
                        while (at !== -1 &&
                            ((at > 0 && text[at - 1] !== ' ') ||
                             (at + segment.length < text.length &&
                              text[at + segment.length] !== ' '))) {
                            at = text.indexOf(segment, at + 1);
                        }
                        if (at === -1) return false;
                        cursor = at + segment.length;
                    }
                    return segments.length > 0;
                }""",
                arg=rendered_words(original),
                timeout=5_000,
            )
            visible["report-" + str(index)] = page.locator("#content").inner_text()
            visible["report_bodies"].append(
                {
                    "report_id": identifiers[index],
                    "text": paper.inner_text(),
                    "visible": paper.is_visible(),
                }
            )
            path = output / ("report-" + str(index) + ".png")
            page.screenshot(path=str(path), full_page=True)
            images.append(
                {
                    "name": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": sha(regular(path)),
                }
            )
        page.goto(base + "/#casebooks", wait_until="networkidle")
        book = expected.get("scoped_casebook", expected.get("casebook"))
        if book:
            # The saved-project row has one Open project button and exact title.
            button = page.locator("article.casebook-tile").filter(
                has=page.get_by_text(book["document"]["title"], exact=True)
            )
            button.get_by_role("button", name="Open project", exact=True).click()
            expect(page.get_by_label("Project name", exact=True)).to_have_value(
                book["document"]["title"]
            )
            visible["casebook"] = page.locator("#content").inner_text()
            if "scoped_casebook" in expected:
                # The control details are opened explicitly before reading values.
                page.locator("details").evaluate_all(
                    "rows => rows.forEach(row => { row.open = true; })"
                )
                page.locator("[data-question-scope-index]").evaluate_all(
                    "rows => rows.forEach(row => { row.open = true; })"
                )
                visible["scope_modes"] = [
                    page.get_by_label(
                        "Sources for question " + str(i), exact=True
                    ).input_value()
                    for i in (1, 2, 3)
                ]
                visible["scope_checks"] = []
                for question in (0, 1):
                    for source in book["document"]["documents"]:
                        control = page.get_by_role(
                            "checkbox",
                            name=f"Question {question + 1} source: "
                            + source["title"]
                            + " — "
                            + source["id"],
                            exact=True,
                        )
                        visible["scope_checks"].append(
                            {
                                "question_index": question,
                                "source_id": source["id"],
                                "checked": control.is_checked(),
                                "visible": control.is_visible(),
                            }
                        )
        page.goto(base + "/#campaigns", wait_until="networkidle")
        if version == "0.5.3":
            page.locator("details.campaign-transfers").evaluate(
                "row => { row.open = true; }"
            )
            page.get_by_role(
                "button",
                name="Open " + expected["campaign"]["document"]["title"],
                exact=True,
            ).click()
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(
            expected["campaign"]["document"]["title"]
        )
        # Open the review details before observing visible warnings.
        page.locator("details").evaluate_all(
            "rows => rows.forEach(row => { row.open = true; })"
        )
        visible["campaign"] = page.locator("#content").inner_text()
        visible["opportunity_facts"] = []
        facts = page.locator(".campaign-focus .campaign-opportunity-facts > div")
        for index in range(facts.count()):
            row = facts.nth(index)
            label, value = row.locator("dt"), row.locator("dd")
            visible["opportunity_facts"].append(
                {
                    "label": label.inner_text(),
                    "text": value.inner_text(),
                    "visible": row.is_visible()
                    and label.is_visible()
                    and value.is_visible(),
                }
            )
        path = output / "campaign.png"
        page.screenshot(path=str(path), full_page=True)
        images.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha(regular(path)),
            }
        )
        actions = page.get_by_role("tab", name="Next actions", exact=True)
        if actions.count():
            actions.click()
            page.locator("details").evaluate_all(
                "rows => rows.forEach(row => { row.open = true; })"
            )
            visible["actions"] = page.locator("#content").inner_text()
            visible["owner_types"] = page.get_by_label(
                "Owner type", exact=True
            ).evaluate_all("rows => rows.map(row => row.value)")
            visible["owner_acceptance"] = page.get_by_role(
                "checkbox", name="This person has accepted this action", exact=True
            ).evaluate_all("rows => rows.map(row => row.checked)")
            visible["owner_semantics"] = []
            visible["owner_semantics_capability"] = (
                "legacy fields only"
                if version == "0.5.3"
                else "conservative owner fields"
            )
            for index, _row in enumerate(expected["campaign"]["document"]["actions"]):
                if version == "0.5.3":
                    break
                row = page.locator(f'.campaign-action[data-action-index="{index}"]')
                task = row.locator(".campaign-action-summary-task")
                summary = row.locator(".campaign-action-summary-meta")
                detail = row.locator("small.campaign-action-meta[data-state]")
                date = row.locator(".campaign-action-date-status")
                control = row.get_by_label("Owner type", exact=True)
                visible["owner_semantics"].append(
                    {
                        "index": index,
                        "task": task.inner_text(),
                        "summary": summary.inner_text(),
                        "detail": detail.inner_text(),
                        "owner_type_label": control.locator(
                            "option:checked"
                        ).inner_text(),
                        "date_text": date.inner_text(),
                        "visible": all(
                            item.is_visible()
                            for item in (row, task, summary, detail, date, control)
                        ),
                    }
                )
        path = output / "actions.png"
        page.screenshot(path=str(path), full_page=True)
        images.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha(regular(path)),
            }
        )
        require(
            not errors and not external,
            "Browser errors or external requests were observed.",
        )
    except BaseException as exc:
        primary, primary_exception = str(exc), exc
    finally:

        def attempt(name, action, fallback=None):
            try:
                return action()
            except BaseException as exc:
                cleanup.append(name + ": " + str(exc))
                return fallback

        if context is not None:
            attempt("context-close", context.close)
        if browser is not None:
            attempt("browser-close", browser.close)
        resources = {
            "context_pages_after_close": attempt(
                "context-pages", lambda: len(context.pages)
            )
            if context
            else 0,
            "browser_connected_after_close": attempt(
                "browser-connected", lambda: browser.is_connected()
            )
            if browser
            else False,
        }
        attempt("playwright-close", lambda: manager.__exit__(None, None, None))
        publication = EvidencePublisher("UI", primary_exception, cleanup)
        publication.attempt(
            output / "ui-diagnostics.json",
            {"failure": primary, "cleanup_failures": cleanup, "resources": resources},
        )
    publication.finish(output / "ui-failed-response.json")
    return {
        "visible": visible,
        "screenshots": images,
        "page_errors": errors,
        "external_requests": external,
        "resources": resources,
    }


def group_alive(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def run(
    prefix,
    version,
    workspace,
    expected,
    output,
    chromium,
    *,
    protocol_mode=False,
    binary_sha=None,
    environment_extra=None,
    runtime=None,
    phase=None,
):
    """Use installed argv in production and explicit source prefixes in the seam."""
    output.mkdir(parents=True)
    home = output / "home"
    home.mkdir()
    captured = output / "opened-url.txt"
    opener = output / "capture.py"
    opener.write_text(
        "import pathlib,sys\n"
        "pathlib.Path(sys.argv[1]).write_text(sys.argv[-1],encoding='utf-8')\n",
        encoding="utf-8",
        newline="\n",
    )
    environment = {
        "PATH": os.defpath,
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "TZ": "UTC",
        "TMPDIR": str(home),
        "SINTER_DATA_DIR": str(workspace),
        "PYTHONDONTWRITEBYTECODE": "1",
        "BROWSER": shlex.join([str(sys.executable), str(opener), str(captured), "%s"]),
    }
    if environment_extra:
        environment.update(environment_extra)
    argv = browser_launch_command(prefix, version)
    version_process = subprocess.Popen(
        [*prefix, "--version"],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        version_stdout, version_stderr = version_process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        version_process.kill()
        version_stdout, version_stderr = version_process.communicate(timeout=2)
    version_row = {
        "argv": [*prefix, "--version"],
        "pid": version_process.pid,
        "exit_code": version_process.returncode,
        "reaped": True,
        "stdout": blob(version_stdout),
        "stderr": blob(version_stderr),
    }
    (output / "version-command.json").write_text(
        encoded(version_row) + "\n", encoding="utf-8", newline="\n"
    )
    require(
        version_process.returncode == 0
        and version_stdout == (version + "\n").encode()
        and version_stderr == b"",
        "Actual binary --version differs.",
    )
    stdout, stderr = output / "stdout", output / "stderr"
    api, process, failure, forced, observations, visual = (
        None,
        None,
        None,
        False,
        [],
        None,
    )
    bridge, primary_exception = None, None
    with stdout.open("wb") as out, stderr.open("wb") as err:
        process = subprocess.Popen(
            argv,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 20
            while not captured.exists() and time.monotonic() < deadline:
                require(
                    process.poll() is None,
                    "Application exited before opening its listener.",
                )
                time.sleep(0.02)
            require(
                captured.exists(), "Application did not open within twenty seconds."
            )
            base = captured.read_text(encoding="utf-8").strip()
            api = API(base)
            session = inspect(api, expected)
            require(
                session["version"] == version and session["desktop"] is True,
                "Actual session version or desktop ownership differs.",
            )
            if protocol_mode:
                protocol(api, expected)
            if runtime is None:
                visual = ui(base, expected, output, chromium, version)
            else:
                visual, bridge = hosted_ui(
                    api,
                    expected,
                    output,
                    runtime,
                    phase,
                    version,
                    process.pid,
                    workspace,
                    binary_sha,
                )
        except BaseException as exc:
            failure, primary_exception = str(exc), exc
        finally:
            if api is not None and process.poll() is None:
                try:
                    api.expect("quit", "/api/desktop/quit", {})
                    process.wait(timeout=5)
                except BaseException as exc:
                    if failure is None:
                        failure, primary_exception = str(exc), exc
            if process.poll() is None:
                forced = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
            if group_alive(process.pid):
                forced = True
                os.killpg(process.pid, signal.SIGKILL)
                deadline = time.monotonic() + 2
                while group_alive(process.pid) and time.monotonic() < deadline:
                    time.sleep(0.02)
            observations = api.rows if api else []
    closed = False
    if api:
        with socket.socket() as listener:
            listener.settimeout(0.2)
            closed = listener.connect_ex(("127.0.0.1", api.port)) != 0
    row = {
        "argv": argv,
        "workspace": str(workspace),
        "binary_sha256": binary_sha,
        "pid": process.pid,
        "exit_code": process.returncode,
        "reaped": True,
        "forced_cleanup": forced,
        "group_remaining": group_alive(process.pid),
        "listener_closed": closed,
        "stdout": blob(regular(stdout)),
        "stderr": blob(regular(stderr)),
    }
    result = {
        "process": row,
        "api": observations,
        "ui": visual,
        "failure": failure,
        "version_command": version_row,
        "bridge": bridge,
    }
    publication = EvidencePublisher("PROBE", primary_exception, [])
    publication.attempt(output / "probe.json", result)
    publication.finish(output / "probe-failed-response.json")
    require(
        failure is None and not forced and closed and process.returncode == 0,
        "Owned application probe failed: " + str(failure),
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--chromium", type=Path, required=True)
    parser.add_argument("--browser-tmp", type=Path, required=True)
    parser.add_argument(
        "--phase",
        choices=[
            "prior",
            "prior-protocol",
            "candidate",
            "candidate-protocol",
            "candidate-cold",
        ],
        required=True,
    )
    args = parser.parse_args(argv)
    try:
        collect(args.runtime, args.chromium, args.phase, args.browser_tmp)
    except EvidenceFailure as exc:
        # The parent retains stderr when evidence files cannot be written.
        emit_failure(exc)
        raise SystemExit(1) from exc
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, "Owned replacement host collector failed: " + str(exc) + "\n")
    print("Owned replacement host phase retained and closed.")


if __name__ == "__main__":
    main()
