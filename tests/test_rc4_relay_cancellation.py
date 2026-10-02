"""Actual owned loopback cancellation controls; no app, UI, or provider calls."""

import errno
import json
import socket
import socketserver
import tempfile
import threading
import time

import pytest

from tools import installed_workflow_browser as browser
from tools import rc4_replacement_probe as probe
from tools.installed_workflow_browser import RelayClosed, receive_request


@pytest.mark.parametrize("scope", ["idle", "header", "body"])
def test_actual_request_stops_when_shutdown_does_not_wake_reader(
    tmp_path, monkeypatch, scope
):
    """Explicit source fault seam for the observed Windows shutdown behavior."""
    actual_shutdown = socket.socket.shutdown
    attempts = []

    def ineffective_shutdown(channel, how):
        attempts.append((channel.fileno(), how))
        # Deliberately leave the real socket open. This is not Windows proof.
        return None

    monkeypatch.setattr(socket.socket, "shutdown", ineffective_shutdown)
    relay = probe.HostRelay(tmp_path)
    actual_receive = relay.receive_owned
    body_entered, headers_received = threading.Event(), threading.Event()

    def observe_receive(channel, size):
        if size == 100 - len(b"first-incomplete-body"):
            body_entered.set()
        result = actual_receive(channel, size)
        if result:
            headers_received.set()
        return result

    monkeypatch.setattr(relay, "receive_owned", observe_receive)
    server = threading.Thread(target=relay.serve_forever)
    server.start()
    client = socket.create_connection(relay.server_address, timeout=1)
    try:
        if scope == "body":
            (tmp_path / "state.json").write_text(json.dumps({"port": 1}))
            partial = (
                f"POST /api/state HTTP/1.1\r\nHost: 127.0.0.1:{relay.server_address[1]}\r\n"
                "Content-Length: 100\r\n\r\nfirst-incomplete-body"
            ).encode()
        else:
            partial = b"" if scope == "idle" else b"GET /api/state HTTP/1.1\r\n"
        if partial:
            client.sendall(partial)
        deadline = time.monotonic() + 2
        while relay.idle() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not relay.idle()
        if scope == "header":
            assert headers_received.wait(1), (
                "Partial headers must actually be consumed."
            )
        if scope == "body":
            assert body_entered.wait(1), (
                "The actual worker must enter the incomplete body read"
            )
        relay.shutdown()
        server.join(timeout=1)
        started = time.monotonic()
        assert relay.close_owned() == (0, 0)
        assert time.monotonic() - started < 2
        assert attempts and not server.is_alive() and relay.idle()
        assert relay.errors == (0 if scope == "idle" else 1)
        assert relay.model_requests == 0
        assert not relay.owned_sockets and not relay.owned_workers
        assert probe.closed_port(relay.server_address[1]) != 0
    finally:
        monkeypatch.setattr(socket.socket, "shutdown", actual_shutdown)
        client.close()
        if server.is_alive():
            relay.shutdown()
            server.join(timeout=1)
        relay.close_owned()


def test_owned_read_conserves_literal_bytes_and_original_timeout(tmp_path):
    relay = probe.HostRelay(tmp_path)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with socket.create_connection(listener.getsockname()) as sender:
            channel, _ = listener.accept()
            with channel:
                channel.settimeout(20)
                content = "café e\u0301 🐝".encode() + b"\x00\xff\r\n"
                sender.sendall(content)
                assert receive_request(relay, channel, len(content)) == content
                assert channel.gettimeout() == 20
                sender.shutdown(socket.SHUT_WR)
                assert receive_request(relay, channel, 1) == b""
    relay.close_owned()


def test_owned_read_timeout_does_not_become_cancellation(tmp_path):
    relay = probe.HostRelay(tmp_path)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with socket.create_connection(listener.getsockname()):
            channel, _ = listener.accept()
            with channel:
                channel.settimeout(0.25)
                started = time.monotonic()
                with pytest.raises(TimeoutError):
                    receive_request(relay, channel, 1)
                assert 0.2 <= time.monotonic() - started < 2
                assert not relay.requests_stopped.is_set()
    relay.close_owned()


def test_stopped_reader_refuses_before_network_io(tmp_path):
    relay = probe.HostRelay(tmp_path)
    assert relay.close_owned() == (0, 0)

    class UnreadableChannel:
        def gettimeout(self):
            return 20

        def recv(self, _):
            pytest.fail("Stopped request must not read or forward bytes")

        def fileno(self):
            pytest.fail("Stopped request must not select a socket")

    with pytest.raises(RelayClosed):
        receive_request(relay, UnreadableChannel(), 1)


def test_legacy_untracked_reader_keeps_direct_socket_contract():
    class Channel:
        def recv(self, size):
            assert size == 17
            return b"original-request-bytes"

    assert receive_request(object(), Channel(), 17) == b"original-request-bytes"


def test_readiness_stop_gap_cannot_start_a_blocking_receive(tmp_path, monkeypatch):
    """Preserve the independent real-socket failure seam, without closing its peer."""
    relay = probe.HostRelay(tmp_path)
    actual_select, actual_recv = probe.select.select, socket.socket.recv
    selected = set()
    before_receive, entered_after_stop = threading.Event(), threading.Event()
    modes = []

    def spurious_readability(readers, writers, errors, timeout=None):
        if len(readers) == 1:
            channel = readers[0]
            with relay.owned_lock:
                owned = channel in relay.owned_sockets
            if owned and channel not in selected:
                selected.add(channel)
                return list(readers), [], []
        return actual_select(readers, writers, errors, timeout)

    def stop_before_receive(channel, size, flags=0):
        if channel in selected and not before_receive.is_set():
            before_receive.set()
            assert relay.requests_stopped.wait(2)
            entered_after_stop.set()
            modes.append(channel.gettimeout())
        return actual_recv(channel, size, flags)

    monkeypatch.setattr(probe.select, "select", spurious_readability)
    monkeypatch.setattr(socket.socket, "recv", stop_before_receive)
    monkeypatch.setattr(socket.socket, "shutdown", lambda *_: None)
    server = threading.Thread(target=relay.serve_forever)
    server.start()
    client = socket.create_connection(relay.server_address, timeout=1)
    try:
        assert before_receive.wait(2)
        relay.shutdown()
        server.join(timeout=1)
        started = time.monotonic()
        assert relay.close_owned() == (0, 0)
        assert time.monotonic() - started < 2
        assert entered_after_stop.is_set() and modes == [0.0]
        assert not server.is_alive() and relay.idle()
        assert relay.errors == relay.model_requests == 0
    finally:
        monkeypatch.setattr(socket.socket, "recv", actual_recv)
        monkeypatch.setattr(probe.select, "select", actual_select)
        client.close()
        if server.is_alive():
            relay.shutdown()
            server.join(timeout=1)
        relay.close_owned()


@pytest.mark.parametrize("restore_failed", [False, True])
def test_genuine_read_failure_retains_identity_and_later_restore_error(
    tmp_path, monkeypatch, restore_failed
):
    relay = probe.HostRelay(tmp_path)
    first, later = OSError("actual-read-fault"), OSError("later-timeout-restore")
    observed = []

    class Channel:
        def gettimeout(self):
            return 20

        def setblocking(self, value):
            observed.append(("blocking", value))

        def recv(self, _):
            raise first

        def settimeout(self, value):
            observed.append(("timeout", value))
            if restore_failed:
                raise later

    monkeypatch.setattr(probe.select, "select", lambda readers, *_: (readers, [], []))
    try:
        with pytest.raises(OSError) as failed:
            receive_request(relay, Channel(), 1)
        assert failed.value is first
        assert observed == [("blocking", False), ("timeout", 20)]
        assert getattr(first, "relay_restoration_errors", ()) == (
            (later,) if restore_failed else ()
        )
    finally:
        relay.close_owned()


def test_stale_readiness_retries_with_original_timeout_and_bytes(tmp_path, monkeypatch):
    relay = probe.HostRelay(tmp_path)
    observed = []
    content = "original café e\u0301 🐝".encode() + b"\x00\xff"

    class Channel:
        reads = 0

        def gettimeout(self):
            return 20

        def setblocking(self, value):
            observed.append(("blocking", value))

        def settimeout(self, value):
            observed.append(("timeout", value))

        def recv(self, _):
            self.reads += 1
            if self.reads == 1:
                raise BlockingIOError("Explicit stale readiness")
            return content

    monkeypatch.setattr(probe.select, "select", lambda readers, *_: (readers, [], []))
    channel = Channel()
    try:
        assert receive_request(relay, channel, len(content)) == content
        assert channel.reads == 2
        assert observed == [("blocking", False), ("timeout", 20)] * 2
        assert not relay.requests_stopped.is_set()
    finally:
        relay.close_owned()


@pytest.mark.parametrize("late", ["data", "eof"])
def test_actual_receive_rejects_result_if_stop_occurs_during_read(
    tmp_path, monkeypatch, late
):
    relay = probe.HostRelay(tmp_path)
    actual_recv = socket.socket.recv
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with socket.create_connection(listener.getsockname()) as sender:
            channel, _ = listener.accept()
            with channel:
                channel.settimeout(20)
                if late == "data":
                    sender.sendall(b"complete-but-cancelled\x00\xff")
                else:
                    sender.shutdown(socket.SHUT_WR)
                observed = []

                def stop_during_read(reader, size, flags=0):
                    assert reader is channel
                    relay.requests_stopped.set()
                    result = actual_recv(reader, size, flags)
                    observed.append((reader.gettimeout(), result))
                    return result

                monkeypatch.setattr(socket.socket, "recv", stop_during_read)
                with pytest.raises(RelayClosed):
                    relay.receive_owned(channel, 65_536)
                assert channel.gettimeout() == 20
                assert observed == [
                    (0.0, b"complete-but-cancelled\x00\xff" if late == "data" else b"")
                ]
    assert relay.close_owned() == (0, 0)


def test_stale_readiness_with_restore_failure_is_not_silently_retried(
    tmp_path, monkeypatch
):
    relay = probe.HostRelay(tmp_path)
    first, later = BlockingIOError("stale-readiness"), KeyboardInterrupt()

    class Channel:
        def gettimeout(self):
            return 20

        def setblocking(self, _):
            pass

        def recv(self, _):
            raise first

        def settimeout(self, _):
            raise later

    monkeypatch.setattr(probe.select, "select", lambda readers, *_: (readers, [], []))
    try:
        with pytest.raises(BlockingIOError) as failed:
            relay.receive_owned(Channel(), 1)
        assert failed.value is first
        assert first.relay_restoration_errors == (later,)
    finally:
        relay.close_owned()


def test_partial_send_preserves_bytes_one_budget_and_original_timeout(
    tmp_path, monkeypatch
):
    relay = probe.HostRelay(tmp_path)
    content = "literal café e\u0301 🐝".encode() + b"\x00\xff"
    sent, modes = bytearray(), []

    class Channel:
        timeout = 20

        def gettimeout(self):
            return self.timeout

        def setblocking(self, _):
            self.timeout = 0.0

        def settimeout(self, value):
            self.timeout = value

        def send(self, data):
            modes.append(self.timeout)
            part = bytes(data[:3])
            sent.extend(part)
            return len(part)

    monkeypatch.setattr(
        probe.select, "select", lambda readers, writers, *_: (readers, writers, [])
    )
    channel = Channel()
    try:
        relay.send_owned(channel, content)
        assert bytes(sent) == content and len(modes) > 1 and set(modes) == {0.0}
        assert channel.gettimeout() == 20
    finally:
        relay.close_owned()


def test_actual_backpressured_send_stops_without_peer_read_or_shutdown(
    tmp_path, monkeypatch
):
    relay = probe.HostRelay(tmp_path)
    actual_send = socket.socket.send
    first_send, outcomes, modes = threading.Event(), [], []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with socket.create_connection(listener.getsockname()) as unread_peer:
            channel, _ = listener.accept()
            with channel:
                channel.settimeout(20)
                channel.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)

                def observe_send(writer, data, flags=0):
                    assert writer is channel
                    modes.append(writer.gettimeout())
                    sent = actual_send(writer, data, flags)
                    first_send.set()
                    return sent

                def sending():
                    try:
                        relay.send_owned(channel, b"literal bytes\x00\xff" * 524_288)
                    except BaseException as error:
                        outcomes.append(error)

                monkeypatch.setattr(socket.socket, "send", observe_send)
                worker = threading.Thread(target=sending)
                worker.start()
                try:
                    assert first_send.wait(2)
                    relay.requests_stopped.set()
                    worker.join(2)
                    assert not worker.is_alive()
                    assert len(outcomes) == 1 and isinstance(outcomes[0], RelayClosed)
                    assert channel.gettimeout() == 20 and set(modes) == {0.0}
                    assert unread_peer.fileno() >= 0
                finally:
                    relay.requests_stopped.set()
                    worker.join(2)
    relay.close_owned()


def test_actual_fixed_loopback_connect_and_send_conserve_bytes(tmp_path):
    relay = probe.HostRelay(tmp_path)
    content = "fixed target café e\u0301 🐝".encode() + b"\x00\xff\r\n"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with relay.open_connection_owned(listener.getsockname()) as channel:
            assert channel.gettimeout() == 20
            peer, _ = listener.accept()
            with peer:
                peer.settimeout(2)
                relay.send_owned(channel, content)
                assert peer.recv(65_536) == content
                assert channel.gettimeout() == 20
    relay.close_owned()


def test_connect_stop_during_completion_cannot_admit_connected_result(
    tmp_path, monkeypatch
):
    relay = probe.HostRelay(tmp_path)

    class Channel:
        timeout = 20

        def gettimeout(self):
            return self.timeout

        def setblocking(self, _):
            self.timeout = 0.0

        def settimeout(self, value):
            self.timeout = value

        def connect(self, address):
            assert address == ("127.0.0.1", 1234) and self.timeout == 0.0
            raise BlockingIOError(errno.EINPROGRESS, "owned pending TCP connect")

        def getsockopt(self, level, option):
            assert (level, option) == (socket.SOL_SOCKET, socket.SO_ERROR)
            relay.requests_stopped.set()
            return 0

    monkeypatch.setattr(
        probe.select, "select", lambda readers, writers, *_: (readers, writers, [])
    )
    channel = Channel()
    try:
        with pytest.raises(RelayClosed):
            relay.connect_owned(channel, ("127.0.0.1", 1234))
        assert channel.gettimeout() == 20
    finally:
        relay.close_owned()


@pytest.mark.parametrize("kind", ["host", "inner"])
def test_actual_upstream_wait_cancels_and_closes_all_owned_channels(
    tmp_path, monkeypatch, kind
):
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("Actual Unix relay sockets are unavailable on this platform.")
    if kind == "inner" and not hasattr(socketserver, "ThreadingUnixStreamServer"):
        pytest.skip("The actual threaded Unix relay server is unavailable.")
    with tempfile.TemporaryDirectory(prefix="c-") as directory:
        from pathlib import Path

        runtime = Path(directory)
        if kind == "host":
            (runtime / "state.json").write_text(json.dumps({"port": 1234}))
            sink = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sink.bind(str(runtime / "relay.sock"))
            relay = probe.HostRelay(runtime)
        else:
            sink = socket.socket()
            sink.bind(("127.0.0.1", 0))
            relay = probe.InstalledRelay(runtime)
            relay.port = sink.getsockname()[1]
        sink.listen()
        sink.settimeout(3)
        forwarded, release_sink, response_wait = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        upstream, records, errors = [], [], []
        actual_connect = relay.connect_owned
        actual_receive = relay.receive_owned

        def connect(channel, address):
            actual_connect(channel, address)
            upstream.append(channel)

        def receive(channel, size):
            if channel in upstream:
                response_wait.set()
            return actual_receive(channel, size)

        def inert_sink():
            try:
                peer, _ = sink.accept()
                with peer:
                    peer.settimeout(3)
                    received = bytearray()
                    while part := peer.recv(4096):
                        received.extend(part)
                    records.append(bytes(received))
                    forwarded.set()
                    assert release_sink.wait(10)
            except BaseException as error:
                errors.append(error)

        monkeypatch.setattr(relay, "connect_owned", connect)
        monkeypatch.setattr(relay, "receive_owned", receive)
        sink_thread = threading.Thread(target=inert_sink)
        server = threading.Thread(target=relay.serve_forever)
        sink_thread.start()
        server.start()
        if kind == "host":
            client = socket.create_connection(relay.server_address, timeout=2)
            request = (
                f"GET /api/state HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{relay.server_address[1]}\r\n\r\n"
            ).encode()
        else:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(2)
            client.connect(str(runtime / "relay.sock"))
            request = b"GET /api/state HTTP/1.1\r\nHost: 127.0.0.1:1234\r\n\r\n"
        try:
            client.sendall(request)
            client.shutdown(socket.SHUT_WR)
            assert forwarded.wait(2) and response_wait.wait(2)
            assert records and records[0].endswith(b"\r\n\r\n")
            relay.shutdown()
            server.join(1)
            started = time.monotonic()
            assert relay.close_owned() == (0, 0)
            assert time.monotonic() - started < 2
            assert upstream and all(channel.fileno() == -1 for channel in upstream)
            assert not server.is_alive() and not errors
            assert not release_sink.is_set() and sink_thread.is_alive()
        finally:
            release_sink.set()
            sink_thread.join(3)
            client.close()
            sink.close()
            if server.is_alive():
                relay.shutdown()
                server.join(1)
            assert relay.close_owned() == (0, 0)
            assert not sink_thread.is_alive()


def test_legacy_untracked_connect_send_and_construction_contract(monkeypatch):
    calls = []

    class Channel:
        def connect(self, address):
            calls.append(("connect", address))

        def sendall(self, data):
            calls.append(("sendall", data))

    channel = Channel()
    server = object()
    browser.connect_channel(server, channel, "literal-fixed-socket")
    browser.send_data(server, channel, b"literal bytes\x00\xff")

    def create(address, timeout):
        calls.append(("create_connection", address, timeout))
        return channel

    monkeypatch.setattr(browser.socket, "create_connection", create)
    assert browser.open_connection(server, ("127.0.0.1", 1234)) is channel
    assert calls == [
        ("connect", "literal-fixed-socket"),
        ("sendall", b"literal bytes\x00\xff"),
        ("create_connection", ("127.0.0.1", 1234), 20),
    ]


def test_actual_backpressured_send_expires_original_operation_budget(tmp_path):
    relay = probe.HostRelay(tmp_path)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with socket.create_connection(listener.getsockname()):
            channel, _ = listener.accept()
            with channel:
                channel.settimeout(0.25)
                channel.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
                started = time.monotonic()
                with pytest.raises(TimeoutError):
                    relay.send_owned(channel, b"literal bytes\x00\xff" * 524_288)
                assert 0.2 <= time.monotonic() - started < 2
                assert channel.gettimeout() == 0.25
                assert not relay.requests_stopped.is_set()
    relay.close_owned()


def test_actual_tracked_tcp_unix_tcp_preserves_raw_request_and_response():
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("Actual Unix relay sockets are unavailable on this platform.")
    if not hasattr(socketserver, "ThreadingUnixStreamServer"):
        pytest.skip("The actual threaded Unix relay server is unavailable.")
    body = "original NOT approved café e\u0301 🐝".encode() + b"\x00\xff"
    response = b"HTTP/1.0 200 OK\r\nContent-Length: 8\r\n\r\n\x00exact\r\n"
    received = []

    class Endpoint(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            content = bytearray()
            while chunk := self.request.recv(4096):
                content.extend(chunk)
            received.append(bytes(content))
            self.request.sendall(response)

    with tempfile.TemporaryDirectory(prefix="c-") as directory:
        from pathlib import Path

        runtime = Path(directory)
        endpoint = socketserver.TCPServer(("127.0.0.1", 0), Endpoint)
        inner = probe.InstalledRelay(runtime)
        inner.port = endpoint.server_address[1]
        (runtime / "state.json").write_text(json.dumps({"port": inner.port}))
        outer = probe.HostRelay(runtime)
        servers = (endpoint, inner, outer)
        workers = [threading.Thread(target=server.serve_forever) for server in servers]
        for worker in workers:
            worker.start()
        address = f"127.0.0.1:{outer.server_address[1]}"
        request = (
            f"POST /api/state HTTP/1.1\r\nHost: {address}\r\n"
            f"Origin: http://{address}\r\nContent-Length: {len(body)}\r\n"
            "X-Sinter-Token: inert-source-fixture\r\n\r\n"
        ).encode() + body
        try:
            with socket.create_connection(outer.server_address, timeout=2) as client:
                client.sendall(request)
                client.shutdown(socket.SHUT_WR)
                actual = bytearray()
                while chunk := client.recv(4096):
                    actual.extend(chunk)
            assert bytes(actual) == response
            expected = request.replace(
                f"Host: {address}".encode(), f"Host: 127.0.0.1:{inner.port}".encode()
            ).replace(
                f"Origin: http://{address}".encode(),
                f"Origin: http://127.0.0.1:{inner.port}".encode(),
            )
            assert received == [expected]
            assert outer.errors == outer.model_requests == 0
        finally:
            for server, worker in zip(reversed(servers), reversed(workers)):
                server.shutdown()
                if isinstance(server, probe.TrackedRequests):
                    assert server.close_owned() == (0, 0)
                else:
                    server.server_close()
                worker.join(2)
        assert not any(worker.is_alive() for worker in workers)


def test_connection_setup_fault_keeps_first_error_if_close_is_interrupted(
    tmp_path, monkeypatch
):
    relay = probe.HostRelay(tmp_path)
    first, later = OSError("setup-fault"), KeyboardInterrupt()

    class Channel:
        def settimeout(self, _):
            raise first

        def close(self):
            raise later

    monkeypatch.setattr(probe.socket, "socket", lambda *_: Channel())
    try:
        with pytest.raises(OSError) as failed:
            relay.open_connection_owned(("127.0.0.1", 1234))
        assert failed.value is first and first.relay_cleanup_errors == (later,)
    finally:
        relay.close_owned()


def test_late_readiness_does_not_admit_data_after_original_deadline(
    tmp_path, monkeypatch
):
    relay = probe.HostRelay(tmp_path)
    clock = [0.0]
    operations = []

    class Channel:
        def gettimeout(self):
            return 20

        def setblocking(self, value):
            operations.append(("blocking", value))

        def recv(self, _):
            operations.append(("recv",))
            return b"late data"

    def delayed_readiness(readers, *_):
        clock[0] = 20.0
        return readers, [], []

    monkeypatch.setattr(probe.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(probe.select, "select", delayed_readiness)
    try:
        with pytest.raises(TimeoutError):
            relay.receive_owned(Channel(), 1)
        assert operations == [] and not relay.requests_stopped.is_set()
    finally:
        # Restore the real clock before cleanup's independent five-second bound.
        monkeypatch.undo()
        relay.close_owned()


@pytest.mark.parametrize("restore_fault", [False, True])
def test_actual_default_unix_queue_keeps_first_connect_refusal(tmp_path, restore_fault):
    import sys
    from pathlib import Path

    if sys.platform != "linux" or not hasattr(socket, "AF_UNIX"):
        pytest.skip("This control qualifies Linux Unix-domain backlog semantics.")
    relay = probe.HostRelay(tmp_path)
    later = KeyboardInterrupt("owned timeout restoration interruption")
    failures, operations, owned = [], [], []

    class ObservedSocket(socket.socket):
        def connect(self, address):
            operations.append(("connect", self.gettimeout()))
            try:
                return super().connect(address)
            except OSError as first:
                failures.append(first)
                raise

        def settimeout(self, value):
            super().settimeout(value)
            if failures and restore_fault:
                raise later

        def getsockopt(self, *args):
            operations.append(("getsockopt", self.gettimeout()))
            return super().getsockopt(*args)

    try:
        with tempfile.TemporaryDirectory(prefix="q-") as directory:
            path = str(Path(directory) / "owned.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            owned.append(listener)
            listener.bind(path)
            listener.listen(browser.InnerRelay.request_queue_size)
            for _ in range(browser.InnerRelay.request_queue_size + 1):
                filler = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                owned.append(filler)
                filler.settimeout(20)
                filler.connect(path)
            legacy = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            owned.append(legacy)
            legacy.settimeout(20)
            with pytest.raises(BlockingIOError) as legacy_refusal:
                browser.connect_channel(object(), legacy, path)
            assert legacy_refusal.value.errno == errno.EAGAIN
            channel = ObservedSocket(socket.AF_UNIX, socket.SOCK_STREAM)
            owned.append(channel)
            channel.settimeout(20)
            with pytest.raises(BlockingIOError) as refusal:
                browser.connect_channel(relay, channel, path)
            assert len(failures) == 1 and refusal.value is failures[0]
            assert refusal.value.errno == legacy_refusal.value.errno
            assert channel.gettimeout() == 20
            assert operations == [("connect", 0.0)]
            assert getattr(refusal.value, "relay_restoration_errors", ()) == (
                (later,) if restore_fault else ()
            )
            with pytest.raises(OSError) as no_peer:
                channel.getpeername()
            assert no_peer.value.errno == errno.ENOTCONN
            assert not relay.requests_stopped.is_set()
    finally:
        for channel in reversed(owned):
            channel.close()
        assert relay.close_owned() == (0, 0)
        assert all(channel.fileno() == -1 for channel in owned)


def test_zero_socket_error_cannot_admit_an_unconnected_pending_channel(tmp_path):
    relay = probe.HostRelay(tmp_path)
    pending = BlockingIOError(errno.EINPROGRESS, "owned pending connect")
    no_peer = OSError(errno.ENOTCONN, "owned unconnected socket")

    class Channel:
        family = socket.AF_INET
        timeout = 20

        def gettimeout(self):
            return self.timeout

        def setblocking(self, value):
            assert value is False
            self.timeout = 0.0

        def settimeout(self, value):
            self.timeout = value

        def connect(self, address):
            assert address == ("127.0.0.1", 1234) and self.timeout == 0.0
            raise pending

        def getsockopt(self, level, option):
            assert (level, option) == (socket.SOL_SOCKET, socket.SO_ERROR)
            assert self.timeout == 0.0
            return 0

        def getpeername(self):
            assert self.timeout == 0.0
            raise no_peer

    channel = Channel()
    # Select is a fixed readiness seam; the refusal itself must survive unchanged.
    actual_ready = relay._ready
    relay._ready = lambda *_args, **_kwargs: None
    try:
        with pytest.raises(OSError) as refusal:
            relay.connect_owned(channel, ("127.0.0.1", 1234))
        assert refusal.value is no_peer and channel.gettimeout() == 20
    finally:
        relay._ready = actual_ready
        relay.close_owned()


def test_current_wrapper_preserves_actual_peek_flags_and_original_timeout(tmp_path):
    relay = probe.HostRelay(tmp_path)
    assert relay.closing is relay.requests_stopped
    literal = "real café e\u0301 🐝".encode() + b"\x00\xff"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with socket.create_connection(listener.getsockname(), timeout=20) as client:
            peer, _ = listener.accept()
            with peer:
                peer.settimeout(20)
                client.sendall(literal)
                wrapped = probe.ClosingRequest(peer, relay.closing, relay.receive_owned)
                assert wrapped.recv(len(literal), socket.MSG_PEEK) == literal
                assert peer.gettimeout() == 20
                assert wrapped.recv(len(literal)) == literal
                assert peer.gettimeout() == 20
                relay.requests_stopped.set()
                assert wrapped.recv(1) == b""
                assert peer.gettimeout() == 20
    assert relay.close_owned() == (0, 0)
