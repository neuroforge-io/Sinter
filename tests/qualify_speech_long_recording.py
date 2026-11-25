#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Manual long-recording qualification for the Sinter speech job lifecycle.

Not collected by pytest. Run it explicitly with a real configured ERAIS audio
endpoint and a real recording:

    SINTER_ERAIS_AUDIO_URL=http://127.0.0.1:18770 \
    SINTER_ERAIS_AUDIO_TOKEN_FILE=/path/to/token \
    python3 tests/qualify_speech_long_recording.py \
        --recording /path/to/meeting.wav \
        --model zipformer-gigaspeech-fp32 --out receipt.json

It starts a private loopback Sinter app, uploads through the same
``/api/transcribe`` route the browser uses, follows incremental job events by
cursor, and optionally cancels mid-stream to verify cleanup and partial events.
"""
from __future__ import annotations

import argparse
import base64
import json
import tempfile
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

from sinter.server import make_server

MAX_UPLOAD = 25 * 1024 * 1024


def request(server, path, method="GET", payload=None, token=True):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=300)
    headers = {}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Sinter-Token"] = server.app.token
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw) if raw else None
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--backend", default="erais-neuroforge")
    parser.add_argument("--language", default="en")
    parser.add_argument("--cancel-after-segments", type=int, default=0)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--transcript-out", type=Path)
    arguments = parser.parse_args()

    size = arguments.recording.stat().st_size
    if not 0 < size <= MAX_UPLOAD:
        raise SystemExit(
            f"recording is {size} bytes; the browser route admits up to {MAX_UPLOAD}")
    encoded = base64.b64encode(arguments.recording.read_bytes()).decode("ascii")
    workspace = tempfile.TemporaryDirectory(prefix="sinter-long-run-")
    server = make_server(port=0, directory=Path(workspace.name))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    started = time.monotonic()
    receipt: dict = {
        "recording": arguments.recording.name,
        "upload_mb": round(size / 1024 / 1024, 2),
        "model": arguments.model,
        "backend": arguments.backend,
    }
    try:
        status, job = request(server, "/api/transcribe", "POST", {
            "audio": encoded,
            "filename": arguments.recording.name,
            "model": arguments.model,
            "backend": arguments.backend,
            "language": arguments.language,
            "consent": True,
        })
        if status != 202 or not isinstance(job, dict):
            raise SystemExit(f"transcription was not accepted: {status} {job}")
        identifier = job["id"]
        receipt["job_id"] = identifier
        cursor = 0
        events: list[dict] = []
        first_segment_s: float | None = None
        cancelled_at: int | None = None
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            status, state = request(server, f"/api/jobs/{identifier}?after={cursor}")
            if status != 200:
                raise SystemExit(f"job poll failed: {status} {state}")
            fresh = state.pop("events", [])
            if fresh:
                expected = list(range(cursor + 1, cursor + 1 + len(fresh)))
                if [event["sequence"] for event in fresh] != expected:
                    raise SystemExit("job events were not contiguous")
                events.extend(fresh)
                cursor += len(fresh)
                segments = [event for event in events if event["event"] == "segment"]
                if segments and first_segment_s is None:
                    first_segment_s = time.monotonic() - started
                    receipt["first_segment_s"] = round(first_segment_s, 2)
                if (arguments.cancel_after_segments
                        and len(segments) >= arguments.cancel_after_segments
                        and cancelled_at is None):
                    request(server, "/api/jobs/cancel", "POST", {"id": identifier})
                    cancelled_at = len(segments)
                    receipt["cancel_requested_at_segment"] = cancelled_at
            if state["status"] in {"done", "failed", "cancelled"}:
                receipt.update({
                    "status": state["status"],
                    "elapsed_s": round(time.monotonic() - started, 2),
                    "event_count": len(events),
                    "segment_events": sum(
                        1 for event in events if event["event"] == "segment"),
                    "session_events": sum(
                        1 for event in events if event["event"] == "session"),
                    "final_message": state["message"],
                    "received_s": state["received_s"],
                    "processed_s": state["processed_s"],
                })
                if state["status"] == "done":
                    result = state["result"] or {}
                    if arguments.transcript_out:
                        arguments.transcript_out.parent.mkdir(
                            parents=True, exist_ok=True)
                        arguments.transcript_out.write_text(json.dumps(result, indent=2))
                    receipt.update({
                        "duration": result.get("duration"),
                        "segments": len(result.get("segments") or ()),
                        "review_count": result.get("review_count"),
                        "runtime_identity": result.get("runtime_identity"),
                        "engine_version": result.get("engine_version"),
                    })
                break
            time.sleep(0.5)
        else:
            raise SystemExit("job did not reach a terminal state")
        if cursor:
            status, replay = request(server, "/api/jobs/%s?after=0" % identifier)
            if status != 200 or len(replay.get("events") or ()) != cursor:
                raise SystemExit("event store did not replay the full cursor range")
            receipt["replay_verified"] = True
        print(json.dumps(receipt, indent=2, sort_keys=True))
        if arguments.out:
            arguments.out.parent.mkdir(parents=True, exist_ok=True)
            arguments.out.write_text(json.dumps(receipt, indent=2) + "\n")
        return 0 if receipt.get("status") in {"done", "cancelled"} else 1
    finally:
        server.shutdown()
        server.app.close()
        server.server_close()
        workspace.cleanup()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
