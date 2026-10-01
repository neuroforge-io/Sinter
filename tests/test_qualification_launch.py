"""Browser qualification requests its presentation without changing app defaults."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from sinter import desktop
from tools import installed_workflow_browser as workflow
from tools import upgrade_smoke as upgrade


@pytest.mark.parametrize(
    "version,legacy,expected",
    [
        ("0.5.3", True, []),
        ("0.5.4rc1", True, []),
        ("0.5.4rc2", True, []),
        ("0.5.3", False, []),
        ("0.5.4rc1", False, []),
        ("0.5.4rc2", False, []),
        ("0.5.4rc3", False, ["--mode", "browser"]),
        ("0.5.4rc3.dev0", False, ["--mode", "browser"]),
    ],
)
def test_upgrade_actual_process_boundary_preserves_historical_launches(
    tmp_path, monkeypatch, version, legacy, expected
):
    directory = tmp_path / "fictional-workspace"
    directory.mkdir()
    preferences = directory / "preferences.json"
    preferences.write_bytes(b'{"fictional":"unchanged"}')
    before = preferences.read_bytes()
    binary = tmp_path / "Sinter"
    output = tmp_path / "proof"
    output.mkdir()
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=version, stderr=""
        ),
    )
    observed = []

    class LaunchObserved(Exception):
        pass

    def observe(command, **kwargs):
        observed.append(command)
        assert kwargs["env"]["SINTER_DATA_DIR"] == str(directory)
        raise LaunchObserved

    monkeypatch.setattr(upgrade.subprocess, "Popen", observe)
    with pytest.raises(LaunchObserved):
        upgrade.run_native(binary, directory, {}, output, version, legacy=legacy)
    assert observed == [[str(binary.resolve()), *expected]]
    assert preferences.read_bytes() == before


@pytest.mark.parametrize("version", ["0.5.4rc3", "0.5.4rc3.dev0", "0.5.4", "0.6.0"])
def test_current_qualification_uses_existing_browser_operation(version, monkeypatch):
    command = workflow.browser_launch_command(["Sinter"], version)
    observed = []
    monkeypatch.setattr(
        desktop,
        "serve_desktop",
        lambda directory, open_browser: observed.append((directory, open_browser)) or 0,
    )
    assert desktop.main(command[1:]) == 0
    assert observed == [(None, True)]


def test_source_launch_retains_interpreter_and_module():
    prefix = ["fictional-python", "-m", "sinter.desktop"]
    assert workflow.browser_launch_command(prefix, "0.5.4rc3.dev0") == [
        *prefix, "--mode", "browser"
    ]
    assert prefix == ["fictional-python", "-m", "sinter.desktop"]


@pytest.mark.parametrize("version", ["0.4.9", "0.5.3", "0.5.4rc1", "0.5.4rc2"])
def test_older_browser_default_candidates_do_not_receive_new_flags(version):
    assert workflow.browser_launch_command(["Sinter"], version) == ["Sinter"]


@pytest.mark.parametrize("version", ["", "unverified", "0.5.4rc3 --no-browser"])
def test_invalid_launch_identity_is_refused(version):
    with pytest.raises(ValueError, match="version"):
        workflow.browser_launch_command(["Sinter"], version)


def test_copied_container_helpers_need_no_repository_or_optional_dependencies(tmp_path):
    root = Path(__file__).parents[1]
    for source, destination in (
        ("installed_workflow_browser.py", "workflow_runtime.py"),
        ("installed_recovery_browser.py", "helper.py"),
    ):
        (tmp_path / destination).write_bytes((root / "tools" / source).read_bytes())
    # Windows Python 3.10 needs its system directory to initialize OS entropy.
    # Retain these platform paths, never the caller's credentials or app settings.
    environment = {"PATH": os.defpath}
    environment.update(
        {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    )
    result = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-c",
            "import runpy,sys;from pathlib import Path;"
            "root=Path(sys.argv[1]);sys.path.insert(0,str(root));"
            "sys.argv=['helper.py','--container'];"
            "helper=runpy.run_path(str(root/'helper.py'));"
            "command=helper['transport'].browser_launch_command(['Sinter'],'0.5.4rc3');"
            "assert command==['Sinter','--mode','browser'];print('standalone helpers pass')",
            str(tmp_path),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "standalone helpers pass"
