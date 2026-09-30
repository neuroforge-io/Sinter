"""Portable public gateway contract fixtures; no origin or live generation.

The fixture is copied verbatim from NeuroForge's build_native_model_contract_fixtures
output. Its source hashes describe the gateway contract, not live answer quality.
"""

import hashlib
import json
from pathlib import Path

import pytest

from sinter import client
from sinter.model_profiles import (
    NATIVE_CAPABILITIES,
    NATIVE_CONTRACT_VERSION,
    NATIVE_PROFILE,
    native_reply,
    native_request,
)
from sinter.providers import ProviderProtocolError

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures/public_native_model_api_contract.v1.json"
)
PACK = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
CASES = PACK["cases"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(
        client.urllib.request,
        "build_opener",
        lambda *args: pytest.fail("unexpected outbound request"),
    )


def test_public_native_fixture_version_identity_and_capabilities_are_exact():
    assert hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest() == (
        "711feb4f774674d4e4c6ab7dbe77dada7668004d4be0014445256a03a0f5edc4"
    )
    assert (
        PACK["contract"]
        == f"neuroforge.public-native-model-client-fixtures.v{NATIVE_CONTRACT_VERSION}"
    )
    assert PACK["model"] == client.NATIVE_MODEL
    assert PACK["capabilities"] == NATIVE_CAPABILITIES
    assert PACK["limits"] == {
        "request_body_bytes": NATIVE_PROFILE.request_bytes,
        "response_body_bytes": NATIVE_PROFILE.response_bytes,
        "edge_deadline_ms": NATIVE_PROFILE.deadline_seconds * 1000,
        "min_output_tokens": NATIVE_PROFILE.min_output_tokens,
        "max_output_tokens": NATIVE_PROFILE.max_output_tokens,
        "default_output_tokens": NATIVE_PROFILE.max_output_tokens,
        "max_prompt_tokens": NATIVE_PROFILE.max_prompt_tokens,
        "max_prompt_bytes": NATIVE_PROFILE.max_question_bytes,
        "max_history_bytes": NATIVE_PROFILE.max_history_bytes,
        "max_history_exchanges": NATIVE_PROFILE.max_history_exchanges,
        "max_output_bytes": NATIVE_PROFILE.max_output_bytes,
    }
    assert (
        PACK["token_budget_preflight"]
        == "not_exposed_without_installed_origin_acceptance"
    )
    assert set(PACK["source_sha256"]) >= {
        "workers/public_model_api.mjs",
        "workers/native_model_api_contract.mjs",
        "static/openapi.json",
        "docs/releases/NATIVE_CONSUMER_CUTOVER_20260929.json",
    }
    assert all(
        isinstance(digest, str)
        and len(digest) == 64
        and set(digest) <= set("0123456789abcdef")
        for digest in PACK["source_sha256"].values()
    )


def test_installed_audio_vision_and_tokenizer_do_not_expand_public_text_contract():
    installed = next(
        row
        for row in CASES
        if row["name"] == "installed-007-audio-origin-projected-to-text"
    )
    origin = installed["upstream"]["json"]["data"][0]["erais"]
    public = installed["expected"]["body"]["data"][0]["erais"]
    assert origin["modalities"] == ["text", "image", "audio"]
    assert origin["token_budget_endpoint"] == "/v1/tokenize"
    assert public["modalities"] == ["text"]
    assert set(public) == set(NATIVE_CAPABILITIES) | {"modalities", "runtime_id"}
    assert public["runtime_id"] == origin["runtime_id"]
    for name, path in [
        ("advertised-origin-tokenize-not-publicly-qualified", "/v1/tokenize"),
        ("installed-origin-audio-not-publicly-qualified", "/v1/audio/speech"),
        ("token-budget-preflight-unavailable", "/v1/chat/preflight"),
    ]:
        case = next(row for row in CASES if row["name"] == name)
        assert case["path"] == path
        assert case["expected"]["status"] == 404
        assert case["expected"]["body"]["error"]["code"] == "not_found"
        assert case["expected"]["forwarded"] is None
    media = next(row for row in CASES if row["name"] == "media-rejected")
    assert media["expected"]["status"] == 400
    assert media["expected"]["forwarded"] is None


@pytest.mark.parametrize(
    "case",
    [
        row
        for row in CASES
        if row["method"] == "POST" and row["expected"]["status"] == 200
    ],
    ids=lambda row: row["name"],
)
def test_native_request_and_complete_reply_match_successful_public_cases(case):
    request = native_request(case["request"])
    assert request == case["expected"]["forwarded"]["request"]
    assert request["messages"] == case["request"]["messages"]
    reply = native_reply(case["expected"]["body"], request["max_tokens"])
    assert reply.content == case["expected"]["body"]["choices"][0]["message"]["content"]
    assert (
        reply.finish_reason == case["expected"]["body"]["choices"][0]["finish_reason"]
    )
    # A buffered completion does not attest which runtime owner produced it.
    assert "runtime_id" not in case["expected"]["body"]


@pytest.mark.parametrize(
    "case",
    [
        row
        for row in CASES
        if row["path"] == "/v1/chat/completions"
        and row["expected"]["status"] in {400, 413}
        and row.get("upstream") is None
    ],
    ids=lambda row: row["name"],
)
def test_native_request_rejects_exact_public_admission_failures(case):
    with pytest.raises(ValueError):
        native_request(case["request"])


@pytest.mark.parametrize(
    "case",
    [
        row
        for row in CASES
        if row["method"] == "GET" and row["expected"]["status"] == 200
    ],
    ids=lambda row: row["name"],
)
def test_native_discovery_qualifies_only_projected_public_text_metadata(case):
    settings = {
        "provider": "openai-compatible",
        "api_url": client.BASE_URL,
        "model": "auto",
        "max_tokens": 128,
    }
    with client.connection_settings(settings):
        assert (
            client.resolve_model(case["expected"]["body"]["data"])
            == client.NATIVE_MODEL
        )
    metadata = case["expected"]["body"]["data"][0]["erais"]
    assert metadata["modalities"] == ["text"]
    assert metadata["assistant_quality"] is False


@pytest.mark.parametrize(
    "case",
    [
        row
        for row in CASES
        if row["method"] == "GET" and row["expected"]["status"] == 502
    ],
    ids=lambda row: row["name"],
)
def test_native_invalid_origin_identity_is_not_accepted_as_public_metadata(case):
    settings = {
        "provider": "openai-compatible",
        "api_url": client.BASE_URL,
        "model": "auto",
        "max_tokens": 128,
    }
    with client.connection_settings(settings), pytest.raises(client.APIError):
        client.resolve_model(case["upstream"]["json"]["data"])


@pytest.mark.parametrize(
    "case",
    [
        row
        for row in CASES
        if row["name"].startswith("upstream-")
        and isinstance(row.get("upstream", {}).get("json"), dict)
    ],
    ids=lambda row: row["name"],
)
def test_native_invalid_completion_matches_public_gateway_rejection(case):
    assert case["expected"]["status"] == 502
    with pytest.raises(ProviderProtocolError):
        native_reply(case["upstream"]["json"], case["request"].get("max_tokens", 128))
