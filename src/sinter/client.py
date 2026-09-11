"""Bounded public Fracture client. Modified in 0.4 for isolated connection settings."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

from . import __version__

BASE_URL = "https://neuroforge.io/v1"
MODEL = "erais-fracture-gemma"
_KEY_FILE = Path.home() / ".sinter_key"
MAX_RESPONSE = 2 * 1024 * 1024
MAX_INPUT = 64000
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


def _open(path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(_endpoint(path), data=data, headers=_headers())
    try:
        return urllib.request.build_opener(_NoRedirect()).open(request, timeout=30)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        messages = {401: "The API key was not accepted.", 403: "API access was denied.",
                    429: "The API is busy or rate-limited. Please try again later."}
        raise APIError(messages.get(code, f"The API returned HTTP {code}."),
                       429 if code == 429 else 502) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise APIError("Cannot reach NeuroForge. Check your connection and try again.") from exc


def _request_json(path: str, body: dict | None = None) -> dict:
    try:
        with _open(path, body) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise APIError("The API response exceeded the safety limit.")
        result = json.loads(raw)
        if not isinstance(result, dict) or "error" in result:
            raise APIError("The API returned an unsuccessful response.")
        return result
    except (ValueError, UnicodeError) as exc:
        raise APIError("The API returned invalid JSON.") from exc
    except (OSError, TimeoutError) as exc:
        raise APIError("The API connection was interrupted. Please retry.") from exc


def _post(path: str, body: dict) -> dict:
    return _request_json(path, body)


def _get(path: str) -> dict:
    return _request_json(path)


def _post_raw(path: str, body: dict):
    return _open(path, body)


def _chat_body(messages: list[Message], max_tokens: int) -> dict:
    if type(max_tokens) is not int or not 1 <= max_tokens <= 8192:
        raise ValueError("max_tokens must be an integer from 1 to 8192.")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 64:
        raise ValueError("Provide between 1 and 64 messages; start a new chat if needed.")
    if any(not isinstance(m, Message) or not isinstance(m.role, str)
           or m.role not in {"system", "user", "assistant"}
           or not isinstance(m.content, str) for m in messages):
        raise ValueError("Messages require a valid role and text content.")
    if sum(len(m.content) for m in messages) > MAX_INPUT:
        raise ValueError("This conversation is too long. Start a new chat or shorten it.")
    settings = _CONNECTION.get()
    if settings is not None:
        max_tokens = min(max_tokens, settings["max_tokens"])
    return {"model": settings["model"] if settings is not None else os.environ.get("NEUROFORGE_MODEL", MODEL),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens}


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
        if not isinstance(content, str):
            raise ValueError("non-text reply")
        usage = result.get("usage") or {}
        return ChatResult(content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                          usage.get("total_tokens", 0), choice.get("finish_reason", ""))
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise APIError("The API returned an invalid chat response.") from exc


def _events(response) -> Iterator[str]:
    data: list[str] = []
    size, started = 0, time.monotonic()
    while True:
        raw = response.readline(65537)
        if not raw:
            if data:
                yield "\n".join(data)
            return
        size += len(raw)
        if len(raw) > 65536 or size > MAX_RESPONSE or time.monotonic() - started > 120:
            raise APIError("The streamed response exceeded its safety limit.")
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                yield "\n".join(data)
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))


def chat_stream(messages: list[Message], max_tokens: int = 512) -> Iterator[str]:
    body = _chat_body(messages, max_tokens)
    body["stream"] = True
    finish_reason = ""
    try:
        with _post_raw("/chat/completions", body) as response:
            for event in _events(response):
                if event.strip() == "[DONE]":
                    if finish_reason not in {"", "stop"}:
                        raise APIError("Generation stopped before a complete answer. Review the partial output.")
                    return
                chunk = json.loads(event)
                if not isinstance(chunk, dict) or "error" in chunk:
                    raise APIError("The API reported an error during generation.")
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                choice = choices[0]
                finish_reason = choice.get("finish_reason") or finish_reason
                content = choice.get("delta", {}).get("content")
                if content is not None:
                    if not isinstance(content, str):
                        raise ValueError("non-text delta")
                    yield content
        raise APIError("The response ended early. The partial answer is not complete.")
    except (ValueError, UnicodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise APIError("The API returned a malformed stream.") from exc
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
