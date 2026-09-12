"""Offline browser quality regressions against Sinter's real local HTTP server.

Exercises navigation, research, exports, settings, responsive layout and explicit
template failure recovery. Model responses are fictional, deterministic fixtures;
all external browser and server network access is blocked. Screenshots and a JSON
receipt are written to browser-artifacts/quality-*.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from sinter import client, evidence, templates  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

COMPLETED = 'FICTIONAL CHECK: The supplied note preserves the original deadline.'
FINAL_PARTIAL = 'FICTIONAL FINAL PARTIAL: Confirm the Thursday deadline before publishing.'
INTERIM = 'FICTIONAL INTERIM: Still drafting…'
SUMMARY = 'FICTIONAL SUMMARY: Review the deadline against the source.'


@contextmanager
def model_fixture(*, complete=False):
    """Drive the actual template engine, HTTP SSE and job recovery code."""
    calls = []

    def answer(messages, **kwargs):
        prompt = messages[-1].content
        calls.append(('json', prompt))
        if prompt.startswith('Suggest concrete fixes'):
            return client.ChatResult(FINAL_PARTIAL, finish_reason='stop' if complete else 'length')
        return client.ChatResult(SUMMARY if prompt.startswith('Summarize') else COMPLETED, finish_reason='stop')

    def stream(messages, **kwargs):
        calls.append(('stream', messages[-1].content))
        yield INTERIM
        return client.ChatResult(FINAL_PARTIAL, finish_reason='stop' if complete else 'length')

    with patch.object(templates, 'chat', side_effect=answer), patch.object(templates, 'chat_stream', side_effect=stream):
        yield calls


class QualityChecks:
    def __init__(self, browser, base, artifacts):
        self.browser, self.base, self.artifacts = browser, base, artifacts
        self.errors, self.external, self.results, self.screenshots = [], [], [], []
        self.screenshot_retries = []
        self.layout_metrics = []

    def screenshot(self, page, name, *, full_page=True):
        path = self.artifacts / f'quality-{name}.png'
        try:
            page.screenshot(path=str(path), full_page=full_page, animations='disabled')
        except Exception as exc:
            if 'Unable to capture screenshot' not in str(exc):
                raise
            # Chromium can reject one capture during a compositor resize. Retry
            # the read-only capture once, never the user's operation.
            self.screenshot_retries.append(name)
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            page.screenshot(path=str(path), full_page=full_page, animations='disabled')
        self.screenshots.append(path.name)

    def check(self, name, action):
        started = time.monotonic()
        context = self.browser.new_context(viewport={'width': 1440, 'height': 1000},
                                           reduced_motion='reduce', accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(7000)
        page.on('pageerror', lambda error: self.errors.append({'check': name, 'error': str(error)}))
        page.on('console', lambda message: self.errors.append({'check': name, 'error': message.text})
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
            action(page)
            result['passed'] = True
            print('PASS: ' + name, flush=True)
        except Exception as exc:
            result['error'] = str(exc)
            self.screenshot(page, name + '-FAILED')
            print('FAIL: ' + name + ': ' + str(exc), flush=True)
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
        page.locator('#view .page-intro, #view .hero').first.wait_for()

    def download_json(self, page, name):
        with page.expect_download() as pending:
            page.get_by_role('button', name=name, exact=True).click()
        return json.loads(Path(pending.value.path()).read_text(encoding='utf-8'))

    def finder(self, page):
        from playwright.sync_api import expect
        self.goto(page, 'home')
        launcher = page.get_by_role('button', name=re.compile('Find a tool'))
        launcher.focus()
        page.keyboard.press('Control+k')
        finder = page.get_by_role('dialog')
        search = page.get_by_role('searchbox', name='Find a Sinter tool')
        expect(finder).to_be_visible()
        expect(search).to_be_focused()
        search.fill('utterly-nonexistent-workflow')
        expect(finder).to_contain_text('No match.')
        expect(finder.locator('.finder-result')).to_have_count(0)
        search.fill('minutes')
        expect(finder.locator('.finder-result')).to_have_count(1)
        page.keyboard.press('Escape')
        expect(finder).not_to_be_visible()
        expect(launcher).to_be_focused()
        page.keyboard.press('Control+k')
        search.fill('minutes')
        page.keyboard.press('ArrowDown')
        expect(finder.get_by_role('button', name=re.compile('Meeting minutes'))).to_be_focused()
        self.screenshot(page, 'finder-desktop')
        page.keyboard.press('Escape')
        expect(finder).not_to_be_visible()
        expect(launcher).to_be_focused()
        page.keyboard.press('Control+k')
        search.fill('research')
        page.keyboard.press('Enter')
        expect(page.get_by_role('heading', name='A good question deserves good sources.')).to_be_visible()
        expect(finder).not_to_be_visible()

    def research(self, page):
        from playwright.sync_api import expect
        self.goto(page, 'research')
        topic = page.get_by_label('Research topic', exact=True)
        query = page.get_by_label('Exact web search query', exact=True)
        topic.fill('Community garden water access')
        expect(query).to_have_value('Community garden water access')
        query.fill('local water availability policy')
        topic.fill('Edited research topic')
        expect(query).to_have_value('local water availability policy')
        fictional_search = client.SearchResponse('2026-09-12T00:00:00Z', [client.SearchResult(
            'Fictional water policy', 'https://example.invalid/water-policy',
            'Community garden water access requires venue permission. No budget has been approved.')])
        with patch.object(client, 'search', return_value=fictional_search) as search:
            page.get_by_role('button', name='Prepare research brief', exact=True).click()
            expect(page.get_by_role('region', name='Your draft report')).to_be_visible(timeout=10000)
        search.assert_called_once_with('local water availability policy')
        self.goto(page, 'research?example=1')
        expect(page.get_by_text('OFFLINE EXAMPLE / All people', exact=False)).to_be_visible()
        page.get_by_role('button', name='Prepare research brief', exact=True).click()
        report = page.get_by_role('region', name='Your draft report')
        expect(report).to_be_visible(timeout=10000)
        expect(report).to_contain_text('Source highlights')
        expect(report).not_to_contain_text('Draft enquiry letter')
        inputs = page.locator('.project-inputs')
        expect(inputs).not_to_have_attribute('open', '')
        page.get_by_text('Review or edit project inputs', exact=True).click()
        expect(page.get_by_label('Research topic', exact=True)).to_have_value('Planning an accessible community garden')
        expect(page.get_by_label('Research topic', exact=True)).to_be_editable()
        page.get_by_text('Review or edit project inputs', exact=True).click()
        pack = self.download_json(page, 'Download evidence pack')
        assert pack['workflow'] == 'research' and pack['sources'] and pack['excerpts']
        assert pack['demo'] is True
        citation = report.get_by_role('button', name=re.compile('Show source:')).first
        source_title = citation.get_attribute('aria-label').removeprefix('Show source: ')
        citation.click()
        source = report.locator('details.source').filter(has=page.locator('summary', has_text=source_title)).first
        expect(source).to_have_attribute('open', '')
        expect(source.locator('summary')).to_be_focused()
        assert page.url.endswith('#research?example=1'), 'Citation changed the application route.'
        page.get_by_role('button', name='Save to this computer').click()
        expect(report).to_contain_text('Saved in My workspace')
        self.screenshot(page, 'research-sources-desktop')
        page.get_by_role('link', name='My workspace', exact=True).click()
        page.get_by_role('button', name='Open draft', exact=True).first.click()
        expect(page.get_by_role('region', name='Your draft report')).to_contain_text(pack['title'])
        reopened = self.download_json(page, 'Download evidence pack')
        assert reopened['markdown'] == pack['markdown']
        assert reopened['sources'] == pack['sources']
        assert reopened['excerpts'] == pack['excerpts']

    def meeting_stats(self, page):
        from playwright.sync_api import expect
        self.goto(page, 'meeting?example=1')
        page.get_by_role('button', name='Prepare my draft').click()
        expect(page.get_by_role('region', name='Your draft report')).to_be_visible(timeout=10000)
        pack = self.download_json(page, 'Download evidence pack')
        assert len(pack['segments']) > 0
        stat = page.locator('.report-stat').filter(has_text='Transcript passages')
        expect(stat.locator('strong')).to_have_text(str(len(pack['segments'])))
        self.screenshot(page, 'meeting-stats')

    def settings(self, page):
        from playwright.sync_api import expect
        self.goto(page, 'settings')
        page.get_by_text('Advanced: API and optional RKC connection', exact=True).click()
        maximum = page.get_by_label('Maximum answer length', exact=True)
        address = page.get_by_label('API address', exact=True)
        address.fill('https://neuroforge.io/v1')
        expect(maximum).to_have_attribute('min', '32')
        expect(maximum).to_have_attribute('max', '2048')
        posts = []
        page.on('request', lambda request: posts.append(request.url)
                if request.method == 'POST' and request.url.endswith('/api/settings') else None)
        for invalid in ('31', '2049', '8192', '32.5', ''):
            maximum.fill(invalid)
            assert not maximum.evaluate('(input) => input.checkValidity()'), invalid
            page.get_by_role('button', name='Save my preferences', exact=True).click()
        assert not posts, 'Invalid token settings were submitted.'
        for valid in ('32', '2048'):
            maximum.fill(valid)
            assert maximum.evaluate('(input) => input.checkValidity()'), valid
        address.fill('https://custom.example/v1')
        expect(maximum).to_have_attribute('max', '8192')
        maximum.fill('8192')
        assert maximum.evaluate('(input) => input.checkValidity()')
        address.fill('https://neuroforge.io/v1')
        maximum.fill('2048')
        page.get_by_label('Reading size', exact=True).select_option('large')
        page.get_by_label('Colour theme', exact=True).select_option('light')
        page.get_by_role('button', name='Save my preferences', exact=True).click()
        expect(page.locator('html')).to_have_attribute('data-text-size', 'large')
        expect(page.locator('html')).to_have_attribute('data-theme', 'light')
        expect(page.get_by_text('Preferences saved on this computer.', exact=False)).to_be_visible()
        assert len(posts) == 1
        page.reload()
        expect(page.locator('html')).to_have_attribute('data-text-size', 'large')
        expect(page.locator('html')).to_have_attribute('data-theme', 'light')
        self.screenshot(page, 'settings-large-light')

    def open_template(self, page):
        self.goto(page, 'explore')
        page.get_by_label('Tool', exact=True).select_option('templates')
        page.get_by_label('Template', exact=True).select_option('code-review')
        page.get_by_label('Code', exact=True).fill('Fictional note: the deadline is Thursday.')
        page.get_by_label('Language', exact=True).fill('English')

    def template_stream(self, page, *, complete):
        from playwright.sync_api import expect
        self.open_template(page)
        posts = []
        page.on('request', lambda request: posts.append(request.url)
                if request.method == 'POST' and request.url.endswith('/api/template/stream') else None)
        with model_fixture(complete=complete) as calls:
            page.get_by_role('button', name='Run template', exact=True).click()
            button = 'Download template output' if complete else 'Download partial output'
            expect(page.get_by_role('button', name=button, exact=True)).to_be_visible(timeout=10000)
            pack = self.download_json(page, button)
        assert len(posts) == 1, 'Template request was replayed.'
        assert pack['complete'] is complete
        assert pack['results'][0]['content'] == COMPLETED
        if complete:
            assert len(calls) == 3 and len(pack['results']) == 3 and 'partial' not in pack
            assert pack['results'][1]['content'] == FINAL_PARTIAL
            expect(page.locator('#view')).to_contain_text(SUMMARY)
        else:
            assert len(calls) == 2 and len(pack['results']) == 1
            assert pack['partial']['content'] == FINAL_PARTIAL
            assert pack['partial']['finish_reason'] == 'length'
            expect(page.locator('#view')).to_contain_text('INCOMPLETE / Dependent steps were not run.')
            expect(page.locator('#view')).to_contain_text(FINAL_PARTIAL)
            expect(page.locator('#view')).not_to_contain_text(INTERIM)
            expect(page.get_by_role('heading', name='Summary', exact=True)).to_have_count(0)
        self.screenshot(page, 'template-complete' if complete else 'template-partial')

    def template_job(self, page):
        from playwright.sync_api import expect
        self.goto(page, 'activity')
        posts = []
        page.on('request', lambda request: posts.append(request.url)
                if request.method == 'POST' and request.url.endswith('/api/template/job') else None)
        with model_fixture() as calls:
            outcome = page.evaluate('''async () => {
                const {request, waitForJob} = await import('/static/api.js');
                const job = await request('/api/template/job', {data: {template: 'code-review',
                    variables: {code: 'Fictional note: the deadline is Thursday.', language: 'English'}}});
                try { await waitForJob(job.id); return {unexpected: 'complete'}; }
                catch (error) { return {id: job.id, error: error.message, partial: error.partialResult}; }
            }''')
        assert outcome.get('id') and outcome['partial']['complete'] is False
        assert len(calls) == 2
        page.get_by_role('button', name='Refresh task status', exact=True).click()
        page.get_by_role('button', name='Recover partial output', exact=True).click()
        recovered = page.get_by_role('region', name='Recovered template output')
        expect(recovered).to_contain_text(COMPLETED)
        expect(recovered).to_contain_text(FINAL_PARTIAL)
        expect(recovered).to_contain_text('INCOMPLETE STEP')
        pack = self.download_json(page, 'Download task result')
        assert pack == outcome['partial']
        assert len(posts) == 1, 'Activity recovery submitted another generation.'
        self.screenshot(page, 'activity-partial-recovery')

    def safe_markdown(self, page):
        """Use the actual template UI, then probe escaped evidence and attacks."""
        from playwright.sync_api import expect
        formatted = ('**Availability:** Thursday afternoon.\n\n'
                     '1. Confirm the **venue**.\n'
                     '2. Run `confirm_deadline`.\n'
                     '3. Read [fixture guidance](https://example.invalid/guidance?x=1&y=2).')

        def streamed_answer(*args, **kwargs):
            yield formatted
            return client.ChatResult(formatted, finish_reason='stop')

        self.goto(page, 'explore')
        page.get_by_label('Tool', exact=True).select_option('templates')
        page.get_by_label('Template', exact=True).select_option('custom')
        page.get_by_label('Prompt', exact=True).fill('Fictional browser formatting fixture.')
        with patch.object(templates, 'chat_stream', side_effect=streamed_answer) as model:
            page.get_by_role('button', name='Run template', exact=True).click()
            expect(page.get_by_role('button', name='Download template output', exact=True)).to_be_visible()
            rendered = page.locator('#view .document')
            expect(rendered.locator('strong')).to_have_text(['Availability:', 'venue'])
            expect(rendered.locator('ol > li')).to_have_count(3)
            expect(rendered.locator('code')).to_have_text('confirm_deadline')
            link = rendered.get_by_role('link', name='fixture guidance', exact=True)
            expect(link).to_have_attribute('href', 'https://example.invalid/guidance?x=1&y=2')
            expect(link).to_have_attribute('target', '_blank')
            expect(link).to_have_attribute('rel', 'noopener noreferrer')
            archive = self.download_json(page, 'Download template output')
        assert model.call_count == 1
        assert archive['complete'] is True and archive['results'][0]['content'] == formatted

        original = ('**literal** and `code` with [reference](https://example.invalid/source), '
                    '<tag> & original entities &lt; &amp; &#x3C;; “exact source quotation”.')
        hostile = ('<img src="https://example.invalid/never-load.png" onerror="window.__sinterUnsafe=true">\n'
                   '<script>window.__sinterUnsafe=true</script>\n'
                   '<svg onload="window.__sinterUnsafe=true"></svg>\n'
                   '<iframe src="https://example.invalid/never-frame"></iframe>\n'
                   '[unsafe](javascript:alert(1))\n'
                   '[encoded](jav&#x61;script:alert(1))\n'
                   '[credentials](https://user:password@example.invalid/source)')
        inspected = page.evaluate('''async ({source, hostile}) => {
            const {markdown, h} = await import('/static/ui.js');
            window.__sinterUnsafe = false;
            const exact = markdown('> ' + source);
            const attacks = markdown(hostile);
            const codeText = '<script>**bold** &lt; literal code</script>';
            const fenced = markdown('```text\\n' + codeText + '\\n```');
            const numbered = markdown('4) Fourth item\\n5) Fifth item');
            const sample = h('section', {class:'stack', 'aria-label':'Formatting safety fixtures'},
                h('h3',{},'Exact source quotation'), exact,
                h('h3',{},'Untrusted markup shown as text'), attacks, fenced, numbered);
            document.getElementById('view').append(sample);
            return {quote:exact.querySelector('blockquote').textContent,
                sourceFormatting:exact.querySelectorAll('strong,code,a,img,script,svg,iframe').length,
                dangerousElements:attacks.querySelectorAll('img,script,svg,iframe,object,embed').length,
                attackLinks:attacks.querySelectorAll('a').length,
                attackText:attacks.textContent,
                code:fenced.querySelector('pre').textContent,
                codeElements:fenced.querySelector('pre').children.length,
                listStart:numbered.querySelector('ol').start,
                listItems:numbered.querySelectorAll('ol > li').length,
                executed:window.__sinterUnsafe};
        }''', {'source': evidence.literal(original), 'hostile': hostile})
        assert inspected['quote'] == original, inspected
        assert inspected['sourceFormatting'] == 0
        assert inspected['dangerousElements'] == 0 and inspected['attackLinks'] == 0
        assert '<img src=' in inspected['attackText'] and '<script>' in inspected['attackText']
        assert '[unsafe](javascript:alert(1))' in inspected['attackText']
        assert inspected['executed'] is False
        assert inspected['code'] == '<script>**bold** &lt; literal code</script>\n'
        assert inspected['codeElements'] == 0
        assert inspected['listStart'] == 4 and inspected['listItems'] == 2
        self.screenshot(page, 'safe-markdown')

    def responsive(self, page):
        from playwright.sync_api import expect
        failures = []
        for theme in ('dark', 'light'):
            for size in ('normal', 'large'):
                for width in (390, 320):
                    self.goto(page, 'research?example=1')
                    page.set_viewport_size({'width': width, 'height': 844})
                    page.evaluate('''async ({theme, size}) => {
                        const {applyAppearance} = await import('/static/settings.js');
                        applyAppearance({theme, text_size:size, density:'comfortable', reduce_motion:true});
                    }''', {'theme': theme, 'size': size})
                    page.get_by_role('button', name='Prepare research brief', exact=True).click()
                    expect(page.get_by_role('region', name='Your draft report')).to_be_visible(timeout=10000)
                    label = f'{width}-{theme}-{size}'
                    overflow = page.evaluate('''() => {
                        const width = innerWidth;
                        return {width, document: document.documentElement.scrollWidth,
                            elements: [...document.querySelectorAll('body *')].filter(element => {
                                const r = element.getBoundingClientRect();
                                return r.width && r.height && (r.right > width + 1 || r.left < -1)
                                  && !element.classList.contains('sr-only') && !element.classList.contains('skip-link');
                            }).slice(0,8).map(element => ({tag:element.tagName,class:element.className,
                                text:element.textContent.slice(0,80),right:element.getBoundingClientRect().right}))};
                    }''')
                    if overflow['document'] > width + 1:
                        failures.append({'layout': label, 'overflow': overflow})
                    contrast = page.evaluate('''() => {
                        const style = getComputedStyle(document.documentElement);
                        const rgb = name => {
                            let hex = style.getPropertyValue(name).trim().replace('#','');
                            if (hex.length === 3) hex = [...hex].map(x=>x+x).join('');
                            return hex.match(/[a-f0-9]{2}/gi).map(x=>parseInt(x,16)/255);
                        };
                        const luminance = rgb => rgb.map(c=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4)
                            .reduce((sum,c,i)=>sum+c*[.2126,.7152,.0722][i],0);
                        const ratios = [];
                        for (const text of ['--text','--muted']) for (const background of ['--bg','--surface','--raised']) {
                            const a=luminance(rgb(text)), b=luminance(rgb(background));
                            ratios.push({text,background,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)});
                        }
                        return ratios;
                    }''')
                    if any(row['ratio'] < 4.5 for row in contrast):
                        failures.append({'layout': label, 'contrast': contrast})
                    self.layout_metrics.append({'layout': label, 'viewport_width': width,
                                                'document_width': overflow['document'],
                                                'minimum_text_token_contrast': round(min(row['ratio'] for row in contrast), 3)})
                    self.screenshot(page, 'research-' + label)
                    self.screenshot(page, 'research-' + label + '-viewport', full_page=False)
                    page.get_by_role('button', name=re.compile('Find a tool')).click()
                    finder = page.get_by_role('dialog')
                    expect(finder).to_be_visible()
                    page.get_by_role('searchbox', name='Find a Sinter tool').fill('meeting')
                    box = finder.bounding_box()
                    assert box and box['x'] >= 0 and box['x'] + box['width'] <= width + 1, label
                    self.screenshot(page, 'finder-' + label, full_page=False)
                    page.keyboard.press('Escape')
                    expect(finder).not_to_be_visible()
        assert not failures, json.dumps(failures, indent=2)


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright
    artifacts = ROOT / 'browser-artifacts'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sinter-quality-browser-') as temporary, ExitStack() as guard:
        for name in ('chat', 'search', '_post', '_get'):
            guard.enter_context(patch.object(client, name, side_effect=AssertionError('Unexpected remote ' + name)))
        server = make_server(port=0, directory=temporary)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright, args.chromium)
                checks = QualityChecks(browser, f'http://127.0.0.1:{server.server_port}', artifacts)
                checks.check('finder-keyboard', checks.finder)
                checks.check('research-evidence-roundtrip', checks.research)
                checks.check('meeting-statistics', checks.meeting_stats)
                checks.check('settings-validity', checks.settings)
                checks.check('template-stream-complete', lambda page: checks.template_stream(page, complete=True))
                checks.check('template-stream-partial', lambda page: checks.template_stream(page, complete=False))
                checks.check('template-job-recovery', checks.template_job)
                checks.check('safe-markdown-rendering', checks.safe_markdown)
                checks.check('responsive-contrast', checks.responsive)
                receipt = {'schema': 'sinter-quality-browser/v1', 'fixture_notice': 'Fictional model responses; no external requests permitted.',
                           'checks': checks.results, 'browser_errors': checks.errors, 'external_requests': checks.external,
                           'screenshot_retries': checks.screenshot_retries,
                           'layout_metrics': checks.layout_metrics,
                           'contrast_scope': 'Text and muted CSS tokens against background, surface and raised tokens; not a complete accessibility audit.',
                           'screenshots': checks.screenshots,
                           'passed': all(row['passed'] for row in checks.results) and not checks.errors and not checks.external}
                (artifacts / 'quality-summary.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
                browser.close()
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
    if not receipt['passed']:
        raise SystemExit('FAIL: inspect browser-artifacts/quality-summary.json and quality-*-FAILED.png.')
    print('PASS: all quality browser checks; no external requests or browser errors. See browser-artifacts/quality-summary.json.')


if __name__ == '__main__':
    main()
