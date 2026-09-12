"""Regressions from the September 12 user-testing session."""
import json
import time
from unittest.mock import patch

import pytest

from sinter import client, workbench
from sinter.preferences import DEFAULTS, validate
from sinter.templates import Step, Template
from sinter.template_runs import TemplateRunError, collect_run
from test_runtime import post, request, server


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


def test_later_search_failure_keeps_received_template_work():
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
