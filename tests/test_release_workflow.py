"""Execute the actual workflow plan without GitHub access or release writes."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("version", "publish", "calls"),
    [("0.5.4rc2.dev0", "false", 0), ("0.5.4rc1", "false", 0), ("0.5.4", "true", 1)],
)
def test_actual_release_plan_skips_unqualified_versions(
    tmp_path: Path, version: str, publish: str, calls: int
) -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    block = workflow.split("        run: |\n", 1)[1].split("  quality:\n", 1)[0]
    command = textwrap.dedent(block)
    package = tmp_path / "src/sinter"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(f"__version__ = {version!r}\n")
    executables = tmp_path / "bin"
    executables.mkdir()
    gh = executables / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$GH_CALLS"\nexit 1\n')
    gh.chmod(0o755)
    output = tmp_path / "output"
    call_log = tmp_path / "calls"
    env = {
        **os.environ,
        "PATH": f"{executables}:{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(output),
        "GH_CALLS": str(call_log),
        "GITHUB_REPOSITORY": "neuroforge-io/Sinter",
    }
    result = subprocess.run(
        ["bash", "-e", "-c", command],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values == {"tag": f"v{version}", "publish": publish}
    actual_calls = call_log.read_text().splitlines() if call_log.exists() else []
    assert len(actual_calls) == calls
    if calls:
        assert actual_calls == [f"release view v{version} --repo neuroforge-io/Sinter"]
