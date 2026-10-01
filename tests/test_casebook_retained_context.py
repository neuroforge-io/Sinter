"""Local context inspection: no inference, transfer, source or document mutation."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_per_question_coverage_and_exact_retained_context():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for browser-module checks")
    result = subprocess.run(
        [node, "--test", "tests/casebook_retained_context.mjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("arguments,code", [(["--help"], 0), ([], 2)])
def test_context_browser_setup_before_side_effects(arguments, code, tmp_path):
    environment = dict(os.environ)
    environment.pop("SINTER_CHROMIUM", None)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-S",
            str(ROOT / "tools/casebook_context_browser.py"),
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
    assert (
        ("usage:" in result.stdout)
        if code == 0
        else ("Playwright is required" in result.stderr)
    )
    assert not list(tmp_path.iterdir())
