"""Run meaningful compact-feedback and recovery regressions through Node."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_campaign_feedback_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for campaign feedback regressions")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", str(root / "tests" / "campaign_feedback.mjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
