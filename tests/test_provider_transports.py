"""Provider contracts, bounded failures and credential separation; no live calls."""

import io
import json
from unittest.mock import patch

import pytest

from sinter import client
from sinter.model_profiles import NATIVE_CAPABILITIES
from sinter.providers import ProviderProtocolError, transport_for


@pytest.mark.parametrize('endpoint, identified', [
    ('https://generativelanguage.googleapis.com/v1beta/openai', True),
    ('https://generativelanguage.googleapis.com.attacker.test/v1beta/openai',
     False),
    ('https://another.example/v1', False),
])
def test_gemini_client_identification_is_destination_bound(endpoint, identified):
    with client.connection_settings({
            'provider': 'openai-compatible', 'api_url': endpoint,
            'api_key': 'fictional-key', 'inherit_key': False}):
        headers = client._headers()
    assert ('x-goog-api-client' in headers) is identified
    if identified:
        assert headers['x-goog-api-client'] == f'sinter/{client.__version__}'


@pytest.fixture(autouse=True)
def isolated_network(monkeypatch):
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


def connection(
    provider="anthropic",
    model="claude-sonnet-4-6",
    maximum=512,
    endpoint="https://api.anthropic.com/v1",
    **extra,
):
    return {
        "provider": provider,
        "model": model,
        "max_tokens": maximum,
        "api_url": endpoint,
        "api_key": "fictional-provider-key",
        **extra,
    }


def messages(system=True):
    return (
        [client.Message("system", "Use evidence, never invent eligibility.")]
        if system
        else []
    ) + [client.Message("user", "What must we confirm?")]


def native_catalog():
    return {"data": [{"id": client.NATIVE_MODEL, "erais": {
        **NATIVE_CAPABILITIES, "modalities": ["text"],
        "runtime_id": "0123456789abcdef0123456789abcdef",
    }}]}


def native_completion(text="Short answer", reason="stop"):
    return {
        "object": "chat.completion", "model": client.NATIVE_MODEL,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                     "finish_reason": reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }


def events(rows, *, done=False):
    raw = "".join("data: " + json.dumps(row) + "\n\n" for row in rows)
    return io.BytesIO((raw + ("data: [DONE]\n\n" if done else "")).encode())


def anthropic_json(reason="end_turn", model="claude-sonnet-4-6"):
    return {
        "model": model,
        "role": "assistant",
        "type": "message",
        "content": [{"type": "text", "text": "Confirm the budget."}],
        "stop_reason": reason,
        "usage": {"input_tokens": 14, "output_tokens": 4},
    }


def anthropic_events(reason="end_turn", model="claude-sonnet-4-6"):
    return [
        {
            "type": "message_start",
            "message": {
                "model": model,
                "content": [],
                "usage": {"input_tokens": 14, "output_tokens": 1},
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": "Confirm "},
        },
        {"type": "ping"},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "the budget."},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": reason},
            "usage": {"output_tokens": 4},
        },
        {"type": "message_stop"},
    ]


def chatgpt_events(status="completed", error=None):
    response = {
        "model": "gpt-6.1-sol",
        "status": status,
        "usage": {"input_tokens": 18, "output_tokens": 5, "total_tokens": 23},
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Confirm the budget."}],
            }
        ],
    }
    if error:
        response["error"] = {"code": error, "message": "private upstream value"}
    if status == "incomplete":
        response["incomplete_details"] = {"reason": "max_output_tokens"}
    return [
        {"type": "response.created", "response": {"model": "gpt-6.1-sol"}},
        {"type": "response.output_text.delta", "delta": "Confirm the budget."},
        {"type": "response." + status, "response": response},
    ]


def chatgpt_connection(**extra):
    return connection(
        "chatgpt",
        "gpt-6.1-sol",
        endpoint="https://api.openai.com/v1",
        account_token=lambda: "fictional-oauth-token",
        **extra,
    )


def test_anthropic_request_and_json_result_preserve_system_and_usage():
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post", return_value=anthropic_json()) as send,
    ):
        result = client.chat(messages(), 768)
    path, body = send.call_args.args
    assert path == "/messages" and body["system"] == messages()[0].content
    assert body["messages"] == [{"role": "user", "content": messages()[-1].content}]
    assert body["max_tokens"] == 512
    assert result == client.ChatResult(
        "Confirm the budget.", 14, 4, 18, "stop", "claude-sonnet-4-6"
    )
    send.assert_called_once()


@pytest.mark.parametrize(
    "reason,normalized",
    [
        ("end_turn", "stop"),
        ("stop_sequence", "stop"),
        ("max_tokens", "length"),
        ("refusal", "refusal"),
    ],
)
def test_anthropic_finish_reason_mapping(reason, normalized):
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post", return_value=anthropic_json(reason)),
    ):
        assert client.chat(messages()).finish_reason == normalized


def test_anthropic_headers_do_not_send_bearer_or_public_credentials():
    with (
        client.connection_settings(connection()),
        patch.object(
            client, "_load_key", side_effect=AssertionError("public key read")
        ),
    ):
        headers = client._headers()
    assert headers["x-api-key"] == "fictional-provider-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in headers


def test_anthropic_stream_text_and_usage_match_json():
    completed = []
    with (
        client.connection_settings(connection()),
        patch.object(
            client, "_post_raw", return_value=events(anthropic_events())
        ) as send,
    ):
        text = "".join(
            client.chat_stream_result(messages(), on_result=completed.append)
        )
    assert text == "Confirm the budget."
    assert completed == [
        client.ChatResult(text, 14, 4, 18, "stop", "claude-sonnet-4-6")
    ]
    assert send.call_args.args[0] == "/messages"
    assert send.call_args.args[1]["stream"] is True
    send.assert_called_once()


@pytest.mark.parametrize("reason", ["max_tokens", "refusal", "tool_use", "pause_turn"])
def test_anthropic_partial_is_retained_and_never_replayed(reason):
    completed = []
    with (
        client.connection_settings(connection()),
        patch.object(
            client, "_post_raw", return_value=events(anthropic_events(reason))
        ) as send,
    ):
        iterator = client.chat_stream_result(messages(), on_result=completed.append)
        assert next(iterator) == "Confirm "
        assert next(iterator) == "the budget."
        with pytest.raises(client.IncompleteGeneration) as failed:
            next(iterator)
    assert failed.value.result.content == "Confirm the budget."
    assert not completed and send.call_count == 1


@pytest.mark.parametrize(
    "rows",
    [
        anthropic_events()[:-1],
        anthropic_events()[1:],
        [
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "bad"},
            }
        ],
        anthropic_events()[:1] + [{"type": "message_stop"}],
        anthropic_events()[:1]
        + [
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_use", "id": "no-execution"},
            }
        ],
        anthropic_events()[:1]
        + [{"type": "error", "error": {"message": "private upstream value"}}],
    ],
)
def test_anthropic_broken_or_unsupported_stream_never_reports_complete(rows):
    completed = []
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post_raw", return_value=events(rows)) as send,
    ):
        with pytest.raises(client.APIError) as failed:
            list(client.chat_stream_result(messages(), on_result=completed.append))
    assert not completed and send.call_count == 1
    assert "private upstream value" not in str(failed.value)


@pytest.mark.parametrize(
    "content", [None, [{"type": "tool_use"}], [{"type": "text", "text": 7}]]
)
def test_anthropic_nontext_json_rejected(content):
    reply = {**anthropic_json(), "content": content}
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post", return_value=reply),
    ):
        with pytest.raises(client.APIError):
            client.chat(messages())


def test_official_openai_uses_current_token_field_and_developer_instructions():
    settings = connection(
        "openai-compatible", "gpt-6.1-sol", endpoint="https://api.openai.com/v1"
    )
    reply = {
        "model": "gpt-6.1-sol",
        "choices": [{"message": {"content": "Answer"}, "finish_reason": "stop"}],
    }
    with (
        client.connection_settings(settings),
        patch.object(client, "_post", return_value=reply) as send,
    ):
        client.chat(messages())
    body = send.call_args.args[1]
    assert body["max_completion_tokens"] == 64 and "max_tokens" not in body
    assert body["messages"][0]["role"] == "developer"


@pytest.mark.parametrize(
    "endpoint,requested,actual",
    [
        ("https://api.openai.com/v1", "gpt-4.1", "gpt-4.1-2025-04-14"),
        (
            "https://api.anthropic.com/v1",
            "claude-haiku-4-5",
            "claude-haiku-4-5-20251001",
        ),
    ],
)
def test_documented_vendor_aliases_accept_only_dated_same_model(
    endpoint, requested, actual
):
    from sinter.providers import require_model

    assert require_model(actual, requested, endpoint) == actual
    for wrong in [None, "other-model", requested + "-made-up", actual + "-extra"]:
        with pytest.raises(ProviderProtocolError):
            require_model(wrong, requested, endpoint)
    with pytest.raises(ProviderProtocolError):
        require_model(actual, requested, "https://compatible.example/v1")


@pytest.mark.parametrize("stream", [False, True])
def test_native_auto_discovers_and_sends_one_nonstream_request(stream):
    reply = native_completion()
    settings = {"api_url": client.BASE_URL, "model": "auto", "max_tokens": 512}
    with (
        client.connection_settings(settings),
        patch.object(
            client, "_get", return_value=native_catalog()
        ),
        patch.object(client, "_post", return_value=reply) as send,
        patch.object(client, "_post_raw") as sse,
    ):
        result = (
            "".join(client.chat_stream(messages(False), 512))
            if stream
            else client.chat(messages(False), 512).content
        )
    assert result == "Short answer" and send.call_count == 1 and sse.call_count == 0
    assert send.call_args.args[1]["max_tokens"] == 128
    assert send.call_args.args[1].get("stream", False) is False
    assert "temperature" not in send.call_args.args[1]


@pytest.mark.parametrize("maximum", [1, 31, 32, 64, 128, 2048])
def test_native_token_minimum_and_ceiling_are_model_specific(maximum):
    with client.connection_settings(
        connection("openai-compatible", client.NATIVE_MODEL, maximum, client.BASE_URL)
    ):
        assert client.effective_max_tokens(maximum) == min(maximum, 128)
    if maximum < 32:
        with pytest.raises(ValueError, match="32"):
            client.validate_max_tokens(maximum)
    assert client.validate_max_tokens(maximum, model=client.NATIVE_MODEL) == maximum


@pytest.mark.parametrize(
    "supplied",
    [
        messages(),
        [client.Message("user", "🌱" * 513)],
        [
            client.Message("user", "u" * 2048),
            client.Message("assistant", "a" * 2049),
            client.Message("user", "next"),
        ],
        [
            client.Message("user" if index % 2 == 0 else "assistant", "turn")
            for index in range(9)
        ],
    ],
)
def test_native_unsupported_context_fails_before_generation_without_dropping_text(
    supplied,
):
    with (
        client.connection_settings(
            connection("openai-compatible", client.NATIVE_MODEL, 64, client.BASE_URL)
        ),
        patch.object(client, "_post") as send,
        patch.object(client, "_post_raw") as sse,
    ):
        with pytest.raises(ValueError):
            client.chat(supplied)
    send.assert_not_called()
    sse.assert_not_called()


def test_native_auto_discovery_revalidates_system_before_generation():
    settings = {"api_url": client.BASE_URL, "model": "auto", "max_tokens": 512}
    with (
        client.connection_settings(settings),
        patch.object(
            client, "_get", return_value=native_catalog()
        ),
        patch.object(client, "_post") as send,
    ):
        with pytest.raises(ValueError, match="system"):
            client.chat(messages())
    send.assert_not_called()


def test_native_partial_json_stream_is_available_and_not_replayed():
    reply = native_completion("Partial", "length")
    with (
        client.connection_settings(
            connection("openai-compatible", client.NATIVE_MODEL, 128, client.BASE_URL)
        ),
        patch.object(client, "_post", return_value=reply) as send,
    ):
        iterator = client.chat_stream(messages(False), 512)
        assert next(iterator) == "Partial"
        with pytest.raises(client.IncompleteGeneration) as failed:
            next(iterator)
    assert failed.value.result.content == "Partial" and failed.value.max_tokens == 128
    assert send.call_count == 1


@pytest.mark.parametrize(
    "provider,endpoint",
    [
        ("anthropic", "https://api.anthropic.com/v1"),
        ("openai-compatible", "http://127.0.0.1:8421/v1"),
        ("chatgpt", "https://api.openai.com/v1"),
    ],
)
def test_public_search_never_receives_external_provider_credentials(
    provider, endpoint, monkeypatch
):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", client.BASE_URL)
    monkeypatch.setenv("SINTER_API_KEY", "fictional-environment-key")
    calls = []

    def search(path, body):
        calls.append((client._endpoint(path), client._headers(), body))
        return {"results": [], "retrieved_at": "now"}

    with (
        client.connection_settings(
            connection(
                provider,
                "model",
                endpoint=endpoint,
                account_token=lambda: pytest.fail("search token read"),
            )
        ),
        patch.object(client, "_post", side_effect=search),
    ):
        client.search("community funding")
        assert client.selected_provider() == provider
    url, headers, body = calls[0]
    assert url == client.BASE_URL + "/search" and body == {"query": "community funding"}
    assert not {"Authorization", "x-api-key", "anthropic-version"} & headers.keys()


def test_chatgpt_oauth_header_is_locked_to_official_endpoint():
    token_calls = []
    settings = chatgpt_connection()
    settings["account_token"] = lambda: (
        token_calls.append(True) or "fictional-oauth-token"
    )
    with client.connection_settings(settings):
        assert client._headers()["Authorization"] == "Bearer fictional-oauth-token"
    assert token_calls == [True]
    settings["api_url"] = "https://compatible.example/v1"
    with (
        client.connection_settings(settings),
        pytest.raises(client.APIError, match="official"),
    ):
        client._headers()
    assert token_calls == [True]


def test_chatgpt_cannot_use_session_api_key_instead_of_account_token():
    settings = chatgpt_connection()
    del settings["account_token"]
    with (
        client.connection_settings(settings),
        pytest.raises(client.APIError, match="Sign in"),
    ):
        client._headers()


def test_chatgpt_account_refresh_failure_does_not_expose_tokens():
    settings = chatgpt_connection()
    settings["account_token"] = lambda: (_ for _ in ()).throw(
        RuntimeError("fictional-token-secret")
    )
    with (
        client.connection_settings(settings),
        pytest.raises(client.APIError, match="reconnect") as failed,
    ):
        client._headers()
    assert "fictional-token-secret" not in str(failed.value)


def test_chatgpt_preserves_safe_account_scope_recovery_message():
    from sinter.accounts import AccountError

    settings = chatgpt_connection()
    advice = "Allow Sinter to use your ChatGPT plan in ChatGPT settings."
    settings["account_token"] = lambda: (_ for _ in ()).throw(AccountError(advice))
    with client.connection_settings(settings), pytest.raises(client.APIError) as failed:
        client._headers()
    assert str(failed.value) == advice


@pytest.mark.parametrize(
    "query",
    ["a", "x" * 161, "word " * 25, "funding https://example.org", "topic \ud800"],
)
def test_public_search_contract_is_validated_before_dispatch(query):
    with patch.object(client, "_post") as send, pytest.raises(ValueError):
        client.search(query)
    send.assert_not_called()


def test_chatgpt_model_catalog_preserves_visible_order_and_labels():
    catalog = {
        "models": [
            {"slug": "gpt-6.1-sol", "display_name": "Model A", "visibility": "list"},
            {"slug": "hidden", "display_name": "Hidden", "visibility": "hide"},
            {"slug": "gpt-6-astra", "display_name": "Model B", "visibility": "list"},
        ]
    }
    with (
        client.connection_settings(chatgpt_connection()),
        patch.object(client, "_get", return_value=catalog),
    ):
        assert client.list_models() == [
            {"id": "gpt-6.1-sol", "display_name": "Model A"},
            {"id": "gpt-6-astra", "display_name": "Model B"},
        ]


@pytest.mark.parametrize("stream", [False, True])
def test_chatgpt_uses_required_stream_only_responses_body_and_completion(stream):
    with (
        client.connection_settings(chatgpt_connection()),
        patch.object(
            client, "_post_raw", return_value=events(chatgpt_events())
        ) as send,
        patch.object(client, "_post") as json_send,
    ):
        result = (
            "".join(client.chat_stream(messages()))
            if stream
            else client.chat(messages()).content
        )
    assert result == "Confirm the budget." and send.call_count == 1
    json_send.assert_not_called()
    path, body = send.call_args.args
    assert path == "/responses"
    assert set(body) == {"model", "input", "store", "stream"}
    assert body["input"][0]["role"] == "developer"
    assert body["input"][-1]["role"] == "user"
    assert body["stream"] is True and body["store"] is False


@pytest.mark.parametrize(
    "status,error",
    [
        ("incomplete", None),
        ("failed", "subscription_sharing_usage_limit_exceeded"),
        ("failed", "subscription_sharing_usage_unavailable"),
        ("failed", "unrecognized_private_error"),
    ],
)
def test_chatgpt_terminal_failure_preserves_partial_and_does_not_report_success(
    status, error
):
    completed = []
    with (
        client.connection_settings(chatgpt_connection()),
        patch.object(
            client, "_post_raw", return_value=events(chatgpt_events(status, error))
        ) as send,
    ):
        iterator = client.chat_stream_result(messages(), on_result=completed.append)
        assert next(iterator) == "Confirm the budget."
        with pytest.raises(client.IncompleteGeneration) as failed:
            next(iterator)
    assert failed.value.result.content == "Confirm the budget."
    assert "private upstream" not in str(failed.value)
    assert not completed and send.call_count == 1


@pytest.mark.parametrize(
    "rows",
    [
        chatgpt_events()[:-1],
        chatgpt_events()[1:],
        chatgpt_events()[:1] + [{"type": "error", "message": "private upstream"}],
    ],
)
def test_chatgpt_interrupted_or_invalid_stream_is_not_success(rows):
    with (
        client.connection_settings(chatgpt_connection()),
        patch.object(client, "_post_raw", return_value=events(rows)) as send,
    ):
        with pytest.raises(client.APIError) as failed:
            list(client.chat_stream(messages()))
    assert "private upstream" not in str(failed.value) and send.call_count == 1


def test_unknown_provider_rejected_without_transport():
    with pytest.raises(ValueError, match="supported"):
        transport_for("invented")


def test_connection_identity_excludes_credentials_and_account_callbacks():
    settings = chatgpt_connection(account_profile_id="profile-fixture")
    with client.connection_settings(settings):
        identity = client.connection_identity()
    assert identity == {
        "provider": "chatgpt",
        "api_url": "https://api.openai.com/v1",
        "model": "gpt-6.1-sol",
        "max_tokens": 512,
        "account_profile_id": "profile-fixture",
    }
    assert "fictional-provider-key" not in json.dumps(identity)
    assert "fictional-oauth-token" not in json.dumps(identity)


def test_explicit_native_preflight_has_no_network_or_credentials():
    settings = connection("openai-compatible", client.NATIVE_MODEL, 64, client.BASE_URL)
    with (
        client.connection_settings(settings),
        patch.object(client, "_get") as discover,
        patch.object(client, "_headers", side_effect=AssertionError("credential read")),
    ):
        client.validate_chat_request(messages(False))
        with pytest.raises(ValueError, match="system"):
            client.validate_chat_request(messages())
    discover.assert_not_called()


def test_chatgpt_completed_text_mismatch_is_not_success():
    rows = chatgpt_events()
    rows[-1]["response"]["output"][0]["content"][0]["text"] = "Different text."
    with (
        client.connection_settings(chatgpt_connection()),
        patch.object(client, "_post_raw", return_value=events(rows)),
    ):
        with pytest.raises(client.APIError, match="did not match"):
            list(client.chat_stream(messages()))


def test_anthropic_json_requires_a_terminal_reason():
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post", return_value=anthropic_json(None)),
    ):
        with pytest.raises(client.APIError, match="completion reason"):
            client.chat(messages())


def test_chatgpt_output_limit_does_not_claim_local_token_cap_was_applied():
    with (
        client.connection_settings(chatgpt_connection()),
        pytest.raises(client.IncompleteGeneration) as failed,
    ):
        client.require_complete(
            client.ChatResult("Partial", finish_reason="length"), 512
        )
    assert "provider-controlled" in str(failed.value)
    assert "512-token" not in str(failed.value)


def test_provider_sse_byte_bound_prevents_unbounded_output():
    with (
        client.connection_settings(connection()),
        patch.object(client, "MAX_RESPONSE", 50),
        patch.object(
            client, "_post_raw", return_value=events(anthropic_events())
        ) as send,
    ):
        with pytest.raises(client.APIError, match="safety limit"):
            list(client.chat_stream(messages()))
    assert send.call_count == 1


def test_chatgpt_stream_terminal_model_change_is_rejected():
    rows = chatgpt_events()
    rows[-1]["response"]["model"] = "gpt-6-astra"
    with (
        client.connection_settings(chatgpt_connection()),
        patch.object(client, "_post_raw", return_value=events(rows)),
    ):
        iterator = client.chat_stream(messages())
        assert next(iterator) == "Confirm the budget."
        with pytest.raises(client.APIError, match="model did not match"):
            next(iterator)


def test_auto_native_json_partial_reports_actual_model_and_limit():
    settings = {"api_url": client.BASE_URL, "model": "auto", "max_tokens": 512}
    reply = native_completion("Partial", "length")
    with (
        client.connection_settings(settings),
        patch.object(
            client, "_get", return_value=native_catalog()
        ),
        patch.object(client, "_post", return_value=reply),
    ):
        result = client.chat(messages(False), 512)
        assert result.model == client.NATIVE_MODEL
        with pytest.raises(client.IncompleteGeneration) as failed:
            client.require_complete(result, 512)
    assert failed.value.max_tokens == 128
    assert "128-token" in str(failed.value)
