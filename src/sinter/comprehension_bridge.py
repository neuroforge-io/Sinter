"""Local-only bridge from Sinter to the comprehension episode API.

The bridge is deliberately explicit: only the comprehension episode routes are
forwarded, the destination must be a loopback HTTP endpoint, and responses are
bounded. Sinter remains the application; ERAIS owns the comprehension state.
"""
from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ENV = "SINTER_COMPREHENSION_URL"
DEFAULT = "http://127.0.0.1:8792"
MAX_BODY = 8 * 1024 * 1024
EPISODE = re.compile(
    r"/api/comprehension/episodes"
    r"(?:/[0-9a-f]{32}(?:/(?:lesson|task|transfer|observe|clarify|correct|"
    r"objective|ask|situation|inspection))?)?\Z")
HEALTH = "/api/health"
ORGANIZATIONAL = "/api/organizational/interpret"


class ComprehensionUnavailable(ValueError):
    """The configured local comprehension service is unavailable."""


def _base() -> tuple[str, int]:
    value = os.environ.get(ENV, DEFAULT).strip()
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("SINTER_COMPREHENSION_URL must be a loopback HTTP origin.")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("The comprehension service must be on this computer.")
    try:
        port = parsed.port or 80
    except ValueError as error:
        raise ValueError("The comprehension service port is invalid.") from error
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return f"http://{host}:{port}", port


def _allowed(path: str) -> bool:
    return (path in {HEALTH, ORGANIZATIONAL}
            or bool(EPISODE.fullmatch(path)))


def request(path: str, *, method: str = "GET", payload=None) -> dict:
    if not _allowed(path):
        raise ValueError("This comprehension route is not available.")
    base, _ = _base()
    data = None if payload is None else json.dumps(
        payload, allow_nan=False).encode("utf-8")
    if data is not None and len(data) > MAX_BODY:
        raise ValueError("The comprehension request is too large.")
    request = Request(
        base + path, data=data, method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read(MAX_BODY + 1)
    except HTTPError as error:
        raw = error.read(4096)
        try:
            value = json.loads(raw)
        except ValueError:
            value = {"error": "The comprehension service rejected the request."}
        raise ValueError(str(value.get("error") or "The comprehension request failed.")) from error
    except (URLError, OSError) as error:
        raise ComprehensionUnavailable(
            "The comprehension service is unavailable. Start the local "
            "comprehension API or set SINTER_COMPREHENSION_URL.") from error
    if len(raw) > MAX_BODY:
        raise ValueError("The comprehension response is too large.")
    try:
        value = json.loads(raw)
    except ValueError as error:
        raise ValueError("The comprehension service returned invalid JSON.") from error
    if not isinstance(value, dict):
        raise ValueError("The comprehension service returned an invalid response.")
    return value


__all__ = [
    "ComprehensionUnavailable", "ENV", "HEALTH", "ORGANIZATIONAL", "request",
]
