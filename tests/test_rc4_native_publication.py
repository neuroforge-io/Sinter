"""SOURCE-only diagnostic fault controls; no browser, app, Docker or provider runs."""

from __future__ import annotations

import base64
import builtins
import copy
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import rc4_native_handoff as native
from tools import rc4_replacement_probe as evidence


def fail(error):
    raise error


def raw(value):
    return (
        (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + "\n")
        .replace("\n", os.linesep)
        .encode()
    )


def assert_bytes(error, path, expected):
    retained = error.unpublished_bytes[str(path)]
    assert retained == expected
    record = error.as_record()["unpublished_bytes"][str(path)]
    assert record["bytes"] == len(expected)
    assert record["sha256"] == hashlib.sha256(expected).hexdigest()
    assert base64.b64decode(record["data_base64"]) == expected


def outer_setup(monkeypatch, primary, *, read_error=None):
    monkeypatch.setattr(
        native, "handoff_lifecycle", lambda *_: fail(primary) if primary else "owned"
    )
    monkeypatch.setattr(
        native.native,
        "binary_digest",
        lambda *_: fail(read_error) if read_error else "a" * 64,
    )
    monkeypatch.setattr(native.owner, "records_hash", lambda *_: "b" * 64)
    return {name: {"bytes": 1, "sha256": "c" * 64} for name in native.contract.FILES}


def outer_call(folder, records):
    return native.observe_handoff_outer(
        folder,
        {},
        {},
        [],
        [{"original": "e\u0301 🐝"}],
        [],
        Path("/never-executed/chrome"),
        {"path": "/never-executed/docker"},
        records,
    )


def test_outer_full_bytes_survive_original_and_all_failed_writes(tmp_path, monkeypatch):
    first = RuntimeError("FIRST lifecycle e\u0301 🐝")
    records = outer_setup(monkeypatch, first)
    attempts = []

    def denied(path, value):
        attempts.append((path, copy.deepcopy(value)))
        raise OSError("cannot retain " + path.name)

    monkeypatch.setattr(native, "write_json", denied)
    with pytest.raises(evidence.EvidenceFailure) as caught:
        outer_call(tmp_path, records)
    error = caught.value
    assert error.primary_exception is first and error.__cause__ is first
    assert [path.name for path, _ in attempts] == [
        "client-commands.json",
        "outer.json",
        "outer-unpublished.json",
    ]
    for path, value in attempts:
        assert_bytes(error, path, raw(value))
    assert error.published_paths == () and not list(tmp_path.iterdir())
    assert [json.loads(row)["role"] for row in error.cleanup_errors] == [
        "retain-client-commands",
        "retain-handoff-outer",
    ]
    assert error.as_record()["schema"] == "sinter-native-handoff-failed-evidence/v1"


@pytest.mark.parametrize("body", [False, True])
@pytest.mark.parametrize("which", ["client", "outer", "both"])
def test_outer_attempts_every_later_publication_once(
    tmp_path, monkeypatch, body, which
):
    first = RuntimeError("first body") if body else None
    records = outer_setup(monkeypatch, first)
    original_write, attempts = native.write_json, []

    def write(path, value):
        attempts.append((path, copy.deepcopy(value)))
        if path.name == "client-commands.json" and which in {"client", "both"}:
            raise OSError("client write")
        if path.name == "outer.json" and which in {"outer", "both"}:
            raise OSError("outer write")
        original_write(path, value)

    monkeypatch.setattr(native, "write_json", write)
    with pytest.raises(evidence.EvidenceFailure) as caught:
        outer_call(tmp_path, records)
    error = caught.value
    assert [path.name for path, _ in attempts] == [
        "client-commands.json",
        "outer.json",
        "outer-unpublished.json",
    ]
    expected = (
        "first body"
        if body
        else ("outer write" if which == "outer" else "client write")
    )
    assert str(error.primary_exception) == expected
    for path, value in attempts:
        if str(path) in error.unpublished_bytes:
            assert_bytes(error, path, raw(value))
            assert str(path) not in error.published_paths
        else:
            assert (
                path.read_bytes() == raw(value) and str(path) in error.published_paths
            )


def test_outer_first_read_fault_and_complete_secondary_outcomes(tmp_path, monkeypatch):
    first = OSError("FIRST fingerprint read")
    records = outer_setup(monkeypatch, None, read_error=first)
    monkeypatch.setattr(
        native.owner, "records_hash", lambda *_: fail(ValueError("later manifest read"))
    )
    monkeypatch.setattr(native, "write_json", lambda *_: fail(OSError("later write")))
    with pytest.raises(evidence.EvidenceFailure) as caught:
        outer_call(tmp_path, records)
    error = caught.value
    assert error.primary_exception is first
    assert [json.loads(row)["role"] for row in error.cleanup_errors] == [
        "observe-docker-after",
        "retain-client-commands",
        "observe-source-manifest",
        "retain-handoff-outer",
    ]
    assert len(error.publication_errors) == 3
    assert (
        json.loads(error.unpublished_bytes[str(tmp_path / "outer.json")])[
            "docker_client"
        ]["sha256_after"]
        is None
    )


def owner_args(tmp_path, monkeypatch):
    owned, inputs = tmp_path / "owned", tmp_path / "inputs"
    owned.mkdir(mode=0o700)
    inputs.mkdir()
    chromium = inputs / "never-executed-chromium"
    chromium.write_bytes(b"fictional SOURCE test input, not an executable")
    chromium.chmod(0o700)
    # This is an inert Linux dispatch control on every test platform. Fictional
    # preflight metadata cannot establish actual host/installation qualification.
    original_stat = Path.stat

    def stat(path, *args, **kwargs):
        observed = original_stat(path, *args, **kwargs)
        if path == owned:
            fields = list(observed)
            fields[0] &= ~0o022
            fields[4] = 1000
            return os.stat_result(fields)
        return observed

    monkeypatch.setattr(native.platform, "system", lambda: "Linux")
    monkeypatch.setattr(native.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(Path, "stat", stat)
    monkeypatch.setattr(native.contract, "HOST_CHROMIUM", chromium)
    monkeypatch.setattr(native.native, "binary_digest", lambda *_: "a" * 64)
    return SimpleNamespace(
        output=owned / "proof",
        repository=inputs / "repository",
        installer=inputs / "candidate.deb",
        package_receipt=inputs / "package.json",
        chromium=chromium,
        chromium_sha256="a" * 64,
        producer_sha256=hashlib.sha256(
            (native.ROOT / native.contract.FILES[0]).read_bytes()
        ).hexdigest(),
        contract_sha256=hashlib.sha256(
            (native.ROOT / native.contract.FILES[1]).read_bytes()
        ).hexdigest(),
        owner_sha256="b" * 64,
        source_commit="c" * 40,
        qualification="dev",
    )


def test_owner_final_bytes_preserve_first_baseline_failure(tmp_path, monkeypatch):
    args = owner_args(tmp_path, monkeypatch)
    first = RuntimeError("FIRST baseline e\u0301 🐝")
    monkeypatch.setattr(native.owner, "run", lambda *_: fail(first))
    original_write, attempts = native.write_json, []

    def write(path, value):
        attempts.append((path, copy.deepcopy(value)))
        if len(attempts) >= 2:
            raise OSError("final and fallback publication denied")
        original_write(path, value)

    monkeypatch.setattr(native, "write_json", write)
    with pytest.raises(evidence.EvidenceFailure) as caught:
        native.run(args)
    error = caught.value
    assert error.primary_exception is first and error.__cause__ is first
    assert len(attempts) == 3
    assert json.loads((args.output / "owner-run.json").read_bytes())["passed"] is False
    assert_bytes(error, attempts[1][0], raw(attempts[1][1]))
    assert attempts[1][1]["error"] == str(first)
    assert_bytes(error, attempts[2][0], raw(attempts[2][1]))


def test_owner_initial_failed_write_never_dispatches(tmp_path, monkeypatch):
    args = owner_args(tmp_path, monkeypatch)
    calls = []
    first = OSError("initial write")
    monkeypatch.setattr(native.owner, "run", lambda *_: calls.append("NOT ALLOWED"))
    monkeypatch.setattr(native, "write_json", lambda *_: fail(first))
    with pytest.raises(evidence.EvidenceFailure) as caught:
        native.run(args)
    assert caught.value.primary_exception is first and calls == []
    assert len(caught.value.unpublished_bytes) == 2


def test_owner_ordinary_body_failure_keeps_existing_one_exit_and_context(
    tmp_path, monkeypatch
):
    args = owner_args(tmp_path, monkeypatch)
    monkeypatch.setattr(
        native.owner, "run", lambda *_: fail(RuntimeError("baseline refused"))
    )
    assert native.run(args) == 1
    value = json.loads((args.output / "owner-run.json").read_bytes())
    assert value == {
        "schema": "sinter-native-handoff-owner-run/v1",
        "passed": False,
        "boundary": (
            "Actual installed run only when all proofs admit; DEV is not a release."
        ),
        "error_type": "RuntimeError",
        "error": "baseline refused",
    }
    assert not (args.output / "owner-run-unpublished.json").exists()


def browser_setup(folder, monkeypatch, primary, *, later_read=None):
    root = folder / "handoff-container/out/handoff"
    root.mkdir(parents=True)
    (root.parent.parent / "client").mkdir()
    inert = SimpleNamespace(
        expect=lambda *_: None,
        sync_playwright=lambda: fail(
            AssertionError("No Playwright execution permitted")
        ),
    )
    monkeypatch.setitem(sys.modules, "playwright", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", inert)
    monkeypatch.setattr(native, "wait_file", lambda *_: {})
    digests = iter(["a" * 64, later_read or "a" * 64])

    def digest(*_):
        value = next(digests)
        return fail(value) if isinstance(value, BaseException) else value

    monkeypatch.setattr(native.native, "binary_digest", digest)
    monkeypatch.setattr(native, "children", lambda: fail(primary))
    return root


def test_browser_full_bytes_and_environment_survive_read_and_write_faults(
    tmp_path, monkeypatch
):
    first = OSError("FIRST actual source-controlled read")
    later = OSError("later digest read")
    root = browser_setup(tmp_path, monkeypatch, first, later_read=later)
    old_tmp = os.environ.get("TMPDIR")
    attempts = []

    def denied(path, value):
        attempts.append((path, copy.deepcopy(value)))
        raise OSError("write denied " + path.name)

    monkeypatch.setattr(native, "write_json", denied)
    with pytest.raises(evidence.EvidenceFailure) as caught:
        native.browser(root, Path("/never-executed/chromium"))
    error = caught.value
    assert error.primary_exception is first and error.__cause__ is first
    assert os.environ.get("TMPDIR") == old_tmp
    assert [path.name for path, _ in attempts] == [
        "browser.json",
        "browser-unpublished.json",
    ]
    for path, value in attempts:
        assert_bytes(error, path, raw(value))
    assert [json.loads(row)["role"] for row in error.cleanup_errors] == [
        "observe-chromium-after",
        "retain-browser-proof",
    ]
    assert attempts[0][1]["error"] == str(first)


def test_browser_normal_error_preserves_original_and_exact_json(tmp_path, monkeypatch):
    first = RuntimeError("first read")
    root = browser_setup(tmp_path, monkeypatch, first)
    with pytest.raises(RuntimeError) as caught:
        native.browser(root, Path("/never-executed/chromium"))
    assert caught.value is first
    path = root.parent.parent / "browser.json"
    value = json.loads(path.read_bytes())
    assert path.read_bytes() == raw(value) and value["error"] == str(first)
    assert not path.with_name("browser-unpublished.json").exists()


def test_real_browser_dependency_refusal_remains_explicit(tmp_path, monkeypatch):
    original_import = builtins.__import__
    first = ModuleNotFoundError("Optional Playwright is unavailable")
    calls = []

    def importing(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise first
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    monkeypatch.setattr(native, "wait_file", lambda *_: calls.append("NOT PERMITTED"))
    with pytest.raises(ModuleNotFoundError) as caught:
        native.browser(tmp_path, Path("/never-executed/chromium"))
    assert caught.value is first and calls == [] and not list(tmp_path.iterdir())


@pytest.mark.parametrize("fault", ["partial-write", "close", "rename"])
def test_real_private_file_faults_keep_full_serialized_bytes(
    tmp_path, monkeypatch, fault
):
    path, fallback = tmp_path / "diagnostic.json", tmp_path / "unpublished.json"
    value = {"original": "e\u0301 🐝", "lines": ["one", "two"], "passed": False}
    first = OSError("actual " + fault)
    original_open, original_replace = Path.open, Path.replace

    class FaultingFile:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def write(self, text):
            if fault == "partial-write":
                self.stream.write(text[:9])
                self.stream.flush()
                raise first
            return self.stream.write(text)

        def __exit__(self, *_):
            self.stream.close()
            if fault == "close":
                raise first

    def opened(candidate, *args, **kwargs):
        stream = original_open(candidate, *args, **kwargs)
        mode = kwargs.get("mode", args[0] if args else "r")
        return (
            FaultingFile(stream)
            if candidate.suffix == ".tmp" and "w" in mode
            else stream
        )

    def renamed(candidate, target):
        if candidate.suffix == ".tmp":
            raise first
        return original_replace(candidate, target)

    if fault == "rename":
        monkeypatch.setattr(Path, "replace", renamed)
    else:
        monkeypatch.setattr(Path, "open", opened)
    publisher = native.diagnostic_publisher("SOURCE-FILE-FAULT", None, [])
    assert publisher.attempt(path, value) is False
    with pytest.raises(evidence.EvidenceFailure) as caught:
        native.finish_diagnostics(publisher, fallback, None, [])
    error = caught.value
    assert (
        error.primary_exception is first and not path.exists() and not fallback.exists()
    )
    assert_bytes(error, path, raw(value))
    temporary = path.with_suffix(".json.tmp")
    partial = raw(value).decode().replace(os.linesep, "\n")[:9]
    expected_partial = partial.replace("\n", os.linesep).encode()
    assert temporary.read_bytes() == (
        expected_partial if fault == "partial-write" else raw(value)
    )
    assert len(error.publication_errors) == 2 and error.published_paths == ()


@pytest.mark.parametrize("fault", ["missing-file", "directory"])
def test_genuine_private_read_failure_is_not_masked_by_final_publication(
    tmp_path, monkeypatch, fault
):
    root = browser_setup(tmp_path, monkeypatch, RuntimeError("unused"))
    source = tmp_path / "fictional-source"
    if fault == "directory":
        source.mkdir()
    observed = []

    def read():
        try:
            source.read_bytes()
        except OSError as error:
            observed.append(error)
            raise

    monkeypatch.setattr(native, "children", read)
    monkeypatch.setattr(
        native, "write_json", lambda *_: fail(OSError("final write denied"))
    )
    with pytest.raises(evidence.EvidenceFailure) as caught:
        native.browser(root, Path("/never-executed/chromium"))
    assert len(observed) == 1 and caught.value.primary_exception is observed[0]
    value = json.loads(
        caught.value.unpublished_bytes[str(root.parent.parent / "browser.json")]
    )
    assert value["error_type"] == type(observed[0]).__name__
    assert value["error"] == str(observed[0])


def test_compound_actual_write_and_close_preserve_first_and_each_later_fault(
    tmp_path, monkeypatch
):
    first, later = OSError("FIRST actual write"), OSError("LATER actual close")
    original_open = Path.open

    class File:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def write(self, text):
            self.stream.write(text[:9])
            self.stream.flush()
            raise first

        def __exit__(self, *_):
            self.stream.close()
            raise later

    def opened(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        mode = kwargs.get("mode", args[0] if args else "r")
        return File(stream) if path.suffix == ".tmp" and "w" in mode else stream

    monkeypatch.setattr(Path, "open", opened)
    publisher = native.diagnostic_publisher("SOURCE-COMPOUND", None, [])
    path, fallback = tmp_path / "diagnostic.json", tmp_path / "unpublished.json"
    value = {"original": "e\u0301 🐝"}
    assert publisher.attempt(path, value) is False
    with pytest.raises(evidence.EvidenceFailure) as caught:
        native.finish_diagnostics(publisher, fallback, None, [])
    error = caught.value
    assert error.primary_exception is first and error.__cause__ is first
    assert [(row["path"], row["error"]) for row in error.publication_errors] == [
        (str(path), str(first)),
        (str(path), str(later)),
        (str(fallback), str(first)),
        (str(fallback), str(later)),
    ]
    assert_bytes(error, path, raw(value))
    assert len(error.unpublished_bytes) == 2 and error.published_paths == ()


def test_handled_unrelated_context_is_not_reclassified_as_publication_failure(
    tmp_path, monkeypatch
):
    unrelated, actual = (
        RuntimeError("handled before publication"),
        OSError("actual write"),
    )
    monkeypatch.setattr(native, "write_json", lambda *_: fail(actual))
    try:
        raise unrelated
    except RuntimeError:
        publisher = native.diagnostic_publisher("SOURCE-CONTEXT", None, [])
        publisher.attempt(tmp_path / "original.json", {"original": True})
        with pytest.raises(evidence.EvidenceFailure) as caught:
            native.finish_diagnostics(
                publisher, tmp_path / "unpublished.json", None, []
            )
    assert caught.value.primary_exception is actual
    assert [row["error"] for row in caught.value.publication_errors] == [
        str(actual),
        str(actual),
    ]


def test_outer_normal_success_has_unchanged_sidecars_and_no_failure_record(
    tmp_path, monkeypatch
):
    records = outer_setup(monkeypatch, None)
    assert outer_call(tmp_path, records) == "owned"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "client-commands.json",
        "outer.json",
    ]
    for name in ["client-commands.json", "outer.json"]:
        path = tmp_path / name
        value = json.loads(path.read_bytes())
        assert path.read_bytes() == raw(value)
    value = json.loads((tmp_path / "outer.json").read_bytes())
    assert set(value) == {
        "schema",
        "commands",
        "cleanup_commands",
        "docker_client",
        "source_manifest",
        "source_manifest_sha256",
        "tools",
    }
    assert value["schema"] == "sinter-owned-native-handoff-container/v1"


def test_falsey_original_exception_remains_first(tmp_path, monkeypatch):
    class FalseError(RuntimeError):
        def __bool__(self):
            return False

    first = FalseError("first even if falsey")
    records = outer_setup(monkeypatch, None)
    monkeypatch.setattr(native, "handoff_lifecycle", lambda *_: fail(first))
    monkeypatch.setattr(native, "write_json", lambda *_: fail(OSError("later write")))
    with pytest.raises(evidence.EvidenceFailure) as caught:
        outer_call(tmp_path, records)
    assert caught.value.primary_exception is first


@pytest.mark.parametrize("code", [0, 1])
def test_native_normal_main_preserves_codes_and_empty_streams(
    tmp_path, monkeypatch, capsys, code
):
    monkeypatch.setattr(native, "inside", lambda *_: code)
    assert (
        native.main(
            [
                "_inside",
                "--repository",
                str(tmp_path / "repo"),
                "--installer",
                str(tmp_path / "candidate.deb"),
                "--package-receipt",
                str(tmp_path / "package.json"),
                "--output",
                str(tmp_path / "proof"),
                "--source-commit",
                "c" * 40,
                "--qualification",
                "dev",
            ]
        )
        == code
    )
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_nested_publication_preserves_primary_bytes_and_cleanup_without_replay(
    tmp_path, monkeypatch
):
    first = RuntimeError("original primary")
    attempts = []

    def denied(path, value):
        attempts.append(path.name)
        raise OSError("denied " + path.name)

    monkeypatch.setattr(native, "write_json", denied)
    inner = native.diagnostic_publisher(
        "INNER", first, [{"role": "original-close", "error": "secondary"}]
    )
    inner.attempt(tmp_path / "inner.json", {"original": True})
    with pytest.raises(evidence.EvidenceFailure) as failed:
        native.finish_diagnostics(
            inner,
            tmp_path / "inner-unpublished.json",
            first,
            [{"role": "original-close", "error": "secondary"}],
        )
    original = failed.value
    outer = native.diagnostic_publisher("OUTER", original, [])
    outer.attempt(tmp_path / "outer.json", {"error_type": type(original).__name__})
    with pytest.raises(evidence.EvidenceFailure) as failed_again:
        native.finish_diagnostics(
            outer,
            tmp_path / "outer-unpublished.json",
            original,
            [{"role": "later-close", "error": "later"}],
        )
    result = failed_again.value
    assert result.primary_exception is first and result.__cause__ is first
    assert len(result.publication_errors) == 4
    assert [json.loads(row)["role"] for row in result.cleanup_errors] == [
        "original-close",
        "later-close",
    ]
    assert list(result.unpublished_bytes) == [str(tmp_path / name) for name in attempts]
    assert len(attempts) == len(set(attempts)) == 4
    for path, content in original.unpublished_bytes.items():
        assert result.unpublished_bytes[path] == content


def test_default_publisher_schema_bytes_and_primary_none_are_unchanged(
    tmp_path, monkeypatch
):
    first = OSError("first write")
    monkeypatch.setattr(evidence, "write", lambda *_: fail(first))
    publisher = evidence.EvidencePublisher("OLD-DEFAULT", None, [])
    publisher.attempt(tmp_path / "original.json", {"original": "🐝"})
    with pytest.raises(evidence.EvidenceFailure) as caught:
        publisher.finish(tmp_path / "failed.json")
    error = caught.value
    assert error.primary_exception is None and error.__cause__ is first
    assert error.as_record()["schema"] == "sinter-rc4-replacement-failed-evidence/v1"
    assert (
        error.unpublished_bytes[str(tmp_path / "original.json")]
        == (evidence.encoded({"original": "🐝"}) + "\n").encode()
    )
    nested = evidence.EvidencePublisher("OLD-NESTED", error, [])
    assert nested.primary is error and nested.published == [] and nested.cleanup == []


@pytest.mark.parametrize("fault", ["none", "write", "short", "flush"])
def test_native_cli_nonzero_retains_original_complete_bytes_even_if_stderr_fails(
    tmp_path, monkeypatch, fault
):
    first = RuntimeError("FIRST cli e\u0301 🐝")
    monkeypatch.setattr(native, "write_json", lambda *_: fail(OSError("disk denied")))
    publisher = native.diagnostic_publisher("CLI-SOURCE", first, [])
    publisher.attempt(tmp_path / "original.json", {"original": str(first)})
    with pytest.raises(evidence.EvidenceFailure) as failed:
        native.finish_diagnostics(publisher, tmp_path / "unpublished.json", first, [])
    error = failed.value
    monkeypatch.setattr(native, "run", lambda *_: fail(error))
    buffer = io.BytesIO()

    class Stream:
        def write(self, payload):
            if fault == "write":
                raise OSError("stderr write denied")
            if fault == "short":
                return buffer.write(payload[:7])
            return buffer.write(payload)

        def flush(self):
            if fault == "flush":
                raise OSError("stderr flush denied")

    monkeypatch.setattr(native.sys, "stderr", SimpleNamespace(buffer=Stream()))
    previous_handler = native.signal.getsignal(native.signal.SIGTERM)
    with pytest.raises(SystemExit) as stopped:
        native.main(
            [
                "run",
                "--repository",
                str(tmp_path / "repo"),
                "--installer",
                str(tmp_path / "candidate.deb"),
                "--package-receipt",
                str(tmp_path / "package.json"),
                "--output",
                str(tmp_path / "proof"),
                "--source-commit",
                "c" * 40,
                "--qualification",
                "dev",
                "--owner-sha256",
                "b" * 64,
                "--producer-sha256",
                "a" * 64,
                "--contract-sha256",
                "d" * 64,
                "--chromium",
                "/never-executed/chromium",
                "--chromium-sha256",
                "e" * 64,
            ]
        )
    assert stopped.value.code == 1 and stopped.value.__cause__ is error
    assert error.primary_exception is first
    assert native.signal.getsignal(native.signal.SIGTERM) == previous_handler
    if fault == "none":
        record = json.loads(buffer.getvalue())
        assert record == error.as_record()
    else:
        assert error.publication_errors[-1]["path"] == "<stderr>"
        record = json.loads(error.unpublished_bytes["<stderr>"])
        assert record["first_failure"] == str(first)
    for path in [tmp_path / "original.json", tmp_path / "unpublished.json"]:
        content = error.unpublished_bytes[str(path)]
        retained = record["unpublished_bytes"][str(path)]
        assert base64.b64decode(retained["data_base64"]) == content
        assert retained["bytes"] == len(content)
        assert retained["sha256"] == hashlib.sha256(content).hexdigest()


def envelope_failure(tmp_path, *, filesystem_byte=False):
    """Real owned write refusals; byte filenames execute where POSIX supports them."""
    if filesystem_byte and os.name == "posix":
        parent = tmp_path / "e\u0301-🐝"
        parent.mkdir()
        path = Path(os.fsdecode(os.fsencode(parent) + b"/owned-\xff"))
    else:
        path = tmp_path / "owned-e\u0301-🐝"
    path.mkdir()
    fallback = tmp_path / "fallback-directory"
    fallback.mkdir()
    cleanup = ["surrogate filename e\u0301 🐝 marker \udcff"] if filesystem_byte else []
    publisher = native.diagnostic_publisher("ENVELOPE-SOURCE", None, cleanup)
    publisher.attempt(path, {"original": "e\u0301 🐝", "source": str(path)})
    first = publisher.exceptions[0]
    assert isinstance(first, OSError)
    with pytest.raises(evidence.EvidenceFailure) as failed:
        publisher.finish(fallback)
    error = failed.value
    assert error.primary_exception is first and error.__cause__ is first
    assert list(error.unpublished_bytes) == [str(path), str(fallback)]
    assert error.published_paths == ()
    return error, first, path


def envelope_cli(tmp_path, monkeypatch, error, stream):
    monkeypatch.setattr(native, "run", lambda *_: fail(error))
    monkeypatch.setattr(native.sys, "stderr", SimpleNamespace(buffer=stream))
    previous_handler = native.signal.getsignal(native.signal.SIGTERM)
    with pytest.raises(SystemExit) as stopped:
        native.main(
            [
                "run",
                "--repository",
                str(tmp_path / "repo"),
                "--installer",
                str(tmp_path / "candidate.deb"),
                "--package-receipt",
                str(tmp_path / "package.json"),
                "--output",
                str(tmp_path / "proof"),
                "--source-commit",
                "c" * 40,
                "--qualification",
                "dev",
                "--owner-sha256",
                "b" * 64,
                "--producer-sha256",
                "a" * 64,
                "--contract-sha256",
                "d" * 64,
                "--chromium",
                "/never-executed/chromium",
                "--chromium-sha256",
                "e" * 64,
            ]
        )
    assert stopped.value.code == 1 and stopped.value.__cause__ is error
    assert native.signal.getsignal(native.signal.SIGTERM) == previous_handler


def envelope_originals(error, record, originals, first):
    assert error.primary_exception is first
    assert record["first_failure"] == str(first)
    for path, content in originals.items():
        assert error.unpublished_bytes[path] == content
        row = record["unpublished_bytes"][path]
        assert base64.b64decode(row["data_base64"]) == content
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()


def test_envelope_valid_unicode_bytes_are_exactly_unchanged(tmp_path):
    error, first, _path = envelope_failure(tmp_path)
    original = error.as_record()
    expected = (evidence.encoded(original) + "\n").encode("utf-8")
    buffer = io.BytesIO()
    assert evidence.emit_failure(error, buffer) == buffer.getvalue() == expected
    assert error.primary_exception is first and error.as_record() == original


@pytest.mark.parametrize("fault", ["none", "write", "short", "flush"])
def test_envelope_owned_byte_filename_and_stderr_refusals(tmp_path, monkeypatch, fault):
    error, first, path = envelope_failure(tmp_path, filesystem_byte=True)
    originals = dict(error.unpublished_bytes)
    buffer = io.BytesIO()

    class Stream:
        def write(self, payload):
            if fault == "write":
                raise OSError("owned stderr refused \udcff")
            return buffer.write(payload[:11] if fault == "short" else payload)

        def flush(self):
            if fault == "flush":
                raise OSError("owned stderr flush refused \udcff")

    envelope_cli(tmp_path, monkeypatch, error, Stream())
    payload = (
        buffer.getvalue() if fault == "none" else error.unpublished_bytes["<stderr>"]
    )
    payload.decode("utf-8", "strict")
    record = json.loads(payload)
    envelope_originals(error, record, originals, first)
    assert {os.fsencode(key) for key in record["unpublished_bytes"]} == {
        os.fsencode(key) for key in originals
    }
    assert b"\\udcff" in payload and "🐝".encode() in payload
    if os.name == "posix":
        assert os.fsencode(path).endswith(b"owned-\xff")
    if fault == "none":
        assert record == error.as_record()
    else:
        assert error.publication_errors[-1]["path"] == "<stderr>"


@pytest.mark.parametrize("render", ["record-once", "encode", "record-always", "both"])
@pytest.mark.parametrize("delivery", ["none", "write", "flush"])
def test_envelope_rendering_faults_preserve_typed_cause_and_full_originals(
    tmp_path, monkeypatch, render, delivery
):
    error, first, _path = envelope_failure(tmp_path, filesystem_byte=True)
    originals = dict(error.unpublished_bytes)
    original_record = error.as_record
    attempts, writes, flushes = [], [], []
    buffer = io.BytesIO()

    def refused_record():
        attempts.append("record")
        if render == "record-always" or len(attempts) == 1:
            raise OSError("source record rendering refused \udcff")
        return original_record()

    if render.startswith("record"):
        monkeypatch.setattr(error, "as_record", refused_record)
    else:
        monkeypatch.setattr(
            evidence,
            "encoded",
            lambda *_: fail(UnicodeError("source renderer refused")),
        )
    if render == "both":
        monkeypatch.setattr(
            evidence.json,
            "dumps",
            lambda *_a, **_k: fail(OSError("ASCII fallback refused")),
        )

    class Stream:
        def write(self, payload):
            writes.append(payload)
            if delivery == "write":
                raise OSError("later stderr write refused")
            return buffer.write(payload)

        def flush(self):
            flushes.append(True)
            if delivery == "flush":
                raise OSError("later stderr flush refused")

    envelope_cli(tmp_path, monkeypatch, error, Stream())
    assert error.primary_exception is first and error.__cause__ is first
    paths = [row["path"] for row in error.publication_errors]
    assert "<stderr-render>" in paths
    if render in {"record-always", "both"}:
        assert paths[-2:] == ["<stderr-render>", "<stderr-render-fallback>"]
        assert writes == flushes == []
        assert "<stderr>" not in error.unpublished_bytes
        record = original_record()
    else:
        assert len(writes) == 1
        if delivery == "none":
            record = json.loads(buffer.getvalue())
            assert record == original_record() and flushes == [True]
        else:
            assert paths[-1] == "<stderr>"
            record = json.loads(error.unpublished_bytes["<stderr>"])
    envelope_originals(error, record, originals, first)
