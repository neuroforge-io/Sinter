"""The explicit document boundary has the same portable editor contract in JS."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_browser_page_break_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for document page-boundary checks")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/document_page_break.mjs"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("arguments,code", [(["--help"], 0), ([], 2)])
def test_optional_browser_setup_has_no_side_effects(arguments, code, tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment.pop("SINTER_CHROMIUM", None)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(root / "tools/document_page_break_browser.py"),
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
