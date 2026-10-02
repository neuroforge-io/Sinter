"""Resealed fictional artifacts exercise gates; no installer execution is claimed."""

from __future__ import annotations

import ast
import base64
import copy
import hashlib
import json
import struct
import zipfile
import zlib

import pytest
from test_candidate_release import bundle as bundle
from test_candidate_release import seal, write_json

from sinter import casebooks, docx_export
from tools import candidate_qualification as qualification
from tools import candidate_release as candidate
from tools import installed_workflow_qualification as workflow
from tools.historical_handover_fixture import historical_handover
from tools.installed_workflow_contract import (
    ARTIFACT_PATHS,
    CHECKS,
    MAX_ARTIFACT_BYTES,
    OPERATOR_NOTE,
    PRACTICE_FILES,
    RESOURCE_FLAGS,
    RESTORED_CAMPAIGN_TITLE,
    RESTORED_CASEBOOK_TITLE,
    SCHEMA,
)

VERSION = "0.5.4rc2"
pytestmark = pytest.mark.parametrize("bundle", [VERSION], indirect=True)


def png(chunk_type=b"IEND", extra=b""):
    def chunk(kind, content):
        return (
            struct.pack(">I", len(content))
            + kind
            + content
            + struct.pack(">I", zlib.crc32(kind + content) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x20\x40\x60"))
        + (chunk(chunk_type, extra) if chunk_type != b"IEND" else b"")
        + chunk(b"IEND", b"")
    )


def source_files(folder, version=VERSION):
    with zipfile.ZipFile(folder / f"sinter-{version}-source.zip") as archive:
        return {
            item.filename: archive.read(item)
            for item in archive.infolist()
            if not item.is_dir()
        }


def refresh_artifacts(folder):
    path = folder / "installed-workflow-browser.json"
    receipt = json.loads(path.read_text())
    for row in receipt["artifacts"]:
        artifact = folder / row["path"]
        if artifact.is_file():
            row.update(sha256=candidate.digest(artifact), bytes=artifact.stat().st_size)
    write_json(path, receipt)
    seal(folder)


@pytest.fixture
def completed(bundle):
    folder, review, repository, commit = bundle
    version = json.loads((folder / "candidate-qualification.json").read_text())[
        "version"
    ]
    source = source_files(folder, version)
    original_book, original_campaign, book, campaign = workflow.fictional_documents(
        source
    )
    web = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in source.items()
        if name.startswith("src/sinter/web/")
    }
    # Historical v1 fixtures retain their captured report/Word bytes. They must
    # not acquire a later generator's wording from the verifier's imports.
    historical = historical_handover("installed_garden")
    assert historical["input"] == book
    report = historical["report"]
    word_content = base64.b64decode(historical["word_base64"], validate=True)
    assert hashlib.sha256(word_content).hexdigest() == historical["word_sha256"]
    for role, name in ARTIFACT_PATHS.items():
        path = folder / name
        path.parent.mkdir(exist_ok=True)
        if role == "handover_word":
            path.write_bytes(word_content)
        elif role == "casebook_backup":
            write_json(path, book)
        elif role == "campaign_backup":
            write_json(path, campaign)
        else:
            path.write_bytes(png())
    native_name = f"Sinter-{version}-linux-x64-test.json"
    native = json.loads((folder / native_name).read_text())
    normalized_book = casebooks.validate(book)
    receipt = {
        "schema": SCHEMA,
        "passed": True,
        "version": version,
        "source_commit": commit,
        "system": "Linux",
        "target_arch": "x64",
        "machine": "x86_64",
        "pointer_bits": 64,
        "frozen": True,
        "desktop": True,
        "installed_executable": "/opt/neuroforge/sinter/Sinter",
        "installer_sha256": native["installer_sha256"],
        "source_archive_sha256": candidate.digest(
            folder / f"sinter-{version}-source.zip"
        ),
        "native_receipt_sha256": candidate.digest(folder / native_name),
        "installed_binary_sha256": hashlib.sha256(
            b"fixture executable, never executed"
        ).hexdigest(),
        "web_assets_sha256": web,
        "practice_fixture_sha256": {
            name: hashlib.sha256(source[name]).hexdigest() for name in PRACTICE_FILES
        },
        "input_hashes": {
            "garden_casebook": workflow.canonical_hash(original_book),
            "garden_campaign": workflow.canonical_hash(original_campaign),
            "static_assets": workflow.canonical_hash(web),
        },
        "result_hashes": {
            "saved_casebook": workflow.canonical_hash(normalized_book),
            "restored_casebook": workflow.canonical_hash(
                casebooks.validate({**book, "title": RESTORED_CASEBOOK_TITLE})
            ),
            "saved_campaign": workflow.canonical_hash(campaign),
            "restored_campaign": workflow.canonical_hash(
                {**campaign, "title": RESTORED_CAMPAIGN_TITLE}
            ),
            "saved_report": workflow.canonical_hash(report),
        },
        "image_id": "sha256:" + "a" * 64,
        "container": "ubuntu:22.04",
        "network": "disabled container; loopback only",
        "network_mode": "none",
        "host_installation": False,
        "os_release": {"ID": "ubuntu", "VERSION_ID": "22.04"},
        "libc": ["glibc", "2.35"],
        "external_requests": 0,
        "page_errors": 0,
        "model_calls": 0,
        "resources": dict.fromkeys(RESOURCE_FLAGS, True),
        "checks": list(CHECKS),
        "artifacts": [
            {
                "role": role,
                "path": name,
                "sha256": candidate.digest(folder / name),
                "bytes": (folder / name).stat().st_size,
            }
            for role, name in ARTIFACT_PATHS.items()
        ],
    }
    write_json(folder / "installed-workflow-browser.json", receipt)
    seal(folder)
    return folder, review, repository, commit


def verify(completed):
    folder, review, repository, commit = completed
    return qualification.verify_candidate(folder, review, VERSION, commit, repository)


def test_rc2_requires_both_pinned_paths_and_bounded_installed_output(
    completed, tmp_path
):
    before = {
        name: candidate.digest(path)
        for name, path in candidate._files(completed[0]).items()
    }
    result = verify(completed)
    assert result["native_target"] == "linux-x64"
    manifest = candidate.prepare(
        *completed[:2], tmp_path / "stage", VERSION, completed[3], completed[2]
    )
    assert candidate.verify_plan(manifest, completed[2])["verification"] == result
    assert before == {
        name: candidate.digest(path)
        for name, path in candidate._files(completed[0]).items()
    }


@pytest.mark.parametrize(
    "role",
    [
        "published-rc1-source-verification.json",
        "published-rc1-SHA256SUMS.txt",
        "published-rc1-copied-upgrade-test.json",
        "published-rc1-native-installer-upgrade-test.json",
        "copied-upgrade-test.json",
        "native-installer-upgrade-test.json",
        "installed-workflow-browser.json",
        *ARTIFACT_PATHS.values(),
    ],
)
def test_resealed_missing_required_role_fails(completed, role):
    (completed[0] / role).unlink()
    seal(completed[0])
    with pytest.raises(ValueError, match="artifact roles"):
        verify(completed)


@pytest.mark.parametrize(
    "filename,field,value",
    [
        ("published-rc1-source-verification.json", "source_commit", "f" * 40),
        ("published-rc1-source-verification.json", "archive_sha256", "f" * 64),
        ("published-rc1-source-verification.json", "version", "0.5.3"),
        ("published-rc1-copied-upgrade-test.json", "prior_source_commit", "f" * 40),
        (
            "published-rc1-copied-upgrade-test.json",
            "prior_source_archive_sha256",
            "f" * 64,
        ),
        ("published-rc1-copied-upgrade-test.json", "candidate_binary_sha256", "f" * 64),
        (
            "published-rc1-native-installer-upgrade-test.json",
            "prior_installer_sha256",
            "f" * 64,
        ),
        (
            "published-rc1-native-installer-upgrade-test.json",
            "prior_package_version",
            "0.5.3",
        ),
        (
            "published-rc1-native-installer-upgrade-test.json",
            "candidate_package_version",
            "0.5.4~rc1",
        ),
        (
            "published-rc1-native-installer-upgrade-test.json",
            "candidate_installer_sha256",
            "f" * 64,
        ),
        ("copied-upgrade-test.json", "candidate_binary_sha256", "f" * 64),
        ("copied-upgrade-test.json", "checks", ["save succeeded"]),
        ("native-installer-upgrade-test.json", "prior_source_archive_sha256", "f" * 64),
    ],
)
def test_resealed_upgrade_identity_forgery_fails(completed, filename, field, value):
    path = completed[0] / filename
    row = json.loads(path.read_text())
    row[field] = value
    write_json(path, row)
    seal(completed[0])
    with pytest.raises(ValueError):
        verify(completed)


@pytest.mark.parametrize(
    "field,value",
    [
        ("passed", 1),
        ("frozen", 1),
        ("desktop", False),
        ("model_calls", False),
        ("network", "enabled"),
        ("host_installation", True),
        ("target_arch", "arm64"),
        ("system", "Darwin"),
        ("pointer_bits", 32),
        ("version", "0.5.4rc2.dev0"),
        ("source_commit", "f" * 40),
        ("installer_sha256", "f" * 64),
        ("source_archive_sha256", "f" * 64),
        ("native_receipt_sha256", "f" * 64),
        ("installed_binary_sha256", "f" * 64),
        ("web_assets_sha256", {}),
        ("practice_fixture_sha256", {}),
        ("image_id", "another-image"),
        ("container", "ubuntu:24.04"),
        ("os_release", {"ID": "ubuntu", "VERSION_ID": "24.04"}),
        ("libc", ["glibc", "2.41"]),
        ("checks", list(CHECKS[:-1])),
        ("checks", [*CHECKS[:-1], CHECKS[0]]),
        ("external_requests", ["https://example.invalid"]),
        ("page_errors", ["page failed"]),
        ("model_calls", 1),
        ("session_token", "private"),
        ("input_hashes", {}),
        ("result_hashes", {}),
    ],
)
def test_resealed_ui_scope_or_identity_forgery_fails(completed, field, value):
    path = completed[0] / "installed-workflow-browser.json"
    row = json.loads(path.read_text())
    row[field] = value
    write_json(path, row)
    seal(completed[0])
    with pytest.raises(ValueError):
        verify(completed)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "unknown",
        "unsafe",
        "bad_hash",
        "bad_bytes",
        "integer_bytes",
        "missing",
        "extra_field",
        "cleanup_integer",
        "cleanup_extra",
        "extra_file",
    ],
)
def test_resealed_ui_inventory_and_cleanup_are_closed(completed, mutation):
    folder = completed[0]
    path = folder / "installed-workflow-browser.json"
    row = json.loads(path.read_text())
    item = row["artifacts"][0]
    if mutation == "duplicate":
        row["artifacts"][-1] = item
    elif mutation == "unknown":
        item["role"] = "raw_trace"
    elif mutation == "unsafe":
        item["path"] = "installed-workflow/../credentials.json"
    elif mutation == "bad_hash":
        item["sha256"] = "f" * 64
    elif mutation == "bad_bytes":
        item["bytes"] += 1
    elif mutation == "integer_bytes":
        item["bytes"] = True
    elif mutation == "missing":
        row["artifacts"].pop()
    elif mutation == "extra_field":
        item["request_headers"] = {"Authorization": "private"}
    elif mutation == "cleanup_integer":
        row["resources"]["browser_closed"] = 1
    elif mutation == "cleanup_extra":
        row["resources"]["session"] = "private"
    else:
        (folder / "installed-workflow/session.html").write_text("private session")
    write_json(path, row)
    seal(folder)
    with pytest.raises(ValueError):
        verify(completed)


@pytest.mark.parametrize(
    "role", ["overview", "casebook_backup", "campaign_backup", "handover_word"]
)
def test_html_cannot_be_disguised_as_an_admitted_artifact(completed, role):
    (completed[0] / ARTIFACT_PATHS[role]).write_text("<html>private session</html>")
    refresh_artifacts(completed[0])
    with pytest.raises(ValueError):
        verify(completed)


@pytest.mark.parametrize("role", ["casebook_backup", "campaign_backup"])
@pytest.mark.parametrize("mutation", ["secret", "changed_source", "confirmed", "extra"])
def test_backup_content_is_fixed_fictional_data_even_after_resealing(
    completed, role, mutation
):
    path = completed[0] / ARTIFACT_PATHS[role]
    row = json.loads(path.read_text())
    if mutation == "secret":
        row["contact_details"] = "private credential"
    elif mutation == "extra":
        row["credentials"] = "private credential"
    elif role == "casebook_backup":
        row["documents"][0]["content"] += "Private material"
    elif mutation == "confirmed":
        row["actions"][1]["owner_confirmed"] = True
    else:
        row["requirements"][1]["source_url"] = row["sources"][0]["url"]
    write_json(path, row)
    refresh_artifacts(completed[0])
    with pytest.raises(ValueError, match="fictional"):
        verify(completed)


def test_png_cannot_carry_text_metadata_after_resealing(completed):
    (completed[0] / ARTIFACT_PATHS["overview"]).write_bytes(
        png(b"tEXt", b"secret\x00private")
    )
    refresh_artifacts(completed[0])
    with pytest.raises(ValueError, match="PNG"):
        verify(completed)


@pytest.mark.parametrize(
    "mutation",
    ["extra", "duplicate", "entity", "oversized", "private_text", "external"],
)
def test_word_rejects_unsafe_or_private_resealed_members(completed, mutation):
    path = completed[0] / ARTIFACT_PATHS["handover_word"]
    with zipfile.ZipFile(path) as archive:
        parts = {item.filename: archive.read(item) for item in archive.infolist()}
    if mutation == "extra":
        parts["word/private.html"] = b"<html>private</html>"
    elif mutation == "entity":
        parts["word/document.xml"] = (
            b'<!DOCTYPE d [<!ENTITY secret SYSTEM "file:///private">]>'
            + parts["word/document.xml"]
        )
    elif mutation == "oversized":
        parts["word/styles.xml"] = b" " * (MAX_ARTIFACT_BYTES + 1)
    elif mutation == "private_text":
        parts["word/document.xml"] = parts["word/document.xml"].replace(
            b"Fictional operator note", b"Private credential operator note"
        )
    elif mutation == "external":
        parts["word/_rels/document.xml.rels"] = parts[
            "word/_rels/document.xml.rels"
        ].replace(
            b'Target="styles.xml"',
            b'Target="https://example.invalid" TargetMode="External"',
        )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
        if mutation == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr("word/document.xml", parts["word/document.xml"])
    refresh_artifacts(completed[0])
    with pytest.raises(ValueError):
        verify(completed)


def test_copied_and_native_sqlite_digests_need_not_equal(completed):
    path = completed[0] / "published-rc1-native-installer-upgrade-test.json"
    row = json.loads(path.read_text())
    row["original_fixture_hashes"]["workspace.sqlite3"] = "b" * 64
    write_json(path, row)
    seal(completed[0])
    verify(completed)


def test_new_ui_json_duplicate_keys_are_rejected(completed):
    path = completed[0] / "installed-workflow-browser.json"
    text = path.read_text()
    path.write_text(text.replace('"passed": true,', '"passed": false, "passed": true,'))
    seal(completed[0])
    with pytest.raises(ValueError, match="duplicate keys"):
        verify(completed)


def test_unknown_candidate_policy_cannot_reuse_rc2_evidence(completed):
    with pytest.raises(ValueError, match="explicit qualification policy"):
        qualification.verify_candidate(
            *completed[:2], "0.5.4rc4", completed[3], completed[2]
        )


def test_rc2_notes_describe_both_priors_and_installed_output(completed):
    notes = candidate.release_notes(VERSION, completed[3])
    assert "published v0.5.4rc1" in notes
    assert "eight" in notes and "not live AI validation" in notes
    assert "0.5.4~rc2" in notes and "sinter-0.5.4rc2-qualification.zip" in notes


def test_all_matching_forged_rc1_records_do_not_replace_policy_pin(completed):
    folder = completed[0]
    names = qualification.prior_roles(qualification.QUALIFIED_PRIORS["0.5.4rc1"])
    for name in (names[0], names[2], names[3]):
        path = folder / name
        row = json.loads(path.read_text())
        if name == names[0]:
            row.update(source_commit="f" * 40, archive_sha256="f" * 64)
        else:
            row.update(
                prior_source_commit="f" * 40, prior_source_archive_sha256="f" * 64
            )
            if name == names[3]:
                row["prior_installer_sha256"] = "f" * 64
        write_json(path, row)
    (folder / names[1]).write_text(
        f"{'f' * 64}  Sinter-0.5.4rc1-linux-x64.deb\n"
        f"{'f' * 64}  sinter-0.5.4rc1-source.zip\n"
    )
    seal(folder)
    with pytest.raises(ValueError, match="prior source"):
        verify(completed)


def test_resealed_nested_zip_cannot_smuggle_private_extra_role(completed, tmp_path):
    manifest = candidate.prepare(
        *completed[:2], tmp_path / "stage", VERSION, completed[3], completed[2]
    )
    path = manifest.parent / f"sinter-{VERSION}-qualification.zip"
    with zipfile.ZipFile(path) as archive:
        files = {item.filename: archive.read(item) for item in archive.infolist()}
    files["canonical/installed-workflow/session.html"] = b"private session"
    canonical = {
        name.removeprefix("canonical/"): data
        for name, data in files.items()
        if name.startswith("canonical/")
    }
    row = json.loads(canonical["candidate-qualification.json"])
    row["artifacts"] = [
        {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        for name, data in sorted(canonical.items())
        if name not in {"candidate-qualification.json", "SHA256SUMS.txt"}
    ]
    files["canonical/candidate-qualification.json"] = json.dumps(row).encode()
    checksums = [
        f"{hashlib.sha256(data).hexdigest()}  {name.removeprefix('canonical/')}"
        for name, data in sorted(files.items())
        if name.startswith("canonical/") and name != "canonical/SHA256SUMS.txt"
    ]
    files["canonical/SHA256SUMS.txt"] = ("\n".join(checksums) + "\n").encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    plan = json.loads(manifest.read_text())
    for asset in plan["assets"]:
        if asset["path"] == path.name:
            asset.update(sha256=candidate.digest(path), bytes=path.stat().st_size)
    write_json(manifest, plan)
    candidate._write_checksums(manifest.parent)
    with pytest.raises(ValueError, match="unexpected artifact roles"):
        candidate.verify_plan(manifest, completed[2])


@pytest.fixture
def current_word_evidence(completed):
    """Synthetic validator evidence only; no installed/browser pass is implied."""
    from pathlib import Path

    from tools.installed_workflow_contract import (
        LATEST_ARTIFACT_PATHS,
        WORD_CHANGED_NOTE,
        workflow_checks,
        workflow_schema,
    )

    folder, _, _, commit = completed
    source = source_files(folder)
    root = Path(workflow.__file__).resolve().parents[1]
    source.update(
        {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in (root / "src/sinter").rglob("*.py")
        }
    )
    receipt_path = folder / "installed-workflow-browser.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["schema"] = workflow_schema(source)
    receipt["checks"] = list(workflow_checks(source))
    _, _, book, _ = workflow.fictional_documents(source)
    report = casebooks.build(book)
    original = {
        "title": book["title"],
        "markdown": report["document_markdown"] + OPERATOR_NOTE,
    }
    # This separate latest-source fixture uses the new generator and closed v3
    # qualification, never the historical v1 download captured above.
    (folder / LATEST_ARTIFACT_PATHS["handover_word"]).write_bytes(
        docx_export.export_docx(original).content
    )
    report["document_edits"] = {
        "markdown": original["markdown"],
        "author": "user",
        "edited_at": "2026-10-01T00:00:00Z",
    }
    receipt["result_hashes"]["saved_report"] = workflow.canonical_hash(report)
    changed = {**original, "markdown": original["markdown"] + WORD_CHANGED_NOTE}
    rows = []
    for index, (payload, role) in enumerate(
        zip(
            (original, changed, changed),
            ("word_copy_applied", "word_copy_changed", "word_copy_unconfirmed"),
        )
    ):
        content = docx_export.export_docx(payload).content
        (folder / LATEST_ARTIFACT_PATHS[role]).write_bytes(content)
        name = f"Fictional-{index}.docx"
        response = {
            "path": "/proof/data/exports/" + name,
            "filename": name,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "content_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            "verification": "Word ZIP integrity and exact byte readback",
            "title": payload["title"],
            "markdown_sha256": hashlib.sha256(payload["markdown"].encode()).hexdigest(),
            "snapshot_sha256": workflow.canonical_hash(payload),
        }
        rows.append(
            {
                "payload": payload,
                "response": response,
                "file_mode": 0o600,
                "file_links": 1,
            }
        )
    before = {
        "tables": {
            name: {
                "definition_sha256": "a" * 64,
                "rows_sha256": "b" * 64,
                "rows": 0 if name.endswith(("/watches", "/casebooks_scoped_v2")) else 1,
            }
            for name in (
                "workspace.sqlite3/reports",
                "workspace.sqlite3/watches",
                "workspace.sqlite3/casebooks",
                "workspace.sqlite3/casebooks_scoped_v2",
                "campaigns.sqlite3/campaigns",
            )
        },
        "preferences_file": "c" * 64,
        "settings_sha256": "d" * 64,
    }
    proof = {
        "schema": "sinter-installed-word-copy/v1",
        "snapshots": rows,
        "saved_report": report,
        "pending": {
            "requests_before": 1,
            "requests_after": 1,
            "editor_text": changed["markdown"],
        },
        "uncertain": {
            "requests_after_failure": 3,
            "requests_after_idle": 3,
            "displayed_path": rows[1]["response"]["path"],
            "displayed_notice": "Previously confirmed copy",
            "editor_text": changed["markdown"],
        },
        "before": before,
        "after": json.loads(json.dumps(before)),
        "synthetic_download_denials": 1,
    }
    write_json(folder / LATEST_ARTIFACT_PATHS["word_copy_recovery"], proof)
    from sinter.runtime import catalog

    operations = catalog()
    operations["version"] = VERSION
    write_json(
        folder / LATEST_ARTIFACT_PATHS["operations_catalog"],
        {
            "schema": "sinter-operation-result/v1",
            "version": VERSION,
            "operation": "operations",
            "ok": True,
            "result": operations,
        },
    )
    receipt["artifacts"] = [
        {
            "role": role,
            "path": name,
            "sha256": candidate.digest(folder / name),
            "bytes": (folder / name).stat().st_size,
        }
        for role, name in LATEST_ARTIFACT_PATHS.items()
    ]
    write_json(receipt_path, receipt)
    return folder, source, commit


def verify_current_word(evidence):
    folder, source, commit = evidence
    receipt = json.loads((folder / "installed-workflow-browser.json").read_text())
    native = json.loads((folder / f"Sinter-{VERSION}-linux-x64-test.json").read_text())
    sums = {
        f"sinter-{VERSION}-source.zip": receipt["source_archive_sha256"],
        f"Sinter-{VERSION}-linux-x64-test.json": receipt["native_receipt_sha256"],
    }
    workflow.verify_installed_workflow(
        folder,
        VERSION,
        commit,
        sums,
        source,
        native,
        receipt["installed_binary_sha256"],
    )


@pytest.mark.parametrize(
    "schema", ["sinter-installed-workflow/v1", "sinter-installed-workflow/v2"]
)
def test_current_presentation_rejects_resealed_historical_workflow_revision(
    current_word_evidence, schema
):
    folder = current_word_evidence[0]
    path = folder / "installed-workflow-browser.json"
    receipt = json.loads(path.read_text())
    receipt["schema"] = schema
    write_json(path, receipt)
    refresh_artifacts(folder)
    with pytest.raises(ValueError):
        verify_current_word(current_word_evidence)


@pytest.mark.parametrize(
    "marker",
    [None, "sinter-handover-presentation/v1", "sinter-handover-presentation/v999"],
)
def test_current_word_saved_snapshot_requires_matching_presentation(
    current_word_evidence, marker
):
    folder = current_word_evidence[0]
    path = folder / "installed-workflow/word-copy-recovery.json"
    proof = json.loads(path.read_text())
    if marker is None:
        proof["saved_report"].pop("handover_presentation")
    else:
        proof["saved_report"]["handover_presentation"] = marker
    write_json(path, proof)
    receipt_path = folder / "installed-workflow-browser.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["result_hashes"]["saved_report"] = workflow.canonical_hash(
        proof["saved_report"]
    )
    write_json(receipt_path, receipt)
    refresh_artifacts(folder)
    with pytest.raises(ValueError):
        verify_current_word(current_word_evidence)


def test_current_word_requires_exact_catalog_saved_bytes_and_conservation(
    current_word_evidence,
):
    verify_current_word(current_word_evidence)


@pytest.mark.parametrize(
    "mutation", ["missing_word", "duplicate", "effect", "route", "extra", "different_version"]
)
def test_resealed_current_catalog_forgery_fails(current_word_evidence, mutation):
    folder = current_word_evidence[0]
    path = folder / "installed-workflow/operations-catalog.json"
    value = json.loads(path.read_text())
    index = next(
        i
        for i, row in enumerate(value["result"]["operations"])
        if row["id"] == "documents.docx.save"
    )
    if mutation == "missing_word":
        value["result"]["operations"].pop(index)
    elif mutation == "duplicate":
        value["result"]["operations"][index] = value["result"]["operations"][0]
    elif mutation in {"effect", "route"}:
        value["result"]["operations"][index][mutation] = "local"
    elif mutation == "extra":
        value["secret"] = "fictional rejection sentinel"
    else:
        value["version"] = "0.5.4rc3"
    write_json(path, value)
    refresh_artifacts(folder)
    with pytest.raises(ValueError):
        verify_current_word(current_word_evidence)


@pytest.mark.parametrize(
    "mutation",
    [
        "unwrapped",
        "outer_schema",
        "outer_version",
        "operation",
        "ok_false",
        "ok_integer",
        "ok_float",
        "ok_string",
        "ok_null",
        "outer_extra",
        "outer_missing",
        "inner_schema",
        "inner_version",
        "inner_extra",
        "result_list",
    ],
)
def test_resealed_cli_envelope_identity_is_required(current_word_evidence, mutation):
    folder = current_word_evidence[0]
    path = folder / "installed-workflow/operations-catalog.json"
    value = json.loads(path.read_text())
    if mutation == "unwrapped":
        value = value["result"]
    elif mutation == "outer_schema":
        value["schema"] = "sinter-operations/v1"
    elif mutation == "outer_version":
        value["version"] = "0.5.4rc3"
    elif mutation == "operation":
        value["operation"] = "runtime.status"
    elif mutation.startswith("ok_"):
        value["ok"] = {
            "ok_false": False,
            "ok_integer": 1,
            "ok_float": 1.0,
            "ok_string": "true",
            "ok_null": None,
        }[mutation]
    elif mutation == "outer_extra":
        value["elapsed"] = 0
    elif mutation == "outer_missing":
        value.pop("operation")
    elif mutation == "inner_schema":
        value["result"]["schema"] = "sinter-operation-result/v1"
    elif mutation == "inner_version":
        value["result"]["version"] = "0.5.4rc3"
    elif mutation == "inner_extra":
        value["result"]["elapsed"] = 0
    else:
        value["result"] = []
    write_json(path, value)
    refresh_artifacts(folder)
    with pytest.raises(ValueError, match="exact 54-operation"):
        verify_current_word(current_word_evidence)


@pytest.mark.parametrize(
    "mutation",
    [
        "snapshot",
        "markdown_hash",
        "bytes",
        "path",
        "duplicate_path",
        "mode",
        "links",
        "extra",
        "pending_request",
        "pending_text",
        "replay",
        "previous_path",
        "no_denial",
        "table_change",
        "missing_table",
        "settings",
        "preferences",
        "saved_report",
        "changed_copy",
        "original_copy",
    ],
)
def test_resealed_word_metadata_status_or_conservation_cannot_replace_bytes(
    current_word_evidence, mutation
):
    folder = current_word_evidence[0]
    path = folder / "installed-workflow/word-copy-recovery.json"
    value = json.loads(path.read_text())
    row = value["snapshots"][0]
    if mutation == "snapshot":
        row["response"]["snapshot_sha256"] = "f" * 64
    elif mutation == "markdown_hash":
        row["response"]["markdown_sha256"] = "f" * 64
    elif mutation == "bytes":
        row["response"]["bytes"] = True
    elif mutation == "path":
        row["response"]["path"] = "/tmp/other/" + row["response"]["filename"]
    elif mutation == "duplicate_path":
        value["snapshots"][1]["response"] = row["response"]
    elif mutation == "mode":
        row["file_mode"] = 0o644
    elif mutation == "links":
        row["file_links"] = 2
    elif mutation == "extra":
        row["response"]["status"] = 200
    elif mutation == "pending_request":
        value["pending"]["requests_after"] = 2
    elif mutation == "pending_text":
        value["pending"]["editor_text"] = "lost"
    elif mutation == "replay":
        value["uncertain"]["requests_after_idle"] = 4
    elif mutation == "previous_path":
        value["uncertain"]["displayed_path"] = row["response"]["path"]
    elif mutation == "no_denial":
        value["synthetic_download_denials"] = False
    elif mutation == "table_change":
        value["after"]["tables"]["workspace.sqlite3/reports"]["rows_sha256"] = "f" * 64
    elif mutation == "missing_table":
        value["before"]["tables"].pop("workspace.sqlite3/watches")
    elif mutation == "settings":
        value["after"]["settings_sha256"] = "f" * 64
    elif mutation == "preferences":
        value["after"]["preferences_file"] = None
    elif mutation == "saved_report":
        value["saved_report"]["title"] = "changed"
    else:
        role = "changed" if mutation == "changed_copy" else "applied"
        (folder / f"installed-workflow/word-copy-{role}.docx").write_bytes(
            b"not an actual DOCX"
        )
    write_json(path, value)
    refresh_artifacts(folder)
    with pytest.raises(ValueError):
        verify_current_word(current_word_evidence)


@pytest.mark.parametrize(
    "mutation",
    ["schema", "missing_word_role", "changed_source52", "source_without_runtime"],
)
def test_old_receipts_and_source_downgrades_cannot_bless_current_word(
    current_word_evidence, mutation
):
    folder, source, _ = current_word_evidence
    path = folder / "installed-workflow-browser.json"
    receipt = json.loads(path.read_text())
    if mutation == "schema":
        receipt["schema"] = SCHEMA
    elif mutation == "missing_word_role":
        receipt["artifacts"].pop()
    elif mutation == "changed_source52":
        source["src/sinter/runtime.py"] = source["src/sinter/runtime.py"].replace(
            b'"documents.docx.save"', b'"documents.fake.save"'
        )
    else:
        source.pop("src/sinter/runtime.py")
    write_json(path, receipt)
    with pytest.raises(ValueError):
        verify_current_word(current_word_evidence)


def test_canonical_roles_derive_current_word_requirements_from_source(
    current_word_evidence,
):
    from tools.installed_workflow_contract import LATEST_ARTIFACT_PATHS

    folder, source, _ = current_word_evidence
    archive = folder / f"sinter-{VERSION}-source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, content in source.items():
            bundle.writestr(name, content)
    native = json.loads((folder / f"Sinter-{VERSION}-linux-x64-test.json").read_text())
    qualification._canonical_roles(folder, VERSION, native)
    (folder / LATEST_ARTIFACT_PATHS["word_copy_changed"]).unlink()
    with pytest.raises(ValueError, match="artifact roles"):
        qualification._canonical_roles(folder, VERSION, native)


@pytest.mark.parametrize(
    "mutation", ["missing_word", "duplicate", "not_write", "keyword", "missing_module"]
)
def test_source_catalogue_itself_cannot_downgrade_current_capability(
    current_word_evidence, mutation
):
    import ast

    source = dict(current_word_evidence[1])
    tree = ast.parse(source["src/sinter/runtime.py"])
    entries = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_OPERATIONS"
            for target in node.targets
        )
    )
    index = next(
        i
        for i, entry in enumerate(entries.elts)
        if entry.args[0].value == "documents.docx.save"
    )
    if mutation == "missing_word":
        entries.elts.pop(index)
    elif mutation == "duplicate":
        entries.elts[index] = entries.elts[0]
    elif mutation == "not_write":
        entries.elts[index].args[-1] = ast.Constant("local")
    elif mutation == "keyword":
        entries.elts[index].keywords.append(
            ast.keyword(arg="effect", value=ast.Constant("write"))
        )
    else:
        source.pop("src/sinter/runtime.py")
    if mutation != "missing_module":
        source["src/sinter/runtime.py"] = ast.unparse(tree).encode()
    with pytest.raises(ValueError):
        workflow.source_operations(source)


def catalogue_contract_fixture(current_word_evidence, count=54):
    """Copy source declarations in memory; retained archives stay unchanged."""
    source = dict(current_word_evidence[1])
    tree = ast.parse(source["src/sinter/runtime.py"])
    entries = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_OPERATIONS"
            for target in node.targets
        )
    )
    envelope = json.loads(
        (current_word_evidence[0] / "installed-workflow/operations-catalog.json")
        .read_text(encoding="utf-8")
    )
    if count == 53:
        entries.elts = [
            entry for entry in entries.elts
            if entry.args[0].value != "campaigns.funding_summary"
        ]
        envelope["result"]["operations"] = [
            entry for entry in envelope["result"]["operations"]
            if entry["id"] != "campaigns.funding_summary"
        ]
    assert len(entries.elts) == count
    assert len(envelope["result"]["operations"]) == count
    source["src/sinter/runtime.py"] = ast.unparse(tree).encode("utf-8")
    return source, envelope, tree, entries


@pytest.mark.parametrize("count", [53, 54])
def test_legacy_and_current_source_catalogues_bind_the_complete_cli_envelope(
    current_word_evidence, count
):
    source, envelope, _, _ = catalogue_contract_fixture(current_word_evidence, count)
    before = dict(source)
    operations = workflow.source_operations(source)
    assert operations == envelope["result"]["operations"]
    assert len(operations) == len({row["id"] for row in operations}) == count
    assert ("campaigns.funding_summary" in {row["id"] for row in operations}) == (
        count == 54
    )
    workflow.validate_operations_catalog(envelope, source, VERSION)
    assert source == before


@pytest.mark.parametrize(
    "mutation",
    ["unexpected54", "omitted", "duplicate", "method", "route", "effect",
     "extra55", "legacy52"],
)
def test_source_catalogue_admits_only_the_recognized_funding_extension(
    current_word_evidence, mutation
):
    source, _, tree, entries = catalogue_contract_fixture(
        current_word_evidence, 53 if mutation == "legacy52" else 54
    )
    if mutation == "legacy52":
        entries.elts.pop(0)
    else:
        funding = next(
            entry for entry in entries.elts
            if entry.args[0].value == "campaigns.funding_summary"
        )
        if mutation == "unexpected54":
            funding.args[0] = ast.Constant("campaigns.unapproved_summary")
        elif mutation == "omitted":
            # Funding is still present, but an original operation was lost.
            entries.elts.pop(0)
        elif mutation == "duplicate":
            entries.elts[0] = copy.deepcopy(funding)
        elif mutation == "method":
            funding.args[1] = ast.Constant("GET")
        elif mutation == "route":
            funding.args[2] = ast.Constant("/api/campaigns/unapproved-summary")
        elif mutation == "effect":
            funding.args = funding.args[:5] + [ast.Constant("provider")]
        elif mutation == "extra55":
            extra = copy.deepcopy(funding)
            extra.args[0] = ast.Constant("campaigns.unapproved_extra")
            entries.elts.append(extra)
    source["src/sinter/runtime.py"] = ast.unparse(tree).encode("utf-8")
    with pytest.raises(ValueError):
        workflow.source_operations(source)


@pytest.mark.parametrize("field", ["method", "route", "effect", "summary", "input"])
def test_current_funding_envelope_remains_bound_to_every_source_declared_field(
    current_word_evidence, field
):
    source, envelope, _, _ = catalogue_contract_fixture(current_word_evidence)
    funding = next(
        entry for entry in envelope["result"]["operations"]
        if entry["id"] == "campaigns.funding_summary"
    )
    funding[field] = "fictional unapproved replacement"
    with pytest.raises(ValueError, match="exact 54-operation source contract"):
        workflow.validate_operations_catalog(envelope, source, VERSION)


def test_changed_transitive_renderer_cannot_verify_current_snapshot(
    current_word_evidence,
):
    current_word_evidence[1]["src/sinter/handover.py"] += (
        b"\n# fictional source drift\n"
    )
    with pytest.raises(ValueError, match="exact candidate Python"):
        verify_current_word(current_word_evidence)


def test_zip_codec_difference_keeps_actual_zip_hash_and_exact_ooxml_parts(
    current_word_evidence,
):
    import io

    folder = current_word_evidence[0]
    path = folder / "installed-workflow/word-copy-applied.docx"
    original = path.read_bytes()
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original)) as source,
        zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as target,
    ):
        for item in source.infolist():
            target.writestr(item.filename, source.read(item))
    content = output.getvalue()
    assert content != original
    path.write_bytes(content)
    (folder / "installed-workflow/handover.docx").write_bytes(content)
    proof_path = folder / "installed-workflow/word-copy-recovery.json"
    proof = json.loads(proof_path.read_text())
    proof["snapshots"][0]["response"].update(
        bytes=len(content), sha256=hashlib.sha256(content).hexdigest()
    )
    write_json(proof_path, proof)
    refresh_artifacts(folder)
    verify_current_word(current_word_evidence)


@pytest.mark.parametrize(
    "mutation",
    [
        "archive_comment",
        "member_comment",
        "member_extra",
        "trailing",
        "prefix",
        "bzip2",
    ],
)
def test_resealed_zip_metadata_cannot_hide_data_outside_snapshot(
    current_word_evidence, mutation
):
    import copy
    import io

    folder = current_word_evidence[0]
    path = folder / "installed-workflow/word-copy-applied.docx"
    original = path.read_bytes()
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original)) as source,
        zipfile.ZipFile(output, "w") as target,
    ):
        for index, item in enumerate(source.infolist()):
            entry = copy.copy(item)
            if index == 0:
                if mutation == "member_comment":
                    entry.comment = b"fictional unadmitted comment"
                elif mutation == "member_extra":
                    entry.extra = b"\xfe\xca\x04\x00TEST"
                elif mutation == "bzip2":
                    entry.compress_type = zipfile.ZIP_BZIP2
            target.writestr(entry, source.read(item))
        if mutation == "archive_comment":
            target.comment = b"fictional unadmitted archive comment"
    content = output.getvalue()
    if mutation == "trailing":
        content += b"fictional unadmitted trailing data"
    elif mutation == "prefix":
        content = b"fictional unadmitted leading data" + content
    path.write_bytes(content)
    (folder / "installed-workflow/handover.docx").write_bytes(content)
    proof_path = folder / "installed-workflow/word-copy-recovery.json"
    proof = json.loads(proof_path.read_text())
    proof["snapshots"][0]["response"].update(
        bytes=len(content), sha256=hashlib.sha256(content).hexdigest()
    )
    write_json(proof_path, proof)
    refresh_artifacts(folder)
    with pytest.raises(ValueError, match="Saved Word ZIP"):
        verify_current_word(current_word_evidence)
