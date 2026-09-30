"""Regressions from the September 12 user-testing session."""
import json
import time
import io
import copy
from urllib.error import HTTPError
from unittest.mock import patch

import pytest

from sinter import client, workbench
from sinter.preferences import DEFAULTS, validate
from sinter.templates import Step, Template
from sinter.template_runs import TemplateRunError, collect_run
from test_runtime import post, request, server


@pytest.mark.parametrize('code', [500, 502, 503, 504])
def test_service_outage_has_recovery_advice_without_exposing_upstream_body(code):
    failure = HTTPError('https://example.org', code, 'error', {}, io.BytesIO(b'private upstream details'))
    with patch.object(client.urllib.request, 'build_opener') as opener:
        opener.return_value.open.side_effect = failure
        with pytest.raises(client.APIError) as raised:
            client._open('/search', {'query': 'public query'})
    assert f'HTTP {code}' in str(raised.value)
    assert 'local tools remain available' in str(raised.value)
    assert 'private upstream' not in str(raised.value)


def test_research_delivers_relevant_sources_without_letter_placeholders():
    response = client.SearchResponse('2026-09-12T00:00:00Z', [
        client.SearchResult('Garden water guide', 'https://example.org/garden',
                            'Community gardens need to confirm their water supply.'),
        client.SearchResult('Other material', 'https://example.org/other',
                            'A telescope tracks a star.'),
    ])
    with patch.object(client, 'search', return_value=response) as search:
        result = workbench.run({'workflow': 'research', 'title': 'Community gardens',
                                'query': 'community gardens water', 'use_search': True})
    search.assert_called_once_with('community gardens water')
    assert result['document_type'] == 'research'
    assert result['coverage'] == {'sources_collected': 2, 'sources_highlighted': 1,
                                  'excerpts_selected': 1}
    assert result['highlights'][0]['url'] == 'https://example.org/garden'
    assert result['highlights'][0]['quote'] == response.results[0].content
    assert 'telescope' not in result['markdown']
    assert 'Draft enquiry letter' not in result['markdown']
    assert '[Add the questions' not in result['markdown']
    assert '## Gaps and next steps' in result['markdown']
    assert result['markdown'].count('## Source register') == 1


def test_research_keeps_a_missing_match_explicit():
    result = workbench.run({'workflow': 'research', 'title': 'Accessible garden',
                            'sources': [{'title': 'Other topic', 'content': 'Stars shine.'}]})
    assert not result['highlights']
    assert 'No excerpts matched' in result['markdown']
    assert result['question_index'][0]['status'] == 'no_keyword_match'


@pytest.mark.parametrize('selected_model', [client.AUTO_MODEL, client.DENSE_MODEL])
def test_nonstream_research_template_completes_with_the_default_dense_budget(
        server, monkeypatch, selected_model):
    """Pin the observed truncation and prove the shorter built-in prompt avoids it."""
    monkeypatch.delenv('NEUROFORGE_MODEL', raising=False)
    server.app.preferences.update({'model': selected_model, 'max_tokens': 2048})
    source = client.SearchResponse('2026-09-29T00:00:00Z', [
        client.SearchResult('Garden guide', 'https://example.org/garden',
                            'Community gardens need a reliable water supply.')])
    requests = []
    completions = []

    def complete(path, body):
        requests.append((path, body))
        prompt = body['messages'][-1]['content']
        if 'expand the supported findings' in prompt:
            legacy = 'at most 450 words' in prompt
            target_words = 450 if legacy else 180
            phrase = 'Garden water evidence is relevant to planning'.split()
            words = (phrase * (target_words // len(phrase))
                     + phrase[:target_words % len(phrase)])
            content = ' '.join(words)
            finish = 'length' if legacy else 'stop'
            completion_tokens = 512 if legacy else 300
        elif 'Research Community gardens using' in prompt:
            content = 'Reliable water supply is relevant to community garden planning. https://example.org/garden'
            finish, completion_tokens = 'stop', 40
        else:
            content = 'Confirm local water access. Ask the site manager about costs. Check current funding rules.'
            finish, completion_tokens = 'stop', 30
        if 'expand the supported findings' in prompt:
            completions.append((len(content.split()), finish, completion_tokens))
        return {'model': client.DENSE_MODEL,
                'choices': [{'message': {'content': content}, 'finish_reason': finish}],
                'usage': {'prompt_tokens': 50, 'completion_tokens': completion_tokens,
                          'total_tokens': 50 + completion_tokens}}

    from sinter.templates import resolve_template
    current_template = resolve_template('research')
    legacy_template = copy.deepcopy(current_template)
    legacy_template.steps[1].prompt = legacy_template.steps[1].prompt.replace(
        'at most 180 words', 'at most 450 words')
    templates = {'legacy-research': legacy_template, 'research': current_template}
    def get_template(name):
        return templates[name] if name in templates else resolve_template(name)

    with (
        patch.object(
            client, '_get', return_value={'data': [{'id': client.DENSE_MODEL}]}
        ) as discover,
        patch.object(client, '_post', side_effect=complete),
        patch('sinter.templates.search', return_value=source),
        patch('sinter.server.resolve_template', side_effect=get_template),
    ):
        legacy_code, _, legacy_raw = post(server, '/api/template/run', {
            'template': 'legacy-research', 'variables': {'topic': 'Community gardens'}})
        current_code, _, current_raw = post(server, '/api/template/run', {
            'template': 'research', 'variables': {'topic': 'Community gardens'}})

    legacy = json.loads(legacy_raw)
    current = json.loads(current_raw)
    assert legacy_code == 502 and legacy['partial_result']['complete'] is False
    assert legacy['partial_result']['partial']['step'] == 'Expand'
    assert legacy['partial_result']['partial']['finish_reason'] == 'length'
    assert legacy['partial_result']['partial']['max_tokens'] == 512
    assert current_code == 200 and current['complete'] is True
    assert [row['step'] for row in current['results']] == [
        'Outline', 'Expand', 'Action Items']
    assert len(requests) == 5
    assert discover.call_count == (2 if selected_model == client.AUTO_MODEL else 0)
    assert all(path == '/chat/completions' for path, _ in requests)
    assert all(body['model'] == client.DENSE_MODEL and body['max_tokens'] == 512
               for _, body in requests)
    assert 'at most 450 words' in requests[1][1]['messages'][-1]['content']
    assert 'at most 180 words' in requests[3][1]['messages'][-1]['content']
    # This deterministic transport stub models truncation under a dense-token
    # API budget; it does not claim to reproduce a particular model tokenizer.
    assert completions == [(450, 'length', 512), (180, 'stop', 300)]


def test_research_question_matches_ignore_generic_question_words():
    result = workbench.run(workbench.example('research'))
    question = result['question_index'][1]
    assert question['matches']
    assert all('water' in row['quote'].lower() for row in question['matches'])


@pytest.mark.parametrize('kind', list(workbench.WORKFLOWS))
def test_workflow_examples_have_accurate_offline_labels(kind):
    with patch.object(client, 'search', side_effect=AssertionError('Network')), \
            patch.object(client, 'chat', side_effect=AssertionError('Network')):
        result = workbench.run(workbench.example(kind))
    assert result['demo'] is True
    assert 'FICTIONAL' in result['markdown'] or 'NOT REAL GRANT' in result['markdown']
    assert ('NOT REAL GRANT INFORMATION' in result['markdown']) == (kind == 'grants')


@pytest.mark.parametrize('consent', [False, None, 0, 1, 'true'])
def test_atlas_consent_rejected_before_job_admission(server, consent):
    with patch.object(client, 'chat', side_effect=AssertionError('Network')):
        status, _, raw = post(server, '/api/atlas/answer', {'consent': consent})
    assert status == 400
    assert 'Confirm that the selected atlas excerpts' in json.loads(raw)['error']
    assert json.loads(request(server, '/api/jobs')[2])['jobs'] == []


def test_research_question_citations_include_the_quote_and_offset():
    result = workbench.run({'workflow': 'research', 'title': 'Garden path accessibility volunteers',
                           'questions': 'What is the irrigation status?', 'sources': [{
                               'title': 'Garden notes', 'content':
                               'Garden path accessibility volunteers discussed seating.\n'
                               'Garden path accessibility volunteers discussed the gate.\n'
                               'Garden path accessibility volunteers discussed the schedule.\n'
                               'Irrigation remains unapproved.'}]})
    match = result['question_index'][0]['matches'][0]
    assert match['excerpt_id'] not in {row['id'] for row in result['excerpts']}
    assert match['quote'] in result['markdown']
    assert f"characters {match['start']}–{match['end']}" in result['markdown']


@pytest.mark.parametrize('endpoint', ['/api/chat', '/api/chat/job', '/api/chat/stream'])
@pytest.mark.parametrize('maximum', [1, 31, True, 8193])
def test_bad_token_budgets_fail_locally_without_admitting_a_job(server, endpoint, maximum):
    with patch.object(client, '_post', side_effect=AssertionError('Network')):
        code, _, raw = post(server, endpoint, {'messages': [{'role': 'user', 'content': 'Hello'}], 'max_tokens': maximum})
    assert code == 400
    assert '32' in json.loads(raw)['error']
    assert json.loads(request(server, '/api/jobs')[2])['jobs'] == []


def test_settings_reject_public_budget_but_allow_custom_provider_budget():
    assert validate({**DEFAULTS, 'max_tokens': 32})['max_tokens'] == 32
    with pytest.raises(ValueError, match='2,048'):
        validate({**DEFAULTS, 'max_tokens': 8192})
    assert validate({**DEFAULTS, 'api_url': 'https://example.org/v1', 'max_tokens': 8192})['max_tokens'] == 8192


@pytest.mark.parametrize('endpoint', ['/api/template/run', '/api/template/job'])
def test_failed_templates_retain_complete_and_partial_steps(server, endpoint):
    server.app.preferences.update({'model': client.MODEL})
    template = Template(name='Recovery fixture', description='A three-step fictional test', variables=[], steps=[
        Step('Extract', 'Extract the fictional notes'), Step('Draft', 'Prepare a draft'),
        Step('Check', 'Check the draft')])
    with patch('sinter.server.resolve_template', return_value=template), patch('sinter.templates.chat', side_effect=[
        client.ChatResult('Completed source extraction.', finish_reason='stop'),
        client.ChatResult('The received but incomplete draft', finish_reason='length'),
    ]) as model:
        code, _, raw = post(server, endpoint, {'template': 'fixture', 'variables': {}})
        value = json.loads(raw)
        if endpoint.endswith('/job'):
            assert code == 202
            for _ in range(100):
                job = json.loads(request(server, '/api/jobs/' + value['id'])[2])
                if job['status'] == 'failed':
                    break
                time.sleep(.01)
            assert job['status'] == 'failed'
            result = job['result']
            assert json.loads(request(server, '/api/jobs')[2])['jobs'][0]['has_result']
        else:
            assert code == 502
            result = value['partial_result']
        assert model.call_count == 2
        assert result['complete'] is False
        assert result['results'][0]['content'] == 'Completed source extraction.'
        assert result['partial']['content'] == 'The received but incomplete draft'
        assert result['partial']['finish_reason'] == 'length'


def test_later_search_failure_keeps_received_template_work(monkeypatch):
    monkeypatch.setenv('NEUROFORGE_MODEL', client.MODEL)
    template = Template('Later search', '', steps=[Step('Draft', 'Draft the supplied notes'),
        Step('Search', 'Search for context', use_search=True)])
    with patch('sinter.templates.chat', return_value=client.ChatResult('Received draft.', finish_reason='stop')) as model, \
            patch('sinter.templates.search', side_effect=client.APIError('Search unavailable')) as search:
        with pytest.raises(TemplateRunError) as error:
            collect_run(template, {'topic': 'Community garden'})
    assert error.value.partial_result['results'][0]['content'] == 'Received draft.'
    assert error.value.partial_result['complete'] is False
    assert 'Search unavailable' in error.value.partial_result['error']
    assert model.call_count == search.call_count == 1
