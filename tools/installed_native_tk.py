"""Bounded UI-only driver for one owned installed Tk window on private Xvfb.

Run this as a separate time-limited child. It uses authenticated Tk send on the
owner's isolated display, never a physical desktop or an application test hook.
The fixed fictional fields are entered through widgets, saved with the actual
button, and closed through the registered window-manager action.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURE = {
    "schema": "sinter-casebook/v1",
    "title": "Fictional installed native menu — {literal}; [no execution] 🐝",
    "questions": "Who approved the fictional lantern?\nIs the date confirmed?",
    "document_type": "brief",
    "documents": [
        {
            "title": "Fictional native original — é",
            "content": "Approval remains unknown.\nFictional price AUD 110 including GST.\nLiteral {braces}; [no command] 🐝 — é.",
            "url": "",
            "date": "",
        }
    ],
}
MAX_WIDGETS = 256


class Driver:
    def __init__(self, root, windows, pid):
        self.root, self.tk = root, root.tk
        own = str(self.tk.call("tk", "appname"))
        matches = []
        peers = self.tk.splitlist(self.tk.call("winfo", "interps"))
        if len(peers) != 2:
            raise ValueError(
                "Use a fresh isolated display with only driver and target."
            )
        for peer in peers:
            if str(peer) == own:
                continue
            self.peer = str(peer)
            client = int(str(self.send("winfo", "id", ".")), 16)
            from tools.native_window_smoke import X11Observer

            observer = X11Observer(os.environ["DISPLAY"])
            try:
                root_id, parent, count = (
                    ctypes.c_ulong(),
                    ctypes.c_ulong(),
                    ctypes.c_uint(),
                )
                children = ctypes.POINTER(ctypes.c_ulong)()
                if not observer.x.XQueryTree(
                    observer.display,
                    client,
                    ctypes.byref(root_id),
                    ctypes.byref(parent),
                    ctypes.byref(children),
                    ctypes.byref(count),
                ):
                    raise ValueError("Cannot bind Tk client to its mapped X parent.")
                if children:
                    observer.x.XFree(children)
                frame = hex(parent.value)
                owned = {
                    int(w["window_id"], 16)
                    for w in observer.windows(pid, mapped_only=True)
                }
                if parent.value in windows and parent.value in owned:
                    matches.append((self.peer, frame))
            finally:
                observer.close()
        if len(matches) != 1:
            raise ValueError("Tk peer does not match the process-owned mapped window.")
        self.peer, self.frame = matches[0]

    def send(self, *arguments):
        # Tcl list construction keeps literal braces, brackets and semicolons
        # inside individual arguments. No eval or Python application hook.
        script = self.tk.call("list", *arguments)
        return self.tk.call("send", "--", self.peer, script)

    def children(self, path):
        return list(self.tk.splitlist(self.send("winfo", "children", path)))

    def widgets(self, path="."):
        result, pending = [], [path]
        while pending:
            path = pending.pop(0)
            if path in result or len(result) >= MAX_WIDGETS:
                raise ValueError("Native widget tree is repeated or too large.")
            result.append(path)
            pending.extend(self.children(path))
        return result

    def kind(self, path):
        return str(self.send("winfo", "class", path))

    def unique(self, paths, predicate, name):
        matches = [path for path in paths if predicate(path)]
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous native control: " + name)
        return matches[0]

    def labelled(self, name, kind="TLabel"):
        return self.unique(
            self.widgets(),
            lambda p: (
                self.kind(p) == kind and str(self.send(p, "cget", "-text")) == name
            ),
            name,
        )

    def button(self, name):
        path = self.labelled(name, "TButton")
        if "disabled" in self.tk.splitlist(self.send(path, "state")):
            raise ValueError("The native control is disabled: " + name)
        return path

    def fields(self):
        label = self.labelled("Project title")
        header = str(self.send("winfo", "parent", label))
        page = str(self.send("winfo", "parent", header))
        title = self.unique(
            self.children(header), lambda p: self.kind(p) == "TEntry", "project title"
        )
        texts = [p for p in self.widgets(page) if self.kind(p) == "Text"]
        if len(texts) != 2:
            raise ValueError("The source page must have exactly two editable texts.")
        source_label = self.unique(
            self.widgets(page),
            lambda p: (
                self.kind(p) == "TLabel"
                and str(self.send(p, "cget", "-text")) == "Selected source title"
            ),
            "selected source title",
        )
        siblings = self.children(page)
        index = siblings.index(source_label)
        source_title = siblings[index + 1]
        if self.kind(source_title) != "TEntry":
            raise ValueError("The source title entry is not adjacent to its label.")
        source_tree = self.unique(
            self.children(page), lambda p: self.kind(p) == "Treeview", "source tree"
        )
        if (
            str(self.send(source_tree, "heading", "#0", "-text"))
            != "Admitted sources — select to inspect or edit"
        ):
            raise ValueError("Unexpected source tree identity.")
        return title, texts[0], source_title, texts[1], source_tree

    def select_source(self, tree):
        items = self.tk.splitlist(self.send(tree, "children", ""))
        if len(items) != 1:
            raise ValueError("The fictional project must contain one source.")
        self.send(tree, "selection", "set", items[0])
        self.send("event", "generate", tree, "<<TreeviewSelect>>")
        self.send("update")

    def replace(self, path, value, *, text=False):
        self.send(path, "delete", "1.0" if text else 0, "end")
        self.send(path, "insert", "1.0" if text else 0, value)
        if text:
            self.send("event", "generate", path, "<<Modified>>")
        self.send("update")

    def saved_tree(self):
        button = self.button("Open project")
        parent = str(self.send("winfo", "parent", button))
        return self.unique(
            self.children(parent),
            lambda p: self.kind(p) == "Treeview",
            "saved projects",
        )

    def project_id(self):
        tree = self.saved_tree()
        items = self.tk.splitlist(self.send(tree, "children", ""))
        if (
            len(items) != 1
            or str(self.send(tree, "item", items[0], "-text")) != FIXTURE["title"]
        ):
            raise ValueError(
                "The saved catalogue must contain the exact fictional title."
            )
        identifier = str(items[0])
        if not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise ValueError("The saved project identity is malformed.")
        return identifier

    def run(self, phase):
        if type(phase) is not str or phase not in {"create", "reopen"}:
            raise ValueError("Use a fixed native UI phase.")
        if phase == "create":
            self.send(self.button("Fictional example"), "invoke")
            self.send("update")
        else:
            identifier = self.project_id()
            tree = self.saved_tree()
            self.send(tree, "selection", "set", identifier)
            self.send(self.button("Open project"), "invoke")
            self.send("update")
        title, questions, source_title, source_text, tree = self.fields()
        self.select_source(tree)
        if phase == "create":
            self.replace(title, FIXTURE["title"])
            self.replace(questions, FIXTURE["questions"], text=True)
            self.replace(source_title, FIXTURE["documents"][0]["title"])
            self.replace(source_text, FIXTURE["documents"][0]["content"], text=True)
            self.send(self.button("Save project locally"), "invoke")
            self.send("update")
            self.select_source(tree)
        expected = (
            FIXTURE["title"],
            FIXTURE["questions"],
            FIXTURE["documents"][0]["title"],
            FIXTURE["documents"][0]["content"],
        )
        actual = (
            str(self.send(title, "get")),
            str(self.send(questions, "get", "1.0", "end-1c")),
            str(self.send(source_title, "get")),
            str(self.send(source_text, "get", "1.0", "end-1c")),
        )
        if actual != expected:
            raise ValueError(
                "The actual Tk field values differ from the literal fixture."
            )
        identifier = self.project_id()
        protocol = str(self.send("wm", "protocol", ".", "WM_DELETE_WINDOW"))
        if not re.fullmatch(r"[0-9]+request_close", protocol):
            raise ValueError("The native window-manager close action is unavailable.")
        self.send(protocol)
        return {
            "schema": "sinter-installed-native-tk-action/v1",
            "phase": phase,
            "project_id": identifier,
            "window_id": self.frame,
            "fields_exact": True,
            "save_button_invoked": phase == "create",
            "wm_close_invoked": True,
        }


def admit_request(request):
    if (
        type(request) is not dict
        or set(request) != {"phase", "window_ids", "pid"}
        or type(request["pid"]) is not int
        or request["pid"] <= 0
        or type(request["phase"]) is not str
        or request["phase"] not in {"create", "reopen"}
        or type(request["window_ids"]) is not list
        or not 0 < len(request["window_ids"]) < 5
        or any(
            type(w) is not str or not re.fullmatch(r"0x[0-9a-f]+", w)
            for w in request["window_ids"]
        )
    ):
        raise ValueError(
            "Use a bounded fixed phase and process-owned X window identities."
        )
    return request


def admit_environment(request_path):
    """A standalone driver must never attach to a customer display."""
    display = os.environ.get("DISPLAY", "")
    authority = Path(os.environ.get("XAUTHORITY", ""))
    if (
        not Path("/.dockerenv").is_file()
        or {p.name for p in Path("/sys/class/net").iterdir()} != {"lo"}
        or not re.fullmatch(r":[0-9]+(?:\.[0-9]+)?", display)
        or authority.parent.resolve() != request_path.parent.resolve()
    ):
        raise ValueError(
            "Use only the owning network-none container and private authorized display."
        )
    info = authority.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_uid != os.geteuid()
    ):
        raise ValueError(
            "X authorization must be a private regular file owned by this driver."
        )
    info = request_path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_size > 8192
    ):
        raise ValueError("Use the bounded request file owned by this driver.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    admit_environment(args.request)
    request = admit_request(json.loads(args.request.read_text(encoding="utf-8")))
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        result = Driver(
            root, {int(w, 16) for w in request["window_ids"]}, request["pid"]
        ).run(request["phase"])
        print(json.dumps(result, ensure_ascii=False))
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
