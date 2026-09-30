"""Native protocol qualification, cancellation and local preservation, offline."""

import copy
import io
import json
import threading
import urllib.error
from email.message import Message as Headers
from unittest.mock import patch

import pytest

from sinter import client
from sinter.model_profiles import (
    NATIVE_CAPABILITIES,
    NATIVE_PROFILE,
    native_profile_applies,
    native_reply,
    native_request,
)
from sinter.operations import Cancelled, budget
from sinter.preferences import Preferences, validate
from sinter.providers import ProviderProtocolError


def connection(**changes):
    return {
        "provider": "openai-compatible",
        "api_url": client.BASE_URL,
        "model": client.NATIVE_MODEL,
        "max_tokens": 128,
        "api_key": "fixture-key",
        "inherit_key": False,
        **changes,
    }


def catalog(**metadata):
    return [
        {
            "id": client.NATIVE_MODEL,
            "erais": {
                **NATIVE_CAPABILITIES,
                "modalities": ["text"],
                "runtime_id": "0123456789abcdef0123456789abcdef",
                **metadata,
            },
        }
    ]


def completion(**changes):
    return {
        "object": "chat.completion",
        "model": client.NATIVE_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "A small answer."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 18, "completion_tokens": 4, "total_tokens": 22},
        **changes,
    }


class BufferedReply(io.BytesIO):
    def __init__(self, value, content_type="application/json"):
        super().__init__(
            value if isinstance(value, bytes) else json.dumps(value).encode()
        )
        self.headers = Headers()
        if content_type:
            self.headers["Content-Type"] = content_type


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
        lambda *args: pytest.fail("unexpected network request"),
    )


@pytest.mark.parametrize(
    "endpoint,provider",
    [
        ("https://neuroforge.io.attacker.test/v1", "openai-compatible"),
        ("https://custom.example/v1", "openai-compatible"),
        ("https://neuroforge.io/v1/other", "openai-compatible"),
        ("https://neuroforge.io:8443/v1", "openai-compatible"),
        ("http://neuroforge.io/v1", "openai-compatible"),
        ("https://neuroforge.io/v1?route=1", "openai-compatible"),
        ("https://neuroforge.io/v1#fragment", "openai-compatible"),
        ("https://user:pass@neuroforge.io/v1", "openai-compatible"),
        (client.BASE_URL, "chatgpt"),
        (client.BASE_URL, "anthropic"),
    ],
)
def test_native_name_does_not_qualify_other_destinations(endpoint, provider):
    assert not native_profile_applies(client.NATIVE_MODEL, endpoint, provider)


def test_native_selector_is_local_and_auto_requires_explicit_resolution():
    with (
        client.connection_settings(connection(model="auto")),
        patch.object(client, "_get") as discover,
    ):
        assert client.is_native_profile() is False
        assert client.is_native_profile(client.NATIVE_MODEL) is True
    discover.assert_not_called()


@pytest.mark.parametrize("selected", ["auto", client.NATIVE_MODEL])
@pytest.mark.parametrize(
    "metadata",
    [
        {"streaming": True},
        {"max_output_tokens": 512},
        {"max_prompt_bytes": 4096},
        {"assistant_quality": True},
        {"quality_scope": "qualified"},
        {"fully_native": 1},
        {"modalities": ["text", "image"]},
        {"runtime_id": "an-invented-runtime"},
    ],
)
def test_native_discovery_requires_exact_truthful_public_capabilities(
    selected, metadata
):
    with (
        client.connection_settings(connection(model=selected)),
        pytest.raises(client.APIError, match="contract"),
    ):
        client.resolve_model(catalog(**metadata))


def test_missing_native_discovery_metadata_is_not_qualified():
    with (
        client.connection_settings(connection(model="auto")),
        pytest.raises(client.APIError, match="verified"),
    ):
        client.resolve_model([{"id": client.NATIVE_MODEL}])


def test_valid_native_discovery_does_not_claim_general_assistant_quality():
    with client.connection_settings(connection(model="auto")):
        assert client.resolve_model(catalog()) == client.NATIVE_MODEL
    assert NATIVE_CAPABILITIES["assistant_quality"] is False
    assert NATIVE_CAPABILITIES["quality_scope"] == "unqualified_for_general_chat"


@pytest.mark.parametrize("value", [1, 31, 32, 64, 128])
def test_exact_native_request_token_limits_and_json_subset(value):
    body = native_request(
        {
            "model": client.NATIVE_MODEL,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": value,
        }
    )
    assert body == {
        "model": client.NATIVE_MODEL,
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": value,
        "stream": False,
        "n": 1,
    }


@pytest.mark.parametrize(
    "patch",
    [
        {"max_tokens": 0},
        {"max_tokens": 129},
        {"max_tokens": True},
        {"stream": True},
        {"stream": 0},
        {"n": 2},
        {"n": True},
        {"temperature": 0},
        {"tools": []},
        {"runtime_id": "owner"},
        {"messages": [{"role": "user", "content": "\0"}]},
        {"messages": [{"role": "user", "content": "\ud800"}]},
        {"messages": [{"role": "user", "content": "é" * 1025}]},
    ],
)
def test_native_request_rejects_outside_contract_without_projection(patch):
    with pytest.raises(ValueError):
        native_request(
            {
                "model": client.NATIVE_MODEL,
                "messages": [{"role": "user", "content": "Hello"}],
                **patch,
            }
        )


@pytest.mark.parametrize("stream", [False, True])
def test_native_complete_json_is_checked_before_text_is_exposed(stream):
    supplied = [client.Message("user", "One short question.")]
    reply = completion()
    reply["choices"][0]["message"]["tool_calls"] = []
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post", return_value=reply) as send,
    ):
        with pytest.raises(client.APIError, match="rejected"):
            if stream:
                next(client.chat_stream(supplied))
            else:
                client.chat(supplied)
    assert send.call_count == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("object", "text.completion"),
        ("model", client.MODEL),
        ("usage", None),
        ("choices", []),
    ],
)
def test_native_reply_requires_exact_envelope(field, value):
    with pytest.raises(ProviderProtocolError):
        native_reply(completion(**{field: value}), 128)


@pytest.mark.parametrize(
    "path,value",
    [
        (("choices", 0, "index"), True),
        (("choices", 0, "index"), 1),
        (("choices", 0, "message", "role"), "user"),
        (("choices", 0, "message", "content"), "\ud800"),
        (("choices", 0, "message", "content"), "\0"),
        (("choices", 0, "message", "content"), "é" * 4097),
        (("choices", 0, "message", "content"), " "),
        (("choices", 0, "finish_reason"), "tool_calls"),
        (("choices", 0, "finish_reason"), None),
        (("usage", "prompt_tokens"), 513),
        (("usage", "prompt_tokens"), 0),
        (("usage", "prompt_tokens"), True),
        (("usage", "completion_tokens"), 129),
        (("usage", "completion_tokens"), 0),
        (("usage", "total_tokens"), 23),
    ],
)
def test_native_reply_rejects_unsafe_text_completion_or_token_accounting(path, value):
    reply = completion()
    target = reply
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ProviderProtocolError):
        native_reply(reply, 128)


def test_native_reply_must_fit_actual_requested_output_limit():
    with pytest.raises(ProviderProtocolError):
        native_reply(completion(), 1)
    exact = completion(
        usage={"prompt_tokens": 512, "completion_tokens": 1, "total_tokens": 513}
    )
    assert native_reply(exact, 1).completion_tokens == 1


@pytest.mark.parametrize("content_type", ["text/event-stream", "text/html", ""])
def test_native_json_transport_rejects_wrong_or_missing_media_type(content_type):
    response = BufferedReply(completion(), content_type)
    body = {"model": client.NATIVE_MODEL, "max_tokens": 128, "stream": False}
    with (
        client.connection_settings(connection()),
        patch.object(client, "_open", return_value=response) as send,
    ):
        with pytest.raises(client.APIError, match="buffered JSON"):
            client._request_json("/chat/completions", body)
    assert response.closed and send.call_count == 1


def test_native_json_response_size_and_deadline_are_profile_bound():
    body = {"model": client.NATIVE_MODEL, "max_tokens": 128, "stream": False}
    response = BufferedReply(b" " * (NATIVE_PROFILE.response_bytes + 1))
    with (
        client.connection_settings(connection()),
        patch.object(client, "_open", return_value=response),
    ):
        assert client._request_timeout("/chat/completions", body) == 50.0
        with pytest.raises(client.APIError, match="safety limit"):
            client._request_json("/chat/completions", body)
    assert response.closed


def test_native_incomplete_json_eof_is_rejected_without_replay():
    response = BufferedReply(b'{"object":"chat.completion"')
    with (
        client.connection_settings(connection()),
        patch.object(client, "_open", return_value=response) as send,
    ):
        with pytest.raises(client.APIError, match="invalid JSON"):
            list(client.chat_stream([client.Message("user", "Hello")]))
    assert response.closed and send.call_count == 1


def test_native_cancellation_during_buffered_read_never_exposes_unverified_text():
    cancel = threading.Event()

    class CancelDuringRead(BufferedReply):
        def read(self, size):
            cancel.set()
            return super().read(size)

    response = CancelDuringRead(completion())
    with (
        client.connection_settings(connection()),
        budget(2, cancel),
        patch.object(client, "_open", return_value=response) as send,
    ):
        with pytest.raises(Cancelled):
            list(client.chat_stream([client.Message("user", "Hello")]))
    assert response.closed and send.call_count == 1


def test_native_admission_error_explains_token_limit_without_guessing_tokenizer():
    body = native_request(
        {
            "model": client.NATIVE_MODEL,
            "messages": [{"role": "user", "content": "Tiny input"}],
        }
    )
    error = urllib.error.HTTPError(
        client.BASE_URL, 400, "rejected", {}, io.BytesIO(b"private upstream detail")
    )
    opener = type(
        "Rejected", (), {"open": lambda *args, **kwargs: (_ for _ in ()).throw(error)}
    )()
    with (
        client.connection_settings(connection()),
        patch.object(client.urllib.request, "build_opener", return_value=opener),
    ):
        with pytest.raises(client.APIError, match="512-token") as failed:
            client._open("/chat/completions", body)
    assert failed.value.upstream_status == 400
    assert "private upstream detail" not in str(failed.value)
    assert "no request was replayed" in str(failed.value)


def test_native_preferences_minimum_does_not_apply_to_a_custom_name(tmp_path):
    native = validate({"model": client.NATIVE_MODEL, "max_tokens": 1})
    assert native["max_tokens"] == 1
    with pytest.raises(ValueError, match="32"):
        validate(
            {
                "api_url": "https://custom.example/v1",
                "model": client.NATIVE_MODEL,
                "max_tokens": 1,
            }
        )
    preferences = Preferences(tmp_path)
    preferences.update({"model": client.NATIVE_MODEL, "max_tokens": 128})
    preferences.update({"theme": "light"})
    restored = Preferences(tmp_path).snapshot()
    assert restored["model"] == client.NATIVE_MODEL and restored["max_tokens"] == 128


def test_custom_native_name_preserves_system_messages_budget_and_saved_settings(
    tmp_path,
):
    settings = connection(api_url="https://custom.example/v1", max_tokens=4096)
    reply = completion()
    reply["usage"]["prompt_tokens"] = 1000
    reply["usage"]["total_tokens"] = 1004
    supplied = [
        client.Message("system", "Keep this exact instruction."),
        client.Message("user", "Hello"),
    ]
    with (
        client.connection_settings(settings),
        patch.object(client, "_post", return_value=reply) as send,
    ):
        assert client.is_native_profile() is False
        assert client.chat(supplied, 4096).content == "A small answer."
    assert send.call_args.args[1]["max_tokens"] == 4096
    assert send.call_args.args[1]["messages"][0]["content"] == supplied[0].content
    preferences = Preferences(tmp_path)
    preferences.update(
        {
            "api_url": settings["api_url"],
            "model": settings["model"],
            "max_tokens": 4096,
        },
        confirm_endpoint=True,
    )
    preferences.update({"density": "compact"})
    assert Preferences(tmp_path).snapshot()["max_tokens"] == 4096


def test_model_selection_pins_generation_identity_without_losing_credentials():
    def callback():
        return "fixture-account-token"

    settings = connection(
        model="auto", account_token=callback, account_profile_id="fixture-profile"
    )
    original = copy.copy(settings)
    with (
        client.connection_settings(settings),
        patch.object(client, "list_models", return_value=catalog()) as discovery,
    ):
        selected = client.resolve_model()
        with client.model_selection(selected):
            assert client.resolve_model() == client.NATIVE_MODEL
            assert client._headers()["Authorization"] == "Bearer fixture-key"
            assert client._CONNECTION.get()["account_token"] is callback
            assert client._CONNECTION.get() == original
            assert client.connection_identity()["model"] == client.NATIVE_MODEL
        assert client.selected_model() == "auto"
    assert discovery.call_count == 1 and settings == original


def test_model_selection_restores_prior_selection_and_unset_connection_on_failure():
    with pytest.raises(RuntimeError):
        with client.model_selection(client.NATIVE_MODEL):
            assert client._CONNECTION.get() is None
            with client.model_selection(client.MODEL):
                assert client.selected_model() == client.MODEL
            assert client.selected_model() == client.NATIVE_MODEL
            raise RuntimeError("fixture")
    assert client.selected_model() == "auto" and client._CONNECTION.get() is None


def test_auto_discovery_applies_exact_profile_cap_without_discarding_legacy_budget():
    supplied = [client.Message("user", "One question.")]
    legacy = completion(model=client.MODEL)
    with (
        client.connection_settings(connection(model="auto", max_tokens=2048)),
        patch.object(client, "_get", return_value={"data": [{"id": client.MODEL}]}),
        patch.object(client, "_post", return_value=legacy) as send,
    ):
        assert client.chat(supplied, 2048).model == client.MODEL
    assert send.call_args.args[1]["max_tokens"] == 2048
