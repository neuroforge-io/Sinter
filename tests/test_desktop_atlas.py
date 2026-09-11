"""Preferences, atlas boundaries and deterministic community-tool regression tests."""
import hashlib
import json
import threading
import time
from unittest.mock import patch

import pytest

from sinter import atlas, client, community
from sinter.desktop import self_test
from sinter.jobs import Jobs
from sinter.preferences import DEFAULTS, Preferences, validate
from test_runtime import server, post, request


def packet():
    snapshot, identity = 'example-snapshot', 'example-node'
    citation = hashlib.sha256((snapshot+'\0node\0'+identity).encode()).hexdigest()
    return {'schema_version': 'rkc-context/v1', 'snapshot_id': snapshot, 'query': 'funding', 'integrity': 'producer-claimed',
            'digest': 'a'*64, 'truncated': False, 'bytes': 1000, 'max_bytes': 32768, 'warnings': [],
            'items': [{'citation_id': citation, 'object_id': identity, 'object_type': 'node', 'title': 'Funding notes',
                       'path': 'notes/funding.md', 'text': 'Funding is proposed. No spending was approved.', 'score': 1.0, 'evidence_ids': []}]}


@pytest.mark.parametrize('update', [{'max_tokens': True}, {'rkc_port': 80}, {'theme': '<script>'}, {'model': 'bad model'}, {'api_url': 'http://example.org/v1'}, {'api_url': 'https://user:pass@example.org/v1'}, {'api_url': 'https://example.org/?secret=1'}, {'unexpected': True}])
def test_bad_preferences_rejected(update):
    with pytest.raises(ValueError): validate(update)


def test_atomic_preferences_and_no_key_on_disk(tmp_path):
    preferences = Preferences(tmp_path)
    preferences.update({**DEFAULTS, 'organisation': 'Garden P&C'}, api_key='private-session-value')
    assert 'private-session-value' not in preferences.path.read_text()
    assert 'private-session-value' not in json.dumps(preferences.public())
    assert Preferences(tmp_path).snapshot()['organisation'] == 'Garden P&C'
    assert Preferences(tmp_path).connection()['api_key'] == ''
    changed = {**DEFAULTS, 'api_url': 'https://example.org/v1'}
    with pytest.raises(ValueError): preferences.update(changed)
    preferences.update(changed, confirm_endpoint=True)
    assert preferences.connection()['api_key'] == '' and not preferences.connection()['inherit_key']


def test_corrupt_preferences_preserved(tmp_path):
    path = tmp_path/'preferences.json'; path.write_text('{bad')
    prefs = Preferences(tmp_path)
    assert prefs.warning and prefs.snapshot() == DEFAULTS
    assert path.read_text() == '{bad'


def test_requests_hold_isolated_connection_context(tmp_path):
    prefs = Preferences(tmp_path)
    prefs.update({**DEFAULTS, 'model': 'first-model'})
    jobs = Jobs()
    gate = threading.Event()
    try:
        with client.connection_settings(prefs.connection()):
            identifier = jobs.submit(lambda progress: (gate.wait(2), client._chat_body([client.Message('user', 'test')], 512))[1])
        prefs.update({**DEFAULTS, 'model': 'second-model'})
        gate.set()
        for _ in range(100):
            result = jobs.get(identifier)
            if result['status'] == 'done': break
            time.sleep(.01)
        assert result['result']['model'] == 'first-model'
    finally: jobs.close()


def test_custom_endpoint_does_not_inherit_neuroforge_key():
    with patch.dict('os.environ', {'NEUROFORGE_API_KEY': 'private-key'}), client.connection_settings({**DEFAULTS, 'api_url': 'https://elsewhere.example/v1', 'api_key': '', 'inherit_key': False}):
        assert 'Authorization' not in client._headers()


def test_settings_http_token_and_key_redaction(server):
    assert post(server, '/api/settings', {'settings': DEFAULTS}, token=False)[0] == 403
    assert post(server, '/api/settings', {'settings': {**DEFAULTS, 'text_size': 'large'}, 'api_key': 'test-key'})[0] == 200
    code, _, raw = request(server, '/api/settings')
    assert code == 200 and b'test-key' not in raw
    assert json.loads(raw)['settings']['text_size'] == 'large'


def test_atlas_exact_evidence_and_mutation_free():
    value = packet(); original = json.dumps(value)
    result = atlas.context(value, 'funding approved')
    assert result['items'][0]['text'] == value['items'][0]['text']
    assert result['items'][0]['pointer'] == '/items/0/text'
    assert json.dumps(value) == original
    assert 'not been independently verified' in ' '.join(result['warnings'])


def test_atlas_mismatch_rejected():
    value = packet(); value['snapshot_id'] = 'different'
    with pytest.raises(ValueError): atlas.validate(value)


@pytest.mark.parametrize('value', [{}, [], {'schema_version': 'rkc-context/v2'}])
def test_invalid_atlas_rejected(value):
    with pytest.raises(ValueError): atlas.validate(value)


def test_empty_context_never_fabricates():
    result = atlas.context(packet(), 'telescope')
    assert not result['items'] and 'No matching material' in result['warnings'][-1]


def test_generation_requires_consent_and_filters_unknown_references():
    with patch.object(client, 'chat', return_value=client.ChatResult('Invented [999]', finish_reason='stop')) as call:
        with pytest.raises(ValueError): atlas.answer(packet(), 'funding', False)
        assert not call.called
        result = atlas.answer(packet(), 'funding', True)
        assert result['citation_check'] == 'rejected_unknown_reference'
        assert 'Invented' not in result['answer']
        assert result['review_status'] == 'unverified_model_draft'


def test_compile_rejects_traversal_before_starting(tmp_path):
    binary = tmp_path/'rkc'; binary.write_text('test')
    with patch('subprocess.Popen') as process:
        with pytest.raises(ValueError): atlas.compile_collection([{'name': '../secret', 'content': 'x'}], str(binary), True)
        assert not process.called


def test_plan_preserves_values_and_neutralises_csv_formulas():
    result = community.plan('Volunteers', [{'action': '=DANGEROUS()', 'owner': '@NAME', 'due': '2026-09-30'}])
    assert result['actions'][0]['action'] == '=DANGEROUS()'
    assert "'=DANGEROUS()" in result['csv'] and "'@NAME" in result['csv']
    assert 'DTSTART;VALUE=DATE:20260930' in result['calendar']
    assert 'DTEND;VALUE=DATE:20261001' in result['calendar']


@pytest.mark.parametrize('value', ['9999-12-31', '2026-02-30', '30/09/2026'])
def test_plan_dates_fail_closed(value):
    with pytest.raises(ValueError): community.plan('Test', [{'action': 'Call', 'due': value}])


def test_plan_missing_dates_remain_missing():
    result = community.plan('Test', [{'action': 'Discuss options'}])
    assert 'BEGIN:VEVENT' not in result['calendar'] and 'Not set' in result['markdown']


def test_compare_exact_changes():
    result = community.compare('No approval.\nDiscuss later.', 'No approval.\nAsk for quotes.')
    assert result['changed_blocks'] == 1
    assert result['changes'][0]['before'] == 'Discuss later.'
    assert result['changes'][0]['after'] == 'Ask for quotes.'


def test_new_assets_and_source_runtime(server, tmp_path):
    for path in ['settings.js', 'atlas.js', 'community.js']:
        assert request(server, '/static/'+path)[0] == 200
    assert post(server, '/api/desktop/quit', {})[0] == 400
    receipt = tmp_path/'native.json'
    assert self_test(str(receipt)) == 0
    assert json.loads(receipt.read_text())['passed']
