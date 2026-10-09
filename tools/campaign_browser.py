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
                 'fit': 'Future equipment only. Costs must be incurred after approval.', 'status': 'closed'},
                {'name': 'Fictional local sponsorship', 'funder': 'Example Business', 'url': 'https://example.invalid/sponsor',
                 'deadline': '', 'decision_window': 'Ask the sponsor', 'ceiling': '1000.00',
                 'fit': 'Ask whether this applicant type is accepted.', 'status': 'clarification'}],
            'requirements': [{'opportunity': 'Fictional equipment fund', 'rule': 'Applicant type accepted', 'status': 'met',
                              'evidence': '', 'source_url': '', 'source_quote': '', 'checked_at': ''},
                             {'opportunity': 'Fictional local sponsorship', 'rule': 'A distinct project is confirmed',
                              'status': 'unknown', 'evidence': '', 'source_url': '', 'source_quote': '', 'checked_at': ''}],
            'answers': [{'opportunity': 'Fictional equipment fund', 'label': 'Describe the project',
                         'text': 'A fictional swimming project. Costs and approvals still need confirmation.', 'limit': 250, 'status': 'draft'}],
            'budget': [{'item': 'Qualified training quote pending', 'opportunity': 'Fictional equipment fund',
                        'quantity': 2, 'unit_cost': None, 'quote_reference': ''},
                       {'item': 'Fictional equipment estimate', 'opportunity': 'Fictional equipment fund',
                        'quantity': 3, 'unit_cost': '12.35', 'quote_reference': 'Fictional supplier estimate; GST included; 2026-09-12'}],
            'actions': [{'task': 'Ask a qualified provider for an itemised quote', 'owner': '', 'due': '2026-09-20', 'status': 'open',
                         'opportunity': 'Fictional local sponsorship', 'scope_confirmed': True},
                        {'task': 'Confirm applicant acceptance in writing', 'owner': 'Example coordinator', 'due': '', 'status': 'open',
                         'opportunity': 'Fictional equipment fund', 'scope_confirmed': True}],
            'sources': [{'title': 'Fictional equipment fund guidance', 'url': 'https://example.invalid/fund',
                         'notes': 'Fictional fixture only. Costs must be incurred after approval.'}]}


class CampaignChecks(DeliverableChecks):
    def screenshot(self, page, name, *, full_page=False):
        path = self.artifacts / f'campaign-{name}.png'
        page.screenshot(path=str(path), full_page=full_page, animations='disabled')
        self.screenshots.append(path.name)

    def transfers(self, page):
        if not page.get_by_label('Import campaign backup', exact=True).is_visible():
            page.get_by_text('Import or back up a campaign', exact=True).click()

    def import_fixture(self, page, document=None):
        from playwright.sync_api import expect
        document = document or fixture()
        self.goto(page, 'campaigns')
        self.transfers(page)
        page.get_by_label('Import campaign backup', exact=True).set_input_files({
            'name': 'fictional-campaign.json', 'mimeType': 'application/json',
            'buffer': json.dumps(document).encode()})
        expect(page.get_by_text('Campaign imported locally.', exact=False)).to_be_visible()
        expect(page.get_by_label('Campaign name', exact=True)).to_have_value(document['title'])

    def save(self, page):
        from playwright.sync_api import expect
        page.get_by_role('button', name='Save campaign', exact=True).click()
        expect(page.get_by_text('Campaign saved. Answers, costs, checks and actions will be here when you return.', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='Save campaign', exact=True)).to_be_enabled()

    def answer_review_invalidation(self, page):
        from playwright.sync_api import expect
        document = fixture()
        document['title'] = 'Fictional application review campaign'
        document['opportunities'][0].update(
            status='open', application_mode='required',
            applicant='Fictional Community Association', applicant_confirmed=True)
        document['answers'][0]['limit'] = '0250'
        document['answers'][0]['status'] = 'reviewed'
        document['answers'].append({
            'opportunity': document['opportunities'][0]['name'],
            'label': 'Describe the unchanged team', 'text': 'A fictional team.',
            'limit': 100, 'status': 'reviewed',
        })
        self.import_fixture(page, document)
        _, initial_backup = self.download(page, 'Export campaign backup')
        initial = json.loads(initial_backup)
        page.get_by_role('tab', name='Application answers', exact=True).click()
        answers = page.get_by_role('article', name='Application answer')
        answer, sibling = answers.nth(0), answers.nth(1)
        question = answer.get_by_label('Application question', exact=True)
        review = answer.get_by_label('Answer review', exact=True)
        limit = answer.get_by_label('Character limit', exact=True)
        text = document['answers'][0]['text']
        expect(review).to_have_value('reviewed')
        question.fill(document['answers'][0]['label'])
        question.dispatch_event('input')
        expect(review).to_have_value('reviewed')
        question.press('End')
        question.press_sequentially(' and explain the need')
        edited_question = document['answers'][0]['label'] + ' and explain the need'
        expect(question).to_have_value(edited_question)
        expect(question).to_be_focused()
        assert question.evaluate('(field) => [field.selectionStart, field.selectionEnd]') == (
            [len(edited_question), len(edited_question)])
        expect(review).to_have_value('draft')
        expect(answer.get_by_label('Draft answer', exact=True)).to_have_value(text)
        expect(sibling.get_by_label('Answer review', exact=True)).to_have_value('reviewed')
        review.select_option('reviewed')
        limit.fill('0250')
        expect(review).to_have_value('reviewed')
        limit.fill('250')
        limit.dispatch_event('input')
        expect(review).to_have_value('reviewed')
        limit.fill('')
        expect(review).to_have_value('draft')
        expect(limit).to_be_focused()
        expect(answer.locator('.campaign-character-count')).to_contain_text('confirm the form’s limit')
        review.select_option('reviewed')
        limit.fill('')
        limit.dispatch_event('input')
        expect(review).to_have_value('reviewed')
        limit.fill('300')
        expect(review).to_have_value('draft')
        expect(limit).to_be_focused()
        expect(answer.get_by_label('Draft answer', exact=True)).to_have_value(text)
        expect(sibling.get_by_label('Answer review', exact=True)).to_have_value('reviewed')
        self.save(page)
        page.reload()
        page.get_by_role('button', name='Start a new campaign', exact=True).click()
        page.get_by_role('button', name='Open ' + document['title'], exact=True).click()
        expect(page.get_by_text('Campaign opened.', exact=False)).to_be_visible()
        page.get_by_role('tab', name='Application answers', exact=True).click()
        expect(answers.nth(0).get_by_label('Application question', exact=True)).to_have_value(edited_question)
        expect(answers.nth(0).get_by_label('Character limit', exact=True)).to_have_value('300')
        expect(answers.nth(0).get_by_label('Draft answer', exact=True)).to_have_value(text)
        expect(answers.nth(0).get_by_label('Answer review', exact=True)).to_have_value('draft')
        expect(answers.nth(1).get_by_label('Answer review', exact=True)).to_have_value('reviewed')
        self.transfers(page)
        _, saved_backup = self.download(page, 'Export campaign backup')
        saved = json.loads(saved_backup)
        assert saved['answers'][0] == {
            **initial['answers'][0], 'label': edited_question, 'limit': 300, 'status': 'draft'}
        assert saved['answers'][1] == initial['answers'][1]
        assert saved['sources'] == initial['sources']

    def action_text_contrast(self, page):
        from playwright.sync_api import expect
        document = fixture()
        document['title'] = 'Fictional action readability campaign'
        self.import_fixture(page, document)
        page.get_by_role('tab', name='Next actions', exact=True).click()
        action = page.get_by_role('article', name='Campaign action', exact=True).filter(
            has_text='Confirm applicant acceptance in writing')
        hold = action.locator('.campaign-action-hold-reason')
        expect(hold).to_have_text('Hold reason: route recorded as closed.')
        action.locator('summary').click()
        action.get_by_label('Owner type', exact=True).select_option('role')
        suggested = action.locator('.campaign-action-meta[data-state="suggested"]')
        expect(suggested).to_have_text(
            'This is a role suggestion, not a named person. Record a person who agrees before marking acceptance.')
        expect(action.get_by_label('This person has accepted this action', exact=True)).to_be_disabled()
        original_theme = page.locator('html').get_attribute('data-theme')
        metrics = []
        for theme in ('light', 'dark'):
            if page.locator('html').get_attribute('data-theme') != theme:
                page.get_by_role('button', name=f'Switch to {theme} theme', exact=True).click()
            expect(page.locator('html')).to_have_attribute('data-theme', theme)
            for label, text in (('hold reason', hold), ('suggested owner', suggested)):
                expect(text).to_be_visible()
                colors = text.evaluate('''element => {
                    const channels = color => {
                        if (!/^rgba?\\(/.test(color)) throw Error('Unexpected rendered color: ' + color);
                        const values = color.match(/[\\d.]+/g).map(Number);
                        return {rgb: values.slice(0, 3).map(value => value / 255), alpha: values[3] ?? 1};
                    };
                    const foreground = getComputedStyle(element).color;
                    const text = channels(foreground);
                    if (text.alpha !== 1) throw Error('Expected opaque action text');
                    for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
                        if (getComputedStyle(ancestor).opacity !== '1') throw Error('Expected fully opaque action ancestors');
                    }
                    let background, surface = element;
                    while (surface) {
                        const style = getComputedStyle(surface);
                        if (style.backgroundImage !== 'none') throw Error('Expected a solid action background');
                        background = style.backgroundColor;
                        const alpha = channels(background).alpha;
                        if (alpha === 1) break;
                        if (alpha !== 0) throw Error('Expected an opaque or transparent action background');
                        surface = surface.parentElement;
                    }
                    if (!surface) throw Error('No opaque rendered action background');
                    const luminance = rgb => rgb.map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4)
                        .reduce((sum, c, i) => sum + c * [.2126, .7152, .0722][i], 0);
                    const a = luminance(text.rgb), b = luminance(channels(background).rgb);
                    return {foreground, background, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05)};
                }''')
                metrics.append({'theme': theme, 'text': label, **colors})
        if page.locator('html').get_attribute('data-theme') != original_theme:
            page.get_by_role('button', name=f'Switch to {original_theme} theme', exact=True).click()
        (self.artifacts / 'campaign-action-text-contrast.json').write_text(
            json.dumps({'scope': 'Rendered hold reason and suggested-owner action text only.',
                        'measurements': metrics}, indent=2), encoding='utf-8')
        assert len(metrics) == 4 and all(row['ratio'] >= 4.5 for row in metrics), metrics

    def capacity_and_recovery(self, page):
        from playwright.sync_api import expect
        document = {
            'title': 'Fictional large product portfolio',
            'assets': [{'name': f'Fictional product {index}',
                        'public_summary': 'x' * 3000} for index in range(55)],
            'sources': [{'title': f'Fictional retained source {index}',
                         'notes': 's' * 6000} for index in range(4)],
        }
        self.import_fixture(page, document)
        capacity = page.get_by_label('Campaign capacity', exact=True)
        expect(capacity).to_have_attribute('data-capacity-state', 'near')
        expect(capacity).to_contain_text('Nearly full')
        expect(capacity).to_contain_text('Saving checks normalized data')
        self.save(page)
        page.get_by_role('tab', name='Communications', exact=True).click()
        page.get_by_role('button', name='Add communication', exact=True).click()
        message = page.get_by_label('Message text or summary', exact=True)
        message.fill('Fictional unsaved evidence ' + 'x' * 19000)
        expect(capacity).to_have_attribute('data-capacity-state', 'over')
        with page.expect_response(lambda response: response.url.endswith('/api/campaigns/save')
                                  and response.status == 400) as rejected:
            page.get_by_role('button', name='Save campaign', exact=True).click()
        assert '200,000 text characters' in rejected.value.json()['error']
        expect(page.get_by_role('alert')).to_contain_text('200,000 text characters')
        expect(message).to_have_value('Fictional unsaved evidence ' + 'x' * 19000)
        self.transfers(page)
        with page.expect_download() as downloaded:
            page.get_by_role('button', name='Export campaign backup', exact=True).click()
        backup = self.artifacts / 'campaign-capacity-unsaved-backup.json'
        downloaded.value.save_as(str(backup))
        retained = json.loads(backup.read_text())
        assert len(retained['assets']) == 55
        assert retained['communications'][0]['content'] == 'Fictional unsaved evidence ' + 'x' * 19000
        message.fill('Explicitly reduced fictional scope; original oversized backup retained.')
        self.save(page)
        self.goto(page, 'campaigns')
        expect(page.get_by_label('Campaign capacity', exact=True)).to_have_attribute(
            'data-capacity-state', 'near')
        page.get_by_role('tab', name='Communications', exact=True).click()
        page.locator('.campaign-communication summary').click()
        expect(page.get_by_label('Message text or summary', exact=True)).to_have_value(
            'Explicitly reduced fictional scope; original oversized backup retained.')
        self.screenshot(page, 'capacity-recovered', full_page=True)
        # Only this asserted rejection is expected; unrelated browser errors fail.
        self.errors[:] = [row for row in self.errors if not (
            row.get('check') == 'campaign-capacity-and-recovery'
            and row.get('url') == self.base + '/api/campaigns/save'
            and row['error'] == 'Failed to load resource: the server responded with a status of 400 (Bad Request)')]

    def workflow(self, page):
        from playwright.sync_api import expect
        self.import_fixture(page)
        expect(page.locator('.campaign-summary')).to_contain_text('1requirements to check')
        expect(page.get_by_role('region', name='Selected opportunity')).to_contain_text('What must be true?')
        decision = page.get_by_role('region', name='Campaign decision and next move')
        expect(decision.locator('.campaign-decision-state')).to_have_text('NOT READY')
        expect(decision).to_contain_text('Ask a qualified provider for an itemised quote')
        expect(decision).to_contain_text('Owner needed')
        expect(decision).to_contain_text('Proposed target:')
        expect(decision).to_contain_text('current official wording')
        requirement = page.locator('.campaign-requirement').first
        expect(requirement.locator('.campaign-check-state')).to_contain_text(
            'User-marked met · unverified')
        requirement.locator('summary').first.click()
        requirement.get_by_text('Supporting source · user-entered, unverified').click()
        page.get_by_label('What the evidence establishes or leaves unclear', exact=True).fill(
            'The user-entered excerpt describes accepted applicant types.')
        page.get_by_label('Source link (user-entered)', exact=True).fill(
            'https://example.invalid/fund/eligibility')
        page.get_by_label('Source wording (user-entered)', exact=True).fill(
            'Registered community associations may apply.')
        page.get_by_label('Date this excerpt was checked', exact=True).fill('2026-09-12')
        expect(requirement.locator('.campaign-check-state')).to_contain_text(
            'User-marked met · unverified')
        expect(requirement.locator('.campaign-proof-status')).to_contain_text(
            'Sinter has not verified the link, wording, date or assessment.')
        self.save(page)
        self.screenshot(page, 'opportunities-desktop', full_page=True)
        page.get_by_role('tab', name='Application answers', exact=True).click()
        answer = page.get_by_role('article', name='Application answer')
        expect(answer.get_by_label('Draft answer', exact=True)).to_have_attribute('readonly', '')
        expect(answer.get_by_label('Draft answer', exact=True)).to_have_value('')
        expect(answer.get_by_role('button', name='Copy unavailable · inactive route', exact=True)).to_be_disabled()
        expect(page.get_by_role('button', name='Add application question', exact=True)).to_be_disabled()
        expect(page.locator('.notice.warning')).to_contain_text('not for submission')
        page.get_by_role('tab', name='Opportunities', exact=True).click()
        page.get_by_text('Edit opportunity details', exact=True).click()
        page.get_by_label('Opportunity status', exact=True).select_option('open')
        page.get_by_role('tab', name='Application answers', exact=True).click()
        answer = page.get_by_role('article', name='Application answer')
        expect(answer.get_by_label('Draft answer', exact=True)).to_have_attribute('readonly', '')
        expect(answer.get_by_label('Draft answer', exact=True)).to_have_value('')
        expect(answer.get_by_role('button', name='Copy unavailable · workflow not confirmed', exact=True)).to_be_disabled()
        expect(page.get_by_role('button', name='Add application question', exact=True)).to_be_disabled()
        expect(page.locator('.notice.warning')).to_contain_text('Confirm whether this route uses a formal application')
        expect(page.locator('.campaign-summary>div').nth(1)).to_contain_text(
            '0answers to shorten')
        expect(page.locator('.campaign-summary>div').nth(2)).to_contain_text(
            '1answer rows held')
        page.get_by_role('tab', name='Opportunities', exact=True).click()
        page.get_by_text('Edit opportunity details', exact=True).click()
        page.get_by_label('Application workflow', exact=True).select_option('required')
        page.get_by_role('tab', name='Application answers', exact=True).click()
        answer = page.get_by_role('article', name='Application answer')
        original_answer = fixture()['answers'][0]
        expect(answer.get_by_label('Application question', exact=True)).to_be_enabled()
        expect(answer.get_by_label('Character limit', exact=True)).to_be_enabled()
        expect(answer.get_by_label('Draft answer', exact=True)).not_to_have_attribute('readonly', '')
        expect(answer.get_by_label('Draft answer', exact=True)).to_have_value(original_answer['text'])
        expect(answer.get_by_label('Answer review', exact=True)).to_be_disabled()
        expect(answer.get_by_role('button', name='Copy unavailable · applicant not recorded', exact=True)).to_be_disabled()
        expect(page.get_by_role('button', name='Add application question', exact=True)).to_be_enabled()
        expect(page.locator('.notice.warning')).to_contain_text('an applicant or lead is not recorded')
        expect(page.locator('.notice.warning')).to_contain_text('You can save local drafts')
        local_question = 'Fictional local planning question — scope still to confirm'
        local_text = 'LOCAL HELD DRAFT: café 🐝 é\nNo applicant confirmation or costs assumed.'
        page.get_by_role('button', name='Add application question', exact=True).click()
        answers = page.get_by_role('article', name='Application answer')
        expect(answers).to_have_count(2)
        local_answer = answers.nth(1)
        local_answer.get_by_label('Application question', exact=True).fill(local_question)
        local_answer.get_by_label('Character limit', exact=True).fill('350')
        local_answer.get_by_label('Draft answer', exact=True).fill(local_text)
        expect(local_answer.get_by_label('Answer review', exact=True)).to_have_value('draft')
        expect(local_answer.get_by_label('Answer review', exact=True)).to_be_disabled()
        expect(local_answer.get_by_role('button', name='Copy unavailable · applicant not recorded', exact=True)).to_be_disabled()
        self.save(page)
        page.reload()
        page.get_by_role('button', name='Start a new campaign', exact=True).click()
        page.get_by_role('button', name='Open ' + fixture()['title'], exact=True).click()
        expect(page.get_by_text('Campaign opened.', exact=False)).to_be_visible()
        page.get_by_role('tab', name='Application answers', exact=True).click()
        expect(answers).to_have_count(2)
        expect(answers.nth(0).get_by_label('Draft answer', exact=True)).to_have_value(original_answer['text'])
        expect(local_answer.get_by_label('Application question', exact=True)).to_have_value(local_question)
        expect(local_answer.get_by_label('Character limit', exact=True)).to_have_value('350')
        expect(local_answer.get_by_label('Draft answer', exact=True)).to_have_value(local_text)
        expect(local_answer.get_by_label('Answer review', exact=True)).to_be_disabled()
        expect(local_answer.get_by_role('button', name='Copy unavailable · applicant not recorded', exact=True)).to_be_disabled()
        self.transfers(page)
        _, local_backup = self.download(page, 'Export campaign backup')
        local_document = json.loads(local_backup)
        assert local_document['opportunities'][0]['applicant'] == ''
        assert local_document['opportunities'][0]['applicant_confirmed'] is False
        assert local_document['answers'][0] == original_answer
        assert local_document['answers'][1] == {
            'opportunity': original_answer['opportunity'], 'label': local_question,
            'text': local_text, 'limit': 350, 'status': 'draft'}
        page.get_by_role('button', name='Prepare campaign brief', exact=True).click()
        expect(page.get_by_role('region', name='Your draft report')).to_be_visible(timeout=10000)
        held_pack = self.pack(page)
        assert len(held_pack['campaign']['answers']) == 2
        for held_answer in held_pack['campaign']['answers']:
            assert held_answer['text'] == ''
            assert held_answer['label'] == 'Held answer details omitted from report'
            assert held_answer['limit'] is None
        assert held_pack['answer_metrics'] == []
        assert 'LOCAL HELD DRAFT' not in json.dumps(held_pack)
        assert local_question not in json.dumps(held_pack, ensure_ascii=False)
        page.get_by_role('tab', name='Opportunities', exact=True).click()
        page.get_by_text('Edit opportunity details', exact=True).click()
        page.get_by_label('Applicant / programme lead', exact=True).fill('Fictional Community Association')
        page.get_by_role('tab', name='Application answers', exact=True).click()
        answer = page.get_by_role('article', name='Application answer').first
        expect(answer.get_by_label('Draft answer', exact=True)).not_to_have_attribute('readonly', '')
        expect(answer.get_by_label('Draft answer', exact=True)).to_have_value(original_answer['text'])
        expect(answer.get_by_label('Answer review', exact=True)).to_be_disabled()
        expect(answer.get_by_role('button', name='Copy unavailable · applicant not confirmed', exact=True)).to_be_disabled()
        expect(page.locator('.campaign-section .notice.warning')).to_contain_text('has not been explicitly confirmed')
        expect(local_answer.get_by_label('Draft answer', exact=True)).to_have_value(local_text)
        expect(local_answer.get_by_role('button', name='Copy unavailable · applicant not confirmed', exact=True)).to_be_disabled()
        local_answer.get_by_role('button', name='Remove question', exact=True).click()
        expect(answers).to_have_count(1)
        page.get_by_role('tab', name='Opportunities', exact=True).click()
        page.get_by_text('Edit opportunity details', exact=True).click()
        page.get_by_label('Applicant confirmed directly', exact=True).check()
        self.save(page)
        page.get_by_role('tab', name='Application answers', exact=True).click()
        answer = page.get_by_role('article', name='Application answer')
        expect(answer.get_by_label('Application question', exact=True)).to_have_value(
            'Describe the project')
        expect(answer.get_by_label('Draft answer', exact=True)).not_to_have_attribute('readonly', '')
        expect(answer.get_by_label('Draft answer', exact=True)).to_have_value(
            'A fictional swimming project. Costs and approvals still need confirmation.')
        expect(answer.locator('.campaign-character-count')).to_contain_text(
            '/ 250 characters')
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
        expect(page.locator('.campaign-budget-total')).to_have_text('Recorded cost subtotal (AUD): A$42.15')
        self.save(page)
        self.screenshot(page, 'budget-editable', full_page=True)
        page.get_by_role('tab', name='Next actions', exact=True).click()
        actions = page.get_by_role('article', name='Campaign action', exact=True)
        # Actions move between urgency/status groups. Follow their task rather
        # than a row position, and open the same disclosure a user would use.
        first_action = actions.filter(has_text='Ask a qualified provider for an itemised quote')
        second_action = actions.filter(has_text='Confirm applicant acceptance in writing')
        for action in (first_action, second_action):
            if action.locator('details').get_attribute('open') is None:
                action.locator('summary').click()
        task = first_action.get_by_label('Next action', exact=True)
        edited_task = fixture()['actions'][0]['task'] + ' and record the response'
        task.focus()
        task.press('End')
        task.press_sequentially(' and record the response')
        expect(task).to_have_value(edited_task)
        expect(task).to_be_focused()
        assert task.evaluate('(field) => [field.selectionStart, field.selectionEnd]') == (
            [len(edited_task), len(edited_task)]
        )
        expect(first_action.locator('details')).to_have_attribute('open', '')
        expect(first_action.locator('.campaign-action-summary-task')).to_have_text(
            edited_task)
        expect(page.locator('.campaign-save-state')).to_have_text('Unsaved changes')
        first_action.locator('summary').click()
        expect(first_action.locator('details')).not_to_have_attribute('open', '')
        expect(first_action.locator('.campaign-action-summary-task')).to_have_text(
            edited_task)
        expect(page.locator('.campaign-save-state')).to_have_text('Unsaved changes')
        first_action.locator('summary').click()
        expect(task).to_have_value(edited_task)
        expect(first_action.get_by_label('Owner name or role', exact=True)).to_have_value('')
        expect(first_action).to_contain_text('Owner needed — no person is recorded.')
        expect(first_action.get_by_label('Owner type', exact=True)).to_have_value('unassigned')
        expect(second_action).to_contain_text('Owner type not confirmed: Example coordinator')
        acceptance = second_action.get_by_label('This person has accepted this action', exact=True)
        expect(acceptance).to_be_disabled()
        expect(acceptance).not_to_be_checked()
        second_action.get_by_label('Owner type', exact=True).select_option('person')
        expect(second_action).to_contain_text('Named person: Example coordinator; acceptance unconfirmed')
        expect(acceptance).to_be_enabled()
        expect(acceptance).not_to_be_checked()
        acceptance.check()
        expect(second_action).to_contain_text('Acceptance recorded by user; verify directly with this person.')
        second_action.get_by_label('Owner name or role', exact=True).fill('Example coordinator alternate')
        expect(acceptance).not_to_be_checked()
        expect(second_action).to_contain_text('Named person: Example coordinator alternate; acceptance unconfirmed')
        target = first_action.get_by_label('Proposed target date', exact=True)
        overdue_date = page.evaluate('''() => {
            const day = new Date(); day.setDate(day.getDate() - 1);
            return [day.getFullYear(), String(day.getMonth() + 1).padStart(2, '0'), String(day.getDate()).padStart(2, '0')].join('-');
        }''')
        target.fill(overdue_date)
        overdue_status = first_action.locator('.campaign-action-date-status')
        expect(overdue_status).to_have_attribute('data-state', 'overdue')
        expect(overdue_status).to_contain_text('Past proposed target')
        first_action.get_by_label('Action status', exact=True).select_option('done')
        expect(overdue_status).to_have_text('Completed — proposed target kept for reference.')
        first_action.get_by_label('Action status', exact=True).select_option('open')
        expect(overdue_status).to_have_attribute('data-state', 'overdue')
        filename, csv = self.download(page, 'Download actions CSV')
        assert filename.endswith('.csv') and 'Ask a qualified provider' in csv
        assert 'Example coordinator alternate (named person; acceptance unconfirmed)' in csv
        long_owner = 'A' * 200
        second_action.get_by_label('Owner name or role', exact=True).fill(long_owner)
        second_action.get_by_label('This person has accepted this action', exact=True).check()
        filename, long_owner_csv = self.download(page, 'Download actions CSV')
        assert filename.endswith('.csv')
        assert long_owner + ' (user-marked accepted; verify directly)' in long_owner_csv
        filename, calendar = self.download(page, 'Download action dates')
        assert filename.endswith('.ics') and 'BEGIN:VCALENDAR' in calendar and overdue_date.replace('-', '') in calendar
        page.get_by_role('tab', name='Opportunities', exact=True).click()
        page.get_by_text('Edit opportunity details', exact=True).click()
        page.get_by_role('button', name='Prepare campaign brief', exact=True).click()
        expect(page.get_by_role('region', name='Your draft report')).to_be_visible(timeout=10000)
        page.get_by_label('Opportunity status', exact=True).select_option('closed')
        expect(page.locator('#campaign-output')).to_have_attribute('data-stale', 'true')
        expect(page.get_by_text('This brief reflects an earlier campaign version.', exact=False)).to_be_visible()
        expect(page.locator('#campaign-output .report-area')).to_have_attribute('inert', '')
        expect(page.locator('#campaign-output .report-area button').first).to_be_disabled()
        self.save(page)
        page.get_by_role('tab', name='Budget', exact=True).click()
        expect(page.get_by_role('heading', name='Current project costs', exact=True)).to_be_visible()
        expect(page.locator('.campaign-budget-total')).to_contain_text(
            'No costs recorded for active opportunities. The current project total is unknown.')
        expect(page.get_by_role('heading', name='Historical costs · inactive routes', exact=True)).to_be_visible()
        expect(page.locator('.campaign-section .notice.warning')).to_contain_text(
            'They do not contribute to the current project total.')
        self.screenshot(page, 'budget-historical', full_page=True)
        page.get_by_role('tab', name='Opportunities', exact=True).click()
        page.get_by_role('button', name='Prepare campaign brief', exact=True).click()
        expect(page.get_by_role('region', name='Your draft report')).to_be_visible(timeout=10000)
        expect(page.locator('#campaign-output')).not_to_have_attribute('data-stale', 'true')
        pack = self.pack(page)
        assert pack['campaign']['answers'][0]['text'] == ''
        assert pack['campaign']['answers'][0]['label'] == 'Held answer details omitted from report'
        assert pack['campaign']['answers'][0]['limit'] is None
        assert pack['answer_metrics'] == []
        stored_answer = page.evaluate('''async () => {
            const {request} = await import('/static/api.js');
            const list = await request('/api/campaigns');
            const item = list.campaigns.find(row =>
                row.title === 'Fictional swimming capacity campaign');
            const saved = await request('/api/campaigns/' + item.id);
            return saved.document.answers[0].text;
        }''')
        assert stored_answer == 'a' * 251
        assert pack['campaign']['budget'][0]['unit_cost'] == '2.55'
        assert pack['campaign']['requirements'][0]['status'] == 'met'
        assert pack['readiness']['claims_without_evidence'] == 0
        assert pack['readiness']['requirements_total'] == 1
        assert pack['readiness']['requirements_archived'] == 1
        assert 'retained for paused, not-pursued, submitted or closed opportunity' in pack['markdown']
        assert 'Historical answer drafts · inactive route' in pack['markdown']
        assert 'are not for submission' in pack['markdown']
        assert 'User-marked met · unverified' in pack['markdown']
        assert 'Supported · human checked' not in pack['markdown']
        assert 'Historical answer drafts · inactive route' not in pack['document_markdown']
        assert 'not for submission' not in pack['document_markdown']
        self.screenshot(page, 'prepared-campaign', full_page=True)
        page.reload()
        self.transfers(page)
        page.get_by_role('button', name='Start a new campaign', exact=True).click()
        expect(page.locator('.campaign-saved-item.is-current')).to_have_count(0)
        expect(page.get_by_role('button', name='Open ' + fixture()['title'], exact=True)).to_be_visible()
        page.get_by_role('button', name='Open ' + fixture()['title'], exact=True).click()
        expect(page.get_by_text('Campaign opened.', exact=False)).to_be_visible()
        expect(page.locator('.campaign-saved-item.is-current')).to_have_count(1)
        page.get_by_role('tab', name='Next actions', exact=True).click()
        reopened_action = page.get_by_role('article', name='Campaign action', exact=True).filter(
            has_text=edited_task)
        expect(reopened_action.locator('.campaign-action-summary-task')).to_have_text(
            edited_task)
        if reopened_action.locator('details').get_attribute('open') is None:
            reopened_action.locator('summary').click()
        expect(reopened_action.get_by_label('Next action', exact=True)).to_have_value(
            edited_task)
        page.get_by_role('tab', name='Opportunities', exact=True).click()
        expect(page.locator('.campaign-opportunity[aria-pressed="true"]')).to_contain_text('Fictional local sponsorship')
        page.locator('.campaign-opportunity').first.click()
        expect(page.locator('.campaign-opportunity[aria-pressed="true"]')).to_contain_text('Fictional equipment fund')
        page.get_by_role('tab', name='Application answers', exact=True).click()
        historical = page.get_by_role('article', name='Application answer')
        expect(historical.get_by_label('Draft answer', exact=True)).to_have_value('')
        expect(historical.get_by_text('not for submission', exact=False)).to_be_visible()
        expect(historical.get_by_role('button', name='Copy unavailable · inactive route', exact=True)).to_be_disabled()
        page.get_by_role('tab', name='Budget', exact=True).click()
        expect(page.get_by_label('Unit cost (AUD)', exact=True).first).to_have_value('2.55')
        for width in (390, 320):
            page.set_viewport_size({'width': width, 'height': 844})
            page.evaluate('''async () => {
                const {applyAppearance} = await import('/static/settings.js');
                applyAppearance({theme:'light',text_size:'large',density:'comfortable',reduce_motion:true});
            }''')
            assert page.evaluate('() => document.documentElement.scrollWidth <= innerWidth + 1'), width
            current_card = page.locator('.campaign-saved-item.is-current')
            expect(current_card.get_by_role('button')).to_have_text('Continue')
            expect(current_card.get_by_role('button')).to_have_attribute(
                'aria-label', 'Continue Fictional swimming capacity campaign')
            assert page.evaluate('''() => {
                const card = document.querySelector('.campaign-saved-item.is-current');
                const content = card.querySelector(':scope > div').getBoundingClientRect();
                const action = card.querySelector(':scope > button').getBoundingClientRect();
                return Math.abs((content.top + content.height / 2) - (action.top + action.height / 2)) < 4;
            }'''), width
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

    def clarification_signer_is_campaign_scoped(self, page):
        from playwright.sync_api import expect
        personal = {
            'full_name': 'Personal Profile Owner', 'role': 'Personal role',
            'organisation': 'Personal organisation', 'email': 'personal@example.invalid',
            'phone': '0400 111 222', 'website': 'https://personal.example.invalid',
        }
        self.set_profile(page, personal)
        self.goto(page, 'campaigns')
        self.transfers(page)
        page.get_by_role('button', name='Start a new campaign', exact=True).click()
        page.get_by_label('Campaign name', exact=True).fill('Fictional signatory scope test')
        page.get_by_label('Applicant organisation', exact=True).fill(
            'Fictional School Community Association')
        page.get_by_label('What will this campaign make possible?', exact=True).fill(
            'CAMPAIGN_WIDE_CONTEXT_MUST_NOT_APPEAR in this unrelated project overview.')
        page.get_by_role('button', name='Add opportunity', exact=True).click()
        page.get_by_label('Opportunity name', exact=True).fill('School-led swimming 2027')
        page.get_by_label('Funder', exact=True).fill('Example Schools Programme')
        page.get_by_label('Project fit and timing', exact=True).fill(
            'SELECTED_OPPORTUNITY_FIT_NOTE_NOT_NEEDED_IN_THIS_LETTER')
        page.get_by_role('button', name='Add requirement', exact=True).click()
        page.get_by_label('Requirement', exact=True).fill('School portal application window')
        page.get_by_role('button', name='Add opportunity', exact=True).click()
        page.get_by_label('Opportunity name', exact=True).fill('Unrelated venue grant')
        page.get_by_label('Funder', exact=True).fill('Other Funder')
        page.get_by_label('Project fit and timing', exact=True).fill(
            'UNRELATED_OPPORTUNITY_CONTEXT_MUST_NOT_APPEAR')
        page.get_by_role('button', name='Add requirement', exact=True).click()
        page.get_by_label('Requirement', exact=True).fill('UNRELATED_REQUIREMENT_MUST_NOT_APPEAR')
        page.locator('.campaign-opportunity').filter(has_text='School-led swimming 2027').click()
        page.get_by_role('button', name='Draft clarification letter', exact=True).click()
        expect(page.locator('#view .page-intro h2')).to_have_text(
            'Prepare a campaign letter for review.')
        expect(page.locator('#view .page-intro p')).to_contain_text(
            'No authorised signatory or reply contact is recorded')
        expect(page.locator('#view')).to_contain_text(
            'No campaign signatory or contact details are recorded.')
        expect(page.locator('.sender-panel')).to_have_attribute('open', '')
        expect(page.get_by_label('Your notes and context', exact=True)).to_have_value('')
        questions = page.get_by_label('Questions you need answered', exact=True).input_value()
        assert questions.splitlines() == [
            'Could you confirm the current requirement for “School portal application window” and what evidence we should provide?',
            'Does this route require a formal application or registration, and which organisation or person is allowed to apply?',
            'Please confirm whether this route has a fixed or rolling intake, its current dates and any next closing date.',
            'Please direct us to the current official programme guidance and application or registration page.',
        ], questions
        for label in ('Your name or role', 'Your role', 'Contact details'):
            expect(page.get_by_label(label, exact=True)).to_have_value('')
        expect(page.get_by_label('Organisation name', exact=True)).to_have_value(
            'Fictional School Community Association')
        page.get_by_role('button', name='Prepare my draft', exact=True).click()
        unsigned = self.document(page).inner_text()
        expect(page.locator('.progress')).to_contain_text('It has not been sent')
        assert 'Kind regards' not in unsigned, unsigned
        assert not any(value in unsigned for value in personal.values()), unsigned
        assert 'School portal application window' in unsigned, unsigned
        assert 'CAMPAIGN_WIDE_CONTEXT_MUST_NOT_APPEAR' not in unsigned, unsigned
        assert 'SELECTED_OPPORTUNITY_FIT_NOTE_NOT_NEEDED_IN_THIS_LETTER' not in unsigned, unsigned
        assert 'UNRELATED_OPPORTUNITY_CONTEXT_MUST_NOT_APPEAR' not in unsigned, unsigned
        assert 'UNRELATED_REQUIREMENT_MUST_NOT_APPEAR' not in unsigned, unsigned
        assert 'Unrelated venue grant' not in unsigned and 'Other Funder' not in unsigned, unsigned
        expect(page.locator('.completion-panel')).to_contain_text('Your name or sign-off')
        expect(page.locator('.completion-panel')).to_contain_text('Your reply contact details')

        self.goto(page, 'campaigns')
        page.get_by_text('Campaign details', exact=True).click()
        page.get_by_label('Authorised campaign signatory', exact=True).fill('Casey Example')
        page.get_by_label('Signatory role', exact=True).fill('P&C President')
        page.get_by_label('Campaign contact details', exact=True).fill(
            'campaign@example.invalid\n0400 222 333')
        page.get_by_role('button', name='Draft clarification letter', exact=True).click()
        expect(page.locator('#view')).to_contain_text('approved for this letter')
        expect(page.locator('#view .page-intro h2')).to_have_text(
            'Prepare a campaign letter for review.')
        expect(page.get_by_label('Your name or role', exact=True)).to_have_value('Casey Example')
        expect(page.get_by_label('Your role', exact=True)).to_have_value('P&C President')
        expect(page.get_by_label('Contact details', exact=True)).to_have_value(
            'campaign@example.invalid\n0400 222 333')
        page.get_by_role('button', name='Prepare my draft', exact=True).click()
        letter = self.document(page).inner_text()
        assert all(value in letter for value in (
            'Casey Example', 'P&C President', 'campaign@example.invalid',
        )), letter
        assert not any(value in letter for value in personal.values()), letter

    def communications_and_clarification_link(self, page):
        from playwright.sync_api import expect
        submitted = []
        communication_campaign = fixture()
        communication_campaign['title'] = 'Fictional communication log campaign'

        def track_workbench_request(request):
            if request.url.endswith('/api/workbench') and request.method == 'POST':
                submitted.append(json.loads(request.post_data or '{}'))

        page.on('request', track_workbench_request)
        self.import_fixture(page, communication_campaign)
        page.get_by_text('Campaign details', exact=True).click()
        page.get_by_label('Authorised campaign signatory', exact=True).fill(
            'Casey Example')
        page.get_by_label('Signatory role', exact=True).fill('P&C President')
        page.get_by_label('Campaign contact details', exact=True).fill(
            'campaign@example.invalid\n0400 222 333')
        self.save(page)
        saved_identity = page.evaluate('''async title => {
            const {request} = await import('/static/api.js');
            const result = await request('/api/campaigns');
            const saved = result.campaigns.find(item =>
                item.title === title);
            return {id: saved.id, revision: saved.revision};
        }''', communication_campaign['title'])

        page.get_by_role('tab', name='Communications', exact=True).click()
        page.get_by_role('button', name='Add communication', exact=True).click()
        message = page.get_by_role('article', name='Campaign communication').first
        message.get_by_label('Direction', exact=True).select_option('incoming')
        message = page.get_by_role('article', name='Campaign communication').first
        expect(message.get_by_label('Communication status', exact=True)).to_have_value(
            'received')
        message.get_by_label('Communication date (user-entered)', exact=True).fill(
            '2026-09-25')
        message.get_by_label('Channel', exact=True).select_option('email')
        message.get_by_label('Person or organisation', exact=True).fill(
            'Jordan Private Contact')
        message.get_by_label('Subject or short title', exact=True).fill(
            'Fictional sponsorship reply')
        message.get_by_label('Message text or summary', exact=True).fill(
            'IncomingMessageBodyFictional: a fictional reply about a '
            'community project.')
        message.get_by_label('Related opportunity', exact=True).select_option(
            'Fictional local sponsorship')
        message.get_by_role('button', name='Add evidence link', exact=True).click()
        message = page.get_by_role('article', name='Campaign communication').first
        link = message.get_by_role('article', name='Communication evidence link')
        link.get_by_label('Evidence title', exact=True).fill('Fictional message record')
        link.get_by_label('Evidence link', exact=True).fill(
            'https://example.invalid/message/42')
        link.get_by_label('Evidence note', exact=True).fill(
            'Fictional browser journey evidence.')
        expect(message).to_contain_text(
            'Recorded as received · user-entered, unverified')
        expect(message).to_contain_text(
            'Evidence links · user-entered, unverified')
        self.save(page)

        page.get_by_role('button', name='Add communication', exact=True).click()
        outgoing = page.get_by_role('article', name='Campaign communication').nth(1)
        expect(outgoing.get_by_label('Communication status', exact=True)).to_have_value(
            'draft')
        outgoing.get_by_label('Communication date (user-entered)', exact=True).fill(
            '2026-09-29')
        outgoing.get_by_label('Person or organisation', exact=True).fill(
            'Riley Private Contact')
        outgoing.get_by_label('Subject or short title', exact=True).fill(
            'Fictional draft question')
        outgoing.get_by_label('Message text or summary', exact=True).fill(
            'OutgoingDraftBodyFictional: not sent.')
        expect(outgoing).to_contain_text('Draft · not sent · user-entered')
        self.save(page)
        communication_rows = page.get_by_role(
            'article', name='Campaign communication')
        expect(communication_rows).to_have_count(2)
        page.get_by_role('tab', name='Opportunities', exact=True).click()
        page.locator('.campaign-opportunity').filter(
            has_text='Fictional local sponsorship').click()
        page.get_by_text('Edit opportunity details', exact=True).click()
        page.get_by_label('Opportunity name', exact=True).fill(
            'Fictional local sponsorship renamed')
        self.save(page)
        saved_identity = page.evaluate('''async title => {
            const {request} = await import('/static/api.js');
            const result = await request('/api/campaigns');
            const saved = result.campaigns.find(item =>
                item.title === title);
            const current = await request('/api/campaigns/' + saved.id);
            return {id: saved.id, revision: saved.revision,
                communications: current.document.communications};
        }''', communication_campaign['title'])
        assert saved_identity['communications'][0]['opportunity'] == \
            'Fictional local sponsorship renamed'
        saved_identity = {key: saved_identity[key] for key in ('id', 'revision')}

        page.reload()
        page.locator('#view .page-intro').first.wait_for()
        page.get_by_role('tab', name='Communications', exact=True).click()
        entries = page.get_by_role('article', name='Campaign communication')
        expect(entries).to_have_count(2)
        entries.nth(0).locator('summary').click()
        expect(entries.nth(0)).to_contain_text(
            'Recorded as received · user-entered, unverified')
        expect(entries.nth(0).get_by_label(
            'Message text or summary', exact=True)).to_have_value(
                'IncomingMessageBodyFictional: a fictional reply about a '
                'community project.')
        entries.nth(1).locator('summary').click()
        expect(entries.nth(1)).to_contain_text('Draft · not sent · user-entered')
        expect(entries.nth(1).get_by_label(
            'Message text or summary', exact=True)).to_have_value(
                'OutgoingDraftBodyFictional: not sent.')
        for width in (390, 320):
            page.set_viewport_size({'width': width, 'height': 844})
            assert page.evaluate(
                '() => document.documentElement.scrollWidth <= innerWidth + 1'), width
        page.set_viewport_size({'width': 1440, 'height': 1000})

        page.get_by_role('button', name='Prepare campaign brief', exact=True).click()
        expect(page.get_by_role('region', name='Your draft report')).to_be_visible(
            timeout=10000)
        export_choice = page.get_by_label(
            'Include full communication records and personal contact details '
            'in this download',
            exact=True)
        assert not export_choice.is_checked()
        filename, redacted_text = self.download(page, 'Download redacted evidence pack')
        assert filename.endswith('.json'), filename
        redacted = json.loads(redacted_text)
        assert redacted['campaign']['communications'][0]['date'] == '2026-09-25'
        assert redacted['campaign']['communications'][1]['status'] == 'draft'
        redacted_json = json.dumps(redacted)
        for private_value in ('IncomingMessageBodyFictional',
                              'OutgoingDraftBodyFictional', 'Jordan Private Contact',
                              'Riley Private Contact',
                              'Casey Example',
                              'campaign@example.invalid', '0400 222 333'):
            assert private_value not in redacted_json, private_value
        assert redacted['export_privacy']['campaign_private_details'] == 'redacted'
        assert 'https://example.invalid/message/42' not in redacted_json

        page.get_by_text('More options', exact=True).click()
        export_choice.check()
        expect(page.get_by_role(
            'button', name='Download evidence pack with private details',
            exact=True)).to_be_visible()
        filename, full_text = self.download(
            page, 'Download evidence pack with private details')
        assert filename.endswith('.json'), filename
        full = json.loads(full_text)
        assert 'IncomingMessageBodyFictional' in full['markdown']
        assert 'OutgoingDraftBodyFictional' in full['markdown']
        assert full['campaign']['communications'][0]['evidence_links'][0]['url'] == \
            'https://example.invalid/message/42'
        assert full['export_privacy']['campaign_private_details'] == \
            'included_by_user_choice'
        assert not export_choice.is_checked()

        stored = page.evaluate('''async id => {
            const {request} = await import('/static/api.js');
            return await request('/api/campaigns/' + id);
        }''', saved_identity['id'])
        assert stored['document']['communications'][0]['content'].startswith(
            'IncomingMessageBodyFictional')
        assert stored['document']['communications'][0]['evidence_links'][0]['url'] == \
            'https://example.invalid/message/42'

        page.get_by_role('tab', name='Opportunities', exact=True).click()
        page.locator('.campaign-opportunity').filter(
            has_text='Fictional local sponsorship renamed').click()
        page.get_by_role('button', name='Draft clarification letter',
                         exact=True).click()
        page.get_by_role('button', name='Prepare my draft', exact=True).click()
        expect(page.get_by_role('region', name='Your draft report')).to_be_visible(
            timeout=10000)
        draft_pack = self.pack(page)
        campaign_link = draft_pack['campaign_link']
        assert {key: campaign_link[key] for key in ('id', 'revision', 'opportunity', 'dirty')} == {
            **saved_identity, 'opportunity': 'Fictional local sponsorship renamed',
            'dirty': False,
        }, campaign_link
        assert campaign_link['evidence_links'] == [{
            'title': 'Fictional local sponsorship renamed',
            'url': 'https://example.invalid/sponsor', 'notes': '',
            'source_id': '', 'checked_at': '',
        }], campaign_link
        assert submitted and all(
            'campaign_link' not in payload for payload in submitted), submitted
        draft_text = page.locator('.document-paper').inner_text()
        page.get_by_label('Draft channel for the campaign log', exact=True).select_option('email')
        page.get_by_role('button', name='Save draft to campaign log', exact=True).click()
        expect(page.get_by_role('button', name='Saved as a draft · not sent', exact=True)).to_be_disabled()
        expect(page.get_by_role('note').filter(has_text='It has not been sent.')).to_be_visible()
        saved_draft = page.evaluate('''async id => {
            const {request} = await import('/static/api.js');
            return await request('/api/campaigns/' + id);
        }''', saved_identity['id'])
        logged = saved_draft['document']['communications'][-1]
        assert logged['opportunity'] == 'Fictional local sponsorship renamed', logged
        assert logged['direction'] == 'outgoing' and logged['status'] == 'draft', logged
        assert logged['channel'] == 'email' and logged['counterparty'] == 'Example Business', logged
        assert logged['date'] == '', logged
        assert logged['content'].startswith('Dear Example Business,'), logged['content']
        assert logged['evidence_links'] == campaign_link['evidence_links'], logged
        assert 'Could you confirm the current requirement for' in logged['content'], logged['content']
        assert 'Could you confirm the current requirement for' in draft_text, draft_text

        self.goto(page, 'campaigns')
        page.get_by_role('tab', name='Communications', exact=True).click()
        entries = page.get_by_role('article', name='Campaign communication')
        expect(entries).to_have_count(3)
        latest = entries.nth(2)
        latest.locator('summary').click()
        expect(latest).to_contain_text('Draft · not sent · user-entered')
        expect(latest.get_by_label(
            'Communication date (user-entered)', exact=True)).to_have_value('')
        latest.get_by_label('Subject or short title', exact=True).fill(
            'Clarification draft saved from the letter screen')
        self.save(page)
        current = page.evaluate('''async id => {
            const {request} = await import('/static/api.js');
            return await request('/api/campaigns/' + id);
        }''', saved_identity['id'])
        assert current['document']['communications'][-1]['subject'] == \
            'Clarification draft saved from the letter screen', current['document']['communications'][-1]

    def communication_source_snapshot(self, page):
        from playwright.sync_api import expect

        snapshot_campaign = fixture()
        # Saved campaigns may share titles, and timestamps have second-level
        # precision. Keep this independent journey's API lookup unambiguous.
        snapshot_campaign['title'] = 'Fictional source snapshot campaign'
        source_id = 'f' * 32
        source = snapshot_campaign['sources'][0]
        source.update(id=source_id, checked_at='2026-09-20')
        original = {
            'title': source['title'], 'url': source['url'],
            'checked_at': source['checked_at'],
        }
        snapshot_campaign['communications'] = [{
            'opportunity': 'Fictional equipment fund', 'date': '2026-09-18',
            'direction': 'outgoing', 'status': 'draft', 'channel': 'email',
            'counterparty': '', 'subject': 'Fictional source snapshot test',
            'content': 'Fictional draft content; not sent.',
            'evidence_links': [{
                'source_id': source_id, **original,
                'notes': 'Fictional snapshot fixture.',
            }],
        }]
        self.import_fixture(page, snapshot_campaign)
        self.save(page)
        saved = page.evaluate('''async title => {
            const {request} = await import('/static/api.js');
            const list = await request('/api/campaigns');
            const item = list.campaigns.find(row =>
                row.title === title);
            const current = await request('/api/campaigns/' + item.id);
            return {id: item.id, document: current.document};
        }''', snapshot_campaign['title'])
        page.get_by_role('tab', name='Opportunities', exact=True).click()
        closed_route = page.locator('.campaign-opportunity').filter(
            has_text='Fictional equipment fund')
        expect(closed_route).to_contain_text('Recorded closed · closing date 28 Sept 2026')
        closed_route.click()
        focus = page.get_by_role('region', name='Selected opportunity')
        expect(focus.locator('.campaign-opportunity-facts')).to_contain_text(
            'Recorded closing date')

        page.locator('.campaign-opportunity').filter(
            has_text='Fictional local sponsorship').click()
        focus = page.get_by_role('region', name='Selected opportunity')
        focus.get_by_text('Edit opportunity details', exact=True).click()
        focus.get_by_label('Application workflow', exact=True).select_option('required')
        page.get_by_role('tab', name='Application answers', exact=True).click()
        expect(page.locator('.notice.warning')).to_contain_text(
            'The application workflow is marked as required, but an applicant or lead is not recorded')
        self.save(page)

        page.get_by_role('tab', name='Communications', exact=True).click()
        communication = page.get_by_role(
            'article', name='Campaign communication').first
        communication.locator('details').evaluate('(details) => { details.open = true; }')
        evidence = communication.get_by_role(
            'article', name='Communication evidence link')
        expect(evidence.get_by_label('Evidence title', exact=True)).to_have_value(
            original['title'])
        expect(evidence.get_by_label('Evidence link', exact=True)).to_have_value(
            original['url'])
        expect(evidence.get_by_label(
            'Source check date at link time · user-entered', exact=True)).to_have_value(
                original['checked_at'])
        self.save(page)

        page.get_by_role('tab', name='Sources', exact=True).click()
        source_card = page.locator(
            f'.campaign-source-details[data-source-id="{source["id"]}"]')
        source_card.locator('summary').click()
        source_card.get_by_label('Source title (required)', exact=True).fill(
            'Fictional updated equipment guidance')
        source_card.get_by_label('Source link', exact=True).fill(
            'https://example.invalid/fund/current')
        source_card.get_by_label(
            'Source checked date · user-entered', exact=True).fill('2026-09-30')
        self.save(page)

        page.get_by_role('tab', name='Communications', exact=True).click()
        communication = page.get_by_role(
            'article', name='Campaign communication').first
        communication.locator('details').evaluate('(details) => { details.open = true; }')
        evidence = communication.get_by_role(
            'article', name='Communication evidence link')
        expect(evidence.get_by_label('Evidence title', exact=True)).to_have_value(
            original['title'])
        expect(evidence.get_by_label('Evidence link', exact=True)).to_have_value(
            original['url'])
        expect(evidence.get_by_label(
            'Source check date at link time · user-entered', exact=True)).to_have_value(
                original['checked_at'])
        expect(evidence.locator('.notice.warning')).to_contain_text(
            'This saved evidence snapshot differs from the current source record')
        self.save(page)

        audited = page.evaluate('''async id => {
            const {request} = await import('/static/api.js');
            const current = await request('/api/campaigns/' + id);
            const report = await request('/api/campaigns/prepare', {
                data: {document: current.document},
            });
            return {document: current.document, markdown: report.markdown};
        }''', saved['id'])
        link = audited['document']['communications'][0]['evidence_links'][0]
        assert link['title'] == original['title'], link
        assert link['url'] == original['url'], link
        assert link['checked_at'] == original['checked_at'], link
        assert 'Saved source snapshot differs from the current source register; recheck before reuse.' \
            in audited['markdown'], audited['markdown']
        assert original['url'] in audited['markdown'], audited['markdown']
        assert 'https://example.invalid/fund/current' in audited['markdown'], audited['markdown']

        evidence.get_by_role('button', name='Clear link', exact=True).click()
        picker = evidence.get_by_label('Link to a saved campaign source', exact=True)
        picker.fill('Fictional updated equipment guidance · example.invalid')
        evidence.get_by_role('button',
            name='Link source: Fictional updated equipment guidance · example.invalid',
            exact=True).click()
        expect(evidence.get_by_label('Evidence title', exact=True)).to_have_value(
            'Fictional updated equipment guidance')
        expect(evidence.get_by_label('Evidence link', exact=True)).to_have_value(
            'https://example.invalid/fund/current')
        expect(evidence.get_by_label(
            'Source check date at link time · user-entered', exact=True)).to_have_value(
                '2026-09-30')
        expect(evidence.locator('.notice.warning')).to_be_hidden()
        self.save(page)
        relinked = page.evaluate('''async id => {
            const {request} = await import('/static/api.js');
            return await request('/api/campaigns/' + id);
        }''', saved['id'])
        refreshed = relinked['document']['communications'][0]['evidence_links'][0]
        assert refreshed['title'] == 'Fictional updated equipment guidance', refreshed
        assert refreshed['url'] == 'https://example.invalid/fund/current', refreshed
        assert refreshed['checked_at'] == '2026-09-30', refreshed


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright
    artifacts = ROOT / 'browser-artifacts'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sinter-campaign-browser-') as temporary, ExitStack() as guard:
        for name in ('chat', 'search', '_post', '_get'):
            guard.enter_context(patch.object(client, name, side_effect=AssertionError('Unexpected remote ' + name)))
        server = make_server(port=0, directory=temporary)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright, args.chromium)
                checks = CampaignChecks(browser, f'http://127.0.0.1:{server.server_port}', artifacts)
                checks.check('campaign-application-budget-roundtrip', checks.workflow)
                checks.check('campaign-answer-review-invalidation', checks.answer_review_invalidation)
                checks.check('campaign-conflict-import-recovery', checks.conflict_and_import)
                checks.check('campaign-clarification-signer-isolation', checks.clarification_signer_is_campaign_scoped)
                checks.check('campaign-communications-and-clarification-link', checks.communications_and_clarification_link)
                checks.check('campaign-communication-source-snapshot', checks.communication_source_snapshot)
                checks.check('campaign-capacity-and-recovery', checks.capacity_and_recovery)
                checks.check('campaign-action-text-contrast', checks.action_text_contrast)
                receipt = {'schema': 'sinter-campaign-browser/v1', 'checks': checks.results,
                           'expected_rejections': ['A stale campaign revision returns HTTP 400 and preserves the user’s edits.',
                                                   'An oversized campaign returns HTTP 400; a backup retains all pending text and an explicit reduced-scope retry succeeds.'],
                           'screenshots': checks.screenshots, 'browser_errors': checks.errors, 'external_requests': checks.external,
                           'passed': all(row['passed'] for row in checks.results) and not checks.errors and not checks.external}
                (artifacts / 'campaign-summary.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
                browser.close()
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
    if not receipt['passed']:
        raise SystemExit('FAIL: inspect browser-artifacts/campaign-summary.json.')
    print('PASS: campaign answers, quote-aware costs, actions, save/reopen, conflict recovery and mobile layout. No external requests.')


if __name__ == '__main__':
    main()
