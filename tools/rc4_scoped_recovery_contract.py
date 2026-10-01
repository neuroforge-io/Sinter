"""Closed semantic evidence for scoped source use/recovery, separate from RC3.

A pass is a reproducible fictional source rehearsal, never installed admission.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from tools import rc4_recovery_contract as v1
from tools.installed_menu_browser import browser_notice
from tools.installed_workflow_qualification import json_object, validate_png
from tools.rc4_recovery_worker import canonical

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sinter-rc4-scoped-casebook-source/v1"
RECEIPT = "rc4-scoped-casebook-source.json"
TITLE = "Fictional scoped recovery handover"
QUESTIONS = (
    "Who coordinates volunteer watering?",
    "Is venue permission confirmed?",
    "What is the application closing deadline?",
)
NOTE = (
    "\n\nFictional human partial handover: watering owner unass"
    "igned; venue permission and closing deadline unknown. é"
    " 🐝 No application or enquiry was sent."
)
ACTION = "Ask who can coordinate watering; owner remains unassigned. No enquiry sent."
WARNING = (
    "Explicit source choices use casebook v2. Older previews "
    "cannot show these saved projects and refuse their backup"
    "s. Keep the unchanged workspace or a v2 backup when retu"
    "rning to this preview. Originals and saved history remai"
    "n local."
)
CORE = frozenset(
    {
        "fixture.json",
        "stale-scope.json",
        "stale-scope.png",
        "stale-inputs.png",
        "stale-choice.png",
        "control-import.json",
        "scoped-conflict.json",
        "scoped-conflict.png",
        "conflict-inputs.png",
        "scope-warning.png",
        "handover.docx",
        "handover.png",
        "protocol.json",
        "reopened.json",
        "clipboard-reference.json",
        "manual-reference.json",
        "clipboard.json",
        "manual.json",
        "clipboard.png",
        "manual.png",
        "observations.json",
        "processes.json",
        "seed-control.json",
        "seed.stdout",
        "seed.stderr",
        *(
            f"process/run-{n}.{suffix}"
            for n in range(1, 5)
            for suffix in (
                "json",
                "stdout",
                "stderr",
                "backup.json",
                "input.json",
                "cli-export.json",
                "native-text.txt",
                "reader-before.json",
                *(
                    op + "." + stream
                    for op in (
                        "casebooks-get",
                        "casebooks-validate",
                        "casebooks-build",
                        "export",
                    )
                    for stream in ("stdout", "stderr")
                ),
            )
        ),
    }
)
FIELDS = frozenset(
    {
        "schema",
        "execution",
        "source_base_commit",
        "source_manifest_sha256",
        "source_files_sha256",
        "observed_version",
        "candidate_admitted",
        "installed_tested",
        "native_tested",
        "prior_replacement_tested",
        "release_qualified",
        "source_rehearsal_passed",
        "source_files_conserved",
        "resources",
        "failure",
        "artifacts",
    }
)


def fixture():
    return {
        "schema": "sinter-casebook/v1",
        "title": TITLE,
        "questions": "\n".join(QUESTIONS),
        "document_type": "handover",
        "handover_evidence": "selected_appendix",
        "recipient": "Fictional incoming volunteer",
        "signatory": "",
        "organisation": "Fictional Garden Group",
        "sender_role": "",
        "contact_details": "",
        "documents": [
            {
                "title": "Fictional watering original",
                "date": "",
                "url": "https://example.invalid/watering",
                "content": (
                    "Volunteer watering coordination is discussed. No one agr"
                    "eed to own watering. Owner is unassigned. 🐝 é\n\nFull ori"
                    "ginal tail: no commitment was made."
                ),
            },
            {
                "title": "Fictional venue original",
                "date": "",
                "url": "https://example.invalid/venue",
                "content": (
                    "Venue permission remains unknown. Proposed event date 20"
                    "26-10-09 is unconfirmed and is not an application closin"
                    "g deadline. 🐝\n\nFull original tail: permission not grante"
                    "d."
                ),
            },
            {
                "title": "Fictional funding original",
                "date": "",
                "url": "https://example.invalid/funding",
                "content": (
                    "The application closing deadline is unknown. An equipmen"
                    "t quote is pending; no eligibility or funding amount was"
                    " verified.\n\nFull original tail: no submission occurred."
                ),
            },
        ],
    }


def equal(a, b):
    return canonical(a) == canonical(b)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def seed_projection(value, initial):
    """Exact seeded raw rows must remain; intentional new rows are validated below."""
    projected = copy.deepcopy(value)
    for name, db in projected["databases"].items():
        original = initial["databases"][name]
        require(
            set(db["tables"]) == set(original["tables"]),
            "Original schema inventory changed",
        )
        for table, rows in db["tables"].items():
            prior = original["tables"][table]
            require(
                rows["sql"] == prior["sql"] and rows["columns"] == prior["columns"],
                "Original schema changed",
            )
            identities = {row[0] for row in prior["rows"]}
            rows["rows"] = [row for row in rows["rows"] if row[0] in identities]
    return projected


def wrappers(snapshot, table, database="workspace.sqlite3"):
    value = snapshot["databases"][database]["tables"][table]
    return [
        {
            "id": row[value["columns"].index("id")],
            "revision": row[value["columns"].index("revision")],
            "document": json.loads(row[value["columns"].index("document")]),
        }
        for row in value["rows"]
    ]


def validate_report(report, expected, word_bytes):
    """Preserve exact source evidence, human partial text and the actual Word body."""
    from sinter.casebooks import build
    from sinter.docx_export import export_docx

    regenerated = build(expected, "handover")
    # Creation time is generated. Evidence and original fields stay exact.
    regenerated["created_at"] = report["created_at"]
    regenerated["document_edits"] = report["document_edits"]
    require(
        equal(report, regenerated), "Stored report raw evidence or presentation differs"
    )
    require(
        report["review_status"] == "draft"
        and report["document_edits"]["author"] == "user"
        and report["document_edits"]["markdown"] == report["document_markdown"] + NOTE,
        "Human partial wording or review status changed",
    )

    require(
        set(report["document_edits"]) == {"author", "markdown", "edited_at"},
        "Applied human edit fields differ",
    )
    compiled = export_docx(
        {
            "title": report.get("document_title") or report["title"],
            "markdown": report["document_edits"]["markdown"],
        }
    ).content
    with (
        zipfile.ZipFile(io.BytesIO(word_bytes)) as actual,
        zipfile.ZipFile(io.BytesIO(compiled)) as wanted,
    ):
        require(
            actual.namelist() == wanted.namelist()
            and all(
                actual.read(name) == wanted.read(name) for name in wanted.namelist()
            ),
            "Actual Word parts differ from the applied human wording",
        )


def validate_semantics(data):
    # Source binding is checked by the caller before invoking this source compiler.
    sys.path.insert(0, str(ROOT / "src"))
    from sinter.campaigns import validate as validate_campaign
    from sinter.casebooks import validate

    initial = json_object(data["seed-control.json"])["seed"]["snapshot"]
    observe = json_object(data["observations.json"])
    require(
        set(observe)
        == {
            "phases",
            "stale_scope",
            "conflict",
            "offline",
            "errors",
            "external",
            "dialogs",
            "warnings",
            "scoped",
            "report_id",
            "report",
            "campaign",
            "clipboard_restored",
            "manual_restored",
        },
        "Scoped observation fields differ",
    )
    require(
        observe["errors"] == observe["external"] == observe["dialogs"] == [],
        "Browser emitted an error or outside request",
    )
    require(
        observe["warnings"] == [WARNING],
        "The visible older-reader scope warning differs",
    )
    require(
        equal(json_object(data["fixture.json"]), fixture()),
        "Fictional original fixture differs",
    )
    expected = validate(fixture())
    ids = [row["id"] for row in expected["documents"]]
    expected = validate(
        {
            **expected,
            "schema": "sinter-casebook/v2",
            "question_scopes": [
                {"question_index": 0, "question": QUESTIONS[0], "source_ids": [ids[0]]},
                {"question_index": 1, "question": QUESTIONS[1], "source_ids": []},
            ],
        }
    )
    saved = observe["scoped"]
    require(
        set(saved) == {"id", "revision", "document"}
        and type(saved["revision"]) is int
        and saved["revision"] == 3
        and re.fullmatch(r"[0-9a-f]{32}", saved["id"]),
        "Scoped saved identity differs",
    )
    require(
        equal(saved["document"], expected)
        and equal(
            json_object(data["reopened.json"]),
            {k: v for k, v in expected.items() if k != "fingerprint"},
        ),
        "Selected/empty/all scopes or full original inputs changed",
    )
    stale = observe["stale_scope"]
    require(
        set(stale) == {"working", "stored", "posts", "warning"}
        and type(stale["posts"]) is int
        and stale["posts"] == 0
        and stale["warning"]
        == "Questions changed or moved. Review their source choices before saving.",
        "Stale question source choices were not blocked locally",
    )
    stale_expected = {k: v for k, v in expected.items() if k != "fingerprint"}
    stale_expected["questions"] = (
        QUESTIONS[0] + " Revised wording?\n" + "\n".join(QUESTIONS[1:])
    )
    require(
        equal(stale["working"], stale_expected)
        and equal(json_object(data["stale-scope.json"]), stale_expected)
        and equal(stale["stored"], {**saved, "revision": 2}),
        "Stale question scope backup or original changed",
    )
    conflict = observe["conflict"]
    require(
        set(conflict)
        == {
            "initial",
            "saved",
            "working",
            "posts",
            "automatic_replays",
            "snapshot_before",
            "snapshot_after",
            "warning",
        },
        "Scoped conflict fields differ",
    )
    control_expected = validate({**expected, "title": TITLE + " — conflict control"})
    require(
        equal(conflict["initial"]["document"], control_expected)
        and type(conflict["initial"]["revision"]) is int
        and conflict["initial"]["revision"] == 1
        and conflict["initial"]["id"] != saved["id"]
        and conflict["saved"]["id"] == conflict["initial"]["id"]
        and conflict["saved"]["revision"] == 2
        and equal(
            conflict["saved"]["document"],
            validate(
                {
                    **control_expected,
                    "recipient": "Fictional other-window saved wording",
                }
            ),
        ),
        "Scoped conflict changed unrelated original or saved wrong wording",
    )
    conflict_working = {k: v for k, v in control_expected.items() if k != "fingerprint"}
    conflict_working["recipient"] = "Fictional local unsaved conflict 🐝"
    require(
        equal(conflict["working"], conflict_working)
        and equal(json_object(data["scoped-conflict.json"]), conflict_working)
        and equal(json_object(data["control-import.json"]), expected)
        and type(conflict["posts"]) is int
        and conflict["posts"] == 1
        and type(conflict["automatic_replays"]) is int
        and conflict["automatic_replays"] == 0
        and equal(conflict["snapshot_before"], conflict["snapshot_after"])
        and "changed in another window" in conflict["warning"],
        "Scoped conflict lost inputs, changed typed records or replayed",
    )
    report = observe["report"]
    validate_report(report, expected, data["handover.docx"])
    require(
        type(observe["report_id"]) is str
        and re.fullmatch(r"[0-9a-f]{32}", observe["report_id"]),
        "Report ID is missing",
    )
    for excerpt in report["excerpts"]:
        original = next(
            row for row in expected["documents"] if row["id"] == excerpt["source_id"]
        )
        require(
            excerpt["quote"] == original["content"][excerpt["start"] : excerpt["end"]],
            "Passage range no longer binds the full original",
        )
    require(
        report["question_index"][0]["source_scope"]["source_ids"] == [ids[0]]
        and report["question_index"][1]["source_scope"]["source_ids"] == []
        and report["question_index"][2]["source_scope"]["mode"] == "all",
        "Report source choices broadened",
    )
    with zipfile.ZipFile(io.BytesIO(data["handover.docx"])) as archive:
        word = ET.fromstring(archive.read("word/document.xml"))
    text = "".join(
        row.text or ""
        for row in word.iter(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
        )
    )
    require(
        "Fictional human partial handover" in text
        and "No sources were selected" in text
        and "No application or enquiry was sent." in text,
        "Actual Word export lost scope or applied wording",
    )
    raw_fixture = json_object(
        (ROOT / "src/sinter/web/offline-garden-campaign.json").read_bytes()
    )
    campaign = validate_campaign(raw_fixture)
    campaign["actions"][0]["task"] = ACTION
    require(
        equal(observe["campaign"]["document"], campaign),
        "Campaign edit changed unknown owners/date/history/evidence",
    )
    phase_names = [r["name"] for r in observe["phases"]]
    require(
        phase_names
        == [
            "saved-use",
            "stopped-1",
            "reopened-use",
            "stopped-2",
            "stopped-3",
            "restored-both",
            "stopped-4",
        ],
        "Actual stop/reopen/use phases differ",
    )
    for row in observe["phases"]:
        require(
            equal(seed_projection(row["snapshot"], initial), initial),
            "Seeded typed rows, settings/model or persistent metadata changed",
        )
    for branch in ("clipboard", "manual"):
        offline = observe["offline"][branch]
        require(
            set(offline)
            == {
                "document",
                "selection",
                "clipboard",
                "snapshot_before",
                "snapshot_after",
            },
            "Offline recovery fields differ",
        )
        document = {
            **expected,
            "recipient": "Fictional " + branch + " recovery 🐝 e\u0301",
        }
        # Backup is the complete editable payload (normalization fingerprint excluded).
        working = {k: v for k, v in document.items() if k != "fingerprint"}
        require(
            equal(offline["document"], working)
            and equal(json_object(data[branch + ".json"]), working)
            and equal(json_object(data[branch + "-reference.json"]), working),
            "Offline recovery omitted full original inputs or scope",
        )
        raw = data[branch + ".json"].decode("utf-8")
        require(
            type(offline["selection"]) is list
            and len(offline["selection"]) == 2
            and all(type(endpoint) is int for endpoint in offline["selection"])
            and offline["selection"] == [0, len(raw.encode("utf-16-le")) // 2]
            and equal(offline["snapshot_before"], offline["snapshot_after"]),
            "Stopped backup changed local records or truncated manual selection",
        )
        require(
            equal(
                offline["clipboard"],
                {"attempts": 1, "successes": int(branch == "clipboard")},
            ),
            "Clipboard branch was not exercised",
        )
        restored = observe[branch + "_restored"]
        require(
            restored["id"] != saved["id"]
            and type(restored["revision"]) is int
            and restored["revision"] == 1
            and equal(
                restored["document"],
                validate({**working, "title": TITLE + " — " + branch + " restored"}),
            ),
            "Restore overwrote original or omitted full source choices",
        )
    require(
        observe["clipboard_restored"]["id"] != observe["manual_restored"]["id"],
        "Recovery copies share an identity",
    )
    protocol = json_object(data["protocol.json"])
    require(
        set(protocol)
        == {
            "matrix",
            "capable_get",
            "capable_validate",
            "snapshot_before",
            "snapshot_after",
            "jobs_before",
            "jobs_after",
        }
        and equal(protocol["snapshot_before"], protocol["snapshot_after"])
        and equal(protocol["jobs_before"], protocol["jobs_after"]),
        "Unsupported protocol work changed rows or queued work",
    )
    pairs = {(row["route"], row["variant"]) for row in protocol["matrix"]}
    require(
        len(protocol["matrix"]) == 30
        and pairs
        == {
            (r, v)
            for r in (
                "get",
                "validate",
                "save_scoped",
                "save_v1_over_scoped",
                "build",
                "draft",
            )
            for v in (
                "missing",
                "wrong",
                "duplicate_valid",
                "valid_wrong",
                "wrong_valid",
            )
        },
        "Protocol capability matrix is incomplete",
    )
    require(
        all(
            type(row["status"]) is int
            and row["status"] == 400
            and "no choices were cleared" in row["response"]["error"]
            for row in protocol["matrix"]
        )
        and equal(protocol["capable_get"], saved)
        and equal(protocol["capable_validate"], expected),
        "Protocol admission or friendly refusal differs",
    )
    processes = json_object(data["processes.json"])
    require(
        set(processes) == {"rows", "failure", "closed"}
        and processes["failure"] is None
        and processes["closed"] is True
        and len(processes["rows"]) == 4,
        "Owned source lifecycle incomplete",
    )
    pids = set()
    for n, row in enumerate(processes["rows"], 1):
        require(
            type(row["run"]) is int
            and row["run"] == n
            and type(row["pid"]) is int
            and row["pid"] > 0
            and row["pid"] not in pids
            and type(row["returncode"]) is int
            and row["returncode"] == 0
            and row["port_closed"] is True
            and row["stop_method"]
            == ("terminate" if n in (2, 3) else "interface_quit"),
            "Actual source process exit/reopen differs",
        )
        pids.add(row["pid"])
        marker = json_object(data[f"process/run-{n}.json"])
        version = re.search(
            r'__version__\s*=\s*["\']([^"\']+)',
            (ROOT / "src/sinter/__init__.py").read_text(encoding="utf-8"),
        )[1]
        require(
            set(marker)
            == {
                "version",
                "frozen",
                "provider_attempts",
                "external_attempts",
                "scheduler_paused",
                "OS_browser_tested",
                "seed",
                "reader_checks",
            }
            and marker["version"] == version
            and marker["seed"] is None
            and type(marker["provider_attempts"]) is int
            and type(marker["external_attempts"]) is int,
            "Worker fields/version/attempt types differ",
        )
        require(
            equal(row["control"], marker)
            and marker["provider_attempts"] == marker["external_attempts"] == 0
            and marker["frozen"] is False
            and marker["scheduler_paused"] is True
            and marker["OS_browser_tested"] is False,
            "Worker identity/model isolation differs",
        )
        readers = marker["reader_checks"]
        require(
            set(readers["native"])
            == {
                "open",
                "import",
                "resave",
                "build",
                "export_scoped_local",
                "add_text_scoped_local",
                "resave_scoped_local",
                "build_scoped_local",
            }
            and set(readers["runtime"])
            == {
                "casebooks.get",
                "casebooks.validate",
                "casebooks.save",
                "casebooks.save_scoped",
                "casebooks.build",
                "casebooks.draft",
            }
            and all(
                "no choices were cleared" in message
                for group in ("native", "runtime")
                for message in readers[group].values()
            )
            and readers["jobs_unchanged"] is True,
            "Current unsupported readers were not refused before work",
        )
        require(
            equal(
                readers["snapshot_before"],
                json_object(data[f"process/run-{n}.reader-before.json"]),
            )
            and equal(readers["snapshot_before"], readers["snapshot_after"])
            and equal(readers["stored"], saved),
            "Current reader probes changed scoped original/history/settings",
        )
        require(
            set(readers["cli"])
            == {"casebooks.get", "casebooks.validate", "casebooks.build", "export"},
            "Current CLI preservation inventory differs",
        )
        for op, result in readers["cli"].items():
            envelope = json_object(
                data[f"process/run-{n}.{op.replace('.', '-')}.stdout"]
            )
            require(
                type(result["returncode"]) is int
                and result["returncode"] == 0
                and result["ok"] is True
                and equal(result["result"], envelope["result"])
                and envelope["ok"] is True,
                "Actual current CLI failed scoped preservation",
            )
        require(
            equal(json_object(data[f"process/run-{n}.cli-export.json"]), expected),
            "CLI export omitted full originals/scopes",
        )
        for stream in ("stdout", "stderr"):
            raw = data[f"process/run-{n}.{stream}"]
            # Binding values against actual raw bytes, not a producer's self-report.
            import base64

            require(
                equal(
                    row[stream],
                    {
                        "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "sample_base64": base64.b64encode(raw[:65536]).decode(),
                        "sample_complete": len(raw) <= 65536,
                    },
                ),
                "Process diagnostic sample/hash differs",
            )
        require(
            data[f"process/run-{n}.stderr"]
            == browser_notice((ROOT / "src/sinter/desktop.py").read_bytes()),
            "Source callback emitted an unexpected diagnostic",
        )
        require(
            equal(seed_projection(row["persistent_snapshot"], initial), initial),
            "Stopped current source changed seeded typed originals/settings",
        )
    final = processes["rows"][-1]["persistent_snapshot"]
    scoped_rows = wrappers(final, "casebooks_scoped_v2")
    require(
        equal(
            sorted(scoped_rows, key=lambda r: r["id"]),
            sorted(
                [
                    saved,
                    observe["clipboard_restored"],
                    observe["manual_restored"],
                    conflict["saved"],
                ],
                key=lambda r: r["id"],
            ),
        ),
        "Stored scoped original/copies differ after real cold reopen",
    )
    final_tables = final["databases"]["workspace.sqlite3"]["tables"]
    initial_tables = initial["databases"]["workspace.sqlite3"]["tables"]
    require(
        all(
            equal(table, initial_tables[name])
            for name, table in final_tables.items()
            if name not in {"casebooks_scoped_v2", "reports"}
        ),
        "Recovery introduced foreign v1 rows or modified original history",
    )
    report_table = final["databases"]["workspace.sqlite3"]["tables"]["reports"]
    require(
        len(report_table["rows"]) == len(initial_tables["reports"]["rows"]) + 1
        and any(
            row[0] == observe["report_id"] and equal(json.loads(row[-1]), report)
            for row in report_table["rows"]
        ),
        "Original report ID/raw JSON/history lost",
    )
    require(
        equal(wrappers(final, "campaigns", "campaigns.sqlite3"), [observe["campaign"]]),
        "Campaign action/history altered by recovery",
    )
    return observe


def validate_rehearsal(
    folder,
    source_files,
    commit,
    manifest_sha,
    *,
    _pending=False,
):
    path = folder / RECEIPT
    require(
        not path.is_symlink() and path.stat().st_size <= 1024 * 1024,
        "Use a bounded source receipt",
    )
    receipt = json_object(path.read_bytes())
    require(set(receipt) == FIELDS, "Scoped source receipt fields differ")
    version = re.search(
        r'__version__\s*=\s*["\']([^"\']+)',
        (ROOT / "src/sinter/__init__.py").read_text(encoding="utf-8"),
    )[1]
    fixed = {
        "schema": SCHEMA,
        "execution": "source",
        "source_base_commit": commit,
        "source_manifest_sha256": manifest_sha,
        "source_files_sha256": source_files,
        "observed_version": version,
        "candidate_admitted": False,
        "installed_tested": False,
        "native_tested": False,
        "prior_replacement_tested": False,
        "release_qualified": False,
        "source_rehearsal_passed": not _pending,
        "source_files_conserved": True,
        "resources": {
            "browser_closed": True,
            "outer_relay_closed": True,
            "inner_relay_closed": True,
            "source_processes_stopped": True,
        },
        "failure": None,
    }
    require(
        all(equal(receipt[k], v) for k, v in fixed.items()),
        "Source-only flags, identity or cleanup differ",
    )
    wanted = CORE | {"v1-profile/" + name for name in v1.ARTIFACTS | {v1.RECEIPT}}
    actual = {
        p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()
    }
    require(
        set(receipt["artifacts"]) == wanted and actual == wanted | {RECEIPT},
        "Scoped artifact roles missing or foreign",
    )
    data = {}
    total = 0
    for name in sorted(wanted):
        p = folder / name
        row = receipt["artifacts"][name]
        require(
            not p.is_symlink()
            and p.resolve().is_relative_to(folder.resolve())
            and p.stat().st_size <= 2 * 1024 * 1024,
            "Artifact exceeds boundary",
        )
        raw = p.read_bytes()
        total += len(raw)
        require(
            total <= 32 * 1024 * 1024
            and set(row) == {"bytes", "sha256"}
            and type(row["bytes"]) is int
            and row["bytes"] == len(raw)
            and hashlib.sha256(raw).hexdigest() == row["sha256"],
            "Actual artifact byte/hash binding differs",
        )
        if name.endswith(".png"):
            validate_png(raw)
        if name in CORE:
            data[name] = raw
    v1.validate_rehearsal(folder / "v1-profile", source_files, commit, manifest_sha)
    validate_semantics(data)
    return receipt
