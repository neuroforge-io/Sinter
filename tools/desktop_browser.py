"""Real browser journeys for settings, community tools and RKC import; no remote AI."""
from __future__ import annotations
import hashlib
import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'src'))
from sinter import client
from sinter.server import make_server
from tools._support import browser_arguments, launch_chromium


def main(argv: list[str] | None = None) -> None:
    """Exercise desktop journeys after checking optional browser setup."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    with tempfile.TemporaryDirectory(prefix='sinter-desktop-browser-') as temp, patch.object(client, 'chat', side_effect=AssertionError('Unexpected AI call')), patch.object(client, 'search', side_effect=AssertionError('Unexpected search')), patch.object(client, '_get', return_value={'data': [{'id': client.DENSE_MODEL}]}):
        server = make_server(port=0, directory=temp)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright, args.chromium)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                page = context.new_page(); errors = []; external = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('dialog', lambda dialog: dialog.accept())
                base = f'http://127.0.0.1:{server.server_port}'
                def guard(route):
                    if route.request.url.startswith(base+'/'): route.continue_()
                    else: external.append(route.request.url); route.abort()
                context.route('**/*', guard)
                page.goto(base+'/#settings')
                expect(page.get_by_role('heading', name='Connect your assistant', exact=True)).to_be_visible()
                page.get_by_text('Connection address and API style', exact=True).click()
                expect(page.get_by_label('API base address', exact=True)).to_have_value(client.BASE_URL)
                expect(page.get_by_label('Model identifier', exact=True)).to_have_value('auto')
                expect(page.get_by_label('Maximum answer length', exact=True)).to_have_value('64')
                check_connection = page.get_by_role('button', name='Check saved connection', exact=True)
                check_connection.click()
                expect(page.get_by_text('dense Gemma 4 E4B; text preview', exact=False)).to_be_visible()
                settings_posts = []
                page.on('request', lambda request: settings_posts.append(request.url)
                        if request.method == 'POST' and request.url.endswith('/api/settings') else None)
                page.get_by_label('Model identifier', exact=True).fill(client.DENSE_MODEL)
                expect(check_connection).to_be_disabled()
                expect(page.get_by_label('Maximum answer length', exact=True)).to_have_attribute('max', '2048')
                expect(page.get_by_text('The dense NeuroForge preview applies at most 512', exact=False)).to_be_visible()
                page.get_by_label('Your group or organisation', exact=True).fill('Garden P&C')
                page.get_by_label('Reading size', exact=True).select_option('large')
                page.get_by_label('Colour theme', exact=True).select_option('light')
                assert not settings_posts, 'Draft connection changes were saved implicitly.'
                page.get_by_role('button', name='Save connection', exact=True).click()
                expect(page.get_by_text('Connection saved. You can check it now or start an assistant task.', exact=True)).to_be_visible()
                expect(check_connection).to_be_enabled()
                assert len(settings_posts) == 1
                expect(page.locator('html')).to_have_attribute('data-text-size', 'large')
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                page.reload()
                expect(page.get_by_label('Your group or organisation', exact=True)).to_have_value('Garden P&C')
                expect(page.get_by_label('Model identifier', exact=True)).to_have_value(client.DENSE_MODEL)
                page.get_by_role('link', name='Community tools', exact=True).click()
                page.get_by_label('Plan name', exact=True).fill('School garden preparation')
                page.get_by_label('Action', exact=True).fill('Ask for quotes')
                page.get_by_label('Person responsible', exact=True).fill('Volunteer to confirm')
                page.get_by_label('Proposed target date (unconfirmed)', exact=True).fill('2026-09-30')
                page.get_by_role('button', name='Prepare my action plan', exact=True).click()
                with page.expect_download() as pending:
                    page.get_by_role('button', name='Download calendar dates', exact=True).click()
                assert '20260930' in Path(pending.value.path()).read_text()
                page.get_by_text('Compare two versions of a document', exact=True).click()
                page.get_by_label('Earlier wording', exact=True).fill('No motion was approved.')
                page.get_by_label('Updated wording', exact=True).fill('A motion was proposed.')
                page.get_by_role('button', name='Show exactly what changed', exact=True).click()
                expect(page.get_by_text('1 changed blocks.', exact=False)).to_be_visible()
                page.get_by_role('link', name='Knowledge atlases', exact=True).click()
                identity = hashlib.sha256(b'fixture\0node\0n1').hexdigest()
                document = {'schema_version': 'rkc-context/v1', 'snapshot_id': 'fixture', 'query':'garden', 'integrity':'fixture', 'truncated':False, 'digest':'a'*64,
                    'items':[{'citation_id':identity,'object_id':'n1','object_type':'node','title':'Garden notes','path':'notes.md','text':'Garden spending was not approved.','score':1,'evidence_ids':[]}], 'warnings':[]}
                source = Path(temp)/'context.json'; source.write_text(json.dumps(document))
                page.get_by_label('Import an RKC atlas or context packet', exact=True).set_input_files(str(source))
                expect(page.get_by_text('1 indexed items.', exact=False)).to_be_visible()
                page.get_by_label('What would you like to find out?', exact=True).fill('garden spending')
                page.get_by_role('button', name='Find supporting material', exact=True).click()
                expect(page.get_by_role('region', name='Knowledge results')).to_contain_text('Garden spending was not approved.')
                page.get_by_role('button', name='Draft with your model', exact=True).click()
                expect(page.get_by_role('region', name='Knowledge results')).to_contain_text('approve the excerpt transfer')
                page.get_by_role('link', name='Overview', exact=True).click()
                expect(page.get_by_role('heading', name='Your next piece of work starts here.', exact=True)).to_be_visible()
                page.set_viewport_size({'width': 1280, 'height': 600})
                last_link = page.get_by_role('link', name='Getting started', exact=True)
                last_link.scroll_into_view_if_needed()
                bounds = last_link.bounding_box()
                assert bounds and 0 <= bounds['y'] and bounds['y'] + bounds['height'] <= 600
                assert page.locator('.sidebar').evaluate('(node) => getComputedStyle(node).overflowY') == 'auto'
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.locator('.sidebar').evaluate('(node) => { node.scrollTop = 0; }')
                page.evaluate('window.scrollTo(0, 0)')
                artifacts = ROOT/'browser-artifacts'; artifacts.mkdir(exist_ok=True)
                page.screenshot(path=str(artifacts/'desktop-overview.png'), full_page=True)
                page.set_viewport_size({'width':390, 'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.screenshot(path=str(artifacts/'desktop-mobile.png'), full_page=True)
                assert not errors, errors
                assert not external, external
                browser.close()
        finally:
            server.shutdown(); server.app.close(); server.server_close(); thread.join(timeout=5)
    print('PASS: persistent appearance, short-screen navigation, user plans/calendar, wording comparison, RKC citation import/context and consent. No remote service calls.')

if __name__ == '__main__': main()
