"""Portable native presentation uses shared operations and fictional text only."""

from __future__ import annotations

import copy
import json
import os
import signal
import time
from types import SimpleNamespace

import pytest

from sinter import client, native_window, templates
from sinter.native_window import NativeController, NativeWindow, NativeWindowError
from sinter.runtime import OperationError, Runtime


@pytest.fixture(autouse=True)
def no_provider_or_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    for name in (
        "NEUROFORGE_BASE_URL",
        "NEUROFORGE_MODEL",
        "NEUROFORGE_API_KEY",
        "SINTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NEUROFORGE_MODEL", "erais-native-qwen3")
    monkeypatch.setattr(
        client.urllib.request,
        "build_opener",
        lambda *_: pytest.fail("unexpected network request"),
    )
    monkeypatch.setattr(
        client, "_load_key", lambda: pytest.fail("unexpected credential access")
    )
    monkeypatch.setattr(
        client, "chat", lambda *_a, **_k: pytest.fail("unexpected model request")
    )
    monkeypatch.setattr(
        templates,
        "chat",
        lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("unexpected model request")
        ),
    )


@pytest.fixture
def controller(tmp_path):
    runtime = Runtime(tmp_path / "workspace")
    value = NativeController(runtime)
    yield value
    value.close()


def fictional_book(days=14):
    return {
        "schema": "sinter-casebook/v1",
        "title": "Fictional Lantern project",
        "questions": "How many days may lanterns be borrowed?\n"
        "Who determined insurance liability?",
        "documents": [
            {
                "title": "Fictional handbook",
                "content": f"Fictional lantern loans last {days} days.",
            }
        ],
        "document_type": "brief",
    }


def build(controller):
    identifier, generation = controller.start_build()
    value = controller.runtime.wait(identifier)
    assert controller.accept_result(generation, value)
    return value


def source_request(controller):
    controller.set_request(
        "Fictional handbook", "Fictional lantern loans last 14 days.", "How many days?"
    )
    return controller.preview()


def test_shared_source_update_history_and_backup_round_trip(controller, tmp_path):
    controller.edit_document(fictional_book())
    old = build(controller)
    assert old["coverage"]["questions_without_wording_matches"] == 1
    assert "14 days" in old["markdown"]
    saved_report = controller.save_report()["id"]
    first_id, first_revision = controller.identifier, controller.revision
    controller.edit_document(fictional_book(21))
    current = build(controller)
    assert (
        controller.identifier == first_id and controller.revision == first_revision + 1
    )
    assert "21 days" in current["markdown"]
    assert old["casebook_fingerprint"] != current["casebook_fingerprint"]
    assert (
        controller.runtime.call("reports.get", {"id": saved_report})["markdown"]
        == old["markdown"]
    )
    backup = tmp_path / "fictional-project.json"
    controller.export_project(backup)
    controller.import_project(backup)
    assert controller.identifier is None and controller.revision is None
    assert (
        controller.document["documents"][0]["content"]
        == "Fictional lantern loans last 21 days."
    )
    assert controller.runtime.call("casebooks.get", {"id": first_id})["revision"] == 2
    controller.save()
    assert controller.identifier != first_id


def test_native_and_programmatic_report_semantics_match(controller):
    controller.edit_document(fictional_book())
    actual = build(controller)
    direct = controller.runtime.call(
        "casebooks.build",
        {"id": controller.identifier, "revision": controller.revision},
    )
    for key in (
        "coverage",
        "excerpts",
        "source_register",
        "question_index",
        "casebook_fingerprint",
    ):
        assert actual[key] == direct[key]


def test_optimistic_revision_failure_keeps_unsaved_edits(controller):
    controller.edit_document(fictional_book())
    controller.save()
    concurrent = {**controller.document, "title": "Fictional concurrent title"}
    controller.runtime.call(
        "casebooks.save",
        {
            "id": controller.identifier,
            "revision": controller.revision,
            "document": concurrent,
        },
    )
    controller.edit_document(fictional_book(21))
    before = copy.deepcopy(controller.document)
    with pytest.raises(OperationError, match="changed in another window"):
        controller.save()
    assert controller.document == before and controller.dirty
    assert controller.revision == 1


def test_noop_save_does_not_create_an_extra_revision(controller):
    controller.edit_document(fictional_book())
    controller.save()
    controller.save()
    assert controller.revision == 1


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
def test_selected_text_admission_uses_shared_limits_and_retains_exact_text(
    controller, tmp_path, ending
):
    source = tmp_path / "fictional-handbook.md"
    exact = "Fictional lantern café loans last 14 days." + ending
    source.write_bytes(exact.encode("utf-8"))
    controller.import_text([source])
    assert controller.document["documents"][0]["content"] == exact
    assert source.resolve() in controller.source_paths
    assert controller.runtime.call("casebooks.list")["casebooks"] == []


@pytest.mark.parametrize("content", [b"binary\x00payload", b"\xff\xfe\x00"])
def test_bad_selected_text_does_not_partially_modify_project(
    controller, tmp_path, content
):
    good, bad = tmp_path / "good.txt", tmp_path / "bad.txt"
    good.write_text("Wholly fictional valid text.")
    bad.write_bytes(content)
    original = copy.deepcopy(controller.document)
    with pytest.raises((ValueError, OperationError)):
        controller.import_text([good, bad])
    assert controller.document == original and not controller.source_paths


def test_selected_text_read_has_a_byte_bound(tmp_path):
    source = tmp_path / "bounded.txt"
    source.write_bytes(b"123456")
    with pytest.raises(ValueError, match="exceeds 5 bytes"):
        native_window.read_selected_text(source, 5)
    assert native_window.read_selected_text(source, 6) == "123456"


def test_x11_window_registers_its_actual_local_client_before_mapping(monkeypatch):
    from types import SimpleNamespace

    clients = []
    root = SimpleNamespace(
        tk=SimpleNamespace(call=lambda *args: "x11"), wm_client=clients.append
    )
    monkeypatch.setattr(native_window.socket, "gethostname", lambda: "fictional-host")
    monkeypatch.setattr(
        native_window.socket,
        "getaddrinfo",
        lambda *_: pytest.fail("Window identity must not perform DNS/network access"),
    )
    native_window.register_window_client(root)
    assert clients == ["fictional-host"]


@pytest.mark.parametrize("system", ["win32", "aqua"])
def test_other_window_systems_do_not_use_x11_client_metadata(system, monkeypatch):
    from types import SimpleNamespace

    root = SimpleNamespace(tk=SimpleNamespace(call=lambda *args: system))
    monkeypatch.setattr(
        native_window.socket, "gethostname", lambda: pytest.fail("X11 metadata only")
    )
    native_window.register_window_client(root)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO only.")
def test_selected_fifo_is_rejected_before_opening(tmp_path, monkeypatch):
    source = tmp_path / "fictional-fifo"
    os.mkfifo(source)
    monkeypatch.setattr(os, "open", lambda *_a, **_k: pytest.fail("opened FIFO"))
    with pytest.raises(ValueError, match="regular text file"):
        native_window.read_selected_text(source)


def test_replaced_selected_file_is_rejected_before_reading(tmp_path, monkeypatch):
    source, replacement = tmp_path / "source.txt", tmp_path / "replacement.txt"
    source.write_text("Original fictional note.")
    replacement.write_text("Replacement fictional note.")
    original_open = os.open

    def replaced(path, flags):
        assert flags & getattr(os, "O_NONBLOCK", 0) == getattr(os, "O_NONBLOCK", 0)
        return original_open(replacement, flags)

    monkeypatch.setattr(os, "open", replaced)
    with pytest.raises(ValueError, match="selected file changed"):
        native_window.read_selected_text(source)


@pytest.mark.parametrize("value", [{"schema": "unrelated/v1"}, [], "not a project"])
def test_invalid_json_project_preserves_saved_identity(controller, tmp_path, value):
    controller.edit_document(fictional_book())
    controller.save()
    identity = controller.identifier, controller.revision
    backup = tmp_path / "invalid.json"
    backup.write_text(json.dumps(value))
    with pytest.raises((ValueError, OperationError)):
        controller.import_project(backup)
    assert (controller.identifier, controller.revision) == identity


def test_export_cannot_overwrite_selected_source_or_backup_alias(controller, tmp_path):
    source = tmp_path / "fictional.txt"
    source.write_text("Fictional lantern loans last 14 days.")
    controller.import_text([source])
    build(controller)
    original = source.read_bytes()
    with pytest.raises(ValueError, match="overwrite your source"):
        controller.export_project(source)
    with pytest.raises(ValueError, match="overwrite your source"):
        controller.export_result(source, "md")
    alias = tmp_path / "source-hardlink.txt"
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("Hard links are unavailable on this filesystem.")
    with pytest.raises(ValueError, match="overwrite your source"):
        controller.export_project(alias)
    assert source.read_bytes() == original


def test_source_report_json_import_and_markdown_export_retain_provenance(
    controller, tmp_path
):
    controller.edit_document(fictional_book())
    report = build(controller)
    source = tmp_path / "fictional-report.json"
    controller.export_result(source)
    assert controller.import_report(source)["excerpts"] == report["excerpts"]
    markdown = tmp_path / "fictional-report.md"
    controller.export_result(markdown, "md")
    assert markdown.read_text() == report["markdown"]
    with pytest.raises(ValueError, match="overwrite your source"):
        controller.export_result(source)


@pytest.mark.parametrize(
    "filename",
    [
        "workspace.sqlite3",
        "preferences.json",
        "accounts/profiles.json",
        "templates/example.json",
    ],
)
def test_exports_protect_runtime_storage_and_private_subtrees(controller, filename):
    controller.edit_document(fictional_book())
    build(controller)
    destination = controller.runtime.app.store.directory / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_text("fictional protected existing data")
    original = destination.read_bytes()
    with pytest.raises((ValueError, OperationError)):
        controller.export_project(destination)
    with pytest.raises((ValueError, OperationError)):
        controller.export_result(destination)
    assert destination.read_bytes() == original


def test_preview_is_exact_and_offline_then_input_changes_clear_consent(controller):
    prepared = source_request(controller)
    assert (
        "Fictional lantern loans last 14 days."
        in prepared["request"]["messages"][-1]["content"]
    )
    assert prepared["excerpts"][0]["quote"] == controller.variables["excerpt"]
    controller.approve(True)
    controller.set_request(
        "Fictional handbook", "Fictional lantern loans last 21 days.", "How many days?"
    )
    assert controller.prepared is None and not controller.consent
    with pytest.raises(ValueError, match="Preview the current exact excerpt"):
        controller.start_answer()


def test_source_update_discards_old_selected_excerpt_and_consent(controller):
    controller.edit_document(fictional_book())
    source_request(controller)
    controller.approve(True)
    controller.edit_document(fictional_book(21))
    assert controller.variables["excerpt"] == ""
    assert controller.variables["source_title"] == ""
    assert not controller.consent
    with pytest.raises(ValueError, match="Preview"):
        controller.start_answer()


def test_destination_change_is_rejected_by_shared_admission(controller, monkeypatch):
    source_request(controller)
    controller.approve(True)
    monkeypatch.setenv("NEUROFORGE_MODEL", "fictional-other-model")
    with pytest.raises(OperationError, match="Preview the current source request"):
        controller.start_answer()
    assert controller.prepared is None and not controller.consent
    assert controller.runtime.call("jobs.list")["jobs"] == []


def test_one_approved_synthetic_answer_uses_shared_jobs_and_consumes_consent(
    controller, monkeypatch
):
    requests = []

    def fictional_answer(messages, max_tokens):
        requests.append((messages, max_tokens))
        return client.ChatResult(
            "14 days. [e1]",
            total_tokens=15,
            finish_reason="stop",
            model="erais-native-qwen3",
        )

    monkeypatch.setattr(templates, "chat", fictional_answer)
    prepared = source_request(controller)
    controller.approve(True)
    identifier, generation = controller.start_answer()
    value = controller.runtime.wait(identifier)
    assert controller.accept_result(generation, value)
    assert value["complete"] and value["results"][0]["content"] == "14 days. [e1]"
    assert value["sources"][0]["sources"] == prepared["sources"]
    assert len(requests) == 1 and not controller.consent and controller.prepared is None
    with pytest.raises(ValueError, match="Preview"):
        controller.start_answer()
    assert len(requests) == 1


def test_delayed_preview_cannot_restore_old_approval(controller, monkeypatch):
    controller.set_request("Fictional", "Fictional 14-day note.", "How many days?")

    def delayed(*args, **kwargs):
        controller.set_request("Fictional", "Fictional 21-day note.", "How many days?")
        return {"context_hash": "old-fictional-hash"}

    monkeypatch.setattr(controller.runtime, "call", delayed)
    with pytest.raises(ValueError, match="Inputs changed"):
        controller.preview()
    assert controller.prepared is None and not controller.consent


def test_late_result_cannot_replace_newer_source_or_closed_workspace(controller):
    generation = controller.generation
    old_result = {"title": "Fictional old result", "markdown": "14 days"}
    assert controller.accept_result(generation, old_result)
    controller.edit_document(fictional_book(21))
    assert not controller.accept_result(generation, {"markdown": "stale 14-day result"})
    assert controller.result == old_result
    controller.close()
    assert not controller.accept_result(
        controller.generation, {"markdown": "after close"}
    )
    with pytest.raises(ValueError, match="closed"):
        controller.save()


def test_failed_submission_consumes_approval_and_never_replays(controller, monkeypatch):
    source_request(controller)
    controller.approve(True)
    calls = []

    def uncertain(operation, *args, **kwargs):
        calls.append(operation)
        raise OperationError("Fictional unknown remote outcome")

    monkeypatch.setattr(controller.runtime, "call", uncertain)
    with pytest.raises(OperationError, match="unknown remote outcome"):
        controller.start_answer()
    with pytest.raises(ValueError, match="Preview"):
        controller.start_answer()
    assert calls == ["template.job"]


def test_incomplete_model_result_is_labelled_and_exact_json_can_be_exported(
    controller, tmp_path
):
    value = {
        "complete": False,
        "results": [],
        "sources": [],
        "partial": {"content": "Fictional unfinished answer"},
    }
    controller.accept_result(controller.generation, value)
    destination = tmp_path / "partial.json"
    controller.export_result(destination)
    assert json.loads(destination.read_text()) == value
    assert "INCOMPLETE" in native_window.result_markdown(value)
    with pytest.raises(ValueError, match="completed source report"):
        controller.save_report()


class FakeRoot:
    def __init__(self):
        self.destroyed = False
        self.timers = {}
        self.cancelled = []

    def after(self, interval, callback):
        identifier = str(len(self.timers) + 1)
        self.timers[identifier] = callback
        return identifier

    def after_cancel(self, identifier):
        self.cancelled.append(identifier)
        self.timers.pop(identifier, None)

    def destroy(self):
        self.destroyed = True


def test_failed_workspace_open_destroys_owned_window_and_preserves_file(
    monkeypatch, tmp_path
):
    root = FakeRoot()
    root.withdraw = lambda: None
    root.update_idletasks = lambda: None
    toolkit = SimpleNamespace(TclError=RuntimeError, Tk=lambda: root)
    monkeypatch.setattr(native_window, "_toolkit", lambda: (toolkit,) + (None,) * 4)
    workspace = tmp_path / "fictional-workspace-file"
    workspace.write_text("Fictional existing content")
    original = workspace.read_bytes()
    with pytest.raises(OSError):
        NativeWindow(workspace)
    assert root.destroyed and workspace.read_bytes() == original


def bare_window(controller):
    window = NativeWindow.__new__(NativeWindow)
    window.root = FakeRoot()
    window.controller = controller
    window.closed = False
    window._poll_id = None
    window._heartbeat_id = None
    window.active_job = None
    return window


def test_native_close_cancels_timers_and_late_poll_does_not_touch_runtime(
    controller, monkeypatch
):
    window = bare_window(controller)
    window._poll_id = window.root.after(100, window._poll_job)
    window._heartbeat_id = window.root.after(200, lambda: None)
    window.active_job = "fictional-job"
    monkeypatch.setattr(
        controller.runtime, "call", lambda *_a, **_k: pytest.fail("late runtime call")
    )
    window.close()
    window.close()
    window._poll_job()
    assert controller.closed and window.root.destroyed
    assert len(window.root.cancelled) == 2 and not window.root.timers


def test_native_run_sigterm_closes_and_restores_previous_handler(controller):
    window = bare_window(controller)
    before = signal.getsignal(signal.SIGTERM)
    window.root.mainloop = lambda: signal.getsignal(signal.SIGTERM)(
        signal.SIGTERM, None
    )
    assert window.run() == 0
    assert window.closed and controller.closed and window.root.destroyed
    assert signal.getsignal(signal.SIGTERM) == before


def test_native_run_keyboard_interrupt_closes_and_restores_handler(controller):
    window = bare_window(controller)
    before = signal.getsignal(signal.SIGTERM)

    def interrupted():
        raise KeyboardInterrupt

    window.root.mainloop = interrupted
    assert window.run() == 130
    assert window.closed and controller.closed
    assert signal.getsignal(signal.SIGTERM) == before


def test_missing_toolkit_does_not_create_runtime_or_workspace(monkeypatch, tmp_path):
    def unavailable():
        raise NativeWindowError("missing Tcl/Tk")

    monkeypatch.setattr(native_window, "_toolkit", unavailable)
    with pytest.raises(NativeWindowError, match="missing Tcl/Tk"):
        NativeWindow(
            tmp_path / "never-created",
            runtime_factory=lambda *_: pytest.fail("runtime opened"),
        )
    assert not (tmp_path / "never-created").exists()


def test_failed_display_does_not_create_runtime_or_workspace(monkeypatch, tmp_path):
    class DisplayError(Exception):
        pass

    def unavailable():
        raise DisplayError("fictional denied display")

    toolkit = SimpleNamespace(Tk=unavailable, TclError=DisplayError)
    monkeypatch.setattr(
        native_window, "_toolkit", lambda: (toolkit, None, None, None, None)
    )
    with pytest.raises(NativeWindowError, match="working desktop"):
        NativeWindow(
            tmp_path / "never-created",
            runtime_factory=lambda *_: pytest.fail("runtime opened"),
        )
    assert not (tmp_path / "never-created").exists()


def test_failed_toolkit_resource_initialization_closes_partial_root(monkeypatch):
    class ResourceError(Exception):
        pass

    root = FakeRoot()
    root.withdraw = lambda: (_ for _ in ()).throw(ResourceError("missing resources"))
    toolkit = SimpleNamespace(TclError=ResourceError, Tk=lambda: root)
    monkeypatch.setattr(
        native_window, "_toolkit", lambda: (toolkit, None, None, None, None)
    )
    with pytest.raises(NativeWindowError):
        NativeWindow(runtime_factory=lambda *_: pytest.fail("runtime opened"))
    assert root.destroyed


@pytest.mark.skipif(
    os.environ.get("SINTER_NATIVE_GUI_TEST") != "1",
    reason="Real Tk GUI journey requires explicitly enabled desktop access.",
)
def test_real_native_widgets_fictional_source_update_and_approved_mock_answer(
    tmp_path, monkeypatch
):
    window = NativeWindow(tmp_path / "fictional-gui")
    monkeypatch.setattr(
        window.messages,
        "showerror",
        lambda *_a, **_k: pytest.fail("unexpected GUI error"),
    )
    monkeypatch.setattr(window.messages, "askyesno", lambda *_a, **_k: True)

    def wait():
        deadline = time.monotonic() + 5
        while window.active_job and time.monotonic() < deadline:
            window.root.update()
            time.sleep(0.01)
        assert window.active_job is None

    try:
        window.example()
        window.save_project()
        window.build_report()
        wait()
        original = copy.deepcopy(window.controller.result)
        window.save_report()
        report_id = window.reports_tree.get_children()[0]
        window.sources_tree.selection_set("0")
        window._source_selected()
        window.source_text.delete("1.0", "end")
        window.source_text.insert(
            "1.0",
            "Wholly fictional practice note: Lantern loans last 21 days. "
            "No budget approval is recorded.",
        )
        window.root.update()
        window.save_project()
        assert window.controller.revision == 2
        window.build_report()
        wait()
        assert "21 days" in window.controller.result["markdown"]
        assert (
            window.controller.runtime.call("reports.get", {"id": report_id})["markdown"]
            == original["markdown"]
        )
        window.excerpts_tree.selection_set("0")
        window.use_excerpt()
        window.question_var.set("How many days may a fictional lantern be borrowed?")
        window.preview()
        prepared = copy.deepcopy(window.controller.prepared)
        requests = []

        def fictional_answer(messages, max_tokens):
            requests.append((messages, max_tokens))
            return client.ChatResult(
                "21 days. [e1]",
                total_tokens=15,
                finish_reason="stop",
                model="erais-native-qwen3",
            )

        monkeypatch.setattr(templates, "chat", fictional_answer)
        window.consent_var.set(True)
        window._approval_changed()
        window.ask()
        wait()
        assert len(requests) == 1 and window.controller.result["complete"]
        assert [vars(message) for message in requests[0][0]] == (
            prepared["request"]["messages"]
        )
        packet = window.controller.result["sources"][0]
        assert packet["sources"] == prepared["sources"]
        assert packet["excerpts"] == prepared["excerpts"]
        assert "21 days. [e1]" in window.report_text.get("1.0", "end")
        assert not window.consent_var.get()
        assert not window.controller.consent
        window.controller.export_result(tmp_path / "fictional-answer.json")
        exported = json.loads((tmp_path / "fictional-answer.json").read_text())
        assert exported["sources"][0] == packet
        project_id = window.controller.identifier
        window.controller.export_project(tmp_path / "fictional-project.json")
        window.close()
        window = NativeWindow(tmp_path / "fictional-gui")
        window.messages.showerror = lambda *_a, **_k: pytest.fail(
            "unexpected GUI error"
        )
        window.messages.askyesno = lambda *_a, **_k: True
        window.saved_tree.selection_set(project_id)
        window.open_project()
        assert window.controller.revision == 2
        assert "21 days" in window.controller.document["documents"][0]["content"]
        assert (
            window.controller.runtime.call("reports.get", {"id": report_id}) == original
        )
        window.controller.import_project(tmp_path / "fictional-project.json")
        assert window.controller.identifier is None
        assert "21 days" in window.controller.document["documents"][0]["content"]
        assert (
            window.controller.runtime.call("runtime.status")[
                "watch_scheduler_started_by_runtime"
            ]
            is False
        )
    finally:
        window.close()


@pytest.mark.skipif(
    os.environ.get("SINTER_NATIVE_GUI_TEST") != "1",
    reason="Real Tk interruption requires explicitly enabled desktop access.",
)
def test_real_native_sigterm_restores_handler_and_allows_repeat_launch(tmp_path):
    previous = signal.getsignal(signal.SIGTERM)
    workspace = tmp_path / "fictional-repeated-launch"
    for _ in range(2):
        window = NativeWindow(workspace)
        window.root.after(30, lambda: signal.raise_signal(signal.SIGTERM))
        try:
            assert window.run() == 0
            assert window.closed and window.controller.closed
            assert window.controller.runtime.app.stop.is_set()
            assert signal.getsignal(signal.SIGTERM) is previous
        finally:
            window.close()


@pytest.mark.skipif(
    os.environ.get("SINTER_NATIVE_GUI_TEST") != "1",
    reason="Real Tk onboarding requires explicitly enabled desktop access.",
)
def test_real_native_first_run_setup_catalogue_save_preview_negation_and_restart(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("NEUROFORGE_MODEL", raising=False)
    workspace = tmp_path / "fictional-first-run"
    window = NativeWindow(workspace)
    monkeypatch.setattr(
        window.messages,
        "showerror",
        lambda *_a, **_k: pytest.fail("unexpected GUI error"),
    )
    monkeypatch.setattr(window.messages, "askyesno", lambda *_a, **_k: True)
    catalogue_calls, model_calls = [], []

    def catalogue():
        catalogue_calls.append(client.connection_identity())
        return [{"id": "erais-native-qwen3", "object": "model"}]

    def answer(messages, max_tokens):
        model_calls.append((messages, max_tokens))
        return client.ChatResult(
            "The ramp inspection remains unconfirmed. [e1]",
            total_tokens=18,
            finish_reason="stop",
            model="erais-native-qwen3",
        )

    monkeypatch.setattr(client, "list_models", catalogue)
    monkeypatch.setattr(templates, "chat", answer)

    def wait():
        deadline = time.monotonic() + 5
        while window.active_job and time.monotonic() < deadline:
            window.root.update()
            time.sleep(0.01)
        assert window.active_job is None

    try:
        window.example()
        window.title_var.set("Fictional ramp note")
        window.root.update()
        window.title_entry.focus_force()
        window.root.update()
        window.title_entry.event_generate("<Control-a>")
        window.root.update()
        assert window.title_entry.selection_present()
        assert window.title_entry.index("sel.first") == 0
        assert window.title_entry.index("sel.last") == len("Fictional ramp note")
        window.sources_tree.selection_set("0")
        window._source_selected()
        exact = "Wholly fictional test note: The ramp inspection remains unconfirmed."
        window.source_text.delete("1.0", "end")
        window.source_text.insert("1.0", exact)
        window.questions_text.delete("1.0", "end")
        window.questions_text.insert("1.0", "Is the ramp inspection confirmed?")
        window.root.update()
        window.save_project()
        window.build_report()
        wait()
        report = copy.deepcopy(window.controller.result)
        assert report["markdown"].startswith("#")
        assert not window.report_text.get("1.0", "end").startswith("#")
        assert window.report_text.tag_ranges("heading")
        window.excerpts_tree.selection_set("0")
        window.use_excerpt()
        window.question_var.set("Is the ramp inspection confirmed?")
        with pytest.raises(OperationError, match="exact identifier"):
            window.preview()
        assert not catalogue_calls and not model_calls
        window.pages.select(window.setup_page)
        window.root.geometry("850x650")
        window.root.update()
        window.setup_scroll.yview_moveto(1)
        window.root.update()
        for control in (window.models_button, window.connection_save_button):
            assert control.winfo_ismapped()
            assert control.winfo_rooty() >= window.setup_scroll.winfo_rooty()
            assert control.winfo_rooty() + control.winfo_height() <= (
                window.setup_scroll.winfo_rooty() + window.setup_scroll.winfo_height()
            )
        assert window.connection_vars["model"].get() == "auto"
        window.connection_confirm_box.invoke()
        window.models_button.invoke()
        wait()
        assert len(catalogue_calls) == 1
        assert window.controller.result == report
        assert window.connection_vars["model"].get() == "auto"
        assert tuple(window.connection_boxes["model"]["values"]) == (
            "erais-native-qwen3",
        )
        window.connection_vars["model"].set("erais-native-qwen3")
        window.connection_save_button.invoke()
        assert not window.controller.consent
        window.pages.select(window.answer_page)
        window.preview_button.invoke()
        prepared = copy.deepcopy(window.controller.prepared)
        assert prepared["request"]["model"] == "erais-native-qwen3"
        window.consent_box.invoke()
        window.ask_button.invoke()
        wait()
        assert len(model_calls) == 1
        assert [vars(message) for message in model_calls[0][0]] == prepared["request"][
            "messages"
        ]
        result = window.controller.result
        assert result["sources"][0]["excerpts"] == prepared["excerpts"]
        assert "remains unconfirmed" in window.report_text.get("1.0", "end")
        assert "UNVERIFIED MODEL DRAFT" in window.report_text.get("1.0", "end")
        exported = tmp_path / "fictional-ramp-answer.json"
        window.controller.export_result(exported)
        assert json.loads(exported.read_text(encoding="utf-8")) == result
        assert not window.consent_var.get()
        window.close()
        window = NativeWindow(workspace)
        assert window.connection_vars["model"].get() == "erais-native-qwen3"
        assert (
            window.controller.runtime.status()["connection"]["model"]
            == "erais-native-qwen3"
        )
        assert len(catalogue_calls) == 1 and len(model_calls) == 1
    finally:
        window.close()
