"""Local-only community application. Not an Internet-facing or multi-user server.

Modified in 0.4 to integrate local preferences, community tools and RKC adapters.
"""
from __future__ import annotations

import errno
import hmac
import json
import logging
import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlsplit

from . import (
    __version__,
    client,
)
from .operations import budget
from .runtime import Application
from .runtime_routes import RouteDispatch
from .templates import resolve_template

log = logging.getLogger(__name__)
MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}


class _Disconnected:
    """Read-only disconnect probe used while a browser stream waits for admission."""
    def __init__(self, connection):
        self.connection = connection

    def is_set(self):
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            return bool(readable) and self.connection.recv(1, socket.MSG_PEEK) == b""
        except (OSError, ValueError):
            return True




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


class Handler(RouteDispatch, BaseHTTPRequestHandler):
    server_version = "Sinter"
    sys_version = ""

    def _resolve_template(self, name):
        # Preserve the existing server-level template resolution extension seam.
        return resolve_template(name)

    @property
    def app(self):
        return self.server.app

    def log_message(self, format, *args):
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

    def _send(self, body: bytes, content_type: str, status: int = 200, *, filename: str | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type + ("" if filename else "; charset=utf-8"))
        if filename:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(filename, safe=""))
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
        limit = (36 if path == "/api/transcribe" else 10 if path.startswith("/api/casebooks/") else 5 if path.startswith("/api/atlas/") else 2) * 1024 * 1024
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
            payload = {"error": str(exc)}
            if getattr(exc, "partial_result", None) is not None:
                payload["partial_result"] = exc.partial_result
            self._json(payload, exc.status)
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
        with self._request_connection(path):
            self._dispatch_get(parsed, path)



    def do_POST(self):
        self._guard(self._post)

    def _post(self):
        self._trusted(write=True)
        path = urlsplit(self.path).path
        body = self._body(path)
        with self._request_connection(path, body):
            self._dispatch_post(path, body)



    def _stream(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "close")
        self._security_headers()
        self.end_headers()
        self.close_connection = True
        try:
            with budget(700, _Disconnected(self.connection)):
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
        finally:
            close = getattr(events, "close", None)
            if close is not None:
                close()


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
