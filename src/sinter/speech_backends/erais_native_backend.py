# SPDX-License-Identifier: Apache-2.0
"""Supervised local ERAIS audio-worker adapter.

This module does not contain a speech engine. It discovers an explicitly
configured native runtime manifest and sends one bounded request to the
application-managed worker. If the runtime is missing or unhealthy, the
caller must choose faster-whisper or install the native runtime; this adapter
never silently substitutes another engine.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from pathlib import Path

from .contracts import (
    BackendCapabilities,
    SpeechBackendError,
    TranscriptionRequest,
)

MANIFEST_ENV = "SINTER_ERAIS_AUDIO_MANIFEST"
DEFAULT_MANIFEST = (
    Path.home() / ".local" / "share" / "sinter" / "erais-audio" / "manifest.json")
SCHEMA = "erais.audio.runtime.v1"
REQUEST_SCHEMA = "sinter.audio.transcription.request.v1"
RESULT_SCHEMA = "sinter.audio.transcription.result.v1"
MAX_INPUT_BYTES = 500 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT = 3600
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_MODEL = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_LANG = re.compile(r"[a-z]{2,3}\Z")


def manifest_path() -> Path:
    configured = os.environ.get(MANIFEST_ENV, "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_MANIFEST


def _read_manifest(path: Path) -> dict | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return None
    worker = value.get("worker")
    if (not isinstance(worker, list) or not 1 <= len(worker) <= 8
            or any(not isinstance(item, str) or not item for item in worker)):
        return None
    executable = Path(worker[0])
    if not executable.is_absolute() or not executable.is_file():
        return None
    if not os.access(executable, os.X_OK):
        return None
    if value.get("protocol_version") != 1:
        return None
    if not isinstance(value.get("runtime_id"), str) or not value["runtime_id"]:
        return None
    if not isinstance(value.get("source_revision"), str) or not _SHA.fullmatch(
            value["source_revision"]):
        return None
    models = value.get("models")
    if (not isinstance(models, list) or not models
            or any(not isinstance(item, str) or not _MODEL.fullmatch(item)
                   for item in models)):
        return None
    languages = value.get("supported_languages", [])
    if (not isinstance(languages, list)
            or any(not isinstance(item, str) or not _LANG.fullmatch(item)
                   for item in languages)):
        return None
    timeout = value.get("timeout_seconds", DEFAULT_TIMEOUT)
    if type(timeout) is not int or not 30 <= timeout <= 24 * 3600:
        return None
    return value


def _manifest() -> tuple[dict | None, Path]:
    path = manifest_path()
    return _read_manifest(path), path


def capabilities() -> BackendCapabilities:
    value, path = _manifest()
    if value is None:
        return BackendCapabilities(
            backend_id="erais-native",
            installed=False,
            local=True,
            notice=(
                "ERAIS native audio is not installed. Set "
                f"{MANIFEST_ENV} to a verified runtime manifest or install the "
                "native audio profile."),
            manifest_identity=str(path),
        )
    return BackendCapabilities(
        backend_id="erais-native",
        installed=True,
        local=True,
        models=tuple(value["models"]),
        supported_languages=tuple(value.get("supported_languages", ())),
        word_timing=str(value.get("word_timing", "estimated")),
        channel_separation=value.get("channel_separation") is True,
        speaker_diarization=value.get("speaker_diarization") is True,
        network_required=False,
        notice="Verified local ERAIS audio runtime manifest.",
        runtime_identity=str(value["runtime_id"]),
        manifest_identity=str(path),
    )


def _request_payload(request: TranscriptionRequest, digest: str) -> dict:
    return {
        "schema": REQUEST_SCHEMA,
        "request_id": request.request_id or uuid.uuid4().hex,
        "model_id": request.model,
        "source_path": str(request.source),
        "source_sha256": digest,
        "source_bytes": request.source.stat().st_size,
        "language": request.language,
        "channel_mode": "separate" if request.split_channels else "mixed",
        "decoding_profile": "installed_default",
        "timing_requirement": "word_estimated",
        "allow_download": False,
        "retention_policy": request.retention_policy,
        "resource_envelope": {"maximum_input_duration_seconds": 4 * 3600},
    }


def transcribe(
    request: TranscriptionRequest,
    progress=lambda _message: None,
) -> dict:
    if request.consent is not True:
        raise SpeechBackendError(
            "Confirm you have permission to process this recording before "
            "transcribing.")
    value, path = _manifest()
    if value is None:
        raise SpeechBackendError(
            "ERAIS native transcription is unavailable: no verified runtime "
            f"manifest was found at {path}. Install the native audio profile "
            "or choose faster-whisper.")
    if request.model not in value["models"]:
        raise SpeechBackendError(
            "The requested model is not provided by the installed ERAIS runtime.")
    if not isinstance(request.language, str) or (
            request.language != "auto" and not _LANG.fullmatch(request.language)):
        raise SpeechBackendError(
            "Choose automatic detection or a language code such as en.")
    supported = value.get("supported_languages") or ()
    if supported and request.language != "auto" and request.language not in supported:
        raise SpeechBackendError(
            "The installed ERAIS model does not declare that language.")
    if type(request.split_channels) is not bool:
        raise SpeechBackendError("Channel separation must be true or false.")
    source = Path(request.source)
    if (not source.is_file() or source.is_symlink()
            or not 0 < source.stat().st_size <= MAX_INPUT_BYTES):
        raise SpeechBackendError("Choose a non-empty recording smaller than 500 MB.")
    digest = hashlib.sha256()
    with source.open("rb") as recording:
        for block in iter(lambda: recording.read(1024 * 1024), b""):
            digest.update(block)
    payload = _request_payload(request, digest.hexdigest())
    progress("Starting the verified local ERAIS audio worker")
    env = {key: item for key in ("PATH", "LANG", "TZ", "HOME")
           if (item := os.environ.get(key)) is not None}
    env.update({"PYTHONDONTWRITEBYTECODE": "1"})
    try:
        completed = subprocess.run(
            value["worker"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=value.get("timeout_seconds", DEFAULT_TIMEOUT),
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SpeechBackendError(
            "The ERAIS audio worker could not be started or did not finish. "
            "Check the installed runtime and retry.") from error
    if completed.returncode != 0:
        raise SpeechBackendError(
            "The ERAIS audio worker refused this recording. Check the runtime "
            "health, model installation and recording format.")
    raw = completed.stdout
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise SpeechBackendError(
            "The ERAIS audio worker returned an oversized result.")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SpeechBackendError(
            "The ERAIS audio worker returned an invalid result.") from error
    if (not isinstance(result, dict) or result.get("schema") != RESULT_SCHEMA
            or not isinstance(result.get("segments"), list)
            or not isinstance(result.get("duration"), (int, float))
            or isinstance(result.get("duration"), bool)
            or result["duration"] < 0
            or not isinstance(result.get("language"), str)
            or not isinstance(result.get("model"), str)):
        raise SpeechBackendError("The ERAIS audio worker result failed validation.")
    # The worker is trusted only for the declared result shape. Sinter still
    # supplies its own provenance receipt and does not infer speaker identity.
    result.setdefault("engine", "ERAIS native audio worker")
    result.setdefault("speaker_diarization", False)
    result.setdefault("channel_separation", request.split_channels)
    result.setdefault("status", "draft" if result["segments"] else "no_speech")
    result["audio_sha256"] = digest.hexdigest()
    result["runtime_identity"] = value["runtime_id"]
    result["source_revision"] = value["source_revision"]
    return result


__all__ = [
    "DEFAULT_MANIFEST", "MANIFEST_ENV", "REQUEST_SCHEMA", "RESULT_SCHEMA",
    "SCHEMA", "capabilities", "manifest_path", "transcribe",
]
