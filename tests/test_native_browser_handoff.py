"""Fictional loopback and UI-state checks; no GUI/browser/provider is launched."""

from __future__ import annotations

import copy
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from sinter import client, native_browser
from sinter.native_window import NativeController, NativeWindow, NativeWindowError
from sinter.runtime import OperationError, Runtime

BOOK = {
    "title": "Fictional 🐝 <script>unsafe literal</script>",
    "questions": "Who approved the order?",
    "documents": [{"title": "Original note", "content": "No approval — é."}],
}


@pytest.fixture
def controller(tmp_path, monkeypatch):
    def no_provider(*_args, **_kwargs):
        pytest.fail("Opening a local workbench must not contact a provider")

    for name in ("_open", "chat", "search", "_load_key"):
        monkeypatch.setattr(client, name, no_provider)
    monkeypatch.setattr(native_browser.webbrowser, "open", lambda *_: False)
    runtime = Runtime(tmp_path / "different workspace 🐝")
    monkeypatch.setattr(runtime.app, "scheduler", no_provider)
    value = NativeController(runtime)
    yield value
    value.close()


def request(workbench, path="/api/session", *, body=None, headers=None):
    address = urlsplit(workbench.url)
    connection = HTTPConnection(address.hostname, address.port, timeout=3)
    values = {"X-Sinter-Token": workbench.app.token, "Content-Type": "application/json"}
    values.update(headers or {})
    try:
        connection.request(
            "GET" if body is None else "POST",
            path,
            body=None if body is None else json.dumps(body).encode(),
            headers=values,
        )
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_listener_shares_exact_application_and_never_runs_due_watches(controller):
    app = controller.runtime.app
    saved = app.campaigns.save({"title": "Fictional campaign"})
    app.store.add_watch("Fictional due watch", "Never send this query", 3600)
    before = copy.deepcopy(app.store.watches())
    with_workbench = native_browser.NativeBrowserWorkbench(app)
    try:
        assert with_workbench.server.app is app
        assert with_workbench.workspace == app.store.directory
        assert urlsplit(with_workbench.url).hostname == "127.0.0.1"
        assert str(app.store.directory) not in with_workbench.url
        assert app.token not in with_workbench.url
        status, content = request(with_workbench)
        session = json.loads(content)
        assert status == 200 and session["native_window_owner"] is True
        assert session["session_notice"] == native_browser.SESSION_NOTICE
        assert session["token"] == app.token
        assert "paused" in session["session_details"]
        assert session["session_details"] == native_browser.SESSION_DETAILS
        assert session["native_quit"]["state"] == "idle"
        assert request(with_workbench, "/api/campaigns/" + saved["id"])[0] == 200
        assert app.store.watches() == before
        assert not controller.closed
    finally:
        with_workbench.close()
    assert not with_workbench.thread.is_alive()
    assert app.desktop_shutdown is None
    assert not hasattr(app, "native_browser_owner")
    assert controller.runtime.call("campaigns.get", {"id": saved["id"]}) == saved


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Sinter-Token": "wrong"},
        {"Host": "evil.invalid"},
        {"Origin": "https://evil.invalid"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_handoff_preserves_existing_write_security(controller, headers):
    workbench = native_browser.NativeBrowserWorkbench(controller.runtime.app)
    try:
        status, _ = request(
            workbench,
            "/api/documents/docx/save",
            body={"title": "Fictional", "markdown": "# Never write"},
            headers=headers,
        )
        assert status == 403
        assert not (workbench.workspace / "exports").exists()
    finally:
        workbench.close()


@pytest.mark.parametrize("raises", [False, True])
def test_browser_refusal_retains_local_service_and_native_inputs(controller, raises):
    controller.edit_document(BOOK)
    original = copy.deepcopy(controller.document)
    workbench = native_browser.NativeBrowserWorkbench(controller.runtime.app)

    def opener(url):
        assert url == workbench.url
        if raises:
            raise OSError("Fictional browser policy refusal")
        return False

    try:
        assert workbench.open_browser(opener) is False
        assert request(workbench)[0] == 200
        assert controller.document == original and controller.dirty
    finally:
        workbench.close()


def test_failed_bind_does_not_change_application_owner_or_saved_data(controller):
    controller.edit_document(BOOK)
    saved = controller.save()

    def unavailable(*_):
        raise OSError("Fictional restricted listener")

    with pytest.raises(OSError, match="restricted listener"):
        native_browser.NativeBrowserWorkbench(
            controller.runtime.app, server_factory=unavailable
        )
    assert controller.runtime.app.desktop_shutdown is None
    assert not hasattr(controller.runtime.app, "native_browser_owner")
    assert controller.runtime.call("casebooks.get", {"id": saved["id"]}) == saved


def test_thread_start_failure_closes_listener_and_restores_owner(
    controller, monkeypatch
):
    from sinter.server import LocalServer

    servers = []

    def create_server(*args):
        server = LocalServer(*args)
        servers.append(server)
        return server

    def refuse_start(_thread):
        raise RuntimeError("Fictional thread resource refusal")

    monkeypatch.setattr(native_browser.threading.Thread, "start", refuse_start)
    with pytest.raises(RuntimeError, match="thread resource refusal"):
        native_browser.NativeBrowserWorkbench(
            controller.runtime.app, server_factory=create_server
        )
    assert servers[0].socket.fileno() == -1
    assert controller.runtime.app.desktop_shutdown is None
    assert not hasattr(controller.runtime.app, "native_browser_owner")
    assert not controller.closed


class Root:
    def __init__(self):
        self.destroyed = False
        self.timers = {}
        self.clipboard = None

    def destroy(self):
        self.destroyed = True

    def after(self, _delay, callback):
        key = str(len(self.timers) + 1)
        self.timers[key] = callback
        return key

    def after_idle(self, callback):
        return self.after("idle", callback)

    def after_cancel(self, key):
        self.timers.pop(key, None)

    def clipboard_clear(self):
        self.clipboard = ""

    def clipboard_append(self, value):
        self.clipboard += value


class Value:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


@pytest.fixture
def window(controller):
    value = NativeWindow.__new__(NativeWindow)
    value.root = Root()
    value.controller = controller
    value.closed = False
    value._poll_id = value._heartbeat_id = value._signal_close_id = None
    value._signal_close_pending = False
    value._browser_workbench = None
    value.active_job = None
    value.status_var = Value()
    value.browser_address = Value()
    value.browser_copy = SimpleNamespace(state=lambda *_: None)
    value._document_changed = lambda: None
    value._refresh = lambda: None
    value.save_project = controller.save
    value.answer = None
    value.close_answer = True
    value.errors = []
    value.messages = SimpleNamespace(
        askyesnocancel=lambda *_a, **_k: value.answer,
        askyesno=lambda *_a, **_k: value.close_answer,
        showerror=lambda *_a, **_k: value.errors.append(_a),
    )
    yield value
    workbench = value._browser_workbench
    if workbench is not None and not workbench.closed:
        workbench.close()
    value.close()


def finish_close(window, timeout=3):
    deadline = time.monotonic() + timeout
    while not window.closed and getattr(window, "_close_pending", False):
        assert time.monotonic() < deadline
        window._poll_workbench_close()
        time.sleep(0.01)


def test_cancel_handoff_changes_neither_saved_nor_unsaved_project(window):
    window.controller.edit_document(BOOK)
    original = copy.deepcopy(window.controller.document)
    window.answer = None
    window.open_workbench()
    assert window._browser_workbench is None
    assert window.controller.document == original and window.controller.dirty
    assert window.controller.runtime.call("casebooks.list") == {"casebooks": []}


@pytest.mark.parametrize("save_first", [False, True])
def test_save_or_keep_native_has_explicit_distinct_results(window, save_first):
    window.controller.edit_document(BOOK)
    saved = window.controller.save()
    window.controller.edit_document(
        {**window.controller.document, "title": "New literal 🐝"}
    )
    window.controller.variables = {
        "source_title": "Original",
        "excerpt": "No approval",
        "question": "Unknown?",
    }
    original = copy.deepcopy(window.controller.document)
    variables = copy.deepcopy(window.controller.variables)
    window.answer = save_first
    window.open_workbench()
    workbench = window._browser_workbench
    assert workbench is not None and window.browser_address.value == workbench.url
    assert window.controller.document["title"] == original["title"]
    assert window.controller.variables == variables
    status, content = request(workbench, "/api/casebooks/" + saved["id"])
    stored = json.loads(content)
    assert status == 200
    assert stored["document"]["title"] == (
        "New literal 🐝" if save_first else saved["document"]["title"]
    )
    assert stored["revision"] == (2 if save_first else 1)
    assert window.controller.dirty is not save_first
    window.copy_workbench_address()
    assert window.root.clipboard == workbench.url


def test_active_task_refuses_without_creating_or_saving_anything(window):
    window.controller.edit_document(BOOK)
    window.active_job = "fictional still-active task"
    with pytest.raises(ValueError, match="Finish or stop"):
        window.open_workbench()
    assert window._browser_workbench is None and window.controller.dirty


def test_save_conflict_keeps_edits_and_does_not_start_the_browser(window):
    window.controller.edit_document(BOOK)
    saved = window.controller.save()
    app = window.controller.runtime.app
    app.casebooks.save(
        {**saved["document"], "title": "Another explicit window's newer save"},
        saved["id"],
        saved["revision"],
    )
    window.controller.edit_document(
        {**window.controller.document, "title": "Native unsaved exact 🐝"}
    )
    original = copy.deepcopy(window.controller.document)
    window.answer = True
    with pytest.raises(OperationError, match="changed"):
        window.open_workbench()
    assert window.controller.document == original and window.controller.dirty
    assert window._browser_workbench is None
    assert app.desktop_shutdown is None


def test_reopening_reuses_one_listener_and_preserves_the_native_report(window):
    report = {"schema": "fictional-incomplete-local-result", "raw": "Keep — 🐝"}
    window.controller.result = report
    window.open_workbench()
    workbench = window._browser_workbench
    window.open_workbench()
    assert window._browser_workbench is workbench
    assert window.controller.result is report
    assert not workbench.quit_requested.is_set()


def test_browser_quit_is_deferred_and_cancel_keeps_both_views_usable(window):
    window.controller.edit_document(BOOK)
    window.answer = False
    window.open_workbench()
    workbench = window._browser_workbench
    assert request(workbench, "/api/desktop/quit", body={})[0] == 200
    assert workbench.quit_requested.wait(1)
    assert not window.closed  # HTTP worker cannot touch Tk or close its runtime.
    window.answer = None
    window._poll_browser_quit()
    assert not window.closed and not workbench.quit_requested.is_set()
    assert request(workbench)[0] == 200 and window.controller.dirty


def test_native_close_confirmation_then_stops_listener_before_owned_runtime(window):
    window.open_workbench()
    workbench = window._browser_workbench
    window.close_answer = False
    window.request_close()
    assert not window.closed and request(workbench)[0] == 200
    old_close = window.controller.close

    def close_runtime():
        assert workbench.closed and not workbench.thread.is_alive()
        old_close()

    window.controller.close = close_runtime
    window.close_answer = True
    window.request_close()
    finish_close(window)
    assert window.closed and window.root.destroyed and window.controller.closed


def test_signal_shutdown_keeps_existing_safe_idle_boundary_and_stops_browser(window):
    window.open_workbench()
    workbench = window._browser_workbench
    before = signal.getsignal(signal.SIGTERM)

    def mainloop():
        handler = signal.getsignal(signal.SIGTERM)
        handler(signal.SIGTERM, None)
        handler(signal.SIGTERM, None)
        assert not window.closed and not workbench.closed
        window.root.timers.pop(window._signal_close_id)()
        finish_close(window)

    window.root.mainloop = mainloop
    assert window.run() == 0
    assert workbench.closed and not workbench.thread.is_alive()
    assert signal.getsignal(signal.SIGTERM) == before


def pending_save(window):
    """Pause a valid admitted save at the store boundary, without invalid input."""
    app = window.controller.runtime.app
    saved = app.campaigns.save(
        {"title": "Original campaign", "objective": "No approval."}
    )
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    actual = app.campaigns.save
    outcome = {}

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return actual(*args, **kwargs)

    app.campaigns.save = delayed

    def perform():
        try:
            outcome["response"] = request(
                window._browser_workbench,
                "/api/campaigns/save",
                body={
                    "document": {**saved["document"], "title": "Explicit pending save"},
                    "id": saved["id"],
                    "revision": saved["revision"],
                },
            )
        finally:
            done.set()

    worker = threading.Thread(target=perform)
    worker.start()
    assert entered.wait(2)
    return saved, entered, release, done, worker, outcome, actual


def test_native_close_waits_for_valid_admitted_save_before_runtime_close(window):
    window.open_workbench()
    saved, _, release, done, worker, outcome, actual = pending_save(window)
    workbench = window._browser_workbench
    try:
        window.close()
        assert not window.closed and not window.controller.runtime._closed
        assert window._close_pending and workbench.server.active_requests == 1
        assert not done.is_set()
        # GUI polling returns immediately while the real handler is paused.
        start = time.monotonic()
        window._poll_workbench_close()
        assert time.monotonic() - start < 0.2
        assert not window.closed
        release.set()
        assert done.wait(2)
        worker.join()
        assert outcome["response"][0] == 200
        assert workbench.app.campaigns.get(saved["id"])["revision"] == 2
        finish_close(window)
        assert window.closed and window.controller.runtime._closed
        assert workbench.closed and not workbench.thread.is_alive()
    finally:
        release.set()
        worker.join(3)
        workbench.app.campaigns.save = actual


def test_bounded_timeout_retains_runtime_and_inputs_then_explicit_retry(window):
    window.controller.edit_document(BOOK)
    window.answer = False
    window.open_workbench()
    original = copy.deepcopy(window.controller.document)
    saved, _, release, done, worker, _, actual = pending_save(window)
    workbench = window._browser_workbench
    try:
        window.close()
        workbench._deadline = time.monotonic() - 1
        window._poll_workbench_close()
        assert not window.closed and not window.controller.runtime._closed
        assert not window._close_pending and workbench.phase == "refused"
        assert window.controller.document == original and window.controller.dirty
        assert request(workbench)[0] == 200
        assert workbench.session_state()["state"] == "refused"
        release.set()
        assert done.wait(2)
        worker.join()
        assert workbench.app.campaigns.get(saved["id"])["revision"] == 2
        window.close()
        finish_close(window)
        assert window.closed
    finally:
        release.set()
        worker.join(3)
        workbench.app.campaigns.save = actual


def test_keep_window_open_cancels_drain_without_replaying_save(window):
    window.open_workbench()
    saved, _, release, done, worker, _, actual = pending_save(window)
    workbench = window._browser_workbench
    try:
        window.close()
        window.cancel_workbench_close()
        assert not window._close_pending and not window.closed
        assert request(workbench)[0] == 200
        assert workbench.session_state()["state"] == "cancelled"
        release.set()
        assert done.wait(2)
        worker.join()
        assert workbench.app.campaigns.get(saved["id"])["revision"] == 2
    finally:
        release.set()
        worker.join(3)
        workbench.app.campaigns.save = actual


def test_native_edits_during_wait_keep_window_open_after_listener_stops(window):
    window.open_workbench()
    _, _, release, done, worker, _, actual = pending_save(window)
    workbench = window._browser_workbench
    try:
        window.close()
        window.controller.edit_document(BOOK)
        release.set()
        assert done.wait(2)
        worker.join()
        finish_close(window)
        assert workbench.closed and not window.closed
        assert not window.controller.runtime._closed
        assert window.controller.document == BOOK and window.controller.dirty
    finally:
        release.set()
        worker.join(3)
        workbench.app.campaigns.save = actual


def test_shutdown_failure_retains_owner_and_runtime_and_retries(window):
    window.open_workbench()
    workbench = window._browser_workbench
    actual = workbench.server.shutdown
    calls = []

    def once():
        calls.append(True)
        if len(calls) == 1:
            raise OSError("Fictional one-time shutdown failure")
        return actual()

    workbench.server.shutdown = once
    try:
        window.close()
        finish_close(window)
        assert not window.closed and not window.controller.runtime._closed
        assert workbench.phase == "failed" and not workbench.closed
        assert workbench.app.desktop_shutdown is workbench._quit_callback
        window.close()
        finish_close(window)
        assert window.closed and workbench.closed
        assert not workbench.thread.is_alive() and len(calls) == 2
    finally:
        workbench.server.shutdown = actual
        if not workbench.closed:
            workbench.close()


def test_new_dispatch_is_refused_atomically_while_quiesced(window):
    window.open_workbench()
    workbench = window._browser_workbench
    workbench.server.quiesce()
    before = workbench.app.campaigns.list()
    try:
        with pytest.raises((OSError, HTTPException)):
            request(
                workbench,
                "/api/campaigns/save",
                body={"document": {"title": "Refused"}},
            )
        assert workbench.server.active_requests == 0
        assert workbench.app.campaigns.list() == before
    finally:
        workbench.server.resume()


def test_dispatch_failure_balances_owned_count_and_existing_semaphore(
    controller, monkeypatch
):
    workbench = native_browser.NativeBrowserWorkbench(controller.runtime.app)
    from http.server import ThreadingHTTPServer

    sock = SimpleNamespace(close=lambda: None)
    try:
        monkeypatch.setattr(
            ThreadingHTTPServer,
            "process_request",
            lambda *_: (_ for _ in ()).throw(RuntimeError("dispatch")),
        )
        with pytest.raises(RuntimeError, match="dispatch"):
            workbench.server.process_request(sock, ("127.0.0.1", 1))
        assert workbench.server.active_requests == 0
        assert workbench.server._connections.acquire(blocking=False)
        workbench.server._connections.release()
    finally:
        workbench.close()


def test_unexpected_mainloop_return_uses_same_drain_and_preserves_signal(window):
    window.open_workbench()
    _, _, release, done, worker, _, actual = pending_save(window)
    workbench = window._browser_workbench
    before = signal.getsignal(signal.SIGTERM)
    turns = []

    def mainloop():
        turns.append(True)
        if len(turns) == 1:
            return
        assert not window.closed and not window.controller.runtime._closed
        assert window._close_pending
        release.set()
        assert done.wait(2)
        finish_close(window)

    window.root.mainloop = mainloop
    try:
        assert window.run() == 0
        assert len(turns) == 2 and window.closed
        assert signal.getsignal(signal.SIGTERM) == before
    finally:
        release.set()
        worker.join(3)
        workbench.app.campaigns.save = actual


def test_lost_tk_emergency_refuses_without_runtime_close_or_losing_drafts(window):
    window.controller.edit_document(BOOK)
    window.answer = False
    window.open_workbench()
    _, _, release, done, worker, _, actual = pending_save(window)
    workbench = window._browser_workbench
    before = signal.getsignal(signal.SIGTERM)
    original = copy.deepcopy(window.controller.document)
    window.root.winfo_exists = lambda: False
    window.root.mainloop = lambda: None
    old = workbench.close

    def short_close():
        return old(timeout=0.02)

    workbench.close = short_close
    try:
        with pytest.raises(
            NativeWindowError,
            match="retained",
        ):
            window.run()
        assert not window.closed and not window.controller.runtime._closed
        assert window.controller.document == original and window.controller.dirty
        assert signal.getsignal(signal.SIGTERM) == before
        release.set()
        assert done.wait(2)
        worker.join()
        workbench.close = old
        window._emergency_close()
        assert window.closed and window.controller.runtime._closed
    finally:
        release.set()
        worker.join(3)
        workbench.close = old
        workbench.app.campaigns.save = actual


@pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), float("inf"), 6])
def test_invalid_wait_cannot_turn_bounded_close_into_unbounded_work(
    controller, timeout
):
    workbench = native_browser.NativeBrowserWorkbench(controller.runtime.app)
    try:
        with pytest.raises(ValueError, match="five seconds"):
            workbench.begin_close(timeout)
        assert workbench.phase == "running" and request(workbench)[0] == 200
    finally:
        workbench.close()


def test_explicit_save_then_refused_close_keeps_separate_answer_draft(window):
    window.controller.edit_document(BOOK)
    window.answer = False
    window.open_workbench()
    window.controller.variables = {
        "source_title": "Exact",
        "excerpt": "No approval — é.",
        "question": "Unknown?",
    }
    variables = copy.deepcopy(window.controller.variables)
    window.answer = True

    # The ordinary Save-project action repaints and clears the separate excerpt.
    # Close must save only the source, because its drain can still be refused.
    def repainting_save():
        window.controller.save()
        window.controller.variables.clear()

    window.save_project = repainting_save
    _, _, release, done, worker, _, actual = pending_save(window)
    workbench = window._browser_workbench
    try:
        window.request_close(browser_requested=True)
        workbench._deadline = time.monotonic() - 1
        window._poll_workbench_close()
        assert not window.closed and not window.controller.runtime._closed
        assert window.controller.variables == variables
        assert not window.controller.dirty
        release.set()
        assert done.wait(2)
        worker.join()
    finally:
        release.set()
        worker.join(3)
        workbench.app.campaigns.save = actual


def test_browser_quit_clean_source_with_answer_draft_requires_native_confirmation(
    window,
):
    window.controller.edit_document(BOOK)
    window.controller.save()
    window.open_workbench()
    window.controller.variables = {"excerpt": "Exact unsaved answer — é."}
    original = copy.deepcopy(window.controller.variables)
    confirmations = []
    window.messages.askyesno = lambda *a, **k: confirmations.append(a) or False
    window.request_close(browser_requested=True)
    assert len(confirmations) == 1
    assert not window.closed and not window.controller.runtime._closed
    assert window.controller.variables == original
    assert window._browser_workbench.session_state()["state"] == "cancelled"


def test_initial_heartbeat_scheduling_error_runs_bounded_emergency_cleanup(window):
    window.open_workbench()
    workbench = window._browser_workbench
    previous = signal.getsignal(signal.SIGTERM)

    def unavailable(*_):
        raise RuntimeError("Fictional unavailable Tk scheduling")

    window.root.after = unavailable
    with pytest.raises(RuntimeError, match="unavailable Tk"):
        window.run()
    assert workbench.closed and not workbench.thread.is_alive()
    assert window.controller.runtime._closed and window.closed
    assert signal.getsignal(signal.SIGTERM) == previous


def test_failed_tk_launcher_exit_does_not_claim_durable_in_memory_recovery(tmp_path):
    """A real subprocess exits; daemon requests and unsaved memory are not a backup."""
    script = r"""
import copy, json, signal, sys, threading
from pathlib import Path
from http.client import HTTPConnection
from types import SimpleNamespace
from urllib.parse import urlsplit
from sinter import client, desktop, native_window
from sinter.native_browser import NativeBrowserWorkbench
from sinter.native_window import NativeController, NativeWindow
from sinter.runtime import Runtime
root = Path(sys.argv[1])
def refuse(*args, **kwargs):
    raise AssertionError('No provider or credential request')
for key in ('_open', '_load_key', 'chat', 'search'):
    setattr(client, key, refuse)
runtime = Runtime(root)
controller = NativeController(runtime)
controller.edit_document({'title':'Saved original', 'questions':'Unknown approval?',
 'documents':[{'title':'Exact quote','content':'AUD110 including GST; production unknown.'}]})
saved_source = controller.save()
controller.edit_document({**controller.document, 'title':'Unsaved in memory'})
controller.variables = {'excerpt':'Unsaved answer — é.'}
workbench = NativeBrowserWorkbench(runtime.app)
saved = runtime.app.campaigns.save({'title':'Saved fictional campaign'})
actual_save = runtime.app.campaigns.save
entered = threading.Event()
never_release = threading.Event()
def waiting_save(*args, **kwargs):
    entered.set()
    never_release.wait(10)
    return actual_save(*args, **kwargs)
runtime.app.campaigns.save = waiting_save
def submit():
    url = urlsplit(workbench.url)
    conn = HTTPConnection(url.hostname, url.port, timeout=10)
    conn.request('POST', '/api/campaigns/save', json.dumps({
       'document':{**saved['document'], 'title':'Unfinished explicit save'},
       'id':saved['id'], 'revision':saved['revision']}),
       headers={'Content-Type':'application/json','X-Sinter-Token':runtime.app.token})
    response = conn.getresponse()
    response.read()
    conn.close()
worker = threading.Thread(target=submit, daemon=True)
worker.start()
assert entered.wait(2)
window = NativeWindow.__new__(NativeWindow)
window.controller = controller
window.closed = False
window._browser_workbench = workbench
window.root = SimpleNamespace(after=lambda *args:'heartbeat',
                             mainloop=lambda:None, winfo_exists=lambda:False)
old_close = workbench.close
workbench.close = lambda:old_close(timeout=0.02)
native_window.run_native = lambda directory:window.run()
previous = signal.getsignal(signal.SIGTERM)
code = desktop.main(['--mode','native','--directory',str(root)])
assert code == 1
observations = {'exit_code':code, 'runtime_closed_before_exit':runtime._closed,
 'native_title_in_memory_before_exit':controller.document['title'],
 'answer_in_memory_before_exit':controller.variables,
 'saved_source':saved_source, 'saved_campaign':saved,
 'live_saved_campaign':runtime.app.campaigns.get(saved['id']),
 'active_requests_before_exit':workbench.server.active_requests,
 'request_thread_alive_before_exit':worker.is_alive(),
 'signal_restored':signal.getsignal(signal.SIGTERM)==previous}
(root/'before-process-exit.json').write_text(json.dumps(observations))
raise SystemExit(code)
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(native_browser.__file__).resolve().parents[1])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    workspace = tmp_path / "failed-gui-fictional"
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(workspace)],
        env=environment,
        capture_output=True,
        timeout=5,
        text=True,
    )
    (tmp_path / "launcher.stdout").write_text(result.stdout)
    (tmp_path / "launcher.stderr").write_text(result.stderr)
    (tmp_path / "launcher-exit.json").write_text(
        json.dumps({"actual_process_exit_code": result.returncode})
    )
    assert result.returncode == 1
    assert "graphical launcher exits with an error" in result.stderr
    assert "only in process memory" in result.stderr
    assert (
        "not guaranteed" in result.stderr and "No request was replayed" in result.stderr
    )
    assert "Traceback" not in result.stderr
    before = json.loads((workspace / "before-process-exit.json").read_text())
    assert not before["runtime_closed_before_exit"]
    assert before["native_title_in_memory_before_exit"] == "Unsaved in memory"
    assert before["answer_in_memory_before_exit"] == {"excerpt": "Unsaved answer — é."}
    assert before["active_requests_before_exit"] == 1
    assert before["request_thread_alive_before_exit"] and before["signal_restored"]
    assert before["live_saved_campaign"] == before["saved_campaign"]
    # Reopening the exited child's isolated workspace cannot recover its memory.
    with Runtime(workspace) as reopened:
        assert (
            reopened.app.casebooks.get(before["saved_source"]["id"])
            == before["saved_source"]
        )
        assert (
            reopened.app.campaigns.get(before["saved_campaign"]["id"])
            == before["saved_campaign"]
        )
