"""Offline native UI qualification through the real server and bounded client.

All source material and gateway responses are fictional public contract fixtures.
This proves interface/protocol behavior, not deployed availability or model quality.
Outbound browser and Python requests are blocked; no origin is accessed.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import tempfile
import threading
import time
import urllib.error
from email.message import Message as Headers
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from sinter import client  # noqa: E402
from sinter.model_profiles import native_request  # noqa: E402
from sinter.operations import checkpoint  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.deliverable_browser import DeliverableChecks  # noqa: E402

FIXTURE = ROOT / "tests/fixtures/public_native_model_api_contract.v1.json"
PACK = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES = {row["name"]: row for row in PACK["cases"]}
SOURCE = "The fictional garden opens Thursday. Water access needs venue approval."
TITLE = "Fictional garden access note"
QUESTION = "What remains to be confirmed?"
CONSENT = (
    "I approve sending exactly this selected material to the displayed model service."
)


class FixtureReply(io.BytesIO):
    def __init__(self, value, mode="stop"):
        super().__init__(json.dumps(value).encode())
        self.headers = Headers()
        self.headers["Content-Type"] = "application/json; charset=utf-8"
        self.mode = mode

    def read(self, size=-1):
        if self.mode == "cancel":
            while True:
                checkpoint()
                time.sleep(0.01)
        if self.mode == "interrupted":
            self.mode = "failed"
            return super().read(min(size, 20))
        if self.mode == "failed":
            raise OSError("Fictional interrupted buffered response")
        return super().read(size)


class FixtureGateway:
    def __init__(self):
        self.mode = "stop"
        self.requests = []
        self.responses = []
        self.discovery = 0
        self.entered = threading.Event()

    def open(self, request, **kwargs):
        if request.full_url == client.BASE_URL + "/models":
            self.discovery += 1
            return FixtureReply(
                CASES["installed-007-audio-origin-projected-to-text"]["expected"][
                    "body"
                ]
            )
        if request.full_url != client.BASE_URL + "/chat/completions":
            raise AssertionError("Unexpected outbound destination was blocked")
        body = json.loads(request.data)
        assert native_request(body) == body
        self.requests.append(body)
        self.entered.set()
        if self.mode in {"busy", "unavailable", "failed-service"}:
            status = {"busy": 429, "unavailable": 503, "failed-service": 502}[self.mode]
            raise urllib.error.HTTPError(
                request.full_url,
                status,
                "Fixture",
                {},
                io.BytesIO(b"Private fixture error must not appear"),
            )
        reply = copy.deepcopy(
            CASES[
                "buffered-length-is-terminal"
                if self.mode == "length"
                else "buffered-stop"
            ]["expected"]["body"]
        )
        if self.mode == "wrong-model":
            reply["model"] = client.DENSE_MODEL
        response = FixtureReply(reply, self.mode)
        self.responses.append(response)
        return response


class NativeChecks(DeliverableChecks):
    def __init__(self, browser, server, artifacts, gateway):
        super().__init__(browser, f"http://127.0.0.1:{server.server_port}", artifacts)
        self.server, self.gateway = server, gateway

    def screenshot(self, page, name, *, full_page=False):
        path = self.artifacts / f"native-{name}.png"
        page.screenshot(path=str(path), full_page=full_page, animations="disabled")
        self.screenshots.append(path.name)

    def check(self, name, action):
        self.gateway.mode = "stop"
        self.gateway.entered.clear()
        self.server.app.preferences.update(
            {
                "provider": "openai-compatible",
                "api_url": client.BASE_URL,
                "model": client.NATIVE_MODEL,
                "max_tokens": 128,
            },
            confirm_endpoint=True,
        )
        before = len(self.gateway.requests)
        super().check(name, action)
        count = len(self.gateway.requests) - before
        expected = (
            0
            if name
            in {
                "native-settings-qualified-discovery-and-preserved-caps",
                "native-oversize-unicode-no-generation",
                "native-full-recipe-refused-before-generation",
            }
            else 1
        )
        self.results[-1]["generation_requests"] = count
        self.results[-1]["expected_generation_requests"] = expected
        if count != expected:
            self.results[-1]["passed"] = False
            previous = self.results[-1].get("error", "")
            self.results[-1]["error"] = (previous + " " if previous else "") + (
                f"Expected {expected} generation requests, received {count}."
            )

    def compact(self, page, *, excerpt=SOURCE):
        self.goto(page, "explore")
        page.get_by_label("Tool", exact=True).select_option("templates")
        page.get_by_label("Template", exact=True).select_option(
            "native-source-question"
        )
        page.get_by_label("Source Title", exact=True).fill(TITLE)
        page.get_by_label("Excerpt", exact=True).fill(excerpt)
        page.get_by_label("Question", exact=True).fill(QUESTION)

    def approve(self, page):
        from playwright.sync_api import expect

        page.get_by_role(
            "button", name="Preview exact source request", exact=True
        ).click()
        expect(
            page.get_by_text("Exact material selected for transmission", exact=True)
        ).to_be_visible()
        approval = page.get_by_role(
            "checkbox",
            name=CONSENT,
        )
        approval.check()
        expect(
            page.get_by_role("button", name="Run template", exact=True)
        ).to_be_enabled()

    def original_inputs(self, page, excerpt=SOURCE):
        from playwright.sync_api import expect

        panel = page.locator("details.project-inputs")
        if panel.get_attribute("open") is None:
            panel.locator("summary").first.click()
        expect(page.get_by_label("Source Title", exact=True)).to_have_value(TITLE)
        expect(page.get_by_label("Excerpt", exact=True)).to_have_value(excerpt)
        expect(page.get_by_label("Question", exact=True)).to_have_value(QUESTION)

    def settings(self, page):
        from playwright.sync_api import expect

        self.server.app.preferences.update({"max_tokens": 512})
        self.goto(page, "settings")
        expect(page.get_by_label("Maximum answer length", exact=True)).to_have_value(
            "512"
        )
        page.get_by_label("Colour theme", exact=True).select_option("light")
        page.get_by_role("button", name="Save my preferences", exact=True).click()
        expect(
            page.get_by_text("Preferences saved on this computer.", exact=False)
        ).to_be_visible()
        assert self.server.app.preferences.snapshot()["max_tokens"] == 512
        page.get_by_role("button", name="Check saved connection", exact=True).click()
        expect(
            page.get_by_text(
                "Model discovery succeeded; generation has not been tested.",
                exact=False,
            )
        ).to_be_visible()
        assert self.gateway.discovery > 0 and not self.gateway.requests
        public = page.evaluate("""async () => {
            const {request} = await import('/static/api.js');
            return (await request('/api/models')).models[0].erais;
        }""")
        assert public["modalities"] == ["text"]
        assert public["assistant_quality"] is False
        assert not set(public) & {
            "audio_generation",
            "vision_scope",
            "token_budget_endpoint",
            "input_modalities",
            "output_modalities",
        }
        for settings in [
            {"model": client.MODEL, "max_tokens": 2048},
            {
                "api_url": "https://fixture-compatible.example/v1",
                "model": "fixture-existing-model",
                "max_tokens": 4096,
            },
        ]:
            self.server.app.preferences.update(settings, confirm_endpoint=True)
            self.goto(page, "settings")
            page.get_by_label("Reading size", exact=True).select_option("large")
            with page.expect_response(
                lambda response: (
                    response.url.endswith("/api/settings")
                    and response.request.method == "POST"
                )
            ) as saved:
                page.get_by_role(
                    "button", name="Save my preferences", exact=True
                ).click()
            assert saved.value.status == 200, saved.value.json()
            for key, value in settings.items():
                assert self.server.app.preferences.snapshot()[key] == value

    def preview_and_complete(self, page):
        from playwright.sync_api import expect

        self.compact(page)
        self.approve(page)
        page.get_by_label("Template", exact=True).select_option("summarize")
        page.get_by_label("Text", exact=True).fill("Distinct fictional summary text.")
        page.get_by_label("Template", exact=True).select_option(
            "native-source-question"
        )
        self.original_inputs(page)
        expect(page.get_by_role("checkbox", name=CONSENT)).not_to_be_checked()
        page.get_by_label("Tool", exact=True).select_option("chat")
        page.get_by_label("Tool", exact=True).select_option("templates")
        expect(page.get_by_label("Template", exact=True)).to_have_value(
            "native-source-question"
        )
        self.original_inputs(page)
        expect(
            page.get_by_role("button", name="Run template", exact=True)
        ).to_be_disabled()
        self.approve(page)
        page.get_by_label("Question", exact=True).fill(QUESTION + " Changed")
        expect(
            page.get_by_role("button", name="Run template", exact=True)
        ).to_be_disabled()
        expect(
            page.get_by_role(
                "checkbox",
                name=CONSENT,
            )
        ).not_to_be_checked()
        page.get_by_label("Question", exact=True).fill(QUESTION)
        self.approve(page)
        page.get_by_role("button", name="Run template", exact=True).click()
        report = page.get_by_role("region", name="Your draft report")
        expect(report).to_be_visible()
        expect(report).to_contain_text("An illustrative fixture response.")
        expect(report.get_by_role("heading").first).to_contain_text(TITLE)
        pack = self.pack(page)
        assert pack["excerpts"][0]["quote"] == SOURCE
        assert pack["sources"][0]["content"] == SOURCE
        assert pack["excerpts"][0]["source_id"] == pack["sources"][0]["id"]
        assert (
            pack["sources"][0]["sha256"] == hashlib.sha256(SOURCE.encode()).hexdigest()
        )
        assert pack["template_inputs"]["variables"]["excerpt"] == SOURCE
        self.original_inputs(page)
        assert len(self.gateway.requests) == 1
        request = self.gateway.requests[-1]
        assert (
            request["max_tokens"] == 128
            and request["stream"] is False
            and request["n"] == 1
        )
        assert (
            len(request["messages"]) == 1
            and SOURCE in request["messages"][0]["content"]
        )
        self.screenshot(page, "complete-source-answer", full_page=True)

    def oversize(self, page):
        from playwright.sync_api import expect

        excerpt = "é" * 1025
        self.compact(page, excerpt=excerpt)
        page.get_by_role(
            "button", name="Preview exact source request", exact=True
        ).click()
        expect(
            page.get_by_text(
                "The native ERAIS question exceeds 2,048 UTF-8 bytes.", exact=False
            )
        ).to_be_visible()
        expect(
            page.get_by_role("button", name="Run template", exact=True)
        ).to_be_disabled()
        self.original_inputs(page, excerpt)

    def length(self, page):
        from playwright.sync_api import expect

        self.gateway.mode = "length"
        self.compact(page)
        self.approve(page)
        page.get_by_role("button", name="Run template", exact=True).click()
        expect(
            page.get_by_role("button", name="Download partial output", exact=True)
        ).to_be_visible()
        with page.expect_download() as pending:
            page.get_by_role(
                "button", name="Download partial output", exact=True
            ).click()
        result = json.loads(Path(pending.value.path()).read_text())
        assert result["complete"] is False
        assert result["partial"]["finish_reason"] == "length"
        assert result["partial"]["content"] == "An illustrative fixture response."
        assert result["template_inputs"]["variables"]["excerpt"] == SOURCE
        assert result["sources"][0]["excerpts"][0]["quote"] == SOURCE
        self.original_inputs(page)
        self.screenshot(page, "incomplete-retained-source", full_page=True)

    def failure(self, page, mode, text):
        from playwright.sync_api import expect

        self.gateway.mode = mode
        self.compact(page)
        self.approve(page)
        page.get_by_role("button", name="Run template", exact=True).click()
        expect(page.get_by_text(text, exact=False)).to_be_visible()
        assert "Private fixture error" not in page.locator("body").inner_text()
        assert page.get_by_role("region", name="Your draft report").count() == 0
        self.original_inputs(page)

    def cancel(self, page):
        from playwright.sync_api import expect

        self.gateway.mode = "cancel"
        self.compact(page)
        self.approve(page)
        page.get_by_role("button", name="Run template", exact=True).click()
        assert self.gateway.entered.wait(3)
        page.get_by_role("button", name="Stop", exact=True).click()
        expect(
            page.get_by_text("Stopped. Partial output is not complete.", exact=True)
        ).to_be_visible()
        self.original_inputs(page)
        for _ in range(100):
            if self.gateway.responses[-1].closed:
                break
            time.sleep(0.01)
        assert self.gateway.responses[-1].closed

    def full_recipe(self, page):
        from playwright.sync_api import expect

        self.compact(page)
        page.get_by_label("Template", exact=True).select_option("research")
        page.get_by_label("Topic", exact=True).fill("Fictional community garden")
        page.get_by_role("button", name="Run template", exact=True).click()
        expect(
            page.get_by_text(
                "The native ERAIS preview supports a short source answer, "
                "not this full template.",
                exact=False,
            )
        ).to_be_visible()
        expect(page.get_by_label("Topic", exact=True)).to_have_value(
            "Fictional community garden"
        )

    def recovered_partial(self, page):
        from playwright.sync_api import expect

        self.gateway.mode = "length"
        submitted = page.evaluate(
            """async variables => {
            const {request} = await import('/static/api.js');
            const selected = {template: 'native-source-question', variables};
            const preview = await request('/api/template/preview', {data: selected});
            return await request('/api/template/job', {data: {
                ...selected, context_hash: preview.context_hash, consent: true,
            }});
        }""",
            {"source_title": TITLE, "excerpt": SOURCE, "question": QUESTION},
        )
        for _ in range(100):
            status = self.server.app.jobs.get(submitted["id"])
            if status["status"] not in {"queued", "running"}:
                break
            time.sleep(0.01)
        assert status["status"] == "failed" and status["result"] is not None
        self.goto(page, "activity")
        page.get_by_role("button", name="Refresh task status", exact=True).click()
        page.get_by_role("button", name="Recover partial output", exact=True).click()
        output = page.get_by_role("region", name="Recovered template output")
        expect(output).to_be_visible()
        expect(output).to_contain_text("INCOMPLETE")
        expect(output).to_contain_text("An illustrative fixture response.")
        with page.expect_download() as pending:
            output.get_by_role(
                "button", name="Download task result", exact=True
            ).click()
        result = json.loads(Path(pending.value.path()).read_text())
        assert result["complete"] is False
        assert result["partial"]["finish_reason"] == "length"
        assert result["template_inputs"]["variables"]["excerpt"] == SOURCE
        assert result["sources"][0]["excerpts"][0]["quote"] == SOURCE
        assert result["sources"][0]["sources"][0]["content"] == SOURCE
        page.get_by_role("button", name="Refresh task status", exact=True).click()
        page.get_by_role("button", name="Recover partial output", exact=True).click()
        expect(
            page.get_by_role("region", name="Recovered template output")
        ).to_contain_text("INCOMPLETE")


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright

    artifacts = ROOT / "browser-artifacts"
    artifacts.mkdir(exist_ok=True)
    gateway = FixtureGateway()
    with (
        tempfile.TemporaryDirectory(prefix="sinter-native-browser-") as temporary,
        patch.object(client.urllib.request, "build_opener", return_value=gateway),
        patch.object(client, "_load_key", return_value=""),
    ):
        server = make_server(port=0, directory=temporary)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright, args.chromium)
                checks = NativeChecks(browser, server, artifacts, gateway)
                checks.check(
                    "native-settings-qualified-discovery-and-preserved-caps",
                    checks.settings,
                )
                # Keep per-journey request counts separate from prior fixtures.
                gateway.requests.clear()
                checks.check(
                    "native-source-preview-consent-edit-invalidation",
                    checks.preview_and_complete,
                )
                checks.check("native-oversize-unicode-no-generation", checks.oversize)
                checks.check(
                    "native-length-retains-incomplete-source-json", checks.length
                )
                for mode, message in [
                    (
                        "wrong-model",
                        "The output was rejected; no request was replayed.",
                    ),
                    ("busy", "The API is busy or rate-limited."),
                    ("unavailable", "temporarily unavailable (HTTP 503)"),
                    ("failed-service", "temporarily unavailable (HTTP 502)"),
                    ("interrupted", "The API connection was interrupted or timed out."),
                ]:
                    checks.check(
                        "native-" + mode + "-no-replay",
                        lambda page, mode=mode, message=message: checks.failure(
                            page, mode, message
                        ),
                    )
                checks.check("native-cancel-closes-buffered-response", checks.cancel)
                checks.check(
                    "native-full-recipe-refused-before-generation", checks.full_recipe
                )
                checks.check(
                    "native-retained-partial-job-recovery-no-replay",
                    checks.recovered_partial,
                )
                expected_errors = [
                    row
                    for row in checks.errors
                    if row.get("check") == "native-oversize-unicode-no-generation"
                    and row.get("url", "").endswith("/api/template/preview")
                    and "400" in row.get("error", "")
                ]
                errors = [row for row in checks.errors if row not in expected_errors]
                receipt = {
                    "schema": "sinter-native-browser/v1",
                    "scope": PACK["scope"],
                    "contract": PACK["contract"],
                    "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                    "checks": checks.results,
                    "screenshots": checks.screenshots,
                    "expected_http_rejections": expected_errors,
                    "browser_errors": errors,
                    "external_requests": checks.external,
                    "passed": all(row["passed"] for row in checks.results)
                    and not errors
                    and not checks.external,
                }
                (artifacts / "native-summary.json").write_text(
                    json.dumps(receipt, indent=2)
                )
                browser.close()
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect browser-artifacts/native-summary.json.")
    print(
        "PASS: native protocol/UI, original inputs, source identities, preserved "
        "settings, incomplete output and failure/cancel boundaries. "
        "No external requests."
    )


if __name__ == "__main__":
    main()
