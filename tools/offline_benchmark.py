"""Profile local casebook preparation; no inference or browser-speed claims."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import platform
import pstats
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sinter import __version__, casebooks, client  # noqa: E402
from sinter.evidence import Excerpt, Source, validate_excerpt  # noqa: E402


def measure(book: dict, samples: int) -> dict:
    """Time preparation independently of provenance checks and instrumentation."""
    times = []
    for _ in range(samples):
        started = time.perf_counter()
        report = casebooks.build(book)
        times.append((time.perf_counter() - started) * 1000)
    sources = [Source(**row) for row in report["sources"]]
    assert all(validate_excerpt(Excerpt(**row), sources) for row in report["excerpts"])
    return {
        "samples": samples,
        "median_ms": statistics.median(times),
        "maximum_ms": max(times),
        "minimum_ms": min(times),
        "documents": len(book["documents"]),
        "characters": sum(len(row["content"]) for row in book["documents"]),
        "casebook_fingerprint": report["casebook_fingerprint"],
        "coverage": report["coverage"],
        "literal_excerpts_verified": True,
    }


def main(argv: list[str] | None = None) -> None:
    """Save a repeatable fictional workload receipt and cumulative CPU profile."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=15)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "self-audit-artifacts/offline-benchmark.json",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.samples <= 100:
        parser.error("Choose 1 to 100 samples.")
    fixture = ROOT / "examples/offline-garden/casebook.json"
    garden = json.loads(fixture.read_text())
    paragraph = (
        "Equipment quote, insurance and eligibility are unconfirmed. "
        "No spending or volunteer commitment has been approved.\n"
    )
    stress = {
        "title": "Synthetic local sizing workload",
        "questions": "\n".join(
            f"Question {n}: quote insurance eligibility?" for n in range(20)
        ),
        "documents": [
            {"title": f"Synthetic note {n}", "content": (paragraph * 60)[:6600]}
            for n in range(300)
        ],
    }
    with patch.object(
        client,
        "_open",
        side_effect=AssertionError(
            "An offline benchmark attempted an external request."
        ),
    ) as network:
        workloads = {
            "fictional_garden": measure(garden, args.samples),
            "synthetic_near_limit": measure(stress, min(args.samples, 3)),
        }
        profiler = cProfile.Profile()
        profiler.runcall(casebooks.build, stress)
        stats = pstats.Stats(profiler)
        hot = sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)
        functions = [
            {
                "file": str(Path(key[0]).relative_to(ROOT))
                if key[0].startswith(str(ROOT) + "/")
                else Path(key[0]).name,
                "line": key[1],
                "function": key[2],
                "calls": value[1],
                "self_seconds": value[2],
                "cumulative_seconds": value[3],
            }
            for key, value in hot[:12]
        ]
        tracemalloc.start()
        try:
            casebooks.build(stress)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        network.assert_not_called()
    result = {
        "schema": "sinter-offline-benchmark/v1",
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scope": "Warm local preparation only; synthetic sizing is not user "
        "acceptance, browser responsiveness or model quality.",
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "casebooks_code_sha256": hashlib.sha256(
            (ROOT / "src/sinter/casebooks.py").read_bytes()
        ).hexdigest(),
        "workloads": workloads,
        "synthetic_peak_traced_bytes": peak,
        "synthetic_cumulative_profile": functions,
        "external_requests": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    for name, row in workloads.items():
        print(
            f"{name}: median {row['median_ms']:.2f} ms; "
            f"max {row['maximum_ms']:.2f} ms; {row['characters']:,} characters"
        )
    print(f"Saved local benchmark: {args.output}")


if __name__ == "__main__":
    main()
