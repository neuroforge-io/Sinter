"""Sinter 0.3 local-only web application with bounded resources and same-origin protection.

Modified from the original development server. Not an Internet-facing or multi-user server.
"""
from __future__ import annotations

import errno
import hmac
import json
import logging
import secrets
import socket
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__, client, speech, workbench
from .evidence import collect, text
from .grants import screen
from .jobs import Jobs
from .meetings import parse_transcript
from .store import Store, calendar
from .templates import available_templates, resolve_template, template_events

log = logging.getLogger(__name__)
MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}


class Application:
    def __init__(self, directory=None):
        self.store = Store(directory)
        self.jobs = Jobs()
        self.token = secrets.token_urlsafe(32)
        self.stop = threading.Event()

    def scheduler(self):
        while not self.stop.wait(5):
            try:
                self.store.run_due()
            except Exception:
                log.exception("Watch scheduler could not complete a check")

    def close(self):
        self.stop.set()
        self.jobs.close()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16
    allow_reuse_address = True

    def __init__(self, address, app):
        self.app = app
        self._connections = threading.BoundedSemaphore(16)
        super().__init__(address, Handler)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(15)
        return request, address

    def process_request(self, request, client_address):
        if not self._connections.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()


class LocalIPv6Server(LocalServer):
    address_family = socket.AF_INET6


class Handler(BaseHTTPRequestHandler):
    server_version = "Sinter"
    sys_version = ""

    @property
    def app(self):
        return self.server.app

    def log_message(self, format, *args):
        # Avoid logging private paths, queries, prompts or recording filenames.
        pass

    def _security_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
                         "frame-ancestors 'none'; form-action 'self'")

    def _send(self, body: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, value, status=200):
        self._send(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json", status)

    def _trusted(self, write=False):
        hosts = self.headers.get_all("Host", [])
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if len(hosts) != 1 or hosts[0].lower() not in allowed:
            raise PermissionError("Open Sinter using the localhost address printed by the launcher.")
        origin = self.headers.get("Origin")
        if origin is not None and origin != "http://" + hosts[0]:
            raise PermissionError("Requests must come from this Sinter window.")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise PermissionError("Cross-site requests are not allowed.")
        if write and not hmac.compare_digest(self.headers.get("X-Sinter-Token", ""), self.app.token):
            raise PermissionError("Your Sinter session changed. Reload the page before trying again.")

    def _body(self, path):
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Send application/json data.")
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Chunked request bodies are not supported.")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1:
            raise ValueError("A single Content-Length is required.")
        try:
            length = int(lengths[0])
        except ValueError as exc:
            raise ValueError("Invalid Content-Length.") from exc
        limit = 36 * 1024 * 1024 if path == "/api/transcribe" else 2 * 1024 * 1024
        if not 0 < length <= limit:
            raise ValueError("The request is empty or too large. Split it into smaller inputs.")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("The request was interrupted before all data arrived.")
        def invalid_constant(value):
            raise ValueError("JSON must not contain NaN or Infinity.")
        body = json.loads(raw, parse_constant=invalid_constant)
        if not isinstance(body, dict):
            raise ValueError("The request must be a JSON object.")
        return body

    def _guard(self, operation):
        try:
            operation()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except PermissionError as exc:
            self._json({"error": str(exc)}, 403)
        except (ValueError, TypeError, UnicodeError) as exc:
            self._json({"error": str(exc)}, 400)
        except KeyError:
            self._json({"error": "That item was not found or has expired."}, 404)
        except client.APIError as exc:
            self._json({"error": str(exc)}, exc.status)
        except Exception:
            log.exception("A local API operation failed")
            self._json({"error": "Sinter could not complete this operation. Your original inputs are unchanged."}, 500)

    def do_GET(self):
        self._guard(self._get)

    def do_HEAD(self):
        self._guard(self._get)

    def do_OPTIONS(self):
        self._json({"error": "Cross-origin access is not enabled."}, 403)

    def _get(self):
        self._trusted()
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path in {"/", "/index.html"} or path.startswith("/static/"):
            name = "index.html" if path in {"/", "/index.html"} else path[8:]
            if not name or any(character in name for character in ("/", "\\", "%")) or name.startswith("."):
                raise KeyError("Invalid asset")
            suffix = "." + name.rsplit(".", 1)[-1]
            if suffix not in MIME:
                raise KeyError("Unknown asset type")
            asset = resources.files("sinter").joinpath("web").joinpath(name)
            if not asset.is_file():
                raise KeyError("Unknown asset")
            self._send(asset.read_bytes(), MIME[suffix])
        elif path == "/api/session":
            self._json({"token": self.app.token, "version": __version__, "workflows": workbench.WORKFLOWS})
        elif path == "/api/health":
            ok, message = client.health_check()
            self._json({"ok": ok, "message": message}, 200 if ok else 503)
        elif path == "/api/templates":
            self._json({"templates": [{"id": key, "name": template.name, "description": template.description,
                                       "variables": [{"name": value, "label": value.replace("_", " ").title()} for value in template.variables],
                                       "steps": len(template.steps)} for key, template in available_templates().items()]})
        elif path == "/api/example":
            query = parse_qs(parsed.query, max_num_fields=8)
            self._json(workbench.example(query.get("workflow", ["brief"])[0]))
        elif path.startswith("/api/jobs/"):
            self._json(self.app.jobs.get(path.removeprefix("/api/jobs/")))
        elif path == "/api/reports":
            self._json({"reports": self.app.store.reports()})
        elif path.startswith("/api/reports/"):
            self._json(self.app.store.report(path.removeprefix("/api/reports/")))
        elif path == "/api/watches":
            self._json({"watches": self.app.store.watches()})
        elif path == "/api/calendar":
            self._send(calendar(self.app.store.watches()).encode("utf-8"), "text/calendar")
        elif path == "/api/speech":
            self._json(speech.capabilities())
        else:
            raise KeyError("Unknown route")

    def do_POST(self):
        self._guard(self._post)

    def _post(self):
        self._trusted(write=True)
        path = urlsplit(self.path).path
        body = self._body(path)
        if path == "/api/transcript/export":
            from .transcript_export import export_transcript
            self._json({"content": export_transcript(body.get("transcript", {}), body.get("format", "json"))})
        elif path in {"/api/chat", "/api/chat/stream"}:
            rows = body.get("messages")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Provide a list of messages.")
            messages = [client.Message(row.get("role"), row.get("content")) for row in rows]
            maximum = body.get("max_tokens", 512)
            client._chat_body(messages, maximum)
            if path.endswith("/stream"):
                self._stream(({"type": "token", "t": token} for token in client.chat_stream(messages, maximum)))
            else:
                result = client.chat(messages, maximum)
                self._json({"content": result.content, "tokens": result.total_tokens, "finish_reason": result.finish_reason})
        elif path == "/api/search":
            self._json(asdict(client.search(body.get("query", ""))))
        elif path in {"/api/template/run", "/api/template/stream"}:
            template = resolve_template(body.get("template", "custom"))
            variables = body.get("variables", {})
            if not isinstance(variables, dict):
                raise ValueError("Template variables must be an object.")
            events = template_events(template, variables, stream=path.endswith("/stream"))
            if path.endswith("/stream"):
                self._stream(events)
            else:
                collected = list(events)
                self._json({"results": [event for event in collected if event["type"] == "step_done"],
                            "sources": [event for event in collected if event["type"] == "sources"]})
        elif path == "/api/workbench":
            self._json({"id": self.app.jobs.submit(lambda progress: workbench.run(body, progress))}, 202)
        elif path == "/api/jobs/cancel":
            self.app.jobs.cancel(text(body.get("id", ""), "Job ID", 100, True))
            self._json({"ok": True})
        elif path == "/api/reports":
            self._json({"id": self.app.store.save_report(body.get("report"))}, 201)
        elif path == "/api/reports/delete":
            self.app.store.delete_report(body.get("id", ""))
            self._json({"ok": True})
        elif path == "/api/watches":
            if body.get("consent") is not True:
                raise ValueError("Confirm that this query may be sent on the selected schedule.")
            identifier = self.app.store.add_watch(body.get("title", ""), body.get("query", ""),
                                                  body.get("interval", 86400), body.get("deadline", ""))
            self._json({"id": identifier}, 201)
        elif path == "/api/watches/update":
            self.app.store.change_watch(body.get("id", ""), body.get("enabled"))
            self._json({"ok": True})
        elif path == "/api/watches/delete":
            self.app.store.delete_watch(body.get("id", ""))
            self._json({"ok": True})
        elif path == "/api/watches/check":
            self._json({"id": self.app.jobs.submit(self._check_watches)}, 202)
        elif path == "/api/screen":
            self._json(screen(body.get("profile", {}), body.get("criteria", []), collect(body.get("sources", []))))
        elif path == "/api/transcript/inspect":
            segments = parse_transcript(body.get("text", ""))
            self._json({"speakers": sorted({segment.speaker for segment in segments}), "segments": len(segments)})
        elif path == "/api/transcribe":
            self._json({"id": self.app.jobs.submit(lambda progress: speech.transcribe_upload(body, progress))}, 202)
        else:
            raise KeyError("Unknown route")

    def _check_watches(self, progress):
        progress("Checking due search watches")
        return {"checked": self.app.store.run_due()}

    def _stream(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "close")
        self._security_headers()
        self.end_headers()
        self.close_connection = True
        try:
            for event in events:
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            message = str(exc) if isinstance(exc, (client.APIError, ValueError)) else "The stream failed. Partial output is not complete."
            try:
                self.wfile.write(("data: " + json.dumps({"type": "error", "error": message}) + "\n\n").encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass


def make_server(host="127.0.0.1", port=8420, directory=None):
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Sinter is local-only. Use 127.0.0.1, localhost or ::1, not a public interface.")
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Choose a port from 0 to 65535 (0 selects a free port).")
    app = Application(directory)
    server_type = LocalIPv6Server if host == "::1" else LocalServer
    try:
        return server_type(("127.0.0.1" if host == "localhost" else host, port), app)
    except Exception:
        app.close()
        raise


def serve(host="127.0.0.1", port=8420, open_browser=True):
    try:
        server = make_server(host, port)
    except OSError as exc:
        if port != 8420 or exc.errno != errno.EADDRINUSE:
            raise
        server = make_server(host, 0)
    address = "[::1]" if host == "::1" else "127.0.0.1"
    url = f"http://{address}:{server.server_port}"
    print(f"\nSinter {__version__} is ready: {url}\nKeep this window open. Press Ctrl+C to stop.\n")
    threading.Thread(target=server.app.scheduler, daemon=True, name="sinter-watches").start()
    if open_browser:
        import webbrowser
        try:
            if not webbrowser.open(url):
                print("Open the address above in your browser.")
        except Exception:
            print("Open the address above in your browser.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSinter stopped.")
    finally:
        server.app.close()
        server.server_close()
