"""Run the real browser-side campaign-to-letter builder under Node."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_campaign_clarification_letter_builder():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required to exercise the browser-side letter builder')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', 'tests/campaign_letter.mjs'], cwd=root,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
