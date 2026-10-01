"""Recovery qualification explains optional browser setup before side effects."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("arguments, code", [(["--help"], 0), ([], 2)])
def test_help_or_missing_browser_setup_has_no_workspace_side_effects(
    arguments, code, tmp_path
):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment.pop("SINTER_CHROMIUM", None)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(root / "tools/document_copy_browser.py"),
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
    assert (
        "usage:" in result.stdout
        if code == 0
        else "Playwright is required" in result.stderr
    )
    assert not list(tmp_path.iterdir())
