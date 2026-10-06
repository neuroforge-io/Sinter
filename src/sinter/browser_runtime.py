"""Browser adapter for the existing domain routes; no HTTP server or remote storage.

Pyodide runs this module in a dedicated worker. The host owns IndexedDB commits,
network transport and single-tab ownership. No JavaScript business-rule fork.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from . import campaigns, casebooks, client
from .jobs import Job, Jobs
from .preferences import Preferences, validate as validate_preferences
from .runtime import _Capture, _public_error
from .store import Store

SCHEMA = "sinter-browser-workspace/v1"
MAX_BACKUP = 25 * 1024 * 1024
FILES = ("workspace.sqlite3", "campaigns.sqlite3", "preferences.json")
ROOT = Path("/sinter-workspace")


class BrowserJobs(Jobs):
    """Bounded, single-worker jobs. UI stays responsive in a separate JS thread."""
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}

    def submit(self, operation, *, label="Task", timeout=1800):
        from .operations import budget
        job = Job(uuid.uuid4().hex, label=label)
        self._purge()
        self._jobs[job.id] = job
        def progress(message):
            job.status, job.message = "running", str(message)[:500]
            job.started_at = job.started_at or time.time()
            job.updated_at = time.time()
        try:
            with budget(timeout, job.cancel):
                progress("Preparing in this browser")
                job.result = operation(progress)
            job.status, job.message = "done", "Ready for review"
        except Exception as exc:
            error = _public_error(exc)
            job.status, job.error = "failed", str(error)
            job.result = error.partial_result
        job.completed_at = time.time()
        return job.id

    def close(self):
        self._jobs.clear()


class BrowserApplication:
    def __init__(self, directory=None):
        self.store = Store(ROOT if directory is None else directory)
        self.preferences = Preferences(self.store.directory)
        self.casebooks = casebooks.Casebooks(self.store)
        self.campaigns = campaigns.CampaignStore(self.store.directory)
        self.jobs = BrowserJobs()
        self.token = "browser-local-worker"
        self.desktop_shutdown = None
        self.accounts = SimpleNamespace(status=lambda: {
            "available": False, "connected": False,
            "message": "Account sign-in needs the installed app. This webpage uses the anonymous NeuroForge preview.",
        })

    def connection(self):
        return {**self.preferences.connection(), "api_url": client.BASE_URL,
                "provider": "openai-compatible", "api_key": "",
                "inherit_key": False, "anonymous": True}


class Capture(_Capture):
    def _stream(self, events):
        self.result = {"events": list(events)}


def configure_network(transport):
    """Use only the fixed same-origin public API; preserve native validation."""
    def request_json(path, body=None):
        if path not in {"/search", "/models", "/chat/completions"}:
            raise client.APIError("This endpoint is unavailable in the webpage.")
        response = json.loads(str(transport(path, json.dumps(body, ensure_ascii=False))))
        if response["status"] >= 400:
            status = response["status"]
            message = ("Search/API rate limit reached. Wait at least 60 seconds before trying again."
                       if status == 429 else
                       "The public service is busy or unavailable. Your local work is unchanged; no request was replayed.")
            raise client.APIError(message, status, error_code=response.get("code", "provider_error"))
        result = response["data"]
        if not isinstance(result, dict) or "error" in result:
            raise client.APIError("The public service returned an invalid response. No request was replayed.")
        return result
    client._request_json = request_json


app = None


def initialize():
    global app
    app = BrowserApplication()
    return {"schema": SCHEMA, "version": __import__("sinter").__version__}


def snapshot():
    return {name: (ROOT / name).read_bytes() for name in FILES if (ROOT / name).exists()}


def restore_files(files):
    global app
    for name in FILES:
        (ROOT / name).unlink(missing_ok=True)
    for name, data in files.items():
        if name not in FILES:
            raise ValueError("Unknown workspace file.")
        (ROOT / name).write_bytes(bytes(data))
    app = BrowserApplication()


def backup(target=None):
    target = target or app
    value = {
        "schema": SCHEMA,
        "version": __import__("sinter").__version__,
        "exported_at": time.time(),
        "casebooks": [target.casebooks.get(row["id"])["document"] for row in target.casebooks.list()],
        "campaigns": [target.campaigns.get(row["id"])["document"] for row in target.campaigns.list()],
        "reports": [target.store.report(row["id"]) for row in target.store.reports()],
        "watches": [{key: row[key] for key in ("title", "query", "interval", "deadline")} for row in target.store.watches()],
        "settings": target.preferences.snapshot(),
        "notice": "Unencrypted saved work only. Unsaved editor inputs are not included. Imported watches start paused.",
    }
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(raw.encode()) > MAX_BACKUP:
        raise ValueError("The workspace exceeds the 25 MB browser backup limit. Export individual projects first.")
    return value


def prepare_import(value):
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("Choose a sinter-browser-workspace/v1 JSON backup. Project backups belong in their project editor.")
    allowed = {"schema", "version", "exported_at", "casebooks", "campaigns", "reports", "watches", "settings", "notice"}
    if set(value) - allowed or len(json.dumps(value, allow_nan=False).encode()) > MAX_BACKUP:
        raise ValueError("The backup has unknown fields or exceeds 25 MB.")
    for name, maximum in (("casebooks", 200), ("campaigns", 200), ("reports", 200), ("watches", 32)):
        if not isinstance(value.get(name), list) or len(value[name]) > maximum:
            raise ValueError("The backup has an invalid " + name + " collection.")
    settings = validate_preferences(value.get("settings", {}))
    settings.update(api_url=client.BASE_URL, provider="openai-compatible", rkc_executable="")
    if settings["model"] not in {client.AUTO_MODEL, client.NATIVE_MODEL}:
        settings["model"] = client.AUTO_MODEL
    directory = Path(tempfile.mkdtemp(prefix="sinter-import-"))
    try:
        staged = BrowserApplication(directory)
        staged.preferences.update(settings, confirm_endpoint=True)
        for item in value["casebooks"]:
            staged.casebooks.save(item)
        for item in value["campaigns"]:
            staged.campaigns.save(item)
        for item in value["reports"]:
            staged.store.save_report(item)
        for item in value["watches"]:
            if not isinstance(item, dict) or set(item) != {"title", "query", "interval", "deadline"}:
                raise ValueError("Invalid saved search watch.")
            identifier = staged.store.add_watch(**item)
            staged.store.change_watch(identifier, False)
        files = {name: (directory / name).read_bytes() for name in FILES if (directory / name).exists()}
        counts = {name: len(value[name]) for name in ("casebooks", "campaigns", "reports", "watches")}
        return files, counts
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def request(raw):
    """JSON framing. Transport errors never claim a local save succeeded."""
    try:
        value = json.loads(raw)
        path = value["path"]
        body = value.get("data")
        method = value.get("method", "GET" if body is None else "POST")
        if method not in {"GET", "POST"} or not isinstance(path, str) or not path.startswith("/api/"):
            raise ValueError("Unsupported browser operation.")
        if body is not None and not isinstance(body, dict):
            raise ValueError("Operation inputs must be a JSON object.")
        if path in {"/api/transcribe", "/api/atlas/compile", "/api/atlas/retrieve", "/api/documents/docx/save", "/api/desktop/quit"} or path.startswith("/api/account/"):
            raise ValueError("This operation needs the installed app. In this webpage, import a transcript or atlas, and use Download Word copy to save a file.")
        if path == "/api/speech":
            return json.dumps({"status": 200, "result": {"available": False, "message": "Local audio transcription needs the installed speech-enabled app. Import an existing transcript here."}})
        if path == "/api/browser/export":
            return json.dumps({"status": 200, "result": backup()})
        if path in {"/api/browser/import/preview", "/api/browser/import"}:
            files, counts = prepare_import(body.get("document"))
            if path.endswith("/import"):
                if body.get("confirm") is not True:
                    raise ValueError("Confirm replacement after reviewing the backup counts.")
                restore_files(files)
            return json.dumps({"status": 200, "result": counts})
        if path == "/api/settings" and method == "POST":
            fields = body.get("settings", {})
            forbidden = {"api_url", "provider", "rkc_executable", "rkc_port"}
            if not isinstance(fields, dict) or set(fields) & forbidden or body.get("api_key"):
                raise ValueError("Webpage connections use the anonymous NeuroForge API. Install Sinter for custom providers or credentials.")
        capture = Capture(app, casebook_schema=casebooks.SCOPED_SCHEMA)
        parsed = urlsplit(path)
        with client.connection_settings(app.connection()):
            if method == "GET":
                capture._dispatch_get(parsed, parsed.path)
            else:
                capture._dispatch_post(parsed.path, body or {})
        return json.dumps({"status": capture.status, "result": capture.result}, ensure_ascii=False, allow_nan=False)
    except Exception as exc:
        error = _public_error(exc)
        return json.dumps({"status": error.status, "result": {"error": str(error), "partial_result": error.partial_result}})
