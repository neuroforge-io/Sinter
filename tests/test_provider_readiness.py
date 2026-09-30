"""Destination-bound readiness and safe HTTP evidence, wholly offline."""

import copy
import io
import json
import urllib.error
from email.message import Message as Headers
from unittest.mock import patch

import pytest

from sinter import assistant, client
from sinter.model_profiles import NATIVE_CAPABILITIES, NATIVE_PROFILE


def connection(**changes):
    return {
        "provider": "openai-compatible",
        "api_url": client.BASE_URL,
        "model": "auto",
        "max_tokens": 512,
        "api_key": "fictional-readiness-key",
        "inherit_key": False,
        **changes,
    }


def native_catalog():
    return {
        "object": "list",
        "data": [
            {
                "id": client.NATIVE_MODEL,
                "object": "model",
                "created": 0,
                "owned_by": "neuroforge",
                "erais": {
                    **NATIVE_CAPABILITIES,
                    "modalities": ["text"],
                    "runtime_id": "0123456789abcdef0123456789abcdef",
                },
            }
        ],
    }


class BufferedReply(io.BytesIO):
    def __init__(self, value, content_type="application/json"):
        super().__init__(json.dumps(value).encode("utf-8"))
        self.headers = Headers()
        if content_type:
            self.headers["Content-Type"] = content_type


class FictionalStore:
    """Only this explicitly fictional in-memory document can be read."""

    def __init__(self, quote="A wholly fictional condition."):
        self.saved = {
            "revision": 1,
            "document": {
                "title": "Fictional readiness exercise",
                "organisation": "Fictional Example Club",
                "objective": "Practise reading wholly fictional recorded conditions.",
                "opportunities": [
                    {
                        "name": "Fictional Example Route",
                        "status": "researching",
                        "application_mode": "unknown",
                        "applicant": "Fictional Club",
                        "applicant_confirmed": False,
                        "deadline": "",
                        "application_window": "unknown",
                        "window_source_quote": "",
                        "window_checked_at": "",
                    }
                ],
                "requirements": [
                    {
                        "opportunity": "Fictional Example Route",
                        "rule": "Fictional rule",
                        "status": "unknown",
                        "evidence": "",
                        "source_id": "",
                        "source_url": "",
                        "source_quote": quote,
                        "checked_at": "",
                    }
                ],
                "sources": [],
                "actions": [],
            },
        }

    def get(self, identifier):
        assert identifier == "fictional-readiness-record"
        return copy.deepcopy(self.saved)


def payload():
    return {
        "id": "fictional-readiness-record",
        "revision": 1,
        "opportunity": "Fictional Example Route",
        "checks": [0],
        "task": "eligibility",
        "question": "",
    }


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in (
        "NEUROFORGE_MODEL",
        "NEUROFORGE_BASE_URL",
        "NEUROFORGE_API_KEY",
        "SINTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        client.urllib.request,
        "build_opener",
        lambda *args: pytest.fail("unexpected outbound request"),
    )
    monkeypatch.setattr(
        client, "_load_key", lambda: pytest.fail("unexpected credential access")
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        client.BASE_URL,
        "https://neuroforge.io:443/v1",
        "https://NEUROFORGE.IO/v1",
        "https://neuroforge.io/v1/",
    ],
)
def test_official_auto_aliases_refuse_oversized_preview_without_discovery(endpoint):
    quote = "Wholly fictional neutral excerpt. " * 90
    store, request = FictionalStore(quote), payload()
    before = copy.deepcopy(store.saved)
    with (
        client.connection_settings(connection(api_url=endpoint)),
        patch.object(client, "_get", side_effect=AssertionError("No discovery")),
        patch.object(client, "_headers", side_effect=AssertionError("No credentials")),
        patch.object(client, "chat") as generate,
    ):
        prepared = assistant.preview(store, request)
        assert prepared["bytes"] > NATIVE_PROFILE.max_question_bytes
        assert prepared["fit"]["allowed"] is False
        assert "native ERAIS preview size" in prepared["fit"]["message"]
        assert prepared["context"]["selected_checks"][0]["source_quote"] == quote
        with pytest.raises(ValueError, match="native ERAIS preview size"):
            assistant.run(
                store,
                {**request, "consent": True, "context_hash": prepared["context_hash"]},
            )
    generate.assert_not_called()
    assert store.saved == before


def test_short_official_auto_preview_preserves_local_readiness_without_discovery():
    with (
        client.connection_settings(connection(api_url="https://neuroforge.io:443/v1")),
        patch.object(client, "_get", side_effect=AssertionError("No discovery")),
        patch.object(client, "_headers", side_effect=AssertionError("No credentials")),
    ):
        prepared = assistant.preview(FictionalStore(), payload())
    assert prepared["bytes"] <= NATIVE_PROFILE.max_question_bytes
    assert prepared["fit"]["allowed"] is True


@pytest.mark.parametrize(
    "provider,endpoint",
    [
        ("openai-compatible", "https://fictional-provider.example/v1"),
        ("openai-compatible", "https://api.openai.com/v1"),
        ("anthropic", "https://api.anthropic.com/v1"),
        ("chatgpt", "https://api.openai.com/v1"),
    ],
)
def test_external_auto_refuses_request_and_assistant_preview_locally(
    provider, endpoint
):
    store, request = FictionalStore(), payload()
    before = copy.deepcopy(store.saved)
    with (
        client.connection_settings(connection(provider=provider, api_url=endpoint)),
        patch.object(client, "_get", side_effect=AssertionError("No discovery")),
        patch.object(client, "_headers", side_effect=AssertionError("No credentials")),
        patch.object(client, "chat") as generate,
    ):
        with pytest.raises(ValueError, match="automatic selection.*NeuroForge"):
            client.validate_chat_request([client.Message("user", "Fictional question")])
        prepared = assistant.preview(store, request)
        assert prepared["fit"]["allowed"] is False
        assert "automatic selection" in prepared["fit"]["message"]
        with pytest.raises(ValueError, match="automatic selection"):
            assistant.run(
                store,
                {**request, "consent": True, "context_hash": prepared["context_hash"]},
            )
    generate.assert_not_called()
    assert store.saved == before


def test_custom_native_name_keeps_its_larger_context_and_configured_model_label():
    settings = connection(
        api_url="https://fictional-provider.example/v1",
        model=client.NATIVE_MODEL,
        max_tokens=4096,
    )
    quote = "Wholly fictional neutral excerpt. " * 90
    with client.connection_settings(settings):
        prepared = assistant.preview(FictionalStore(quote), payload())
        assert prepared["bytes"] > NATIVE_PROFILE.max_question_bytes
        assert prepared["fit"]["allowed"] is True
        assert client.is_native_profile() is False
        assert client.effective_max_tokens(4096) == 4096
        with patch.object(
            client, "list_models", return_value=[{"id": client.NATIVE_MODEL}]
        ):
            ready, message = client.health_check()
    assert ready is True
    assert "configured model" in message
    assert "native ERAIS" not in message


@pytest.mark.parametrize(
    "model", [client.NATIVE_MODEL, client.DENSE_MODEL, client.MODEL]
)
def test_custom_catalog_names_do_not_inherit_public_architecture_labels(model):
    with (
        client.connection_settings(
            connection(api_url="https://fictional-provider.example/v1", model=model)
        ),
        patch.object(client, "list_models", return_value=[{"id": model}]),
    ):
        ready, message = client.health_check()
    assert ready is True and "configured model" in message
    assert "native ERAIS" not in message and "dense Gemma" not in message
    assert "Fracture hybrid" not in message


@pytest.mark.parametrize("content_type", ["text/html", "text/event-stream", ""])
def test_official_catalog_wrong_media_cannot_claim_readiness(content_type):
    response = BufferedReply(native_catalog(), content_type)
    with (
        client.connection_settings(connection()),
        patch.object(client, "_open", return_value=response) as discover,
        patch.object(response, "read", wraps=response.read) as read,
        patch.object(client, "chat") as generate,
    ):
        ready, message = client.health_check()
    assert ready is False
    assert "catalogue" in message and "JSON" in message
    assert "No generation request was sent" in message
    read.assert_not_called()
    assert response.closed and discover.call_count == 1
    generate.assert_not_called()


@pytest.mark.parametrize(
    "content_type", ["application/json", "Application/JSON; charset=utf-8"]
)
def test_official_catalog_json_media_keeps_verified_native_identity(content_type):
    response = BufferedReply(native_catalog(), content_type)
    with (
        client.connection_settings(connection(api_url="https://neuroforge.io:443/v1")),
        patch.object(client, "_open", return_value=response) as discover,
    ):
        ready, message = client.health_check()
    assert ready is True and "native ERAIS; short text preview" in message
    assert "generation has not been tested" in message
    assert response.closed and discover.call_count == 1


def test_custom_catalog_media_does_not_inherit_neuroforge_qualification():
    response = BufferedReply({"data": [{"id": client.NATIVE_MODEL}]}, "text/html")
    with (
        client.connection_settings(
            connection(
                api_url="https://fictional-provider.example/v1",
                model=client.NATIVE_MODEL,
            )
        ),
        patch.object(client, "_open", return_value=response),
    ):
        ready, message = client.health_check()
    assert ready is True and "configured model" in message
    assert response.closed


@pytest.mark.parametrize("status", [404, 503, 504])
def test_generic_http_failures_retain_status_without_raw_body_or_replay(status):
    body = io.BytesIO(
        b'{"error":{"code":"fictional-only-code","message":"RAW_SENTINEL"}}'
    )
    failure = urllib.error.HTTPError(
        "https://fictional-provider.example/v1/models",
        status,
        "RAW_REASON_SENTINEL",
        {},
        body,
    )

    class Rejected:
        def __init__(self):
            self.calls = 0

        def open(self, request, timeout):
            self.calls += 1
            raise failure

    opener = Rejected()
    with (
        client.connection_settings(
            connection(
                api_url="https://fictional-provider.example/v1", model="fictional-model"
            )
        ),
        patch.object(client.urllib.request, "build_opener", return_value=opener),
        patch.object(
            body, "read", side_effect=AssertionError("Do not parse upstream bodies")
        ),
        pytest.raises(client.APIError) as caught,
    ):
        client._open("/models")
    assert caught.value.status == 502
    assert caught.value.upstream_status == status
    assert caught.value.error_code == ""
    assert "SENTINEL" not in str(caught.value)
    assert "fictional-only-code" not in str(caught.value)
    assert body.closed and opener.calls == 1
