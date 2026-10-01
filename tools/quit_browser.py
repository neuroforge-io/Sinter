"""Fictional in-page Quit decisions, narrow-screen access and lost-reply recovery."""

from __future__ import annotations

import hashlib
import json
import socket
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.native_browser import NativeBrowserWorkbench  # noqa: E402
from sinter.runtime import Runtime  # noqa: E402
from sinter.server import LocalServer  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

PATHS = (
    "src/sinter/web/app.js",
    "src/sinter/web/workspace.css",
    "src/sinter/web/confirm-action.js",
    "src/sinter/web/api.js",
    "src/sinter/web/report-drafts.js",
    "src/sinter/web/library.js",
    "src/sinter/web/navigation.js",
    "src/sinter/web/draft-state.js",
    "src/sinter/web/casebooks.js",
    "src/sinter/web/garden-practice.js",
    "src/sinter/native_browser.py",
    "src/sinter/runtime_routes.py",
    "tools/quit_browser.py",
)


def unload_guarded(page):
    """Inspect the listener policy without opening a browser-native dialog."""
    return page.evaluate("""() => {
      const event = new Event('beforeunload', {cancelable: true});
      window.dispatchEvent(event); return event.defaultPrevented;
    }""")


def wait_local(page, predicate):
    """Bounded CDP reads avoid wait_for_function's CSP-sensitive eval polling."""
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if page.evaluate(predicate):
            return
        page.wait_for_timeout(25)
    raise AssertionError("The controlled local browser condition did not finish.")


def late_quit_route(page, *, outcome, label, artifacts, expect, row):
    """Public UI race in an owned fictional standalone session.

    An installed runner can reuse this browser step, but must independently bind
    its actual source/asset and verify process exit, workspace and cleanup. This
    helper observes the quit acknowledgement, never installed shutdown itself.
    """
    if outcome not in {"success", "error"}:
        raise ValueError("Choose a successful or failed delayed local response.")
    quit_button = page.get_by_role("button", name="Quit Sinter", exact=True)
    expect(quit_button).to_be_visible()
    page.get_by_role("button", name="Open garden handover", exact=True).click()
    page.get_by_label("Project name", exact=True).fill(
        "Fictional unsaved café 🐝 e\u0301 " + label
    )
    page.evaluate("""outcome => {
      const state = {originalFetch: window.fetch, captured: false};
      window.sinterQuitRace = state;
      window.fetch = async (...args) => {
        const response = await state.originalFetch.apply(window, args);
        if (args[0] !== '/api/reports' || state.captured) return response;
        state.body = await response.clone().text();
        state.status = response.status; state.captured = true;
        const originalJSON = response.json.bind(response);
        response.json = async () => {
          const result = await originalJSON(); state.consumed = true; return result;
        };
        return new Promise((resolve, reject) => {
          state.release = () => {
            if (state.released) throw new Error('The controlled reply was already released.');
            state.released = true;
            if (outcome === 'success') resolve(response);
            else {
              state.consumed = true;
              reject(new TypeError('Fictional delayed local read reply lost.'));
            }
          };
        });
      };
    }""", outcome)
    try:
        page.keyboard.press("Control+k")
        finder = page.get_by_role("dialog", name="What would you like to do?", exact=True)
        expect(finder).to_be_visible()
        finder.locator(".finder-result").filter(has_text="My workspace").click()
        wait_local(page, "() => Boolean(window.sinterQuitRace?.captured)")
        captured = page.evaluate("""() => ({
          body: window.sinterQuitRace.body, status: window.sinterQuitRace.status
        })""")
        listing = json.loads(captured["body"])
        assert captured["status"] == 200
        assert set(listing) == {"reports"} and isinstance(listing["reports"], list)
        response_bytes = captured["body"].encode("utf-8")
        response_path = artifacts / f"{label}-reports.json"
        response_path.write_bytes(response_bytes)
        row["route_response"] = {
            "path": "/api/reports", "status": captured["status"],
            "bytes": len(response_bytes),
            "sha256": hashlib.sha256(response_bytes).hexdigest(),
            "report_count": len(listing["reports"]), "outcome": outcome,
        }
        row["checks"].append("Actual reports JSON is retained before the controlled route delay")
        quit_button.click()
        decision = page.get_by_role("dialog", name="Quit Sinter?", exact=True)
        expect(decision).to_be_visible()
        assert unload_guarded(page)
        decision.get_by_role("button", name="Quit Sinter", exact=True).click()
        stopped = page.get_by_text("Sinter has stopped. You can close this window.", exact=True)
        expect(stopped).to_be_visible()
        assert not unload_guarded(page)
        row["checks"].append("Confirmed stop releases the unload guard before a pending route finishes")
        page.evaluate("window.sinterQuitRace.release()")
        wait_local(page, "() => Boolean(window.sinterQuitRace?.consumed)")
        page.evaluate("""async () => {
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        }""")
        expect(stopped).to_be_visible()
        assert not unload_guarded(page)
        expect(quit_button).to_be_disabled()
        expect(page.locator("#theme-toggle")).to_be_disabled()
        expect(page.locator("#tool-finder-button")).to_be_disabled()
        row["checks"].append(f"Late route {outcome} cannot replace the stopped view or restore its unload guard")
        row["route_consumed"] = page.evaluate("window.sinterQuitRace.consumed === true")
        page.screenshot(path=str(artifacts / f"{label}-stopped.png"))
    finally:
        page.evaluate("""() => {
          if (window.sinterQuitRace) window.fetch = window.sinterQuitRace.originalFetch;
        }""")


def late_route_journey(browser, *, width, height, outcome, artifacts, rows,
                       resources, external, errors, chrome_dialogs, expect):
    """Own the disposable source fixture; no installed/process-exit claim."""
    label = f"standalone-late-{outcome}-{width}"
    row = {"mode": label, "passed": False, "checks": []}
    rows.append(row)
    with tempfile.TemporaryDirectory(prefix="sinter-quit-race-data-") as data, Runtime(data) as runtime:
        calls = []
        runtime.app.desktop_shutdown = lambda: calls.append("quit")
        server = LocalServer(("127.0.0.1", 0), runtime.app)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        cleanup = {"mode": label, "server_closed": False, "context_closed": False}
        resources.append(cleanup)
        context = browser.new_context(viewport={"width": width, "height": height},
                                      reduced_motion="reduce", service_workers="block")
        context.route("**/*", lambda route: (
            route.continue_() if route.request.url.startswith(base + "/")
            else (external.append(route.request.url), route.abort())
        ))
        context.route_web_socket("**/*", lambda route: (external.append("websocket"), route.close()))
        try:
            page = context.new_page()
            page.set_default_timeout(8000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("dialog", lambda item: (chrome_dialogs.append(item.type), item.dismiss()))
            posts = []
            page.on("request", lambda item: (
                posts.append(item.url) if item.method == "POST" and item.url.endswith("/api/desktop/quit") else None
            ))
            page.goto(base)
            page.wait_for_load_state("networkidle")
            before = {"casebooks": runtime.app.casebooks.list(), "reports": runtime.app.store.reports(),
                      "preferences": runtime.app.preferences.path.read_bytes() if runtime.app.preferences.path.exists() else None}
            late_quit_route(page, outcome=outcome, label=label, artifacts=artifacts, expect=expect, row=row)
            deadline = time.monotonic() + 8
            while not calls and time.monotonic() < deadline:
                page.wait_for_timeout(25)
            assert calls == ["quit"] and len(posts) == 1
            assert before == {"casebooks": runtime.app.casebooks.list(), "reports": runtime.app.store.reports(),
                              "preferences": runtime.app.preferences.path.read_bytes() if runtime.app.preferences.path.exists() else None}
            row["quit_callback_count"] = len(calls)
            row["quit_posts"] = len(posts)
            row["workspace_conserved"] = True
            assert not external and not errors and not chrome_dialogs
            row["passed"] = True
        finally:
            try:
                context.close(); cleanup["context_closed"] = True
            finally:
                server.shutdown(); server.server_close(); worker.join(timeout=3)
                assert not worker.is_alive()
                with socket.socket() as probe:
                    probe.settimeout(1)
                    assert probe.connect_ex(("127.0.0.1", server.server_port)) != 0
                cleanup["server_closed"] = True


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-quit-proof-"))
    artifacts.chmod(0o700)
    source_hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PATHS
    }
    rows, external, errors, chrome_dialogs, provider = [], [], [], [], []
    resources = []
    failure = None
    started = time.monotonic()

    def refused(*_, **__):
        provider.append("refused")
        raise AssertionError("This fictional journey permits no provider call.")

    try:
        with patch.object(client, "_open", refused), sync_playwright() as driver:
            browser = launch_chromium(driver, args.chromium)
            try:
                for owner in (False, True):
                    for width, height in ((1440, 1000), (390, 844)):
                        label = f"{'native-owned' if owner else 'standalone'}-{width}"
                        row = {"mode": label, "passed": False, "checks": []}
                        rows.append(row)
                        with tempfile.TemporaryDirectory(prefix="sinter-quit-data-") as data:
                            with Runtime(data) as runtime:
                                calls = []
                                if owner:
                                    workbench = NativeBrowserWorkbench(runtime.app)
                                    server, worker = workbench.server, workbench.thread
                                else:
                                    workbench = None
                                    runtime.app.desktop_shutdown = lambda: calls.append("quit")
                                    server = LocalServer(("127.0.0.1", 0), runtime.app)
                                    worker = threading.Thread(target=server.serve_forever, daemon=True)
                                    worker.start()
                                base = f"http://127.0.0.1:{server.server_port}"
                                cleanup = {"mode": label, "server_closed": False, "context_closed": False}
                                resources.append(cleanup)
                                context = browser.new_context(
                                    viewport={"width": width, "height": height},
                                    reduced_motion="reduce", service_workers="block",
                                )
                                context.route("**/*", lambda route: (
                                    route.continue_() if route.request.url.startswith(base + "/")
                                    else (external.append(route.request.url), route.abort())
                                ))
                                context.route_web_socket("**/*", lambda route: (
                                    external.append("websocket"), route.close()
                                ))
                                try:
                                    page = context.new_page()
                                    page.set_default_timeout(8000)
                                    page.on("pageerror", lambda error: errors.append(str(error)))
                                    page.on("dialog", lambda item: (
                                        chrome_dialogs.append(item.type), item.dismiss()
                                    ))
                                    posts = []
                                    page.on("request", lambda item: (
                                        posts.append(item.url) if item.method == "POST" and
                                        item.url.endswith("/api/desktop/quit") else None
                                    ))
                                    page.goto(base)
                                    quit_button = page.get_by_role("button", name="Quit Sinter", exact=True)
                                    expect(quit_button).to_be_visible()
                                    assert page.evaluate("document.documentElement.scrollWidth") == width
                                    row["checks"].append("Quit is visible without hidden navigation or horizontal overflow")
                                    page.get_by_role("button", name="Open garden handover", exact=True).click()
                                    title = page.get_by_label("Project name", exact=True)
                                    original = "Fictional unsaved café 🐝 e\u0301 " + label
                                    title.fill(original)

                                    def decision():
                                        quit_button.click()
                                        local = page.get_by_role("dialog", name="Quit Sinter?", exact=True)
                                        expect(local).to_be_visible()
                                        expect(local.get_by_role("button", name="Keep working", exact=True)).to_be_focused()
                                        expect(local).to_contain_text("Save or export")
                                        measured = page.evaluate("document.documentElement.scrollWidth")
                                        if measured != width:
                                            observation = page.evaluate("""limit => [...document.querySelectorAll('body *')]
                                              .map(el=>({tag:el.tagName,cls:el.className,
                                                left:el.getBoundingClientRect().left,
                                                right:el.getBoundingClientRect().right,
                                                width:el.getBoundingClientRect().width,
                                                scroll:el.scrollWidth,client:el.clientWidth,
                                                text:el.textContent.slice(0,80)}))
                                              .filter(row=>row.width>0 && (row.left<0 || row.right>limit+1 || row.scroll>row.client+1)).slice(-40)""", width)
                                            metadata = page.evaluate("""() => ({innerWidth, scrollX,
                                              client:document.documentElement.clientWidth,
                                              docScroll:document.documentElement.scrollWidth,
                                              bodyWidth:document.body.getBoundingClientRect().width,
                                              bodyScroll:document.body.scrollWidth})""")
                                            observation = {"metadata":metadata,"rows":observation}
                                            (artifacts / (label+'-overflow.json')).write_text(json.dumps(observation,indent=2))
                                            page.screenshot(path=str(artifacts / (label+'-overflow.png')))
                                        assert measured == width, (measured, width)
                                        bounds = local.bounding_box()
                                        assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1
                                        return local

                                    local = decision()
                                    accept_label = "Request quit" if owner else "Quit Sinter"
                                    page.keyboard.press("Shift+Tab")
                                    expect(local.get_by_role("button", name=accept_label, exact=True)).to_be_focused()
                                    page.keyboard.press("Tab")
                                    expect(local.get_by_role("button", name="Keep working", exact=True)).to_be_focused()
                                    page.keyboard.press("Control+k")
                                    expect(page.get_by_role("dialog", name="What would you like to do?", exact=True)).not_to_be_visible()
                                    local.get_by_role("button", name="Keep working", exact=True).click()
                                    expect(local).to_have_count(0)
                                    expect(quit_button).to_be_focused()
                                    assert title.input_value() == original and not posts
                                    assert runtime.app.casebooks.list() == []
                                    row["checks"].append("Cancel, focus containment and tool-finder guard preserve an unsaved Unicode project")
                                    local = decision()
                                    page.keyboard.press("Escape")
                                    expect(local).to_have_count(0)
                                    assert title.input_value() == original and not posts
                                    row["checks"].append("Escape preserves inputs without a quit request")

                                    page.get_by_role("button", name="Prepare source-only report", exact=True).click()
                                    report = page.get_by_role("region", name="Your draft report", exact=True)
                                    expect(report.get_by_role("tabpanel", name="Document", exact=True)).to_contain_text("Source-only handover checklist")
                                    report.get_by_text("More options", exact=True).click()
                                    report.get_by_role("button", name="Edit draft", exact=True).click()
                                    editor = report.get_by_label("Edit your draft", exact=True)
                                    pending = editor.input_value() + "\n\nFictional pending report only: approval remains unconfirmed. 🐝"
                                    editor.fill(pending)
                                    stored_before = runtime.app.casebooks.get(runtime.app.casebooks.list()[0]["id"])
                                    local = decision()
                                    local.get_by_role("button", name="Keep working", exact=True).click()
                                    assert editor.input_value() == pending and not posts
                                    assert runtime.app.store.reports() == []
                                    row["checks"].append("Report-only pending edits also require a cancellable choice")

                                    def lost_reply(route):
                                        reply = route.fetch()
                                        assert reply.status == 200
                                        route.abort("failed")

                                    pattern = "**/api/desktop/quit"
                                    page.route(pattern, lost_reply)
                                    local = decision()
                                    page.screenshot(path=str(artifacts / f"{label}-decision.png"))
                                    local.get_by_role("button", name=accept_label, exact=True).click()
                                    expect(page.get_by_role("alert")).to_contain_text("Quit was not confirmed.")
                                    assert len(posts) == 1 and editor.input_value() == pending
                                    assert page.evaluate("""() => {const event=new Event('beforeunload', {cancelable:true});
                                      window.dispatchEvent(event); return event.defaultPrevented;}""")
                                    assert title.input_value() == original
                                    assert runtime.app.casebooks.get(stored_before["id"]) == stored_before
                                    assert runtime.app.store.reports() == []
                                    page.wait_for_timeout(1200)
                                    assert len(posts) == 1
                                    if owner:
                                        assert workbench.quit_requested.is_set()
                                    else:
                                        assert calls == ["quit"]
                                    row["checks"].append("Actual accepted quit with a lost reply retains local work and never replays")
                                    page.unroute(pattern, lost_reply)
                                    local = decision()
                                    local.get_by_role("button", name=accept_label, exact=True).click()
                                    expect(local).to_have_count(0)
                                    assert len(posts) == 2
                                    if owner:
                                        expect(page.locator(".native-session").get_by_text("Quit requested. Check Sinter; inputs stay here.", exact=True)).to_be_visible()
                                        assert editor.input_value() == pending and title.input_value() == original
                                        workbench.set_quit_state("cancelled")
                                        expect(page.locator(".native-session").get_by_text("Quit cancelled. Both views stay open.", exact=True)).to_be_visible()
                                        assert editor.input_value() == pending
                                        row["checks"].append("Explicit native request and simulated native cancellation keep browser inputs; no actual Tk confirmation claim")
                                    else:
                                        expect(page.get_by_text("Sinter has stopped. You can close this window.", exact=True)).to_be_visible()
                                        expect(quit_button).to_be_disabled()
                                        assert calls == ["quit", "quit"]
                                        assert not page.evaluate("""() => {const event=new Event('beforeunload', {cancelable:true});
                                          window.dispatchEvent(event); return event.defaultPrevented;}""")
                                        row["checks"].append("Confirmed stopped state releases the unload guard; an uncertain request retains it")
                                        row["checks"].append("Only an explicit confirmed standalone retry clears browser drafts; callback is observed, real process exit is separate")
                                    assert runtime.app.casebooks.get(stored_before["id"]) == stored_before
                                    assert runtime.app.store.reports() == []
                                    assert not chrome_dialogs and not external and not errors and not provider
                                    page.screenshot(path=str(artifacts / f"{label}-result.png"))
                                    row["passed"] = True
                                finally:
                                    context.close(); cleanup["context_closed"] = True
                                    if workbench:
                                        workbench.close()
                                    else:
                                        server.shutdown(); server.server_close(); worker.join(timeout=3)
                                    assert not worker.is_alive()
                                    with socket.socket() as probe:
                                        probe.settimeout(1)
                                        assert probe.connect_ex(("127.0.0.1", server.server_port)) != 0
                                    cleanup["server_closed"] = True
                for outcome in ("success", "error"):
                    for width, height in ((1440, 1000), (390, 844)):
                        late_route_journey(browser, width=width, height=height, outcome=outcome,
                                           artifacts=artifacts, rows=rows, resources=resources,
                                           external=external, errors=errors, chrome_dialogs=chrome_dialogs,
                                           expect=expect)
            finally:
                browser.close()
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
        (artifacts / "failure.log").write_text(traceback.format_exc())
    receipt = {
        "schema": "sinter-source-quit-browser-proof/v1", "passed": failure is None,
        "source_hashes": source_hashes, "journeys": rows, "resources": resources,
        "checks_passed": sum(len(row["checks"]) for row in rows),
        "seconds": round(time.monotonic() - started, 3), "failure": failure,
        "native_browser_dialogs": chrome_dialogs, "external_requests": external,
        "page_errors": errors, "provider_calls": provider,
        "installed_pass": False, "physical_tk_confirmation": False,
    }
    (artifacts / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"passed": receipt["passed"], "checks": receipt["checks_passed"], "receipt": str(artifacts / "receipt.json")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
