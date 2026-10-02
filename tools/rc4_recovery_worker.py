"""Isolated fictional source worker; no installed or OS-browser qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def snapshot(directory):
    """Observe typed original rows and live persistent metadata before reopen."""
    result = {"databases": {}}
    preferences = (directory / "preferences.json").read_bytes()
    result["preferences_sha256"] = hashlib.sha256(preferences).hexdigest()
    result["preferences"] = json.loads(preferences)
    for name in ("workspace.sqlite3", "campaigns.sqlite3"):
        path = directory / name
        with closing(
            sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        ) as db:
            db.execute("PRAGMA query_only=ON")
            tables = {}
            for table, sql in db.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"
            ):
                quoted = '"' + table.replace('"', '""') + '"'
                columns = [
                    r[1] for r in db.execute("PRAGMA table_info(" + quoted + ")")
                ]
                rows = [list(row) for row in db.execute("SELECT * FROM " + quoted)]
                tables[table] = {
                    "sql": sql,
                    "columns": columns,
                    "rows": sorted(rows, key=canonical),
                }
            result["databases"][name] = {
                "metadata": {
                    key: db.execute("PRAGMA " + key).fetchone()[0]
                    for key in (
                        "user_version",
                        "application_id",
                        "encoding",
                        "page_size",
                    )
                },
                "tables": tables,
            }
    return result


def protected(value):
    """Campaign row changes are deliberate; every other original stays exact."""
    return {
        "preferences_sha256": value["preferences_sha256"],
        "preferences": value["preferences"],
        "workspace": value["databases"]["workspace.sqlite3"],
        "campaign_metadata": value["databases"]["campaigns.sqlite3"]["metadata"],
        "campaign_schema": {
            name: {"sql": table["sql"], "columns": table["columns"]}
            for name, table in value["databases"]["campaigns.sqlite3"]["tables"].items()
        },
    }


def seed(directory):
    from sinter import casebooks
    from sinter.campaigns import CampaignStore
    from sinter.preferences import Preferences
    from sinter.store import Store

    directory.mkdir(mode=0o700)
    store = Store(directory)
    preferences = Preferences(directory)
    preferences.update(
        {
            "api_url": "https://example.invalid/v1",
            "provider": "openai-compatible",
            "model": "fictional-recovery-model",
            "max_tokens": 512,
            "theme": "light",
            "text_size": "large",
            "density": "compact",
            "reduce_motion": True,
            "full_name": "Morgan Example",
            "organisation": "Fictional Garden Group",
            "email": "morgan@example.invalid",
            "location": "Fictional Riverbank",
        },
        confirm_endpoint=True,
    )
    book = casebooks.Casebooks(store).save(
        {
            "title": "Fictional retained recovery history",
            "questions": "Is venue approval confirmed?",
            "documents": [
                {
                    "title": "Fictional original unknown venue",
                    "date": "",
                    "url": "https://example.invalid/venue",
                    "content": (
                        "Venue approval is NOT confirmed. "
                        "Original café e\u0301 🐝 wording."
                    ),
                }
            ],
        }
    )
    report = casebooks.build(book["document"])
    report["document_edits"] = {
        "markdown": "# Applied human wording\n\nApproval remains unknown. e\u0301 🐝",
        "edited_at": "2026-10-02T12:00:00Z",
        "author": "user",
    }
    report_id = store.save_report(report)
    watch_id = store.add_watch(
        "Fictional disabled recovery watch", "fictional garden", 86400
    )
    store.change_watch(watch_id, False)
    CampaignStore(directory)
    for index, name in enumerate(("workspace.sqlite3", "campaigns.sqlite3"), 1):
        with closing(sqlite3.connect(directory / name)) as db, db:
            db.execute("PRAGMA application_id=" + str(12340 + index))
    return {
        "casebook": book,
        "report_id": report_id,
        "original_report": report,
        "settings": preferences.snapshot(),
        "public_settings": preferences.public(),
        "connection": preferences.connection(),
        "snapshot": snapshot(directory),
    }


def main(argv=None, *, after_stop=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--launch-url", type=Path)
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(args.source.resolve() / "src"))
    from sinter import __version__, client, desktop
    from sinter.runtime import Application

    attempts = {"provider": 0, "external": 0}
    ports = set()
    original_connect = socket.socket.connect

    def connect(sock, address):
        if (
            not isinstance(address, tuple)
            or address[0] != "127.0.0.1"
            or address[1] not in ports
        ):
            attempts["external"] += 1
            raise AssertionError(
                "Recovery worker permits only its owned loopback listener."
            )
        return original_connect(sock, address)

    def refused(*args, **kwargs):
        attempts["provider"] += 1
        raise AssertionError("Recovery rehearsal must not call a provider.")

    def opener(url):
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
            raise ValueError("Source launch did not select its own loopback URL.")
        ports.add(parsed.port)
        args.launch_url.write_text(url, encoding="utf-8")
        return True  # Captured, not an OS-visible browser launch.

    socket.socket.connect = connect
    client._open = refused
    client.chat = refused
    desktop.webbrowser.open = opener
    # This source rehearsal deliberately pauses background watch polling.
    # It does not claim an installed scheduler or native-owner transition.
    Application.scheduler = lambda app: app.stop.wait()
    result = None
    readers = None
    try:
        for name, module in list(sys.modules.items()):
            if name == "sinter" or name.startswith("sinter."):
                location = getattr(module, "__file__", None)
                if not location or not Path(location).resolve().is_relative_to(
                    args.source.resolve() / "src"
                ):
                    raise ValueError(
                        "Recovery imported Sinter outside its pinned source."
                    )
        if args.seed_only:
            result = seed(args.data)
        else:
            if args.launch_url is None:
                raise ValueError("The owned source launcher needs a capture path.")
            code = desktop.main(["--mode", "browser", "--directory", str(args.data)])
            if code != 0:
                raise ValueError("Source desktop did not exit normally.")
            if after_stop is not None:
                readers = after_stop(args)
    finally:
        args.control.write_text(
            json.dumps(
                {
                    "version": __version__,
                    "frozen": False,
                    "provider_attempts": attempts["provider"],
                    "external_attempts": attempts["external"],
                    "scheduler_paused": True,
                    "OS_browser_tested": False,
                    "seed": result,
                    **({"reader_checks": readers} if after_stop is not None else {}),
                },
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
