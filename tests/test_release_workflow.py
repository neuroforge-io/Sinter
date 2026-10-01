"""Execute the actual workflow plan without GitHub access or release writes."""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def bash_executable() -> str:
    if os.name == "nt":
        # Windows' System32 bash is a WSL launcher, not the workflow shell.
        # Existing Git for Windows supplies the bash used by hosted CI.
        for name in ("ProgramFiles", "ProgramFiles(x86)"):
            directory = os.environ.get(name)
            candidate = Path(directory or "") / "Git/bin/bash.exe"
            if directory and candidate.is_file():
                return str(candidate)
        raise AssertionError("The Windows workflow test requires Git for Windows bash.")
    executable = shutil.which("bash")
    assert executable, "The release workflow test requires bash."
    return executable


def test_windows_release_harness_uses_git_bash_instead_of_wsl(tmp_path, monkeypatch):
    git_bash = tmp_path / "Git/bin/bash.exe"
    git_bash.parent.mkdir(parents=True)
    git_bash.write_bytes(b"fictional shell path; never executed")
    monkeypatch.setitem(
        bash_executable.__globals__,
        "os",
        SimpleNamespace(name="nt", environ={"ProgramFiles": str(tmp_path)}),
    )
    monkeypatch.setattr(shutil, "which", lambda *_: pytest.fail("selected PATH's WSL"))
    assert bash_executable() == str(git_bash)


def test_windows_release_harness_does_not_fall_back_to_wsl(monkeypatch):
    monkeypatch.setitem(
        bash_executable.__globals__, "os", SimpleNamespace(name="nt", environ={})
    )
    monkeypatch.setattr(shutil, "which", lambda *_: "fictional/System32/bash.exe")
    with pytest.raises(AssertionError, match="Git for Windows"):
        bash_executable()


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
    gh.write_bytes(b'#!/bin/sh\nprintf "%s\\n" "$*" >> "$GH_CALLS"\nexit 1\n')
    gh.chmod(0o755)
    output = tmp_path / "output"
    call_log = tmp_path / "calls"
    env = {
        **os.environ,
        "PATH": os.pathsep.join((str(executables), os.environ["PATH"])),
        "GITHUB_OUTPUT": output.as_posix(),
        "GH_CALLS": call_log.as_posix(),
        "GITHUB_REPOSITORY": "neuroforge-io/Sinter",
    }
    result = subprocess.run(
        [bash_executable(), "-e", "-c", command],
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
