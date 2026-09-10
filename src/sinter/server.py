"""Local web server — serves the GUI and proxies API calls with streaming."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from .client import (
    chat,
    chat_stream,
    search,
    list_models,
    Message,
    BASE_URL,
    _headers,
)

log = logging.getLogger(__name__)

_WEB_DIR = Path(__file__).parent / "web"
_MIME = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _cors(self) -> None:
        # CORS: wildcard is intentional — this is a local-only dev server.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            fp = _WEB_DIR / "index.html"
            if fp.exists():
                self._html(fp.read_bytes())
            else:
                self.send_error(404)
            return

        # Static assets
        if path.startswith("/static/"):
            name = path[len("/static/"):]
            fp = _WEB_DIR / name
            if fp.exists():
                ext = fp.suffix
                ct = _MIME.get(ext, "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", f"{ct}; charset=utf-8")
                self._cors()
                self.end_headers()
                self.wfile.write(fp.read_bytes())
            else:
                self.send_error(404)
            return

        if path == "/api/health":
            models = list_models()
            self._json({"ok": True, "models": [m["id"] for m in models]})
            return

        if path == "/api/templates":
            from .templates import get_builtin_template, list_builtin_templates

            tpls = []
            for name in list_builtin_templates():
                t = get_builtin_template(name)
                tpls.append({
                    "id": name,
                    "name": t.name,
                    "description": t.description,
                    "variables": [
                        {"name": v, "label": v.replace("_", " ").title()}
                        for v in t.variables
                        if v != "previous"
                    ],
                    "steps": len(t.steps),
                })
            self._json({"templates": tpls})
            return

        self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        body = json.loads(raw)

        if path == "/api/chat":
            self._api_chat(body)
        elif path == "/api/chat/stream":
            self._api_chat_stream(body)
        elif path == "/api/search":
            self._api_search(body)
        elif path == "/api/template/run":
            self._api_template_run(body)
        elif path == "/api/template/stream":
            self._api_template_stream(body)
        else:
            self.send_error(404)

    def _api_chat(self, body: dict) -> None:
        messages = [Message(role=m["role"], content=m["content"]) for m in body.get("messages", [])]
        max_tokens = body.get("max_tokens", 512)
        try:
            result = chat(messages, max_tokens=max_tokens)
            self._json({
                "content": result.content,
                "tokens": result.total_tokens,
                "finish_reason": result.finish_reason,
            })
        except urllib.error.HTTPError as exc:
            self._json({"error": exc.read().decode(errors="replace")}, exc.code)

    def _api_chat_stream(self, body: dict) -> None:
        messages = [Message(role=m["role"], content=m["content"]) for m in body.get("messages", [])]
        max_tokens = body.get("max_tokens", 512)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()

        try:
            for token in chat_stream(messages, max_tokens=max_tokens):
                self.wfile.write(f"data: {json.dumps({'t': token})}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass

    def _api_search(self, body: dict) -> None:
        query = body.get("query", "")
        try:
            result = search(query)
            self._json({
                "retrieved_at": result.retrieved_at,
                "results": [
                    {"title": r.title, "url": r.url, "content": r.content}
                    for r in result.results
                ],
            })
        except urllib.error.HTTPError as exc:
            self._json({"error": exc.read().decode(errors="replace")}, exc.code)

    def _api_template_run(self, body: dict) -> None:
        from .templates import get_builtin_template, render_prompt

        tpl_name = body.get("template", "custom")
        variables = body.get("variables", {})
        template = get_builtin_template(tpl_name)

        history: list[Message] = []
        results = []

        for step in template.steps:
            prompt = render_prompt(step.prompt, variables)

            if step.use_search:
                query = variables.get(step.search_field, "")
                if query:
                    try:
                        sr = search(query)
                        if sr.results:
                            snippets = "\n".join(
                                f"[{j+1}] {r.title}: {r.content[:300]}"
                                for j, r in enumerate(sr.results[:3])
                            )
                            prompt += f"\n\nWeb search results:\n{snippets}"
                    except Exception as exc:
                        log.warning("Search failed for %r: %s", query, exc)

            step_messages = list(history) + [Message(role="user", content=prompt)]
            result = chat(step_messages, max_tokens=step.max_tokens)
            results.append({"step": step.name, "content": result.content, "tokens": result.total_tokens})
            history.append(Message(role="user", content=prompt))
            history.append(Message(role="assistant", content=result.content))
            variables["previous"] = "\n\n".join(r["content"] for r in results)

        self._json({"results": results})

    def _api_template_stream(self, body: dict) -> None:
        from .templates import get_builtin_template, render_prompt

        tpl_name = body.get("template", "custom")
        variables = body.get("variables", {})
        template = get_builtin_template(tpl_name)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()

        history: list[Message] = []

        try:
            for si, step in enumerate(template.steps):
                # Announce step
                self.wfile.write(f"data: {json.dumps({'type': 'step', 'name': step.name, 'index': si, 'total': len(template.steps)})}\n\n".encode())
                self.wfile.flush()

                prompt = render_prompt(step.prompt, variables)
                step_messages = list(history) + [Message(role="user", content=prompt)]

                full = []
                for token in chat_stream(step_messages, max_tokens=step.max_tokens):
                    full.append(token)
                    self.wfile.write(f"data: {json.dumps({'type': 'token', 't': token})}\n\n".encode())
                    self.wfile.flush()

                content = "".join(full)
                self.wfile.write(f"data: {json.dumps({'type': 'step_done', 'content': content})}\n\n".encode())
                self.wfile.flush()

                history.append(Message(role="user", content=prompt))
                history.append(Message(role="assistant", content=content))
                variables["previous"] = content

            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass


def serve(host: str = "127.0.0.1", port: int = 8420, open_browser: bool = True) -> None:
    server = HTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}"
    print(f"\n  Sinter is running at {url}\n")
    if open_browser:
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception:
            print(f"  Open {url} in your browser to get started.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.server_close()
