"""Exercise the public download site without releasing or downloading executables."""
from __future__ import annotations
import functools
import json
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools._support import browser_arguments, launch_chromium
API = 'https://api.github.com/repos/neuroforge-io/Sinter/releases?per_page=10'
REPO = 'https://github.com/neuroforge-io/Sinter'


def main(argv: list[str] | None = None) -> None:
    """Exercise the public download page after checking browser setup."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT/'site'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    assets = [{'name': f'Sinter-0.4.0-{system}-{arch}{suffix}', 'size': 1024,
               'browser_download_url': REPO+f'/releases/download/v0.4.0/Sinter-0.4.0-{system}-{arch}{suffix}'}
              for system, arch, suffix in [('windows','x64','-setup.exe'),('windows','x86','-setup.exe'),('windows','arm64','-setup.exe'),
                                            ('darwin','x64','.pkg'),('darwin','arm64','.pkg'),('linux','x64','.deb'),('linux','x86','.deb'),
                                            ('linux','arm64','.deb'),('linux','armv7','.deb')]]
    releases = [{'draft':False, 'prerelease':True, 'tag_name':'v0.4.0', 'assets':assets}]
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright, args.chromium)
            context = browser.new_context(viewport={'width':1440,'height':1000})
            errors = []; unexpected = []
            def guard(route):
                if route.request.url.startswith(base+'/'): route.continue_()
                elif route.request.url == API: route.fulfill(status=200, json=releases)
                else: unexpected.append(route.request.url); route.abort()
            context.route('**/*', guard)
            page = context.new_page(); page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.get_by_role('heading', name='Less busywork. More community.')).to_be_visible()
            expect(page.locator('#release-status')).to_contain_text('v0.4.0')
            for system, count in [('windows',3),('darwin',2),('linux',4)]:
                page.get_by_label('Your operating system').select_option(system)
                expect(page.locator('#downloads a')).to_have_count(count)
                for link in page.locator('#downloads a').all():
                    assert link.get_attribute('href').startswith(REPO+'/releases/download/v0.4.0/')
            artifacts=ROOT/'browser-artifacts'; artifacts.mkdir(exist_ok=True)
            page.screenshot(path=str(artifacts/'public-site-desktop.png'), full_page=True)
            page.set_viewport_size({'width':390, 'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            page.screenshot(path=str(artifacts/'public-site-mobile.png'), full_page=True)
            releases.clear(); page.reload()
            expect(page.locator('#release-status')).to_contain_text('releases page')
            expect(page.locator('#downloads a')).to_have_count(0)
            assert not errors, errors
            assert not unexpected, unexpected
            browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    print('PASS: public landing, all architecture selectors, real-asset-only links, no-release fallback, mobile width. No binaries downloaded.')


if __name__ == '__main__': main()
