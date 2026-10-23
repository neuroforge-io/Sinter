"""Exercise saved reading, copy confirmation and local passage navigation."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_report_reader_state_and_confirmation_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise browser report-reader logic")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            node,
            "--test",
            "--test-concurrency=1",
            "tests/report_reader_header.mjs",
            "tests/report_passage_navigation.mjs",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
