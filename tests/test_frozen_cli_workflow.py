"""The packaged CLI qualification must perform a real shared source workflow."""

import sys
import time
from pathlib import Path

import pytest

from tools.frozen_cli_smoke import Commands, workflow


@pytest.mark.parametrize("output_encoding", [None, "cp1252"])
def test_packaging_entry_runs_qualification_workflow_without_provider(
    tmp_path, output_encoding
):
    root = Path(__file__).parents[1]
    command = (
        "import sys,runpy; "
        f"sys.path.insert(0,{str(root / 'src')!r}); "
        f"runpy.run_path({str(root / 'packaging/desktop_entry.py')!r},"
        "run_name='__main__')"
    )
    receipt = {"checks": []}
    commands = Commands([sys.executable, "-B", "-c", command], tmp_path, receipt)
    if output_encoding:
        commands.environment["PYTHONIOENCODING"] = output_encoding
    assert workflow(commands) >= 52
    assert all(row["passed"] for row in receipt["checks"])
    assert all(row["exit_code"] in (0, 2) for row in receipt["checks"])


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_qualification_bounds_actual_child_output(tmp_path, stream):
    receipt = {"checks": []}
    code = f"import sys;sys.{stream}.write('x' * (2 * 1024 * 1024))"
    commands = Commands([sys.executable, "-B", "-c", code], tmp_path, receipt)
    with pytest.raises(RuntimeError, match="output bound"):
        commands.run("fictional_output_flood", [])
    assert receipt["checks"][-1]["owned_process_exited"] is True


def test_qualification_timeout_reaps_its_owned_child(tmp_path):
    receipt = {"checks": []}
    commands = Commands(
        [sys.executable, "-B", "-c", "import time;time.sleep(5)"], tmp_path, receipt
    )
    commands.deadline = time.monotonic() + 0.1
    with pytest.raises(RuntimeError, match="time bound"):
        commands.run("fictional_stopped_child", [])
    assert receipt["checks"][-1]["forced_cleanup"] is True
    assert receipt["checks"][-1]["owned_process_exited"] is True
