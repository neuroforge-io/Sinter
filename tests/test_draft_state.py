"""Exercise the browser's dirty-draft exit-warning policy in Node."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_draft_state_exit_warning_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise browser draft-state logic")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/draft_state.mjs"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
