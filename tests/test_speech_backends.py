# SPDX-License-Identifier: Apache-2.0
"""Backend discovery and the bounded ERAIS native worker contract."""
from __future__ import annotations

import base64
import json
import sys
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
