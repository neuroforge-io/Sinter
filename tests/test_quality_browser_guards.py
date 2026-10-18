"""Browser rehearsal fixtures cannot escape into model/account HTTP."""
from unittest.mock import Mock

import pytest

from sinter import accounts, client, templates
from tools.quality_browser import (
    COMPLETED,
    FINAL_PARTIAL,
    INTERIM,
    model_fixture,
    offline_services,
)


def legacy_connection():
    return {
        'provider': 'openai-compatible',
        'api_url': client.BASE_URL,
        'model': client.MODEL,
        'max_tokens': 64,
        'api_key': 'fictional-test-only',
        'inherit_key': False,
    }


def test_captured_legacy_stream_is_blocked_before_http():
    stream_alias = client.chat_stream
    with offline_services(), client.connection_settings(legacy_connection()):
        iterator = stream_alias([client.Message('user', 'Fictional question.')])
        try:
            with pytest.raises(AssertionError, match='Unexpected remote _open'):
                next(iterator)
        finally:
            iterator.close()


def test_captured_raw_transport_cannot_bypass_the_guard(monkeypatch):
    import urllib.request

    captured_open = client._open
    underlying = Mock(side_effect=AssertionError('Underlying network reached'))
    monkeypatch.setattr(urllib.request, 'build_opener', underlying)
    with offline_services(), client.connection_settings(legacy_connection()):
        with pytest.raises(AssertionError, match='Unexpected remote urllib.build_opener'):
            captured_open('/models')
    underlying.assert_not_called()
    assert urllib.request.build_opener is underlying


def test_captured_account_transport_is_blocked_before_http(tmp_path, monkeypatch):
    import urllib.request

    manager = accounts.AccountManager(tmp_path)
    captured_request = manager._request
    underlying = Mock(side_effect=AssertionError('Underlying account network reached'))
    monkeypatch.setattr(urllib.request, 'build_opener', underlying)
    with offline_services():
        with pytest.raises(AssertionError, match='Unexpected remote urllib.build_opener'):
            captured_request(accounts.JWKS_URL)
    underlying.assert_not_called()
    assert not manager._jwks


def test_direct_urlopen_is_blocked_before_http(monkeypatch):
    import urllib.request

    underlying = Mock(side_effect=AssertionError('Underlying network reached'))
    monkeypatch.setattr(urllib.request, 'urlopen', underlying)
    with offline_services():
        with pytest.raises(AssertionError, match='Unexpected remote urllib.urlopen'):
            urllib.request.urlopen('https://fictional.invalid/')
    underlying.assert_not_called()


def test_intended_higher_layer_model_fixtures_still_complete():
    with offline_services(), model_fixture(complete=True) as calls:
        answer = templates.chat([client.Message('user', 'Fictional note.')])
        assert answer.content == COMPLETED
        iterator = templates.chat_stream([client.Message('user', 'Fictional note.')])
        assert next(iterator) == INTERIM
        with pytest.raises(StopIteration) as done:
            next(iterator)
        assert done.value.value.content == FINAL_PARTIAL
        assert done.value.value.finish_reason == 'stop'
        assert len(calls) == 2


def test_guard_restores_transports_after_failure():
    import urllib.request

    before = (client._open, urllib.request.urlopen, urllib.request.build_opener)
    with pytest.raises(RuntimeError, match='Fictional rehearsal failure'):
        with offline_services():
            raise RuntimeError('Fictional rehearsal failure')
    assert (client._open, urllib.request.urlopen, urllib.request.build_opener) == before
