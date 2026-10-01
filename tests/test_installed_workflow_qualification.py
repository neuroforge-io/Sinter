"""Resealed fictional artifacts exercise gates; no installer execution is claimed."""

from __future__ import annotations

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
    report = casebooks.build(book)
    word = docx_export.export_docx(
        {
            "title": report["title"],
            "markdown": report["document_markdown"] + OPERATOR_NOTE,
        }
    )
    for role, name in ARTIFACT_PATHS.items():
        path = folder / name
        path.parent.mkdir(exist_ok=True)
        if role == "handover_word":
            path.write_bytes(word.content)
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
