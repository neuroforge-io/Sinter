"""Regression checks for source-only writing and reviewable recognition."""
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sinter import speech
from sinter.briefs import question_index
from sinter.client import ChatResult
from sinter.evidence import source
from sinter.jobs import Cancelled
from sinter.meetings import minutes, parse_transcript
from sinter.templates import resolve_template, run_template
from sinter.transcript_export import export_transcript
from sinter.workbench import example, run


@pytest.mark.parametrize('kind,heading', [('enquiry', 'Draft enquiry letter'), ('agenda', 'Draft agenda item'), ('briefing', 'Briefing note')])
def test_document_formats(kind, heading):
    report = run({**example('brief'), 'document_type': kind, 'recipient': '<script>person</script>'})
    assert heading in report['markdown'] and '<script>' not in report['markdown']
    assert report['document_type'] == kind and report['review_status'] == 'draft'
    assert 'Keyword matches' in report['markdown']


def test_question_guide_preserves_negation_and_exact_offsets():
    sources = [source('Guidance', 'Hearing assistance is NOT available.\nAsk about a ramp.')]
    index = question_index('Is hearing assistance available?\nWhat insurance is required?', sources)
    assert index[0]['status'] == 'related_material' and 'NOT' in index[0]['matches'][0]['quote']
    assert index[1]['status'] == 'no_keyword_match'
    for row in index:
        for match in row['matches']:
            assert sources[0].content[match['start']:match['end']] == match['quote']


@pytest.mark.parametrize('value', ['bad', 3, []])
def test_bad_document_format(value):
    with pytest.raises(ValueError):
        run({**example('brief'), 'document_type': value})


def test_question_limit():
    with pytest.raises(ValueError, match='30 questions'):
        question_index('\n'.join(f'Question {i}' for i in range(31)), [])


@pytest.mark.parametrize('name', ['enquiry-letter', 'agenda-item', 'action-register', 'grant-checklist'])
def test_recipes_preserve_original_context(name):
    template = resolve_template(name)
    assert len(template.steps) == 3 and 'review required' in template.description
    with patch('sinter.templates.chat', return_value=ChatResult('Draft', finish_reason='stop')) as model:
        run_template(template, {key: 'No vote was taken.' for key in template.variables})
    messages = model.call_args.args[0]
    assert any('No vote was taken.' in message.content for message in messages)
    assert 'not independent verification' in messages[-1].content


@pytest.fixture
def engine(tmp_path, monkeypatch):
    recording = tmp_path / 'recording.wav'
    recording.write_bytes(b'fixture recording')
    word = SimpleNamespace(start=0., end=1., word=' No', probability=.3)
    segment = SimpleNamespace(start=0., end=1., text='No vote was taken.', avg_logprob=-.5,
                              no_speech_prob=.1, compression_ratio=1., words=[word])
    calls = []
    class Engine:
        supported_languages = ['en', 'fr']
        def __init__(self, model, **kwargs):
            calls.append(('load', kwargs))
        def transcribe(self, audio, **kwargs):
            calls.append(('transcribe', kwargs))
            return iter([segment]), SimpleNamespace(duration=2., language='en')
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=Engine))
    monkeypatch.setattr(speech, '_CACHE', None)
    return recording, segment, calls


def test_words_flags_and_recording_provenance(engine):
    result = speech.transcribe(engine[0], consent=True, language='en')
    assert result['segments'][0]['words'][0]['probability'] == .3
    assert result['review_count'] == 1 and len(result['audio_sha256']) == 64
    assert result['segments'][0]['id'] == 'T0001'
    calls = engine[2]
    assert calls[0][1]['local_files_only'] is True
    assert calls[1][1]['condition_on_previous_text'] is False
    assert calls[1][1]['hallucination_silence_threshold'] == 2
    assert calls[1][1]['language'] == 'en'
    report = minutes('Test', json.dumps(result))
    assert report['segments'][0]['review_flags']
    assert 'Passages requiring an audio check' in report['markdown']


def test_channel_labels_are_not_identity(engine):
    with patch.object(speech, '_channel_inputs', return_value=[('left', 'CHANNEL_1'), ('right', 'CHANNEL_2')]):
        result = speech.transcribe(engine[0], consent=True, split_channels=True)
    assert {row['speaker'] for row in result['segments']} == {'CHANNEL_1', 'CHANNEL_2'}
    assert result['channel_separation'] and result['speaker_diarization'] is False


@pytest.mark.parametrize('options', [{'model': 'base.en', 'language': 'fr'}, {'language': 'english'},
    {'language': []}, {'split_channels': 'yes'}, {'allow_download': 'yes'}, {'language': 'zz'}])
def test_speech_option_validation(engine, options):
    with pytest.raises(ValueError):
        speech.transcribe(engine[0], consent=True, **options)
    assert not speech._LOCK.locked()


@pytest.mark.parametrize('attribute,value', [('start', float('nan')), ('end', -1.), ('end', 10.)])
def test_bad_engine_times_are_rejected(engine, attribute, value):
    setattr(engine[1], attribute, value)
    with pytest.raises(ValueError):
        speech.transcribe(engine[0], consent=True)
    assert not speech._LOCK.locked()


def test_cancellation_releases_engine(engine):
    def cancelled(message):
        raise Cancelled()
    with pytest.raises(Cancelled):
        speech.transcribe(engine[0], consent=True, progress=cancelled)
    assert not speech._LOCK.locked()


def test_model_cache_reuse(engine):
    speech.transcribe(engine[0], consent=True, allow_download=True)
    speech.transcribe(engine[0], consent=True)
    assert sum(name == 'load' for name, _ in engine[2]) == 1


def test_empty_speech_stays_empty(engine):
    engine[1].text = ' '
    result = speech.transcribe(engine[0], consent=True)
    assert result['segments'] == [] and result['status'] == 'no_speech'


@pytest.mark.parametrize('format', ['srt', 'vtt', 'txt', 'json'])
def test_transcript_export(engine, format):
    result = speech.transcribe(engine[0], consent=True)
    output = export_transcript(result, format)
    assert 'No vote was taken.' in output
    if format in {'srt', 'vtt'}:
        assert '-->' in output
    if format == 'json':
        assert json.loads(output)['audio_sha256'] == result['audio_sha256']


def test_subtitles_escape_text_and_cue_markers():
    data = {'segments': [{'start': 0, 'end': 1, 'text': '<b>Hello</b>\n\n00:00:01 --> 00:00:10\nFAKE', 'speaker': 'Speaker'}]}
    output = export_transcript(data, 'vtt')
    assert '<b>' not in output and output.count('-->') == 1


def test_untimed_subtitles_are_rejected():
    with pytest.raises(ValueError):
        export_transcript({'segments': [{'text': 'No timing'}]}, 'srt')


@pytest.mark.parametrize('flags', ['unsafe', [1], ['x' * 501]])
def test_flag_validation(flags):
    with pytest.raises(ValueError):
        parse_transcript(json.dumps({'segments': [{'text': 'words', 'review_flags': flags}]}))
