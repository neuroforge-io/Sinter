"""A scoped portable desktop workspace over the application's shared operations.

Tk displays untrusted source text as text. It does not host web pages, open a
socket until requested, run a watch scheduler or invent another model/source
implementation. The full web workbench is an explicit, owned browser view.
"""

from __future__ import annotations

import copy
import json
import os
import re
import signal
import socket
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import client
from .casebooks import FORMATS
from .document_markup import inline
from .evidence import literal
from .outputs import atomic_write_text
from .presentation import result_markdown

TEXT_BYTES = 800_000
PROJECT_BYTES = 10_000_000


def report_date(value):
    """Show recorded UTC dates without inventing missing metadata."""
    try:
        if isinstance(value, bool):
            raise ValueError()
        if isinstance(value, (int, float)):
            stamp = datetime.fromtimestamp(value, timezone.utc)
        elif isinstance(value, str):
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.tzinfo is not None:
                stamp = stamp.astimezone(timezone.utc)
        else:
            raise ValueError()
        return stamp.date().isoformat()
    except (ValueError, OverflowError, OSError):
        return "date not recorded"


def report_catalogue_title(row):
    """Date labels are presentation only; the catalogue keeps the original ID."""
    return f"Saved {report_date(row.get('created_at'))} · {row['title']}"


def report_scope_notice(report, *, current=False):
    """Distinguish campaign snapshots from selected source results and AI drafts."""
    dated = report_date(report.get("created_at"))
    if report.get("workflow") == "campaign":
        if report.get("review_status") == "needs_refresh":
            return (
                f"Campaign report · {dated}. This snapshot needs refresh; "
                "its source content is unavailable in this view."
            )
        evidence = (
            "Source-backed, user-entered campaign records"
            if campaign_source_records(report.get("campaign"))
            else "User-entered campaign records; no source register recorded"
        )
        summary = report.get("funding_summary")
        as_of = summary.get("as_of") if isinstance(summary, dict) else None
        checks = (
            f" Derived funding checks as of {report_date(as_of)}."
            if as_of else " Displayed checks may be refreshed from this snapshot."
        )
        return (
            f"Campaign report · saved snapshot dated {dated}. {evidence}; "
            "not independently verified." + checks
            + " This is not the live campaign editor."
        )
    model = bool(report.get("results") or report.get("model_draft")) or (
        report.get("workflow") == "assistant"
    )
    if model:
        return (
            ("Current model output. " if current else f"Saved model output · {dated}. ")
            + "Check the displayed source snapshot and every claim. "
            "Model output is not factual verification."
        )
    if current:
        return (
            "Source-only selected evidence; "
            "every related match needs human interpretation."
        )
    if report.get("workflow") == "casebook":
        return (
            f"Saved source-only report · {dated}. Inspect its retained "
            "source snapshot; every related match needs human interpretation."
        )
    return (
        f"Saved report · {dated}. Its origin is not classified here; "
        "check the displayed provenance and every claim."
    )


def campaign_source_records(document):
    """Project source metadata onto literal display fields without fetching."""
    if (
        not isinstance(document, dict)
        or not isinstance(document.get("sources"), list)
    ):
        return []
    return [
        {
            field: row.get(field, "") if isinstance(row.get(field, ""), str) else ""
            for field in ("id", "title", "url", "checked_at", "notes")
        }
        for row in document["sources"] if isinstance(row, dict)
    ]


def campaign_source_details(row):
    """Keep full URLs, notes and record dates accessible as selectable text."""
    return (
        f"Source: {row['title']}\nSource ID: {row['id']}\n"
        f"URL: {row['url'] or 'Not recorded'}\n"
        f"Source record checked: {row['checked_at'] or 'Not recorded'}\n\n"
        "Notes (user-entered; source not opened or independently verified):\n"
        + (row["notes"] or "No notes recorded.")
        + "\n\nA source record date does not refresh earlier claim snapshots."
    )


class NativeFundingController:
    """Read-only presentation state borrowing the existing runtime and workspace."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.closed = False
        self.saved = None
        self.summary = None

    def _check(self):
        if self.closed:
            raise ValueError("This funding view is closed.")

    def list(self):
        self._check()
        return self.runtime.call("campaigns.list")["campaigns"]

    def open(self, identifier):
        self._check()
        saved = self.runtime.call("campaigns.get", {"id": identifier})
        summary = self.runtime.call(
            "campaigns.funding_summary", {"document": saved["document"]}
        )
        self.saved, self.summary = copy.deepcopy(saved), copy.deepcopy(summary)
        return self.saved, self.summary

    def close(self):
        # The parent owns the application. Closing this view must not close it.
        self.closed = True


class CampaignSourcesPane:
    """Selectable metadata shared by native campaign reports and funding views."""

    def __init__(self, owner, parent):
        self.owner = owner
        self.rows = []
        self.frame = owner.ttk.Frame(parent)
        owner.ttk.Label(
            self.frame, text="Campaign sources · user-entered, unverified"
        ).pack(anchor="w")
        self.tree = owner.ttk.Treeview(
            self.frame, columns=("checked",), height=3, selectmode="browse"
        )
        self.tree.heading(
            "#0", text="Source title — select to inspect URL and full notes"
        )
        self.tree.heading("checked", text="Recorded check date")
        self.tree.column("checked", width=140, stretch=False)
        self.tree.pack(fill="x", pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.select())
        self.details = owner._text(self.frame, height=5, readonly=True)
        self.copy_button = owner.ttk.Button(
            self.frame, text="Copy source URL",
            command=lambda: owner._perform(self.copy_url),
        )
        self.copy_button.pack(anchor="w", pady=4)
        self.set_document(None)

    def set_document(self, document):
        self.rows = campaign_source_records(document)
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            self.tree.insert(
                "", "end", iid=str(index), text=row["title"],
                values=(row["checked_at"] or "Not recorded",),
            )
        if self.rows:
            self.tree.selection_set("0")
            self.select()
        else:
            self.owner._put(
                self.details,
                "No campaign source records are present in this snapshot.",
                readonly=True,
            )
            self.copy_button.state(["disabled"])

    def select(self):
        selected = self.tree.selection()
        if not selected:
            self.copy_button.state(["disabled"])
            return
        row = self.rows[int(selected[0])]
        self.owner._put(self.details, campaign_source_details(row), readonly=True)
        self.copy_button.state(
            ["!disabled"] if client.safe_url(row["url"]) else ["disabled"]
        )

    def copy_url(self):
        selected = self.tree.selection()
        if not selected or not client.safe_url(self.rows[int(selected[0])]["url"]):
            raise ValueError("Select a source with a recorded HTTP or HTTPS URL.")
        self.owner.root.clipboard_clear()
        self.owner.root.clipboard_append(self.rows[int(selected[0])]["url"])
        self.owner.status_var.set("Source URL copied. Sinter did not open or verify it.")


class NativeFundingWindow:
    """Modeless campaign inspection without a listener or additional runtime."""

    def __init__(self, owner):
        self.owner = owner
        self.controller = NativeFundingController(owner.controller.runtime)
        self.closed = False
        self.root = owner.tk.Toplevel(owner.root)
        try:
            self._build()
            self.refresh()
        except Exception:
            self.close()
            raise

    def _build(self):
        owner = self.owner
        self.root.title("Sinter — funding campaigns (read-only)")
        self.root.geometry("950x650")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        outer = owner.ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        owner.ttk.Label(
            outer, text="Current saved campaign totals and sources · read-only. "
            "Campaign editing remains in the full workbench. No provider request is made.",
            wraplength=880,
        ).pack(anchor="w")
        controls = owner.ttk.Frame(outer)
        controls.pack(fill="x", pady=6)
        owner.ttk.Button(
            controls, text="Refresh saved campaigns",
            command=lambda: owner._perform(self.refresh),
        ).pack(side="left", padx=(0, 6))
        owner.ttk.Button(
            controls, text="Close funding view", command=self.close,
        ).pack(side="left")
        body = owner.ttk.Panedwindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True)
        sidebar = owner.ttk.Frame(body)
        body.add(sidebar, weight=1)
        self.tree = owner.ttk.Treeview(sidebar, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True)
        owner.ttk.Button(
            sidebar, text="Inspect selected campaign",
            command=lambda: owner._perform(self.open_selected),
        ).pack(fill="x", pady=4)
        view = owner.ttk.Frame(body, padding=8)
        body.add(view, weight=3)
        self.notice = owner.tk.StringVar(value="Select a saved campaign to inspect.")
        owner.ttk.Label(view, textvariable=self.notice, wraplength=620).pack(anchor="w")
        tabs = owner.ttk.Notebook(view)
        tabs.pack(fill="both", expand=True, pady=6)
        totals, sources = owner.ttk.Frame(tabs), owner.ttk.Frame(tabs)
        tabs.add(totals, text="Recorded totals")
        tabs.add(sources, text="Sources and notes")
        self.summary_text = owner._text(totals, readonly=True)
        self.sources = CampaignSourcesPane(owner, sources)
        self.sources.frame.pack(fill="both", expand=True)

    def refresh(self):
        if self.closed:
            return
        selected = self.tree.selection()
        rows = self.controller.list()
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert("", "end", iid=row["id"], text=row["title"])
        if selected and selected[0] in self.tree.get_children():
            self.tree.selection_set(selected[0])
            self.open_selected()
        else:
            self.notice.set(
                "Select a saved campaign to inspect." if rows else
                "No saved campaigns. Create or import one through the "
                "shared CLI or full workbench."
            )
            self.owner._put(self.summary_text, "", readonly=True)
            self.sources.set_document(None)
            self.controller.saved = self.controller.summary = None

    def open_selected(self):
        if self.closed:
            return
        selected = self.tree.selection()
        if not selected:
            raise ValueError("Select a saved campaign first.")
        saved, summary = self.controller.open(selected[0])
        self.notice.set(
            f"{saved['document']['title']} · saved revision {saved['revision']} · "
            f"totals as of {summary['as_of']}. User-entered, not independently verified."
        )
        self.owner._put_readable(self.summary_text, summary["markdown"])
        self.sources.set_document(saved["document"])

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.controller.close()
        try:
            self.root.destroy()
        except self.owner.tk.TclError:
            pass
        if getattr(self.owner, "_funding_window", None) is self:
            self.owner._funding_window = None


class NativeWindowError(RuntimeError):
    """The native presentation cannot start in this environment."""


def register_window_client(root) -> None:
    # Tk on X11 emits its real _NET_WM_PID only with WM_CLIENT_MACHINE.
    # gethostname is local; this never resolves or contacts another host.
    if root.tk.call("tk", "windowingsystem") == "x11":
        root.wm_client(socket.gethostname())


def read_selected_text(path: str | Path, limit: int = TEXT_BYTES) -> str:
    """Read only a selected regular file, with a byte limit before decoding."""
    source = Path(path)
    before = source.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Choose a regular text file.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(source, flags)
    with os.fdopen(descriptor, "rb") as stream:
        actual = os.fstat(stream.fileno())
        if not stat.S_ISREG(actual.st_mode):
            raise ValueError("Choose a regular text file.")
        if (actual.st_dev, actual.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("The selected file changed. Choose it again.")
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f"Selected file exceeds {limit:,} bytes. Split it first.")
    try:
        return content.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Choose UTF-8 text or a Sinter JSON backup.") from exc


def readable_report_lines(markdown, *, report=None):
    """Project safe markup onto text; stored Markdown and exports stay exact."""
    lines = markdown.splitlines(keepends=True)
    duplicate = None
    if (
        isinstance(report, dict)
        and report.get("workflow") == "casebook"
        and not report.get("model_draft")
        and isinstance(report.get("document_type"), str)
        and report.get("document_type") in FORMATS
        and isinstance(report.get("title"), str)
        and isinstance(report.get("document_markdown"), str)
    ):
        heading = "# " + literal(report["title"])
        preface = [
            heading,
            "",
            FORMATS[report["document_type"]] + " - DRAFT / HUMAN REVIEW REQUIRED",
            "",
            heading,
        ]
        if [line.rstrip("\r\n") for line in lines[:5]] == preface and report[
            "document_markdown"
        ].splitlines()[:1] == [heading]:
            duplicate = 4

    # The model fallback includes unfenced exact JSON provenance. It is already
    # readable text, not authored Markdown, and must not be unescaped.
    decode = report is None or isinstance(report.get("markdown"), str)

    def readable(value):
        if not decode:
            return value
        return "".join(
            span.text + (" (" + span.href + ")" if span.href else "")
            for span in inline(value)
        )

    fence = None
    for index, line in enumerate(lines):
        if index == duplicate:
            continue
        marker = re.fullmatch(r"[ \t]*(`{3,}|~{3,})([^\r\n]*)\r?\n?", line)
        if fence is not None:
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= fence[1]
                and not marker[2].strip()
            ):
                fence = None
            yield line, "code"
        elif marker:
            fence = (marker[1][0], len(marker[1]))
            yield line, "code"
        elif line.startswith("> "):
            yield readable(line[2:]), "quote"
        elif line.startswith(("# ", "## ", "### ", "#### ")):
            yield readable(line.split(" ", 1)[1]), "heading"
        elif line.startswith("- "):
            yield "• " + readable(line[2:]), "bullet"
        else:
            yield readable(line), "body"


def select_all(event):
    """Standard select-all for this window's entries and source/report text."""
    widget = event.widget
    if widget.winfo_class() in {"Entry", "TEntry", "TCombobox"}:
        widget.selection_range(0, "end")
        widget.icursor("end")
    elif widget.winfo_class() == "Text":
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set("insert", "end-1c")
    else:
        return None
    return "break"


class NativeController:
    """Presentation state only; admission, retrieval and inference stay shared."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.document = {
            "schema": "sinter-casebook/v1",
            "title": "Untitled project",
            "questions": "",
            "documents": [],
            "document_type": "brief",
        }
        self.identifier = None
        self.revision = None
        self.dirty = False
        self.generation = 0
        self.variables = {"source_title": "", "excerpt": "", "question": ""}
        self.prepared = None
        self.consent = False
        self.result = None
        self.result_generation = None
        self.source_paths: set[Path] = set()
        self.closed = False

    def _check(self):
        if self.closed:
            raise ValueError("This workspace is closed.")

    def invalidate(self, *, source_changed=False):
        self.generation += 1
        self.prepared = None
        self.consent = False
        if source_changed:
            self.variables = {**self.variables, "source_title": "", "excerpt": ""}

    def edit_document(self, document):
        self._check()
        if document != self.document:
            self.document = copy.deepcopy(document)
            self.dirty = True
            self.invalidate(source_changed=True)

    def _load(self, document, identifier=None, revision=None):
        self.document = copy.deepcopy(document)
        self.identifier, self.revision = identifier, revision
        self.dirty = identifier is None
        self.invalidate(source_changed=True)

    def new(self):
        self._check()
        self._load(
            {
                "schema": "sinter-casebook/v1",
                "title": "Untitled project",
                "questions": "",
                "documents": [],
                "document_type": "brief",
            }
        )

    def import_project(self, path):
        self._check()
        content = read_selected_text(path, PROJECT_BYTES)
        try:
            document = json.loads(content)
        except ValueError as exc:
            raise ValueError("Choose a valid Sinter casebook JSON backup.") from exc
        admitted = self.runtime.call("casebooks.validate", {"document": document})
        self._load(admitted["document"])
        self.source_paths.add(Path(path).resolve())

    def import_text(self, paths):
        self._check()
        rows = [
            {"title": Path(path).name, "content": read_selected_text(path)}
            for path in paths
        ]
        if not rows:
            return
        candidate = {**self.document, "documents": [*self.document["documents"], *rows]}
        admitted = self.runtime.call("casebooks.validate", {"document": candidate})
        self.edit_document(admitted["document"])
        self.source_paths.update(Path(path).resolve() for path in paths)

    def open_project(self, identifier):
        self._check()
        value = self.runtime.call("casebooks.get", {"id": identifier})
        self._load(value["document"], value["id"], value["revision"])
        return value

    def save(self):
        self._check()
        if not self.dirty and self.identifier is not None:
            return {
                "id": self.identifier,
                "revision": self.revision,
                "document": copy.deepcopy(self.document),
            }
        value = self.runtime.call(
            "casebooks.save",
            {
                "document": self.document,
                "id": self.identifier,
                "revision": self.revision,
            },
        )
        self.document = copy.deepcopy(value["document"])
        self.identifier, self.revision = value["id"], value["revision"]
        self.dirty = False
        return value

    def start_build(self):
        self.save()
        value = self.runtime.call(
            "casebooks.build",
            {
                "id": self.identifier,
                "revision": self.revision,
                "document_type": self.document.get("document_type", "brief"),
            },
            wait=False,
        )
        return value["id"], self.generation

    def set_request(self, source_title, excerpt, question):
        self._check()
        values = {
            "source_title": source_title,
            "excerpt": excerpt,
            "question": question,
        }
        if values != self.variables:
            self.variables = values
            self.invalidate()

    def connection_settings(self):
        self._check()
        return self.runtime.connection_settings()

    def save_connection(self, values, *, confirm_endpoint=False, api_key=None):
        self._check()
        result = self.runtime.connection_settings(
            values,
            confirm_endpoint=confirm_endpoint,
            api_key=api_key,
        )
        self.invalidate()
        return result

    def start_models(self, values, *, confirm_endpoint=False, api_key=None):
        self._check()
        return self.runtime.connection_settings(
            values,
            confirm_endpoint=confirm_endpoint,
            api_key=api_key,
            discover=True,
            wait=False,
        )["id"]

    def preview(self):
        self._check()
        self.prepared = None
        self.consent = False
        generation = self.generation
        value = self.runtime.call(
            "template.preview",
            {"template": "native-source-question", "variables": self.variables},
        )
        if generation != self.generation or self.closed:
            raise ValueError("Inputs changed. Preview the current excerpt again.")
        self.prepared = copy.deepcopy(value)
        return value

    def approve(self, value):
        self._check()
        if value is True and self.prepared is None:
            raise ValueError("Preview the exact request before approving transfer.")
        self.consent = value is True

    def start_answer(self):
        self._check()
        if self.prepared is None or self.consent is not True:
            raise ValueError(
                "Preview the current exact excerpt and approve transfer first."
            )
        payload = {
            "template": "native-source-question",
            "variables": copy.deepcopy(self.variables),
            "context_hash": self.prepared["context_hash"],
            "consent": True,
        }
        generation = self.generation
        # Even a failed/uncertain submission consumes this approval. No replay.
        self.prepared = None
        self.consent = False
        value = self.runtime.call("template.job", payload, wait=False)
        return value["id"], generation

    def accept_result(self, generation, value):
        if self.closed or generation != self.generation:
            return False
        self.result = copy.deepcopy(value)
        self.result_generation = generation
        return True

    def save_report(self):
        self._check()
        if self.result is None or not isinstance(self.result.get("markdown"), str):
            raise ValueError(
                "Only a completed source report can be saved here. "
                "Export model-run JSON separately."
            )
        return self.runtime.call("reports.save", {"report": self.result})

    def open_report(self, identifier):
        self._check()
        self.result = self.runtime.call("reports.get", {"id": identifier})
        self.result_generation = None
        return self.result

    def import_report(self, path):
        self._check()
        try:
            value = json.loads(read_selected_text(path, 2_000_000))
        except ValueError as exc:
            raise ValueError("Choose a completed Sinter report JSON export.") from exc
        saved = self.runtime.call("reports.save", {"report": value})
        self.source_paths.add(Path(path).resolve())
        return self.open_report(saved["id"])

    def export_project(self, path):
        self._check()
        admitted = self.runtime.call("casebooks.validate", {"document": self.document})
        protected = self.runtime.output_sources(path, sources=tuple(self.source_paths))
        atomic_write_text(
            path,
            json.dumps(admitted["document"], ensure_ascii=False, indent=2),
            sources=protected,
        )

    def export_result(self, path, format="json"):
        self._check()
        if self.result is None:
            raise ValueError("Build or open a report before exporting it.")
        content = (
            json.dumps(self.result, ensure_ascii=False, indent=2)
            if format == "json"
            else result_markdown(self.result)
        )
        protected = self.runtime.output_sources(path, sources=tuple(self.source_paths))
        atomic_write_text(path, content, sources=protected)

    def close(self):
        if not self.closed:
            self.closed = True
            self.invalidate()
            self.runtime.close()


def _toolkit():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, ttk
    except ImportError as exc:
        raise NativeWindowError(
            "The native window needs Python's Tcl/Tk support. "
            "Use a Sinter desktop package or the command line."
        ) from exc
    return tk, ttk, filedialog, messagebox, scrolledtext


class NativeWindow:
    """Main-thread Tk view; existing Jobs perform long work, polled by after()."""

    def __init__(self, directory=None, *, runtime_factory=None, root_factory=None):
        self.tk, self.ttk, self.dialogs, self.messages, self.scrolledtext = _toolkit()
        try:
            self.root = (root_factory or self.tk.Tk)()
            self.root.withdraw()
            self.root.update_idletasks()
        except self.tk.TclError as exc:
            root = getattr(self, "root", None)
            if root is not None:
                try:
                    root.destroy()
                except self.tk.TclError:
                    pass
            raise NativeWindowError(
                "The native window cannot access a working desktop "
                "or Tcl/Tk resources. "
                "Use Sinter's command line in headless environments."
            ) from exc
        self.closed = False
        self._painting = False
        self._selected_source = None
        self._poll_id = None
        self._heartbeat_id = None
        self._signal_close_id = None
        self._signal_close_pending = False
        self.active_job = None
        self._job_generation = None
        self._job_kind = None
        self._setup_generation = 0
        self._setting_paint = False
        self._connection_key_edited = False
        self._browser_workbench = None
        self._funding_window = None
        self._close_pending = False
        self._close_poll_id = None
        self._close_generation = None
        try:
            if runtime_factory is None:
                from .runtime import Runtime

                runtime_factory = Runtime
            self.controller = NativeController(runtime_factory(directory))
            self._build_widgets()
            self._refresh()
            self._paint_document()
            self.root.deiconify()
        except Exception:
            controller = getattr(self, "controller", None)
            if controller is not None:
                controller.close()
            self.root.destroy()
            raise

    def _button(self, parent, text, command, *, inline=True):
        button = self.ttk.Button(
            parent, text=text, command=lambda: self._perform(command)
        )
        button.pack(side="left" if inline else "top", anchor="w", padx=(0, 6), pady=4)
        return button

    def _text(self, parent, *, height=8, readonly=False):
        box = self.scrolledtext.ScrolledText(
            parent, height=height, wrap="word", undo=not readonly, padx=8, pady=8
        )
        box.pack(fill="both", expand=True, pady=4)
        if readonly:
            box.configure(state="disabled")
        return box

    def _build_widgets(self):
        tk, ttk = self.tk, self.ttk
        self.root.title("Sinter — portable source workspace")
        register_window_client(self.root)
        self.root.geometry("1120x820")
        self.root.minsize(850, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.request_close)
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Sinter", font=("TkDefaultFont", 22, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            outer,
            text="Keep your sources together. Inspect evidence locally; "
            "send only an approved excerpt.",
            wraplength=1000,
        ).pack(anchor="w", pady=(2, 10))
        browser_bar = ttk.Frame(outer)
        browser_bar.pack(fill="x")
        self._button(browser_bar, "Open full workbench", self.open_workbench)
        self.browser_address = tk.StringVar(value="")
        ttk.Entry(
            browser_bar, textvariable=self.browser_address, state="readonly"
        ).pack(side="left", fill="x", expand=True, padx=6)
        self.browser_copy = self._button(
            browser_bar, "Copy local address", self.copy_workbench_address
        )
        self.browser_copy.state(["disabled"])
        self.browser_keep = self._button(
            browser_bar, "Keep window open", self.cancel_workbench_close
        )
        self.browser_keep.state(["disabled"])
        ttk.Label(
            outer,
            text="Campaign editing, Word files and other tools open in your browser. "
            "Keep this window open; saved work is shared, unsaved inputs stay here.",
            wraplength=1000,
        ).pack(anchor="w", pady=(0, 6))
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x")
        self._button(toolbar, "New project", self.new_project)
        self._button(toolbar, "Fictional example", self.example)
        self._button(toolbar, "Restore project JSON…", self.import_project)
        self._button(toolbar, "Export project JSON…", self.export_project)
        self._button(toolbar, "Refresh saved work", self._refresh)
        self._button(toolbar, "Funding campaigns", self.open_funding_campaigns)
        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True, pady=8)
        catalogue = ttk.Notebook(panes)
        panes.add(catalogue, weight=1)
        self.saved_tree = self._catalogue(
            catalogue, "Saved projects", "Open project", self.open_project
        )
        self.reports_tree = self._catalogue(
            catalogue, "Saved reports", "Open report", self.open_report
        )
        self.pages = ttk.Notebook(panes)
        panes.add(self.pages, weight=4)
        self.source_page = ttk.Frame(self.pages, padding=12)
        self.report_page = ttk.Frame(self.pages, padding=12)
        self.answer_page = ttk.Frame(self.pages, padding=12)
        self.setup_page = ttk.Frame(self.pages, padding=12)
        self.status_page = ttk.Frame(self.pages, padding=12)
        for page, name in (
            (self.source_page, "Sources"),
            (self.report_page, "Evidence & reports"),
            (self.setup_page, "Assistant setup"),
            (self.answer_page, "Short AI answer"),
            (self.status_page, "Status & scope"),
        ):
            self.pages.add(page, text=name)
        self.title_var = tk.StringVar(value="")
        self.format_var = tk.StringVar(value="brief")
        header = ttk.Frame(self.source_page)
        header.pack(fill="x")
        ttk.Label(header, text="Project title").pack(side="left")
        self.title_entry = ttk.Entry(header, textvariable=self.title_var)
        self.title_entry.pack(side="left", fill="x", expand=True, padx=8)
        self.format_box = ttk.Combobox(
            header,
            textvariable=self.format_var,
            values=("brief", "enquiry", "agenda", "handover"),
            state="readonly",
            width=12,
        )
        self.format_box.pack(side="left")
        ttk.Label(self.source_page, text="Questions to inspect — one per line").pack(
            anchor="w", pady=(8, 0)
        )
        self.questions_text = self._text(self.source_page, height=3)
        row = ttk.Frame(self.source_page)
        row.pack(fill="x")
        self._button(row, "Add UTF-8 text files…", self.import_text)
        self._button(row, "Add empty source", self.add_source)
        self._button(row, "Remove selected source", self.remove_source)
        self.sources_tree = ttk.Treeview(
            self.source_page, columns=("characters",), height=3, selectmode="browse"
        )
        self.sources_tree.heading(
            "#0", text="Admitted sources — select to inspect or edit"
        )
        self.sources_tree.heading("characters", text="Characters")
        self.sources_tree.column("characters", width=90, stretch=False)
        self.sources_tree.pack(fill="x", pady=4)
        self.sources_tree.bind("<<TreeviewSelect>>", self._source_selected)
        self.source_title_var = tk.StringVar(value="")
        ttk.Label(self.source_page, text="Selected source title").pack(anchor="w")
        ttk.Entry(self.source_page, textvariable=self.source_title_var).pack(
            fill="x", pady=4
        )
        ttk.Label(self.source_page, text="Selected source text").pack(anchor="w")
        self.source_text = self._text(self.source_page, height=8)
        ttk.Label(
            self.source_page,
            text="Edits are local. URLs inside text are never fetched. "
            "Save keeps a revision; backups keep full sources.",
            wraplength=800,
        ).pack(anchor="w")
        actions = ttk.Frame(self.source_page)
        actions.pack(fill="x")
        self.save_button = self._button(
            actions, "Save project locally", self.save_project
        )
        self.build_button = self._button(
            actions, "Find source evidence & gaps", self.build_report
        )
        report_actions = ttk.Frame(self.report_page)
        report_actions.pack(fill="x")
        self._button(report_actions, "Keep source report in history", self.save_report)
        self._button(report_actions, "Import report JSON…", self.import_report)
        self._button(
            report_actions, "Export exact JSON…", lambda: self.export_result("json")
        )
        self._button(
            report_actions,
            "Export readable Markdown…",
            lambda: self.export_result("md"),
        )
        self.report_notice = tk.StringVar(
            value="Build a source-only report, or open one from saved history."
        )
        ttk.Label(
            self.report_page, textvariable=self.report_notice, wraplength=800
        ).pack(anchor="w", pady=6)
        self.excerpts_tree = ttk.Treeview(
            self.report_page, columns=("source",), height=3, selectmode="browse"
        )
        self.excerpts_tree.heading("#0", text="Exact excerpt ID")
        self.excerpts_tree.heading("source", text="Source title")
        self.excerpts_tree.pack(fill="x")
        self.use_excerpt_button = self._button(
            self.report_page,
            "Use selected excerpt for one question",
            self.use_excerpt,
            inline=False,
        )
        report_tabs = self.report_tabs = ttk.Notebook(self.report_page)
        report_tabs.pack(fill="both", expand=True)
        readable, exact = ttk.Frame(report_tabs), ttk.Frame(report_tabs)
        report_tabs.add(readable, text="Readable report")
        report_tabs.add(exact, text="Exact JSON / provenance")
        self.report_text = self._text(readable, readonly=True)
        self.report_json = self._text(exact, readonly=True)
        self.campaign_sources_page = ttk.Frame(report_tabs)
        report_tabs.add(self.campaign_sources_page, text="Campaign sources and notes")
        self.campaign_sources = CampaignSourcesPane(self, self.campaign_sources_page)
        self.campaign_sources.frame.pack(fill="both", expand=True)
        report_tabs.hide(self.campaign_sources_page)
        self._build_connection_widgets()
        ttk.Label(
            self.answer_page,
            text="Optional short draft. A selected excerpt "
            "is not a complete-source review. "
            "Model output and citation IDs do not establish factual support.",
            wraplength=800,
        ).pack(anchor="w")
        self._button(
            self.answer_page,
            "Choose provider & model…",
            lambda: self.pages.select(self.setup_page),
            inline=False,
        )
        self.answer_title_var = tk.StringVar(value="")
        ttk.Label(self.answer_page, text="Selected source title").pack(
            anchor="w", pady=(8, 0)
        )
        ttk.Entry(self.answer_page, textvariable=self.answer_title_var).pack(fill="x")
        ttk.Label(
            self.answer_page, text="Exact selected excerpt — review before sending"
        ).pack(anchor="w", pady=(8, 0))
        self.excerpt_text = self._text(self.answer_page, height=5)
        self.question_var = tk.StringVar(value="")
        ttk.Label(self.answer_page, text="One question").pack(anchor="w")
        ttk.Entry(self.answer_page, textvariable=self.question_var).pack(
            fill="x", pady=4
        )
        self.preview_button = self._button(
            self.answer_page,
            "Preview exact request & destination",
            self.preview,
            inline=False,
        )
        self.preview_text = self._text(self.answer_page, height=7, readonly=True)
        self.consent_var = tk.BooleanVar(value=False)
        self.consent_box = ttk.Checkbutton(
            self.answer_page,
            variable=self.consent_var,
            text="I approve this exact preview and displayed destination. "
            "I will review the draft.",
            command=lambda: self._perform(self._approval_changed),
        )
        self.consent_box.pack(anchor="w", pady=6)
        self.consent_box.state(["disabled"])
        self.ask_button = self._button(
            self.answer_page, "Ask once with this approval", self.ask, inline=False
        )
        self.ask_button.state(["disabled"])
        self.status_text = self._text(self.status_page, readonly=True)
        footer = ttk.Frame(outer)
        footer.pack(fill="x")
        self.status_var = tk.StringVar(
            value="Ready. Source work is offline; nothing is sent automatically."
        )
        ttk.Label(footer, textvariable=self.status_var, wraplength=850).pack(
            side="left", fill="x", expand=True
        )
        self.stop_button = self._button(footer, "Stop task", self.cancel_task)
        self.stop_button.state(["disabled"])
        for variable in (self.title_var, self.format_var, self.source_title_var):
            variable.trace_add("write", lambda *_: self._document_changed())
        for variable in (self.answer_title_var, self.question_var):
            variable.trace_add("write", lambda *_: self._request_changed())
        for widget, handler in (
            (self.questions_text, self._document_changed),
            (self.source_text, self._document_changed),
            (self.excerpt_text, self._request_changed),
        ):
            widget.bind(
                "<<Modified>>",
                lambda event, callback=handler: self._modified(event, callback),
            )
        self.root.bind("<Control-s>", lambda event: self._perform(self.save_project))
        self.root.bind("<Control-a>", select_all)
        if self.root.tk.call("tk", "windowingsystem") == "aqua":
            self.root.bind("<Command-a>", select_all)

    def _build_connection_widgets(self):
        tk, ttk = self.tk, self.ttk
        # Keep setup usable at the minimum window height rather than clipping
        # the explicit destination approval and Save controls below the page.
        self.setup_scroll = tk.Canvas(self.setup_page, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            self.setup_page, orient="vertical", command=self.setup_scroll.yview
        )
        self.setup_scroll.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.setup_scroll.pack(side="left", fill="both", expand=True)
        page = ttk.Frame(self.setup_scroll, padding=(0, 0, 12, 0))
        item = self.setup_scroll.create_window((0, 0), window=page, anchor="nw")
        page.bind(
            "<Configure>",
            lambda _event: self.setup_scroll.configure(
                scrollregion=self.setup_scroll.bbox("all")
            ),
        )

        def fit_setup(event):
            self.setup_scroll.itemconfigure(item, width=event.width)
            for widget in page.winfo_children():
                if isinstance(widget, ttk.Label):
                    widget.configure(wraplength=max(240, event.width - 24))

        self.setup_scroll.bind("<Configure>", fit_setup)
        ttk.Label(
            page,
            text="Choose the optional assistant connection",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            page,
            text="Source evidence works offline. Loading model names sends "
            "no source text and generates no answer. A catalogue does not prove "
            "free inference, availability or quality.",
            wraplength=760,
        ).pack(anchor="w", pady=8)
        self.connection_vars = {
            name: tk.StringVar()
            for name in ("provider", "api_url", "model", "max_tokens")
        }
        self.connection_boxes = {}
        for name, label in (
            ("provider", "API style"),
            ("api_url", "API base address"),
            ("model", "Exact model identifier"),
            ("max_tokens", "Maximum output tokens"),
        ):
            ttk.Label(page, text=label).pack(anchor="w", pady=(6, 0))
            if name in {"provider", "model"}:
                box = ttk.Combobox(page, textvariable=self.connection_vars[name])
                if name == "provider":
                    box.configure(
                        values=("openai-compatible", "anthropic", "chatgpt"),
                        state="readonly",
                    )
            else:
                box = ttk.Entry(page, textvariable=self.connection_vars[name])
            box.pack(fill="x", pady=2)
            self.connection_boxes[name] = box
        ttk.Label(
            page,
            text="Remote APIs require HTTPS; an installed local server may "
            "use HTTP on loopback. Enter an exact provider ID or load the catalogue "
            "and explicitly select one. ChatGPT subscriptions and provider API keys "
            "are separate. The chatgpt style uses an already configured Sinter "
            "account; account sign-in remains in the full workbench.",
            wraplength=760,
        ).pack(anchor="w", pady=8)
        self.connection_key_var = tk.StringVar()
        ttk.Label(
            page, text="New API key for this session (optional, write-only)"
        ).pack(anchor="w")
        self.connection_key_box = ttk.Entry(
            page,
            textvariable=self.connection_key_var,
            show="•",
        )
        self.connection_key_box.pack(fill="x", pady=2)
        ttk.Label(
            page,
            text="Leave blank to retain a saved session key. Keys are never "
            "saved to disk or exports. Public endpoints may allow anonymous access; "
            "authentication or charges can still be required. Default NeuroForge "
            "environment/key-file credentials may apply if configured by you.",
            wraplength=760,
        ).pack(anchor="w", pady=4)
        self.connection_confirm_var = tk.BooleanVar(value=False)
        self.connection_confirm_box = ttk.Checkbutton(
            page,
            variable=self.connection_confirm_var,
            text="I approve contacting the API address displayed above.",
        )
        self.connection_confirm_box.pack(anchor="w", pady=6)
        buttons = ttk.Frame(page)
        buttons.pack(fill="x")
        self.models_button = self._button(
            buttons, "Load available models", self.load_models
        )
        self.connection_save_button = self._button(
            buttons, "Save connection locally", self.save_connection
        )
        secondary = ttk.Frame(page)
        secondary.pack(fill="x")
        self._button(secondary, "Forget session key", self.forget_connection_key)
        self._button(secondary, "Reload saved connection", self.reload_connection)
        self.connection_notice = tk.StringVar()
        ttk.Label(page, textvariable=self.connection_notice, wraplength=760).pack(
            anchor="w", pady=8
        )
        self._paint_connection(self.controller.connection_settings())
        for name, variable in self.connection_vars.items():
            variable.trace_add(
                "write", lambda *_, field=name: self._connection_changed(field)
            )
        self.connection_key_var.trace_add(
            "write", lambda *_: self._connection_changed("key")
        )

    def _paint_connection(self, public):
        self._setting_paint = True
        try:
            self._connection_saved = public["settings"]
            for name, variable in self.connection_vars.items():
                variable.set(str(public["settings"][name]))
            self.connection_key_var.set("")
            self.connection_key_box.configure(
                state="disabled"
                if public["settings"]["provider"] == "chatgpt"
                else "normal"
            )
            self._connection_key_edited = False
            self.connection_confirm_var.set(False)
            self.connection_boxes["model"].configure(values=())
            message = (
                "Connection saved locally. "
                + (
                    "A write-only key is held for this session. "
                    if public["has_session_key"]
                    else "No session key is held. "
                )
                + "Preview and approve the exact source request before asking."
            )
            if public["environment_override"]:
                message += (
                    " Launcher environment overrides the saved API address/model; "
                    "Status shows the effective connection. Change that launcher "
                    "configuration to use the selection here."
                )
            if public.get("warning"):
                message += " " + public["warning"]
            self.connection_notice.set(message)
        finally:
            self._setting_paint = False

    def _connection_changed(self, field):
        if self._setting_paint or self.closed:
            return
        self._setup_generation += 1
        self.controller.invalidate()
        if hasattr(self, "consent_var"):
            self._clear_preview()
        if field in {"api_url", "provider"}:
            self._setting_paint = True
            try:
                self.connection_key_var.set("")
                self._connection_key_edited = False
                self.connection_confirm_var.set(False)
                self.connection_boxes["model"].configure(values=())
                self.connection_key_box.configure(
                    state="disabled"
                    if self.connection_vars["provider"].get() == "chatgpt"
                    else "normal"
                )
            finally:
                self._setting_paint = False
        elif field == "key":
            self._connection_key_edited = True
        self.connection_notice.set(
            "Unsaved connection changes. Save before previewing a source request."
        )

    def _connection_draft(self):
        values = {
            name: variable.get().strip()
            for name, variable in self.connection_vars.items()
        }
        try:
            values["max_tokens"] = int(values["max_tokens"])
        except ValueError:
            raise ValueError(
                "Enter a whole number for maximum output tokens."
            ) from None
        return values

    def load_models(self):
        if self.active_job:
            raise ValueError("One task is already active. Stop or finish it first.")
        if not self.connection_confirm_var.get():
            raise ValueError(
                "Approve the displayed API destination before loading its model list."
            )
        values = self._connection_draft()
        values["model"] = "probe-placeholder"
        # Discovery has no output. A valid native 1-token cap must not fail
        # the placeholder's general-provider minimum or change the saved cap.
        values["max_tokens"] = max(client.MIN_OUTPUT_TOKENS, values["max_tokens"])
        identifier = self.controller.start_models(
            values,
            confirm_endpoint=True,
            api_key=self.connection_key_var.get()
            if self._connection_key_edited
            else None,
        )
        self.connection_notice.set(
            "Loading model names only. This does not save the connection "
            "or generate an answer."
        )
        self._begin_job(identifier, self._setup_generation, "models")

    def _accept_models(self, generation, value):
        if generation != self._setup_generation:
            self.connection_notice.set(
                "Connection inputs changed. The older catalogue was not applied; "
                "load again explicitly."
            )
            return
        ids = tuple(model["id"] for model in value.get("models", []))
        self.connection_boxes["model"].configure(values=ids)
        self.connection_notice.set(
            f"{len(ids)} model identifiers returned. Select one explicitly, then save. "
            "No answer or source transfer was tested."
            if ids
            else "No model identifiers returned. Enter the exact ID "
            "supplied by your provider."
        )

    def save_connection(self):
        if self.active_job:
            raise ValueError(
                "Stop or finish the active task before changing its connection."
            )
        public = self.controller.save_connection(
            self._connection_draft(),
            confirm_endpoint=self.connection_confirm_var.get(),
            api_key=self.connection_key_var.get()
            if self._connection_key_edited
            else None,
        )
        self._setup_generation += 1
        self._paint_connection(public)
        self._clear_preview()
        self._refresh()
        self.status_var.set(
            "Connection saved locally. Preview the exact source request again; "
            "nothing was sent."
        )

    def forget_connection_key(self):
        if self.active_job:
            raise ValueError(
                "Stop or finish the active task before clearing its session key."
            )
        values = {name: self._connection_saved[name] for name in self.connection_vars}
        public = self.controller.save_connection(values, api_key="")
        self._setup_generation += 1
        self._paint_connection(public)
        self.connection_notice.set(
            "Session key forgotten. Default NeuroForge environment/key-file "
            "credentials may still apply."
        )
        self._clear_preview()
        self._refresh()

    def reload_connection(self):
        if self.active_job:
            raise ValueError(
                "Stop or finish the active task before reloading settings."
            )
        self.controller.invalidate()
        self._setup_generation += 1
        self._paint_connection(self.controller.connection_settings())
        self._clear_preview()

    def _catalogue(self, parent, title, button, command):
        frame = self.ttk.Frame(parent, padding=8)
        parent.add(frame, text=title)
        tree = self.ttk.Treeview(frame, show="tree", selectmode="browse", height=15)
        tree.pack(fill="both", expand=True)
        self._button(frame, button, command, inline=False)
        return tree

    @staticmethod
    def _contents(widget):
        return widget.get("1.0", "end-1c")

    @staticmethod
    def _put(widget, content, *, readonly=False):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.edit_modified(False)
        if readonly:
            widget.configure(state="disabled")

    @staticmethod
    def _put_readable(widget, markdown, *, report=None):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.tag_configure(
            "heading", font=("TkDefaultFont", 13, "bold"), spacing1=10, spacing3=4
        )
        widget.tag_configure("quote", lmargin1=16, lmargin2=16, spacing3=6)
        widget.tag_configure("code", font="TkFixedFont")
        for line, style in readable_report_lines(markdown, report=report):
            widget.insert("end", line, style)
        widget.edit_modified(False)
        widget.configure(state="disabled")

    def _perform(self, callback):
        if self.closed:
            return
        try:
            callback()
        except Exception as exc:
            self.status_var.set(str(exc))
            self.messages.showerror(
                "Sinter — action could not finish", str(exc), parent=self.root
            )

    def _modified(self, event, callback):
        if event.widget.edit_modified():
            event.widget.edit_modified(False)
            if not self._painting:
                callback()

    def _clear_preview(self):
        self.consent_var.set(False)
        self.consent_box.state(["disabled"])
        self.ask_button.state(["disabled"])
        self._put(
            self.preview_text,
            "Inputs changed. Preview again before approving transfer.",
            readonly=True,
        )

    def _document_changed(self):
        if self._painting or self.closed:
            return
        value = copy.deepcopy(self.controller.document)
        value.update(
            title=self.title_var.get(),
            questions=self._contents(self.questions_text),
            document_type=self.format_var.get(),
        )
        if self._selected_source is not None and self._selected_source < len(
            value["documents"]
        ):
            value["documents"][self._selected_source].update(
                title=self.source_title_var.get(),
                content=self._contents(self.source_text),
            )
        generation = self.controller.generation
        self.controller.edit_document(value)
        if generation != self.controller.generation:
            self._clear_preview()
            self._painting = True
            try:
                self.answer_title_var.set("")
                self._put(self.excerpt_text, "")
            finally:
                self._painting = False
            self.status_var.set(
                "Unsaved source changes. Prior saved reports remain unchanged."
            )
            self._report_scope()

    def _request_changed(self):
        if self._painting or self.closed:
            return
        self.controller.set_request(
            self.answer_title_var.get(),
            self._contents(self.excerpt_text),
            self.question_var.get(),
        )
        self._clear_preview()

    def _paint_document(self):
        self.controller.set_request("", "", self.question_var.get())
        self._painting = True
        try:
            self.title_var.set(self.controller.document["title"])
            self.format_var.set(self.controller.document.get("document_type", "brief"))
            self._put(
                self.questions_text, self.controller.document.get("questions", "")
            )
            self.sources_tree.delete(*self.sources_tree.get_children())
            for index, row in enumerate(self.controller.document["documents"]):
                self.sources_tree.insert(
                    "",
                    "end",
                    iid=str(index),
                    text=row["title"],
                    values=(len(row["content"]),),
                )
            self._selected_source = None
            self.source_title_var.set("")
            self._put(self.source_text, "")
            self.answer_title_var.set("")
            self._put(self.excerpt_text, "")
        finally:
            self._painting = False
        self._clear_preview()
        self._report_scope()

    def _source_selected(self, _event=None):
        selected = self.sources_tree.selection()
        if not selected or self.closed:
            return
        self._document_changed()
        self._selected_source = int(selected[0])
        row = self.controller.document["documents"][self._selected_source]
        self._painting = True
        try:
            self.source_title_var.set(row["title"])
            self._put(self.source_text, row["content"])
        finally:
            self._painting = False

    def _refresh(self):
        for tree, operation, key in (
            (self.saved_tree, "casebooks.list", "casebooks"),
            (self.reports_tree, "reports.list", "reports"),
        ):
            rows = self.controller.runtime.call(operation)[key]
            tree.delete(*tree.get_children())
            for row in rows:
                title = (
                    report_catalogue_title(row)
                    if operation == "reports.list" else row["title"]
                )
                tree.insert("", "end", iid=row["id"], text=title)
        state = self.controller.runtime.call("runtime.status")
        self._put(
            self.status_text,
            "Native workspace scope\n\n"
            "Sources, saved projects, source-only evidence/gaps, "
            "short approved source answers, and JSON/Markdown exports "
            "use the same Sinter runtime as the web UI and CLI.\n\n"
            "Funding campaigns provides read-only recorded totals and sources "
            "from this same workspace. The full browser workbench provides "
            "campaign editing, recording and rich-document screens. This window does not run "
            "scheduled watches or sign into accounts. Assistant setup shares "
            "saved connection preferences and write-only session keys with "
            "the full workbench.\n\n"
            "No provider has been tested by opening this window. "
            "No AI quality or platform qualification is implied.\n\n"
            + json.dumps(state, ensure_ascii=False, indent=2),
            readonly=True,
        )

    def _confirm_replace(self):
        return not self.controller.dirty or self.messages.askyesno(
            "Keep unsaved work?",
            "Replace this unsaved project? Export or save it first "
            "if you want to keep these edits.",
            parent=self.root,
        )

    def new_project(self):
        if self.active_job:
            raise ValueError("Stop the current task before changing projects.")
        if self._confirm_replace():
            self.controller.new()
            self._paint_document()
            self.pages.select(self.source_page)

    def example(self):
        if self.active_job:
            raise ValueError("Stop the current task before changing projects.")
        if self._confirm_replace():
            self.controller.new()
            self.controller.edit_document(
                {
                    "schema": "sinter-casebook/v1",
                    "title": "Fictional Lantern project",
                    "questions": "How many days may a fictional lantern "
                    "be borrowed?\nWho approved the fictional budget?",
                    "document_type": "brief",
                    "documents": [
                        {
                            "title": "Fictional handbook",
                            "content": "Wholly fictional practice note: "
                            "Lantern loans last 14 days. "
                            "No budget approval is recorded.",
                        }
                    ],
                }
            )
            self._paint_document()
            self.pages.select(self.source_page)

    def import_project(self):
        if self.active_job:
            raise ValueError("Stop the current task before changing projects.")
        path = self.dialogs.askopenfilename(
            parent=self.root,
            title="Restore as a new unsaved project",
            filetypes=[("Sinter JSON backup", "*.json")],
        )
        if path and self._confirm_replace():
            self.controller.import_project(path)
            self._paint_document()
            self.status_var.set(
                "Backup admitted as a new project. "
                "Existing saved projects were not overwritten."
            )

    def import_text(self):
        paths = self.dialogs.askopenfilenames(
            parent=self.root,
            title="Select UTF-8 source text",
            filetypes=[("Text sources", "*.txt *.md *.csv *.json"), ("All files", "*")],
        )
        if paths:
            self.controller.import_text(paths)
            self._paint_document()
            self.status_var.set(
                "Selected text admitted locally. Review and save it; nothing was sent."
            )

    def add_source(self):
        self.controller.edit_document(
            {
                **self.controller.document,
                "documents": [
                    *self.controller.document["documents"],
                    {"title": "New source", "content": ""},
                ],
            }
        )
        self._paint_document()
        selected = str(len(self.controller.document["documents"]) - 1)
        self.sources_tree.selection_set(selected)
        self._source_selected()
        self.source_text.focus_set()

    def remove_source(self):
        if self._selected_source is None:
            raise ValueError("Select a source first.")
        value = copy.deepcopy(self.controller.document)
        value["documents"].pop(self._selected_source)
        self.controller.edit_document(value)
        self._paint_document()

    def save_project(self):
        self._document_changed()
        value = self.controller.save()
        self._refresh()
        self._paint_document()
        self.status_var.set(
            f"Saved locally at revision {value['revision']}. "
            "Other-window changes are checked before replacing anything."
        )

    def open_project(self):
        selected = self.saved_tree.selection()
        if not selected:
            raise ValueError("Select a saved project first.")
        if self.active_job:
            raise ValueError("Stop the current task before changing projects.")
        if self._confirm_replace():
            self.controller.open_project(selected[0])
            self._paint_document()
            self.pages.select(self.source_page)
            self.status_var.set(
                f"Opened locally at revision {self.controller.revision}."
            )

    def build_report(self):
        if self.active_job:
            raise ValueError("One task is already active.")
        self._document_changed()
        identifier, generation = self.controller.start_build()
        self._begin_job(identifier, generation, "source")

    def _begin_job(self, identifier, generation, kind):
        self.active_job, self._job_generation, self._job_kind = (
            identifier,
            generation,
            kind,
        )
        self.stop_button.state(["!disabled"])
        self.build_button.state(["disabled"])
        self.ask_button.state(["disabled"])
        self.status_var.set(
            "Task started. Stop requests cancellation at the next "
            "bounded checkpoint; no automatic replay."
        )
        self._poll_id = self.root.after(100, self._poll_job)

    def _poll_job(self):
        self._poll_id = None
        if self.closed or not self.active_job:
            return
        try:
            state = self.controller.runtime.call("jobs.get", {"id": self.active_job})
            self.status_var.set(
                state.get("error") or state.get("message") or state["status"]
            )
            if state["status"] in {"queued", "running"}:
                self._poll_id = self.root.after(100, self._poll_job)
                return
            if self._job_kind == "models":
                if self._job_generation != self._setup_generation:
                    self._accept_models(self._job_generation, {})
                    self.status_var.set(
                        "Older catalogue outcome ignored after connection edits."
                    )
                elif state["status"] == "done":
                    self._accept_models(self._job_generation, state["result"])
                else:
                    self.connection_notice.set(
                        state.get("error") or state.get("message") or state["status"]
                    )
            elif isinstance(state.get("result"), dict):
                if self.controller.accept_result(self._job_generation, state["result"]):
                    self._paint_result()
                else:
                    self.status_var.set(
                        "The inputs changed during this task. "
                        "Its older result was not applied; "
                        "no repeat request was sent."
                    )
            if state["status"] == "done":
                self._refresh()
        except Exception as exc:
            if not self.closed:
                self.status_var.set(str(exc))
        finally:
            if not self._poll_id and not self.closed:
                self.active_job = None
                self.stop_button.state(["disabled"])
                self.build_button.state(["!disabled"])

    def cancel_task(self):
        if self.active_job:
            self.controller.runtime.call("jobs.cancel", {"id": self.active_job})
            self.status_var.set(
                "Stop requested. Remote outcomes may be uncertain; "
                "no request will be replayed automatically."
            )

    def _report_scope(self):
        if self.controller.result is None:
            return
        current = self.controller.result_generation == self.controller.generation
        self.report_notice.set(
            report_scope_notice(self.controller.result, current=current)
        )

    def _paint_result(self):
        value = self.controller.result
        self._put_readable(self.report_text, result_markdown(value), report=value)
        self._put(
            self.report_json,
            json.dumps(value, ensure_ascii=False, indent=2),
            readonly=True,
        )
        self.excerpts_tree.delete(*self.excerpts_tree.get_children())
        sources = {
            row["id"]: row.get("title", "")
            for row in value.get("sources", [])
            if "id" in row
        }
        for index, row in enumerate(value.get("excerpts", [])):
            self.excerpts_tree.insert(
                "",
                "end",
                iid=str(index),
                text=row["id"],
                values=(sources.get(row["source_id"], row["source_id"]),),
            )
        if value.get("workflow") == "campaign":
            self.campaign_sources.set_document(value.get("campaign"))
            self.report_tabs.add(
                self.campaign_sources_page, text="Campaign sources and notes"
            )
            self.excerpts_tree.pack_forget()
            self.use_excerpt_button.pack_forget()
        else:
            self.campaign_sources.set_document(None)
            self.report_tabs.hide(self.campaign_sources_page)
            self.excerpts_tree.pack(fill="x", before=self.report_tabs)
            self.use_excerpt_button.pack(anchor="w", before=self.report_tabs)
        self._report_scope()
        self.pages.select(self.report_page)

    def open_funding_campaigns(self):
        if self.closed:
            return
        child = self._funding_window
        if child is not None and not child.closed:
            child.root.lift()
            child.root.focus_set()
            return
        self._funding_window = NativeFundingWindow(self)

    def save_report(self):
        self.controller.save_report()
        self._refresh()
        self.status_var.set(
            "Exact source report retained in local history. "
            "Future source changes do not rewrite it."
        )

    def open_report(self):
        selected = self.reports_tree.selection()
        if not selected:
            raise ValueError("Select a saved report first.")
        self.controller.open_report(selected[0])
        self._paint_result()

    def import_report(self):
        path = self.dialogs.askopenfilename(
            parent=self.root,
            title="Import a completed report snapshot",
            filetypes=[("Report JSON", "*.json")],
        )
        if path:
            self.controller.import_report(path)
            self._paint_result()
            self._refresh()
            self.status_var.set(
                "Report snapshot imported into local history. "
                "Source projects were not changed."
            )

    def use_excerpt(self):
        selected = self.excerpts_tree.selection()
        if not selected:
            raise ValueError(
                "Select a retrieved excerpt first, or enter your own "
                "exact selected text in Short AI answer."
            )
        value = self.controller.result
        row = value["excerpts"][int(selected[0])]
        source = next(
            item for item in value["sources"] if item["id"] == row["source_id"]
        )
        self._painting = True
        try:
            self.answer_title_var.set(source["title"])
            self._put(self.excerpt_text, row["quote"])
        finally:
            self._painting = False
        self._request_changed()
        self.pages.select(self.answer_page)

    def preview(self):
        if hasattr(self, "connection_vars") and (
            self._connection_key_edited
            or self._connection_draft()
            != {name: self._connection_saved[name] for name in self.connection_vars}
        ):
            self.pages.select(self.setup_page)
            raise ValueError(
                "Save or discard the connection changes before previewing."
            )
        self._request_changed()
        value = self.controller.preview()
        self._put(
            self.preview_text,
            json.dumps(value, ensure_ascii=False, indent=2),
            readonly=True,
        )
        self.consent_box.state(["!disabled"])
        self.status_var.set(
            "Exact request and destination previewed locally. "
            "No provider request was sent."
        )

    def _approval_changed(self):
        self.controller.approve(self.consent_var.get())
        self.ask_button.state(
            [
                "!disabled"
                if self.controller.consent and not self.active_job
                else "disabled"
            ]
        )

    def ask(self):
        if self.active_job:
            raise ValueError("One task is already active.")
        identifier, generation = self.controller.start_answer()
        self._clear_preview()
        self._begin_job(identifier, generation, "answer")

    def export_project(self):
        self._document_changed()
        path = self.dialogs.asksaveasfilename(
            parent=self.root,
            title="Export full project sources",
            defaultextension=".json",
            initialfile="sinter-casebook.json",
            filetypes=[("JSON", "*.json")],
        )
        if path:
            self.controller.export_project(path)
            self.status_var.set(
                "Project backup saved. Original selected source files were protected."
            )

    def export_result(self, format):
        extension = ".json" if format == "json" else ".md"
        path = self.dialogs.asksaveasfilename(
            parent=self.root,
            title="Export the displayed snapshot",
            defaultextension=extension,
            initialfile="sinter-report" + extension,
            filetypes=[("Report", "*" + extension)],
        )
        if path:
            self.controller.export_result(path, format)
            self.status_var.set(
                "Displayed snapshot exported unchanged; "
                "original selected source files were protected."
            )

    def open_workbench(self) -> None:
        """Open an explicit local browser view while retaining native inputs."""
        if self.closed:
            return
        if getattr(self, "_close_pending", False):
            raise ValueError("Wait for the local close result or keep the window open.")
        if self.active_job:
            raise ValueError(
                "Finish or stop the current task before opening the workbench."
            )
        self._document_changed()
        if self._browser_workbench is None or self._browser_workbench.closed:
            if self.controller.dirty:
                answer = self.messages.askyesnocancel(
                    "Open full workbench",
                    "Save this source project before opening your browser?\n\n"
                    "Yes saves it locally. No keeps your unsaved edits here; "
                    "the browser sees only saved records. Cancel stays here.",
                    parent=self.root,
                )
                if answer is None:
                    return
                if answer:
                    # Save only the source project. Repainting it would also
                    # clear the separate, unsaved short-answer excerpt.
                    self.controller.save()
                    self._refresh()
            from .native_browser import NativeBrowserWorkbench

            self._browser_workbench = NativeBrowserWorkbench(
                self.controller.runtime.app
            )
            self.browser_address.set(self._browser_workbench.url)
            self.browser_copy.state(["!disabled"])
        opened = self._browser_workbench.open_browser()
        self.status_var.set(
            (
                "Browser launch requested. "
                if opened
                else "No browser accepted the launch. The local workbench is running; "
                "copy its address if your browser policy permits it. "
            )
            + "Your native inputs remain here. Scheduled watch checks stay paused. "
            "Closing waits for local requests before stopping the browser service."
        )

    def copy_workbench_address(self) -> None:
        """Copy only the owned loopback URL, without credentials or payload."""
        workbench = self._browser_workbench
        if workbench is None or workbench.closed:
            raise ValueError("Open the full workbench first.")
        self.root.clipboard_clear()
        self.root.clipboard_append(workbench.url)
        self.status_var.set(
            "Local workbench address copied. No document text or key is in it."
        )

    def _poll_browser_quit(self) -> None:
        workbench = getattr(self, "_browser_workbench", None)
        if self.closed or workbench is None or not workbench.quit_requested.is_set():
            return
        if getattr(self, "_close_pending", False):
            return
        workbench.quit_requested.clear()
        workbench.set_quit_state("confirming")
        self._perform(lambda: self.request_close(browser_requested=True))

    def request_close(self, *, browser_requested: bool = False) -> None:
        if self.closed or getattr(self, "_close_pending", False):
            return
        if (
            getattr(self, "_browser_workbench", None) is not None
            and not self._browser_workbench.closed
        ):
            if not self.messages.askyesno(
                "Close Sinter and its workbench?",
                "This waits for local browser requests, stops the listener and "
                "requests task cancellation. Save or export browser work first. "
                "Close both views?",
                parent=self.root,
            ):
                self._browser_workbench.set_quit_state("cancelled")
                return
        if self.controller.dirty:
            answer = self.messages.askyesnocancel(
                "Unsaved source edits",
                "Save this project locally before closing?",
                parent=self.root,
            )
            if answer is None:
                workbench = getattr(self, "_browser_workbench", None)
                if workbench is not None:
                    workbench.set_quit_state("cancelled")
                return
            if answer:
                try:
                    # A refused close must keep separate answer/setup drafts.
                    self._document_changed()
                    self.controller.save()
                    self._refresh()
                except Exception as exc:
                    self.messages.showerror(
                        "Sinter — keep your edits", str(exc), parent=self.root
                    )
                    workbench = getattr(self, "_browser_workbench", None)
                    if workbench is not None:
                        workbench.set_quit_state("refused")
                    return
        self.close()

    def _request_signal_close(self):
        # A Python signal can interrupt a live Tk callback between resolving a
        # widget and calling its Tcl command. Destroying it synchronously makes
        # the resumed callback address a deleted widget. Leave that callback
        # intact and close at the next safe idle boundary; repeated signals do
        # not queue multiple closes.
        if self.closed or self._signal_close_pending:
            return
        # Mark this before registering with Tk: another Python signal can also
        # interrupt the registration itself.
        self._signal_close_pending = True

        def close_when_idle():
            self._signal_close_id = None
            self._signal_close_pending = False
            self.close()

        try:
            self._signal_close_id = self.root.after_idle(close_when_idle)
        except Exception:
            self._signal_close_pending = False
            raise

    def _set_keep_enabled(self, enabled):
        button = getattr(self, "browser_keep", None)
        if button is not None:
            button.state(["!disabled"] if enabled else ["disabled"])

    def close(self):
        """Begin owned cleanup; retain the GUI and runtime until it succeeds."""
        if self.closed or getattr(self, "_close_pending", False):
            return
        workbench = getattr(self, "_browser_workbench", None)
        if workbench is None or workbench.closed:
            self._finish_close()
            return
        self._close_generation = self.controller.generation
        self._close_pending = True
        workbench.retry_close()
        self._set_keep_enabled(True)
        self._poll_workbench_close()

    def cancel_workbench_close(self):
        workbench = getattr(self, "_browser_workbench", None)
        if not getattr(self, "_close_pending", False) or workbench is None:
            return
        if not workbench.cancel_close():
            self.status_var.set(
                "The listener is already stopping. Wait for its result."
            )
            return
        self._close_pending = False
        if self._close_poll_id is not None:
            self.root.after_cancel(self._close_poll_id)
            self._close_poll_id = None
        self._set_keep_enabled(False)
        self.status_var.set(
            "Close cancelled. Both views and native inputs remain open."
        )

    def _poll_workbench_close(self):
        self._close_poll_id = None
        if self.closed or not getattr(self, "_close_pending", False):
            return
        workbench = self._browser_workbench
        state = workbench.poll_close()
        if state == "closed":
            self._close_pending = False
            self._set_keep_enabled(False)
            if self.controller.generation != self._close_generation:
                self.status_var.set(
                    "Native inputs changed while waiting. The browser service stopped; "
                    "your runtime and inputs remain open. Save or close explicitly."
                )
                return
            self._finish_close()
        elif state in {"refused", "failed"}:
            self._close_pending = False
            self._set_keep_enabled(False)
            self.status_var.set(
                "Close refused: local requests or listener cleanup did not finish. "
                "Your native runtime and inputs remain open. Check saved work, then "
                "close again explicitly; no request was replayed."
            )
        else:
            self._set_keep_enabled(workbench.phase == "draining")
            self.status_var.set(
                "Finishing local requests or listener cleanup. Keep this window open; "
                "you can keep it open while requests are still running."
            )
            self._close_poll_id = self.root.after(50, self._poll_workbench_close)

    def _finish_close(self):
        if self.closed:
            return
        root_available = self._root_available()
        self.closed = True
        self._signal_close_pending = False
        for field in (
            "_signal_close_id",
            "_poll_id",
            "_heartbeat_id",
            "_close_poll_id",
        ):
            identifier = getattr(self, field, None)
            if identifier is not None:
                if root_available:
                    self.root.after_cancel(identifier)
                setattr(self, field, None)
        try:
            funding = getattr(self, "_funding_window", None)
            if funding is not None:
                funding.close()
            self.controller.close()
        finally:
            if root_available:
                self.root.destroy()

    def _root_available(self):
        try:
            exists = getattr(self.root, "winfo_exists", None)
            return (
                bool(exists())
                if exists is not None
                else not getattr(self.root, "destroyed", False)
            )
        except Exception:
            return False

    def _emergency_close(self):
        """No usable Tk loop: bounded drain, or explicit error with runtime retained."""
        workbench = getattr(self, "_browser_workbench", None)
        if workbench is not None and not workbench.closed:
            from .native_browser import WorkbenchCloseRefused

            try:
                workbench.close()
            except WorkbenchCloseRefused as exc:
                raise NativeWindowError(
                    "Tk stopped before local requests or cleanup finished. "
                    "This cleanup did not close the runtime; retained inputs are "
                    "only in process memory. The graphical launcher exits with an "
                    "error, so unsaved inputs and unfinished local requests are not "
                    "guaranteed. No request was replayed. A caller that continues "
                    "must clean up explicitly."
                ) from exc
        self._finish_close()

    def run(self):
        previous = None
        installed = threading.current_thread() is threading.main_thread()
        if installed:
            previous = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, lambda *_: self._request_signal_close())

        def heartbeat():
            self._heartbeat_id = None
            if not self.closed:
                self._poll_browser_quit()
                if not self.closed:
                    self._heartbeat_id = self.root.after(200, heartbeat)

        result = 0
        try:
            try:
                heartbeat()
            except BaseException:
                self._emergency_close()
                raise
            while not self.closed:
                try:
                    self.root.mainloop()
                except KeyboardInterrupt:
                    result = 130
                except BaseException:
                    self._emergency_close()
                    raise
                if not self.closed:
                    if self._root_available():
                        # A quit/early mainloop return must not bypass request drain.
                        self.close()
                    else:
                        self._emergency_close()
            return result
        finally:
            if installed:
                signal.signal(signal.SIGTERM, previous)


def run_native(directory=None) -> int:
    return NativeWindow(directory).run()
