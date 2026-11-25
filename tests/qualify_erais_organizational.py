#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the ERAIS organizational projection through Sinter composition."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))

from sinter.meeting_semantics import Passage, analyze  # noqa: E402
from sinter.organizational_interpreter import (  # noqa: E402
    EraisOrganizationalInterpreter,
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def revision(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _event_key(event: dict) -> tuple:
    amount = event.get("amount") or {}
    return (
        event.get("event_type"),
        event.get("actor"),
        event.get("object"),
        amount.get("raw"),
        event.get("due_date"),
        event.get("outcome"),
    )


def _gold() -> list[dict]:
    return [
        {"event_type": "motion", "actor": "Alex", "object": "equipment",
         "amount": {"raw": "$600"}, "due_date": None, "outcome": None},
        {"event_type": "amendment", "actor": "Sam", "object": None,
         "amount": {"raw": "$450"}, "due_date": None, "outcome": None},
        {"event_type": "acceptance", "actor": "Alex", "object": None,
         "amount": None, "due_date": None, "outcome": None},
        {"event_type": "responsibility", "actor": "Sam",
         "object": "equipment", "amount": None, "due_date": "Friday",
         "outcome": None},
        {"event_type": "motion", "actor": "Alex", "object": "training",
         "amount": {"raw": "$300"}, "due_date": None, "outcome": None},
        {"event_type": "motion", "actor": "Sam", "object": "signage",
         "amount": {"raw": "$200"}, "due_date": None, "outcome": None},
        {"event_type": "discussion", "actor": "Alex",
         "object": "training budget", "amount": None,
         "due_date": "next month", "outcome": None},
    ]


def _passages() -> list[Passage]:
    return [
        Passage("T1", "Alex", "I propose we spend $600 on equipment."),
        Passage("T2", "Sam", "Can we change that to $450?"),
        Passage("T3", "Alex", "Agreed."),
        Passage("T4", "Sam", "I will order the equipment by Friday."),
        Passage("T5", "Alex", "I propose we allocate $300 to training."),
        Passage("T6", "Sam", "I propose we allocate $200 to signage."),
        Passage("T7", "Alex",
                "We should review the training budget next month."),
    ]


def _score(events: list[dict], gold: list[dict]) -> dict:
    comparable = [event for event in events
                  if event.get("event_type") in {
                      "motion", "amendment", "acceptance", "responsibility",
                      "discussion"}]
    gold_keys = [_event_key(item) for item in gold]
    predicted_keys = [_event_key(item) for item in comparable]
    matched = []
    used = set()
    for index, key in enumerate(gold_keys):
        try:
            position = predicted_keys.index(key)
        except ValueError:
            continue
        matched.append((index, position))
        used.add(position)
    participants = sum(
        1 for gold_index, predicted_index in matched
        if gold[gold_index].get("actor")
        == comparable[predicted_index].get("actor"))
    evidence_ok = sum(
        1 for _gold_index, predicted_index in matched
        if any(
            comparable[predicted_index].get("evidence", "") in passage.text
            for passage in _passages()))
    return {
        "gold_events": len(gold),
        "predicted_events": len(comparable),
        "matched": len(matched),
        "recall": round(len(matched) / max(1, len(gold)), 4),
        "precision": round(len(matched) / max(1, len(comparable)), 4),
        "participant_accuracy": round(
            participants / max(1, len(matched)), 4),
        "evidence_accuracy": round(evidence_ok / max(1, len(matched)), 4),
        "unmatched_gold": [
            gold[index] for index in range(len(gold))
            if index not in {item[0] for item in matched}],
        "unmatched_predicted": [
            comparable[index] for index in range(len(comparable))
            if index not in used],
    }


def _chain_checks(result: dict) -> dict:
    motions = result["motions"]
    checks = {
        "motion_count": len(motions) == 3,
        "first_amount_history": bool(motions) and [
            row["amount"]["raw"] for row in motions[0]["amount_history"]] == [
                "$600", "$450"],
        "first_acceptance": bool(motions) and motions[0].get(
            "acceptance") == "stated_agreement",
        "first_responsibility": bool(motions) and bool(
            motions[0].get("responsibility_ids")),
        "responsibility_deadline": any(
            event.get("event_type") == "responsibility"
            and event.get("due_date") == "Friday"
            for event in result["events"]),
        "second_motion": len(motions) > 1 and motions[1].get(
            "current_amount", {}).get("raw") in {None, "$300"},
        "third_motion": len(motions) > 2 and motions[2].get(
            "current_amount", {}).get("raw") in {None, "$200"},
    }
    return checks


def _correction_check(interpreter) -> dict:
    original = _passages()
    corrected = [
        Passage(item.passage_id, item.speaker,
                ("Can we change that to $425?"
                 if item.passage_id == "T2" else item.text),
                item.start, item.end)
        for item in original
    ]
    result = analyze(
        corrected, interpreter=interpreter, revision_source=original)
    motion = result["motions"][0]
    history = [row["amount"]["raw"] for row in motion["amount_history"]]
    changed = result["revision"]["changed"]
    stale = [claim for claim in result["claims"]
             if claim["claim_status"] == "stale"]
    return {
        "history": history,
        "history_corrected": history == ["$600", "$425"],
        "amendment_changed": any(
            "amount" in changes for changes in changed.values()),
        "stale_claims": len(stale),
        "motion_amendment_stale": any(
            claim["claim_type"] == "motion_amendment"
            for claim in stale),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--erais-root", type=Path,
        default=Path("/home/lloyd/erais-meeting-stream"))
    parser.add_argument(
        "--erais-python", type=Path,
        default=Path("/home/lloyd/erais/.venv/bin/python"))
    parser.add_argument(
        "--out", type=Path,
        default=HERE / "docs/audio/receipts/erais_organizational_20261126.json")
    arguments = parser.parse_args(argv)
    port = free_port()
    with tempfile.TemporaryDirectory() as directory:
        environment = {
            key: value for key, value in os.environ.items()
            if key in {"PATH", "LANG", "TZ", "HOME"}
        }
        process = subprocess.Popen(
            [str(arguments.erais_python),
             str(arguments.erais_root / "scripts/comprehension_api.py"),
             "--root", directory, "--port", str(port)],
            cwd=str(arguments.erais_root), env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(process.stderr.read())
                try:
                    connection = HTTPConnection(
                        "127.0.0.1", port, timeout=2)
                    connection.request("GET", "/api/health")
                    response = connection.getresponse()
                    response.read()
                    connection.close()
                    if response.status == 200:
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("comprehension service did not start")
            os.environ["SINTER_COMPREHENSION_URL"] = (
                f"http://127.0.0.1:{port}")
            interpreter = EraisOrganizationalInterpreter()
            result = analyze(_passages(), interpreter=interpreter)
            baseline = analyze(_passages())
            scores = _score(result["events"], _gold())
            baseline_scores = _score(baseline["events"], _gold())
            chains = _chain_checks(result)
            correction = _correction_check(interpreter)
            qualified = (
                scores["recall"] == 1.0
                and scores["precision"] == 1.0
                and scores["participant_accuracy"] == 1.0
                and scores["evidence_accuracy"] == 1.0
                and all(chains.values())
                and correction["history_corrected"]
                and correction["amendment_changed"]
                and correction["motion_amendment_stale"])
            receipt = {
                "schema": "sinter.erais-organizational-qualification.v1",
                "generated_at": datetime.now(UTC).isoformat(),
                "status": "qualified" if qualified else "unresolved",
                "erais_revision": revision(arguments.erais_root),
                "sinter_revision": revision(HERE),
                "interpreter": "erais.canonical.organizational.v1",
                "environment": {
                    "python": sys.version.split()[0],
                    "platform": sys.platform,
                },
                "erais_scores": scores,
                "deterministic_scores": baseline_scores,
                "chain_checks": chains,
                "correction": correction,
                "claims": {
                    "total": len(result["claims"]),
                    "motion_amendment": sum(
                        1 for claim in result["claims"]
                        if claim["claim_type"] == "motion_amendment"),
                },
            }
            arguments.out.parent.mkdir(parents=True, exist_ok=True)
            arguments.out.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
            print(json.dumps(receipt, indent=2, sort_keys=True))
            return 0 if qualified else 1
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
