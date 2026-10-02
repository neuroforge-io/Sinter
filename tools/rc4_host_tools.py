"""Read and compare external RC4 host tools; their bytes are not bundled.

This is a trusted host/library/daemon boundary. Fingerprints bind actual selected
files before and after a run; they do not attest every mapped library or daemon.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path

BOUNDARY = (
    "Trusted external host executables, Playwright library and Docker daemon; "
    "fingerprints only, no executable-byte closure or installed admission."
)
MAX_HOST_FILE = 512 * 1024 * 1024
TOOLS = ("docker", "chromium", "python", "playwright_node")


def fingerprint(path):
    """Hash one actual resolved regular file without retaining its payload."""
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("An exact resolved external host file is required.")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_HOST_FILE:
        raise ValueError("External host file is not regular or exceeds its read limit.")
    digest, size = hashlib.sha256(), 0
    stream, primary = None, None
    try:
        stream = path.open("rb")
        opened = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("External host file changed before the observed read.")
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_HOST_FILE:
                raise ValueError("External host file grew beyond its read limit.")
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    except BaseException as error:
        primary = error
    finally:
        if stream is not None:
            try:
                stream.close()
            except BaseException as close_error:
                if primary is None:
                    primary = close_error
                else:
                    primary.host_tool_close_errors = [
                        {
                            "error_type": type(close_error).__name__,
                            "error": str(close_error),
                        }
                    ]
    if primary is not None:
        raise primary
    final = path.lstat()
    identity = lambda info: (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )
    if not identity(before) == identity(opened) == identity(after) == identity(final):
        raise ValueError("External host file changed during the observed read.")
    if size != before.st_size:
        raise ValueError("External host file read was incomplete.")
    return {"path": str(path), "bytes": size, "sha256": digest.hexdigest()}


def observe(callbacks):
    """Attempt every actual read and retain the first exception and all errors."""
    result, errors, primary = {}, [], None
    for role, callback in callbacks.items():
        try:
            result[role] = callback()
        except BaseException as error:
            result[role] = None
            errors.append(
                {"role": role, "error_type": type(error).__name__, "error": str(error)}
            )
            for close_error in getattr(error, "host_tool_close_errors", []):
                errors.append({"role": role + ".close", **close_error})
            if primary is None:
                primary = error
    return result, errors, primary


def validate_fingerprint(value):
    if not (
        type(value) is dict
        and set(value) == {"path", "bytes", "sha256"}
        and type(value["path"]) is str
        and value["path"].startswith("/")
        and "\x00" not in value["path"]
        and not any(part in {"", ".", ".."} for part in value["path"].split("/")[1:])
        and type(value["bytes"]) is int
        and 0 < value["bytes"] <= MAX_HOST_FILE
        and type(value["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
    ):
        raise ValueError("Complete typed external host fingerprint is required.")


def validate_host_snapshot(value):
    if not (
        type(value) is dict
        and set(value)
        == {
            "tools",
            "browser_tmp",
            "python_launch",
            "playwright_version",
            "driver_cli",
            "collector_source",
        }
        and type(value["tools"]) is dict
        and set(value["tools"]) == set(TOOLS)
    ):
        raise ValueError("Complete external host snapshot is required.")
    for record in [
        *value["tools"].values(),
        value["driver_cli"],
        value["collector_source"],
    ]:
        validate_fingerprint(record)
    for name in ("browser_tmp", "python_launch"):
        if not (
            type(value[name]) is str
            and value[name].startswith("/")
            and "\x00" not in value[name]
        ):
            raise ValueError("Actual host launch/temp identity is incomplete.")
    if not (
        type(value["playwright_version"]) is str
        and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value["playwright_version"])
    ):
        raise ValueError("Actual Playwright package version is incomplete.")


def validate_host_pair(value):
    if not (
        type(value) is dict
        and set(value) == {"schema", "boundary", "before", "after", "after_errors"}
        and value["schema"] == "sinter-rc4-host-tools/v1"
        and value["boundary"] == BOUNDARY
        and type(value["after_errors"]) is list
        and value["after_errors"] == []
    ):
        raise ValueError("Actual before/after host observation schema differs.")
    validate_host_snapshot(value["before"])
    validate_host_snapshot(value["after"])
    if value["before"] != value["after"]:
        raise ValueError("Actual external host identity changed during qualification.")
