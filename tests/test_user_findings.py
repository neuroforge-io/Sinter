"""Regressions from the September 12 user-testing session."""
import json
from unittest.mock import patch

import pytest

from sinter import client, workbench
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
