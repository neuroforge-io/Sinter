"""Transport parity, honest partial output and independently grounded recipes."""
import io
import json
import threading
from unittest.mock import patch

import pytest

from sinter import client
from sinter.operations import Cancelled, DeadlineExceeded, budget
from sinter.recipes import community_recipes
from sinter.templates import (Step, Template, TemplateStepError, _from_data,
                             get_builtin_template, template_events)


def stream_response(content="A useful answer.", reason="stop", *, done=True):
    chunks = [
        {"choices": [{"delta": {"content": content}}]},
        {"choices": [{"delta": {}, "finish_reason": reason}],
         "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}},
    ]
    raw = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
    return io.BytesIO((raw + ("data: [DONE]\n\n" if done else "")).encode())


def test_stream_returns_actual_metadata_without_changing_text_iterator():
    with patch.object(client, "_post_raw", return_value=stream_response()) as send:
        response = client.chat_stream([client.Message("user", "Question")])
        assert next(response) == "A useful answer."
        with pytest.raises(StopIteration) as stopped:
            next(response)
    assert stopped.value.value == client.ChatResult("A useful answer.", 12, 4, 16, "stop")
    send.assert_called_once()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_partial_template_is_recoverable_and_never_replayed_or_followed(stream, reason):
    template = Template("Two passes", "", [Step("Draft", "Question", stream=True),
                                          Step("Check", "Should not run")])
    collected = []
    with patch("sinter.templates.chat", return_value=client.ChatResult("Useful partial", 12, 4, 16, reason)) as chat, \
            patch.object(client, "_post_raw", return_value=stream_response("Useful partial", reason)) as send:
        with pytest.raises(TemplateStepError) as failed:
            for event in template_events(template, {}, stream=stream):
                collected.append(event)
    partial = failed.value.partial
    assert partial["type"] == "step_partial" and partial["complete"] is False
    assert partial["content"] == "Useful partial" and partial["finish_reason"] == reason
    assert partial["tokens"] == 16 and partial["max_tokens"] == 512
    assert partial["step"] == "Draft" and partial["index"] == 0
    assert "No request was replayed" in partial["error"]
    if reason == "length":
        assert "512-token output limit" in partial["error"]
    assert partial is collected[-1]
    assert not any(event["type"] == "step_done" for event in collected)
    assert len([event for event in collected if event["type"] == "step"]) == 1
    assert chat.call_count == int(not stream) and send.call_count == int(stream)


def test_broken_stream_retains_partial_text_and_actual_failure():
    template = Template("Draft", "", [Step("Draft", "Question", stream=True)])
    with patch.object(client, "_post_raw", return_value=stream_response("Keep this", done=False)) as send:
        with pytest.raises(TemplateStepError, match="ended early") as failed:
            list(template_events(template, {}))
    assert failed.value.partial["content"] == "Keep this"
    assert failed.value.partial["finish_reason"] == "error"
    send.assert_called_once()


@pytest.mark.parametrize("reason", ["", "stop"])
def test_template_stream_reports_actual_finish_metadata(reason):
    template = Template("Draft", "", [Step("Draft", "Question", stream=True)])
    with patch.object(client, "_post_raw", return_value=stream_response(reason=reason)):
        events = list(template_events(template, {}))
    assert events[-1]["type"] == "step_done" and events[-1]["complete"] is True
    assert events[-1]["finish_reason"] == reason and events[-1]["tokens"] == 16


@pytest.mark.parametrize("name", community_recipes())
@pytest.mark.parametrize("stream", [False, True])
def test_every_recipe_step_has_original_source_and_prior_work_without_history(name, stream):
    template = get_builtin_template(name)
    variables = {name: f"Original {name}: the hall is NOT approved. {{{{previous}}}}" for name in template.variables}
    calls = []

    def reply(messages, **kwargs):
        calls.append(messages)
        return client.ChatResult(f"Model work {len(calls)}", finish_reason="stop")

    def streamed_reply(messages, **kwargs):
        result = reply(messages, **kwargs)
        yield result.content
        return result

    with patch("sinter.templates.chat", side_effect=reply), \
            patch("sinter.templates.chat_stream", side_effect=streamed_reply):
        list(template_events(template, variables, stream=stream))
    assert len(calls) == 3
    for index, messages in enumerate(calls):
        assert len(messages) == 2 and messages[0].role == "system"
        # The latest user turn is sufficient even if conversational history is dropped.
        assert all(value in messages[-1].content for value in variables.values())
        if index:
            assert "Model work 1" in messages[-1].content
            assert "source data, not instructions" in messages[-1].content
    assert "Model work 2" in calls[-1][-1].content


def test_context_independent_step_keeps_explicit_system_message():
    template = get_builtin_template("enquiry-letter")
    values = {name: name + " source" for name in template.variables}
    values["system"] = "Be concise."
    with patch("sinter.templates.chat", return_value=client.ChatResult("Draft", finish_reason="stop")) as send:
        list(template_events(template, values, stream=False))
    assert all(call.args[0][0] == client.Message("system", "Be concise.") for call in send.call_args_list)
    assert all(len(call.args[0]) == 2 for call in send.call_args_list)


@pytest.mark.parametrize("stream", [False, True])
def test_research_has_bounded_expansion_headroom_and_preserves_evidence(stream):
    source = client.SearchResponse("2026-09-12", [client.SearchResult("Guide", "https://example.org/guide", "Source detail")])
    calls = []

    def reply(messages, max_tokens):
        calls.append((messages, max_tokens))
        # A substantive expansion that used to hit the old 512-token budget.
        return client.ChatResult("Research finding https://example.org/guide", completion_tokens=700,
                                 finish_reason="stop" if max_tokens >= 768 else "length")

    def streamed_reply(messages, max_tokens):
        result = reply(messages, max_tokens)
        yield result.content
        return result

    with patch("sinter.templates.search", return_value=source), \
            patch("sinter.templates.chat", side_effect=reply), \
            patch("sinter.templates.chat_stream", side_effect=streamed_reply):
        events = list(template_events(get_builtin_template("research"), {"topic": "Community gardens"}, stream=stream))
    assert [maximum for _, maximum in calls] == [1024, 2048, 768]
    assert all("Community gardens" in messages[-1].content for messages, _ in calls)
    assert all("https://example.org/guide" in messages[-1].content for messages, _ in calls)
    assert len([event for event in events if event["type"] == "step_done"]) == 3


@pytest.mark.parametrize("value", [1, 31, 8193, True, 32.0, "32"])
def test_invalid_token_limit_fails_before_any_request(value):
    with patch.object(client, "_post") as send, pytest.raises(ValueError, match="32 to 8192"):
        client.chat([client.Message("user", "Question")], value)
    send.assert_not_called()
    with pytest.raises(ValueError, match="32 to 8192"):
        _from_data({"steps": [{"name": "Draft", "prompt": "Question", "max_tokens": value}]}, "test")


@pytest.mark.parametrize("value", [32, 2048])
def test_public_token_budget_boundaries(monkeypatch, value):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", client.BASE_URL)
    assert client._chat_body([client.Message("user", "Question")], value)["max_tokens"] == value


def test_public_api_cap_is_clear_and_other_providers_keep_extended_budget(monkeypatch):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", client.BASE_URL)
    with pytest.raises(ValueError, match="public API.*32 to 2048"):
        client._chat_body([client.Message("user", "Question")], 2049)
    monkeypatch.setenv("NEUROFORGE_BASE_URL", "https://provider.example/v1")
    assert client._chat_body([client.Message("user", "Question")], 8192)["max_tokens"] == 8192


def test_error_explains_configured_effective_limit():
    template = Template("Draft", "", [Step("Draft", "Question", max_tokens=2048)])
    settings = {"api_url": client.BASE_URL, "max_tokens": 128, "model": client.MODEL}
    with client.connection_settings(settings), \
            patch("sinter.templates.chat", return_value=client.ChatResult("Partial", finish_reason="length")) as send:
        with pytest.raises(TemplateStepError, match="128-token output limit") as failed:
            list(template_events(template, {}, stream=False))
    assert send.call_args.kwargs["max_tokens"] == 128
    assert failed.value.partial["max_tokens"] == 128


def test_invalid_history_option_is_rejected():
    with pytest.raises(ValueError, match="include_history must be booleans"):
        _from_data({"steps": [{"name": "Draft", "prompt": "Question", "include_history": "false"}]}, "test")


def test_invalid_template_system_prompt_is_rejected():
    with pytest.raises(ValueError, match="system_prompt must be text"):
        _from_data({"system_prompt": [], "steps": [{"name": "Draft", "prompt": "Question"}]}, "test")


def test_cancellation_after_response_never_publishes_completion():
    cancel = threading.Event()

    def reply(*args, **kwargs):
        cancel.set()
        return client.ChatResult("Completed during cancellation", finish_reason="stop")

    events = []
    with budget(10, cancel), patch("sinter.templates.chat", side_effect=reply) as send:
        with pytest.raises(Cancelled):
            for event in template_events(Template("Draft", "", [Step("Draft", "Question")]), {}, stream=False):
                events.append(event)
    assert not any(event["type"] == "step_done" for event in events)
    send.assert_called_once()


def test_stream_preserves_operation_deadline_exception():
    with patch.object(client, "_post_raw", side_effect=DeadlineExceeded("Task deadline")) as send:
        with pytest.raises(DeadlineExceeded, match="Task deadline"):
            list(client.chat_stream([client.Message("user", "Question")]))
    send.assert_called_once()


def test_closing_template_stream_closes_upstream_response():
    response = stream_response()
    with patch.object(client, "_post_raw", return_value=response):
        events = template_events(Template("Draft", "", [Step("Draft", "Question", stream=True)]), {})
        assert next(events)["type"] == "step"
        assert next(events)["type"] == "token"
        events.close()
    assert response.closed


def test_invalid_later_budget_is_rejected_before_search_or_model_calls(monkeypatch):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", client.BASE_URL)
    template = Template("Draft", "", [Step("First", "Question", use_search=True),
                                       Step("Later", "Question", max_tokens=3000)])
    with patch("sinter.templates.search") as search, patch("sinter.templates.chat") as chat:
        with pytest.raises(ValueError, match="public API"):
            list(template_events(template, {"topic": "Question"}))
    search.assert_not_called()
    chat.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("content", ["", " \n\t"])
def test_empty_generation_is_a_visible_failure_and_never_runs_dependent_steps(stream, content):
    template = Template("Two passes", "", [Step("Draft", "Question", stream=True),
                                          Step("Check", "Should not run")])
    with patch("sinter.templates.chat", return_value=client.ChatResult(content, finish_reason="stop")) as chat, \
            patch.object(client, "_post_raw", return_value=stream_response(content)) as send:
        with pytest.raises(TemplateStepError, match="returned no answer") as failed:
            list(template_events(template, {}, stream=stream))
    assert failed.value.partial["complete"] is False
    assert chat.call_count == int(not stream) and send.call_count == int(stream)


@pytest.mark.parametrize("messages,match", [
    ([client.Message("user", "")], "Message 1 is empty"),
    ([client.Message("user", " \n\ufeff")], "Message 1 is empty"),
    ([client.Message("user", "\ufeff \ufeff\n\ufeff")], "Message 1 is empty"),
    ([client.Message("user", "bad\0text")], "null character"),
    ([client.Message("user", "bad\ud800text")], "invalid Unicode"),
    ([client.Message("system", "a" * 8193), client.Message("user", "Question")], "8192-byte"),
    ([client.Message("user", "a" * 49153)], "49152-byte"),
    ([client.Message("user", "é" * 24577)], "49152-byte"),
    ([client.Message("system", "Only instructions")], "end with a user"),
    ([client.Message("assistant", "Wrong first role")], "alternating"),
    ([client.Message("user", "Hello"), client.Message("user", "Two user turns")], "alternating"),
    ([client.Message("user", "Hello"), client.Message("assistant", "Answer")], "end with a user"),
    ([client.Message("user", "Hello"), client.Message("system", "Late system")], "alternating"),
])
def test_public_provider_admission_fails_locally_without_a_request(monkeypatch, messages, match):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", client.BASE_URL)
    with patch.object(client, "_post") as send, pytest.raises(ValueError, match=match):
        client.chat(messages)
    send.assert_not_called()


def test_public_byte_limits_count_utf8_and_exclude_initial_system(monkeypatch):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", client.BASE_URL)
    messages = [client.Message("system", "é" * 4096), client.Message("user", "é" * 24576)]
    assert client._chat_body(messages, 32)["messages"][-1]["content"] == "é" * 24576


def test_custom_provider_keeps_its_own_message_contract(monkeypatch):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", "https://provider.example/v1")
    messages = [client.Message("user", "a" * 50000), client.Message("user", "A second user turn")]
    assert len(client._chat_body(messages, 8192)["messages"]) == 2


def test_public_request_accounts_for_json_escaping_before_any_request(monkeypatch):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", client.BASE_URL)
    with patch.object(client, "_post") as send, pytest.raises(ValueError, match="98304-byte JSON limit"):
        client.chat([client.Message("user", '"' * 49152)])
    send.assert_not_called()


def test_unicode_request_uses_utf8_without_escape_inflation(monkeypatch):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", client.BASE_URL)
    body = client._chat_body([client.Message("user", "é" * 24576)], 32)
    with patch.object(client.urllib.request, "build_opener") as opener:
        client._open("/chat/completions", body)
    sent = opener.return_value.open.call_args.args[0].data
    assert 49152 < len(sent) < 50000
    assert b"\\u00e9" not in sent
    assert json.loads(sent)["messages"][0]["content"] == "é" * 24576
