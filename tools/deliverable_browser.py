"""Offline browser regressions for usable documents and reusable local profiles.

Exercises finished copy/download/edit/save journeys through the real server. All
people, source material and model responses are fictional; external requests are
blocked. These checks establish delivery behaviour, not a product-quality score.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
import time
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from sinter import client, evidence, templates  # noqa: E402
from sinter.profiles import PROFILE_DEFAULTS  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

PROFILE = {
    'full_name': 'Morgan Example', 'role': 'Volunteer coordinator',
    'organisation': 'Fictional Garden P&C', 'email': 'morgan@example.invalid',
    'phone': '0400 000 000', 'website': 'https://example.invalid/garden',
    'location': 'Fictional Riverbank', 'organisation_type': 'Community association',
}
UNFINISHED = re.compile(r'\[(?:recipient|name|organisation|contact details|add\b|review\b|for the meeting\b)[^\]]*\]', re.I)
INTERNAL_ID = re.compile(r'\b[SE][a-f0-9]{16}\b|SHA-?256|[a-f0-9]{64}', re.I)
SOURCE = 'The fictional garden opens on Thursday. Water access needs venue approval.'
FINAL_DRAFT = ('# Garden access enquiry\n\nDear Casey Example,\n\n'
               'Could you confirm **water access** for our *Thursday* volunteer session?\n\n'
               '1. Confirm access with the venue.\n2. Share the agreed arrival time.\n\n'
               'Thank you,\nMorgan Example\nFictional Garden P&C')


class DeliverableChecks:
    def __init__(self, browser, base, artifacts):
        self.browser, self.base, self.artifacts = browser, base, artifacts
        self.results, self.errors, self.external, self.screenshots = [], [], [], []

    def screenshot(self, page, name, *, full_page=False):
        path = self.artifacts / f'deliverable-{name}.png'
        page.screenshot(path=str(path), full_page=full_page, animations='disabled')
        self.screenshots.append(path.name)

    def check(self, name, action):
        started = time.monotonic()
        context = self.browser.new_context(
            viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce',
            accept_downloads=True, permissions=['clipboard-read', 'clipboard-write'])
        page = context.new_page()
        page.set_default_timeout(8000)
        page.on('pageerror', lambda error: self.errors.append({'check': name, 'error': str(error)}))
        page.on('console', lambda message: self.errors.append({'check': name, 'error': message.text, 'url': message.location.get('url', '')})
                if message.type == 'error' else None)
        page.on('dialog', lambda dialog: dialog.accept())

        def guard(route):
            if route.request.url.startswith(self.base + '/'):
                route.continue_()
            else:
                self.external.append(route.request.url)
                route.abort()

        context.route('**/*', guard)
        result = {'check': name, 'passed': False}
        try:
            self.goto(page, 'home')
            self.set_profile(page, PROFILE_DEFAULTS)
            action(page)
            visible = page.locator('body').inner_text()
            assert not re.search(r'(?m)^\s*(?:null|undefined)\s*$', visible), 'An absent UI value is displayed as null/undefined.'
            result['passed'] = True
            print('PASS: ' + name, flush=True)
        except Exception as error:
            result['error'] = str(error)
            try:
                self.screenshot(page, name + '-FAILED', full_page=True)
            except Exception as capture_error:
                result['screenshot_error'] = str(capture_error)
            print('FAIL: ' + name + ': ' + str(error), flush=True)
        finally:
            result['seconds'] = round(time.monotonic() - started, 2)
            self.results.append(result)
            context.close()

    def goto(self, page, route):
        target = self.base + '/#' + route
        if page.url == target:
            page.reload()
        else:
            page.goto(target)
        page.locator('#view .page-intro, #view .workspace-welcome').first.wait_for()

    def set_profile(self, page, profile):
        page.evaluate('''async profile => {
            const {request} = await import('/static/api.js');
            const current = await request('/api/settings');
            await request('/api/settings', {data: {settings: {...current.settings, ...profile}}});
        }''', profile)

    def options(self, page):
        options = (
            page.get_by_role('button', name='Download redacted evidence pack', exact=True),
            page.get_by_role('button', name='Download evidence pack', exact=True),
        )
        if not any(option.is_visible() for option in options):
            page.get_by_text('More options', exact=True).click()

    def download(self, page, label):
        if not page.get_by_role('button', name=label, exact=True).is_visible():
            self.options(page)
        with page.expect_download() as pending:
            page.get_by_role('button', name=label, exact=True).click()
        item = pending.value
        return item.suggested_filename, Path(item.path()).read_text(encoding='utf-8')

    def pack(self, page):
        self.options(page)
        label = 'Download redacted evidence pack'
        if not page.get_by_role('button', name=label, exact=True).is_visible():
            label = 'Download evidence pack'
        name, content = self.download(page, label)
        assert name.endswith('.json'), name
        return json.loads(content)

    def copy(self, page, *, incomplete=False):
        page.get_by_role('button', name='Copy draft text', exact=True).click()
        confirmation = ('Incomplete draft copied. Review the partial text before using it.'
                        if incomplete else 'Copied. Ready to paste into your email or document.')
        page.get_by_text(confirmation, exact=True).wait_for()
        return page.evaluate('() => navigator.clipboard.readText()')

    def document(self, page):
        from playwright.sync_api import expect
        report = page.get_by_role('region', name='Your draft report')
        expect(report).to_be_visible(timeout=10000)
        tab = report.get_by_role('tab', name='Document', exact=True)
        expect(tab).to_have_attribute('aria-selected', 'true')
        return report.get_by_role('tabpanel', name='Document', exact=True)

    def prepare_brief(self, page, *, example=False):
        self.goto(page, 'brief?example=1' if example else 'brief')
        if not example:
            page.get_by_label('Project name', exact=True).fill('Fictional garden access enquiry')
            page.get_by_label('Your notes and context', exact=True).fill(SOURCE)
            page.get_by_label('Questions you need answered', exact=True).fill('Can volunteers use the venue water tap on Thursday?')
        page.get_by_role('button', name='Prepare my draft', exact=True).click()
        return self.document(page)

    def blank_profile(self, page):
        doc = self.prepare_brief(page)
        text = doc.inner_text()
        assert not UNFINISHED.search(text), text
        assert not INTERNAL_ID.search(text), text
        assert 'Thursday' in text and 'water' in text.lower(), text
        assert not any(value in text for value in PROFILE.values()), text
        copied = self.copy(page)
        assert not UNFINISHED.search(copied) and not INTERNAL_ID.search(copied), copied
        assert '**' not in copied and '&amp;' not in copied, copied
        self.screenshot(page, 'blank-profile-letter', full_page=True)

    def complete_example(self, page):
        from playwright.sync_api import expect
        doc = self.prepare_brief(page, example=True)
        body = doc.inner_text()
        assert not UNFINISHED.search(body), body
        assert not INTERNAL_ID.search(body), body
        copied = self.copy(page)
        assert 'Dear ' in copied and 'Thank' in copied, copied
        assert not UNFINISHED.search(copied), copied
        assert 'SHA-256' not in copied and 'Source register' not in copied, copied
        filename, html = self.download(page, 'Download document')
        assert filename.endswith('.html'), filename
        assert '<!doctype html>' in html.lower() and '<style>' in html, html[:300]
        assert 'Fictional example' in html
        exported = page.context.new_page()
        exported.set_content(html)
        expect(exported.locator('.document')).to_contain_text('Dear ')
        expect(exported.locator('script, iframe, img, object, embed')).to_have_count(0)
        assert not UNFINISHED.search(exported.locator('.document').inner_text())
        assert not INTERNAL_ID.search(exported.locator('.document').inner_text())
        self.screenshot(exported, 'portable-letter')
        exported.close()
        pack = self.pack(page)
        assert pack['demo'] is True and pack['sources'] and pack['excerpts'], pack
        assert INTERNAL_ID.search(pack['markdown']), 'Evidence bookkeeping was discarded.'
        assert pack.get('document_markdown'), 'No dedicated document is retained.'
        report = page.get_by_role('region', name='Your draft report')
        report.get_by_role('tab', name='Evidence', exact=True).click()
        expect(report.get_by_role('tab', name='Evidence', exact=True)).to_have_attribute('aria-selected', 'true')
        expect(report).to_contain_text('Source register')
        assert not re.search(r'(?m)^\s*(?:null|undefined)\s*$', report.inner_text()), 'Evidence view displays an absent UI value.'
        report.get_by_role('tab', name='Document', exact=True).click()
        if page.locator('details.export-menu[open]').count():
            page.get_by_text('More options', exact=True).click()
        self.screenshot(page, 'example-letter-desktop', full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.evaluate('''async () => {
            const {applyAppearance} = await import('/static/settings.js');
            applyAppearance({theme:'light',text_size:'large',density:'comfortable',reduce_motion:true});
        }''')
        report.scroll_into_view_if_needed()
        page.evaluate('() => document.querySelector(".report-area").scrollIntoView({block:"start"})')
        metrics = doc.bounding_box()
        assert metrics and metrics['y'] < 844, 'The result itself begins below the first mobile viewport.'
        assert page.evaluate('() => document.documentElement.scrollWidth <= innerWidth + 1')
        self.screenshot(page, 'example-letter-mobile-large')

    def profile_roundtrip(self, page):
        from playwright.sync_api import expect
        self.goto(page, 'settings')
        page.get_by_text('Funding and organisation defaults', exact=True).click()
        labels = {
            'full_name': 'Your full name', 'role': 'Your role',
            'organisation': 'Your group or organisation', 'email': 'Email address',
            'phone': 'Phone number', 'website': 'Website', 'location': 'Location',
            'organisation_type': 'Organisation type',
        }
        for key, label in labels.items():
            page.get_by_label(label, exact=True).fill(PROFILE[key])
        page.get_by_role('button', name='Save my preferences', exact=True).click()
        expect(page.get_by_text('Preferences saved on this computer.', exact=False)).to_be_visible()
        page.reload()
        for key, label in labels.items():
            expect(page.get_by_label(label, exact=True)).to_have_value(PROFILE[key])
        self.goto(page, 'brief')
        page.get_by_text('Your sign-off', exact=True).click()
        expect(page.get_by_label('Your name or role', exact=True)).to_have_value(PROFILE['full_name'])
        expect(page.get_by_label('Your role', exact=True)).to_have_value(PROFILE['role'])
        expect(page.get_by_label('Organisation name', exact=True)).to_have_value(PROFILE['organisation'])
        contact = page.get_by_label('Contact details', exact=True)
        expect(contact).to_have_value('\n'.join(PROFILE[key] for key in ('email', 'phone', 'website')))
        page.get_by_label('Recipient or audience', exact=True).fill('Casey Example')
        page.get_by_label('Project name', exact=True).fill('A complete fictional garden enquiry')
        page.get_by_label('Your notes and context', exact=True).fill(SOURCE)
        page.get_by_label('Questions you need answered', exact=True).fill('Who approves venue water access?')
        page.get_by_role('button', name='Prepare my draft', exact=True).click()
        signed = self.document(page).inner_text()
        assert all(PROFILE[key] in signed for key in ('full_name', 'role', 'organisation', 'email', 'phone', 'website')), signed
        assert not UNFINISHED.search(signed), signed
        self.screenshot(page, 'personalised-letter', full_page=True)
        page.get_by_text('Review or edit project inputs', exact=True).click()
        page.get_by_label('Your name or role', exact=True).fill('')
        page.get_by_label('Your role', exact=True).fill('')
        page.get_by_label('Organisation name', exact=True).fill('')
        contact.fill('')
        page.get_by_label('Project name', exact=True).fill('Explicitly unsigned fictional enquiry')
        page.get_by_label('Your notes and context', exact=True).fill(SOURCE)
        page.get_by_label('Questions you need answered', exact=True).fill('Who approves venue water access?')
        page.get_by_role('button', name='Prepare my draft', exact=True).click()
        doc = self.document(page)
        expect(doc).to_contain_text('Explicitly unsigned fictional enquiry')
        body = doc.inner_text()
        assert not any(PROFILE[key] in body for key in ('full_name', 'role', 'organisation', 'email', 'phone', 'website')), body
        assert not UNFINISHED.search(body), body
        page.get_by_text('Review or edit project inputs', exact=True).click()
        for label in ('Your name or role', 'Your role', 'Organisation name', 'Contact details'):
            expect(page.get_by_label(label, exact=True)).to_have_value('')
        self.goto(page, 'home')
        self.goto(page, 'brief')
        for label in ('Your name or role', 'Your role', 'Organisation name', 'Contact details'):
            expect(page.get_by_label(label, exact=True)).to_have_value('')
        persisted = page.evaluate('''async () => {
            const {request} = await import('/static/api.js'); return (await request('/api/settings')).settings;
        }''')
        assert all(persisted[key] == value for key, value in PROFILE.items())
        self.screenshot(page, 'profile-explicit-blanks', full_page=True)

    def edited_draft_roundtrip(self, page):
        from playwright.sync_api import expect
        self.prepare_brief(page, example=True)
        before = self.pack(page)
        self.options(page)
        page.get_by_role('button', name='Edit draft', exact=True).click()
        updated = '# Reviewed garden enquiry\n\nDear Casey,\n\nPlease confirm **Thursday** water access for the P&C.\n\nMorgan'
        page.get_by_label('Edit your draft', exact=True).fill(updated)
        page.get_by_role('button', name='Apply edits', exact=True).click()
        doc = self.document(page)
        expect(doc.get_by_role('heading', name='Reviewed garden enquiry', exact=True)).to_be_visible()
        assert self.copy(page) == 'Reviewed garden enquiry\n\nDear Casey,\n\nPlease confirm Thursday water access for the P&C.\n\nMorgan'
        after = self.pack(page)
        assert after['markdown'] == before['markdown']
        assert after['sources'] == before['sources'] and after['excerpts'] == before['excerpts']
        assert after['document_markdown'] == before['document_markdown']
        assert after['document_edits']['markdown'] == updated
        page.get_by_role('button', name='Save to My workspace', exact=True).click()
        expect(page.get_by_text('Saved in My workspace', exact=False)).to_be_visible()
        self.goto(page, 'library')
        page.get_by_role('button', name='Open draft', exact=True).first.click()
        doc = self.document(page)
        expect(doc).to_contain_text('Reviewed garden enquiry')
        reopened = self.pack(page)
        assert reopened['document_edits'] == after['document_edits']
        assert reopened['markdown'] == before['markdown'] and reopened['sources'] == before['sources']
        filename, html = self.download(page, 'Download document')
        assert filename.endswith('.html') and 'Reviewed garden enquiry' in html
        assert '**Thursday**' not in html and 'P&amp;C' in html
        self.screenshot(page, 'edited-draft-reopened', full_page=True)

    def template_document(self, page):
        from playwright.sync_api import expect

        def stream(*args, **kwargs):
            yield FINAL_DRAFT
            return client.ChatResult(FINAL_DRAFT, finish_reason='stop')

        self.goto(page, 'explore')
        page.get_by_label('Tool', exact=True).select_option('templates')
        page.get_by_label('Template', exact=True).select_option('custom')
        page.get_by_label('Prompt', exact=True).fill('Prepare the fictional garden enquiry with supplied details.')
        with patch.object(templates, 'chat_stream', side_effect=stream) as model:
            page.get_by_role('button', name='Run template', exact=True).click()
            expect(page.get_by_role('button', name='Copy draft text', exact=True)).to_be_visible(timeout=10000)
        assert model.call_count == 1
        copied = self.copy(page)
        assert 'Garden access enquiry' in copied and 'Thursday' in copied and 'P&C' in copied
        assert '**' not in copied and '*Thursday*' not in copied and '&amp;' not in copied
        name, html = self.download(page, 'Download document')
        assert name.endswith('.html') and 'Model-generated draft' in html
        assert '<strong>water access</strong>' in html and '<em>Thursday</em>' in html
        pack = self.pack(page)
        assert pack['model_draft'] is True and pack.get('document_markdown') == FINAL_DRAFT
        page.get_by_role('button', name='Save to My workspace', exact=True).click()
        expect(page.get_by_text('Saved in My workspace', exact=False)).to_be_visible()
        self.goto(page, 'library')
        page.get_by_role('button', name='Open draft', exact=True).first.click()
        expect(self.document(page)).to_contain_text('Garden access enquiry')
        self.screenshot(page, 'template-final-document', full_page=True)

    def readable_markdown(self, page):
        from playwright.sync_api import expect
        self.prepare_brief(page, example=True)
        self.options(page)
        page.get_by_role('button', name='Edit draft', exact=True).click()
        original = '**literal** and `code` with <tag> & original entities &lt; &amp;; “exact source quotation”.'
        formatted = ('# Reviewed plan\n\nA *useful paragraph* that wraps\n'
                     'onto another source line without a new paragraph.\n\n'
                     '#### What happens next\n\n'
                     '| Task | Owner |\n| --- | --- |\n| Confirm venue | Casey |\n| Check water | Morgan |\n\n'
                     '* First item\n* Second item\n\n'
                     '> First quoted line\n> Second quoted line\n\n'
                     '> ' + evidence.literal(original) + '\n\n'
                     '<img src="https://example.invalid/never.png" onerror="window.__unsafe=true">\n\n'
                     '[unsafe](javascript:alert(1))')
        page.get_by_label('Edit your draft', exact=True).fill(formatted)
        page.get_by_role('button', name='Apply edits', exact=True).click()
        doc = self.document(page)
        expect(doc.locator('em')).to_have_text('useful paragraph')
        expect(doc.locator('h4')).to_have_text('What happens next')
        expect(doc.locator('table tbody tr')).to_have_count(2)
        expect(doc.locator('th')).to_have_text(['Task', 'Owner'])
        expect(doc.locator('ul > li')).to_have_text(['First item', 'Second item'])
        expect(doc.locator('blockquote')).to_have_count(2)
        assert original in doc.locator('blockquote').nth(1).inner_text()
        expect(doc.locator('img, script, svg, iframe, object, embed')).to_have_count(0)
        expect(doc.locator('a[href^="javascript:"]')).to_have_count(0)
        paragraphs = doc.locator('p').all_inner_texts()
        assert any('wraps onto another source line' in ' '.join(value.split()) for value in paragraphs), paragraphs
        copied = self.copy(page)
        assert 'Task\tOwner' in copied and 'Confirm venue\tCasey' in copied, copied
        assert original in copied, copied
        assert '*useful paragraph*' not in copied and '| --- |' not in copied, copied
        self.screenshot(page, 'readable-markdown', full_page=True)

    def assistant_evidence(self, page, *, incomplete=False):
        """Selected records survive save/reopen without becoming verified sources."""
        from playwright.sync_api import expect

        submitted = []
        page.on('request', lambda request: submitted.append(request.url)
                if request.method == 'POST'
                and request.url == self.base + '/api/assistant/job' else None)
        source_id = 'a' * 32
        quotes = [
            'Registered associations may apply with school approval.',
            'Earlier wording: costs must be incurred after approval.',
            '**Literal quote** <script>window.__assistantXss=1</script>',
        ]
        route = ('Fictional garden recovery fund' if incomplete
                 else 'Fictional garden fund')
        document = {
            'title': ('Fictional garden partial-recovery campaign' if incomplete
                      else 'Fictional garden funding campaign'),
            'organisation': PROFILE['organisation'],
            'objective': 'Confirm applicant acceptance and supported garden costs.',
            'opportunities': [{'name': route, 'status': 'clarification'}],
            'sources': [{'id': source_id, 'title': 'Fictional garden guidance',
                         'url': 'https://example.invalid/garden/current',
                         'checked_at': '2026-09-12'}],
            'requirements': [
                {'opportunity': route, 'rule': 'Confirm applicant type',
                 'status': 'unknown', 'evidence': 'Confirmation not received.',
                 'source_id': source_id, 'source_url': 'https://example.invalid/garden/current',
                 'source_quote': quotes[0], 'checked_at': '2026-09-12'},
                {'opportunity': route, 'rule': 'Recheck supported costs',
                 'status': 'unknown', 'source_id': source_id,
                 'source_url': 'https://example.invalid/garden/earlier',
                 'source_quote': quotes[1], 'checked_at': '2026-09-01'},
                {'opportunity': route, 'rule': 'Review the unlinked quotation',
                 'status': 'unknown', 'source_url': 'https://example.invalid/garden/unlinked',
                 'source_quote': quotes[2], 'checked_at': '2026-09-12'},
            ],
            'actions': [{'task': 'Request the garden quote', 'status': 'done',
                         'owner': 'Morgan Example', 'owner_kind': 'person',
                         'owner_confirmed': False, 'opportunity': route,
                         'scope_confirmed': True},
                        {'task': 'Confirm the project scope', 'status': 'open',
                         'owner': 'Funding coordinator (suggested role)',
                         'owner_kind': 'role', 'owner_confirmed': False,
                         'opportunity': route, 'scope_confirmed': True}],
        }
        saved = page.evaluate('''async document => {
            const {request} = await import('/static/api.js');
            await request('/api/settings', {data: {settings: {
              provider:'openai-compatible', api_url:'https://example.invalid/v1',
              model:'fixture-model', max_tokens:512}, confirm_endpoint:true}});
            return await request('/api/campaigns/save', {data:{document}});
        }''', document)
        self.goto(page, 'explore')
        page.get_by_label('Saved campaign', exact=True).select_option(saved['id'])
        expect(page.get_by_label('Funding route', exact=True)).to_have_value(route)
        page.get_by_label('Help me with', exact=True).select_option('enquiry')
        for rule in ('Confirm applicant type', 'Recheck supported costs', 'Review the unlinked quotation'):
            page.get_by_label(rule + ' · unknown', exact=True).check()
        page.get_by_text('Include existing actions', exact=True).click()
        page.get_by_label('Request the garden quote · done', exact=True).check()
        page.get_by_label('Confirm the project scope · open', exact=True).check()
        page.get_by_role('button', name='Preview what will be sent', exact=True).click()
        page.get_by_label('Send only the displayed context to my selected model.', exact=True).check()
        partial_text = ('# Garden applicant enquiry\n\nDear Casey Example,\n\n'
                        'Please confirm whether our garden association can apply '
                        'with school approval.\n\nWe also need confirmation of')
        result = client.ChatResult(
            partial_text if incomplete else FINAL_DRAFT,
            finish_reason='incomplete' if incomplete else 'stop',
            model='fixture-model')
        model_reply = ({'side_effect': client.IncompleteGeneration(result, 512)}
                       if incomplete else {'return_value': result})
        with patch.object(client, 'chat', **model_reply) as model:
            page.get_by_role('button', name='Ask my assistant', exact=True).click()
            doc = self.document(page)
        assert model.call_count == 1
        if incomplete:
            expect(doc).to_contain_text('INCOMPLETE MODEL DRAFT')
            expect(doc).to_contain_text('We also need confirmation of')
            expect(page.get_by_text('Incomplete model suggestion.', exact=False)).to_be_visible()

        def review_saved_context():
            report = page.get_by_role('region', name='Your draft report')
            report.get_by_role('tab', name='Evidence', exact=True).click()
            evidence = report.get_by_role('tabpanel', name='Evidence', exact=True)
            expect(evidence).to_contain_text('3 selected checks · 2 selected actions')
            expect(evidence).to_contain_text('User-entered and unverified')
            assert '0 sources' not in evidence.inner_text()
            assert 'Original sources' not in evidence.inner_text()
            for index, rule in enumerate(('Confirm applicant type', 'Recheck supported costs', 'Review the unlinked quotation'), 1):
                evidence.get_by_text(f'Check {index}: {rule}', exact=True).click()
            expect(evidence.locator('blockquote')).to_have_text(quotes)
            expect(evidence).to_contain_text('matches current source record (not source verification)')
            expect(evidence).to_contain_text('differs from current source record; review needed')
            expect(evidence).to_contain_text('unlinked quote')
            links = evidence.get_by_role('link', name='Open the recorded source link', exact=True)
            expect(links).to_have_count(3)
            assert [links.nth(i).get_attribute('href') for i in range(3)] == [
                'https://example.invalid/garden/current',
                'https://example.invalid/garden/earlier',
                'https://example.invalid/garden/unlinked',
            ]
            for index in range(3):
                expect(links.nth(index)).to_have_attribute('rel', 'noopener noreferrer')
            evidence.get_by_text('Action 1: Request the garden quote', exact=True).click()
            expect(evidence).to_contain_text('Recorded state: done')
            expect(evidence).to_contain_text('acceptance unconfirmed')
            evidence.get_by_text('Action 2: Confirm the project scope', exact=True).click()
            expect(evidence).to_contain_text('Suggested role only; no person named (Funding coordinator)')
            assert page.evaluate('() => window.__assistantXss') is None
            expect(evidence.locator('script, img, iframe')).to_have_count(0)
            return evidence

        evidence = review_saved_context()
        path = self.artifacts / ('deliverable-assistant-partial-record-evidence.png'
                                 if incomplete else 'deliverable-assistant-record-evidence.png')
        evidence.screenshot(path=str(path), animations='disabled')
        self.screenshots.append(path.name)
        pack = self.pack(page)
        assert pack['sources'] == [] and pack['excerpts'] == []
        assert len(pack['context']['selected_checks']) == 3
        assert len(pack['context']['selected_actions']) == 2
        assert pack['context_hash'] in pack['markdown']
        assert pack['context_hash'] not in pack['document_markdown']

        def partial_exports(expected_text):
            report = page.get_by_role('region', name='Your draft report')
            report.get_by_role('tab', name='Document', exact=True).click()
            expect(self.document(page)).to_contain_text('INCOMPLETE MODEL DRAFT')
            record = self.pack(page)
            assert record['incomplete'] is True
            assert 'INCOMPLETE MODEL' in record['markdown']
            assert 'INCOMPLETE MODEL' in record['document_markdown']
            assert record['result']['content'] == partial_text
            assert record['result']['finish_reason'] == 'incomplete'
            assert record['context'] == pack['context']
            assert record['context_hash'] == pack['context_hash']
            copied = self.copy(page, incomplete=True)
            assert 'INCOMPLETE MODEL DRAFT' in copied and expected_text in copied
            name, markdown = self.download(page, 'Download Markdown')
            assert name.endswith('.md')
            assert 'INCOMPLETE MODEL DRAFT' in markdown and expected_text in markdown
            name, html = self.download(page, 'Download document')
            assert name.endswith('.html')
            exported = page.context.new_page()
            try:
                exported.set_content(html)
                text = exported.locator('.document').inner_text()
                assert 'INCOMPLETE MODEL DRAFT' in text and expected_text in text
                expect(exported.locator('script, iframe, object, embed')).to_have_count(0)
            finally:
                exported.close()
            with page.expect_download() as pending:
                page.get_by_role('button', name='Download Word (.docx)', exact=True).click()
            assert pending.value.suggested_filename.endswith('.docx')
            with zipfile.ZipFile(pending.value.path()) as archive:
                assert archive.testzip() is None
                word = ET.fromstring(archive.read('word/document.xml'))
                text = ''.join(element.text or '' for element in word.iter(
                    '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
                assert 'INCOMPLETE MODEL DRAFT' in text and expected_text in text
            return record

        if incomplete:
            partial_exports('We also need confirmation of')
            name, raw = self.download(page, 'Download the assistant record')
            assert name.endswith('.json')
            assistant_record = json.loads(raw)
            assert assistant_record['incomplete'] is True
            assert assistant_record['context'] == pack['context']
            assert assistant_record['result']['content'] == partial_text
        page.get_by_role('button', name='Save to My workspace', exact=True).click()
        expect(page.get_by_text('Saved in My workspace', exact=False)).to_be_visible()
        self.goto(page, 'library')
        page.get_by_role('button', name='Open draft', exact=True).first.click()
        self.document(page)
        review_saved_context()
        if incomplete:
            partial_exports('We also need confirmation of')
            self.options(page)
            page.get_by_role('button', name='Edit draft', exact=True).click()
            updated = ('# Retained garden notes\n\n'
                       'Water access still needs venue confirmation.\n\nMorgan Example')
            editor = page.get_by_label('Edit your draft', exact=True)
            expect(editor).to_be_visible()
            assert 'INCOMPLETE MODEL DRAFT' in editor.input_value()
            editor.fill(updated)
            assert 'INCOMPLETE' not in editor.input_value()
            page.get_by_role('button', name='Apply edits', exact=True).click()
            edited = partial_exports('Water access still needs venue confirmation.')
            assert edited['document_edits']['markdown'] == updated
            assert edited['document_markdown'] == pack['document_markdown']
            page.get_by_role('button', name='Save to My workspace', exact=True).click()
            expect(page.get_by_text('Saved in My workspace', exact=False)).to_be_visible()
            self.goto(page, 'library')
            page.get_by_role('button', name='Open draft', exact=True).first.click()
            self.document(page)
            review_saved_context()
            reopened = partial_exports('Water access still needs venue confirmation.')
            assert reopened['document_edits'] == edited['document_edits']
            self.screenshot(page, 'assistant-partial-edited-reopened', full_page=True)
        current = page.evaluate('''async id => {
            const {request} = await import('/static/api.js');
            return await request('/api/campaigns/' + id);
        }''', saved['id'])
        assert current == saved, 'Assistant generation or document editing changed the campaign.'
        assert model.call_count == 1, 'The partial model request was replayed.'
        assert len(submitted) == 1, 'More than one assistant task was submitted.'


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright
    artifacts = ROOT / 'browser-artifacts'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sinter-deliverable-browser-') as temporary, ExitStack() as guard:
        for name in ('chat', 'search', '_post', '_get'):
            guard.enter_context(patch.object(client, name, side_effect=AssertionError('Unexpected remote ' + name)))
        server = make_server(port=0, directory=temporary)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright, args.chromium)
                checks = DeliverableChecks(browser, f'http://127.0.0.1:{server.server_port}', artifacts)
                checks.check('blank-profile-usable-letter', checks.blank_profile)
                checks.check('complete-example-copy-export', checks.complete_example)
                checks.check('profile-defaults-explicit-blanks', checks.profile_roundtrip)
                checks.check('edit-save-reopen-original-retained', checks.edited_draft_roundtrip)
                server.app.preferences.update({'model': client.MODEL, 'max_tokens': 2048})
                checks.check('template-final-document', checks.template_document)
                checks.check('readable-safe-markdown', checks.readable_markdown)
                checks.check('assistant-selected-record-evidence', checks.assistant_evidence)
                checks.check('assistant-partial-recovery-exports-save-edit',
                             lambda page: checks.assistant_evidence(page, incomplete=True))
                receipt = {
                    'schema': 'sinter-deliverable-browser/v1',
                    'fixture_notice': 'Fictional people, sources and model responses. No external requests permitted. Passing checks do not establish a quality rating.',
                    'checks': checks.results, 'browser_errors': checks.errors,
                    'external_requests': checks.external, 'screenshots': checks.screenshots,
                    'passed': all(row['passed'] for row in checks.results) and not checks.errors and not checks.external,
                }
                (artifacts / 'deliverable-summary.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
                browser.close()
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
    if not receipt['passed']:
        raise SystemExit('FAIL: inspect browser-artifacts/deliverable-summary.json and deliverable-*-FAILED.png.')
    print('PASS: all deliverable browser checks; no external requests or browser errors.')


if __name__ == '__main__':
    main()
