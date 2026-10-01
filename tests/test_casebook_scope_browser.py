"""Help and missing optional tooling refuse before writing source-choice artifacts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("arguments,code", [(["--help"], 0), ([], 2)])
@pytest.mark.parametrize(
    "runner", ["casebook_scope_browser.py", "casebook_source_filter_browser.py"]
)
def test_scope_runner_optional_setup_precedes_side_effects(
    arguments, code, runner, tmp_path
):
    environment = dict(os.environ)
    environment.pop("SINTER_CHROMIUM", None)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "tools" / runner),
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
