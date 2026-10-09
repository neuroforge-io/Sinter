"""Header UI qualification explains setup before browser imports or artifacts."""

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
    environment["TMPDIR"] = str(tmp_path)
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(root / "tools" / "campaign_header_browser.py"),
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
        assert "--output-dir" in result.stdout
    else:
        assert "Playwright is required" in result.stderr
    assert not list(tmp_path.iterdir())


def test_existing_evidence_is_not_reused_or_modified(tmp_path):
    output = tmp_path / "retained"
    output.mkdir()
    sentinel = output / "original.txt"
    sentinel.write_text("Fictional original evidence.\n")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(root / "tools" / "campaign_header_browser.py"),
            "--output-dir",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "Retain the existing output" in result.stderr
    assert "Traceback" not in result.stderr
    assert sentinel.read_text() == "Fictional original evidence.\n"
    assert list(output.iterdir()) == [sentinel]
    assert list(tmp_path.iterdir()) == [output]
