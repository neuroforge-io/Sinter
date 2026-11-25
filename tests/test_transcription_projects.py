# SPDX-License-Identifier: Apache-2.0
"""Saved transcription projects survive process restart with their cursor."""
from __future__ import annotations

import base64
import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from sinter import runtime_routes
from sinter.server import make_server
from sinter.transcriptions import TranscriptionError, Transcriptions

BACKEND = {
    "id": "erais-native",
    "installed": True,
    "models": ["zipformer-test-fp32"],
    "runtime_identity": "runtime-test",
    "manifest_identity": "/fixture/manifest.json",
    "network_required": False,
}


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


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


def _get(server, path):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request("GET", path, headers={
            "X-Sinter-Token": server.app.token})
        response = connection.getresponse()
        return response.status, json.loads(response.read() or b"null")
    finally:
        connection.close()


def _server(tmp_path):
    server = make_server(port=0, directory=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop(server, thread):
    server.shutdown()
    server.app.close()
    server.server_close()
    thread.join(timeout=5)


def _wait(server, identifier):
    for _ in range(400):
        status, state = _get(server, f"/api/jobs/{identifier}")
        if status == 200 and state["status"] in {"done", "failed", "cancelled"}:
            return state
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def _segment(identifier, start, end, text):
    return {
        "id": identifier, "start": start, "end": end, "speaker": "Unidentified",
        "text": text, "review_flags": [],
        "words": [{"word": text.split()[0], "start": start, "end": end}],
    }


def _result(segments, duration):
    return {
        "schema_version": 1, "segments": segments, "language": "en",
        "duration": duration, "model": "zipformer-test-fp32",
        "engine": "fixture", "status": "draft",
        "review_count": sum(bool(row["review_flags"]) for row in segments),
        "runtime_receipt": {
            "model_id": "zipformer-test-fp32",
            "source_mode": "bounded_wav",
            "runtime_identity": "runtime-test",
        },
    }


def _upload(server, path: Path):
    _, created = _post(server, "/api/recordings", {
        "filename": path.name, "expected_size": path.stat().st_size})
    identifier = created["recording_id"]
    offset = 0
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            status, _ = _post(server, "/api/recordings/chunk", {
                "recording_id": identifier, "offset": offset,
                "data": _b64(block)})
            assert status == 200
            offset += len(block)
    status, finished = _post(server, "/api/recordings/finish", {
        "recording_id": identifier})
    assert status == 200 and finished["size_bytes"] == path.stat().st_size
    return identifier


def _wav(path: Path, seconds: float = 4.0) -> None:
    import wave
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x00\x00" * int(seconds * 16_000))


def test_saved_project_survives_restart_with_cursor_and_segments(
        tmp_path, monkeypatch):
    recording = tmp_path / "meeting.wav"
    _wav(recording)
    segments = [_segment("T0001", 0.0, 2.0, "fixture words"),
                _segment("T0002", 2.0, 4.0, "more words")]

    def fake_transcribe(path, **kwargs):
        progress = kwargs["progress"]
        progress({"event": "session", "session": {"id": "session-1"}})
        for segment in segments:
            progress({
                "event": "segments", "segments": [segment],
                "received_s": segment["end"], "processed_s": segment["end"],
            })
        return _result(segments, 4.0)

    monkeypatch.setattr(runtime_routes.speech, "transcribe", fake_transcribe)
    monkeypatch.setattr(runtime_routes.speech, "capabilities", lambda: {
        "backends": [BACKEND]})
    server, thread = _server(tmp_path)
    try:
        recording_id = _upload(server, recording)
        status, started = _post(server, "/api/transcribe", {
            "recording_id": recording_id, "backend": "erais-native",
            "model": "zipformer-test-fp32", "consent": True, "save": True,
            "filename": "Fictional meeting.wav",
        })
        assert status == 202 and started["project"]
        state = _wait(server, started["id"])
        assert state["status"] == "done", state
        project_id = started["project"]
        status, project = _get(server, f"/api/transcriptions/{project_id}")
        assert status == 200
        assert project["status"] == "done"
        assert project["next_cursor"] >= 3
        assert [row["id"] for row in project["segments"]] == ["T0001", "T0002"]
        assert project["source_present"] is True
        assert project["runtime"]["runtime_identity"] == "runtime-test"
    finally:
        _stop(server, thread)

    # A fresh process reads the same workspace directory.
    server, thread = _server(tmp_path)
    try:
        status, listing = _get(server, "/api/transcriptions")
        assert status == 200
        assert [row["id"] for row in listing["transcriptions"]] == [project_id]
        status, project = _get(server, f"/api/transcriptions/{project_id}")
        assert project["status"] == "done"
        assert [row["id"] for row in project["segments"]] == ["T0001", "T0002"]
        assert project["transcript"]["segments"][1]["text"] == "more words"
        assert project["next_cursor"] >= 3
        assert project["source_present"] is True
    finally:
        _stop(server, thread)


def test_interrupted_project_restores_partial_transcript_and_resumes(
        tmp_path, monkeypatch):
    recording = tmp_path / "meeting.wav"
    _wav(recording, 6.0)
    store = Transcriptions(tmp_path / "transcriptions")
    project = store.create(
        recording, filename="Fictional meeting.wav", backend="erais-native",
        model="zipformer-test-fp32", language="en", split_channels=False,
        runtime_identity="runtime-test", manifest_identity="/fixture/manifest.json")
    prior = [_segment("T0001", 0.0, 2.0, "first words"),
             _segment("T0002", 2.0, 4.0, "second words")]
    for segment in prior:
        store.append(project["id"], {"event": "segment", "segment": segment},
                     processed_s=segment["end"])
    # Simulate a crash: the status is still running on disk.
    del store

    resumed_segments = [_segment("T0003", 4.0, 6.0, "third words")]

    def fake_transcribe(path, **kwargs):
        assert kwargs["resume_after_s"] == pytest.approx(4.0)
        assert kwargs["consent"] is True
        kwargs["progress"]({
            "event": "segments", "segments": resumed_segments,
            "processed_s": 6.0})
        result = _result(resumed_segments, 6.0)
        result["runtime_receipt"]["resumed"] = True
        return result

    monkeypatch.setattr(runtime_routes.speech, "transcribe", fake_transcribe)
    monkeypatch.setattr(runtime_routes.speech, "capabilities", lambda: {
        "backends": [BACKEND]})
    server, thread = _server(tmp_path)
    try:
        listing = _get(server, "/api/transcriptions")[1]["transcriptions"]
        identifier = listing[0]["id"]
        assert listing[0]["status"] == "interrupted"
        status, project = _get(server, f"/api/transcriptions/{identifier}")
        assert project["status"] == "interrupted"
        assert project["segments"] == prior
        assert project["next_cursor"] == 2
        status, compatibility = _get(
            server, f"/api/transcriptions/{identifier}/compatibility")
        assert compatibility["compatible"] is True
        assert compatibility["resumable"] is True
        assert compatibility["resume_after_s"] == 4.0
        status, started = _post(
            server, f"/api/transcriptions/{identifier}/resume",
            {"consent": True})
        assert status == 202, started
        state = _wait(server, started["id"])
        assert state["status"] == "done", state
        status, project = _get(server, f"/api/transcriptions/{identifier}")
        assert [row["id"] for row in project["segments"]] == [
            "T0001", "T0002", "T0003"]
        assert project["status"] == "done"
        assert project["attempt"] == 2
    finally:
        _stop(server, thread)


def test_resume_refuses_tampered_source(tmp_path, monkeypatch):
    recording = tmp_path / "meeting.wav"
    _wav(recording, 3.0)
    store = Transcriptions(tmp_path / "transcriptions")
    project = store.create(
        recording, filename="meeting.wav", backend="erais-native",
        model="zipformer-test-fp32", language="en", split_channels=False,
        runtime_identity="runtime-test")
    store.append(project["id"], {"event": "segment",
        "segment": _segment("T0001", 0.0, 2.0, "hello")})
    source = tmp_path / "transcriptions" / project["id"] / "source.wav"
    payload = bytearray(source.read_bytes())
    payload[-1] ^= 0xFF
    source.write_bytes(payload)
    monkeypatch.setattr(runtime_routes.speech, "capabilities", lambda: {
        "backends": [BACKEND]})
    server, thread = _server(tmp_path)
    try:
        status, compatibility = _get(
            server, f"/api/transcriptions/{project['id']}/compatibility")
        assert compatibility["compatible"] is False
        assert any("digest" in issue for issue in compatibility["issues"])
        status, refused = _post(
            server, f"/api/transcriptions/{project['id']}/resume",
            {"consent": True})
        assert status == 409
        assert "cannot resume" in refused["error"]
    finally:
        _stop(server, thread)


def test_project_rejects_unknown_identifier(tmp_path):
    store = Transcriptions(tmp_path / "transcriptions")
    with pytest.raises(TranscriptionError):
        store.get("../../etc/passwd")


def _get_bytes(server, path):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request("GET", path, headers={
            "X-Sinter-Token": server.app.token})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_saved_project_audio_is_served_without_exposing_a_path(
        tmp_path, monkeypatch):
    recording = tmp_path / "meeting.wav"
    _wav(recording, 2.0)
    original = recording.read_bytes()

    def fake_transcribe(path, **kwargs):
        return _result([], 2.0)

    monkeypatch.setattr(runtime_routes.speech, "transcribe", fake_transcribe)
    monkeypatch.setattr(runtime_routes.speech, "capabilities", lambda: {
        "backends": [BACKEND]})
    server, thread = _server(tmp_path)
    try:
        recording_id = _upload(server, recording)
        _, started = _post(server, "/api/transcribe", {
            "recording_id": recording_id, "backend": "erais-native",
            "model": "zipformer-test-fp32", "consent": True, "save": True,
        })
        _wait(server, started["id"])
        status, headers, payload = _get_bytes(
            server, f"/api/transcriptions/{started['project']}/audio")
        assert status == 200
        assert headers["Content-Type"] == "audio/wav"
        assert payload == original
        assert headers["Accept-Ranges"] == "none"
    finally:
        _stop(server, thread)


def test_saving_requires_consent_before_any_copy(tmp_path, monkeypatch):
    recording = tmp_path / "meeting.wav"
    _wav(recording, 2.0)
    monkeypatch.setattr(runtime_routes.speech, "capabilities", lambda: {
        "backends": [BACKEND]})
    server, thread = _server(tmp_path)
    try:
        recording_id = _upload(server, recording)
        status, refused = _post(server, "/api/transcribe", {
            "recording_id": recording_id, "backend": "erais-native",
            "model": "zipformer-test-fp32", "consent": False, "save": True,
        })
        assert status == 400 and "permission" in refused["error"].lower()
        _, listing = _get(server, "/api/transcriptions")
        assert listing["transcriptions"] == []
    finally:
        _stop(server, thread)
