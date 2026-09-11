"""Real browser journey: community casebook, original excerpts, recovery and backups."""
from pathlib import Path
import json
import os
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sinter.server import make_server
from playwright.sync_api import sync_playwright, expect


def main():
    out = Path('browser-artifacts'); out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        server = make_server(port=0, directory=directory)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as driver:
                browser = driver.chromium.launch(executable_path=os.environ.get('SINTER_CHROMIUM') or None)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                base = f'http://127.0.0.1:{server.server_port}'
                page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
                page.goto(base + '/#casebooks')
                page.get_by_role('button', name='Try a fictional community example', exact=True).click()
                page.get_by_role('button', name='Prepare source-only report', exact=True).click()
                page.get_by_text('Your work, with the receipts.', exact=True).wait_for()
                assert 'No wording match' in page.locator('.document').inner_text()
                assert 'No one agreed' in page.locator('.document').inner_text()
                page.screenshot(path=str(out / 'casebook-desktop.png'), full_page=True)
                page.get_by_role('button', name='Light theme', exact=True).click()
                page.screenshot(path=str(out / 'casebook-light.png'), full_page=True)
                page.get_by_role('button', name='Dark theme', exact=True).click()
                with page.expect_download() as download:
                    page.get_by_role('button', name='Export project backup', exact=True).click()
                contents = json.loads(Path(download.value.path()).read_text())
                assert len(contents['documents']) == 3
                # Lose one poll response; the harness must recover the same id, without another submission.
                counts = {'polls': 0, 'posts': 0}
                def route_job(route):
                    counts['polls'] += 1
                    if counts['polls'] == 1: route.abort()
                    else: route.continue_()
                page.route('**/api/jobs/*', route_job)
                page.on('request', lambda req: counts.__setitem__('posts', counts['posts'] + 1) if req.url.endswith('/api/casebooks/build') else None)
                page.get_by_role('button', name='Prepare source-only report', exact=True).click()
                page.get_by_role('button', name='Prepare source-only report', exact=True).wait_for(state='visible')
                expect(page.get_by_role("button", name="Prepare source-only report", exact=True)).to_be_enabled(timeout=15000)
                assert counts['polls'] >= 2 and counts['posts'] == 1
                page.get_by_role('link', name='Recent activity', exact=True).click()
                page.get_by_role('button', name='Open result', exact=True).first.click()
                page.get_by_text('Your work, with the receipts.', exact=True).wait_for()
                page.get_by_role('link', name='Community casebooks', exact=True).click()
                page.get_by_role('button', name='Open project', exact=True).wait_for()
                page.on('dialog', lambda dialog: dialog.accept())
                page.get_by_role('button', name='Open project', exact=True).first.click()
                assert page.get_by_label('Project name', exact=True).input_value() == 'Fictional P&C community evening'
                page.set_viewport_size({'width': 390, 'height': 844})
                page.screenshot(path=str(out / 'casebook-mobile.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.get_by_text('Add notes and references', exact=True).click()
                page.get_by_label('Add text files', exact=True).set_input_files([
                    {'name': f'fragment-{i}.txt', 'mimeType': 'text/plain', 'buffer': b'example'} for i in range(301)])
                page.get_by_text('Choose fewer files. A casebook supports at most 300 documents.', exact=True).wait_for()
                assert page.get_by_label('Project name', exact=True).input_value() == 'Fictional P&C community evening'
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown(); server.app.close(); server.server_close(); thread.join(timeout=5)
    print('PASS: casebook save, source-only matching/gaps, export, single-poll recovery without replay, activity retrieval, reopen and mobile layout.')

if __name__ == '__main__': main()
