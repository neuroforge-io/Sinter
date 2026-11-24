# SPDX-License-Identifier: Apache-2.0
"""Sinter consumes the installed ERAIS meeting-stream API without fallback."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import wave

import pytest

from sinter import speech
from sinter.speech_backends import erais_http_backend

TOKEN = "sinter-meeting-token-0123456789"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def _send(self, value, status=200):
        raw = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._send({"error": "unauthorized"}, 401)
        if self.path == "/api/erais-speech/v1/health":
            return self._send({
                "status": "ready",
                "backend": {"id": "erais-native-zipformer-large"},
                "model": {"id": "test-model"},
                "manifest_sha256": "a" * 64,
                "meeting_stream": {
                    "contract": "erais.audio.meeting-stream.v1",
                    "speaker_diarization": False,
                },
            })
        return self._send({"error": "not_found"}, 404)

    def do_POST(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._send({"error": "unauthorized"}, 401)
        if self.path == "/api/erais-speech/v1/meetings":
            return self._send({"session_id": "session-1"}, 201)
        if self.path.endswith("/finish"):
            return self._send({
                "status": "complete",
                "events": [{
                    "schema": "erais.audio.meeting-transcript-event.v1",
                    "sequence": 1,
                    "start_s": 0.0,
                    "end_s": 1.0,
                    "text": "The motion was not carried.",
                    "speaker": "Unidentified",
                    "speaker_identity_status": "unconfirmed",
                    "word_timestamps": [{"word": "motion", "start_s": 0.1, "end_s": 0.4}],
                }],
            })
        if "/meetings/" in self.path:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            return self._send({"status": "recording", "events": []})
        return self._send({"error": "not_found"}, 404)


def _server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    return server, thread


def _wav(path):
    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b"\x00\x00" * 16000)


def test_meeting_http_backend_full_path(tmp_path, monkeypatch):
    server, thread = _server()
    try:
        monkeypatch.setenv(
            erais_http_backend.URL_ENV,
            f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv(erais_http_backend.TOKEN_ENV, TOKEN)
        path = tmp_path / "meeting.wav"
        _wav(path)
        result = speech.transcribe(
            path, model="test-model", consent=True,
            backend="erais-neuroforge")
        assert result["engine"] == "ERAIS native meeting service"
        assert result["meeting_session_id"] == "session-1"
        assert result["segments"][0]["start"] == 0.0
        assert result["segments"][0]["end"] == 1.0
        assert result["segments"][0]["speaker"] == "Unidentified"
        assert result["segments"][0]["words"][0]["word"] == "motion"
        assert result["speaker_identity_verified"] is False
        assert result["review_count"] == 1
        capabilities = speech.capabilities()
        native = next(
            item for item in capabilities["backends"]
            if item["id"] == "erais-neuroforge")
        assert native["installed"] is True
        assert native["meeting_stream"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_missing_meeting_service_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv(erais_http_backend.URL_ENV, "http://127.0.0.1:9")
    monkeypatch.setenv(erais_http_backend.TOKEN_ENV, TOKEN)
    path = tmp_path / "meeting.wav"
    _wav(path)
    capabilities = speech.capabilities()
    native = next(
        item for item in capabilities["backends"]
        if item["id"] == "erais-neuroforge")
    assert native["installed"] is False
    with pytest.raises(ValueError, match="unavailable|unreachable"):
        speech.transcribe(
            path, model="test-model", consent=True,
            backend="erais-neuroforge")
