"""Transport controls only; no archived gate, installed or browser execution."""

from __future__ import annotations

import builtins
import copy
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from tools import rc4_evidence_catalog as catalog

PHYSICAL = pytest.mark.skipif(
    not catalog.physical_reader_supported(),
    reason="This physical control needs POSIX descriptor-relative no-follow reads.",
)


def encode(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture_values():
    payload = "Original é 🐝 {literal}; owner unassigned.\n".encode("utf-8")
    code = b"raise AssertionError('ARCHIVED CODE MUST NEVER EXECUTE')\n"
    blobs = {sha(payload): payload, sha(code): code}
    authority = {
        "schema": catalog.AUTHORITY_SCHEMA,
        "identities": [
            {"name": "source", "kind": "git-commit", "value": "a" * 40},
            {"name": "package", "kind": "sha256", "value": "b" * 64},
        ],
        "labels": [
            {
                "scope": "native/owner",
                "name": "input",
                "namespace": "host",
                "value": "/home/absent/original/source.py",
            },
            {
                "scope": "replacement/rc3",
                "name": "input",
                "namespace": "container",
                "value": "/out/run/{literal}/../kept-label 🐝",
            },
            {
                "scope": "recovery",
                "name": "code",
                "namespace": "host",
                "value": "/etc/passwd\n{opaque data}",
            },
        ],
        "roles": [
            {
                "scope": "native/owner",
                "role": "raw-original",
                "identity": "source",
                "label": "input",
                "bytes": len(payload),
                "sha256": sha(payload),
            },
            {
                "scope": "replacement/rc3",
                "role": "raw-original",
                "identity": "package",
                "label": "input",
                "bytes": len(payload),
                "sha256": sha(payload),
            },
            {
                "scope": "recovery",
                "role": "archived-source",
                "identity": "source",
                "label": "code",
                "bytes": len(code),
                "sha256": sha(code),
            },
        ],
        "directories": ["blobs", "empty", "empty/runtime"],
    }
    index = {**copy.deepcopy(authority), "schema": catalog.INDEX_SCHEMA}
    return authority, index, blobs


def materialize(root, authority, index, blobs):
    root.mkdir()
    for name in authority["directories"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    for digest, raw in blobs.items():
        (root / "blobs" / digest).write_bytes(raw)
    raw = encode(index)
    (root / catalog.INDEX_NAME).write_bytes(raw)
    return sha(raw)


@pytest.fixture
def values():
    return fixture_values()


@PHYSICAL
def test_untouched_catalog_relocates_to_two_roots_with_independent_dedup_roles(
    tmp_path, values
):
    authority, index, blobs = values
    roots = [tmp_path / "first extracted snapshot", tmp_path / "different-location 🐝"]
    readers = []
    for root in roots:
        pin = materialize(root, authority, index, blobs)
        readers.append(
            catalog.Catalog(root, index_sha256=pin, authority=encode(authority))
        )
    assert readers[0].records() == readers[1].records()
    assert readers[0].read_role("native/owner", "raw-original") == readers[1].read_role(
        "replacement/rc3", "raw-original"
    )
    assert (
        readers[0].original_label("replacement/rc3", "input")
        == authority["labels"][1]["value"]
    )
    assert (
        readers[0]
        .read_role("recovery", "archived-source")
        .startswith(b"raise AssertionError")
    )
    record = readers[0].records()
    assert record["retained_files"] == 3  # catalog plus two unique blobs, three roles
    assert record["retained_unique_bytes"] == len(encode(index)) + sum(
        map(len, blobs.values())
    )
    assert record["transport_only"] is True
    assert record["semantic_gate_validated"] is False
    assert record["historical_qualification"] is False
    assert record["installed_execution"] is False
    record["installed_execution"] = True
    assert readers[0].records()["installed_execution"] is False
    identity = readers[0].identity("source")
    identity["value"] = "unapproved"
    assert readers[0].identity("source")["value"] == "a" * 40
    print(
        json.dumps(
            {
                "actual_transport_roots": [str(root) for root in roots],
                "observed_transport_records": [reader.records() for reader in readers],
                "raw_original_sha256": sha(
                    readers[0].read_role("native/owner", "raw-original")
                ),
                "opaque_original_label": readers[0].original_label(
                    "replacement/rc3", "input"
                ),
            },
            ensure_ascii=True,
        )
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "top-extra",
        "missing-field",
        "wrong-schema",
        "identity-extra",
        "identity-duplicate",
        "identity-kind",
        "identity-bool",
        "identity-short-commit",
        "identity-short-sha",
        "label-extra",
        "label-duplicate",
        "label-namespace",
        "label-surrogate",
        "role-extra",
        "role-duplicate",
        "role-bool-size",
        "role-float-size",
        "role-negative-size",
        "role-large-size",
        "role-upper-sha",
        "role-missing-identity",
        "role-missing-label",
        "role-other-scope-label",
        "dedup-conflicting-size",
        "unbound-identity",
        "unbound-label",
        "directory-duplicate",
        "directory-absolute",
        "directory-dotdot",
        "directory-backslash",
        "directory-noncanonical",
        "directory-nul",
        "directory-file-overlap",
        "missing-directory-parent",
        "empty-roles",
    ],
)
def test_portable_authority_schema_refuses_malformed_or_unbound_claims(
    values, mutation
):
    authority, _, _ = values
    value = copy.deepcopy(authority)
    if mutation == "top-extra":
        value["installed_execution"] = True
    elif mutation == "missing-field":
        value.pop("labels")
    elif mutation == "wrong-schema":
        value["schema"] = "sinter-installed-admission/v1"
    elif mutation == "identity-extra":
        value["identities"][0]["command"] = "execute"
    elif mutation == "identity-duplicate":
        value["identities"].append(copy.deepcopy(value["identities"][0]))
    elif mutation == "identity-kind":
        value["identities"][0]["kind"] = "admission"
    elif mutation == "identity-bool":
        value["identities"][0]["value"] = True
    elif mutation == "identity-short-commit":
        value["identities"][0]["value"] = "a" * 7
    elif mutation == "identity-short-sha":
        value["identities"][1]["value"] = "b" * 63
    elif mutation == "label-extra":
        value["labels"][0]["path_to_read"] = "/etc/passwd"
    elif mutation == "label-duplicate":
        value["labels"].append(copy.deepcopy(value["labels"][0]))
    elif mutation == "label-namespace":
        value["labels"][0]["namespace"] = "reader-host"
    elif mutation == "label-surrogate":
        value["labels"][0]["value"] = "\ud800"
    elif mutation == "role-extra":
        value["roles"][0]["passed"] = True
    elif mutation == "role-duplicate":
        value["roles"].append(copy.deepcopy(value["roles"][0]))
    elif mutation == "role-bool-size":
        value["roles"][0]["bytes"] = True
    elif mutation == "role-float-size":
        value["roles"][0]["bytes"] = 1.0
    elif mutation == "role-negative-size":
        value["roles"][0]["bytes"] = -1
    elif mutation == "role-large-size":
        value["roles"][0]["bytes"] = catalog.MAX_MEMBER + 1
    elif mutation == "role-upper-sha":
        value["roles"][0]["sha256"] = "A" * 64
    elif mutation == "role-missing-identity":
        value["roles"][0]["identity"] = "unapproved"
    elif mutation == "role-missing-label":
        value["roles"][0]["label"] = "unapproved"
    elif mutation == "role-other-scope-label":
        value["roles"][0]["scope"] = "wrong-scope"
    elif mutation == "dedup-conflicting-size":
        value["roles"][1]["bytes"] += 1
    elif mutation == "unbound-identity":
        value["identities"].append(
            {"name": "extra", "kind": "text", "value": "unchained"}
        )
    elif mutation == "unbound-label":
        value["labels"].append(
            {"scope": "extra", "name": "extra", "namespace": "host", "value": "/opaque"}
        )
    elif mutation == "directory-duplicate":
        value["directories"].append("blobs")
    elif mutation == "directory-absolute":
        value["directories"].append("/outside")
    elif mutation == "directory-dotdot":
        value["directories"].append("../outside")
    elif mutation == "directory-backslash":
        value["directories"].append("empty\\outside")
    elif mutation == "directory-noncanonical":
        value["directories"].append("empty//nested")
    elif mutation == "directory-nul":
        value["directories"].append("empty/\x00")
    elif mutation == "directory-file-overlap":
        value["directories"].append("catalog.json")
    elif mutation == "missing-directory-parent":
        value["directories"].remove("empty")
    else:
        value["roles"] = []
    with pytest.raises(catalog.CatalogError):
        catalog.validate_authority(encode(value))


@pytest.mark.parametrize(
    "raw",
    [
        b"{} {}",
        b"[]",
        b"\xff",
        b'{"schema":1,"schema":2}',
        b'{"number":NaN}',
        b'{"number":Infinity}',
        b'{"number":1.25}',
        b'{"number":1e400}',
    ],
)
def test_portable_json_refuses_duplicate_nonfinite_noninteger_and_invalid_utf8(raw):
    with pytest.raises(catalog.CatalogError):
        catalog.validate_authority(raw)


def test_portable_approved_inventory_has_no_arbitrary_small_role_limit(values):
    authority, _, _ = values
    role, label = authority["roles"][0], authority["labels"][0]
    authority["identities"] = authority["identities"][:1]
    authority["roles"] = [{**role, "scope": "scope-" + str(n)} for n in range(11001)]
    authority["labels"] = [{**label, "scope": "scope-" + str(n)} for n in range(11001)]
    assert len(catalog.validate_authority(encode(authority)).roles) == 11001


def test_portable_bounds_count_unique_blobs_and_reject_total_overflow(values):
    authority, _, _ = values
    authority["roles"] = []
    authority["labels"] = []
    authority["identities"] = authority["identities"][:1]
    for n in range(5):
        authority["labels"].append(
            {"scope": str(n), "name": "input", "namespace": "host", "value": "/opaque"}
        )
        authority["roles"].append(
            {
                "scope": str(n),
                "role": "raw",
                "identity": "source",
                "label": "input",
                "bytes": catalog.MAX_MEMBER,
                "sha256": f"{n:064x}",
            }
        )
    with pytest.raises(catalog.CatalogError, match="total"):
        catalog.validate_authority(encode(authority))


@pytest.mark.parametrize("field", ["identities", "labels", "roles", "directories"])
def test_portable_inventory_list_types_are_exact(values, field):
    authority, _, _ = values
    authority[field] = {}
    with pytest.raises(catalog.CatalogError, match="lists"):
        catalog.validate_authority(encode(authority))


@pytest.mark.parametrize("schema", [True, "invented", None])
def test_portable_schema_selector_cannot_expand_closed_authority(values, schema):
    authority, _, _ = values
    with pytest.raises(catalog.CatalogError, match="schema authority"):
        catalog.validate_authority(encode(authority), schema=schema)


def test_portable_nested_duplicate_and_deep_json_errors_are_catalog_errors(values):
    authority, _, _ = values
    raw = encode(authority).replace(
        b'"name":"source"', b'"name":"source","name":"source"'
    )
    for malformed in (raw, b'{"nested":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"):
        with pytest.raises(catalog.CatalogError):
            catalog.validate_authority(malformed)


@pytest.mark.parametrize("with_primary", [True, False])
def test_descriptor_faults_attempt_every_close_and_keep_primary_and_all_errors(
    monkeypatch, with_primary
):
    closed = []

    def close(descriptor):
        closed.append(descriptor)
        raise OSError("injected close " + str(descriptor))

    monkeypatch.setattr(os, "close", close)
    primary = catalog.CatalogError("original read failure")
    with pytest.raises(catalog.CatalogError) as observed:
        with catalog._descriptors() as descriptors:
            descriptors.extend([101, 202, 303])
            if with_primary:
                raise primary
    assert closed == [303, 202, 101]
    assert [str(error) for error in observed.value.cleanup_errors] == [
        "injected close 303",
        "injected close 202",
        "injected close 101",
    ]
    if with_primary:
        assert observed.value is primary
        assert str(observed.value) == "original read failure"
    else:
        assert str(observed.value) == "Read-only descriptor cleanup failed."


def test_unsupported_physical_reader_is_explicit_and_portable_schema_still_runs(
    tmp_path, values, monkeypatch
):
    authority, index, _ = values
    assert catalog.validate_authority(encode(authority))
    monkeypatch.setattr(catalog, "physical_reader_supported", lambda: False)
    with pytest.raises(catalog.UnsupportedReader):
        catalog.Catalog(
            tmp_path, index_sha256=sha(encode(index)), authority=encode(authority)
        )


@pytest.mark.parametrize("root", [None, True, 123, b"path", "\x00"])
def test_portable_actual_root_types_and_nul_refuse_without_a_physical_read(root):
    with pytest.raises(catalog.CatalogError, match="Actual root"):
        catalog._Tree(root)


def test_portable_pathlike_callback_cannot_execute_through_actual_root():
    attempts = []

    class UnapprovedPathLike:
        def __fspath__(self):
            attempts.append("unapproved callback executed")
            return "/original/host/label"

    with pytest.raises(catalog.CatalogError, match="Actual root"):
        catalog._Tree(UnapprovedPathLike())
    assert attempts == []


@PHYSICAL
@pytest.mark.parametrize(
    "mutation",
    [
        "identity",
        "label",
        "role-scope",
        "role-name",
        "blob-size",
        "blob-digest",
        "extra-directory",
        "extra-claim",
    ],
)
def test_self_resealed_index_cannot_override_external_authority(
    tmp_path, values, mutation
):
    authority, index, blobs = values
    if mutation == "identity":
        index["identities"][0]["value"] = "c" * 40
    elif mutation == "label":
        index["labels"][0]["value"] = "/different/original"
    elif mutation == "role-scope":
        index["roles"][0]["scope"] = "other"
    elif mutation == "role-name":
        index["roles"][0]["role"] = "other"
    elif mutation == "blob-size":
        index["roles"][2]["bytes"] += 1
    elif mutation == "blob-digest":
        index["roles"][2]["sha256"] = "c" * 64
    elif mutation == "extra-directory":
        index["directories"].append("new-empty")
    else:
        index["installed_execution"] = True
    pin = materialize(tmp_path / "bundle", authority, index, blobs)
    with pytest.raises(catalog.CatalogError):
        catalog.Catalog(
            tmp_path / "bundle", index_sha256=pin, authority=encode(authority)
        )


@PHYSICAL
def test_external_index_pin_is_required_before_blob_payload_reads(
    tmp_path, values, monkeypatch
):
    authority, index, blobs = values
    root = tmp_path / "bundle"
    materialize(root, authority, index, blobs)
    seen = []
    original = catalog._Tree.read

    def read(self, descriptor, name, **kwargs):
        seen.append(name)
        return original(self, descriptor, name, **kwargs)

    monkeypatch.setattr(catalog._Tree, "read", read)
    with pytest.raises(catalog.CatalogError, match="digest"):
        catalog.Catalog(root, index_sha256="0" * 64, authority=encode(authority))
    assert seen == ["catalog.json"]


@PHYSICAL
@pytest.mark.parametrize(
    "entry",
    [
        "extra-file",
        "extra-empty-directory",
        "missing-empty-directory",
        "missing-blob",
        "symlink",
        "hardlink",
        "fifo",
        "socket",
        "directory-instead-of-blob",
    ],
)
def test_inventory_refuses_unknown_missing_and_special_entries_before_payload_reads(
    tmp_path, values, monkeypatch, entry
):
    authority, index, blobs = values
    root = tmp_path / "bundle"
    pin = materialize(root, authority, index, blobs)
    leaf = root / "blobs" / next(iter(blobs))
    channel = None
    if entry == "extra-file":
        (root / "unlisted").write_bytes(b"wrong")
    elif entry == "extra-empty-directory":
        (root / "unlisted").mkdir()
    elif entry == "missing-empty-directory":
        (root / "empty/runtime").rmdir()
    elif entry == "missing-blob":
        leaf.unlink()
    else:
        leaf.unlink()
        if entry == "symlink":
            leaf.symlink_to(tmp_path / "private-original")
        elif entry == "hardlink":
            (tmp_path / "private-original").write_bytes(b"outside")
            os.link(tmp_path / "private-original", leaf)
        elif entry == "fifo":
            os.mkfifo(leaf, 0o600)
        elif entry == "socket":
            channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            # The relative pathname keeps this resource control inside the
            # portable UNIX socket pathname bound even for long pytest roots.
            monkeypatch.chdir(root)
            channel.bind("blobs/" + leaf.name)
        else:
            leaf.mkdir()
    monkeypatch.setattr(
        catalog._Tree,
        "read",
        lambda *args, **kwargs: pytest.fail(
            "Inventory must refuse before payload reads"
        ),
    )
    try:
        with pytest.raises(catalog.CatalogError):
            catalog.Catalog(root, index_sha256=pin, authority=encode(authority))
    finally:
        if channel is not None:
            channel.close()


@PHYSICAL
def test_existing_reader_refuses_changed_payload_index_inventory_and_lookup(
    tmp_path, values
):
    authority, index, blobs = values
    root = tmp_path / "bundle"
    pin = materialize(root, authority, index, blobs)
    reader = catalog.Catalog(root, index_sha256=pin, authority=encode(authority))
    digest = authority["roles"][0]["sha256"]
    (root / "blobs" / digest).write_bytes(b"x" * len(blobs[digest]))
    with pytest.raises(catalog.CatalogError, match="digest"):
        reader.read_role("native/owner", "raw-original")
    (root / "blobs" / digest).write_bytes(blobs[digest])
    (root / "catalog.json").write_bytes(encode({**index, "forged": True}))
    with pytest.raises(catalog.CatalogError, match="digest"):
        reader.records()
    (root / "catalog.json").write_bytes(encode(index))
    (root / "new-empty").mkdir()
    with pytest.raises(catalog.CatalogError):
        reader.read_role("native/owner", "raw-original")
    for scope, role in [
        ("../unapproved", "raw-original"),
        ("native/owner", "/etc/passwd"),
        (True, "raw-original"),
    ]:
        with pytest.raises(catalog.CatalogError):
            reader.read_role(scope, role)


@PHYSICAL
def test_redirected_root_and_parent_never_open_outside_blob(
    tmp_path, values, monkeypatch
):
    authority, index, blobs = values
    root, outside = tmp_path / "bundle", tmp_path / "outside"
    pin = materialize(root, authority, index, blobs)
    materialize(outside, authority, index, blobs)
    linked = tmp_path / "linked"
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(catalog.CatalogError):
        catalog.Catalog(linked, index_sha256=pin, authority=encode(authority))
    original = catalog._Tree.inventory

    def replace_parent(self, descriptor, approved):
        original(self, descriptor, approved)
        (root / "blobs").rename(root / "old-blobs")
        (root / "blobs").symlink_to(outside / "blobs", target_is_directory=True)

    monkeypatch.setattr(catalog._Tree, "inventory", replace_parent)
    with pytest.raises(catalog.CatalogError, match="parent"):
        catalog.Catalog(root, index_sha256=pin, authority=encode(authority))


@PHYSICAL
def test_reader_attempts_no_write_process_network_import_or_original_label_read(
    tmp_path, values, monkeypatch
):
    authority, index, blobs = values
    root = tmp_path / "bundle"
    pin = materialize(root, authority, index, blobs)
    before = {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }
    attempted, opened = [], []
    original_open, original_import = os.open, builtins.__import__

    def forbidden(kind):
        def fail(*args, **kwargs):
            attempted.append(kind)
            pytest.fail("Catalog attempted " + kind)

        return fail

    def checked_open(path, flags, *args, **kwargs):
        assert not flags & (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        )
        assert path not in {row["value"] for row in authority["labels"]}
        opened.append(str(path))
        return original_open(path, flags, *args, **kwargs)

    def checked_import(name, *args, **kwargs):
        if name.startswith(("playwright", "sinter")):
            attempted.append("archive/library import")
            pytest.fail("Catalog must not import semantic or runtime libraries")
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        # The underlying capabilities were checked before wrapping their methods.
        patch.setattr(catalog, "physical_reader_supported", lambda: True)
        patch.setattr(os, "open", checked_open)
        patch.setattr(os, "write", forbidden("write"))
        patch.setattr(Path, "open", forbidden("path open"))
        patch.setattr(builtins, "open", forbidden("builtin open"))
        patch.setattr(builtins, "__import__", checked_import)
        patch.setattr(builtins, "exec", forbidden("archive code execution"))
        patch.setattr(builtins, "eval", forbidden("archive code evaluation"))
        patch.setattr(subprocess, "Popen", forbidden("process"))
        patch.setattr(os, "system", forbidden("shell"))
        patch.setattr(socket, "socket", forbidden("network"))
        patch.setattr(socket, "getaddrinfo", forbidden("network name lookup"))
        for name in (
            "unlink",
            "remove",
            "rename",
            "replace",
            "mkdir",
            "rmdir",
            "chmod",
            "chown",
            "truncate",
            "ftruncate",
            "link",
            "symlink",
            "mknod",
            "mkfifo",
        ):
            if hasattr(os, name):
                patch.setattr(os, name, forbidden("filesystem mutation " + name))
        for name in (
            "fork",
            "forkpty",
            "posix_spawn",
            "posix_spawnp",
            "execv",
            "execve",
        ):
            if hasattr(os, name):
                patch.setattr(os, name, forbidden("process " + name))
        reader = catalog.Catalog(root, index_sha256=pin, authority=encode(authority))
        assert (
            reader.read_role("recovery", "archived-source")
            == blobs[authority["roles"][2]["sha256"]]
        )
        assert (
            reader.original_label("recovery", "code") == authority["labels"][2]["value"]
        )
        assert reader.records()["installed_execution"] is False
    assert opened and not attempted
    assert before == {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }
    print(
        json.dumps(
            {
                "actual_readonly_open_requests": opened,
                "forbidden_attempts": attempted,
                "unchanged_retained_bytes": {
                    name: {"bytes": len(raw), "sha256": sha(raw)}
                    for name, raw in before.items()
                },
                "transport_record": reader.records(),
            },
            ensure_ascii=True,
        )
    )


@PHYSICAL
def test_oversized_actual_member_refuses_without_reading_its_contents(
    tmp_path, values, monkeypatch
):
    authority, index, blobs = values
    root = tmp_path / "bundle"
    pin = materialize(root, authority, index, blobs)
    with (root / "blobs" / next(iter(blobs))).open("r+b") as stream:
        stream.truncate(catalog.MAX_MEMBER + 1)
    monkeypatch.setattr(
        catalog._Tree,
        "read",
        lambda *args, **kwargs: pytest.fail(
            "Oversized inventory must refuse before read"
        ),
    )
    with pytest.raises(catalog.CatalogError, match="bound"):
        catalog.Catalog(root, index_sha256=pin, authority=encode(authority))


@PHYSICAL
@pytest.mark.parametrize(
    "mutation", ["opened-identity", "truncated", "grown", "added-entry"]
)
def test_mid_read_changes_refuse_instead_of_returning_unchecked_bytes(
    tmp_path, values, monkeypatch, mutation
):
    authority, index, blobs = values
    root = tmp_path / "bundle"
    pin = materialize(root, authority, index, blobs)
    reader = catalog.Catalog(root, index_sha256=pin, authority=encode(authority))
    expected = blobs[authority["roles"][0]["sha256"]]
    original_fstat, original_read = os.fstat, os.read
    changed = False

    def fstat(descriptor):
        result = original_fstat(descriptor)
        if mutation == "opened-identity" and result.st_size == len(expected):
            fields = list(result)
            fields[1] += 1
            return os.stat_result(fields)
        return result

    def read(descriptor, size):
        nonlocal changed
        raw = original_read(descriptor, size)
        if not changed and original_fstat(descriptor).st_size == len(expected) and raw:
            changed = True
            if mutation == "truncated":
                return raw[:-1]
            if mutation == "grown":
                return raw + b"x"
            if mutation == "added-entry":
                (root / "unlisted-during-read").mkdir()
        return raw

    monkeypatch.setattr(os, "fstat", fstat)
    monkeypatch.setattr(os, "read", read)
    with pytest.raises(catalog.CatalogError):
        reader.read_role("native/owner", "raw-original")
