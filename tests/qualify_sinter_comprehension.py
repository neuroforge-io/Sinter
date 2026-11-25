#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-pinned Sinter -> ERAIS comprehension capability transfer witness.

Starts the local ERAIS comprehension API and a Sinter server configured to
proxy it, teaches through Sinter, transfers the acquired capability, restarts
Sinter, and verifies the same capability identity remains usable.
"""
from __future__ import annotations

import argparse
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime

HERE = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def call(port, method, path, payload=None, token=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=20)
    try:
        body = None if payload is None else json.dumps(payload)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Sinter-Token"] = token
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        if response.status >= 400:
            raise RuntimeError(f"{method} {path}: {response.status} {data[:300]!r}")
        return response.status, json.loads(data or b"null")
    finally:
        connection.close()


def start(command, env, port, path):
    process = subprocess.Popen(
        command, cwd=HERE, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(process.stderr.read())
        try:
            call(port, "GET", path)
            return process
        except OSError:
            time.sleep(0.1)
    process.terminate()
    raise RuntimeError(f"service did not start: {' '.join(command)}")


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def revision(path):
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comprehension-script", type=Path, required=True)
    parser.add_argument("--comprehension-python", type=Path, required=True)
    parser.add_argument("--lesson", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    lesson = arguments.lesson.read_text(encoding="utf-8")
    root = arguments.root
    root.mkdir(parents=True, exist_ok=True)
    comprehension_root = root / "comprehension"
    sinter_root = root / "sinter"
    comprehension_root.mkdir(exist_ok=True)
    sinter_root.mkdir(exist_ok=True)
    comprehension_port = free_port()
    sinter_port = free_port()
    env = {key: item for key, item in os.environ.items()
           if key in {"PATH", "LANG", "TZ", "HOME"}}
    comprehension_env = dict(env)
    sinter_env = dict(env)
    sinter_env["PYTHONPATH"] = str(HERE / "src")
    sinter_env["SINTER_DATA_DIR"] = str(sinter_root)
    sinter_env["SINTER_COMPREHENSION_URL"] = (
        f"http://127.0.0.1:{comprehension_port}")
    receipt = {
        "schema": "sinter.comprehension-transfer-qualification.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "sinter_revision": revision(HERE),
        "sinter_root": str(sinter_root),
        "comprehension_revision": revision(
            arguments.comprehension_script.resolve().parents[1]),
        "comprehension_port": comprehension_port,
        "sinter_port": sinter_port,
        "processes": [],
        "transfers": [],
    }
    comprehension = start(
        [str(arguments.comprehension_python),
         str(arguments.comprehension_script),
         "--root", str(comprehension_root),
         "--port", str(comprehension_port)],
        comprehension_env, comprehension_port, "/api/health")
    sinter = start(
        [sys.executable, "-m", "sinter", "serve",
         "--port", str(sinter_port), "--no-browser"],
        sinter_env, sinter_port, "/api/session")
    try:
        token = call(sinter_port, "GET", "/api/session")[1]["token"]
        # Static assets are served as JavaScript, not JSON.
        connection = HTTPConnection("127.0.0.1", sinter_port, timeout=20)
        connection.request("GET", "/static/comprehension.js")
        response = connection.getresponse()
        asset = response.read().decode("utf-8")
        connection.close()
        receipt["sinter_page"] = {
            "status": response.status,
            "has_teaching_controls": "Teach and inspect" in asset,
            "has_transfer_controls": "Transfer capability" in asset,
        }
        _, created = call(
            sinter_port, "POST", "/api/comprehension/episodes", {},
            token=token)
        episode = created["episode_id"]
        receipt["episode_id"] = episode
        _, taught = call(
            sinter_port, "POST",
            f"/api/comprehension/episodes/{episode}/lesson",
            {"lesson_id": "dalven-1", "text": lesson}, token=token)
        capability = taught["inspection"]["capability_id"]
        receipt["capability_id"] = capability
        receipt["state_digest"] = taught["inspection"]["state_digest"]
        for application, task, expected in (
            ("inventory",
             "A functioning dalven contains 41 units and requires a reserve of 9. "
             "How much can be drawn?", "32"),
        ):
            _, transferred = call(
                sinter_port, "POST",
                f"/api/comprehension/episodes/{episode}/transfer",
                {"application": application, "task": task}, token=token)
            receipt["transfers"].append({
                "application": application,
                "capability_id": transferred["capability_id"],
                "answer": transferred["result"]["answer"]["exact"],
                "expected": expected,
                "phase": "before_restart",
            })
        receipt["processes"].append({
            "service": "comprehension", "pid": comprehension.pid,
            "revision": receipt["comprehension_revision"]})
        receipt["processes"].append({
            "service": "sinter", "pid": sinter.pid,
            "revision": receipt["sinter_revision"]})
    finally:
        stop(sinter)
    # Restart Sinter only; the comprehension state remains on disk.
    sinter = start(
        [sys.executable, "-m", "sinter", "serve",
         "--port", str(sinter_port), "--no-browser"],
        sinter_env, sinter_port, "/api/session")
    try:
        token = call(sinter_port, "GET", "/api/session")[1]["token"]
        _, restored = call(
            sinter_port, "GET",
            f"/api/comprehension/episodes/{episode}", token=token)
        receipt["after_restart"] = {
            "status": restored["status"],
            "revision": restored["revision"],
            "turns": len(restored["turns"]),
        }
        _, transferred = call(
            sinter_port, "POST",
            f"/api/comprehension/episodes/{episode}/transfer",
            {"application": "workspace",
             "task": "A functioning dalven contains 23 units and requires a "
                     "reserve of 7. How much can be drawn?"}, token=token)
        receipt["transfers"].append({
            "application": "workspace",
            "capability_id": transferred["capability_id"],
            "answer": transferred["result"]["answer"]["exact"],
            "expected": "16",
            "phase": "after_restart",
        })
        receipt["processes"].append({
            "service": "sinter", "pid": sinter.pid,
            "revision": receipt["sinter_revision"], "phase": "after_restart"})
        receipt["retained_after_restart"] = (
            restored.get("lab_state") is not None
            and receipt["after_restart"]["turns"] >= 2)
        receipt["status"] = (
            "qualified" if (
                receipt["sinter_page"].get("status") == 200
                and receipt["sinter_page"].get("has_teaching_controls")
                and receipt["sinter_page"].get("has_transfer_controls")
                and all(item["answer"] == item["expected"]
                        for item in receipt["transfers"])
                and all(item["capability_id"] == receipt["capability_id"]
                        for item in receipt["transfers"])
                and receipt["retained_after_restart"]) else "unresolved")
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if receipt["status"] == "qualified" else 1
    finally:
        stop(sinter)
        stop(comprehension)


if __name__ == "__main__":
    raise SystemExit(main())
