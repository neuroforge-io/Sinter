"""Local SQLite reports and restart-safe search watches.

Network calls happen outside transactions. Claims use expiring leases and
compare-and-set completion. A missing search result is never labelled closed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import client
from .evidence import text
from .grants import confirmed_deadline


def data_directory() -> Path:
    return Path(os.environ.get("SINTER_DATA_DIR", str(Path.home() / ".sinter")))


class Store:
    def __init__(self, directory: Path | str | None = None):
        self.directory = Path(directory) if directory is not None else data_directory()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / "workspace.sqlite3"
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise ValueError("This workspace needs a newer Sinter. Back it up before upgrading.")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at REAL NOT NULL, document TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS watches (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, query TEXT NOT NULL,
                    interval INTEGER NOT NULL, next_run REAL NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1, last_run REAL,
                    lease_until REAL NOT NULL DEFAULT 0, lease_token TEXT NOT NULL DEFAULT '',
                    results TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
                    failures INTEGER NOT NULL DEFAULT 0, deadline TEXT NOT NULL DEFAULT ''
                );
                PRAGMA user_version=1;
            """)
        if os.name != "nt":
            self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_report(self, report: dict) -> str:
        if not isinstance(report, dict) or not isinstance(report.get("markdown"), str):
            raise ValueError("Only completed reports can be saved.")
        title = text(report.get("title", ""), "Report title", 200, True)
        document = json.dumps(report, ensure_ascii=False, allow_nan=False)
        if len(document.encode("utf-8")) > 2_000_000:
            raise ValueError("This report exceeds the 2 MB workspace limit.")
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM reports").fetchone()[0] >= 200:
                raise ValueError("The workspace has 200 reports. Export and remove old reports before saving more.")
            db.execute("INSERT INTO reports VALUES (?, ?, ?, ?)", (identifier, title, time.time(), document))
        return identifier

    def reports(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id, title, created_at FROM reports ORDER BY created_at DESC")]

    def report(self, identifier: str) -> dict:
        text(identifier, "Report ID", 100, True)
        with self.connect() as db:
            row = db.execute("SELECT document FROM reports WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError("Report not found.")
        return json.loads(row[0])

    def delete_report(self, identifier: str) -> None:
        text(identifier, "Report ID", 100, True)
        with self.connect() as db:
            db.execute("DELETE FROM reports WHERE id=?", (identifier,))

    def add_watch(self, title: str, query: str, interval: int, deadline: str = "") -> str:
        text(title, "Watch name", 200, True)
        text(query, "Search query", 1024, True)
        text(deadline, "Deadline", 10)
        if type(interval) is not int or interval not in {3600, 86400, 604800}:
            raise ValueError("Choose hourly, daily or weekly checking.")
        if deadline:
            confirmed_deadline(deadline)
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM watches").fetchone()[0] >= 32:
                raise ValueError("At most 32 watches are allowed. Remove an unused watch first.")
            db.execute("INSERT INTO watches (id,title,query,interval,next_run,deadline) VALUES (?,?,?,?,?,?)",
                       (identifier, title, query, interval, time.time(), deadline))
        return identifier

    def watches(self) -> list[dict]:
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM watches ORDER BY title")]
        for row in rows:
            row["results"] = json.loads(row["results"])
            row.pop("lease_token", None)
        return rows

    def change_watch(self, identifier: str, enabled: bool) -> None:
        text(identifier, "Watch ID", 100, True)
        if type(enabled) is not bool:
            raise ValueError("Watch enabled must be true or false.")
        with self.connect() as db:
            db.execute("UPDATE watches SET enabled=?, lease_token='', lease_until=0 WHERE id=?", (int(enabled), identifier))

    def delete_watch(self, identifier: str) -> None:
        text(identifier, "Watch ID", 100, True)
        with self.connect() as db:
            db.execute("DELETE FROM watches WHERE id=?", (identifier,))

    def claim(self, now: float) -> dict | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM watches WHERE enabled=1 AND next_run<=? AND lease_until<=? "
                             "ORDER BY next_run LIMIT 1", (now, now)).fetchone()
            if row is None:
                return None
            result = dict(row)
            token = uuid.uuid4().hex
            db.execute("UPDATE watches SET lease_token=?, lease_until=? WHERE id=?", (token, now + 300, row["id"]))
            result["lease_token"] = token
            return result

    def run_due(self, now: float | None = None, search_fn=None, limit: int = 3) -> int:
        search_fn = search_fn or client.search
        checked = 0
        for _ in range(limit):
            moment = time.time() if now is None else now
            watch = self.claim(moment)
            if watch is None:
                break
            token = watch["lease_token"]
            try:
                response = search_fn(watch["query"])
                old = json.loads(watch["results"]).get("items", [])
                items = [{"title": item.title, "url": item.url, "content": item.content,
                          "sha256": hashlib.sha256((item.title + "\0" + item.content).encode()).hexdigest()}
                         for item in response.results[:30]]
                before = {item["url"]: item["sha256"] for item in old}
                after = {item["url"]: item["sha256"] for item in items}
                results = {"retrieved_at": response.retrieved_at, "items": items,
                           "new": [url for url in after if url not in before],
                           "changed": [url for url in after if url in before and after[url] != before[url]],
                           "not_returned": [url for url in before if url not in after],
                           "notice": "Search excerpts only. Not returned does not mean closed or withdrawn."}
                with self.connect() as db:
                    db.execute("UPDATE watches SET results=?, last_run=?, next_run=?, failures=0, error='', "
                               "lease_token='', lease_until=0 WHERE id=? AND lease_token=?",
                               (json.dumps(results), moment, moment + watch["interval"], watch["id"], token))
            except (client.APIError, ValueError, OSError):
                delay = min(300 * (2 ** min(watch["failures"], 6)), 21600)
                with self.connect() as db:
                    db.execute("UPDATE watches SET error=?, failures=failures+1, next_run=?, "
                               "lease_token='', lease_until=0 WHERE id=? AND lease_token=?",
                               ("Search failed. Previous results are retained; a bounded retry is scheduled.",
                                moment + delay, watch["id"], token))
            checked += 1
        return checked


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\r", "").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _fold(line: str) -> str:
    chunks, current = [], ""
    for character in line:
        if len((current + character).encode("utf-8")) > 75:
            chunks.append(current)
            current = " "
        current += character
    chunks.append(current)
    return "\r\n".join(chunks)


def calendar(watches: list[dict]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Sinter//Community Workbench//EN", "CALSCALE:GREGORIAN"]
    for item in watches:
        if not item["enabled"]:
            continue
        frequency = {3600: "HOURLY", 86400: "DAILY", 604800: "WEEKLY"}[item["interval"]]
        start = datetime.fromtimestamp(item["next_run"], timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines += ["BEGIN:VEVENT", f"UID:{item['id']}@sinter.local", f"DTSTAMP:{stamp}", f"DTSTART:{start}",
                  f"RRULE:FREQ={frequency}", "SUMMARY:" + _ics_escape("Review search: " + item["title"]),
                  "DESCRIPTION:" + _ics_escape("Open Sinter to check this watch. Searches run only while Sinter is running. Query: " + item["query"]), "END:VEVENT"]
        if item.get("deadline"):
            deadline = date.fromisoformat(confirmed_deadline(item["deadline"]))
            lines += ["BEGIN:VEVENT", f"UID:{item['id']}-deadline@sinter.local", f"DTSTAMP:{stamp}",
                      "DTSTART;VALUE=DATE:" + deadline.strftime("%Y%m%d"),
                      "DTEND;VALUE=DATE:" + (deadline + timedelta(days=1)).strftime("%Y%m%d"),
                      "SUMMARY:" + _ics_escape("Check confirmed deadline: " + item["title"]),
                      "DESCRIPTION:Date entered by a person. Confirm closing time and time zone with the funder.", "END:VEVENT"]
    return "\r\n".join(_fold(line) for line in lines + ["END:VCALENDAR"]) + "\r\n"
