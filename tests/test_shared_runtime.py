"""One fictional user workflow across UI routes, CLI and direct Python calls."""

from __future__ import annotations

import copy
import io
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from test_runtime import post, request
from test_runtime import server as runtime_server

from sinter import cli, client
from sinter.operations import checkpoint
from sinter.runtime import Application, OperationError, Runtime, catalog
from sinter.runtime_routes import RouteDispatch
from sinter.server import Handler, make_server

server = runtime_server


@pytest.fixture(autouse=True)
def fictional_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("SINTER_DATA_DIR", str(tmp_path / "workspace"))
    for name in (
        "NEUROFORGE_BASE_URL",
        "NEUROFORGE_MODEL",
        "NEUROFORGE_API_KEY",
        "SINTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        client, "_open", lambda *a, **k: pytest.fail("No remote request permitted")
    )
    monkeypatch.setattr(
        client, "_load_key", lambda: pytest.fail("No credential read permitted")
    )


def project(days=14):
    return {
        "title": "Fictional Lantern library",
        "questions": "How long is the lending period?",
        "documents": [
            {
                "title": "Fictional handbook.md",
                "content": (
                    f"The Lantern lending period is {days} days. "
                    "Renewals require staff approval."
                ),
                "date": "2026-01-01",
            }
        ],
    }


def variables(days=14):
    return {
        "source_title": "Fictional handbook.md",
        "excerpt": project(days)["documents"][0]["content"],
        "question": "How long is the lending period?",
    }


def bridge_packet():
    return json.loads(
        (
            Path(__file__).parent / "fixtures" / "rkc_sinter_context_bridge.v1.json"
        ).read_text()
    )["packets"]["before"]


def configured(runtime):
    runtime.app.preferences.update({"model": client.NATIVE_MODEL, "max_tokens": 128})
    return runtime


def test_shared_dispatch_is_same_code_without_socket(tmp_path):
    assert Handler._dispatch_get is RouteDispatch._dispatch_get
    assert Handler._dispatch_post is RouteDispatch._dispatch_post
    assert Handler._request_connection is RouteDispatch._request_connection
    with (
        patch("socket.socket", side_effect=AssertionError("No socket")),
        Runtime(tmp_path) as app,
    ):
        saved = app.call("casebooks.save", {"document": project()})
        report = app.call(
            "casebooks.build", {"id": saved["id"], "revision": saved["revision"]}
        )
        assert "14 days" in report["markdown"]
        assert report["excerpts"] and report["sources"]
        assert app.call("casebooks.get", {"id": saved["id"]}) == saved
        assert app.call("runtime.status")["counts"]["casebooks"] == 1


def test_source_update_snapshot_export_import_reopen(tmp_path):
    with Runtime(tmp_path) as app:
        initial = app.call("casebooks.save", {"document": project()})
        historical = app.call("casebooks.build", {"id": initial["id"], "revision": 1})
        identifier = app.call("reports.save", {"report": historical})["id"]
        exported = json.loads(
            json.dumps(app.call("casebooks.get", {"id": initial["id"]})["document"])
        )
        updated = app.call(
            "casebooks.save",
            {"id": initial["id"], "revision": 1, "document": project(21)},
        )
        assert updated["revision"] == 2
        assert initial["document"]["fingerprint"] != updated["document"]["fingerprint"]
        latest = app.call("casebooks.build", {"id": updated["id"], "revision": 2})
        assert "21 days" in latest["markdown"]
        old = app.call("reports.get", {"id": identifier})
        assert old == historical and "14 days" in old["markdown"]
        restored = app.call("casebooks.save", {"document": exported})
        assert restored["document"] == initial["document"]
        with pytest.raises(OperationError, match="changed"):
            app.call(
                "casebooks.save",
                {"id": initial["id"], "revision": 1, "document": project(7)},
            )
    with Runtime(tmp_path) as reopened:
        assert reopened.call("casebooks.get", {"id": initial["id"]}) == updated
        assert reopened.call("reports.get", {"id": identifier}) == historical
        assert reopened.call("runtime.status")["counts"]["casebooks"] == 2


def test_ui_and_direct_operation_semantic_parity(server):
    with Runtime(application=server.app) as app:
        payload = {"document": project()}
        code, _, raw = post(server, "/api/casebooks/validate", payload)
        assert code == 200 and json.loads(raw) == app.call(
            "casebooks.validate", payload
        )
        saved = app.call("casebooks.save", payload)
        code, _, raw = request(server, "/api/casebooks/" + saved["id"])
        assert code == 200 and json.loads(raw) == saved
        assert json.loads(request(server, "/api/casebooks")[2]) == app.call(
            "casebooks.list"
        )
        packet = {"document": bridge_packet(), "question": "Lantern lending period"}
        code, _, raw = post(server, "/api/atlas/context", packet)
        assert code == 200
        assert json.loads(raw) == app.call("atlas.context", packet)
    assert not server.app.stop.is_set()  # Borrowed facade never closes the UI app.


@pytest.mark.parametrize(
    "change", ["excerpt", "question", "model", "cap", "destination", "consent", "hash"]
)
@pytest.mark.parametrize("operation", ["template.run", "template.job"])
def test_exact_preview_and_consent_changes_block_before_provider(
    tmp_path, change, operation
):
    with configured(Runtime(tmp_path)) as app:
        payload = {"template": "native-source-question", "variables": variables()}
        prepared = app.call("template.preview", payload)
        payload.update(consent=True, context_hash=prepared["context_hash"])
        if change in {"excerpt", "question"}:
            payload["variables"][change] += " Updated."
        elif change == "model":
            app.app.preferences.update({"model": client.MODEL})
        elif change == "cap":
            app.app.preferences.update({"max_tokens": 64})
        elif change == "destination":
            app.app.preferences.update(
                {
                    "api_url": "https://fictional-provider.example/v1",
                    "model": "fictional-model",
                },
                confirm_endpoint=True,
            )
        elif change == "consent":
            payload["consent"] = False
        else:
            payload["context_hash"] = "stale"
        with patch("sinter.templates.chat") as provider:
            with pytest.raises(OperationError, match="Preview"):
                app.call(operation, payload)
        provider.assert_not_called()
        assert not app.call("jobs.list")["jobs"]


def test_exact_preview_python_and_ui_same_request_one_mock_call(server):
    with configured(Runtime(application=server.app)) as app:
        payload = {"template": "native-source-question", "variables": variables()}
        prepared = app.call("template.preview", payload)
        assert json.loads(post(server, "/api/template/preview", payload)[2]) == prepared
        payload.update(consent=True, context_hash=prepared["context_hash"])
        with patch(
            "sinter.templates.chat",
            return_value=client.ChatResult(
                "14 days [e1].", finish_reason="stop", model=client.NATIVE_MODEL
            ),
        ) as provider:
            result = app.call("template.job", payload)
        provider.assert_called_once()
        sent = provider.call_args.args[0]
        assert [vars(message) for message in sent] == prepared["request"]["messages"]
        assert (
            result["complete"] is True and "14 days" in result["results"][0]["content"]
        )
        assert result["sources"][0]["sources"] == prepared["sources"]
        assert result["sources"][0]["excerpts"] == prepared["excerpts"]


def test_python_caller_mutation_cannot_change_queued_approved_inputs(tmp_path):
    gate = threading.Event()
    arrived = threading.Event()

    def generate(messages, **kwargs):
        arrived.set()
        assert gate.wait(3)
        assert "14 days" in messages[0].content and "21 days" not in messages[0].content
        return client.ChatResult(
            "14 days [e1].", finish_reason="stop", model=client.NATIVE_MODEL
        )

    with configured(Runtime(tmp_path)) as app:
        payload = {"template": "native-source-question", "variables": variables()}
        original = copy.deepcopy(payload)
        prepared = app.call("template.preview", payload)
        payload.update(consent=True, context_hash=prepared["context_hash"])
        with patch("sinter.templates.chat", side_effect=generate) as provider:
            identifier = app.call("template.job", payload, wait=False)["id"]
            assert arrived.wait(3)
            payload["variables"] = variables(21)
            gate.set()
            result = app.wait(identifier)
        provider.assert_called_once()
        assert result["template_inputs"]["variables"] == original["variables"]


def test_absent_atlas_evidence_never_calls_provider(tmp_path):
    with Runtime(tmp_path) as app, patch.object(client, "chat") as provider:
        result = app.call(
            "atlas.answer",
            {
                "document": bridge_packet(),
                "question": "zxquasar-nebula",
                "consent": True,
            },
        )
        assert result["citation_check"] == "no_generation" and not result["items"]
    provider.assert_not_called()


def test_failed_template_retains_partial_original_sources_once(tmp_path):
    with configured(Runtime(tmp_path)) as app:
        payload = {"template": "native-source-question", "variables": variables()}
        prepared = app.call("template.preview", payload)
        payload.update(consent=True, context_hash=prepared["context_hash"])
        with patch(
            "sinter.templates.chat",
            return_value=client.ChatResult(
                "14 days [e1]",
                completion_tokens=128,
                finish_reason="length",
                model=client.NATIVE_MODEL,
            ),
        ) as provider:
            with pytest.raises(OperationError) as error:
                app.call("template.job", payload)
        provider.assert_called_once()
        result = error.value.partial_result
        assert (
            result["complete"] is False
            and result["partial"]["content"] == "14 days [e1]"
        )
        assert result["sources"][0]["sources"] == prepared["sources"]
        assert result["template_inputs"]["variables"] == variables()


def test_cancel_and_close_do_not_replay_owned_jobs(tmp_path):
    started = threading.Event()

    def operation(progress):
        started.set()
        while True:
            checkpoint()
            time.sleep(0.01)

    app = Runtime(tmp_path)
    identifier = app.app.jobs.submit(operation)
    assert started.wait(2)
    app.call("jobs.cancel", {"id": identifier})
    with pytest.raises(OperationError) as error:
        app.wait(identifier)
    assert error.value.code == "cancelled"
    app.close()
    app.close()
    assert app.app.stop.is_set()
    with pytest.raises(OperationError) as error:
        app.call("runtime.status")
    assert error.value.code == "runtime_closed"


def test_keyboard_interrupt_cancels_existing_job_once(tmp_path):
    with (
        Runtime(tmp_path) as app,
        patch.object(app.app.jobs, "get", side_effect=KeyboardInterrupt),
        patch.object(app.app.jobs, "cancel") as cancel,
    ):
        with pytest.raises(KeyboardInterrupt):
            app.wait("fictional-job")
    cancel.assert_called_once_with("fictional-job")


@pytest.mark.parametrize(
    "operation",
    [
        "account.status",
        "account.connect",
        "settings.get",
        "settings.update",
        "desktop.quit",
        "/api/settings",
    ],
)
def test_sensitive_or_transport_operations_are_not_exposed(tmp_path, operation):
    with (
        Runtime(tmp_path) as app,
        patch.object(app.app.accounts, "connection") as account,
    ):
        with pytest.raises(OperationError) as error:
            app.call(operation, {"api_key": "fictional-not-an-actual-key"})
        assert error.value.code == "unknown_operation"
    account.assert_not_called()


def test_catalog_discovery_does_not_create_workspace_or_socket(tmp_path):
    with patch("socket.socket", side_effect=AssertionError("No socket")):
        result = catalog()
    ids = {row["id"] for row in result["operations"]}
    assert (
        len(ids) == 54
        and {
            "template.preview",
            "atlas.context",
            "casebooks.save",
            "documents.docx.save",
            "campaigns.funding_summary",
        }
        <= ids
    )
    local_save = next(
        row for row in result["operations"] if row["id"] == "documents.docx.save"
    )
    assert (local_save["method"], local_save["route"], local_save["effect"]) == (
        "POST",
        "/api/documents/docx/save",
        "write",
    )
    assert "No destination paths" in local_save["input"]
    assert not list(tmp_path.iterdir())


def test_status_redacts_credentials_and_profile_fields(tmp_path, monkeypatch):
    with Runtime(tmp_path) as app:
        app.app.preferences.update(
            {"organisation": "Fictional private organisation"},
            api_key="fictional-session-key",
        )
        monkeypatch.setenv(
            "NEUROFORGE_BASE_URL",
            "https://fictional-user:fictional-pass@fictional.example/v1",
        )
        serialized = json.dumps(app.call("runtime.status"))
    assert (
        "fictional-session-key" not in serialized
        and "Fictional private organisation" not in serialized
    )
    assert "fictional-user" not in serialized and "fictional-pass" not in serialized
    assert "Invalid configured destination" in serialized


def test_server_constructor_denial_closes_existing_application(tmp_path):
    app = Application(tmp_path)
    with (
        patch("sinter.server.Application", return_value=app),
        patch(
            "sinter.server.LocalServer",
            side_effect=PermissionError("Fictional sandbox denies sockets"),
        ),
        patch.object(app, "close", wraps=app.close) as closed,
    ):
        with pytest.raises(PermissionError):
            make_server(port=0, directory=tmp_path)
    closed.assert_called_once()
    assert app.stop.is_set()


def invoke(args, capsys):
    cli.main(args)
    result = capsys.readouterr()
    assert len(result.out.splitlines()) == 1
    envelope = json.loads(result.out)
    assert envelope["schema"] == "sinter-operation-result/v1" and envelope["ok"] is True
    return envelope["result"], result.err


def test_cli_import_update_export_reopen_same_python_workspace(tmp_path, capsys):
    path = tmp_path / "source.json"
    path.write_text(json.dumps({"document": project()}))
    directory = str(tmp_path / "workspace")
    saved, err = invoke(
        [
            "run",
            "casebooks.save",
            "--input",
            str(path),
            "--directory",
            directory,
            "--format",
            "json",
        ],
        capsys,
    )
    assert not err
    path.write_text(json.dumps({"id": saved["id"], "revision": 1}))
    report, err = invoke(
        [
            "run",
            "casebooks.build",
            "--input",
            str(path),
            "--directory",
            directory,
            "--format",
            "json",
            "--output",
            str(tmp_path / "report.json"),
        ],
        capsys,
    )
    assert "Saved:" in err and "14 days" in report["markdown"]
    assert json.loads((tmp_path / "report.json").read_text()) == report
    with Runtime(directory) as app:
        updated = app.call(
            "casebooks.save",
            {"id": saved["id"], "revision": 1, "document": project(21)},
        )
    path.write_text(json.dumps({"id": saved["id"]}))
    reopened, err = invoke(
        [
            "run",
            "casebooks.get",
            "--input",
            str(path),
            "--directory",
            directory,
            "--format",
            "json",
        ],
        capsys,
    )
    assert reopened == updated and not err
    path.write_text(json.dumps({"report": report}))
    identifier, err = invoke(
        [
            "run",
            "reports.save",
            "--input",
            str(path),
            "--directory",
            directory,
            "--format",
            "json",
        ],
        capsys,
    )
    with Runtime(directory) as app:
        assert app.call("reports.get", identifier) == report


def test_cli_exact_preview_consent_mock_provider_and_clean_stdout(tmp_path, capsys):
    directory = tmp_path / "workspace"
    with configured(Runtime(directory)):
        pass
    payload = {"template": "native-source-question", "variables": variables()}
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload))
    prepared, err = invoke(
        ["run", "template.preview", "--input", str(path), "--format", "json"], capsys
    )
    assert not err and prepared["sources"][0]["content"] == variables()["excerpt"]
    payload.update(consent=True, context_hash=prepared["context_hash"])
    path.write_text(json.dumps(payload))
    with patch(
        "sinter.templates.chat",
        return_value=client.ChatResult(
            "14 days [e1].", finish_reason="stop", model=client.NATIVE_MODEL
        ),
    ) as provider:
        result, err = invoke(
            ["run", "template.job", "--input", str(path), "--format", "json"], capsys
        )
    provider.assert_called_once()
    assert err and result["complete"] is True
    assert result["sources"][0]["sources"] == prepared["sources"]


@pytest.mark.parametrize("raw", ["[]", "{broken", '{"number":NaN}'])
def test_cli_machine_input_errors_have_stable_exit_clean_envelope(
    tmp_path, capsys, raw
):
    path = tmp_path / "input.json"
    path.write_text(raw)
    with pytest.raises(SystemExit) as exited:
        cli.main(["run", "casebooks.save", "--input", str(path), "--format", "json"])
    assert exited.value.code == 2
    result = capsys.readouterr()
    envelope = json.loads(result.out)
    assert envelope["ok"] is False and envelope["error"]["code"] == "invalid_input"
    assert "Sinter:" in result.err and "Traceback" not in result.err
    assert not (tmp_path / "workspace").exists()


def test_cli_stdout_pipeline_and_no_workspace_discovery(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"document": project()})))
    result, err = invoke(
        ["run", "casebooks.validate", "--input", "-", "--format", "json"], capsys
    )
    assert (
        result["document"]["documents"][0]["content"]
        == project()["documents"][0]["content"]
    )
    assert not err
    cli.main(["operations", "template.preview", "--format", "json"])
    assert json.loads(capsys.readouterr().out)["result"]["id"] == "template.preview"


def test_cli_output_source_alias_fails_before_runtime(tmp_path, capsys):
    path = tmp_path / "input.json"
    original = json.dumps({"document": project()})
    path.write_text(original)
    with (
        patch("sinter.runtime_cli.Runtime") as application,
        pytest.raises(SystemExit) as exited,
    ):
        cli.main(
            [
                "run",
                "casebooks.save",
                "--input",
                str(path),
                "--output",
                str(path),
                "--format",
                "json",
            ]
        )
    assert exited.value.code == 2 and path.read_text() == original
    application.assert_not_called()
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"


def test_cli_app_forwards_mode_and_directory_without_starting_second_runtime():
    with (
        patch("sinter.desktop.main", return_value=0) as desktop,
        pytest.raises(SystemExit) as exited,
    ):
        cli.main(["app", "--mode", "headless", "--directory", "fictional-workspace"])
    assert exited.value.code == 0
    desktop.assert_called_once_with(
        ["--mode", "headless", "--directory", "fictional-workspace"]
    )


def test_legacy_compact_cli_cannot_bypass_preview_consent(tmp_path):
    args = ["template", "native-source-question", "--no-stream"]
    for key, value in variables().items():
        args.extend(["--var", f"{key}={value}"])
    with (
        configured(Runtime(tmp_path / "workspace")),
        patch("sinter.templates.chat") as provider,
        pytest.raises(SystemExit) as exited,
    ):
        cli.main(args)
    assert exited.value.code == 1
    provider.assert_not_called()


def test_legacy_compact_cli_keeps_readable_source_packet(tmp_path, capsys):
    payload = {"template": "native-source-question", "variables": variables()}
    with configured(Runtime(tmp_path / "workspace")) as app:
        prepared = app.call("template.preview", payload)
    destination = tmp_path / "fictional-answer.md"
    args = [
        "template",
        "native-source-question",
        "--consent",
        "--context-hash",
        prepared["context_hash"],
        "--no-stream",
        "-o",
        str(destination),
    ]
    for key, value in variables().items():
        args.extend(["--var", f"{key}={value}"])
    with patch(
        "sinter.templates.chat",
        return_value=client.ChatResult(
            "Fictional loans last 14 days [e1].", 42, "stop", client.NATIVE_MODEL
        ),
    ) as provider:
        cli.main(args)
    readable = destination.read_text(encoding="utf-8")
    assert "UNVERIFIED MODEL DRAFT" in readable
    assert '"source_id"' in readable and "Fictional handbook.md" in readable
    assert project()["documents"][0]["content"] in readable
    assert readable.rstrip() in capsys.readouterr().out
    assert provider.call_count == 1


def test_legacy_compact_export_refuses_runtime_state_before_generation(tmp_path):
    with configured(Runtime(tmp_path / "workspace")) as app:
        database = app.app.store.directory / "workspace.sqlite3"
        prepared = app.call(
            "template.preview",
            {"template": "native-source-question", "variables": variables()},
        )
    original = database.read_bytes()
    args = [
        "template",
        "native-source-question",
        "--consent",
        "--context-hash",
        prepared["context_hash"],
        "-o",
        str(database),
    ]
    for key, value in variables().items():
        args.extend(["--var", f"{key}={value}"])
    with (
        patch(
            "sinter.templates.chat",
            return_value=client.ChatResult(
                "Fictional loans last 14 days [e1].", 42, "stop", client.NATIVE_MODEL
            ),
        ) as provider,
        pytest.raises(SystemExit) as error,
    ):
        cli.main(args)
    assert error.value.code == 1
    provider.assert_not_called()
    assert database.read_bytes() == original


def test_wait_queued_executor_job_after_close_returns_closed_immediately(tmp_path):
    gate = threading.Event()
    app = Runtime(tmp_path)
    try:
        app.app.jobs.submit(lambda progress: gate.wait(3))
        app.app.jobs.submit(lambda progress: gate.wait(3))
        queued = app.app.jobs.submit(lambda progress: {})
        app.close()
        # The cancelled executor future can remain queued in the existing ledger.
        with patch.object(
            app.app.jobs,
            "get",
            side_effect=AssertionError("Closed runtime must not poll"),
        ):
            with pytest.raises(OperationError) as error:
                app.wait(queued)
        assert error.value.code == "runtime_closed"
    finally:
        gate.set()
        app.close()


def test_close_during_wait_returns_closed_without_polling_forever(tmp_path):
    gate = threading.Event()
    arrived = threading.Event()
    errors = []
    app = Runtime(tmp_path)
    identifier = app.app.jobs.submit(lambda progress: gate.wait(3))

    def wait():
        try:
            app.wait(identifier, progress=lambda message: arrived.set())
        except OperationError as error:
            errors.append(error.code)

    thread = threading.Thread(target=wait)
    thread.start()
    try:
        assert arrived.wait(2)
        app.close()
        thread.join(timeout=1)
        assert not thread.is_alive() and errors == ["runtime_closed"]
    finally:
        gate.set()
        app.close()
        thread.join(timeout=1)


def test_closed_borrowed_runtime_wait_does_not_touch_ui_application(tmp_path):
    app = Application(tmp_path)
    try:
        facade = Runtime(application=app)
        facade.close()
        with (
            patch.object(app.jobs, "get") as get,
            patch.object(app.jobs, "cancel") as cancel,
        ):
            with pytest.raises(OperationError) as error:
                facade.wait("fictional-job")
        assert error.value.code == "runtime_closed"
        get.assert_not_called()
        cancel.assert_not_called()
        assert not app.stop.is_set()
    finally:
        app.close()


def test_close_borrowed_runtime_during_wait_leaves_ui_job_running(tmp_path):
    gate = threading.Event()
    arrived = threading.Event()
    errors = []
    app = Application(tmp_path)
    facade = Runtime(application=app)
    identifier = app.jobs.submit(
        lambda progress: (gate.wait(3), {"fictional": True})[1]
    )

    def wait():
        try:
            facade.wait(identifier, progress=lambda message: arrived.set())
        except OperationError as error:
            errors.append(error.code)

    thread = threading.Thread(target=wait)
    thread.start()
    try:
        assert arrived.wait(2)
        facade.close()
        thread.join(timeout=1)
        assert not thread.is_alive() and errors == ["runtime_closed"]
        assert not app.stop.is_set()
        assert app.jobs.get(identifier)["cancel_requested"] is False
        gate.set()
        with Runtime(application=app) as second:
            assert second.wait(identifier) == {"fictional": True}
    finally:
        gate.set()
        thread.join(timeout=1)
        app.close()


def test_cli_convenience_casebook_and_report_roundtrip_without_wrapper(
    tmp_path, capsys
):
    input_path = tmp_path / "fictional-casebook.json"
    input_path.write_text(json.dumps(project()))
    directory = str(tmp_path / "workspace")
    original, err = invoke(
        [
            "import",
            str(input_path),
            "--kind",
            "casebook",
            "--directory",
            directory,
            "--format",
            "json",
        ],
        capsys,
    )
    assert not err
    exported = tmp_path / "casebook-export.json"
    cli.main(
        [
            "export",
            "casebook",
            original["id"],
            "-o",
            str(exported),
            "--directory",
            directory,
            "--machine",
        ]
    )
    result = capsys.readouterr()
    assert json.loads(result.out)["ok"] is True and "Saved:" in result.err
    assert json.loads(exported.read_text()) == original["document"]
    other_directory = str(tmp_path / "fresh-workspace")
    imported, err = invoke(
        [
            "import",
            str(exported),
            "--kind",
            "casebook",
            "--directory",
            other_directory,
            "--format",
            "json",
        ],
        capsys,
    )
    assert (
        imported["id"] != original["id"]
        and imported["document"] == original["document"]
    )
    with Runtime(directory) as runtime:
        report = runtime.call("casebooks.build", {"id": original["id"], "revision": 1})
        report_id = runtime.call("reports.save", {"report": report})["id"]
    report_json = tmp_path / "report-export.json"
    cli.main(
        [
            "export",
            "report",
            report_id,
            "-o",
            str(report_json),
            "--directory",
            directory,
            "--machine",
        ]
    )
    assert json.loads(capsys.readouterr().out)["ok"] is True
    copied, err = invoke(
        [
            "import",
            str(report_json),
            "--kind",
            "report",
            "--directory",
            other_directory,
            "--format",
            "json",
        ],
        capsys,
    )
    with Runtime(other_directory) as runtime:
        assert runtime.call("reports.get", copied) == report
    markdown = tmp_path / "casebook-export.md"
    cli.main(
        [
            "export",
            "casebook",
            original["id"],
            "-o",
            str(markdown),
            "--directory",
            directory,
            "--format",
            "markdown",
            "--machine",
        ]
    )
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert (
        "14 days" in markdown.read_text() and "source" in markdown.read_text().lower()
    )


def test_cli_saved_casebook_envelope_import_creates_fresh_copy(tmp_path, capsys):
    with Runtime(tmp_path / "workspace") as runtime:
        saved = runtime.call("casebooks.save", {"document": project()})
    incoming = tmp_path / "saved-envelope.json"
    incoming.write_text(json.dumps(saved))
    imported, err = invoke(
        ["import", str(incoming), "--kind", "casebook", "--format", "json"], capsys
    )
    assert imported["id"] != saved["id"] and imported["revision"] == 1
    assert imported["document"] == saved["document"] and not err


@pytest.mark.parametrize(
    "name",
    [
        "workspace.sqlite3",
        "campaigns.sqlite3",
        "preferences.json",
        "accounts/chatgpt.json",
        "templates/user.json",
    ],
)
@pytest.mark.parametrize("command", ["run", "export"])
def test_cli_output_cannot_overwrite_runtime_state(tmp_path, capsys, name, command):
    directory = tmp_path / "workspace"
    with Runtime(directory) as runtime:
        saved = runtime.call("casebooks.save", {"document": project()})
    target = directory / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text("Fictional state that must be preserved")
    original = target.read_bytes()
    args = (
        ["run", "runtime.status", "--format", "json"]
        if command == "run"
        else ["export", "casebook", saved["id"], "--machine"]
    )
    with (
        patch("sinter.runtime_cli.Runtime") as application,
        pytest.raises(SystemExit) as error,
    ):
        cli.main([*args, "--directory", str(directory), "-o", str(target)])
    assert error.value.code == 2
    application.assert_not_called()
    assert target.read_bytes() == original
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"


def test_unknown_cli_operation_never_creates_workspace(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["run", "account.connect", "--format", "json"])
    assert error.value.code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "unknown_operation"
    assert not (tmp_path / "workspace").exists()


def test_cli_machine_interrupt_has_exit_130_and_one_error(tmp_path, capsys):
    with (
        patch("sinter.runtime_cli.Runtime.call", side_effect=KeyboardInterrupt),
        pytest.raises(SystemExit) as error,
    ):
        cli.main(["run", "runtime.status", "--format", "json"])
    assert error.value.code == 130
    result = capsys.readouterr()
    assert len(result.out.splitlines()) == 1
    assert json.loads(result.out)["error"]["code"] == "interrupted"
    assert "no request was replayed" in result.err


@pytest.mark.parametrize("selected", ["explicit", "environment", "relative"])
def test_workspace_path_and_export_guard_use_one_normalization(
    tmp_path, monkeypatch, capsys, selected
):
    current = tmp_path / "current"
    home = tmp_path / "home"
    current.mkdir()
    home.mkdir()
    monkeypatch.chdir(current)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    if selected == "explicit":
        directory = "~/fictional"
        expected = home / "fictional"
        arguments = ["--directory", directory]
    elif selected == "environment":
        directory = None
        expected = home / "fictional"
        arguments = []
        monkeypatch.setenv("SINTER_DATA_DIR", "~/fictional")
    else:
        directory = "fictional"
        expected = current / "fictional"
        arguments = ["--directory", directory]
    with Runtime(directory) as app:
        assert app.app.store.directory == expected
        assert app.call("runtime.status")["workspace"] == str(expected)
        database = app.app.store.path
        with pytest.raises(ValueError, match="overwrite your source"):
            app.output_sources(database)
    assert database.exists() and not (current / "~").exists()
    original = database.read_bytes()
    with (
        patch("sinter.runtime_cli.Runtime") as application,
        pytest.raises(SystemExit) as error,
    ):
        cli.main(
            [
                "run",
                "runtime.status",
                *arguments,
                "--format",
                "json",
                "-o",
                str(database),
            ]
        )
    assert error.value.code == 2 and database.read_bytes() == original
    application.assert_not_called()
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"


def test_shared_output_guard_protects_workspace_state_and_input_alias(tmp_path):
    with Runtime(tmp_path / "workspace") as app:
        source = tmp_path / "fictional.md"
        source.write_text("Fictional source text")
        target = tmp_path / "export.json"
        protected = app.output_sources(target, sources=(source,))
        assert source in protected and app.app.store.path in protected
        for path in (
            app.app.store.path,
            app.app.preferences.path,
            app.app.campaigns.path,
        ):
            with pytest.raises(ValueError, match="overwrite your source"):
                app.output_sources(path)
        for path in (
            app.app.accounts.path,
            app.app.store.directory / "templates" / "fictional.json",
        ):
            with pytest.raises(ValueError, match="account/template"):
                app.output_sources(path)
        with pytest.raises(ValueError, match="overwrite your source"):
            app.output_sources(source, sources=(source,))


def test_template_plural_aliases_remain_supported_without_workspace_discovery(
    tmp_path, capsys
):
    from sinter.runtime import describe_operation

    assert describe_operation("templates.preview")["id"] == "template.preview"
    cli.main(["operations", "templates.preview", "--format", "json"])
    assert json.loads(capsys.readouterr().out)["result"]["id"] == "template.preview"
    assert not (tmp_path / "workspace").exists()


def test_shared_export_guard_protects_legacy_user_template_root(tmp_path, capsys):
    templates = tmp_path / ".sinter" / "templates"
    templates.mkdir(parents=True)
    template = templates / "fictional.json"
    template.write_text(
        json.dumps(
            {
                "name": "Fictional template",
                "steps": [{"name": "Fictional", "prompt": "Only synthetic text"}],
            }
        )
    )
    original = template.read_bytes()
    with Runtime(tmp_path / "custom-workspace") as app:
        assert "user:fictional" in {
            row["id"] for row in app.call("templates.list")["templates"]
        }
        with pytest.raises(ValueError, match="account/template"):
            app.output_sources(template)
    with (
        patch("sinter.runtime_cli.Runtime") as application,
        pytest.raises(SystemExit) as error,
    ):
        cli.main(
            [
                "run",
                "runtime.status",
                "--directory",
                str(tmp_path / "custom-workspace"),
                "--format",
                "json",
                "-o",
                str(template),
            ]
        )
    assert error.value.code == 2 and template.read_bytes() == original
    application.assert_not_called()
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"


def test_shared_export_guard_resolves_parent_template_alias(tmp_path):
    from sinter.runtime import output_sources

    actual = tmp_path / "fictional-actual-template-directory"
    actual.mkdir()
    alias = tmp_path / ".sinter" / "templates"
    alias.parent.mkdir()
    try:
        alias.symlink_to(actual, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Directory symbolic links are unavailable: {type(exc).__name__}")
    target = actual / "fictional.json"
    target.write_text("Fictional original template")
    original = target.read_bytes()
    with pytest.raises(ValueError, match="account/template"):
        output_sources(tmp_path / "custom-workspace", target)
    assert target.read_bytes() == original


def test_real_cli_processes_use_shared_workspace_and_one_loopback_mock(tmp_path):
    """Actual process boundaries with HTTP mock framing, without real inference."""
    import os
    import subprocess
    import sys
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []

    class FictionalProvider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            assert self.path == "/v1/chat/completions"
            assert self.headers.get("Authorization") is None
            assert self.headers.get("Cookie") is None
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(body)
            result = {
                "model": "fictional-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "The fictional lending period is 14 days [e1].",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 12,
                    "total_tokens": 42,
                },
            }
            raw = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    provider = ThreadingHTTPServer(("127.0.0.1", 0), FictionalProvider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    workspace = tmp_path / "process-workspace"
    source_path = str(Path(__file__).resolve().parents[1] / "src")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "SINTER_DATA_DIR": str(workspace),
        "PYTHONPATH": source_path,
        "PYTHONDONTWRITEBYTECODE": "1",
        "NEUROFORGE_BASE_URL": f"http://127.0.0.1:{provider.server_port}/v1",
        "NEUROFORGE_MODEL": "fictional-model",
    }
    if os.name == "nt":
        for name in ("SYSTEMROOT", "WINDIR"):
            if name in os.environ:
                env[name] = os.environ[name]

    def command(*args):
        result = subprocess.run(
            [sys.executable, "-m", "sinter", *args],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
        assert len(result.stdout.splitlines()) == 1
        value = json.loads(result.stdout)
        assert value["ok"] is True
        return value["result"]

    try:
        material = tmp_path / "fictional-material.json"
        material.write_text(json.dumps(project()))
        initial = command(
            "import", str(material), "--kind", "casebook", "--format", "json"
        )
        query = tmp_path / "request.json"
        query.write_text(json.dumps({"id": initial["id"], "revision": 1}))
        report = command(
            "run", "casebooks.build", "--input", str(query), "--format", "json"
        )
        assert "14 days" in report["markdown"]
        exported = tmp_path / "process-casebook-export.json"
        command("export", "casebook", initial["id"], "-o", str(exported), "--machine")
        imported = command(
            "import",
            str(exported),
            "--kind",
            "casebook",
            "--directory",
            str(tmp_path / "process-import"),
            "--format",
            "json",
        )
        assert imported["document"] == initial["document"]
        payload = {"template": "native-source-question", "variables": variables()}
        query.write_text(json.dumps(payload))
        prepared = command(
            "run", "template.preview", "--input", str(query), "--format", "json"
        )
        assert not calls
        payload.update(consent=True, context_hash=prepared["context_hash"])
        query.write_text(json.dumps(payload))
        answer = command(
            "run", "template.job", "--input", str(query), "--format", "json"
        )
        assert (
            answer["complete"] is True and "14 days" in answer["results"][0]["content"]
        )
        assert (
            len(calls) == 1 and calls[0]["messages"] == prepared["request"]["messages"]
        )
        assert answer["sources"][0]["sources"] == prepared["sources"]
        query.write_text(
            json.dumps({"id": initial["id"], "revision": 1, "document": project(21)})
        )
        updated = command(
            "run", "casebooks.save", "--input", str(query), "--format", "json"
        )
        assert updated["revision"] == 2
        status = command("status", "--format", "json")
        assert status["counts"]["casebooks"] == 1 and status["provider_tested"] is False
        with Runtime(workspace) as runtime:
            assert runtime.call("casebooks.get", {"id": initial["id"]}) == updated
        assert len(calls) == 1  # Reopen and status do not repeat generation.
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()
