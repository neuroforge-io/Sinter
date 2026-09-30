"""Optional account failure cannot strand local work or connection recovery."""
import json
import os
import threading
import time
from unittest.mock import patch

import pytest
import test_runtime
from test_campaigns import campaign
from test_runtime import post, request

from sinter import accounts, client

server = test_runtime.server


@pytest.mark.parametrize("failure", ["corrupt", "startup", "permissions", "extra"])
def test_optional_account_failure_preserves_local_app_and_recovery(
    server, monkeypatch, failure,
):
    monkeypatch.delenv("NEUROFORGE_BASE_URL", raising=False)
    monkeypatch.delenv("NEUROFORGE_MODEL", raising=False)
    server.app.preferences.update({
        "provider": "chatgpt", "api_url": accounts.RESOURCE, "model": "fixture-model",
    }, confirm_endpoint=True)
    if failure in {"corrupt", "startup"}:
        server.app.accounts.path.write_text("preserve this damaged account record")
        if failure == "startup":
            server.app.accounts = accounts.AccountManager(server.app.store.directory)
    elif failure == "permissions":
        if os.name == "nt":
            pytest.skip("Unix owner-only permission regression")
        server.app.accounts.path.chmod(0o644)
    else:
        monkeypatch.setattr(accounts.AccountManager, "_verification_available",
                            staticmethod(lambda: False))
    original = server.app.accounts.path.read_bytes()
    with patch.object(client, "_post_raw") as model:
        for path in ("/", "/static/app.js", "/api/session", "/api/settings",
                     "/api/campaigns"):
            assert request(server, path)[0] == 200, path
        code, _, raw = request(server, "/api/account")
        status = json.loads(raw)
        assert code == 200 and status["available"] is False
        assert status["message"]
        assert post(server, "/api/campaigns/prepare", {
            "document": campaign(),
        })[0] == 200
        with client.connection_settings(server.app.connection()):
            with pytest.raises(client.APIError):
                client._headers()
        model.assert_not_called()
    assert post(server, "/api/settings", {
        "settings": {"provider": "openai-compatible", "api_url": client.BASE_URL,
                     "model": "auto"}, "confirm_endpoint": True,
    })[0] == 200
    assert request(server, "/api/settings")[0] == 200
    assert server.app.accounts.path.read_bytes() == original


def test_core_requests_do_not_wait_for_account_renewal_lock(server, monkeypatch):
    monkeypatch.delenv("NEUROFORGE_BASE_URL", raising=False)
    monkeypatch.delenv("NEUROFORGE_MODEL", raising=False)
    server.app.preferences.update({
        "provider": "chatgpt", "api_url": accounts.RESOURCE, "model": "fixture-model",
    }, confirm_endpoint=True)
    acquired, release = threading.Event(), threading.Event()

    def occupied():
        with server.app.accounts._lock, server.app.accounts._disk_lock():
            acquired.set()
            release.wait(5)

    worker = threading.Thread(target=occupied, daemon=True)
    worker.start()
    assert acquired.wait(1)
    before = time.monotonic()
    try:
        assert request(server, "/api/settings")[0] == 200
        assert request(server, "/api/campaigns")[0] == 200
        assert time.monotonic() - before < 1
    finally:
        release.set()
        worker.join(timeout=2)
