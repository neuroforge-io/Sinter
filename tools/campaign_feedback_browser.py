"""Fictional proof of readable campaign recovery messages and no request replay.

Real local saves produce a stale revision and a deliberately dropped successful
acknowledgement. A long Unicode provider error is a display fixture only. No
provider, account, model, download or installed-release qualification is used.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

THEME = "theme => document.documentElement.dataset.theme = theme"
NO_OVERFLOW = "document.documentElement.scrollWidth <= innerWidth"
LIVE_OR_ACTIVE = '[aria-live], [role="alert"], [role="status"], img, script'
AT_END = """selector => {
  const e = document.querySelector(selector);
  return e.scrollTop + e.clientHeight >= e.scrollHeight - 2;
}"""
READ_STORED = "async id => (await fetch('/api/campaigns/' + id)).json()"
LONG_STATUS = "window.feedbackTest.feedback.textContent = 'Fictional '.repeat(200)"


def source_hashes() -> dict[str, str]:
    """Bind this prospective source test to the actual bytes exercised."""
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            "src/sinter/web/campaign-feedback.js",
            "src/sinter/web/campaigns.js",
            "src/sinter/web/campaigns.css",
            "src/sinter/web/api.js",
            "src/sinter/web/ui.js",
            "tools/campaign_feedback_browser.py",
        )
    }


def main(argv: list[str] | None = None) -> None:
    """Use explicit UI actions and retain screenshots, exact text and outcomes."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-campaign-feedback-"))
    before = source_hashes()
    cases, errors, external = [], [], []
    closed = {"browser": False, "server": False, "contexts": False}
    provider_text = (
        "Fictional provider unavailable — display fixture only.\n"
        + "Source evidence: café, 中文, 🧭, e\u0301; retain every original character. "
        * 30
        + '\n<img src="https://example.invalid/x" onerror="window.injected=true">'
        + "\nRecovery: keep the original inputs and partial result. Check the saved "
        "connection explicitly; do not automatically retry an uncertain request."
    )
    saved_title = "Fictional recovery workspace"
    with tempfile.TemporaryDirectory(prefix="sinter-feedback-workspace-") as data:
        with patch.object(
            client, "_open", side_effect=AssertionError("Offline only")
        ) as remote:
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)

                    def private_context(**options):
                        context = browser.new_context(
                            service_workers="block", **options
                        )
                        context.set_default_timeout(8000)
                        context.route(
                            "**/*",
                            lambda route: (
                                route.continue_()
                                if route.request.url.startswith(base + "/")
                                else (external.append(route.request.url), route.abort())
                            ),
                        )
                        context.on(
                            "page",
                            lambda page: page.on(
                                "pageerror", lambda error: errors.append(str(error))
                            ),
                        )
                        return context

                    def edit_title(page, title):
                        field = page.get_by_label("Campaign name", exact=True)
                        if not field.is_visible():
                            summary = page.get_by_text("Campaign details", exact=True)
                            summary.focus()
                            summary.press("Enter")
                        expect(field).to_be_visible()
                        field.fill(title)

                    try:
                        setup = private_context()
                        page = setup.new_page()
                        page.goto(base + "/#campaigns")
                        page.get_by_label("Campaign name", exact=True).fill(saved_title)
                        page.get_by_label(
                            "What will this campaign make possible?", exact=True
                        ).fill(
                            "Fictional only. Keep unknown owners and unconfirmed dates."
                        )
                        with page.expect_response(
                            base + "/api/campaigns/save"
                        ) as reply:
                            page.get_by_role(
                                "button", name="Save campaign", exact=True
                            ).click()
                        saved = reply.value.json()
                        setup.close()
                        for theme, width, height in (
                            ("light", 390, 844),
                            ("dark", 390, 844),
                            ("light", 320, 400),
                            ("dark", 320, 400),
                            ("light", 1440, 1000),
                            ("dark", 1440, 1000),
                            ("light", 640, 240),
                            ("dark", 640, 240),
                            ("light", 640, 200),
                            ("dark", 640, 200),
                        ):
                            for kind in ("conflict", "uncertain", "provider"):
                                label = f"{kind}-{theme}-{width}x{height}"
                                record = {"case": label, "passed": False}
                                cases.append(record)
                                context = private_context(
                                    viewport={"width": width, "height": height},
                                    reduced_motion="reduce",
                                )
                                page = context.new_page()
                                posts = []
                                page.on(
                                    "request",
                                    lambda request: (
                                        posts.append(request.url)
                                        if request.method == "POST"
                                        else None
                                    ),
                                )
                                try:
                                    page.goto(base + "/#campaigns")
                                    expect(
                                        page.get_by_label("Campaign name", exact=True)
                                    ).not_to_have_value("")
                                    page.evaluate(THEME, theme)
                                    edited = (
                                        "Fictional retained edits — café 中文 🧭 "
                                        + label
                                    )
                                    edit_title(page, edited)
                                    if kind == "conflict":
                                        # Another real editor advances the revision.
                                        other = context.new_page()
                                        other.goto(base + "/#campaigns")
                                        expect(
                                            other.get_by_label(
                                                "Campaign name", exact=True
                                            )
                                        ).not_to_have_value("")
                                        edit_title(
                                            other, "Fictional other editor " + label
                                        )
                                        with other.expect_response(
                                            base + "/api/campaigns/save"
                                        ) as reply:
                                            other.get_by_role(
                                                "button",
                                                name="Save campaign",
                                                exact=True,
                                            ).click()
                                        saved = reply.value.json()
                                        other.close()
                                    elif kind == "uncertain":

                                        def lose_acknowledgement(route):
                                            nonlocal saved
                                            result = route.fetch()
                                            assert result.ok
                                            saved = result.json()
                                            route.abort("failed")

                                        page.route(
                                            "**/api/campaigns/save",
                                            lose_acknowledgement,
                                        )
                                    else:
                                        page.route(
                                            "**/api/campaigns/prepare",
                                            lambda route: route.fulfill(
                                                status=503,
                                                content_type="application/json",
                                                body=json.dumps(
                                                    {"error": provider_text}
                                                ),
                                            ),
                                        )
                                    control = (
                                        "Prepare campaign brief"
                                        if kind == "provider"
                                        else "Save campaign"
                                    )
                                    page.get_by_role(
                                        "button", name=control, exact=True
                                    ).click()
                                    feedback = page.locator(".campaign-save-feedback")
                                    expect(
                                        feedback.locator(".notice.error")
                                    ).to_be_visible()
                                    complete = feedback.text_content()
                                    assert complete and (
                                        kind == "provider"
                                        or "Your edits are still here" in complete
                                    )
                                    if kind == "provider":
                                        assert complete == provider_text
                                    expect(
                                        page.get_by_label("Campaign name", exact=True)
                                    ).to_have_value(edited)
                                    expect(
                                        page.get_by_role(
                                            "button", name="Save campaign", exact=True
                                        )
                                    ).to_be_enabled()
                                    post_count = len(posts)
                                    expand = page.get_by_role(
                                        "button", name="Read full message", exact=True
                                    )
                                    clipped = feedback.evaluate(
                                        "e => e.scrollHeight > e.clientHeight + 1"
                                    )
                                    if not clipped:
                                        expect(expand).to_be_hidden()
                                        # Viewport change alone reveals the cue.
                                        page.set_viewport_size(
                                            {"width": 320, "height": 400}
                                        )
                                    expect(expand).to_be_visible()
                                    bounds = page.get_by_role(
                                        "region",
                                        name="Campaign save and preview",
                                        exact=True,
                                    ).bounding_box()
                                    # Keep room beneath the bar even at keyboard height.
                                    fraction = 0.75 if height < 400 else 0.5
                                    assert (
                                        bounds
                                        and bounds["height"]
                                        < page.viewport_size["height"] * fraction
                                    )
                                    assert page.evaluate(NO_OVERFLOW)
                                    page.screenshot(
                                        path=str(artifacts / (label + "-bar.png"))
                                    )
                                    expand.focus()
                                    expand.press("Enter")
                                    dialog = page.get_by_role(
                                        "dialog", name="Campaign message", exact=True
                                    )
                                    expect(dialog).to_be_visible()
                                    message = dialog.get_by_role(
                                        "region",
                                        name="Complete campaign message",
                                        exact=True,
                                    )
                                    expect(message).to_be_focused()
                                    assert message.text_content() == complete
                                    assert dialog.locator(LIVE_OR_ACTIVE).count() == 0
                                    assert page.evaluate(
                                        "window.injected === undefined"
                                    )
                                    box = dialog.bounding_box()
                                    assert box and box["x"] >= 0 and box["y"] >= 0
                                    assert (
                                        box["x"] + box["width"]
                                        <= page.viewport_size["width"]
                                    )
                                    assert (
                                        box["y"] + box["height"]
                                        <= page.viewport_size["height"]
                                    )
                                    page.screenshot(
                                        path=str(artifacts / (label + "-message.png"))
                                    )
                                    message.press("End")
                                    page.wait_for_function(
                                        AT_END, arg=".campaign-message-text"
                                    )
                                    expect(
                                        dialog.get_by_role(
                                            "button", name="Close", exact=True
                                        )
                                    ).to_be_visible()
                                    page.screenshot(
                                        path=str(artifacts / (label + "-end.png"))
                                    )
                                    message.press("Escape")
                                    expect(dialog).to_have_count(0)
                                    expect(expand).to_be_focused()
                                    assert feedback.text_content() == complete
                                    expand.click()
                                    page.get_by_role(
                                        "dialog", name="Campaign message", exact=True
                                    ).get_by_role(
                                        "button", name="Close", exact=True
                                    ).click()
                                    expect(expand).to_be_focused()
                                    # Original keyboard scrolling remains available.
                                    feedback.focus()
                                    feedback.press("End")
                                    page.wait_for_function(
                                        AT_END, arg=".campaign-save-feedback"
                                    )
                                    assert len(posts) == post_count
                                    expect(
                                        page.get_by_label("Campaign name", exact=True)
                                    ).to_have_value(edited)
                                    # Read stored state without replaying either action.
                                    actual = page.evaluate(
                                        READ_STORED,
                                        saved["id"],
                                    )
                                    assert actual == saved
                                    record.update(
                                        passed=True,
                                        message=complete,
                                        posts=posts,
                                        clipped_initially=clipped,
                                        save_bar=bounds,
                                        dialog=box,
                                        stored_revision=saved["revision"],
                                        original_edits_retained=True,
                                        no_request_replay=True,
                                    )
                                finally:
                                    context.close()
                        # A source-only isolated component exercises snapshots and a
                        # missing ResizeObserver, without changing campaign work.
                        context = private_context(
                            viewport={"width": 390, "height": 844}
                        )
                        context.add_init_script("window.ResizeObserver = undefined")
                        page = context.new_page()
                        page.goto(base + "/#campaigns")
                        page.evaluate("""async () => {
                          const mod = await import('/static/campaign-feedback.js');
                          const {campaignFeedback} = mod;
                          const fallback = document.createElement('button');
                          fallback.textContent = 'Fictional focus return';
                          window.feedbackTest = campaignFeedback(() => fallback);
                          const host = document.createElement('div');
                          host.className = 'campaign-save-bar';
                          host.append(fallback, window.feedbackTest.panel);
                          document.body.append(host);
                          window.feedbackTest.host = host;
                          const text = 'Fictional '.repeat(200);
                          window.feedbackTest.feedback.textContent = text;
                        }""")
                        expand = page.get_by_role(
                            "button", name="Read full message", exact=True
                        ).last
                        expand.click()
                        dialog = page.get_by_role(
                            "dialog", name="Campaign message", exact=True
                        )
                        expect(dialog).to_be_visible()
                        original = dialog.get_by_label(
                            "Complete campaign message", exact=True
                        ).text_content()
                        page.evaluate(
                            "window.feedbackTest.feedback.textContent = "
                            "'New short fictional status'"
                        )
                        assert (
                            dialog.get_by_label(
                                "Complete campaign message", exact=True
                            ).text_content()
                            == original
                        )
                        dialog.get_by_role("button", name="Close", exact=True).click()
                        expect(
                            page.locator(".campaign-save-feedback").last
                        ).to_be_focused()
                        expect(expand).to_be_hidden()
                        # Mutation and resize fallback still discover overflow.
                        page.evaluate(LONG_STATUS)
                        expect(expand).to_be_visible()
                        expand.click()
                        page.evaluate("window.feedbackTest.feedback.textContent = ''")
                        assert (
                            dialog.get_by_label(
                                "Complete campaign message", exact=True
                            ).text_content()
                            == original
                        )
                        dialog.get_by_role("button", name="Close", exact=True).click()
                        expect(
                            page.get_by_role(
                                "button", name="Fictional focus return", exact=True
                            )
                        ).to_be_focused()
                        expect(expand).to_be_hidden()
                        page.evaluate(
                            "window.feedbackTest.feedback.textContent = "
                            "'Fictional '.repeat(40)"
                        )
                        expect(expand).to_be_visible()
                        page.set_viewport_size({"width": 1440, "height": 1000})
                        expect(expand).to_be_hidden()
                        page.set_viewport_size({"width": 390, "height": 844})
                        expect(expand).to_be_visible()
                        page.evaluate(LONG_STATUS)
                        expand.click()
                        # Disposal closes the viewer and disconnects observers.
                        page.evaluate(
                            "window.feedbackTest.dispose(); "
                            "window.feedbackTest.host.remove()"
                        )
                        expect(dialog).to_have_count(0)
                        context.close()
                        cases.append(
                            {
                                "case": "snapshot-clear-resize-fallback-disposal",
                                "passed": True,
                                "original_message": original,
                                "snapshot_preserved": True,
                                "focus_return": True,
                            }
                        )
                        closed["contexts"] = True
                    finally:
                        browser.close()
                        closed["browser"] = True
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
                closed["server"] = not thread.is_alive()
                after = source_hashes()
                receipt = {
                    "schema": "sinter-fictional-campaign-feedback-browser/v1",
                    "source_root": str(ROOT),
                    "source_hashes_before": before,
                    "source_hashes_after": after,
                    "source_unchanged": before == after,
                    "cases": cases,
                    "page_errors": errors,
                    "external_requests": external,
                    "model_calls": remote.call_count,
                    "closed": closed,
                    "scope": (
                        "Prospective source-only fictional UI. Provider text is a "
                        "display fixture; no installed, live provider, account or "
                        "customer-device acceptance."
                    ),
                }
                (artifacts / "receipt.json").write_text(
                    json.dumps(receipt, indent=2) + "\n"
                )
                print(
                    json.dumps(
                        {
                            "artifacts": str(artifacts),
                            "cases": len(cases),
                            "closed": closed,
                        }
                    )
                )
            assert cases and all(case["passed"] for case in cases)
            assert not errors and not external and remote.call_count == 0
            assert before == after and all(closed.values())


if __name__ == "__main__":
    main()
