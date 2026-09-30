"""Fictional provider readiness through the real Sinter browser/server.

The only gateway is an in-memory public-contract fixture. No inference occurs.
Use a disposable workspace and a fresh browser context; block external requests.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.deliverable_browser import DeliverableChecks  # noqa: E402
from tools.native_browser import CASES, FixtureReply  # noqa: E402


class MetadataGateway:
    def __init__(self):
        self.mode = "json"
        self.requests = []
        self.attempts = []
        self.generation_attempts = 0
        self.unexpected_attempts = 0

    def open(self, request, **kwargs):
        target = urlsplit(request.full_url)
        self.attempts.append(
            {"destination": request.full_url, "method": request.get_method()}
        )
        if target.path.endswith("/chat/completions"):
            self.generation_attempts += 1
        if (
            request.get_method() != "GET"
            or request.has_header("Authorization")
            or request.has_header("Cookie")
        ):
            self.unexpected_attempts += 1
            raise AssertionError("Only anonymous GET catalogue fixtures are allowed")
        if target.path != "/v1/models" or target.hostname not in {
            "neuroforge.io",
            "fictional-provider.example.invalid",
        }:
            self.unexpected_attempts += 1
            raise AssertionError("Generation and other outbound calls blocked")
        self.requests.append(request.full_url)
        reply = FixtureReply(
            CASES["installed-007-audio-origin-projected-to-text"]["expected"]["body"]
        )
        if self.mode == "html":
            reply.headers.replace_header("Content-Type", "text/html")
        return reply


class ReadinessChecks(DeliverableChecks):
    def __init__(self, browser, server, artifacts, gateway):
        super().__init__(browser, f"http://127.0.0.1:{server.server_port}", artifacts)
        self.server, self.gateway = server, gateway
        self.server.app.campaigns.save(
            {
                "title": "Fictional Copper Kite access planning",
                "organisation": "Copper Kite Practice Group (fictional)",
                "objective": "Fictional workshop access condition. " * 75,
                "opportunities": [{"name": "Fictional materials exercise"}],
            }
        )

    def connection(self, url, model):
        self.server.app.preferences.update(
            {
                "provider": "openai-compatible",
                "api_url": url,
                "model": model,
                "max_tokens": 128,
            },
            confirm_endpoint=True,
        )

    def preview(self, page):
        self.goto(page, "explore")
        page.get_by_role("button", name="Preview what will be sent", exact=True).click()
        page.get_by_role(
            "heading", name="What your assistant will see", exact=True
        ).wait_for()
        return page.get_by_role("button", name="Ask my assistant", exact=True)

    def automatic_native_alias(self, page):
        from playwright.sync_api import expect

        before = len(self.gateway.requests)
        for url in (client.BASE_URL, "https://NeUrOfOrGe.Io:443/v1/"):
            self.connection(url, client.AUTO_MODEL)
            send = self.preview(page)
            expect(
                page.get_by_text(
                    "This context exceeds the native ERAIS preview size.", exact=False
                )
            ).to_be_visible()
            page.get_by_label(
                "Send only the displayed context to my selected model.", exact=True
            ).check()
            expect(send).to_be_disabled()
        assert len(self.gateway.requests) == before
        self.screenshot(page, "readiness-native-alias-refusal")

    def unsupported_custom_auto(self, page):
        from playwright.sync_api import expect

        before = len(self.gateway.requests)
        self.connection("https://fictional-provider.example.invalid/v1", "auto")
        send = self.preview(page)
        expect(
            page.get_by_text(
                "automatic selection is only available at NeuroForge.", exact=False
            )
        ).to_be_visible()
        page.get_by_label(
            "Send only the displayed context to my selected model.", exact=True
        ).check()
        expect(send).to_be_disabled()
        assert len(self.gateway.requests) == before
        self.screenshot(page, "readiness-custom-auto-refusal")

    def custom_model_label(self, page):
        from playwright.sync_api import expect

        self.gateway.mode = "json"
        self.connection(
            "https://fictional-provider.example.invalid/v1", client.NATIVE_MODEL
        )
        self.goto(page, "settings")
        page.get_by_role("button", name="Check saved connection", exact=True).click()
        expect(page.get_by_text("(configured model)", exact=False)).to_be_visible()
        expect(
            page.get_by_text("(native ERAIS; short text preview)", exact=False)
        ).to_have_count(0)
        expect(
            page.get_by_text(
                "Model discovery succeeded; generation has not been tested.",
                exact=False,
            )
        ).to_be_visible()
        self.screenshot(page, "readiness-custom-model-label")

    def reject_non_json_discovery(self, page):
        from playwright.sync_api import expect

        self.gateway.mode = "html"
        self.connection(client.BASE_URL, client.NATIVE_MODEL)
        self.goto(page, "settings")
        page.get_by_role("button", name="Check saved connection", exact=True).click()
        expect(
            page.get_by_text(
                "The NeuroForge model catalogue requires a JSON response.", exact=False
            )
        ).to_be_visible()
        expect(
            page.get_by_text("Model connection checked.", exact=False)
        ).to_have_count(0)
        expect(
            page.get_by_text("No generation request was sent.", exact=False)
        ).to_be_visible()
        self.screenshot(page, "readiness-wrong-discovery-media")


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright

    artifact_root = ROOT / "browser-artifacts"
    artifact_root.mkdir(exist_ok=True)
    artifacts = Path(
        tempfile.mkdtemp(prefix="provider-readiness-", dir=artifact_root)
    )
    gateway = MetadataGateway()
    with (
        tempfile.TemporaryDirectory(prefix="sinter-provider-fictional-data-") as data,
        patch.object(client.urllib.request, "build_opener", return_value=gateway),
        patch.object(client, "destination_key", return_value=""),
        patch.object(
            client,
            "_load_key",
            side_effect=AssertionError("Credential fallback is blocked"),
        ),
    ):
        server = make_server(port=0, directory=data)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright, args.chromium)
                checks = ReadinessChecks(browser, server, artifacts, gateway)
                for name, action in (
                    ("automatic-native-alias-refusal", checks.automatic_native_alias),
                    ("custom-auto-refusal", checks.unsupported_custom_auto),
                    ("custom-model-health-label", checks.custom_model_label),
                    ("non-json-discovery-refusal", checks.reject_non_json_discovery),
                ):
                    checks.check(name, action)
                expected = [
                    row
                    for row in checks.errors
                    if row["check"] == "non-json-discovery-refusal"
                    and row.get("url", "").endswith("/api/health")
                    and "503" in row["error"]
                ]
                unexpected = [row for row in checks.errors if row not in expected]
                receipt = {
                    "schema": "sinter-provider-readiness-browser/v1",
                    "scope": (
                        "Fictional records, real browser/server, "
                        "mocked catalogue; no inference"
                    ),
                    "checks": checks.results,
                    "screenshots": checks.screenshots,
                    "expected_http_errors": expected,
                    "unexpected_browser_errors": unexpected,
                    "external_requests": checks.external,
                    "mock_catalogue_requests": len(gateway.requests),
                    "gateway_attempts": gateway.attempts,
                    "generation_requests": gateway.generation_attempts,
                    "unexpected_gateway_attempts": gateway.unexpected_attempts,
                    "passed": all(row["passed"] for row in checks.results)
                    and not unexpected
                    and not checks.external
                    and not gateway.generation_attempts
                    and not gateway.unexpected_attempts,
                }
                (artifacts / "receipt.json").write_text(
                    json.dumps(receipt, indent=2) + "\n"
                )
                browser.close()
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
    print("Evidence: " + str(artifacts), flush=True)
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect receipt.json")
    print(
        "PASS: four fictional provider readiness user journeys; "
        "no inference or external app requests"
    )


if __name__ == "__main__":
    main()
