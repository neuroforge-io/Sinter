"""Fixture diagnostics and selector logic; no Windows qualification is implied."""

import builtins
import json
import os
import sys
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
