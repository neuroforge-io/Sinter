"""Exercise lossless local working-copy recovery without server admission."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_campaign_backup_controls():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise campaign backup controls")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", str(root / "tests/campaign_backup.mjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
