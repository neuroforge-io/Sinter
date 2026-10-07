"""Render the workspace note through each actual API backend switch."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_workspace_storage_note_matches_backend():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to render the workspace module")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/library_storage.mjs"],
        cwd=root,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        result.stdout.decode("utf-8") + result.stderr.decode("utf-8")
    )
