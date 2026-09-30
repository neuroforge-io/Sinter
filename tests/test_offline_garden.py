"""The customer practice bundle stays useful without models or inferred facts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

from sinter import campaigns, casebooks, client
from sinter.store import Store

BUNDLE = Path(__file__).resolve().parents[1] / 'examples' / 'offline-garden'


def document(name: str) -> dict:
    return json.loads((BUNDLE / name).read_text(encoding='utf-8'))


def test_garden_casebook_restores_originals_format_and_unanswered_question(tmp_path):
    original = document('casebook.json')
    before = copy.deepcopy(original)
    with patch.object(client, '_open', side_effect=AssertionError('Offline only')) as network:
        repository = casebooks.Casebooks(Store(tmp_path))
        saved = repository.save(original)
        reopened = casebooks.Casebooks(Store(tmp_path)).get(saved['id'])
        restored = repository.save(json.loads(json.dumps(reopened['document'])))
        report = casebooks.build(restored['document'])
    network.assert_not_called()
    assert original == before
    assert restored['id'] != saved['id']
    assert restored['document']['documents'] == original['documents']
    assert report['document_type'] == 'handover'
    assert 'Handover next steps' in report['document_markdown']
    assert report['coverage']['exhaustive_review'] is False
    insurance = next(row for row in report['question_index']
                     if row['question'] == 'What insurance excess applies?')
    assert insurance['status'] == 'no_wording_match'
    assert not insurance['excerpt_ids']


def test_garden_campaign_keeps_ownership_targets_and_old_source_snapshot(tmp_path):
    original = document('campaign.json')
    before = copy.deepcopy(original)
    with patch.object(client, '_open', side_effect=AssertionError('Offline only')) as network:
        repository = campaigns.CampaignStore(tmp_path)
        saved = repository.save(original)
        reopened = campaigns.CampaignStore(tmp_path).get(saved['id'])
        restored = repository.save(json.loads(json.dumps(reopened['document'])))
        report = campaigns.prepare(restored['document'])
    network.assert_not_called()
    assert original == before
    assert restored['id'] != saved['id']
    assert restored['document'] == reopened['document']
    actions = restored['document']['actions']
    assert [row['owner_kind'] for row in actions[:3]] == ['unassigned', 'unknown', 'role']
    assert not any(row['owner_confirmed'] for row in actions)
    assert actions[1]['due'] == '2026-10-09'
    assert not restored['document']['opportunities'][0]['deadline']
    older_check = restored['document']['requirements'][1]
    source = next(row for row in restored['document']['sources']
                  if row['id'] == older_check['source_id'])
    assert older_check['source_url'] != source['url']
    assert older_check['checked_at'] != source['checked_at']
    assert older_check['source_quote'] == before['requirements'][1]['source_quote']
    assert 'proposed' in report['markdown'].lower()
    assert 'not confirmed' in report['markdown'].lower()
    historical = restored['document']['answers'][0]
    assert 'Not submitted.' in historical['text']
    assert restored['document']['opportunities'][1]['status'] == 'closed'
    assert historical['text'] not in report['document_markdown']
    assert historical['text'] not in report['markdown']
