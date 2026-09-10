"""Real optional-engine integration using pinned public upstream audio, not personal recordings."""
from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sinter.speech import transcribe
from sinter.transcript_export import export_transcript

REVISION = 'ed9a06cd89a93e47838f564998a6c09b655d7f43'
FIXTURES = {'jfk.flac': 'e44b7c13897eae7f78beb220c61fe77429a3961d',
            'stereo_diarization.wav': '3f5ae75dac40be2b33c2c76ac291a4d147b0b47d'}


def fixture(name, directory):
    url = f'https://raw.githubusercontent.com/SYSTRAN/faster-whisper/{REVISION}/tests/data/{name}'
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    assert len(data) <= 2 * 1024 * 1024, 'Unexpected fixture size'
    assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == FIXTURES[name], 'Fixture mismatch'
    path = directory / name
    path.write_bytes(data)
    return path


def words(text):
    return ' '.join(re.findall(r'[a-z]+', text.lower()))


def main():
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='sinter-speech-test-') as temporary:
        directory = Path(temporary)
        sample = transcribe(fixture('jfk.flac', directory), model='tiny', consent=True,
                            allow_download=True, language='en', progress=print)
        recognised = words(' '.join(row['text'] for row in sample['segments']))
        assert 'ask not what your country' in recognised, recognised
        assert all(row['words'] for row in sample['segments'])
        assert all(row['speaker'] == 'Unidentified' for row in sample['segments'])
        assert 'WEBVTT' in export_transcript(sample, 'vtt')
        stereo = transcribe(fixture('stereo_diarization.wav', directory), model='tiny', consent=True,
                            language='en', split_channels=True, progress=print)
        channels = {label: words(' '.join(row['text'] for row in stereo['segments'] if row['speaker'] == label))
                    for label in ['CHANNEL_1', 'CHANNEL_2']}
        assert 'wizard' in channels['CHANNEL_1'] and 'horizon' in channels['CHANNEL_2'], channels
        assert 'horizon' not in channels['CHANNEL_1'] and 'wizard' not in channels['CHANNEL_2'], channels
        silence = directory / 'silence.wav'
        with wave.open(str(silence), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b'\0\0' * 16000 * 3)
        empty = transcribe(silence, model='tiny', consent=True, language='en')
        assert empty['segments'] == [] and empty['status'] == 'no_speech'
        try:
            transcribe(silence, model='tiny', consent=True, language='en', split_channels=True)
        except ValueError as error:
            assert 'two-channel' in str(error)
        else:
            raise AssertionError('Mono was duplicated into two speakers')
        receipt = {'status': 'passed', 'platform': platform.platform(), 'python': platform.python_version(),
                   'engine_version': sample['engine_version'], 'model': 'tiny', 'fixture_revision': REVISION,
                   'checks': ['real speech', 'word timing', 'VTT export', 'isolated channels', 'silence', 'mono rejection'],
                   'elapsed_seconds': round(time.monotonic() - started, 2),
                   'scope': 'Short-fixture interoperability only; not meeting accuracy or identity verification.'}
        output = ROOT / 'speech-artifacts'
        output.mkdir(exist_ok=True)
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
