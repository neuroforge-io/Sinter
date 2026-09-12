"""Run offline browser integration against the real local HTTP server.

Install the browser extra and run playwright install chromium first.
SINTER_CHROMIUM optionally selects an already installed Chromium executable.
No external model, search, personal data or audio service is contacted.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from sinter import client
from sinter.server import make_server
from tools._support import browser_arguments, launch_chromium


def main(argv: list[str] | None = None) -> None:
    """Exercise the main browser journeys after checking optional setup."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = ROOT / 'browser-artifacts'
    artifacts.mkdir(exist_ok=True)
    errors, external = [], []
    with tempfile.TemporaryDirectory(prefix='sinter-browser-') as temp, patch.object(client, 'search', side_effect=AssertionError('Unexpected remote search')), patch.object(client, 'chat', side_effect=AssertionError('Unexpected remote model')):
        server = make_server(port=0, directory=temp)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright, args.chromium)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce', accept_downloads=True)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
                page.on('dialog', lambda dialog: dialog.accept())
                base = f'http://127.0.0.1:{server.server_port}'
                def guard(route):
                    if not route.request.url.startswith(base + '/'):
                        external.append(route.request.url); route.abort()
                    else: route.continue_()
                context.route('**/*', guard)
                page.goto(base)
                expect(page.get_by_role('heading', name=re.compile('Less busywork'))).to_be_visible()
                page.get_by_role('link', name='Skip to main content').focus()
                expect(page.get_by_role('link', name='Skip to main content')).to_be_focused()
                page.keyboard.press('Enter')
                expect(page.locator('#content')).to_be_focused()
                page.screenshot(path=str(artifacts / 'overview-dark.png'), full_page=True)
                page.get_by_role('button', name='Switch to light theme').click()
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                page.screenshot(path=str(artifacts / 'overview-light.png'), full_page=True)
                page.get_by_role('button', name='Switch to dark theme').click()
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.screenshot(path=str(artifacts / 'overview-mobile.png'), full_page=True)
                page.set_viewport_size({'width': 1440, 'height': 1000})
                for kind in ['brief', 'grants', 'meeting']:
                    page.goto(base + f'/#{kind}?example=1')
                    page.get_by_role('button', name='Prepare my draft').click()
                    report = page.get_by_role('region', name='Your draft report')
                    expect(report).to_be_visible(timeout=10000)
                    expect(report).to_contain_text('DRAFT')
                    expect(report).to_contain_text('FICTIONAL')
                    page.screenshot(path=str(artifacts / f'{kind}-draft.png'), full_page=True)
                    with page.expect_download() as download:
                        page.get_by_role('button', name='Download evidence pack').click()
                    pack = json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
                    assert pack['workflow'] == kind and pack['sources']
                    if kind == 'brief':
                        page.get_by_role('button', name='Save to this computer').click()
                        expect(report).to_contain_text('Saved in My workspace')
                    if kind == 'meeting':
                        page.get_by_text('Make a traceable transcript correction', exact=True).click()
                        page.get_by_label('Reviewed replacement', exact=True).fill('We discussed the garden but did not approve any spending.')
                        page.get_by_label('Why is this correction justified?', exact=True).fill('Fictional test correction; wording verified for this fixture.')
                        page.get_by_role('button', name='Apply reviewed correction').click()
                        expect(report).to_contain_text('Human correction history', timeout=10000)
                        expect(report).to_contain_text('We discussed the garden but did not approve any spending.')
                page.get_by_role('link', name='My workspace', exact=True).click()
                page.get_by_role('button', name='Open draft', exact=True).click()
                expect(page.get_by_role('region', name='Your draft report')).to_be_visible()
                page.get_by_role('link', name='Search watches', exact=True).click()
                page.get_by_label('Watch name', exact=True).fill('Fictional garden watch')
                page.get_by_label('Exact search query', exact=True).fill('fictional garden funding')
                page.get_by_role('checkbox', name='I authorise repeated searches').check()
                page.get_by_role('button', name='Create search watch').click()
                expect(page.get_by_role('heading', name='Fictional garden watch')).to_be_visible()
                page.get_by_role('button', name='Pause watch').click()
                expect(page.get_by_role('button', name='Resume watch')).to_be_visible()
                page.get_by_role('button', name='Resume watch').click()
                with page.expect_download() as download:
                    page.get_by_role('button', name='Download calendar reminders').click()
                assert 'BEGIN:VCALENDAR' in Path(download.value.path()).read_text()
                page.get_by_role('button', name='Delete watch').click()
                expect(page.get_by_text('No watches yet.', exact=False)).to_be_visible()
                # Exercise DOM and SSE modules directly inside the same real browser.
                result = page.evaluate('''async () => {
                    const {markdown, safeLink} = await import('/static/ui.js');
                    const {sseParser} = await import('/static/api.js');
                    const unsafe = markdown('<img src=x onerror=alert(1)>');
                    const received = []; const parser = sseParser(x => received.push(x));
                    for (const part of ['data: one\\r', '\\n\\r\\n', 'data: two\\ndata: three\\n\\n', 'data: [DONE]']) parser.feed(part);
                    parser.feed('', true);
                    return {html: unsafe.querySelector('img'), text: unsafe.textContent,
                            link: safeLink('javascript:alert(1)').tagName, received};
                }''')
                assert result['html'] is None and '<img' in result['text'] and result['link'] == 'SPAN'
                assert result['received'] == ['one', 'two\nthree', '[DONE]']
                assert not errors, errors
                assert not external, external
                browser.close()
        finally:
            server.shutdown(); server.app.close(); server.server_close(); thread.join(timeout=5)
    print('PASS: dark/light/mobile, keyboard navigation, all three offline workflows, corrections, evidence download, local save/reopen, watches/calendar, safe rendering and SSE framing. No external requests or browser errors.')


if __name__ == '__main__':
    main()
