"""Induced startup stalls must identify their stage and stack before timeout."""

import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


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


@pytest.mark.parametrize(
    "stage", ["runtime_initialization_started", "workbench_initialization_started"]
)
def test_startup_stall_retains_exact_stage_and_stack_without_reaching_shutdown(
    tmp_path, stage
):
    script = launcher_script()
    marker = "checkpoint('" + stage + "')"
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        marker
        + "\nfaulthandler.cancel_dump_traceback_later()\nfaulthandler.dump_traceback_later(.1, repeat=False)\ntime.sleep(10)",
    )
    # Accelerate only the deliberate test stall and watchdog; the existing
    # real child still has 10s diagnostics, 20s harness and 0.02s close refusal.
    assert script.count("dump_traceback_later(10, repeat=False)") == 1
    workspace = tmp_path / "fictional"
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(tmp_path),
    }
    with (
        (tmp_path / "actual-child.stdout").open("w+b") as stdout,
        (tmp_path / "actual-child.stderr").open("w+b") as stderr_stream,
    ):
        process = subprocess.Popen(
            [sys.executable, "-B", "-c", script, str(workspace)],
            env=environment,
            stdout=stdout,
            stderr=stderr_stream,
        )
        try:
            # Start the deliberate stall test clock after reaching its stage,
            # rather than assuming Python import/storage duration is negligible.
            deadline = time.monotonic() + 5
            reached = False
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    stages = json.loads(
                        (workspace / "child-stages.json").read_text(encoding="utf-8")
                    )
                    reached = stages[-1]["stage"] == stage
                except (OSError, ValueError):
                    pass
                if reached:
                    break
                time.sleep(0.01)
            assert reached, (
                f"Child did not reach the deliberate {stage} stall; raw streams retained"
            )
            with pytest.raises(subprocess.TimeoutExpired) as result:
                process.wait(timeout=0.7)
            assert result.value.timeout == 0.7
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
        stdout.seek(0)
        stderr_stream.seek(0)
        output = stdout.read()
        stderr = stderr_stream.read()
    journal = json.loads((workspace / "child-stages.json").read_text(encoding="utf-8"))
    assert journal[-1]["stage"] == stage
    assert not any(row["stage"] == "cleanup_started" for row in journal)
    assert not (workspace / "before-process-exit.json").exists()
    assert b"Timeout (" in stderr and b"in <module>" in stderr
    assert not output
    # The trace is diagnostic evidence, not an executed close or inferred cause.
    (tmp_path / "actual-child.stderr").write_bytes(stderr)
