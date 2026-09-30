"""Offline browser checks for action-plan edits, stale exports and recovery."""
from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    """Use the real local plan service without any external connection."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = ROOT / 'browser-artifacts'
    artifacts.mkdir(exist_ok=True)
    receipt_path = artifacts / 'community-recovery-summary.json'
    receipt_path.write_text(json.dumps({
        'schema': 'sinter-community-recovery-browser/v1', 'passed': False,
        'state': 'running; only a completed process establishes a pass',
    }, indent=2), encoding='utf-8')
    checks: list[str] = []
    errors: list[str] = []
    external: list[str] = []
    requests: list[str] = []
    with tempfile.TemporaryDirectory(prefix='sinter-community-recovery-') as data:
        with patch.object(client, '_open', side_effect=AssertionError(
            'An offline action plan attempted an external request.')) as network:
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = launch_chromium(playwright, args.chromium)
                    context = browser.new_context(
                        viewport={'width': 1440, 'height': 1000},
                        reduced_motion='reduce', accept_downloads=True)
                    context.route('**/*', lambda route: route.continue_()
                                  if route.request.url.startswith(base + '/')
                                  else (external.append(route.request.url), route.abort()))
                    page = context.new_page()
                    page.set_default_timeout(7000)
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('dialog', lambda dialog: dialog.accept())
                    page.on('request', lambda request: requests.append(request.url)
                            if request.method == 'POST' else None)
                    page.goto(base + '/#tools')
                    title = page.get_by_label('Plan name', exact=True)
                    action = page.get_by_label('Action', exact=True)
                    prepare = page.get_by_role('button', name='Prepare my action plan', exact=True)
                    csv_button = page.get_by_role('button', name='Download spreadsheet CSV', exact=True)
                    export_buttons = [csv_button,
                        page.get_by_role('button', name='Download calendar dates', exact=True),
                        page.get_by_role('button', name='Download plan JSON', exact=True),
                        page.get_by_role('button', name='Save plan in My workspace', exact=True)]

                    def prepare_current() -> None:
                        prepare.click()
                        expect(prepare).to_be_enabled()
                        for button in export_buttons:
                            expect(button).to_be_enabled()

                    def assert_stale() -> None:
                        expect(page.get_by_text('This plan reflects earlier inputs.', exact=False)).to_be_visible()
                        for button in export_buttons:
                            expect(button).to_be_disabled()

                    title.fill('Fictional volunteer plan')
                    action.fill('Obtain equipment quote')
                    prepare_current()
                    edits = [
                        ('action', lambda: action.fill('Check current insurance wording')),
                        ('owner', lambda: page.get_by_label('Person responsible', exact=True).fill('Casey Example')),
                        ('date', lambda: page.get_by_label('Proposed target date (unconfirmed)', exact=True).fill('2026-10-09')),
                        ('progress', lambda: page.get_by_label('Progress', exact=True).select_option('in_progress')),
                        ('title', lambda: title.fill('Fictional revised volunteer plan')),
                    ]
                    for label, edit in edits:
                        posts = len(requests)
                        edit()
                        assert_stale()
                        assert len(requests) == posts, 'Editing silently regenerated or saved the plan.'
                        prepare_current()
                        checks.append('stale-' + label + '-requires-explicit-preparation')
                    with page.expect_download() as downloaded:
                        csv_button.click()
                    csv_rows = list(csv.reader(io.StringIO(
                        Path(downloaded.value.path()).read_text(encoding='utf-8'))))
                    assert csv_rows[1] == [
                        'Check current insurance wording', '', 'Casey Example',
                        '2026-10-09', 'in_progress'], csv_rows
                    with page.expect_download() as downloaded:
                        page.get_by_role('button', name='Download calendar dates', exact=True).click()
                    calendar = Path(downloaded.value.path()).read_text(encoding='utf-8').replace('\n ', '')
                    assert 'SUMMARY:Check current insurance wording' in calendar
                    assert 'DTSTART;VALUE=DATE:20261009' in calendar
                    assert 'Proposed target date' in calendar
                    checks.append('regenerated-csv-and-calendar-use-current-inputs')

                    page.get_by_role('button', name='Add another action', exact=True).click()
                    assert_stale()
                    page.get_by_label('Action', exact=True).nth(1).fill('Ask for current guideline wording')
                    prepare_current()
                    page.get_by_role('button', name='Remove this action', exact=True).nth(1).click()
                    assert_stale()
                    prepare_current()
                    checks.append('adding-and-removing-actions-retires-prior-plan')

                    # Both events occur in one browser turn. The real HTTP
                    # request captures earlier inputs before its response can
                    # arrive, so the returned plan must be held as stale.
                    action.evaluate("""input => {
                        [...document.querySelectorAll('button')].find(
                            button => button.textContent === 'Prepare my action plan').click();
                        input.value = 'Confirm access arrangements';
                        input.dispatchEvent(new Event('input', {bubbles:true}));
                    }""")
                    expect(prepare).to_be_enabled()
                    assert_stale()
                    expect(action).to_have_value('Confirm access arrangements')
                    expect(page.locator('#view')).to_contain_text('Check current insurance wording')
                    checks.append('editing-during-preparation-holds-returned-plan')

                    # Real local validation fails. Keep the user's invalid
                    # input and previous result rather than replacing either.
                    title.fill('')
                    prepare.click()
                    expect(page.get_by_role('alert')).to_contain_text('Your inputs and any earlier prepared plan are still here.')
                    expect(title).to_have_value('')
                    expect(page.locator('#view')).to_contain_text('Check current insurance wording')
                    for button in export_buttons:
                        expect(button).to_be_disabled()
                    title.fill('Fictional recovered plan')
                    assert_stale()
                    prepare_current()
                    expect(page.locator('#view')).to_contain_text('Confirm access arrangements')
                    checks.append('failed-preparation-preserves-inputs-and-earlier-result')

                    page.get_by_role('button', name='Save plan in My workspace', exact=True).click()
                    expect(page.locator('#announcements')).to_contain_text('Plan saved.')
                    page.get_by_role('link', name='My workspace', exact=True).click()
                    expect(page.get_by_role('heading', name='Fictional recovered plan', exact=True)).to_be_visible()
                    page.get_by_role('button', name='Open draft', exact=True).click()
                    expect(page.get_by_role('region', name='Your draft report')).to_contain_text('Confirm access arrangements')
                    checks.append('explicit-save-reopens-current-plan')
                    page.screenshot(path=str(artifacts / 'community-recovery-current-plan.png'), full_page=True)
                    assert not errors, errors
                    assert not external, external
                    assert network.call_count == 0
                    browser.close()
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
    receipt = {'schema': 'sinter-community-recovery-browser/v1', 'passed': True,
               'checks': checks, 'browser_errors': errors, 'external_requests': external,
               'local_posts': len(requests), 'external_api_calls': 0}
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(f'PASS: {len(checks)} action-plan recovery checks; no external requests.')


if __name__ == '__main__':
    main()
