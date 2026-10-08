"""Fixture diagnostics and selector logic; no Windows qualification is implied."""

import builtins
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_review_recovery as fixtures


@pytest.mark.parametrize("blocked", ["sys", "json", "pathlib"])
def test_entry_stage_survives_a_fixture_import_failure(tmp_path, monkeypatch, blocked):
    marker, stages = tmp_path / "marker.json", tmp_path / "stages.bin"
    ordinary = builtins.__import__

    def fail(name, *args, **kwargs):
        if name == blocked:
            raise ImportError("inert fixture import refusal: " + name)
        return ordinary(name, *args, **kwargs)

    source = fixtures._wrapper_entry_source(marker, stages)
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", fail)
        with pytest.raises(ImportError, match="inert fixture import refusal"):
            exec(compile(source, "inert-wrapper-entry.py", "exec"), {})
    observation = fixtures._wrapper_stage_observation(stages)
    assert observation["python_entered"] is True
    assert observation["lines"][0] == "python_entered"
    assert "marker_written" not in observation["lines"]
    assert not marker.exists()
    assert observation["final_stream_proven"] is False
    if blocked == "sys":
        assert observation["lines"] == ["python_entered"]
    else:
        assert "sys_imported" in observation["lines"]
        assert any(line.startswith("runtime=") for line in observation["lines"])


def test_completed_entry_preserves_runtime_argv_and_unicode_paths(tmp_path, capsys):
    marker = tmp_path / "fixture Ω.json"
    stages = tmp_path / "stages Ω.bin"
    source = fixtures._wrapper_entry_source(marker, stages)
    exec(compile(source, "inert-wrapper-entry.py", "exec"), {})
    observation = fixtures._wrapper_stage_observation(stages)
    runtime = json.loads(marker.read_text(encoding="utf-8"))
    stdout = json.loads(capsys.readouterr().out)
    assert observation["python_entered"] is True
    assert observation["lines"][-1] == "marker_written"
    assert runtime["executable"] == sys.executable
    assert runtime["version_info"] == list(sys.version_info[:3])
    assert runtime["argv"] == sys.argv
    assert stdout["arguments"] == sys.argv[1:]


@pytest.mark.parametrize("content", [None, b"python_entered\n" + b"x" * 5000, b"\xff"])
def test_missing_oversized_or_unreadable_stage_is_unknown(tmp_path, content):
    stages = tmp_path / "stages.bin"
    if content is not None:
        stages.write_bytes(content)
    observation = fixtures._wrapper_stage_observation(stages)
    assert observation["python_entered"] is None
    assert "lines" not in observation
    assert "marker_written" not in observation.get("lines", [])


@pytest.mark.parametrize(
    "content", [b"", b"python_enter", b"python_entered", b"unexpected\n"]
)
def test_incomplete_or_unexpected_entry_acknowledgement_stays_unknown(
    tmp_path, content
):
    stages = tmp_path / "stages.bin"
    stages.write_bytes(content)
    observation = fixtures._wrapper_stage_observation(stages)
    assert observation["python_entered"] is None
    assert observation["lines"] == content.decode("utf-8").splitlines()
    assert observation["final_stream_proven"] is False


@pytest.mark.parametrize("lane", ["configured-local-venv", "requested-minor-runtime"])
@pytest.mark.parametrize("version", [None, [3, 14, 7], [3, 13, "7"], [3, 13]])
def test_configured_selection_rejects_unknown_or_wrong_runtime(lane, version, tmp_path):
    selection = {
        "lane": lane,
        "expected_version": [3, 13],
        "expected_executable": str(tmp_path / "configured-python"),
    }
    runtime = {"version_info": version, "executable": str(tmp_path / "other-python")}
    assert fixtures._wrapper_selection_satisfied(selection, runtime) is False


@pytest.mark.parametrize("runtime", [None, [], "unfinished marker", True])
def test_malformed_configured_marker_cannot_invent_selection(runtime):
    selection = {"lane": "requested-minor-runtime", "expected_version": [3, 13]}
    assert fixtures._wrapper_selection_satisfied(selection, runtime) is False


def test_minor_selection_and_exact_venv_selection_are_distinct(tmp_path):
    expected = tmp_path / "configured-python"
    actual = tmp_path / "other-python"
    runtime = {"version_info": [3, 13, 7], "executable": str(actual)}
    selection = {"expected_version": [3, 13], "expected_executable": None}
    assert (
        fixtures._wrapper_selection_satisfied(
            {**selection, "lane": "requested-minor-runtime"}, runtime
        )
        is True
    )
    assert (
        fixtures._wrapper_selection_satisfied(
            {
                **selection,
                "lane": "configured-local-venv",
                "expected_executable": str(expected),
            },
            runtime,
        )
        is False
    )
    assert (
        fixtures._wrapper_selection_satisfied(
            {
                **selection,
                "lane": "configured-local-venv",
                "expected_executable": str(actual),
            },
            runtime,
        )
        is True
    )
    assert (
        fixtures._wrapper_selection_satisfied({"lane": "system-discovery"}, {}) is None
    )


def test_failed_parent_keeps_entry_stage_and_selection_in_junit_before_refusal(
    tmp_path, monkeypatch
):
    request = SimpleNamespace(node=SimpleNamespace(user_properties=[]))
    marker = tmp_path / "wrapper-marker.json"
    stages = tmp_path / "wrapper-stages.bin"
    stages.write_bytes(b"python_entered\n")
    launches = []

    def observe(command, directory, final_marker, *, timeout):
        launches.append(command)
        assert directory == tmp_path and final_marker == marker and timeout == 5
        return {
            "timed_out": True,
            "parent_exited": True,
            "cleanup_errors": [],
            "returncode": 1,
            "marker": {},
        }, b""

    monkeypatch.setattr(fixtures, "observe_wrapper", observe)
    with pytest.raises(AssertionError) as raised:
        fixtures._exercise_wrapper_fixture(
            tmp_path, "start-sinter.sh", [], request, monkeypatch
        )
    assert len(launches) == 1
    name, raw = request.node.user_properties[0]
    assert name == "sinter_wrapper_diagnostics"
    observation = json.loads(raw)
    assert observation["timed_out"] is True
    assert observation["startup_stages"]["python_entered"] is True
    assert observation["interpreter_selection"]["lane"] == "system-discovery"
    assert observation["interpreter_selection"]["satisfied"] is None
    assert raw in str(raised.value)


@pytest.mark.parametrize("inherited", ["1", "false"])
def test_windows_fixture_requests_both_launcher_policies_before_one_launch(
    tmp_path, monkeypatch, inherited
):
    request = SimpleNamespace(node=SimpleNamespace(user_properties=[]))
    policy = {
        "PYLAUNCHER_DEBUG": "1",
        "PYLAUNCHER_ALLOW_INSTALL": None,
        "PYLAUNCHER_ALWAYS_INSTALL": None,
        "PYMANAGER_DEBUG": "1",
        "PYTHON_MANAGER_AUTOMATIC_INSTALL": "false",
    }
    for key in policy:
        monkeypatch.setenv(key, inherited)
    monkeypatch.setenv("COMSPEC", "inert-cmd.exe")
    launches = []

    def observe(command, directory, marker, *, timeout):
        # Observe requested process policy without running a Windows executable.
        launches.append(command)
        assert timeout == 5
        assert {key: os.environ.get(key) for key in policy} == policy
        return {
            "timed_out": True,
            "parent_exited": True,
            "cleanup_errors": [],
            "returncode": 1,
            "marker": {},
        }, b""

    monkeypatch.setattr(fixtures, "observe_wrapper", observe)
    with monkeypatch.context() as scoped:
        with pytest.raises(AssertionError):
            fixtures._exercise_wrapper_fixture(
                tmp_path, "Start-Sinter.bat", [], request, scoped
            )
    assert len(launches) == 1
    assert {key: os.environ.get(key) for key in policy} == {
        key: inherited for key in policy
    }
    diagnostics = json.loads(request.node.user_properties[0][1])
    selection = diagnostics["interpreter_selection"]
    assert selection["requested_launcher_environment"] == policy
    assert selection["launcher_family"] == "unknown"
    assert selection["launcher_policy_effective"] is None
    assert selection["launcher_policy_boundary"] == (
        "Administrator configuration may override requested environment."
    )
    assert selection["satisfied"] is None
    assert diagnostics["startup_stages"]["python_entered"] is None


def _windows_selection_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest,
    *, lane: str, exit_code: int = 0,
) -> dict:
    """Run the real batch wrapper with an owned zero-work entry, never Sinter.

    The registered fallback is a real installed launcher/runtime. Alias and
    broken-runtime files are deliberate refusal fixtures, not Python versions.
    Every actual dispatch keeps the existing five-second whole-wrapper bound.
    """
    source = tmp_path / "source Ω & (draft)! 100% folder"
    source.mkdir()
    launcher = source / "Start-Sinter.bat"
    shutil.copyfile(Path(fixtures.__file__).parents[1] / launcher.name, launcher)
    marker, stages = tmp_path / "runtime.json", tmp_path / "stages.bin"
    (source / "start.py").write_text(
        fixtures._wrapper_entry_source(marker, stages)
        + f"raise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    py = shutil.which("py.exe")
    runtime = Path(sys.executable).parent
    path = [system32]
    if lane in {"registered-fallback", "broken-before-fallback"}:
        assert py, "The Windows CI image must provide its registered launcher."
        path.insert(0, Path(py).parent)
    elif lane in {"path-failure", "alias-before-path", "local-failure", "broken-local"}:
        assert py, "Retain an available fallback to detect an unintended replay."
        path[:0] = [runtime, Path(py).parent]
    else:
        assert lane == "no-runtime"
    if lane in {"alias-before-path", "broken-before-fallback"}:
        refusal = tmp_path / "unusable runtime Ω ! 100%"
        refusal.mkdir()
        (refusal / "python.exe").write_bytes(b"not an executable")
        if lane == "broken-before-fallback":
            (refusal / "Lib").mkdir()
            (refusal / "Lib" / "os.py").write_text("# refusal fixture\n")
        path.insert(0, refusal)
    if lane == "local-failure":
        import venv

        venv.EnvBuilder(with_pip=False, symlinks=False).create(source / ".venv")
    if lane == "broken-local":
        private = source / ".venv" / "Scripts"
        private.mkdir(parents=True)
        (private / "python.exe").write_bytes(b"not an executable")
    monkeypatch.setenv("PATH", os.pathsep.join(map(str, path)))
    monkeypatch.setenv("PYTHON_MANAGER_AUTOMATIC_INSTALL", "false")
    monkeypatch.delenv("PYLAUNCHER_ALLOW_INSTALL", raising=False)
    monkeypatch.delenv("PYLAUNCHER_ALWAYS_INSTALL", raising=False)
    arguments = ["review", "notes Ω & (draft)! 100% ready.txt", "--offline"]
    shell = subprocess.list2cmdline([os.environ["COMSPEC"]])
    invocation = subprocess.list2cmdline([str(launcher), *arguments])
    command = f'{shell} /d /s /c "{invocation}"'
    observation, stdout = fixtures.observe_wrapper(
        command, tmp_path, marker, timeout=5,
    )
    observation["startup_stages"] = fixtures._wrapper_stage_observation(stages)
    observation["selection_fixture"] = {
        "lane": lane, "path": list(map(str, path)), "py": py,
        "matrix_python": sys.executable, "matrix_version": list(sys.version_info),
        "expected_exit": (
            "nonzero" if lane == "broken-local"
            else 1 if lane == "no-runtime" else exit_code
        ),
    }
    raw = json.dumps(observation, sort_keys=True, separators=(",", ":"))
    request.node.user_properties.append(("sinter_wrapper_diagnostics", raw))
    assert not observation["timed_out"], raw
    assert observation["parent_exited"], raw
    assert observation["cleanup_errors"] == [], raw
    if lane == "broken-local":
        assert observation["returncode"] != 0, raw
        assert not marker.exists() and not stages.exists(), raw
        return observation
    assert observation["returncode"] == (1 if lane == "no-runtime" else exit_code), raw
    if lane == "no-runtime":
        assert not marker.exists() and not stages.exists(), raw
        assert b"Sinter needs Python 3.10 or newer" in stdout, raw
        return observation
    actual = observation["marker"]["value"]
    assert actual["version_info"][:2] >= [3, 10], raw
    assert actual["argv"][1:] == arguments, raw
    assert Path(actual["cwd"]) == source, raw
    assert observation["startup_stages"]["lines"].count("python_entered") == 1, raw
    assert observation["startup_stages"]["lines"].count("marker_written") == 1, raw
    if lane in {"path-failure", "alias-before-path"}:
        assert Path(actual["executable"]).resolve() == Path(sys.executable).resolve()
    if lane == "local-failure":
        assert Path(actual["executable"]).resolve() == (
            source / ".venv" / "Scripts" / "python.exe"
        ).resolve(), raw
    return observation


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows fallback and refusal.")
@pytest.mark.parametrize("lane", [
    "registered-fallback", "broken-before-fallback", "alias-before-path", "no-runtime",
    "broken-local",
])
def test_windows_selection_fallback_and_refusal(
    tmp_path, monkeypatch, request, lane,
):
    _windows_selection_fixture(tmp_path, monkeypatch, request, lane=lane)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows single dispatch exit.")
@pytest.mark.parametrize("lane", ["path-failure", "local-failure"])
def test_windows_application_failure_keeps_exit_without_fallback(
    tmp_path, monkeypatch, request, lane,
):
    _windows_selection_fixture(
        tmp_path, monkeypatch, request, lane=lane, exit_code=7,
    )


@pytest.mark.skipif(os.name != "nt", reason="Actual batch parser and runtime probe.")
@pytest.mark.parametrize("record, admitted", [
    ("legacy", True), ("modern", True), ("default-quoted", True),
    ("header", False), ("vendor", False), ("arguments", False),
    ("relative", False), ("command-text", False),
    ("embedded-quotes", False), ("unbalanced-quotes", False),
])
def test_windows_listing_helpers_preserve_paths_and_refuse_unknown_records(
    tmp_path, monkeypatch, request, record, admitted,
):
    """Exercise exact batch helper bodies; this is not registered discovery."""
    import venv

    runtime = tmp_path / "runtime Ω & (draft)! %SINTER_LITERAL_PATH%"
    venv.EnvBuilder(with_pip=False, symlinks=False).create(runtime)
    executable = runtime / "Scripts" / "python.exe"
    minor = sys.version_info.minor
    tag = f"-V:3.{minor}"
    candidate = str(executable)
    forbidden = tmp_path / "must-not-run.txt"
    if record == "legacy":
        tag = f"-3.{minor}-64"
    elif record == "default-quoted":
        candidate = f'* "{executable}"'
    elif record == "header":
        tag = "Installed"
    elif record == "vendor":
        tag = f"-V:Other/3.{minor}"
    elif record == "arguments":
        candidate += " --unexpected"
    elif record == "relative":
        candidate = "Scripts\\python.exe"
    elif record == "command-text":
        candidate = f'{executable} & echo unsafe > "{forbidden}"'
    elif record == "embedded-quotes":
        candidate = str(executable).replace("runtime", 'run"time"', 1)
    elif record == "unbalanced-quotes":
        candidate = '"' + str(executable)
    monkeypatch.setenv("SINTER_LITERAL_PATH", "must-not-expand")
    monkeypatch.setenv("SINTER_LIST_TAG", tag)
    monkeypatch.setenv("SINTER_CANDIDATE", candidate)
    entry = tmp_path / "entry.py"
    monkeypatch.setenv("SINTER_CASE_ENTRY", str(entry))
    marker, stages = tmp_path / "runtime.json", tmp_path / "stages.bin"
    entry.write_text(fixtures._wrapper_entry_source(marker, stages), encoding="utf-8")
    batch = (Path(fixtures.__file__).parents[1] / "Start-Sinter.bat").read_text()
    helpers = batch[batch.index("\n:listed_candidate\n") + 1:]
    driver = tmp_path / "parser-control.bat"
    driver.write_text(
        "@echo off\nsetlocal EnableExtensions DisableDelayedExpansion\n"
        'set "SINTER_PYTHON="\n'
        "call :listed_candidate\nif not defined SINTER_PYTHON exit /b 3\n"
        '"%SINTER_PYTHON%" "%SINTER_CASE_ENTRY%"\n'
        "exit /b %errorlevel%\n" + helpers,
        encoding="utf-8", newline="\r\n",
    )
    shell = subprocess.list2cmdline([os.environ["COMSPEC"]])
    invocation = subprocess.list2cmdline([str(driver)])
    observation, _ = fixtures.observe_wrapper(
        f'{shell} /d /s /c "{invocation}"', tmp_path, marker, timeout=5,
    )
    observation["parser_control"] = {"record": record, "admitted": admitted}
    observation["startup_stages"] = fixtures._wrapper_stage_observation(stages)
    raw = json.dumps(observation, sort_keys=True, separators=(",", ":"))
    request.node.user_properties.append(("sinter_wrapper_diagnostics", raw))
    assert not observation["timed_out"] and observation["parent_exited"], raw
    assert observation["cleanup_errors"] == [], raw
    assert observation["returncode"] == (0 if admitted else 3), raw
    assert not forbidden.exists(), raw
    if admitted:
        actual = observation["marker"]["value"]
        assert Path(actual["executable"]).resolve() == executable.resolve(), raw
        assert actual["version_info"][:2] == list(sys.version_info[:2]), raw
        assert observation["startup_stages"]["lines"].count("python_entered") == 1
    else:
        assert not marker.exists() and not stages.exists(), raw


@pytest.mark.parametrize("version, admitted", [
    ((2, 7, 18), False), ((3, 9, 20), False), ((3, 10, 0), True),
    ((3, 13, 15), True), ((3, 14, 7), True),
])
def test_isolated_runtime_probe_admits_supported_versions_only(version, admitted):
    """Check the exact isolated probe predicate, not Windows batch execution."""
    batch = (Path(fixtures.__file__).parents[1] / "Start-Sinter.bat").read_text()
    line = next(line for line in batch.splitlines() if ' -I -S -c "' in line)
    code = line.split(' -I -S -c "', 1)[1].split('" >nul', 1)[0]

    def import_sys(name, *args, **kwargs):
        assert name == "sys", "The discovery probe must import no product helpers."
        return SimpleNamespace(version_info=version)

    with pytest.raises(SystemExit) as result:
        exec(code, {"__builtins__": {
            "__import__": import_sys, "SystemExit": SystemExit,
        }})
    assert result.value.code == (0 if admitted else 1)


@pytest.mark.skipif(os.name != "nt", reason="Actual CMD signed exit admission.")
@pytest.mark.parametrize("probe_exit", [0, 1, -1, -1073741819])
def test_windows_runtime_admission_requires_exact_success(
    tmp_path, monkeypatch, request, probe_exit,
):
    """Run the exact production guard after a controlled real CMD exit.

    Negative codes exercise signed Windows failures; this does not manufacture
    an interpreter crash or qualify runtime discovery.
    """
    batch = (Path(fixtures.__file__).parents[1] / "Start-Sinter.bat").read_text()
    admission = next(
        line for line in batch.splitlines()
        if 'set "SINTER_PYTHON=%SINTER_CANDIDATE%"' in line
    )
    monkeypatch.setenv("SINTER_CASE_EXIT", str(probe_exit))
    monkeypatch.setenv("SINTER_CANDIDATE", sys.executable)
    driver = tmp_path / "probe-exit-control.bat"
    driver.write_text(
        '@echo off\nsetlocal EnableExtensions DisableDelayedExpansion\n'
        'set "SINTER_PYTHON="\n'
        '"%COMSPEC%" /d /c exit /b %SINTER_CASE_EXIT%\n'
        + admission + '\necho observed-probe-exit=%errorlevel%\n'
        'if defined SINTER_PYTHON exit /b 0\nexit /b 3\n',
        encoding="utf-8", newline="\r\n",
    )
    shell = subprocess.list2cmdline([os.environ["COMSPEC"]])
    invocation = subprocess.list2cmdline([str(driver)])
    observation, stdout = fixtures.observe_wrapper(
        f'{shell} /d /s /c "{invocation}"', tmp_path,
        tmp_path / "no-application-marker.json", timeout=5,
    )
    observation["requested_probe_exit"] = probe_exit
    raw = json.dumps(observation, sort_keys=True, separators=(",", ":"))
    request.node.user_properties.append(("sinter_wrapper_diagnostics", raw))
    assert not observation["timed_out"] and observation["parent_exited"], raw
    assert observation["cleanup_errors"] == [], raw
    assert observation["returncode"] == (0 if probe_exit == 0 else 3), raw
    assert stdout.strip() == f"observed-probe-exit={probe_exit}".encode(), raw
