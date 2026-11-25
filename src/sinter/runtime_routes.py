"""Shared application dispatch; HTTP and in-process clients use these same routes."""

from __future__ import annotations

import threading
from dataclasses import asdict
from importlib import resources
import shutil
from urllib.parse import parse_qs

from . import (
    __version__,
    assistant,
    atlas,
    campaigns,
    casebooks,
    client,
    community,
    practice,
    speech,
    workbench,
)
from .document_copies import save_word_copy
from .docx_export import export_docx
from .evidence import collect, text
from .grants import screen
from .meetings import parse_transcript
from .operations import Cancelled
from .preferences import PreferencesConflict
from .store import calendar
from .templates import available_templates, resolve_template, template_events

def project_events(message: dict) -> list[dict]:
    """Map one backend progress message to durable project events."""
    kind = message.get("event")
    if kind == "segments":
        return [
            {"event": "segment", "segment": segment}
            for segment in message.get("segments") or ()
            if isinstance(segment, dict)
        ]
    if kind in {"session", "warning", "phase", "unresolved"}:
        return [dict(message)]
    return []


def project_progress(transcriptions, identifier: str, progress):
    """Persist every committed event before forwarding it to the job."""
    def capture(message):
        if isinstance(message, dict):
            received = message.get("received_s")
            processed = message.get("processed_s")
            for event in project_events(message):
                transcriptions.append(
                    identifier, event,
                    received_s=received if isinstance(received, (int, float))
                    else None,
                    processed_s=processed if isinstance(processed, (int, float))
                    else None)
        return progress(message)
    return capture


def combine_resume(prior: list[dict], result: dict,
                   resume_after_s: float) -> dict:
    """Join saved segments with worker segments produced after the boundary."""
    new = [
        segment for segment in result.get("segments") or ()
        if isinstance(segment, dict)
        and float(segment.get("start") or 0) >= resume_after_s - 0.05
    ]
    combined = list(prior) + new
    combined.sort(key=lambda segment: (
        float(segment.get("start") or 0), str(segment.get("id") or "")))
    merged = dict(result)
    merged["segments"] = combined
    merged["speech_duration"] = round(
        sum(float(segment.get("end") or 0)
            - float(segment.get("start") or 0)
            for segment in combined), 4)
    merged["review_count"] = (
        sum(bool(segment.get("review_flags")) for segment in combined)
        + len(merged.get("unresolved_regions") or ()))
    if merged.get("unresolved_regions"):
        merged["status"] = "partial"
    elif combined:
        merged["status"] = "draft"
    else:
        merged["status"] = "no_speech"
    receipt = dict(merged.get("runtime_receipt") or {})
    receipt["resumed"] = True
    receipt["resume_after_s"] = round(float(resume_after_s), 4)
    merged["runtime_receipt"] = receipt
    return merged


MIME = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
}


class RouteDispatch:
    """Domain orchestration only; adapters own framing and transport trust checks."""

    def _resolve_template(self, name):
        return resolve_template(name)

    def _casebook_schema_capability(self):
        return self.headers.get_all("X-Sinter-Casebook-Schema", [])

    def _admit_casebook_reader(self, document):
        if (
            isinstance(document, dict)
            and document.get("schema") == casebooks.SCOPED_SCHEMA
            and self._casebook_schema_capability() != [casebooks.SCOPED_SCHEMA]
        ):
            raise ValueError(
                "This project has saved source choices that this interface "
                "cannot preserve. "
                "Reload Sinter and reopen the project in the current interface. "
                "Keep the original project or backup unchanged; "
                "no choices were cleared."
            )

    def _request_connection(self, path, body=None):
        """Local work never depends on an optional account token supplier.

        Model previews still bind the selected account identity, and jobs retain
        their destination-bound snapshot through the existing context capture.
        Search is a separate tool whose transport never uses model credentials.
        """
        # Refuse an incompatible scoped draft caller before an optional account
        # refresh/connection is resolved, as well as before queueing the job.
        if (
            path == "/api/casebooks/draft"
            and body is not None
            and self._casebook_schema_capability() != [casebooks.SCOPED_SCHEMA]
        ):
            saved = self.app.casebooks.get(body.get("id"))
            self._admit_casebook_reader(saved["document"])
        model = (
            path in {"/api/models", "/api/health"}
            if body is None
            else (
                path
                in {
                    "/api/assistant/preview",
                    "/api/assistant/job",
                    "/api/casebooks/draft",
                    "/api/chat/job",
                    "/api/template/job",
                    "/api/atlas/answer",
                    "/api/chat",
                    "/api/chat/stream",
                    "/api/template/preview",
                    "/api/template/run",
                    "/api/template/stream",
                }
                or (path == "/api/workbench" and body.get("use_model") is True)
            )
        )
        if path == "/api/health" and body is None:
            with self.app.preferences.lock:
                candidate = self.app.preferences.connection()
                self._settings_revision = self.app.preferences.public()["revision"]
            return client.connection_settings(self.app.connection(candidate))
        return client.connection_settings(
            self.app.connection() if model else self.app.preferences.connection()
        )

    def _dispatch_get(self, parsed, path):
        if path in {"/", "/index.html"} or path.startswith("/static/"):
            name = "index.html" if path in {"/", "/index.html"} else path[8:]
            if (
                not name
                or any(character in name for character in ("/", "\\", "%"))
                or name.startswith(".")
            ):
                raise KeyError("Invalid asset")
            suffix = "." + name.rsplit(".", 1)[-1]
            if suffix not in MIME:
                raise KeyError("Unknown asset type")
            asset = resources.files("sinter").joinpath("web").joinpath(name)
            if not asset.is_file():
                raise KeyError("Unknown asset")
            self._send(asset.read_bytes(), MIME[suffix])
        elif path == "/api/session":
            value = {
                "token": self.app.token,
                "version": __version__,
                "workflows": workbench.WORKFLOWS,
                "desktop": self.app.desktop_shutdown is not None,
            }
            if getattr(self.app, "native_browser_owner", False):
                from .native_browser import SESSION_DETAILS, SESSION_NOTICE

                value.update(
                    native_window_owner=True,
                    session_notice=SESSION_NOTICE,
                    session_details=SESSION_DETAILS,
                    native_quit=self.app.native_browser_owner.session_state(),
                )
            self._json(value)
        elif path == "/api/settings":
            self._json(self.app.preferences.public())
        elif path == "/api/account":
            self._json(self.app.accounts.status())
        elif path == "/api/models":
            self._json({"models": client.list_models()})
        elif path == "/api/health":
            ok, message = client.health_check()
            self._json(
                {"ok": ok, "message": message,
                 "settings_revision": self._settings_revision},
                200 if ok else 503,
            )
        elif path == "/api/templates":
            self._json(
                {
                    "templates": [
                        {
                            "id": key,
                            "name": template.name,
                            "description": template.description,
                            "variables": [
                                {
                                    "name": value,
                                    "label": value.replace("_", " ").title(),
                                }
                                for value in template.variables
                            ],
                            "steps": len(template.steps),
                            "output_step": template.output_step,
                            "review_step": template.review_step,
                            "compact_source": template.compact_source,
                        }
                        for key, template in available_templates().items()
                    ]
                }
            )
        elif path == "/api/example":
            query = parse_qs(parsed.query, max_num_fields=8)
            self._json(workbench.example(query.get("workflow", ["brief"])[0]))
        elif path == "/api/practice/garden":
            self._json(practice.garden())
        elif path == "/api/jobs":
            self._json({"jobs": self.app.jobs.list()})
        elif path == "/api/transcriptions":
            self._json({"transcriptions": self.app.transcriptions.list()})
        elif (path.startswith("/api/transcriptions/")
              and path.endswith("/compatibility")):
            identifier = path.removeprefix(
                "/api/transcriptions/").removesuffix(
                "/compatibility").strip("/")
            backends = speech.capabilities().get("backends", [])
            self._json(self.app.transcriptions.compatibility(
                identifier, backends))
        elif (path.startswith("/api/transcriptions/")
              and path.endswith("/audio")):
            identifier = path.removeprefix(
                "/api/transcriptions/").removesuffix("/audio").strip("/")
            source = self.app.transcriptions.source_path(identifier)
            suffix = source.suffix.lower()
            content_type = {
                ".wav": "audio/wav", ".mp3": "audio/mpeg",
                ".m4a": "audio/mp4", ".mp4": "audio/mp4",
                ".ogg": "audio/ogg", ".oga": "audio/ogg",
                ".opus": "audio/ogg", ".webm": "audio/webm",
                ".flac": "audio/flac", ".aac": "audio/aac",
                ".wma": "audio/x-ms-wma",
            }.get(suffix, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(source.stat().st_size))
            self.send_header("Accept-Ranges", "none")
            self._security_headers()
            self.end_headers()
            if self.command != "HEAD":
                with source.open("rb") as audio:
                    shutil.copyfileobj(audio, self.wfile, length=1024 * 1024)
        elif path.startswith("/api/transcriptions/"):
            identifier = path.removeprefix(
                "/api/transcriptions/").strip("/")
            self._json(self.app.transcriptions.get(identifier))
        elif path == "/api/casebooks":
            self._json({"casebooks": self.app.casebooks.list()})
        elif path == "/api/campaigns":
            self._json({"campaigns": self.app.campaigns.list()})
        elif path.startswith("/api/campaigns/"):
            self._json(self.app.campaigns.get(path.removeprefix("/api/campaigns/")))
        elif path.startswith("/api/casebooks/"):
            saved = self.app.casebooks.get(path.removeprefix("/api/casebooks/"))
            self._admit_casebook_reader(saved["document"])
            self._json(saved)
        elif path.startswith("/api/jobs/"):
            query = parse_qs(parsed.query, max_num_fields=4)
            after_text = query.get("after", [None])[0]
            after = None
            if after_text is not None:
                try:
                    after = int(after_text)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "Job cursor must be a non-negative integer.") from exc
            self._json(self.app.jobs.get(
                path.removeprefix("/api/jobs/"), after))
        elif path == "/api/reports":
            self._json({"reports": self.app.store.reports()})
        elif path.startswith("/api/reports/"):
            self._json(self.app.store.report(path.removeprefix("/api/reports/")))
        elif path == "/api/watches":
            self._json({"watches": self.app.store.watches()})
        elif path == "/api/calendar":
            self._send(
                calendar(self.app.store.watches()).encode("utf-8"), "text/calendar"
            )
        elif path == "/api/speech":
            self._json(speech.capabilities())
        else:
            raise KeyError("Unknown route")

    def _dispatch_post(self, path, body):
        if path == "/api/settings":
            try:
                result = self.app.preferences.update(
                    body.get("settings"),
                    confirm_endpoint=body.get("confirm_endpoint") is True,
                    api_key=body.get("api_key"),
                    **({"expected_revision": body["expected_revision"]}
                       if "expected_revision" in body else {}),
                )
            except PreferencesConflict as exc:
                self._json({"error": str(exc)}, 409)
            else:
                self._json(result)
        elif path == "/api/models":
            candidate = self.app.preferences.preview_destination(
                body.get("settings"),
                confirm_endpoint=body.get("confirm_endpoint") is True,
                api_key=body.get("api_key"),
            )
            with client.connection_settings(self.app.connection(candidate)):
                self._json({"models": client.list_models()})
        elif path == "/api/account/connect":
            profile_id = body.get("profile_id")
            if profile_id is not None:
                profile_id = text(profile_id, "ChatGPT account selection", 32, True)
            result = self.app.accounts.start(profile_id)
            self._json({**self.app.accounts.status(), **result})
        elif path == "/api/account/activate":
            self._json(
                self.app.accounts.activate(
                    text(body.get("profile_id"), "ChatGPT account selection", 32, True)
                )
            )
        elif path == "/api/account/cancel":
            self._json(self.app.accounts.cancel())
        elif path == "/api/account/disconnect":
            self._json(self.app.accounts.disconnect())
        elif path == "/api/assistant/preview":
            self._json(assistant.preview(self.app.campaigns, body))
        elif path == "/api/assistant/job":
            if body.get("consent") is not True:
                raise ValueError(
                    "Confirm the displayed campaign context may be sent to your model."
                )
            prepared = assistant.preview(self.app.campaigns, body)
            if prepared["context_hash"] != body.get("context_hash"):
                raise ValueError(
                    "Preview the current assistant context before sending it."
                )
            if not prepared["fit"]["allowed"]:
                raise ValueError(prepared["fit"]["message"])
            identifier = self.app.jobs.submit(
                lambda progress: (
                    progress("Reviewing the selected campaign context"),
                    assistant.run(self.app.campaigns, body),
                )[1],
                label="Campaign assistant",
                timeout=(
                    client.STREAM_DEADLINE + 40
                    if prepared["connection"]["provider"] == "chatgpt"
                    else 180
                ),
            )
            self._json({"job_id": identifier}, 202)
        elif path == "/api/desktop/quit":
            if self.app.desktop_shutdown is None:
                raise ValueError("Stop the source launcher with Ctrl+C.")
            self._json({"ok": True})
            threading.Thread(target=self.app.desktop_shutdown, daemon=True).start()
        elif path == "/api/casebooks/validate":
            document = casebooks.validate(body.get("document"))
            self._admit_casebook_reader(document)
            self._json({"document": document})
        elif path == "/api/campaigns/prepare":
            self._json(
                campaigns.prepare(
                    body.get("document"), body.get("focused_opportunity", "")
                )
            )
        elif path == "/api/campaigns/focus":
            self._json(campaigns.focused_document(
                body.get("document"), body.get("opportunity"), body.get("title"),
                body.get("options"), body.get("parent"),
            ))
        elif path == "/api/campaigns/funding-summary":
            self._json(campaigns.funding_summary(body.get("document")))
        elif path == "/api/campaigns/save":
            self._json(
                self.app.campaigns.save(
                    body.get("document"), body.get("id"), body.get("revision")
                )
            )
        elif path == "/api/campaigns/delete":
            self.app.campaigns.delete(body.get("id"), body.get("revision"))
            self._json({"ok": True})
        elif path == "/api/casebooks/save":
            self._admit_casebook_reader(body.get("document"))
            if body.get("id") is not None:
                current = self.app.casebooks.get(body["id"])
                self._admit_casebook_reader(current["document"])
            self._json(
                self.app.casebooks.save(
                    body.get("document"), body.get("id"), body.get("revision")
                )
            )
        elif path == "/api/casebooks/delete":
            self.app.casebooks.delete(body.get("id"), body.get("revision"))
            self._json({"ok": True})
        elif path in {"/api/casebooks/build", "/api/casebooks/draft"}:
            saved = self.app.casebooks.get(body.get("id"))
            self._admit_casebook_reader(saved["document"])
            if saved["revision"] != body.get("revision"):
                raise ValueError(
                    "The project changed. Reopen or save it before preparing a report."
                )
            effective_type = body.get(
                "document_type", saved["document"].get("document_type", "brief")
            )
            effective_book = casebooks.validate(
                {**saved["document"], "document_type": effective_type}
            )
            if path.endswith("/draft") and (
                body.get("consent") is not True
                or body.get("fingerprint") != effective_book["fingerprint"]
            ):
                raise ValueError(
                    (
                        "Preview the current source-only report and approve "
                        "transfer before asking for a draft."
                    )
                )

            def operation(progress):
                report = casebooks.build(
                    saved["document"], body.get("document_type"), progress
                )
                return (
                    casebooks.draft(report, True, progress)
                    if path.endswith("/draft")
                    else report
                )

            self._json(
                {
                    "id": self.app.jobs.submit(
                        operation,
                        label="Casebook: " + saved["document"]["title"][:180],
                        timeout=300,
                    )
                },
                202,
            )
        elif path in {"/api/chat/job", "/api/template/job"}:
            if path == "/api/chat/job":
                rows = body.get("messages")
                if not isinstance(rows, list) or any(
                    not isinstance(row, dict) for row in rows
                ):
                    raise ValueError("Provide a list of messages.")
                messages = [
                    client.Message(row.get("role"), row.get("content")) for row in rows
                ]
                maximum = body.get("max_tokens", 512)
                client._chat_body(messages, maximum)

                def operation(progress):
                    progress("Waiting for the configured model; no automatic replay")
                    return asdict(client.chat(messages, maximum))
            else:
                template = self._resolve_template(body.get("template", "custom"))
                values = body.get("variables", {})
                if not isinstance(values, dict):
                    raise ValueError("Template variables must be an object.")
                if template.compact_source:
                    from .template_scope import preview

                    if body.get("consent") is not True or preview(template, values)[
                        "context_hash"
                    ] != body.get("context_hash"):
                        raise ValueError(
                            (
                                "Preview the current source request and approve"
                                " transfer before sending it."
                            )
                        )

                def operation(progress):
                    from .template_runs import collect_run

                    return collect_run(template, values, progress)

            self._json(
                {
                    "id": self.app.jobs.submit(
                        operation, label="Model task", timeout=900
                    )
                },
                202,
            )
        elif path == "/api/atlas/inspect":
            self._json(atlas.inspect(body.get("document")))
        elif path == "/api/atlas/context":
            self._json(atlas.context(body.get("document"), body.get("question")))
        elif path == "/api/atlas/retrieve":
            self._json(
                {
                    "document": atlas.retrieve(
                        self.app.preferences.snapshot()["rkc_port"],
                        body.get("question"),
                    )
                }
            )
        elif path == "/api/atlas/answer":
            atlas.require_answer_consent(body.get("consent"))
            self._json(
                {
                    "id": self.app.jobs.submit(
                        lambda progress: atlas.answer(
                            body.get("document"),
                            body.get("question"),
                            body.get("consent"),
                            progress,
                        )
                    )
                },
                202,
            )
        elif path == "/api/atlas/compile":
            executable = self.app.preferences.snapshot()["rkc_executable"]
            self._json(
                {
                    "id": self.app.jobs.submit(
                        lambda progress: atlas.compile_collection(
                            body.get("files"), executable, body.get("consent"), progress
                        )
                    )
                },
                202,
            )
        elif path == "/api/community/compare":
            self._json(community.compare(body.get("before", ""), body.get("after", "")))
        elif path == "/api/community/plan":
            self._json(community.plan(body.get("title", ""), body.get("actions")))
        elif path == "/api/transcript/export":
            from .transcript_export import export_transcript

            self._json(
                {
                    "content": export_transcript(
                        body.get("transcript", {}), body.get("format", "json")
                    )
                }
            )
        elif path in {"/api/chat", "/api/chat/stream"}:
            rows = body.get("messages")
            if not isinstance(rows, list) or any(
                not isinstance(row, dict) for row in rows
            ):
                raise ValueError("Provide a list of messages.")
            messages = [
                client.Message(row.get("role"), row.get("content")) for row in rows
            ]
            maximum = body.get("max_tokens", 512)
            client._chat_body(messages, maximum)
            if path.endswith("/stream"):
                self._stream(
                    (
                        {"type": "token", "t": token}
                        for token in client.chat_stream(messages, maximum)
                    )
                )
            else:
                result = client.chat(messages, maximum)
                self._json(
                    {
                        "content": result.content,
                        "tokens": result.total_tokens,
                        "finish_reason": result.finish_reason,
                    }
                )
        elif path == "/api/search":
            self._json(asdict(client.search(body.get("query", ""))))
        elif path == "/api/template/preview":
            from .template_scope import preview

            self._json(
                preview(
                    self._resolve_template(body.get("template", "")),
                    body.get("variables", {}),
                )
            )
        elif path in {"/api/template/run", "/api/template/stream"}:
            template = self._resolve_template(body.get("template", "custom"))
            variables = body.get("variables", {})
            if not isinstance(variables, dict):
                raise ValueError("Template variables must be an object.")
            if template.compact_source:
                from .template_scope import preview

                if body.get("consent") is not True or preview(template, variables)[
                    "context_hash"
                ] != body.get("context_hash"):
                    raise ValueError(
                        (
                            "Preview the current source request and approve "
                            "transfer before sending it."
                        )
                    )
            events = template_events(
                template, variables, stream=path.endswith("/stream")
            )
            if path.endswith("/stream"):
                self._stream(events)
            else:
                from .template_runs import collect_run

                self._json(collect_run(template, variables))
        elif path == "/api/workbench":
            self._json(
                {
                    "id": self.app.jobs.submit(
                        lambda progress: workbench.run(body, progress),
                        label="Community report",
                    )
                },
                202,
            )
        elif path == "/api/jobs/cancel":
            self.app.jobs.cancel(text(body.get("id", ""), "Job ID", 100, True))
            self._json({"ok": True})
        elif path == "/api/reports":
            self._json({"id": self.app.store.save_report(body.get("report"))}, 201)
        elif path == "/api/documents/docx":
            document = export_docx(body)
            self._send(
                document.content, document.content_type, filename=document.filename
            )
        elif path == "/api/documents/docx/save":
            self._json(save_word_copy(self.app.store.directory, body))
        elif path == "/api/reports/delete":
            self.app.store.delete_report(body.get("id", ""))
            self._json({"ok": True})
        elif path == "/api/watches":
            if body.get("consent") is not True:
                raise ValueError(
                    "Confirm that this query may be sent on the selected schedule."
                )
            identifier = self.app.store.add_watch(
                body.get("title", ""),
                body.get("query", ""),
                body.get("interval", 86400),
                body.get("deadline", ""),
            )
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
            self._json(
                screen(
                    body.get("profile", {}),
                    body.get("criteria", []),
                    collect(body.get("sources", [])),
                )
            )
        elif path == "/api/transcript/inspect":
            segments = parse_transcript(body.get("text", ""))
            self._json(
                {
                    "speakers": sorted({segment.speaker for segment in segments}),
                    "segments": len(segments),
                }
            )
        elif path == "/api/recordings":
            self._json(
                self.app.recordings.create(
                    body.get("filename"), body.get("expected_size")), 201)
        elif path == "/api/recordings/chunk":
            self._json(self.app.recordings.append(
                text(body.get("recording_id"), "recording", 100, True),
                body.get("offset"), body.get("data")))
        elif path == "/api/recordings/finish":
            self._json(self.app.recordings.finish(
                text(body.get("recording_id"), "recording", 100, True)))
        elif path == "/api/recordings/cancel":
            self._json(self.app.recordings.cancel(
                text(body.get("recording_id"), "recording", 100, True)))
        elif path == "/api/transcriptions/delete":
            identifier = text(body.get("id"), "saved transcription", 100, True)
            saved = self.app.transcriptions.get(identifier)
            if saved.get("status") == "running":
                self._json({
                    "error": "Cancel or finish the transcription before "
                             "deleting its saved source.",
                }, 409)
                return
            self.app.transcriptions.delete(identifier)
            self._json({"id": identifier, "deleted": True})
        elif path.startswith("/api/transcriptions/") and path.endswith("/resume"):
            identifier = path.removeprefix(
                "/api/transcriptions/").removesuffix("/resume").strip("/")
            if body.get("consent") is not True:
                raise ValueError(
                    "Confirm permission to continue this saved recording.")
            saved = self.app.transcriptions.get(identifier)
            backends = speech.capabilities().get("backends", [])
            compatibility = self.app.transcriptions.compatibility(
                identifier, backends)
            if not compatibility["compatible"]:
                self._json({
                    "error": "This saved transcription cannot resume.",
                    "issues": compatibility["issues"],
                }, 409)
                return
            if not compatibility["resumable"]:
                self._json({
                    "error": "This saved transcription is already complete, "
                             "currently running, or not resumable with the "
                             "installed native backend.",
                }, 409)
                return
            self.app.transcriptions.begin_resume(identifier)
            source = self.app.transcriptions.source_path(identifier)
            prior = list(saved.get("segments") or ())
            resume_after = float(compatibility["resume_after_s"])

            def operation(progress):
                tracker = project_progress(
                    self.app.transcriptions, identifier, progress)
                try:
                    result = speech.transcribe(
                        source,
                        model=saved["request"]["model"],
                        consent=True,
                        allow_download=False,
                        progress=tracker,
                        language=saved["request"]["language"],
                        split_channels=saved["request"]["split_channels"],
                        backend=saved["request"]["backend"],
                        resume_after_s=resume_after,
                    )
                except Cancelled:
                    self.app.transcriptions.finish(
                        identifier, status="cancelled")
                    raise
                except Exception as error:
                    self.app.transcriptions.finish(
                        identifier, status="failed", error=str(error))
                    raise
                merged = combine_resume(prior, result, resume_after)
                self.app.transcriptions.finish(
                    identifier, result=merged, status="done")
                return merged

            try:
                job = self.app.jobs.submit(
                    operation,
                    label=f"Resume {saved.get('title', 'recording')}"[:200])
            except Exception as error:
                self.app.transcriptions.finish(
                    identifier, status="failed", error=str(error))
                raise
            self._json({"id": job, "project": identifier}, 202)
        elif path == "/api/transcribe":
            identifier = body.get("recording_id")
            if identifier is not None:
                identifier = text(identifier, "recording", 100, True)
                source = self.app.recordings.path(identifier)
                saved = None
                project_source = source
                if body.get("save") is True:
                    if body.get("consent") is not True:
                        raise ValueError(
                            "Confirm permission before saving a recording.")
                    backends = speech.capabilities().get("backends", [])
                    backend_id = str(body.get("backend") or "faster-whisper")
                    entry = next(
                        (item for item in backends
                         if item.get("id") == backend_id), {})
                    saved = self.app.transcriptions.create(
                        source,
                        filename=body.get("filename") or source.name,
                        backend=backend_id,
                        model=str(body.get("model", "base")),
                        language=str(body.get("language", "auto")),
                        split_channels=body.get("split_channels") is True,
                        runtime_identity=str(
                            entry.get("runtime_identity") or ""),
                        manifest_identity=str(
                            entry.get("manifest_identity") or ""),
                    )
                    project_source = self.app.transcriptions.source_path(
                        saved["id"])

                def operation(progress):
                    tracker = (
                        project_progress(
                            self.app.transcriptions, saved["id"], progress)
                        if saved is not None else progress)
                    try:
                        result = speech.transcribe(
                            project_source,
                            model=body.get("model", "base"),
                            consent=body.get("consent") is True,
                            allow_download=body.get("allow_download", False),
                            progress=tracker,
                            language=body.get("language", "auto"),
                            split_channels=body.get("split_channels", False),
                            backend=body.get("backend"),
                        )
                    except Cancelled:
                        if saved is not None:
                            self.app.transcriptions.finish(
                                saved["id"], status="cancelled")
                        raise
                    except Exception as error:
                        if saved is not None:
                            self.app.transcriptions.finish(
                                saved["id"], status="failed",
                                error=str(error))
                        raise
                    else:
                        if saved is not None:
                            self.app.transcriptions.finish(
                                saved["id"], result=result, status="done")
                        return result
                    finally:
                        self.app.recordings.release(identifier)

                self._json(
                    {"id": self.app.jobs.submit(operation),
                     **({"project": saved["id"]} if saved else {})}, 202)
            else:
                self._json(
                    {
                        "id": self.app.jobs.submit(
                            lambda progress: speech.transcribe_upload(body, progress)
                        )
                    },
                    202,
                )
        else:
            raise KeyError("Unknown route")

    def _check_watches(self, progress):
        progress("Checking due search watches")
        return {"checked": self.app.store.run_due()}
