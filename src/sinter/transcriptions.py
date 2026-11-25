"""Saved transcription projects with durable partial transcript state.

A project owns a private copy of the recording, the request and runtime
identities, an append-only event log, and (when finished) the final transcript.
The event cursor is the number of committed events. Loading a project never
starts a worker; ``compatibility`` verifies the source and installed runtime
before a caller resumes it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid

SCHEMA = "sinter.transcription-project.v1"
MAX_EVENTS = 20000
MAX_EVENT_BYTES = 2 * 1024 * 1024
MAX_PROJECTS = 100
IDENTIFIER = re.compile(r"[0-9a-f]{32}\Z")
TERMINAL = {"done", "cancelled", "failed"}
RESUMABLE = {"interrupted", "cancelled", "failed"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".ogg", ".oga", ".opus", ".webm",
                  ".flac", ".mp4", ".aac", ".wma"}


class TranscriptionError(ValueError):
    """The saved project is outside the bounded local project contract."""


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise TranscriptionError("Choose a saved transcription project.")
    return value


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _segments(events: list[dict]) -> list[dict]:
    return [
        event["segment"] for event in events
        if event.get("event") == "segment"
        and isinstance(event.get("segment"), dict)
    ]


def _partial_transcript(meta: dict, segments: list[dict]) -> dict:
    duration = meta.get("duration")
    if not isinstance(duration, (int, float)):
        duration = max(
            (float(segment.get("end") or 0) for segment in segments),
            default=0.0)
    status = meta.get("status")
    return {
        "schema_version": 1,
        "segments": segments,
        "language": meta.get("request", {}).get("language", "en"),
        "duration": duration,
        "model": meta.get("request", {}).get("model"),
        "audio_sha256": meta.get("source", {}).get("sha256"),
        "engine": "ERAIS native Zipformer",
        "status": status,
        "review_count": sum(
            1 for segment in segments if segment.get("review_flags")),
        "warnings": [
            "This is a saved partial transcript. Resume or inspect the "
            "recording before relying on missing passages."],
        "runtime_receipt": {
            "model_id": meta.get("request", {}).get("model"),
            "source_mode": meta.get("runtime", {}).get("source_mode"),
            "resume_after_s": meta.get("progress", {}).get("resume_after_s"),
            "partial": True,
        },
    }


class Transcriptions:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.mark_interrupted()

    def _directory(self, identifier: str) -> Path:
        return self.root / _identifier(identifier)

    def _meta(self, identifier: str) -> dict:
        value = _read_json(self._directory(identifier) / "meta.json")
        if value is None or value.get("schema") != SCHEMA:
            raise TranscriptionError("This saved transcription is unavailable.")
        return value

    def _events(self, identifier: str) -> list[dict]:
        path = self._directory(identifier) / "events.ndjson"
        events = []
        try:
            with path.open(encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        break
                    if isinstance(event, dict):
                        events.append(event)
        except OSError:
            return []
        return events

    def create(
        self, source: Path, *, filename: str, backend: str, model: str,
        language: str, split_channels: bool, runtime_identity: str = "",
        manifest_identity: str = "",
    ) -> dict:
        source = Path(source)
        if not source.is_file() or source.is_symlink():
            raise TranscriptionError("The recording is no longer available.")
        name = Path(filename).name
        if not name or len(name) > 255:
            raise TranscriptionError("Choose a recorded file name.")
        suffix = Path(name).suffix.lower()
        if suffix not in AUDIO_SUFFIXES:
            raise TranscriptionError("Choose a supported audio recording.")
        with self._lock:
            if len(self.list()) >= MAX_PROJECTS:
                raise TranscriptionError(
                    "The workspace has 100 saved transcriptions. Remove one "
                    "before saving another.")
            identifier = uuid.uuid4().hex
            directory = self.root / identifier
            directory.mkdir(mode=0o700)
            stored = directory / ("source" + suffix)
            digest = hashlib.sha256()
            size = 0
            try:
                with source.open("rb") as reader, stored.open("wb") as writer:
                    for block in iter(lambda: reader.read(1024 * 1024), b""):
                        writer.write(block)
                        digest.update(block)
                        size += len(block)
                stored.chmod(0o600)
                if size <= 0:
                    raise TranscriptionError("The recording is empty.")
            except (OSError, TranscriptionError):
                shutil.rmtree(directory, ignore_errors=True)
                raise
            now = time.time()
            meta = {
                "schema": SCHEMA,
                "id": identifier,
                "title": name,
                "created_at": now,
                "updated_at": now,
                "status": "running",
                "attempt": 1,
                "error": "",
                "source": {
                    "filename": name,
                    "stored_name": stored.name,
                    "size_bytes": size,
                    "sha256": digest.hexdigest(),
                },
                "request": {
                    "backend": backend,
                    "model": model,
                    "language": language,
                    "split_channels": bool(split_channels),
                },
                "runtime": {
                    "runtime_identity": runtime_identity,
                    "manifest_identity": manifest_identity,
                    "source_mode": "",
                },
                "progress": {
                    "received_s": 0.0,
                    "processed_s": 0.0,
                    "resume_after_s": 0.0,
                    "event_count": 0,
                },
                "duration": 0.0,
            }
            _write_json(directory / "meta.json", meta)
            (directory / "events.ndjson").touch(mode=0o600)
            return dict(meta)

    def source_path(self, identifier: str) -> Path:
        meta = self._meta(identifier)
        path = self._directory(identifier) / meta["source"]["stored_name"]
        if not path.is_file() or path.is_symlink():
            raise TranscriptionError("The saved recording is missing.")
        return path

    def append(
        self, identifier: str, event: dict, *,
        received_s: float | None = None, processed_s: float | None = None,
        source_mode: str = "",
    ) -> dict:
        if not isinstance(event, dict):
            raise TranscriptionError("Only structured transcript events are saved.")
        line = json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
        if len(line.encode("utf-8")) > MAX_EVENT_BYTES:
            raise TranscriptionError("A transcript event is too large to save.")
        directory = self._directory(identifier)
        meta = self._meta(identifier)
        with self._lock:
            path = directory / "events.ndjson"
            size = path.stat().st_size if path.exists() else 0
            if meta["progress"]["event_count"] >= MAX_EVENTS:
                raise TranscriptionError(
                    "This saved transcription reached its event limit.")
            with path.open("ab") as target:
                target.write(line.encode("utf-8"))
                target.flush()
            meta["progress"]["event_count"] += 1
            meta["updated_at"] = time.time()
            if isinstance(received_s, (int, float)) and not isinstance(
                    received_s, bool):
                meta["progress"]["received_s"] = float(received_s)
            if isinstance(processed_s, (int, float)) and not isinstance(
                    processed_s, bool):
                meta["progress"]["processed_s"] = float(processed_s)
                meta["progress"]["resume_after_s"] = float(processed_s)
            if source_mode:
                meta["runtime"]["source_mode"] = str(source_mode)[:40]
            _write_json(directory / "meta.json", meta)
        return {"event_count": meta["progress"]["event_count"],
                "next_cursor": meta["progress"]["event_count"],
                "bytes": size + len(line.encode("utf-8"))}

    def finish(
        self, identifier: str, *, result: dict | None = None,
        status: str = "done", error: str = "",
    ) -> dict:
        if status not in TERMINAL:
            raise TranscriptionError("A finished project needs a terminal status.")
        directory = self._directory(identifier)
        meta = self._meta(identifier)
        with self._lock:
            if isinstance(result, dict):
                _write_json(directory / "result.json", result)
                duration = result.get("duration")
                if isinstance(duration, (int, float)) and not isinstance(
                        duration, bool):
                    meta["duration"] = float(duration)
                runtime = result.get("runtime_receipt") or {}
                if isinstance(runtime, dict):
                    meta["runtime"]["source_mode"] = str(
                        runtime.get("source_mode") or "")[:40]
            meta["status"] = status
            meta["error"] = str(error)[:1000]
            meta["updated_at"] = time.time()
            _write_json(directory / "meta.json", meta)
        return dict(meta)

    def begin_resume(self, identifier: str) -> dict:
        directory = self._directory(identifier)
        meta = self._meta(identifier)
        if meta.get("status") not in RESUMABLE:
            raise TranscriptionError(
                "Only an interrupted, cancelled or failed project can resume.")
        with self._lock:
            meta["status"] = "running"
            meta["attempt"] = int(meta.get("attempt") or 1) + 1
            meta["error"] = ""
            meta["updated_at"] = time.time()
            (directory / "result.json").unlink(missing_ok=True)
            _write_json(directory / "meta.json", meta)
        return dict(meta)

    def get(self, identifier: str, *, include_events: bool = False) -> dict:
        meta = self._meta(identifier)
        events = self._events(identifier)
        segments = _segments(events)
        result = _read_json(self._directory(identifier) / "result.json")
        transcript = result if isinstance(result, dict) else _partial_transcript(
            meta, segments)
        payload = dict(meta)
        payload["next_cursor"] = len(events)
        payload["segments"] = (
            transcript.get("segments") if isinstance(transcript, dict) else [])
        payload["transcript"] = transcript
        payload["source_present"] = (
            self._directory(identifier) / meta["source"]["stored_name"]).is_file()
        if include_events:
            payload["events"] = events
        return payload

    def compatibility(self, identifier: str, backends: list[dict]) -> dict:
        meta = self._meta(identifier)
        directory = self._directory(identifier)
        source = directory / meta["source"]["stored_name"]
        issues = []
        source_intact = source.is_file() and not source.is_symlink()
        if not source_intact:
            issues.append("The saved recording is missing.")
        else:
            if source.stat().st_size != meta["source"]["size_bytes"]:
                source_intact = False
                issues.append("The saved recording changed size.")
            elif _digest(source) != meta["source"]["sha256"]:
                source_intact = False
                issues.append("The saved recording digest changed.")
        backend = next(
            (item for item in backends
             if item.get("id") == meta["request"]["backend"]), None)
        if backend is None or backend.get("installed") is not True:
            issues.append("The saved recognition backend is not installed.")
        elif meta["request"]["model"] not in (backend.get("models") or []):
            issues.append("The saved recognition model is not installed.")
        elif (meta["runtime"].get("runtime_identity")
              and backend.get("runtime_identity")
              and meta["runtime"]["runtime_identity"]
              != backend["runtime_identity"]):
            issues.append(
                "The installed runtime identity differs from the saved one.")
        events = self._events(identifier)
        segments = _segments(events)
        resume_after = max(
            (float(segment.get("end") or 0) for segment in segments),
            default=0.0)
        return {
            "compatible": not issues,
            "source_intact": source_intact,
            "issues": issues,
            "status": meta.get("status"),
            "resumable": (
                meta.get("status") in RESUMABLE
                and meta["request"]["backend"] == "erais-native"),
            "resume_after_s": round(resume_after, 4),
            "committed_segments": len(segments),
            "next_cursor": len(events),
            "runtime_identity": meta["runtime"].get("runtime_identity", ""),
        }

    def list(self) -> list[dict]:
        rows = []
        for directory in self.root.iterdir():
            if not directory.is_dir() or not IDENTIFIER.fullmatch(directory.name):
                continue
            meta = _read_json(directory / "meta.json")
            if meta is None or meta.get("schema") != SCHEMA:
                continue
            rows.append({
                "id": meta["id"],
                "title": meta.get("title", "Recording"),
                "status": meta.get("status"),
                "created_at": meta.get("created_at"),
                "updated_at": meta.get("updated_at"),
                "duration": meta.get("duration"),
                "attempt": meta.get("attempt"),
                "model": meta.get("request", {}).get("model"),
                "backend": meta.get("request", {}).get("backend"),
                "runtime_identity": meta.get("runtime", {}).get(
                    "runtime_identity", ""),
                "event_count": meta.get("progress", {}).get("event_count", 0),
                "segment_count": sum(
                    1 for event in self._events(meta["id"])
                    if event.get("event") == "segment"),
                "source_bytes": meta.get("source", {}).get("size_bytes"),
            })
        return sorted(rows, key=lambda row: row.get("updated_at") or 0,
                      reverse=True)

    def delete(self, identifier: str) -> None:
        directory = self._directory(identifier)
        if directory.exists():
            shutil.rmtree(directory)

    def mark_interrupted(self) -> None:
        for directory in self.root.iterdir():
            if not directory.is_dir() or not IDENTIFIER.fullmatch(directory.name):
                continue
            meta = _read_json(directory / "meta.json")
            if meta is None or meta.get("schema") != SCHEMA:
                continue
            if meta.get("status") == "running":
                meta["status"] = "interrupted"
                meta["updated_at"] = time.time()
                _write_json(directory / "meta.json", meta)

    def close(self) -> None:
        pass


__all__ = ["TranscriptionError", "Transcriptions"]
