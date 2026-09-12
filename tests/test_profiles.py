"""Saved user details reduce retyping without silent transfer or invented identity."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from sinter import client, profiles
from sinter.preferences import DEFAULTS, Preferences, validate
from test_runtime import post, request, server


PROFILE = {
    'full_name': "Ana O'Connor",
    'role': 'Volunteer coordinator',
    'organisation': 'Riverbank community group',
    'email': 'ana+community@example.org',
    'phone': '+61 7 5550 0100 ext. 2',
    'website': 'https://example.org/community',
    'location': 'Brisbane, Queensland',
    'organisation_type': 'Incorporated community association',
}


def test_saved_profile_survives_restart_and_partial_appearance_save(tmp_path):
    preferences = Preferences(tmp_path)
    preferences.update(PROFILE, api_key='fixture-secret')
    preferences.update({'theme': 'light'})
    loaded = Preferences(tmp_path)
    assert {name: loaded.snapshot()[name] for name in PROFILE} == PROFILE
    assert loaded.snapshot()['theme'] == 'light'
    assert loaded.connection()['api_key'] == ''
    assert 'fixture-secret' not in preferences.path.read_text()
    assert 'fixture-secret' not in json.dumps(preferences.public())


def test_legacy_settings_gain_blank_profile_without_losing_values(tmp_path):
    legacy = {'schema_version': 1, 'organisation': 'Legacy group',
              'theme': 'light', 'model': 'existing-model', 'max_tokens': 512}
    path = tmp_path / 'preferences.json'
    path.write_text(json.dumps(legacy))
    preferences = Preferences(tmp_path)
    assert not preferences.warning
    assert preferences.snapshot()['organisation'] == 'Legacy group'
    assert preferences.snapshot()['model'] == 'existing-model'
    assert preferences.snapshot()['full_name'] == ''
    assert preferences.snapshot()['email'] == ''
    assert json.loads(path.read_text()) == legacy  # Loading does not rewrite the file.


def test_empty_profile_fields_clear_only_explicit_values(tmp_path):
    preferences = Preferences(tmp_path)
    preferences.update(PROFILE)
    preferences.update({'email': '', 'phone': ''})
    saved = preferences.snapshot()
    assert saved['email'] == '' and saved['phone'] == ''
    assert saved['full_name'] == PROFILE['full_name']
    assert saved['website'] == PROFILE['website']
    assert profiles.sender_defaults(saved)['contact_details'] == PROFILE['website']


def test_sender_defaults_are_exact_editable_values_without_credentials():
    settings = {**DEFAULTS, **PROFILE, 'api_key': 'never-a-sender', 'unknown': 'ignored'}
    before = dict(settings)
    result = profiles.sender_defaults(settings)
    assert result == {
        'signatory': PROFILE['full_name'], 'sender_role': PROFILE['role'],
        'organisation': PROFILE['organisation'],
        'contact_details': '\n'.join(PROFILE[key] for key in ('email', 'phone', 'website')),
        'location': PROFILE['location'], 'organisation_type': PROFILE['organisation_type'],
    }
    result['signatory'] = 'An explicit draft override'
    assert settings == before
    assert 'never-a-sender' not in json.dumps(result)


def test_blank_profile_never_infers_identity_from_computer():
    with patch('getpass.getuser', side_effect=AssertionError('No inferred identity')):
        assert set(profiles.sender_defaults({}).values()) == {''}


def test_profile_does_not_enter_model_connection_or_request_body(tmp_path):
    preferences = Preferences(tmp_path)
    preferences.update(PROFILE)
    connection = preferences.connection()
    assert set(connection) == {'api_url', 'model', 'max_tokens', 'api_key', 'inherit_key'}
    with client.connection_settings(connection):
        body = client._chat_body([client.Message('user', 'Public question')], 512)
    encoded = json.dumps(body)
    assert not any(value in encoded for value in PROFILE.values())


@pytest.mark.parametrize('name,value', [
    ('full_name', None), ('role', False), ('email', 123),
    ('full_name', 'A' * 201), ('organisation', 'A' * 1025),
    ('role', 'A' * 201), ('location', 'A' * 201), ('organisation_type', 'A' * 201),
    ('email', 'a' * 255), ('phone', '1' * 81), ('website', 'a' * 2049),
    ('full_name', 'Name\nSecond line'), ('phone', '555\rBcc: hidden'),
    ('role', 'Control\x7f'), ('organisation', 'Name\u2028Second line'),
    ('full_name', 'Name\x00'), ('role', 'Name\x85Second line'),
    ('email', 'not-an-address'), ('email', 'two@@example.org'),
    ('email', 'Name <name@example.org>'), ('email', '.name@example.org'),
    ('email', 'name..test@example.org'), ('email', 'name@example..org'),
    ('email', 'name@-example.org'), ('email', 'name@example.org,other@example.org'),
    ('website', 'javascript:alert(1)'), ('website', 'https://user:pass@example.org'),
    ('website', 'example.org'), ('website', 'https://example.org/with space'),
])
def test_invalid_profile_value_is_rejected_atomically(tmp_path, name, value):
    preferences = Preferences(tmp_path)
    preferences.update(PROFILE)
    original = preferences.path.read_bytes()
    with pytest.raises(ValueError):
        preferences.update({name: value})
    assert preferences.path.read_bytes() == original
    assert {name: preferences.snapshot()[name] for name in PROFILE} == PROFILE


def test_unicode_names_and_idn_contact_domain_are_preserved():
    result = validate({'full_name': '  Zoë 李  ', 'organisation': '  Équipe & Friends ',
                       'email': 'hello@bücher.example', 'website': 'https://bücher.example'})
    assert result['full_name'] == 'Zoë 李'
    assert result['organisation'] == 'Équipe & Friends'
    assert result['email'] == 'hello@bücher.example'


def test_unknown_keys_and_non_objects_still_fail_partial_settings_update(tmp_path):
    preferences = Preferences(tmp_path)
    preferences.update(PROFILE)
    original = preferences.path.read_bytes()
    for values in [{'unrecognised': True}, [], None]:
        with pytest.raises(ValueError, match='Unrecognised settings'):
            preferences.update(values)
    assert preferences.path.read_bytes() == original


def test_simultaneous_partial_updates_keep_both_profile_changes(tmp_path):
    preferences = Preferences(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(preferences.update, [
            {'full_name': PROFILE['full_name']}, {'email': PROFILE['email']},
        ]))
    loaded = Preferences(tmp_path).snapshot()
    assert loaded['full_name'] == PROFILE['full_name'] and loaded['email'] == PROFILE['email']


def test_profile_http_round_trip_preserves_fields_and_requires_launch_token(server):
    assert post(server, '/api/settings', {'settings': PROFILE}, token=False)[0] == 403
    with patch.object(client, '_open', side_effect=AssertionError('Profile saving stays local')):
        assert post(server, '/api/settings', {'settings': PROFILE})[0] == 200
        assert post(server, '/api/settings', {'settings': {'theme': 'light'}})[0] == 200
        code, _, raw = request(server, '/api/settings')
    assert code == 200
    saved = json.loads(raw)['settings']
    assert {name: saved[name] for name in PROFILE} == PROFILE
    assert saved['theme'] == 'light'


def test_endpoint_changes_still_require_explicit_confirmation_with_profile(tmp_path):
    preferences = Preferences(tmp_path)
    preferences.update(PROFILE, api_key='old-session-key')
    with pytest.raises(ValueError, match='Confirm the new API destination'):
        preferences.update({'api_url': 'https://other.example/v1'})
    preferences.update({'api_url': 'https://other.example/v1'}, confirm_endpoint=True)
    assert preferences.connection()['api_key'] == ''
    assert {name: preferences.snapshot()[name] for name in PROFILE} == PROFILE
