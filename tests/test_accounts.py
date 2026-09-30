"""Account sign-in uses real signed identities and the real loopback callback."""
import base64
import hashlib
import json
import stat
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from sinter import accounts


@pytest.fixture
def manager(tmp_path):
    instance = accounts.AccountManager(tmp_path)
    yield instance
    instance.close()


@pytest.fixture
def signer():
    jwt = pytest.importorskip("jwt")
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test-signing-key", use="sig", alg="RS256")

    def sign(attempt, **changes):
        claims = {"iss": accounts.AUTHORITY,
                  "aud": attempt.client_id or "oaiapp_fictional",
                  "sub": "account-one", "nonce": attempt.nonce,
                  "exp": int(time.time()) + 3600,
                  "email": "one@example.test", "name": "Account One"}
        claims.update(changes)
        return jwt.encode(claims, key, algorithm="RS256",
                          headers={"kid": "test-signing-key"})

    return {"keys": [jwk]}, sign


def mock_service(monkeypatch, manager, signer, *, scope=accounts.SCOPES,
                 changes=None, fail=None):
    jwks, sign = signer
    requests = []

    def request(url, fields=None, **kwargs):
        requests.append((url, fields, kwargs))
        if fail:
            raise accounts.AccountError(fail)
        if url == accounts.JWKS_URL:
            return jwks
        if url == accounts.REVOKE_URL:
            return {}
        return {"access_token": "protected-access-one",
                "refresh_token": "protected-refresh-one",
                "id_token": sign(manager._pending, **(changes or {})),
                "token_type": "Bearer", "expires_in": 3600,
                "scope": scope}

    monkeypatch.setattr(manager, "_request", request)
    return requests


def complete(manager, **overrides):
    attempt = manager._pending
    fields = {"state": attempt.state, "code": "fictional-auth-code",
              "client_id": attempt.client_id or "oaiapp_fictional"}
    fields.update(overrides)
    manager._callback(attempt, fields)
    return attempt


def test_host_and_permissions_persist_without_credentials(manager, tmp_path):
    host = manager._read()["host_id"]
    second = accounts.AccountManager(tmp_path)
    assert second._read()["host_id"] == host
    assert host.startswith("urn:uuid:")
    assert manager.status()["connected"] is False
    if accounts.os.name != "nt":
        assert stat.S_IMODE(manager.path.stat().st_mode) == 0o600
        assert stat.S_IMODE(manager.directory.stat().st_mode) == 0o700
    second.close()


def test_missing_optional_dependency_is_explained(manager, monkeypatch):
    monkeypatch.setattr(accounts.importlib.util, "find_spec", lambda name: None)
    assert manager.status()["available"] is False
    assert "accounts extra" in manager.status()["message"]
    with pytest.raises(accounts.AccountError, match="accounts extra"):
        manager.start()
    assert manager.status()["pending"] is None


def test_frozen_build_missing_accounts_has_actionable_build_help(manager, monkeypatch):
    monkeypatch.setattr(accounts.sys, "frozen", True, raising=False)
    monkeypatch.setattr(accounts.importlib.util, "find_spec", lambda name: None)
    status = manager.status()
    assert status["available"] is False
    assert "unavailable in this Sinter build" in status["message"]
    assert "source installation" in status["message"]
    assert "Install Sinter's accounts extra" not in status["message"]
    with pytest.raises(accounts.AccountError, match="unavailable in this Sinter build"):
        manager.start()
    with pytest.raises(accounts.AccountError, match="unavailable in this Sinter build"):
        manager.connection()["account_token"]()


def test_start_has_exact_pkce_loopback_contract(manager, signer):
    first = manager.start()
    attempt = manager._pending
    parsed = urlsplit(first["auth_url"])
    query = parse_qs(parsed.query)
    assert parsed.scheme + "://" + parsed.netloc + parsed.path == accounts.AUTHORIZE_URL
    assert query["client_id"] == ["dynamic_agent_client"]
    assert query["agent_name_hint"] == ["Sinter"]
    assert query["ext_agent_host_id"] == [manager._read()["host_id"]]
    assert query["scope"] == [accounts.SCOPES]
    assert query["resource"] == [accounts.RESOURCE]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    expected = base64.urlsafe_b64encode(hashlib.sha256(
        attempt.verifier.encode()).digest()).decode().rstrip("=")
    assert query["code_challenge"] == [expected]
    assert query["redirect_uri"] == [attempt.redirect_uri]
    redirect = urlsplit(attempt.redirect_uri)
    assert redirect.hostname == "127.0.0.1"
    assert redirect.path == "/auth/callback"
    manager.cancel()
    manager.start()
    assert manager._pending.state != attempt.state
    assert manager._pending.nonce != attempt.nonce
    assert manager._pending.verifier != attempt.verifier


def test_real_loopback_callback_and_safe_status(manager, signer, monkeypatch):
    requests = mock_service(monkeypatch, manager, signer)
    manager.start()
    attempt = manager._pending
    callback = attempt.redirect_uri + "?" + urlencode({
        "state": attempt.state, "code": "fictional-auth-code",
        "client_id": "oaiapp_fictional"})
    with urllib.request.urlopen(callback, timeout=5) as response:
        assert response.status == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert "Return to Sinter" in response.read().decode()
    status = manager.status()
    assert status["connected"] is True
    assert status["plan_usage"] is True
    assert status["pending"]["status"] == "complete"
    assert status["profiles"][0]["email"] == "one@example.test"
    exposed = json.dumps(status)
    for secret in ("protected-access", "protected-refresh", "id_token",
                   attempt.state, attempt.nonce, attempt.verifier, "auth_url"):
        assert secret not in exposed
    token_fields = next(row[1] for row in requests if row[0] == accounts.TOKEN_URL)
    assert token_fields == {
        "grant_type": "authorization_code", "client_id": "oaiapp_fictional",
        "code": "fictional-auth-code", "code_verifier": attempt.verifier,
        "redirect_uri": attempt.redirect_uri, "resource": accounts.RESOURCE}
    assert manager.access_token() == "protected-access-one"


@pytest.mark.parametrize("override", [
    {"state": "wrong-state"}, {"state": "untrusted-\u00e9"}, {"client_id": ""},
    {"client_id": "dynamic_agent_client"}, {"code": ""},
])
def test_bad_callback_never_exchanges_code(manager, signer, monkeypatch, override):
    requests = mock_service(monkeypatch, manager, signer)
    manager.start()
    with pytest.raises(accounts.AccountError):
        complete(manager, **override)
    assert requests == []
    assert manager.status()["connected"] is False


@pytest.mark.parametrize("error, message", [
    ("access_denied", "ChatGPT did not authorise this sign-in."),
    ("server_error", "ChatGPT sign-in could not be completed."),
])
def test_provider_failure_is_truthful_and_never_exchanges_code(
    manager, signer, monkeypatch, error, message,
):
    requests = mock_service(monkeypatch, manager, signer)
    manager.start()
    with pytest.raises(accounts.AccountError, match=message):
        complete(manager, error=error,
                 error_description="untrusted-private-provider-diagnostic")
    assert requests == []
    assert manager.status()["pending"]["status"] == "failed"
    assert "declined" not in manager.status()["pending"]["message"]
    assert "untrusted-private" not in json.dumps(manager.status())


@pytest.mark.parametrize("terminal", ["failed", "expired"])
def test_local_cancel_dismisses_failure_race_without_changing_active_account(
    manager, signer, monkeypatch, terminal,
):
    requests = mock_service(monkeypatch, manager, signer)
    manager.start()
    complete(manager)
    connected = manager._read()
    manager.start()
    attempt = manager._pending
    if terminal == "failed":
        with pytest.raises(accounts.AccountError, match="did not authorise"):
            complete(manager, error="access_denied")
    else:
        manager._expire(attempt)
    before_cancel = len(requests)
    status = manager.cancel()
    assert status["pending"]["status"] == "cancelled"
    assert status["pending"]["message"] == "Sign-in cancelled."
    assert status["connected"] is True
    assert manager._read() == connected
    # A late callback cannot turn the dismissed attempt into a failure or
    # connect another account after the user pressed the local Cancel button.
    with pytest.raises(accounts.AccountError, match="did not match"):
        complete(manager, error="access_denied")
    assert manager.status()["pending"]["status"] == "cancelled"
    assert len(requests) == before_cancel


def test_local_cancel_cannot_undo_completed_sign_in(manager, signer, monkeypatch):
    mock_service(monkeypatch, manager, signer)
    manager.start()
    complete(manager)
    connected = manager._read()
    assert manager.cancel()["pending"]["status"] == "complete"
    assert manager._read() == connected


@pytest.mark.parametrize("changes", [
    {"nonce": "incorrect"}, {"iss": "https://attacker.example"},
    {"aud": "another-client"}, {"exp": int(time.time()) - 10}, {"sub": ""},
])
def test_real_signature_does_not_override_invalid_claims(
    manager, signer, monkeypatch, changes,
):
    mock_service(monkeypatch, manager, signer, changes=changes)
    manager.start()
    with pytest.raises(accounts.AccountError):
        complete(manager)
    assert manager.status()["connected"] is False
    assert manager.status()["pending"]["status"] == "failed"
    saved = manager._read()["profiles"][manager._pending.profile_id]
    assert saved == {"client_id": "oaiapp_fictional"}


def test_signed_identity_with_no_plan_scope_cannot_infer(manager, signer, monkeypatch):
    mock_service(monkeypatch, manager, signer, scope="openid profile email")
    manager.start()
    complete(manager, scope=accounts.SCOPES)
    assert manager.status()["connected"] is True
    assert manager.status()["plan_usage"] is False
    with pytest.raises(accounts.AccountError, match="Allow Sinter"):
        manager.access_token()


def test_registration_saved_before_failed_exchange(manager, signer, monkeypatch):
    mock_service(monkeypatch, manager, signer, fail="Code expired. Sign in again.")
    manager.start()
    with pytest.raises(accounts.AccountError, match="Code expired"):
        complete(manager)
    identity = manager._pending.profile_id
    assert manager._read()["profiles"][identity] == {"client_id": "oaiapp_fictional"}
    result = manager.start(identity)
    query = parse_qs(urlsplit(result["auth_url"]).query)
    assert query["client_id"] == ["oaiapp_fictional"]
    assert "agent_name_hint" not in query


def test_reauthorization_retains_registration_and_checks_identity(
    manager, signer, monkeypatch,
):
    mock_service(monkeypatch, manager, signer)
    manager.start()
    complete(manager)
    original = manager.status()["active_profile_id"]
    query = parse_qs(urlsplit(manager.start(original)["auth_url"]).query)
    assert query["client_id"] == ["oaiapp_fictional"]
    assert "id_token_hint" not in query
    assert "agent_name_hint" not in query
    mock_service(monkeypatch, manager, signer, changes={"sub": "someone-else"})
    with pytest.raises(accounts.AccountError, match="different account"):
        complete(manager)
    assert manager._read()["profiles"][original]["subject"] == "account-one"
    assert manager.status()["active_profile_id"] == original


def test_reauthorization_rejects_different_issued_client(manager, signer, monkeypatch):
    mock_service(monkeypatch, manager, signer)
    manager.start()
    complete(manager)
    original = manager.status()["active_profile_id"]
    requests = mock_service(monkeypatch, manager, signer)
    manager.start(original)
    with pytest.raises(accounts.AccountError):
        complete(manager, client_id="oaiapp_different")
    assert requests == []


def test_same_email_accounts_stay_separate_and_connection_is_bound(
    manager, signer, monkeypatch,
):
    mock_service(monkeypatch, manager, signer)
    manager.start()
    complete(manager)
    first = manager.status()["active_profile_id"]
    connection = manager.connection()
    assert connection["account_profile_id"] == first
    query = parse_qs(urlsplit(manager.start()["auth_url"]).query)
    assert query["client_id"] == ["dynamic_agent_client"]
    assert not {"login_hint", "id_token_hint", "prompt"}.intersection(query)
    assert manager.status()["active_profile_id"] == first
    complete(manager, client_id="oaiapp_second")
    second = manager.status()["active_profile_id"]
    assert first != second
    assert len(manager.status()["profiles"]) == 2
    assert len({row["label"] for row in manager.status()["profiles"]}) == 2
    manager.disconnect(first)
    assert manager.status()["active_profile_id"] == second
    with pytest.raises(accounts.AccountError, match="connect an account"):
        connection["account_token"]()


def test_expiry_and_cancel_do_not_change_active_account(manager, signer, monkeypatch):
    mock_service(monkeypatch, manager, signer)
    manager.start()
    attempt = manager._pending
    manager._expire(attempt)
    assert manager.status()["pending"]["status"] == "expired"
    with pytest.raises(accounts.AccountError):
        complete(manager)
    manager.start()
    manager.cancel()
    assert manager.status()["pending"]["status"] == "cancelled"
    assert manager.status()["connected"] is False


def test_refresh_serialized_across_two_managers(
    manager, signer, monkeypatch, tmp_path,
):
    mock_service(monkeypatch, manager, signer)
    manager.start()
    complete(manager)
    data = manager._read()
    profile = data["profiles"][data["active_id"]]
    profile["expires_at"] = time.time() - 1
    manager._write(data)
    second = accounts.AccountManager(tmp_path)
    requests = []
    count_lock = threading.Lock()

    def renew(url, fields, **kwargs):
        with count_lock:
            requests.append((url, fields))
        time.sleep(0.02)
        return {"access_token": "rotated-access", "refresh_token": "rotated-refresh",
                "token_type": "Bearer", "expires_in": 3600,
                "scope": accounts.SCOPES}

    monkeypatch.setattr(manager, "_request", renew)
    monkeypatch.setattr(second, "_request", renew)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda instance: instance.access_token(),
                             [manager, second])) == ["rotated-access", "rotated-access"]
    assert len(requests) == 1
    assert requests[0] == (accounts.TOKEN_URL, {
        "grant_type": "refresh_token", "client_id": "oaiapp_fictional",
        "refresh_token": "protected-refresh-one", "resource": accounts.RESOURCE})
    assert manager._read()["profiles"][data["active_id"]][
        "refresh_token"] == "rotated-refresh"
    second.close()


def test_revocation_failure_clears_local_tokens_and_explains(
    manager, signer, monkeypatch,
):
    mock_service(monkeypatch, manager, signer)
    manager.start()
    complete(manager)
    identity = manager.status()["active_profile_id"]
    requests = mock_service(monkeypatch, manager, signer, fail="Provider offline")
    result = manager.disconnect()
    assert "Remote revocation was not confirmed" in result["warning"]
    assert result["connected"] is False
    assert requests[0][1] == {
        "token": "protected-refresh-one", "token_type_hint": "refresh_token",
        "client_id": "oaiapp_fictional"}
    profile = manager._read()["profiles"][identity]
    for secret in ("access_token", "refresh_token", "id_token", "scopes"):
        assert secret not in profile
    assert profile["client_id"] == "oaiapp_fictional"
    assert manager.disconnect()["connected"] is False


def test_unsigned_identity_is_rejected(manager, monkeypatch, signer):
    jwt = pytest.importorskip("jwt")
    mock_service(monkeypatch, manager, signer)
    manager.start()
    token = jwt.encode({"sub": "fake", "iss": accounts.AUTHORITY,
                        "aud": "oaiapp_fictional", "exp": time.time() + 3600,
                        "nonce": manager._pending.nonce}, key="", algorithm="none")
    with pytest.raises(accounts.AccountError, match="signature"):
        manager._verify_identity(token, "oaiapp_fictional", manager._pending.nonce)


def test_unsafe_storage_is_preserved(tmp_path):
    folder = tmp_path / "accounts"
    folder.mkdir()
    path = folder / "chatgpt.json"
    path.write_text("not-valid-json")
    manager = accounts.AccountManager(tmp_path)
    assert manager.status()["available"] is False
    assert "preserved" in manager.status()["message"]
    with pytest.raises(accounts.AccountError, match="preserved"):
        manager.start()
    assert path.read_text() == "not-valid-json"


def test_storage_link_is_rejected(tmp_path):
    folder = tmp_path / "accounts"
    folder.mkdir()
    other = tmp_path / "other.json"
    other.write_text("private")
    (folder / "chatgpt.json").symlink_to(other)
    manager = accounts.AccountManager(tmp_path)
    assert manager.status()["available"] is False
    assert "must not be a link" in manager.status()["message"]
    assert other.read_text() == "private"


def test_credentials_never_follow_http_redirect(manager, monkeypatch):
    requested = []

    class Redirect(urllib.request.HTTPSHandler):
        def https_open(self, request):
            import io
            import urllib.response
            requested.append(request)
            response = urllib.response.addinfourl(
                io.BytesIO(), {"Location": "https://attacker.example/steal"},
                request.full_url, 302)
            response.msg = "Found"
            return response

    opener = urllib.request.build_opener(accounts._NoRedirect(), Redirect())
    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: opener)
    with pytest.raises(accounts.AccountError):
        manager._request(accounts.TOKEN_URL, {"refresh_token": "never-forward"})
    assert len(requested) == 1
    assert requested[0].full_url == accounts.TOKEN_URL


def test_loopback_wrong_host_and_duplicate_state_rejected(
    manager, signer, monkeypatch,
):
    calls = mock_service(monkeypatch, manager, signer)
    manager.start()
    attempt = manager._pending
    values = {"state": attempt.state, "code": "code", "client_id": "oaiapp_test"}
    request = urllib.request.Request(attempt.redirect_uri + "?" + urlencode(values),
                                     headers={"Host": "attacker.example"})
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=5)
    assert error.value.code == 400
    duplicate = attempt.redirect_uri + "?" + urlencode(values) + "&state=second"
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(duplicate, timeout=5)
    assert calls == []


def test_refresh_unusable_clears_credentials_but_retains_registration(
    manager, signer, monkeypatch,
):
    mock_service(monkeypatch, manager, signer)
    manager.start()
    complete(manager)
    data = manager._read()
    identity = data["active_id"]
    data["profiles"][identity]["expires_at"] = time.time() - 1
    manager._write(data)

    def failed(*args, **kwargs):
        raise accounts.AccountError("Continue with ChatGPT again.", "invalid_grant")

    monkeypatch.setattr(manager, "_request", failed)
    with pytest.raises(accounts.AccountError):
        manager.access_token()
    assert manager.status()["connected"] is False
    assert manager._read()["profiles"][identity]["client_id"] == "oaiapp_fictional"


def test_refresh_transient_preserves_tokens(manager, signer, monkeypatch):
    mock_service(monkeypatch, manager, signer)
    manager.start()
    complete(manager)
    data = manager._read()
    identity = data["active_id"]
    data["profiles"][identity]["expires_at"] = time.time() - 1
    manager._write(data)
    mock_service(monkeypatch, manager, signer, fail="Temporarily unavailable")
    with pytest.raises(accounts.AccountError):
        manager.access_token()
    assert manager._read()["profiles"][identity][
        "refresh_token"] == "protected-refresh-one"


def test_disk_lock_contention_is_bounded(manager, monkeypatch):
    if accounts.os.name == "nt":
        pytest.skip("Unix flock contention test")
    monkeypatch.setattr(accounts, "LOCK_SECONDS", 0.03)
    with manager._disk_lock():
        before = time.monotonic()
        with pytest.raises(accounts.AccountError, match="busy"):
            with manager._disk_lock():
                pytest.fail("A second refresh obtained the same storage lock")
        assert time.monotonic() - before < 0.3


def test_invalid_token_type_is_safe_error(manager):
    with pytest.raises(accounts.AccountError, match="incomplete"):
        manager._credentials({"access_token": "token", "refresh_token": "refresh",
                              "token_type": 123, "expires_in": 3600,
                              "scope": accounts.SCOPES})


def test_closing_core_after_account_file_corruption_is_safe(manager):
    manager.path.write_text("file corrupted after startup")
    manager.close()


@pytest.mark.parametrize("missing", ["subject", "issuer", "refresh_token", "scopes"])
def test_partial_credential_record_fails_closed_without_token_transfer(
    manager, signer, monkeypatch, missing,
):
    mock_service(monkeypatch, manager, signer)
    manager.start()
    complete(manager)
    saved = manager._read()
    saved["profiles"][saved["active_id"]].pop(missing)
    manager._write(saved)
    assert manager.status()["available"] is False
    with pytest.raises(accounts.AccountError, match="preserved"):
        manager.connection()["account_token"]()
