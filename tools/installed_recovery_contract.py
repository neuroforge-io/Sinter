"""Closed fictional RC3 recovery evidence; no producer execution is implied.

The preceding installed-workflow/v1 gate remains mandatory and unchanged. This
additional contract admits complete local recovery payloads and observed process
transitions, rather than accepting a list of self-declared successful checks.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

from tools.installed_workflow_qualification import (
    canonical_hash,
    json_object,
    validate_png,
)

SCHEMA = "sinter-installed-recovery/v1"
VERSION = "0.5.4rc3"
RECEIPT_PATH = "installed-recovery-browser.json"
CAMPAIGN_SOURCE = "src/sinter/web/offline-garden-campaign.json"
HELD_ACTION_INDEX = 1
CONTROL_ACTION = MappingProxyType(
    {
        "opportunity": "",
        "scope_confirmed": True,
        "submission_phase": "pre_submission",
        "task": "Fictional calendar control - proposed date only",
        "owner": "Fictional control owner",
        "owner_kind": "unknown",
        "owner_confirmed": False,
        "due": "2026-10-10",
        "status": "open",
    }
)
OFFLINE_NOTE = "\n\nFictional offline correction — water approval remains unknown. 🐝"
RESTORED_CLIPBOARD_TITLE = "Restored fictional clipboard recovery"
RESTORED_MANUAL_TITLE = "Restored fictional manual recovery"
COPY_NOTICE = (
    "Backup text copied from your inputs at the time you clicked. Paste it into "
    "a text file to keep a copy. This does not save the campaign or create a file."
)
MANUAL_NOTICE = (
    "Clipboard unavailable. Select and copy the complete backup text below. "
    "This does not save the campaign or create a file."
)
PHASES = (
    "initial",
    "held",
    "reopened_held",
    "held_closed",
    "resumed_closed",
    "resumed",
    "original_after_clipboard_restore",
    "original_after_manual_restore",
    "restored_clipboard",
    "restored_manual",
)
ARTIFACT_PATHS = MappingProxyType(
    {
        "phases": "installed-recovery/campaign-phases.json",
        "clipboard_reference": "installed-recovery/clipboard-reference.json",
        "clipboard_text": "installed-recovery/clipboard-text.json",
        "manual_reference": "installed-recovery/manual-reference.json",
        "manual_text": "installed-recovery/manual-text.json",
        "held_csv": "installed-recovery/held-actions.csv",
        "held_calendar": "installed-recovery/held-calendar.ics",
        "resumed_closed_calendar": "installed-recovery/resumed-closed-calendar.ics",
        "resumed_calendar": "installed-recovery/resumed-calendar.ics",
        "held_screen": "installed-recovery/01-held.png",
        "reopened_screen": "installed-recovery/02-reopened.png",
        "clipboard_screen": "installed-recovery/03-offline-clipboard.png",
        "manual_screen": "installed-recovery/04-offline-manual.png",
        "restored_screen": "installed-recovery/05-restored.png",
    }
)
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
RUNTIME_FIELDS = (
    "system",
    "target_arch",
    "machine",
    "pointer_bits",
    "frozen",
    "desktop",
    "installed_executable",
    "image_id",
    "container",
    "network",
    "network_mode",
    "host_installation",
    "os_release",
    "libc",
    "external_requests",
    "page_errors",
    "model_calls",
    "resources",
    "web_assets_sha256",
    "practice_fixture_sha256",
)
RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "version",
        "source_commit",
        "installer_sha256",
        "source_archive_sha256",
        "native_receipt_sha256",
        "installed_binary_sha256",
        "installed_workflow_receipt_sha256",
        "runtime",
        "processes",
        "offline",
        "artifacts",
        "input_hashes",
        "result_hashes",
    }
)
CSV_HEADER = (
    "Action",
    "Scope",
    "Phase",
    "Owner",
    "Proposed target date (unconfirmed)",
    "Status",
)
_SHA = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[0-9a-f]{32}")


def _equal(actual: object, expected: object) -> bool:
    return canonical_hash(actual) == canonical_hash(expected)


def fictional_states(source: dict[str, bytes]) -> dict[str, dict]:
    """Only admitted UI edits; full source arrays/history remain unmodified."""
    if CAMPAIGN_SOURCE not in source:
        raise ValueError("The installed recovery lacks its pinned fictional campaign.")
    original = json_object(source[CAMPAIGN_SOURCE])
    actions, routes = original.get("actions", []), original.get("opportunities", [])
    if (
        original.get("schema") != "sinter-campaign/v1"
        or len(actions) != 4
        or len(routes) != 2
        or actions[1].get("status") != "open"
        or actions[1].get("owner_kind") != "unknown"
        or actions[1].get("owner_confirmed") is not False
        or actions[1].get("due") != "2026-10-09"
        or actions[1].get("opportunity") != routes[0].get("name")
        or actions[1].get("scope_confirmed") is not True
        or actions[1].get("submission_phase") != "pre_submission"
        or routes[0].get("status") != "clarification"
    ):
        raise ValueError("The pinned fictional recovery fixture has another shape.")
    baseline = copy.deepcopy(original)
    baseline["actions"].append(dict(CONTROL_ACTION))
    held = copy.deepcopy(baseline)
    held["actions"][HELD_ACTION_INDEX]["status"] = "held"
    closed = copy.deepcopy(held)
    closed["opportunities"][0]["status"] = "closed"
    resumed_closed = copy.deepcopy(closed)
    resumed_closed["actions"][HELD_ACTION_INDEX]["status"] = "open"
    working = copy.deepcopy(baseline)
    working["objective"] += OFFLINE_NOTE
    return {
        "original": original,
        "initial": baseline,
        "held": held,
        "reopened_held": held,
        "held_closed": closed,
        "resumed_closed": resumed_closed,
        "resumed": baseline,
        "original_after_clipboard_restore": baseline,
        "original_after_manual_restore": baseline,
        "working": working,
        "restored_clipboard": {**working, "title": RESTORED_CLIPBOARD_TITLE},
        "restored_manual": {**working, "title": RESTORED_MANUAL_TITLE},
    }


def _phases(content: bytes, states: dict[str, dict]) -> dict:
    phases = json_object(content)
    if set(phases) != set(PHASES):
        raise ValueError("Installed recovery phase inventory differs.")
    for phase in PHASES:
        wrapper = phases[phase]
        if (
            not isinstance(wrapper, dict)
            or set(wrapper) != {"id", "revision", "document"}
            or not isinstance(wrapper["id"], str)
            or not _ID.fullmatch(wrapper["id"])
            or type(wrapper["revision"]) is not int
            or wrapper["revision"] < 1
            or not _equal(wrapper["document"], states[phase])
        ):
            raise ValueError("Installed recovery changed retained campaign data.")
    initial = phases["initial"]
    for phase, offset in (
        ("held", 1),
        ("held_closed", 2),
        ("resumed_closed", 3),
        ("resumed", 4),
    ):
        if (
            phases[phase]["id"] != initial["id"]
            or phases[phase]["revision"] != initial["revision"] + offset
        ):
            raise ValueError(
                "Installed recovery lost campaign identity or revision order."
            )
    if not _equal(phases["held"], phases["reopened_held"]):
        raise ValueError("Cold reopening changed the held campaign.")
    for phase in ("original_after_clipboard_restore", "original_after_manual_restore"):
        if not _equal(phases[phase], phases["resumed"]):
            raise ValueError("Restore rewrote the saved original campaign.")
    ids = {initial["id"]}
    for phase in ("restored_clipboard", "restored_manual"):
        if phases[phase]["id"] in ids or phases[phase]["revision"] != 1:
            raise ValueError(
                "Installed recovery did not create separate restored copies."
            )
        ids.add(phases[phase]["id"])
    return phases


def _owner(row: dict) -> str:
    if row["owner_kind"] == "unassigned":
        return "Unassigned"
    if row["owner_kind"] == "role":
        value = re.sub(r"\s*\(suggested role\)$", "", row["owner"])
        return value + " (suggested role; no person named)"
    if row["owner_kind"] == "unknown":
        return row["owner"] + " (owner type not confirmed)"
    raise ValueError("The fictional fixture gained an unqualified owner type.")


def _plan_rows(document: dict) -> list[dict]:
    active = {
        route["name"]
        for route in document["opportunities"]
        if route["status"] in {"researching", "open", "upcoming", "clarification"}
    }
    rows = []
    for row in document["actions"]:
        scope = (
            (
                row["opportunity"]
                if row["opportunity"] in active
                else "Historical · " + row["opportunity"]
            )
            if row["opportunity"]
            else "Campaign-wide"
        )
        rows.append(
            {
                "action": row["task"],
                "scope": scope,
                "phase": "Before submission"
                if row["opportunity"]
                else "Not applicable · campaign-wide",
                "owner": _owner(row),
                "due": row["due"],
                "status": "held" if row["status"] == "held" else "not_started",
            }
        )
    return rows


def _csv(content: bytes, document: dict) -> None:
    try:
        rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    except (UnicodeError, csv.Error) as error:
        raise ValueError("Installed recovery CSV is unreadable.") from error
    expected = [list(CSV_HEADER)] + [list(row.values()) for row in _plan_rows(document)]
    if rows != expected:
        raise ValueError(
            "Installed recovery CSV lost held, owner or proposed-date meaning."
        )


def _calendar(content: bytes, document: dict) -> None:
    """Parse actual folded ICS; no occurrence counts or substring claims."""
    try:
        physical = content.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise ValueError("Installed recovery calendar is unreadable.") from error
    lines = []
    for line in physical:
        if not line or len(line.encode()) > 73:
            raise ValueError("Installed recovery calendar has invalid folded lines.")
        if line.startswith(" "):
            if not lines:
                raise ValueError("Installed recovery calendar has a dangling fold.")
            lines[-1] += line[1:]
        else:
            lines.append(line)
    if lines[:4] != [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NeuroForge//Sinter user plan//EN",
        "CALSCALE:GREGORIAN",
    ] or lines[-1:] != ["END:VCALENDAR"]:
        raise ValueError("Installed recovery calendar has another envelope.")
    expected_rows = [
        plan
        for row, plan in zip(document["actions"], _plan_rows(document))
        if row["status"] == "open"
        and row["due"]
        and row["scope_confirmed"]
        and row["submission_phase"] == "pre_submission"
        and (not row["opportunity"] or not plan["scope"].startswith("Historical · "))
    ]
    cursor, events = 4, []
    while cursor < len(lines) - 1:
        if lines[cursor] != "BEGIN:VEVENT":
            raise ValueError("Installed recovery calendar contains unexpected content.")
        cursor += 1
        event = {}
        while cursor < len(lines) - 1 and lines[cursor] != "END:VEVENT":
            key, separator, value = lines[cursor].partition(":")
            if not separator or key in event:
                raise ValueError(
                    "Installed recovery calendar has duplicate or malformed fields."
                )
            event[key] = value
            cursor += 1
        if cursor >= len(lines) - 1:
            raise ValueError("Installed recovery calendar has an incomplete event.")
        events.append(event)
        cursor += 1
    if len(events) != len(expected_rows) or not events:
        raise ValueError(
            "Installed recovery calendar has missing or forbidden actions."
        )

    def escape(text):
        return (
            text.replace("\\", "\\\\")
            .replace("\r", "")
            .replace("\n", "\\n")
            .replace(";", "\\;")
            .replace(",", "\\,")
        )

    for index, (event, row) in enumerate(zip(events, expected_rows)):
        day = date.fromisoformat(row["due"])
        stamp = event.get("DTSTAMP", "")
        expected = {
            "UID": hashlib.sha256(
                (document["title"] + "\0" + str(index) + "\0" + row["action"]).encode()
            ).hexdigest()
            + "@sinter.local",
            "DTSTAMP": stamp,
            "DTSTART;VALUE=DATE": day.strftime("%Y%m%d"),
            "DTEND;VALUE=DATE": (day + timedelta(days=1)).strftime("%Y%m%d"),
            "SUMMARY": escape(row["action"]),
            "DESCRIPTION": escape(
                "; ".join(
                    [
                        "Scope: " + row["scope"],
                        "Phase: " + row["phase"],
                        "Owner: " + row["owner"],
                        "Proposed target date · unconfirmed",
                    ]
                )
            ),
        }
        if not re.fullmatch(r"\d{8}T\d{6}Z", stamp) or event != expected:
            raise ValueError(
                "Installed recovery calendar changed scope, phase, owner "
                "or proposed timing."
            )
        try:
            datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
        except ValueError as error:
            raise ValueError(
                "Installed recovery calendar has an invalid UTC stamp."
            ) from error


def _processes(records: object, binary_sha: str) -> None:
    if not isinstance(records, list) or len(records) != 4:
        raise ValueError("Installed recovery needs four actual frozen process runs.")
    pids = set()
    for number, record in enumerate(records, 1):
        if (
            not isinstance(record, dict)
            or set(record)
            != {
                "run",
                "pid",
                "executable",
                "binary_sha256",
                "stop_method",
                "returncode",
            }
            or type(record["run"]) is not int
            or record["run"] != number
            or type(record["pid"]) is not int
            or record["pid"] < 1
            or record["pid"] in pids
            or record["executable"] != "/opt/neuroforge/sinter/Sinter"
            or record["binary_sha256"] != binary_sha
            or record["stop_method"]
            != ("interface_quit" if number in {1, 4} else "terminate")
            or type(record["returncode"]) is not int
            or record["returncode"] not in ({0} if number in {1, 4} else {0, -15})
        ):
            raise ValueError(
                "Installed recovery process exit/cold restart evidence differs."
            )
        pids.add(record["pid"])


def _offline(observed: object) -> None:
    if not isinstance(observed, dict) or set(observed) != {"clipboard", "manual"}:
        raise ValueError(
            "Installed recovery is missing a complete stopped-process branch."
        )
    for branch in ("clipboard", "manual"):
        row = observed[branch]
        if not isinstance(row, dict) or set(row) != {
            "mode",
            "save_connection_refusals",
            "backup_network_requests",
            "write_attempts",
            "write_successes",
            "notice",
            "textarea_selection_start",
            "textarea_selection_end",
        }:
            raise ValueError(
                "Installed recovery has an unqualified clipboard observation."
            )
        mode = row["mode"]
        expected = {
            "mode": mode,
            "save_connection_refusals": 1,
            "backup_network_requests": 0,
            "write_attempts": 1 if mode != "unavailable" else 0,
            "write_successes": 1 if branch == "clipboard" else 0,
            "notice": COPY_NOTICE if branch == "clipboard" else MANUAL_NOTICE,
            "textarea_selection_start": row["textarea_selection_start"],
            "textarea_selection_end": row["textarea_selection_end"],
        }
        if (
            mode
            not in ({"written"} if branch == "clipboard" else {"denied", "unavailable"})
            or not _equal(row, expected)
            or any(
                type(row[key]) is not int
                for key in (
                    "save_connection_refusals",
                    "backup_network_requests",
                    "write_attempts",
                    "write_successes",
                    "textarea_selection_start",
                    "textarea_selection_end",
                )
            )
        ):
            raise ValueError(
                "Installed recovery falsely claims clipboard/save success."
            )


def _bounded_file(folder: Path, path: Path) -> bytes:
    if (
        not path.is_file()
        or path.is_symlink()
        or not path.resolve().is_relative_to(folder.resolve())
        or any(
            parent.is_symlink()
            for parent in path.parents
            if parent != folder and parent.is_relative_to(folder)
        )
        or not 0 < path.stat().st_size <= MAX_ARTIFACT_BYTES
    ):
        raise ValueError("Installed recovery evidence is absent, unsafe or oversized.")
    return path.read_bytes()


def verify_installed_recovery(
    folder: Path,
    version: str,
    commit: str,
    sums: dict,
    source: dict[str, bytes],
    native: dict,
    binary_sha: str,
) -> None:
    """Validate source-bound complete payloads; preceding v1 gate must also pass."""
    if version != VERSION:
        raise ValueError("This installed recovery contract is qualified for RC3 only.")
    path = folder / RECEIPT_PATH
    receipt = json_object(_bounded_file(folder, path))
    workflow_path = folder / "installed-workflow-browser.json"
    workflow_bytes = _bounded_file(folder, workflow_path)
    workflow = json_object(workflow_bytes)
    fixed = {
        "schema": SCHEMA,
        "version": version,
        "source_commit": commit,
        "installer_sha256": native["installer_sha256"],
        "source_archive_sha256": sums[f"sinter-{version}-source.zip"],
        "native_receipt_sha256": sums[f"Sinter-{version}-linux-x64-test.json"],
        "installed_binary_sha256": binary_sha,
        "installed_workflow_receipt_sha256": hashlib.sha256(workflow_bytes).hexdigest(),
        "runtime": {key: workflow[key] for key in RUNTIME_FIELDS},
    }
    if set(receipt) != RECEIPT_FIELDS or any(
        not _equal(receipt.get(key), value) for key, value in fixed.items()
    ):
        raise ValueError(
            "Installed recovery identity or runtime differs "
            "from installed qualification."
        )
    _processes(receipt["processes"], binary_sha)
    _offline(receipt["offline"])
    artifacts = receipt["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != len(ARTIFACT_PATHS):
        raise ValueError("Installed recovery artifact inventory is incomplete.")
    retained, total = {}, 0
    for row in artifacts:
        if (
            not isinstance(row, dict)
            or set(row) != {"role", "path", "sha256", "bytes"}
            or not isinstance(row["role"], str)
            or row["role"] not in ARTIFACT_PATHS
            or row["role"] in retained
            or row["path"] != ARTIFACT_PATHS[row["role"]]
            or not isinstance(row["sha256"], str)
            or not _SHA.fullmatch(row["sha256"])
            or type(row["bytes"]) is not int
            or not 1 <= row["bytes"] <= MAX_ARTIFACT_BYTES
        ):
            raise ValueError("Installed recovery artifact role/path/bound differs.")
        artifact = folder / row["path"]
        if (
            artifact.is_symlink()
            or not artifact.is_file()
            or not artifact.resolve().is_relative_to(folder.resolve())
            or artifact.stat().st_size != row["bytes"]
        ):
            raise ValueError(
                "Installed recovery artifact is absent or escapes its bundle."
            )
        data = _bounded_file(folder, artifact)
        if (
            hashlib.sha256(data).hexdigest() != row["sha256"]
            or sums.get(row["path"]) != row["sha256"]
        ):
            raise ValueError(
                "Installed recovery artifact differs from its bound digest."
            )
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ValueError(
                "Installed recovery artifacts exceed their combined bound."
            )
        retained[row["role"]] = data
    states = fictional_states(source)
    _phases(retained["phases"], states)
    for branch in ("clipboard", "manual"):
        if retained[branch + "_reference"] != retained[branch + "_text"] or not _equal(
            json_object(retained[branch + "_text"]), states["working"]
        ):
            raise ValueError("Installed recovery backup text is incomplete or changed.")
        selected = receipt["offline"][branch]
        # JavaScript textarea offsets count UTF-16 units, including surrogate pairs.
        length = (
            len(retained[branch + "_text"].decode("utf-8").encode("utf-16-le")) // 2
        )
        if (
            selected["textarea_selection_start"] != 0
            or selected["textarea_selection_end"] != length
        ):
            raise ValueError(
                "Installed recovery did not select the complete backup text."
            )
    _csv(retained["held_csv"], states["held"])
    for role, phase in (
        ("held_calendar", "held"),
        ("resumed_closed_calendar", "resumed_closed"),
        ("resumed_calendar", "resumed"),
    ):
        _calendar(retained[role], states[phase])
    for role, data in retained.items():
        if role.endswith("_screen"):
            validate_png(data)
    expected_inputs = {"garden_campaign": canonical_hash(states["original"])}
    expected_results = {phase: canonical_hash(states[phase]) for phase in PHASES}
    expected_results["working_copy"] = canonical_hash(states["working"])
    if not _equal(receipt["input_hashes"], expected_inputs) or not _equal(
        receipt["result_hashes"], expected_results
    ):
        raise ValueError(
            "Installed recovery hashes do not bind complete source/current payloads."
        )
