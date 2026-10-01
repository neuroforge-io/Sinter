"""A scoped portable desktop workspace over the application's shared operations.

Tk displays untrusted source text as text. It does not host web pages, open a
socket, run a watch scheduler or invent a separate model/source implementation.
The full web workbench remains a separate, explicit presentation choice.
"""

from __future__ import annotations

import copy
import json
import os
import signal
import stat
import threading
from pathlib import Path

from .outputs import atomic_write_text
from .presentation import result_markdown

TEXT_BYTES = 800_000
PROJECT_BYTES = 10_000_000


class NativeWindowError(RuntimeError):
    """The native presentation cannot start in this environment."""


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
        self.active_job = None
        self._job_generation = None
        self._job_kind = None
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
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x")
        self._button(toolbar, "New project", self.new_project)
        self._button(toolbar, "Fictional example", self.example)
        self._button(toolbar, "Restore project JSON…", self.import_project)
        self._button(toolbar, "Export project JSON…", self.export_project)
        self._button(toolbar, "Refresh saved work", self._refresh)
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
        self.status_page = ttk.Frame(self.pages, padding=12)
        for page, name in (
            (self.source_page, "Sources"),
            (self.report_page, "Evidence & reports"),
            (self.answer_page, "Short AI answer"),
            (self.status_page, "Status & scope"),
        ):
            self.pages.add(page, text=name)
        self.title_var = tk.StringVar(value="")
        self.format_var = tk.StringVar(value="brief")
        header = ttk.Frame(self.source_page)
        header.pack(fill="x")
        ttk.Label(header, text="Project title").pack(side="left")
        ttk.Entry(header, textvariable=self.title_var).pack(
            side="left", fill="x", expand=True, padx=8
        )
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
        ttk.Entry(self.source_page, textvariable=self.source_title_var).pack(
            fill="x", pady=4
        )
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
        self._button(
            self.report_page,
            "Use selected excerpt for one question",
            self.use_excerpt,
            inline=False,
        )
        report_tabs = ttk.Notebook(self.report_page)
        report_tabs.pack(fill="both", expand=True)
        readable, exact = ttk.Frame(report_tabs), ttk.Frame(report_tabs)
        report_tabs.add(readable, text="Readable report")
        report_tabs.add(exact, text="Exact JSON / provenance")
        self.report_text = self._text(readable, readonly=True)
        self.report_json = self._text(exact, readonly=True)
        ttk.Label(
            self.answer_page,
            text="Optional short draft. A selected excerpt "
            "is not a complete-source review. "
            "Model output and citation IDs do not establish factual support.",
            wraplength=800,
        ).pack(anchor="w")
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
            text="I approve sending exactly this preview to the displayed provider "
            "and will review the draft.",
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
                tree.insert("", "end", iid=row["id"], text=row["title"])
        state = self.controller.runtime.call("runtime.status")
        self._put(
            self.status_text,
            "Native workspace scope\n\n"
            "Sources, saved projects, source-only evidence/gaps, "
            "short approved source answers, and JSON/Markdown exports "
            "use the same Sinter runtime as the web UI and CLI.\n\n"
            "The full browser workbench provides the remaining campaign, "
            "recording and rich-document screens. This window does not run "
            "scheduled watches, configure accounts or handle credentials.\n\n"
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
            if isinstance(state.get("result"), dict):
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
            "Source-only selected evidence; "
            "every related match needs human interpretation."
            if current and not self.controller.result.get("results")
            else "Historical or model output. It is retained unchanged; "
            "check the displayed source snapshot and every claim."
        )

    def _paint_result(self):
        value = self.controller.result
        self._put(self.report_text, result_markdown(value), readonly=True)
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
        self._report_scope()
        self.pages.select(self.report_page)

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

    def request_close(self):
        if self.controller.dirty:
            answer = self.messages.askyesnocancel(
                "Unsaved source edits",
                "Save this project locally before closing?",
                parent=self.root,
            )
            if answer is None:
                return
            if answer:
                try:
                    self.save_project()
                except Exception as exc:
                    self.messages.showerror(
                        "Sinter — keep your edits", str(exc), parent=self.root
                    )
                    return
        self.close()

    def close(self):
        if not self.closed:
            self.closed = True
            if self._poll_id is not None:
                self.root.after_cancel(self._poll_id)
                self._poll_id = None
            if self._heartbeat_id is not None:
                self.root.after_cancel(self._heartbeat_id)
                self._heartbeat_id = None
            try:
                self.controller.close()
            finally:
                self.root.destroy()

    def run(self):
        previous = None
        installed = threading.current_thread() is threading.main_thread()
        if installed:
            previous = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, lambda *_: self.close())

        def heartbeat():
            self._heartbeat_id = None
            if not self.closed:
                self._heartbeat_id = self.root.after(200, heartbeat)

        try:
            heartbeat()
            self.root.mainloop()
            return 0
        except KeyboardInterrupt:
            return 130
        finally:
            self.close()
            if installed:
                signal.signal(signal.SIGTERM, previous)


def run_native(directory=None) -> int:
    return NativeWindow(directory).run()
