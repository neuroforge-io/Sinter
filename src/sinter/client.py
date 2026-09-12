"""Bounded public Fracture client. Modified in 0.4 for isolated connection settings."""
from __future__ import annotations

import json
import http.client
import os
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Iterator
from urllib.parse import urlsplit

from . import __version__
from .operations import checkpoint, remaining, DeadlineExceeded

BASE_URL = "https://neuroforge.io/v1"
MODEL = "erais-fracture-gemma"
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


@contextmanager
def connection_settings(settings):
    """Bind an immutable configuration snapshot to this request or worker."""
    token = _CONNECTION.set(dict(settings))
    try:
        yield
    finally:
        _CONNECTION.reset(token)


class APIError(RuntimeError):
    """An error safe to display without upstream bodies or credentials."""
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


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


class IncompleteGeneration(APIError):
    """A received answer that must remain visibly incomplete, with no replay."""

    def __init__(self, result: ChatResult, max_tokens: int):
        self.result = result
        self.max_tokens = max_tokens
        if result.finish_reason == "length":
            message = (f"The answer reached its {max_tokens}-token output limit. "
                       "The partial text is available for review. Shorten the requested "
                       "answer or raise the output limit within your service's range.")
        else:
            message = "The model stopped before completing its answer. Review the partial text."
        super().__init__(message + " No request was replayed.")


def require_complete(result: ChatResult, max_tokens: int) -> ChatResult:
    """Apply the same explicit completion policy to JSON and streamed answers."""
    if not isinstance(result.content, str) or not result.content.strip():
        raise APIError("The model returned no answer. No request was replayed. "
                       "Try a clearer or shorter prompt.")
    if not isinstance(result.finish_reason, str):
        raise APIError("The API returned an invalid completion reason.")
    if result.finish_reason not in {"", "stop"}:
        raise IncompleteGeneration(result, max_tokens)
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


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": f"sinter/{__version__}"}
    settings = _CONNECTION.get()
    if settings is None:
        key = _load_key()
    else:
        key = settings.get("api_key", "")
        if not key and settings.get("inherit_key"):
            key = _load_key()
    if key:
        if any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise APIError("The API key contains invalid characters.")
        headers["Authorization"] = f"Bearer {key}"
    return headers


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
    return base + path


def _request_timeout(path: str, body: dict | None) -> float:
    if path == "/models":
        return CONTROL_TIMEOUT
    if path == "/chat/completions" and not (body or {}).get("stream"):
        return JSON_CHAT_TIMEOUT
    return REQUEST_TIMEOUT


def _open(path: str, body: dict | None = None):
    data = None if body is None else _json_bytes(body)
    headers = _headers()
    if body and body.get("stream"):
        headers["Accept"] = "text/event-stream"
    request = urllib.request.Request(_endpoint(path), data=data, headers=headers)
    try:
        return urllib.request.build_opener(_NoRedirect()).open(request, timeout=remaining(_request_timeout(path, body)))
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        messages = {401: "The API key was not accepted.", 403: "API access was denied.",
                    429: "The API is busy or rate-limited. Please try again later."}
        raise APIError(messages.get(code, f"The API returned HTTP {code}."),
                       429 if code == 429 else 502) from exc
    except DeadlineExceeded:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
            raise APIError("The service did not respond in time. No request was replayed. Try a smaller task or check the service status.", 504) from exc
        raise APIError("Cannot reach the configured API. Check your connection and try again.") from exc


def _request_json(path: str, body: dict | None = None) -> dict:
    deadline = time.monotonic() + _request_timeout(path, body)
    try:
        with _open(path, body) as response:
            parts, size = [], 0
            while True:
                checkpoint()
                if time.monotonic() >= deadline:
                    raise APIError("The API response exceeded its overall time budget. No request was replayed.", 504)
                _read_timeout(response, deadline, _request_timeout(path, body))
                part = response.read1(min(16384, MAX_RESPONSE + 1 - size)) if isinstance(response, http.client.HTTPResponse) else response.read(MAX_RESPONSE + 1 - size)
                checkpoint()
                if time.monotonic() >= deadline:
                    raise APIError("The API response exceeded its overall time budget. No request was replayed.", 504)
                if not part:
                    break
                parts.append(part); size += len(part)
                if size > MAX_RESPONSE:
                    raise APIError("The API response exceeded the safety limit.")
            raw = b"".join(parts)
        if len(raw) > MAX_RESPONSE:
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


def validate_max_tokens(max_tokens: int) -> int:
    """Validate the shared template, CLI and API output-token range."""
    if (type(max_tokens) is not int
            or not MIN_OUTPUT_TOKENS <= max_tokens <= MAX_OUTPUT_TOKENS):
        raise ValueError(f"max_tokens must be an integer from {MIN_OUTPUT_TOKENS} "
                         f"to {MAX_OUTPUT_TOKENS}.")
    return max_tokens


def effective_max_tokens(max_tokens: int) -> int:
    """Apply the user's cap and fail locally for unsupported public API budgets."""
    validate_max_tokens(max_tokens)
    settings = _CONNECTION.get()
    if settings is not None:
        max_tokens = min(max_tokens, validate_max_tokens(settings["max_tokens"]))
    if _uses_public_api() and max_tokens > PUBLIC_MAX_OUTPUT_TOKENS:
        raise ValueError("The NeuroForge public API supports an output limit from "
                         f"{MIN_OUTPUT_TOKENS} to {PUBLIC_MAX_OUTPUT_TOKENS} tokens.")
    return max_tokens


def _uses_public_api() -> bool:
    endpoint = urlsplit(_endpoint(""))
    return endpoint.hostname == "neuroforge.io" and endpoint.path.rstrip("/") == "/v1"


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
    settings = _CONNECTION.get()
    body = {"model": settings["model"] if settings is not None else os.environ.get("NEUROFORGE_MODEL", MODEL),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens}
    if public_api:
        # Account for JSON escaping and the defaults added by the public gateway.
        expanded = {**body, "stream": False, "temperature": 0, "n": 1}
        if len(_json_bytes(expanded)) > PUBLIC_MAX_REQUEST_BYTES:
            raise ValueError("This request exceeds the NeuroForge public API's "
                             f"{PUBLIC_MAX_REQUEST_BYTES}-byte JSON limit after escaping. "
                             "Shorten the supplied text before sending.")
    return body


def list_models() -> list[dict]:
    models = _get("/models").get("data")
    if not isinstance(models, list) or any(not isinstance(model, dict) for model in models):
        raise APIError("The API returned an invalid model list.")
    return models


def chat(messages: list[Message], max_tokens: int = 512) -> ChatResult:
    result = _post("/chat/completions", _chat_body(messages, max_tokens))
    try:
        choice = result["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str) or not isinstance(choice.get("finish_reason", ""), str):
            raise ValueError("non-text reply")
        usage = result.get("usage") or {}
        return ChatResult(content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                          usage.get("total_tokens", 0), choice.get("finish_reason", ""))
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise APIError("The API returned an invalid chat response.") from exc


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


def chat_stream(messages: list[Message], max_tokens: int = 512) -> Generator[str, None, ChatResult]:
    """Yield text and return final metadata to callers that retain the generator result."""
    body = _chat_body(messages, max_tokens)
    body["stream"] = True
    finish_reason = ""
    parts: list[str] = []
    usage: dict = {}
    deadline = time.monotonic() + STREAM_DEADLINE
    try:
        with _post_raw("/chat/completions", body) as response:
            for event in _events(response, deadline=deadline):
                if event.strip() == "[DONE]":
                    result = ChatResult("".join(parts), usage.get("prompt_tokens", 0),
                                        usage.get("completion_tokens", 0), usage.get("total_tokens", 0),
                                        finish_reason)
                    return require_complete(result, body["max_tokens"])
                chunk = json.loads(event)
                if not isinstance(chunk, dict) or "error" in chunk:
                    raise APIError("The API reported an error during generation.")
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                choice = choices[0]
                finish_reason = choice.get("finish_reason") or finish_reason
                content = choice.get("delta", {}).get("content")
                if content is not None:
                    if not isinstance(content, str):
                        raise ValueError("non-text delta")
                    parts.append(content)
                    yield content
        raise APIError("The response ended early. The partial answer is not complete.")
    except (ValueError, UnicodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise APIError("The API returned a malformed stream.") from exc
    except DeadlineExceeded:
        raise
    except (OSError, TimeoutError) as exc:
        raise APIError("The stream was interrupted. The partial answer is not complete.") from exc


def search(query: str) -> SearchResponse:
    if not isinstance(query, str) or not query.strip() or len(query) > 1024:
        raise ValueError("Enter a search query of 1 to 1024 characters.")
    result = _post("/search", {"query": query.strip()})
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
        return True, "Connected. Models: " + ", ".join(str(model.get("id", "?")) for model in models)
    except (APIError, ValueError) as exc:
        return False, str(exc)
