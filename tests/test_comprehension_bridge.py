# SPDX-License-Identifier: Apache-2.0
"""Sinter forwards only the local comprehension episode routes."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection
import json
import threading

import pytest

from sinter import comprehension_bridge, runtime_routes
from sinter.server import make_server


class Fixture(BaseHTTPRequestHandler):
    calls: list[tuple[str, str, object]] = []

    def log_message(self, *args):
        pass

    def _reply(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else None
        self.calls.append((self.command, self.path, body))
        value = {"status": "ok", "path": self.path, "body": body}
        encoded = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    do_GET = _reply
    do_POST = _reply


def _fixture():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_bridge_forwards_only_episode_routes(monkeypatch):
    Fixture.calls = []
    server, thread = _fixture()
    monkeypatch.setenv("SINTER_COMPREHENSION_URL",
                       f"http://127.0.0.1:{server.server_port}")
    try:
        value = comprehension_bridge.request("/api/health")
        assert value["status"] == "ok"
        value = comprehension_bridge.request(
            "/api/comprehension/episodes/0123456789abcdef0123456789abcdef/lesson",
            method="POST", payload={"lesson_id": "x", "text": "y"})
        assert value["body"] == {"lesson_id": "x", "text": "y"}
        value = comprehension_bridge.request(
            "/api/organizational/interpret", method="POST",
            payload={"passage_id": "T1", "speaker": "Alex", "text": "x"})
        assert value["body"]["passage_id"] == "T1"
        with pytest.raises(ValueError, match="not available"):
            comprehension_bridge.request("/api/transcribe", method="POST",
                                          payload={})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_bridge_rejects_non_loopback_destination(monkeypatch):
    monkeypatch.setenv("SINTER_COMPREHENSION_URL", "http://example.com:8792")
    with pytest.raises(ValueError, match="loopback|this computer"):
        comprehension_bridge.request("/api/health")


def test_sinter_routes_proxy_comprehension(monkeypatch, tmp_path):
    calls = []

    def fake_request(path, *, method="GET", payload=None):
        calls.append((path, method, payload))
        return {"status": "ok", "path": path, "method": method}

    monkeypatch.setattr(runtime_routes.comprehension_bridge, "request", fake_request)
    server = make_server(port=0, directory=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        connection.request("GET", "/api/comprehension/health",
                           headers={"X-Sinter-Token": server.app.token})
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["path"] == "/api/health"
        connection.close()
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        connection.request(
            "POST", "/api/comprehension/episodes/0123456789abcdef0123456789abcdef/transfer",
            body=json.dumps({"application": "inventory", "task": "x"}),
            headers={"Content-Type": "application/json",
                     "X-Sinter-Token": server.app.token})
        response = connection.getresponse()
        assert response.status == 200
        connection.close()
        assert calls[-1][0].endswith("/transfer")
        assert calls[-1][2]["application"] == "inventory"
    finally:
        server.shutdown()
        server.app.close()
        server.server_close()
        thread.join(timeout=5)
