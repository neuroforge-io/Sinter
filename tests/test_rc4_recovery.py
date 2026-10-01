"""Synthetic closed-contract and real local-file tests, not installed proof."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_installed_workflow_qualification import png

from sinter import community
from tools import installed_recovery_contract as old
from tools import rc4_recovery_contract as contract
from tools import rc4_recovery_source as producer
from tools import rc4_recovery_worker as worker
from tools.installed_menu_browser import browser_notice
from tools.installed_workflow_qualification import canonical_hash


def write(path, value):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def reseal(folder):
    path = folder / contract.RECEIPT
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["artifacts"] = {
        name: {
            "bytes": (folder / name).stat().st_size,
            "sha256": contract.digest(folder / name),
        }
        for name in contract.ARTIFACTS
        if (folder / name).is_file()
    }
    write(path, receipt)


@pytest.fixture
def rehearsal(tmp_path):
    """Synthesized six-row evidence exercises refusal, never a real process claim."""
    data = tmp_path / "data"
    seeded = worker.seed(data)
    version = __import__("sinter").__version__
    marker = {
        "version": version,
        "frozen": False,
        "provider_attempts": 0,
        "external_attempts": 0,
        "scheduler_paused": True,
        "OS_browser_tested": False,
        "seed": seeded,
    }
    folder = tmp_path / "proof"
    folder.mkdir()
    states = old.fictional_states(
        {old.CAMPAIGN_SOURCE: (producer.ROOT / old.CAMPAIGN_SOURCE).read_bytes()}
    )
    offsets = {
        "held": 1,
        "reopened_held": 1,
        "held_closed": 2,
        "resumed_closed": 3,
        "resumed": 4,
        "original_after_clipboard_restore": 4,
        "original_after_manual_restore": 4,
    }
    phases = {
        phase: {
            "id": "c" * 32,
            "revision": 1 + offsets.get(phase, 0),
            "document": copy.deepcopy(states[phase]),
        }
        for phase in old.PHASES
    }
    phases["restored_clipboard"]["id"] = "d" * 32
    phases["restored_manual"]["id"] = "e" * 32
    payload = json.dumps(states["working"], ensure_ascii=False, indent=2).encode()
    for role, name in old.ARTIFACT_PATHS.items():
        path = folder / name
        path.parent.mkdir(exist_ok=True, parents=True)
        if role == "phases":
            write(path, phases)
        elif role.endswith("reference") or role.endswith("text"):
            path.write_bytes(payload)
        elif role == "held_csv" or role.endswith("calendar"):
            phase = {
                "held_csv": "held",
                "held_calendar": "held",
                "resumed_closed_calendar": "resumed_closed",
                "resumed_calendar": "resumed",
            }[role]
            rows = old._plan_rows(states[phase])
            if role.endswith("calendar"):
                rows = [
                    r
                    for r in rows
                    if r["due"]
                    and r["status"] != "held"
                    and not r["scope"].startswith("Historical · ")
                ]
            path.write_text(
                community.plan(states[phase]["title"], rows)[
                    "csv" if role == "held_csv" else "calendar"
                ],
                encoding="utf-8",
                newline="",
            )
        else:
            path.write_bytes(png())
    imported = {**states["resumed"], "title": contract.UNCERTAIN_TITLE}
    base = {"id": "f" * 32, "revision": 1, "document": imported}
    local = {**imported, "objective": imported["objective"] + contract.LOCAL_NOTE}
    other = {**imported, "objective": imported["objective"] + contract.OTHER_NOTE}
    current = {**base, "revision": 2, "document": other}
    working = {**other, "objective": other["objective"] + contract.SAVE_NOTE}
    actual = {**current, "revision": 3, "document": working}
    dirty = {**working, "objective": working["objective"] + contract.QUIT_NOTE}
    advanced = {
        "stale_source": {
            "stored_mark": imported["requirements"][1]["status"],
            "registered_date": imported["sources"][0]["checked_at"],
            "excerpt_checked_date": imported["requirements"][1]["checked_at"],
            "warning_visible": True,
            "stored_original_preserved": True,
        },
        "conflict": {
            "base": base,
            "other_saved": current,
            "local_document": local,
            "failed_save_posts": 1,
            "stored_original_preserved": True,
        },
        "uncertain_save": {
            "before": current,
            "actual_saved": actual,
            "working_document": working,
            "actual_status": 200,
            "reported_status": 503,
            "save_posts": 1,
            "automatic_replays": 0,
        },
        "uncertain_quit": {
            "working_document": dirty,
            "keep_working_posts": 0,
            "keep_working_retained_input": True,
            "actual_status": 200,
            "reported_status": 503,
            "quit_posts": 1,
            "automatic_replays": 0,
            "input_retained_after_stop": True,
        },
        "reopened_uncertain_save": actual,
        "external_requests": 0,
        "page_errors": 0,
        "browser_dialogs": 0,
    }
    for name, value in {
        "control-import": imported,
        "conflict-backup": local,
        "actual-save-response": actual,
        "uncertain-save-backup": working,
        "actual-quit-response": {"ok": True},
        "uncertain-quit-backup": dirty,
        "observations": advanced,
    }.items():
        write(folder / f"advanced/{name}.json", value)
    for name in ("conflict", "uncertain-quit", "stale-source"):
        (folder / f"advanced/{name}.png").write_bytes(png())
    write(folder / "seed-control.json", marker)
    for name in ("seed.stdout", "seed.stderr"):
        (folder / name).write_bytes(b"")
    rows = []
    notice = browser_notice((producer.ROOT / "src/sinter/desktop.py").read_bytes())
    for n in range(1, 7):
        row = {
            "run": n,
            "pid": 100 + n,
            "returncode": 0,
            "stop_method": "terminate" if n in (2, 3) else "interface_quit",
            "port_closed": True,
            "persistent_snapshot": copy.deepcopy(seeded["snapshot"]),
            "control": {**marker, "seed": None},
        }
        for name, raw in (
            ("stdout", b"source-only synthetic output\n"),
            ("stderr", notice),
        ):
            path = folder / f"process/run-{n}.{name}"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(raw)
            row[name] = producer.capture_stream(path)
        write(folder / f"process/run-{n}.json", row["control"])
        rows.append(row)
    table = rows[-1]["persistent_snapshot"]["databases"]["campaigns.sqlite3"]["tables"][
        "campaigns"
    ]
    table["rows"] = [
        [
            w["id"],
            w["revision"],
            w["document"]["title"],
            "synthetic stamp",
            json.dumps(w["document"], ensure_ascii=False),
        ]
        for w in (
            phases["resumed"],
            phases["restored_clipboard"],
            phases["restored_manual"],
            actual,
        )
    ]
    write(folder / "processes.json", {"rows": rows, "failure": None, "closed": True})
    length = len(payload.decode().encode("utf-16-le")) // 2
    write(
        folder / "base-observations.json",
        {
            "processes": [
                {
                    "run": row["run"],
                    "pid": row["pid"],
                    "executable": sys.executable,
                    "binary_sha256": producer.digest(Path(sys.executable)),
                    "stop_method": row["stop_method"],
                    "returncode": row["returncode"],
                }
                for row in rows[:4]
            ],
            "offline": {
                branch: {
                    "mode": "written" if branch == "clipboard" else "denied",
                    "save_connection_refusals": 1,
                    "backup_network_requests": 0,
                    "write_attempts": 1,
                    "write_successes": 1 if branch == "clipboard" else 0,
                    "notice": old.COPY_NOTICE
                    if branch == "clipboard"
                    else old.MANUAL_NOTICE,
                    "textarea_selection_start": 0,
                    "textarea_selection_end": length,
                }
                for branch in ("clipboard", "manual")
            },
            "page_errors": 0,
            "external_requests": 0,
            "result_hashes": {
                **{
                    phase: canonical_hash(phases[phase]["document"])
                    for phase in old.PHASES
                },
                "working_copy": canonical_hash(states["working"]),
            },
        },
    )
    receipt = {
        "schema": contract.SCHEMA,
        "execution": "source",
        "profile": "rc4-local-campaign-recovery",
        "source_base_commit": "a" * 40,
        "observed_version": version,
        "source_manifest_sha256": "b" * 64,
        "source_files_sha256": {"synthetic": "c" * 64},
        "candidate_admitted": False,
        "installed_tested": False,
        "release_qualified": False,
        "source_rehearsal_passed": True,
        "resources": {
            "browser_closed": True,
            "source_processes_stopped": True,
            "outer_relay_closed": True,
            "inner_relay_closed": True,
        },
        "failure": None,
        "artifacts": {},
        "source_files_conserved": True,
    }
    write(folder / contract.RECEIPT, receipt)
    reseal(folder)
    return folder


def verify(folder):
    return contract.validate_rehearsal(
        folder, {"synthetic": "c" * 64}, "a" * 40, "b" * 64
    )


def mutate(folder, path, callback):
    full = folder / path
    value = json.loads(full.read_text(encoding="utf-8"))
    callback(value)
    write(full, value)
    reseal(folder)


def test_complete_synthetic_source_contract_and_historical_policy(rehearsal):
    result = verify(rehearsal)
    assert result["source_rehearsal_passed"] is True
    assert result["installed_tested"] is result["release_qualified"] is False
    assert old.SCHEMA == "sinter-installed-recovery/v1" and old.VERSION == "0.5.4rc3"


@pytest.mark.parametrize(
    "field", ["candidate_admitted", "installed_tested", "release_qualified"]
)
def test_source_result_cannot_claim_installed_or_release(rehearsal, field):
    mutate(rehearsal, contract.RECEIPT, lambda value: value.update({field: True}))
    with pytest.raises(ValueError, match="installed"):
        verify(rehearsal)


@pytest.mark.parametrize(
    "role", ["clipboard_reference", "clipboard_text", "manual_reference", "manual_text"]
)
def test_full_payload_cannot_be_truncated_or_rewritten(rehearsal, role):
    path = rehearsal / old.ARTIFACT_PATHS[role]
    path.write_bytes(path.read_bytes()[:-8])
    reseal(rehearsal)
    with pytest.raises(ValueError, match="backup"):
        verify(rehearsal)


@pytest.mark.parametrize(
    "mutation", ["owner", "date", "source", "held", "closed", "restore_id"]
)
def test_source_phase_semantics_remain_literal(rehearsal, mutation):
    def edit(value):
        if mutation == "owner":
            value["held"]["document"]["actions"][1]["owner_confirmed"] = True
        elif mutation == "date":
            value["held"]["document"]["opportunities"][0]["deadline"] = "2026-10-09"
        elif mutation == "source":
            value["resumed"]["document"]["sources"][0]["notes"] += (
                " forged current evidence"
            )
        elif mutation == "held":
            value["held"]["document"]["actions"][1]["status"] = "open"
        elif mutation == "closed":
            value["resumed_closed"]["document"]["opportunities"][0]["status"] = (
                "clarification"
            )
        else:
            value["restored_clipboard"]["id"] = value["initial"]["id"]

    mutate(rehearsal, old.ARTIFACT_PATHS["phases"], edit)
    with pytest.raises(ValueError):
        verify(rehearsal)


@pytest.mark.parametrize(
    "key", ["user_version", "application_id", "encoding", "page_size"]
)
def test_live_metadata_mutation_before_reopen_is_refused(rehearsal, key):
    def edit(value):
        metadata = value["rows"][1]["persistent_snapshot"]["databases"][
            "workspace.sqlite3"
        ]["metadata"]
        metadata[key] = "UTF-16le" if key == "encoding" else metadata[key] + 1

    mutate(rehearsal, "processes.json", edit)
    with pytest.raises(ValueError, match="protected"):
        verify(rehearsal)


@pytest.mark.parametrize(
    "mutation",
    ["preferences", "history", "diagnostics", "closed_port", "base_pid", "hash"],
)
def test_actual_source_identity_and_originals_are_required(rehearsal, mutation):
    if mutation == "diagnostics":
        (rehearsal / "process/run-3.stderr").write_bytes(b"Exception in Tk callback\n")
        raw = rehearsal / "process/run-3.stderr"
        mutate(
            rehearsal,
            "processes.json",
            lambda v: v["rows"][2].update(stderr=producer.capture_stream(raw)),
        )
    elif mutation == "base_pid":
        mutate(
            rehearsal,
            "base-observations.json",
            lambda v: v["processes"][0].update(pid=999),
        )
    elif mutation == "hash":
        mutate(
            rehearsal,
            "base-observations.json",
            lambda v: v["result_hashes"].update(working_copy="f" * 64),
        )
    else:

        def edit(value):
            row = value["rows"][2]
            if mutation == "preferences":
                row["persistent_snapshot"]["preferences"]["model"] = "other-model"
            elif mutation == "history":
                row["persistent_snapshot"]["databases"]["workspace.sqlite3"]["tables"][
                    "reports"
                ]["rows"].clear()
            else:
                row["port_closed"] = False

        mutate(rehearsal, "processes.json", edit)
    with pytest.raises(ValueError):
        verify(rehearsal)


@pytest.mark.parametrize(
    "mutation",
    [
        "save_replay",
        "quit_replay",
        "lost_input",
        "other_original",
        "bool_revision",
        "false_confirmed",
    ],
)
def test_uncertain_and_conflicting_work_cannot_be_reinterpreted(rehearsal, mutation):
    def edit(value):
        if mutation == "save_replay":
            value["uncertain_save"]["automatic_replays"] = 1
        elif mutation == "quit_replay":
            value["uncertain_quit"]["automatic_replays"] = 1
        elif mutation == "lost_input":
            value["uncertain_quit"]["input_retained_after_stop"] = False
        elif mutation == "other_original":
            value["conflict"]["other_saved"]["document"]["objective"] += (
                " discarded correction"
            )
        elif mutation == "bool_revision":
            value["conflict"]["base"]["revision"] = True
        else:
            value["uncertain_save"]["reported_status"] = 200

    mutate(rehearsal, "advanced/observations.json", edit)
    with pytest.raises(ValueError):
        verify(rehearsal)


def test_foreign_artifact_or_missing_process_is_not_hidden(rehearsal):
    (rehearsal / "private-note.txt").write_text("foreign", encoding="utf-8")
    with pytest.raises(ValueError, match="foreign"):
        verify(rehearsal)


@pytest.mark.parametrize("args,code", [(["--help"], 0), ([], 2)])
def test_source_help_requires_no_optional_browser(args, code):
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(producer.ROOT / "tools/rc4_recovery_source.py"),
            *args,
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == code
    assert b"usage:" in result.stdout + result.stderr
    assert b"Traceback" not in result.stderr


def test_source_verification_is_complete_before_any_output(tmp_path, monkeypatch):
    root = tmp_path / "source"
    (root / "src/sinter").mkdir(parents=True)
    (root / "src/sinter/__init__.py").write_text('__version__ = "0.5.4rc4.dev0"\n')
    files = {"src/sinter/__init__.py": producer.digest(root / "src/sinter/__init__.py")}
    manifest = tmp_path / "manifest.json"
    write(manifest, {"base_commit": "a" * 40, "files": files})
    args = argparse.Namespace(
        source_manifest=manifest,
        source_manifest_sha256=producer.digest(manifest),
        source_commit="a" * 40,
        output=tmp_path / "proof",
    )
    monkeypatch.setattr(producer, "ROOT", root)
    assert producer.verify_source(args)["files"] == files
    assert not args.output.exists()
    (root / "unlisted.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        producer.verify_source(args)
    assert not args.output.exists()


def test_stream_capture_counts_and_hashes_full_non_utf8_file(tmp_path):
    path = tmp_path / "stderr"
    raw = b" \xff" * 40000
    path.write_bytes(raw)
    captured = producer.capture_stream(path)
    assert captured["bytes"] == len(raw)
    assert captured["sha256"] == hashlib.sha256(raw).hexdigest()
    assert base64.b64decode(captured["sample_base64"]) == raw[:65536]
    assert captured["sample_complete"] is False


@pytest.mark.parametrize("fault", ["snapshot", "stop", "relay_close"])
def test_process_streams_survive_body_and_cleanup_observation_faults(
    tmp_path, monkeypatch, fault
):
    import threading

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    output = tmp_path / "output"
    (output / "process").mkdir(parents=True)
    seeded = worker.seed(runtime / "data")
    (runtime / "home").mkdir()
    notice = browser_notice((producer.ROOT / "src/sinter/desktop.py").read_bytes())
    identity = {
        "notice": notice,
        "version": "source-only",
        "binary_sha256": "a" * 64,
        "web": {},
    }
    closed = threading.Event()

    class Inner:
        def __init__(self, _):
            self.port = 1

        def serve_forever(self):
            closed.wait(1)

        def shutdown(self):
            closed.set()

        def server_close(self):
            if fault == "relay_close":
                raise OSError("owned relay cleanup fault")

    class Process:
        pid = 123
        returncode = 0

        def __init__(self, command, **kwargs):
            kwargs["stdout"].write(b"owned child output\n")
            kwargs["stderr"].write(notice)
            Path(command[command.index("--launch-url") + 1]).write_text(
                "http://127.0.0.1:1", encoding="utf-8"
            )
            write(Path(command[command.index("--control") + 1]), {"synthetic": True})

        def poll(self):
            return 0

    monkeypatch.setattr(producer.transport, "InnerRelay", Inner)
    monkeypatch.setattr(producer.subprocess, "Popen", Process)
    actual_snapshot = producer.snapshot
    snapshots = []

    def observed(directory):
        snapshots.append(directory)
        if fault == "snapshot" and len(snapshots) == 2:
            raise OSError("before-reopen raw observation fault")
        return actual_snapshot(directory)

    monkeypatch.setattr(producer, "snapshot", observed)

    def stop(_):
        if fault == "stop":
            raise OSError("already stopped cleanup fault")

    monkeypatch.setattr(producer.legacy, "stop_owned", stop)
    write(runtime / "control.json", {"action": "cleanup"})
    lifecycle = producer.SourceLifecycle(
        runtime, output, identity, worker.protected(seeded["snapshot"])
    )
    lifecycle.run()
    retained = json.loads((output / "processes.json").read_text(encoding="utf-8"))
    assert retained["closed"] is True
    assert retained["failure"] and (
        "observation" in retained["failure"]
        if fault == "snapshot"
        else "cleanup" in retained["failure"]
    )
    assert len(retained["rows"]) == 1
    row = retained["rows"][0]
    assert base64.b64decode(row["stderr"]["sample_base64"]) == notice
    assert row["stderr"]["bytes"] == len(notice)
    assert base64.b64decode(row["stdout"]["sample_base64"]) == b"owned child output\n"
    assert (output / "process/run-1.stderr").read_bytes() == notice


def test_optimisation_cannot_bypass_browser_observations(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-O",
            str(producer.ROOT / "tools/rc4_recovery_source.py"),
            "--source-manifest",
            str(tmp_path / "missing.json"),
            "--source-manifest-sha256",
            "a" * 64,
            "--source-commit",
            "b" * 40,
            "--output",
            str(tmp_path / "proof"),
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert b"without Python optimisation" in result.stderr
    assert not (tmp_path / "proof").exists()


def test_stale_source_notice_cannot_be_turned_into_a_current_review(rehearsal):
    mutate(
        rehearsal,
        "advanced/observations.json",
        lambda value: value["stale_source"].update(warning_visible=False),
    )
    with pytest.raises(ValueError, match="Stale"):
        verify(rehearsal)


def test_diagnostic_sample_cannot_hide_full_stderr(rehearsal):
    mutate(
        rehearsal,
        "processes.json",
        lambda value: value["rows"][3]["stderr"].update(bytes=0, sample_base64=""),
    )
    with pytest.raises(ValueError, match="capture"):
        verify(rehearsal)


def test_final_raw_rows_cannot_drop_an_original_even_with_valid_restore_phase(
    rehearsal,
):
    def edit(value):
        table = value["rows"][-1]["persistent_snapshot"]["databases"][
            "campaigns.sqlite3"
        ]["tables"]["campaigns"]
        table["rows"].pop(0)

    mutate(rehearsal, "processes.json", edit)
    with pytest.raises(ValueError, match="Cold reopen"):
        verify(rehearsal)


def _windows_text_defaults(monkeypatch):
    """Map omitted text settings to the observed Windows cp1252/CRLF defaults."""
    actual_open = Path.open

    def mapped_open(
        path, mode="r", buffering=-1, encoding=None, errors=None, newline=None
    ):
        if "b" not in mode:
            if encoding in (None, "locale"):
                encoding = "cp1252"
            if newline is None and any(flag in mode for flag in ("w", "a", "x")):
                newline = "\r\n"
        return actual_open(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", mapped_open)


def test_owned_json_retains_literal_originals_under_windows_text_defaults(
    tmp_path, monkeypatch
):
    seeded = worker.seed(tmp_path / "data")
    original = copy.deepcopy(seeded["snapshot"])
    value = {
        "rows": [{"persistent_snapshot": original}],
        "failure": "Fictional cleanup — e\u0301 🐝",
        "closed": True,
    }
    expected = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    path = tmp_path / "processes.json"
    previous = b"original receipt remains until replacement"
    path.write_bytes(previous)
    _windows_text_defaults(monkeypatch)
    # Retain the observed old default failure; do not alter the legacy helper.
    with pytest.raises(UnicodeEncodeError):
        producer.transport.write_json(path, value)
    assert path.read_bytes() == previous
    producer.write_json(path, value)
    assert path.read_bytes() == expected
    assert b"\r\n" not in expected and "e\u0301 🐝".encode("utf-8") in expected
    assert json.loads(path.read_bytes()) == value
    assert not path.with_suffix(".tmp").exists()
    assert seeded["snapshot"] == original


@pytest.mark.parametrize("fault", ["snapshot", "stop", "relay_close"])
def test_cleanup_proof_survives_windows_text_defaults(tmp_path, monkeypatch, fault):
    _windows_text_defaults(monkeypatch)
    test_process_streams_survive_body_and_cleanup_observation_faults(
        tmp_path, monkeypatch, fault
    )
