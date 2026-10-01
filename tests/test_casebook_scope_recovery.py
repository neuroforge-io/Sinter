"""Actual invalid scalars remain recoverable through UTF-8 jobs and persistence."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from unittest.mock import patch

import pytest
from test_casebook_scope import response_rows, scoped
from test_runtime import post as legacy_post
from test_runtime import request, server, wait_job  # noqa: F401

from sinter import casebooks, client
from sinter.casebook_scope import SURROGATE_ENCODING, draft_context
from sinter.operations import DeadlineExceeded


def post(instance, path, payload):
    if not path.startswith("/api/casebooks/"):
        return legacy_post(instance, path, payload)
    return request(
        instance,
        path,
        "POST",
        json.dumps(payload),
        {
            "Content-Type": "application/json",
            "X-Sinter-Token": instance.app.token,
            "X-Sinter-Casebook-Schema": "sinter-casebook/v2",
        },
    )


def decode_escaped(value):
    """Independent decoder; never let JSON combine adjacent surrogate pairs."""
    assert set(value) == {"encoding", "escaped_text"}
    assert value["encoding"] == SURROGATE_ENCODING
    text, restored, offset = value["escaped_text"], [], 0
    while offset < len(text):
        if text[offset] != "\\":
            restored.append(text[offset])
            offset += 1
        elif text.startswith("\\\\", offset):
            restored.append("\\")
            offset += 2
        else:
            assert text.startswith("\\u{", offset)
            assert text[offset + 7] == "}"
            unit = int(text[offset + 3 : offset + 7], 16)
            assert 0xD800 <= unit <= 0xDFFF
            restored.append(chr(unit))
            offset += 8
    return "".join(restored)


@pytest.mark.parametrize(
    "units", ["\ud800", "\udfff", "\ud800\udc00", "\ud800\ud800\udfff\udfff"]
)
def test_actual_invalid_content_roundtrips_exact_units_and_valid_metadata(units):
    report = casebooks.build(scoped())
    before = copy.deepcopy(report)
    rows = response_rows(draft_context(report))
    rows[0]["text"] += " literal \\u{D800} \\\\ 🐝 e\u0301 " + units
    raw = json.dumps({"sections": rows}, ensure_ascii=False)
    response = client.ChatResult(
        raw,
        prompt_tokens=9,
        completion_tokens=4,
        total_tokens=13,
        finish_reason="stop",
        model="fictional-valid-model-🐝",
    )
    with patch.object(client, "chat", return_value=response) as model:
        with pytest.raises(client.APIError) as failure:
            casebooks.draft(report, True)
        assert model.call_count == 1
    partial = failure.value.partial_result
    wire = json.dumps(
        {"error": str(failure.value), "result": partial},
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    delivered = json.loads(wire)["result"]
    assert decode_escaped(delivered["scoped_model_response"]["content"]) == raw
    assert (
        "reversible escaped representation, not verbatim Unicode text"
        in (delivered["document_markdown"])
    )
    for key, value in asdict(response).items():
        if key != "content":
            assert delivered["scoped_model_response"][key] == value
    assert delivered["source_document_markdown"] == report["document_markdown"]
    assert delivered["markdown"].endswith(report["markdown"])
    assert delivered["source_register"] == report["source_register"]
    assert delivered["excerpts"] == report["excerpts"]
    assert report == before


@pytest.mark.parametrize("field", ["model", "finish_reason"])
def test_invalid_response_metadata_is_withheld_without_changing_valid_content(field):
    report = casebooks.build(scoped())
    raw = json.dumps(
        {"sections": response_rows(draft_context(report))}, ensure_ascii=False
    )
    response = client.ChatResult(raw, finish_reason="stop", model="fictional-model")
    original = "invalid metadata 🐝 \\u{D800} \ud800\udc00"
    setattr(response, field, original)
    with patch.object(client, "chat", return_value=response) as model:
        with pytest.raises(client.APIError) as failure:
            casebooks.draft(report, True)
        assert model.call_count == 1
    partial = json.loads(
        json.dumps(failure.value.partial_result, ensure_ascii=False).encode("utf-8")
    )
    assert partial["scoped_model_response"]["content"] == raw
    assert decode_escaped(partial["scoped_model_response"][field]) == original
    assert partial["incomplete"] is True
    assert "retained verbatim below" in partial["document_markdown"]
    assert "metadata" in partial["document_markdown"]


@pytest.mark.parametrize("kind", ["error", "deadline", "partial"])
def test_invalid_error_strings_deliver_exact_escaped_original_and_safe_job_error(kind):
    report = casebooks.build(scoped())
    message = "Fictional interrupted error 🐝 \\u{D800} \ud800\udc00"
    failure = (
        client.APIError(message, 504)
        if kind == "error"
        else DeadlineExceeded(message)
        if kind == "deadline"
        else client.IncompleteGeneration(
            client.ChatResult("Valid partial 🐝", finish_reason="incomplete"),
            1024,
            message=message,
        )
    )
    original_message = str(failure)
    with patch.object(client, "chat", side_effect=failure) as model:
        with pytest.raises(type(failure)) as raised:
            casebooks.draft(report, True)
        assert model.call_count == 1
    wire = json.dumps(
        {"error": str(raised.value), "result": raised.value.partial_result},
        ensure_ascii=False,
    ).encode("utf-8")
    delivered = json.loads(wire)
    assert (
        decode_escaped(delivered["result"]["generation_error"]["original_message"])
        == original_message
    )
    assert "Reversible escaped representation" in delivered["error"]
    assert (
        delivered["result"]["source_document_markdown"] == report["document_markdown"]
    )


@pytest.mark.parametrize("kind", ["content", "metadata", "error"])
def test_actual_http_job_delivers_and_saves_invalid_unicode_recovery(server, kind):  # noqa: F811
    code, _, encoded = post(server, "/api/casebooks/save", {"document": scoped()})
    assert code == 200
    saved = json.loads(encoded)
    source = casebooks.build(saved["document"])
    rows = response_rows(draft_context(source))
    response = client.ChatResult(
        json.dumps({"sections": rows}, ensure_ascii=False),
        finish_reason="stop",
        model="fictional-model",
    )
    if kind == "content":
        rows[0]["text"] += " Actual invalid units \ud800\udc00 literal \\u{D800} 🐝"
        response.content = json.dumps({"sections": rows}, ensure_ascii=False)
    elif kind == "metadata":
        response.model = "Fictional invalid model \ud800\udc00"
    outcome = (
        client.APIError("Fictional error \ud800", 504) if kind == "error" else response
    )
    expected_error = str(outcome) if isinstance(outcome, Exception) else None
    with (
        patch.object(
            client, "_open", side_effect=AssertionError("No hosted calls")
        ) as remote,
        patch.object(
            client,
            "chat",
            side_effect=outcome if isinstance(outcome, Exception) else None,
            return_value=response,
        ) as model,
    ):
        code, _, encoded = post(
            server,
            "/api/casebooks/draft",
            {
                "id": saved["id"],
                "revision": saved["revision"],
                "consent": True,
                "fingerprint": source["casebook_fingerprint"],
            },
        )
        assert code == 202
        identifier = json.loads(encoded)["id"]
        job = wait_job(server.app.jobs, identifier)
        assert job["status"] == "failed"
        code, _, encoded = request(server, "/api/jobs/" + identifier)
        assert code == 200
        delivered = json.loads(encoded.decode("utf-8"))
        assert delivered["status"] == "failed"
        partial = delivered["result"]
        assert partial["incomplete"] is True
        assert partial["source_document_markdown"] == source["document_markdown"]
        assert partial["excerpts"] == source["excerpts"]
        if kind == "error":
            assert (
                decode_escaped(partial["generation_error"]["original_message"])
                == expected_error
            )
        else:
            field = "content" if kind == "content" else "model"
            assert decode_escaped(partial["scoped_model_response"][field]) == getattr(
                response, field
            )
        code, _, encoded = post(server, "/api/reports", {"report": partial})
        assert code == 201
        stored = server.app.store.report(json.loads(encoded)["id"])
        assert stored == partial
        assert server.app.casebooks.get(saved["id"]) == saved
        assert model.call_count == 1
        remote.assert_not_called()


def test_native_scope_progress_never_claims_a_request_was_sent(monkeypatch):
    monkeypatch.setenv("NEUROFORGE_MODEL", client.NATIVE_MODEL)
    messages = []
    with patch.object(
        client, "_open", side_effect=AssertionError("No hosted calls")
    ) as remote:
        with pytest.raises(ValueError):
            casebooks.draft(casebooks.build(scoped()), True, messages.append)
        remote.assert_not_called()
    assert messages == ["Preparing the previewed, bounded evidence request"]
