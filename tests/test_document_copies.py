"""Local recovery proves real bytes without trusting browser download delivery."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from sinter import document_copies as copies
from sinter.docx_export import export_docx

pytestmark = pytest.mark.skipif(
    not copies.SAFE_LOCAL_SAVE, reason="Safe POSIX directory operations required"
)

PAYLOAD = {
    "title": "Fictional 🐝 e\u0301 decision",
    "markdown": "# Fictional decision\n\nNo order approved — 🐝 e\u0301.\n\n"
    "> Exact supplied source.\n\n<!-- sinter:page-break -->\n\nStill unconfirmed.",
}


def exported(directory):
    folder = directory / "exports"
    return sorted(folder.glob("*.docx")) if folder.exists() else []


def test_copy_exact_package_snapshot_privacy_and_distinct_non_overwriting_files(
    tmp_path,
):
    original = dict(PAYLOAD)
    expected = export_docx(PAYLOAD).content
    first = copies.save_word_copy(tmp_path, PAYLOAD)
    second = copies.save_word_copy(tmp_path, PAYLOAD)
    assert first["path"] != second["path"]
    for result in (first, second):
        path = Path(result["path"])
        assert path.parent == tmp_path / "exports"
        assert path.read_bytes() == expected
        assert result["bytes"] == len(expected)
        assert result["sha256"] == hashlib.sha256(expected).hexdigest()
        assert (
            result["markdown_sha256"]
            == hashlib.sha256(PAYLOAD["markdown"].encode()).hexdigest()
        )
        assert (
            result["snapshot_sha256"]
            == hashlib.sha256(
                json.dumps(
                    PAYLOAD, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        )
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "exports").stat().st_mode) == 0o700
    assert PAYLOAD == original
    assert not list((tmp_path / "exports").glob("*.tmp"))


def test_unsafe_and_long_unicode_title_is_literal_and_stays_inside_fixed_directory(
    tmp_path,
):
    payload = {**PAYLOAD, "title": "../../<script>:" + "🐝" * 180}
    result = copies.save_word_copy(tmp_path, payload)
    path = Path(result["path"])
    assert path.parent == tmp_path / "exports"
    assert len(path.name.encode()) < 255
    assert "/" not in result["filename"] and "\\" not in result["filename"]
    assert result["title"] == payload["title"]
    assert path.read_bytes() == export_docx(payload).content


@pytest.mark.parametrize(
    "payload",
    [
        {**PAYLOAD, "path": "/tmp/unapproved.docx"},
        {**PAYLOAD, "filename": "other.docx"},
        {**PAYLOAD, "overwrite": True},
        {**PAYLOAD, "markdown": ""},
        {**PAYLOAD, "markdown": "x" * 500001},
        {**PAYLOAD, "markdown": "Lone scalar \ud800"},
        {**PAYLOAD, "title": True},
        [],
    ],
)
def test_admission_never_creates_folder_or_alters_originals(tmp_path, payload):
    sentinel = tmp_path / "preferences.json"
    sentinel.write_bytes(b"fictional preferences unchanged")
    with pytest.raises(ValueError):
        copies.save_word_copy(tmp_path, payload)
    assert not (tmp_path / "exports").exists()
    assert sentinel.read_bytes() == b"fictional preferences unchanged"


def test_directory_symlink_refused_without_touching_target(tmp_path):
    target = tmp_path / "originals"
    target.mkdir()
    (target / "keep").write_bytes(b"unchanged")
    (tmp_path / "exports").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        copies.save_word_copy(tmp_path, PAYLOAD)
    assert sorted(path.name for path in target.iterdir()) == ["keep"]
    assert (target / "keep").read_bytes() == b"unchanged"


def test_public_existing_directory_and_unsafe_lock_not_chmoded(tmp_path):
    folder = tmp_path / "exports"
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)
    with pytest.raises(ValueError, match="private directory"):
        copies.save_word_copy(tmp_path, PAYLOAD)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o755
    folder.chmod(0o700)
    target = tmp_path / "keep"
    target.write_bytes(b"do not follow")
    (folder / ".word-copy.lock").symlink_to(target)
    with pytest.raises(ValueError):
        copies.save_word_copy(tmp_path, PAYLOAD)
    assert target.read_bytes() == b"do not follow"
    assert exported(tmp_path) == []


def test_name_collision_never_overwrites_or_leaves_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(copies.secrets, "token_hex", lambda size: "a" * 32)
    result = copies.save_word_copy(tmp_path, PAYLOAD)
    original = Path(result["path"]).read_bytes()
    with pytest.raises(ValueError, match="not be confirmed"):
        copies.save_word_copy(tmp_path, {**PAYLOAD, "markdown": "Different text"})
    assert Path(result["path"]).read_bytes() == original
    assert len(exported(tmp_path)) == 1
    assert not list((tmp_path / "exports").glob("*.tmp"))


@pytest.mark.parametrize("stage", ["partial_write", "readback"])
def test_interrupted_write_has_no_published_copy_or_false_success(
    tmp_path, monkeypatch, stage
):
    def interrupted(fd, content):
        if stage == "partial_write":
            os.write(fd, content[:20])
        raise OSError("synthetic failure")

    monkeypatch.setattr(
        copies, "_write" if stage == "partial_write" else "_verify_bytes", interrupted
    )
    with pytest.raises(ValueError, match="not be confirmed"):
        copies.save_word_copy(tmp_path, PAYLOAD)
    assert exported(tmp_path) == []
    assert not list((tmp_path / "exports").glob("*.tmp"))


def test_failed_confirmation_after_publication_retains_copy_and_never_reports_success(
    tmp_path, monkeypatch
):
    original = copies.os.fsync
    calls = 0

    def fail_once(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic directory confirmation failure")
        original(fd)

    monkeypatch.setattr(copies.os, "fsync", fail_once)
    with pytest.raises(ValueError, match="may already exist"):
        copies.save_word_copy(tmp_path, PAYLOAD)
    files = exported(tmp_path)
    assert len(files) == 1 and files[0].read_bytes() == export_docx(PAYLOAD).content
    assert not list((tmp_path / "exports").glob("*.tmp"))


def test_directory_replacement_does_not_redirect_write_or_claim_false_path(
    tmp_path, monkeypatch
):
    original = copies._write

    def replace_after_write(fd, content):
        original(fd, content)
        (tmp_path / "exports").rename(tmp_path / "displaced")
        (tmp_path / "exports").mkdir(mode=0o700)

    monkeypatch.setattr(copies, "_write", replace_after_write)
    with pytest.raises(ValueError, match="not be confirmed"):
        copies.save_word_copy(tmp_path, PAYLOAD)
    assert exported(tmp_path) == []
    old = list((tmp_path / "displaced").glob("*.docx"))
    assert len(old) == 1 and old[0].read_bytes() == export_docx(PAYLOAD).content


def test_fifo_capacity_and_output_size_refuse_without_reading_or_deleting(
    tmp_path, monkeypatch
):
    folder = tmp_path / "exports"
    folder.mkdir(mode=0o700)
    os.mkfifo(folder / "not-a-copy")
    with pytest.raises(ValueError, match="unsupported entry"):
        copies.save_word_copy(tmp_path, PAYLOAD)
    (folder / "not-a-copy").unlink()
    expected = export_docx(PAYLOAD).content
    monkeypatch.setattr(copies, "MAX_COPY_BYTES", len(expected) - 1)
    with pytest.raises(ValueError, match="too large"):
        copies.save_word_copy(tmp_path, PAYLOAD)
    monkeypatch.setattr(copies, "MAX_COPY_BYTES", len(expected))
    monkeypatch.setattr(copies, "MAX_FOLDER_BYTES", len(expected))
    first = copies.save_word_copy(tmp_path, PAYLOAD)
    with pytest.raises(ValueError, match="folder is full"):
        copies.save_word_copy(tmp_path, PAYLOAD)
    assert Path(first["path"]).read_bytes() == expected


def test_locked_folder_and_unsupported_platform_make_no_copy(tmp_path, monkeypatch):
    import fcntl

    folder = tmp_path / "exports"
    folder.mkdir(mode=0o700)
    lock = folder / ".word-copy.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setattr(copies, "LOCK_SECONDS", 0)
        with pytest.raises(ValueError, match="busy"):
            copies.save_word_copy(tmp_path, PAYLOAD)
    finally:
        os.close(fd)
    monkeypatch.setattr(copies, "SAFE_LOCAL_SAVE", False)
    with pytest.raises(ValueError, match="unavailable on this platform"):
        copies.save_word_copy(tmp_path, PAYLOAD)
    assert exported(tmp_path) == []


def test_concurrent_saves_are_distinct_bounded_and_exact(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(lambda _: copies.save_word_copy(tmp_path, PAYLOAD), range(8))
        )
    assert len({result["path"] for result in results}) == 8
    expected = export_docx(PAYLOAD).content
    assert all(Path(result["path"]).read_bytes() == expected for result in results)
    assert len(exported(tmp_path)) == 8
    assert not list((tmp_path / "exports").glob("*.tmp"))


def test_modeled_combined_lock_creation_failure_is_avoided(tmp_path, monkeypatch):
    # Model the observed Darwin ENOENT at combined create/open. This establishes
    # the failing call boundary, not a proven explanation of the hosted failure.
    folder = tmp_path / "exports"
    folder.mkdir(mode=0o700)
    original_open = os.open
    attempts = []

    def modeled_open(path, flags, mode=0o777, *, dir_fd=None):
        if path == ".word-copy.lock":
            attempts.append(flags)
            if flags & os.O_CREAT and not flags & os.O_EXCL:
                raise FileNotFoundError(errno.ENOENT, "modeled create/open race", path)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(copies.os, "open", modeled_open)
    folder_fd = original_open(folder, os.O_DIRECTORY | os.O_RDONLY)
    try:
        with pytest.raises(FileNotFoundError, match="modeled create/open race"):
            modeled_open(
                ".word-copy.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=folder_fd,
            )
    finally:
        os.close(folder_fd)
    attempts.clear()
    result = copies.save_word_copy(tmp_path, PAYLOAD)
    assert len(attempts) == 1 and attempts[0] & os.O_EXCL
    assert Path(result["path"]).read_bytes() == export_docx(PAYLOAD).content


@pytest.mark.parametrize("existing", [False, True])
def test_lock_creation_is_exclusive_and_existing_open_does_not_create(
    tmp_path, monkeypatch, existing
):
    folder = tmp_path / "exports"
    folder.mkdir(mode=0o700)
    lock = folder / ".word-copy.lock"
    if existing:
        lock.write_bytes(b"existing private lock; retain exact bytes")
        lock.chmod(0o600)
        before = lock.stat()
    original_open = os.open
    attempts = []

    def tracked_open(path, flags, mode=0o777, *, dir_fd=None):
        if path == ".word-copy.lock":
            attempts.append((flags, mode))
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(copies.os, "open", tracked_open)
    result = copies.save_word_copy(tmp_path, PAYLOAD)
    base = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    expected = [(base | os.O_CREAT | os.O_EXCL, 0o600)]
    if existing:
        expected.append((base, 0o777))
        after = lock.stat()
        assert (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
        assert lock.read_bytes() == b"existing private lock; retain exact bytes"
    assert attempts == expected
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    assert Path(result["path"]).read_bytes() == export_docx(PAYLOAD).content


@pytest.mark.parametrize("stage", ["creation", "existing"])
def test_missing_lock_path_is_not_retried_or_recreated(tmp_path, monkeypatch, stage):
    original_open = os.open
    attempts = []

    def missing_open(path, flags, mode=0o777, *, dir_fd=None):
        if path != ".word-copy.lock":
            return original_open(path, flags, mode, dir_fd=dir_fd)
        attempts.append(flags)
        if stage == "existing" and flags & os.O_EXCL:
            raise FileExistsError(errno.EEXIST, "modeled competing creation", path)
        raise FileNotFoundError(errno.ENOENT, "modeled missing lock path", path)

    monkeypatch.setattr(copies.os, "open", missing_open)
    with pytest.raises(ValueError, match="not be confirmed") as caught:
        copies.save_word_copy(tmp_path, PAYLOAD)
    assert isinstance(caught.value.__cause__, FileNotFoundError)
    base = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    assert attempts == [base | os.O_CREAT | os.O_EXCL] + (
        [base] if stage == "existing" else []
    )
    assert exported(tmp_path) == []
    assert list((tmp_path / "exports").iterdir()) == []


@pytest.mark.parametrize("kind", ["public", "hardlink", "fifo", "owner"])
def test_existing_lock_safety_checks_survive_exclusive_creation_fallback(
    tmp_path, monkeypatch, kind
):
    folder = tmp_path / "exports"
    folder.mkdir(mode=0o700)
    lock = folder / ".word-copy.lock"
    if kind == "fifo":
        os.mkfifo(lock, 0o600)
    else:
        lock.write_bytes(b"unsafe lock must stay unchanged")
        lock.chmod(0o600)
        if kind == "public":
            lock.chmod(0o644)
        elif kind == "hardlink":
            os.link(lock, tmp_path / "fictional-lock-link")
        elif kind == "owner":
            original_fstat = os.fstat

            def different_owner(fd):
                information = original_fstat(fd)
                if stat.S_ISREG(information.st_mode):
                    fields = list(information)
                    fields[4] = information.st_uid + 1
                    return os.stat_result(fields)
                return information

            monkeypatch.setattr(copies.os, "fstat", different_owner)
    before = lock.stat()
    with pytest.raises(ValueError, match="lock is unsafe"):
        copies.save_word_copy(tmp_path, PAYLOAD)
    after = lock.stat()
    assert (before.st_dev, before.st_ino, before.st_mode, before.st_nlink) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
    )
    if kind != "fifo":
        assert lock.read_bytes() == b"unsafe lock must stay unchanged"
    assert exported(tmp_path) == []
    assert not list(folder.glob("*.tmp"))
