"""Exercise public downloads without releasing or downloading executables."""

from __future__ import annotations

import functools
import hashlib
import json
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools._support import browser_arguments, launch_chromium  # noqa: E402

API = "https://api.github.com/repos/neuroforge-io/Sinter/releases?per_page=10"
REPO = "https://github.com/neuroforge-io/Sinter"
TARGETS = [
    ("windows", "x64", "-setup.exe"),
    ("windows", "x86", "-setup.exe"),
    ("windows", "arm64", "-setup.exe"),
    ("darwin", "x64", ".pkg"),
    ("darwin", "arm64", ".pkg"),
    ("linux", "x64", ".deb"),
    ("linux", "x86", ".deb"),
    ("linux", "arm64", ".deb"),
    ("linux", "armv7", ".deb"),
]


def installer(tag: str, system: str, arch: str, suffix: str) -> dict:
    name = f"Sinter-{tag[1:]}-{system}-{arch}{suffix}"
    return {
        "name": name,
        "size": 13034874,
        "browser_download_url": f"{REPO}/releases/download/{tag}/{name}",
    }


def main(argv: list[str] | None = None) -> None:
    """Check exact preview links, absent targets and metadata recovery in a browser."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    out = ROOT / "browser-artifacts" / "site-download-preview"
    out.mkdir(parents=True, exist_ok=True)
    receipt = out / "browser-receipt.json"
    checks: list[str] = []
    errors: list[str] = []
    unexpected: list[str] = []
    summary = {
        "passed": False,
        "scope": "Standalone download interface; no installers executed "
        "or platform qualification inferred.",
        "checks": checks,
        "page_errors": errors,
        "unexpected_requests": unexpected,
    }
    receipt.write_text(json.dumps({**summary, "state": "running"}) + "\n")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT / "site"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    legacy = {
        "draft": False,
        "prerelease": True,
        "tag_name": "v0.5.3",
        "assets": [installer("v0.5.3", *target) for target in TARGETS],
    }
    native = {
        "draft": False,
        "prerelease": True,
        "tag_name": "v0.5.4rc1",
        "assets": [installer("v0.5.4rc1", "linux", "x64", ".deb")],
    }
    response = {"status": 200, "json": [legacy]}
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright, args.chromium)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})

            def guard(route):
                if route.request.url.startswith(base + "/"):
                    route.continue_()
                elif route.request.url == API:
                    if response.get("abort"):
                        route.abort()
                    elif "body" in response:
                        route.fulfill(
                            status=response["status"],
                            content_type="application/json",
                            body=response["body"],
                        )
                    else:
                        route.fulfill(status=response["status"], json=response["json"])
                else:
                    unexpected.append(route.request.url)
                    route.abort()

            context.route("**/*", guard)
            page = context.new_page()
            page.set_default_timeout(7000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(
                page.get_by_role("heading", name="Less busywork. More community.")
            ).to_be_visible()
            expect(page.locator("#release-status")).to_contain_text("v0.5.3")
            for system, count in [("windows", 3), ("darwin", 2), ("linux", 4)]:
                page.get_by_label("Your operating system").select_option(system)
                expect(page.locator("#downloads a")).to_have_count(count)
                for link in page.locator("#downloads a").all():
                    assert link.get_attribute("href").startswith(
                        REPO + "/releases/download/v0.5.3/"
                    )
            checks.append(
                "Prior v0.5.3 links retain all nine exact architecture fixtures "
                "when it is the selected version"
            )

            response["json"] = [legacy, native]
            page.reload()
            expect(page.locator("#release-status")).to_contain_text(
                "v0.5.4rc1 / Community preview"
            )
            notes = page.locator("#release-status a")
            expect(notes).to_have_attribute("href", REPO + "/releases/tag/v0.5.4rc1")
            page.get_by_label("Your operating system").select_option("linux")
            expect(page.locator("#downloads a")).to_have_count(1)
            expect(page.locator("#downloads a")).to_have_attribute(
                "href", native["assets"][0]["browser_download_url"]
            )
            expect(page.locator("#downloads")).to_contain_text(
                "No Linux arm64 installer is available here for v0.5.4rc1"
            )
            page.locator("#download").screenshot(path=str(out / "linux-preview.png"))
            checks.append(
                "Current rc preview wins over older metadata order and shows "
                "its sole Linux x64 installer with exact release notes"
            )
            for system, label in [("windows", "Windows"), ("darwin", "macOS")]:
                page.get_by_label("Your operating system").select_option(system)
                expect(page.locator("#downloads a")).to_have_count(0)
                expect(page.locator("#downloads")).to_contain_text(
                    f"No {label} x64 installer is available here for v0.5.4rc1"
                )
                expect(page.locator("#downloads")).to_contain_text(
                    "qualified targets; earlier previews remain "
                    "on the all-releases page"
                )
                expect(page.locator("#release-status")).to_contain_text("v0.5.4rc1")
            page.locator("#download").screenshot(path=str(out / "macos-absent.png"))
            checks.append(
                "Windows and macOS explicitly lack current preview installers "
                "and never borrow an older platform package"
            )
            expect(
                page.get_by_role(
                    "link", name="All releases, checksums and build receipts"
                )
            ).to_have_attribute("href", REPO + "/releases")
            expect(page.locator("#download")).to_contain_text(
                "do not disable security protections"
            )
            checks.append(
                "Older previews and unsigned installation guidance remain "
                "accessible through release notes"
            )

            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            )
            page.screenshot(path=str(out / "mobile-preview.png"), full_page=True)
            checks.append(
                "Current preview and absent target messages fit a narrow "
                "viewport without overflow"
            )
            page.set_viewport_size({"width": 1440, "height": 1000})

            response["json"] = [
                None,
                {},
                {**native, "tag_name": "v9.0.0rc01"},
                {**native, "tag_name": "v8.0.0rc1", "prerelease": False},
                {**legacy, "tag_name": "v7.0.0", "draft": True},
                legacy,
            ]
            page.reload()
            expect(page.locator("#release-status")).to_contain_text("v0.5.3")
            page.get_by_label("Your operating system").select_option("windows")
            expect(page.locator("#downloads a")).to_have_count(3)
            checks.append(
                "Malformed, draft and incorrectly promoted rc metadata "
                "cannot become a download version"
            )

            bad_windows = installer("v0.5.4rc1", "windows", "x64", "-setup.exe")
            bad_windows["browser_download_url"] = bad_windows[
                "browser_download_url"
            ].replace("/v0.5.4rc1/", "/v0.5.3/")
            bad_macos = installer("v0.5.4rc1", "darwin", "arm64", ".pkg")
            bad_macos["browser_download_url"] = "https://evil.invalid/installer.pkg"
            response["json"] = [
                legacy,
                {
                    **native,
                    "assets": [None, {}, *native["assets"], bad_windows, bad_macos],
                },
            ]
            page.reload()
            expect(page.locator("#release-status")).to_contain_text("v0.5.4rc1")
            for system in ["windows", "darwin"]:
                page.get_by_label("Your operating system").select_option(system)
                expect(page.locator("#downloads a")).to_have_count(0)
            page.get_by_label("Your operating system").select_option("linux")
            expect(page.locator("#downloads a")).to_have_count(1)
            checks.append(
                "Wrong-release URLs and unsafe hosts stay unavailable while "
                "the valid current installer remains usable"
            )

            response["json"] = [legacy, {**native, "assets": []}]
            page.reload()
            expect(page.locator("#release-status")).to_contain_text("v0.5.4rc1")
            expect(page.locator("#downloads a")).to_have_count(0)
            checks.append(
                "A current preview with no installer stays current "
                "instead of silently falling back"
            )
            for case in [
                {"status": 200, "json": [legacy, {**native, "assets": None}]},
                {"status": 200, "json": []},
                {"status": 200, "json": {}},
                {"status": 503, "json": {"error": "Unavailable"}},
                {"status": 200, "body": "Not JSON"},
                {"status": 200, "abort": True},
            ]:
                response.clear()
                response.update(case)
                page.reload()
                expect(page.locator("#release-status")).to_contain_text(
                    "Download metadata could not be checked"
                )
                expect(page.locator("#downloads a")).to_have_count(0)
            checks.append(
                "Six missing, malformed, unavailable or interrupted metadata "
                "cases keep only the explicit releases-page recovery route"
            )
            assert not errors, errors
            assert not unexpected, unexpected
            browser.close()
            summary["passed"] = True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        summary.update(
            {
                "source_sha256": hashlib.sha256(
                    (ROOT / "site/app.js").read_bytes()
                ).hexdigest(),
                "server_stopped": not thread.is_alive(),
                "browser_closed": True,
                "installer_downloads": 0,
                "public_mutations": 0,
            }
        )
        receipt.write_text(json.dumps(summary, indent=2) + "\n")
    print(
        f"PASS: {len(checks)} public download journeys. "
        f"No binaries downloaded. {receipt}"
    )


if __name__ == "__main__":
    main()
