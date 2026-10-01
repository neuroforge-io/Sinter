"""Recover fictional unsaved campaign inputs after the actual local server stops.

Uses the real campaign UI and JSON export for the independent working-copy
comparison. Clipboard denial/stall are explicitly controlled browser fixtures;
campaign API responses and document contents are never mocked.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.campaign_browser import CampaignChecks, fixture  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_files(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): digest(path)
        for path in directory.rglob("*")
        if path.is_file()
    }


def clipboard_probe() -> str:
    """Observe real clipboard success, or explicitly fixture platform failures."""
    return """mode => {
      const write = navigator.clipboard.writeText.bind(navigator.clipboard);
      window.backupProbe = {writes: [], pending: null};
      Object.defineProperty(navigator.clipboard, 'writeText', {value: text => {
        window.backupProbe.writes.push(text);
        if (mode === 'denied') {
          return Promise.reject(
            new DOMException('Fictional denial', 'NotAllowedError'));
        }
        if (mode === 'stalled') {
          return new Promise(resolve => { window.backupProbe.pending = resolve; });
        }
        return write(text);
      }});
    }"""


def journey(
    browser, artifacts: Path, name: str, mode: str, width: int, oversized=False
):
    from playwright.sync_api import expect

    started = time.monotonic()
    result = {
        "check": name,
        "passed": False,
        "clipboard_fixture": mode,
        "viewport": [width, 844],
        "oversized": oversized,
    }
    resources = {"context_closed": False, "server_closed": False}
    requests, external, errors, expected_connection_errors = [], [], [], []
    server = thread = context = page = None
    saving_after_stop = False
    with tempfile.TemporaryDirectory(prefix="sinter-backup-working-copy-") as data:
        directory = Path(data)
        try:
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            context = browser.new_context(
                viewport={"width": width, "height": 844},
                accept_downloads=True,
                reduced_motion="reduce",
                permissions=["clipboard-read", "clipboard-write"],
            )

            def guard(route):
                if route.request.url.startswith(base + "/"):
                    route.continue_()
                else:
                    external.append(urlsplit(route.request.url).scheme)
                    route.abort()

            context.route("**/*", guard)
            page = context.new_page()
            page.set_default_timeout(10000)
            page.on(
                "request", lambda request: requests.append(urlsplit(request.url).path)
            )
            page.on("pageerror", lambda error: errors.append(str(error)))

            def console(message):
                if message.type != "error":
                    return
                location = urlsplit(message.location.get("url", ""))
                if (
                    saving_after_stop
                    and location.path == "/api/campaigns/save"
                    and "net::ERR_CONNECTION_REFUSED" in message.text
                ):
                    expected_connection_errors.append("stopped-server save refused")
                else:
                    errors.append(message.text)

            page.on("console", console)
            page.on("dialog", lambda dialog: dialog.accept())
            checks = CampaignChecks(browser, base, artifacts)
            campaign = fixture()
            campaign["title"] = f"Fictional stopped-server backup {name}"
            campaign["sources"][0]["id"] = "1234567890abcdef1234567890abcdef"
            campaign["assets"] = [
                {
                    "id": "abcdef1234567890abcdef1234567890",
                    "name": "Fictional product",
                    "references": [],
                }
            ]
            checks.import_fixture(page, campaign)
            checks.save(page)
            before_unsaved = workspace_files(directory)
            page.get_by_role("tab", name="Communications", exact=True).click()
            count = 27 if oversized else 2
            for index in range(count):
                page.get_by_role("button", name="Add communication", exact=True).click()
                card = page.locator(
                    f'.campaign-communication[data-communication-index="{index}"]'
                )
                card.get_by_label("Subject or short title", exact=True).fill(
                    f"Fictional unsaved record {index + 1}"
                )
                content = (
                    "🐝" * 10000
                    if oversized
                    else f"Not sent or agreed. Record {index + 1} e\u0301\n"
                    '<img src="https://example.invalid/not-opened">'
                )
                card.get_by_label("Message text or summary", exact=True).fill(content)
                assert (
                    card.get_by_label(
                        "Message text or summary", exact=True
                    ).input_value()
                    == content
                )
            checks.transfers(page)
            with page.expect_download() as download:
                page.get_by_role(
                    "button", name="Export campaign backup", exact=True
                ).click()
            reference_path = artifacts / f"{name}-working-copy.json"
            download.value.save_as(reference_path)
            expected = json.loads(reference_path.read_text())
            assert len(expected["communications"]) == count
            assert expected["sources"][0]["id"] == campaign["sources"][0]["id"]
            assert expected["assets"][0]["id"] == campaign["assets"][0]["id"]
            if oversized:
                assert reference_path.stat().st_size > 1_000_000
                expect(
                    page.get_by_label("Campaign capacity", exact=True)
                ).to_have_attribute("data-capacity-state", "over")
            assert workspace_files(directory) == before_unsaved
            page.evaluate(clipboard_probe(), mode)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            assert not thread.is_alive()
            resources["server_closed"] = True
            saving_after_stop = True
            page.get_by_role("button", name="Save campaign", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text(
                "Cannot reach the local Sinter app"
            )
            expect(
                page.get_by_role("button", name="Save campaign", exact=True)
            ).to_be_enabled()
            saving_after_stop = False
            request_count = len(requests)
            control = page.get_by_role(
                "region", name="Copy campaign backup", exact=True
            )
            control.get_by_role("button", name="Copy backup text", exact=True).click()
            text = control.get_by_label("Campaign backup text", exact=True)
            expect(text).to_have_value(reference_path.read_text())
            assert json.loads(text.input_value()) == expected
            assert text.get_attribute("readonly") is not None
            assert text.get_attribute("maxlength") is None
            assert page.evaluate("window.backupProbe.writes.length") == 1
            if mode == "stalled":
                expect(
                    control.get_by_role("button", name="Copy backup text", exact=True)
                ).to_be_disabled()
                first = page.locator(
                    '.campaign-communication[data-communication-index="0"]'
                )
                first.get_by_label("Message text or summary", exact=True).fill(
                    "Newer unsaved wording 🐝; no commitment."
                )
                expected["communications"][0]["content"] = (
                    "Newer unsaved wording 🐝; no commitment."
                )
                control.get_by_role(
                    "button", name="Refresh backup text", exact=True
                ).click()
                assert json.loads(text.input_value()) == expected
                expect(control).to_contain_text(
                    "Clipboard may contain an earlier snapshot"
                )
                page.evaluate("window.backupProbe.pending()")
                expect(
                    control.get_by_role("button", name="Copy backup text", exact=True)
                ).to_be_enabled()
                expect(control).to_contain_text(
                    "Clipboard may contain an earlier snapshot"
                )
                assert "Backup text copied from" not in control.inner_text()
            elif mode == "denied":
                expect(control).to_contain_text("Clipboard unavailable")
                expect(text).to_be_focused()
            else:
                expect(control).to_contain_text("Backup text copied from your inputs")
                assert (
                    page.evaluate("navigator.clipboard.readText()")
                    == text.input_value()
                )
            control.get_by_role("button", name="Select backup text", exact=True).click()
            assert text.evaluate(
                "element => element.selectionStart === 0 && "
                "element.selectionEnd === element.value.length"
            )
            assert len(requests) == request_count, (
                "Backup actions made a network request."
            )
            assert workspace_files(directory) == before_unsaved, (
                "Backup changed saved campaign files."
            )
            expect(page.locator(".campaign-save-state")).to_have_text("Unsaved changes")
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            )
            page.screenshot(path=str(artifacts / f"{name}.png"), animations="disabled")
            retained = artifacts / f"{name}-recovery.json"
            retained.write_text(text.input_value())
            result.update(
                {
                    "passed": True,
                    "working_copy_sha256": digest(reference_path),
                    "recovery_sha256": digest(retained),
                    "recovery_bytes": retained.stat().st_size,
                    "clipboard_writes": page.evaluate(
                        "window.backupProbe.writes.length"
                    ),
                    "backup_network_requests": len(requests) - request_count,
                    "saved_workspace_unchanged": True,
                }
            )
        except Exception as problem:
            result["error"] = str(problem)
            if page:
                page.screenshot(
                    path=str(artifacts / f"{name}-FAILED.png"), animations="disabled"
                )
        finally:
            if context:
                context.close()
                resources["context_closed"] = True
            if server:
                if thread and thread.is_alive():
                    server.shutdown()
                    thread.join(timeout=5)
                server.app.close()
                server.server_close()
                resources["server_closed"] = not thread or not thread.is_alive()
    result.update(
        {
            "resources": resources,
            "external_requests": external,
            "page_errors": errors,
            "expected_connection_errors": expected_connection_errors,
            "seconds": round(time.monotonic() - started, 2),
        }
    )
    result["passed"] = (
        result["passed"] and not external and not errors and all(resources.values())
    )
    print(("PASS: " if result["passed"] else "FAIL: ") + name, flush=True)
    return result


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-campaign-backup-proof-"))
    files = (
        "src/sinter/web/campaign-backup.js",
        "src/sinter/web/local-backup.js",
        "src/sinter/web/campaigns.js",
        "tools/campaign_backup_browser.py",
    )
    hashes = {name: digest(ROOT / name) for name in files}
    browser_closed = False
    with ExitStack() as guard:
        for name in ("chat", "search", "_post", "_get"):
            guard.enter_context(
                patch.object(
                    client,
                    name,
                    side_effect=AssertionError("Offline campaign backup only"),
                )
            )
        with sync_playwright() as driver:
            browser = launch_chromium(driver, args.chromium)
            try:
                results = [
                    journey(browser, artifacts, *case)
                    for case in (
                        ("copied-desktop", "real", 1440, False),
                        ("denied-mobile", "denied", 390, False),
                        ("stalled-refresh", "stalled", 1440, False),
                        ("oversized-working-copy", "real", 1440, True),
                    )
                ]
            finally:
                browser.close()
                browser_closed = True
    receipt = {
        "schema": "sinter-campaign-backup-browser/v1",
        "fixture_only": True,
        "checks": results,
        "model_operations_requested": 0,
        "browser_closed": browser_closed,
        "source_sha256": hashes,
        "source_unchanged_during_run": hashes
        == {name: digest(ROOT / name) for name in files},
    }
    receipt["passed"] = (
        all(row["passed"] for row in results)
        and browser_closed
        and receipt["source_unchanged_during_run"]
    )
    target = artifacts / "browser-receipt.json"
    target.write_text(json.dumps(receipt, indent=2))
    print(target)
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect retained fictional backup receipt.")


if __name__ == "__main__":
    main()
