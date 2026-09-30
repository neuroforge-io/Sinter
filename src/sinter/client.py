"""Bounded model client. Modified 2026-09-27 for explicit hosted model identity."""
from __future__ import annotations

import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Iterator
from urllib.parse import SplitResult, urlsplit

from . import __version__
from .model_profiles import (
    NATIVE_MODEL,
    NATIVE_PROFILE,
    native_profile_applies,
    native_reply,
    native_request,
    qualify_native_catalog,
)
from .operations import Cancelled, DeadlineExceeded, budget, checkpoint, remaining
from .providers import (
    CHATGPT,
    CHATGPT_API_URL,
    OPENAI_COMPATIBLE,
    ProviderCompletionMismatch,
    ProviderIdentityError,
    ProviderProtocolError,
    ProviderReply,
    chatgpt_failure,
    transport_for,
)

BASE_URL = "https://neuroforge.io/v1"
MODEL = "erais-fracture-gemma"  # Explicit legacy selection remains supported.
DENSE_MODEL = "erais-dense-gemma4-e4b"
AUTO_MODEL = "auto"
DEFAULT_MODEL = AUTO_MODEL
DENSE_MAX_OUTPUT_TOKENS = 512
NATIVE_MAX_OUTPUT_TOKENS = NATIVE_PROFILE.max_output_tokens
NATIVE_MAX_QUESTION_BYTES = NATIVE_PROFILE.max_question_bytes
NATIVE_MAX_HISTORY_BYTES = NATIVE_PROFILE.max_history_bytes
NATIVE_MAX_REQUEST_BYTES = NATIVE_PROFILE.request_bytes
DEFAULT_OUTPUT_TOKENS = 64
_HOSTED_GENERATION = threading.Lock()
_HOSTED_PENDING = threading.BoundedSemaphore(4)
_KEY_FILE = Path.home() / ".sinter_key"
MAX_RESPONSE = 2 * 1024 * 1024
MAX_INPUT = 64000
MIN_OUTPUT_TOKENS = 32
MAX_OUTPUT_TOKENS = 8192
PUBLIC_MAX_OUTPUT_TOKENS = 2048
PUBLIC_MAX_CONVERSATION_BYTES = 49152
PUBLIC_MAX_SYSTEM_BYTES = 8192
PUBLIC_MAX_REQUEST_BYTES = 98304
_PUBLIC_WHITESPACE = (
    "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
    "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)
CONTROL_TIMEOUT = 10.0
REQUEST_TIMEOUT = 30.0
JSON_CHAT_TIMEOUT = 120.0
STREAM_DEADLINE = 660.0
_CONNECTION = ContextVar("sinter_connection", default=None)
_MODEL_SELECTION = ContextVar("sinter_model_selection", default=None)


@contextmanager
def connection_settings(settings):
    """Bind an immutable configuration snapshot to this request or worker."""
    token = _CONNECTION.set(dict(settings))
    try:
        yield
    finally:
        _CONNECTION.reset(token)


@contextmanager
def model_selection(model: str):
    """Pin an already resolved model without changing keys or caller settings."""
    if (not isinstance(model, str) or not model or model == AUTO_MODEL
            or len(model) > 200 or any(ord(char) < 32 for char in model)):
        raise ValueError("Pin a resolved model identifier before running this workflow.")
    token = _MODEL_SELECTION.set(model)
    try:
        yield
    finally:
        _MODEL_SELECTION.reset(token)


class APIError(RuntimeError):
    """An error safe to display without upstream bodies or credentials."""
    def __init__(self, message: str, status: int = 502, *, error_code: str = "",
                 upstream_status: int | None = None):
        super().__init__(message)
        self.status = status
        self.error_code = error_code
        self.upstream_status = upstream_status


@dataclass
class Message:
    role: str
    content: str


@dataclass
class ChatResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = ""
    model: str = ""


class IncompleteGeneration(APIError):
    """A received answer that must remain visibly incomplete, with no replay."""

    def __init__(self, result: ChatResult, max_tokens: int, *, message: str = "",
                 error_code: str = "", upstream_status: int | None = None):
        self.result = result
        self.max_tokens = max_tokens
        if message:
            message += " Review the received partial text."
        elif result.finish_reason == "length" and selected_provider() == CHATGPT:
            message = ("ChatGPT reached a provider-controlled output limit. "
                       "The partial text is available for review. "
                       "Sinter's token cap does not apply to ChatGPT plan usage; "
                       "ask for a shorter answer or split the task.")
        elif result.finish_reason == "length":
            message = (f"The answer reached its {max_tokens}-token output limit. "
                       "The partial text is available for review. Shorten the requested "
                       "answer or raise the output limit within your service's range.")
        else:
            message = "The model stopped before completing its answer. Review the partial text."
        super().__init__(message + " No request was replayed.",
                         error_code=error_code, upstream_status=upstream_status)


def require_complete(result: ChatResult, max_tokens: int) -> ChatResult:
    """Apply the same explicit completion policy to JSON and streamed answers."""
    if not isinstance(result.content, str) or not result.content.strip():
        raise APIError("The model returned no answer. No request was replayed. "
                       "Try a clearer or shorter prompt.")
    if not isinstance(result.finish_reason, str):
        raise APIError("The API returned an invalid completion reason.")
    if result.finish_reason not in {"", "stop"}:
        limit = (effective_max_tokens(max_tokens, model=result.model)
                 if result.model else max_tokens)
        raise IncompleteGeneration(result, limit)
    return result


@dataclass
class SearchResult:
    title: str
    url: str
    content: str


@dataclass
class SearchResponse:
    retrieved_at: str
    results: list[SearchResult] = field(default_factory=list)


def safe_url(value: str) -> bool:
    if not isinstance(value, str) or "\\" in value or any(ord(c) < 33 or ord(c) == 127 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme in {"https", "http"} and bool(parsed.hostname)
                and not parsed.username and not parsed.password and parsed.port != 0)
    except ValueError:
        return False


def _load_key() -> str:
    """Read credentials belonging to the default NeuroForge service only."""
    key = os.environ.get("NEUROFORGE_API_KEY", "").strip()
    if key:
        return key
    try:
        if _KEY_FILE.stat().st_size > 8192:
            raise APIError("The optional key file is too large.")
        for line in _KEY_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("#"):
                continue
            name, sep, value = line.partition("=")
            if sep and name.strip() == "NEUROFORGE_API_KEY":
                return value.strip()
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError) as exc:
        raise APIError("Cannot read the optional API key file.") from exc
    return ""


def same_api_destination(first: str, second: str) -> bool:
    """Compare complete API bases, including scheme, port and path."""
    if not safe_url(first) or not safe_url(second):
        return False
    left, right = urlsplit(first), urlsplit(second)
    if left.query or left.fragment or right.query or right.fragment:
        return False

    def identity(url: SplitResult) -> tuple[str, str | None, int, str]:
        return (url.scheme, url.hostname,
                url.port or (443 if url.scheme == "https" else 80),
                url.path.rstrip("/"))

    return identity(left) == identity(right)


def uses_neuroforge_api(base_url: str) -> bool:
    """Allow public-provider credentials and limits only at the official API."""
    return same_api_destination(base_url, BASE_URL)


def destination_key(base_url: str, *, api_key: str = "",
                    inherit_key: bool = True) -> str:
    """Select an explicit destination key or an eligible public-provider key.

    Session keys are supplied with their connection snapshot. A CLI custom key
    must be paired with an explicit environment URL, so changing saved UI
    preferences cannot silently retarget that credential.
    """
    if api_key:
        return api_key
    environment_url = os.environ.get("NEUROFORGE_BASE_URL", "")
    if same_api_destination(base_url, environment_url):
        custom_key = os.environ.get("SINTER_API_KEY", "").strip()
        if custom_key:
            return custom_key
    if inherit_key and uses_neuroforge_api(base_url):
        return _load_key()
    return ""


def _headers(base_url: str | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": f"sinter/{__version__}"}
    settings = _CONNECTION.get() or {}
    destination = _endpoint("") if base_url is None else base_url
    provider = _transport()
    if settings.get("anonymous"):
        key = ""
    elif provider.identifier == CHATGPT:
        if not same_api_destination(destination, CHATGPT_API_URL):
            raise APIError("ChatGPT account connections require the official OpenAI API.")
        token_provider = settings.get("account_token")
        if not callable(token_provider):
            raise APIError("Sign in with ChatGPT in Settings before using this connection.")
        from .accounts import AccountError
        try:
            key = token_provider()
        except (Cancelled, DeadlineExceeded):
            raise
        except AccountError as exc:
            raise APIError(str(exc)) from exc
        except Exception as exc:
            raise APIError("The ChatGPT sign-in session could not be renewed. "
                           "Open Settings to reconnect; no model request was sent.") from exc
        if not isinstance(key, str) or not key:
            raise APIError("The ChatGPT connection needs sign-in. Open Settings to reconnect.")
    else:
        key = destination_key(
            destination, api_key=settings.get("api_key", ""),
            inherit_key=settings.get("inherit_key", True),
        )
    if key:
        if any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise APIError("The API key contains invalid characters.")
    headers.update(provider.headers(key, destination))
    return headers


def selected_provider() -> str:
    settings = _CONNECTION.get() or {}
    return settings.get("provider", OPENAI_COMPATIBLE)


def _transport():
    return transport_for(selected_provider())


def connection_identity() -> dict:
    """Describe the active request destination without tokens or callbacks."""
    settings = _CONNECTION.get() or {}
    identity = {"provider": selected_provider(), "api_url": _endpoint(""),
                "model": selected_model(),
                "max_tokens": settings.get("max_tokens", DEFAULT_OUTPUT_TOKENS)}
    account = settings.get("account_profile_id", "")
    if isinstance(account, str) and account:
        identity["account_profile_id"] = account
    return identity


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _endpoint(path: str) -> str:
    settings = _CONNECTION.get()
    base = (settings["api_url"] if settings is not None else os.environ.get("NEUROFORGE_BASE_URL", BASE_URL)).rstrip("/")
    if not safe_url(base):
        raise APIError("NEUROFORGE_BASE_URL must be a valid HTTP(S) URL.")
    parsed = urlsplit(base)
    if parsed.query or parsed.fragment:
        raise APIError("The API base URL cannot contain a query or fragment.")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise APIError("Remote API connections require HTTPS.")
    provider = selected_provider()
    if provider == CHATGPT and not same_api_destination(base, CHATGPT_API_URL):
        raise APIError("ChatGPT account connections require the official OpenAI API.")
    if provider != OPENAI_COMPATIBLE and uses_neuroforge_api(base):
        raise APIError("Choose the compatible API connection for NeuroForge.")
    return base + path



def selected_model() -> str:
    selected = _MODEL_SELECTION.get()
    if selected is not None:
        return selected
    settings = _CONNECTION.get()
    return settings["model"] if settings is not None else os.environ.get("NEUROFORGE_MODEL", DEFAULT_MODEL)


def is_native_profile(model: str | None = None) -> bool:
    """Check exact native capabilities without discovery or credential access.

    An automatic selection is unknown until resolve_model() succeeds; callers
    can pass that returned identity explicitly. Custom destinations never gain
    these capabilities merely by reusing the native model's name.
    """
    return native_profile_applies(selected_model() if model is None else model, _endpoint(""),
                                  selected_provider())


def resolve_model(models: list[dict] | None = None) -> str:
    """Discovery chooses only an unambiguous official model, never a fallback."""
    selected = selected_model()
    if selected != AUTO_MODEL:
        if models is not None and selected not in {item.get("id") for item in models}:
            available = ", ".join(item["id"] for item in models[:8])
            raise APIError(f"The selected model is unavailable. Available models: {available}. Choose one in Settings; no request was sent.")
        if models is not None and is_native_profile(selected):
            _qualify_native_model(next(item for item in models if item.get("id") == selected))
        return selected
    if not _uses_public_api():
        raise APIError("Choose the model identifier supplied by your custom provider; automatic selection is only available at NeuroForge.")
    available = list_models() if models is None else models
    identifiers = [item.get("id") for item in available]
    if len(identifiers) != 1 or identifiers[0] not in {MODEL, DENSE_MODEL, NATIVE_MODEL}:
        raise APIError("The service did not advertise one supported model. Choose a model explicitly in Settings; no request was sent.")
    if identifiers[0] == NATIVE_MODEL:
        _qualify_native_model(available[0])
    return identifiers[0]


def _qualify_native_model(item: dict) -> None:
    try:
        qualify_native_catalog(item)
    except ProviderProtocolError as exc:
        raise APIError(str(exc)) from exc


@contextmanager
def _hosted_generation(seconds: float):
    """Only official model requests share this local, cancellable admission slot."""
    if not _uses_public_api():
        yield
        return
    # Queueing and discovery consume the existing operation budget. The lock
    # stays held until the response closes, including partial/abandoned streams.
    with budget(seconds):
        if not _HOSTED_PENDING.acquire(blocking=False):
            raise APIError("Four hosted model requests are already active or waiting. Finish or cancel one before starting another.", 429)
        acquired = False
        try:
            while not acquired:
                checkpoint()
                acquired = _HOSTED_GENERATION.acquire(timeout=min(.05, remaining(seconds)))
            checkpoint()
            yield
        finally:
            if acquired:
                _HOSTED_GENERATION.release()
            _HOSTED_PENDING.release()


def _resolved_body(body: dict) -> dict:
    model = resolve_model()
    resolved = {**body, "model": model,
                "max_tokens": effective_max_tokens(body["max_tokens"], model=model)}
    if is_native_profile(model):
        _validate_native_body(resolved)
        resolved.update(stream=False, n=1)
    return resolved


def _require_response_model(value: dict, model: str) -> None:
    if not isinstance(value, dict) or value.get("model") != model:
        raise APIError("The response model did not match the requested model. The output was rejected; no request was replayed.")


def _request_timeout(path: str, body: dict | None) -> float:
    if path == "/models":
        return CONTROL_TIMEOUT
    if (path == "/chat/completions" and body
            and is_native_profile(body.get("model"))):
        return NATIVE_PROFILE.deadline_seconds
    if path in {"/chat/completions", "/messages", "/responses"} and not (body or {}).get("stream"):
        return JSON_CHAT_TIMEOUT
    return REQUEST_TIMEOUT


def _open(path: str, body: dict | None = None):
    data = None if body is None else _json_bytes(body)
    base_url = _endpoint("")
    headers = _headers(base_url)
    if body and body.get("stream"):
        headers["Accept"] = "text/event-stream"
    request = urllib.request.Request(base_url + path, data=data, headers=headers)
    try:
        return urllib.request.build_opener(_NoRedirect()).open(request, timeout=remaining(_request_timeout(path, body)))
    except urllib.error.HTTPError as exc:
        code = exc.code
        if selected_provider() == CHATGPT:
            try:
                # Admission can return JSON error/detail envelopes or another
                # format. Read a small bounded body solely to match known
                # codes; never display its message or retain its raw content.
                deadline = time.monotonic() + CONTROL_TIMEOUT
                response = exc.fp
                parts, size = [], 0
                while response is not None and size <= 16384:
                    checkpoint()
                    if time.monotonic() >= deadline:
                        break
                    _read_timeout(response, deadline, CONTROL_TIMEOUT)
                    read = (response.read1 if isinstance(response, http.client.HTTPResponse)
                            else response.read)
                    part = read(16385 - size)
                    if not part:
                        raw = b"".join(parts)
                        parsed = json.loads(raw) if size <= 16384 else {}
                        break
                    parts.append(part)
                    size += len(part)
                else:
                    parsed = {}
                if time.monotonic() >= deadline:
                    parsed = {}
            except (OSError, ValueError, UnicodeError):
                parsed = {}
            finally:
                exc.close()
            failure = chatgpt_failure(parsed, http_status=code)
            raise APIError(failure.message + " No request was replayed.",
                           429 if code == 429 else 502,
                           error_code=failure.code,
                           upstream_status=failure.upstream_status) from exc
        exc.close()
        if (code in {400, 413, 422} and body
                and path == "/chat/completions"
                and is_native_profile(body.get("model"))):
            raise APIError(
                "Native ERAIS did not admit this question or history. Its input "
                "must fit both the byte limits and a 512-token prompt budget; "
                "byte validation alone cannot guarantee a fit. Shorten the "
                "question or start a new conversation. No text was removed "
                "and no request was replayed.", 400, upstream_status=code,
            ) from exc
        messages = {401: "The API key was not accepted.", 403: "API access was denied.",
                    429: "The API is busy or rate-limited. Please try again later.",
                    500: "The configured service could not complete this request (HTTP 500). Try again later; local tools remain available.",
                    502: "The configured service is temporarily unavailable (HTTP 502). Try again later; local tools remain available.",
                    503: "The configured service is temporarily unavailable (HTTP 503). Try again later; local tools remain available.",
                    504: "The configured service took too long to respond (HTTP 504). Try again later; local tools remain available."}
        raise APIError(messages.get(code, f"The API returned HTTP {code}."),
                       429 if code == 429 else 502) from exc
    except DeadlineExceeded:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
            raise APIError("The service did not respond in time. No request was replayed. Try a smaller task or check the service status.", 504) from exc
        raise APIError("Cannot reach the configured API. Check your connection and try again.") from exc


def _request_json(path: str, body: dict | None = None) -> dict:
    native = (path == "/chat/completions" and body
              and is_native_profile(body.get("model")))
    maximum = NATIVE_PROFILE.response_bytes if native else MAX_RESPONSE
    deadline = time.monotonic() + _request_timeout(path, body)
    try:
        with _open(path, body) as response:
            if native:
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    raise APIError("Native ERAIS requires a buffered JSON response. "
                                   "The output was rejected; no request was replayed.")
            parts, size = [], 0
            while True:
                checkpoint()
                if time.monotonic() >= deadline:
                    raise APIError("The API response exceeded its overall time budget. No request was replayed.", 504)
                _read_timeout(response, deadline, _request_timeout(path, body))
                part = response.read1(min(16384, maximum + 1 - size)) if isinstance(response, http.client.HTTPResponse) else response.read(maximum + 1 - size)
                checkpoint()
                if time.monotonic() >= deadline:
                    raise APIError("The API response exceeded its overall time budget. No request was replayed.", 504)
                if not part:
                    break
                parts.append(part)
                size += len(part)
                if size > maximum:
                    raise APIError("The API response exceeded the safety limit.")
            raw = b"".join(parts)
        if len(raw) > maximum:
            raise APIError("The API response exceeded the safety limit.")
        result = json.loads(raw)
        if not isinstance(result, dict) or "error" in result:
            raise APIError("The API returned an unsuccessful response.")
        return result
    except (ValueError, UnicodeError) as exc:
        raise APIError("The API returned invalid JSON.") from exc
    except DeadlineExceeded:
        raise
    except (OSError, TimeoutError) as exc:
        raise APIError("The API connection was interrupted or timed out. No request was replayed; your source inputs are unchanged.", 504) from exc


def _post(path: str, body: dict) -> dict:
    return _request_json(path, body)


def _get(path: str) -> dict:
    return _request_json(path)


def _post_raw(path: str, body: dict):
    return _open(path, body)


def validate_max_tokens(max_tokens: int, *, model: str | None = None) -> int:
    """Validate the shared template, CLI and API output-token range."""
    minimum = 1 if model == NATIVE_MODEL else MIN_OUTPUT_TOKENS
    if (type(max_tokens) is not int
            or not minimum <= max_tokens <= MAX_OUTPUT_TOKENS):
        raise ValueError(f"max_tokens must be an integer from {minimum} "
                         f"to {MAX_OUTPUT_TOKENS}.")
    return max_tokens


def effective_max_tokens(max_tokens: int, *, model: str | None = None) -> int:
    """Apply the user's cap and fail locally for unsupported public API budgets."""
    selected = model or selected_model()
    native = is_native_profile(selected)
    validate_max_tokens(max_tokens, model=NATIVE_MODEL if native else None)
    settings = _CONNECTION.get()
    if settings is not None:
        max_tokens = min(max_tokens, validate_max_tokens(
            settings["max_tokens"], model=NATIVE_MODEL if native else None))
    if native:
        return min(max_tokens, NATIVE_MAX_OUTPUT_TOKENS)
    if _uses_public_api() and selected == DENSE_MODEL:
        return min(max_tokens, DENSE_MAX_OUTPUT_TOKENS)
    if _uses_public_api() and max_tokens > PUBLIC_MAX_OUTPUT_TOKENS:
        raise ValueError("The NeuroForge public API supports an output limit from "
                         f"{MIN_OUTPUT_TOKENS} to {PUBLIC_MAX_OUTPUT_TOKENS} tokens.")
    return max_tokens


def _uses_public_api() -> bool:
    return (selected_provider() == OPENAI_COMPATIBLE
            and uses_neuroforge_api(_endpoint("")))


def _json_bytes(body: dict) -> bytes:
    """Keep Unicode as UTF-8 and use one encoding for admission and transport."""
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _validate_public_messages(messages: list[Message]) -> None:
    """Match the public service's UTF-8 and conversation-shape admission rules."""
    conversation_bytes = 0
    expected_role = "user"
    for index, message in enumerate(messages):
        if not message.content.strip(_PUBLIC_WHITESPACE):
            raise ValueError(f"Message {index + 1} is empty. "
                             "Enter text or remove the empty message.")
        if "\0" in message.content:
            raise ValueError(f"Message {index + 1} contains a null character. "
                             "Remove it before sending.")
        try:
            size = len(message.content.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValueError(f"Message {index + 1} contains invalid Unicode text. "
                             "Paste valid text before sending.") from exc
        if index == 0 and message.role == "system":
            if size > PUBLIC_MAX_SYSTEM_BYTES:
                raise ValueError("The system instructions exceed the NeuroForge "
                                 f"public API's {PUBLIC_MAX_SYSTEM_BYTES}-byte limit. "
                                 "Shorten them before sending.")
        else:
            if message.role != expected_role:
                raise ValueError("The NeuroForge public API requires alternating user "
                                 "and assistant messages, with optional system instructions "
                                 "first. Start a new chat or correct the message order.")
            conversation_bytes += size
            expected_role = "assistant" if expected_role == "user" else "user"
    if expected_role != "assistant":
        raise ValueError("The conversation must end with a user message. "
                         "Add your question before sending.")
    if conversation_bytes > PUBLIC_MAX_CONVERSATION_BYTES:
        raise ValueError("This conversation exceeds the NeuroForge public API's "
                         f"{PUBLIC_MAX_CONVERSATION_BYTES}-byte limit (UTF-8). "
                         "Start a new chat or shorten the supplied text.")


def _validate_native_body(body: dict) -> None:
    """Reject unsupported native context rather than dropping user instructions."""
    native_request(body)


def _chat_body(messages: list[Message], max_tokens: int) -> dict:
    max_tokens = effective_max_tokens(max_tokens)
    if not isinstance(messages, list) or not 1 <= len(messages) <= 64:
        raise ValueError("Provide between 1 and 64 messages; start a new chat if needed.")
    if any(not isinstance(m, Message) or not isinstance(m.role, str)
           or m.role not in {"system", "user", "assistant"}
           or not isinstance(m.content, str) for m in messages):
        raise ValueError("Messages require a valid role and text content.")
    if sum(len(m.content) for m in messages) > MAX_INPUT:
        raise ValueError("This conversation is too long. Start a new chat or shorten it.")
    public_api = _uses_public_api()
    if public_api:
        _validate_public_messages(messages)
    body = {"model": selected_model(),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens}
    if is_native_profile():
        _validate_native_body(body)
    if public_api:
        # Account for JSON escaping and the defaults added by the public gateway.
        expanded = {**body, "stream": False, "temperature": 0, "n": 1}
        if len(_json_bytes(expanded)) > PUBLIC_MAX_REQUEST_BYTES:
            raise ValueError("This request exceeds the NeuroForge public API's "
                             f"{PUBLIC_MAX_REQUEST_BYTES}-byte JSON limit after escaping. "
                             "Shorten the supplied text before sending.")
    return body


def validate_chat_request(messages: list[Message],
                          max_tokens: int = DEFAULT_OUTPUT_TOKENS) -> None:
    """Check explicit capabilities without network or credential access.

    Automatic NeuroForge selection needs discovery during execution to check
    profile-specific limits. No context is silently removed at either stage.
    """
    body = _chat_body(messages, max_tokens)
    _transport().request_body(body, _endpoint(""))


def list_models() -> list[dict]:
    result = _get("/models")
    if selected_provider() == CHATGPT:
        catalog = result.get("models")
        if (not isinstance(catalog, list) or len(catalog) > 256
                or any(not isinstance(item, dict) for item in catalog)):
            raise APIError("The API returned an invalid model list.")
        models = [{"id": item.get("slug"), "display_name": item.get("display_name")}
                  for item in catalog if item.get("visibility") == "list"]
        if any(not isinstance(item["display_name"], str)
               or not item["display_name"] or len(item["display_name"]) > 200
               for item in models):
            raise APIError("The API returned an invalid model list.")
    else:
        models = result.get("data")
    if (not isinstance(models, list) or len(models) > 256
            or any(not isinstance(model, dict) or not isinstance(model.get("id"), str)
                   or not model["id"] or len(model["id"]) > 200 for model in models)
            or len({model["id"] for model in models}) != len(models)):
        raise APIError("The API returned an invalid model list.")
    return models


def chat(messages: list[Message], max_tokens: int = DEFAULT_OUTPUT_TOKENS) -> ChatResult:
    body = _chat_body(messages, max_tokens)
    timeout = (STREAM_DEADLINE if selected_provider() == CHATGPT
               else NATIVE_PROFILE.deadline_seconds if is_native_profile()
               else JSON_CHAT_TIMEOUT)
    with _hosted_generation(timeout):
        body = _resolved_body(body)
        checkpoint()
        if selected_provider() == CHATGPT:
            iterator = _chat_stream_body(body)
            while True:
                try:
                    next(iterator)
                except StopIteration as complete:
                    return complete.value
        provider = _transport()
        result = _post(provider.chat_path, provider.request_body(body, _endpoint("")))
        try:
            return _parse_chat_result(result, body)
        except ProviderProtocolError as exc:
            raise APIError(str(exc)) from exc
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise APIError("The API returned an invalid chat response.") from exc


def _chat_result(reply: ProviderReply) -> ChatResult:
    return ChatResult(reply.content, reply.prompt_tokens, reply.completion_tokens,
                      reply.total_tokens, reply.finish_reason, reply.model)


def _parse_chat_result(value: dict, body: dict) -> ChatResult:
    if is_native_profile(body["model"]):
        return _chat_result(native_reply(value, body["max_tokens"]))
    return _chat_result(_transport().parse_reply(value, body["model"], _endpoint("")))


def _read_timeout(response, deadline, idle=REQUEST_TIMEOUT):
    """Clamp a real HTTP socket to the remaining deadline without disabling TLS."""
    socket = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
    if socket is not None:
        socket.settimeout(remaining(max(.001, min(idle, deadline - time.monotonic()))))


def _bounded_lines(response, deadline):
    # HTTPResponse.readline can be kept alive forever by a peer dribbling bytes.
    # read1 performs at most one underlying read, so each chunk checks the clock.
    if not isinstance(response, http.client.HTTPResponse):
        while True:
            line = response.readline(65537)
            if not line:
                return
            yield line
    else:
        buffer = b''
        while True:
            checkpoint()
            if time.monotonic() >= deadline:
                raise APIError('The stream exceeded its overall time budget. Review any partial output.', 504)
            _read_timeout(response, deadline)
            chunk = response.read1(16384)
            if not chunk:
                if buffer:
                    yield buffer
                return
            buffer += chunk
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                yield line + b'\n'
            if len(buffer) > 65536:
                raise APIError('The streamed response exceeded its safety limit.')


def _events(response, *, deadline: float | None = None) -> Iterator[str]:
    data: list[str] = []
    size = 0
    deadline = time.monotonic() + STREAM_DEADLINE if deadline is None else deadline
    lines = _bounded_lines(response, deadline)
    while True:
        if time.monotonic() >= deadline:
            raise APIError("The stream exceeded its overall time budget. Review any partial output.")
        checkpoint()
        raw = next(lines, b"")
        checkpoint()
        if time.monotonic() >= deadline:
            raise APIError("The stream exceeded its overall time budget. Review any partial output.")
        if not raw:
            if data:
                yield "\n".join(data)
            return
        size += len(raw)
        if len(raw) > 65536 or size > MAX_RESPONSE:
            raise APIError("The streamed response exceeded its safety limit.")
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                yield "\n".join(data)
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))


def chat_stream(messages: list[Message], max_tokens: int = DEFAULT_OUTPUT_TOKENS) -> Generator[str, None, ChatResult]:
    """Yield identity-checked text; closing the iterator releases hosted admission."""
    body = _chat_body(messages, max_tokens)
    timeout = NATIVE_PROFILE.deadline_seconds if is_native_profile() else STREAM_DEADLINE
    with _hosted_generation(timeout):
        body = _resolved_body(body)
        native = is_native_profile(body["model"])
        if native:
            # The native deployment is JSON-only. One call, never an SSE retry.
            provider = _transport()
            checkpoint()
            raw = _post(provider.chat_path, {**body, "stream": False})
            try:
                result = _parse_chat_result(raw, body)
            except ProviderProtocolError as exc:
                raise APIError(str(exc)) from exc
            if result.content:
                yield result.content
            return require_complete(result, body["max_tokens"])
        body["stream"] = True
        checkpoint()
        return (yield from _chat_stream_body(body))


def chat_stream_result(messages: list[Message], max_tokens: int = DEFAULT_OUTPUT_TOKENS,
                       *, on_result=None) -> Generator[str, None, ChatResult]:
    """Yield text and notify a caller only after confirmed final completion."""
    result = yield from chat_stream(messages, max_tokens)
    if on_result is not None:
        on_result(result)
    return result


def _chat_stream_body(body: dict) -> Generator[str, None, ChatResult]:
    provider = _transport()
    destination = _endpoint("")
    decoder = provider.stream_decoder(body["model"], destination)
    deadline = time.monotonic() + STREAM_DEADLINE

    def interrupted(message: str) -> APIError:
        """Retain only text accepted before a transport/decoding interruption."""
        if decoder.started and any(part.strip() for part in decoder.parts):
            try:
                result = _chat_result(decoder.result())
            except ProviderProtocolError:
                result = ChatResult("".join(decoder.parts), model=decoder.actual_model)
            result.finish_reason = "incomplete"
            return IncompleteGeneration(result, body["max_tokens"], message=message)
        return APIError(message)
    try:
        with _post_raw(provider.chat_path, provider.request_body(body, destination)) as response:
            for event in _events(response, deadline=deadline):
                if event.strip() == "[DONE]":
                    if provider.identifier != OPENAI_COMPATIBLE:
                        raise APIError("The response ended early. The partial answer is not complete.")
                    result = _chat_result(decoder.result())
                    return require_complete(result, body["max_tokens"])
                chunk = json.loads(event)
                content, done = decoder.feed(chunk)
                if content:
                    yield content
                if done:
                    if decoder.error_message:
                        if decoder.started and any(part.strip() for part in decoder.parts):
                            result = _chat_result(decoder.result())
                            raise IncompleteGeneration(result, body["max_tokens"],
                                message=decoder.error_message,
                                error_code=decoder.error_code,
                                upstream_status=decoder.error_status)
                        raise APIError(decoder.error_message + " No request was replayed.",
                                       error_code=decoder.error_code,
                                       upstream_status=decoder.error_status)
                    result = _chat_result(decoder.result())
                    return require_complete(result, body["max_tokens"])
        raise APIError("The response ended early. The partial answer is not complete.")
    except ProviderProtocolError as exc:
        if isinstance(exc, ProviderCompletionMismatch) and decoder.started:
            result = _chat_result(decoder.result())
            if result.content.strip():
                raise IncompleteGeneration(result, body["max_tokens"],
                                           message=str(exc)) from exc
        if isinstance(exc, ProviderIdentityError):
            raise APIError(str(exc)) from exc
        raise interrupted(str(exc)) from exc
    except (ValueError, UnicodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise interrupted("The API returned a malformed stream.") from exc
    except DeadlineExceeded as exc:
        if decoder.started and any(part.strip() for part in decoder.parts):
            raise interrupted("The task reached its time limit before the answer completed.") from exc
        raise
    except IncompleteGeneration:
        raise
    except APIError as exc:
        if not exc.error_code and decoder.started and any(part.strip() for part in decoder.parts):
            raise interrupted(str(exc)) from exc
        raise
    except (OSError, TimeoutError) as exc:
        raise interrupted("The stream was interrupted. The partial answer is not complete.") from exc


def search(query: str) -> SearchResponse:
    if not isinstance(query, str) or not 3 <= len(query.strip()) <= 160:
        raise ValueError("Enter a search topic of 3 to 160 characters.")
    query = query.strip()
    if len(query.split()) > 24:
        raise ValueError("Keep the search topic to 24 words or fewer.")
    if "http://" in query.lower() or "https://" in query.lower():
        raise ValueError("Search for a topic rather than a URL. "
                         "Open the source directly if you already have its address.")
    try:
        if len(_json_bytes({"query": query})) > 2048:
            raise ValueError("The search topic exceeds the service's JSON limit.")
    except UnicodeEncodeError as exc:
        raise ValueError("The search topic contains invalid Unicode text.") from exc
    if selected_provider() != OPENAI_COMPATIBLE or not _uses_public_api():
        # Model-provider keys and OAuth tokens never accompany public search.
        # Search remains a separate NeuroForge tool when an external model is used.
        with connection_settings({"api_url": BASE_URL, "provider": OPENAI_COMPATIBLE,
                                  "api_key": "", "inherit_key": False, "anonymous": True}):
            result = _post("/search", {"query": query})
    else:
        result = _post("/search", {"query": query})
    items = result.get("results")
    if not isinstance(items, list):
        raise APIError("The search service returned an invalid result list.")
    output = []
    for item in items[:30]:
        if (isinstance(item, dict) and safe_url(item.get("url"))
                and all(isinstance(item.get(key), str) for key in ("title", "content"))):
            output.append(SearchResult(item["title"][:500], item["url"], item["content"][:12000]))
    return SearchResponse(str(result.get("retrieved_at", ""))[:100], output)


def health_check() -> tuple[bool, str]:
    try:
        models = list_models()
        if not models:
            return False, "The API returned no available models. Local workflows remain available."
        model = resolve_model(models)
        label = ("dense Gemma 4 E4B; text preview" if model == DENSE_MODEL
                 else "native ERAIS; short text preview" if model == NATIVE_MODEL
                 else "Fracture hybrid" if model == MODEL else "configured model")
        return True, f"Connected. Selected model: {model} ({label}). " \
                     "Model discovery succeeded; generation has not been tested."
    except (APIError, ValueError) as exc:
        return False, str(exc)
