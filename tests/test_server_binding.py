"""Real local requests must not depend on reverse hostname service."""

import errno
import json
import socket
import threading
from http.client import HTTPConnection

import pytest

from sinter import client
from sinter.native_browser import NativeBrowserWorkbench
from sinter.runtime import Runtime
from sinter.server import make_server


def forbid_optional_lookup(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise AssertionError("No hostname or provider lookup for a local listener")

    for name in ("getfqdn", "gethostbyaddr"):
        monkeypatch.setattr(socket, name, unavailable)
    for name in ("_open", "chat", "search", "_load_key"):
        monkeypatch.setattr(client, name, unavailable)


def request(server, host, path, *, payload=None, headers=None, duplicate_host=False):
    connection = HTTPConnection(host, server.server_port, timeout=3)
    try:
        if duplicate_host:
            connection.putrequest("GET", path, skip_host=True)
            authority = (
                ("[::1]" if host == "::1" else host) + ":" + str(server.server_port)
            )
            connection.putheader("Host", authority)
            connection.putheader("Host", authority)
            connection.endheaders()
        else:
            values = dict(headers or {})
            if payload is not None:
                values.setdefault("Content-Type", "application/json")
            connection.request(
                "POST" if payload is not None else "GET",
                path,
                json.dumps(payload) if payload is not None else None,
                values,
            )
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


@pytest.mark.parametrize("bind", ["127.0.0.1", "localhost", "::1"])
def test_offline_binding_preserves_host_token_and_actual_saved_requests(
    tmp_path, monkeypatch, bind
):
    forbid_optional_lookup(monkeypatch)
    try:
        server = make_server(bind, 0, tmp_path)
    except OSError as error:
        if bind == "::1" and error.errno in {
            errno.EAFNOSUPPORT,
            errno.EADDRNOTAVAIL,
            errno.EPROTONOSUPPORT,
        }:
            pytest.skip("This runner has no available IPv6 loopback interface")
        raise
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = "::1" if bind == "::1" else "127.0.0.1"
    try:
        assert server.server_name == host
        assert server.server_port == server.server_address[1] > 0
        code, headers, content = request(server, host, "/api/session")
        assert code == 200 and json.loads(content)["token"] == server.app.token
        assert headers["X-Frame-Options"] == "DENY"
        assert request(server, host, "/static/app.js")[0] == 200
        for hostile in (
            {"Host": "evil.invalid"},
            {"Origin": "https://evil.invalid"},
            {"Sec-Fetch-Site": "cross-site"},
        ):
            assert request(server, host, "/api/session", headers=hostile)[0] == 403
        assert request(server, host, "/api/session", duplicate_host=True)[0] == 403
        document = {"title": "Fictional offline source — é 🐝"}
        assert (
            request(
                server, host, "/api/campaigns/save", payload={"document": document}
            )[0]
            == 403
        )
        assert server.app.campaigns.list() == []
        code, _, content = request(
            server,
            host,
            "/api/campaigns/save",
            payload={"document": document},
            headers={"X-Sinter-Token": server.app.token},
        )
        saved = json.loads(content)
        assert code == 200 and saved["revision"] == 1
        assert saved["document"]["title"] == document["title"]
        assert server.app.campaigns.get(saved["id"]) == saved
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        server.app.close()
    assert not thread.is_alive()


def test_owned_native_listener_uses_same_numeric_binding_without_provider(
    tmp_path, monkeypatch
):
    forbid_optional_lookup(monkeypatch)
    with Runtime(tmp_path) as runtime:
        workbench = NativeBrowserWorkbench(runtime.app)
        try:
            assert workbench.server.server_name == "127.0.0.1"
            code, _, content = request(workbench.server, "127.0.0.1", "/api/session")
            assert code == 200 and json.loads(content)["native_window_owner"] is True
        finally:
            workbench.close()
        assert workbench.closed and not workbench.thread.is_alive()
        assert workbench.server.active_requests == 0
        assert runtime.app.desktop_shutdown is None


def test_occupied_socket_is_not_retried_or_resolved(tmp_path, monkeypatch):
    forbid_optional_lookup(monkeypatch)
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        with pytest.raises(OSError) as refusal:
            make_server("127.0.0.1", occupied.getsockname()[1], tmp_path)
        assert refusal.value.errno == errno.EADDRINUSE


@pytest.mark.parametrize("bind", ["0.0.0.0", "::", "evil.invalid", "192.0.2.1"])
def test_offline_binding_does_not_admit_remote_interfaces(tmp_path, monkeypatch, bind):
    forbid_optional_lookup(monkeypatch)
    with pytest.raises(ValueError, match="local-only"):
        make_server(bind, 0, tmp_path)
    assert not (tmp_path / "workspace.sqlite3").exists()
