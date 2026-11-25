# SPDX-License-Identifier: Apache-2.0
"""Backend discovery and the bounded ERAIS native worker contract."""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import speech
from sinter.speech_backends import erais_native_backend


def _worker(path: Path) -> Path:
    path.write_text(
        "import json, sys\n"
        "request = json.load(sys.stdin)\n"
        "assert request['schema'] == 'sinter.audio.transcription.request.v1'\n"
        "print(json.dumps({\n"
        "  'schema': 'sinter.audio.transcription.result.v1',\n"
        "  'segments': [{'start': 0, 'end': 1, 'speaker': 'Unidentified',\n"
        "               'text': 'No vote was taken.', 'review_flags': [],\n"
        "               'words': []}],\n"
        "  'language': 'en', 'duration': 1.0, 'model': 'erais-native-large',\n"
        "}))\n",
        encoding="utf-8",
    )
    return path


def _manifest(path: Path, worker: Path) -> Path:
    path.write_text(json.dumps({
        "schema": "erais.audio.runtime.v1",
        "runtime_id": "test-era-is-runtime",
        "source_revision": "a" * 40,
        "protocol_version": 1,
        "worker": [sys.executable, str(worker)],
        "models": ["erais-native-large"],
        "supported_languages": ["en"],
        "word_timing": "estimated",
        "channel_separation": True,
        "timeout_seconds": 30,
    }), encoding="utf-8")
    return path


def test_capabilities_advertise_only_the_verified_native_runtime(tmp_path, monkeypatch):
    worker = _worker(tmp_path / "worker.py")
    manifest = _manifest(tmp_path / "manifest.json", worker)
    monkeypatch.setenv(erais_native_backend.MANIFEST_ENV, str(manifest))
    value = speech.capabilities()
    native = next(
        item for item in value["backends"] if item["id"] == "erais-native")
    assert native["installed"] is True
    assert native["models"] == ["erais-native-large"]
    assert native["runtime_identity"] == "test-era-is-runtime"
    assert "erais-native" in value["available_backends"]


def test_native_transcription_uses_the_worker_without_fallback(tmp_path, monkeypatch):
    worker = _worker(tmp_path / "worker.py")
    manifest = _manifest(tmp_path / "manifest.json", worker)
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"fictional recording bytes")
    monkeypatch.setenv(erais_native_backend.MANIFEST_ENV, str(manifest))
    result = speech.transcribe(
        recording, model="erais-native-large", consent=True,
        backend="erais-native", language="en")
    assert result["engine"] == "ERAIS native audio worker"
    assert result["runtime_identity"] == "test-era-is-runtime"
    assert result["segments"][0]["text"] == "No vote was taken."
    assert len(result["audio_sha256"]) == 64


def test_missing_native_runtime_fails_closed(tmp_path, monkeypatch):
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"fictional recording bytes")
    monkeypatch.setenv(
        erais_native_backend.MANIFEST_ENV, str(tmp_path / "missing.json"))
    with pytest.raises(ValueError, match="unavailable"):
        speech.transcribe(
            recording, model="erais-native-large", consent=True,
            backend="erais-native")


def test_backend_choice_and_consent_are_explicit(tmp_path, monkeypatch):
    worker = _worker(tmp_path / "worker.py")
    manifest = _manifest(tmp_path / "manifest.json", worker)
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"fictional recording bytes")
    monkeypatch.setenv(erais_native_backend.MANIFEST_ENV, str(manifest))
    with pytest.raises(ValueError, match="permission"):
        speech.transcribe(
            recording, model="erais-native-large", consent=False,
            backend="erais-native")
    with pytest.raises(ValueError, match="local speech backend"):
        speech.transcribe(
            recording, consent=True, backend="other")


def test_upload_forwards_the_selected_backend():
    with patch.object(
            speech, "transcribe", return_value={"segments": []}) as transcribe:
        speech.transcribe_upload({
            "consent": True,
            "filename": "recording.wav",
            "audio": base64.b64encode(b"fixture").decode(),
            "backend": "erais-native",
        })
    assert transcribe.call_args.kwargs["backend"] == "erais-native"


def _meeting_worker(
    path: Path, *, delay: float = 0.0, pid_file: Path | None = None,
) -> Path:
    pid_target = str(pid_file or path.with_suffix(".pid"))
    path.write_text(
        "import json, os, sys, time\n"
        "request = json.load(sys.stdin)\n"
        "assert request['processing'] == 'meeting'\n"
        "assert request['stream'] is True\n"
        f"with open({pid_target!r}, 'w') as target:\n"
        "    target.write(str(os.getpid()))\n"
        "event_schema = 'erais.sinter-audio-worker.event.v1'\n"
        "result_schema = 'sinter.audio.transcription.result.v1'\n"
        "print(json.dumps({'schema': event_schema, 'event': 'started',\n"
        "                  'model': request['model_id']}), flush=True)\n"
        f"time.sleep({delay!r})\n"
        "segments = []\n"
        "for index in range(3):\n"
        "    segment = {'id': f'T{index:04d}', 'start': index * 2.0,\n"
        "               'end': index * 2.0 + 1.9, 'speaker': 'Unidentified',\n"
        "               'text': f'part {index}', 'review_flags': [], 'words': []}\n"
        "    segments.append(segment)\n"
        "    print(json.dumps({'schema': event_schema, 'event': 'segment',\n"
        "                      'segment': segment}), flush=True)\n"
        f"    time.sleep({delay!r})\n"
        "print(json.dumps({'schema': event_schema, 'event': 'complete',\n"
        "                  'result': {'schema': result_schema,\n"
        "                             'segments': segments, 'language': 'en',\n"
        "                             'duration': 6.0,\n"
        "                             'model': request['model_id']}}), flush=True)\n",
        encoding="utf-8",
    )
    return path


def _meeting_manifest(path: Path, worker: Path) -> Path:
    path.write_text(json.dumps({
        "schema": "erais.audio.runtime.v1",
        "runtime_id": "test-meeting-runtime",
        "source_revision": "b" * 40,
        "protocol_version": 1,
        "worker": [sys.executable, str(worker)],
        "models": ["erais-native-large"],
        "supported_languages": ["en"],
        "word_timing": "estimated",
        "meeting_stream": True,
        "max_meeting_seconds": 14400,
        "timeout_seconds": 600,
    }), encoding="utf-8")
    return path


def test_meeting_worker_streams_segments_without_a_network(
        tmp_path, monkeypatch):
    worker = _meeting_worker(tmp_path / "worker.py")
    manifest = _meeting_manifest(tmp_path / "manifest.json", worker)
    monkeypatch.setenv(erais_native_backend.MANIFEST_ENV, str(manifest))
    recording = tmp_path / "meeting.wav"
    recording.write_bytes(b"fictional meeting bytes")
    observed = []
    result = speech.transcribe(
        recording, model="erais-native-large", consent=True,
        backend="erais-native", progress=observed.append)
    kinds = [item.get("event") for item in observed if isinstance(item, dict)]
    assert kinds[0] == "session"
    assert kinds.count("segments") == 3
    assert [segment["text"] for segment in result["segments"]] == [
        "part 0", "part 1", "part 2"]
    assert result["duration"] == 6.0
    assert result["runtime_identity"] == "test-meeting-runtime"
    capabilities = speech.capabilities()
    native = next(
        item for item in capabilities["backends"] if item["id"] == "erais-native")
    assert native["meeting_stream"] is True


def test_meeting_worker_cancellation_terminates_the_process(tmp_path, monkeypatch):
    from sinter.operations import Cancelled

    pid_file = tmp_path / "pid"
    worker = _meeting_worker(
        tmp_path / "worker.py", delay=0.5, pid_file=pid_file)
    manifest = _meeting_manifest(tmp_path / "manifest.json", worker)
    monkeypatch.setenv(erais_native_backend.MANIFEST_ENV, str(manifest))
    recording = tmp_path / "meeting.wav"
    recording.write_bytes(b"fictional meeting bytes")
    seen = {"segments": 0}

    def progress(item):
        if isinstance(item, dict) and item.get("event") == "segments":
            seen["segments"] += 1
            if seen["segments"] >= 1:
                raise Cancelled()

    with pytest.raises(Cancelled):
        speech.transcribe(
            recording, model="erais-native-large", consent=True,
            backend="erais-native", progress=progress)
    pid = int(pid_file.read_text())
    for _ in range(40):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("the meeting worker was not terminated")
