"""Unsaved provider checks cannot persist or retarget existing credentials."""
import json

import pytest
import test_runtime
from test_runtime import post, request

from sinter.preferences import Preferences

server = test_runtime.server


def test_legacy_preferences_keep_compatible_transport(tmp_path):
    path = tmp_path / 'preferences.json'
    path.write_text(json.dumps({'model': 'existing', 'max_tokens': 512}))
    prefs = Preferences(tmp_path)
    assert prefs.snapshot()['provider'] == 'openai-compatible'
    assert 'provider' not in json.loads(path.read_text())


def test_candidate_check_does_not_save_settings_or_key(tmp_path):
    prefs = Preferences(tmp_path)
    before = prefs.snapshot()
    candidate = prefs.preview_connection({
        'api_url': 'https://api.anthropic.com/v1', 'provider': 'anthropic',
        'model': 'probe-placeholder'}, confirm_endpoint=True,
        api_key='fictional-claude-key')
    assert candidate['api_key'] == 'fictional-claude-key'
    assert candidate['provider'] == 'anthropic'
    assert prefs.snapshot() == before
    assert prefs.connection()['api_key'] == ''
    assert not prefs.path.exists()


def test_protocol_change_requires_confirmation_and_drops_session_key(tmp_path):
    prefs = Preferences(tmp_path)
    prefs.update({'api_url': 'https://example.org/v1'},
                 confirm_endpoint=True, api_key='fictional-secret')
    with pytest.raises(ValueError, match='Confirm'):
        prefs.preview_connection({'provider': 'anthropic'})
    candidate = prefs.preview_connection({'provider': 'anthropic'},
                                         confirm_endpoint=True)
    assert candidate['api_key'] == ''
    prefs.update({'provider': 'anthropic'}, confirm_endpoint=True)
    assert prefs.connection()['api_key'] == ''


def test_chatgpt_account_cannot_use_custom_destination(tmp_path):
    prefs = Preferences(tmp_path)
    with pytest.raises(ValueError, match='official OpenAI'):
        prefs.update({'provider': 'chatgpt', 'api_url': 'https://example.org/v1'},
                     confirm_endpoint=True)


@pytest.mark.parametrize('provider', ['unknown', None, {}, []])
def test_invalid_provider_rejected_cleanly(tmp_path, provider):
    with pytest.raises(ValueError):
        Preferences(tmp_path).update({'provider': provider})


def test_catalog_preview_requires_session_token_and_redacts_key(server):
    from unittest.mock import patch

    from sinter import client

    payload = {'settings': {'api_url': 'https://custom.example/v1',
                           'provider': 'openai-compatible',
                           'model': 'probe-placeholder'},
               'confirm_endpoint': True, 'api_key': 'fictional-only-key'}
    with patch.object(client, 'list_models', return_value=[{'id': 'a-model'}]):
        assert post(server, '/api/models', payload, token=False)[0] == 403
        code, _, body = post(server, '/api/models', payload)
    assert code == 200 and json.loads(body)['models'] == [{'id': 'a-model'}]
    assert b'fictional-only-key' not in request(server, '/api/settings')[2]
    assert server.app.preferences.connection()['api_key'] == ''


def test_public_account_status_never_contains_tokens(server):
    code, _, body = request(server, '/api/account')
    assert code == 200
    assert json.loads(body)['connected'] is False
    assert not any(key in json.loads(body) for key in
                   ('access_token', 'refresh_token', 'id_token'))
    assert post(server, '/api/account/connect', {}, token=False)[0] == 403
