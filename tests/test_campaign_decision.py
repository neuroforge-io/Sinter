"""Exercise campaign decision summaries from real browser-side policy code."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_campaign_decision_summary_contract():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required to exercise the campaign decision policy')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', 'tests/campaign_decision.mjs'], cwd=root,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
