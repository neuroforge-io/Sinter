"""Campaign-layout proof explains browser setup before creating artifacts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("arguments, code", [(["--help"], 0), ([], 2)])
def test_setup_without_browser_dependencies(arguments, code, tmp_path):
    environment = dict(os.environ)
    environment.pop("SINTER_CHROMIUM", None)
    root = Path(__file__).resolve().parents[1]
    artifact_root = root / "browser-artifacts"
    before = set(artifact_root.iterdir()) if artifact_root.exists() else set()
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(root / "tools" / "campaign_layout_browser.py"),
            *arguments,
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == code, result.stderr
    assert "Traceback" not in result.stderr
    if code == 0:
        assert "usage:" in result.stdout and "--chromium" in result.stdout
    else:
        assert "Playwright is required" in result.stderr
    after = set(artifact_root.iterdir()) if artifact_root.exists() else set()
    assert after == before
    assert not list(tmp_path.iterdir())
