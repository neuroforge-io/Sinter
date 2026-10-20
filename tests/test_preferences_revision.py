"""Interrupted preference writes must not overwrite a later observed revision."""
import json
import threading
from unittest.mock import patch

import pytest
import test_runtime
from test_runtime import post, request

from sinter.preferences import Preferences, PreferencesConflict

server = test_runtime.server


def test_delayed_old_write_cannot_follow_a_new_write(tmp_path):
    prefs = Preferences(tmp_path)
    original = prefs.public()
    ready, release = threading.Event(), threading.Event()
    outcome = []

    def old_request():
        ready.set()
        assert release.wait(3)
        try:
            prefs.update({'organisation': 'Delayed old request'},
                         api_key='fictional-old', expected_revision=original['revision'])
        except PreferencesConflict:
            outcome.append('conflict')

    worker = threading.Thread(target=old_request)
    worker.start()
    try:
        assert ready.wait(3)
        observed = prefs.public()
        newer = prefs.update({'organisation': 'New explicit choice'},
                             api_key='fictional-new', expected_revision=observed['revision'])
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert outcome == ['conflict']
    assert prefs.public() == newer
    assert prefs.connection()['api_key'] == 'fictional-new'
    assert json.loads(prefs.path.read_text())['organisation'] == 'New explicit choice'


def test_lost_ack_requires_new_observed_revision_and_partial_forget(tmp_path):
    prefs = Preferences(tmp_path)
    original = prefs.public()
    committed = prefs.update({'model': 'erais-native-qwen3', 'max_tokens': 16,
                              'organisation': 'Fictional group', 'theme': 'light'},
                             api_key='fictional-held', expected_revision=original['revision'])
    with pytest.raises(PreferencesConflict):
        prefs.update({}, api_key='', expected_revision=original['revision'])
    observed = prefs.public()
    forgotten = prefs.update({}, api_key='', expected_revision=observed['revision'])
    assert forgotten['settings'] == committed['settings']
    assert forgotten['has_session_key'] is False
    assert prefs.connection()['api_key'] == ''
    assert forgotten['revision'] != observed['revision']


@pytest.mark.parametrize('value', [None, True, '', [], {}, 'not-a-revision', 'A' * 32])
def test_explicit_malformed_revision_never_writes(tmp_path, value):
    prefs = Preferences(tmp_path)
    before = prefs.public()
    with pytest.raises(ValueError, match='settings revision'):
        prefs.update({'organisation': 'Must not apply'}, expected_revision=value)
    assert prefs.public() == before
    assert not prefs.path.exists()


def test_revision_is_runtime_only_and_changes_for_every_success(tmp_path):
    prefs = Preferences(tmp_path)
    first = prefs.public()
    no_op = prefs.update({}, expected_revision=first['revision'])
    keyed = prefs.update({}, api_key='fictional-only', expected_revision=no_op['revision'])
    assert len({first['revision'], no_op['revision'], keyed['revision']}) == 3
    assert prefs.public() == keyed
    raw = prefs.path.read_text()
    assert 'revision' not in raw and 'fictional-only' not in raw
    restarted = Preferences(tmp_path)
    assert restarted.public()['revision'] != keyed['revision']
    assert restarted.snapshot() == prefs.snapshot()
    with pytest.raises(PreferencesConflict):
        restarted.update({}, expected_revision=keyed['revision'])
    assert restarted.public()['has_session_key'] is False
    # Older non-editor callers remain compatible.
    assert restarted.update({'theme': 'light'})['settings']['theme'] == 'light'


def test_failed_write_preserves_settings_key_and_revision(tmp_path):
    prefs = Preferences(tmp_path)
    before = prefs.update({}, api_key='fictional-retained')
    with patch('sinter.preferences.os.replace', side_effect=OSError('fixture disk failure')):
        with pytest.raises(OSError):
            prefs.update({'organisation': 'Must not apply'}, api_key='',
                         expected_revision=before['revision'])
    assert prefs.public() == before
    assert prefs.connection()['api_key'] == 'fictional-retained'
    assert not list(tmp_path.glob('.preferences-*'))


def test_acknowledgement_stays_bound_to_its_own_write(tmp_path):
    prefs = Preferences(tmp_path)
    entered, attempted, finished = threading.Event(), threading.Event(), threading.Event()
    original_public = prefs.public
    responses = {}

    def observed_public():
        if threading.current_thread().name == 'first-settings-writer':
            entered.set()
            assert attempted.wait(3)
            finished.wait(.1)
        return original_public()

    def first():
        responses['first'] = prefs.update({'organisation': 'First'}, api_key='fictional-first')

    def second():
        assert entered.wait(3)
        attempted.set()
        responses['second'] = prefs.update({'organisation': 'Second'}, api_key='')
        finished.set()

    with patch.object(prefs, 'public', side_effect=observed_public):
        workers = [threading.Thread(target=first, name='first-settings-writer'),
                   threading.Thread(target=second, name='second-settings-writer')]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(4)
        assert all(not worker.is_alive() for worker in workers)
    assert responses['first']['settings']['organisation'] == 'First'
    assert responses['first']['has_session_key'] is True
    assert responses['second']['settings']['organisation'] == 'Second'
    assert responses['second']['has_session_key'] is False
    assert responses['first']['revision'] != responses['second']['revision']


def test_http_settings_revision_rejection_and_legacy_compatibility(server):
    code, _, raw = request(server, '/api/settings')
    assert code == 200
    before = json.loads(raw)
    code, _, raw = post(server, '/api/settings', {
        'settings': {'organisation': 'HTTP fictional group'},
        'expected_revision': before['revision']})
    assert code == 200
    saved = json.loads(raw)
    assert saved['revision'] != before['revision']
    assert post(server, '/api/settings', {
        'settings': {}, 'api_key': '', 'expected_revision': before['revision']})[0] == 409
    assert post(server, '/api/settings', {
        'settings': {}, 'expected_revision': None})[0] == 400
    assert json.loads(request(server, '/api/settings')[2]) == saved
    assert post(server, '/api/settings', {'settings': {'theme': 'light'}})[0] == 200


def test_health_echoes_the_revision_used_for_its_connection(server):
    before = json.loads(request(server, '/api/settings')[2])
    with patch('sinter.client.health_check', return_value=(True, 'Fictional availability')):
        code, _, raw = request(server, '/api/health')
    assert code == 200
    assert json.loads(raw)['settings_revision'] == before['revision']


@pytest.mark.parametrize('ok', [True, False])
def test_browser_adapter_health_keeps_anonymous_binding_and_revision(tmp_path, monkeypatch, ok):
    from sinter import browser_runtime, client

    app = browser_runtime.BrowserApplication(tmp_path)
    monkeypatch.setattr(browser_runtime, 'app', app)
    before = app.preferences.update({'model': 'erais-native-qwen3', 'max_tokens': 16})
    seen = []

    def health():
        connection = client._CONNECTION.get()
        seen.append((connection['api_url'], connection['model'],
                     connection['anonymous'], connection['inherit_key'], connection['api_key']))
        return ok, 'Fictional browser availability'

    with patch.object(client, 'health_check', side_effect=health):
        reply = json.loads(browser_runtime.request(json.dumps({'path': '/api/health'})))
    assert reply['status'] == (200 if ok else 503)
    assert reply['result']['settings_revision'] == before['revision']
    assert reply['result']['ok'] is ok
    assert seen == [(client.BASE_URL, 'erais-native-qwen3', True, False, '')]
    app.jobs.close()
