"""Boundary and preservation checks for the quoted-budget presentation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_quoted_budget_presentation():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for budget presentation tests")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/campaign_budget.mjs"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
