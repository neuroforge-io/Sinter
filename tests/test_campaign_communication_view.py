"""Exercise the correspondence view's real browser-side policy from Python CI."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_campaign_communication_view_contract():
    """Run identity, status, literal preview and Unicode regressions together."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise the correspondence view policy")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/campaign_communication_view.mjs"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
