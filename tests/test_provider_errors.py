"""Safe ChatGPT failure advice from real stream shapes; no remote requests."""

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from sinter import client, providers
from sinter.operations import Cancelled, DeadlineExceeded


def connection():
    return {
        "provider": "chatgpt",
        "api_url": "https://api.openai.com/v1",
        "model": "gpt-6.1-sol",
        "max_tokens": 512,
        "account_token": lambda: "private-token-sentinel",
        "inherit_key": False,
    }


def stream(rows):
    return io.BytesIO(
        "".join("data: " + json.dumps(row) + "\n\n" for row in rows).encode()
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(
        client.urllib.request,
        "build_opener",
        lambda *args: pytest.fail("unexpected remote request"),
    )


@pytest.mark.parametrize("shape", ["event", "envelope", "failed"])
@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize(
    "code, advice",
    [
        ("subscription_sharing_usage_limit_exceeded", "Sinter's app limit"),
        ("subscription_sharing_usage_unavailable", "try again later"),
        ("subscription_sharing_user_not_eligible", "eligible connection"),
        ("subscription_sharing_invalid_user", "validate the selected account"),
        ("chatpass_v2_scope_not_authorized", "granted permissions"),
        ("server_error", "service error"),
        ("rate_limit_exceeded", "rate limit"),
    ],
)
def test_documented_stream_failures_keep_safe_code_and_partial_without_replay(
    shape,
    partial,
    code,
    advice,
):
    error = {
        "code": code,
        "message": "private-message-sentinel",
        "param": "private-param-sentinel",
    }
    rows = []
    if partial or shape == "failed":
        rows.append({"type": "response.created", "response": {"model": "gpt-6.1-sol"}})
    if partial:
        rows.append({"type": "response.output_text.delta", "delta": "Partial"})
    if shape == "event":
        rows.append({"type": "error", "sequence_number": 2, **error})
    elif shape == "envelope":
        rows.append({"error": error})
    else:
        rows.append(
            {
                "type": "response.failed",
                "response": {
                    "model": "gpt-6.1-sol",
                    "status": "failed",
                    "error": error,
                },
            }
        )
    completed = []
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post_raw", return_value=stream(rows)) as send,
    ):
        iterator = client.chat_stream_result(
            [client.Message("user", "Give a short answer")], on_result=completed.append
        )
        if partial:
            assert next(iterator) == "Partial"
        with pytest.raises(client.APIError) as failure:
            list(iterator)
    assert advice in str(failure.value)
    assert failure.value.error_code == code
    assert failure.value.upstream_status is None
    assert "No request was replayed." in str(failure.value)
    assert "private-" not in str(failure.value)
    if partial:
        assert isinstance(failure.value, client.IncompleteGeneration)
        assert failure.value.result.content == "Partial"
    assert not completed and send.call_count == 1


@pytest.mark.parametrize(
    "code",
    [
        None,
        "private-code-sentinel",
        "a" * 10000,
        ["server_error"],
        {"code": "server_error"},
    ],
)
def test_unknown_or_malformed_error_fields_stay_private(code):
    failure = providers.chatgpt_failure(
        {
            "code": code,
            "message": "private-message-sentinel",
            "param": "private-param-sentinel",
            "status": 429,
        }
    )
    assert failure.code == ""
    assert failure.upstream_status is None
    assert "private-" not in failure.message
    assert "usage limit" not in failure.message
    assert len(failure.message) < 200


@pytest.mark.parametrize(
    "status, body, code, advice",
    [
        (
            429,
            {
                "error": {
                    "code": "subscription_sharing_usage_limit_exceeded",
                    "message": "private-message-sentinel",
                }
            },
            "subscription_sharing_usage_limit_exceeded",
            "Sinter's app limit",
        ),
        (403, {"detail": "private-detail-sentinel"}, "", "permissions and policy"),
        (401, {"error": {"code": "private-code-sentinel"}}, "", "granted permissions"),
        (503, {"detail": "private-detail-sentinel"}, "", "routing or capacity"),
    ],
)
def test_http_admission_errors_keep_actual_status_without_upstream_text(
    monkeypatch,
    status,
    body,
    code,
    advice,
):
    failure = urllib.error.HTTPError(
        "https://api.openai.com/v1/responses",
        status,
        "private-reason-sentinel",
        {},
        io.BytesIO(json.dumps(body).encode()),
    )

    class Opener:
        def open(self, request, timeout):
            raise failure

    monkeypatch.setattr(client.urllib.request, "build_opener", lambda *args: Opener())
    with (
        client.connection_settings(connection()),
        pytest.raises(client.APIError) as caught,
    ):
        client._open("/responses", {"stream": True})
    assert caught.value.upstream_status == status
    assert caught.value.error_code == code
    assert f"Upstream HTTP status: {status}." in str(caught.value)
    assert advice in str(caught.value)
    assert "private-" not in str(caught.value)
    assert failure.fp is None or failure.fp.closed


def test_usage_limit_advice_never_infers_full_plan_exhaustion_or_reset():
    failure = providers.chatgpt_failure(
        {"code": "subscription_sharing_usage_limit_exceeded"}
    )
    assert "which limit applies or its reset time" in failure.message
    temporary = providers.chatgpt_failure(
        {"code": "subscription_sharing_usage_unavailable"}
    )
    assert (
        "temporarily" not in temporary.message or "try again later" in temporary.message
    )
    assert "eligibility" not in temporary.message


def test_interleaved_text_segments_reconcile_by_documented_indexes():
    rows = [
        {"type": "response.created", "response": {"model": "gpt-6.1-sol"}},
        {
            "type": "response.output_text.delta",
            "output_index": 1,
            "content_index": 0,
            "delta": "Second",
        },
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "content_index": 0,
            "delta": "First",
        },
        {
            "type": "response.completed",
            "response": {
                "model": "gpt-6.1-sol",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "First"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Second"}],
                    },
                ],
            },
        },
    ]
    completed = []
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post_raw", return_value=stream(rows)) as send,
    ):
        assert list(
            client.chat_stream_result(
                [client.Message("user", "Two points")], on_result=completed.append
            )
        ) == ["Second", "First"]
    assert completed[0].content == "FirstSecond"
    assert completed[0].finish_reason == "stop" and send.call_count == 1


@pytest.mark.parametrize("indexed", [False, True])
def test_actual_completion_mismatch_preserves_verified_partial_with_safe_counts(
    indexed,
):
    delta = {"type": "response.output_text.delta", "delta": "Received text"}
    if indexed:
        delta.update(output_index=0, content_index=0)
    rows = [
        {"type": "response.created", "response": {"model": "gpt-6.1-sol"}},
        delta,
        {
            "type": "response.completed",
            "response": {
                "model": "gpt-6.1-sol",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Unmatched private text"}
                        ],
                    },
                ],
            },
        },
    ]
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post_raw", return_value=stream(rows)) as send,
    ):
        with pytest.raises(client.IncompleteGeneration) as failure:
            list(client.chat_stream([client.Message("user", "One point")]))
    assert failure.value.result.content == "Received text"
    assert failure.value.result.model == "gpt-6.1-sol"
    assert failure.value.result.finish_reason == "error"
    assert "13 streamed / 22 final characters" in str(failure.value)
    assert "Unmatched private text" not in str(failure.value)
    assert send.call_count == 1


@pytest.mark.parametrize("ending", ["eof", "json", "protocol", "network", "deadline"])
def test_stream_interruption_keeps_only_verified_partial_text(ending):
    prefix = stream(
        [
            {"type": "response.created", "response": {"model": "gpt-6.1-sol"}},
            {"type": "response.output_text.delta", "delta": "Verified partial"},
        ]
    ).getvalue()
    if ending == "json":
        reply = io.BytesIO(prefix + b"data: {malformed\n\n")
    elif ending == "protocol":
        reply = io.BytesIO(prefix + b"data: []\n\n")
    elif ending in {"network", "deadline"}:

        class Interrupted(io.BytesIO):
            def readline(self, *args):
                if self.tell() >= len(prefix):
                    if ending == "deadline":
                        raise DeadlineExceeded("private-deadline-sentinel")
                    raise OSError("private-network-sentinel")
                return super().readline(*args)

        reply = Interrupted(prefix)
    else:
        reply = io.BytesIO(prefix)
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post_raw", return_value=reply) as send,
    ):
        with pytest.raises(client.IncompleteGeneration) as failure:
            list(client.chat_stream([client.Message("user", "One point")]))
    assert failure.value.result.content == "Verified partial"
    assert failure.value.result.model == "gpt-6.1-sol"
    assert failure.value.result.finish_reason == "incomplete"
    assert "private-" not in str(failure.value)
    assert "No request was replayed." in str(failure.value)
    assert send.call_count == 1 and reply.closed


def test_wrong_model_after_valid_prefix_is_rejected_without_partial_endorsement():
    rows = [
        {"type": "response.created", "response": {"model": "gpt-6.1-sol"}},
        {"type": "response.output_text.delta", "delta": "Valid prefix"},
        {"type": "response.in_progress", "response": {"model": "wrong-model"}},
        {"type": "response.output_text.delta", "delta": "Attacker text"},
    ]
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post_raw", return_value=stream(rows)) as send,
    ):
        with pytest.raises(client.APIError, match="did not match") as failure:
            list(client.chat_stream([client.Message("user", "One point")]))
    assert not isinstance(failure.value, client.IncompleteGeneration)
    assert "Attacker text" not in str(failure.value)
    assert send.call_count == 1


def test_user_cancellation_does_not_turn_into_a_partial_report():
    prefix = stream(
        [
            {"type": "response.created", "response": {"model": "gpt-6.1-sol"}},
            {"type": "response.output_text.delta", "delta": "Valid prefix"},
        ]
    ).getvalue()

    class CancelledReply(io.BytesIO):
        def readline(self, *args):
            if self.tell() >= len(prefix):
                raise Cancelled()
            return super().readline(*args)

    reply = CancelledReply(prefix)
    with (
        client.connection_settings(connection()),
        patch.object(client, "_post_raw", return_value=reply) as send,
    ):
        with pytest.raises(Cancelled):
            list(client.chat_stream([client.Message("user", "One point")]))
    assert send.call_count == 1 and reply.closed
