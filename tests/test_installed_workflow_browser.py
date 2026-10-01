"""Admission, transparent transport and cleanup for installed UI test tooling."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import socket
import socketserver
import stat
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import installed_workflow_browser as flow  # noqa: E402
from tools.installed_workflow_contract import (  # noqa: E402
    ARTIFACT_PATHS,
    CHECKS,
    RECEIPT_FIELDS,
)


def test_atomic_json_write_preserves_unicode_with_windows_default_encoding(
    tmp_path, monkeypatch
):
    write_text = Path.write_text

    def windows_write_text(path, text, encoding=None, errors=None, **kwargs):
        return write_text(
            path, text, encoding=encoding or "cp1252", errors=errors, **kwargs
        )

    monkeypatch.setattr(Path, "write_text", windows_write_text)
    path = tmp_path / "fictional-recovery.json"
    value = {
        "decomposed": "Fictional Cafe\u0301",
        "precomposed": "Fictional Café",
        "notes": "Fictional 🐝 中文 sources retained.",
    }
    flow.write_json(path, value)
    assert path.read_bytes() == json.dumps(
        value, ensure_ascii=False, indent=2
    ).encode("utf-8")
    assert json.loads(path.read_bytes()) == value
    assert not path.with_suffix(".tmp").exists()


@pytest.mark.parametrize("arguments,code", [(["--help"], 0), ([], 2)])
def test_help_and_missing_arguments_need_no_browser_or_docker(arguments, code):
    result = subprocess.run(
        [sys.executable, "-S", str(Path(flow.__file__)), *arguments],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == code
    assert "usage:" in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert "ModuleNotFoundError" not in result.stderr


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:1234",
        "http://localhost:1234",
        "http://example.test:1234",
        "http://user:secret@127.0.0.1:1234",
        "http://127.0.0.1:1234?token=secret",
        "http://127.0.0.1:1234/#secret",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:1234/path",
    ],
)
def test_capture_rejects_nonlocal_or_credential_bearing_urls(value):
    with pytest.raises(ValueError):
        flow.inner_address(value)


def test_capture_accepts_only_exact_native_launch_url():
    assert flow.inner_address("http://127.0.0.1:1234") == ("127.0.0.1", 1234)


def test_header_rewrite_changes_only_host_and_origin():
    raw = (
        b"POST /api/casebooks/save HTTP/1.1\r\nHost: 127.0.0.1:4567\r\n"
        b"Origin: http://127.0.0.1:4567\r\nContent-Length: 17\r\n"
        b"X-Sinter-Token: fixture-only\r\nReferer: http://127.0.0.1:4567/\r\n\r\n"
    )
    rewritten = flow.rewrite_headers(raw, "127.0.0.1:4567", "127.0.0.1:1234")
    assert rewritten == raw.replace(
        b"Host: 127.0.0.1:4567", b"Host: 127.0.0.1:1234"
    ).replace(b"Origin: http://127.0.0.1:4567", b"Origin: http://127.0.0.1:1234")


@pytest.mark.parametrize(
    "wire",
    [
        b"GET http://example.test/ HTTP/1.1\r\nHost: 127.0.0.1:1\r\n\r\n",
        b"GET //example.test/ HTTP/1.1\r\nHost: 127.0.0.1:1\r\n\r\n",
        b"GET / HTTP/1.1\r\nHost: example.test\r\n\r\n",
        b"GET / HTTP/1.1\r\n\r\n",
        b"GET / HTTP/1.1\r\nHost: 127.0.0.1:1\r\nHost: 127.0.0.1:1\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: 127.0.0.1:1\r\nOrigin: null\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: 127.0.0.1:1\r\nTransfer-Encoding: chunked\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: 127.0.0.1:1\r\nContent-Length: -1\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: 127.0.0.1:1\r\n"
        b"Content-Length: 1\r\nContent-Length: 2\r\n\r\n",
        b"GET / HTTP/1.1\r\nHost: 127.0.0.1:1\r\n folded\r\n\r\n",
    ],
)
def test_ambiguous_or_offscope_requests_fail_closed(wire):
    with pytest.raises(ValueError):
        flow.rewrite_headers(wire, "127.0.0.1:1", "127.0.0.1:2")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only installed relay")
def test_real_tcp_unix_tcp_relay_preserves_request_body_and_response_bytes(tmp_path):
    body = '{"original":"NOT approved — 前😀"}'.encode()
    response = b"HTTP/1.0 200 OK\r\nContent-Length: 8\r\n\r\n\x00exact\r\n"
    received = []

    class Endpoint(socketserver.BaseRequestHandler):
        def handle(self):
            chunks = bytearray()
            while chunk := self.request.recv(4096):
                chunks.extend(chunk)
            received.append(bytes(chunks))
            self.request.sendall(response)

    endpoint = socketserver.TCPServer(("127.0.0.1", 0), Endpoint)
    inner = flow.InnerRelay(tmp_path)
    inner.port = endpoint.server_address[1]
    flow.write_json(tmp_path / "state.json", {"port": inner.port})
    outer = flow.Relay(tmp_path)
    servers = (endpoint, inner, outer)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for thread in threads:
        thread.start()
    address = f"127.0.0.1:{outer.server_address[1]}"
    raw = (
        f"POST /api/casebooks/save HTTP/1.1\r\nHost: {address}\r\n"
        f"Origin: http://{address}\r\nContent-Length: {len(body)}\r\n"
        "X-Sinter-Token: fixture-only\r\n\r\n"
    ).encode() + body
    try:
        with socket.create_connection(outer.server_address, timeout=3) as browser:
            browser.sendall(raw)
            browser.shutdown(socket.SHUT_WR)
            actual = bytearray()
            while chunk := browser.recv(4096):
                actual.extend(chunk)
        assert bytes(actual) == response
        expected = raw.replace(
            f"Host: {address}".encode(), f"Host: 127.0.0.1:{inner.port}".encode()
        ).replace(
            f"Origin: http://{address}".encode(),
            f"Origin: http://127.0.0.1:{inner.port}".encode(),
        )
        assert received == [expected]
        assert outer.errors == outer.model_requests == 0
    finally:
        for server, thread in zip(reversed(servers), reversed(threads)):
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    assert outer.idle() and not any(thread.is_alive() for thread in threads)


def test_partial_header_disconnect_does_not_spin_or_fake_success(tmp_path):
    relay = flow.Relay(tmp_path)
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection(relay.server_address, timeout=3) as browser:
            browser.sendall(b"GET / HTTP/1.1\r\nHost:")
            browser.shutdown(socket.SHUT_WR)
            assert browser.recv(4096) == b""
        assert relay.errors == 1
    finally:
        relay.shutdown()
        relay.server_close()
        thread.join(timeout=3)
    assert relay.idle() and not thread.is_alive()


def candidates(tmp_path, monkeypatch):
    source = tmp_path / "source.zip"
    commit = "a" * 40
    with zipfile.ZipFile(source, "w") as archive:
        archive.comment = commit.encode()
        archive.writestr("src/sinter/__init__.py", '__version__ = "0.5.4rc2"')
        for kind in ("casebook", "campaign"):
            archive.writestr(
                f"src/sinter/web/offline-garden-{kind}.json",
                json.dumps({"title": "Fictional test", "schema": kind}),
            )
    installer = tmp_path / "candidate.deb"
    installer.write_bytes(b"Pinned unit-test input; not an installable package")
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            {
                "schema": "sinter-native-test/v1",
                "passed": True,
                "frozen": True,
                "system": "Linux",
                "target_arch": "x64",
                "version": "0.5.4rc2",
                "source_commit": commit,
                "installer_sha256": flow.digest(installer),
                "package_version": "0.5.4~rc2",
            }
        )
    )
    args = argparse.Namespace(
        installer=installer,
        installer_sha256=flow.digest(installer),
        source_archive=source,
        source_sha256=flow.digest(source),
        source_commit=commit,
        version="0.5.4rc2",
        native_receipt=native,
        output=tmp_path / "new-proof",
        image="fixture:image",
        chromium=None,
    )
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: source.read_bytes())
    return args


def test_exact_bound_inputs_can_be_inspected_without_docker(tmp_path, monkeypatch):
    args = candidates(tmp_path, monkeypatch)
    fixture, native = flow.validate_inputs(args)
    assert native["frozen"] is True
    assert set(fixture["practice_hashes"]) == {
        "src/sinter/web/offline-garden-casebook.json",
        "src/sinter/web/offline-garden-campaign.json",
    }
    assert len(fixture["web"]) == 2
    assert not args.output.exists()


@pytest.mark.parametrize(
    "change",
    [
        {"installer_sha256": "0" * 64},
        {"source_sha256": "0" * 64},
        {"source_commit": "main"},
        {"version": "latest"},
    ],
)
def test_unbound_inputs_are_rejected_before_side_effects(tmp_path, monkeypatch, change):
    args = candidates(tmp_path, monkeypatch)
    for name, value in change.items():
        setattr(args, name, value)
    with pytest.raises(ValueError):
        flow.validate_inputs(args)
    assert not args.output.exists()


def test_old_output_is_protected_even_when_empty(tmp_path, monkeypatch):
    args = candidates(tmp_path, monkeypatch)
    args.output.mkdir()
    original = args.output / "keep.json"
    original.write_text("existing proof")
    with pytest.raises(ValueError, match="existing output is protected"):
        flow.validate_inputs(args)
    assert original.read_text() == "existing proof"


def test_build_receipt_cannot_relabel_other_source_or_nonfrozen_runtime(
    tmp_path, monkeypatch
):
    args = candidates(tmp_path, monkeypatch)
    native = json.loads(args.native_receipt.read_text())
    native["source_commit"] = "b" * 40
    native["frozen"] = False
    args.native_receipt.write_text(json.dumps(native))
    with pytest.raises(ValueError, match="does not bind"):
        flow.validate_inputs(args)


def test_internal_install_mode_is_refused_outside_root_container(monkeypatch):
    monkeypatch.setattr(flow.os, "geteuid", lambda: 1000, raising=False)
    with pytest.raises(ValueError, match="disposable root Docker"):
        flow.container_main()


def test_artifact_roles_are_fixed_and_extra_private_files_are_rejected(tmp_path):
    directory = tmp_path / "installed-workflow"
    directory.mkdir()
    for name in flow.ARTIFACTS.values():
        (directory / name).write_bytes(
            b"\x89PNG\r\n\x1a\nfixture"
            if name.endswith(".png")
            else b"{}"
            if name.endswith(".json")
            else b"not-a-real-docx"
        )
    rows = flow.artifact_inventory(tmp_path)
    assert {row["role"]: row["path"] for row in rows} == dict(ARTIFACT_PATHS)
    (directory / "session.txt").write_text("must never be retained")
    with pytest.raises(ValueError, match="roles differ"):
        flow.artifact_inventory(tmp_path)


def test_json_hashes_are_canonical_unicode_and_reject_nonfinite_numbers():
    expected = hashlib.sha256('{"a":"前😀","z":1}'.encode()).hexdigest()
    assert flow.object_digest({"z": 1, "a": "前😀"}) == expected
    with pytest.raises(ValueError):
        flow.object_digest({"invalid": float("nan")})


def garden_campaign():
    return json.loads(
        (flow.ROOT / "src/sinter/web/offline-garden-campaign.json").read_text()
    )


def test_source_first_action_check_accepts_only_task_edit_without_changing_fixture():
    original = garden_campaign()
    before = copy.deepcopy(original)
    saved = copy.deepcopy(original)
    saved["actions"][0]["task"] = flow.ACTION_TASK
    flow.check_campaign_actions(saved, original)
    flow.check_campaign_actions(copy.deepcopy(saved), original)
    assert original == before
    assert saved["actions"][0]["owner"] == ""
    assert saved["actions"][0]["due"] == ""
    assert saved["actions"][1:] == before["actions"][1:]


@pytest.mark.parametrize(
    "change",
    [
        "display_first_instead_of_source_first",
        "both_tasks",
        "source_first_owner",
        "source_first_due",
        "another_action_confirmation",
        "reordered_actions",
        "missing_action",
    ],
)
def test_action_check_rejects_wrong_row_and_any_unintended_action_change(change):
    original = garden_campaign()
    saved = copy.deepcopy(original)
    saved["actions"][0]["task"] = flow.ACTION_TASK
    if change == "display_first_instead_of_source_first":
        saved["actions"][0]["task"] = original["actions"][0]["task"]
        saved["actions"][1]["task"] = flow.ACTION_TASK
    elif change == "both_tasks":
        saved["actions"][1]["task"] = flow.ACTION_TASK
    elif change == "source_first_owner":
        saved["actions"][0]["owner"] = "Unintended owner"
    elif change == "source_first_due":
        saved["actions"][0]["due"] = "2026-10-01"
    elif change == "another_action_confirmation":
        saved["actions"][1]["owner_confirmed"] = True
    elif change == "reordered_actions":
        saved["actions"][0], saved["actions"][1] = (
            saved["actions"][1],
            saved["actions"][0],
        )
    else:
        saved["actions"].pop()
    with pytest.raises(ValueError, match="intended source action edit"):
        flow.check_campaign_actions(saved, original)


def test_word_proof_rejects_external_relationships_and_macro_payloads(tmp_path):
    path = tmp_path / "unsafe.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr(
            "word/_rels/document.xml.rels",
            '<Relationships><Relationship TargetMode="External"/></Relationships>',
        )
    with pytest.raises(ValueError, match="external relationship"):
        flow.word_check(path, [])
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("word/vbaProject.bin", b"macro")
    with pytest.raises(ValueError, match="Unexpected Word payload"):
        flow.word_check(path, [])


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only installed lifecycle")
def test_failed_installed_flow_retains_false_receipt_and_removes_container(
    tmp_path, monkeypatch
):
    args = candidates(tmp_path, monkeypatch)
    fixture, _ = flow.validate_inputs(args)
    calls = []
    runtime = None

    def command(*arguments, **kwargs):
        nonlocal runtime
        calls.append(arguments)
        if arguments[:3] == ("docker", "image", "inspect"):
            return "sha256:" + "c" * 64
        if arguments[:2] == ("docker", "create"):
            mount = next(value for value in arguments if value.endswith("dst=/proof"))
            runtime = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
            flow.write_json(runtime / "removed.json", {"package_removed": True})
        if arguments[:2] == ("docker", "inspect"):
            return "none"
        return "fixture-container"

    state = {
        "package": "sinter",
        "architecture": "amd64",
        "version": args.version,
        "package_version": "0.5.4~rc2",
        "installed_package_version": "0.5.4~rc2",
        "web": fixture["web"],
        "binary_sha256": "d" * 64,
        "os_release": {"ID": "ubuntu", "VERSION_ID": "22.04"},
        "libc": ["glibc", "2.35"],
        "runtime": {
            "os_id": "ubuntu",
            "os_version": "22.04",
            "machine": "x86_64",
            "pointer_bits": 64,
        },
        "frozen_test": {
            "passed": True,
            "frozen": True,
            "version": args.version,
            "system": "Linux",
            "machine": "x86_64",
            "pointer_bits": 64,
        },
    }
    monkeypatch.setattr(flow, "command", command)
    monkeypatch.setattr(flow, "wait_state", lambda *a, **k: state)
    monkeypatch.setattr(
        flow,
        "browser_workflow",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("injected browser failure")),
    )
    with pytest.raises(ValueError, match="injected browser failure"):
        flow.qualify(args, fixture)
    receipt = json.loads((args.output / "installed-workflow-browser.json").read_text())
    assert set(receipt) == RECEIPT_FIELDS
    assert receipt["passed"] is False
    assert receipt["checks"] == list(CHECKS[:2])
    assert receipt["resources"]["container_removed"] is True
    assert receipt["resources"]["package_removed"] is True
    assert receipt["resources"]["browser_closed"] is False
    create = next(call for call in calls if call[:2] == ("docker", "create"))
    assert "--pull=never" in create and "--network=none" in create
    assert any(call[:3] == ("docker", "rm", "--force") for call in calls)
    assert runtime is not None and not runtime.exists()


def actual_word_files(tmp_path, monkeypatch):
    from sinter.docx_export import export_docx

    runtime, output = tmp_path / "runtime", tmp_path / "output"
    exports = runtime / "data/exports"
    exports.mkdir(parents=True)
    output.mkdir()
    content = export_docx(
        {"title": "Fictional", "markdown": "# No approval\n\nOwner remains unknown."}
    ).content
    rows = []
    for index in range(3):
        name = f"Fictional-{index}.docx"
        path = exports / name
        path.write_bytes(content)
        path.chmod(0o600)
        rows.append(
            {
                "response": {
                    "filename": name,
                    "path": "/proof/data/exports/" + name,
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            }
        )
    # The producer admits files from a Linux guest. Model only that guest's
    # ownership/permission metadata on every test host, retaining real bytes,
    # size, type, link count, paths and hashes for admission and mutation checks.
    guest_uid, metadata = 1701, {}
    original_stat = Path.stat

    def guest_stat(path, *args, **kwargs):
        information = original_stat(path, *args, **kwargs)
        if path.parent == exports and kwargs.get("follow_symlinks", True):
            values = list(information)
            fields = metadata.get(path, {})
            values[0] = stat.S_IFMT(information.st_mode) | fields.get("mode", 0o600)
            values[4] = fields.get("uid", guest_uid)
            return os.stat_result(values)
        return information

    monkeypatch.setattr(flow.os, "getuid", lambda: guest_uid, raising=False)
    monkeypatch.setattr(Path, "stat", guest_stat)
    return runtime, output, {"snapshots": rows}, content, metadata


@pytest.mark.parametrize("missing_native_uid", [False, True])
def test_word_capture_reads_three_actual_private_files_and_retains_exact_bytes(
    tmp_path, monkeypatch, missing_native_uid
):
    if missing_native_uid:
        monkeypatch.delattr(flow.os, "getuid", raising=False)
    runtime, output, proof, content, _ = actual_word_files(tmp_path, monkeypatch)
    flow.retain_word_copies(runtime, output, proof)
    assert {path.name for path in output.iterdir()} == {
        "word-copy-applied.docx",
        "word-copy-changed.docx",
        "word-copy-unconfirmed.docx",
    }
    assert all(path.read_bytes() == content for path in output.iterdir())
    assert all(
        row["file_mode"] == 0o600 and row["file_links"] == 1
        for row in proof["snapshots"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "hash",
        "mode",
        "owner",
        "links",
        "symlink",
        "folder_symlink",
        "escape",
        "duplicates",
        "short_list",
    ],
)
def test_success_response_does_not_replace_actual_word_file_admission(
    tmp_path, monkeypatch, mutation
):
    runtime, output, proof, _, metadata = actual_word_files(tmp_path, monkeypatch)
    path = runtime / "data/exports/Fictional-0.docx"
    if mutation == "missing":
        path.unlink()
    elif mutation == "hash":
        path.write_bytes(b"changed actual file")
    elif mutation == "mode":
        path.chmod(0o644)
        metadata[path] = {"mode": 0o644}
    elif mutation == "owner":
        metadata[path] = {"uid": 1702}
    elif mutation == "links":
        (tmp_path / "other.docx").hardlink_to(path)
    elif mutation == "symlink":
        original = tmp_path / "original.docx"
        path.rename(original)
        path.symlink_to(original)
    elif mutation == "folder_symlink":
        original = tmp_path / "original-folder"
        path.parent.rename(original)
        path.parent.symlink_to(original)
    elif mutation == "escape":
        proof["snapshots"][0]["response"]["filename"] = "../Fictional-0.docx"
        proof["snapshots"][0]["response"]["path"] = (
            "/proof/data/exports/../Fictional-0.docx"
        )
    elif mutation == "duplicates":
        proof["snapshots"][1] = copy.deepcopy(proof["snapshots"][0])
    else:
        proof["snapshots"].pop()
    with pytest.raises((ValueError, FileNotFoundError)):
        flow.retain_word_copies(runtime, output, proof)


def test_word_observations_track_rows_and_ignore_unrelated_sidecars(
    tmp_path,
):
    import sqlite3

    runtime = tmp_path / "runtime"
    data = runtime / "data"
    data.mkdir(parents=True)
    for name in ("workspace.sqlite3", "campaigns.sqlite3"):
        with sqlite3.connect(data / name) as database:
            database.execute("CREATE TABLE fictional (id TEXT PRIMARY KEY, value TEXT)")
            database.execute(
                "INSERT INTO fictional VALUES (?,?)", ("fixture", "Unknown — 🐝")
            )
    (data / "preferences.json").write_text(
        '{"model":"fictional-explicit","provider":"neuroforge"}'
    )
    before = flow.workspace_observations(runtime, {"model": "fictional-explicit"})
    (data / "workspace.sqlite3-fixture-sidecar").write_bytes(
        b"fictional unrelated sidecar"
    )
    assert (
        flow.workspace_observations(runtime, {"model": "fictional-explicit"}) == before
    )
    with sqlite3.connect(data / "workspace.sqlite3") as database:
        database.execute("UPDATE fictional SET value='changed'")
    assert (
        flow.workspace_observations(runtime, {"model": "fictional-explicit"}) != before
    )
