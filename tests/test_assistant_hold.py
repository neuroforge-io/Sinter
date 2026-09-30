"""A retained action cannot silently become current work through assistance."""
from unittest.mock import patch

import pytest

from sinter import assistant, client
from sinter.campaigns import CampaignStore


@pytest.fixture
def saved_hold(tmp_path):
    store = CampaignStore(tmp_path)
    record = store.save({
        'title': 'Fictional held study', 'organisation': 'Example Club',
        'opportunities': [{'name': 'Example route', 'status': 'open'}],
        'actions': [{'task': 'Earlier fictional study', 'status': 'held',
                     'opportunity': 'Example route', 'scope_confirmed': True,
                     'owner': '', 'due': ''}],
    })
    payload = {'id': record['id'], 'revision': record['revision'],
               'opportunity': 'Example route', 'actions': [0],
               'task': 'next_actions'}
    return store, record, payload


def test_held_next_action_refused_before_any_connection_or_model(saved_hold):
    store, record, payload = saved_hold
    before = store.get(record['id'])
    with patch.object(client, 'chat') as model, \
            patch.object(client, 'list_models') as discovery:
        with pytest.raises(ValueError, match='Resume it explicitly'):
            assistant.preview(store, payload)
        with pytest.raises(ValueError, match='Resume it explicitly'):
            assistant.run(store, {**payload, 'consent': True,
                                  'context_hash': 'old-preview'})
    model.assert_not_called()
    discovery.assert_not_called()
    assert store.get(record['id']) == before


@pytest.mark.parametrize('task', ['eligibility', 'enquiry'])
def test_other_tasks_keep_held_history_explicit_and_unchanged(saved_hold, task):
    store, record, payload = saved_hold
    before = store.get(record['id'])
    with patch.object(client, 'chat') as model:
        result = assistant.preview(store, {**payload, 'task': task})
    model.assert_not_called()
    assert result['context']['selected_actions'][0]['status'] == 'held'
    assert ('Do not recommend held or completed selected actions as current work.'
            in result['content'])
    assert store.get(record['id']) == before


def test_explicit_resume_requires_current_revision_and_new_preview(saved_hold):
    store, record, payload = saved_hold
    record['document']['actions'][0]['status'] = 'open'
    resumed = store.save(record['document'], record['id'], record['revision'])
    with pytest.raises(ValueError, match='campaign changed'):
        assistant.preview(store, payload)
    with patch.object(client, 'chat') as model:
        result = assistant.preview(store, {**payload, 'revision': resumed['revision']})
    model.assert_not_called()
    assert result['context']['selected_actions'][0]['status'] == 'open'
