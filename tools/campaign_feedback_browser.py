"""Fictional proof of readable campaign recovery messages and no request replay.

Real local saves produce a stale revision and a deliberately dropped successful
acknowledgement. Damaged replies and list-refresh failures are explicit transport
fixtures around real local saves. A long Unicode provider error is display-only. No
provider, account, model, download or installed-release qualification is used.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
from copy import deepcopy
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
ABORTED_BODY = """() => {
  const fetchOriginal = window.fetch;
  window.fetch = async (path, options) => {
    const response = await fetchOriginal(path, options);
    if (path !== '/api/campaigns/save') return response;
    window.feedbackSavedReply = await response.clone().json();
    const body = new ReadableStream({start(controller) {
      controller.error(new DOMException('Fictional body interruption', 'AbortError'));
    }});
    return new Response(body, {status: 200});
  };
}"""


def damaged_reply_body(saved: dict, kind: str) -> tuple[int, str]:
    """Damage a reply copy, never the genuine saved document used for comparison."""
    if kind == "server-error-after-write":
        return 500, json.dumps(
            {
                "error": "Fictional failure after writing",
                "partial_result": {"original": "kept"},
            }
        )
    if kind in ("malformed-applicant", "malformed-evidence"):
        broken = deepcopy(saved)
        document = broken["document"]
        document["opportunities"] = [
            {
                "name": "Fictional malformed route",
                "status": "open",
                "applicant": "",
                "applicant_confirmed": False,
                "application_mode": "required",
            }
        ]
        if kind == "malformed-applicant":
            document["opportunities"][0].update(applicant={}, applicant_confirmed=True)
        else:
            document["requirements"] = [
                {
                    "opportunity": "Fictional malformed route",
                    "rule": "Fictional checked criterion",
                    "status": "met",
                    "evidence": 123,
                    "source_url": "https://example.invalid/x",
                    "source_quote": "Fictional wording",
                    "checked_at": "2026-10-08",
                    "source_id": "",
                }
            ]
        return 200, json.dumps(broken)
    return 200, "{" if kind == "malformed-body" else "null"


def source_hashes() -> dict[str, str]:
    """Bind this prospective source test to the actual bytes exercised."""
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            "src/sinter/web/campaign-feedback.js",
            "src/sinter/web/campaigns.js",
            "src/sinter/web/campaigns.css",
            "src/sinter/web/campaign-save.js",
            "src/sinter/web/api.js",
            "src/sinter/web/ui.js",
            "tools/_support.py",
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
    contexts = []
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
                        contexts.append({"context": context, "closed": False})
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

                    def close_context(context):
                        context.close()
                        for owned in contexts:
                            if owned["context"] is context:
                                owned["closed"] = True
                                if "record" in owned:
                                    owned["record"]["context_closed"] = True
                                break

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
                        close_context(setup)
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
                            kinds = ("conflict", "uncertain", "provider")
                            if width == 390 and height == 844:
                                kinds += (
                                    "malformed-body",
                                    "aborted-body",
                                    "malformed-ack",
                                    "validation",
                                    "confirmed-shelf",
                                    "server-error-after-write",
                                    "malformed-applicant",
                                    "malformed-evidence",
                                )
                            for kind in kinds:
                                label = f"{kind}-{theme}-{width}x{height}"
                                record = {
                                    "case": label,
                                    "passed": False,
                                    "context_closed": False,
                                }
                                cases.append(record)
                                context = private_context(
                                    viewport={"width": width, "height": height},
                                    reduced_motion="reduce",
                                )
                                contexts[-1]["record"] = record
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
                                    if kind == "validation":
                                        edited = ""
                                    prior_saved = saved
                                    edit_title(page, edited)
                                    original_title_node = page.get_by_label(
                                        "Campaign name", exact=True
                                    ).element_handle()
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
                                    elif kind in (
                                        "malformed-body",
                                        "malformed-ack",
                                        "server-error-after-write",
                                        "malformed-applicant",
                                        "malformed-evidence",
                                    ):

                                        def damaged_reply(route):
                                            nonlocal saved
                                            result = route.fetch()
                                            assert result.ok
                                            saved = result.json()
                                            status, body = damaged_reply_body(
                                                saved, kind
                                            )
                                            route.fulfill(
                                                status=status,
                                                content_type="application/json",
                                                body=body,
                                            )

                                        page.route(
                                            "**/api/campaigns/save", damaged_reply
                                        )
                                    elif kind == "aborted-body":
                                        page.evaluate(ABORTED_BODY)
                                    elif kind == "confirmed-shelf":
                                        page.route(
                                            "**/api/campaigns",
                                            lambda route: route.fulfill(
                                                status=500,
                                                content_type="application/json",
                                                body=json.dumps(
                                                    {
                                                        "error": (
                                                            "Fictional list "
                                                            "refresh failure"
                                                        )
                                                    }
                                                ),
                                            ),
                                        )
                                    elif kind == "provider":
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
                                    notice_kind = (
                                        "warning"
                                        if kind == "confirmed-shelf"
                                        else "error"
                                    )
                                    expect(
                                        feedback.locator(".notice." + notice_kind)
                                    ).to_be_visible()
                                    if kind == "aborted-body":
                                        saved = page.evaluate(
                                            "window.feedbackSavedReply"
                                        )
                                    elif kind == "confirmed-shelf":
                                        saved = server.app.campaigns.get(
                                            prior_saved["id"]
                                        )
                                    complete = feedback.text_content()
                                    assert complete and (
                                        kind in ("provider", "confirmed-shelf")
                                        or "Your edits are still here" in complete
                                    )
                                    if kind == "provider":
                                        assert complete == provider_text
                                    unconfirmed = kind in (
                                        "uncertain",
                                        "malformed-body",
                                        "aborted-body",
                                        "malformed-ack",
                                        "server-error-after-write",
                                        "malformed-applicant",
                                        "malformed-evidence",
                                    )
                                    assert (
                                        "save may have finished" in complete
                                    ) == unconfirmed
                                    if unconfirmed:
                                        assert "check the saved campaign" in complete
                                        assert "then retry" not in complete
                                        assert (
                                            saved["revision"]
                                            == prior_saved["revision"] + 1
                                        )
                                    if kind == "uncertain":
                                        assert (
                                            "Cannot reach the local Sinter app"
                                            in complete
                                        )
                                    if kind == "server-error-after-write":
                                        assert (
                                            "Fictional failure after writing"
                                            in complete
                                        )
                                    if kind in (
                                        "malformed-applicant",
                                        "malformed-evidence",
                                    ):
                                        assert (
                                            "earlier campaign inputs are retained"
                                            in complete
                                        )
                                    if kind == "confirmed-shelf":
                                        assert (
                                            "You do not need to save again" in complete
                                        )
                                        expect(
                                            page.locator(".campaign-save-state")
                                        ).to_have_text("Saved on this computer")
                                        assert (
                                            saved["revision"]
                                            == prior_saved["revision"] + 1
                                        )
                                    elif kind != "provider":
                                        expect(
                                            page.locator(".campaign-save-state")
                                        ).to_have_text("Unsaved changes")
                                        expect(
                                            page.locator(
                                                ".campaign-saved-item.is-current"
                                            )
                                        ).to_have_count(1)
                                    expect(
                                        page.get_by_label("Campaign name", exact=True)
                                    ).to_have_value(edited)
                                    expect(
                                        page.get_by_role(
                                            "button", name="Save campaign", exact=True
                                        )
                                    ).to_be_enabled()
                                    post_count = len(posts)
                                    assert posts.count(
                                        base + "/api/campaigns/save"
                                    ) == (0 if kind == "provider" else 1)
                                    expand = page.get_by_role(
                                        "button", name="Read full message", exact=True
                                    )
                                    clipped = feedback.evaluate(
                                        "e => e.scrollHeight > e.clientHeight + 1"
                                    )
                                    # Recovery text is always inspectable, even
                                    # when a short notice happens to fit inline.
                                    expect(expand).to_be_visible()
                                    expect(page.locator(
                                        ".campaign-message-summary"
                                    )).to_be_visible()
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
                                    expect(
                                        page.locator(".campaign-message-dialog")
                                    ).to_have_count(0)
                                    expect(expand).to_be_focused()
                                    assert feedback.text_content() == complete
                                    expand.click()
                                    page.get_by_role(
                                        "dialog", name="Campaign message", exact=True
                                    ).get_by_role(
                                        "button", name="Close", exact=True
                                    ).click()
                                    expect(dialog).to_have_count(0)
                                    expect(
                                        page.locator(".campaign-message-dialog")
                                    ).to_have_count(0)
                                    expect(expand).to_be_focused()
                                    # Original keyboard scrolling remains available.
                                    expand.press("Shift+Tab")
                                    expect(feedback).to_be_focused()
                                    feedback.press("End")
                                    try:
                                        page.wait_for_function(
                                            AT_END, arg=".campaign-save-feedback"
                                        )
                                    except Exception:
                                        record["keyboard_fallback_failure"] = (
                                            feedback.evaluate("""e => ({
                                              focused: e === document.activeElement,
                                              active: document.activeElement.outerHTML,
                                              top: e.scrollTop, height: e.clientHeight,
                                              total: e.scrollHeight
                                            })""")
                                        )
                                        raise
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
                                    if kind != "confirmed-shelf":
                                        assert original_title_node.evaluate(
                                            "e => e.isConnected"
                                        )
                                    if kind in (
                                        "malformed-applicant",
                                        "malformed-evidence",
                                        "malformed-ack",
                                    ):
                                        # Backup stays available for retained inputs.
                                        page.get_by_text(
                                            "Import or back up a campaign", exact=True
                                        ).click()
                                        expect(
                                            page.get_by_role(
                                                "button",
                                                name="Copy backup text",
                                                exact=True,
                                            )
                                        ).to_be_enabled()
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
                                        save_outcome="confirmed"
                                        if kind == "confirmed-shelf"
                                        else "unconfirmed"
                                        if unconfirmed
                                        else "known rejection"
                                        if kind in ("conflict", "validation")
                                        else "display fixture",
                                    )
                                finally:
                                    close_context(context)
                                    record["context_closed"] = True
                        # A source-only isolated component exercises snapshots and a
                        # missing ResizeObserver, without changing campaign work.
                        context = private_context(
                            viewport={"width": 390, "height": 844}
                        )
                        isolated = {
                            "case": "snapshot-clear-resize-fallback-disposal",
                            "passed": False,
                            "context_closed": False,
                        }
                        cases.append(isolated)
                        contexts[-1]["record"] = isolated
                        page = None
                        try:
                            context.add_init_script(
                                "window.ResizeObserver = undefined"
                            )
                            page = context.new_page()
                            page.goto(base + "/#campaigns")
                            page.evaluate("""async () => {
                              const mod = await import('/static/campaign-feedback.js');
                              const {campaignFeedback} = mod;
                              const fallback = document.createElement('button');
                              fallback.textContent = 'Fictional focus return';
                              window.feedbackTest = campaignFeedback(() => fallback);
                              const host = document.createElement('div');
                              host.id = 'fictional-feedback-component';
                              host.className = 'campaign-save-bar';
                              host.append(fallback, window.feedbackTest.panel);
                              document.body.append(host);
                              window.feedbackTest.host = host;
                              const text = 'Fictional '.repeat(200);
                              window.feedbackTest.feedback.textContent = text;
                            }""")
                            component = page.locator("#fictional-feedback-component")
                            # Include hidden nodes so clearing the isolated panel
                            # cannot retarget the real campaign's visible disclosure.
                            expand = component.get_by_role(
                                "button", name="Read full message", exact=True,
                                include_hidden=True,
                            )
                            feedback = component.locator(".campaign-save-feedback")
                            announcement = component.locator(
                                ".campaign-message-announcement"
                            )
                            expand.click()
                            dialog = page.get_by_role(
                                "dialog", name="Campaign message", exact=True
                            )
                            expect(dialog).to_be_visible()
                            message = dialog.get_by_label(
                                "Complete campaign message", exact=True
                            )
                            original = message.text_content()
                            short = "New short fictional status"
                            page.evaluate(
                                "text => window.feedbackTest.feedback.textContent "
                                "= text",
                                short,
                            )
                            expect(message).to_have_text(original)
                            dialog.get_by_role(
                                "button", name="Close", exact=True
                            ).click()
                            expect(expand).to_be_focused()
                            expect(expand).to_be_visible()
                            expect(feedback).to_have_text(short)
                            expect(feedback).to_be_hidden()
                            expect(announcement).to_have_text(short)
                            assert feedback.text_content() == short
                            assert announcement.text_content() == short
                            expand.click()
                            expect(message).to_have_text(short)
                            assert message.text_content() == short
                            dialog.get_by_role(
                                "button", name="Close", exact=True
                            ).click()
                            expect(expand).to_be_focused()
                            # Routine text stays reachable regardless of its length.
                            page.evaluate(LONG_STATUS)
                            expect(feedback).to_have_text(original)
                            expect(announcement).to_have_text(original)
                            expect(expand).to_be_visible()
                            expand.click()
                            page.evaluate(
                                "window.feedbackTest.feedback.textContent = ''"
                            )
                            expect(message).to_have_text(original)
                            dialog.get_by_role(
                                "button", name="Close", exact=True
                            ).click()
                            expect(component.get_by_role(
                                "button", name="Fictional focus return", exact=True
                            )).to_be_focused()
                            expect(feedback).to_have_text("")
                            expect(announcement).to_have_text("")
                            expect(expand).to_be_hidden()
                            page.evaluate(
                                "window.feedbackTest.feedback.textContent = "
                                "'Fictional '.repeat(40)"
                            )
                            expect(expand).to_be_visible()
                            expect(feedback).to_have_text("Fictional " * 40)
                            expect(announcement).to_have_text("Fictional " * 40)
                            page.set_viewport_size({"width": 1440, "height": 1000})
                            expect(expand).to_be_visible()
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
                            isolated.update(
                                passed=True,
                                original_message=original,
                                snapshot_preserved=True,
                                short_message=short,
                                exact_announcement=True,
                                focus_return=True,
                            )
                        except Exception as problem:
                            isolated["failure"] = (
                                type(problem).__name__ + ": " + str(problem)
                            )
                            if page:
                                try:
                                    page.screenshot(path=str(
                                        artifacts / "isolated-component-FAILED.png"
                                    ))
                                except Exception as capture_problem:
                                    isolated["capture_failure"] = (
                                        type(capture_problem).__name__
                                        + ": " + str(capture_problem)
                                    )
                            raise
                        finally:
                            close_context(context)
                            isolated["context_closed"] = True
                    finally:
                        # Record each successful explicit close even when an
                        # assertion/setup failed before its ordinary finally block.
                        for owned in contexts:
                            if not owned["closed"]:
                                try:
                                    close_context(owned["context"])
                                except Exception as problem:
                                    errors.append(
                                        "Context cleanup: "
                                        + type(problem).__name__ + ": " + str(problem)
                                    )
                        closed["contexts"] = bool(contexts) and all(
                            owned["closed"] for owned in contexts
                        )
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
