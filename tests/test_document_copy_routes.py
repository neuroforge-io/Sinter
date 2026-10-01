"""The recovery route retains ordinary localhost, session and payload gates."""

from __future__ import annotations

import hashlib
import json
import threading
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import client
from sinter.docx_export import export_docx
from sinter.runtime import Runtime
from sinter.server import make_server

PAYLOAD = {
    "title": "Fictional local copy 🐝",
    "markdown": "# Exact supplied text\n\nNot approved — e\u0301 🐝.",
}
ROUTE = "/api/documents/docx/save"


@pytest.fixture
def server(tmp_path):
    instance = make_server(port=0, directory=tmp_path)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    with patch.object(client, "_open", side_effect=AssertionError("No hosted request")):
        yield instance
    instance.shutdown()
    instance.app.close()
    instance.server_close()
    thread.join(timeout=5)


def call(server, *, path=ROUTE, method="POST", payload=PAYLOAD, headers=None, raw=None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    selected = {"Content-Type": "application/json", "X-Sinter-Token": server.app.token}
    if headers is not None:
        selected.update(headers)
    try:
        connection.request(
            method,
            path,
            body=raw
            if raw is not None
            else json.dumps(payload, ensure_ascii=False).encode(),
            headers=selected,
        )
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_exact_binary_equivalence_and_no_url_or_auth_exception(server):
    status, headers, body = call(server)
    assert status == 200 and headers["Cache-Control"] == "no-store"
    result = json.loads(body)
    disk = Path(result["path"]).read_bytes()
    assert disk == export_docx(PAYLOAD).content
    assert hashlib.sha256(disk).hexdigest() == result["sha256"]
    status, normal_headers, normal = call(server, path="/api/documents/docx")
    assert status == 200 and normal == disk
    assert normal_headers["Content-Type"].endswith("wordprocessingml.document")
    assert "attachment;" in normal_headers["Content-Disposition"]
    assert server.app.token.encode() not in body
    assert call(server, method="GET")[0] == 404


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Sinter-Token": ""},
        {"X-Sinter-Token": "wrong"},
        {"Host": "evil.example"},
        {"Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_existing_security_denies_before_disk_write(server, headers):
    assert call(server, headers=headers)[0] == 403
    assert not (server.app.store.directory / "exports").exists()


@pytest.mark.parametrize(
    "payload",
    [
        {**PAYLOAD, "path": "/tmp/arbitrary.docx"},
        {**PAYLOAD, "overwrite": True},
        {**PAYLOAD, "markdown": ""},
        [],
    ],
)
def test_only_exact_document_payload_admitted_without_storage_mutation(server, payload):
    assert call(server, payload=payload)[0] == 400
    assert not (server.app.store.directory / "exports").exists()


def test_content_type_and_existing_body_limit_are_retained(server):
    assert call(server, headers={"Content-Type": "text/plain"})[0] == 400
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.putrequest("POST", ROUTE)
        connection.putheader("Content-Type", "application/json")
        connection.putheader("X-Sinter-Token", server.app.token)
        connection.putheader("Content-Length", str(2 * 1024 * 1024 + 1))
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 400
        response.read()
    finally:
        connection.close()
    assert not (server.app.store.directory / "exports").exists()


def test_existing_report_preferences_and_campaigns_survive_local_export(server):
    app = server.app
    campaign = app.campaigns.save(
        {"title": "Fictional campaign", "organisation": "Fictional group"}
    )
    app.preferences.update({"full_name": "Fictional owner"})
    before = {
        name: (app.store.directory / name).read_bytes()
        for name in ["preferences.json", "campaigns.sqlite3"]
    }
    assert call(server)[0] == 200
    assert app.campaigns.get(campaign["id"]) == campaign
    assert all(
        (app.store.directory / name).read_bytes() == value
        for name, value in before.items()
    )


def test_shared_runtime_explicit_operation_uses_the_same_private_recovery(tmp_path):
    with Runtime(tmp_path) as runtime:
        result = runtime.call("documents.docx.save", PAYLOAD)
        assert Path(result["path"]).read_bytes() == export_docx(PAYLOAD).content
