"""Closed source archive path; no Sinter binary, installer or network is executed."""

import base64
import copy
import io
import json
import tarfile
from pathlib import PurePosixPath, PureWindowsPath

import pytest
from test_installed_native_entry_contract import inner_fixture

from tools import installed_native_container as outer
from tools import installed_native_entry_contract as contract
from tools import installed_native_menu as owner

COMMIT = "c" * 40


def member(name, raw, kind=tarfile.REGTYPE):
    item = tarfile.TarInfo(name)
    item.type = kind
    item.size = len(raw)
    if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
        item.linkname = "tools/installed_native_menu.py"
        item.size = 0
    return item, raw


def pack(rows, revision=COMMIT):
    sink = io.BytesIO()
    with tarfile.open(
        fileobj=sink,
        mode="w",
        format=tarfile.PAX_FORMAT,
        pax_headers={"comment": revision},
    ) as archive:
        for item, raw in rows:
            archive.addfile(item, io.BytesIO(raw) if item.isfile() else None)
    return sink.getvalue()


def fixture(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    files = {name: b"fictional exact producer\n" for name in owner.OWN_PATHS}
    files["src/sinter/__init__.py"] = b'__version__ = "0.5.4rc4.dev0"\n'
    for name, raw in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    monkeypatch.setattr(owner, "ROOT", source)
    rows = [
        member(path.relative_to(source).as_posix(), b"", tarfile.DIRTYPE)
        for path in sorted(source.rglob("*"))
        if path.is_dir()
    ] + [member(name, raw) for name, raw in files.items()]
    archive = pack(rows)
    identity = owner.strict_archive(archive, COMMIT)
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / owner.ARCHIVE_NAME).write_bytes(archive)
    (repository / owner.ORIGIN_NAME).write_text(
        json.dumps(owner.archive_origin(identity, len(archive))), encoding="utf-8"
    )
    return source, repository, rows, archive, identity


def test_actual_fixed_archive_reader_keeps_exact_originals_and_source(
    tmp_path, monkeypatch
):
    _source, repository, _rows, archive, expected = fixture(tmp_path, monkeypatch)
    commands, observed = [], {}
    assert (
        owner.archive_source_identity(repository, COMMIT, commands, observed)
        == expected
    )
    assert commands[0]["argv"][1:] == [
        "-B",
        "-c",
        owner.ARCHIVE_READ,
        str(repository / owner.ARCHIVE_NAME),
    ]
    assert commands[0]["stdout"]["bytes"] == len(archive)
    assert commands[0]["stdout"]["sha256"] == contract.sha(archive)
    assert commands[0]["streams_complete"] is True
    assert (
        observed["origin"]["base64"]
        == base64.b64encode((repository / owner.ORIGIN_NAME).read_bytes()).decode()
    )


@pytest.mark.parametrize(
    "attack",
    [
        "absolute",
        "traversal",
        "backslash",
        "double_slash",
        "hardlink",
        "symlink",
        "fifo",
        "duplicate",
        "extra",
        "cache",
        "pyc",
        "directory_size",
        "revision",
        "producer_override",
        "source_missing",
        "member_limit",
        "archive_limit",
        "count_limit",
    ],
)
def test_unsupported_archive_members_or_source_overrides_refuse(
    tmp_path, monkeypatch, attack
):
    _source, _repo, rows, archive, _identity = fixture(tmp_path, monkeypatch)
    first_file = next(index for index, row in enumerate(rows) if row[0].isfile())
    if attack in {"absolute", "traversal", "backslash", "double_slash"}:
        rows[first_file] = member(
            {
                "absolute": "/unowned.py",
                "traversal": "../unowned.py",
                "backslash": "tools\\unowned.py",
                "double_slash": "tools//unowned.py",
            }[attack],
            b"hostile",
        )
    elif attack in {"hardlink", "symlink", "fifo"}:
        rows[first_file] = member(
            rows[first_file][0].name,
            b"",
            {
                "hardlink": tarfile.LNKTYPE,
                "symlink": tarfile.SYMTYPE,
                "fifo": tarfile.FIFOTYPE,
            }[attack],
        )
    elif attack == "duplicate":
        rows.append(copy.deepcopy(rows[first_file]))
    elif attack in {"extra", "cache", "pyc"}:
        rows.append(
            member(
                {
                    "extra": "extra.py",
                    "cache": "__pycache__/other.py",
                    "pyc": "tools/other.pyc",
                }[attack],
                b"extra",
            )
        )
    elif attack == "directory_size":
        item = tarfile.TarInfo("fictional-dir")
        item.type, item.size = tarfile.DIRTYPE, 1
        rows.append((item, b""))
    elif attack == "producer_override":
        rows[first_file] = member(rows[first_file][0].name, b"different producer")
    elif attack == "source_missing":
        rows.pop()
    elif attack == "member_limit":
        monkeypatch.setattr(owner, "MAX_MEMBER", 1)
    elif attack == "archive_limit":
        monkeypatch.setattr(owner, "MAX_ARCHIVE", len(archive) - 1)
    elif attack == "count_limit":
        monkeypatch.setattr(owner, "MAX_ENTRIES", 1)
    archive = pack(rows, "d" * 40 if attack == "revision" else COMMIT)
    with pytest.raises((ValueError, tarfile.TarError)):
        owner.strict_archive(archive, COMMIT)


@pytest.mark.parametrize(
    "attack",
    [
        "wrong_revision",
        "wrong_source",
        "bool_bytes",
        "wrong_hash",
        "extra_field",
        "duplicate_field",
        "archive_symlink",
        "origin_symlink",
    ],
)
def test_claimed_archive_origin_never_substitutes_for_originals(
    tmp_path, monkeypatch, attack
):
    _source, repository, _rows, _archive, identity = fixture(tmp_path, monkeypatch)
    origin = owner.archive_origin(
        identity, (repository / owner.ARCHIVE_NAME).stat().st_size
    )
    if attack == "wrong_revision":
        origin["source"]["commit"] = "d" * 40
    elif attack == "wrong_source":
        origin["source"]["producer_sha256"] = "0" * 64
    elif attack == "bool_bytes":
        origin["archive"]["bytes"] = False
    elif attack == "wrong_hash":
        origin["archive"]["sha256"] = "0" * 64
    elif attack == "extra_field":
        origin["passed"] = True
    (repository / owner.ORIGIN_NAME).write_text(json.dumps(origin), encoding="utf-8")
    if attack == "duplicate_field":
        (repository / owner.ORIGIN_NAME).write_text(
            '{"schema":"sinter-bound-git-source-archive/v1","schema":"same claim"}',
            encoding="utf-8",
        )
    elif attack.endswith("symlink"):
        path = repository / (
            owner.ARCHIVE_NAME if attack == "archive_symlink" else owner.ORIGIN_NAME
        )
        saved = repository / "redirected"
        path.rename(saved)
        path.symlink_to(saved)
    with pytest.raises((ValueError, OSError)):
        owner.archive_source_identity(repository, COMMIT, [])


def archive_receipt(tmp_path):
    receipt, source, package, pins = inner_fixture(tmp_path)
    receipt["schema"] = owner.ARCHIVE_INNER_SCHEMA
    pins["source_route"] = "archive"
    raw = json.dumps(owner.archive_origin(source, 7)).encode()
    origin = {
        "schema": "sinter-bound-git-source-archive-observed/v1",
        "archive_name": owner.ARCHIVE_NAME,
        "origin_name": owner.ORIGIN_NAME,
        "origin": {
            "bytes": len(raw),
            "sha256": contract.sha(raw),
            "base64": base64.b64encode(raw).decode(),
        },
    }
    receipt["source_origin"] = origin
    receipt["source_origin_after"] = copy.deepcopy(origin)
    for index in (1, 14):
        receipt["commands"][index]["argv"] = [
            "/usr/bin/python3",
            "-B",
            "-c",
            owner.ARCHIVE_READ,
            "/repository/" + owner.ARCHIVE_NAME,
        ]
    return receipt, source, package, pins


def test_archive_receipt_keeps_all_native_gates_and_distinct_origin(tmp_path):
    receipt, source, package, pins = archive_receipt(tmp_path)
    result = contract.validate_inner(receipt, source, package, 7, pins)
    assert result["entry_pids"] == [1001, 1002, 1003, 1004]


@pytest.mark.parametrize(
    "attack",
    [
        "argv",
        "reader",
        "false_origin",
        "origin_changed",
        "old_schema",
        "route_override",
        "native_pid",
        "cleanup",
    ],
)
def test_archive_origin_branch_cannot_relax_installed_criteria(tmp_path, attack):
    receipt, source, package, pins = archive_receipt(tmp_path)
    if attack == "argv":
        receipt["commands"][1]["argv"][-1] = "/unowned/archive.tar"
    elif attack == "reader":
        receipt["commands"][14]["argv"][3] = "print('claimed source')"
    elif attack == "false_origin":
        receipt["source_origin"]["archive_name"] = "other.tar"
    elif attack == "origin_changed":
        receipt["source_origin_after"]["origin"]["bytes"] += 1
    elif attack == "old_schema":
        receipt["schema"] = contract.INNER_SCHEMA
    elif attack == "route_override":
        pins["source_route"] = "caller-supplied"
    elif attack == "native_pid":
        receipt["tk_launches"][1]["pid"] = receipt["tk_launches"][0]["pid"]
    else:
        receipt["fictional_workspace_removed"] = False
    with pytest.raises(ValueError):
        contract.validate_inner(receipt, source, package, 7, pins)


def test_actual_missing_git_is_explicitly_optional_only_for_archive_route():
    evidence = {
        "actual_tool_paths": {
            key: None if key == "git" else "/usr/bin/" + key
            for key in outer.REQUIRED_TOOLS
        }
    }
    outer.require_installed_tooling(evidence, "archive")
    with pytest.raises(ValueError, match="lacks installed-owner tooling"):
        outer.require_installed_tooling(evidence, "git")


@pytest.mark.parametrize("path_type", [PurePosixPath, PureWindowsPath])
def test_logical_archive_members_keep_posix_names_on_either_host(
    tmp_path, monkeypatch, path_type
):
    _source, _repository, _rows, archive, expected = fixture(tmp_path, monkeypatch)
    assert (
        path_type("src") / "sinter" / "__init__.py"
    ).as_posix() == "src/sinter/__init__.py"
    monkeypatch.setattr(owner, "Path", path_type)
    assert owner.strict_archive(archive, COMMIT) == expected
