"""Presentation-only prototype regressions and side-effect-free optional setup."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_question_evidence_projection_and_historical_citations():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the browser pure-module checks")
    result = subprocess.run(
        [
            node,
            "--test",
            "tests/casebook_question_evidence.mjs",
            "tests/report_citations.mjs",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("arguments, code", [(["--help"], 0), ([], 2)])
def test_question_evidence_browser_optional_setup_before_side_effects(
    arguments, code, tmp_path
):
    environment = dict(os.environ)
    environment.pop("SINTER_CHROMIUM", None)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "tools/casebook_question_evidence_browser.py"),
            *arguments,
        ],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == code
    assert "Traceback" not in result.stderr
    if code == 0:
        assert "usage:" in result.stdout and "--chromium" in result.stdout
    else:
        assert "Playwright is required" in result.stderr
    assert not list(tmp_path.iterdir())
