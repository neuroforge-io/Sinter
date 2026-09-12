"""Credentials follow the selected destination through both CLI and UI paths."""
import io
import urllib.request
import urllib.response
from contextlib import nullcontext
from unittest.mock import patch

import pytest

from sinter import client
from sinter.preferences import Preferences


@pytest.fixture
def credentials(tmp_path, monkeypatch):
    for name in ("NEUROFORGE_API_KEY", "NEUROFORGE_BASE_URL", "SINTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    key_file = tmp_path / "fictional-key"
    key_file.write_text("NEUROFORGE_API_KEY=fictional-saved-key\n")
    monkeypatch.setattr(client, "_KEY_FILE", key_file)
    return Preferences(tmp_path)


def request_headers(preferences, ui: bool) -> dict[str, str]:
    """Exercise the real request construction without contacting a provider."""
    context = (client.connection_settings(preferences.connection())
               if ui else nullcontext())
    with context, patch.object(urllib.request, "build_opener") as factory:
        factory.return_value.open.return_value = io.BytesIO(b'{"data": []}')
        assert client.list_models() == []
    assert isinstance(factory.call_args.args[0], client._NoRedirect)
    return dict(factory.return_value.open.call_args.args[0].header_items())


@pytest.mark.parametrize("ui", [False, True], ids=["cli", "ui"])
@pytest.mark.parametrize("base", [
    "https://custom.example/v1", "http://127.0.0.1:8421/v1",
    "http://localhost:8421/v1", "http://[::1]:8421/v1",
    "https://neuroforge.io:8443/v1", "https://neuroforge.io/custom",
    "https://neuroforge.io.example/v1",
])
@pytest.mark.parametrize("environment_key", ["", "fictional-public-env-key"])
def test_custom_destination_never_loads_public_key(
    credentials, monkeypatch, ui, base, environment_key,
):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", base)
    monkeypatch.setenv("NEUROFORGE_API_KEY", environment_key)
    with patch.object(client, "_load_key", side_effect=AssertionError("key leak")):
        assert "Authorization" not in request_headers(credentials, ui)


@pytest.mark.parametrize("ui", [False, True], ids=["cli", "ui"])
@pytest.mark.parametrize("base", [None, client.BASE_URL, "https://NEUROFORGE.io:443/v1/"])
@pytest.mark.parametrize("environment_key", ["", "fictional-public-env-key"])
def test_official_destination_retains_saved_and_environment_credentials(
    credentials, monkeypatch, ui, base, environment_key,
):
    if base:
        monkeypatch.setenv("NEUROFORGE_BASE_URL", base)
    monkeypatch.setenv("NEUROFORGE_API_KEY", environment_key)
    expected = environment_key or "fictional-saved-key"
    assert request_headers(credentials, ui)["Authorization"] == f"Bearer {expected}"


@pytest.mark.parametrize("ui", [False, True], ids=["cli", "ui"])
@pytest.mark.parametrize("base", ["https://custom.example/v1", "http://127.0.0.1:8421/v1"])
def test_explicit_custom_environment_key(credentials, monkeypatch, ui, base):
    monkeypatch.setenv("NEUROFORGE_BASE_URL", base)
    monkeypatch.setenv("SINTER_API_KEY", "fictional-custom-key")
    monkeypatch.setenv("NEUROFORGE_API_KEY", "fictional-public-env-key")
    assert request_headers(credentials, ui)["Authorization"] == "Bearer fictional-custom-key"


def test_ui_session_key_is_destination_bound(credentials, monkeypatch):
    base = "https://custom.example/v1"
    credentials.update({"api_url": base}, confirm_endpoint=True,
                       api_key="fictional-session-key")
    assert request_headers(credentials, True)["Authorization"] == "Bearer fictional-session-key"
    monkeypatch.setenv("NEUROFORGE_BASE_URL", "https://other.example/v1")
    assert "Authorization" not in request_headers(credentials, True)


def test_custom_environment_key_requires_matching_explicit_url(credentials, monkeypatch):
    credentials.update({"api_url": "https://custom.example/v1"}, confirm_endpoint=True)
    monkeypatch.setenv("SINTER_API_KEY", "fictional-custom-key")
    assert "Authorization" not in request_headers(credentials, True)
    monkeypatch.setenv("NEUROFORGE_BASE_URL", "https://other.example/v1")
    with client.connection_settings({"api_url": "https://custom.example/v1",
                                     "inherit_key": True}):
        assert "Authorization" not in client._headers()


def test_inherit_flag_cannot_override_destination_policy(credentials):
    with client.connection_settings({"api_url": "https://custom.example/v1",
                                     "inherit_key": True}):
        assert "Authorization" not in client._headers()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_authorized_request_cannot_follow_redirect(credentials, status):
    requests = []

    class RedirectingService(urllib.request.HTTPSHandler):
        def https_open(self, request):
            requests.append(request)
            response = urllib.response.addinfourl(
                io.BytesIO(), {"location": "https://other.example/models"},
                request.full_url, status,
            )
            response.msg = "Found"
            return response

    opener = urllib.request.build_opener(client._NoRedirect(), RedirectingService())
    with patch.object(urllib.request, "build_opener", return_value=opener):
        with pytest.raises(client.APIError, match=f"HTTP {status}"):
            client.list_models()
    assert len(requests) == 1
    assert requests[0].get_header("Authorization") == "Bearer fictional-saved-key"
