"""Check actionable first-use guidance without apps, accounts or providers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_local_first_onboarding_controls() -> None:
    """Click the rendered entry controls and retain original practice evidence."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise first-use controls.")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--experimental-default-type=module", "--test", "tests/onboarding.mjs"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
