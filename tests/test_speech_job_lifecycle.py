"""Long-recording job lifecycle over the ERAIS meeting transport."""
from __future__ import annotations

import json
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sinter import speech
from sinter.jobs import Jobs
from sinter.speech_backends import erais_http_backend

TOKEN = "job-lifecycle-token-0123456789"
CANCELS: list[str] = []


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
                "profiles": [{"id": "meeting-model", "label": "Meeting candidate"}],
                "manifest_sha256": "c" * 64,
                "meeting_stream": {
                    "contract": "erais.audio.meeting-stream.v1",
                    "speaker_diarization": False,
                },
            })
        return self._send({"error": "not_found"}, 404)

    def do_POST(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._send({"error": "unauthorized"}, 401)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/api/erais-speech/v1/meetings":
            return self._send({
                "session_id": "session-long",
                "model": "meeting-model",
                "backend_id": "erais-native-zipformer-gigaspeech",
                "manifest_sha256": "c" * 64,
            }, 201)
        if self.path.endswith("/cancel"):
            CANCELS.append(self.path)
            return self._send({"status": "cancelled", "events": []})
        if self.path.endswith("/finish"):
            return self._send({"status": "complete", "events": []})
        if "/meetings/" in self.path:
            time.sleep(0.02)
            seconds = len(body) / 32000
            start = self.server.received
            self.server.received += seconds
            if seconds < 10:
                # A short final chunk can be trailing silence: send no event.
                return self._send({"status": "recording", "events": []})
            self.server.chunks += 1
            number = self.server.chunks
            return self._send({
                "status": "recording",
                "events": [{
                    "schema": "erais.audio.meeting-transcript-event.v1",
                    "sequence": number,
                    "start_s": round(start, 3),
                    "end_s": round(start + seconds, 3),
                    "text": f"part {number}",
                    "speaker": "Unidentified",
                    "speaker_identity_status": "unconfirmed",
                    "word_timestamps": [],
                }],
            })
        return self._send({"error": "not_found"}, 404)


@pytest.fixture
def endpoint(monkeypatch):
    CANCELS.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    server.chunks = 0
    server.received = 0.0
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


def test_segments_stream_before_finish_and_duration_keeps_trailing_silence(
        tmp_path, endpoint):
    recording = tmp_path / "meeting.wav"
    _wav(recording, 35)
    observed: list[dict] = []

    result = speech.transcribe(
        recording, model="meeting-model", consent=True,
        backend="erais-neuroforge", progress=observed.append)

    session = [item for item in observed
               if isinstance(item, dict) and item["event"] == "session"]
    assert session and session[0]["session"]["backend"] == (
        "erais-native-zipformer-gigaspeech")
    segments = [segment for item in observed
                if isinstance(item, dict) and item["event"] == "segments"
                for segment in item["segments"]]
    assert [segment["text"] for segment in segments] == [
        "part 1", "part 2", "part 3"]
    # Progress arrived while chunks were still being sent, not only at the end.
    first_segment_index = next(
        index for index, item in enumerate(observed)
        if isinstance(item, dict) and item["event"] == "segments")
    assert any(isinstance(item, str) and item.startswith("Finishing")
               for item in observed[first_segment_index:])
    assert result["duration"] == 35.0
    assert result["segments"][-1]["end"] == 30.0


def wait_job(jobs: Jobs, identifier: str, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = jobs.get(identifier)
        if job["status"] in {"done", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("Job did not finish")


def test_cancelled_long_job_keeps_partial_events_and_closes_the_session(
        tmp_path, endpoint):
    recording = tmp_path / "meeting.wav"
    _wav(recording, 120)
    jobs = Jobs()
    try:
        identifier = jobs.submit(
            lambda progress: speech.transcribe(
                recording, model="meeting-model", consent=True,
                backend="erais-neuroforge", progress=progress),
            label="Meeting transcription")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if jobs.get(identifier)["next_cursor"] >= 2:
                break
            time.sleep(0.01)
        jobs.cancel(identifier)
        cancelled = wait_job(jobs, identifier)
        assert cancelled["status"] == "cancelled"
        assert "partial transcript" in cancelled["message"]
        events = jobs.get(identifier, after=0)["events"]
        assert events[0]["event"] == "session"
        assert any(event["event"] == "segment" for event in events)
        assert CANCELS == ["/api/erais-speech/v1/meetings/session-long/cancel"]
    finally:
        jobs.close()
