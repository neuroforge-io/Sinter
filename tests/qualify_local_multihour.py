#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Manual multi-hour local qualification for the Sinter meeting worker.

Not collected by pytest. It starts a private loopback Sinter app, submits the
local ERAIS backend directly (the browser upload route is limited to 25 MB),
follows incremental job events, samples worker/Sinter RSS, and can cancel.

    python3 tests/qualify_local_multihour.py \
        --recording /path/to/long.wav \
        --model zipformer-gigaspeech-fp32 --out receipt.json
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

from sinter import speech
from sinter.server import make_server

WORKER_MARKER = b"erais.integration.sinter_worker"


def request(server, path, method="GET", payload=None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=60)
    headers = {"X-Sinter-Token": server.app.token}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw) if raw else None
    finally:
        connection.close()


def _rss_kb(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def _worker_pids() -> list[int]:
    pids = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if WORKER_MARKER in cmdline:
            pids.append(int(entry.name))
    return pids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--backend", default="erais-native")
    parser.add_argument("--cancel-after-segments", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=7200)
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()
    size = arguments.recording.stat().st_size
    server = make_server(
        port=0, directory=arguments.recording.parent / ".sinter-multihour")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    receipt: dict = {
        "recording": arguments.recording.name,
        "size_mb": round(size / 1024 / 1024, 2),
        "backend": arguments.backend,
        "model": arguments.model,
    }
    started = time.monotonic()
    try:
        identifier = server.app.jobs.submit(
            lambda progress: speech.transcribe(
                arguments.recording, model=arguments.model, consent=True,
                backend=arguments.backend, progress=progress),
            label="Long local meeting",
            timeout=arguments.timeout,
        )
        receipt["job_id"] = identifier
        cursor = 0
        segments = 0
        peak_worker = peak_sinter = 0
        first_segment = None
        cancelled = False
        while True:
            status, state = request(
                server, f"/api/jobs/{identifier}?after={cursor}")
            if status != 200:
                raise SystemExit(f"poll failed: {status} {state}")
            fresh = state.pop("events", [])
            if fresh:
                cursor += len(fresh)
                segments += sum(
                    1 for event in fresh if event.get("event") == "segment")
                if segments and first_segment is None:
                    first_segment = round(time.monotonic() - started, 2)
            peak_sinter = max(peak_sinter, _rss_kb(os.getpid()))
            for pid in _worker_pids():
                peak_worker = max(peak_worker, _rss_kb(pid))
            if (arguments.cancel_after_segments
                    and segments >= arguments.cancel_after_segments
                    and not cancelled):
                request(server, "/api/jobs/cancel", "POST", {"id": identifier})
                cancelled = True
                receipt["cancel_requested_at_segment"] = segments
            if state["status"] in {"done", "failed", "cancelled"}:
                receipt.update({
                    "status": state["status"],
                    "error": state["error"],
                    "message": state["message"],
                    "elapsed_s": round(time.monotonic() - started, 2),
                    "first_segment_s": first_segment,
                    "segment_events": segments,
                    "event_count": cursor,
                    "peak_worker_rss_mb": round(peak_worker / 1024, 1),
                    "peak_sinter_rss_mb": round(peak_sinter / 1024, 1),
                    "received_s": state.get("received_s"),
                    "processed_s": state.get("processed_s"),
                })
                if state["status"] == "done":
                    result = state["result"] or {}
                    receipt.update({
                        "duration": result.get("duration"),
                        "segments": len(result.get("segments") or ()),
                        "review_count": result.get("review_count"),
                        "speaker_diarization": result.get("speaker_diarization"),
                        "runtime_identity": result.get("runtime_identity"),
                    })
                    speakers: dict[str, int] = {}
                    for segment in result.get("segments") or ():
                        key = str(segment.get("speaker", "Unidentified"))
                        speakers[key] = speakers.get(key, 0) + 1
                    receipt["speakers"] = speakers
                break
            time.sleep(2)
        time.sleep(1)
        receipt["worker_processes_after"] = len(_worker_pids())
        print(json.dumps(receipt, indent=2, sort_keys=True))
        if arguments.out:
            arguments.out.parent.mkdir(parents=True, exist_ok=True)
            arguments.out.write_text(json.dumps(receipt, indent=2) + "\n")
        return 0 if receipt["status"] in {"done", "cancelled"} else 1
    finally:
        server.shutdown()
        server.app.close()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
