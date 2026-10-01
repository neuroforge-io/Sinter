"""Explicit, private local Word copies; no user-supplied destination paths.

The ordinary browser download remains separate. A successful copy means the
compiled bytes were verified and atomically published on this local computer;
it says nothing about browser delivery or the accuracy of the document text.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import stat
import time
import zipfile
from contextlib import ExitStack
from pathlib import Path

from .docx_export import export_docx

MAX_COPY_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_FOLDER_BYTES = 64 * 1024 * 1024
MAX_COPIES = 200
LOCK_SECONDS = 2
_LOCK = ".word-copy.lock"
_PARTS = {
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "docProps/core.xml",
}
SAFE_LOCAL_SAVE = (
    os.name == "posix"
    and all(
        operation in os.supports_dir_fd
        for operation in (os.open, os.mkdir, os.link, os.unlink, os.stat)
    )
    and hasattr(os, "O_NOFOLLOW")
)


def _private_directory(fd: int) -> None:
    information = os.fstat(fd)
    if (
        not stat.S_ISDIR(information.st_mode)
        or information.st_uid != os.geteuid()
        or information.st_mode & 0o077
    ):
        raise ValueError(
            "Sinter's exports folder must be a private directory owned by you. "
            "Use Download Word instead; no folder permissions were changed."
        )


def _write(fd: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise OSError("The Word copy write did not complete.")
        remaining = remaining[written:]


def _verify_bytes(fd: int, content: bytes) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    readback = bytearray()
    while len(readback) <= MAX_COPY_BYTES:
        part = os.read(fd, min(65536, MAX_COPY_BYTES + 1 - len(readback)))
        if not part:
            break
        readback.extend(part)
    if bytes(readback) != content:
        raise OSError("The saved Word bytes did not match the prepared document.")


def _verify_package(content: bytes) -> None:
    if len(content) > MAX_COPY_BYTES:
        raise ValueError(
            "This Word copy is too large. Reduce the document or use Download Word."
        )
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        if (
            not _PARTS.issubset(archive.namelist())
            or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES
        ):
            raise ValueError(
                "This Word copy could not be verified within its size limit."
            )
        if archive.testzip() is not None:
            raise ValueError(
                "This Word copy could not be verified. Your document text is retained."
            )


def save_word_copy(directory: Path, payload: object) -> dict:
    """Create a distinct copy of the exact explicitly supplied document snapshot.

    Only the local workspace exports directory is used. A cooperating-process
    lock bounds its capacity; directory handles prevent symlink redirection.
    No existing copy is replaced or deleted. No background retry is performed.
    """
    snapshot = dict(payload) if isinstance(payload, dict) else payload
    document = export_docx(snapshot)
    if not SAFE_LOCAL_SAVE:
        raise ValueError(
            "Safe local Word saving is unavailable on this platform. "
            "Use Download Word instead."
        )
    import fcntl

    _verify_package(document.content)
    digest = hashlib.sha256(document.content).hexdigest()
    root = Path(directory).resolve(strict=True)
    flags = os.O_DIRECTORY | os.O_NOFOLLOW | os.O_RDONLY
    try:
        with ExitStack() as resources:
            root_fd = os.open(root, flags)
            resources.callback(os.close, root_fd)
            try:
                os.mkdir("exports", 0o700, dir_fd=root_fd)
            except FileExistsError:
                pass
            folder_fd = os.open("exports", flags, dir_fd=root_fd)
            resources.callback(os.close, folder_fd)
            _private_directory(folder_fd)
            lock_fd = os.open(
                _LOCK,
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=folder_fd,
            )
            resources.callback(os.close, lock_fd)
            lock_info = os.fstat(lock_fd)
            if (
                not stat.S_ISREG(lock_info.st_mode)
                or lock_info.st_nlink != 1
                or lock_info.st_uid != os.geteuid()
                or lock_info.st_mode & 0o077
            ):
                raise ValueError(
                    "The local Word copy lock is unsafe. Use Download Word instead."
                )
            deadline = time.monotonic() + LOCK_SECONDS
            while True:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ValueError(
                            "Another local Word save is busy. Your text is retained; "
                            "retry explicitly when it finishes."
                        ) from None
                    time.sleep(0.01)
            copies = []
            for name in os.listdir(folder_fd):
                if name == _LOCK:
                    continue
                entry = os.stat(name, dir_fd=folder_fd, follow_symlinks=False)
                if not stat.S_ISREG(entry.st_mode):
                    raise ValueError(
                        "The local exports folder contains an unsupported entry. "
                        "Use Download Word instead."
                    )
                copies.append(entry.st_size)
            if (
                len(copies) >= MAX_COPIES
                or sum(copies) + len(document.content) > MAX_FOLDER_BYTES
            ):
                raise ValueError(
                    "Sinter's local exports folder is full. Move copies you want "
                    "to keep elsewhere, then retry explicitly, or use Download Word."
                )
            identifier = secrets.token_hex(16)
            # Leave room for the unique suffix within common filesystem limits,
            # even when the supplied title consists entirely of four-byte text.
            stem = (
                document.filename[:-5]
                .encode("utf-8")[:150]
                .decode("utf-8", errors="ignore")
            )
            filename = f"{stem}-{identifier}.docx"
            temporary = f".word-{identifier}.tmp"
            content_fd = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
                0o600,
                dir_fd=folder_fd,
            )
            resources.callback(os.close, content_fd)
            try:
                _write(content_fd, document.content)
                os.fsync(content_fd)
                _verify_bytes(content_fd, document.content)
                os.link(
                    temporary,
                    filename,
                    src_dir_fd=folder_fd,
                    dst_dir_fd=folder_fd,
                    follow_symlinks=False,
                )
                os.fsync(folder_fd)
            finally:
                os.unlink(temporary, dir_fd=folder_fd)
                os.fsync(folder_fd)
            # The returned path must still name these exact directories and
            # bytes; a renamed/replaced directory must never yield false success.
            for expected, actual in (
                (os.fstat(root_fd), os.stat(root, follow_symlinks=False)),
                (
                    os.fstat(folder_fd),
                    os.stat("exports", dir_fd=root_fd, follow_symlinks=False),
                ),
                (
                    os.fstat(content_fd),
                    os.stat(filename, dir_fd=folder_fd, follow_symlinks=False),
                ),
            ):
                if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
                    raise OSError(
                        "The saved Word file path changed during the operation."
                    )
            saved_fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder_fd)
            resources.callback(os.close, saved_fd)
            _verify_bytes(saved_fd, document.content)
            return {
                "path": str(root / "exports" / filename),
                "filename": filename,
                "bytes": len(document.content),
                "sha256": digest,
                "content_type": document.content_type,
                "verification": "Word ZIP integrity and exact byte readback",
                "title": snapshot["title"],
                "markdown_sha256": hashlib.sha256(
                    snapshot["markdown"].encode("utf-8")
                ).hexdigest(),
                "snapshot_sha256": hashlib.sha256(
                    json.dumps(
                        snapshot,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            }
    except OSError as error:
        raise ValueError(
            "The local Word save could not be confirmed. Your text is retained. "
            "Check Sinter's exports folder before explicitly retrying; "
            "a copy may already exist."
        ) from error
