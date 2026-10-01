"""Native first-run setup uses shared routes with fictional catalogue/key data."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from sinter import client, native_window
from sinter.native_window import NativeController, NativeWindow
from sinter.runtime import OperationError, Runtime, _Capture


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    for name in (
        "NEUROFORGE_BASE_URL",
        "NEUROFORGE_MODEL",
        "NEUROFORGE_API_KEY",
        "SINTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(client, "_open", lambda *_a, **_k: pytest.fail("No network"))
    monkeypatch.setattr(client, "_load_key", lambda: pytest.fail("No credential read"))
    monkeypatch.setattr(client, "chat", lambda *_a, **_k: pytest.fail("No inference"))


@pytest.fixture
def controller(tmp_path):
    value = NativeController(Runtime(tmp_path / "fictional"))
    yield value
    value.close()


def connection(**values):
    return {
        "provider": "openai-compatible",
        "api_url": client.BASE_URL,
        "model": "erais-native-qwen3",
        "max_tokens": 64,
        **values,
    }


def test_default_auto_manual_id_save_exact_preview_and_restart(controller):
    controller.set_request(
        "Fictional note",
        "The fictional ramp inspection remains unconfirmed.",
        "Is inspection confirmed?",
    )
    with pytest.raises(OperationError, match="exact identifier"):
        controller.preview()
    value = controller.save_connection(connection())
    assert value["settings"]["model"] == "erais-native-qwen3"
    preview = controller.preview()
    assert preview["request"]["model"] == "erais-native-qwen3"
    assert "unconfirmed" in preview["request"]["messages"][0]["content"]
    controller.approve(True)
    controller.save_connection(connection(max_tokens=32))
    assert controller.prepared is None and not controller.consent
    directory = controller.runtime.app.store.directory
    controller.close()
    with Runtime(directory) as reopened:
        assert (
            reopened.connection_settings()["settings"]["model"] == "erais-native-qwen3"
        )
        assert reopened.connection_settings()["settings"]["max_tokens"] == 32


def test_native_setup_and_web_dispatch_share_validation_and_persistence(controller):
    runtime = controller.runtime
    via_web = _Capture(runtime.app)
    via_web._dispatch_post("/api/settings", {"settings": connection()})
    assert controller.connection_settings() == via_web.result
    via_native = controller.save_connection(connection(max_tokens=48))
    via_web._dispatch_get(None, "/api/settings")
    assert via_native == via_web.result
    with pytest.raises(OperationError, match="only the model connection"):
        runtime.connection_settings({"organisation": "Fictional organisation"})
    with pytest.raises(OperationError) as unknown:
        runtime.call("settings.update", {"api_key": "fictional"})
    assert unknown.value.code == "unknown_operation"


def test_catalogue_is_explicit_unsaved_and_contains_no_documents(
    controller, monkeypatch
):
    before = controller.connection_settings()
    controller.set_request(
        "Fictional", "Fictional private-to-test note", "How many days?"
    )
    received = []

    def catalogue():
        received.append(client.connection_identity())
        return [{"id": "fictional-model"}]

    monkeypatch.setattr(client, "list_models", catalogue)
    job = controller.start_models(connection(model="probe-placeholder"))
    assert controller.runtime.wait(job) == {"models": [{"id": "fictional-model"}]}
    assert len(received) == 1
    assert received[0]["model"] == "probe-placeholder"
    assert "Fictional private-to-test note" not in json.dumps(received)
    assert controller.connection_settings() == before
    assert controller.variables["excerpt"] == "Fictional private-to-test note"
    assert controller.result is None


def test_failed_discovery_keeps_saved_preferences_and_source(controller, monkeypatch):
    before = controller.connection_settings()
    source = copy.deepcopy(controller.document)

    def denied():
        raise client.APIError("Fictional authentication required", status=401)

    monkeypatch.setattr(client, "list_models", denied)
    job = controller.start_models(connection(model="probe-placeholder"))
    with pytest.raises(OperationError, match="authentication required"):
        controller.runtime.wait(job)
    assert controller.connection_settings() == before
    assert controller.document == source


def test_write_only_key_retention_clear_destination_guard(controller, monkeypatch):
    controller.save_connection(connection(), api_key="fictional-session-key")
    controller.save_connection(connection(max_tokens=32))
    public = controller.connection_settings()
    assert public["has_session_key"] is True
    serialized = (
        json.dumps(public) + controller.runtime.app.preferences.path.read_text()
    )
    assert "fictional-session-key" not in serialized
    custom = connection(api_url="https://fictional.invalid/v1", model="fictional-model")
    with pytest.raises(OperationError, match="Confirm"):
        controller.save_connection(custom)
    forwarded = []
    monkeypatch.setattr(
        client,
        "list_models",
        lambda: forwarded.append(client._headers()) or [{"id": "fictional-model"}],
    )
    controller.runtime.connection_settings(custom, discover=True, confirm_endpoint=True)
    assert len(forwarded) == 1 and "Authorization" not in forwarded[0]
    assert controller.connection_settings()["has_session_key"] is True
    controller.save_connection(custom, confirm_endpoint=True)
    assert controller.connection_settings()["has_session_key"] is False
    controller.save_connection(custom, api_key="fictional-new-session-key")
    controller.save_connection(custom, api_key="")
    assert controller.connection_settings()["has_session_key"] is False


def test_environment_override_is_honest_and_no_discovery(controller, monkeypatch):
    monkeypatch.setenv("NEUROFORGE_MODEL", "fictional-launcher-model")
    public = controller.save_connection(connection())
    assert public["environment_override"] is True
    assert (
        controller.runtime.status()["connection"]["model"] == "fictional-launcher-model"
    )
    assert controller.connection_settings()["settings"]["model"] == "erais-native-qwen3"


def test_closed_runtime_rejects_settings(controller):
    controller.close()
    with pytest.raises(OperationError) as error:
        controller.runtime.connection_settings()
    assert error.value.code == "runtime_closed"


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Box:
    def __init__(self):
        self.options = {}

    def configure(self, **kwargs):
        self.options.update(kwargs)


def setup_window(controller):
    window = NativeWindow.__new__(NativeWindow)
    window.controller, window.closed, window.active_job = controller, False, None
    window._setup_generation, window._setting_paint = 0, False
    window._connection_key_edited = False
    window._connection_saved = controller.connection_settings()["settings"]
    window.connection_vars = {k: Value(str(v)) for k, v in connection().items()}
    window.connection_boxes = {k: Box() for k in window.connection_vars}
    window.connection_key_var, window.connection_key_box = Value(), Box()
    window.connection_confirm_var, window.connection_notice = Value(True), Value()
    window.status_var = Value()
    return window


@pytest.mark.parametrize("cap", [1, 16, 31, 64])
def test_low_native_output_cap_does_not_break_catalogue_or_change_saved_cap(
    controller, cap, monkeypatch
):
    controller.save_connection(connection(max_tokens=cap))
    window = setup_window(controller)
    window.connection_vars["max_tokens"].set(str(cap))
    monkeypatch.setattr(client, "list_models", lambda: [{"id": "erais-native-qwen3"}])
    started = []
    window._begin_job = lambda *args: started.append(args)
    window.load_models()
    assert controller.runtime.wait(started[0][0])["models"] == [
        {"id": "erais-native-qwen3"}
    ]
    assert controller.connection_settings()["settings"]["max_tokens"] == cap
    assert window.connection_vars["max_tokens"].get() == str(cap)


def test_endpoint_edit_clears_draft_key_confirmation_catalogue_and_consent(controller):
    controller.save_connection(connection())
    controller.set_request(
        "Fictional", "Fictional loans last 14 days.", "How many days?"
    )
    controller.preview()
    controller.approve(True)
    window = setup_window(controller)
    window.connection_key_var.set("fictional-draft-key")
    window._connection_key_edited = True
    window.connection_vars["api_url"].set("https://fictional.invalid/v1")
    window._connection_changed("api_url")
    assert window.connection_key_var.get() == ""
    assert window.connection_confirm_var.get() is False
    assert window.connection_boxes["model"].options["values"] == ()
    assert controller.prepared is None and not controller.consent


@pytest.mark.parametrize("status", ["done", "failed", "cancelled"])
def test_stale_catalogue_success_error_and_cancel_do_not_replace_current_setup(
    controller, status, monkeypatch
):
    window = setup_window(controller)
    window._setup_generation = 2
    window._job_generation, window._job_kind, window.active_job = (
        1,
        "models",
        "fictional-job",
    )
    window._poll_id = None
    window.stop_button = SimpleNamespace(state=lambda *_: None)
    window.build_button = SimpleNamespace(state=lambda *_: None)
    window._refresh = lambda: None
    monkeypatch.setattr(
        controller.runtime,
        "call",
        lambda *_: {
            "status": status,
            "result": {"models": [{"id": "old-model"}]},
            "error": "Old authentication error",
            "message": "Old catalogue",
        },
    )
    window._poll_job()
    assert "older catalogue was not applied" in window.connection_notice.get()
    assert "Old authentication error" not in window.connection_notice.get()
    assert "values" not in window.connection_boxes["model"].options
    assert controller.result is None


def test_readable_render_preserves_exact_markdown_and_literal_code():
    markdown = (
        "# Evidence\n> Literal # source quote.\n- Source e1\n```\n# exact code\n```\n"
    )
    lines = list(native_window.readable_report_lines(markdown))
    assert lines[:3] == [
        ("Evidence\n", "heading"),
        ("Literal # source quote.\n", "quote"),
        ("• Source e1\n", "bullet"),
    ]
    assert ("# exact code\n", "code") in lines
    assert markdown.startswith("# Evidence\n> ")


@pytest.mark.parametrize("kind", ["TEntry", "Entry", "TCombobox"])
def test_native_select_all_sets_entire_entry_selection(kind):
    calls = []
    widget = SimpleNamespace(
        winfo_class=lambda: kind,
        selection_range=lambda *a: calls.append(("select", a)),
        icursor=lambda *a: calls.append(("cursor", a)),
    )
    assert native_window.select_all(SimpleNamespace(widget=widget)) == "break"
    assert calls == [("select", (0, "end")), ("cursor", ("end",))]
