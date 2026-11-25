"""Speaker revisions from the ERAIS service replace provisional passage labels."""
from __future__ import annotations

import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sinter import speech
from sinter.speech_backends import erais_http_backend

TOKEN = "speaker-revision-token-0123456789"


def _event(revision: int, status: str, speaker: str) -> dict:
    return {
        "schema": "erais.audio.meeting-transcript-event.v1",
        "sequence": 1,
        "start_s": 0.0,
        "end_s": 2.0,
        "text": "The motion was carried.",
        "speaker": speaker,
        "speaker_identity_status": status,
        "speaker_confidence": 0.9 if status == "anonymous_cluster" else None,
        "speaker_cluster": "Speaker A" if status == "anonymous_cluster" else None,
        "word_timestamps": [],
        "revision": revision,
    }


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
                "backend": {"id": "erais-native-zipformer-gigaspeech"},
                "model": {"id": "meeting-model"},
                "models": ["meeting-model"],
                "manifest_sha256": "d" * 64,
                "meeting_stream": {
                    "contract": "erais.audio.meeting-stream.v1",
                    "speaker_diarization": True,
                    "speaker_identity": {"available": True},
                },
            })
        return self._send({"error": "not_found"}, 404)

    def do_POST(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._send({"error": "unauthorized"}, 401)
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.path == "/api/erais-speech/v1/meetings":
            return self._send({"session_id": "session-1", "model": "meeting-model"}, 201)
        if self.path.endswith("/finish"):
            return self._send({"status": "complete", "events": [
                _event(2, "anonymous_cluster", "Speaker A")]})
        if self.path.endswith("/cancel"):
            return self._send({"status": "cancelled", "events": []})
        return self._send({"status": "recording", "events": [
            _event(1, "speaker_pending", "Unidentified")]})


@pytest.fixture
def endpoint(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    monkeypatch.setenv(
        erais_http_backend.URL_ENV, f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv(erais_http_backend.TOKEN_ENV, TOKEN)
    yield server
    server.shutdown()
    server.server_close()
    thread.join(2)


def _wav(path, seconds: float) -> None:
    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b"\x00\x00" * int(seconds * 16000))


def test_finish_revision_replaces_the_provisional_speaker_label(tmp_path, endpoint):
    recording = tmp_path / "meeting.wav"
    _wav(recording, 2)
    observed = []
    result = speech.transcribe(
        recording, model="meeting-model", consent=True,
        backend="erais-neuroforge", progress=observed.append)
    assert len(result["segments"]) == 1
    segment = result["segments"][0]
    assert segment["speaker"] == "Speaker A"
    assert segment["speaker_identity_status"] == "anonymous_cluster"
    assert segment["speaker_cluster"] == "Speaker A"
    assert segment["speaker_confidence"] == 0.9
    assert "anonymous cluster" in segment["review_flags"][0]
    emitted = [item for item in observed
               if isinstance(item, dict) and item["event"] == "segments"]
    assert emitted[-1]["segments"][0]["speaker"] == "Speaker A"
    assert result["speaker_diarization"] is True
