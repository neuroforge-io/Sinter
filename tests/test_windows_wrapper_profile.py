"""Same-runner A/B/B/A launcher qualification with unchanged readiness assertions."""

import functools
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import venv
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_review_recovery as fixtures
import test_wrapper_fixture_lanes as selection

BASELINE_SHA256 = "319f2079a920f22ce1878f64a6a2b0b38e18f7c42019a137070b63fc41c50cf7"
WINDOWS = pytest.mark.skipif(
    os.name != "nt" or os.environ.get("SINTER_WINDOWS_WRAPPER_PROFILE") != "1",
    reason="Dedicated actual Windows launcher comparison required.",
)


def _git_bytes(path):
    return subprocess.check_output(["git", "show", "HEAD:" + path], timeout=5)


def _save(name, value):
    output = Path(os.environ["SINTER_STARTUP_DIAGNOSTICS_DIR"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    path = output / name
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def _request():
    return SimpleNamespace(node=SimpleNamespace(user_properties=[]))


def _observation(request):
    values = [json.loads(v) for k, v in request.node.user_properties
              if k == "sinter_wrapper_diagnostics"]
    assert len(values) == 1, "Retain exactly one completed observation per launch."
    return values[0]


def _prove_closed(value):
    proof = value.get("owned_tree")
    assert isinstance(proof, dict) and proof["clean"], value
    assert proof["active_after"] == 0 and proof["parent_reaped"], value
    assert value["cleanup_errors"] == [], value
    assert value["timeout_seconds"] == 5
    assert value["owned_cleanup_budget_seconds"] == 2
    assert value["phase_timing"]["wait_budget_seconds"] == 5


def _entry_identity(directory):
    entries = list(directory.rglob("start.py"))
    assert len(entries) == 1
    data = entries[0].read_bytes()
    text = data.decode("utf-8")
    # Absolute per-cell marker paths differ; normalize only that declared prefix.
    prefix = repr(str(directory))[1:-1]
    normalized = text.replace(prefix, "FIXTURE_CELL")
    return {
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "normalized_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    }


def _retain_control(label, request, action, *, phases=True, save_success=True):
    try:
        action()
    except BaseException as error:
        try:
            if request.node.user_properties:
                _save(label + ".json", _observation(request))
            elif hasattr(error, "wrapper_observation"):
                _save(label + ".json", error.wrapper_observation)
            else:
                _save(label + ".json", {
                    "setup_or_outcome_unconfirmed": True,
                    "error": f"{type(error).__name__}: {error}",
                })
        except Exception as report_error:
            error.qualification_report_error = str(report_error)
        raise
    value = _observation(request)
    if save_success:
        _save(label + ".json", value)
    if phases:
        _prove_closed(value)
    else:
        proof = value["owned_tree"]
        assert proof["clean"] and proof["active_after"] == 0 and proof["parent_reaped"]
        assert value["cleanup_errors"] == [] and value["timeout_seconds"] == 5
    return value


@WINDOWS
def test_windows_launcher_matched_abba_and_candidate_recovery(tmp_path, monkeypatch):
    """No model/API work: execute the real wrapper against its existing fake entry."""
    baseline = _git_bytes("tests/fixtures/start_sinter_b269.bat")
    candidate = _git_bytes("Start-Sinter.bat")
    assert len(baseline) == 4471 and hashlib.sha256(baseline).hexdigest() == BASELINE_SHA256
    assert baseline != candidate
    harness = {
        "source": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "baseline_source": "b2691f6f5d2a3e2a9c62c07f66398c555d7b4d00",
        "baseline_sha256": BASELINE_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "python": sys.version, "executable": sys.executable,
        "platform": platform.platform(), "runner": os.environ.get("RUNNER_NAME"),
        "image_version": os.environ.get("ImageVersion"), "harness_pid": os.getpid(),
        "wait_seconds": 5, "separate_cleanup_seconds": 2,
        "order": ["A", "B", "B", "A"],
        "scope": "Zero-work source-wrapper readiness, not installed app or useful generation.",
    }
    _save("launcher-comparison-source.json", harness)
    rows = []
    summaries = []
    serial = 0
    for lane in ("system-discovery", "configured-path", "registered-fallback"):
        lane_rows = []
        for variant in ("A", "B", "B", "A"):
            serial += 1
            cell = tmp_path / f"{serial:02d}-{variant}"
            cell.mkdir()
            request = _request()
            failure = None
            with monkeypatch.context() as patch:
                def launch():
                    if lane in ("system-discovery", "configured-path"):
                        fixtures._exercise_wrapper_fixture(
                            cell, "Start-Sinter.bat",
                            ["review", "notes Ω & (draft)! 100% ready.txt", "--offline"],
                            request, patch, lane=lane,
                            wrapper_bytes=baseline if variant == "A" else candidate,
                            windows_tree=True,
                        )
                    else:
                        selection._windows_selection_fixture(
                            cell, patch, request, lane=lane,
                            wrapper_bytes=baseline if variant == "A" else candidate,
                            windows_tree=True,
                        )
                try:
                    _retain_control(
                        f"launcher-pre-failure-{serial:02d}", request, launch, save_success=False,
                    )
                except AssertionError as error:
                    failure = str(error)[:2000]
            value = _observation(request)
            record = {
                "lane": lane, "variant": variant, "serial": serial,
                "original_assertions_passed": failure is None,
                "failure": failure, "observation": value, "entry": _entry_identity(cell),
            }
            _save(f"launcher-{serial:02d}-{variant}-{lane}.json", record)
            # Never proceed from an unproven cleanup, including a failed baseline.
            _prove_closed(value)
            assert value["wrapper_sha256"] == hashlib.sha256(
                baseline if variant == "A" else candidate
            ).hexdigest()
            rows.append(record)
            lane_rows.append(record)
        assert len({r["entry"]["normalized_sha256"] for r in lane_rows}) == 1
        observed = {
            (os.path.normcase(r["observation"]["marker"]["value"]["executable"]),
             tuple(r["observation"]["marker"]["value"]["version_info"]))
            for r in lane_rows if "value" in r["observation"]["marker"]
        }
        assert len(observed) == 1, "Discovery must preserve the selected runtime."
        all_pass = all(r["original_assertions_passed"] for r in lane_rows)
        summary = {
            "lane": lane,
            "all_four_original_assertions_passed": all_pass,
            "timing_comparison_admissible": all_pass,
            "timing_basis": "Full owned observation includes construction and cleanup; no costs subtracted.",
            "runtime": list(observed),
            "process_counts": {
                v: [r["observation"]["owned_tree"]["process_counts_after"]["total_processes"]
                    for r in lane_rows if r["variant"] == v] for v in ("A", "B")
            },
            "full_elapsed_seconds": {
                v: [r["observation"]["full_owned_elapsed_seconds"]
                    for r in lane_rows if r["variant"] == v] for v in ("A", "B")
            },
        }
        if all_pass:
            summary["median_elapsed_seconds"] = {
                v: statistics.median(summary["full_elapsed_seconds"][v]) for v in ("A", "B")
            }
        summaries.append(summary)
        _save("launcher-summary-" + lane + ".json", summary)
    candidate_failures = [r for r in rows if r["variant"] == "B"
                          and not r["original_assertions_passed"]]
    _save("launcher-candidate-failures.json", candidate_failures)
    assert not candidate_failures, "Candidate must satisfy every original readiness assertion."
    for summary in summaries:
        if summary["lane"] != "system-discovery":
            assert max(summary["process_counts"]["B"]) < min(summary["process_counts"]["A"])

    # Existing refusal/admission/status controls use the same qualified ownership.
    controls = [
        ("alias-before-path", {"lane": "alias-before-path"}),
        ("broken-before-fallback", {"lane": "broken-before-fallback"}),
        ("no-runtime", {"lane": "no-runtime"}),
        ("broken-local", {"lane": "broken-local"}),
        ("local-exit", {"lane": "local-failure", "exit_code": 7}),
        ("path-exit", {"lane": "path-failure", "exit_code": 7}),
        ("quoted-path", {"lane": "path-failure", "path_format": "quoted"}),
        ("casefold-path", {"lane": "path-failure", "path_format": "casefold"}),
        ("ignore-current-directory", {"lane": "path-failure", "cwd_python_decoy": True}),
    ]
    for label, options in controls:
        serial += 1
        cell = tmp_path / f"control-{serial:02d}"
        cell.mkdir()
        request = _request()
        with monkeypatch.context() as patch:
            patch.setenv("ERRORLEVEL", "0")
            for name in ("SINTER_CANDIDATE", "SINTER_FIRST_PATH", "SINTER_PYTHON",
                         "SINTER_PY_LAUNCHER", "SINTER_RUNTIME_PRESENT"):
                patch.setenv(name, "must-not-be-admitted")
            observed_control = _retain_control("launcher-control-" + label, request, lambda: (
                selection._windows_selection_fixture(
                    cell, patch, request, wrapper_bytes=candidate, windows_tree=True, **options,
                )
            ))
            probes = observed_control["batch_stages"].get("lines", []).count("runtime_probe_begin")
            if label == "broken-before-fallback":
                assert probes == 2, "Do not probe the refused first PATH runtime twice."
            elif label in ("alias-before-path", "quoted-path", "casefold-path", "ignore-current-directory"):
                assert probes == 1
    # A real venv proves a PATH runtime containing literal variable markers and metacharacters.
    runtime = tmp_path / "runtime Ω & (draft)! %SINTER_LITERAL_PATH%"
    venv.EnvBuilder(with_pip=False, symlinks=False).create(runtime)
    cell = tmp_path / "control-metachar-path"
    cell.mkdir()
    request = _request()
    with monkeypatch.context() as patch:
        patch.setenv("SINTER_LITERAL_PATH", "must-not-expand")
        _retain_control("launcher-control-metachar-path", request, lambda: (
            selection._windows_selection_fixture(
                cell, patch, request, lane="path-failure", runtime_path=runtime / "Scripts",
                wrapper_bytes=candidate, windows_tree=True,
            )
        ))

    # Keep exact extracted helper and signed admission assertions; only own their CMD process.
    original_observer = fixtures.observe_wrapper
    for kind, values in (
        ("record", ["legacy", "modern", "default-quoted", "header", "vendor",
                    "arguments", "relative", "command-text", "embedded-quotes", "unbalanced-quotes"]),
        ("exit", [0, 1, -1, -1073741819]),
    ):
        for index, value in enumerate(values):
            cell = tmp_path / f"helper-{kind}-{index}"
            cell.mkdir()
            request = _request()
            with monkeypatch.context() as patch:
                patch.setattr(fixtures, "observe_wrapper", functools.partial(
                    original_observer, windows_tree=True,
                    windows_executable=os.environ["COMSPEC"],
                ))
                def control():
                    if kind == "record":
                        selection.test_windows_listing_helpers_preserve_paths_and_refuse_unknown_records(
                            cell, patch, request, value,
                            value in ("legacy", "modern", "default-quoted"),
                        )
                    else:
                        selection.test_windows_runtime_admission_requires_exact_success(
                            cell, patch, request, value,
                        )
                _retain_control(f"launcher-helper-{kind}-{index}", request, control, phases=False)
