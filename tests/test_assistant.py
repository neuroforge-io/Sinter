"""Campaign context selection, revision pins, consent and partial recovery."""
import copy
from unittest.mock import patch

import pytest
from test_campaigns import campaign

from sinter import assistant, client
from sinter.campaigns import CampaignStore


@pytest.fixture
def saved(tmp_path):
    store = CampaignStore(tmp_path)
    document = campaign()
    document['communications'] = [{
        'subject': 'PRIVATE MAIL', 'content': 'PRIVATE BODY', 'opportunity': '',
    }]
    result = store.save(document)
    return store, result, {
        'id': result['id'], 'revision': result['revision'],
        'opportunity': document['opportunities'][0]['name'],
        'checks': [0], 'task': 'eligibility', 'question': '',
    }


def test_preview_sends_only_selected_context_without_network(saved):
    store, record, payload = saved
    before = copy.deepcopy(store.get(record['id']))
    with patch.object(client, 'chat') as model:
        preview = assistant.preview(store, payload)
    model.assert_not_called()
    assert 'Confirm the applicant type' in preview['content']
    assert 'PRIVATE BODY' not in preview['content']
    assert 'PRIVATE MAIL' not in preview['content']
    assert 'Provide shared swim equipment.' not in preview['content']
    assert preview['bytes'] == len(preview['content'].encode('utf-8'))
    assert store.get(record['id']) == before


@pytest.mark.parametrize('purpose', ['discussion', 'research'])
def test_planning_preview_scopes_context_without_inferred_grant(saved, purpose):
    store, record, payload = saved
    record['document']['opportunities'][0]['purpose'] = purpose
    record['document']['opportunities'][0]['application_mode'] = 'unknown'
    updated = store.save(record['document'], record['id'], record['revision'])
    before = copy.deepcopy(updated)
    with patch.object(client, 'chat') as model:
        preview = assistant.preview(store, {**payload, 'revision': updated['revision']})
    model.assert_not_called()
    assert preview['context']['route']['purpose'] == purpose
    assert 'Do not assume it is a grant application' in preview['content']
    assert 'questions for the funder' not in preview['content']
    assert 'PRIVATE BODY' not in preview['content']
    assert store.get(record['id']) == before


def test_preview_preserves_absent_purpose_and_required_application_scope(saved):
    store, record, payload = saved
    original = assistant.preview(store, payload)
    assert 'purpose' not in original['context']['route']
    route = record['document']['opportunities'][0]
    route.update(purpose='research', application_mode='required')
    updated = store.save(record['document'], record['id'], record['revision'])
    preview = assistant.preview(store, {**payload, 'revision': updated['revision']})
    assert preview['context']['route']['purpose'] == 'research'
    assert 'questions for the funder' in preview['content']
    assert 'purpose conflicts with the application workflow' in preview['content']
    assert 'Do not assume it is a grant application' not in preview['content']
    assert preview['context_hash'] != original['context_hash']


def test_application_purpose_does_not_resolve_no_form_workflow_by_assumption(saved):
    store, record, payload = saved
    record['document']['opportunities'][0].update(
        purpose='application', application_mode='not_required')
    updated = store.save(record['document'], record['id'], record['revision'])
    with patch.object(client, 'chat') as model:
        preview = assistant.preview(store, {**payload, 'revision': updated['revision']})
    model.assert_not_called()
    assert 'explicit local reconciliation' in preview['content']
    assert 'do not resolve the conflict by assumption' in preview['content']
    assert preview['context']['route']['application_mode'] == 'not_required'


def test_consent_and_preview_hash_required_before_any_model_request(saved):
    store, _, payload = saved
    with patch.object(client, 'chat') as model:
        with pytest.raises(ValueError, match='Confirm'):
            assistant.run(store, payload)
        with pytest.raises(ValueError, match='context changed'):
            assistant.run(store, {**payload, 'consent': True,
                                  'context_hash': 'different'})
    model.assert_not_called()


def test_campaign_revision_change_invalidates_approved_preview(saved):
    store, record, payload = saved
    preview = assistant.preview(store, payload)
    record['document']['objective'] = 'Updated objective'
    store.save(record['document'], record['id'], record['revision'])
    with patch.object(client, 'chat') as model:
        with pytest.raises(ValueError, match='campaign changed'):
            assistant.run(store, {**payload, 'consent': True,
                                  'context_hash': preview['context_hash']})
    model.assert_not_called()


@pytest.mark.parametrize('indexes', [[True], [-1], [0, 0], [100], 'all'])
def test_invalid_check_selection_rejected(saved, indexes):
    store, _, payload = saved
    with pytest.raises(ValueError):
        assistant.preview(store, {**payload, 'checks': indexes})


def test_draft_keeps_model_output_separate_from_campaign(saved):
    store, record, payload = saved
    before = store.get(record['id'])
    preview = assistant.preview(store, payload)
    with patch.object(client, 'chat', return_value=client.ChatResult(
            'Ask the funder to confirm applicant type.', finish_reason='stop')):
        report = assistant.run(store, {**payload, 'consent': True,
                                      'context_hash': preview['context_hash']})
    assert report['model_draft'] is True
    assert store.get(record['id']) == before


def test_partial_answer_remains_recoverable_and_never_complete(saved):
    store, _, payload = saved
    preview = assistant.preview(store, payload)
    with patch.object(client, 'chat', return_value=client.ChatResult(
            'Incomplete suggestion', finish_reason='length')):
        with pytest.raises(client.IncompleteGeneration) as failure:
            assistant.run(store, {**payload, 'consent': True,
                                  'context_hash': preview['context_hash']})
    assert failure.value.partial_result['result']['content'] == 'Incomplete suggestion'
    assert failure.value.partial_result['incomplete'] is True
    assert failure.value.partial_result['document_markdown'].startswith(
        '**INCOMPLETE MODEL DRAFT')
    assert failure.value.partial_result['markdown'].startswith('INCOMPLETE MODEL')


def test_stream_failure_before_chat_returns_keeps_the_approved_evidence(saved):
    store, record, payload = saved
    before = store.get(record['id'])
    preview = assistant.preview(store, payload)
    partial = client.ChatResult('Useful received text', 30, 20, 50,
                                'incomplete', 'selected-model')
    interruption = client.IncompleteGeneration(
        partial, 512, message='The stream ended without matching final text.')
    with patch.object(client, 'chat', side_effect=interruption) as model:
        with pytest.raises(client.IncompleteGeneration) as failure:
            assistant.run(store, {**payload, 'consent': True,
                                  'context_hash': preview['context_hash']})
    model.assert_called_once()
    report = failure.value.partial_result
    assert report['result']['content'] == partial.content
    assert report['result']['finish_reason'] == 'incomplete'
    assert report['result']['model'] == 'selected-model'
    assert report['context'] == preview['context']
    assert report['request_content'] == preview['content']
    assert report['context_hash'] == preview['context_hash']
    assert report['revision'] == record['revision']
    assert report['warnings'][0] == str(interruption)
    assert store.get(record['id']) == before


def test_connection_switch_invalidates_approved_preview(saved):
    store, _, payload = saved
    first = {'api_url': 'https://one.example/v1', 'provider': 'openai-compatible',
             'model': 'model-a', 'max_tokens': 512, 'api_key': 'private-a'}
    with client.connection_settings(first):
        approved = assistant.preview(store, payload)
    assert 'private-a' not in str(approved)
    with client.connection_settings({**first, 'api_url': 'https://two.example/v1'}):
        with patch.object(client, 'chat') as model:
            with pytest.raises(ValueError, match='context changed'):
                assistant.run(store, {**payload, 'consent': True,
                                      'context_hash': approved['context_hash']})
    model.assert_not_called()


def test_native_context_fit_rejected_before_generation(saved):
    store, record, payload = saved
    record['document']['requirements'][0]['source_quote'] = 'Long quote ' * 250
    updated = store.save(record['document'], record['id'], record['revision'])
    payload = {**payload, 'revision': updated['revision']}
    with client.connection_settings({'api_url': client.BASE_URL,
            'model': client.NATIVE_MODEL, 'max_tokens': 128,
            'provider': 'openai-compatible'}):
        prepared = assistant.preview(store, payload)
        assert prepared['fit']['allowed'] is False
        with patch.object(client, 'chat') as model:
            with pytest.raises(ValueError, match='2,048|2048'):
                assistant.run(store, {**payload, 'consent': True,
                                      'context_hash': prepared['context_hash']})
        model.assert_not_called()


def test_selected_completed_action_is_visible_and_export_keeps_provenance(saved):
    store, _, payload = saved
    payload = {**payload, 'actions': [0]}
    with client.connection_settings({'api_url': 'https://compatible.example/v1',
            'provider': 'openai-compatible', 'model': 'fixture-model',
            'max_tokens': 512}):
        prepared = assistant.preview(store, payload)
        assert (prepared['context']['selected_actions'][0]['task']
                == 'Obtain training quotes')
        with patch.object(client, 'chat', return_value=client.ChatResult(
                'Suggestion.', finish_reason='stop')):
            report = assistant.run(store, {**payload, 'consent': True,
                                          'context_hash': prepared['context_hash']})
    assert report['request_content'] == prepared['content']
    assert report['context_hash'] in report['markdown']
    assert 'MODEL SUGGESTION' in report['markdown']
    assert report['document_markdown'] == 'Suggestion.'
    assert report['connection']['model'] == 'fixture-model'
