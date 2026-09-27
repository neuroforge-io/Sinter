"""Hosted-model identity and admission regressions; no provider is contacted."""
import io
import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from sinter import client, review
from sinter.jobs import Jobs
from sinter.operations import Cancelled, DeadlineExceeded, budget
from sinter.preferences import Preferences
from sinter.server import _Disconnected


@pytest.fixture(autouse=True)
def isolated_connection(monkeypatch):
    for key in ("NEUROFORGE_MODEL", "NEUROFORGE_BASE_URL", "NEUROFORGE_API_KEY", "SINTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(client.urllib.request, "build_opener",
                        lambda *args: pytest.fail("unexpected outbound request"))


def reply(model=client.DENSE_MODEL):
    return {"model": model, "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}}


def stream_reply(model=client.DENSE_MODEL):
    rows = [{"model": model, "choices": [{"delta": {"content": "Hello"}}]},
            {"model": model, "choices": [{"delta": {}, "finish_reason": "stop"}]}]
    return io.BytesIO(("".join("data: " + json.dumps(row) + "\n\n" for row in rows)
                       + "data: [DONE]\n\n").encode())


def settings(model=client.DENSE_MODEL, maximum=64, endpoint=client.BASE_URL):
    return {"api_url": endpoint, "model": model, "max_tokens": maximum}


@pytest.mark.parametrize("model", [client.MODEL, client.DENSE_MODEL])
@pytest.mark.parametrize("stream", [False, True])
def test_new_connection_discovers_exact_identity_once(model, stream):
    with patch.object(client, "_get", return_value={"data": [{"id": model}]}) as discover, \
            patch.object(client, "_post", return_value=reply(model)) as send, \
            patch.object(client, "_post_raw", return_value=stream_reply(model)) as send_stream:
        if stream:
            assert "".join(client.chat_stream([client.Message("user", "Hello")])) == "Hello"
            body = send_stream.call_args.args[1]
        else:
            assert client.chat([client.Message("user", "Hello")]).content == "Hello"
            body = send.call_args.args[1]
    assert body["model"] == model and body["max_tokens"] == 64
    discover.assert_called_once_with("/models")
    assert send.call_count + send_stream.call_count == 1


@pytest.mark.parametrize("listing", [{"data": []}, {"data": [{"id": "unknown"}]},
                                    {"data": [{"id": client.MODEL}, {"id": client.DENSE_MODEL}]},
                                    {"data": [{"id": []}]}])
def test_failed_or_ambiguous_discovery_never_dispatches(listing):
    with patch.object(client, "_get", return_value=listing), patch.object(client, "_post") as send:
        with pytest.raises(client.APIError):
            client.chat([client.Message("user", "Hello")])
    send.assert_not_called()


def test_discovery_transport_failure_has_no_fallback_or_generation_retry():
    with patch.object(client, "_get", side_effect=client.APIError("offline")) as discover, \
            patch.object(client, "_post") as send:
        with pytest.raises(client.APIError, match="offline"):
            client.chat([client.Message("user", "Hello")])
    discover.assert_called_once()
    send.assert_not_called()


def test_saved_explicit_model_and_budget_are_preserved(tmp_path):
    path = tmp_path / "preferences.json"
    original = json.dumps({"model": client.MODEL, "max_tokens": 2048})
    path.write_text(original)
    preferences = Preferences(tmp_path)
    assert preferences.snapshot()["model"] == client.MODEL
    assert preferences.snapshot()["max_tokens"] == 2048
    assert path.read_text() == original
    with client.connection_settings(preferences.connection()), \
            patch.object(client, "_get", return_value={"data": [{"id": client.DENSE_MODEL}]}), \
            patch.object(client, "_post", return_value=reply(client.MODEL)) as send:
        ok, message = client.health_check()
        assert ok is False and client.DENSE_MODEL in message
        client.chat([client.Message("user", "Hello")], 2048)
    assert send.call_args.args[1]["model"] == client.MODEL
    assert send.call_args.args[1]["max_tokens"] == 2048


def test_new_preferences_use_short_automatic_preview(tmp_path):
    preferences = Preferences(tmp_path)
    assert preferences.snapshot()["model"] == "auto"
    assert preferences.snapshot()["max_tokens"] == 64


@pytest.mark.parametrize("maximum,expected", [(32, 32), (64, 64), (512, 512), (2048, 512)])
def test_dense_effective_ceiling_preserves_lower_user_bound(maximum, expected):
    with client.connection_settings(settings(maximum=maximum)), \
            patch.object(client, "_post", return_value=reply()) as send:
        client.chat([client.Message("user", "Hello")], 2048)
    assert send.call_args.args[1]["max_tokens"] == expected


def test_custom_destination_keeps_explicit_identity_budget_and_no_discovery():
    with client.connection_settings(settings("custom/model", 8192, "https://provider.example/v1")), \
            patch.object(client, "_get") as discover, \
            patch.object(client, "_post", return_value=reply("custom/model")) as send:
        client.chat([client.Message("user", "Hello")], 8192)
    discover.assert_not_called()
    assert send.call_args.args[1]["model"] == "custom/model"
    assert send.call_args.args[1]["max_tokens"] == 8192


def test_custom_destination_does_not_inherit_automatic_selection():
    with client.connection_settings(settings("auto", endpoint="http://127.0.0.1:8421/v1")), \
            patch.object(client, "_get") as discover, patch.object(client, "_post") as send:
        with pytest.raises(client.APIError, match="custom provider"):
            client.chat([client.Message("user", "Hello")])
    discover.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize("actual", [client.MODEL, None])
@pytest.mark.parametrize("stream", [False, True])
def test_wrong_or_missing_response_identity_never_yields_text(actual, stream):
    with client.connection_settings(settings()), \
            patch.object(client, "_post", return_value=reply(actual)) as send, \
            patch.object(client, "_post_raw", return_value=stream_reply(actual)) as send_stream:
        with pytest.raises(client.APIError, match="model did not match"):
            if stream:
                next(client.chat_stream([client.Message("user", "Hello")]))
            else:
                client.chat([client.Message("user", "Hello")])
    assert send.call_count + send_stream.call_count == 1
    assert client._HOSTED_GENERATION.acquire(blocking=False)
    client._HOSTED_GENERATION.release()


def test_midstream_identity_change_rejects_later_text_and_releases_admission():
    initial = stream_reply().getvalue().split(b"data: [DONE]")[0]
    changed = stream_reply(client.MODEL).getvalue()
    response = io.BytesIO(initial + changed)
    with client.connection_settings(settings()), patch.object(client, "_post_raw", return_value=response):
        iterator = client.chat_stream([client.Message("user", "Hello")])
        assert next(iterator) == "Hello"
        with pytest.raises(client.APIError, match="model did not match"):
            next(iterator)
    assert response.closed
    assert client._HOSTED_GENERATION.acquire(blocking=False)
    client._HOSTED_GENERATION.release()


def test_closed_stream_releases_slot_and_closes_upstream():
    response = stream_reply()
    with client.connection_settings(settings()), patch.object(client, "_post_raw", return_value=response):
        iterator = client.chat_stream([client.Message("user", "Hello")])
        assert next(iterator) == "Hello"
        assert not client._HOSTED_GENERATION.acquire(blocking=False)
        iterator.close()
    assert response.closed
    assert client._HOSTED_GENERATION.acquire(blocking=False)
    client._HOSTED_GENERATION.release()


def test_waiting_request_cancels_before_dispatch_while_local_job_runs():
    entered, release, waiting, cancel = (threading.Event() for _ in range(4))
    requests = []

    def send(path, body):
        requests.append(body)
        entered.set()
        assert release.wait(3)
        return reply()

    def invoke(queued=False):
        with client.connection_settings(settings()), budget(3, cancel if queued else None):
            if queued:
                waiting.set()
            return client.chat([client.Message("user", "Hello")])

    jobs = Jobs()
    local_done = threading.Event()
    try:
        with patch.object(client, "_post", side_effect=send), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(invoke)
            assert entered.wait(2)
            second = pool.submit(invoke, True)
            assert waiting.wait(2)
            jobs.submit(lambda progress: local_done.set())
            assert local_done.wait(2)
            cancel.set()
            with pytest.raises(Cancelled):
                second.result(timeout=2)
            release.set()
            assert first.result(timeout=2).content == "Hello"
        assert len(requests) == 1
    finally:
        release.set()
        jobs.close()


def test_queue_time_consumes_deadline_without_dispatch():
    with client.connection_settings(settings()), patch.object(client, "_post") as send:
        client._HOSTED_GENERATION.acquire()
        try:
            with budget(.01), pytest.raises(DeadlineExceeded):
                client.chat([client.Message("user", "Hello")])
        finally:
            client._HOSTED_GENERATION.release()
    send.assert_not_called()


def test_full_local_admission_fails_without_discovery_or_dispatch():
    for _ in range(4):
        assert client._HOSTED_PENDING.acquire(blocking=False)
    try:
        with patch.object(client, "_get") as discover, patch.object(client, "_post") as send:
            with pytest.raises(client.APIError, match="Four hosted") as failed:
                client.chat([client.Message("user", "Hello")])
        assert failed.value.status == 429
        discover.assert_not_called()
        send.assert_not_called()
    finally:
        for _ in range(4):
            client._HOSTED_PENDING.release()


def test_second_hosted_request_runs_once_after_first_finishes():
    first_started, second_started, release, queued = (threading.Event() for _ in range(4))
    count = []

    def send(path, body):
        count.append(body)
        if len(count) == 1:
            first_started.set()
            assert release.wait(3)
        else:
            second_started.set()
        return reply()

    def invoke(second=False):
        with client.connection_settings(settings()):
            if second:
                queued.set()
            return client.chat([client.Message("user", "Hello")])

    with patch.object(client, "_post", side_effect=send), ThreadPoolExecutor(max_workers=2) as pool:
        try:
            first = pool.submit(invoke)
            assert first_started.wait(2)
            second = pool.submit(invoke, True)
            assert queued.wait(2)
            assert not second_started.wait(.05)
            release.set()
            assert first.result(timeout=2).content == second.result(timeout=2).content == "Hello"
        finally:
            release.set()
    assert len(count) == 2


def test_browser_disconnect_is_visible_to_queued_operation():
    browser, server = socket.socketpair()
    try:
        disconnected = _Disconnected(server)
        assert disconnected.is_set() is False
        browser.close()
        with pytest.raises(Cancelled), budget(2, disconnected):
            pass
    finally:
        browser.close()
        server.close()


def test_automatic_review_cannot_rebind_resumable_evidence():
    payload = {"title": "Notes", "documents": [{"title": "notes.txt", "content": "A note."}]}
    with patch.object(client, "_get") as discover, patch.object(client, "chat") as send:
        with pytest.raises(ValueError, match="explicit model identifier"):
            review.run(payload)
        review.run(payload, offline=True)
    discover.assert_not_called()
    send.assert_not_called()
