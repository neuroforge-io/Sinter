"""Run explicit browser-side route-purpose policy through standard Python CI."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_campaign_route_purpose_contract() -> None:
    """Exercise purpose, formal conflicts and record preservation without a browser."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise the campaign route-purpose policy")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/campaign_route_purpose.mjs"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
