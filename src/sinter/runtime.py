"""One local application runtime for native, HTTP, command-line and Python use."""

from __future__ import annotations

import base64
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

from . import __version__, accounts, campaigns, casebooks, client
from .jobs import Jobs
from .outputs import validate_output
from .preferences import Preferences
from .runtime_routes import RouteDispatch
from .store import Store, data_directory


def workspace_directory(directory=None):
    """One path interpretation for UI, CLI, Python and export admission."""
    selected = data_directory() if directory is None else Path(directory)
    return selected.expanduser().resolve()


def output_sources(directory, destination, sources=()):
    """Protect supplied sources and reserved local runtime state from exports.

    Only paths are inspected. Account/template contents and credential values
    are never opened. This helper also works before a Runtime is created.
    """
    root = workspace_directory(directory)
    target = Path(destination).expanduser().resolve()
    folders = (
        root / "accounts",
        root / "templates",
        Path.home() / ".sinter" / "templates",
    )
    for folder in folders:
        # Existing user templates use HOME even with a custom workspace.
        # Resolve both folder and target to reject parent-directory aliases.
        if target.is_relative_to(folder.resolve()):
            raise ValueError(
                "Choose an export outside runtime account/template storage."
            )
    reserved = [root / "preferences.json"]
    for database in ("workspace.sqlite3", "campaigns.sqlite3"):
        reserved.extend(
            root / (database + suffix) for suffix in ("", "-wal", "-shm", "-journal")
        )
    protected = (*sources, *reserved)
    validate_output(destination, sources=protected)
    return protected


class Application:
    def __init__(self, directory=None):
        self.store = Store(workspace_directory(directory))
        self.preferences = Preferences(self.store.directory)
        self.accounts = accounts.AccountManager(self.store.directory)
        self.casebooks = casebooks.Casebooks(self.store)
        self.campaigns = campaigns.CampaignStore(self.store.directory)
        self.desktop_shutdown = None
        self.jobs = Jobs()
        self.token = secrets.token_urlsafe(32)
        self.stop = threading.Event()

    def scheduler(self):
        while not self.stop.wait(5):
            try:
                with client.connection_settings(self.preferences.connection()):
                    self.store.run_due()
            except Exception:
                log.exception("Watch scheduler could not complete a check")

    def close(self):
        self.stop.set()
        self.jobs.close()
        self.accounts.close()

    def connection(self, candidate=None):
        """Bind account access only to its selected, official destination."""
        settings = (
            self.preferences.connection() if candidate is None else dict(candidate)
        )
        if settings.get("provider") == "chatgpt":
            if not client.same_api_destination(
                settings["api_url"], "https://api.openai.com/v1"
            ):
                raise ValueError("ChatGPT account access requires the official API.")
            settings.update(self.accounts.connection())
        return settings


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Operation:
    id: str
    method: str
    route: str
    summary: str
    inputs: str = "JSON object; omitted fields retain the existing API defaults."
    effect: str = "local"

    def public(self):
        return {
            "id": self.id,
            "method": self.method,
            "route": self.route,
            "summary": self.summary,
            "input": self.inputs,
            "effect": self.effect,
        }


# This deliberately excludes account setup, credentials, settings mutations,
# browser sessions and desktop lifecycle. Those remain in the trusted UI.
_OPERATIONS = (
    Operation(
        "runtime.status",
        "GET",
        "",
        "Inspect local runtime and saved work without contacting a provider.",
    ),
    Operation(
        "templates.list",
        "GET",
        "/api/templates",
        "List templates and required variables.",
    ),
    Operation(
        "template.preview",
        "POST",
        "/api/template/preview",
        "Preview the exact short source request and destination.",
        "template, variables: source_title, excerpt, question; optional system.",
    ),
    Operation(
        "template.run",
        "POST",
        "/api/template/run",
        (
            "Run an existing template; compact source requests require the "
            "matching preview."
        ),
        (
            "template, variables; compact sources also require consent: true "
            "and context_hash."
        ),
        "provider",
    ),
    Operation(
        "template.job",
        "POST",
        "/api/template/job",
        "Run the same template as a cancellable job.",
        (
            "template, variables; compact sources also require consent: true "
            "and context_hash."
        ),
        "provider",
    ),
    Operation(
        "workbench.example",
        "GET",
        "/api/example",
        "Load a wholly fictional offline workflow.",
        "workflow: brief, grants, meeting or research.",
    ),
    Operation(
        "workbench.run",
        "POST",
        "/api/workbench",
        "Prepare the existing source-linked community report.",
        (
            "workflow, title, notes, sources, questions; use_search/use_model "
            "are explicit optional flags."
        ),
        "conditional_provider",
    ),
    Operation(
        "practice.garden",
        "GET",
        "/api/practice/garden",
        "Load the fictional offline practice workspace.",
    ),
    Operation("casebooks.list", "GET", "/api/casebooks", "List saved source projects."),
    Operation(
        "casebooks.get",
        "GET",
        "/api/casebooks/{id}",
        "Read a saved source project and its revision.",
        "id.",
    ),
    Operation(
        "casebooks.validate",
        "POST",
        "/api/casebooks/validate",
        "Inspect source material and its fingerprint.",
        "document.",
    ),
    Operation(
        "casebooks.save",
        "POST",
        "/api/casebooks/save",
        "Import or update a source project atomically.",
        "document; updates require id and current revision.",
        "write",
    ),
    Operation(
        "casebooks.delete",
        "POST",
        "/api/casebooks/delete",
        "Remove a source project at its current revision.",
        "id, revision.",
        "write",
    ),
    Operation(
        "casebooks.build",
        "POST",
        "/api/casebooks/build",
        "Build a source-only report from a saved revision.",
        "id, revision; optional document_type.",
    ),
    Operation(
        "casebooks.draft",
        "POST",
        "/api/casebooks/draft",
        "Draft from the current fingerprint with explicit consent.",
        "id, revision, fingerprint, consent: true; optional document_type.",
        "provider",
    ),
    Operation("campaigns.list", "GET", "/api/campaigns", "List saved campaigns."),
    Operation(
        "campaigns.get",
        "GET",
        "/api/campaigns/{id}",
        "Read a saved campaign and revision.",
        "id.",
    ),
    Operation(
        "campaigns.prepare",
        "POST",
        "/api/campaigns/prepare",
        "Inspect the existing campaign source and decisions.",
        "document; optional focused_opportunity.",
    ),
    Operation(
        "campaigns.save",
        "POST",
        "/api/campaigns/save",
        "Save a campaign using its revision guard.",
        "document; updates require id and revision.",
        "write",
    ),
    Operation(
        "campaigns.delete",
        "POST",
        "/api/campaigns/delete",
        "Remove a campaign at its current revision.",
        "id, revision.",
        "write",
    ),
    Operation(
        "assistant.preview",
        "POST",
        "/api/assistant/preview",
        "Preview the selected campaign context and fit.",
        "id, revision, opportunity, checks, actions, task, question.",
    ),
    Operation(
        "assistant.job",
        "POST",
        "/api/assistant/job",
        "Ask about exactly the current approved campaign context.",
        "Preview payload plus consent: true, context_hash.",
        "provider",
    ),
    Operation(
        "atlas.inspect",
        "POST",
        "/api/atlas/inspect",
        "Validate an imported RKC atlas or context packet.",
        "document.",
    ),
    Operation(
        "atlas.context",
        "POST",
        "/api/atlas/context",
        "Search imported material without model inference.",
        "document, question.",
    ),
    Operation(
        "atlas.retrieve",
        "POST",
        "/api/atlas/retrieve",
        "Read a current context packet from the configured loopback RKC.",
        "question.",
        "loopback",
    ),
    Operation(
        "atlas.answer",
        "POST",
        "/api/atlas/answer",
        "Use the existing Atlas draft operation and its evidence gate.",
        (
            "document, question, consent: true. Review atlas.context first; "
            "this existing operation needs a capable full-context provider."
        ),
        "provider",
    ),
    Operation(
        "atlas.compile",
        "POST",
        "/api/atlas/compile",
        "Compile explicitly selected files with the configured installed RKC.",
        "files: [{name, content}], consent: true.",
        "local_process",
    ),
    Operation("reports.list", "GET", "/api/reports", "List saved reports."),
    Operation(
        "reports.get",
        "GET",
        "/api/reports/{id}",
        "Read or export a saved report with source metadata.",
        "id.",
    ),
    Operation(
        "reports.save",
        "POST",
        "/api/reports",
        "Import a completed report into the existing workspace.",
        "report: object containing title and markdown.",
        "write",
    ),
    Operation(
        "reports.delete",
        "POST",
        "/api/reports/delete",
        "Remove a saved report.",
        "id.",
        "write",
    ),
    Operation(
        "documents.docx",
        "POST",
        "/api/documents/docx",
        "Export the existing document as base64-encoded DOCX for non-HTTP clients.",
        "Existing document-export payload.",
    ),
    Operation(
        "community.compare",
        "POST",
        "/api/community/compare",
        "Compare source text exactly.",
        "before, after.",
    ),
    Operation(
        "community.plan",
        "POST",
        "/api/community/plan",
        "Prepare the existing source-aware action plan and exports.",
        "title, actions.",
    ),
    Operation(
        "transcript.inspect",
        "POST",
        "/api/transcript/inspect",
        "Inspect transcript segments locally.",
        "text.",
    ),
    Operation(
        "transcript.export",
        "POST",
        "/api/transcript/export",
        "Export an existing transcript in JSON/TXT/SRT/VTT.",
        "transcript, format.",
    ),
    Operation(
        "speech.capabilities",
        "GET",
        "/api/speech",
        "Inspect optional local transcription dependencies.",
    ),
    Operation(
        "speech.transcribe",
        "POST",
        "/api/transcribe",
        "Run the existing local upload transcription operation.",
        "Existing transcription upload payload and explicit consent/download flags.",
        "conditional_download",
    ),
    Operation(
        "grants.screen",
        "POST",
        "/api/screen",
        "Screen entered criteria against supplied sources.",
        "profile, criteria, sources.",
    ),
    Operation(
        "jobs.list",
        "GET",
        "/api/jobs",
        "Inspect current temporary jobs; jobs do not survive runtime closure.",
    ),
    Operation(
        "jobs.get", "GET", "/api/jobs/{id}", "Inspect a current temporary job.", "id."
    ),
    Operation(
        "jobs.cancel",
        "POST",
        "/api/jobs/cancel",
        "Cancel an existing bounded job without replay.",
        "id.",
    ),
    Operation(
        "watches.list",
        "GET",
        "/api/watches",
        "Inspect saved search watches without running them.",
    ),
    Operation(
        "watches.add",
        "POST",
        "/api/watches",
        "Add an explicitly approved scheduled query.",
        "title, query, interval, deadline; consent: true.",
        "write",
    ),
    Operation(
        "watches.update",
        "POST",
        "/api/watches/update",
        "Change an existing watch enabled state.",
        "id, enabled.",
        "write",
    ),
    Operation(
        "watches.delete",
        "POST",
        "/api/watches/delete",
        "Remove an existing watch.",
        "id.",
        "write",
    ),
    Operation(
        "watches.check",
        "POST",
        "/api/watches/check",
        "Run due queries once using the existing leases.",
        "Empty object.",
        "search_provider",
    ),
    Operation(
        "calendar.export", "GET", "/api/calendar", "Export the existing watch calendar."
    ),
    Operation(
        "models.list",
        "GET",
        "/api/models",
        "Explicitly discover the configured provider models.",
        "Empty object.",
        "provider_metadata",
    ),
    Operation(
        "health.check",
        "GET",
        "/api/health",
        "Explicitly check provider discovery; this does not test generation.",
        "Empty object.",
        "provider_metadata",
    ),
    Operation(
        "search.run",
        "POST",
        "/api/search",
        "Send the exact entered query to the existing search tool.",
        "query.",
        "search_provider",
    ),
    Operation(
        "chat.job",
        "POST",
        "/api/chat/job",
        "Run existing unverified chat as a cancellable task.",
        (
            "messages: [{role, content}], max_tokens. This operation has no "
            "source verification."
        ),
        "provider",
    ),
)
OPERATION_SCHEMA = "sinter-operations/v1"
RESULT_SCHEMA = "sinter-operation-result/v1"
_INDEX = {operation.id: operation for operation in _OPERATIONS}
_INDEX.update(
    {
        "templates." + name: _INDEX["template." + name]
        for name in ("preview", "run", "job")
    }
)


def describe_operation(operation=None):
    """Read one static operation contract without creating a workspace."""
    if operation is None:
        return catalog()
    try:
        return _INDEX[operation].public()
    except (KeyError, TypeError):
        raise OperationError(
            "Unknown operation. Use sinter operations to discover "
            "supported operations.",
            code="unknown_operation",
            status=404,
        ) from None


def catalog():
    """Static discovery needs no workspace, secrets, sockets or imports of a GUI."""
    return {
        "schema": OPERATION_SCHEMA,
        "version": __version__,
        "operations": [operation.public() for operation in _OPERATIONS],
        "excluded": [
            "account setup",
            "credentials",
            "settings mutations",
            "HTTP session/security controls",
            "desktop lifecycle",
        ],
        "jobs": (
            "Temporary within one Runtime; CLI waits and never starts a daemon."
            " Save/export useful results explicitly."
        ),
    }


class OperationError(Exception):
    """Stable public failure independent of HTTP transport framing."""

    def __init__(
        self, message, *, code="operation_failed", status=400, partial_result=None
    ):
        super().__init__(message)
        self.code = code
        self.status = status
        self.partial_result = partial_result

    def public(self):
        value = {"code": self.code, "message": str(self), "status": self.status}
        if self.partial_result is not None:
            value["partial_result"] = self.partial_result
        return value


def _public_error(exc):
    if isinstance(exc, OperationError):
        return exc
    if isinstance(exc, client.APIError):
        return OperationError(
            str(exc),
            code=getattr(exc, "error_code", "") or "provider_error",
            status=exc.status,
            partial_result=getattr(exc, "partial_result", None),
        )
    if isinstance(exc, KeyError):
        return OperationError(
            "That item was not found or has expired.", code="not_found", status=404
        )
    if isinstance(exc, PermissionError):
        return OperationError(str(exc), code="permission_denied", status=403)
    if isinstance(exc, (ValueError, TypeError, UnicodeError)):
        return OperationError(str(exc), code="invalid_input", status=400)
    if isinstance(exc, OSError):
        return OperationError(
            (
                "Local storage could not complete this operation. Check its "
                "path and permissions."
            ),
            code="storage_error",
            status=500,
        )
    log.exception("An in-process operation failed")
    return OperationError(
        "Sinter could not complete this operation. Your original inputs are unchanged.",
        code="internal_error",
        status=500,
    )


class _Capture(RouteDispatch):
    def __init__(self, app):
        self.app = app
        self.result = None
        self.status = 200

    def _json(self, value, status=200):
        self.result, self.status = value, status

    def _send(self, body, content_type, status=200, *, filename=None):
        # Binary bytes remain exact and have an explicit machine encoding.
        if content_type.startswith("text/"):
            self.result = {
                "content": body.decode("utf-8"),
                "content_type": content_type,
            }
        else:
            self.result = {
                "content_base64": base64.b64encode(body).decode("ascii"),
                "content_type": content_type,
                "encoding": "base64",
            }
        if filename:
            self.result["filename"] = filename
        self.status = status

    def _stream(self, events):
        raise OperationError(
            "Use the collected or job operation for in-process output.",
            code="unsupported_operation",
        )


class Runtime:
    """The existing application state, directly callable without HTTP or a GUI.

    Creation does not run the watch scheduler or contact any provider. Calls
    reuse the same route dispatcher and destination-bound connection context as
    the UI. A context manager owns and closes only its own temporary jobs.
    """

    def __init__(self, directory=None, *, application=None):
        self.app = application if application is not None else Application(directory)
        self._owns_application = application is None
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if not self._closed:
            self._closed = True
            if self._owns_application:
                self.app.close()

    def output_sources(self, destination, *, sources=()):
        return output_sources(self.app.store.directory, destination, sources)

    def catalog(self):
        return catalog()

    def describe(self, operation=None):
        return describe_operation(operation)

    def status(self):
        settings = self.app.preferences.connection()
        warning = ""
        try:
            with client.connection_settings(settings):
                connection = client.connection_identity()
        except (client.APIError, ValueError) as exc:
            warning = str(exc)
            connection = {
                key: settings[key] for key in ("provider", "model", "max_tokens")
            }
            connection["api_url"] = "Invalid configured destination"
        return {
            "schema": "sinter-runtime-status/v1",
            "version": __version__,
            "workspace": str(self.app.store.directory),
            "connection": {
                key: connection[key]
                for key in ("api_url", "provider", "model", "max_tokens")
            },
            "provider_tested": False,
            "watch_scheduler_started_by_runtime": False,
            "counts": {
                "casebooks": len(self.app.casebooks.list()),
                "campaigns": len(self.app.campaigns.list()),
                "reports": len(self.app.store.reports()),
                "watches": len(self.app.store.watches()),
            },
            "preferences_warning": self.app.preferences.warning,
            "connection_warning": warning,
            "model_selection_help": (
                "For exact source previews, choose an explicit model through "
                "browser Settings or launch with NEUROFORGE_MODEL set to your "
                "provider's verified model ID. "
                "This status check never discovers or tests models."
                if connection["model"] == client.AUTO_MODEL
                else ""
            ),
        }

    def call(self, operation_id, payload=None, *, wait=True, progress=None):
        """Return existing domain JSON; wait for this runtime's jobs by default."""
        if self._closed:
            raise OperationError(
                "This runtime is closed. Open a new Runtime before starting work.",
                code="runtime_closed",
            )
        operation = self.describe(operation_id)
        body = {} if payload is None else payload
        if not isinstance(body, dict):
            raise OperationError(
                "The input must be a JSON object.", code="invalid_input"
            )
        try:
            raw = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            # Python callers cannot mutate approved inputs after a job is queued.
            body = json.loads(raw)
            route = operation["route"]
            limit = (
                (
                    36
                    if route == "/api/transcribe"
                    else 10
                    if route.startswith("/api/casebooks/")
                    else 5
                    if route.startswith("/api/atlas/")
                    else 2
                )
                * 1024
                * 1024
            )
            if len(raw) > limit:
                raise ValueError(
                    "The request is too large. Split it into smaller inputs."
                )
            if operation_id == "runtime.status":
                return self.status()
            if "{id}" in route:
                identifier = body.get("id")
                if (
                    not isinstance(identifier, str)
                    or not identifier
                    or len(identifier) > 100
                ):
                    raise ValueError("Provide the item id.")
                route = route.replace("{id}", quote(identifier, safe=""))
            if operation_id == "workbench.example":
                route += "?" + urlencode({"workflow": body.get("workflow", "brief")})
            parsed = urlsplit(route)
            capture = _Capture(self.app)
            with capture._request_connection(
                parsed.path, body if operation["method"] == "POST" else None
            ):
                if operation["method"] == "GET":
                    capture._dispatch_get(parsed, parsed.path)
                else:
                    capture._dispatch_post(parsed.path, body)
            if capture.status >= 400:
                raise OperationError(
                    capture.result.get("error")
                    or capture.result.get("message")
                    or "The operation was unavailable.",
                    code="operation_unavailable",
                    status=capture.status,
                    partial_result=capture.result,
                )
            if capture.status == 202 and wait:
                identifier = capture.result.get("id") or capture.result.get("job_id")
                return self.wait(identifier, progress=progress)
            return capture.result
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise _public_error(exc) from None

    def wait(self, identifier, *, progress=None):
        """Wait once; cancellation and provider failures never replay a request."""
        last = None
        try:
            while True:
                if self._closed:
                    raise OperationError(
                        "This runtime is closed. Open a new Runtime before "
                        "starting work.",
                        code="runtime_closed",
                    )
                job = self.app.jobs.get(identifier)
                state = (job["status"], job["message"], job["error"])
                if progress is not None and state != last:
                    progress(job["message"] or job["status"])
                last = state
                if job["status"] == "done":
                    return job["result"]
                if job["status"] == "failed":
                    raise OperationError(
                        job["error"],
                        code="job_failed",
                        status=502,
                        partial_result=job["result"],
                    )
                if job["status"] == "cancelled":
                    raise OperationError(
                        (
                            "Cancelled; no request was replayed. Inspect saved "
                            "results before retrying."
                        ),
                        code="cancelled",
                        status=409,
                        partial_result=job["result"],
                    )
                time.sleep(0.02)
        except KeyboardInterrupt:
            self.app.jobs.cancel(identifier)
            raise
        except Exception as exc:
            raise _public_error(exc) from None
