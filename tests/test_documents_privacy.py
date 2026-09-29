"""Exercise local campaign evidence-export privacy policy in browser-side code."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_campaign_evidence_download_privacy_policy():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required to exercise the browser-side export policy')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', 'tests/documents_privacy.mjs'], cwd=root,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
