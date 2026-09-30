"""Optional model accounts cannot become dependencies of local work or trust checks."""

from __future__ import annotations

import io
import json
import threading
import time
import zipfile
from unittest.mock import patch

import pytest
from test_runtime import post, request, wait_job

from sinter import accounts, client, practice, workbench
from sinter.server import make_server

FIRST = "1" * 32
SECOND = "2" * 32


@pytest.fixture
def server(tmp_path):
    instance = make_server(port=0, directory=tmp_path)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.app.close()
        instance.server_close()
        thread.join(timeout=5)


@pytest.fixture
def selected_account(server, monkeypatch):
    """Use only synthetic account storage in the disposable server fixture."""
    monkeypatch.delenv("NEUROFORGE_BASE_URL", raising=False)
    monkeypatch.delenv("NEUROFORGE_MODEL", raising=False)
    server.app.preferences.update(
        {
            "provider": "chatgpt",
            "api_url": accounts.RESOURCE,
            "model": "fictional-model",
            "max_tokens": 512,
        },
        confirm_endpoint=True,
    )
    manager = server.app.accounts
    data = manager._read()
    data["active_id"] = FIRST
    data["profiles"] = {
        identity: {
            "client_id": "oaiapp_fictional",
            "subject": "fictional-" + identity,
            "issuer": accounts.AUTHORITY,
            "access_token": "fictional-" + identity,
            "refresh_token": "fictional-refresh",
            "id_token": "fictional-identity",
            "scopes": [accounts.PLAN_SCOPE],
            "expires_at": time.time() + 3600,
        }
        for identity in (FIRST, SECOND)
    }
    manager._write(data)
    monkeypatch.setattr(manager, "_verification_available", lambda: True)
    return manager


@pytest.mark.parametrize("state", ["missing", "expired", "unavailable", "corrupt"])
def test_optional_account_states_leave_local_pages_available(
    server,
    selected_account,
    monkeypatch,
    state,
):
    manager = selected_account
    data = manager._read()
    if state == "missing":
        data.update(active_id="", profiles={})
        manager._write(data)
    elif state == "expired":
        data["profiles"][FIRST]["expires_at"] = time.time() - 100
        manager._write(data)
    elif state == "unavailable":
        monkeypatch.setattr(manager, "_verification_available", lambda: False)
    else:
        manager.path.write_text("fictional corrupt account record")
    with (
        patch.object(manager, "connection", wraps=manager.connection) as binding,
        patch.object(manager, "_request", side_effect=AssertionError("No refresh")),
        patch.object(client, "_open", side_effect=AssertionError("No inference")),
    ):
        for path in (
            "/",
            "/static/app.js",
            "/api/session",
            "/api/settings",
            "/api/templates",
            "/api/example?workflow=brief",
            "/api/practice/garden",
            "/api/casebooks",
            "/api/campaigns",
            "/api/reports",
            "/api/jobs",
        ):
            assert request(server, path)[0] == 200, path
        assert request(server, "/", "HEAD")[0] == 200
        binding.assert_not_called()


def test_account_connection_failure_cannot_block_offline_save_prepare_or_export(
    server,
    selected_account,
):
    fixture = practice.garden()
    with (
        patch.object(
            selected_account,
            "connection",
            side_effect=accounts.AccountError("Fictional optional account unavailable"),
        ) as binding,
        patch.object(client, "_open", side_effect=AssertionError("Offline only")),
    ):
        code, _, raw = post(
            server,
            "/api/casebooks/save",
            {
                "document": fixture["casebook"],
            },
        )
        assert code == 200
        saved = json.loads(raw)
        code, _, raw = post(
            server,
            "/api/casebooks/build",
            {
                "id": saved["id"],
                "revision": saved["revision"],
            },
        )
        assert code == 202
        result = wait_job(server.app.jobs, json.loads(raw)["id"])
        assert result["status"] == "done"
        report = result["result"]
        assert report["document_type"] == "handover"
        assert request(server, "/api/casebooks/" + saved["id"])[0] == 200
        assert post(server, "/api/reports", {"report": report})[0] == 201
        code, _, raw = post(
            server,
            "/api/documents/docx",
            {
                "title": report["title"],
                "markdown": report["document_markdown"],
            },
        )
        assert code == 200 and zipfile.ZipFile(io.BytesIO(raw)).testzip() is None
        assert (
            post(
                server,
                "/api/campaigns/save",
                {
                    "document": fixture["campaign"],
                },
            )[0]
            == 200
        )
        assert (
            post(
                server,
                "/api/campaigns/prepare",
                {
                    "document": fixture["campaign"],
                },
            )[0]
            == 200
        )
        code, _, raw = post(server, "/api/workbench", workbench.example("brief"))
        assert code == 202
        assert wait_job(server.app.jobs, json.loads(raw)["id"])["status"] == "done"
        assert (
            post(
                server,
                "/api/settings",
                {
                    "settings": {"organisation": "Fictional local group"},
                },
            )[0]
            == 200
        )
        binding.assert_not_called()


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.invalid"},
        {"Origin": "https://evil.invalid"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_remote_route_trust_checks_precede_optional_account_lookup(
    server,
    selected_account,
    headers,
):
    with patch.object(
        selected_account,
        "connection",
        side_effect=accounts.AccountError("Fictional optional account unavailable"),
    ) as binding:
        assert request(server, "/api/models", headers=headers)[0] == 403
        assert request(server, "/api/models", "HEAD", headers=headers)[0] == 403
        binding.assert_not_called()


def test_model_post_token_and_json_checks_precede_account_lookup(
    server,
    selected_account,
):
    with patch.object(
        selected_account,
        "connection",
        side_effect=accounts.AccountError("Fictional optional account unavailable"),
    ) as binding:
        assert post(server, "/api/chat", {}, token=False)[0] == 403
        assert (
            request(
                server,
                "/api/chat",
                "POST",
                "{bad",
                {
                    "Content-Type": "application/json",
                    "X-Sinter-Token": server.app.token,
                },
            )[0]
            == 400
        )
        binding.assert_not_called()


def test_remote_catalogue_keeps_selected_destination_and_account_identity(
    server,
    selected_account,
):
    observed = []

    def models():
        observed.append(client.connection_identity())
        assert callable(client._CONNECTION.get()["account_token"])
        return [{"id": "fictional-model"}]

    with (
        patch.object(client, "list_models", side_effect=models),
        patch.object(
            selected_account, "_request", side_effect=AssertionError("No refresh")
        ),
    ):
        assert request(server, "/api/models")[0] == 200
    assert observed == [
        {
            "provider": "chatgpt",
            "api_url": accounts.RESOURCE,
            "model": "fictional-model",
            "max_tokens": 512,
            "account_profile_id": FIRST,
        }
    ]


def test_candidate_catalogue_can_leave_an_unavailable_selected_account(
    server,
    selected_account,
):
    before = server.app.preferences.snapshot()
    observed = []

    def models():
        observed.append(client.connection_identity())
        return [{"id": "fictional-candidate-model"}]

    with (
        patch.object(
            selected_account,
            "connection",
            side_effect=accounts.AccountError("Fictional optional account unavailable"),
        ) as binding,
        patch.object(client, "list_models", side_effect=models),
    ):
        assert (
            post(
                server,
                "/api/models",
                {
                    "settings": {
                        "provider": "openai-compatible",
                        "api_url": client.BASE_URL,
                        "model": "fictional-candidate-model",
                        "max_tokens": 512,
                    },
                    "confirm_endpoint": True,
                },
            )[0]
            == 200
        )
        binding.assert_not_called()
    assert observed[0]["provider"] == "openai-compatible"
    assert observed[0]["api_url"] == client.BASE_URL
    assert "account_profile_id" not in observed[0]
    assert server.app.preferences.snapshot() == before


def test_queued_model_job_retains_the_original_account_after_activation(
    server,
    selected_account,
):
    started, release = threading.Event(), threading.Event()
    observed = []

    def chat(messages, maximum):
        started.set()
        assert release.wait(5)
        observed.append((client.connection_identity(), client._headers()))
        return client.ChatResult("Fictional answer", finish_reason="stop")

    with (
        patch.object(client, "chat", side_effect=chat),
        patch.object(
            selected_account, "_request", side_effect=AssertionError("No refresh")
        ),
        patch.object(client, "_open", side_effect=AssertionError("No hosted calls")),
    ):
        try:
            code, _, raw = post(
                server,
                "/api/chat/job",
                {
                    "messages": [{"role": "user", "content": "Fictional question"}],
                },
            )
            assert code == 202 and started.wait(5)
            data = selected_account._read()
            data["active_id"] = SECOND
            selected_account._write(data)
        finally:
            release.set()
        assert wait_job(server.app.jobs, json.loads(raw)["id"])["status"] == "done"
    identity, headers = observed[0]
    assert identity["account_profile_id"] == FIRST
    assert headers["Authorization"] == "Bearer fictional-" + FIRST


def test_connection_bound_preview_changes_when_the_selected_account_changes(
    server,
    selected_account,
):
    saved = server.app.campaigns.save(practice.garden()["campaign"])
    payload = {
        "id": saved["id"],
        "revision": saved["revision"],
        "opportunity": saved["document"]["opportunities"][0]["name"],
    }
    with patch.object(client, "chat") as model:
        code, _, raw = post(server, "/api/assistant/preview", payload)
        assert code == 200
        first = json.loads(raw)
        data = selected_account._read()
        data["active_id"] = SECOND
        selected_account._write(data)
        code, _, raw = post(server, "/api/assistant/preview", payload)
        assert code == 200
        second = json.loads(raw)
        assert first["connection"]["account_profile_id"] == FIRST
        assert second["connection"]["account_profile_id"] == SECOND
        assert first["context_hash"] != second["context_hash"]
        assert (
            post(
                server,
                "/api/assistant/job",
                {
                    **payload,
                    "consent": True,
                    "context_hash": first["context_hash"],
                },
            )[0]
            == 400
        )
        model.assert_not_called()


def test_search_and_watch_scheduler_use_no_model_account_callback(
    server,
    selected_account,
):
    calls = []

    def search(path, body):
        assert path == "/search"
        assert client.selected_provider() == "openai-compatible"
        assert client._CONNECTION.get()["api_url"] == client.BASE_URL
        assert "account_token" not in client._CONNECTION.get()
        assert "Authorization" not in client._headers()
        calls.append(body["query"])
        return {"results": [], "retrieved_at": "2026-09-30"}

    with (
        patch.object(
            selected_account,
            "connection",
            side_effect=accounts.AccountError("Fictional optional account unavailable"),
        ) as binding,
        patch.object(client, "_post", side_effect=search),
        patch.object(server.app.stop, "wait", side_effect=[False, True]),
    ):
        assert post(server, "/api/search", {"query": "fictional garden"})[0] == 200
        server.app.store.add_watch("Fictional watch", "fictional funding", 86400)
        server.app.scheduler()
        assert calls == ["fictional garden", "fictional funding"]
        assert server.app.store.watches()[0]["last_run"] is not None
        binding.assert_not_called()
