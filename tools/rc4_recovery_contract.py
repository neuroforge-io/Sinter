"""Closed source-only campaign recovery evidence; not RC4 installed admission.

The RC3 installed/v1 verifier remains unchanged. This separate rehearsal proves
its actual source process/UI subset and refuses installed/release claim fields.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from pathlib import Path

from tools.installed_menu_browser import browser_notice
from tools.installed_recovery_contract import (
    ARTIFACT_PATHS,
    CAMPAIGN_SOURCE,
    PHASES,
    _calendar,
    _csv,
    _offline,
    _phases,
    fictional_states,
)
from tools.installed_workflow_qualification import (
    canonical_hash,
    json_object,
    validate_png,
)
from tools.rc4_recovery_worker import canonical, protected

SCHEMA = "sinter-rc4-local-recovery-source/v1"
RECEIPT = "rc4-local-recovery-source.json"
UNCERTAIN_TITLE = "Fictional uncertain recovery control"
LOCAL_NOTE = (
    "\n\nFictional unsaved local correction — water approval is unknown. e\u0301 🐝"
)
OTHER_NOTE = "\n\nFictional other-window correction — permission is not confirmed."
SAVE_NOTE = "\n\nFictional saved wording with a lost acknowledgement."
QUIT_NOTE = "\n\nFictional unsaved wording retained after an uncertain quit."


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 1024 * 1024
MAX_TOTAL = 20 * 1024 * 1024
ADVANCED = (
    "control-import.json",
    "stale-source.png",
    "conflict-backup.json",
    "conflict.png",
    "actual-save-response.json",
    "uncertain-save-backup.json",
    "actual-quit-response.json",
    "uncertain-quit-backup.json",
    "uncertain-quit.png",
    "observations.json",
)
ARTIFACTS = frozenset(
    {
        *ARTIFACT_PATHS.values(),
        *("advanced/" + name for name in ADVANCED),
        *(
            f"process/run-{n}.{suffix}"
            for n in range(1, 7)
            for suffix in ("json", "stdout", "stderr")
        ),
        "processes.json",
        "seed.stdout",
        "seed.stderr",
        "seed-control.json",
        "base-observations.json",
    }
)
FIELDS = frozenset(
    {
        "schema",
        "execution",
        "profile",
        "source_base_commit",
        "observed_version",
        "source_manifest_sha256",
        "source_files_sha256",
        "candidate_admitted",
        "installed_tested",
        "release_qualified",
        "source_rehearsal_passed",
        "resources",
        "failure",
        "artifacts",
        "source_files_conserved",
    }
)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            result.update(chunk)
    return result.hexdigest()


def equal(first, second):
    return canonical(first) == canonical(second)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_artifacts(folder, declared):
    require(
        isinstance(declared, dict) and set(declared) == ARTIFACTS,
        "Recovery artifact inventory differs.",
    )
    actual = {
        p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()
    }
    require(
        actual == ARTIFACTS | {RECEIPT},
        "Recovery bundle contains foreign or missing files.",
    )
    data, total = {}, 0
    for name in sorted(ARTIFACTS):
        path = folder / name
        require(
            not path.is_symlink()
            and path.is_file()
            and path.resolve().is_relative_to(folder.resolve()),
            "Recovery artifact escapes its bundle.",
        )
        size = path.stat().st_size
        require(size <= MAX_FILE, "Recovery artifact exceeds its read bound.")
        row = declared[name]
        require(
            isinstance(row, dict)
            and set(row) == {"bytes", "sha256"}
            and type(row["bytes"]) is int
            and row["bytes"] == size
            and type(row["sha256"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
            and digest(path) == row["sha256"],
            "Recovery artifact identity differs.",
        )
        total += size
        require(total <= MAX_TOTAL, "Recovery bundle exceeds its read bound.")
        data[name] = path.read_bytes()
        if name.endswith(".png"):
            validate_png(data[name])
    return data


def validate_rehearsal(folder, source_files, commit, manifest_sha, *, _pending=False):
    """Validate complete actual artifacts under source-only caller identity."""
    receipt_path = folder / RECEIPT
    require(
        not receipt_path.is_symlink() and receipt_path.stat().st_size <= MAX_FILE,
        "Use the bounded source rehearsal receipt.",
    )
    receipt = json_object(receipt_path.read_bytes())
    require(set(receipt) == FIELDS, "Recovery receipt fields differ.")
    version = re.search(
        r'__version__\s*=\s*["\']([^"\']+)',
        (ROOT / "src/sinter/__init__.py").read_text(),
    )[1]
    fixed = {
        "schema": SCHEMA,
        "execution": "source",
        "profile": "rc4-local-campaign-recovery",
        "source_base_commit": commit,
        "observed_version": version,
        "source_manifest_sha256": manifest_sha,
        "source_files_sha256": source_files,
        "candidate_admitted": False,
        "installed_tested": False,
        "release_qualified": False,
        "failure": None,
        "source_files_conserved": True,
    }
    require(
        all(equal(receipt[k], v) for k, v in fixed.items()),
        "Source recovery cannot admit installed, changed-source or release claims.",
    )
    require(
        receipt["source_rehearsal_passed"] is (False if _pending else True),
        "Recovery result is not a completed source pass.",
    )
    resources = {
        "browser_closed": True,
        "source_processes_stopped": True,
        "outer_relay_closed": True,
        "inner_relay_closed": True,
    }
    require(equal(receipt["resources"], resources), "Recovery resources did not close.")
    data = read_artifacts(folder, receipt["artifacts"])
    states = fictional_states({CAMPAIGN_SOURCE: (ROOT / CAMPAIGN_SOURCE).read_bytes()})
    phases = _phases(data[ARTIFACT_PATHS["phases"]], states)
    base = json_object(data["base-observations.json"])
    require(
        set(base)
        == {"processes", "offline", "page_errors", "external_requests", "result_hashes"}
        and equal([base["page_errors"], base["external_requests"]], [0, 0]),
        "Base recovery observations differ.",
    )
    _offline(base["offline"])
    for branch in ("clipboard", "manual"):
        reference = data[ARTIFACT_PATHS[branch + "_reference"]]
        text = data[ARTIFACT_PATHS[branch + "_text"]]
        require(
            reference == text and equal(json_object(text), states["working"]),
            "Recovery backup omitted or changed original input.",
        )
        selected = base["offline"][branch]
        require(
            selected["textarea_selection_start"] == 0
            and selected["textarea_selection_end"]
            == len(text.decode().encode("utf-16-le")) // 2,
            "Recovery selection does not cover the full payload.",
        )
    _csv(data[ARTIFACT_PATHS["held_csv"]], states["held"])
    for role, phase in (
        ("held_calendar", "held"),
        ("resumed_closed_calendar", "resumed_closed"),
        ("resumed_calendar", "resumed"),
    ):
        _calendar(data[ARTIFACT_PATHS[role]], states[phase])
    seed = json_object(data["seed-control.json"])
    require(
        equal([seed["provider_attempts"], seed["external_attempts"]], [0, 0])
        and seed["frozen"] is False,
        "Source seed attempted an external service.",
    )
    require(
        data["seed.stdout"] == data["seed.stderr"] == b"",
        "Source seed diagnostics differ.",
    )
    baseline = protected(seed["seed"]["snapshot"])
    require(
        seed["seed"]["public_settings"]["has_session_key"] is False
        and seed["seed"]["public_settings"]["environment_override"] is False
        and seed["seed"]["connection"]["inherit_key"] is False
        and seed["seed"]["connection"]["api_key"] == ""
        and seed["seed"]["settings"]["model"] == "fictional-recovery-model",
        "Source settings/model fixture differs.",
    )
    processes = json_object(data["processes.json"])
    require(
        set(processes) == {"rows", "failure", "closed"}
        and processes["failure"] is None
        and processes["closed"] is True
        and len(processes["rows"]) == 6,
        "Recovery lacks six actual clean process stops.",
    )
    require(
        equal(
            base["result_hashes"],
            {
                **{
                    phase: canonical_hash(phases[phase]["document"]) for phase in PHASES
                },
                "working_copy": canonical_hash(states["working"]),
            },
        ),
        "Recovery phase hashes differ.",
    )
    require(
        equal(
            base["processes"],
            [
                {
                    "run": row["run"],
                    "pid": row["pid"],
                    "executable": sys.executable,
                    "binary_sha256": digest(Path(sys.executable)),
                    "stop_method": row["stop_method"],
                    "returncode": row["returncode"],
                }
                for row in processes["rows"][:4]
            ],
        ),
        "Recovery browser observations do not match actual source children.",
    )
    seed_value = seed["seed"]
    require(
        set(seed)
        == {
            "version",
            "frozen",
            "provider_attempts",
            "external_attempts",
            "scheduler_paused",
            "OS_browser_tested",
            "seed",
        }
        and seed["version"] == version
        and seed["scheduler_paused"] is True
        and seed["OS_browser_tested"] is False
        and set(seed_value)
        == {
            "casebook",
            "report_id",
            "original_report",
            "settings",
            "public_settings",
            "connection",
            "snapshot",
        },
        "Source seed control differs.",
    )
    settings = seed_value["snapshot"]["preferences"]
    require(
        equal(settings, seed_value["settings"])
        and all(
            equal(settings.get(key), value)
            for key, value in {
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
            }.items()
        ),
        "Source preferences/model fixture differs.",
    )
    tables = seed_value["snapshot"]["databases"]["workspace.sqlite3"]["tables"]

    def stored(table, identifier):
        value = tables[table]
        columns = {key: index for index, key in enumerate(value["columns"])}
        rows = [row for row in value["rows"] if row[columns["id"]] == identifier]
        require(len(rows) == 1, "Protected source history row is missing.")
        return json_object(rows[0][columns["document"]].encode())

    book = seed_value["casebook"]
    report = seed_value["original_report"]
    require(
        equal(stored("casebooks", book["id"]), book["document"])
        and equal(stored("reports", seed_value["report_id"]), report)
        and book["document"]["documents"][0]["content"]
        == "Venue approval is NOT confirmed. Original café e\u0301 🐝 wording."
        and equal(
            report.get("document_edits"),
            {
                "markdown": (
                    "# Applied human wording\n\nApproval remains unknown. e\u0301 🐝"
                ),
                "edited_at": "2026-10-02T12:00:00Z",
                "author": "user",
            },
        )
        and "id" not in report,
        "Protected original source/report/applied wording differs.",
    )
    pids = set()
    notice = browser_notice((ROOT / "src/sinter/desktop.py").read_bytes())
    for n, row in enumerate(processes["rows"], 1):
        require(
            set(row)
            == {
                "run",
                "pid",
                "returncode",
                "stop_method",
                "stdout",
                "stderr",
                "port_closed",
                "persistent_snapshot",
                "control",
            },
            "Process fields differ.",
        )
        require(
            type(row["run"]) is int
            and row["run"] == n
            and type(row["pid"]) is int
            and row["pid"] > 0
            and row["pid"] not in pids
            and type(row["returncode"]) is int
            and row["returncode"] == 0
            and row["stop_method"] == ("terminate" if n in (2, 3) else "interface_quit")
            and row["port_closed"] is True,
            "Process identity, exit or closed-port observation differs.",
        )
        pids.add(row["pid"])
        require(
            equal(protected(row["persistent_snapshot"]), baseline),
            "Stopped process changed protected history, settings or metadata.",
        )
        require(
            equal(row["control"], json_object(data[f"process/run-{n}.json"]))
            and equal(
                row["control"],
                {
                    "version": version,
                    "frozen": False,
                    "provider_attempts": 0,
                    "external_attempts": 0,
                    "scheduler_paused": True,
                    "OS_browser_tested": False,
                    "seed": None,
                },
            ),
            "Source process attempted a provider or retained an unexpected control.",
        )
        for stream in ("stdout", "stderr"):
            raw = data[f"process/run-{n}.{stream}"]
            expected = {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "sample_base64": base64.b64encode(raw[:65536]).decode(),
                "sample_complete": len(raw) <= 65536,
            }
            require(equal(row[stream], expected), "Process stream capture differs.")
        require(
            data[f"process/run-{n}.stderr"] == notice,
            "Unexpected source diagnostic cannot pass.",
        )
    advanced = json_object(data["advanced/observations.json"])
    require(
        set(advanced)
        == {
            "conflict",
            "stale_source",
            "uncertain_save",
            "uncertain_quit",
            "reopened_uncertain_save",
            "external_requests",
            "page_errors",
            "browser_dialogs",
        }
        and all(
            type(advanced[k]) is int and advanced[k] == 0
            for k in ("external_requests", "page_errors", "browser_dialogs")
        ),
        "Advanced recovery observations differ.",
    )
    imported = {**states["resumed"], "title": UNCERTAIN_TITLE}
    require(
        equal(json_object(data["advanced/control-import.json"]), imported),
        "Recovery control import differs.",
    )
    require(
        equal(
            advanced["stale_source"],
            {
                "stored_mark": imported["requirements"][1]["status"],
                "registered_date": imported["sources"][0]["checked_at"],
                "excerpt_checked_date": imported["requirements"][1]["checked_at"],
                "warning_visible": True,
                "stored_original_preserved": True,
            },
        ),
        "Stale source meaning or original human mark differs.",
    )
    conflict = advanced["conflict"]
    require(
        set(conflict)
        == {
            "base",
            "other_saved",
            "local_document",
            "failed_save_posts",
            "stored_original_preserved",
        }
        and equal(conflict["failed_save_posts"], 1)
        and conflict["stored_original_preserved"] is True,
        "Conflict observations differ.",
    )

    def wrapper(value, revision):
        return (
            isinstance(value, dict)
            and set(value) == {"id", "revision", "document"}
            and type(value["id"]) is str
            and re.fullmatch(r"[0-9a-f]{32}", value["id"])
            and type(value["revision"]) is int
            and value["revision"] == revision
        )

    require(
        wrapper(conflict["base"], 1) and wrapper(conflict["other_saved"], 2),
        "Conflict wrapper identity differs.",
    )
    require(
        type(conflict["base"]["revision"]) is int
        and conflict["base"]["revision"] == 1
        and equal(conflict["base"]["document"], imported),
        "Conflict baseline differs.",
    )
    local = {**imported, "objective": imported["objective"] + LOCAL_NOTE}
    other = {**imported, "objective": imported["objective"] + OTHER_NOTE}
    require(
        equal(conflict["local_document"], local)
        and equal(json_object(data["advanced/conflict-backup.json"]), local),
        "Conflict lost local recovery input.",
    )
    current = conflict["other_saved"]
    require(
        current["id"] == conflict["base"]["id"]
        and type(current["revision"]) is int
        and current["revision"] == 2
        and equal(current["document"], other),
        "Conflict changed the other saved original.",
    )
    saved = advanced["uncertain_save"]
    require(
        set(saved)
        == {
            "before",
            "actual_saved",
            "working_document",
            "actual_status",
            "reported_status",
            "save_posts",
            "automatic_replays",
        }
        and equal(saved["before"], current)
        and equal(
            [
                saved[k]
                for k in (
                    "actual_status",
                    "reported_status",
                    "save_posts",
                    "automatic_replays",
                )
            ],
            [200, 503, 1, 0],
        ),
        "Uncertain save observations differ.",
    )
    working = {**other, "objective": other["objective"] + SAVE_NOTE}
    actual = saved["actual_saved"]
    require(wrapper(actual, 3), "Uncertain save wrapper identity differs.")
    require(
        actual["id"] == current["id"]
        and type(actual["revision"]) is int
        and actual["revision"] == 3
        and equal(actual["document"], working)
        and equal(saved["working_document"], working)
        and equal(json_object(data["advanced/actual-save-response.json"]), actual)
        and equal(json_object(data["advanced/uncertain-save-backup.json"]), working)
        and equal(advanced["reopened_uncertain_save"], actual),
        "Uncertain save lost actual stored wording or input.",
    )
    quit_state = advanced["uncertain_quit"]
    dirty = {**working, "objective": working["objective"] + QUIT_NOTE}
    expected = {
        "working_document": dirty,
        "keep_working_posts": 0,
        "keep_working_retained_input": True,
        "actual_status": 200,
        "reported_status": 503,
        "quit_posts": 1,
        "automatic_replays": 0,
        "input_retained_after_stop": True,
    }
    require(
        equal(quit_state, expected)
        and equal(json_object(data["advanced/uncertain-quit-backup.json"]), dirty)
        and equal(
            json_object(data["advanced/actual-quit-response.json"]), {"ok": True}
        ),
        "Uncertain quit cleared input, replayed or falsely claimed confirmation.",
    )
    # The reopened live-file campaigns must contain exactly three recovery rows
    # plus the deliberately separate uncertain control; no original is rewritten.
    last = processes["rows"][-1]["persistent_snapshot"]["databases"][
        "campaigns.sqlite3"
    ]["tables"]["campaigns"]
    indexes = {name: index for index, name in enumerate(last["columns"])}
    wrappers = [
        {
            "id": row[indexes["id"]],
            "revision": row[indexes["revision"]],
            "document": json.loads(row[indexes["document"]]),
        }
        for row in last["rows"]
    ]
    wanted = [
        phases["resumed"],
        phases["restored_clipboard"],
        phases["restored_manual"],
        actual,
    ]
    require(
        equal(
            sorted(wrappers, key=lambda row: row["id"]),
            sorted(wanted, key=lambda row: row["id"]),
        ),
        "Cold reopen changed originals, separate copies or actual uncertain save.",
    )
    return receipt
