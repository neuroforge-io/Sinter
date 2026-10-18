"""Qualify lossless single-report JSON admission independently of the browser."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_report_backup_admission():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise report JSON admission")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--experimental-default-type=module", "--test",
         "--test-concurrency=1", "tests/report_backup.mjs", "tests/saved_report_restore.mjs"],
        cwd=root, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
