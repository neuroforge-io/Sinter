"""A reviewed correction keeps its original transcript source, across clocks."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from sinter import workbench

NOTES = ('Alex: We agreed to request a coat; no purchase was approved.\n'
         'Sam: I will ask for the written estimate.')
FIRST = '2026-10-16T04:20:27+00:00'
LATER = '2026-10-16T04:20:28+00:00'
CHANGE = {'segment_id': 'T0001',
          'original': 'We agreed to request a coat; no purchase was approved.',
          'replacement': 'We agreed to request a quote; no purchase was approved.',
          'reason': 'Fictional operator confirmed quote, not coat.'}


def prepare(at, **changes):
    with patch('sinter.evidence.utc_now', return_value=at), \
            patch('sinter.workbench.utc_now', return_value=at):
        return workbench.run({'workflow': 'meeting', 'title': 'Fictional meeting',
                              'notes': NOTES, **changes})


def source_pin(report):
    return {key: report['sources'][0][key]
            for key in ('id', 'sha256', 'retrieved_at')}


def test_correction_keeps_exact_source_while_recording_new_preparation_time():
    first = prepare(FIRST)
    untouched = deepcopy(first)
    corrected = prepare(LATER, corrections=[deepcopy(CHANGE)],
                        transcript_source=source_pin(first))
    assert corrected['sources'] == first['sources']
    assert corrected['created_at'] == LATER != first['created_at']
    assert corrected['segments'] == first['segments']
    assert corrected['corrections'] == [{**CHANGE, 'author': 'human reviewer'}]
    assert corrected['sources'][0]['content'] == NOTES
    assert first == untouched


def test_fresh_preparation_has_its_own_capture_but_derivations_retain_history():
    first = prepare(FIRST)
    pin = source_pin(first)
    fresh = prepare(LATER)
    assert fresh['sources'][0]['retrieved_at'] == LATER
    assert fresh['sources'][0]['id'] == first['sources'][0]['id']
    corrected = prepare(LATER, transcript_source=pin, corrections=[CHANGE])
    later = prepare('2026-10-16T04:20:29+00:00',
                    transcript_source=source_pin(corrected), corrections=[CHANGE])
    assert later['sources'] == corrected['sources'] == first['sources']
    assert later['created_at'] != corrected['created_at']
    changed = prepare(LATER, notes=NOTES + '\nAlex: We still need approval.')
    assert changed['sources'][0]['id'] != first['sources'][0]['id']


def test_whitespace_and_unicode_remain_exact_in_the_source_snapshot():
    raw = ' \nAlex: Café and cafe\u0301 are recorded verbatim.  \n'
    first = prepare(FIRST, notes=raw)
    later = prepare(LATER, notes=raw, transcript_source=source_pin(first))
    assert first['sources'][0]['content'] == raw
    assert later['sources'] == first['sources']


@pytest.mark.parametrize('pin', [None, {}, [], '', {'id': 'missing fields'}])
def test_explicit_malformed_pin_never_falls_back_to_a_fresh_capture(pin):
    with patch('sinter.workbench.minutes') as minutes, \
            patch('sinter.client.chat') as model, \
            patch('sinter.client.search') as search, \
            pytest.raises(ValueError, match='transcript'):
        prepare(LATER, transcript_source=pin)
    minutes.assert_not_called()
    model.assert_not_called()
    search.assert_not_called()


@pytest.mark.parametrize(('key', 'value'), [
    ('id', 'S' + '0' * 16), ('id', None),
    ('sha256', '0' * 64), ('sha256', False),
    ('retrieved_at', ''), ('retrieved_at', None),
    ('retrieved_at', '2026-10-16T04:20:27'),
    ('retrieved_at', '2026-02-30T04:20:27+00:00'),
    ('retrieved_at', ' 2026-10-16T04:20:27+00:00'),
    ('retrieved_at', '2026-10-16'),
    ('extra', 'unsupported'),
])
def test_invalid_or_mismatched_metadata_stops_before_processing(key, value):
    pin = {**source_pin(prepare(FIRST)), key: value}
    with patch('sinter.workbench.minutes') as minutes, \
            pytest.raises(ValueError, match='transcript'):
        prepare(LATER, transcript_source=pin)
    minutes.assert_not_called()


def test_changed_or_corrected_text_cannot_borrow_the_old_source_pin():
    first = prepare(FIRST)
    original = deepcopy(first)
    for notes in (NOTES + '\nNew evidence.', NOTES.replace('coat', 'quote')):
        with patch('sinter.workbench.minutes') as minutes, \
                pytest.raises(ValueError, match='original notes'):
            prepare(LATER, notes=notes, transcript_source=source_pin(first))
        minutes.assert_not_called()
    assert first == original


@pytest.mark.parametrize('timestamp', [
    FIRST, '2026-10-16T04:20:27Z', '2026-10-16T04:20:27.123456+00:00',
    '2026-10-16T14:20:27+10:00',
])
def test_valid_historical_timestamp_spelling_is_preserved(timestamp):
    first = prepare(FIRST)
    pinned = {**source_pin(first), 'retrieved_at': timestamp}
    result = prepare(LATER, transcript_source=pinned)
    assert result['sources'][0]['retrieved_at'] == timestamp
    assert result['sources'][0]['sha256'] == first['sources'][0]['sha256']


def test_transcript_pin_is_not_an_instruction_for_another_workflow():
    with patch('sinter.client.search') as search, \
            pytest.raises(ValueError, match='only to meeting'):
        workbench.run({'workflow': 'brief', 'title': 'Fictional letter',
                       'use_search': True, 'query': 'fictional query',
                       'transcript_source': None})
    search.assert_not_called()
