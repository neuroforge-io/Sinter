"""Protected local ChatGPT accounts using the documented OSS OAuth flow.

Browser sign-in returns to a separate, short-lived loopback listener. Tokens never
enter the Sinter browser session or public account status. Identity verification
uses PyJWT and OpenAI's published signing keys, not unsigned token claims.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import math
import os
import re
import secrets
import stat
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

AUTHORITY = "https://auth.openai.com"
AUTHORIZE_URL = AUTHORITY + "/api/accounts/authorize"
TOKEN_URL = AUTHORITY + "/api/accounts/oauth/token"
REVOKE_URL = AUTHORITY + "/api/accounts/oauth/revoke"
JWKS_URL = AUTHORITY + "/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = "openid profile email offline_access resource.invoke " + PLAN_SCOPE
CALLBACK_PATH = "/auth/callback"
PENDING_SECONDS = 300
LOCK_SECONDS = 5
MAX_BYTES = 1024 * 1024
INSTALL_HELP = "Install Sinter's accounts extra to enable ChatGPT sign-in."
BUILD_HELP = ("ChatGPT sign-in is unavailable in this Sinter build. "
              "Use a supported build or a source installation with accounts support.")
UNUSABLE_REFRESH = frozenset({
    "invalid_grant", "invalid_refresh_token", "token_expired",
    "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused",
})


class AccountError(ValueError):
    """A safe, actionable account error that contains no provider credentials."""

    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


class _CallbackServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, address, handler):
        self._slots = threading.BoundedSemaphore(4)
        super().__init__(address, handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        return connection, address

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class _Attempt:
    profile_id: str
    state: str
    nonce: str
    verifier: str
    redirect_uri: str
    expires_at: float
    client_id: str = ""
    status: str = "awaiting"
    message: str = "Finish sign-in in your browser."
    server: ThreadingHTTPServer | None = field(default=None, repr=False)
    timer: threading.Timer | None = field(default=None, repr=False)


def _ordinary(value: object, maximum: int = 16384) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= maximum
            and all(32 <= ord(character) < 127 for character in value))


class AccountManager:
    """Manage local account registrations and serialized OAuth token renewal."""

    def __init__(self, directory: Path):
        self.directory = Path(directory) / "accounts"
        self.path = self.directory / "chatgpt.json"
        self._lock = threading.RLock()
        self._pending: _Attempt | None = None
        self._jwks: dict = {}
        self._jwks_at = 0.0
        self._storage_error = ""
        self.warning = ""
        try:
            if self.directory.is_symlink():
                raise AccountError("The account storage folder must not be a link.")
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                self.directory.chmod(0o700)
            with self._lock, self._disk_lock():
                if self.path.is_symlink():
                    raise AccountError("The account storage file must not be a link.")
                if not self.path.exists():
                    self._write({"schema": 1,
                                 "host_id": "urn:uuid:" + str(uuid.uuid4()),
                                 "active_id": "", "profiles": {}})
                self._read()
        except (AccountError, OSError) as error:
            self._storage_error = (
                str(error) if isinstance(error, AccountError) else
                "ChatGPT account storage is unavailable. Local Sinter tools "
                "remain available; the original account files were preserved.")
            self.warning = self._storage_error

    @contextmanager
    def _disk_lock(self):
        """Serialize rotating refresh tokens across local Sinter processes."""
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.directory / ".chatgpt.lock", flags, 0o600)
        locked = False
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
            else:
                import fcntl
            deadline = time.monotonic() + LOCK_SECONDS
            while not locked:
                try:
                    if os.name == "nt":
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except (BlockingIOError, OSError) as error:
                    if time.monotonic() >= deadline:
                        raise AccountError(
                            "ChatGPT account storage is busy. Try again shortly."
                        ) from error
                    time.sleep(0.025)
            yield
        finally:
            if locked and os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            elif locked:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self) -> dict:
        try:
            if self.path.is_symlink():
                raise ValueError("linked storage")
            info = self.path.stat()
            if (info.st_size > MAX_BYTES or not stat.S_ISREG(info.st_mode)
                    or (os.name != "nt" and stat.S_IMODE(info.st_mode) & 0o077)):
                raise ValueError("unprotected storage")
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(value, dict) or value.get("schema") != 1
                    or not isinstance(value.get("profiles"), dict)
                    or len(value["profiles"]) > 20
                    or not isinstance(value.get("active_id"), str)):
                raise ValueError("invalid account data")
            host = value.get("host_id", "")
            if not isinstance(host, str) or not host.startswith("urn:uuid:"):
                raise ValueError("invalid host identity")
            uuid.UUID(host[9:])
            for identity, profile in value["profiles"].items():
                if (not re.fullmatch(r"[0-9a-f]{32}", identity)
                        or not isinstance(profile, dict)
                        or not _ordinary(profile.get("client_id"), 200)
                        or profile["client_id"] == "dynamic_agent_client"):
                    raise ValueError("invalid registration")
                if any(name in profile and not _ordinary(profile[name])
                       for name in ("access_token", "refresh_token", "id_token")):
                    raise ValueError("invalid credentials")
                credential_fields = {
                    "access_token", "refresh_token", "id_token", "scopes", "expires_at",
                }
                if (credential_fields.intersection(profile)
                        and not credential_fields.union({"subject", "issuer"})
                        .issubset(profile)):
                    raise ValueError("incomplete credentials or verified identity")
                if ("scopes" in profile and (not isinstance(profile["scopes"], list)
                        or len(profile["scopes"]) > 100
                        or any(not _ordinary(item, 200)
                               for item in profile["scopes"]))):
                    raise ValueError("invalid scopes")
                if "expires_at" in profile and (
                        type(profile["expires_at"]) not in {int, float}
                        or not math.isfinite(profile["expires_at"])):
                    raise ValueError("invalid token expiry")
                if ("subject" in profile and not _ordinary(profile["subject"], 500)
                        or "issuer" in profile and profile["issuer"] != AUTHORITY):
                    raise ValueError("invalid verified identity")
                if any(name in profile and (not isinstance(profile[name], str)
                        or len(profile[name]) > maximum)
                       for name, maximum in (("name", 200), ("email", 254))):
                    raise ValueError("invalid account label")
            if (value["active_id"]
                    and value["active_id"] not in value["profiles"]):
                raise ValueError("unknown active registration")
            return value
        except (OSError, ValueError, UnicodeError, TypeError) as error:
            raise AccountError(
                "Saved ChatGPT accounts could not be safely read. "
                "The original account file has been preserved."
            ) from error

    def _write(self, value: dict) -> None:
        fd, name = tempfile.mkstemp(prefix=".chatgpt-", dir=self.directory)
        try:
            if os.name != "nt":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(value, output, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _request(self, url: str, fields: dict | None = None,
                 *, empty: bool = False) -> dict:
        """Call a fixed OpenAI account endpoint without redirects or body logs."""
        if url not in {TOKEN_URL, REVOKE_URL, JWKS_URL}:
            raise AccountError("Unsupported ChatGPT account destination.")
        request = urllib.request.Request(
            url, data=urlencode(fields).encode() if fields is not None else None,
            headers={"Accept": "application/json", **(
                {"Content-Type": "application/x-www-form-urlencoded"}
                if fields is not None else {})})
        try:
            with urllib.request.build_opener(_NoRedirect()).open(
                    request, timeout=15) as response:
                body = response.read(MAX_BYTES + 1)
                if empty and not body:
                    return {}
                if len(body) > MAX_BYTES:
                    raise AccountError("ChatGPT account response was too large.")
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise AccountError("ChatGPT account response was invalid.")
                return result
        except urllib.error.HTTPError as error:
            code = ""
            try:
                detail = json.loads(error.read(4096))
                item = detail.get("error", "") if isinstance(detail, dict) else ""
                candidate = item.get("code", "") if isinstance(item, dict) else item
                if candidate in UNUSABLE_REFRESH | {"invalid_client"}:
                    code = candidate
            except (OSError, ValueError, TypeError):
                pass
            if error.code in {400, 401, 403}:
                raise AccountError(
                    "ChatGPT did not accept this sign-in or renewal. "
                    "Continue with ChatGPT again.", code
                ) from error
            raise AccountError(
                "ChatGPT account service is temporarily unavailable. Try again.",
                "temporarily_unavailable"
            ) from error
        except AccountError:
            raise
        except (OSError, ValueError, UnicodeError) as error:
            raise AccountError(
                "Could not reach the ChatGPT account service. Try again.",
                "temporarily_unavailable"
            ) from error

    def _verify_identity(self, token: str, client_id: str,
                         nonce: str | None = None) -> dict:
        try:
            import jwt
            if not _ordinary(token):
                raise AccountError("ChatGPT returned an invalid identity token.")
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not _ordinary(
                    header.get("kid"), 200):
                raise AccountError("ChatGPT identity signature was not supported.")
            if time.monotonic() - self._jwks_at > 300 or not self._jwks:
                self._jwks = self._request(JWKS_URL)
                self._jwks_at = time.monotonic()
            key = next((row for row in self._jwks.get("keys", [])
                        if isinstance(row, dict)
                        and row.get("kid") == header["kid"]
                        and row.get("kty") == "RSA"
                        and row.get("use", "sig") == "sig"
                        and row.get("alg", "RS256") == "RS256"), None)
            if key is None:
                # A rotated signing key gets one fresh discovery attempt.
                self._jwks = self._request(JWKS_URL)
                self._jwks_at = time.monotonic()
                key = next((row for row in self._jwks.get("keys", [])
                            if isinstance(row, dict)
                            and row.get("kid") == header["kid"]
                            and row.get("kty") == "RSA"
                            and row.get("use", "sig") == "sig"
                            and row.get("alg", "RS256") == "RS256"), None)
            if key is None:
                raise AccountError("ChatGPT identity signature could not be verified.")
            claims = jwt.decode(
                token, jwt.PyJWK.from_dict(key, algorithm="RS256").key,
                algorithms=["RS256"], issuer=AUTHORITY, audience=client_id,
                options={"require": ["iss", "aud", "exp", "sub"]})
            if not _ordinary(claims.get("sub"), 500):
                raise AccountError("ChatGPT returned an invalid account identity.")
            if nonce is not None and (not isinstance(claims.get("nonce"), str)
                    or not hmac.compare_digest(claims["nonce"], nonce)):
                raise AccountError("ChatGPT sign-in could not be verified.")
            return claims
        except ImportError as error:
            raise AccountError(self._installation_help()) from error
        except AccountError:
            raise
        except (ValueError, KeyError, TypeError, jwt.PyJWTError) as error:
            raise AccountError("ChatGPT sign-in could not be verified.") from error

    def _credentials(self, result: dict) -> dict:
        if (not _ordinary(result.get("access_token"))
                or not _ordinary(result.get("refresh_token"))
                or not isinstance(result.get("token_type"), str)
                or result["token_type"].lower() != "bearer"
                or type(result.get("expires_in")) is not int
                or not 0 < result["expires_in"] <= 86400
                or not isinstance(result.get("scope"), str)
                or len(result["scope"]) > 4096
                or any(not _ordinary(scope, 200)
                       for scope in result["scope"].split())):
            raise AccountError("ChatGPT returned incomplete account credentials.")
        return {"access_token": result["access_token"],
                "refresh_token": result["refresh_token"],
                "scopes": result["scope"].split(),
                "expires_at": time.time() + result["expires_in"]}

    def status(self) -> dict:
        """Return only display information, never OAuth tokens or auth URLs."""
        if self._storage_error:
            return self._unavailable(self._storage_error)
        try:
            with self._lock, self._disk_lock():
                return self._status()
        except (AccountError, OSError) as error:
            return self._unavailable(self._storage_message(error))

    @staticmethod
    def _verification_available() -> bool:
        return (importlib.util.find_spec("jwt") is not None
                and importlib.util.find_spec("cryptography") is not None)

    @staticmethod
    def _installation_help() -> str:
        return BUILD_HELP if getattr(sys, "frozen", False) else INSTALL_HELP

    @staticmethod
    def _storage_message(error: Exception) -> str:
        return (str(error) if isinstance(error, AccountError) else
                "ChatGPT account storage is unavailable. Local Sinter tools "
                "remain available; the original account files were preserved.")

    @staticmethod
    def _unavailable(message: str) -> dict:
        return {"available": False, "message": message,
                "connected": False, "plan_usage": False,
                "active_profile_id": "", "profiles": [], "pending": None,
                "warning": message}

    def _status(self) -> dict:
        """Build display state while the caller holds the storage lock."""
        data = self._read()
        profiles = []
        for index, (identity, row) in enumerate(data["profiles"].items(), 1):
            connected = bool(row.get("access_token") and row.get("subject"))
            profiles.append({
                "id": identity, "email": row.get("email", ""),
                "name": row.get("name", ""),
                "label": f"{row.get('email') or 'ChatGPT account'} · {index}",
                "connected": connected,
                "plan_usage": connected and PLAN_SCOPE in row.get("scopes", []),
                "expires_at": row.get("expires_at", 0),
            })
        selected = next((row for row in profiles
                         if row["id"] == data["active_id"]), {})
        pending = (None if self._pending is None else {
            "status": self._pending.status,
            "expires_at": self._pending.expires_at,
            "message": self._pending.message})
        available = self._verification_available()
        return {"available": available,
                "message": "" if available else self._installation_help(),
                "connected": selected.get("connected", False),
                "plan_usage": selected.get("plan_usage", False),
                "active_profile_id": data["active_id"], "profiles": profiles,
                "pending": pending, "warning": self.warning}

    @staticmethod
    def _close_attempt(attempt: _Attempt) -> None:
        if attempt.timer:
            attempt.timer.cancel()
        if attempt.server:
            server, attempt.server = attempt.server, None
            def shutdown():
                server.shutdown()
                server.server_close()
            threading.Thread(target=shutdown, daemon=True).start()

    def _expire(self, attempt: _Attempt) -> None:
        with self._lock:
            if self._pending is attempt and attempt.status == "awaiting":
                attempt.status = "expired"
                attempt.message = "Sign-in expired. Continue with ChatGPT again."
                self._close_attempt(attempt)

    def start(self, profile_id: str | None = None) -> dict:
        """Start the loopback listener before returning the OpenAI sign-in URL."""
        availability = self.status()
        if not availability["available"]:
            raise AccountError(availability["message"])
        with self._lock, self._disk_lock():
            data = self._read()
            profile = data["profiles"].get(profile_id) if profile_id else None
            if profile_id and profile is None:
                raise AccountError("Choose a saved ChatGPT account.")
            if not profile and len(data["profiles"]) >= 20:
                raise AccountError("This workspace has 20 ChatGPT registrations.")
            if self._pending:
                self._pending.status = "cancelled"
                self._close_attempt(self._pending)
            manager = self
            class Callback(BaseHTTPRequestHandler):
                def do_GET(self):
                    parsed = urlsplit(self.path)
                    if (parsed.path != CALLBACK_PATH or len(self.path) > 8192
                            or self.headers.get("Host") != urlsplit(
                                attempt.redirect_uri).netloc):
                        self.send_error(400, "Invalid sign-in callback")
                        return
                    try:
                        values = parse_qs(parsed.query, max_num_fields=8)
                        if any(len(row) != 1 for row in values.values()):
                            raise AccountError("Invalid sign-in callback.")
                        manager._callback(attempt, {key: row[0]
                                                   for key, row in values.items()})
                        message = "Sign-in finished. Return to Sinter."
                        code = 200
                    except (AccountError, ValueError):
                        message = "Sign-in was not completed. Return to Sinter."
                        code = 400
                    body = ("<!doctype html><meta charset=utf-8>"
                            "<meta name=viewport content='width=device-width'>"
                            "<title>Sinter sign-in</title><h1>" + message + "</h1>")
                    self.send_response(code)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body.encode())))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("Content-Security-Policy", "default-src 'none'")
                    self.end_headers()
                    self.wfile.write(body.encode())

                def log_message(self, format, *args):
                    pass

            server = _CallbackServer(("127.0.0.1", 0), Callback)
            verifier = secrets.token_urlsafe(64)
            attempt = _Attempt(
                profile_id or uuid.uuid4().hex, secrets.token_urlsafe(32),
                secrets.token_urlsafe(32), verifier,
                f"http://127.0.0.1:{server.server_port}{CALLBACK_PATH}",
                time.time() + PENDING_SECONDS,
                profile["client_id"] if profile else "", server=server)
            self._pending = attempt
            query = {
                "client_id": attempt.client_id or "dynamic_agent_client",
                "ext_agent_host_id": data["host_id"], "response_type": "code",
                "redirect_uri": attempt.redirect_uri, "scope": SCOPES,
                "resource": RESOURCE, "state": attempt.state, "nonce": attempt.nonce,
                "code_challenge_method": "S256", "code_challenge":
                base64.urlsafe_b64encode(hashlib.sha256(
                    verifier.encode()).digest()).decode().rstrip("="),
            }
            if profile:
                if profile.get("email"):
                    query["login_hint"] = profile["email"]
            else:
                query["agent_name_hint"] = "Sinter"
            threading.Thread(target=server.serve_forever, daemon=True).start()
            attempt.timer = threading.Timer(PENDING_SECONDS, self._expire, [attempt])
            attempt.timer.daemon = True
            attempt.timer.start()
        return {"auth_url": AUTHORIZE_URL + "?" + urlencode(query),
                "pending": self.status()["pending"]}

    def _callback(self, attempt: _Attempt, fields: dict) -> None:
        with self._lock, self._disk_lock():
            if (self._pending is not attempt or attempt.status != "awaiting"
                    or time.time() >= attempt.expires_at
                    or not _ordinary(fields.get("state"), 200)
                    or not hmac.compare_digest(fields["state"], attempt.state)):
                raise AccountError("Sign-in callback did not match this attempt.")
            if fields.get("error"):
                attempt.status = "failed"
                # OAuth denial does not distinguish a cancelled consent screen
                # from a workspace policy block. Do not attribute either to
                # the user, or expose untrusted provider diagnostic text.
                attempt.message = (
                    "ChatGPT did not authorise this sign-in. You can try again "
                    "or use another account."
                    if fields["error"] == "access_denied" else
                    "ChatGPT sign-in could not be completed. You can try again.")
                self._close_attempt(attempt)
                raise AccountError(attempt.message)
            issued = fields.get("client_id", attempt.client_id)
            if (not _ordinary(issued, 200) or issued == "dynamic_agent_client"
                    or (attempt.client_id and issued != attempt.client_id)
                    or not _ordinary(fields.get("code"), 4096)):
                raise AccountError("ChatGPT registration was incomplete.")
            attempt.client_id = issued
            attempt.status = "processing"
            attempt.message = "Verifying your ChatGPT account…"
            data = self._read()
            prior = dict(data["profiles"].get(attempt.profile_id, {}))
            # Keep the issued registration even if the code expires at exchange.
            if not prior:
                data["profiles"][attempt.profile_id] = {"client_id": issued}
                self._write(data)
        try:
            result = self._request(TOKEN_URL, {
                "grant_type": "authorization_code", "client_id": issued,
                "code": fields["code"], "code_verifier": attempt.verifier,
                "redirect_uri": attempt.redirect_uri, "resource": RESOURCE})
            identity = self._verify_identity(result.get("id_token"), issued,
                                             attempt.nonce)
            credentials = self._credentials(result)
            if (prior.get("subject") and (identity["sub"] != prior["subject"]
                    or identity["iss"] != prior["issuer"])):
                raise AccountError("ChatGPT returned a different account. "
                                   "Add it as a separate account instead.")
            with self._lock, self._disk_lock():
                if self._pending is not attempt or attempt.status != "processing":
                    raise AccountError("This sign-in attempt was cancelled.")
                data = self._read()
                data["profiles"][attempt.profile_id] = {
                    "client_id": issued, "issuer": identity["iss"],
                    "subject": identity["sub"],
                    "email": str(identity.get("email", ""))[:254],
                    "name": str(identity.get("name", ""))[:200],
                    "id_token": result["id_token"], **credentials}
                data["active_id"] = attempt.profile_id
                self._write(data)
                attempt.status = "complete"
                attempt.message = ("ChatGPT connected. Plan usage is enabled."
                                   if PLAN_SCOPE in credentials["scopes"] else
                                   "ChatGPT connected. Plan usage was not enabled; "
                                   "allow it in ChatGPT settings before using AI.")
                self.warning = ""
        except AccountError as error:
            with self._lock:
                if self._pending is attempt and attempt.status == "processing":
                    attempt.status = "failed"
                    attempt.message = str(error)
            raise
        finally:
            self._close_attempt(attempt)

    def cancel(self) -> dict:
        """Cancel or dismiss an attempt without changing connected accounts."""
        with self._lock:
            if self._pending and self._pending.status in {
                    "awaiting", "processing", "failed", "expired"}:
                self._pending.status = "cancelled"
                self._pending.message = "Sign-in cancelled."
                self._close_attempt(self._pending)
        return self.status()

    def activate(self, profile_id: str) -> dict:
        """Select an already verified account registration."""
        with self._lock, self._disk_lock():
            data = self._read()
            profile = data["profiles"].get(profile_id)
            if not profile or not profile.get("subject"):
                raise AccountError("Sign in to this ChatGPT account first.")
            data["active_id"] = profile_id
            self._write(data)
        return self.status()

    def access_token(self, profile_id: str | None = None) -> str:
        """Return a protected bearer credential, renewing it once when needed."""
        with self._lock, self._disk_lock():
            data = self._read()
            selected = data["active_id"] if profile_id is None else profile_id
            profile = data["profiles"].get(selected)
            if not profile or not profile.get("access_token"):
                raise AccountError("Continue with ChatGPT to connect an account.")
            if PLAN_SCOPE not in profile.get("scopes", []):
                raise AccountError("Allow Sinter to use your ChatGPT plan in "
                                   "ChatGPT settings, then sign in again.")
            if float(profile.get("expires_at", 0)) <= time.time() + 60:
                try:
                    result = self._request(TOKEN_URL, {
                        "grant_type": "refresh_token",
                        "client_id": profile["client_id"],
                        "refresh_token": profile["refresh_token"],
                        "resource": RESOURCE})
                except AccountError as error:
                    if error.code in UNUSABLE_REFRESH:
                        self._clear_tokens(profile)
                        self._write(data)
                    raise
                credentials = self._credentials(result)
                if result.get("id_token"):
                    identity = self._verify_identity(result["id_token"],
                                                     profile["client_id"])
                    if (identity["sub"] != profile["subject"]
                            or identity["iss"] != profile["issuer"]):
                        raise AccountError(
                            "ChatGPT renewal returned a different account.")
                    profile["id_token"] = result["id_token"]
                profile.update(credentials)
                self._write(data)
                if PLAN_SCOPE not in profile["scopes"]:
                    raise AccountError("ChatGPT plan usage is no longer enabled. "
                                       "Review Sinter's access in ChatGPT settings.")
            return profile["access_token"]

    def connection(self) -> dict:
        """Return a destination-bound token supplier for the model transport."""
        error_message = self._storage_error
        selected = ""
        try:
            if error_message:
                raise AccountError(error_message)
            # Atomic replacements make this read safe without the renewal lock.
            # Core requests must not wait for an optional account's network call.
            selected = self._read()["active_id"]
        except (AccountError, OSError) as error:
            error_message = self._storage_message(error)

        def account_token():
            if error_message:
                raise AccountError(error_message)
            if not self._verification_available():
                raise AccountError(self._installation_help())
            return self.access_token(selected)

        return {"provider": "chatgpt", "api_url": RESOURCE,
                "account_profile_id": selected,
                "account_token": account_token}

    def disconnect(self, profile_id: str | None = None) -> dict:
        """Revoke the selected renewable session and remove its local tokens."""
        if self._storage_error:
            return self.status()
        self.cancel()
        with self._lock, self._disk_lock():
            data = self._read()
            selected = profile_id or data["active_id"]
            profile = data["profiles"].get(selected)
            self.warning = ""
            if profile and profile.get("refresh_token"):
                try:
                    self._request(REVOKE_URL, {
                        "token": profile["refresh_token"],
                        "token_type_hint": "refresh_token",
                        "client_id": profile["client_id"]}, empty=True)
                except AccountError:
                    self.warning = ("Signed out on this computer. Remote revocation "
                                    "was not confirmed; disconnect Sinter in "
                                    "ChatGPT settings.")
            if profile:
                self._clear_tokens(profile)
                if selected == data["active_id"]:
                    data["active_id"] = ""
                self._write(data)
        return self.status()

    @staticmethod
    def _clear_tokens(profile: dict) -> None:
        for name in ("access_token", "refresh_token", "id_token", "scopes",
                     "expires_at"):
            profile.pop(name, None)

    def close(self) -> None:
        """Close any short-lived sign-in listener when Sinter shuts down."""
        with self._lock:
            if self._pending:
                self._pending.status = "cancelled"
                self._close_attempt(self._pending)
