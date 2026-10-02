"""Finite read-only retained-evidence transport; never a qualification gate.

Original labels are opaque data. Only the caller-approved catalog/blob inventory
is opened, through descriptor-relative no-follow reads on supported POSIX hosts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PosixPath, PurePosixPath, WindowsPath
from types import MappingProxyType

AUTHORITY_SCHEMA = "sinter-rc4-evidence-authority/v1"
INDEX_SCHEMA = "sinter-rc4-evidence-catalog/v1"
TRANSPORT_SCHEMA = "sinter-rc4-evidence-transport/v1"
INDEX_NAME = "catalog.json"
MAX_MEMBER = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")


class CatalogError(ValueError):
    """Missing, unsafe, unapproved, changed or over-bound transport data."""

    def __init__(self, *args):
        super().__init__(*args)
        self.cleanup_errors = ()


class UnsupportedReader(CatalogError):
    """This host lacks the physical no-follow directory-reader capabilities."""


def _require(condition, message):
    if not condition:
        raise CatalogError(message)


def _keys(value, expected, message):
    _require(type(value) is dict and set(value) == set(expected), message)


def _text(value):
    _require(type(value) is str and value != "", "Use a nonempty UTF-8 string.")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise CatalogError("String is not exact UTF-8.") from error
    return value


def _digest(value):
    _require(type(value) is str and _SHA.fullmatch(value), "Use a SHA-256 pin.")
    return value


def _relative(value):
    _text(value)
    path = PurePosixPath(value)
    _require(
        "\\" not in value
        and "\x00" not in value
        and not path.is_absolute()
        and value != "."
        and ".." not in path.parts
        and str(path) == value,
        "Transport entry name is not canonical relative POSIX.",
    )
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON field.")
        result[key] = value
    return result


def _no_number(value):
    raise CatalogError("Only builtin integer metadata is permitted.")


def _json(raw):
    _require(
        type(raw) is bytes and len(raw) <= MAX_MEMBER, "JSON exceeds member bound."
    )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_float=_no_number,
            parse_constant=_no_number,
        )
    except CatalogError:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise CatalogError("Require bounded strict UTF-8 JSON.") from error
    _require(type(value) is dict, "Require one JSON object.")
    return value


@dataclass(frozen=True)
class Role:
    scope: str
    role: str
    identity: str
    label: str
    bytes: int
    sha256: str

    @property
    def blob(self):
        return "blobs/" + self.sha256


@dataclass(frozen=True)
class _Authority:
    identities: dict
    labels: dict
    roles: dict
    directories: frozenset
    blobs: dict


def validate_authority(raw, *, schema=AUTHORITY_SCHEMA):
    """Portable schema/authority parsing, independent of physical-reader support.

    This validates a finite caller approval, not source/package/gate semantics.
    No role or label becomes authority merely because a receipt supplies it.
    """
    _require(
        type(schema) is str and schema in {AUTHORITY_SCHEMA, INDEX_SCHEMA},
        "Unknown catalog schema authority.",
    )
    value = _json(raw)
    _keys(
        value,
        {"schema", "identities", "labels", "roles", "directories"},
        "Catalog fields differ.",
    )
    _require(value["schema"] == schema, "Catalog schema differs.")
    for key in ("identities", "labels", "roles", "directories"):
        _require(type(value[key]) is list, "Catalog inventories must be lists.")
    identities = {}
    for row in value["identities"]:
        _keys(row, {"name", "kind", "value"}, "Identity fields differ.")
        name, kind, item = map(_text, (row["name"], row["kind"], row["value"]))
        _require(name not in identities, "Duplicate identity.")
        _require(kind in {"sha256", "git-commit", "text"}, "Unknown identity kind.")
        if kind == "sha256":
            _digest(item)
        elif kind == "git-commit":
            _require(_COMMIT.fullmatch(item), "Git identity must be a full commit.")
        identities[name] = (kind, item)
    labels = {}
    for row in value["labels"]:
        _keys(row, {"scope", "name", "namespace", "value"}, "Label fields differ.")
        scope, name, namespace, item = map(
            _text, (row["scope"], row["name"], row["namespace"], row["value"])
        )
        _require(namespace in {"host", "container"}, "Unknown original namespace.")
        _require((scope, name) not in labels, "Duplicate scoped label.")
        labels[(scope, name)] = (namespace, item)
    roles, blobs, used_identities, used_labels = {}, {}, set(), set()
    for row in value["roles"]:
        _keys(
            row,
            {"scope", "role", "identity", "label", "bytes", "sha256"},
            "Role fields differ.",
        )
        scope, name, identity, label = map(
            _text, (row["scope"], row["role"], row["identity"], row["label"])
        )
        size, digest = row["bytes"], _digest(row["sha256"])
        _require(
            type(size) is int and 0 <= size <= MAX_MEMBER, "Role member size differs."
        )
        _require(
            identity in identities and (scope, label) in labels,
            "Role authority reference is missing.",
        )
        _require((scope, name) not in roles, "Duplicate scoped role.")
        _require(
            digest not in blobs or blobs[digest] == size,
            "Deduplicated blob sizes disagree.",
        )
        roles[(scope, name)] = Role(scope, name, identity, label, size, digest)
        blobs[digest] = size
        used_identities.add(identity)
        used_labels.add((scope, label))
    _require(
        roles and used_identities == set(identities) and used_labels == set(labels),
        "Unbound or empty authority inventory.",
    )
    directories = [_relative(item) for item in value["directories"]]
    _require(len(directories) == len(set(directories)), "Duplicate directory.")
    files = {INDEX_NAME, *("blobs/" + digest for digest in blobs)}
    _require(not files.intersection(directories), "File/directory roles overlap.")
    parents = {
        parent.as_posix()
        for name in files | set(directories)
        for parent in PurePosixPath(name).parents
        if parent.as_posix() != "."
    }
    _require(parents <= set(directories), "Directory ancestors are missing.")
    _require(
        sum(blobs.values()) <= MAX_TOTAL, "Unique blob total exceeds bundle bound."
    )
    return _Authority(
        MappingProxyType(identities),
        MappingProxyType(labels),
        MappingProxyType(roles),
        frozenset(directories),
        MappingProxyType(blobs),
    )


def physical_reader_supported():
    return (
        os.name == "posix"
        and hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks
        and os.scandir in os.supports_fd
    )


@contextmanager
def _descriptors():
    opened, primary = [], None
    try:
        yield opened
    except BaseException as error:
        primary = error
        raise
    finally:
        errors = []
        for descriptor in reversed(opened):
            try:
                os.close(descriptor)
            except OSError as error:
                errors.append(error)
        if errors:
            if primary is not None:
                primary.cleanup_errors = getattr(primary, "cleanup_errors", ()) + tuple(
                    errors
                )
                raise primary
            failure = CatalogError("Read-only descriptor cleanup failed.")
            failure.cleanup_errors = tuple(errors)
            raise failure from errors[0]


_DIRECTORY_FLAGS = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


class _Tree:
    def __init__(self, root):
        _require(
            type(root) in {str, PosixPath, WindowsPath},
            "Actual root must be a builtin string or concrete host Path.",
        )
        _require("\x00" not in str(root), "Actual root contains NUL.")
        self.root = Path(root).absolute()
        _require(".." not in self.root.parts, "Actual root has ambiguous parents.")

    @contextmanager
    def root_fd(self):
        if not physical_reader_supported():
            raise UnsupportedReader(
                "Physical transport needs POSIX descriptor-relative no-follow reads."
            )
        with _descriptors() as opened:
            try:
                descriptor = os.open(self.root.anchor, _DIRECTORY_FLAGS)
                opened.append(descriptor)
                for component in self.root.parts[1:]:
                    descriptor = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
                    opened.append(descriptor)
            except OSError as error:
                raise CatalogError("Actual root is absent or redirected.") from error
            yield descriptor

    @contextmanager
    def parent_fd(self, root_fd, name):
        with _descriptors() as opened:
            descriptor = root_fd
            try:
                for component in PurePosixPath(name).parts[:-1]:
                    descriptor = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
                    opened.append(descriptor)
            except OSError as error:
                raise CatalogError(
                    "Retained parent is absent or redirected."
                ) from error
            yield descriptor

    def inventory(self, root_fd, authority):
        expected_files = {
            INDEX_NAME,
            *("blobs/" + digest for digest in authority.blobs),
        }
        expected = expected_files | set(authority.directories)
        seen, pending = set(), [""]
        while pending:
            directory = pending.pop()
            sentinel = directory + "/unused" if directory else "unused"
            with self.parent_fd(root_fd, sentinel) as descriptor:
                try:
                    with os.scandir(descriptor) as entries:
                        for entry in entries:
                            name = (
                                directory + "/" + entry.name
                                if directory
                                else entry.name
                            )
                            _require(
                                name in expected and name not in seen,
                                "Unknown or repeated retained entry.",
                            )
                            seen.add(name)
                            info = os.stat(
                                entry.name, dir_fd=descriptor, follow_symlinks=False
                            )
                            if name in authority.directories:
                                _require(
                                    stat.S_ISDIR(info.st_mode),
                                    "Retained directory is redirected or special.",
                                )
                                pending.append(name)
                            else:
                                _require(
                                    stat.S_ISREG(info.st_mode),
                                    "Retained file is redirected or special.",
                                )
                                _require(
                                    info.st_nlink == 1,
                                    "Hard-linked retained files refuse.",
                                )
                                _require(
                                    info.st_size <= MAX_MEMBER,
                                    "Retained member exceeds bound.",
                                )
                except OSError as error:
                    raise CatalogError(
                        "Retained inventory could not be read safely."
                    ) from error
        _require(seen == expected, "Missing retained file or directory.")

    def read(self, root_fd, name, *, size=None, digest=None, retain=True):
        with self.parent_fd(root_fd, name) as parent:
            leaf = PurePosixPath(name).name
            with _descriptors() as opened:
                try:
                    before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                    _require(
                        stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                        "Retained member is redirected or special.",
                    )
                    _require(
                        before.st_size <= MAX_MEMBER
                        and (size is None or before.st_size == size),
                        "Retained member size differs.",
                    )
                    descriptor = os.open(leaf, _FILE_FLAGS, dir_fd=parent)
                    opened.append(descriptor)
                    after = os.fstat(descriptor)
                    _require(
                        stat.S_ISREG(after.st_mode)
                        and after.st_nlink == 1
                        and (before.st_dev, before.st_ino, before.st_size)
                        == (after.st_dev, after.st_ino, after.st_size),
                        "Retained member changed while opening.",
                    )
                    chunks, count, hashed = [], 0, hashlib.sha256()
                    while True:
                        raw = os.read(
                            descriptor, min(1024 * 1024, MAX_MEMBER + 1 - count)
                        )
                        if not raw:
                            break
                        count += len(raw)
                        _require(
                            count <= MAX_MEMBER, "Retained member grew beyond bound."
                        )
                        hashed.update(raw)
                        if retain:
                            chunks.append(raw)
                    _require(
                        count == after.st_size and (size is None or count == size),
                        "Complete member size differs.",
                    )
                    _require(
                        digest is None or hashed.hexdigest() == digest,
                        "Retained member digest differs.",
                    )
                    return b"".join(chunks) if retain else None
                except OSError as error:
                    raise CatalogError(
                        "Retained member could not be read safely."
                    ) from error


class Catalog:
    """Consume only an independently approved retained transport inventory.

    `authority` is external strict JSON bytes; `index_sha256` is an external pin.
    Neither should be discovered from an untrusted receipt or admission boolean.
    Every lookup is a scoped approved key, never a path supplied by a receipt.
    """

    def __init__(self, root, *, index_sha256, authority):
        self._pin = _digest(index_sha256)
        self._authority = validate_authority(authority)
        self._authority_sha256 = hashlib.sha256(authority).hexdigest()
        self._tree = _Tree(root)
        self._index_bytes = 0
        self._check_all()

    def _check_index(self, descriptor):
        raw = self._tree.read(descriptor, INDEX_NAME, digest=self._pin)
        observed = validate_authority(raw, schema=INDEX_SCHEMA)
        _require(
            observed == self._authority, "Index differs from external finite authority."
        )
        _require(
            len(raw) + sum(observed.blobs.values()) <= MAX_TOTAL,
            "Index plus unique blobs exceed bundle bound.",
        )
        self._index_bytes = len(raw)

    def _check_all(self):
        with self._tree.root_fd() as descriptor:
            self._tree.inventory(descriptor, self._authority)
            self._check_index(descriptor)
            for digest, size in self._authority.blobs.items():
                self._tree.read(
                    descriptor,
                    "blobs/" + digest,
                    size=size,
                    digest=digest,
                    retain=False,
                )
            self._tree.inventory(descriptor, self._authority)

    def read_role(self, scope, role):
        _text(scope)
        _text(role)
        _require((scope, role) in self._authority.roles, "Unapproved scoped role.")
        record = self._authority.roles[(scope, role)]
        with self._tree.root_fd() as descriptor:
            self._tree.inventory(descriptor, self._authority)
            self._check_index(descriptor)
            raw = self._tree.read(
                descriptor, record.blob, size=record.bytes, digest=record.sha256
            )
            self._tree.inventory(descriptor, self._authority)
            return raw

    def original_label(self, scope, name):
        _text(scope)
        _text(name)
        _require((scope, name) in self._authority.labels, "Unapproved scoped label.")
        return self._authority.labels[(scope, name)][1]

    def identity(self, name):
        _text(name)
        _require(name in self._authority.identities, "Unapproved identity.")
        kind, value = self._authority.identities[name]
        return {"kind": kind, "value": value}

    def records(self):
        """A byte-transport record with deliberately impossible admission claims."""
        self._check_all()
        return {
            "schema": TRANSPORT_SCHEMA,
            "transport_only": True,
            "semantic_gate_validated": False,
            "historical_qualification": False,
            "installed_execution": False,
            "index_sha256": self._pin,
            "authority_sha256": self._authority_sha256,
            "retained_unique_bytes": self._index_bytes
            + sum(self._authority.blobs.values()),
            "retained_files": 1 + len(self._authority.blobs),
            "retained_directories": sorted(self._authority.directories),
            "roles": [
                {
                    "scope": row.scope,
                    "role": row.role,
                    "identity": row.identity,
                    "label": row.label,
                    "bytes": row.bytes,
                    "sha256": row.sha256,
                }
                for _, row in sorted(self._authority.roles.items())
            ],
        }
