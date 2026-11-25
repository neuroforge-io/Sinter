# SPDX-License-Identifier: Apache-2.0
"""Bounded chunked admission for long local recordings.

Small recordings still use the existing base64 upload. Large files are admitted
as a sequence of bounded base64 chunks, so no single request has to carry the
whole recording and the browser route is not capped by one payload limit.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
import hashlib
import secrets
import threading
import time
from pathlib import Path

MAX_CHUNK_BYTES = 1024 * 1024
MAX_CHUNK_ENCODED = ((MAX_CHUNK_BYTES + 2) // 3) * 4
MAX_RECORDING_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_TTL_SECONDS = 6 * 3600
ALLOWED_SUFFIXES = {"wav", "mp3", "m4a", "ogg", "webm", "flac", "mp4"}
TERMINAL_STATUSES = {"finished", "cancelled"}


class RecordingError(ValueError):
    """The admission request is outside the bounded recording contract."""


@dataclass
class Recording:
    id: str
    filename: str
    suffix: str
    path: Path
    expected_size: int | None = None
    received: int = 0
    digest: "hashlib._Hash" = field(default_factory=hashlib.sha256)
    last_digest: str = ""
    last_size: int = 0
    status: str = "open"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def expires_at(self) -> float:
        return self.updated_at + DEFAULT_TTL_SECONDS


class Recordings:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._items: dict[str, Recording] = {}

    def _purge(self) -> None:
        now = time.time()
        for identifier, recording in list(self._items.items()):
            if recording.expires_at > now and recording.status != "cancelled":
                continue
            self._items.pop(identifier, None)
            try:
                recording.path.unlink(missing_ok=True)
            except OSError:
                pass

    def create(self, filename: str, expected_size: int | None = None) -> dict:
        if not isinstance(filename, str) or not filename.strip():
            raise RecordingError("Choose a recording file.")
        name = Path(filename.strip()).name
        suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if suffix not in ALLOWED_SUFFIXES:
            raise RecordingError(
                "Choose WAV, MP3, M4A, OGG, WebM, FLAC or MP4 audio.")
        if expected_size is not None:
            if isinstance(expected_size, bool) or not isinstance(expected_size, int):
                raise RecordingError("The expected size must be a byte count.")
            if not 0 < expected_size <= MAX_RECORDING_BYTES:
                raise RecordingError(
                    "The recording must be non-empty and smaller than 2 GB.")
        identifier = secrets.token_urlsafe(24)
        path = self.root / f"{identifier}.{suffix}"
        with self._lock:
            self._purge()
            self._items[identifier] = Recording(
                id=identifier, filename=name, suffix=suffix, path=path,
                expected_size=expected_size)
        path.touch(mode=0o600)
        return {
            "recording_id": identifier,
            "filename": name,
            "received_bytes": 0,
            "max_chunk_bytes": MAX_CHUNK_BYTES,
        }

    def _lookup(self, identifier: str) -> Recording:
        if not isinstance(identifier, str) or not identifier:
            raise RecordingError("Choose an admitted recording.")
        with self._lock:
            self._purge()
            recording = self._items.get(identifier)
            if recording is None or recording.status == "cancelled":
                raise RecordingError(
                    "This recording session expired. Start the upload again.")
            return recording

    def _get(self, identifier: str) -> Recording:
        recording = self._lookup(identifier)
        if recording.status != "open":
            raise RecordingError(
                "This recording was already finalized. Start a new upload.")
        return recording

    def append(self, identifier: str, offset: int, encoded: str) -> dict:
        recording = self._get(identifier)
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise RecordingError("The chunk offset must be a non-negative integer.")
        if not isinstance(encoded, str) or not encoded or len(encoded) > MAX_CHUNK_ENCODED:
            raise RecordingError("Each audio chunk must be from 1 byte to 1 MB.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise RecordingError("The audio chunk is not valid base64.") from error
        if not 0 < len(data) <= MAX_CHUNK_BYTES:
            raise RecordingError("Each audio chunk must be from 1 byte to 1 MB.")
        chunk_digest = hashlib.sha256(data).hexdigest()
        with self._lock:
            if recording.status != "open":
                raise RecordingError("This recording was already finalized.")
            if offset == recording.received - recording.last_size and \
                    chunk_digest == recording.last_digest:
                # Exact replay of the last accepted chunk is idempotent.
                return self._progress(recording)
            if offset != recording.received:
                raise RecordingError(
                    f"Expected chunk at byte {recording.received}, not {offset}.")
            if recording.received + len(data) > MAX_RECORDING_BYTES:
                raise RecordingError("The recording exceeded the 2 GB limit.")
            if (recording.expected_size is not None
                    and recording.received + len(data) > recording.expected_size):
                raise RecordingError(
                    "The chunk exceeds the declared recording size.")
            with recording.path.open("ab") as target:
                target.write(data)
            recording.digest.update(data)
            recording.received += len(data)
            recording.last_digest = chunk_digest
            recording.last_size = len(data)
            recording.updated_at = time.time()
            return self._progress(recording)

    @staticmethod
    def _progress(recording: Recording) -> dict:
        return {
            "recording_id": recording.id,
            "received_bytes": recording.received,
            "expected_size": recording.expected_size,
        }

    def finish(self, identifier: str) -> dict:
        recording = self._get(identifier)
        with self._lock:
            if recording.received <= 0:
                raise RecordingError("The recording has no audio.")
            if (recording.expected_size is not None
                    and recording.received != recording.expected_size):
                raise RecordingError(
                    f"Received {recording.received} of "
                    f"{recording.expected_size} declared bytes.")
            digest = recording.digest.hexdigest()
            recording.status = "finished"
            recording.updated_at = time.time()
        return {
            "recording_id": identifier,
            "filename": recording.filename,
            "size_bytes": recording.received,
            "sha256": digest,
        }

    def path(self, identifier: str) -> Path:
        recording = self._lookup(identifier)
        if recording.status != "finished":
            raise RecordingError("Finalize the recording before transcribing it.")
        if not recording.path.is_file():
            raise RecordingError("The admitted recording is no longer available.")
        return recording.path

    def release(self, identifier: str) -> None:
        with self._lock:
            recording = self._items.pop(identifier, None)
        if recording is not None:
            try:
                recording.path.unlink(missing_ok=True)
            except OSError:
                pass

    def cancel(self, identifier: str) -> dict:
        self.release(identifier)
        return {"recording_id": identifier, "status": "cancelled"}

    def close(self) -> None:
        with self._lock:
            items = list(self._items.values())
            self._items.clear()
        for recording in items:
            try:
                recording.path.unlink(missing_ok=True)
            except OSError:
                pass


__all__ = [
    "ALLOWED_SUFFIXES", "MAX_CHUNK_BYTES", "MAX_RECORDING_BYTES",
    "RecordingError", "Recordings",
]
