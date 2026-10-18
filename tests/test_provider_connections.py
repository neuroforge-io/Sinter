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

@pytest.mark.parametrize('cap', [1, 16, 31])
def test_destination_discovery_preserves_native_selection_and_key(tmp_path, cap):
    from sinter.model_profiles import NATIVE_MODEL

    prefs = Preferences(tmp_path)
    prefs.update({'model': NATIVE_MODEL, 'max_tokens': cap},
                 api_key='fictional-held-key')
    original = prefs.path.read_bytes()
    snapshot = prefs.snapshot()
    candidate = prefs.preview_destination({
        'api_url': snapshot['api_url'], 'provider': snapshot['provider'],
        'model': 'probe-placeholder', 'max_tokens': cap})
    assert set(candidate) == {'api_url', 'provider', 'api_key', 'inherit_key'}
    assert candidate['api_key'] == 'fictional-held-key'
    assert candidate['inherit_key'] is True
    assert prefs.path.read_bytes() == original
    assert prefs.snapshot() == snapshot
    assert prefs.connection()['api_key'] == 'fictional-held-key'
    # Discovery does not weaken the full-profile compatibility API or saves.
    with pytest.raises(ValueError, match='32'):
        prefs.preview_connection({'model': 'probe-placeholder'})
    with pytest.raises(ValueError, match='32'):
        prefs.update({'model': 'ordinary-model'})
    assert prefs.path.read_bytes() == original


def test_destination_discovery_ignores_only_known_generation_fields(tmp_path):
    prefs = Preferences(tmp_path)
    before = prefs.snapshot()
    candidate = prefs.preview_destination({'model': '', 'max_tokens': None})
    assert set(candidate) == {'api_url', 'provider', 'api_key', 'inherit_key'}
    assert prefs.snapshot() == before
    assert not prefs.path.exists()
    with pytest.raises(ValueError, match='only the model connection'):
        prefs.preview_destination({'organisation': 'Fictional group'})


@pytest.mark.parametrize('values', [
    {'api_url': None}, {'provider': {}}, {'provider': []},
    {'provider': 'unrecognised'}, {'api_url': 'https://user:pass@example.org/v1'},
    {'api_url': 'http://remote.example/v1'}, {'api_url': 'https://example.org/v1?x=1'},
    {'api_url': 'https://example.org/v1#part'},
    {'provider': 'chatgpt', 'api_url': 'https://example.org/v1'},
    {'provider': 'anthropic'},
])
def test_destination_discovery_keeps_address_and_style_guards(tmp_path, values):
    prefs = Preferences(tmp_path)
    before = prefs.snapshot()
    with pytest.raises(ValueError):
        prefs.preview_destination(values, confirm_endpoint=True)
    assert prefs.snapshot() == before
    assert not prefs.path.exists()


@pytest.mark.parametrize('candidate', [
    {'api_url': 'https://example.org/v2'},
    {'api_url': 'https://example.org:8443/v1'},
    {'provider': 'anthropic'},
])
def test_destination_preview_never_retargets_a_held_key(tmp_path, candidate):
    prefs = Preferences(tmp_path)
    prefs.update({'api_url': 'https://example.org/v1'},
                 confirm_endpoint=True, api_key='fictional-held-key')
    original = prefs.path.read_bytes()
    with pytest.raises(ValueError, match='Confirm'):
        prefs.preview_destination(candidate)
    with pytest.raises(ValueError, match='Confirm'):
        prefs.preview_destination(candidate, confirm_endpoint=1)
    checked = prefs.preview_destination(candidate, confirm_endpoint=True)
    assert checked['api_key'] == ''
    assert checked['inherit_key'] is False
    assert prefs.connection()['api_key'] == 'fictional-held-key'
    assert prefs.path.read_bytes() == original


def test_destination_preview_explicit_key_is_temporary(tmp_path):
    prefs = Preferences(tmp_path)
    prefs.update({}, api_key='fictional-held-key')
    original = prefs.path.read_bytes()
    assert prefs.preview_destination({})['api_key'] == 'fictional-held-key'
    assert prefs.preview_destination({}, api_key='')['api_key'] == ''
    candidate = prefs.preview_destination({}, api_key='fictional-candidate-key')
    assert candidate['api_key'] == 'fictional-candidate-key'
    for invalid in ['contains a space', 'nonascii-é', 'line\nbreak', [], 42]:
        with pytest.raises(ValueError, match='key'):
            prefs.preview_destination({}, api_key=invalid)
    assert prefs.connection()['api_key'] == 'fictional-held-key'
    assert prefs.path.read_bytes() == original
    assert 'fictional-candidate-key' not in json.dumps(prefs.public())


@pytest.mark.parametrize('cap', [1, 16, 31])
@pytest.mark.parametrize('available', [True, False])
def test_native_low_cap_catalogue_route_uses_only_destination(
        server, cap, available):
    from unittest.mock import patch

    from sinter import client
    from sinter.model_profiles import NATIVE_MODEL

    prefs = server.app.preferences
    prefs.update({'model': NATIVE_MODEL, 'max_tokens': cap},
                 api_key='fictional-held-key')
    original = prefs.path.read_bytes()
    observed = []

    def catalogue(path):
        settings = client._CONNECTION.get()
        assert 'model' not in settings and 'max_tokens' not in settings
        observed.append((path, settings['api_url'], settings['provider']))
        if not available:
            raise client.APIError('Fictional catalogue unavailable', status=503)
        return {'data': [{'id': NATIVE_MODEL}]}

    payload = {'settings': {'model': 'probe-placeholder', 'max_tokens': cap}}
    with patch.object(client, '_get', side_effect=catalogue), patch.object(
            client, '_open', side_effect=AssertionError('No hosted request')) as network:
        assert post(server, '/api/models', payload, token=False)[0] == 403
        assert observed == []
        code, _, raw = post(server, '/api/models', payload)
        assert network.call_count == 0
    if available:
        assert code == 200 and json.loads(raw)['models'] == [{'id': NATIVE_MODEL}]
    else:
        assert code == 503
        assert 'Fictional catalogue unavailable' in json.loads(raw)['error']
    assert observed == [('/models', client.BASE_URL, 'openai-compatible')]
    assert prefs.path.read_bytes() == original
    assert prefs.snapshot()['model'] == NATIVE_MODEL
    assert prefs.snapshot()['max_tokens'] == cap
    assert prefs.connection()['api_key'] == 'fictional-held-key'


def test_native_name_on_custom_provider_keeps_full_generation_limits(tmp_path):
    from sinter.model_profiles import NATIVE_MODEL

    prefs = Preferences(tmp_path)
    candidate = {'api_url': 'https://example.org/v1',
                 'model': NATIVE_MODEL, 'max_tokens': 16}
    assert prefs.preview_destination(candidate, confirm_endpoint=True)['api_url'] == candidate['api_url']
    with pytest.raises(ValueError, match='32'):
        prefs.preview_connection(candidate, confirm_endpoint=True)
    with pytest.raises(ValueError, match='32'):
        prefs.update(candidate, confirm_endpoint=True)
    assert not prefs.path.exists()


def test_destination_catalogue_uses_real_get_transport_without_model(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace

    from sinter import client
    from sinter.model_profiles import NATIVE_MODEL

    prefs = Preferences(tmp_path)
    prefs.update({'model': NATIVE_MODEL, 'max_tokens': 16},
                 api_key='fictional-held-key')
    original = prefs.path.read_bytes()
    candidate = prefs.preview_destination({
        'api_url': '  ' + client.BASE_URL + '///  '})
    opened = []

    def open_catalogue(request, timeout):
        assert request.full_url == client.BASE_URL + '/models'
        assert request.get_method() == 'GET'
        assert request.data is None
        assert request.get_header('Accept') == 'application/json'
        assert request.get_header('Authorization') == 'Bearer fictional-held-key'
        assert 0 < timeout <= client.CONTROL_TIMEOUT
        opened.append(request.full_url)
        response = io.BytesIO(json.dumps({'data': [{'id': NATIVE_MODEL}]}).encode())
        response.headers = {'Content-Type': 'application/json; charset=utf-8'}
        return response

    monkeypatch.setattr(client.urllib.request, 'build_opener',
                        lambda *_: SimpleNamespace(open=open_catalogue))
    with client.connection_settings(candidate):
        assert 'model' not in client._CONNECTION.get()
        assert 'max_tokens' not in client._CONNECTION.get()
        assert client.list_models() == [{'id': NATIVE_MODEL}]
    assert opened == [client.BASE_URL + '/models']
    assert prefs.path.read_bytes() == original
    assert prefs.snapshot()['model'] == NATIVE_MODEL
    assert prefs.snapshot()['max_tokens'] == 16
