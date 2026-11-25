# SPDX-License-Identifier: Apache-2.0
"""Bounded chunked recording admission feeds the existing transcription job."""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from sinter.recordings import MAX_CHUNK_BYTES, RecordingError, Recordings
from sinter.server import make_server


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_manager_accepts_bounded_chunks_and_replays_idempotently(tmp_path):
    manager = Recordings(tmp_path / "recordings")
    created = manager.create("meeting.wav", expected_size=6)
    identifier = created["recording_id"]
    first = manager.append(identifier, 0, _b64(b"abc"))
    assert first["received_bytes"] == 3
    assert manager.append(identifier, 0, _b64(b"abc"))["received_bytes"] == 3
    with pytest.raises(RecordingError, match="Expected chunk at byte 3"):
        manager.append(identifier, 5, _b64(b"x"))
    manager.append(identifier, 3, _b64(b"def"))
    finished = manager.finish(identifier)
    assert finished["size_bytes"] == 6
    assert finished["sha256"] == hashlib.sha256(b"abcdef").hexdigest()
    path = manager.path(identifier)
    assert path.read_bytes() == b"abcdef"
    manager.release(identifier)
    assert not path.exists()
    manager.close()


def test_manager_rejects_oversize_and_incomplete_recordings(tmp_path):
    manager = Recordings(tmp_path / "recordings")
    identifier = manager.create("meeting.wav", expected_size=4)["recording_id"]
    with pytest.raises(RecordingError, match="1 MB"):
        manager.append(identifier, 0, _b64(b"x" * (MAX_CHUNK_BYTES + 1)))
    manager.append(identifier, 0, _b64(b"ab"))
    with pytest.raises(RecordingError, match="Received 2 of 4"):
        manager.finish(identifier)
    with pytest.raises(RecordingError, match="Finalize"):
        manager.path(identifier)
    manager.close()


def _server(tmp_path):
    instance = make_server(port=0, directory=tmp_path)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    return instance, thread


def _post(server, path, payload):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request(
            "POST", path, body=json.dumps(payload),
            headers={"Content-Type": "application/json",
                     "X-Sinter-Token": server.app.token})
        response = connection.getresponse()
        return response.status, json.loads(response.read() or b"null")
    finally:
        connection.close()


def test_http_admission_reaches_transcription_and_cleans_up(
        tmp_path, monkeypatch):
    from sinter import runtime_routes

    captured = {}

    def fake_transcribe(path, **kwargs):
        captured["path"] = Path(path)
        captured["existed"] = captured["path"].is_file()
        captured["bytes"] = captured["path"].read_bytes()
        return {"segments": [], "duration": 0.0, "source": "fixture"}

    monkeypatch.setattr(runtime_routes.speech, "transcribe", fake_transcribe)
    server, thread = _server(tmp_path)
    try:
        status, created = _post(server, "/api/recordings", {
            "filename": "meeting.wav", "expected_size": 6})
        assert status == 201
        identifier = created["recording_id"]
        status, first = _post(server, "/api/recordings/chunk", {
            "recording_id": identifier, "offset": 0, "data": _b64(b"abc")})
        assert status == 200 and first["received_bytes"] == 3
        _post(server, "/api/recordings/chunk", {
            "recording_id": identifier, "offset": 3, "data": _b64(b"def")})
        status, finished = _post(
            server, "/api/recordings/finish", {"recording_id": identifier})
        assert status == 200 and finished["size_bytes"] == 6
        status, job = _post(server, "/api/transcribe", {
            "recording_id": identifier, "model": "base",
            "consent": True, "backend": "faster-whisper"})
        assert status == 202
        for _ in range(200):
            state = server.app.jobs.get(job["id"])
            if state["status"] in {"done", "failed"}:
                break
            time.sleep(0.01)
        assert state["status"] == "done", state
        assert captured["existed"] is True
        assert captured["bytes"] == b"abcdef"
        assert not captured["path"].exists()
    finally:
        server.shutdown()
        server.app.close()
        server.server_close()
        thread.join(timeout=5)


def test_out_of_order_chunk_is_rejected_over_http(tmp_path):
    server, thread = _server(tmp_path)
    try:
        _, created = _post(server, "/api/recordings", {"filename": "a.wav"})
        identifier = created["recording_id"]
        status, value = _post(server, "/api/recordings/chunk", {
            "recording_id": identifier, "offset": 10, "data": _b64(b"abc")})
        assert status == 400 and "Expected chunk" in value["error"]
    finally:
        server.shutdown()
        server.app.close()
        server.server_close()
        thread.join(timeout=5)
