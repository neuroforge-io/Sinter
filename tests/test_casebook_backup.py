"""Lossless casebook recovery must retain even work awaiting scope admission."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_casebook_backup_text():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for casebook backup regression checks')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', str(root / 'tests/casebook_backup.mjs')],
                            cwd=root, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
