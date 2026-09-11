"""Real browser journeys for settings, community tools and RKC import; no remote AI."""
from __future__ import annotations
import hashlib
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from playwright.sync_api import expect, sync_playwright
from sinter import client
from sinter.server import make_server


def main():
    with tempfile.TemporaryDirectory(prefix='sinter-desktop-browser-') as temp, patch.object(client, 'chat', side_effect=AssertionError('Unexpected AI call')), patch.object(client, 'search', side_effect=AssertionError('Unexpected search')):
        server = make_server(port=0, directory=temp)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as playwright:
                options = {'headless': True}
                if os.environ.get('SINTER_CHROMIUM'): options['executable_path'] = os.environ['SINTER_CHROMIUM']
                browser = playwright.chromium.launch(**options)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page(); errors = []; external = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('dialog', lambda dialog: dialog.accept())
                base = f'http://127.0.0.1:{server.server_port}'
                def guard(route):
                    if route.request.url.startswith(base+'/'): route.continue_()
                    else: external.append(route.request.url); route.abort()
                context.route('**/*', guard)
                page.goto(base+'/#settings')
                page.get_by_label('Your group or organisation', exact=True).fill('Garden P&C')
                page.get_by_label('Reading size', exact=True).select_option('large')
                page.get_by_label('Colour theme', exact=True).select_option('light')
                page.get_by_role('button', name='Save my preferences', exact=True).click()
                expect(page.locator('html')).to_have_attribute('data-text-size', 'large')
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                page.reload()
                expect(page.get_by_label('Your group or organisation', exact=True)).to_have_value('Garden P&C')
                page.get_by_role('link', name='Community tools', exact=True).click()
                page.get_by_label('Plan name', exact=True).fill('School garden preparation')
                page.get_by_label('Action', exact=True).fill('Ask for quotes')
                page.get_by_label('Person responsible', exact=True).fill('Volunteer to confirm')
                page.get_by_label('Confirmed due date', exact=True).fill('2026-09-30')
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
                page.get_by_role('button', name='Draft with Fracture', exact=True).click()
                expect(page.get_by_role('region', name='Knowledge results')).to_contain_text('approve the excerpt transfer')
                page.get_by_role('link', name='Overview', exact=True).click()
                expect(page.get_by_role('heading', name='Less busywork.', exact=False)).to_be_visible()
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
    print('PASS: persistent appearance, user plans/calendar, wording comparison, RKC citation import/context and consent. No remote service calls.')

if __name__ == '__main__': main()
