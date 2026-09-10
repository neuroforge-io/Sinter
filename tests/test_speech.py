"""Optional speech contracts with a fake engine; no weights or audio accuracy claims."""
import base64
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sinter import speech


def test_recording_permission_precedes_processing(tmp_path):
    with pytest.raises(ValueError, match='permission'):
        speech.transcribe(tmp_path / 'missing.wav')


@pytest.mark.parametrize('payload', [
    {'consent': False},
    {'consent': True, 'audio': 'invalid-base64!'},
    {'consent': True, 'audio': '', 'filename': 'test.wav'},
    {'consent': True, 'audio': 'YQ==', 'filename': 'test.exe'},
])
def test_invalid_uploads(payload):
    with pytest.raises(ValueError):
        speech.transcribe_upload(payload)


def test_upload_uses_sanitized_temporary_path():
    def engine(path, *args):
        assert path.name == 'recording.wav' and path.read_bytes() == b'fixture'
        return {'segments': []}
    with patch.object(speech, 'transcribe', side_effect=engine):
        assert speech.transcribe_upload({'consent': True, 'filename': '../../secret.wav', 'audio': base64.b64encode(b'fixture').decode()}) == {'segments': []}


def test_local_speech_requires_explicit_download_and_never_guesses_identity(tmp_path, monkeypatch):
    recording = tmp_path / 'fixture.wav'; recording.write_bytes(b'fictional test bytes')
    kwargs_seen = []
    class Engine:
        def __init__(self, model, **kwargs): kwargs_seen.append(kwargs)
        def transcribe(self, path, **kwargs):
            segment = SimpleNamespace(start=0, end=1, text='No vote was taken.', avg_logprob=-2, no_speech_prob=.7)
            return iter([segment]), SimpleNamespace(duration=1, language='en')
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=Engine))
    monkeypatch.setattr(speech, '_CACHE', None)
    result = speech.transcribe(recording, consent=True)
    assert kwargs_seen[0]['local_files_only'] is True
    assert result['speaker_diarization'] is False
    assert result['segments'][0]['speaker'] == 'Unidentified'
    assert result['segments'][0]['review_flags']
