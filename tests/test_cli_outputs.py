"""CLI export admission and failure recovery, without speech or remote work."""
import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sinter import cli, outputs, review


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    project = tmp_path / "project.json"
    project.write_text(json.dumps({
        "workflow": "research", "title": "Garden access",
        "notes": "The garden entrance is on River Road. Access is not confirmed.",
    }), encoding="utf-8")
    audio = tmp_path / "recording.wav"
    audio.write_bytes(b"Fictional audio bytes; never sent to a speech engine.")
    directory = tmp_path / ".sinter" / "templates"
    directory.mkdir(parents=True)
    template = directory / "fictional.json"
    template.write_text(json.dumps({
        "name": "Fictional", "steps": [{"name": "Draft", "prompt": "Fictional"}],
    }), encoding="utf-8")
    return {"workbench": project, "transcribe": audio, "template": template}


def arguments(command: str, inputs: dict) -> list[str]:
    if command == "template":
        return [command, "user:fictional", "--no-stream"]
    if command == "research":
        return [command, "Garden access"]
    return [command, str(inputs[command])]


@contextmanager
def no_expensive_work():
    with patch("sinter.workbench.run") as workflow, patch(
        "sinter.speech.transcribe",
    ) as speech, patch("sinter.templates.template_events") as template:
        yield
    workflow.assert_not_called()
    speech.assert_not_called()
    template.assert_not_called()


@pytest.mark.parametrize("command", ["workbench", "transcribe", "template"])
@pytest.mark.parametrize("alias", ["same", "hardlink", "symlink"])
def test_exports_reject_source_alias_before_work(inputs, tmp_path, capsys, command, alias):
    source = inputs[command]
    original = source.read_bytes()
    target = source if alias == "same" else tmp_path / "report.md"
    if alias == "hardlink":
        os.link(source, target)
    elif alias == "symlink":
        target.symlink_to(source)
    with no_expensive_work(), pytest.raises(SystemExit) as exited:
        cli.main(arguments(command, inputs) + ["-o", str(target)])
    assert exited.value.code == 1
    assert source.read_bytes() == original
    assert target.read_bytes() == original
    assert "Sinter:" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["workbench", "transcribe"])
def test_symlinked_input_cannot_be_overwritten(inputs, tmp_path, command):
    source = inputs[command]
    original = source.read_bytes()
    link = tmp_path / "input-link"
    link.symlink_to(source)
    with no_expensive_work(), pytest.raises(SystemExit) as exited:
        cli.main([command, str(link), "-o", str(source)])
    assert exited.value.code == 1
    assert source.read_bytes() == original


@pytest.mark.parametrize("command", ["workbench", "transcribe", "research", "template"])
@pytest.mark.parametrize("kind", [
    "directory", "fifo", "missing-parent", "file-parent", "symlink", "dangling-link",
])
def test_invalid_export_paths_fail_before_work(inputs, tmp_path, capsys, command, kind):
    target = tmp_path / "output"
    if kind == "directory":
        target.mkdir()
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("Named pipes require POSIX.")
        os.mkfifo(target)
    elif kind == "missing-parent":
        target = tmp_path / "absent" / "output.md"
    elif kind == "file-parent":
        target.write_text("A file cannot contain another file.")
        target = target / "output.md"
    elif kind in {"symlink", "dangling-link"}:
        other = tmp_path / "unrelated.txt"
        if kind == "symlink":
            other.write_text("Preserve unrelated work.")
        target.symlink_to(other)
    with no_expensive_work(), pytest.raises(SystemExit) as exited:
        cli.main(arguments(command, inputs) + ["-o", str(target)])
    assert exited.value.code == 1
    assert "Sinter:" in capsys.readouterr().err
    if kind == "symlink":
        assert other.read_text() == "Preserve unrelated work."


def test_unwritable_parent_rejected_before_work(inputs, tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX directory mode bits are not Windows ACLs.")
    parent = tmp_path / "read-only"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        if os.access(parent, os.W_OK):
            pytest.skip("The test user can override directory permissions.")
        with no_expensive_work(), pytest.raises(SystemExit) as exited:
            cli.main(arguments("workbench", inputs) + ["-o", str(parent / "out.md")])
        assert exited.value.code == 1
    finally:
        parent.chmod(0o700)


@pytest.mark.parametrize("command, default", [
    ("workbench", "sinter_report.md"), ("transcribe", "transcript.json"),
])
def test_default_export_name_cannot_overwrite_source(inputs, tmp_path, command, default):
    original = inputs[command].read_bytes()
    source = tmp_path / default
    source.write_bytes(original)
    with no_expensive_work(), pytest.raises(SystemExit) as exited:
        cli.main([command, str(source)])
    assert exited.value.code == 1
    assert source.read_bytes() == original


def test_invalid_output_is_checked_before_reading_workbench_json(inputs, tmp_path, capsys):
    inputs["workbench"].write_text("Not JSON")
    with no_expensive_work(), pytest.raises(SystemExit):
        cli.main(arguments("workbench", inputs) + ["-o", str(tmp_path / "absent" / "out")])
    assert "output directory" in capsys.readouterr().err


@pytest.mark.parametrize("suffix", [".md", ".json", ".JSON"])
def test_successful_workbench_exports_keep_their_input(inputs, tmp_path, suffix):
    source = inputs["workbench"]
    original = source.read_bytes()
    target = tmp_path / ("report" + suffix)
    target.write_text("Old deliverable")
    cli.main(["workbench", "~/project.json", "-o", str(target)])
    content = target.read_text(encoding="utf-8")
    if suffix.lower() == ".json":
        report = json.loads(content)
        assert report["workflow"] == "research"
        content = report["markdown"]
    assert "River Road" in content
    assert source.read_bytes() == original
    assert not list(tmp_path.glob(".sinter-output-*"))


@pytest.mark.parametrize("format", ["json", "txt", "srt", "vtt"])
def test_successful_transcript_formats_keep_audio(inputs, tmp_path, format):
    source = inputs["transcribe"]
    original = source.read_bytes()
    transcript = {"segments": [{
        "id": "T0001", "start": 0, "end": 1.5, "speaker": "Unidentified",
        "text": "Fictional words for export.",
    }]}
    with patch("sinter.speech.transcribe", return_value=transcript) as speech:
        cli.main(["transcribe", "~/recording.wav", "--consent", "--format", format])
    assert speech.call_args.args[0] == source
    content = (tmp_path / f"transcript.{format}").read_text(encoding="utf-8")
    assert "Fictional words for export." in content
    if format == "json":
        assert json.loads(content) == transcript
    elif format in {"srt", "vtt"}:
        assert " --> " in content
    assert source.read_bytes() == original


@pytest.mark.parametrize("failure", ["write", "fsync", "replace", "encoding", "create"])
def test_failed_atomic_export_preserves_deliverable_and_only_cleans_owned_temp(
    tmp_path, monkeypatch, capsys, failure,
):
    target = tmp_path / "report.md"
    target.write_bytes(b"Original deliverable\n")
    unrelated = tmp_path / ".sinter-output-unrelated"
    unrelated.write_bytes(b"Other user's temporary work")
    content = "A complete new deliverable: café\n"
    if failure == "write":
        create = outputs.tempfile.NamedTemporaryFile

        @contextmanager
        def failing_writer(**kwargs):
            with create(**kwargs) as stream:
                def write(value):
                    stream.write(value[:8])
                    raise OSError("Fictional full disk during write")
                yield SimpleNamespace(name=stream.name, write=write)

        monkeypatch.setattr(outputs.tempfile, "NamedTemporaryFile", failing_writer)
    elif failure in {"fsync", "replace", "create"}:
        owner, name = ((outputs.tempfile, "NamedTemporaryFile") if failure == "create"
                       else (outputs.os, failure))
        def fail(*args, **kwargs):
            raise OSError("Fictional storage failure")
        monkeypatch.setattr(owner, name, fail)
    else:
        content += "\ud800"
    with pytest.raises((OSError, UnicodeError)):
        cli._write(target, content)
    assert target.read_bytes() == b"Original deliverable\n"
    assert unrelated.read_bytes() == b"Other user's temporary work"
    assert sorted(path.name for path in tmp_path.iterdir()) == [unrelated.name, target.name]
    assert "Saved:" not in capsys.readouterr().out


def test_atomic_export_rechecks_target_after_writing(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("Preserve original source")
    target = tmp_path / "report.md"
    monkeypatch.setattr(outputs.os, "fsync", lambda descriptor: os.link(source, target))
    with pytest.raises(ValueError, match="overwrite your source"):
        outputs.atomic_write_text(target, "New report", sources=(source,))
    assert target.samefile(source)
    assert source.read_text() == "Preserve original source"
    assert not list(tmp_path.glob(".sinter-output-*"))


def test_atomic_export_uses_same_directory_and_replaces_once(tmp_path):
    target = tmp_path / "report.md"
    target.write_text("Old deliverable")
    replace = os.replace
    with patch.object(outputs.os, "replace", wraps=replace) as replacement:
        cli._write(target, "Complete UTF-8 deliverable: café\n")
    temporary, destination = replacement.call_args.args
    assert temporary.parent == target.parent
    assert destination == target
    assert replacement.call_count == 1
    assert target.read_bytes() == "Complete UTF-8 deliverable: café\n".encode()
    assert not temporary.exists()


def test_checkpoint_serialization_failure_preserves_previous_receipt(tmp_path):
    target = tmp_path / "report.checkpoint.json"
    review.atomic_save(target, {"saved": "progress"})
    original = target.read_bytes()
    with pytest.raises(ValueError):
        review.atomic_save(target, {"invalid": float("nan")})
    assert target.read_bytes() == original
    assert list(tmp_path.iterdir()) == [target]
