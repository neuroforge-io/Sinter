"""The optional UI proof handles help/dependency errors before side effects."""

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
            str(ROOT / "tools" / "casebook_confirm_browser.py"),
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
