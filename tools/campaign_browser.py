"""Offline campaign journeys: unknown costs, answer limits, persistence and conflicts.

All campaign details are fictional. Exercises the real local server and browser;
no model, external page or private correspondence is used.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.deliverable_browser import DeliverableChecks  # noqa: E402


def fixture():
    return {'schema': 'sinter-campaign/v1', 'title': 'Fictional swimming capacity campaign',
            'organisation': 'Fictional School Community Association',
            'objective': 'Compare current-year swimming options with next-year training and movable equipment. Costs and approvals are not confirmed.',
            'opportunities': [
                {'name': 'Fictional equipment fund', 'funder': 'Example Foundation', 'url': 'https://example.invalid/fund',
                 'deadline': '2026-09-28', 'decision_window': 'Four to five months after closing', 'ceiling': '35000.00',
                 'fit': 'Future equipment only. Costs must be incurred after approval.', 'status': 'open'},
                {'name': 'Fictional local sponsorship', 'funder': 'Example Business', 'url': 'https://example.invalid/sponsor',
                 'deadline': '', 'decision_window': 'Ask the sponsor', 'ceiling': '1000.00',
                 'fit': 'Ask whether this applicant type is accepted.', 'status': 'clarification'}],
            'requirements': [{'opportunity': 'Fictional equipment fund', 'rule': 'Applicant type accepted', 'status': 'met',
                              'evidence': '', 'source_url': '', 'source_quote': '', 'checked_at': ''}],
            'answers': [{'opportunity': 'Fictional equipment fund', 'label': 'Describe the project',
                         'text': 'A fictional swimming project. Costs and approvals still need confirmation.', 'limit': 250, 'status': 'draft'}],
            'budget': [{'item': 'Qualified training quote pending', 'opportunity': 'Fictional equipment fund',
                        'quantity': 2, 'unit_cost': None, 'quote_reference': ''},
                       {'item': 'Fictional equipment estimate', 'opportunity': 'Fictional equipment fund',
                        'quantity': 3, 'unit_cost': '12.35', 'quote_reference': 'Fictional supplier estimate; GST included; 2026-09-12'}],
            'actions': [{'task': 'Ask a qualified provider for an itemised quote', 'owner': '', 'due': '2026-09-20', 'status': 'open'},
                        {'task': 'Confirm applicant acceptance in writing', 'owner': 'Example coordinator', 'due': '', 'status': 'open'}],
            'sources': [{'title': 'Fictional equipment fund guidance', 'url': 'https://example.invalid/fund',
                         'notes': 'Fictional fixture only. Costs must be incurred after approval.'}]}


class CampaignChecks(DeliverableChecks):
    def screenshot(self, page, name, *, full_page=False):
        path = self.artifacts / f'campaign-{name}.png'
        page.screenshot(path=str(path), full_page=full_page, animations='disabled')
        self.screenshots.append(path.name)

    def transfers(self, page):
        if not page.get_by_label('Import campaign backup', exact=True).is_visible():
            page.get_by_text('Open, import or back up a campaign', exact=True).click()

    def import_fixture(self, page):
        from playwright.sync_api import expect
        self.goto(page, 'campaigns')
        self.transfers(page)
        page.get_by_label('Import campaign backup', exact=True).set_input_files({
            'name': 'fictional-campaign.json', 'mimeType': 'application/json',
            'buffer': json.dumps(fixture()).encode()})
        expect(page.get_by_text('Campaign imported locally.', exact=False)).to_be_visible()
        expect(page.get_by_label('Campaign name', exact=True)).to_have_value(fixture()['title'])

    def save(self, page):
        from playwright.sync_api import expect
        page.get_by_role('button', name='Save campaign', exact=True).click()
        expect(page.get_by_text('Campaign saved. Answers, costs, checks and actions will be here when you return.', exact=True)).to_be_visible()

    def workflow(self, page):
        from playwright.sync_api import expect
        self.import_fixture(page)
        expect(page.locator('.campaign-summary')).to_contain_text('1requirements to check')
        expect(page.get_by_role('region', name='Selected opportunity')).to_contain_text('What must be true?')
        self.save(page)
        self.screenshot(page, 'opportunities-desktop', full_page=True)
        page.get_by_role('tab', name='Application answers', exact=True).click()
        answer = page.get_by_role('article', name='Application answer')
        answer.get_by_label('Draft answer', exact=True).fill('a' * 251)
        expect(answer.get_by_role('status')).to_have_text('251 / 250 characters · 1 over — shorten before using')
        answer.get_by_role('button', name='Copy this answer', exact=True).click()
        expect(answer.get_by_text('Copied as written.', exact=False)).to_be_visible()
        assert page.evaluate('() => navigator.clipboard.readText()') == 'a' * 251
        self.save(page)
        self.screenshot(page, 'answer-over-limit')
        page.get_by_role('tab', name='Budget', exact=True).click()
        expect(page.locator('.campaign-budget-total')).to_contain_text('$37.05')
        expect(page.locator('.campaign-budget-total')).to_contain_text('1 uncosted item — total incomplete')
        items = page.get_by_role('article', name='Budget item', exact=True)
        expect(items.first.get_by_label('Unit cost (AUD)', exact=True)).to_have_value('')
        items.first.get_by_label('Unit cost (AUD)', exact=True).fill('2.55')
        expect(page.locator('.campaign-budget-total')).to_have_text('Known cost estimate: $42.15')
        self.save(page)
        self.screenshot(page, 'budget-editable', full_page=True)
        page.get_by_role('tab', name='Next actions', exact=True).click()
        filename, csv = self.download(page, 'Download actions CSV')
        assert filename.endswith('.csv') and 'Ask a qualified provider' in csv
        filename, calendar = self.download(page, 'Download action dates')
        assert filename.endswith('.ics') and 'BEGIN:VCALENDAR' in calendar and '20260920' in calendar
        page.get_by_role('button', name='Prepare campaign brief', exact=True).click()
        expect(page.get_by_role('region', name='Your draft report')).to_be_visible(timeout=10000)
        pack = self.pack(page)
        assert pack['campaign']['answers'][0]['text'] == 'a' * 251
        assert pack['campaign']['budget'][0]['unit_cost'] == '2.55'
        assert pack['campaign']['requirements'][0]['status'] == 'met'
        assert pack['readiness']['claims_without_evidence'] >= 1
        self.screenshot(page, 'prepared-campaign', full_page=True)
        page.reload()
        self.transfers(page)
        page.get_by_role('button', name='Open ' + fixture()['title'], exact=True).click()
        expect(page.get_by_text('Campaign opened.', exact=False)).to_be_visible()
        page.get_by_role('tab', name='Application answers', exact=True).click()
        expect(page.get_by_label('Draft answer', exact=True)).to_have_value('a' * 251)
        page.get_by_role('tab', name='Budget', exact=True).click()
        expect(page.get_by_label('Unit cost (AUD)', exact=True).first).to_have_value('2.55')
        for width in (390, 320):
            page.set_viewport_size({'width': width, 'height': 844})
            page.evaluate('''async () => {
                const {applyAppearance} = await import('/static/settings.js');
                applyAppearance({theme:'light',text_size:'large',density:'comfortable',reduce_motion:true});
            }''')
            assert page.evaluate('() => document.documentElement.scrollWidth <= innerWidth + 1'), width
            self.screenshot(page, f'budget-mobile-{width}', full_page=True)

    def conflict_and_import(self, page):
        from playwright.sync_api import expect
        self.import_fixture(page)
        page.get_by_label('Campaign name', exact=True).evaluate('(field) => field.closest("details").open = true')
        page.get_by_label('Campaign name', exact=True).fill('Fictional conflict recovery')
        self.save(page)
        page.evaluate('''async () => {
            const {request} = await import('/static/api.js');
            const list = await request('/api/campaigns');
            const row = list.campaigns.find(item => item.title === 'Fictional conflict recovery');
            const saved = await request('/api/campaigns/' + row.id);
            saved.document.objective = 'Separate window change: preserve this newer version.';
            await request('/api/campaigns/save', {data: {document:saved.document,id:row.id,revision:saved.revision}});
        }''')
        page.get_by_label('What will this campaign make possible?', exact=True).fill('My unsaved work must survive a conflict.')
        with page.expect_response(lambda response: response.url.endswith('/api/campaigns/save') and response.status == 400):
            page.get_by_role('button', name='Save campaign', exact=True).click()
        expect(page.get_by_role('alert')).to_contain_text('Your edits are still here.')
        expect(page.get_by_label('What will this campaign make possible?', exact=True)).to_have_value('My unsaved work must survive a conflict.')
        self.transfers(page)
        filename, backup = self.download(page, 'Export campaign backup')
        assert filename.endswith('.json') and json.loads(backup)['objective'] == 'My unsaved work must survive a conflict.'
        page.get_by_label('Import campaign backup', exact=True).set_input_files({
            'name': 'bad.json', 'mimeType': 'application/json', 'buffer': b'{unclosed'})
        expect(page.get_by_role('alert')).to_contain_text('not valid campaign JSON')
        expect(page.get_by_label('What will this campaign make possible?', exact=True)).to_have_value('My unsaved work must survive a conflict.')
        self.screenshot(page, 'conflict-recovery', full_page=True)
        # This exact 400 is the independently asserted stale-revision rejection.
        # Keep every unrelated page/console error in the failing receipt.
        self.errors[:] = [row for row in self.errors if not (
            row['check'] == 'campaign-conflict-import-recovery'
            and row.get('url') == self.base + '/api/campaigns/save'
            and row['error'] == 'Failed to load resource: the server responded with a status of 400 (Bad Request)')]


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright
    artifacts = ROOT / 'browser-artifacts'; artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sinter-campaign-browser-') as temporary, ExitStack() as guard:
        for name in ('chat', 'search', '_post', '_get'):
            guard.enter_context(patch.object(client, name, side_effect=AssertionError('Unexpected remote ' + name)))
        server = make_server(port=0, directory=temporary)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright, args.chromium)
                checks = CampaignChecks(browser, f'http://127.0.0.1:{server.server_port}', artifacts)
                checks.check('campaign-application-budget-roundtrip', checks.workflow)
                checks.check('campaign-conflict-import-recovery', checks.conflict_and_import)
                receipt = {'schema': 'sinter-campaign-browser/v1', 'checks': checks.results,
                           'expected_rejections': ['A stale campaign revision returns HTTP 400 and preserves the user’s edits.'],
                           'screenshots': checks.screenshots, 'browser_errors': checks.errors, 'external_requests': checks.external,
                           'passed': all(row['passed'] for row in checks.results) and not checks.errors and not checks.external}
                (artifacts / 'campaign-summary.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
                browser.close()
        finally:
            server.shutdown(); server.app.close(); server.server_close(); thread.join(timeout=5)
    if not receipt['passed']:
        raise SystemExit('FAIL: inspect browser-artifacts/campaign-summary.json.')
    print('PASS: campaign answers, quote-aware costs, actions, save/reopen, conflict recovery and mobile layout. No external requests.')


if __name__ == '__main__':
    main()
