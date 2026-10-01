"""Exercise snapshot identity without accepting request success as a saved file."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_word_copy_state():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for Word-copy state checks")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", str(root / "tests/word_copy_state.mjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
