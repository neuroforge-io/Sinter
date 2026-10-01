"""Explicit loopback view with admission tracked until each handler completes."""

from __future__ import annotations

import math
import threading
import time
import webbrowser
from collections.abc import Callable

from .runtime import Application
from .server import LocalServer

SESSION_NOTICE = "Same local workspace. Keep the Sinter window open."
SESSION_DETAILS = (
    "Only saved work is shared; unsaved native inputs stay in the Sinter window. "
    "Scheduled watch checks are paused. Check now is an explicit service request. "
    "Closing Sinter waits for admitted local requests; unfinished jobs receive "
    "their existing cancellation request."
)


class WorkbenchCloseRefused(RuntimeError):
    """The owner must retain its runtime and inputs after a bounded close refusal."""


class OwnedLocalServer(LocalServer):
    """Keep the standalone server's dispatch rules; add owned admission tracking."""

    def __init__(self, address, app):
        self._admission_lock = threading.Lock()
        self._accepting = True
        self._active = 0
        super().__init__(address, app)

    def _admit_request(self, request, client_address):
        with self._admission_lock:
            if not self._accepting:
                return False
            self._active += 1
            return True

    def _complete_request(self, request, client_address):
        with self._admission_lock:
            self._active -= 1

    def quiesce(self):
        with self._admission_lock:
            self._accepting = False
            return self._active

    def resume(self):
        with self._admission_lock:
            self._accepting = True

    @property
    def active_requests(self):
        with self._admission_lock:
            return self._active


ServerFactory = Callable[[tuple[str, int], Application], OwnedLocalServer]


class NativeBrowserWorkbench:
    """The native controller retains its Application until owned cleanup succeeds."""

    def __init__(
        self, app: Application, *, server_factory: ServerFactory = OwnedLocalServer
    ):
        if app.desktop_shutdown is not None:
            raise ValueError("This application already has an owned browser interface.")
        self.app = app
        self.workspace = app.store.directory
        self.quit_requested = threading.Event()
        self._state_lock = threading.Lock()
        self._quit_state = "idle"
        self._quit_callback = self.request_quit
        self.server = server_factory(("127.0.0.1", 0), app)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="sinter-native-workbench-http",
            daemon=True,
        )
        self.url = f"http://127.0.0.1:{self.server.server_port}/#campaigns"
        self.closed = False
        self.phase = "running"
        self._deadline = None
        self._cleanup_thread = None
        self._cleanup_done = threading.Event()
        self._cleanup_error = None
        self.app.desktop_shutdown = self._quit_callback
        self.app.native_browser_owner = self
        try:
            self.thread.start()
        except Exception:
            try:
                self.server.server_close()
            finally:
                self._release_owner()
            raise

    def _release_owner(self):
        if self.app.desktop_shutdown is self._quit_callback:
            self.app.desktop_shutdown = None
            del self.app.native_browser_owner

    def request_quit(self):
        with self._state_lock:
            self._quit_state = "requested"
            self.quit_requested.set()

    def set_quit_state(self, state):
        with self._state_lock:
            self._quit_state = state

    def session_state(self):
        with self._state_lock:
            state = self._quit_state
        return {"state": state, "active_requests": self.server.active_requests}

    def open_browser(self, opener: Callable[[str], bool] | None = None) -> bool:
        if self.closed or self.phase not in {"running", "refused"}:
            raise ValueError("This browser workbench is closed or stopping.")
        try:
            return bool((opener or webbrowser.open)(self.url))
        except (OSError, webbrowser.Error):
            return False

    def begin_close(self, timeout=5):
        """Start a bounded close, without blocking the GUI or closing its runtime."""
        if (
            type(timeout) not in {int, float}
            or not math.isfinite(timeout)
            or not 0 < timeout <= 5
        ):
            raise ValueError(
                "Close wait must be greater than zero and at most five seconds."
            )
        if self.closed:
            return
        if self.phase in {"draining", "stopping"}:
            return
        self._deadline = time.monotonic() + timeout
        self.server.quiesce()
        self.phase = "draining"
        self.set_quit_state("waiting")

    def cancel_close(self):
        if self.phase != "draining":
            return False
        self.server.resume()
        self.phase = "running"
        self.set_quit_state("cancelled")
        return True

    def _cleanup(self):
        # Retain every cleanup attempt's error and always attempt later cleanup.
        errors = []
        try:
            if self.thread.is_alive():
                self.server.shutdown()
        except Exception as exc:
            errors.append(exc)
        try:
            self.server.server_close()
        except Exception as exc:
            errors.append(exc)
        try:
            self.thread.join(timeout=1)
            if self.thread.is_alive():
                errors.append(RuntimeError("The owned local listener did not stop."))
        except Exception as exc:
            errors.append(exc)
        self._cleanup_error = errors[0] if errors else None
        self._cleanup_done.set()

    def poll_close(self):
        """Return closed/waiting/refused/failed; only successful cleanup releases ownership."""
        if self.closed:
            return "closed"
        if self.phase not in {"draining", "stopping"}:
            return self.phase
        if self._cleanup_thread is not None:
            if self._cleanup_done.is_set():
                self._cleanup_thread.join()
                if self._cleanup_error is not None:
                    self.phase = "failed"
                    self.set_quit_state("failed")
                    return "failed"
                self.closed = True
                self.phase = "closed"
                self._release_owner()
                return "closed"
            if time.monotonic() >= self._deadline:
                self.phase = "failed"
                self.set_quit_state("failed")
                return "failed"
            return "waiting"
        if self.server.active_requests:
            if time.monotonic() >= self._deadline:
                self.server.resume()
                self.phase = "refused"
                self.set_quit_state("refused")
                return "refused"
            return "waiting"
        self.phase = "stopping"
        self._cleanup_done.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup, name="sinter-native-workbench-close", daemon=True
        )
        try:
            self._cleanup_thread.start()
        except Exception as exc:
            self._cleanup_thread = None
            self._cleanup_error = exc
            self.phase = "failed"
            self.set_quit_state("failed")
            return "failed"
        return "waiting"

    def retry_close(self, timeout=5):
        """An explicit retry may consume finished cleanup or start a fresh attempt."""
        if self.phase == "failed" and self._cleanup_done.is_set():
            if self._cleanup_error is not None:
                self._cleanup_thread.join()
                self._cleanup_thread = None
                self._cleanup_done.clear()
        self.begin_close(timeout)

    def close(self, timeout=5):
        """Bounded emergency/test cleanup. GUI normally uses nonblocking polling."""
        self.retry_close(timeout)
        while True:
            state = self.poll_close()
            if state == "closed":
                return
            if state in {"refused", "failed"}:
                raise WorkbenchCloseRefused(
                    "Local requests or listener cleanup did not finish. "
                    "The native runtime and inputs must remain open; retry explicitly."
                ) from self._cleanup_error
            self._cleanup_done.wait(0.01)
