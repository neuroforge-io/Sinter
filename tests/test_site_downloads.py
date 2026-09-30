"""Exercise the actual standalone public download policy without network access."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_standalone_download_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise the standalone download policy")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/site_downloads.mjs"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
