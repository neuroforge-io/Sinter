"""Evidence, grant and transcript invariants. Fixtures are fictional, never live claims."""
import json
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import client
from sinter.evidence import collect, excerpts, render_evidence, select, source, validate_excerpt
from sinter.grants import confirmed_deadline, screen
from sinter.meetings import minutes, parse_transcript
from sinter.templates import load_template_file, render_prompt, template_events, get_builtin_template
from sinter.workbench import example, run


@pytest.mark.parametrize('kind', ['grants', 'brief', 'meeting'])
def test_examples_are_offline_traceable_drafts(kind):
    with patch.object(client, 'chat', side_effect=AssertionError('unexpected network')), patch.object(client, 'search', side_effect=AssertionError('unexpected network')):
        result = run(example(kind))
    assert result['demo'] is True
    assert result['review_status'] == 'draft'
    assert result['sources']
    assert 'FICTIONAL' in result['markdown']
    if kind == 'grants':
        assert result['screening']['status'] == 'review_required'


@pytest.mark.parametrize('flag', ['use_model', 'use_search'])
def test_examples_reject_remote_processing(flag):
    payload = example('brief'); payload[flag] = True
    with pytest.raises(ValueError, match='offline'):
        run(payload)


def test_source_identity_and_exact_offsets():
    original = source('Reference', 'Garden grant.\nDo not approve spending.\n' + 'garden ' * 150, 'https://example.org/guide', 'reference_excerpt')
    duplicate = source('Renamed', original.content, original.url, original.kind)
    assert original.id == duplicate.id
    assert original.sha256 != source('Changed', original.content + '!').sha256
    for excerpt in excerpts([original]):
        assert validate_excerpt(excerpt, [original])
        assert original.content[excerpt.start:excerpt.end] == excerpt.quote
        assert not validate_excerpt(replace(excerpt, quote='fabricated'), [original])
    with pytest.raises(ValueError, match='no longer matches'):
        render_evidence([replace(excerpts([original])[0], end=999999)], [original])


def test_collect_deduplicates_and_enforces_total_limit():
    row = {'title': 'A', 'content': 'same'}
    assert len(collect([row, row])) == 1
    with pytest.raises(ValueError, match='Combined sources'):
        collect([{'content': 'x' * 110000}, {'content': 'y' * 110000}])


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'file:///tmp/a', 'https://a@host.test', 'https://host.test/\nx', 'https://host.test\\@evil.test'])
def test_unsafe_reference_links_rejected(url):
    with pytest.raises(ValueError):
        source('A', 'Evidence', url)


@pytest.mark.parametrize('reply', ['not json', '{"evidence_ids":["made-up"]}', '{"evidence_ids":[{}]}', 'null', '{"evidence_ids":[]}'])
def test_model_cannot_invent_evidence(reply):
    refs = [source('A', 'Spending was not approved.\nObtain quotes first.')]
    expected, _ = select(refs, 'spending')
    with patch.object(client, 'chat', return_value=client.ChatResult(reply)):
        actual, warnings = select(refs, 'spending', True)
    assert actual == expected and any('discarded' in warning for warning in warnings)


def test_model_can_only_reorder_existing_ids():
    refs = [source('A', 'First relevant line.\nSecond relevant line.')]
    before, _ = select(refs, 'relevant')
    with patch.object(client, 'chat', return_value=client.ChatResult(json.dumps({'evidence_ids': [before[-1].id]}))):
        after, _ = select(refs, 'relevant', True)
    assert after[0] == before[-1] and set(after) == set(before)


def test_search_sources_keep_urls_and_current_snapshot():
    response = client.SearchResponse('2026-09-10T00:00:00Z', [client.SearchResult('Example guide', 'https://example.org', 'Applicants must confirm requirements.')])
    with patch.object(client, 'search', return_value=response):
        result = run({'workflow': 'grants', 'title': 'Garden', 'use_search': True, 'query': 'garden grant'})
    assert result['sources'][0]['url'] == 'https://example.org'
    assert result['sources'][0]['retrieved_at'] == response.retrieved_at
    assert result['screening']['status'] == 'review_required'


@pytest.mark.parametrize('kind', ['sample', 'user_note', 'transcript'])
def test_non_authoritative_sources_cannot_pass_grant_check(kind):
    ref = source('A', 'Applicants must be P&C associations.', kind=kind)
    rule = {'field': 'organisation_type', 'operator': 'equals', 'value': 'P&C', 'quote': ref.content, 'source_id': ref.id, 'confirmed': True}
    assert screen({'organisation_type': 'P&C'}, [rule], [ref])['checks'][0]['status'] == 'unknown'


@pytest.mark.parametrize('actual,expected,operator,status', [(500, 500, 'minimum', 'met'), (501, 500, 'maximum', 'not_met'), (True, 1, 'minimum', 'unknown'), ('NaN', 100, 'minimum', 'unknown'), ('inf', 100, 'maximum', 'unknown')])
def test_numeric_grant_requirements(actual, expected, operator, status):
    ref = source('A', 'Budget limit as quoted.', kind='reference_excerpt')
    rule = {'field': 'budget', 'operator': operator, 'value': expected, 'quote': ref.content, 'source_id': ref.id, 'confirmed': True}
    output = screen({'budget': actual}, [rule], [ref])
    assert output['checks'][0]['status'] == status
    assert output['status'] == 'review_required'


@pytest.mark.parametrize('value', ['2026-02-30', '2026-1-01', '', 'not a date'])
def test_invalid_deadlines(value):
    with pytest.raises(ValueError):
        confirmed_deadline(value)


@pytest.mark.parametrize('value,speaker', [
    ('Alex: We did not approve funding.', 'Alex'),
    ('No speakers supplied.', 'Unidentified'),
    ('1\n00:00:01,000 --> 00:00:02,000\nNo vote was taken.\n', 'Unidentified'),
    ('WEBVTT\n\n00:01.000 --> 00:02.000\n<v Alex>No vote was taken.</v>\n', 'Alex'),
    (json.dumps({'segments': [{'speaker': 'A', 'text': 'No vote.', 'start': 0, 'end': 1}]}), 'A')])
def test_transcript_formats(value, speaker):
    result = parse_transcript(value)
    assert len(result) == 1 and result[0].speaker == speaker
    assert result[0].id == 'T0001'


@pytest.mark.parametrize('row', [{'text': 'a', 'start': 1, 'end': 0}, {'text': 'a', 'start': 0}, {'text': 'a', 'start': float('nan'), 'end': 1}, {'text': ''}])
def test_invalid_transcript_segments(row):
    with pytest.raises(ValueError):
        parse_transcript(json.dumps([row]))


def test_corrections_preserve_original_and_reason():
    change = {'segment_id': 'T0001', 'original': 'We did approve.', 'replacement': 'We did not approve.', 'reason': 'Checked recording at 00:05.'}
    result = minutes('Meeting', 'A: We did approve.', {'A': 'Alex'}, [change])
    assert result['segments'][0]['text'] == 'We did approve.'
    assert result['corrections'][0]['replacement'] == 'We did not approve.'
    assert 'NOT APPROVED' in result['markdown']
    with pytest.raises(ValueError, match='original transcript changed'):
        minutes('Meeting', 'A: Different words.', {}, [change])


def test_unknown_speakers_not_guessed_and_negation_preserved():
    result = minutes('Meeting', 'No vote was taken.\nNobody agreed to spend money.')
    assert all(row['status'] == 'needs_review' for row in result['candidates'])
    assert 'No vote was taken.' in result['markdown']
    with pytest.raises(ValueError, match='cannot all be assigned'):
        minutes('Meeting', 'Unknown speaker.', {'Unidentified': 'Alex'})


def test_template_substitution_does_not_reinterpret_user_data():
    assert render_prompt('{{input}} {{previous}}', {'input': '{{previous}}', 'previous': 'history'}) == '{{previous}} history'


def test_template_search_and_history_shared_in_streaming_mode():
    response = client.SearchResponse('now', [client.SearchResult('Guide', 'https://example.org/guide', 'Quoted evidence')])
    calls = []
    def chat(messages, **kwargs):
        calls.append(messages)
        return client.ChatResult('Reply', finish_reason='stop')
    def stream(messages, **kwargs):
        calls.append(messages)
        yield 'Streamed reply'
    with patch('sinter.templates.search', return_value=response), patch('sinter.templates.chat', side_effect=chat), patch('sinter.templates.chat_stream', side_effect=stream):
        events = list(template_events(get_builtin_template('research'), {'topic': 'garden'}, stream=True))
    assert any(e['type'] == 'sources' for e in events)
    assert 'https://example.org/guide' in calls[0][-1].content
    assert any(m.role == 'assistant' and m.content == 'Reply' for m in calls[1])
    assert len([e for e in events if e['type'] == 'step_done']) == 3


@pytest.mark.parametrize('name', ['research.yaml', 'code-review.yaml'])
def test_shipped_templates_are_supported(name):
    assert load_template_file(Path(__file__).parents[1] / 'templates' / name).steps
