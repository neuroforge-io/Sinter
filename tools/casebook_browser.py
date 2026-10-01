"""Real browser journey: community casebook, original excerpts, recovery and backups."""
from __future__ import annotations
from pathlib import Path
import json
import re
import sys
import tempfile
import threading
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from sinter import client
from sinter.server import make_server
from tools._support import browser_arguments, launch_chromium


def main(argv: list[str] | None = None) -> None:
    """Exercise casebook journeys after checking optional browser setup."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright, expect

    out = Path('browser-artifacts'); out.mkdir(exist_ok=True)
    with (tempfile.TemporaryDirectory() as directory,
          patch.object(client, '_open', side_effect=AssertionError(
              'An offline casebook attempted an external API request.')) as network):
        server = make_server(port=0, directory=directory)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as driver:
                browser = launch_chromium(driver, args.chromium)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                base = f'http://127.0.0.1:{server.server_port}'
                page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
                page.goto(base + '/#casebooks')
                page.get_by_role('button', name='Try a fictional community example', exact=True).click()
                page.get_by_label('Prepare a', exact=True).select_option('handover')
                originals = page.locator('.casebook-editor details.source').filter(
                    has=page.get_by_role(
                        "button",
                        name="Remove source",
                        exact=True,
                        include_hidden=True,
                    )
                )
                expect(originals).to_have_count(3)
                for index in range(3):
                    originals.nth(index).locator('summary').click()
                    expect(originals.nth(index).locator('pre')).to_be_visible()
                expect(originals.nth(0)).to_contain_text('No booking has been confirmed.')
                expect(originals.nth(2)).to_contain_text('No one agreed to own the roster yet.')
                page.get_by_role('button', name='Prepare source-only report', exact=True).click()
                report = page.get_by_role('region', name='Your draft report')
                expect(report.get_by_role('tab', name='Document', exact=True)).to_have_attribute('aria-selected', 'true')
                document = report.get_by_role('tabpanel', name='Document', exact=True)
                expect(document).to_contain_text('No one agreed')
                expect(document).to_contain_text('Handover next steps')
                report.get_by_role('tab', name='Evidence', exact=True).click()
                expect(report.get_by_role('tabpanel', name='Evidence', exact=True)).to_contain_text('No wording match')
                report.get_by_role('tab', name='Document', exact=True).click()
                page.screenshot(path=str(out / 'casebook-desktop.png'), full_page=True)
                page.locator('#theme-toggle').click()
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                page.screenshot(path=str(out / 'casebook-light.png'), full_page=True)
                page.locator('#theme-toggle').click()
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                # Every correspondence detail is an actual input to the report.
                # Editing it must retire the previous report and remember edits.
                page.locator('.sender-panel summary').click()
                details = {
                    'Recipient or audience': 'Fictional incoming committee',
                    'Your name or role': 'Casey Example',
                    'Your role': 'Fictional secretary',
                    'Organisation name': 'Fictional Community Association',
                    'Contact details': 'casey@example.invalid',
                }
                for label, value in details.items():
                    page.get_by_label(label, exact=True).fill(value)
                    expect(page.get_by_role('region', name='Your draft report')).to_have_count(0)
                    page.get_by_role('button', name='Prepare source-only report', exact=True).click()
                    expect(page.get_by_role('region', name='Your draft report')).to_be_visible()
                    expect(page.get_by_role('button', name='Prepare source-only report', exact=True)).to_be_enabled()
                page.get_by_label('Recipient or audience', exact=True).fill('Fictional handover team')
                expect(page.get_by_role('region', name='Your draft report')).to_have_count(0)
                page.get_by_role('link', name='Recent activity', exact=True).click()
                page.get_by_role('link', name='Community casebooks', exact=True).click()
                expect(page.get_by_label('Recipient or audience', exact=True)).to_have_value('Fictional handover team')
                expect(page.get_by_label('Your name or role', exact=True)).to_have_value(details['Your name or role'])
                expect(page.get_by_label('Prepare a', exact=True)).to_have_value('handover')
                page.get_by_role('button', name='Save project', exact=True).click()
                expect(page.get_by_text('Saved revision', exact=False)).to_be_visible()
                with page.expect_download() as download:
                    page.get_by_role('button', name='Export project backup', exact=True).click()
                contents = json.loads(Path(download.value.path()).read_text())
                assert len(contents['documents']) == 3
                assert contents['document_type'] == 'handover'
                assert contents['recipient'] == 'Fictional handover team'
                assert contents['contact_details'] == details['Contact details']
                # Lose one poll response; recover the same id without another submission.
                counts = {'polls': 0, 'posts': 0}
                def route_job(route):
                    counts['polls'] += 1
                    if counts['polls'] == 1: route.abort()
                    else: route.continue_()
                page.route('**/api/jobs/*', route_job)
                page.on('request', lambda req: counts.__setitem__('posts', counts['posts'] + 1) if req.url.endswith('/api/casebooks/build') else None)
                page.get_by_role('button', name='Prepare source-only report', exact=True).click()
                page.get_by_role('button', name='Prepare source-only report', exact=True).wait_for(state='visible')
                expect(page.get_by_role('button', name='Prepare source-only report', exact=True)).to_be_enabled(timeout=15000)
                assert counts['polls'] >= 2 and counts['posts'] == 1
                page.get_by_role('link', name='Recent activity', exact=True).click()
                page.get_by_role('button', name='Open result', exact=True).first.click()
                expect(page.get_by_role('region', name='Your draft report')).to_be_visible()
                page.get_by_role('link', name='Community casebooks', exact=True).click()
                page.get_by_role('button', name='Open project', exact=True).wait_for()
                page.on('dialog', lambda dialog: dialog.accept()
                    if dialog.type == 'beforeunload' else (
                        errors.append('Unexpected native decision: ' + dialog.type),
                        dialog.dismiss()))
                page.get_by_role('button', name='Open project', exact=True).first.click()
                assert page.get_by_label('Project name', exact=True).input_value() == 'Fictional P&C community evening'
                expect(page.get_by_label('Prepare a', exact=True)).to_have_value('handover')
                expect(page.get_by_label('Recipient or audience', exact=True)).to_have_value('Fictional handover team')
                # Reopening a new browser window uses persisted project data,
                # rather than the previous page's in-memory draft seed.
                reopened = browser.new_page(viewport={'width': 1440, 'height': 1000})
                reopened.on('pageerror', lambda error: errors.append(str(error)))
                reopened.on('dialog', lambda dialog: dialog.accept()
                    if dialog.type == 'beforeunload' else (
                        errors.append('Unexpected native decision: ' + dialog.type),
                        dialog.dismiss()))
                reopened.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
                try:
                    reopened.goto(base + '/#casebooks')
                    reopened.get_by_role('button', name='Open project', exact=True).first.click()
                    expect(reopened.get_by_label('Prepare a', exact=True)).to_have_value('handover')
                    expect(reopened.get_by_label('Contact details', exact=True)).to_have_value(details['Contact details'])
                    exit_is_blocked = '''() => {
                        const event = new Event('beforeunload', {cancelable:true});
                        window.dispatchEvent(event); return event.defaultPrevented;
                    }'''
                    assert not reopened.evaluate(exit_is_blocked), 'An unchanged saved project was marked dirty.'
                    reopened.get_by_label('What do you need to find out?', exact=True).fill(
                        contents['questions'] + '\nWho will check the current venue reply?')
                    assert reopened.evaluate(exit_is_blocked), 'An actual unsaved edit was not protected.'
                    reopened.get_by_role('button', name='Save project', exact=True).click()
                    expect(reopened.get_by_text('Saved revision', exact=False)).to_be_visible()
                    assert not reopened.evaluate(exit_is_blocked), 'Saving did not clear the exit warning.'
                    page.get_by_label('Recipient or audience', exact=True).fill('Fictional unsaved conflict edits')
                    page.get_by_role('button', name='Save project', exact=True).click()
                    expect(page.get_by_text('This casebook changed in another window', exact=False)).to_be_visible()
                    expect(page.get_by_label('Recipient or audience', exact=True)).to_have_value('Fictional unsaved conflict edits')
                    page.screenshot(path=str(out / 'casebook-conflict-recovery.png'), full_page=True)
                    with page.expect_download() as conflict_download:
                        page.get_by_role('button', name='Export project backup', exact=True).click()
                    conflict_backup = Path(conflict_download.value.path()).read_bytes()
                    assert json.loads(conflict_backup)['recipient'] == 'Fictional unsaved conflict edits'
                    page.get_by_role('button', name='Open project', exact=True).first.click()
                    page.get_by_role(
                        'dialog', name='Replace this unsaved editor?', exact=True
                    ).get_by_role('button', name='Replace editor', exact=True).click()
                    expect(page.get_by_label('What do you need to find out?', exact=True)).to_have_value(
                        re.compile('Who will check the current venue reply\\?'))
                    expect(page.get_by_label('Recipient or audience', exact=True)).to_have_value('Fictional handover team')
                    page.get_by_text('Backups and project removal', exact=True).click()
                    page.get_by_label('Restore a casebook backup', exact=True).set_input_files({
                        'name': 'fictional-handover-backup.json', 'mimeType': 'application/json',
                        'buffer': conflict_backup})
                    expect(page.get_by_text('Backup opened as a new unsaved project.', exact=True)).to_be_visible()
                    expect(page.get_by_label('Recipient or audience', exact=True)).to_have_value('Fictional unsaved conflict edits')
                    expect(page.get_by_label('Prepare a', exact=True)).to_have_value('handover')
                    assert page.evaluate(exit_is_blocked), 'A restored unsaved backup was marked clean.'
                    page.get_by_role('button', name='Save project', exact=True).click()
                    expect(page.get_by_text('Saved revision 1.', exact=False)).to_be_visible()
                    expect(page.get_by_role('button', name='Open project', exact=True)).to_have_count(2)
                    with page.expect_download() as restored_download:
                        page.get_by_role('button', name='Export project backup', exact=True).click()
                    restored_backup = json.loads(Path(restored_download.value.path()).read_text())
                    assert restored_backup['documents'] == contents['documents']
                    assert restored_backup['document_type'] == 'handover'
                    page.get_by_role('button', name='Prepare source-only report', exact=True).click()
                    restored_report = page.get_by_role('region', name='Your draft report')
                    expect(restored_report.get_by_role('tabpanel', name='Document', exact=True)).to_contain_text('Handover next steps')
                    expect(restored_report.get_by_role('tabpanel', name='Document', exact=True)).to_contain_text('No one agreed')
                    page.screenshot(path=str(out / 'casebook-restored-handover.png'), full_page=True)
                    expect(reopened.get_by_label('What do you need to find out?', exact=True)).to_have_value(
                        re.compile('Who will check the current venue reply\\?'))
                finally:
                    reopened.close()
                page.set_viewport_size({'width': 390, 'height': 844})
                page.screenshot(path=str(out / 'casebook-mobile.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.get_by_text('Add notes and references', exact=True).click()
                page.get_by_label('Add text files', exact=True).set_input_files([
                    {'name': f'fragment-{i}.txt', 'mimeType': 'text/plain', 'buffer': b'example'} for i in range(301)])
                page.get_by_text('Choose fewer files. A casebook supports at most 300 documents.', exact=True).wait_for()
                assert page.get_by_label('Project name', exact=True).input_value() == 'Fictional P&C community evening'
                assert not errors, errors
                network.assert_not_called()
                browser.close()
        finally:
            server.shutdown(); server.app.close(); server.server_close(); thread.join(timeout=5)
    print('PASS: source-only handover, exact originals/gaps, sender edit invalidation, format persistence, save/reopen, conflict preservation, backup restore, single-poll recovery without replay, activity retrieval and mobile layout. No model calls.')

if __name__ == '__main__': main()
