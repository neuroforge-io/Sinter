"""Isolated fictional seed worker; use the identity-verifying outer producer.

This worker uses source Python only. It never executes an installer, launches a
browser, starts a scheduler, accesses an account or requests a model response.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import shutil
import socket
import sqlite3
import sys
import threading
import time
from pathlib import Path

SCHEMA = "sinter-casebook/v2"
VERSION = "0.5.4rc3"
MAX_RESPONSE = 2 * 1024 * 1024


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def same_json(first, second):
    """Conserve JSON value types as well as values (True is not integer 1)."""
    return encoded(first) == encoded(second)


def sqlite_snapshot(path):
    """Read persistent live-file metadata and typed rows without runtime repair."""
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        tables = {}
        for name, sql in db.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ):
            # Names come from the fixture's admitted SQLite schema, not input SQL.
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [
                row[1] for row in db.execute("PRAGMA table_info(" + quoted + ")")
            ]
            rows = [list(row) for row in db.execute("SELECT * FROM " + quoted)]
            tables[name] = {
                "sql": sql,
                "columns": columns,
                "rows": sorted(rows, key=encoded),
            }
        return {
            "metadata": {
                name: db.execute("PRAGMA " + name).fetchone()[0]
                for name in ("user_version", "application_id", "encoding", "page_size")
            },
            "tables": tables,
        }


def workspace_snapshot(directory):
    preferences = (directory / "preferences.json").read_bytes()
    return {
        "preferences_sha256": hashlib.sha256(preferences).hexdigest(),
        "preferences": json.loads(preferences),
        "databases": {
            name: sqlite_snapshot(directory / name)
            for name in ("workspace.sqlite3", "campaigns.sqlite3")
        },
    }


def source_protocol_checks(directory, v1, v2, app_class, server_class, allowed_ports):
    """Actual owned loopback only; capabilities are selected per request."""
    app = app_class(directory)
    server = server_class(("127.0.0.1", 0), app)
    allowed_ports.add(server.server_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    before = workspace_snapshot(directory)
    checks = {}
    thread.start()

    def request(path, body=None, *, capability=False):
        headers = {"X-Sinter-Token": app.token}
        if capability:
            headers["X-Sinter-Casebook-Schema"] = SCHEMA
        data = None
        if body is not None:
            data = encoded(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=5
        )
        try:
            connection.request(
                "POST" if body is not None else "GET", path, data, headers
            )
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise ValueError("Fixture protocol response exceeds its bound.")
            return response.status, json.loads(raw)
        finally:
            connection.close()

    def expect(name, path, body=None, *, capability=False, status=200, expected=None):
        actual, value = request(path, body, capability=capability)
        if actual != status or (
            expected is not None and not same_json(value, expected)
        ):
            raise AssertionError(f"Source protocol check failed: {name}")
        if status == 400 and not isinstance(value.get("error"), str):
            raise AssertionError(f"Refusal lacks its explanation: {name}")
        checks[name] = {"status": actual, "capability_present": capability}
        return value

    try:
        expect("v1_read_without_capability", "/api/casebooks/" + v1["id"], expected=v1)
        expect(
            "v2_read_without_capability_refused",
            "/api/casebooks/" + v2["id"],
            status=400,
        )
        expect(
            "v2_read_with_capability",
            "/api/casebooks/" + v2["id"],
            capability=True,
            expected=v2,
        )
        validate_body = {"document": v2["document"]}
        expect(
            "v2_backup_without_capability_refused",
            "/api/casebooks/validate",
            validate_body,
            status=400,
        )
        expect(
            "v2_backup_with_capability",
            "/api/casebooks/validate",
            validate_body,
            capability=True,
            expected=validate_body,
        )
        broad = {
            key: value
            for key, value in v2["document"].items()
            if key not in {"question_scopes", "fingerprint"}
        }
        broad["schema"] = "sinter-casebook/v1"
        save_body = {"id": v2["id"], "revision": v2["revision"], "document": broad}
        expect(
            "older_reader_resave_refused", "/api/casebooks/save", save_body, status=400
        )
        jobs_before = len(app.jobs.list())
        work = {"id": v2["id"], "revision": v2["revision"]}
        expect(
            "v2_build_without_capability_refused",
            "/api/casebooks/build",
            work,
            status=400,
        )
        expect(
            "v2_draft_without_capability_refused",
            "/api/casebooks/draft",
            work,
            status=400,
        )
        expect(
            "v2_draft_without_consent_refused",
            "/api/casebooks/draft",
            work,
            capability=True,
            status=400,
        )
        if len(app.jobs.list()) != jobs_before:
            raise AssertionError("Refused source requests queued work.")
        checks["refusals_queued_no_work"] = True
        queued = expect(
            "v2_source_build_with_capability",
            "/api/casebooks/build",
            work,
            capability=True,
            status=202,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            job = app.jobs.get(queued["id"])
            if job["status"] in {"done", "failed", "cancelled"}:
                break
            time.sleep(0.01)
        else:
            raise AssertionError(
                "Fixture source report did not finish within ten seconds."
            )
        if job["status"] != "done":
            raise AssertionError("Fixture source report failed.")
        questions = job["result"]["question_index"]
        if (
            questions[0]["source_scope"]["source_ids"]
            != v2["document"]["question_scopes"][0]["source_ids"]
            or questions[1]["source_scope"]["source_ids"] != []
            or questions[1]["excerpt_ids"] != []
            or questions[2]["source_scope"]["mode"] != "all"
        ):
            raise AssertionError(
                "Source-only report changed explicit question choices."
            )
        checks["selected_empty_and_default_all_choices_preserved"] = True
        expect(
            "v2_read_after_refusals_and_build",
            "/api/casebooks/" + v2["id"],
            capability=True,
            expected=v2,
        )
        if not same_json(before, workspace_snapshot(directory)):
            raise AssertionError("Protocol checks changed persistent work or settings.")
        checks["persistent_originals_and_settings_unchanged"] = True
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        app.close()
        allowed_ports.discard(server.server_port)
        if thread.is_alive():
            raise AssertionError("Fixture listener did not stop.")
    checks["owned_listener_closed"] = True
    return checks


def seed(source, directory, output):
    """Import solely the supplied prior source after outer immutable admission."""
    source = source.resolve()
    sys.path.insert(0, str(source / "src"))
    from sinter import __version__, casebooks, client
    from sinter.campaigns import CampaignStore
    from sinter.preferences import Preferences
    from sinter.runtime import Application
    from sinter.server import LocalServer
    from sinter.store import Store

    if __version__ != VERSION:
        raise ValueError("Fixture source is not the published RC3 version.")
    for name, module in list(sys.modules.items()):
        if name == "sinter" or name.startswith("sinter."):
            location = getattr(module, "__file__", None)
            if not location or not Path(location).resolve().is_relative_to(
                source / "src"
            ):
                raise ValueError(
                    "The seed imported Sinter outside the verified prior source."
                )
    provider_calls = []
    external_calls = []
    connect = socket.socket.connect
    allowed_ports = set()

    def local_connect(sock, address):
        if (
            not isinstance(address, tuple)
            or address[0] != "127.0.0.1"
            or address[1] not in allowed_ports
        ):
            external_calls.append(str(address))
            raise AssertionError(
                "Fixture seeding allows only its owned loopback requests."
            )
        return connect(sock, address)

    def refuse_provider(*args, **kwargs):
        provider_calls.append(True)
        raise AssertionError("Fixture preparation must not request a provider.")

    socket.socket.connect = local_connect
    client.chat = refuse_provider
    client._open = refuse_provider
    directory.mkdir(mode=0o700)
    store = Store(directory)
    preferences = Preferences(directory)
    preferences.update(
        {
            "theme": "light",
            "text_size": "large",
            "density": "compact",
            "reduce_motion": True,
            "provider": "openai-compatible",
            "api_url": "https://example.invalid/v1",
            "model": "fictional-upgrade-model",
            "max_tokens": 512,
            "full_name": "Morgan Example",
            "organisation": "Fictional Garden Group",
            "email": "morgan@example.invalid",
            "location": "Fictional Riverbank",
        },
        confirm_endpoint=True,
    )
    payload = {
        "title": "Fictional E garden record",
        "questions": (
            "Is the venue confirmed?\nWho owns water approval?\n"
            "What funding conditions remain?"
        ),
        "document_type": "handover",
        "handover_evidence": "selected_appendix",
        "documents": [
            {
                "title": "Fictional current venue note",
                "date": "2026-09-29",
                "url": "https://example.invalid/current-venue",
                "content": (
                    "The garden venue is NOT confirmed. Water approval is unknown. 🐝"
                ),
            },
            {
                "title": "Fictional historical venue note",
                "date": "2025-09-12",
                "url": "https://example.invalid/historical-venue",
                "content": (
                    "Last year's garden venue was confirmed; "
                    "this is historical, not current permission."
                ),
            },
            {
                "title": "Fictional undated owner note",
                "date": "",
                "url": "",
                "content": (
                    "Water approval owner is unassigned. "
                    "A suggested volunteer has not accepted."
                ),
            },
        ],
    }
    books = casebooks.Casebooks(store)
    plain = books.save({**payload, "title": "Fictional plain v1 garden record"})
    historical = books.save(payload)
    old_report = casebooks.build(historical["document"])
    old_report["document_edits"] = {
        "markdown": (
            "# Human reviewed garden enquiry\n\n"
            "Venue permission remains unknown. e\u0301 🐝"
        ),
        "edited_at": "2026-09-29T12:00:00Z",
        "author": "user",
    }
    old_report_id = store.save_report(old_report)
    scoped = books.save(
        {
            **historical["document"],
            "schema": SCHEMA,
            "question_scopes": [
                {
                    "question_index": 0,
                    "question": payload["questions"].splitlines()[0],
                    "source_ids": [historical["document"]["documents"][0]["id"]],
                },
                {
                    "question_index": 1,
                    "question": payload["questions"].splitlines()[1],
                    "source_ids": [],
                },
            ],
        },
        historical["id"],
        historical["revision"],
    )
    current_report = casebooks.build(scoped["document"])
    current_report_id = store.save_report(current_report)
    campaign = CampaignStore(directory).save(
        {
            "title": "Fictional E funding campaign",
            "organisation": "Fictional Garden Group",
            "objective": "Check original rules and permissions before any application.",
            "opportunities": [
                {
                    "name": "Fictional Garden Fund",
                    "status": "clarification",
                    "ceiling": "200.00",
                }
            ],
            "sources": [
                {
                    "id": "a" * 32,
                    "title": "Fictional changed funding page",
                    "url": "https://example.invalid/current-round",
                    "checked_at": "2026-09-29",
                    "notes": "Retained earlier check differs from the current source.",
                }
            ],
            "requirements": [
                {
                    "opportunity": "Fictional Garden Fund",
                    "rule": "Venue permission",
                    "status": "met",
                    "evidence": "Retained user mark; current permission not received.",
                    "source_id": "a" * 32,
                    "source_url": "https://example.invalid/earlier-round",
                    "source_quote": (
                        "Venue permission must be obtained before applying."
                    ),
                    "checked_at": "2026-09-12",
                }
            ],
            "actions": [
                {
                    "task": "Request venue permission",
                    "owner": "Morgan Example",
                    "owner_kind": "unknown",
                    "owner_confirmed": False,
                    "due": "2026-10-09",
                    "status": "open",
                },
                {
                    "task": "Check water approval",
                    "owner": "",
                    "owner_kind": "unassigned",
                    "owner_confirmed": False,
                    "due": "",
                    "status": "open",
                },
            ],
            "answers": [
                {
                    "opportunity": "Fictional Garden Fund",
                    "label": "Is permission confirmed?",
                    "text": "No current permission received.",
                    "status": "reviewed",
                }
            ],
            "budget": [
                {
                    "item": "Fictional inc GST quote",
                    "opportunity": "Fictional Garden Fund",
                    "quantity": 1,
                    "unit_cost": "110.00",
                    "quote_reference": "Written fictional quote: AUD110 including GST.",
                },
                {
                    "item": "Fictional ex GST quote",
                    "opportunity": "Fictional Garden Fund",
                    "quantity": 1,
                    "unit_cost": "100.00",
                    "quote_reference": "Written fictional quote: AUD100 excluding GST.",
                },
                {
                    "item": "Unknown production cost",
                    "opportunity": "",
                    "quantity": 1,
                    "unit_cost": None,
                    "quote_reference": "",
                },
            ],
        }
    )
    watch_id = store.add_watch(
        "Fictional disabled garden watch", "fictional garden grant", 86400
    )
    store.change_watch(watch_id, False)
    backups = directory / "fixture-backups"
    backups.mkdir()
    for name, document in (
        ("plain-v1", plain["document"]),
        ("historical-v1", historical["document"]),
        ("scoped-v2", scoped["document"]),
    ):
        (backups / (name + ".json")).write_text(
            encoded(document) + "\n", encoding="utf-8"
        )
    # Historical IDs are separate from the original report JSON. Never inject id.
    with store.connect() as db:
        raw_reports = [
            {"report_id": row["id"], "stored_report": json.loads(row["document"])}
            for row in db.execute("SELECT id,document FROM reports ORDER BY id")
        ]
    original_snapshot = workspace_snapshot(directory)
    protocol_directory = directory.parent / "disposable-source-protocol"
    shutil.copytree(directory, protocol_directory)
    protocol = source_protocol_checks(
        protocol_directory, plain, scoped, Application, LocalServer, allowed_ports
    )
    if (
        provider_calls
        or external_calls
        or not same_json(original_snapshot, workspace_snapshot(directory))
    ):
        raise AssertionError(
            "Fixture originals changed or attempted a provider/external connection."
        )
    expected = {
        "prior_version": __version__,
        "settings": preferences.snapshot(),
        "public_settings": preferences.public(),
        "connection": preferences.connection(),
        "campaign": campaign,
        "plain_casebook": plain,
        "historical_casebook": historical,
        "scoped_casebook": scoped,
        "historical_report_id": old_report_id,
        "scoped_report_id": current_report_id,
        "raw_reports": raw_reports,
        "watch": next(row for row in store.watches() if row["id"] == watch_id),
        "persistent_snapshot": original_snapshot,
        "source_protocol_checks": protocol,
        "provider_calls": len(provider_calls),
        "external_connections": len(external_calls),
    }
    output.write_text(
        json.dumps(expected, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return expected


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 3:
        raise ValueError("Use the identity-verifying published_rc3_fixture producer.")
    seed(*map(Path, arguments))


if __name__ == "__main__":
    main()
