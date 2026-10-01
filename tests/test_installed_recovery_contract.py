"""Synthetic/resealed gate fixtures; no installer or process execution claimed."""

from __future__ import annotations

import copy
import json

import pytest
from test_candidate_release import bundle as bundle
from test_candidate_release import seal, write_json
from test_installed_workflow_qualification import completed as completed
from test_installed_workflow_qualification import png, source_files

from sinter import community
from tools import candidate_qualification as qualification
from tools import candidate_release as candidate
from tools import installed_recovery_contract as recovery
from tools.installed_workflow_qualification import canonical_hash

VERSION = "0.5.4rc3"
pytestmark = pytest.mark.parametrize("bundle", [VERSION], indirect=True)


def plan(document, *, calendar=False):
    rows = recovery._plan_rows(document)
    if calendar:
        rows = [
            row
            for row in rows
            if row["due"]
            and row["status"] != "held"
            and not row["scope"].startswith("Historical · ")
        ]
    return community.plan(document["title"], rows)


def reseal(folder):
    path = folder / recovery.RECEIPT_PATH
    receipt = json.loads(path.read_text())
    for row in receipt["artifacts"]:
        path = folder / row["path"]
        if path.is_file():
            row.update(sha256=candidate.digest(path), bytes=path.stat().st_size)
    write_json(folder / recovery.RECEIPT_PATH, receipt)
    seal(folder)


@pytest.fixture
def recovered(completed):
    folder, _, _, commit = completed
    source = source_files(folder, VERSION)
    states = recovery.fictional_states(source)
    phases = {}
    offsets = {
        "initial": 0,
        "held": 1,
        "reopened_held": 1,
        "held_closed": 2,
        "resumed_closed": 3,
        "resumed": 4,
        "original_after_clipboard_restore": 4,
        "original_after_manual_restore": 4,
    }
    for phase in recovery.PHASES:
        phases[phase] = {
            "id": "c" * 32,
            "revision": 1 + offsets.get(phase, 0),
            "document": copy.deepcopy(states[phase]),
        }
    phases["restored_clipboard"].update(id="d" * 32, revision=1)
    phases["restored_manual"].update(id="e" * 32, revision=1)
    working = json.dumps(states["working"], ensure_ascii=False, indent=2).encode()
    for role, name in recovery.ARTIFACT_PATHS.items():
        path = folder / name
        path.parent.mkdir(exist_ok=True)
        if role == "phases":
            write_json(path, phases)
        elif role in {
            "clipboard_reference",
            "clipboard_text",
            "manual_reference",
            "manual_text",
        }:
            path.write_bytes(working)
        elif role == "held_csv":
            path.write_text(plan(states["held"])["csv"], newline="")
        elif role.endswith("_calendar"):
            phase = {
                "held_calendar": "held",
                "resumed_closed_calendar": "resumed_closed",
                "resumed_calendar": "resumed",
            }[role]
            path.write_text(plan(states[phase], calendar=True)["calendar"], newline="")
        else:
            path.write_bytes(png())
    workflow = json.loads((folder / "installed-workflow-browser.json").read_text())
    binary_sha = workflow["installed_binary_sha256"]
    length = len(working.decode().encode("utf-16-le")) // 2
    receipt = {
        "schema": recovery.SCHEMA,
        "version": VERSION,
        "source_commit": commit,
        **{
            key: workflow[key]
            for key in (
                "installer_sha256",
                "source_archive_sha256",
                "native_receipt_sha256",
                "installed_binary_sha256",
            )
        },
        "installed_workflow_receipt_sha256": candidate.digest(
            folder / "installed-workflow-browser.json"
        ),
        "runtime": {key: workflow[key] for key in recovery.RUNTIME_FIELDS},
        "processes": [
            {
                "run": number,
                "pid": 100 + number,
                "executable": "/opt/neuroforge/sinter/Sinter",
                "binary_sha256": binary_sha,
                "stop_method": "interface_quit" if number in {1, 4} else "terminate",
                "returncode": 0,
            }
            for number in range(1, 5)
        ],
        "offline": {
            branch: {
                "mode": "written" if branch == "clipboard" else "denied",
                "save_connection_refusals": 1,
                "backup_network_requests": 0,
                "write_attempts": 1,
                "write_successes": 1 if branch == "clipboard" else 0,
                "notice": recovery.COPY_NOTICE
                if branch == "clipboard"
                else recovery.MANUAL_NOTICE,
                "textarea_selection_start": 0,
                "textarea_selection_end": length,
            }
            for branch in ("clipboard", "manual")
        },
        "artifacts": [
            {
                "role": role,
                "path": name,
                "sha256": candidate.digest(folder / name),
                "bytes": (folder / name).stat().st_size,
            }
            for role, name in recovery.ARTIFACT_PATHS.items()
        ],
        "input_hashes": {"garden_campaign": canonical_hash(states["original"])},
        "result_hashes": {
            **{phase: canonical_hash(states[phase]) for phase in recovery.PHASES},
            "working_copy": canonical_hash(states["working"]),
        },
    }
    write_json(folder / recovery.RECEIPT_PATH, receipt)
    seal(folder)
    return completed


def verify(recovered):
    return qualification.verify_candidate(
        *recovered[:2], VERSION, recovered[3], recovered[2]
    )


def test_rc3_has_exact_three_priors_and_closed_roles(bundle):
    assert [prior.version for prior in qualification.candidate_priors(VERSION)] == [
        "0.5.3",
        "0.5.4rc1",
        "0.5.4rc2",
    ]
    assert qualification.prior_roles(qualification.QUALIFIED_PRIORS["0.5.4rc2"]) == (
        "published-rc2-source-verification.json",
        "published-rc2-SHA256SUMS.txt",
        "published-rc2-copied-upgrade-test.json",
        "published-rc2-native-installer-upgrade-test.json",
    )
    with pytest.raises(ValueError):
        qualification.prior_roles(
            qualification.QUALIFIED_PRIORS["0.5.3"]._replace(source_commit="f" * 40)
        )
    with pytest.raises(ValueError):
        qualification.candidate_priors("0.5.4rc4")


def test_complete_synthetic_rc3_admission_and_local_stage(recovered, tmp_path):
    assert verify(recovered)["installed_and_upgrade_evidence"] is True
    path = candidate.prepare(
        *recovered[:2], tmp_path / "stage", VERSION, recovered[3], recovered[2]
    )
    assert candidate.verify_plan(path, recovered[2])["source_commit"] == recovered[3]
    notes = candidate.release_notes(VERSION, recovered[3])
    assert all(
        name in notes
        for name in (
            "v0.5.3",
            "v0.5.4rc1",
            "v0.5.4rc2",
            "installed-recovery/v1",
            "On hold",
        )
    )
    assert "not certified" in notes and "single trusted" in notes
    with pytest.raises(ValueError, match="notes policy"):
        candidate.release_notes("0.5.4rc4", recovered[3])


@pytest.mark.parametrize("role", list(recovery.ARTIFACT_PATHS))
def test_rc3_rejects_missing_mandatory_artifact_even_after_resealing(recovered, role):
    (recovered[0] / recovery.ARTIFACT_PATHS[role]).unlink()
    reseal(recovered[0])
    with pytest.raises(ValueError, match="artifact roles"):
        verify(recovered)


@pytest.mark.parametrize("prior", ["0.5.3", "0.5.4rc1", "0.5.4rc2"])
def test_rc3_cannot_omit_any_original_upgrade_route(recovered, prior):
    filename = qualification.prior_roles(qualification.QUALIFIED_PRIORS[prior])[2]
    (recovered[0] / filename).unlink()
    reseal(recovered[0])
    with pytest.raises(ValueError, match="artifact roles"):
        verify(recovered)


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "date",
        "quote",
        "missing_action",
        "stale_mark",
        "historical",
        "auto_resume",
        "reopened_revision",
        "rewrite_original",
        "replace_original",
        "copy_revision",
    ],
)
def test_resealed_phase_forgery_is_refused(recovered, mutation):
    path = recovered[0] / recovery.ARTIFACT_PATHS["phases"]
    phases = json.loads(path.read_text())
    document = phases["held"]["document"]
    if mutation == "owner":
        document["actions"][1]["owner_confirmed"] = True
    elif mutation == "date":
        document["actions"][1]["due"] = "2026-10-10"
    elif mutation == "quote":
        document["sources"][0]["notes"] += " rewritten"
    elif mutation == "missing_action":
        document["actions"].pop(0)
    elif mutation == "stale_mark":
        document["requirements"][1]["status"] = "unknown"
    elif mutation == "historical":
        document["answers"][0]["text"] = "Overwritten history"
    elif mutation == "auto_resume":
        phases["reopened_held"]["document"]["actions"][1]["status"] = "open"
    elif mutation == "reopened_revision":
        phases["reopened_held"]["revision"] += 1
    elif mutation == "rewrite_original":
        phases["original_after_manual_restore"]["document"]["objective"] += (
            recovery.OFFLINE_NOTE
        )
    elif mutation == "replace_original":
        phases["restored_manual"]["id"] = phases["initial"]["id"]
    elif mutation == "copy_revision":
        phases["restored_clipboard"]["revision"] = 2
    write_json(path, phases)
    reseal(recovered[0])
    with pytest.raises(ValueError):
        verify(recovered)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_evidence",
        "truncated",
        "differing_text",
        "oversized",
        "invented_control",
        "source_reordered",
    ],
)
def test_resealed_backup_capture_must_remain_complete(recovered, mutation):
    folder = recovered[0]
    reference = folder / recovery.ARTIFACT_PATHS["manual_reference"]
    text = folder / recovery.ARTIFACT_PATHS["manual_text"]
    document = json.loads(text.read_text())
    if mutation == "missing_evidence":
        document["sources"].pop()
    elif mutation == "invented_control":
        document["actions"][-1]["owner_kind"] = "person"
    elif mutation == "source_reordered":
        document["sources"].reverse()
    elif mutation == "differing_text":
        text.write_text(text.read_text() + "\n")
    elif mutation == "truncated":
        text.write_bytes(text.read_bytes()[:-1])
    elif mutation == "oversized":
        text.write_bytes(b" " * (recovery.MAX_ARTIFACT_BYTES + 1))
    if mutation in {"missing_evidence", "invented_control", "source_reordered"}:
        write_json(reference, document)
        write_json(text, document)
    reseal(folder)
    with pytest.raises(ValueError):
        verify(recovered)


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "written"),
        ("write_successes", 1),
        ("save_connection_refusals", 0),
        ("backup_network_requests", 1),
        ("write_attempts", True),
        ("notice", "Saved to a file"),
        ("textarea_selection_end", 2),
    ],
)
def test_manual_branch_cannot_claim_a_file_save_or_false_clipboard_success(
    recovered, field, value
):
    path = recovered[0] / recovery.RECEIPT_PATH
    receipt = json.loads(path.read_text())
    receipt["offline"]["manual"][field] = value
    write_json(path, receipt)
    reseal(recovered[0])
    with pytest.raises(ValueError):
        verify(recovered)


def test_unavailable_clipboard_branch_is_explicit_and_has_no_write_attempt(recovered):
    path = recovered[0] / recovery.RECEIPT_PATH
    receipt = json.loads(path.read_text())
    receipt["offline"]["manual"].update(mode="unavailable", write_attempts=0)
    write_json(path, receipt)
    reseal(recovered[0])
    verify(recovered)


@pytest.mark.parametrize(
    "mutation",
    [
        "held_present",
        "closed_present",
        "control_missing",
        "owner_accepted",
        "date_confirmed",
        "scope_changed",
        "phase_changed",
        "duplicate",
        "csv_done",
    ],
)
def test_actual_calendar_and_csv_semantics_are_required(recovered, mutation):
    folder = recovered[0]
    states = recovery.fictional_states(source_files(folder, VERSION))
    held = folder / recovery.ARTIFACT_PATHS["held_calendar"]
    if mutation == "held_present":
        held.write_text(plan(states["resumed"], calendar=True)["calendar"], newline="")
    elif mutation == "closed_present":
        (folder / recovery.ARTIFACT_PATHS["resumed_closed_calendar"]).write_text(
            plan(states["resumed"], calendar=True)["calendar"], newline=""
        )
    elif mutation == "control_missing":
        held.write_text(
            "BEGIN:VCALENDAR\nVERSION:2.0\n"
            "PRODID:-//NeuroForge//Sinter user plan//EN\n"
            "CALSCALE:GREGORIAN\nEND:VCALENDAR\n"
        )
    elif mutation == "csv_done":
        path = folder / recovery.ARTIFACT_PATHS["held_csv"]
        path.write_text(path.read_text().replace(",held", ",done"))
    else:
        text = held.read_text()
        if mutation == "owner_accepted":
            text = text.replace("owner type not confirmed", "accepted owner")
        elif mutation == "date_confirmed":
            text = text.replace("unconfirmed", "confirmed")
        elif mutation == "scope_changed":
            text = text.replace("Campaign-wide", "Unsupported route")
        elif mutation == "phase_changed":
            text = text.replace("Not applicable", "After submission")
        elif mutation == "duplicate":
            text = text.replace(
                "END:VEVENT",
                "END:VEVENT\n"
                + text[
                    text.index("BEGIN:VEVENT") : text.index("END:VEVENT")
                    + len("END:VEVENT")
                ],
            )
        held.write_text(text, newline="")
    reseal(folder)
    with pytest.raises(ValueError):
        verify(recovered)


@pytest.mark.parametrize(
    "mutation",
    [
        "same_pid",
        "no_exit",
        "wrong_binary",
        "wrong_installer",
        "runtime_network",
        "extra_field",
        "workflow_resealed",
    ],
)
def test_observed_process_and_exact_installed_identity_are_required(
    recovered, mutation
):
    folder = recovered[0]
    path = folder / recovery.RECEIPT_PATH
    receipt = json.loads(path.read_text())
    if mutation == "same_pid":
        receipt["processes"][1]["pid"] = receipt["processes"][0]["pid"]
    elif mutation == "no_exit":
        receipt["processes"][1]["returncode"] = None
    elif mutation == "wrong_binary":
        receipt["processes"][3]["binary_sha256"] = "f" * 64
    elif mutation == "wrong_installer":
        receipt["installer_sha256"] = "f" * 64
    elif mutation == "runtime_network":
        receipt["runtime"]["network_mode"] = "bridge"
    elif mutation == "extra_field":
        receipt["passed"] = True
    elif mutation == "workflow_resealed":
        receipt["installed_workflow_receipt_sha256"] = "f" * 64
    write_json(path, receipt)
    reseal(folder)
    with pytest.raises(ValueError):
        verify(recovered)


def test_rc2_rich_prior_check_cannot_be_silently_skipped(recovered):
    filename = qualification.prior_roles(qualification.QUALIFIED_PRIORS["0.5.4rc2"])[3]
    path = recovered[0] / filename
    receipt = json.loads(path.read_text())
    receipt["candidate_native_checks"] = [
        check
        for check in receipt["candidate_native_checks"]
        if not check.startswith("rich prior")
    ]
    write_json(path, receipt)
    reseal(recovered[0])
    with pytest.raises(ValueError, match="preservation"):
        verify(recovered)


def test_extra_unqualified_product_cannot_hide_in_recovery_folder(recovered):
    (recovered[0] / "installed-recovery/windows.exe").write_bytes(b"not qualified")
    reseal(recovered[0])
    with pytest.raises(ValueError, match="artifact roles"):
        verify(recovered)


@pytest.mark.parametrize("prior_field", ["source", "installer", "archive", "package"])
def test_matching_forged_rc2_prior_documents_do_not_replace_published_pin(
    recovered, prior_field
):
    folder = recovered[0]
    prior = qualification.QUALIFIED_PRIORS["0.5.4rc2"]
    source_name, sums_name, copied_name, native_name = qualification.prior_roles(prior)
    for name in (source_name, copied_name, native_name):
        path = folder / name
        row = json.loads(path.read_text())
        if prior_field == "source":
            row["source_commit" if name == source_name else "prior_source_commit"] = (
                "f" * 40
            )
        elif prior_field == "archive":
            row[
                "archive_sha256"
                if name == source_name
                else "prior_source_archive_sha256"
            ] = "f" * 64
        elif prior_field == "installer" and name == native_name:
            row["prior_installer_sha256"] = "f" * 64
        elif prior_field == "package" and name == native_name:
            row["prior_package_version"] = "9.9.9"
        write_json(path, row)
    if prior_field in {"archive", "installer"}:
        path = folder / sums_name
        path.write_text(
            path.read_text().replace(
                prior.source_archive_sha256
                if prior_field == "archive"
                else prior.installer_sha256,
                "f" * 64,
            )
        )
    reseal(folder)
    with pytest.raises(ValueError):
        verify(recovered)


def test_symlinked_recovery_artifact_is_not_admitted(recovered):
    folder = recovered[0]
    path = folder / recovery.ARTIFACT_PATHS["manual_text"]
    data = path.read_bytes()
    other = folder.parent / "outside-synthetic.json"
    other.write_bytes(data)
    path.unlink()
    path.symlink_to(other)
    with pytest.raises(ValueError, match="symlink"):
        verify(recovered)


def test_contract_rejects_duplicate_json_keys_before_payload_admission(recovered):
    folder = recovered[0]
    path = folder / recovery.ARTIFACT_PATHS["manual_text"]
    text = path.read_text()
    # Even an identical duplicate is not a complete unambiguous JSON record.
    text = text.replace(
        '"schema": "sinter-campaign/v1",',
        '"schema": "sinter-campaign/v1", "schema": "sinter-campaign/v1",',
        1,
    )
    path.write_text(text)
    (folder / recovery.ARTIFACT_PATHS["manual_reference"]).write_text(text)
    reseal(folder)
    with pytest.raises(ValueError, match="duplicate"):
        verify(recovered)


def test_recovery_receipt_is_size_admitted_before_content_read(recovered, monkeypatch):
    folder = recovered[0]
    path = folder / recovery.RECEIPT_PATH
    with path.open("wb") as output:
        output.truncate(recovery.MAX_ARTIFACT_BYTES + 1)
    original = type(path).read_bytes

    def no_read(checked):
        if checked == path:
            pytest.fail("Oversized evidence should be refused before it is read")
        return original(checked)

    monkeypatch.setattr(type(path), "read_bytes", no_read)
    with pytest.raises(ValueError, match="oversized"):
        recovery.verify_installed_recovery(
            folder, VERSION, recovered[3], {}, {}, {}, "f" * 64
        )


@pytest.mark.parametrize(
    "mutation", ["html", "private_marker", "wrong_count", "boolean_count", "duplicate"]
)
def test_new_rc2_source_role_admits_only_qualified_source_fields(recovered, mutation):
    folder = recovered[0]
    name = qualification.prior_roles(qualification.QUALIFIED_PRIORS["0.5.4rc2"])[0]
    path = folder / name
    row = json.loads(path.read_text())
    if mutation == "html":
        row["html"] = "<script>Fictional unexpected attachment</script>"
    elif mutation == "private_marker":
        row["operator_notes"] = "Fictional PRIVATE-MARKER"
    elif mutation == "wrong_count":
        row["source_files"] = 250
    elif mutation == "boolean_count":
        row["source_files"] = True
    if mutation == "duplicate":
        text = json.dumps(row)
        path.write_text(
            text.replace(
                '"schema": ', '"schema": "Fictional PRIVATE-MARKER", "schema": ', 1
            )
        )
    else:
        write_json(path, row)
    reseal(folder)
    with pytest.raises(ValueError):
        verify(recovered)


def test_new_rc2_source_role_accepts_actual_pinned_zip_file_count(recovered):
    path = (
        recovered[0]
        / qualification.prior_roles(qualification.QUALIFIED_PRIORS["0.5.4rc2"])[0]
    )
    row = json.loads(path.read_text())
    row["source_files"] = 251
    write_json(path, row)
    reseal(recovered[0])
    verify(recovered)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize(
    "mutation",
    [
        "extra_html",
        "private_marker",
        "notice",
        "checks",
        "duplicate",
        "prior_checks",
        "candidate_checks",
    ],
)
def test_new_rc2_upgrade_role_does_not_carry_unrelated_content(
    recovered, native, mutation
):
    folder = recovered[0]
    name = qualification.prior_roles(qualification.QUALIFIED_PRIORS["0.5.4rc2"])[
        3 if native else 2
    ]
    path = folder / name
    row = json.loads(path.read_text())
    if mutation == "extra_html":
        row["html"] = "<p>Fictional unexpected attachment</p>"
    elif mutation == "private_marker":
        row["operator_notes"] = "Fictional PRIVATE-MARKER"
    elif mutation == "notice":
        row["fixture_notice"] += " Fictional PRIVATE-MARKER"
    elif mutation in {"checks", "prior_checks", "candidate_checks"}:
        key = (
            {
                "prior_checks": "prior_native_checks",
                "candidate_checks": "candidate_native_checks",
            }.get(mutation, "checks")
            if native
            else "checks"
        )
        row[key].append("Fictional PRIVATE-MARKER")
    if mutation == "duplicate":
        path.write_text(
            json.dumps(row).replace(
                '"schema": ', '"schema": "Fictional PRIVATE-MARKER", "schema": ', 1
            )
        )
    else:
        write_json(path, row)
    reseal(folder)
    with pytest.raises(ValueError):
        verify(recovered)


@pytest.mark.parametrize(
    "mutation",
    ["extra_filename", "crlf", "reordered", "changed_notes", "trailing_blank"],
)
def test_new_rc2_checksum_role_is_the_exact_published_document(recovered, mutation):
    path = (
        recovered[0]
        / qualification.prior_roles(qualification.QUALIFIED_PRIORS["0.5.4rc2"])[1]
    )
    data = path.read_bytes()
    if mutation == "extra_filename":
        data += ("f" * 64 + "  fictional-private-marker.html\n").encode()
    elif mutation == "crlf":
        data = data.replace(b"\n", b"\r\n")
    elif mutation == "reordered":
        data = b"\n".join(reversed(data.rstrip(b"\n").split(b"\n"))) + b"\n"
    elif mutation == "changed_notes":
        data = data.replace(b"RELEASE-NOTES.md", b"private-notes.md")
    elif mutation == "trailing_blank":
        data += b"\n"
    path.write_bytes(data)
    reseal(recovered[0])
    with pytest.raises(ValueError, match="checksum document"):
        verify(recovered)
