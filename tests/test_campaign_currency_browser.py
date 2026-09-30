"""Optional browser tooling handles setup before creating proof artifacts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("arguments,code", [(["--help"], 0), ([], 2)])
def test_setup_without_optional_browser_dependencies(arguments, code, tmp_path):
    environment = dict(os.environ)
    environment.pop("SINTER_CHROMIUM", None)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "tools/campaign_currency_browser.py"),
            *arguments,
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == code
    assert "Traceback" not in result.stderr
    if code == 0:
        assert "usage:" in result.stdout
    else:
        assert "Playwright is required" in result.stderr
    assert not list(tmp_path.iterdir())
