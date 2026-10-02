"""Run the browser-independent timing presentation contract through Node."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_recorded_deadline_presentation_contract():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the JavaScript presentation contract')
    root = Path(__file__).resolve().parents[1]
    subprocess.run([node, '--test', 'tests/campaign_deadline_visibility.mjs'],
                   cwd=root, check=True, capture_output=True, text=True, timeout=20)
