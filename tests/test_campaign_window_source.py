"""Keep application-window evidence bound to its explicitly chosen source."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_window_source_transition():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise window source selection")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", str(root / "tests/campaign_window_source.mjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
