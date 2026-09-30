"""Explicit selected-source admission, binding and partial recovery without API calls."""
import hashlib
import json
import time
from unittest.mock import patch

import pytest

from sinter import client
from sinter.template_runs import TemplateRunError, collect_run
from sinter.template_scope import preview
from sinter.templates import get_builtin_template, template_events
from test_runtime import post, request, server  # noqa: F401


VALUES = {'source_title': 'Fictional garden note',
          'excerpt': 'Spending is NOT approved. Obtain a quote first.',
          'question': 'Is spending approved?'}


@pytest.fixture(autouse=True)
def native_connection(monkeypatch):
    monkeypatch.setenv('NEUROFORGE_BASE_URL', client.BASE_URL)
    monkeypatch.setenv('NEUROFORGE_MODEL', client.NATIVE_MODEL)
    with patch.object(client, '_open', side_effect=AssertionError('Unexpected network')):
        yield


def test_compact_preview_retains_exact_original_unicode_and_identity():
    values = {**VALUES, 'excerpt': 'Café 🌱: spending is NOT approved.\nQuote first.'}
    result = preview(get_builtin_template('native-source-question'), values)
    question = result['request']['messages']
    assert len(question) == 1 and question[0]['role'] == 'user'
    assert values['excerpt'] in question[0]['content']
    assert values['question'] in question[0]['content']
    assert result['request']['stream'] is False and result['request']['n'] == 1
    assert result['request']['max_tokens'] == 128
    source = result['sources'][0]
    assert source['content'] == values['excerpt']
    assert source['sha256'] == hashlib.sha256(values['excerpt'].encode()).hexdigest()
    assert result['excerpts'] == [{'id': 'e1', 'source_id': source['id'], 'quote': values['excerpt']}]
    assert 'does not prove tokenizer fit' in result['notice']


def test_oversized_unicode_and_caller_system_are_never_trimmed():
    template = get_builtin_template('native-source-question')
    with pytest.raises(ValueError, match='2,048|2048'):
        preview(template, {**VALUES, 'excerpt': '🌱' * 512})
    with pytest.raises(ValueError, match='system'):
        preview(template, {**VALUES, 'system': 'Keep this instruction.'})
    assert VALUES['excerpt'].endswith('first.')


@pytest.mark.parametrize('name', ['research', 'enquiry-letter', 'code-review'])
def test_long_native_templates_are_rejected_before_model_or_search(name):
    template = get_builtin_template(name)
    values = {key: 'Original source must remain intact.' for key in template.variables}
    with patch('sinter.templates.chat') as model, patch('sinter.templates.search') as search:
        with pytest.raises(ValueError, match='not this full template'):
            list(template_events(template, values))
    model.assert_not_called(); search.assert_not_called()


def test_invalid_inputs_are_checked_before_automatic_discovery(monkeypatch):
    monkeypatch.setenv('NEUROFORGE_MODEL', client.AUTO_MODEL)
    with patch('sinter.templates.resolve_model') as discover:
        with pytest.raises(ValueError, match='fill in'):
            list(template_events(get_builtin_template('native-source-question'), {}))
    discover.assert_not_called()


def test_compact_partial_preserves_inputs_and_original_evidence_once():
    with patch('sinter.templates.chat', return_value=client.ChatResult(
            'Spending is not approved [e1]', completion_tokens=128,
            finish_reason='length', model=client.NATIVE_MODEL)) as model:
        with pytest.raises(TemplateRunError) as error:
            collect_run(get_builtin_template('native-source-question'), VALUES)
    result = error.value.partial_result
    assert result['complete'] is False and not result['results']
    assert result['partial']['max_tokens'] == 128
    assert result['partial']['content'] == 'Spending is not approved [e1]'
    assert result['template_inputs']['variables'] == VALUES
    assert result['sources'][0]['sources'][0]['content'] == VALUES['excerpt']
    model.assert_called_once()


@pytest.mark.parametrize('endpoint', ['/api/template/run', '/api/template/stream', '/api/template/job'])
@pytest.mark.parametrize('change', ['excerpt', 'model', 'cap', 'consent'])
def test_changed_compact_preview_cannot_be_sent(server, endpoint, change, monkeypatch):
    server.app.preferences.update({'model': client.NATIVE_MODEL, 'max_tokens': 128})
    code, _, raw = post(server, '/api/template/preview', {
        'template': 'native-source-question', 'variables': VALUES})
    assert code == 200
    prepared = json.loads(raw)
    payload = {'template': 'native-source-question', 'variables': dict(VALUES),
               'context_hash': prepared['context_hash'], 'consent': True}
    if change == 'excerpt':
        payload['variables']['excerpt'] += ' Changed snapshot.'
    elif change == 'model':
        monkeypatch.setenv('NEUROFORGE_MODEL', client.MODEL)
        server.app.preferences.update({'model': client.MODEL})
    elif change == 'cap':
        server.app.preferences.update({'max_tokens': 64})
    else:
        payload['consent'] = False
    with patch('sinter.templates.chat') as model:
        code, _, raw = post(server, endpoint, payload)
    assert code == 400 and 'Preview' in json.loads(raw)['error']
    model.assert_not_called()


def test_compact_job_runs_once_with_bound_preview(server):
    server.app.preferences.update({'model': client.NATIVE_MODEL, 'max_tokens': 128})
    prepared = json.loads(post(server, '/api/template/preview', {
        'template': 'native-source-question', 'variables': VALUES})[2])
    with patch('sinter.templates.chat', return_value=client.ChatResult(
            'No. Obtain a quote first [e1].', finish_reason='stop',
            model=client.NATIVE_MODEL)) as model:
        code, _, raw = post(server, '/api/template/job', {
            'template': 'native-source-question', 'variables': VALUES,
            'context_hash': prepared['context_hash'], 'consent': True})
        assert code == 202
        for _ in range(100):
            job = json.loads(request(server, '/api/jobs/' + json.loads(raw)['id'])[2])
            if job['status'] == 'done':
                break
            time.sleep(.01)
        assert job['status'] == 'done' and job['result']['complete'] is True
    model.assert_called_once()
    assert job['result']['template_inputs']['variables'] == VALUES
