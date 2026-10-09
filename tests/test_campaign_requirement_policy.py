"""Check shared summary/decision evidence policy through its browser-side module."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_campaign_requirement_evidence_policy() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise the campaign requirement policy")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/campaign_requirement_policy.mjs"], cwd=root,
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
