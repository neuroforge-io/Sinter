"""Induced startup stalls must identify their stage and stack before timeout."""

import ast
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

STAGE_ADMISSION_SECONDS = 5
STALL_WAIT_SECONDS = 0.7
REAP_SECONDS = 2
PRE_STAGE_TRACE_SECONDS = 2
JUNIT_BYTE_LIMIT = 8192


def launcher_script():
    path = Path(__file__).with_name("test_native_browser_handoff.py")
    module = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name
        == "test_failed_tk_launcher_exit_does_not_claim_durable_in_memory_recovery"
    )
    return next(
        node.value.value
        for node in function.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "script"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and type(node.value.value) is str
    )


def induced_stall_script(stage):
    script = launcher_script()
    marker = "checkpoint('" + stage + "')"
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        marker + "\nfaulthandler.cancel_dump_traceback_later()"
        "\nfaulthandler.dump_traceback_later(.1, repeat=False)\ntime.sleep(10)",
    )
    # Accelerate only the deliberate test stall and watchdog; the existing
    # real child still has 10s diagnostics, 20s harness and 0.02s close refusal.
    assert script.count("dump_traceback_later(10, repeat=False)") == 1
    # Only this induced-stall copy gets a trace before its 5s stage admission.
    return script.replace(
        "dump_traceback_later(10, repeat=False)",
        f"dump_traceback_later({PRE_STAGE_TRACE_SECONDS}, repeat=False)",
    )


def observe_startup_child(tmp_path, stage, script, request):
    """Retain this fictional child's evidence even when admission or cleanup fails."""
    workspace = tmp_path / "fictional"
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(tmp_path),
    }
    observation = {
        "schema": "sinter-induced-native-startup-diagnostics/v1",
        "expected_stage": stage,
        "stage_admission_seconds": STAGE_ADMISSION_SECONDS,
        "stall_wait_seconds": STALL_WAIT_SECONDS,
        "reap_seconds": REAP_SECONDS,
        "pre_stage_trace_seconds": PRE_STAGE_TRACE_SECONDS,
        "original_launcher_trace_seconds": 10,
        "original_launcher_harness_seconds": 20,
        "child_pid": None,
        "exit_before_cleanup": None,
        "exit_after_cleanup": None,
        "parent_reaped": False,
        "cleanup_wait_completed": False,
        "kill_attempted": False,
        "stage_observed": False,
        "stall_wait_timed_out": False,
        "descendants_observed": False,
        "first_error": None,
        "secondary_errors": [],
        "timings_seconds": {},
        "files": {},
        "artifact_files": {},
    }
    primary = None
    process = None
    handles = {}
    data = {}
    started = time.monotonic()

    def fault(operation, error):
        nonlocal primary
        row = {
            "operation": operation,
            "type": type(error).__name__,
            "message": str(error),
        }
        if primary is None:
            primary = error
            observation["first_error"] = row
        else:
            observation["secondary_errors"].append(row)

    def retain(name, raw):
        stream = None
        written = closed = False
        try:
            stream = (destination / name).open("xb")
            assert stream.write(raw) == len(raw), "Incomplete diagnostic artifact write"
            written = True
        except BaseException as error:
            fault("retain_" + name, error)
        finally:
            if stream is not None:
                try:
                    stream.close()
                    closed = True
                except BaseException as error:
                    fault("close_artifact_" + name, error)
        if written and closed:
            observation["artifact_files"][name] = {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }

    try:
        for name in ("stdout", "stderr"):
            handles[name] = (tmp_path / ("actual-child." + name)).open("w+b")
        process = subprocess.Popen(
            [sys.executable, "-B", "-c", script, str(workspace)],
            env=environment,
            stdout=handles["stdout"],
            stderr=handles["stderr"],
        )
        observation["child_pid"] = process.pid
        observation["timings_seconds"]["launch"] = time.monotonic() - started
        admitted_at = time.monotonic()
        deadline = admitted_at + STAGE_ADMISSION_SECONDS
        while time.monotonic() < deadline and process.poll() is None:
            try:
                stages = json.loads(
                    (workspace / "child-stages.json").read_text(encoding="utf-8")
                )
                observation["stage_observed"] = stages[-1]["stage"] == stage
            except (OSError, ValueError):
                pass
            if observation["stage_observed"]:
                break
            time.sleep(0.01)
        observation["timings_seconds"]["stage_admission"] = (
            time.monotonic() - admitted_at
        )
        assert observation["stage_observed"], (
            f"Child did not reach the deliberate {stage} stall; raw streams retained"
        )
        waiting_at = time.monotonic()
        try:
            with pytest.raises(subprocess.TimeoutExpired) as result:
                process.wait(timeout=STALL_WAIT_SECONDS)
            assert result.value.timeout == STALL_WAIT_SECONDS
            observation["stall_wait_timed_out"] = True
        finally:
            observation["timings_seconds"]["stall_wait"] = time.monotonic() - waiting_at
    except BaseException as error:
        fault("launch_or_stage_or_stall_wait", error)
    finally:
        cleanup_at = time.monotonic()
        if process is not None:
            try:
                observation["exit_before_cleanup"] = process.poll()
                observation["parent_reaped"] = process.returncode is not None
            except BaseException as error:
                fault("poll_before_cleanup", error)
            if process.returncode is None:
                observation["kill_attempted"] = True
                try:
                    process.kill()
                except BaseException as error:
                    fault("kill", error)
            try:
                process.wait(timeout=REAP_SECONDS)
                observation["parent_reaped"] = True
                observation["cleanup_wait_completed"] = True
            except BaseException as error:
                fault("reap", error)
            observation["exit_after_cleanup"] = process.returncode
            observation["parent_reaped"] = process.returncode is not None
        for name, stream in handles.items():
            try:
                stream.close()
            except BaseException as error:
                fault("close_" + name, error)
        observation["timings_seconds"]["cleanup"] = time.monotonic() - cleanup_at

    paths = {
        "actual-child.stdout": tmp_path / "actual-child.stdout",
        "actual-child.stderr": tmp_path / "actual-child.stderr",
        "child-stages.json": workspace / "child-stages.json",
    }
    for name, path in paths.items():
        try:
            raw = path.read_bytes()
            data[name] = raw
            sample = raw[:JUNIT_BYTE_LIMIT]
            observation["files"][name] = {
                "path": str(path),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "sample_base64": base64.b64encode(sample).decode("ascii"),
                "sample_bytes": len(sample),
                "sample_truncated": len(raw) > len(sample),
                "scope": "Actual snapshot after bounded parent cleanup; "
                "descendants unobserved",
            }
        except BaseException as error:
            observation["files"][name] = {"path": str(path), "read_succeeded": False}
            fault("read_" + name, error)

    destination = Path(
        os.environ.get(
            "SINTER_STARTUP_DIAGNOSTICS_DIR",
            str(tmp_path / "retained-startup-diagnostics"),
        )
    ) / (
        hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:16]
        + "-"
        + stage
    )
    observation["artifact_directory"] = str(destination)
    try:
        destination.mkdir(parents=True, exist_ok=False)
    except BaseException as error:
        fault("create_artifact_directory", error)
    else:
        for name, raw in data.items():
            retain(name, raw)
        observation["snapshot_phase"] = (
            "After raw retention; before observation-file and JUnit publication"
        )
        observation["timings_seconds"]["through_raw_retention"] = (
            time.monotonic() - started
        )
        try:
            raw = (
                json.dumps(observation, sort_keys=True, ensure_ascii=True, indent=2)
                + "\n"
            ).encode("utf-8")
        except BaseException as error:
            fault("serialize_observation", error)
        else:
            retain("observation.json", raw)
    observation["snapshot_phase"] = "After artifact retention; before JUnit publication"
    observation["timings_seconds"]["through_artifact_retention"] = (
        time.monotonic() - started
    )
    try:
        request.node.user_properties.append(
            (
                "sinter_native_startup_diagnostics",
                json.dumps(observation, sort_keys=True),
            )
        )
    except BaseException as error:
        fault("retain_junit_property", error)
    if primary is not None:
        try:
            primary.sinter_startup_diagnostics = observation
        except BaseException as error:
            fault("attach_diagnostics", error)
        raise primary
    return data


@pytest.mark.parametrize(
    "stage", ["runtime_initialization_started", "workbench_initialization_started"]
)
def test_startup_stall_retains_exact_stage_and_stack_without_reaching_shutdown(
    tmp_path, stage, request
):
    script = induced_stall_script(stage)
    data = observe_startup_child(tmp_path, stage, script, request)
    journal = json.loads(data["child-stages.json"])
    stderr = data["actual-child.stderr"]
    output = data["actual-child.stdout"]
    workspace = tmp_path / "fictional"
    assert journal[-1]["stage"] == stage
    assert not any(row["stage"] == "cleanup_started" for row in journal)
    assert not (workspace / "before-process-exit.json").exists()
    assert b"Timeout (" in stderr and b"in <module>" in stderr
    assert not output
    # The trace is diagnostic evidence, not an executed close or inferred cause.


EARLY_EXIT_SCRIPT = """
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
root.mkdir(parents=True)
sys.stdout.buffer.write(b'controlled early exit\\n')
sys.stderr.buffer.write(b'controlled diagnostic\\n')
(root / 'child-stages.json').write_text(
    json.dumps([{'stage': 'child_started'}]), encoding='utf-8')
raise SystemExit(7)
"""


def test_actual_early_child_exit_retains_original_bytes_and_failure(tmp_path, request):
    with pytest.raises(AssertionError, match="did not reach") as failure:
        observe_startup_child(
            tmp_path, "runtime_initialization_started", EARLY_EXIT_SCRIPT, request
        )
    observation = failure.value.sinter_startup_diagnostics
    assert observation["exit_before_cleanup"] == observation["exit_after_cleanup"] == 7
    assert observation["parent_reaped"] and observation["cleanup_wait_completed"]
    assert not observation["kill_attempted"]
    assert observation["first_error"]["type"] == "AssertionError"
    assert not observation["secondary_errors"]
    directory = Path(observation["artifact_directory"])
    expected = {
        "actual-child.stdout": b"controlled early exit\n",
        "actual-child.stderr": b"controlled diagnostic\n",
        "child-stages.json": b'[{"stage": "child_started"}]',
    }
    for name, raw in expected.items():
        assert (directory / name).read_bytes() == raw
        assert (
            observation["artifact_files"][name]["sha256"]
            == hashlib.sha256(raw).hexdigest()
        )
        assert base64.b64decode(observation["files"][name]["sample_base64"]) == raw
    artifact = json.loads((directory / "observation.json").read_bytes())
    junit = json.loads(request.node.user_properties[-1][1])
    assert "before observation-file" in artifact["snapshot_phase"]
    assert "before JUnit" in junit["snapshot_phase"]
    for name in ("files", "first_error", "exit_before_cleanup", "exit_after_cleanup"):
        assert artifact[name] == junit[name]
    assert "through_raw_retention" in artifact["timings_seconds"]
    assert "through_artifact_retention" in junit["timings_seconds"]


@pytest.mark.parametrize("later_fault", ["reap", "artifact_write_and_close"])
def test_early_failure_survives_later_cleanup_or_retention_fault(
    tmp_path, request, monkeypatch, later_fault
):
    if later_fault == "reap":
        original_popen = subprocess.Popen

        def popen(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            original_wait = process.wait

            def wait(timeout=None):
                result = original_wait(timeout=timeout)
                if timeout == REAP_SECONDS:
                    raise OSError("controlled error after actual reap")
                return result

            process.wait = wait
            return process

        monkeypatch.setattr(subprocess, "Popen", popen)
    else:
        original_open = Path.open

        class FaultingArtifact:
            def __init__(self, stream):
                self.stream = stream

            def write(self, raw):
                self.stream.write(raw)
                raise OSError("controlled artifact write error")

            def close(self):
                self.stream.close()
                raise OSError("controlled artifact close error")

        def open_path(path, mode="r", *args, **kwargs):
            stream = original_open(path, mode, *args, **kwargs)
            if mode == "xb" and path.name == "actual-child.stderr":
                return FaultingArtifact(stream)
            return stream

        monkeypatch.setattr(Path, "open", open_path)
    with pytest.raises(AssertionError, match="did not reach") as failure:
        observe_startup_child(
            tmp_path, "runtime_initialization_started", EARLY_EXIT_SCRIPT, request
        )
    observation = failure.value.sinter_startup_diagnostics
    assert observation["first_error"]["type"] == "AssertionError"
    assert observation["exit_before_cleanup"] == observation["exit_after_cleanup"] == 7
    assert observation["parent_reaped"] and not observation["kill_attempted"]
    operations = [row["operation"] for row in observation["secondary_errors"]]
    if later_fault == "reap":
        assert operations == ["reap"]
        assert not observation["cleanup_wait_completed"]
    else:
        assert operations == [
            "retain_actual-child.stderr",
            "close_artifact_actual-child.stderr",
        ]
        assert "actual-child.stderr" not in observation["artifact_files"]
    junit = json.loads(request.node.user_properties[-1][1])
    assert junit["first_error"] == observation["first_error"]
    assert junit["secondary_errors"] == observation["secondary_errors"]


def test_induced_pre_stage_stall_retains_trace_before_unchanged_admission(
    tmp_path, request
):
    script = induced_stall_script("runtime_initialization_started")
    watchdog = f"dump_traceback_later({PRE_STAGE_TRACE_SECONDS}, repeat=False)"
    assert script.count(watchdog) == 1
    script = script.replace(watchdog, watchdog + "\ntime.sleep(10)")
    with pytest.raises(AssertionError, match="did not reach") as failure:
        observe_startup_child(
            tmp_path, "runtime_initialization_started", script, request
        )
    observation = failure.value.sinter_startup_diagnostics
    assert observation["stage_admission_seconds"] == 5
    assert observation["exit_before_cleanup"] is None
    assert observation["kill_attempted"] and observation["parent_reaped"]
    assert observation["cleanup_wait_completed"]
    directory = Path(observation["artifact_directory"])
    assert (
        json.loads((directory / "child-stages.json").read_bytes())[-1]["stage"]
        == "child_started"
    )
    stderr = (directory / "actual-child.stderr").read_bytes()
    assert b"Timeout (" in stderr and b"in <module>" in stderr
