# SPDX-License-Identifier: Apache-2.0
"""HTTP consumer for the installed ERAIS native meeting-stream service.

The worker may be on another trusted host (for example over Tailscale). The
endpoint and bearer credential are explicit; this adapter never falls back to a
different speech engine and never labels unconfirmed speakers as identified.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import wave

from .contracts import (
    BackendCapabilities,
    SpeechBackendError,
    TranscriptionRequest,
)

URL_ENV = "SINTER_ERAIS_AUDIO_URL"
TOKEN_ENV = "SINTER_ERAIS_AUDIO_TOKEN"
TOKEN_FILE_ENV = "SINTER_ERAIS_AUDIO_TOKEN_FILE"
DEFAULT_URL = "http://127.0.0.1:8770"
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "erais" / "speech-token"
PREFIX = "/api/erais-speech/v1"
MEETINGS = PREFIX + "/meetings"
HEALTH = PREFIX + "/health"
MAX_INPUT_BYTES = 500 * 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
CHUNK_BYTES = 320_000  # 10 seconds of 16 kHz mono s16le
_LANG = re.compile(r"^[a-z]{2,3}$")


def _base_url() -> str:
    value = os.environ.get(URL_ENV, DEFAULT_URL).strip()
    if not value or len(value) > 2048:
        raise SpeechBackendError("ERAIS audio endpoint is not configured.")
    if not value.startswith(("http://", "https://")):
        raise SpeechBackendError("ERAIS audio endpoint must use HTTP or HTTPS.")
    return value.rstrip("/")


def _token() -> str:
    value = os.environ.get(TOKEN_ENV, "").strip()
    if value:
        return value
    path = Path(os.environ.get(TOKEN_FILE_ENV, str(DEFAULT_TOKEN_FILE))).expanduser()
    if not path.is_file() or path.is_symlink():
        raise SpeechBackendError(
            "ERAIS audio credential is unavailable. Set "
            f"{TOKEN_ENV} or {TOKEN_FILE_ENV}.")
    mode = path.stat().st_mode & 0o777
    if os.name == "posix" and mode & 0o077:
        raise SpeechBackendError("ERAIS audio credential file is not private.")
    value = path.read_text(encoding="utf-8").strip()
    if not 16 <= len(value) <= 512:
        raise SpeechBackendError("ERAIS audio credential is invalid.")
    return value


def _request(method: str, path: str, *, body: bytes | None = None,
             content_type: str | None = None, timeout: float = 120) -> dict:
    request = urllib.request.Request(
        _base_url() + path, data=body, method=method,
        headers={"Authorization": "Bearer " + _token(),
                 **({"Content-Type": content_type} if content_type else {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise SpeechBackendError("ERAIS audio service returned an oversized response.")
            value = json.loads(raw)
    except urllib.error.HTTPError as error:
        code = ""
        try:
            code = str(json.loads(error.read(4096)).get("error", ""))
        except Exception:
            pass
        raise SpeechBackendError(
            f"ERAIS audio service refused the request ({error.code}"
            + (f": {code})" if code else ").")) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SpeechBackendError(
            "ERAIS audio service is unreachable. Check the endpoint, tunnel "
            "and service health.") from error
    except json.JSONDecodeError as error:
        raise SpeechBackendError("ERAIS audio service returned invalid JSON.") from error
    if not isinstance(value, dict):
        raise SpeechBackendError("ERAIS audio service returned an invalid object.")
    return value


def capabilities() -> BackendCapabilities:
    try:
        value = _request("GET", HEALTH, timeout=10)
    except SpeechBackendError as error:
        return BackendCapabilities(
            backend_id="erais-neuroforge", installed=False, local=False,
            network_required=True, notice=str(error))
    backend = value.get("backend") if isinstance(value.get("backend"), dict) else {}
    model = value.get("model") if isinstance(value.get("model"), dict) else {}
    audio = value.get("audio") if isinstance(value.get("audio"), dict) else {}
    meeting = value.get("meeting_stream") if isinstance(
        value.get("meeting_stream"), dict) else {}
    identity = meeting.get("speaker_identity") if isinstance(
        meeting.get("speaker_identity"), dict) else {}
    advertised = value.get("models")
    if isinstance(advertised, list):
        models = tuple(
            item for item in advertised if isinstance(item, str) and item)
    else:
        models = tuple()
    if not models:
        models = tuple(
            item for item in (model.get("id"),) if isinstance(item, str) and item)
    labels: list[tuple[str, str]] = []
    profiles = value.get("profiles")
    if isinstance(profiles, list):
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            identifier = profile.get("id")
            label = profile.get("label")
            if (isinstance(identifier, str) and identifier
                    and isinstance(label, str) and label.strip()):
                labels.append((identifier, label.strip()))
    return BackendCapabilities(
        backend_id="erais-neuroforge",
        installed=value.get("status") == "ready",
        local=False,
        models=models,
        model_labels=tuple(labels),
        supported_languages=(),
        word_timing="word_estimated" if meeting else "unavailable",
        channel_separation=False,
        speaker_diarization=bool(
            meeting.get("speaker_diarization") is True
            and identity.get("available") is True),
        meeting_stream=bool(
            meeting.get("contract") == "erais.audio.meeting-stream.v1"),
        network_required=True,
        notice="Installed ERAIS native audio service over its explicit endpoint.",
        runtime_identity=str(backend.get("id", "")),
        manifest_identity=str(value.get("manifest_sha256", "")),
    )


def _pcm_chunks(source: Path):
    if source.suffix.lower() == ".wav":
        try:
            with wave.open(str(source), "rb") as recording:
                if (recording.getnchannels() == 1
                        and recording.getsampwidth() == 2
                        and recording.getframerate() == 16000):
                    while True:
                        chunk = recording.readframes(16000 * 10)
                        if not chunk:
                            return
                        yield chunk
        except (wave.Error, EOFError):
            pass
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SpeechBackendError(
            "The ERAIS meeting adapter needs a 16 kHz mono WAV file or ffmpeg "
            "to decode another format.")
    process = subprocess.Popen(
        [ffmpeg, "-v", "error", "-i", str(source), "-f", "s16le",
         "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    assert process.stdout is not None
    try:
        while True:
            chunk = process.stdout.read(CHUNK_BYTES)
            if not chunk:
                break
            yield chunk
    finally:
        process.stdout.close()
        code = process.wait(timeout=10)
        if code != 0:
            raise SpeechBackendError("The recording could not be decoded for ERAIS.")


def _segment(event: dict) -> dict | None:
    text = event.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    words = []
    for word in event.get("word_timestamps") or ():
        if not isinstance(word, dict):
            continue
        if not isinstance(word.get("word"), str):
            continue
        words.append({
            "start": word.get("start_s"),
            "end": word.get("end_s"),
            "word": word["word"],
        })
    return {
        "start": float(event.get("start_s", 0)),
        "end": float(event.get("end_s", 0)),
        "speaker": str(event.get("speaker", "Unidentified")),
        "text": text.strip(),
        "review_flags": [
            "Speaker identity matched a consented introduction voiceprint; "
            "confirm the named introduction against the recording."
            if event.get("speaker_identity_status") in {
                "enrolled_introduction", "voiceprint_match"} else
            "Speaker identity is unconfirmed. Confirm names against the recording."],
        "speaker_identity_status": str(
            event.get("speaker_identity_status", "unconfirmed")),
        "speaker_match_score": event.get("speaker_match_score"),
        "words": words,
    }


def transcribe(request: TranscriptionRequest, progress=lambda _message: None) -> dict:
    if request.consent is not True:
        raise SpeechBackendError(
            "Confirm you have permission to process this recording before transcribing.")
    if not isinstance(request.model, str) or not request.model:
        raise SpeechBackendError("Choose an installed ERAIS audio model.")
    if not isinstance(request.language, str) or (
            request.language != "auto" and not _LANG.fullmatch(request.language)):
        raise SpeechBackendError("Choose automatic detection or a language code such as en.")
    source = Path(request.source)
    if (not source.is_file() or source.is_symlink()
            or not 0 < source.stat().st_size <= MAX_INPUT_BYTES):
        raise SpeechBackendError("Choose a non-empty recording smaller than 500 MB.")
    health = capabilities()
    if not health.installed or not health.meeting_stream:
        raise SpeechBackendError(
            "ERAIS native meeting transcription is unavailable at the configured "
            "endpoint. Install the meeting-stream service or choose another backend.")
    if health.models and request.model not in health.models:
        raise SpeechBackendError("The requested model is not provided by the ERAIS service.")
    progress("Creating a local ERAIS meeting session")
    created = _request(
        "POST", MEETINGS,
        body=json.dumps({"consent": True, "model": request.model}).encode(),
        content_type="application/json")
    session_id = created.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise SpeechBackendError("ERAIS did not create a meeting session.")
    events: dict[int, dict] = {}
    received = 0
    try:
        for chunk in _pcm_chunks(source):
            received += len(chunk)
            progress(f"Sending {received // 32000} seconds to ERAIS")
            value = _request(
                "POST", f"{MEETINGS}/{session_id}", body=chunk,
                content_type="audio/pcm")
            for event in value.get("events") or ():
                if isinstance(event, dict) and isinstance(event.get("sequence"), int):
                    events[event["sequence"]] = event
        progress("Finishing the ERAIS meeting session")
        value = _request("POST", f"{MEETINGS}/{session_id}/finish")
        for event in value.get("events") or ():
            if isinstance(event, dict) and isinstance(event.get("sequence"), int):
                events[event["sequence"]] = event
    except Exception:
        try:
            _request("POST", f"{MEETINGS}/{session_id}/cancel")
        except SpeechBackendError:
            pass
        raise
    segments = [item for sequence in sorted(events)
                if (item := _segment(events[sequence])) is not None]
    digest = hashlib.sha256()
    with source.open("rb") as recording:
        for block in iter(lambda: recording.read(1024 * 1024), b""):
            digest.update(block)
    duration = max((item["end"] for item in segments), default=received / 32000)
    return {
        "schema_version": 1,
        "segments": segments,
        "language": "en" if request.language == "auto" else request.language,
        "languages": ["en"] if request.language == "auto" else [request.language],
        "duration": duration,
        "model": request.model,
        "audio_sha256": digest.hexdigest(),
        "engine": "ERAIS native meeting service",
        "engine_version": health.manifest_identity[:12],
        "runtime_identity": health.runtime_identity,
        "meeting_session_id": session_id,
        "speaker_diarization": health.speaker_diarization,
        "speaker_identity_available": health.speaker_diarization,
        "speaker_identity_verified": False,
        "channel_separation": False,
        "review_count": sum(bool(item["review_flags"]) for item in segments),
        "status": "draft" if segments else "no_speech",
        "warnings": [
            "Speaker labels from this service are unconfirmed unless an explicit "
            "enrolled voiceprint match is present.",
            "Check names, amounts, negation and unclear words against the recording.",
        ],
    }


__all__ = [
    "DEFAULT_URL", "HEALTH", "MEETINGS", "PREFIX", "TOKEN_ENV",
    "TOKEN_FILE_ENV", "URL_ENV", "capabilities", "transcribe",
]
