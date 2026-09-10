"""Sinter API client — handles chat, streaming, and search against the Fracture API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

BASE_URL = "https://neuroforge.io/v1"
MODEL = "erais-fracture-gemma"
_USER_AGENT = "sinter/0.1"
_KEY_FILE = Path.home() / ".sinter_key"


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
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


def _load_key() -> str:
    key = os.environ.get("NEUROFORGE_API_KEY", "")
    if key:
        return key
    if _KEY_FILE.exists():
        for line in _KEY_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "NEUROFORGE_API_KEY" and v.strip():
                return v.strip()
    return ""


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json", "User-Agent": _USER_AGENT}
    key = _load_key()
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=_headers(), method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _post_raw(path: str, body: dict) -> urllib.request.urlopen:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=_headers(), method="POST"
    )
    return urllib.request.urlopen(req, timeout=60)


def _get(path: str) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{path}", headers=_headers(), method="GET"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ── Public API ───────────────────────────────────────────────────────


def list_models() -> list[dict]:
    result = _get("/models")
    return result.get("data", [])


def chat(messages: list[Message], max_tokens: int = 512) -> ChatResult:
    body = {
        "model": MODEL,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens,
    }
    result = _post("/chat/completions", body)
    choice = result["choices"][0]
    usage = result.get("usage", {})
    return ChatResult(
        content=choice["message"]["content"],
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        finish_reason=choice.get("finish_reason", ""),
    )


def chat_stream(
    messages: list[Message], max_tokens: int = 512
) -> Iterator[str]:
    body = {
        "model": MODEL,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens,
        "stream": True,
    }
    try:
        with _post_raw("/chat/completions", body) as resp:
            for raw_line in resp:
                line = raw_line.decode().strip()
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    text = chunk["choices"][0].get("delta", {}).get("content", "")
                    if text:
                        yield text
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        yield f"\n[API error {exc.code}: {body_text}]"


def search(query: str) -> SearchResponse:
    body = {"query": query}
    result = _post("/search", body)
    return SearchResponse(
        retrieved_at=result.get("retrieved_at", ""),
        results=[
            SearchResult(title=r["title"], url=r["url"], content=r["content"])
            for r in result.get("results", [])
        ],
    )


def health_check() -> tuple[bool, str]:
    try:
        models = list_models()
        ids = [m.get("id", "?") for m in models]
        return True, f"Connected. Models: {', '.join(ids)}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)
