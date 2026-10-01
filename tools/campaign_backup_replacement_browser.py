"""Fictional actual-interface backup replacement and clipboard recovery checks.

Runs only a temporary local workspace. It does not contact model providers or
inspect personal campaigns. Receipts distinguish captured bytes from saved work.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

PATHS = (
    "src/sinter/web/local-backup.js",
    "src/sinter/web/campaign-backup.js",
    "src/sinter/web/campaigns.js",
    "src/sinter/web/app.js",
    "src/sinter/web/api.js",
    "src/sinter/web/ui.js",
    "src/sinter/web/dom.js",
    "src/sinter/runtime_routes.py",
    "src/sinter/runtime.py",
    "src/sinter/campaigns.py",
    "src/sinter/web/campaigns.css",
)


def fiction(label):
    return {
        "schema": "sinter-campaign/v1",
        "title": f"Fictional garden {label}",
        "organisation": "Fictional volunteer group",
        "objective": "No dates agreed.",
        "sources": [
            {
                "title": "Exact original <🐝>",
                "url": "",
                "notes": "Original e\u0301 source\r\nunknown; not confirmed.",
            }
        ],
        "actions": [
            {"task": "Ask for a quote", "owner": "", "due": "", "status": "open"}
        ],
        "communications": [
            {
                "subject": "Not a sent message",
                "status": "draft",
                "content": "Original draft <literal> 🐝",
            }
        ],
    }


def flow(page, server, base, label, artifacts, expect):
    first = server.app.campaigns.save(fiction(label + " original"))
    page.goto(base + "/#campaigns")
    page.get_by_label("Campaign name", exact=True).wait_for(state="attached")
    expect(
        page.get_by_text("Most recently updated campaign opened.", exact=False)
    ).to_be_visible()
    page.get_by_role(
        "button",
        name=re.compile(
            r"^(?:Open|Continue) " + re.escape(first["document"]["title"]) + r"$"
        ),
    ).click()
    expect(page.get_by_label("Campaign name", exact=True)).to_have_value(
        first["document"]["title"]
    )
    panel = page.locator(".campaign-clipboard-backup")
    page.get_by_text("Import or back up a campaign", exact=True).click()
    text = panel.get_by_label("Campaign backup text", exact=True)
    refresh = panel.get_by_role("button", name="Refresh backup text", exact=True)
    copy = panel.get_by_role("button", name="Copy backup text", exact=True)
    timings = []

    def capture():
        refresh.click()
        expect(text).to_be_visible()
        return json.loads(text.input_value())

    def cleared(action, title):
        started = time.perf_counter()
        action()
        expect(page.get_by_label("Campaign name", exact=True)).to_have_value(title)
        # The hidden stale capture must be empty, and old success wording gone.
        expect(text).to_have_value("")
        expect(text).to_be_hidden()
        expect(panel).to_contain_text("Earlier backup text cleared")
        expect(panel).not_to_contain_text("refreshed from your current inputs")
        timings.append(round((time.perf_counter() - started) * 1000, 3))

    assert capture() == first["document"]
    cleared(
        lambda: page.get_by_role(
            "button", name="Start a new campaign", exact=True
        ).click(),
        "",
    )
    second_title = f"Fictional new feedback {label}"
    page.get_by_label("Campaign name", exact=True).fill(second_title)
    page.get_by_role("button", name="Save campaign", exact=True).click()
    expect(
        page.get_by_text(
            "Campaign saved. Answers, costs, checks and actions "
            "will be here when you return.",
            exact=True,
        )
    ).to_be_visible()
    second = next(
        row for row in server.app.campaigns.list() if row["title"] == second_title
    )
    assert second["revision"] == 1
    assert server.app.campaigns.get(first["id"]) == first
    assert text.input_value() == ""
    assert capture()["title"] == second_title
    cleared(
        lambda: page.get_by_role(
            "button", name="Open " + first["document"]["title"], exact=True
        ).click(),
        first["document"]["title"],
    )
    assert capture() == first["document"]
    cleared(
        lambda: page.get_by_role(
            "button", name="Continue " + first["document"]["title"], exact=True
        ).click(),
        first["document"]["title"],
    )
    assert capture() == first["document"]

    imported = fiction(label + " imported unsaved")
    cleared(
        lambda: page.get_by_label("Import campaign backup", exact=True).set_input_files(
            {
                "name": "fictional-backup.json",
                "mimeType": "application/json",
                "buffer": json.dumps(imported).encode(),
            }
        ),
        imported["title"],
    )
    imported_capture = capture()
    assert imported_capture["sources"][0]["notes"] == imported["sources"][0]["notes"]
    assert (
        imported_capture["communications"][0]["content"]
        == imported["communications"][0]["content"]
    )
    # Invalid import never replaces local inputs or the existing valid capture.
    before = text.input_value()
    page.get_by_label("Import campaign backup", exact=True).set_input_files(
        {"name": "broken.json", "mimeType": "application/json", "buffer": b"not JSON"}
    )
    expect(page.get_by_role("alert")).to_be_visible()
    assert text.input_value() == before
    expect(page.get_by_label("Campaign name", exact=True)).to_have_value(
        imported["title"]
    )

    # A deliberately stalled browser clipboard is an environmental fixture. All
    # capture/replacement/refresh operations remain actual accessible UI actions.
    for completion in ["resolve", "reject"]:
        page.evaluate("""() => {
          window.backupWrites = [];
          Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{
            writeText:text => {
              window.backupWrites.push(text); return new Promise((ok,no) => {
              window.finishBackup = ok; window.failBackup = no;
            }); }
          }});
        }""")
        copy.click()
        expect(copy).to_be_disabled()
        cleared(
            lambda: page.get_by_role(
                "button", name="Start a new campaign", exact=True
            ).click(),
            "",
        )
        page.get_by_label("Campaign name", exact=True).fill(
            f"Fictional {completion} new {label}"
        )
        refreshed = capture()
        assert refreshed["title"] == f"Fictional {completion} new {label}"
        feedback = panel.inner_text()
        focused = page.evaluate("document.activeElement.id")
        page.evaluate(
            "kind => kind==='resolve' ? window.finishBackup() : "
            "window.failBackup(new Error('Denied old capture'))",
            completion,
        )
        expect(copy).to_be_enabled()
        assert panel.inner_text() == feedback
        assert page.evaluate("document.activeElement.id") == focused
        assert len(page.evaluate("window.backupWrites")) == 1
        assert (
            json.loads(page.evaluate("window.backupWrites[0]"))["title"]
            != refreshed["title"]
        )
        assert json.loads(text.input_value()) == refreshed
    assert server.app.campaigns.get(first["id"]) == first
    assert server.app.campaigns.get(second["id"])["revision"] == 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(
        path=str(artifacts / (label + "-current-recovery.png")),
        full_page=True,
        animations="disabled",
    )
    return {
        "passed": True,
        "viewport": label,
        "replacement_to_assertion_ms": timings,
        "start_save_open_same_id_import_recovery": True,
        "invalid_import_retains_capture": True,
        "pending_resolve_and_reject_suppressed_after_replacement": True,
        "original_saved_campaign_and_second_revision_preserved": True,
    }


def held_transition_flow(page, server, base, label, artifacts, expect):
    """Hold real local requests; only declared failure responses are synthetic."""
    first = server.app.campaigns.save(fiction(label + " held source"))
    other = server.app.campaigns.save(fiction(label + " held destination"))
    page.reload()
    expect(
        page.get_by_text("Most recently updated campaign opened.", exact=False)
    ).to_be_visible()
    name = page.get_by_label("Campaign name", exact=True)
    new = page.get_by_role("button", name="Start a new campaign", exact=True)
    panel = page.locator(".campaign-clipboard-backup")
    page.get_by_text("Import or back up a campaign", exact=True).click()
    text = panel.get_by_label("Campaign backup text", exact=True)
    refresh = panel.get_by_role("button", name="Refresh backup text", exact=True)
    rows = []

    def open_first():
        page.get_by_role(
            "button",
            name=re.compile(
                r"^(?:Open|Continue) " + re.escape(first["document"]["title"]) + r"$"
            ),
        ).click()
        expect(name).to_have_value(first["document"]["title"])
        expect(new).to_be_enabled()

    for operation in ["open", "save", "import"]:
        for outcome in ["success", "failure"]:
            open_first()
            current = server.app.campaigns.get(first["id"])
            if operation == "save":
                if not name.is_visible():
                    page.get_by_text("Campaign details", exact=True).click()
                page.get_by_label("Applicant organisation", exact=True).fill(
                    f"Fictional retained edit {label} {outcome}"
                )
            refresh.click()
            before_capture = text.input_value()
            before_title = name.input_value()
            held = []
            endpoint = (
                "/api/campaigns/" + other["id"]
                if operation == "open"
                else "/api/campaigns/save"
                if operation == "save"
                else "/api/campaigns/prepare"
            )
            target = base + endpoint
            page.route(target, lambda route: held.append(route))
            started = time.perf_counter()
            with page.expect_request(lambda request: request.url == target):
                if operation == "open":
                    page.get_by_role(
                        "button", name="Open " + other["document"]["title"], exact=True
                    ).click()
                elif operation == "save":
                    page.get_by_role("button", name="Save campaign", exact=True).click()
                else:
                    candidate = fiction(label + " held import")
                    page.get_by_label(
                        "Import campaign backup", exact=True
                    ).set_input_files(
                        {
                            "name": "fictional-held.json",
                            "mimeType": "application/json",
                            "buffer": json.dumps(candidate).encode(),
                        }
                    )
            expect(new).to_be_disabled()
            # The visible native disabled state protects human pointer/keyboard
            # use. Deliberate synthetic dispatch also challenges the busy guard.
            new.dispatch_event("click")
            assert name.input_value() == before_title
            assert text.input_value() == before_capture
            assert len(held) == 1, "No transition request may be replayed."
            held_ms = round((time.perf_counter() - started) * 1000, 3)
            if operation == "open" and outcome == "success":
                page.screenshot(
                    path=str(artifacts / (label + "-new-disabled-during-open.png")),
                    animations="disabled",
                )
            if outcome == "success":
                held[0].continue_()
                expected_title = (
                    other["document"]["title"]
                    if operation == "open"
                    else candidate["title"]
                    if operation == "import"
                    else before_title
                )
                expect(name).to_have_value(expected_title)
                if operation == "save":
                    expect(
                        page.get_by_text(
                            "Campaign saved. Answers, costs, checks and actions "
                            "will be here when you return.",
                            exact=True,
                        )
                    ).to_be_visible()
                    assert (
                        server.app.campaigns.get(first["id"])["revision"]
                        == current["revision"] + 1
                    )
                    assert text.input_value() == before_capture
                else:
                    expect(text).to_have_value("")
                    expect(text).to_be_hidden()
            else:
                held[0].fulfill(
                    status=503,
                    content_type="application/json",
                    body=json.dumps({"error": "Fictional unavailable local service"}),
                )
                expect(page.get_by_role("alert")).to_contain_text(
                    "Fictional unavailable local service"
                )
                assert name.input_value() == before_title
                assert text.input_value() == before_capture
                assert server.app.campaigns.get(first["id"]) == current
            expect(new).to_be_enabled()
            page.unroute(target)
            assert server.app.campaigns.get(other["id"]) == other
            # A fresh, explicit choice after completion is allowed and cannot
            # later be overwritten by the completed request.
            new.click()
            expect(name).to_have_value("")
            expect(text).to_have_value("")
            expect(text).to_be_hidden()
            assert len(held) == 1
            rows.append(
                {
                    "operation": operation,
                    "outcome": outcome,
                    "new_disabled_and_callback_refused": True,
                    "new_restored_and_explicit_blank_retained": True,
                    "no_request_cancellation_or_replay": True,
                    "held_to_assertion_ms": held_ms,
                    "synthetic_unavailable_response": outcome == "failure",
                }
            )
    return {
        "passed": True,
        "viewport": label,
        "held_transitions": rows,
        "saved_destination_unchanged": True,
    }


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(
        tempfile.mkdtemp(prefix="sinter-private-backup-replacement-proof-")
    )
    artifacts.chmod(0o700)
    hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in PATHS
    }
    checks, errors, external = [], [], []
    resources = {"browser_closed": False, "server_closed": False}
    with (
        tempfile.TemporaryDirectory(prefix="sinter-private-backup-data-") as data,
        patch.object(
            client, "_open", side_effect=AssertionError("No hosted calls")
        ) as remote,
        patch.object(
            client, "chat", side_effect=AssertionError("No model calls")
        ) as model,
    ):
        server = make_server(port=0, directory=data)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as driver:
                browser = launch_chromium(driver, args.chromium)
                try:
                    for width, height in [(1440, 1000), (390, 844)]:
                        label = f"{width}x{height}"
                        context = browser.new_context(
                            viewport={"width": width, "height": height},
                            reduced_motion="reduce",
                        )
                        context.route(
                            "**/*",
                            lambda route: (
                                route.continue_()
                                if route.request.url.startswith(base + "/")
                                else (external.append(route.request.url), route.abort())
                            ),
                        )
                        page = context.new_page()
                        page.set_default_timeout(10000)
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on("dialog", lambda dialog: dialog.accept())
                        try:
                            checks.append(
                                flow(page, server, base, label, artifacts, expect)
                            )
                            checks.append(
                                held_transition_flow(
                                    page, server, base, label, artifacts, expect
                                )
                            )
                        except Exception as error:
                            checks.append(
                                {
                                    "passed": False,
                                    "viewport": label,
                                    "error": str(error),
                                    "traceback": traceback.format_exc(),
                                }
                            )
                            page.screenshot(
                                path=str(artifacts / (label + "-FAILED.png"))
                            )
                        finally:
                            context.close()
                finally:
                    browser.close()
                    resources["browser_closed"] = True
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
            resources["server_closed"] = not thread.is_alive()
        remote.assert_not_called()
        model.assert_not_called()
    unchanged = hashes == {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in PATHS
    }
    receipt = {
        "schema": "sinter-private-backup-replacement-proof/v2",
        "source_root": str(ROOT),
        "source_sha256": hashes,
        "source_unchanged": unchanged,
        "checks": checks,
        "errors": errors,
        "external": external,
        "hosted_model_calls": 0,
        "real_workspace_mutations": 0,
        "resources": resources,
        "passed": all(row["passed"] for row in checks)
        and unchanged
        and not errors
        and not external
        and all(resources.values()),
    }
    target = artifacts / "backup-replacement-receipt.json"
    target.write_text(json.dumps(receipt, indent=2) + "\n")
    for path in artifacts.iterdir():
        path.chmod(0o600)
    print(target)
    print(json.dumps(checks))
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect retained private backup replacement evidence.")


if __name__ == "__main__":
    main()
