"""Cached interfaces must not broaden v2 evidence through current adapters."""

from __future__ import annotations

import copy
import json
from http.client import HTTPConnection
from unittest.mock import patch

import pytest
from test_casebook_scope import project, scoped
from test_runtime import post, request, server  # noqa: F401

from sinter import casebooks, cli, client
from sinter.runtime import OperationError, Runtime
from sinter.store import Store

SCHEMA = "sinter-casebook/v2"
HEADER = "X-Sinter-Casebook-Schema"


def old_reconstruction(document):
    """The old page rebuilds known v1 fields and omits unfamiliar choices."""
    return {
        **{
            key: value
            for key, value in document.items()
            if key not in {"question_scopes", "fingerprint"}
        },
        "schema": "sinter-casebook/v1",
    }


def protocol_request(instance, path, method="GET", payload=None, capability=None):
    connection = HTTPConnection("127.0.0.1", instance.server_port, timeout=5)
    raw = json.dumps(payload) if payload is not None else None
    try:
        connection.putrequest(method, path)
        if raw is not None:
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", str(len(raw.encode())))
            connection.putheader("X-Sinter-Token", instance.app.token)
        for value in capability or []:
            connection.putheader(HEADER, value)
        connection.endheaders(raw.encode() if raw is not None else None)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


@pytest.mark.parametrize("field", ["absent", None, False, True, "[]", {}, [False]])
def test_cached_same_id_save_cannot_erase_scopes_or_change_any_local_state(
    tmp_path, field
):
    store = Store(tmp_path)
    repository = casebooks.Casebooks(store)
    saved = repository.save(scoped())
    report = casebooks.build(saved["document"])
    history = store.save_report(report)
    old_payload = old_reconstruction(saved["document"])
    if field != "absent":
        old_payload["question_scopes"] = field
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        repository.save(old_payload, saved["id"], saved["revision"])
    assert store.path.read_bytes() == before
    assert repository.get(saved["id"]) == saved
    assert store.report(history) == report


def test_explicit_clear_is_atomic_normalized_v1_and_does_not_change_originals(tmp_path):
    store = Store(tmp_path)
    repository = casebooks.Casebooks(store)
    saved = repository.save(scoped([]))
    # An explicit zero-source choice remains v2; only the whole typed empty list
    # is the deliberate all-sources transition.
    original = copy.deepcopy(saved)
    cleared = repository.save(
        {**old_reconstruction(saved["document"]), "question_scopes": []}, saved["id"], 1
    )
    assert cleared["revision"] == 2
    assert "question_scopes" not in cleared["document"]
    assert cleared["document"] == casebooks.validate(project())
    assert cleared["document"]["documents"] == original["document"]["documents"]
    assert repository.get(saved["id"]) == cleared
    # Ordinary subsequent legacy saves need no new intent marker.
    assert repository.save(cleared["document"], saved["id"], 2)["revision"] == 3


@pytest.mark.parametrize(
    "capability",
    [
        None,
        [""],
        ["sinter-casebook/v1"],
        [SCHEMA + ", " + SCHEMA],
        [SCHEMA, SCHEMA],
        [SCHEMA, "sinter-casebook/v1"],
    ],
)
@pytest.mark.parametrize(
    "route", ["get", "head", "validate", "save_new", "save_clear", "build", "draft"]
)
def test_incompatible_reader_refuses_before_result_mutation_or_provider(
    server,  # noqa: F811
    capability,
    route,  # noqa: F811
):
    saved = server.app.casebooks.save(scoped())
    before = server.app.store.path.read_bytes()
    path, method, payload = "/api/casebooks/" + saved["id"], "GET", None
    if route == "head":
        method = "HEAD"
    elif route in {"validate", "save_new"}:
        path, method = (
            "/api/casebooks/" + ("save" if route == "save_new" else route),
            "POST",
        )
        payload = {"document": saved["document"]}
    elif route == "save_clear":
        path, method = "/api/casebooks/save", "POST"
        payload = {
            "id": saved["id"],
            "revision": 1,
            "document": {
                **old_reconstruction(saved["document"]),
                "question_scopes": [],
            },
        }
    elif route in {"build", "draft"}:
        path, method = "/api/casebooks/" + route, "POST"
        payload = {
            "id": saved["id"],
            "revision": 1,
            "consent": True,
            "fingerprint": saved["document"]["fingerprint"],
        }
    with (
        patch.object(
            server.app,
            "connection",
            side_effect=AssertionError("No provider resolution"),
        ) as connection,
        patch.object(
            client, "_open", side_effect=AssertionError("No hosted calls")
        ) as remote,
    ):
        code, raw = protocol_request(server, path, method, payload, capability)
        assert code == 400
        if route != "head":
            assert "this interface cannot preserve" in json.loads(raw)["error"]
            assert "question_scopes" not in json.loads(raw)
        assert not server.app.jobs.list()
        connection.assert_not_called()
        remote.assert_not_called()
    assert server.app.store.path.read_bytes() == before
    assert server.app.casebooks.get(saved["id"]) == saved


def test_exact_capability_open_restore_save_and_explicit_clear_preserve_sources(server):  # noqa: F811
    saved = server.app.casebooks.save(scoped())
    code, raw = protocol_request(
        server, "/api/casebooks/" + saved["id"], capability=[SCHEMA]
    )
    assert code == 200 and json.loads(raw) == saved
    code, raw = protocol_request(
        server,
        "/api/casebooks/validate",
        "POST",
        {"document": saved["document"]},
        [SCHEMA],
    )
    assert code == 200 and json.loads(raw)["document"] == saved["document"]
    code, raw = protocol_request(
        server, "/api/casebooks/save", "POST", {"document": saved["document"]}, [SCHEMA]
    )
    clone = json.loads(raw)
    assert code == 200 and clone["id"] != saved["id"]
    assert clone["document"] == saved["document"]
    # Same-ID cached save is independently guarded, even if a caller spoofs
    # capability but omits the deliberate-clear marker.
    old = old_reconstruction(saved["document"])
    code, raw = protocol_request(
        server,
        "/api/casebooks/save",
        "POST",
        {"id": saved["id"], "revision": 1, "document": old},
        [SCHEMA],
    )
    assert code == 400 and "saved source choices" in json.loads(raw)["error"]
    assert server.app.casebooks.get(saved["id"]) == saved
    code, raw = protocol_request(
        server,
        "/api/casebooks/save",
        "POST",
        {"id": saved["id"], "revision": 1, "document": {**old, "question_scopes": []}},
        [SCHEMA],
    )
    assert code == 200
    clear = json.loads(raw)
    assert clear["document"]["schema"] == "sinter-casebook/v1"
    assert clear["document"]["documents"] == saved["document"]["documents"]
    assert protocol_request(server, "/api/casebooks/" + saved["id"])[0] == 200
    assert server.app.casebooks.get(clone["id"]) == clone


def test_legacy_http_requests_work_without_capability(server):  # noqa: F811
    code, _, raw = post(server, "/api/casebooks/save", {"document": project()})
    assert code == 200
    saved = json.loads(raw)
    assert json.loads(request(server, "/api/casebooks/" + saved["id"])[2]) == saved
    assert post(server, "/api/casebooks/validate", {"document": project()})[0] == 200
    assert (
        post(server, "/api/casebooks/build", {"id": saved["id"], "revision": 1})[0]
        == 202
    )


def test_runtime_requires_explicit_lossless_caller_and_preserves_v1(tmp_path):
    with Runtime(tmp_path) as runtime:
        ordinary = runtime.call("casebooks.save", {"document": project()})
        assert runtime.call("casebooks.get", {"id": ordinary["id"]}) == ordinary
        with pytest.raises(OperationError, match="this interface cannot preserve"):
            runtime.call("casebooks.save", {"document": scoped()})
        chosen = runtime.call(
            "casebooks.save", {"document": scoped()}, casebook_schema=SCHEMA
        )
        with pytest.raises(OperationError, match="this interface cannot preserve"):
            runtime.call(
                "casebooks.save",
                {
                    "id": chosen["id"],
                    "revision": 1,
                    "document": {
                        **old_reconstruction(chosen["document"]),
                        "question_scopes": [],
                    },
                },
            )
        for operation, payload in [
            ("casebooks.get", {"id": chosen["id"]}),
            ("casebooks.validate", {"document": chosen["document"]}),
            ("casebooks.build", {"id": chosen["id"], "revision": 1}),
            ("casebooks.draft", {"id": chosen["id"], "revision": 1}),
        ]:
            with pytest.raises(OperationError, match="this interface cannot preserve"):
                runtime.call(operation, payload)
        assert (
            runtime.call("casebooks.get", {"id": chosen["id"]}, casebook_schema=SCHEMA)
            == chosen
        )
        report = runtime.call(
            "casebooks.build",
            {"id": chosen["id"], "revision": 1},
            casebook_schema=SCHEMA,
        )
        assert report["question_scopes"] == chosen["document"]["question_scopes"]
        assert not report.get("model_draft")


def test_current_cli_lossless_import_export_and_call_preserve_v2(tmp_path, capsys):
    workspace, original, exported = (
        tmp_path / "workspace",
        tmp_path / "input.json",
        tmp_path / "export.json",
    )
    original.write_text(json.dumps(scoped()), encoding="utf-8")
    with patch.object(
        client, "_open", side_effect=AssertionError("No hosted calls")
    ) as remote:
        cli.main(
            [
                "import",
                str(original),
                "--kind",
                "casebook",
                "--directory",
                str(workspace),
                "--format",
                "json",
            ]
        )
        saved = json.loads(capsys.readouterr().out)["result"]
        cli.main(
            [
                "export",
                "casebook",
                saved["id"],
                "--directory",
                str(workspace),
                "--machine",
                "-o",
                str(exported),
            ]
        )
        assert json.loads(capsys.readouterr().out)["ok"] is True
        assert json.loads(exported.read_text(encoding="utf-8")) == saved["document"]
        original.write_text(json.dumps({"id": saved["id"]}), encoding="utf-8")
        cli.main(
            [
                "run",
                "casebooks.get",
                "--input",
                str(original),
                "--directory",
                str(workspace),
                "--format",
                "json",
            ]
        )
        assert json.loads(capsys.readouterr().out)["result"] == saved
        remote.assert_not_called()
