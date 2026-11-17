"""Synthetic Anthropic catalogue discovery; no credentials or network access."""

import io
import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from test_runtime import request as http_request

from sinter import client, operations
from sinter.server import make_server


@pytest.fixture(autouse=True)
def isolated_connection(tmp_path, monkeypatch):
    for name in (
        "NEUROFORGE_MODEL", "NEUROFORGE_BASE_URL", "NEUROFORGE_API_KEY",
        "SINTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(client, "_KEY_FILE", tmp_path / "unused-fictional-key")
    monkeypatch.setattr(
        client, "_load_key",
        lambda: pytest.fail("Synthetic discovery must not read a public key"),
    )
    monkeypatch.setattr(
        client.urllib.request, "build_opener",
        lambda *args: pytest.fail("Synthetic discovery must not use the network"),
    )
    with client.connection_settings({
        "provider": "anthropic", "api_url": "https://api.anthropic.com/v1",
        "model": "fictional-claude-selected", "max_tokens": 64,
        "api_key": "fictional-key", "inherit_key": False,
    }):
        yield


def page(*identifiers, more=False):
    return {
        "data": [{"id": identifier} for identifier in identifiers],
        "has_more": more,
        "last_id": identifiers[-1] if identifiers else None,
    }


def test_anthropic_catalogue_includes_later_pages_in_provider_order():
    pages = [page("fictional-new", more=True),
             page("fictional-claude-selected")]
    with patch.object(client, "_get", side_effect=pages) as discover:
        models = client.list_models()
    assert [model["id"] for model in models] == [
        "fictional-new", "fictional-claude-selected",
    ]
    assert [call.args[0] for call in discover.call_args_list] == [
        "/models", "/models?after_id=fictional-new",
    ]


def test_health_check_can_verify_selected_model_on_later_page():
    pages = [page("fictional-new", more=True),
             page("fictional-claude-selected")]
    with (
        patch.object(client, "_get", side_effect=pages) as discover,
        patch.object(client, "_post") as generation,
    ):
        connected, message = client.health_check()
    assert connected is True
    assert "fictional-claude-selected" in message
    assert "generation has not been tested" in message
    assert discover.call_count == 2
    generation.assert_not_called()


@pytest.mark.parametrize("catalogue", [page(), page("fictional-one"),
                                     {"data": [{"id": "fictional-one"}]}])
def test_single_page_and_legacy_compatible_catalogues_do_not_request_more(catalogue):
    with patch.object(client, "_get", return_value=catalogue) as discover:
        assert client.list_models() == catalogue["data"]
    discover.assert_called_once_with("/models")


@pytest.mark.parametrize("more", [None, 0, 1, "true", [], {}])
def test_invalid_pagination_flag_stops_before_another_request(more):
    catalogue = {**page("fictional-one"), "has_more": more}
    with patch.object(client, "_get", return_value=catalogue) as discover:
        with pytest.raises(client.APIError, match="invalid model list"):
            client.list_models()
    assert discover.call_count == 1


@pytest.mark.parametrize("cursor", [None, "", 7, [], {}, "fictional-other"])
def test_missing_or_mismatched_cursor_stops_before_another_request(cursor):
    catalogue = {**page("fictional-one", more=True), "last_id": cursor}
    with patch.object(client, "_get", return_value=catalogue) as discover:
        with pytest.raises(client.APIError, match="invalid model list"):
            client.list_models()
    assert discover.call_count == 1


@pytest.mark.parametrize("cursor", ["fictional\nmodel", "fictional model",
                                   "fictional?next=1", "fictional&other=1",
                                   "fictional#fragment", "fictional%0a",
                                   "fictional-🌱", "x" * 201])
def test_unsafe_matching_cursor_is_rejected_without_following_it(cursor):
    with patch.object(client, "_get", return_value=page(cursor, more=True)) as discover:
        with pytest.raises(client.APIError, match="invalid model list"):
            client.list_models()
    assert discover.call_count == 1


def test_encoded_cursor_keeps_selected_endpoint_and_native_headers(monkeypatch):
    cursor = "fictional/model:variant+one"
    pages = iter([page(cursor, more=True), page("fictional-claude-selected")])
    requests = []

    class MockOpener:
        def open(self, request, timeout):
            requests.append((request, timeout))
            return io.BytesIO(json.dumps(next(pages)).encode())

    monkeypatch.setattr(
        client.urllib.request, "build_opener", lambda *args: MockOpener(),
    )
    assert len(client.list_models()) == 2
    assert [request.full_url for request, _ in requests] == [
        "https://api.anthropic.com/v1/models",
        "https://api.anthropic.com/v1/models?after_id=fictional%2Fmodel%3Avariant%2Bone",
    ]
    for request, timeout in requests:
        assert request.get_header("X-api-key") == "fictional-key"
        assert request.get_header("Anthropic-version") == "2023-06-01"
        assert request.get_header("Authorization") is None
        assert 0 < timeout <= client.CONTROL_TIMEOUT


@pytest.mark.parametrize("pages", [
    [page(more=True)],
    [page("fictional-one", "fictional-one")],
    [page("fictional-one", more=True), page("fictional-one", more=True)],
    [page("fictional-one", more=True), page("fictional-two", "fictional-one")],
])
def test_empty_continuation_duplicate_models_and_cursor_loops_are_rejected(pages):
    with patch.object(client, "_get", side_effect=pages) as discover:
        with pytest.raises(client.APIError, match="invalid model list"):
            client.list_models()
    assert discover.call_count == len(pages)


def test_catalogue_bound_allows_exactly_256_models_across_pages():
    identifiers = [f"fictional-{index}" for index in range(256)]
    pages = [page(*identifiers[:128], more=True), page(*identifiers[128:])]
    with patch.object(client, "_get", side_effect=pages) as discover:
        assert [model["id"] for model in client.list_models()] == identifiers
    assert discover.call_count == 2


@pytest.mark.parametrize("pages", [
    [page(*(f"fictional-{index}" for index in range(257)))],
    [page(*(f"fictional-{index}" for index in range(256)), more=True)],
    [page(*(f"fictional-{index}" for index in range(255)), more=True),
     page("fictional-255", "fictional-256")],
])
def test_catalogue_bound_is_aggregate_and_never_returns_truncated_success(pages):
    with patch.object(client, "_get", side_effect=pages) as discover:
        with pytest.raises(client.APIError, match="invalid model list"):
            client.list_models()
    assert discover.call_count == len(pages)


def test_later_page_failure_is_not_retried_or_treated_as_complete():
    with patch.object(client, "_get", side_effect=[
        page("fictional-one", more=True), client.APIError("Fictional offline"),
    ]) as discover:
        with pytest.raises(client.APIError, match="Fictional offline"):
            client.list_models()
    assert discover.call_count == 2


def test_all_pages_share_one_control_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(operations, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    calls = []

    def discover(path):
        calls.append(path)
        clock[0] += 4
        return page(f"fictional-{len(calls)}", more=True)

    with patch.object(client, "_get", side_effect=discover):
        with pytest.raises(client.APIError, match="Model discovery exceeded") as failed:
            client.list_models()
    assert len(calls) == 3
    assert failed.value.status == 504


def test_discovery_timeout_is_a_visible_health_check_failure(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(operations, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    def discover(path):
        clock[0] = client.CONTROL_TIMEOUT + 1
        return page("fictional-one", more=True)

    with patch.object(client, "_get", side_effect=discover) as discover:
        connected, message = client.health_check()
    assert connected is False
    assert "Model discovery exceeded" in message
    assert "No request was replayed" in message
    assert discover.call_count == 1


@pytest.mark.parametrize("path,status", [("/api/models", 504), ("/api/health", 503)])
def test_discovery_timeout_returns_local_json(tmp_path, monkeypatch, path, status):
    clock = [0.0]
    monkeypatch.setattr(operations, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    def discover(model_path):
        clock[0] = client.CONTROL_TIMEOUT + 1
        return page("fictional-one", more=True)

    server = make_server(port=0, directory=tmp_path)
    server.app.preferences.update({
        "provider": "anthropic", "api_url": "https://api.anthropic.com/v1",
        "model": "fictional-one", "max_tokens": 64,
    }, confirm_endpoint=True, api_key="fictional-key")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.object(client, "_get", side_effect=discover) as discover:
            code, headers, raw = http_request(server, path)
        body = json.loads(raw)
        assert code == status
        assert headers["Content-Type"].startswith("application/json")
        assert "Model discovery exceeded" in body.get("error", body.get("message", ""))
        assert "fictional-key" not in raw.decode()
        assert discover.call_count == 1
    finally:
        server.shutdown()
        server.app.close()
        server.server_close()
        thread.join(timeout=5)


def test_shorter_enclosing_deadline_prevents_another_page(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(operations, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    def discover(path):
        clock[0] = 1
        return page("fictional-one", more=True)

    with patch.object(client, "_get", side_effect=discover) as request:
        with operations.budget(.5), pytest.raises(operations.DeadlineExceeded):
            client.list_models()
    assert request.call_count == 1


def test_enclosing_cancellation_prevents_another_page():
    cancellation = threading.Event()

    def discover(path):
        cancellation.set()
        return page("fictional-one", more=True)

    with patch.object(client, "_get", side_effect=discover) as request:
        with operations.budget(20, cancellation), pytest.raises(operations.Cancelled):
            client.list_models()
    assert request.call_count == 1


@pytest.mark.parametrize("provider,catalogue", [
    ("openai-compatible", page("fictional-compatible", more=True)),
    ("chatgpt", {"models": [{"slug": "fictional-plan", "visibility": "list",
                              "display_name": "Fictional plan model"}],
                 "has_more": True}),
])
def test_other_provider_catalogue_protocols_remain_single_request(provider, catalogue):
    with (
        client.connection_settings({"provider": provider}),
        patch.object(client, "_get", return_value=catalogue) as discover,
    ):
        models = client.list_models()
    if provider == "chatgpt":
        assert models == [{"id": "fictional-plan",
                           "display_name": "Fictional plan model"}]
    else:
        assert models == catalogue["data"]
    discover.assert_called_once_with("/models")
