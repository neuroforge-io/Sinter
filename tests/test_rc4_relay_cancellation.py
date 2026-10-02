"""Actual owned loopback cancellation controls; no app, UI, or provider calls."""

import errno
import hashlib
import json
import socket
import socketserver
import sys
import tempfile
import threading
import time
from contextlib import contextmanager

import pytest

from tools import installed_workflow_browser as browser
from tools import rc4_replacement_probe as probe
from tools.installed_workflow_browser import RelayClosed, receive_request


@contextmanager
def _unread_tcp_pair():
    """Own all three sockets and conserve first failure through LIFO cleanup."""
    owned, attempts, cleanup_errors, primary = [], [], [], None
    observations = {"pair_cleanup_attempts": attempts}
    try:
        listener = socket.socket()
        owned.append(("listener", listener))
        peer = socket.socket()
        owned.append(("peer", peer))
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        peer.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        peer.settimeout(2)
        peer.connect(listener.getsockname())
        channel, _ = listener.accept()
        owned.append(("channel", channel))
        channel.settimeout(20)
        channel.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        observations.update(
            sender_buffer=channel.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF),
            unread_peer_buffer=peer.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF),
            peer_reads=0,
            peer_shutdowns=0,
        )
        assert observations["sender_buffer"] > 0
        assert observations["unread_peer_buffer"] > 0
        yield channel, peer, observations
    except BaseException as error:
        primary = error
        raise
    finally:
        for role, channel in reversed(owned):
            attempt = {"role": role, "fileno_before": channel.fileno()}
            attempts.append(attempt)
            try:
                channel.close()
            except BaseException as error:
                cleanup_errors.append(error)
                attempt["error"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                }
            finally:
                attempt["fileno_after"] = channel.fileno()
        if primary is not None:
            primary.source_pair_cleanup_errors = tuple(cleanup_errors)
            primary.source_pair_cleanup_attempts = tuple(attempts)
        elif cleanup_errors:
            first = cleanup_errors[0]
            first.source_pair_cleanup_errors = tuple(cleanup_errors[1:])
            first.source_pair_cleanup_attempts = tuple(attempts)
            raise first


def _observe_unread_peer(monkeypatch, peer, observations):
    """Count and refuse any peer read/shutdown before the tested outcome."""
    actual_recv = socket.socket.recv
    actual_recv_into = socket.socket.recv_into
    actual_shutdown = socket.socket.shutdown

    def recv(channel, *args, **kwargs):
        if channel is peer:
            observations["peer_reads"] += 1
            pytest.fail("Unread backpressure peer must not consume bytes")
        return actual_recv(channel, *args, **kwargs)

    def recv_into(channel, *args, **kwargs):
        if channel is peer:
            observations["peer_reads"] += 1
            pytest.fail("Unread backpressure peer must not consume bytes")
        return actual_recv_into(channel, *args, **kwargs)

    def shutdown(channel, *args, **kwargs):
        if channel is peer:
            observations["peer_shutdowns"] += 1
            pytest.fail("Unread backpressure peer must remain open")
        return actual_shutdown(channel, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "recv", recv)
    monkeypatch.setattr(socket.socket, "recv_into", recv_into)
    monkeypatch.setattr(socket.socket, "shutdown", shutdown)


def _require_pending_send(observations, payload_bytes):
    # A completed send, even followed by an unwritable socket, is not a pending
    # operation that can demonstrate cancellation of this payload.
    assert 0 < observations["sent_bytes"] < payload_bytes
    assert observations["unwritable"] is True
    assert observations["peer_reads"] == observations["peer_shutdowns"] == 0


def _fill_until_actual_backpressure(
    channel,
    observations,
    *,
    send_syscall=None,
    select_syscall=None,
    production_prefix=None,
    production_payload=None,
    requests_stopped=None,
):
    """Bound fixture bytes separately from the production payload under test."""
    active_context = any(
        value is not None
        for value in (production_prefix, production_payload, requests_stopped)
    )
    if active_context:
        assert all(
            value is not None
            for value in (production_prefix, production_payload, requests_stopped)
        )
        prefix = bytes(production_prefix)
        assert 0 < len(prefix) < len(production_payload)
        assert prefix == production_payload[: len(prefix)]
        assert observations["sent_bytes"] == len(prefix)
        assert observations["peer_reads"] == observations["peer_shutdowns"] == 0
        assert not requests_stopped.is_set()
    actual_send = send_syscall or socket.socket.send
    actual_select = select_syscall or probe.select.select
    original_timeout = channel.gettimeout()
    started = time.monotonic()
    deadline, sent = started + 2, 0
    chunk = b"SOURCE pending fixture bytes\x00\xff" * 2048
    digest, modes, primary = hashlib.sha256(), set(), None
    observations.update(prefill_limit_bytes=32 * 1024 * 1024, prefill_limit_seconds=2)
    try:
        channel.setblocking(False)
        while time.monotonic() < deadline and sent < 32 * 1024 * 1024:
            modes.add(channel.gettimeout())
            data = chunk[: min(len(chunk), 32 * 1024 * 1024 - sent)]
            try:
                count = actual_send(channel, data)
            except BlockingIOError as actual:
                observations["prefill_would_block_type"] = type(actual).__name__
                observations["prefill_would_block_errno"] = actual.errno
                observations["would_block_type"] = type(actual).__name__
                observations["would_block_errno"] = actual.errno
                _, writable, _ = actual_select([], [channel], [], 0.05)
                observations["prefill_unwritable"] = not writable
                if not writable:
                    assert (sent > 0 or active_context) and modes == {0.0}
                    if active_context:
                        assert not requests_stopped.is_set()
                    observations["zero_extra_prefill"] = sent == 0
                    observations["unwritable"] = True
                    return
            else:
                assert count > 0
                sent += count
                digest.update(data[:count])
        pytest.fail("Bounded real unread socket did not demonstrate backpressure")
    except BaseException as error:
        primary = error
        raise
    finally:
        observations.update(
            prefill_bytes=sent,
            prefill_sha256=digest.hexdigest(),
            prefill_modes=sorted(modes),
            prefill_elapsed=time.monotonic() - started,
        )
        try:
            channel.settimeout(original_timeout)
        except BaseException as error:
            observations["prefill_restoration_error"] = type(error).__name__
            if primary is None:
                raise
            primary.source_prefill_restoration_errors = (error,)


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
                "POST /api/state HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{relay.server_address[1]}\r\n"
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
            channel = next(iter(readers))
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
    tmp_path, monkeypatch, record_property
):
    relay = probe.HostRelay(tmp_path)
    actual_send, actual_select = socket.socket.send, probe.select.select
    prepared, pending, release = (threading.Event() for _ in range(3))
    outcomes, modes, setup_errors, cleanup_errors = [], [], [], []
    payload = b"literal bytes\x00\xff" * 524_288
    sent_prefix = bytearray()
    observations = {
        "phase": "pair_setup",
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "production_send_cap_bytes": 16_384,
        "operation_timeout": 20,
        "pending_limit_seconds": 2,
        "cancellation_limit_seconds": 2,
        "sent_bytes": 0,
        "unwritable": False,
    }
    worker, primary = None, None

    def error_record(error):
        return {"type": type(error).__name__, "message": str(error)}

    try:
        with _unread_tcp_pair() as (channel, unread_peer, buffers):
            observations.update(buffers)
            _observe_unread_peer(monkeypatch, unread_peer, observations)
            assert channel.gettimeout() == 20 and not relay.requests_stopped.is_set()

            def admit_pending(kind):
                # Fixture prefill alone cannot admit a production pending send.
                assert observations["phase"] == "production_pending"
                assert observations["prefill_unwritable"] is True
                assert not relay.requests_stopped.is_set()
                assert bytes(sent_prefix) == payload[: len(sent_prefix)]
                observations["unwritable"] = True
                _require_pending_send(observations, len(payload))
                observations["pending_kind"] = kind
                pending.set()
                assert release.wait(2)

            def observe_send(writer, data, flags=0):
                assert writer is channel
                modes.append(writer.gettimeout())
                try:
                    sent = actual_send(writer, data[:16_384], flags)
                except BlockingIOError as actual:
                    observations["production_would_block_type"] = type(actual).__name__
                    observations["production_would_block_errno"] = actual.errno
                    if prepared.is_set() and not pending.is_set():
                        admit_pending("actual_send_would_block")
                    raise
                observations["sent_bytes"] += sent
                sent_prefix.extend(bytes(data[:sent]))
                if not prepared.is_set():
                    observations["phase"] = "fixture_prefill"
                    try:
                        assert 0 < sent < len(payload) and writer.gettimeout() == 0.0
                        _fill_until_actual_backpressure(
                            writer,
                            observations,
                            send_syscall=actual_send,
                            select_syscall=actual_select,
                            production_prefix=sent_prefix,
                            production_payload=payload,
                            requests_stopped=relay.requests_stopped,
                        )
                        observations["unwritable"] = False
                        observations["phase"] = "production_pending"
                    except BaseException as error:
                        setup_errors.append(error)
                        raise
                    finally:
                        prepared.set()
                return sent

            def observe_pending(readers, writers, errors, timeout=None):
                result = actual_select(readers, writers, errors, timeout)
                if channel in writers:
                    observations["production_select_writable"] = bool(result[1])
                    if not result[1] and not pending.is_set():
                        admit_pending("actual_select_unwritable")
                return result

            def sending():
                try:
                    relay.send_owned(channel, payload)
                except BaseException as error:
                    outcomes.append(error)
                finally:
                    prepared.set()

            monkeypatch.setattr(socket.socket, "send", observe_send)
            monkeypatch.setattr(probe.select, "select", observe_pending)
            worker = threading.Thread(target=sending)
            worker.start()
            try:
                assert prepared.wait(2), "Bounded actual prefill did not complete"
                if setup_errors:
                    raise setup_errors[0]
                if outcomes:
                    raise outcomes[0]
                assert observations["phase"] == "production_pending"
                admitted = pending.wait(2)
                if not admitted and outcomes:
                    raise outcomes[0]
                assert admitted and worker.is_alive()
                _require_pending_send(observations, len(payload))
                assert not relay.requests_stopped.is_set()
                observations["phase"] = "cancel"
                started = time.monotonic()
                relay.requests_stopped.set()
                release.set()
                worker.join(2)
                elapsed = time.monotonic() - started
                assert not worker.is_alive() and elapsed < 2
                assert len(outcomes) == 1 and isinstance(outcomes[0], RelayClosed)
                assert channel.gettimeout() == 20 and set(modes) == {0.0}
                assert unread_peer.fileno() >= 0
                observations["cancel_exception"] = type(outcomes[0]).__name__
                observations["cancel_elapsed"] = elapsed
                observations["phase"] = "passed"
            finally:
                try:
                    observations["before_cleanup"] = {
                        "worker_alive": worker.is_alive(),
                        "stopped": relay.requests_stopped.is_set(),
                        "pending": pending.is_set(),
                        "timeout": channel.gettimeout(),
                        "peer_open": unread_peer.fileno() >= 0,
                    }
                except BaseException as error:
                    cleanup_errors.append(error)
                relay.requests_stopped.set()
                release.set()
                try:
                    worker.join(2)
                    assert not worker.is_alive()
                except BaseException as error:
                    cleanup_errors.append(error)
        observations["pair_closed"] = channel.fileno() == unread_peer.fileno() == -1
        assert observations["pair_closed"]
    except BaseException as error:
        primary = error
        cleanup_errors.extend(getattr(error, "source_pair_cleanup_errors", ()))
        observations["pair_cleanup_attempts"] = list(
            getattr(error, "source_pair_cleanup_attempts", ())
        )
        raise
    finally:
        try:
            observations["relay_close"] = relay.close_owned()
            assert observations["relay_close"] == (0, 0)
        except BaseException as error:
            cleanup_errors.append(error)
        observations.update(
            sent_prefix_bytes=len(sent_prefix),
            sent_prefix_sha256=hashlib.sha256(sent_prefix).hexdigest(),
            sent_prefix_matches_payload=bytes(sent_prefix)
            == payload[: len(sent_prefix)],
            production_modes=sorted(set(modes)),
            worker_alive=worker.is_alive() if worker else None,
            outcomes=[error_record(error) for error in outcomes],
            setup_errors=[error_record(error) for error in setup_errors],
            primary=error_record(primary) if primary else None,
            cleanup_errors=[error_record(error) for error in cleanup_errors],
            pair_cleanup_errors=[
                error_record(error)
                for error in getattr(primary, "source_pair_cleanup_errors", ())
            ],
        )
        try:
            record_property("SOURCE_backpressure_cancel", json.dumps(observations))
        except BaseException as error:
            cleanup_errors.append(error)
        if primary is not None:
            primary.source_cleanup_errors = tuple(cleanup_errors)
        elif cleanup_errors:
            raise cleanup_errors[0]


def test_actual_pending_send_with_stale_write_readiness(
    tmp_path, monkeypatch, record_property
):
    """A source seam for stale readiness still needs a genuine kernel send fault."""

    def stale_ready(owner, channel, *, reading, deadline):
        owner._check_open()
        assert not reading and time.monotonic() < deadline

    monkeypatch.setattr(probe.TrackedRequests, "_ready", stale_ready)
    test_actual_backpressured_send_stops_without_peer_read_or_shutdown(
        tmp_path, monkeypatch, record_property
    )


@pytest.mark.parametrize("later_stage", ["cleanup", "diagnostics"])
def test_pending_setup_failure_retains_primary_and_failure_telemetry(
    tmp_path, monkeypatch, later_stage
):
    """Synthetic setup/cleanup faults retain the real partial prefix and sockets."""
    first, later = OSError("literal-prefill-first"), KeyboardInterrupt("literal-later")
    properties, relays = [], []
    actual_relay = probe.HostRelay

    def own_relay(path):
        relay = actual_relay(path)
        relays.append(relay)
        if later_stage == "cleanup":
            close = relay.close_owned

            def fail_after_close():
                assert close() == (0, 0)
                raise later

            monkeypatch.setattr(relay, "close_owned", fail_after_close)
        return relay

    def fail_prefill(*args, **kwargs):
        raise first

    def retain_property(name, value):
        properties.append((name, json.loads(value)))
        if later_stage == "diagnostics":
            raise later

    monkeypatch.setattr(probe, "HostRelay", own_relay)
    monkeypatch.setattr(
        sys.modules[__name__],
        "_fill_until_actual_backpressure",
        fail_prefill,
    )
    with pytest.raises(OSError) as failed:
        test_actual_backpressured_send_stops_without_peer_read_or_shutdown(
            tmp_path, monkeypatch, retain_property
        )
    assert failed.value is first and first.source_cleanup_errors == (later,)
    assert len(properties) == 1
    name, evidence = properties[0]
    assert name == "SOURCE_backpressure_cancel"
    assert evidence["phase"] == "fixture_prefill"
    assert evidence["primary"] == {"type": "OSError", "message": str(first)}
    assert 0 < evidence["sent_bytes"] < evidence["payload_bytes"]
    assert evidence["sent_prefix_matches_payload"] is True
    assert evidence["production_modes"] == [0.0]
    assert evidence["before_cleanup"]["stopped"] is False
    assert evidence["before_cleanup"]["timeout"] == 20
    assert evidence["before_cleanup"]["peer_open"] is True
    assert evidence["worker_alive"] is False
    assert evidence["peer_reads"] == evidence["peer_shutdowns"] == 0
    assert probe.closed_port(relays[0].server_address[1]) != 0


def test_prefill_primary_survives_timeout_restoration_failure():
    first, later = OSError("literal-send-first"), KeyboardInterrupt("restore-later")
    observations = {}

    class Channel:
        def gettimeout(self):
            return 20

        def setblocking(self, value):
            assert value is False

        def settimeout(self, value):
            assert value == 20
            raise later

    def actual_failure(channel, data):
        raise first

    with pytest.raises(OSError) as failed:
        _fill_until_actual_backpressure(
            Channel(), observations, send_syscall=actual_failure
        )
    assert failed.value is first and first.source_prefill_restoration_errors == (later,)
    assert observations["prefill_bytes"] == 0
    assert observations["prefill_restoration_error"] == "KeyboardInterrupt"


@pytest.mark.parametrize("first_type", [OSError, KeyboardInterrupt])
@pytest.mark.parametrize("close_type", [OSError, KeyboardInterrupt])
def test_actual_pair_close_faults_keep_setup_first_and_all_later(
    tmp_path, monkeypatch, first_type, close_type
):
    """Actual closes plus explicit faults conserve first/three later objects."""
    first = first_type("actual-prefix-prefill-first")
    later = [
        close_type("channel-close-later"),
        OSError("peer-close-later"),
        KeyboardInterrupt("listener-close-later"),
    ]
    properties, closed, captured, relays = [], [], {}, []
    actual_close, actual_relay = socket.socket.close, probe.HostRelay

    def own_relay(path):
        relay = actual_relay(path)
        relays.append(relay)
        return relay

    def fail_prefill(channel, observations, **kwargs):
        captured["channel"] = channel
        captured["fault_active"] = True
        raise first

    def close(channel):
        result = actual_close(channel)
        if captured.get("fault_active") and len(closed) < 3:
            closed.append(channel)
            raise later[len(closed) - 1]
        return result

    monkeypatch.setattr(probe, "HostRelay", own_relay)
    monkeypatch.setattr(
        sys.modules[__name__], "_fill_until_actual_backpressure", fail_prefill
    )
    monkeypatch.setattr(socket.socket, "close", close)
    with pytest.raises(first_type) as failed:
        test_actual_backpressured_send_stops_without_peer_read_or_shutdown(
            tmp_path,
            monkeypatch,
            lambda name, value: properties.append((name, json.loads(value))),
        )
    assert failed.value is first
    assert first.source_pair_cleanup_errors == tuple(later)
    assert first.source_cleanup_errors == tuple(later)
    assert len(properties) == 1
    evidence = properties[0][1]
    assert 0 < evidence["sent_bytes"] < evidence["payload_bytes"]
    assert evidence["sent_prefix_matches_payload"] is True
    assert evidence["before_cleanup"]["stopped"] is False
    assert evidence["before_cleanup"]["timeout"] == 20
    assert evidence["worker_alive"] is False
    assert evidence["peer_reads"] == evidence["peer_shutdowns"] == 0
    attempts = evidence["pair_cleanup_attempts"]
    assert [attempt["role"] for attempt in attempts] == ["channel", "peer", "listener"]
    assert all(
        attempt["fileno_before"] >= 0 and attempt["fileno_after"] == -1
        for attempt in attempts
    )
    assert [error["type"] for error in evidence["pair_cleanup_errors"]] == [
        type(error).__name__ for error in later
    ]
    assert evidence["primary"] == {"type": first_type.__name__, "message": str(first)}
    assert closed[0] is captured["channel"]
    assert all(channel.fileno() == -1 for channel in closed)
    assert probe.closed_port(relays[0].server_address[1]) != 0


@pytest.mark.parametrize("close_type", [OSError, KeyboardInterrupt])
def test_actual_pair_close_first_without_body_error_keeps_later(
    monkeypatch, close_type
):
    first, later = close_type("first-close"), OSError("second-close")
    actual_close, closed, active = socket.socket.close, [], False

    def close(channel):
        result = actual_close(channel)
        if active:
            closed.append(channel)
            if len(closed) < 3:
                raise first if len(closed) == 1 else later
        return result

    monkeypatch.setattr(socket.socket, "close", close)
    with pytest.raises(close_type) as failed:
        with _unread_tcp_pair() as (channel, peer, observations):
            active = True
    assert failed.value is first and first.source_pair_cleanup_errors == (later,)
    assert [attempt["role"] for attempt in observations["pair_cleanup_attempts"]] == [
        "channel",
        "peer",
        "listener",
    ]
    assert all(item.fileno() == -1 for item in closed)
    assert channel.fileno() == peer.fileno() == -1


def _fill_with_same_zero_observation(
    channel, observations, *, fill, active_context, **kwargs
):
    """Use the zero-byte invocation itself; a second fill can regain capacity."""
    started, attempts = time.monotonic(), []
    initial = dict(observations)
    observations["already_full_setup_attempts"] = attempts
    if not active_context:
        kwargs = {key: kwargs[key] for key in ("send_syscall", "select_syscall")}
    for _ in range(8):
        assert time.monotonic() - started < 2
        trial = dict(initial)
        try:
            fill(channel, trial, **kwargs)
        finally:
            # Keep the exact observation, including the original refusal before
            # zero_extra_prefill is assigned. Never replay that instantaneous state.
            attempts.append(trial)
            observations.clear()
            observations.update(trial)
            observations["already_full_setup_attempts"] = attempts
        if trial["prefill_bytes"] == 0:
            assert active_context and trial["zero_extra_prefill"] is True
            assert trial["prefill_unwritable"] is True
            assert trial["prefill_would_block_type"] == "BlockingIOError"
            return
    pytest.fail("Bounded actual setup never demonstrated zero extra fill")


@pytest.fixture
def controlled_zero_prefill():
    """Deterministic syscall seam; no socket or hosted-platform claim."""
    state = {"plans": [0, 65536], "calls": 0, "errors": [], "modes": []}
    prefix = b"known production prefix\x00\xff"
    observations = {"sent_bytes": len(prefix), "peer_reads": 0, "peer_shutdowns": 0}

    class Channel:
        timeout = 0.0

        def gettimeout(self):
            return self.timeout

        def setblocking(self, blocking):
            assert blocking is False
            self.timeout = 0.0

        def settimeout(self, value):
            self.timeout = value

    channel = Channel()

    def send(writer, data):
        assert writer is channel
        state["modes"].append(writer.gettimeout())
        if state["remaining"] == 0:
            raise BlockingIOError(errno.EAGAIN, "Controlled actual-send seam")
        count = min(len(data), state["remaining"])
        state["remaining"] -= count
        return count

    def select(readers, writers, errors, timeout):
        assert readers == errors == [] and writers == [channel] and timeout == 0.05
        assert state["remaining"] == 0
        return [], [], []

    def fill(writer, trial, **kwargs):
        state["remaining"] = state["plans"][state["calls"]]
        state["calls"] += 1
        try:
            return _fill_until_actual_backpressure(writer, trial, **kwargs)
        except BaseException as error:
            state["errors"].append(error)
            raise

    kwargs = {
        "send_syscall": send,
        "select_syscall": select,
        "production_prefix": prefix,
        "production_payload": prefix + b"remaining original payload",
        "requests_stopped": threading.Event(),
    }
    return channel, observations, kwargs, fill, state


@pytest.mark.parametrize("active_context", [False, True])
@pytest.mark.parametrize("plans", [[0, 65536], [61440, 131072, 0, 65536]])
def test_zero_prefill_never_replays_after_observed_capacity_can_return(
    controlled_zero_prefill, active_context, plans
):
    channel, observations, kwargs, fill, state = controlled_zero_prefill
    state["plans"] = plans
    if active_context:
        _fill_with_same_zero_observation(
            channel, observations, fill=fill, active_context=True, **kwargs
        )
        assert state["errors"] == []
        assert observations["zero_extra_prefill"] is True
    else:
        with pytest.raises(AssertionError) as refusal:
            _fill_with_same_zero_observation(
                channel, observations, fill=fill, active_context=False, **kwargs
            )
        assert state["errors"] == [refusal.value]
        assert "zero_extra_prefill" not in observations
    assert state["calls"] == plans.index(0) + 1
    assert observations["prefill_bytes"] == 0
    assert observations["prefill_unwritable"] is True
    assert observations["prefill_would_block_type"] == "BlockingIOError"
    assert observations["prefill_would_block_errno"] == errno.EAGAIN
    assert observations["prefill_sha256"] == hashlib.sha256(b"").hexdigest()
    assert len(observations["already_full_setup_attempts"]) == state["calls"]
    assert observations["already_full_setup_attempts"][-1]["prefill_bytes"] == 0
    assert channel.gettimeout() == 0.0 and set(state["modes"]) == {0.0}
    assert not kwargs["requests_stopped"].is_set()


def test_zero_prefill_retains_eight_attempt_limit(controlled_zero_prefill):
    channel, observations, kwargs, fill, state = controlled_zero_prefill
    state["plans"] = [1] * 8
    with pytest.raises(pytest.fail.Exception, match="never demonstrated zero"):
        _fill_with_same_zero_observation(
            channel, observations, fill=fill, active_context=True, **kwargs
        )
    assert state["calls"] == 8
    assert len(observations["already_full_setup_attempts"]) == 8
    assert observations["prefill_bytes"] == 1
    assert observations["zero_extra_prefill"] is False


def test_zero_prefill_retains_two_second_budget(controlled_zero_prefill, monkeypatch):
    channel, observations, kwargs, fill, state = controlled_zero_prefill
    state.update(plans=[1], clock=0)
    monkeypatch.setattr(time, "monotonic", lambda: state["clock"])

    def spend_budget(*args, **supplied):
        result = fill(*args, **supplied)
        state["clock"] = 2
        return result

    with pytest.raises(AssertionError):
        _fill_with_same_zero_observation(
            channel, observations, fill=spend_budget, active_context=True, **kwargs
        )
    assert state["calls"] == 1
    assert len(observations["already_full_setup_attempts"]) == 1
    assert observations["prefill_bytes"] == 1


@pytest.mark.parametrize("active_context", [False, True])
def test_actual_zero_extra_prefill_requires_active_original_prefix(
    tmp_path, monkeypatch, record_property, active_context
):
    """Real production prefix, real already-full kernel, unchanged next gate."""
    actual_fill = _fill_until_actual_backpressure
    captured = []

    def already_full(channel, observations, **kwargs):
        _fill_with_same_zero_observation(
            channel,
            observations,
            fill=actual_fill,
            active_context=active_context,
            **kwargs,
        )

    def retain_property(name, value):
        captured.append(json.loads(value))
        record_property(name, value)

    monkeypatch.setattr(
        sys.modules[__name__], "_fill_until_actual_backpressure", already_full
    )
    if active_context:
        test_actual_backpressured_send_stops_without_peer_read_or_shutdown(
            tmp_path, monkeypatch, retain_property
        )
    else:
        with pytest.raises(AssertionError):
            test_actual_backpressured_send_stops_without_peer_read_or_shutdown(
                tmp_path, monkeypatch, retain_property
            )
    assert len(captured) == 1
    evidence = captured[0]
    assert 0 < evidence["sent_bytes"] < evidence["payload_bytes"]
    assert evidence["sent_prefix_matches_payload"] is True
    assert evidence["prefill_bytes"] == 0 and evidence["prefill_unwritable"] is True
    assert evidence["peer_reads"] == evidence["peer_shutdowns"] == 0
    assert evidence["worker_alive"] is False and evidence["relay_close"] == [0, 0]
    assert all(
        attempt["fileno_after"] == -1 for attempt in evidence["pair_cleanup_attempts"]
    )
    if active_context:
        assert evidence["phase"] == "passed"
        assert evidence["cancel_exception"] == "RelayClosed"
        assert evidence["pending_kind"] in {
            "actual_select_unwritable",
            "actual_send_would_block",
        }
        assert evidence["cancel_elapsed"] < 2
    else:
        assert evidence["phase"] == "fixture_prefill"
        assert evidence["primary"]["type"] == "AssertionError"
        assert evidence["before_cleanup"]["pending"] is False


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


def test_actual_backpressured_send_expires_original_operation_budget(
    tmp_path, monkeypatch, record_property
):
    relay = probe.HostRelay(tmp_path)
    try:
        with _unread_tcp_pair() as (channel, unread_peer, observations):
            _observe_unread_peer(monkeypatch, unread_peer, observations)
            _fill_until_actual_backpressure(channel, observations)
            channel.settimeout(0.25)
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                relay.send_owned(channel, b"literal bytes\x00\xff" * 524_288)
            elapsed = time.monotonic() - started
            assert 0.2 <= elapsed < 2
            assert channel.gettimeout() == 0.25
            assert not relay.requests_stopped.is_set() and unread_peer.fileno() >= 0
            observations["operation_elapsed"] = elapsed
        observations["pair_closed"] = channel.fileno() == unread_peer.fileno() == -1
        assert observations["pair_closed"]
    finally:
        assert relay.close_owned() == (0, 0)
    record_property("SOURCE_backpressure_timeout", json.dumps(observations))


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


def test_windows_selector_set_call_shape_reaches_the_real_receive_seam(
    tmp_path, monkeypatch
):
    import selectors

    class WindowsShapeSelector(selectors.SelectSelector):
        # This is the Windows stdlib SelectSelector call shape: its actual
        # _readers/_writers sets reach the patched global select function.
        def _select(self, readers, writers, _errors, timeout=None):
            return probe.select.select(readers, writers, writers, timeout)

    monkeypatch.setattr(socketserver, "_ServerSelector", WindowsShapeSelector)
    test_readiness_stop_gap_cannot_start_a_blocking_receive(tmp_path, monkeypatch)


@pytest.mark.parametrize("sent_bytes", [0, 7_864_320, 7_864_321])
def test_completed_or_unstarted_send_is_not_backpressure_admission(sent_bytes):
    observations = {
        "sent_bytes": sent_bytes,
        "unwritable": True,
        "peer_reads": 0,
        "peer_shutdowns": 0,
    }
    with pytest.raises(AssertionError):
        _require_pending_send(observations, 7_864_320)


@pytest.mark.parametrize("field", ["peer_reads", "peer_shutdowns"])
def test_peer_consumption_or_shutdown_cannot_establish_pending_admission(field):
    observations = {
        "sent_bytes": 1,
        "unwritable": True,
        "peer_reads": 0,
        "peer_shutdowns": 0,
    }
    observations[field] = 1
    with pytest.raises(AssertionError):
        _require_pending_send(observations, 2)


def test_actual_whole_completed_send_is_not_pending_backpressure(record_property):
    with _unread_tcp_pair() as (channel, unread_peer, observations):
        content = b"SOURCE complete whole send\x00\xff"
        observations["sent_bytes"] = channel.send(content)
        _, writable, _ = probe.select.select([], [channel], [], 0)
        observations["unwritable"] = not writable
        assert observations["sent_bytes"] == len(content)
        with pytest.raises(AssertionError):
            _require_pending_send(observations, len(content))
        assert unread_peer.fileno() >= 0
    assert channel.fileno() == unread_peer.fileno() == -1
    record_property(
        "SOURCE_completed_send_refused_as_pending", json.dumps(observations)
    )
