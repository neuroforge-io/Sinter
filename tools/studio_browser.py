"""Additional offline browser journeys for document formats and recording review."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from sinter import client, speech
from sinter.server import make_server
from tools._support import browser_arguments, launch_chromium


def main(argv: list[str] | None = None) -> None:
    """Exercise studio journeys after checking optional browser setup."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = ROOT / 'browser-artifacts'
    artifacts.mkdir(exist_ok=True)
    errors, external = [], []
    with tempfile.TemporaryDirectory(prefix='sinter-studio-') as temporary:
        recording = Path(temporary) / 'fixture.wav'
        with wave.open(str(recording), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b'\0\0' * 16000)
        transcript = {'segments': [{'start': 0, 'end': .8, 'speaker': 'Unidentified',
            'text': 'No vote was taken.', 'review_flags': ['Check the negation against the recording.'],
            'words': [{'start': 0, 'end': .2, 'word': 'No', 'probability': .4}]}],
            'duration': 1, 'review_count': 1, 'engine': 'MOCK BROWSER FIXTURE', 'audio_sha256': 'fixture'}
        server = make_server(port=0, directory=temporary)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(client, 'search', side_effect=AssertionError('Unexpected remote search')), \
                 patch.object(client, 'chat', side_effect=AssertionError('Unexpected remote model')), \
                 patch.object(speech, 'capabilities', return_value={'available': True, 'notice': 'Test engine available'}), \
                 patch.object(speech, 'transcribe_upload', return_value=transcript) as recogniser, sync_playwright() as playwright:
                browser = launch_chromium(playwright, args.chromium)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
                page.on('dialog', lambda dialog: dialog.accept())
                base = f'http://127.0.0.1:{server.server_port}'
                def guard(route):
                    if not route.request.url.startswith(base + '/'):
                        external.append(route.request.url)
                        route.abort()
                    else:
                        route.continue_()
                context.route('**/*', guard)
                page.goto(base + '/#brief')
                page.get_by_label('Project name', exact=True).fill('Real unsaved project')
                page.get_by_label('Your notes and context', exact=True).fill('No spending has been approved.')
                page.get_by_role('link', name='Overview', exact=True).click()
                page.get_by_role('button', name='Try an example', exact=True).click()
                page.get_by_label('What are you preparing?', exact=True).select_option('agenda')
                page.get_by_role('button', name='Prepare my draft').click()
                expect(page.get_by_role('region', name='Your draft report')).to_contain_text('Draft agenda item', timeout=10000)
                page.get_by_role('link', name='Overview', exact=True).click()
                page.get_by_role('button', name='Continue: Real unsaved project', exact=True).click()
                expect(page.get_by_label('Project name', exact=True)).to_have_value('Real unsaved project')
                expect(page.get_by_label('Your notes and context', exact=True)).to_have_value('No spending has been approved.')
                page.get_by_role('link', name='Meeting minutes', exact=True).click()
                # A label shared by two routes can otherwise match the outgoing page.
                expect(page.get_by_role('heading', name='Prepare a clear meeting record.', exact=True)).to_be_visible()
                page.get_by_label('Project name', exact=True).fill('Review test')
                expect(page.get_by_label('Project name', exact=True)).to_have_value('Review test')
                page.get_by_text('Start with an audio recording (optional)', exact=True).click()
                page.get_by_label('Meeting recording', exact=True).set_input_files(str(recording))
                page.get_by_role('button', name='Transcribe on this computer').click()
                assert not recogniser.called, 'Recording processed before permission'
                page.get_by_role('checkbox', name='I have permission to process this recording', exact=False).check()
                page.get_by_role('button', name='Transcribe on this computer').click()
                review = page.get_by_role('region', name='Review the recording')
                expect(review).to_be_visible(timeout=10000)
                expect(review).to_contain_text('Check the negation')
                expect(page.get_by_label('Local recording playback', exact=True)).to_be_visible()
                page.get_by_text('Label this passage after listening', exact=True).click()
                page.get_by_label('Speaker label for passage 1', exact=True).fill('SPEAKER_01')
                page.get_by_role('button', name='Keep this speaker label').click()
                expect(page.get_by_label('Transcript', exact=True)).to_have_value(re.compile('SPEAKER_01'))
                with page.expect_download() as pending:
                    page.get_by_role('button', name='Download transcript VTT').click()
                assert 'No vote was taken.' in Path(pending.value.path()).read_text(encoding='utf-8')
                with page.expect_download() as pending:
                    page.get_by_role('button', name='Download transcript JSON').click()
                archive = json.loads(Path(pending.value.path()).read_text(encoding='utf-8'))
                assert archive['segments'][0]['original_speaker'] == 'Unidentified'
                assert archive['segments'][0]['words'][0]['probability'] == .4
                expect(page.get_by_label('Project name', exact=True)).to_have_value('Review test')
                page.get_by_role('button', name=re.compile('Listen 0:00')).click()
                expect(page.locator('audio')).not_to_have_js_property('currentTime', 0, timeout=5000)
                expect(page.locator('audio')).to_have_js_property('paused', True, timeout=5000)
                expect(page.locator('audio')).to_have_js_property('error', None)
                page.screenshot(path=str(artifacts / 'transcription-review.png'), full_page=True)
                page.get_by_role('button', name='Prepare my draft').click()
                expect(page.get_by_role('region', name='Your draft report')).to_contain_text('Passages requiring an audio check', timeout=10000)
                assert not errors, errors
                assert not external, external
                browser.close()
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
    print('PASS: agenda format, real/example isolation, consent, local playback UI, speaker edits, lossless JSON, subtitles and minute review flags. Recognition mocked; no external requests.')


if __name__ == '__main__':
    main()
